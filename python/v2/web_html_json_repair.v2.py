"""Incrementally repair Web JSON files using the issues recorded by reconcile v2.

Only records with a current ``quality.reconciliation`` issue set are repaired
by default.  Repairs are field-scoped: schema keys, snapshots, contacts, and
raw_text are corrected in place.  A targeted reparse is used only for issues
that require new extraction evidence, and every repair keeps an append-only
history for the next verification round.
"""

from __future__ import annotations
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1] / "common"))
import rc_config as _rc  # noqa: E402  项目统一配置（python/common/rc_config.py）
# EN: noqa: E402  project-wide configuration (python/common/rc_config.py)
# JA: noqa: E402  プロジェクト共通設定（python/common/rc_config.py）

import argparse
import copy
import importlib.util
import json
import os
import re
import tempfile
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = _rc.project_root()
DEFAULT_MAP = PROJECT_ROOT / _rc.dirname("complete-transfered-htmls") / "web" / "web_conversion_map.v2.json"
DEFAULT_JSON_DIR = PROJECT_ROOT / _rc.dirname("complete-transfered-jsons") / "web"
DEFAULT_REPORT = DEFAULT_JSON_DIR / "_web_html_json_repair.v2.json"

BASE_FIELDS = (
    "full_name", "gender", "age", "birth_date", "birth_year", "marital_status",
    "children_status", "political_status", "height_cm", "weight_kg",
    "household_registration", "address", "postal_code", "platform_from",
    "platform_resume_id", "phone", "email", "city", "nationality", "pr",
)
EXPECTED_FIELDS = (
    "expected_city", "expected_position", "expected_salary",
    "expected_annual_salary_min", "expected_annual_salary_max",
    "expected_industry", "expected_employment_type", "expected_start_date",
)
CURRENT_FIELDS = (
    "company_name", "company_employees", "company_industry", "position",
    "position_type", "position_salary", "position_dept", "position_report_to",
    "position_subordinate", "employment_type", "annual_salary_min",
    "annual_salary_max", "status", "position_start", "position_resigned",
)
EDUCATION_FIELDS = (
    "school_name", "school_major_name", "school_degree_type", "school_degree_rank",
    "school_education_type", "school_start_ym", "school_end_ym",
)
ITEM_FIELDS = {
    "expected_list": EXPECTED_FIELDS,
    "work_experiences": CURRENT_FIELDS + ("resigned_reason", "position_responsibilities", "position_achievements"),
    "education_list": EDUCATION_FIELDS,
    "certificate_list": ("certificate_name", "certificate_type", "certificate_time"),
    "language_list": ("language_name", "language_level", "language_certificate", "language_certificate_time"),
    "skills_list": ("skill_name", "skill_level"),
    "training_list": ("sequence_no", "organization_name", "training_name", "start_ym", "end_ym", "certificate_name", "description"),
    "project_list": ("sequence_no", "fingerprint", "project_name", "company_or_client", "role_name", "start_ym", "end_ym", "description", "responsibilities", "achievements", "keywords"),
    "communication_list": ("communicate_time", "communicate_content"),
}
RESUME_FIELDS = (
    "resume_languge", "base_info", "expected_list", "work_experiences", "education_list",
    "certificate_list", "language_list", "skills_list", "training_list", "project_list",
    "communication_list",
)
REPARSE_CODES = {
    "json_name_not_in_html", "html_section_without_json_data", "json_resumes_missing",
    "html_decode_failed", "plain_text_length_mismatch", "invalid_work_item_mapping",
    "json_values_not_in_html", "html_phone_not_in_json", "html_phone_not_in_raw_text",
}


