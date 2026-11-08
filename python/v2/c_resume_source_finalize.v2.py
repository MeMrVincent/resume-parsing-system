"""同步已晋级 JSON 到转换映射，并删除其对应 HTML。

EN: Sync promoted JSON into the conversion map and delete the corresponding HTML.

JA: 昇格済みの JSON を変換マップに同期し、対応する HTML を削除する。
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path


def key(value: object) -> str:
    return os.path.normcase(os.path.normpath(str(value or "")))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--map", type=Path, required=True)
    parser.add_argument("--promotion-reports", type=Path, nargs="+", required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    promoted = {}
    for report_path in args.promotion_reports:
        report = json.loads(report_path.read_text(encoding="utf-8"))
        for item in report.get("items") or []:
            promoted[key(item.get("source"))] = item
    rows = json.loads(args.map.read_text(encoding="utf-8"))
    updated = 0
    deleted = 0
    missing_html = 0
    for row in rows:
        item = promoted.get(key(row.get("source_path")))
        if not item:
            continue
        html = Path(str(row.get("html_path") or ""))
        if html.is_file():
            html.unlink()
            deleted += 1
        else:
            missing_html += 1
        row["json_status"] = "passed_source_audited"
        row["json_path"] = str(item.get("formal") or "")
        row["parsed_completed"] = True
        row["html_status"] = "deleted_after_valid_json_promotion"
        updated += 1
    args.map.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    output = {"promoted_sources": len(promoted), "updated_map_rows": updated, "deleted_html": deleted, "missing_html": missing_html}
    args.report.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
