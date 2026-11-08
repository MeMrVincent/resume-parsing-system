"""将剩余自动 review 疑难项转入人工处理队列，并保留 HTML。

EN: Move the remaining automatic-review difficult items into the manual-processing queue, keeping the HTML.

JA: 残った自動レビューの難しい項目を人手の処理キューに移し、HTML は残す。
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--map", type=Path, required=True)
    parser.add_argument("--progress", type=Path, required=True)
    parser.add_argument("--json-report", type=Path, required=True)
    parser.add_argument("--csv-report", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    rows = json.loads(args.map.read_text(encoding="utf-8"))
    progress = json.loads(args.progress.read_text(encoding="utf-8"))
    unfinished_sources = {
        str(item.get("source_path") or "").casefold()
        for item in progress.get("unfinished", [])
        if item.get("status") == "needs_review"
    }
    items: list[dict[str, str]] = []
    for row in rows:
        source_key = str(row.get("source_path") or "").casefold()
        if row.get("status") == "deferred_manual_review" and source_key not in unfinished_sources:
            row["status"] = "needs_review"
            row.pop("automatic_processing", None)
            row.pop("manual_review_reason", None)
        if source_key not in unfinished_sources:
            continue
        reason = str(row.get("error_reason") or row.get("reason") or "自动解析失败、结构不足或严格源审计未通过")
        item = {
            "language_folder": str(row.get("language_folder") or "未分类"),
            "source_path": str(row.get("source_path") or ""),
            "html_path": str(row.get("html_path") or ""),
            "reason": reason,
            "html_exists": str(Path(str(row.get("html_path") or "")).is_file()),
        }
        items.append(item)
        if args.apply:
            row["status"] = "deferred_manual_review"
            row["automatic_processing"] = "skipped_difficult"
            row["manual_review_reason"] = reason

    items.sort(key=lambda item: (item["language_folder"], item["source_path"].casefold()))
    by_language: dict[str, int] = {}
    for item in items:
        language = item["language_folder"]
        by_language[language] = by_language.get(language, 0) + 1

    report = {
        "mode": "apply" if args.apply else "dry-run",
        "total": len(items),
        "by_language": dict(sorted(by_language.items(), key=lambda pair: (-pair[1], pair[0]))),
        "items": items,
    }
    args.json_report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with args.csv_report.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["language_folder", "source_path", "html_path", "reason", "html_exists"])
        writer.writeheader()
        writer.writerows(items)
    if args.apply:
        args.map.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"mode": report["mode"], "total": len(items), "by_language": report["by_language"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
