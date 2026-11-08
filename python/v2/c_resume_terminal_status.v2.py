"""将已人工核验且不可继续解析的单个转换项标为终态。

EN: Mark a single conversion item that has been manually verified and cannot be parsed further as terminal.

JA: 人手で確認済みで、これ以上解析できない単一の変換項目を終了状態にする。
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--map", type=Path, required=True)
    parser.add_argument("--source-path", required=True)
    parser.add_argument("--status", required=True)
    parser.add_argument("--reason", required=True)
    args = parser.parse_args()
    rows = json.loads(args.map.read_text(encoding="utf-8"))
    matched = 0
    for row in rows:
        if str(row.get("source_path") or "") == args.source_path:
            row["status"] = args.status
            row["error_reason"] = args.reason
            row["terminal_classification"] = args.status
            matched += 1
    if matched != 1:
        raise SystemExit(f"expected exactly one map row, matched={matched}")
    args.map.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"matched": matched, "status": args.status}, ensure_ascii=False))


if __name__ == "__main__":
    main()
