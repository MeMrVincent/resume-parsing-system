from __future__ import annotations
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1] / "common"))
import rc_config as _rc  # noqa: E402  项目统一配置（python/common/rc_config.py）
# EN: noqa: E402  project-wide configuration (python/common/rc_config.py)
# JA: noqa: E402  プロジェクト共通設定（python/common/rc_config.py）

import argparse
import hashlib
import json
import re
import tempfile
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = _rc.project_root()
PDF_ROOT = PROJECT_ROOT / _rc.dirname("complete-transfered-htmls") / "pdf"
DEFAULT_MAP = PDF_ROOT / "rebuild-work" / "pdf_rebuild_map.v2.json"
DEFAULT_JSON_ROOT = PDF_ROOT / "rebuild-work" / "json-by-candidate"
DEFAULT_REPORT = PDF_ROOT / "rebuild-reports" / "pdf_candidate_audit.v2.json"
VERSION = "pdf-rebuild-candidate-audit-v2.0.0"

TOP_KEYS = {"schema_version", "record_id", "source", "dates", "extraction", "classification", "structured_data", "raw_text", "quality"}
BASE_FIELDS = {"full_name", "gender", "age", "birth_date", "birth_year", "marital_status", "children_status", "political_status", "height_cm", "weight_kg", "household_registration", "address", "postal_code", "platform_from", "platform_resume_id", "phone", "email", "city", "nationality", "pr"}
LIST_FIELDS = {
    "expected_list": {"expected_city", "expected_position", "expected_salary", "expected_annual_salary_min", "expected_annual_salary_max", "expected_industry", "expected_employment_type", "expected_start_date"},
    "work_experiences": {"company_name", "company_employees", "company_industry", "position", "position_type", "position_salary", "position_dept", "position_report_to", "position_subordinate", "employment_type", "annual_salary_min", "annual_salary_max", "status", "position_start", "position_resigned", "resigned_reason", "position_responsibilities", "position_achievements"},
    "education_list": {"school_name", "school_major_name", "school_degree_type", "school_degree_rank", "school_education_type", "school_start_ym", "school_end_ym"},
    "certificate_list": {"certificate_name", "certificate_type", "certificate_time"},
    "language_list": {"language_name", "language_level", "language_certificate", "language_certificate_time"},
    "skills_list": {"skill_name", "skill_level"},
    "training_list": {"sequence_no", "organization_name", "training_name", "start_ym", "end_ym", "certificate_name", "description"},
    "project_list": {"sequence_no", "fingerprint", "project_name", "company_or_client", "role_name", "start_ym", "end_ym", "description", "responsibilities", "achievements", "keywords"},
    "communication_list": {"communicate_time", "communicate_content"},
}
STRUCTURED_KEYS = {"base_info", "expected_info", "current_info", "education_info", "resumes"}
NAME_NOISE = re.compile(r"履歴書|職務経歴|基本情報|个人简历|resume|curriculum|vitae|看图王|^(?:address|job preferences?|住所|ふりがな)$", re.I)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="独立审计 PDF v2 候选人级合并 JSON" " / Independent audit of the PDF v2 candidate-level merged JSON / PDF v2 の候補者単位に統合した JSON を独立して監査する")
    parser.add_argument("--map", type=Path, default=DEFAULT_MAP)
    parser.add_argument("--json-root", type=Path, default=DEFAULT_JSON_ROOT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    return parser.parse_args()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".tmp", dir=path.parent, delete=False) as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
        temporary = Path(stream.name)
    temporary.replace(path)


def compact(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or "")).casefold()


def source_key(source_file: dict[str, Any]) -> str:
    return f"{str(source_file.get('sha256') or '').casefold()}|{str(source_file.get('input_path') or '').casefold()}"


