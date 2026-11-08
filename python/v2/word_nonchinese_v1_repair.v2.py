"""增量修复 complete-v1 多语言 JSON，输出到暂存区，不覆盖正式结果。

EN: Incrementally repair complete-v1 multilingual JSON, outputting to the staging area without overwriting the formal results.

JA: complete-v1 の多言語 JSON を増分で修復し、一時保存領域に出力する。正式な結果は上書きしない。
"""

from __future__ import annotations

import argparse
import copy
import json
import os
from collections import Counter
from pathlib import Path
from typing import Any

from reuse_complete_v1_jsons import validate_json
from run_chinese_html_to_json import canonicalize_complete_schema, rebuild_raw_text


def norm_path(value: str) -> str:
    return os.path.normcase(os.path.normpath(str(value or "")))


def repair_payload(payload: dict[str, Any], source_path: str) -> dict[str, Any]:
    repaired = copy.deepcopy(payload)
    structured = canonicalize_complete_schema(dict(repaired.get("structured_data") or {}))
    repaired["structured_data"] = structured
    repaired["raw_text"] = rebuild_raw_text(structured.get("resumes") or [])
    source = repaired.setdefault("source", {})
    source["original_path"] = source_path
    return repaired


def unique_destination(directory: Path, filename: str, reserved: set[str]) -> Path:
    stem, suffix = Path(filename).stem, Path(filename).suffix or ".json"
    candidate = directory / f"{stem}{suffix}"
    sequence = 2
    while candidate.name.casefold() in reserved or candidate.exists():
        candidate = directory / f"{stem}_{sequence}{suffix}"
        sequence += 1
    reserved.add(candidate.name.casefold())
    return candidate


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reuse-report", type=Path, required=True)
    parser.add_argument("--map", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    reuse = json.loads(args.reuse_report.read_text(encoding="utf-8"))
    map_rows = json.loads(args.map.read_text(encoding="utf-8"))
    map_by_source = {norm_path(row.get("source_path", "")): row for row in map_rows}
    items: list[dict[str, Any]] = []
    summary: Counter[str] = Counter()
    reserved_by_folder: dict[str, set[str]] = {}

    for old in reuse.get("items") or []:
        folder = str(old.get("language_folder") or "")
        if folder == "中文" or old.get("status") != "json_invalid":
            continue
        source_path = str(old.get("source_path") or "")
        candidate = Path(str(old.get("candidate_json") or ""))
        row = map_by_source.get(norm_path(source_path), {})
        result: dict[str, Any] = {
            "source_path": source_path,
            "language_folder": folder,
            "candidate_json": str(candidate),
            "previous_issues": old.get("issues") or [],
        }
        try:
            payload = json.loads(candidate.read_text(encoding="utf-8"))
            repaired = repair_payload(payload, source_path)
            # 文件夹分类可能来自正文中提到的语言技能，不能据此制造空 resume。
            # 以 JSON 中真实存在的独立语言版本为准，其余严格校验保持不变。
            # EN: The folder classification may come from language skills mentioned in the body, so empty resumes must not be fabricated from it.
            #     The independent language versions that really exist in the JSON are authoritative; the other strict checks remain unchanged.
            # JA: フォルダの分類は本文中で言及された語学スキルから来ていることがあるため、それを根拠に空の resume を作り出してはならない。
            #     JSON に実際にある独立した言語の版を正とし、その他の厳格なチェックは変えない。
            issues = validate_json(
                candidate,
                repaired,
                source_path,
                str(row.get("phone") or ""),
                str(row.get("email") or ""),
                "其他",
                strict=True,
            )
            result["issues"] = issues
            result["resume_languages"] = [
                str(resume.get("resume_language") or resume.get("resume_languge") or "")
                for resume in (repaired.get("structured_data") or {}).get("resumes") or []
            ]
            if issues:
                result["status"] = "still_invalid"
                summary["still_invalid"] += 1
            else:
                directory = args.output_root / folder
                directory.mkdir(parents=True, exist_ok=True)
                reserved = reserved_by_folder.setdefault(folder, set())
                output = unique_destination(directory, candidate.name, reserved)
                output.write_text(json.dumps(repaired, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                result["status"] = "repaired_valid"
                result["output_json"] = str(output)
                summary["repaired_valid"] += 1
        except Exception as exc:
            result["status"] = "repair_failed"
            result["error"] = repr(exc)
            summary["repair_failed"] += 1
        items.append(result)

    report = {"summary": dict(summary), "items": items}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"summary": dict(summary), "report": str(args.report)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
