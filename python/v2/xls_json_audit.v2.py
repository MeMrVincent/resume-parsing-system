"""Strict post-run audit for every rebuilt XLS JSON against its source map."""
from __future__ import annotations
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1] / "common"))
import rc_config as _rc  # noqa: E402  项目统一配置（python/common/rc_config.py）
# EN: noqa: E402  project-wide configuration (python/common/rc_config.py)
# JA: noqa: E402  プロジェクト共通設定（python/common/rc_config.py）

import json
from collections import Counter
from pathlib import Path

from process_xls_html_to_json import valid_rule_issues

ROOT = _rc.project_root()
OUT = ROOT / _rc.dirname("complete-transfered-jsons") / "xls" / "中文"
MAP = ROOT / _rc.dirname("complete-transfered-htmls") / "xls" / "xls_conversion_map.json"
REPORT = OUT / "_xls_html_to_json_v3_post_audit.json"


def key(value: str) -> str:
    try:
        return str(Path(value).resolve()).casefold()
    except (OSError, ValueError):
        return str(value or "").casefold()


def main() -> int:
    rows = json.loads(MAP.read_text(encoding="utf-8"))
    by_source: dict[str, list[dict]] = {}
    for row in rows:
        by_source.setdefault(key(str(row.get("source_path") or "")), []).append(row)
    seen: set[str] = set()
    items = []
    for path in sorted(OUT.glob("*.json")):
        if path.name.startswith("_"):
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            items.append({"json": str(path), "valid": False, "issues": [f"invalid_json:{exc}"]})
            continue
        source = str((payload.get("source") or {}).get("original_path") or "")
        candidates = by_source.get(key(source), [])
        html_text = str((payload.get("source") or {}).get("html_path") or "").replace("/", "\\").casefold()
        base = ((payload.get("structured_data") or {}).get("base_info") or {})
        row = next((candidate for candidate in candidates if str(candidate.get("language_folder") or "").casefold() in html_text and str(candidate.get("language_folder") or "")), None)
        if row is None and candidates:
            row = next((candidate for candidate in candidates if str(candidate.get("phone") or "").strip() == str(base.get("phone") or "").strip() or str(candidate.get("email") or "").casefold() == str(base.get("email") or "").casefold()), candidates[0])
        issues = []
        if not source or row is None:
            issues.append("source_missing_from_map")
        else:
            if key(source) in seen:
                issues.append("duplicate_original_source")
            seen.add(key(source))
            issues.extend(valid_rule_issues(payload, path, row))
        html_path = Path(str((payload.get("source") or {}).get("html_path") or ""))
        if not html_path.is_file():
            issues.append("html_missing")
        items.append({"json": str(path), "source": source, "html": str(html_path), "valid": not issues, "issues": sorted(set(issues))})
    counts = Counter("valid" if item["valid"] else "invalid" for item in items)
    issue_counts = Counter(issue for item in items for issue in item["issues"])
    report = {"total_json": len(items), "valid": counts["valid"], "invalid": counts["invalid"], "issue_counts": dict(issue_counts), "items": items}
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("total_json", "valid", "invalid", "issue_counts")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
