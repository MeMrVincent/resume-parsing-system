"""终止 failed1 无输出源文件，并清理已判定无效的批次副本与结果 JSON。

EN: Terminate failed1 source files with no output, and clean up batch copies and result JSON already judged invalid.

JA: 出力のない failed1 のソースファイルを終了扱いにし、無効と判定済みのバッチのコピーと結果 JSON を片付ける。
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path


def norm(value: object) -> str:
    return os.path.normcase(os.path.normpath(str(value or "")))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--map", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--without-json-report", type=Path, required=True)
    parser.add_argument("--validation-report", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    rows = json.loads(args.map.read_text(encoding="utf-8"))
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    without = json.loads(args.without_json_report.read_text(encoding="utf-8"))
    validation = json.loads(args.validation_report.read_text(encoding="utf-8"))

    by_source = {norm(item.get("source_path")): item for item in manifest.get("items", [])}
    no_json_sources = {norm(item.get("source_path")) for item in without.get("items", [])}
    invalid_json_sources = {
        norm(source)
        for item in validation.get("items", []) if item.get("status") == "invalid"
        for source in item.get("original_paths") or []
    }
    invalid_sources = no_json_sources | invalid_json_sources
    updated_no_json = deleted_html = deleted_copies = 0
    for row in rows:
        source_key = norm(row.get("source_path"))
        if source_key not in no_json_sources:
            continue
        html = Path(str(row.get("html_path") or ""))
        if html.is_file():
            html.unlink()
            deleted_html += 1
        row["status"] = "non_resume"
        row["terminal_classification"] = "invalid_resume"
        row["error_reason"] = "failed1 批处理未生成有效 JSON，按用户确认登记为无效简历"
        row["parsed_completed"] = False
        row["json_status"] = "invalid_resume"
        row["json_path"] = ""
        row["html_status"] = "deleted_after_invalid_resume_classification"
        updated_no_json += 1

    for source_key in invalid_sources:
        item = by_source.get(source_key) or {}
        copied = Path(str(item.get("copied_path") or ""))
        if copied.is_file():
            copied.unlink()
            deleted_copies += 1

    deleted_result_json = 0
    for item in validation.get("items", []):
        path = Path(str(item.get("input_json") or ""))
        if path.is_file():
            path.unlink()
            deleted_result_json += 1

    if updated_no_json != len(no_json_sources):
        raise RuntimeError(f"无输出源文件登记不完整：期望 {len(no_json_sources)}，实际 {updated_no_json}")
    args.map.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report = {
        "no_json_invalid_sources": len(no_json_sources),
        "invalid_json_sources": len(invalid_json_sources),
        "total_invalid_sources": len(invalid_sources),
        "updated_no_json_rows": updated_no_json,
        "deleted_html": deleted_html,
        "deleted_failed_copies": deleted_copies,
        "deleted_result_json": deleted_result_json,
    }
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
