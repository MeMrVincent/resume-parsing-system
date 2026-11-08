"""把需要用户 OCR 的原始文档复制到指定目录，并在转换映射中标记等待 OCR。

EN: Copy original documents that need user OCR into the designated directory and mark them as awaiting OCR in the conversion map.

JA: ユーザーによる OCR が必要な元文書を指定ディレクトリにコピーし、変換マップで OCR 待ちとしてマークする。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import re
from pathlib import Path


def key(value: object) -> str:
    return os.path.normcase(os.path.normpath(str(value or "")))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--map", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--include-other-generic-docs", action="store_true")
    parser.add_argument("--include-failed-resumes", action="store_true")
    parser.add_argument("--skip-liepin-default", action="store_true")
    parser.add_argument("--include-passed-english", action="store_true")
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    rows = json.loads(args.map.read_text(encoding="utf-8"))
    by_source = {key(row.get("source_path")): row for row in rows}
    manifest_items = manifest.get("items") or manifest.get("unfinished") or []
    selected = [] if args.skip_liepin_default else [
        item for item in manifest_items
        if item.get("language_folder") == "英文"
        and "猎聘" in (
            str(item.get("source_path") or "") + str(item.get("html_path") or "")
        )
    ]
    if args.include_other_generic_docs:
        selected.extend(
            item for item in manifest_items
            if item.get("status") == "needs_review"
            and item.get("language_folder") == "其他"
            and re.fullmatch(r"Doc\d+\.docx?", str(item.get("filename") or ""), re.I)
            and item not in selected
        )
    if args.include_failed_resumes:
        selected.extend(
            item for item in manifest_items
            if item.get("status") == "failed"
            and not re.search(r"证书材料|(?:^|[\\/])照片\.docx?$", str(item.get("source_path") or ""), re.I)
            and item not in selected
        )
    if args.include_passed_english:
        selected.extend(
            item for item in manifest_items
            if item.get("status") == "passed"
            and item.get("language_folder") == "英文"
            and item not in selected
        )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for item in selected:
        source = Path(str(item.get("source_path") or ""))
        result = {"source_path": str(source), "html_path": str(item.get("html_path") or "")}
        if not source.is_file():
            result["status"] = "missing_source"
            results.append(result)
            continue
        digest = hashlib.sha256(str(source).encode("utf-8", "surrogatepass")).hexdigest()[:12]
        target = args.output_dir / f"{source.stem}_{digest}{source.suffix}"
        shutil.copy2(source, target)
        result.update(status="copied", ocr_document=str(target))
        row = by_source.get(key(source))
        if row is not None:
            row["status"] = "pending_user_ocr"
            row["error_reason"] = "源文为图片型猎聘简历；已复制原始文档，等待用户 OCR"
            row["terminal_classification"] = "pending_user_ocr"
            row["ocr_document_path"] = str(target)
        results.append(result)
    args.map.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report = {
        "selected": len(selected),
        "copied": sum(row.get("status") == "copied" for row in results),
        "missing_source": sum(row.get("status") == "missing_source" for row in results),
        "output_dir": str(args.output_dir),
        "items": results,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    ocr_manifest_path = args.output_dir / "ocr_manifest.json"
    existing_items = []
    if ocr_manifest_path.is_file():
        try:
            existing_items = json.loads(ocr_manifest_path.read_text(encoding="utf-8")).get("items") or []
        except (OSError, json.JSONDecodeError, AttributeError):
            existing_items = []
    merged = {key(item.get("source_path")): item for item in existing_items}
    merged.update({key(item.get("source_path")): item for item in results})
    aggregate = {
        "selected": len(merged),
        "copied": sum(item.get("status") == "copied" for item in merged.values()),
        "missing_source": sum(item.get("status") == "missing_source" for item in merged.values()),
        "output_dir": str(args.output_dir),
        "items": list(merged.values()),
    }
    ocr_manifest_path.write_text(json.dumps(aggregate, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key != "items"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
