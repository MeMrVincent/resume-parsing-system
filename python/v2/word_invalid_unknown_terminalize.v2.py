"""将 unknown 校验失败 JSON 及其全部源文档登记为无效简历终态。

EN: Register the unknown JSON that failed validation, and all their source documents, as invalid résumés in a terminal state.

JA: 検証に失敗した unknown の JSON とそのすべてのソース文書を、無効な履歴書として終了状態に登録する。
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
    parser.add_argument("--validation-report", type=Path, required=True)
    parser.add_argument("--map", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    validation = json.loads(args.validation_report.read_text(encoding="utf-8"))
    invalid_items = [item for item in validation.get("items", []) if item.get("status") == "invalid"]
    source_reasons: dict[str, str] = {}
    json_records = []
    for item in invalid_items:
        json_path = Path(str(item.get("input_json") or ""))
        errors = [str(value) for value in item.get("errors") or []]
        reason = "unknown JSON 严格校验未通过：" + ", ".join(errors)
        payload = json.loads(json_path.read_text(encoding="utf-8"))
        classification = payload.setdefault("classification", {})
        classification["document_type"] = "invalid_resume"
        classification["reason"] = reason
        extraction = payload.setdefault("extraction", {})
        extraction["status"] = "invalid"
        extraction["validation_errors"] = errors
        json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        originals = [str(value) for value in item.get("original_paths") or []]
        for source_path in originals:
            source_reasons[norm(source_path)] = reason
        json_records.append({"json_path": str(json_path), "errors": errors, "original_paths": originals})

    rows = json.loads(args.map.read_text(encoding="utf-8"))
    updated = 0
    deleted_html = 0
    for row in rows:
        source_key = norm(row.get("source_path"))
        if source_key not in source_reasons:
            continue
        html_path = Path(str(row.get("html_path") or ""))
        if html_path.is_file():
            html_path.unlink()
            deleted_html += 1
        row["status"] = "non_resume"
        row["terminal_classification"] = "invalid_resume"
        row["error_reason"] = source_reasons[source_key]
        row["parsed_completed"] = False
        row["json_status"] = "invalid_resume"
        row["html_status"] = "deleted_after_invalid_resume_classification"
        row["json_path"] = ""
        updated += 1

    if updated != len(source_reasons):
        raise RuntimeError(f"源路径登记数量不一致：期望 {len(source_reasons)}，实际 {updated}")
    args.map.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report = {
        "invalid_json_files": len(json_records),
        "source_documents": len(source_reasons),
        "updated_map_rows": updated,
        "deleted_html": deleted_html,
        "items": json_records,
    }
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("invalid_json_files", "source_documents", "updated_map_rows", "deleted_html")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
