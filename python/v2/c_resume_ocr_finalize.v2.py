"""登记用户 OCR JSON，恢复原始源路径，移动到正式中文目录。

EN: Register the user's OCR JSON, restore the original source path, and move it into the formal Chinese directory.

JA: ユーザーの OCR JSON を登録し、元のソースパスを復元して、正式な中国語ディレクトリへ移動する。
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
from collections import defaultdict
from pathlib import Path


def key(value: object) -> str:
    return os.path.normcase(os.path.normpath(str(value or "")))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json-dir", type=Path, required=True)
    parser.add_argument("--map", type=Path, required=True)
    parser.add_argument("--formal-dir", type=Path, required=True)
    parser.add_argument("--document-manifest", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    rows = json.loads(args.map.read_text(encoding="utf-8"))
    by_ocr_name: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        ocr_path = str(row.get("ocr_document_path") or "")
        if ocr_path:
            by_ocr_name[Path(ocr_path).name.casefold()].append(row)
    if args.document_manifest:
        manifest = json.loads(args.document_manifest.read_text(encoding="utf-8"))
        for manifest_item in manifest.get("items", []):
            copied_path = str(manifest_item.get("copied_path") or "")
            source_path = str(manifest_item.get("source_path") or "")
            matches = [row for row in rows if key(row.get("source_path")) == key(source_path)]
            if copied_path and len(matches) == 1:
                by_ocr_name[Path(copied_path).name.casefold()] = matches

    results = []
    claimed_sources: set[str] = set()
    destinations: set[str] = set()
    args.formal_dir.mkdir(parents=True, exist_ok=True)
    for json_path in sorted(args.json_dir.glob("*.json")):
        payload = json.loads(json_path.read_text(encoding="utf-8"))
        source = payload.setdefault("source", {})
        source_files = source.get("source_files") or []
        matched_rows: list[dict] = []
        enriched_files = []
        for source_file in source_files:
            item = dict(source_file) if isinstance(source_file, dict) else {"filename": str(source_file)}
            filename = str(item.get("filename") or "")
            matches = by_ocr_name.get(filename.casefold(), [])
            if len(matches) != 1:
                raise RuntimeError(f"{json_path.name}: OCR 文件映射数量不是 1: {filename} -> {len(matches)}")
            row = matches[0]
            matched_rows.append(row)
            item["original_path"] = str(row.get("source_path") or "")
            item["ocr_document_path"] = str(row.get("ocr_document_path") or "")
            enriched_files.append(item)
        if not matched_rows:
            raise RuntimeError(f"{json_path.name}: 没有 source_files")
        originals = [str(row.get("source_path") or "") for row in matched_rows]
        if any(key(path) in claimed_sources for path in originals):
            raise RuntimeError(f"{json_path.name}: 原始源路径被多个 OCR JSON 重复认领")
        claimed_sources.update(key(path) for path in originals)
        source["source_files"] = enriched_files
        source["original_path"] = originals[0]
        source["path"] = originals[0]
        source["filename"] = Path(originals[0]).name
        source["merged_original_paths"] = originals
        source["converter"] = "user-ocr-json"
        note = str(source.get("note") or "").strip()
        addition = f"已按 OCR 文件名恢复 {len(originals)} 条原始 Word 源路径，并登记到转换映射。"
        if addition not in note:
            source["note"] = (note + " " + addition).strip()

        destination = args.formal_dir / json_path.name
        sequence = 2
        while destination.exists() or key(destination) in destinations:
            destination = args.formal_dir / f"{json_path.stem}_{sequence}{json_path.suffix}"
            sequence += 1
        destinations.add(key(destination))
        result = {
            "input_json": str(json_path), "output_json": str(destination),
            "original_paths": originals, "merged_sources": len(originals),
        }
        if args.apply:
            temporary = destination.with_suffix(destination.suffix + ".tmp")
            temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            os.replace(temporary, destination)
            json_path.unlink()
            for row in matched_rows:
                html = Path(str(row.get("html_path") or ""))
                if html.is_file():
                    html.unlink()
                row["status"] = "passed"
                row["language_folder"] = "中文"
                row["json_status"] = "passed_user_ocr"
                row["json_path"] = str(destination)
                row["parsed_completed"] = True
                row["html_status"] = "deleted_after_user_ocr_json"
                row["terminal_classification"] = ""
                row["error_reason"] = ""
        results.append(result)

    if args.apply:
        args.map.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report = {
        "mode": "apply" if args.apply else "dry-run",
        "json_files": len(results),
        "source_documents": sum(row["merged_sources"] for row in results),
        "merged_document_count": sum(max(0, row["merged_sources"] - 1) for row in results),
        "items": results,
    }
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "items"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
