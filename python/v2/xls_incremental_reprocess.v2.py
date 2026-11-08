"""Rebuild only XLS sources whose current profile DOM/JSON is demonstrably bad."""
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

BAD_LABELS = ("通讯地址", "户口", "现在单位", "现在（前）单位", "学校名称", "专业名称", "最高学历", "期望月薪", "Political Status", "联系电话", "Phone")


def bad_profile(record: dict) -> bool:
    for resume in (record.get("structured_data") or {}).get("resumes") or []:
        base = resume.get("base_info") or {}
        household = str(base.get("household_registration") or "")
        city = str(base.get("city") or "")
        political = str(base.get("political_status") or "")
        if household.strip() in {"现在单位", "现在（前）单位", "户口"}:
            return True
        if city.strip() in {"户口", "通讯地址"} or sum(label in city for label in BAD_LABELS) >= 2:
            return True
        if re.search(r"政治面貌|Political Status|联系电话|Phone|手机|电话|@|\d{7,}", political, re.I):
            return True
    source = str((record.get("source") or {}).get("original_path") or "")
    if any(token in source for token in ("陈磊 履歴書（日本語）.xls", "TangJun_Resume_EnslishVersion.xls")):
        return True
    html_path = Path(str((record.get("source") or {}).get("html_path") or ""))
    try:
        html = html_path.read_text(encoding="utf-8", errors="replace") if html_path.is_file() else ""
    except OSError:
        html = ""
    resumes = (record.get("structured_data") or {}).get("resumes") or []
    has_work = any(r.get("work_experiences") for r in resumes if isinstance(r, dict))
    if not has_work and re.search(r'data-section-type="work_experiences"[^>]*>.*?(?:19|20)\d{2}.*?公司\s*[:：]', html, re.S | re.I):
        return True
    if re.search(r'data-language-count="2"', html) and not re.search(r'data-language-code="en"', html):
        return True
    if re.search(r'<h2[^>]*>[^<]*(?:教育经历|教育背景|Education)[\s\S]{0,160}(?:19|20)\d{2}\s*[-./]\s*\d{1,2}', html, re.I):
        return True
    if re.search(r'<h2[^>]*>[^<]*(?:自我评价|Self[- ]Assessment)[\s\S]{80,}</h2>', html, re.I):
        return True
    return False


def main() -> int:
    rows = json.loads(MAP.read_text(encoding="utf-8"))
    by_source = {str(row.get("source_path") or "").casefold(): row for row in rows if row.get("source_path")}
    selected: dict[str, dict] = {}
    for path in OUT.glob("*.json"):
        if path.name.startswith("_"):
            continue
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not bad_profile(record):
            continue
        source = str((record.get("source") or {}).get("original_path") or "")
        row = by_source.get(source.casefold())
        if row:
            selected[source.casefold()] = row
    results = [process_row(row, OUT, PASSED, REVIEW) for row in sorted(selected.values(), key=lambda item: str(item.get("source_path") or "").casefold())]
    report = {
        "selected_sources": len(results),
        "success": sum(item.get("status") == "success" for item in results),
        "needs_review": sum(item.get("status") == "needs_review" for item in results),
        "failed": sum(item.get("status") == "failed" for item in results),
        "items": results,
    }
    target = OUT / "_xls_incremental_reprocess_report.json"
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("selected_sources", "success", "needs_review", "failed")}, ensure_ascii=False))
    return 0 if not report["failed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