def audit_payload(path: Path, payload: dict[str, Any], valid_keys: set[str]) -> tuple[list[dict[str, str]], list[str]]:
    issues: list[dict[str, str]] = []

    def add(code: str, field: str, detail: str) -> None:
        issues.append({"code": code, "field": field, "detail": detail})

    if set(payload) != TOP_KEYS:
        add("top_keys_mismatch", "$", f"missing={sorted(TOP_KEYS-set(payload))} extra={sorted(set(payload)-TOP_KEYS)}")
    source_files = (payload.get("source") or {}).get("source_files") or []
    keys: list[str] = []
    for index, source_file in enumerate(source_files):
        source_hash = str((source_file or {}).get("sha256") or "").casefold()
        key = source_key(source_file or {})
        if not source_hash:
            add("source_hash_missing", f"source.source_files[{index}].sha256", "")
        elif key not in valid_keys:
            add("source_not_in_map", f"source.source_files[{index}]", key)
        keys.append(key)
    if not keys:
        add("source_files_missing", "source.source_files", "")
    hashes = [key.split("|", 1)[0] for key in keys if key.split("|", 1)[0]]
    expected_id = hashlib.sha256("|".join(sorted(hashes)).encode("utf-8")).hexdigest()
    if keys and payload.get("record_id") != expected_id:
        add("record_id_mismatch", "record_id", str(payload.get("record_id") or ""))
    for field in ("resume_updated_date", "resume_download_date", "sys_created_date", "sys_updated_date"):
        if not str((payload.get("dates") or {}).get(field) or "").strip():
            add("missing_date", f"dates.{field}", "")
    structured = payload.get("structured_data") or {}
    if set(structured) != STRUCTURED_KEYS:
        add(
            "structured_keys_mismatch", "structured_data",
            f"missing={sorted(STRUCTURED_KEYS-set(structured))} extra={sorted(set(structured)-STRUCTURED_KEYS)}",
        )
    resumes = structured.get("resumes") or []
    if not resumes:
        add("missing_resumes", "structured_data.resumes", "")
        return issues, keys
    primary = resumes[0]
    if primary.get("resume_language") != "zh":
        add("first_resume_not_chinese", "structured_data.resumes[0].resume_language", str(primary.get("resume_language")))
    if set(primary.get("base_info") or {}) != BASE_FIELDS:
        add("base_fields_mismatch", "structured_data.resumes[0].base_info", "")
    if structured.get("base_info") != primary.get("base_info"):
        add("top_base_not_synced", "structured_data.base_info", "")
    name = str((primary.get("base_info") or {}).get("full_name") or "").strip()
    if not name or NAME_NOISE.search(name):
        add("invalid_full_name", "structured_data.base_info.full_name", name)
    seen_languages: set[str] = set()
    for resume_index, resume in enumerate(resumes):
        language = str(resume.get("resume_language") or "")
        if not language:
            add("missing_resume_language", f"structured_data.resumes[{resume_index}].resume_language", "")
        elif language in seen_languages:
            add("duplicate_resume_language", f"structured_data.resumes[{resume_index}].resume_language", language)
        seen_languages.add(language)
        if "resume_languge" in resume:
            add("legacy_language_key", f"structured_data.resumes[{resume_index}]", "")
        if set(resume.get("base_info") or {}) != BASE_FIELDS:
            add("base_fields_mismatch", f"structured_data.resumes[{resume_index}].base_info", "")
        for collection, expected_fields in LIST_FIELDS.items():
            rows = resume.get(collection)
            if not isinstance(rows, list):
                add("collection_not_list", f"structured_data.resumes[{resume_index}].{collection}", type(rows).__name__)
                continue
            for row_index, row in enumerate(rows):
                if not isinstance(row, dict) or set(row) != expected_fields:
                    actual = set(row) if isinstance(row, dict) else set()
                    add("item_fields_mismatch", f"structured_data.resumes[{resume_index}].{collection}[{row_index}]", f"missing={sorted(expected_fields-actual)} extra={sorted(actual-expected_fields)}")
    raw = str(payload.get("raw_text") or "")
    if len(compact(raw)) < 20:
        add("raw_text_short", "raw_text", str(len(raw)))
    # raw_text is an independent source transcript, not a serialization of
    # structured fields. Identity fields may be established by PDF visual
    # review or source-map metadata even when OCR/Word text omits them.
    if str((payload.get("extraction") or {}).get("raw_text_source") or "") != "canonical_deduplicated_pdf_word_html_text":
        add("raw_text_source_invalid", "extraction.raw_text_source", str((payload.get("extraction") or {}).get("raw_text_source") or ""))
    return issues, keys


def main() -> int:
    cfg = parse_args()
    mapping = read_json(cfg.map)
    valid_keys = {
        f"{str(row.get('source_sha256') or '').casefold()}|{str(row.get('input_path') or '').casefold()}"
        for row in (mapping.get("records") or [])
        if row.get("classification") == "resume"
    }
    coverage: Counter[str] = Counter()
    records: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    record_ids: set[str] = set()
    for path in sorted(cfg.json_root.glob("*.json")):
        try:
            payload = read_json(path)
        except Exception as exc:
            records.append({"json_path": str(path), "status": "failed", "issues": [{"code": "json_unreadable", "field": "$", "detail": str(exc)}]})
            counts["failed"] += 1
            continue
        issues, keys = audit_payload(path, payload, valid_keys)
        coverage.update(item for item in keys if item)
        record_id = str(payload.get("record_id") or "")
        if record_id in record_ids:
            issues.append({"code": "duplicate_record_id", "field": "record_id", "detail": record_id})
        record_ids.add(record_id)
        status = "passed" if not issues else "needs_review"
        counts[status] += 1
        warnings = list((payload.get("quality") or {}).get("warnings") or [])
        quality_state = (
            "translation_pending" if "foreign_translation_missing" in warnings
            else "gpt_translation_review" if "gpt_translation_structure_mismatch" in warnings
            else "source_rework_pending" if "resume_structure_incomplete" in warnings
            else "ready"
        )
        counts[f"quality:{quality_state}"] += 1
        for issue in issues:
            counts[f"issue:{issue['code']}"] += 1
        records.append({"json_path": str(path.resolve()), "status": status, "quality_state": quality_state, "warnings": warnings, "issues": issues})
    missing_hashes = sorted(valid_keys - set(coverage))
    duplicate_hashes = sorted(source_key_value for source_key_value, count in coverage.items() if count != 1)
    report = {
        "version": VERSION,
        "generated_at": datetime.now().astimezone().isoformat(),
        "candidate_total": len(records),
        "source_expected": len(valid_keys),
        "source_covered_once": sum(coverage[source_key_value] == 1 for source_key_value in valid_keys),
        "missing_source_hashes": missing_hashes,
        "duplicate_source_hashes": duplicate_hashes,
        "counts": dict(counts),
        "records": records,
    }
    atomic_json(cfg.report, report)
    print(json.dumps({key: value for key, value in report.items() if key != "records"}, ensure_ascii=False, indent=2))
    print(f"report={cfg.report.resolve()}")
    return 1 if missing_hashes or duplicate_hashes or counts.get("failed") or counts.get("needs_review") else 0


if __name__ == "__main__":
    raise SystemExit(main())
