"""只提升已通过源证据审计的多语言 JSON，并同步转换清单。

EN: Only promote multilingual JSON that passed the source-evidence audit, and update the conversion list accordingly.

JA: ソース証拠の監査に合格した多言語 JSON だけを昇格させ、変換リストも同期する。
"""

from __future__ import annotations
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1] / "common"))
import rc_config as _rc  # noqa: E402  项目统一配置（python/common/rc_config.py）
# EN: noqa: E402  project-wide configuration (python/common/rc_config.py)
# JA: noqa: E402  プロジェクト共通設定（python/common/rc_config.py）

import argparse
import json
import os
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any


def path_key(value: str) -> str:
    return os.path.normcase(os.path.normpath(str(value or "")))


def atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    finally:
        Path(temp_name).unlink(missing_ok=True)


def unique_path(directory: Path, name: str) -> Path:
    candidate = directory / name
    sequence = 2
    while candidate.exists():
        candidate = directory / f"{Path(name).stem}_{sequence}{Path(name).suffix}"
        sequence += 1
    return candidate


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audit-report", type=Path, required=True)
    parser.add_argument("--formal-root", type=Path, required=True)
    parser.add_argument("--map", type=Path, required=True)
    parser.add_argument("--extra-map-root", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    audit = json.loads(args.audit_report.read_text(encoding="utf-8"))
    map_rows = json.loads(args.map.read_text(encoding="utf-8"))
    map_by_source = {path_key(row.get("source_path", "")): row for row in map_rows}
    htmls_by_source: dict[str, set[Path]] = {}
    for row in map_rows:
        source = path_key(row.get("source_path", ""))
        html = Path(str(row.get("html_path") or ""))
        if source and html.is_file():
            htmls_by_source.setdefault(source, set()).add(html)
    if args.extra_map_root:
        for extra_map in args.extra_map_root.glob("*/word_conversion_map.json"):
            try:
                rows = json.loads(extra_map.read_text(encoding="utf-8"))
            except Exception:
                continue
            for row in rows:
                source = path_key(row.get("source_path", ""))
                html = Path(str(row.get("html_path") or ""))
                if source and html.is_file():
                    htmls_by_source.setdefault(source, set()).add(html)

    existing_sources: set[str] = set()
    for directory in args.formal_root.iterdir():
        if not directory.is_dir():
            continue
        for path in directory.glob("*.json"):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            original = str((payload.get("source") or {}).get("original_path") or "")
            if original:
                existing_sources.add(path_key(original))

    results: list[dict[str, Any]] = []
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    for item in audit.get("items") or []:
        if item.get("status") != "passed":
            continue
        source_path = str(item.get("source_path") or "")
        source_key = path_key(source_path)
        result: dict[str, Any] = {"source_path": source_path, "language_folder": item.get("language_folder")}
        if source_key in existing_sources:
            result["status"] = "skipped_existing_source"
            results.append(result)
            continue
        source_json = Path(str(item.get("json_path") or ""))
        folder = args.formal_root / str(item.get("language_folder") or "其他")
        folder.mkdir(parents=True, exist_ok=True)
        destination = unique_path(folder, source_json.name)
        shutil.copy2(source_json, destination)
        # 复制后重新读取，确保正式文件完整可解析，再删除可再生 HTML。
        # EN: Re-read after copying to make sure the formal file is complete and parseable, then delete the regenerable HTML.
        # JA: コピー後に読み直して正式ファイルが完全で解析可能であることを確認し、その後で再生成可能な HTML を削除する。
        json.loads(destination.read_text(encoding="utf-8"))
        deleted: list[str] = []
        for html in sorted(htmls_by_source.get(source_key, set())):
            resolved = html.resolve()
            if _rc.project_root() not in resolved.parents:
                continue
            resolved.unlink(missing_ok=True)
            deleted.append(str(resolved))
        row = map_by_source.get(source_key)
        if row is not None:
            row["json_status"] = "passed_repaired_complete_v1_source_audited"
            row["json_path"] = str(destination)
            row["json_source"] = "complete-v1 + source/html evidence audit"
            row["json_validated_at"] = now
            row["html_status"] = "deleted_after_valid_json_promotion"
            row["parsed_completed"] = True
        existing_sources.add(source_key)
        result.update(status="promoted", output_json=str(destination), deleted_html=deleted)
        results.append(result)

    atomic_json(args.map, map_rows)
    report = {
        "promoted": sum(item.get("status") == "promoted" for item in results),
        "skipped_existing_source": sum(item.get("status") == "skipped_existing_source" for item in results),
        "items": results,
    }
    atomic_json(args.report, report)
    print(json.dumps({key: value for key, value in report.items() if key != "items"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
