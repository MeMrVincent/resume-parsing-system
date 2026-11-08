"""Record and verify recovery from the former `intern`/`International` boundary defect."""

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
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = _rc.project_root()
MAP_PATH = ROOT / _rc.dirname("complete-transfered-htmls") / "web" / "web_conversion_map.v2.json"
REPAIR_PATH = ROOT / _rc.dirname("complete-transfered-jsons") / "web" / "_web_full_repair.v2.json"
REPORT_PATH = ROOT / _rc.dirname("complete-transfered-jsons") / "web" / "_web_internship_boundary_recovery.v2.json"


def atomic_json(path: Path, payload: Any) -> None:
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    finally:
        Path(temp_name).unlink(missing_ok=True)


def work_count(path: Path) -> int:
    if not path.is_file():
        return 0
    payload = json.loads(path.read_text(encoding="utf-8"))
    resumes = (((payload.get("structured_data") or {}).get("resumes")) or [])
    return sum(len(resume.get("work_experiences") or []) for resume in resumes if isinstance(resume, dict))


def affected_indexes(repair: dict[str, Any]) -> set[int]:
    result: set[int] = set()
    for item in repair.get("items", []):
        if not isinstance(item, dict):
            continue
        for history in item.get("repair_round_history", []):
            fixes = history.get("fixes_applied") if isinstance(history, dict) else None
            if isinstance(fixes, dict) and int(fixes.get("internship_work_items_removed") or 0) > 0:
                result.add(int(item.get("index") or 0))
                break
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--complete", action="store_true")
    parser.add_argument("--cleanup-stale", action="store_true")
    args = parser.parse_args()
    mapping = json.loads(MAP_PATH.read_text(encoding="utf-8"))
    by_index = {int(item.get("index") or 0): item for item in mapping.get("records", [])}
    repair = json.loads(REPAIR_PATH.read_text(encoding="utf-8"))
    indexes = affected_indexes(repair)
    previous = json.loads(REPORT_PATH.read_text(encoding="utf-8")) if (args.complete or args.cleanup_stale) and REPORT_PATH.is_file() else {}
    previous_by_index = {int(item.get("index") or 0): item for item in previous.get("items", [])}
    items = []
    for index in sorted(indexes):
        record = by_index[index]
        path = Path(str(record.get("json_path") or ""))
        old_path_value = str(previous_by_index.get(index, {}).get("json_path_before_recovery") or previous_by_index.get(index, {}).get("json_path") or path)
        before = int(previous_by_index.get(index, {}).get("work_item_count_before_recovery") or work_count(path))
        after = work_count(path) if args.complete else None
        items.append({
            "index": index,
            "json_path_before_recovery": old_path_value,
            "json_path": str(path),
            "source_path": str(record.get("source_path") or ""),
            "issue": "former_intern_token_lacked_word_boundary_and_could_match_International",
            "work_item_count_before_recovery": before,
            "work_item_count_after_recovery": after,
            "work_item_count_delta": (after - before) if after is not None else None,
            "status": "recovered_and_rechecked" if (args.complete or args.cleanup_stale) else "scheduled_for_source_regeneration",
        })
    stale_deleted = 0
    if args.cleanup_stale:
        output_root = (ROOT / _rc.dirname("complete-transfered-jsons") / "web").resolve()
        mapped_paths = {Path(str(record.get("json_path") or "")).resolve() for record in by_index.values() if record.get("json_path")}
        for item in items:
            old_path = Path(item["json_path_before_recovery"])
            new_path = Path(item["json_path"])
            if old_path.resolve() == new_path.resolve():
                continue
            if old_path.parent.resolve() != output_root:
                raise RuntimeError(f"拒绝删除根目录外旧副本: {old_path}")
            if not new_path.is_file():
                raise RuntimeError(f"恢复后文件不存在，拒绝删除旧副本: {new_path}")
            if old_path.resolve() in mapped_paths:
                raise RuntimeError(f"旧副本仍被 map 引用，拒绝删除: {old_path}")
            if old_path.is_file():
                old_path.unlink()
                stale_deleted += 1
                item["stale_copy_deleted"] = True
    report = {
        "report_version": "web-internship-boundary-recovery-v2",
        "status": "complete" if (args.complete or args.cleanup_stale) else "issues_recorded_before_repair",
        "checked_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "affected_records": len(items),
        "stale_copies_deleted": stale_deleted,
        "items": items,
    }
    atomic_json(REPORT_PATH, report)
    print(json.dumps({"status": report["status"], "affected_records": len(items), "stale_copies_deleted": stale_deleted}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
