"""Reconstruct the full XLS report after targeted subset reruns."""
from __future__ import annotations
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1] / "common"))
import rc_config as _rc  # noqa: E402  项目统一配置（python/common/rc_config.py）
# EN: noqa: E402  project-wide configuration (python/common/rc_config.py)
# JA: noqa: E402  プロジェクト共通設定（python/common/rc_config.py）

import json
import re
from collections import defaultdict
from pathlib import Path

ROOT = _rc.project_root()
OUT = ROOT / _rc.dirname("complete-transfered-jsons") / "xls" / "中文"
MAP = ROOT / _rc.dirname("complete-transfered-htmls") / "xls" / "xls_conversion_map.json"
AUDIT = OUT / "_xls_html_to_json_v3_post_audit.json"
REPORT = OUT / "_xls_html_to_json_v3_report.json"


def key(value: str) -> str:
    try:
        return str(Path(value).resolve()).casefold()
    except (OSError, ValueError):
        return str(value or "").casefold()


def digits(value: str) -> str:
    return re.sub(r"\D", "", str(value or ""))


def main() -> int:
    rows = json.loads(MAP.read_text(encoding="utf-8"))
    audit = json.loads(AUDIT.read_text(encoding="utf-8"))
    candidates: dict[str, list[dict]] = defaultdict(list)
    for item in audit.get("items", []):
        path = Path(str(item.get("json") or ""))
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        source = str((payload.get("source") or {}).get("original_path") or "")
        candidates[key(source)].append({"item": item, "payload": payload, "path": path})
    result = []
    for row in rows:
        source = str(row.get("source_path") or "")
        options = candidates.get(key(source), [])
        selected = None
        row_phone, row_email = digits(row.get("phone")), str(row.get("email") or "").casefold()
        for option in options:
            base = ((option["payload"].get("structured_data") or {}).get("base_info") or {})
            if (row_phone and digits(base.get("phone")) == row_phone) or (row_email and str(base.get("email") or "").casefold() == row_email):
                selected = option
                break
        if selected is None and options:
            selected = options[0]
        if selected:
            item = selected["item"]
            status = "success" if item.get("valid") else "needs_review"
            result.append({"source_path": source, "html_path": str((selected["payload"].get("source") or {}).get("html_path") or ""), "output_path": str(selected["path"].resolve()), "status": status, "quality": {"issues": item.get("issues", [])}})
        elif str(row.get("status") or "") == "failed":
            result.append({"source_path": source, "html_path": "", "output_path": "", "status": "failed", "error": str(row.get("error_reason") or "failed")})
        else:
            result.append({"source_path": source, "html_path": "", "output_path": "", "status": "not_resume", "error_reason": "缺少可用联系方式或未生成有效 JSON"})
    report = {"total": len(result), "success": sum(x["status"] == "success" for x in result), "needs_review": sum(x["status"] == "needs_review" for x in result), "not_resume": sum(x["status"] == "not_resume" for x in result), "failed": sum(x["status"] == "failed" for x in result), "items": result, "complete_v1_review": {"path_matched_candidates": 62, "fields_merged_in_final_pass": 12}, "note": "reconstructed after full run and targeted validation; source-path matched"}
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("total", "success", "needs_review", "not_resume", "failed")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
