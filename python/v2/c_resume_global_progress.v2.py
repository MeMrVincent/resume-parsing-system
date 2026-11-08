"""按源文件路径严格核算 Word 转换清单与正式 JSON 的全局进度。

EN: Strictly account the global progress of the Word conversion list against the formal JSON, by source file path.

JA: ソースファイルのパスに基づき、Word 変換リストと正式 JSON の全体進捗を厳密に集計する。
"""

from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from pathlib import Path


def path_key(value: object) -> str:
    return os.path.normcase(os.path.normpath(str(value or "")))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--map", type=Path, required=True)
    parser.add_argument("--formal-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    rows = json.loads(args.map.read_text(encoding="utf-8"))
    formal_by_source: dict[str, list[str]] = {}
    invalid_json: list[str] = []
    formal_files = 0
    for path in args.formal_root.rglob("*.json"):
        if path.name.startswith("_"):
            continue
        formal_files += 1
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            invalid_json.append(str(path))
            continue
        source_info = payload.get("source") or {}
        sources = [str(source_info.get("original_path") or "")]
        sources.extend(str(value or "") for value in (source_info.get("merged_original_paths") or []))
        for item in source_info.get("source_files") or []:
            if isinstance(item, dict):
                sources.append(str(item.get("original_path") or ""))
        for source in dict.fromkeys(value for value in sources if value):
            formal_by_source.setdefault(path_key(source), []).append(str(path))

    completed = []
    unfinished = []
    for row in rows:
        item = dict(row)
        matches = formal_by_source.get(path_key(row.get("source_path")), [])
        if matches:
            item["formal_jsons"] = matches
            completed.append(item)
        else:
            unfinished.append(item)

    report = {
        "counts": {
            "map_sources": len(rows),
            "formal_json_files": formal_files,
            "formal_source_paths": len(formal_by_source),
            "duplicate_formal_json_files": sum(max(0, len(set(v)) - 1) for v in formal_by_source.values()),
            "completed_map_sources": len(completed),
            "unfinished_map_sources": len(unfinished),
            "unfinished_by_status": dict(Counter(str(row.get("status") or "") for row in unfinished)),
            "completed_by_map_status": dict(Counter(str(row.get("status") or "") for row in completed)),
            "invalid_formal_json": len(invalid_json),
        },
        "invalid_formal_json": invalid_json,
        "unfinished": unfinished,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["counts"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
