from __future__ import annotations
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1] / "common"))
import rc_config as _rc  # noqa: E402  项目统一配置（python/common/rc_config.py）
# EN: noqa: E402  project-wide configuration (python/common/rc_config.py)
# JA: noqa: E402  プロジェクト共通設定（python/common/rc_config.py）

import json
import tempfile
from collections import OrderedDict
from pathlib import Path
from typing import Any


ROOT = _rc.project_root()
TARGET = ROOT / _rc.dirname("complete-transfered-htmls") / "pdf" / "rebuild-reports" / "pdf_semantic_overrides.v2.json"


class Pairs(list[tuple[str, Any]]):
    pass


def merge(left: Any, right: Any) -> Any:
    if isinstance(left, dict) and isinstance(right, dict):
        output = OrderedDict(left)
        for key, value in right.items():
            output[key] = merge(output[key], value) if key in output else value
        return output
    return right


def convert(value: Any) -> Any:
    if isinstance(value, Pairs):
        output: OrderedDict[str, Any] = OrderedDict()
        for key, child in value:
            current = convert(child)
            output[key] = merge(output[key], current) if key in output else current
        return output
    if isinstance(value, list):
        return [convert(child) for child in value]
    return value


def main() -> int:
    raw = TARGET.read_text(encoding="utf-8-sig")
    payload = convert(json.loads(raw, object_pairs_hook=Pairs))
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".tmp", dir=TARGET.parent, delete=False) as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
        temporary = Path(stream.name)
    temporary.replace(TARGET)
    print(f"deduplicated={TARGET}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
