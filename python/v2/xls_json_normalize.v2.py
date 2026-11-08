from __future__ import annotations
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1] / "common"))
import rc_config as _rc  # noqa: E402  项目统一配置（python/common/rc_config.py）
# EN: noqa: E402  project-wide configuration (python/common/rc_config.py)
# JA: noqa: E402  プロジェクト共通設定（python/common/rc_config.py）

import json
from pathlib import Path

from process_xls_html_to_json import normalize_record_contacts, normalize_record_dates, sanitize_record


ROOT = _rc.project_root()
OUT = ROOT / _rc.dirname("complete-transfered-jsons") / "xls" / "中文"


def main() -> int:
    changed = 0
    for path in OUT.glob("*.json"):
        if path.name.startswith("_"):
            continue
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        before = json.dumps(record, ensure_ascii=False, sort_keys=True)
        sanitize_record(record)
        normalize_record_contacts(record)
        normalize_record_dates(record)
        sanitize_record(record)
        after = json.dumps(record, ensure_ascii=False, sort_keys=True)
        if after != before:
            path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            changed += 1
    print(json.dumps({"changed": changed}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
