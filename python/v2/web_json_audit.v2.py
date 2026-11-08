"""Audit Web HTML-like -> JSON v2 outputs against the conversion map."""

from __future__ import annotations
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1] / "common"))
import rc_config as _rc  # noqa: E402  项目统一配置（python/common/rc_config.py）
# EN: noqa: E402  project-wide configuration (python/common/rc_config.py)
# JA: noqa: E402  プロジェクト共通設定（python/common/rc_config.py）

import argparse
import importlib.util
import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = _rc.project_root()
DEFAULT_MAP = PROJECT_ROOT / _rc.dirname("complete-transfered-htmls") / "web" / "web_conversion_map.v2.json"
DEFAULT_JSON_DIR = PROJECT_ROOT / _rc.dirname("complete-transfered-jsons") / "web"
DEFAULT_REPORT = DEFAULT_JSON_DIR / "_web_json_audit.v2.json"
EXPECTED_FIELDS = {
    "expected_city", "expected_position", "expected_salary",
    "expected_annual_salary_min", "expected_annual_salary_max",
    "expected_industry", "expected_employment_type", "expected_start_date",
}
LIST_FIELDS = {
    "work_experiences", "education_list", "project_list", "training_list",
    "certificate_list", "language_list", "skills_list", "communication_list",
}
REQUIRED_TOP = {
    "schema_version", "record_id", "source", "extraction", "dates",
    "classification", "structured_data", "raw_text", "quality",
}


def normalize_path(value: Any) -> str:
    return os.path.normcase(os.path.normpath(os.path.abspath(str(value or ""))))


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


