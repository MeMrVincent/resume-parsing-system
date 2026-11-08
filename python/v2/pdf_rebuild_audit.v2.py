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
DEFAULT_JSON_ROOT = PDF_ROOT / "rebuild-work" / "json-by-source"
DEFAULT_REPORT = PDF_ROOT / "rebuild-reports" / "pdf_pilot_audit.v2.json"
VERSION = "pdf-rebuild-audit-v2.0.0"

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
NAME_NOISE = re.compile(r"履歴書|職務経歴|日本語|日本语|携帯|電話|基本情報|简历|resume|curriculum|vitae", re.I)


def args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="独立审计 PDF v2 逐源暂存 JSON" " / Independent audit of the PDF v2 per-source staging JSON / PDF v2 の元ファイルごとのステージング JSON を独立して監査する")
    parser.add_argument("--map", type=Path, default=DEFAULT_MAP)
    parser.add_argument("--json-root", type=Path, default=DEFAULT_JSON_ROOT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    return parser.parse_args()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".tmp", dir=path.parent, delete=False) as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
        temporary = Path(stream.name)
    temporary.replace(path)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def compact(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or "")).casefold()


def audit_payload(path: Path, payload: dict[str, Any], map_record: dict[str, Any]) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []

    def add(code: str, field: str, detail: str) -> None:
        issues.append({"code": code, "field": field, "detail": detail})

    keys = set(payload)
    if keys != TOP_KEYS:
        add("top_keys_mismatch", "$", f"missing={sorted(TOP_KEYS-keys)} extra={sorted(keys-TOP_KEYS)}")
    source = payload.get("source") or {}
    input_path = Path(str(source.get("path") or ""))
    if input_path.resolve() != Path(map_record["input_path"]).resolve():
        add("source_path_mismatch", "source.path", str(input_path))
    elif not input_path.is_file() or sha256(input_path) != map_record["source_sha256"]:
        add("source_hash_mismatch", "source.source_files[0].sha256", input_path.name)
    for field in ("resume_updated_date", "resume_download_date", "sys_created_date", "sys_updated_date"):
        if not str((payload.get("dates") or {}).get(field) or "").strip():
            add("missing_date", f"dates.{field}", "日期为空")
    structured = payload.get("structured_data") or {}
    resumes = structured.get("resumes") or []
    if not resumes:
        add("missing_resumes", "structured_data.resumes", "没有语言简历")
        return issues
    primary = resumes[0]
    if primary.get("resume_language") != "zh":
        add("first_resume_not_chinese", "structured_data.resumes[0].resume_language", str(primary.get("resume_language")))
    if set(primary.get("base_info") or {}) != BASE_FIELDS:
        add("base_fields_mismatch", "structured_data.resumes[0].base_info", "基础字段集合不标准")
    if structured.get("base_info") != primary.get("base_info"):
        add("top_base_not_synced", "structured_data.base_info", "与中文主版本不一致")
    name = str((structured.get("base_info") or {}).get("full_name") or "")
    if not name or NAME_NOISE.search(name):
        add("invalid_full_name", "structured_data.base_info.full_name", name)
    for resume_index, resume in enumerate(resumes):
        if "resume_languge" in resume:
            add("legacy_language_key", f"structured_data.resumes[{resume_index}]", "仍含 resume_languge")
        for collection, required in LIST_FIELDS.items():
            rows = resume.get(collection)
            if not isinstance(rows, list):
                add("collection_not_list", f"resumes[{resume_index}].{collection}", type(rows).__name__)
                continue
            for row_index, row in enumerate(rows):
                if not isinstance(row, dict):
                    add("item_not_object", f"resumes[{resume_index}].{collection}[{row_index}]", type(row).__name__)
                    continue
                row_keys = set(row)
                if row_keys != required:
                    add("item_fields_mismatch", f"resumes[{resume_index}].{collection}[{row_index}]", f"missing={sorted(required-row_keys)} extra={sorted(row_keys-required)}")
    raw = str(payload.get("raw_text") or "")
    if len(compact(raw)) < 20:
        add("raw_text_short", "raw_text", str(len(raw)))
    for field in ("full_name", "phone", "email"):
        value = str((structured.get("base_info") or {}).get(field) or "")
        if value and compact(value) not in compact(raw):
            add("identity_missing_from_raw_text", f"structured_data.base_info.{field}", value)
    return issues


def main() -> int:
    cfg = args()
    mapping = read_json(cfg.map)
    by_path = {str(Path(row["input_path"]).resolve()).casefold(): row for row in mapping.get("records") or []}
    records: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    for path in sorted(cfg.json_root.glob("*.json")):
        try:
            payload = read_json(path)
        except Exception as exc:
            records.append({"json_path": str(path), "status": "failed", "issues": [{"code": "json_unreadable", "field": "$", "detail": str(exc)}]})
            counts["failed"] += 1
            continue
        source_path = str(Path(str((payload.get("source") or {}).get("path") or "")).resolve()).casefold()
        map_record = by_path.get(source_path)
        issues = audit_payload(path, payload, map_record) if map_record else [{"code": "source_not_in_map", "field": "source.path", "detail": source_path}]
        status = "passed" if not issues else "needs_review"
        counts[status] += 1
        for issue in issues:
            counts[f"issue:{issue['code']}"] += 1
        records.append({"json_path": str(path.resolve()), "input_filename": map_record.get("input_filename", "") if map_record else "", "status": status, "issues": issues})
    report = {"version": VERSION, "generated_at": datetime.now().astimezone().isoformat(), "total": len(records), "counts": dict(counts), "records": records}
    atomic_json(cfg.report, report)
    print(json.dumps(report["counts"], ensure_ascii=False, indent=2))
    print(f"report={cfg.report.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