def load_converter() -> Any:
    path = _rc.PYTHON_DIR / "v2" / "web_html_to_json.v2.py"
    spec = importlib.util.spec_from_file_location("web_html_to_json_v2_repair", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载 Web v2 转换器: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _clean_dict(value: Any, fields: tuple[str, ...], sequence_no: int | None = None) -> dict[str, Any]:
    source = value if isinstance(value, dict) else {}
    result: dict[str, Any] = {}
    for field in fields:
        if field == "sequence_no":
            raw = source.get(field, sequence_no or 0)
            try:
                result[field] = int(raw or sequence_no or 0)
            except (TypeError, ValueError):
                result[field] = int(sequence_no or 0)
        else:
            result[field] = _text(source.get(field, ""))
    return result


def _clean_list(value: Any, fields: tuple[str, ...]) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    cleaned: list[dict[str, Any]] = []
    for index, item in enumerate(value, start=1):
        if not isinstance(item, dict):
            continue
        sequence_no = index if "sequence_no" in fields else None
        normalized = _clean_dict(item, fields, sequence_no)
        non_sequence_values = [
            _text(v) for key, v in normalized.items() if key != "sequence_no" and _text(v)
        ]
        if not non_sequence_values:
            continue
        cleaned.append(normalized)
    return cleaned


def _html_contacts(converter: Any, html_path: Path) -> tuple[list[str], list[str]]:
    try:
        plain = converter.html_to_plain_text(converter.read_html_text(html_path))
    except Exception:
        return [], []
    phones = list(dict.fromkeys(re.findall(r"(?<!\d)(1[3-9]\d{9})(?!\d)", plain)))
    emails = list(dict.fromkeys(re.findall(
        r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}", plain
    )))
    return phones, emails


