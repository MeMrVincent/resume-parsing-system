"""Apply the current semantic DOM cleanup to already-generated XLS HTML."""
from __future__ import annotations
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1] / "common"))
import rc_config as _rc  # noqa: E402  项目统一配置（python/common/rc_config.py）
# EN: noqa: E402  project-wide configuration (python/common/rc_config.py)
# JA: noqa: E402  プロジェクト共通設定（python/common/rc_config.py）

import json
from pathlib import Path

from process_xls_html_to_json import repair_bound_identity_dom

ROOT = _rc.project_root()
OUT = ROOT / _rc.dirname("complete-transfered-jsons") / "xls" / "中文"


def main() -> None:
    touched = 0
    for path in OUT.glob("*.json"):
        if path.name.startswith("_"):
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        source = payload.get("source") or {}
        html = Path(str(source.get("html_path") or ""))
        original = str(source.get("original_path") or "")
        if not html.is_file():
            continue
        text = html.read_text(encoding="utf-8", errors="replace")
        repaired = repair_bound_identity_dom(text)
        if repaired != text:
            html.write_text(repaired, encoding="utf-8")
            touched += 1
    print(f"touched_html={touched}")


if __name__ == "__main__":
    main()
