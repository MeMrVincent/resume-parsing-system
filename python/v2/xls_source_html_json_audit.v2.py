"""Conservative source -> HTML -> JSON coverage audit for the XLS batch."""
from __future__ import annotations
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1] / "common"))
import rc_config as _rc  # noqa: E402  项目统一配置（python/common/rc_config.py）
# EN: noqa: E402  project-wide configuration (python/common/rc_config.py)
# JA: noqa: E402  プロジェクト共通設定（python/common/rc_config.py）

import json
import re
import unicodedata
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup

from process_xls_to_html import read_excel_grid


ROOT = _rc.project_root()
IGNORE = {"", "-", "－", "—", "―", "〒", "●", "〇", "○", "√", "□", "■", "毕业情况", "卒業状況", "学校名", "学校", "时间", "時間"}


def compact(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).casefold()
    return re.sub(r"\s+", "", text)


def source_text(path: Path) -> str:
    chunks: list[str] = []
    for _sheet, grid in read_excel_grid(path):
        for row in grid:
            chunks.extend(str(getattr(cell, "val", "") or "") for cell in row)
    return " ".join(chunks)


def json_values(payload: dict[str, Any]) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    structured = payload.get("structured_data") or {}
    for ri, resume in enumerate(structured.get("resumes") or []):
        base = resume.get("base_info") or {}
        for field, value in base.items():
            if field in {"platform_from", "platform_resume_id", "city", "age", "birth_year", "pr", "birth_date", "school_start_ym", "school_end_ym", "position_start", "position_resigned"}:
                continue
            if str(value or "").strip() and compact(value) not in {compact(x) for x in IGNORE}:
                out.append((f"resume[{ri}].base_info.{field}", str(value)))
        for collection in ("education_list", "work_experiences", "certificate_list", "language_list", "skills_list", "expected_list"):
            for ii, item in enumerate(resume.get(collection) or []):
                for field, value in item.items():
                    if field in {
                        "status", "certificate_type", "sequence_no", "language_name", "language_level",
                        "school_start_ym", "school_end_ym", "position_start", "position_resigned",
                    }:
                        continue
                    if str(value or "").strip() and compact(value) not in {compact(x) for x in IGNORE}:
                        out.append((f"resume[{ri}].{collection}[{ii}].{field}", str(value)))
    return out


def appears(value: str, texts: tuple[str, str]) -> bool:
    needle = compact(value)
    if len(needle) < 2:
        return True
    if needle in compact(texts[0]) or needle in compact(texts[1]):
        return True
    # Certificate/language names are translated between Chinese and Japanese;
    # an identical level/year token is sufficient evidence that the source
    # row was carried through.
    level_tokens = re.findall(r"(?:N[1-5]|[1-9１-９]級|[一二三四五六七八九十]級|[1-9１-９]级|[一二三四五六七八九十]级|CET[-－]?[四六6４]|ISO\s*\d+|日常会話)", unicodedata.normalize("NFKC", value), re.I)
    if level_tokens:
        haystack = compact(texts[0]) + compact(texts[1])
        if all(compact(token) in haystack for token in level_tokens):
            return True
    # Canonical dates are intentionally normalized in JSON; compare year and
    # month/day tokens when punctuation/era text differs in the XLS source.
    nums = re.findall(r"(?:19|20)\d{2}", unicodedata.normalize("NFKC", value))
    return bool(nums) and all(token in compact(texts[0]) + compact(texts[1]) for token in nums)


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--map", type=Path, required=True)
    ap.add_argument("--report", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    rows = json.loads(args.map.read_text(encoding="utf-8"))
    report = json.loads(args.report.read_text(encoding="utf-8-sig"))
    by_source = {str(item.get("source_path")): item for item in report.get("items", [])}
    results: list[dict[str, Any]] = []
    for row in rows:
        item = by_source.get(str(row.get("source_path"))) or {}
        if item.get("status") == "not_resume":
            continue
        output = Path(str(item.get("output_path") or ""))
        html = Path(str(item.get("html_path") or ""))
        source = Path(str(row.get("source_path") or ""))
        issues: list[str] = []
        if not (output.is_file() and html.is_file() and source.is_file()):
            results.append({"source": str(source), "status": "missing_artifact", "issues": ["source/html/json"]})
            continue
        payload = json.loads(output.read_text(encoding="utf-8-sig"))
        html_text = html.read_text(encoding="utf-8", errors="replace")
        try:
            src_text = source_text(source)
        except Exception as exc:
            src_text = ""
            issues.append(f"source_read:{type(exc).__name__}")
        for path, value in json_values(payload):
            if not appears(value, (src_text, html_text)):
                issues.append(f"json_not_in_source_or_html:{path}:{value[:80]}")
        results.append({
            "source": str(source), "html": str(html), "json": str(output),
            "status": "ok" if not issues else "needs_review", "issues": issues,
        })
    summary = {
        "checked": len(results),
        "ok": sum(item["status"] == "ok" for item in results),
        "needs_review": sum(item["status"] != "ok" for item in results),
        "items": results,
    }
    args.output.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: summary[k] for k in ("checked", "ok", "needs_review")}, ensure_ascii=False))
    return 0 if summary["needs_review"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
