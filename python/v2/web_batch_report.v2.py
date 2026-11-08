"""Rebuild a full Web batch report from the durable conversion map."""

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
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = _rc.project_root()
DEFAULT_MAP = PROJECT_ROOT / _rc.dirname("complete-transfered-htmls") / "web" / "web_conversion_map.v2.json"
DEFAULT_REPORT = PROJECT_ROOT / _rc.dirname("complete-transfered-jsons") / "web" / "_web_batch_report.v2.json"


def atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    finally:
        Path(temp_name).unlink(missing_ok=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="从 Web map 重建全量批处理报告" " / Rebuild the full batch report from the Web map / Web マップから、一括処理の全件レポートを再構築する")
    parser.add_argument("--map", dest="map_path", type=Path, default=DEFAULT_MAP)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload = json.loads(args.map_path.read_text(encoding="utf-8"))
    records = payload.get("records", []) if isinstance(payload, dict) else payload
    records = [row for row in records if isinstance(row, dict)]
    status_counts = Counter(str(row.get("status") or "pending") for row in records)
    items = []
    for row in records:
        status = str(row.get("status") or "pending")
        items.append({
            "seq": row.get("index"),
            "report_row": row.get("report_row"),
            "html": row.get("html_filename") or row.get("filename", ""),
            "source_path": row.get("source_path", ""),
            "stage_path": row.get("stage_path", ""),
            "status": status,
            "success": status in {"passed", "passed_existing", "audit_passed"},
            "skipped": status in {"not_resume", "skipped_no_contact"},
            "message": row.get("message", ""),
            "json_path": row.get("json_path", ""),
        })
    report = {
        "schema_version": "web-batch-report-v2",
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "map_path": str(args.map_path.resolve()),
        "source_scope": payload.get("source_scope", "") if isinstance(payload, dict) else "",
        "counts": {
            "found": len(records),
            "success": sum(status_counts[x] for x in ("passed", "passed_existing", "audit_passed")),
            "failed": status_counts.get("failed", 0),
            "skipped": status_counts.get("not_resume", 0) + status_counts.get("skipped_no_contact", 0),
            "not_resume": status_counts.get("not_resume", 0),
            "skipped_no_contact": status_counts.get("skipped_no_contact", 0),
        },
        "status_counts": dict(status_counts),
        "items": items,
        "note": "从持久化 Web map 重建；全量转换过程日志见控制台输出。",
    }
    atomic_json(args.report, report)
    print(json.dumps(report["counts"], ensure_ascii=False))
    print(f"批处理报告: {args.report}" f" / Batch report: {args.report} / 一括処理レポート：{args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
