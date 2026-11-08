"""列出 OCR/unknown 批次中未被任何结果 JSON 认领的源文档。

EN: List source documents in the OCR/unknown batch that no result JSON has claimed.

JA: OCR/unknown のバッチの中で、どの結果 JSON にも対応付けられていないソース文書を一覧にする。
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--json-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    items = manifest.get("items") or manifest.get("unfinished") or []
    by_name = {
        Path(str(item.get("copied_path") or item.get("ocr_document_path") or "")).name.casefold(): item
        for item in items
        if item.get("copied_path") or item.get("ocr_document_path")
    }
    claimed = set()
    for path in args.json_dir.glob("*.json"):
        payload = json.loads(path.read_text(encoding="utf-8"))
        for source_file in payload.get("source", {}).get("source_files") or []:
            filename = source_file.get("filename") if isinstance(source_file, dict) else source_file
            if filename:
                claimed.add(Path(str(filename)).name.casefold())
    missing = []
    for name, item in by_name.items():
        if name not in claimed:
            missing.append({
                "document_name": Path(str(item.get("copied_path") or item.get("ocr_document_path") or "")).name,
                "source_path": item.get("source_path") or item.get("original_path"),
                "previous_status": item.get("status"),
            })
    report = {
        "manifest_documents": len(by_name),
        "json_claimed_documents": len(claimed.intersection(by_name)),
        "without_json": len(missing),
        "items": sorted(missing, key=lambda value: str(value.get("source_path") or "").casefold()),
    }
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("manifest_documents", "json_claimed_documents", "without_json")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