def load_full_reviewer() -> Any:
    path = _rc.PYTHON_DIR / "v2" / "web_full_review.v2.py"
    spec = importlib.util.spec_from_file_location("web_full_review_v2_audit", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载 Web 全字段审计器: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def no_nested_raw_text(value: Any, path: str = "") -> list[str]:
    errors: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else key
            if key == "raw_text":
                errors.append(f"nested_raw_text:{child_path}")
            else:
                errors.extend(no_nested_raw_text(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            errors.extend(no_nested_raw_text(child, f"{path}[{index}]"))
    return errors


def normalized_language(resume: dict[str, Any]) -> str:
    value = str(resume.get("resume_language") or resume.get("resume_languge") or "").strip().lower()
    aliases = {"cn": "zh", "chinese": "zh", "中文": "zh", "jp": "ja", "日文": "ja"}
    return aliases.get(value, value)


def audit_payload(path: Path, payload: Any, record: dict[str, Any], full_reviewer: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(payload, dict):
        return ["root_not_object"]
    missing = REQUIRED_TOP - set(payload)
    extra = set(payload) - REQUIRED_TOP
    if missing:
        errors.append(f"missing_top:{','.join(sorted(missing))}")
    if extra:
        errors.append(f"extra_top:{','.join(sorted(extra))}")
    source = payload.get("source")
    if not isinstance(source, dict):
        errors.append("source_not_object")
    else:
        expected_source = normalize_path(record.get("source_path"))
        actual_source = normalize_path(source.get("original_path"))
        if expected_source != actual_source:
            errors.append("source_original_path_mismatch")
        html_path = Path(str(source.get("html_path") or source.get("path") or ""))
        if not html_path.exists():
            errors.append("staged_html_missing")
    structured = payload.get("structured_data")
    if not isinstance(structured, dict):
        return errors + ["structured_data_not_object"]
    expected_sd = {"base_info", "expected_info", "current_info", "education_info", "resumes"}
    if set(structured) != expected_sd:
        errors.append("structured_data_keys_mismatch")
    expected = structured.get("expected_info")
    if not isinstance(expected, dict) or set(expected) != EXPECTED_FIELDS:
        errors.append("expected_info_not_8_field_object")
    resumes = structured.get("resumes")
    if not isinstance(resumes, list) or not resumes:
        errors.append("resumes_missing")
        resumes = []
    for index, resume in enumerate(resumes):
        if not isinstance(resume, dict):
            errors.append(f"resume_{index}_not_object")
            continue
        if not isinstance(resume.get("base_info"), dict):
            errors.append(f"resume_{index}_base_info_missing")
        expected_list = resume.get("expected_list")
        if not isinstance(expected_list, list):
            errors.append(f"resume_{index}_expected_list_not_array")
        for field in LIST_FIELDS:
            if not isinstance(resume.get(field), list):
                errors.append(f"resume_{index}_{field}_not_array")
    if resumes and isinstance(resumes[0], dict):
        first = resumes[0]
        if normalized_language(first) != "zh":
            errors.append("first_resume_not_zh")
        if structured.get("base_info") != first.get("base_info"):
            errors.append("base_info_snapshot_mismatch")
        first_expected = first.get("expected_list") or []
        first_expected_object = first_expected[0] if first_expected and isinstance(first_expected[0], dict) else {}
        if structured.get("expected_info") != first_expected_object:
            errors.append("expected_info_snapshot_mismatch")
        has_contact = False
        for resume in resumes:
            resume_base = resume.get("base_info") if isinstance(resume, dict) else {}
            if isinstance(resume_base, dict) and str(
                resume_base.get("phone") or resume_base.get("mobile_phone") or resume_base.get("email") or ""
            ).strip():
                has_contact = True
                break
        quality = payload.get("quality") or {}
        quality_contact = quality.get("contact") if isinstance(quality, dict) else {}
        if isinstance(quality_contact, dict) and str(
            quality_contact.get("phone") or quality_contact.get("email") or ""
        ).strip():
            has_contact = True
        if not has_contact:
            errors.append("no_contact_in_base_info")
    raw_text = payload.get("raw_text")
    if not isinstance(raw_text, str) or len(raw_text.strip()) < 20:
        errors.append("raw_text_missing_or_short")
    errors.extend(no_nested_raw_text(payload.get("source"), "source"))
    errors.extend(no_nested_raw_text(payload.get("extraction"), "extraction"))
    errors.extend(no_nested_raw_text(payload.get("dates"), "dates"))
    errors.extend(no_nested_raw_text(payload.get("classification"), "classification"))
    errors.extend(no_nested_raw_text(payload.get("structured_data"), "structured_data"))
    source_path = Path(str(record.get("stage_path") or record.get("html_path") or record.get("source_path") or ""))
    if source_path.is_file():
        plain = full_reviewer.source_plain(source_path)
        for finding in full_reviewer.review_payload(payload, record, path, plain):
            errors.append(f"full_review:{finding.get('code', 'unknown')}")
    return sorted(set(errors))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="审计 Web HTML-like -> JSON v2 全量结果" " / Audit the full results of Web HTML-like -> JSON v2 / Web HTML 風 -> JSON v2 の全件結果を監査する")
    parser.add_argument("--map", dest="map_path", type=Path, default=DEFAULT_MAP)
    parser.add_argument("--json-dir", type=Path, default=DEFAULT_JSON_DIR)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--apply", action="store_true", help="把 audit_passed/audit_failed 回写 map" " / Write audit_passed/audit_failed back to the map / audit_passed/audit_failed をマップに書き戻す")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    full_reviewer = load_full_reviewer()
    map_payload = json.loads(args.map_path.read_text(encoding="utf-8"))
    records = map_payload.get("records", []) if isinstance(map_payload, dict) else map_payload
    records = [row for row in records if isinstance(row, dict)]
    by_json = {
        normalize_path(row.get("json_path")): row
        for row in records
        if row.get("json_path")
    }
    outputs = [
        path for path in args.json_dir.rglob("*.json")
        if not path.name.startswith("_")
    ] if args.json_dir.exists() else []
    items: list[dict[str, Any]] = []
    pass_count = 0
    fail_count = 0
    orphan_count = 0
    for path in sorted(outputs):
        record = by_json.get(normalize_path(path))
        if record is None:
            orphan_count += 1
            items.append({"json_path": str(path), "status": "orphan", "errors": ["not_in_map"]})
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            errors = audit_payload(path, payload, record, full_reviewer)
        except Exception as exc:
            errors = [f"json_read_error:{exc}"]
        status = "audit_passed" if not errors else "audit_failed"
        if errors:
            fail_count += 1
        else:
            pass_count += 1
        record["audit_status"] = status
        record["audit_errors"] = errors
        items.append({
            "index": record.get("index"),
            "source_path": record.get("source_path", ""),
            "json_path": str(path),
            "status": status,
            "errors": errors,
        })

    missing_outputs = []
    for record in records:
        if str(record.get("status") or "") in {"passed", "passed_existing", "audit_passed"}:
            json_path = Path(str(record.get("json_path") or ""))
            if not json_path.exists():
                missing_outputs.append(record.get("index"))
    report = {
        "schema_version": "web-json-audit-v2",
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "map_path": str(args.map_path.resolve()),
        "json_dir": str(args.json_dir.resolve()),
        "counts": {
            "map_records": len(records),
            "json_outputs": len(outputs),
            "audit_passed": pass_count,
            "audit_failed": fail_count,
            "orphan_outputs": orphan_count,
            "missing_expected_outputs": len(missing_outputs),
        },
        "missing_expected_indices": missing_outputs,
        "items": items,
    }
    atomic_json(args.report, report)
    if args.apply and isinstance(map_payload, dict):
        map_payload["last_audit_report"] = str(args.report.resolve())
        map_payload["last_audit_at"] = report["generated_at"]
        atomic_json(args.map_path, map_payload)
    print(json.dumps(report["counts"], ensure_ascii=False))
    print(f"审计报告: {args.report}" f" / Audit report: {args.report} / 監査レポート：{args.report}")
    return 0 if fail_count == 0 and orphan_count == 0 and not missing_outputs else 2


if __name__ == "__main__":
    raise SystemExit(main())
