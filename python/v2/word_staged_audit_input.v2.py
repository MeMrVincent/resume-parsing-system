"""把隔离解析目录中的 JSON 组装成多语言源文审计输入。

EN: Assemble the JSON in the isolated parse directory into input for the multilingual source audit.

JA: 分離した解析ディレクトリの JSON を、多言語の原文監査の入力として組み立てる。
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path


def key(value: str) -> str:
    return os.path.normcase(os.path.normpath(str(value or "")))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json-dir", type=Path, required=True)
    parser.add_argument("--map", type=Path, required=True)
    parser.add_argument("--language-folder", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rows = json.loads(args.map.read_text(encoding="utf-8"))
    by_source = {key(row.get("source_path", "")): row for row in rows}
    by_html = {key(row.get("html_path", "")): row for row in rows}
    items = []
    unmatched = []
    for path in args.json_dir.rglob("*.json"):
        if path.name.startswith("_"):
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        source = payload.get("source") or {}
        original = str(source.get("original_path") or "")
        row = by_source.get(key(original)) or by_html.get(key(original))
        if not row:
            unmatched.append(str(path))
            continue
        languages = [
            str(resume.get("resume_language") or "")
            for resume in ((payload.get("structured_data") or {}).get("resumes") or [])
            if str(resume.get("resume_language") or "")
        ]
        items.append({
            "status": "repaired_valid",
            "source_path": row.get("source_path"),
            "language_folder": args.language_folder,
            "candidate_json": str(path),
            "output_json": str(path),
            "resume_languages": languages,
            "issues": [],
        })
    report = {"summary": {"items": len(items), "unmatched": len(unmatched)}, "items": items, "unmatched": unmatched}
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False))


if __name__ == "__main__":
    main()