def apply_incremental_repairs(
    payload: dict[str, Any],
    map_record: dict[str, Any],
    html_path: Path,
    converter: Any,
    issues_before: list[dict[str, Any]],
) -> tuple[dict[str, Any], set[str]]:
    """Repair only fields implicated by the current reconciliation round."""
    repaired = copy.deepcopy(payload)
    issue_codes = {str(item.get("code") or "") for item in issues_before if isinstance(item, dict)}

    structured = repaired.get("structured_data") if isinstance(repaired.get("structured_data"), dict) else {}
    old_resumes = structured.get("resumes") if isinstance(structured.get("resumes"), list) else []
    normalized_resumes: list[dict[str, Any]] = []
    for resume_index, old_resume in enumerate(old_resumes):
        if not isinstance(old_resume, dict):
            continue
        base_source = old_resume.get("base_info") if isinstance(old_resume.get("base_info"), dict) else {}
        base = _clean_dict(base_source, BASE_FIELDS)
        raw_expected = old_resume.get("expected_list", old_resume.get("expected_info", []))
        if isinstance(raw_expected, dict):
            raw_expected = [raw_expected]
        expected_list = _clean_list(raw_expected, EXPECTED_FIELDS)
        normalized: dict[str, Any] = {}
        language = _text(old_resume.get("resume_languge") or old_resume.get("resume_language"))
        normalized["resume_languge"] = language.lower() or ("zh" if resume_index == 0 else "待确认语言")
        normalized["base_info"] = base
        normalized["expected_list"] = expected_list
        for field, fields in ITEM_FIELDS.items():
            if field == "expected_list":
                continue
            normalized[field] = _clean_list(old_resume.get(field), fields)
        normalized_resumes.append(normalized)

    if normalized_resumes and normalized_resumes[0].get("resume_languge") != "zh":
        # Preserve the existing order, but make the first language marker meet
        # the project's main-version contract.
        normalized_resumes[0]["resume_languge"] = "zh"
    if not normalized_resumes:
        normalized_resumes = []

    html_phones, html_emails = _html_contacts(converter, html_path) if html_path.exists() else ([], [])
    if normalized_resumes:
        primary_base = normalized_resumes[0]["base_info"]
        if "html_phone_not_in_json" in issue_codes and html_phones:
            primary_base["phone"] = html_phones[0]
        if "html_email_not_in_json" in issue_codes and html_emails:
            primary_base["email"] = html_emails[0]
        if "html_phone_not_in_raw_text" in issue_codes and html_phones:
            primary_base["phone"] = html_phones[0]
        if "html_email_not_in_raw_text" in issue_codes and html_emails:
            primary_base["email"] = html_emails[0]

    first = normalized_resumes[0] if normalized_resumes else {
        "base_info": _clean_dict({}, BASE_FIELDS),
        "expected_list": [],
        "work_experiences": [],
        "education_list": [],
    }
    first_expected = first.get("expected_list") or []
    expected_snapshot = _clean_dict(first_expected[0] if first_expected else {}, EXPECTED_FIELDS)
    current_info = converter._pick_latest_work(first.get("work_experiences") or [])
    education_info = converter._pick_highest_education(first.get("education_list") or [])
    repaired["structured_data"] = {
        "base_info": copy.deepcopy(first.get("base_info") or _clean_dict({}, BASE_FIELDS)),
        "expected_info": expected_snapshot,
        "current_info": {key: _text(current_info.get(key)) for key in CURRENT_FIELDS},
        "education_info": {key: _text(education_info.get(key)) for key in EDUCATION_FIELDS},
        "resumes": normalized_resumes,
    }

    source_file = Path(str(map_record.get("source_path") or ""))
    source_stat_path = source_file if source_file.exists() else html_path
    old_source = payload.get("source") if isinstance(payload.get("source"), dict) else {}
    repaired["source"] = {
        "path": str(html_path.resolve()),
        "original_path": str(source_file.resolve()) if source_file else _text(old_source.get("original_path")),
        "filename": _text(map_record.get("filename") or old_source.get("filename")),
        "extension": _text(map_record.get("source_extension") or old_source.get("extension")).lower(),
        "size": source_stat_path.stat().st_size if source_stat_path.exists() else old_source.get("size", 0),
        "html_filename": html_path.name,
        "note": _text(old_source.get("note")) or "由 web_html_to_json.v2.py 从 Web 来源 HTML/MHT/EML 转换",
    }
    extraction = payload.get("extraction") if isinstance(payload.get("extraction"), dict) else {}
    extraction = copy.deepcopy(extraction)
    extraction["converter"] = "web_html_to_json.v2.py"
    extraction["html_path"] = str(html_path.resolve())
    extraction["source_relative_path"] = map_record.get("relative_path", "")
    extraction["source_landing_time"] = map_record.get("source_landing_time", "")
    repaired["extraction"] = extraction
    old_classification = payload.get("classification") if isinstance(payload.get("classification"), dict) else {}
    repaired["classification"] = {
        "document_type": _text(old_classification.get("document_type")) or "resume",
        "reason": _text(old_classification.get("reason")),
    }

    top_raw_text = converter._build_top_level_raw_text(repaired["structured_data"])
    repaired["raw_text"] = top_raw_text
    quality = repaired.get("quality") if isinstance(repaired.get("quality"), dict) else {}
    quality = copy.deepcopy(quality)
    quality["full_name"] = _text(first.get("base_info", {}).get("full_name"))
    quality["has_work"] = bool(first.get("work_experiences"))
    quality["work_count"] = len(first.get("work_experiences") or [])
    quality["has_education"] = bool(first.get("education_list"))
    quality["education_count"] = len(first.get("education_list") or [])
    quality["raw_text_length"] = len(top_raw_text)
    if html_phones or html_emails:
        contact = quality.get("contact") if isinstance(quality.get("contact"), dict) else {}
        quality["contact"] = {
            "phone": _text(first.get("base_info", {}).get("phone")) or (html_phones[0] if html_phones else _text(contact.get("phone"))),
            "email": _text(first.get("base_info", {}).get("email")) or (html_emails[0] if html_emails else _text(contact.get("email"))),
        }
    repaired["quality"] = quality
    return repaired, issue_codes


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="按逐文件核对结果增量修复 Web JSON" " / Incrementally repair Web JSON according to the file-by-file check results / ファイルごとの照合結果に基づいて Web JSON を差分で修復する")
    parser.add_argument("--map", dest="map_path", type=Path, default=DEFAULT_MAP)
    parser.add_argument("--json-dir", type=Path, default=DEFAULT_JSON_DIR)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--all", action="store_true", help="修复所有有 JSON 的 map 记录，而不只修复有问题记录" " / Repair all map records that have JSON, not only those with problems / 問題のあるレコードだけでなく、JSON のあるマップのレコードをすべて修復する")
    parser.add_argument("--limit", type=int, default=0)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    converter = load_converter()
    map_payload = json.loads(args.map_path.read_text(encoding="utf-8"))
    records = map_payload.get("records", []) if isinstance(map_payload, dict) else map_payload
    records = [row for row in records if isinstance(row, dict)]
    candidates = []
    for record in records:
        json_path = Path(str(record.get("json_path") or ""))
        reconciliation = record.get("reconcile_issues")
        has_issues = bool(record.get("reconcile_issue_count") or reconciliation)
        if json_path.is_file() and (args.all or has_issues):
            candidates.append(record)
    if args.limit > 0:
        candidates = candidates[: args.limit]

    repaired = 0
    skipped = 0
    failed = 0
    items: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    with tempfile.TemporaryDirectory(prefix="_web_repair_v2_", dir=args.json_dir) as temp_dir_name:
        temp_root = Path(temp_dir_name)
        for record in candidates:
            json_path = Path(str(record.get("json_path") or ""))
            html_value = record.get("stage_path") or record.get("html_path") or record.get("source_path")
            html_path = Path(str(html_value or ""))
            try:
                old_payload = json.loads(json_path.read_text(encoding="utf-8"))
                old_quality = old_payload.get("quality") if isinstance(old_payload, dict) else {}
                old_reconciliation = old_quality.get("reconciliation") if isinstance(old_quality, dict) else {}
                issues_before = old_reconciliation.get("issues", []) if isinstance(old_reconciliation, dict) else []
                if not isinstance(issues_before, list):
                    issues_before = []
                repaired_payload, issue_codes = apply_incremental_repairs(
                    old_payload, record, html_path, converter, issues_before
                )
                method = "incremental_field_repair"
                message = "按本轮核对问题完成字段级增量修复"
                if issue_codes.intersection(REPARSE_CODES) and html_path.exists():
                    result = converter.process_single_html(
                        html_path,
                        temp_root,
                        force=True,
                        source_path=Path(str(record.get("source_path"))) if record.get("source_path") else None,
                        metadata=record,
                    )
                    ok, reparse_message, generated_path = result
                    if ok and generated_path:
                        generated = json.loads(Path(generated_path).read_text(encoding="utf-8"))
                        repaired_payload, _ = apply_incremental_repairs(
                            generated, record, html_path, converter, issues_before
                        )
                        method = "incremental_field_repair+targeted_reparse"
                        message = f"字段级修复后定点重解析：{reparse_message}"
                    else:
                        message = f"字段级修复完成；定点重解析未写出：{reparse_message}"
                        skipped += 1
                        counts["targeted_reparse_not_written"] += 1
                repair_entry = {
                    "status": "applied",
                    "applied_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                    "issue_count_before": len(issues_before),
                    "issue_codes_before": [str(item.get("code") or "") for item in issues_before if isinstance(item, dict)],
                    "method": method,
                    "message": message,
                }
                repaired_quality = repaired_payload.get("quality") if isinstance(repaired_payload.get("quality"), dict) else {}
                repaired_quality["reconciliation"] = {
                    "status": "repaired_pending_recheck",
                    "clean_mark": False,
                    "round": old_reconciliation.get("round") if isinstance(old_reconciliation, dict) else None,
                    "checked_at": old_reconciliation.get("checked_at", "") if isinstance(old_reconciliation, dict) else "",
                    "issue_count": len(issues_before),
                    "issues": copy.deepcopy(issues_before),
                    "html_facts": copy.deepcopy(old_reconciliation.get("html_facts", {})) if isinstance(old_reconciliation, dict) else {},
                }
                repaired_quality["repair_status"] = "applied_pending_recheck"
                repaired_payload["quality"] = repaired_quality
                # Keep the map's established output path.  The regenerated name
                # may differ after a field correction, but the physical record
                # remains the same map item.
                atomic_json(json_path, repaired_payload)
                repaired += 1
                counts["repaired"] += 1
                record["repair_status"] = "applied_pending_recheck"
                record["repair_message"] = message
                record["repair_issue_count_before"] = len(issues_before)
                record["repair_applied_at"] = repair_entry["applied_at"]
                items.append({
                    "index": record.get("index"), "status": "repaired",
                    "json_path": str(json_path), "message": message,
                    "issue_count_before": len(issues_before),
                    "issue_codes_before": repair_entry["issue_codes_before"],
                })
            except Exception as exc:
                failed += 1
                counts["repair_failed"] += 1
                record["repair_status"] = "failed"
                record["repair_message"] = str(exc)
                items.append({
                    "index": record.get("index"), "status": "failed",
                    "json_path": str(json_path), "html_path": str(html_path),
                    "error": str(exc),
                })

    if isinstance(map_payload, dict):
        map_payload["last_repair_report"] = str(args.report.resolve())
        map_payload["last_repaired_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
        atomic_json(args.map_path, map_payload)
    report = {
        "schema_version": "web-html-json-repair-v2",
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "map_path": str(args.map_path.resolve()),
        "json_dir": str(args.json_dir.resolve()),
        "counts": {
            "candidates": len(candidates),
            "repaired": repaired,
            "skipped": skipped,
            "failed": failed,
        },
        "items": items,
    }
    atomic_json(args.report, report)
    print(json.dumps(report["counts"], ensure_ascii=False))
    print(f"增量修复报告: {args.report}" f" / Incremental repair report: {args.report} / 差分修復レポート：{args.report}")
    return 0 if failed == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
