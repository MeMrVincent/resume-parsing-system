"""让 OCR 工作目录只保留当前 pending_user_ocr 文档并刷新清单。

EN: Keep only the current pending_user_ocr documents in the OCR working directory and refresh the list.

JA: OCR の作業ディレクトリには現在の pending_user_ocr の文書だけを残し、一覧を更新する。
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
from pathlib import Path


def key(value: object) -> str:
    return os.path.normcase(os.path.normpath(str(value or "")))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--map", type=Path, required=True)
    parser.add_argument("--ocr-dir", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    root = args.ocr_dir.resolve()
    rows = json.loads(args.map.read_text(encoding="utf-8"))
    pending = []
    removed = []
    for row in rows:
        ocr_value = str(row.get("ocr_document_path") or "")
        if not ocr_value:
            continue
        path = Path(ocr_value)
        try:
            resolved = path.resolve()
            inside = resolved.parent == root
        except OSError:
            inside = False
        if not inside:
            continue
        if row.get("status") == "pending_user_ocr":
            pending.append({
                "source_path": row.get("source_path"),
                "ocr_document": str(path),
                "html_path": row.get("html_path"),
                "language_folder": row.get("language_folder"),
            })
        elif path.is_file():
            path.unlink()
            removed.append(str(path))
    restored = []
    for item in pending:
        target = Path(str(item["ocr_document"]))
        if target.is_file():
            continue
        source = Path(str(item.get("source_path") or ""))
        if source.is_file():
            shutil.copy2(source, target)
            restored.append(str(target))
    missing = [item for item in pending if not Path(str(item["ocr_document"])).is_file()]
    manifest = {
        "pending_documents": len(pending),
        "missing_documents": len(missing),
        "items": pending,
    }
    (root / "ocr_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report = {**manifest, "restored_missing_copies": len(restored), "restored": restored, "removed_completed_copies": len(removed), "removed": removed}
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"pending_documents": len(pending), "missing_documents": len(missing), "restored_missing_copies": len(restored), "removed_completed_copies": len(removed)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
