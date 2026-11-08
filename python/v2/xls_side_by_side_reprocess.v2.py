"""Incrementally rebuild XLS files that contain left/right language resumes."""
from __future__ import annotations
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1] / "common"))
import rc_config as _rc  # noqa: E402  项目统一配置（python/common/rc_config.py）
# EN: noqa: E402  project-wide configuration (python/common/rc_config.py)
# JA: noqa: E402  プロジェクト共通設定（python/common/rc_config.py）

import json
import re
from pathlib import Path

from process_xls_html_to_json import process_row

ROOT = _rc.project_root()
OUT = ROOT / _rc.dirname("complete-transfered-jsons") / "xls" / "中文"
MAP = ROOT / _rc.dirname("complete-transfered-htmls") / "xls" / "xls_conversion_map.json"
PASSED = ROOT / _rc.dirname("complete-transfered-htmls") / "xls" / "passed"
REVIEW = ROOT / _rc.dirname("complete-transfered-htmls") / "xls" / "review"


def is_side_by_side(record: dict) -> bool:
    source = record.get("source") or {}
    folder = str(source.get("language_folder") or "")
    html_path = Path(str(source.get("html_path") or ""))
    try:
        html = html_path.read_text(encoding="utf-8", errors="replace") if html_path.is_file() else ""
    except OSError:
        html = ""
    if str(source.get("original_path") or "").casefold().endswith(".xls") and ("中英文" in folder or "中日文" in folder):
        return True
    if re.search(r'data-language-count="2"', html):
        return True
    # Some generated files lost the count attribute but retain a five-column
    # table with Chinese labels on the left and English labels on the right.
    return bool(re.search(r"data-column-index=\"(?:4|5)\"[^>]*>\s*(?:Basic information|Name|Gender|Work Experience|Company Name|Address)", html, re.I) and re.search(r"[㐀-鿿]", html))


def main() -> int:
    rows = json.loads(MAP.read_text(encoding="utf-8"))
    row_by_source = {str(row.get("source_path") or "").casefold(): row for row in rows if row.get("source_path")}
    selected: dict[str, dict] = {}
    for path in OUT.glob("*.json"):
        if path.name.startswith("_"):
            continue
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not is_side_by_side(record):
            continue
        source = str((record.get("source") or {}).get("original_path") or "")
        if source.casefold() in row_by_source:
            selected[source.casefold()] = row_by_source[source.casefold()]
    results = [process_row(row, OUT, PASSED, REVIEW) for row in sorted(selected.values(), key=lambda item: str(item.get("source_path") or "").casefold())]
    valid_variants = 0
    variant_failures = []
    for item in results:
        output = Path(str(item.get("output_path") or ""))
        try:
            payload = json.loads(output.read_text(encoding="utf-8"))
            codes = {str(r.get("resume_languge") or "").casefold() for r in (payload.get("structured_data") or {}).get("resumes") or []}
        except (OSError, ValueError):
            codes = set()
        if len(codes & {"en", "jp", "ja"}) >= 1 and len(codes) >= 2:
            valid_variants += 1
        else:
            variant_failures.append({"source_path": item.get("source_path"), "output_path": item.get("output_path"), "codes": sorted(codes)})
    report = {"selected_sources": len(results), "success": sum(item.get("status") == "success" for item in results), "needs_review": sum(item.get("status") == "needs_review" for item in results), "failed": sum(item.get("status") == "failed" for item in results), "valid_language_variants": valid_variants, "variant_failures": variant_failures, "items": results}
    (OUT / "_xls_side_by_side_reprocess_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("selected_sources", "success", "needs_review", "failed", "valid_language_variants")}, ensure_ascii=False))
    return 0 if not report["failed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
