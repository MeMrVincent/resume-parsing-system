"""Compare every Web JSON output with its mapped HTML-like source.

This is intentionally a separate first phase from repair.  Each existing JSON
receives a durable ``quality.reconciliation`` block containing the exact
issues found, source facts, and check time.  Missing JSON outputs are recorded
in the conversion map because there is no JSON file to annotate.
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
import hashlib
import importlib.util
import json
import os
import re
import tempfile
import unicodedata
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = _rc.project_root()
DEFAULT_MAP = PROJECT_ROOT / _rc.dirname("complete-transfered-htmls") / "web" / "web_conversion_map.v2.json"
DEFAULT_JSON_DIR = PROJECT_ROOT / _rc.dirname("complete-transfered-jsons") / "web"
DEFAULT_REPORT = DEFAULT_JSON_DIR / "_web_html_json_reconcile.v2.json"
WEB_SUFFIXES = {".html", ".htm", ".mht", ".mhtml", ".eml"}
LIST_FIELDS = (
    "work_experiences", "education_list", "project_list", "training_list",
    "certificate_list", "language_list", "skills_list", "communication_list",
)
TOP_FIELDS = {
    "schema_version", "record_id", "source", "dates", "extraction",
    "classification", "structured_data", "raw_text", "quality",
}
SOURCE_FIELDS = {"path", "original_path", "filename", "extension", "size", "html_filename", "note"}
DATES_FIELDS = {
    "resume_updated_date", "resume_download_date", "resume_updated_date_source",
    "resume_download_date_source", "sys_created_date", "sys_updated_date",
}
CLASSIFICATION_FIELDS = {"document_type", "reason"}
STRUCTURED_FIELDS = {"base_info", "expected_info", "current_info", "education_info", "resumes"}
BASE_FIELDS = {
    "full_name", "gender", "age", "birth_date", "birth_year", "marital_status",
    "children_status", "political_status", "height_cm", "weight_kg",
    "household_registration", "address", "postal_code", "platform_from",
    "platform_resume_id", "phone", "email", "city", "nationality", "pr",
}
EXPECTED_FIELDS = {
    "expected_city", "expected_position", "expected_salary",
    "expected_annual_salary_min", "expected_annual_salary_max",
    "expected_industry", "expected_employment_type", "expected_start_date",
}
CURRENT_FIELDS = {
    "company_name", "company_employees", "company_industry", "position",
    "position_type", "position_salary", "position_dept", "position_report_to",
    "position_subordinate", "employment_type", "annual_salary_min",
    "annual_salary_max", "status", "position_start", "position_resigned",
}
EDUCATION_FIELDS = {
    "school_name", "school_major_name", "school_degree_type", "school_degree_rank",
    "school_education_type", "school_start_ym", "school_end_ym",
}
RESUME_FIELDS = {
    "resume_languge", "base_info", "expected_list", "work_experiences",
    "education_list", "certificate_list", "language_list", "skills_list",
    "training_list", "project_list", "communication_list",
}
ITEM_FIELDS = {
    "expected_list": EXPECTED_FIELDS,
    "work_experiences": CURRENT_FIELDS | {"resigned_reason", "position_responsibilities", "position_achievements"},
    "education_list": EDUCATION_FIELDS,
    "certificate_list": {"certificate_name", "certificate_type", "certificate_time"},
    "language_list": {"language_name", "language_level", "language_certificate", "language_certificate_time"},
    "skills_list": {"skill_name", "skill_level"},
    "training_list": {"sequence_no", "organization_name", "training_name", "start_ym", "end_ym", "certificate_name", "description"},
    "project_list": {"sequence_no", "fingerprint", "project_name", "company_or_client", "role_name", "start_ym", "end_ym", "description", "responsibilities", "achievements", "keywords"},
    "communication_list": {"communicate_time", "communicate_content"},
}
IGNORED_VALUE_KEYS = {
    "sequence_no", "fingerprint", "resume_language", "resume_languge",
    "school_degree_rank", "expected_start_date", "platform_from",
    "platform_resume_id", "city", "school_education_type",
    "position_start", "position_resigned", "school_start_ym", "school_end_ym",
    "start_ym", "end_ym", "expected_annual_salary_min", "expected_annual_salary_max",
}
CHECK_VALUE_KEYS = {
    "full_name", "expected_position", "expected_salary",
    "company_name", "position", "position_responsibilities", "position_achievements",
    "school_name", "school_major_name", "school_degree_type",
    "certificate_name", "language_name", "skill_name", "training_name",
    "project_name", "description", "responsibilities", "achievements",
    "communicate_content",
}


def load_converter() -> Any:
    path = _rc.PYTHON_DIR / "v2" / "web_html_to_json.v2.py"
    spec = importlib.util.spec_from_file_location("web_html_to_json_v2_reconcile", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载 Web v2 转换器: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_full_reviewer() -> Any:
    path = _rc.PYTHON_DIR / "v2" / "web_full_review.v2.py"
    spec = importlib.util.spec_from_file_location("web_full_review_v2_reconcile", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载 Web 全字段审计器: {path}")
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


def normalize_path(value: Any) -> str:
    return os.path.normcase(os.path.normpath(os.path.abspath(str(value or ""))))


def compact(value: Any) -> str:
    # HTML 常把全角数字/符号与 JSON 中的半角形式混用；先做 NFKC
    # 归一化，避免“手取り４５００元”和“手取り4500元”被误报为缺失。
    # EN: HTML often mixes full-width digits/symbols with the half-width forms in JSON; apply NFKC
    #     normalisation first, so "手取り４５００元" and "手取り4500元" (take-home 4500 yuan) are not falsely reported as missing.
    # JA: HTML では全角の数字・記号と JSON の半角の形式が混在することが多い。まず NFKC で
    #     正規化し、「手取り４５００元」と「手取り4500元」が欠落として誤報されないようにする。
    normalized = unicodedata.normalize("NFKC", str(value or ""))
    return re.sub(r"[^0-9A-Za-z\u3400-\u9fff]+", "", normalized).casefold()


def digits(value: Any) -> str:
    return re.sub(r"\D+", "", str(value or ""))


def extract_contacts(text: str) -> tuple[list[str], list[str]]:
    phones = list(dict.fromkeys(re.findall(r"(?<!\d)(1[3-9]\d{9})(?!\d)", text)))
    emails = list(dict.fromkeys(re.findall(
        r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}", text
    )))
    return phones, emails


def json_contacts(payload: dict[str, Any]) -> tuple[set[str], set[str]]:
    phones: set[str] = set()
    emails: set[str] = set()
    structured = payload.get("structured_data") or {}
    resumes = structured.get("resumes") if isinstance(structured, dict) else []
    if not isinstance(resumes, list):
        resumes = []
    for resume in resumes:
        base = resume.get("base_info") if isinstance(resume, dict) else {}
        if not isinstance(base, dict):
            continue
        phone = digits(base.get("phone") or base.get("mobile_phone"))
        email = str(base.get("email") or "").strip().casefold()
        if phone:
            phones.add(phone)
        if email:
            emails.add(email)
    quality = payload.get("quality") or {}
    contact = quality.get("contact") if isinstance(quality, dict) else {}
    if isinstance(contact, dict):
        phone = digits(contact.get("phone"))
        email = str(contact.get("email") or "").strip().casefold()
        if phone:
            phones.add(phone)
        if email:
            emails.add(email)
    return phones, emails


def iter_leaf_values(value: Any, key: str = "") -> list[tuple[str, str]]:
    result: list[tuple[str, str]] = []
    if isinstance(value, dict):
        for child_key, child in value.items():
            result.extend(iter_leaf_values(child, child_key))
    elif isinstance(value, list):
        for child in value:
            result.extend(iter_leaf_values(child, key))
    elif isinstance(value, str) and value.strip() and key not in IGNORED_VALUE_KEYS and key in CHECK_VALUE_KEYS:
        result.append((key, value.strip()))
    return result


def issue(code: str, severity: str = "error", **details: Any) -> dict[str, Any]:
    return {"code": code, "severity": severity, **details}


def check_keys(
    issues: list[dict[str, Any]],
    code: str,
    value: Any,
    expected: set[str],
    **details: Any,
) -> None:
    if not isinstance(value, dict):
        issues.append(issue(f"{code}_not_object", **details))
        return
    actual = set(value)
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    if missing or extra:
        issues.append(issue(
            code,
            missing=missing,
            extra=extra,
            **details,
        ))


def check_schema_alignment(payload: dict[str, Any]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    check_keys(issues, "top_level_fields_mismatch", payload, TOP_FIELDS)
    source = payload.get("source")
    check_keys(issues, "source_fields_mismatch", source, SOURCE_FIELDS)
    dates = payload.get("dates")
    check_keys(issues, "dates_fields_mismatch", dates, DATES_FIELDS)
    classification = payload.get("classification")
    check_keys(issues, "classification_fields_mismatch", classification, CLASSIFICATION_FIELDS)
    structured = payload.get("structured_data")
    check_keys(issues, "structured_data_fields_mismatch", structured, STRUCTURED_FIELDS)
    if not isinstance(structured, dict):
        return issues
    check_keys(issues, "base_info_fields_mismatch", structured.get("base_info"), BASE_FIELDS, scope="top")
    check_keys(issues, "expected_info_fields_mismatch", structured.get("expected_info"), EXPECTED_FIELDS, scope="top")
    check_keys(issues, "current_info_fields_mismatch", structured.get("current_info"), CURRENT_FIELDS, scope="top")
    check_keys(issues, "education_info_fields_mismatch", structured.get("education_info"), EDUCATION_FIELDS, scope="top")
    resumes = structured.get("resumes")
    if not isinstance(resumes, list):
        issues.append(issue("resumes_not_array"))
        return issues
    for resume_index, resume in enumerate(resumes):
        check_keys(issues, "resume_fields_mismatch", resume, RESUME_FIELDS, resume_index=resume_index)
        if not isinstance(resume, dict):
            continue
        for field, expected_fields in ITEM_FIELDS.items():
            values = resume.get(field)
            if not isinstance(values, list):
                issues.append(issue(
                    "resume_list_not_array", field=field, resume_index=resume_index
                ))
                continue
            for item_index, item in enumerate(values):
                check_keys(
                    issues,
                    "resume_item_fields_mismatch",
                    item,
                    expected_fields,
                    field=field,
                    resume_index=resume_index,
                    item_index=item_index,
                )
    return issues


def compare_pair(
    payload: dict[str, Any],
    json_path: Path,
    map_record: dict[str, Any],
    html_path: Path,
    converter: Any,
    full_reviewer: Any,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    issues.extend(check_schema_alignment(payload))
    raw_bytes = html_path.read_bytes() if html_path.exists() else b""
    html_hash = hashlib.sha256(raw_bytes).hexdigest() if raw_bytes else ""
    if not html_path.exists():
        issues.append(issue("html_missing", path=str(html_path)))
        return issues, {"sha256": html_hash, "size": 0, "plain_text_length": 0}

    try:
        html_text = converter.read_html_text(html_path)
        plain = converter.html_to_plain_text(html_text)
    except Exception as exc:
        issues.append(issue("html_decode_failed", error=str(exc)))
        return issues, {"sha256": html_hash, "size": len(raw_bytes), "plain_text_length": 0}

    # Run the independent all-field rules as part of normal reconciliation.
    # This covers exact snapshots, every resume/item schema, dates, ordering,
    # raw_text coverage and high-confidence field-misalignment heuristics.
    independent_plain = full_reviewer.source_plain(html_path)
    issues.extend(full_reviewer.review_payload(payload, map_record, json_path, independent_plain))

    source = payload.get("source") if isinstance(payload.get("source"), dict) else {}
    expected_source = normalize_path(map_record.get("source_path"))
    actual_source = normalize_path(source.get("original_path"))
    if actual_source != expected_source:
        issues.append(issue(
            "source_original_path_mismatch",
            expected=map_record.get("source_path", ""),
            actual=source.get("original_path", ""),
        ))
    actual_html = normalize_path(source.get("html_path") or source.get("path"))
    expected_html = normalize_path(html_path)
    if actual_html != expected_html:
        issues.append(issue(
            "source_html_path_mismatch", expected=str(html_path), actual=source.get("html_path") or source.get("path", "")
        ))
    expected_filename = str(map_record.get("filename") or Path(str(map_record.get("source_path"))).name)
    if str(source.get("filename") or "") != expected_filename:
        issues.append(issue(
            "source_filename_mismatch", expected=expected_filename, actual=source.get("filename", "")
        ))
    expected_extension = str(map_record.get("source_extension") or Path(expected_filename).suffix).lower()
    if str(source.get("extension") or "").lower() != expected_extension:
        issues.append(issue(
            "source_extension_mismatch", expected=expected_extension, actual=source.get("extension", "")
        ))

    extraction = payload.get("extraction") if isinstance(payload.get("extraction"), dict) else {}
    recorded_length = extraction.get("plain_text_length")
    if isinstance(recorded_length, int) and recorded_length != len(plain):
        issues.append(issue(
            "plain_text_length_mismatch", expected=len(plain), actual=recorded_length
        ))
    if len(plain.strip()) < 20:
        issues.append(issue("html_plain_text_short", length=len(plain)))

    structured = payload.get("structured_data") if isinstance(payload.get("structured_data"), dict) else {}
    resumes = structured.get("resumes") if isinstance(structured, dict) else []
    if not isinstance(resumes, list) or not resumes:
        resumes = []
        issues.append(issue("json_resumes_missing"))
    first = resumes[0] if resumes and isinstance(resumes[0], dict) else {}
    base = first.get("base_info") if isinstance(first.get("base_info"), dict) else {}
    name = str(base.get("full_name") or "").strip()
    if name and not name.startswith("待确认姓名_") and compact(name) not in compact(plain):
        issues.append(issue("json_name_not_in_html", value=name))
    if name and compact(name) not in compact(str(payload.get("raw_text") or "")):
        issues.append(issue("json_name_not_in_raw_text", value=name))

    # 记录已知的结构错位：这类条目通常是 HTML 表格的“规模/企业性质”
    # 被错放到了公司名或职位字段，不能只靠字段名校验发现。
    # EN: Record known structural misplacements: such entries are usually the "size / enterprise type" of an HTML table
    #     placed in the company name or position field by mistake, which cannot be found by field-name validation alone.
    # JA: 既知の構造のずれを記録する：この種の項目は通常、HTML の表の「規模／企業の性質」が
    #     会社名や職位のフィールドに誤って置かれたもので、フィールド名の検証だけでは見つけられない。
    work_items = first.get("work_experiences") if isinstance(first, dict) else []
    if isinstance(work_items, list):
        for item_index, item in enumerate(work_items):
            if not isinstance(item, dict):
                continue
            company = str(item.get("company_name") or "").strip()
            position = str(item.get("position") or "").strip()
            if (
                company in {"", ":", "：", "|", "｜", "(", ")", "（", "）"}
                or any(k in company for k in ("公司性质", "企业性质", "公司规模", "公司行业"))
                or position in {"规模", "企业性质", "公司性质", "行业", "Major", "Degree", "专业", "学历"}
                or bool(re.match(r"^(?:规模|企业性质|公司性质|行业|Major|Degree|专业|学历)\s*[：:]", position, re.I))
            ):
                issues.append(issue(
                    "invalid_work_item_mapping",
                    section="work",
                    item_index=item_index,
                    company_name=company,
                    position=position,
                ))

    html_phones, html_emails = extract_contacts(plain)
    json_phones, json_emails = json_contacts(payload)
    # Schema 的 phone/email 是主联系方式单值字段；HTML 中的家庭电话、备用电话
    # 可以保留在 html_facts，但不应因此把一条记录判为错误。按正文首次出现的
    # 主联系方式做强一致核对。
    # EN: The schema's phone/email are single-value primary contact fields; home phones and backup phones in the HTML
    #     may be kept in html_facts, but must not cause a record to be judged wrong. Check strictly for consistency against the primary contact
    #     that appears first in the body.
    # JA: スキーマの phone/email は主な連絡先を 1 つだけ持つフィールドである。HTML 中の自宅電話や予備の電話は
    #     html_facts に残してよいが、それを理由にレコードを誤りと判定してはならない。本文で最初に現れる
    #     主な連絡先に対して厳密に一致を確認する。
    missing_phones = [html_phones[0]] if html_phones and html_phones[0] not in json_phones else []
    missing_emails = [html_emails[0]] if html_emails and html_emails[0].casefold() not in json_emails else []
    if missing_phones:
        issues.append(issue("html_phone_not_in_json", values=missing_phones[:10], total=len(missing_phones)))
    if missing_emails:
        issues.append(issue("html_email_not_in_json", values=missing_emails[:10], total=len(missing_emails)))
    raw_compact = compact(payload.get("raw_text") or "")
    if html_phones and not any(phone in digits(payload.get("raw_text") or "") for phone in html_phones):
        issues.append(issue("html_phone_not_in_raw_text", values=html_phones[:10]))
    if html_emails and not any(compact(email) in raw_compact for email in html_emails):
        issues.append(issue("html_email_not_in_raw_text", values=html_emails[:10]))

    for marker, field, label in (
        (("工作经历", "工作经验", "work experience", "work history", "professional experience"), "work_experiences", "work"),
        (("教育经历", "教育背景", "educational experience", "education", "academic background"), "education_list", "education"),
        (("求职意向", "期望职位", "expected position", "career objective"), "expected_list", "expected"),
    ):
        plain_lines = [line.strip().casefold() for line in plain.splitlines() if line.strip()]
        marker_found = any(
            line == item.casefold()
            or line.startswith(item.casefold() + ":")
            or line.startswith(item.casefold() + "：")
            for line in plain_lines for item in marker
        )
        list_value = first.get(field) if isinstance(first, dict) else None
        if marker_found and isinstance(list_value, list) and not list_value:
            issues.append(issue("html_section_without_json_data", section=label, field=field))

    html_compact = compact(plain)
    structured_missing: list[dict[str, str]] = []
    for key, value in iter_leaf_values(resumes):
        normalized = compact(value)
        if len(normalized) < 3:
            continue
        if normalized not in html_compact:
            structured_missing.append({"field": key, "value": value[:120]})
            if len(structured_missing) >= 10:
                break
    if structured_missing:
        issues.append(issue(
            "json_values_not_in_html", severity="warning",
            values=structured_missing, truncated=len(structured_missing) >= 10,
        ))

    html_classification = converter.DocumentClassifier().classify(plain, expected_filename)
    html_doc_type = str(getattr(html_classification, "document_type", ""))
    json_doc_type = str((payload.get("classification") or {}).get("document_type", ""))
    if json_doc_type and html_doc_type and json_doc_type not in {html_doc_type, "resume" if html_doc_type == "ambiguous_resume" else html_doc_type}:
        issues.append(issue(
            "classification_mismatch", severity="warning",
            html_document_type=html_doc_type, json_document_type=json_doc_type,
        ))

    facts = {
        "sha256": html_hash,
        "size": len(raw_bytes),
        "plain_text_length": len(plain),
        "html_path": str(html_path.resolve()),
        "source_path": str(Path(str(map_record.get("source_path"))).resolve()),
        "json_path": str(json_path.resolve()),
        "html_contacts": {"phones": html_phones, "emails": html_emails},
        "html_document_type": html_doc_type,
    }
    return issues, facts


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="逐个核对 Web JSON 与 HTML-like 源文件" " / Check Web JSON against the HTML-like source file one by one / Web JSON と HTML 風の元ファイルを 1 件ずつ照合する")
    parser.add_argument("--map", dest="map_path", type=Path, default=DEFAULT_MAP)
    parser.add_argument("--json-dir", type=Path, default=DEFAULT_JSON_DIR)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--limit", type=int, default=0)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    converter = load_converter()
    full_reviewer = load_full_reviewer()
    map_payload = json.loads(args.map_path.read_text(encoding="utf-8"))
    records = map_payload.get("records", []) if isinstance(map_payload, dict) else map_payload
    records = [row for row in records if isinstance(row, dict)]
    selected = records[: args.limit] if args.limit > 0 else records
    report_items: list[dict[str, Any]] = []
    issue_counts: Counter[str] = Counter()
    checked = 0
    missing_json = 0
    for map_record in selected:
        json_path = Path(str(map_record.get("json_path") or ""))
        html_value = map_record.get("stage_path") or map_record.get("html_path") or map_record.get("source_path")
        html_path = Path(str(html_value or ""))
        if not str(map_record.get("json_path") or "") or not json_path.is_file():
            source_status = str(map_record.get("status") or "")
            expected_no_json = source_status in {
                "skipped_no_contact", "not_resume", "source_missing", "unsupported_web_extension"
            }
            if expected_no_json:
                map_record["reconcile_status"] = "no_json_expected"
                map_record["reconcile_issue_count"] = 0
                map_record["reconcile_issues"] = []
                report_items.append({
                    "index": map_record.get("index"), "status": "no_json_expected",
                    "json_path": str(json_path), "html_path": str(html_path), "issues": [],
                })
                continue
            missing_json += 1
            map_record["reconcile_status"] = "json_missing"
            map_record["reconcile_issue_count"] = 1
            map_record["reconcile_issues"] = [{"code": "json_missing", "severity": "error"}]
            report_items.append({
                "index": map_record.get("index"), "status": "json_missing",
                "json_path": str(json_path), "html_path": str(html_path),
                "issues": map_record["reconcile_issues"],
            })
            issue_counts["json_missing"] += 1
            continue
        try:
            payload = json.loads(json_path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("root JSON 不是对象")
            issues, facts = compare_pair(payload, json_path, map_record, html_path, converter, full_reviewer)
            checked += 1
            quality = payload.get("quality") if isinstance(payload.get("quality"), dict) else {}
            previous_reconciliation = quality.get("reconciliation") if isinstance(quality, dict) else {}
            round_no = int(previous_reconciliation.get("round") or 0) + 1 if isinstance(previous_reconciliation, dict) else 1
            checked_at = datetime.now().astimezone().isoformat(timespec="seconds")
            round_entry = {
                "round": round_no,
                "phase": "detected",
                "checked_at": checked_at,
                "issue_count": len(issues),
                "issues": copy.deepcopy(issues),
                "html_facts": copy.deepcopy(facts),
            }
            quality["reconciliation"] = {
                "status": "issues" if issues else "clean",
                "clean_mark": not issues,
                "round": round_no,
                "checked_at": checked_at,
                "issue_count": len(issues),
                "issues": issues,
                "html_facts": facts,
            }
            payload["quality"] = quality
            atomic_json(json_path, payload)
            for item in issues:
                issue_counts[str(item.get("code") or "unknown")] += 1
            status = "issues" if issues else "clean"
            map_record["reconcile_status"] = status
            map_record["reconcile_issue_count"] = len(issues)
            map_record["reconcile_issues"] = issues
            map_record["reconcile_round"] = round_no
            map_record["reconciled_at"] = checked_at
            report_items.append({
                "index": map_record.get("index"), "status": status,
                "json_path": str(json_path), "html_path": str(html_path),
                "issue_count": len(issues), "issues": issues,
            })
        except Exception as exc:
            failure_issues = [{
                "code": "json_read_or_compare_failed",
                "severity": "error",
                "error": str(exc),
            }]
            if json_path.is_file():
                try:
                    failed_payload = json.loads(json_path.read_text(encoding="utf-8"))
                    failed_quality = failed_payload.get("quality") if isinstance(failed_payload, dict) else {}
                    if not isinstance(failed_quality, dict):
                        failed_quality = {}
                    failed_previous = failed_quality.get("reconciliation") if isinstance(failed_quality.get("reconciliation"), dict) else {}
                    failed_round_no = int(failed_previous.get("round") or 0) + 1 if isinstance(failed_previous, dict) else 1
                    failed_checked_at = datetime.now().astimezone().isoformat(timespec="seconds")
                    failed_quality["reconciliation"] = {
                        "status": "issues",
                        "clean_mark": False,
                        "round": failed_round_no,
                        "checked_at": failed_checked_at,
                        "issue_count": 1,
                        "issues": failure_issues,
                        "html_facts": {},
                    }
                    failed_payload["quality"] = failed_quality
                    atomic_json(json_path, failed_payload)
                except Exception:
                    pass
            map_record["reconcile_status"] = "compare_failed"
            map_record["reconcile_issue_count"] = 1
            map_record["reconcile_issues"] = failure_issues
            report_items.append({
                "index": map_record.get("index"), "status": "compare_failed",
                "json_path": str(json_path), "html_path": str(html_path),
                "issues": failure_issues,
            })
            issue_counts["json_read_or_compare_failed"] += 1

    if isinstance(map_payload, dict):
        map_payload["last_reconciliation_report"] = str(args.report.resolve())
        map_payload["last_reconciled_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
        atomic_json(args.map_path, map_payload)
    status_counts = Counter(str(item.get("status") or "") for item in report_items)
    report = {
        "schema_version": "web-html-json-reconcile-v2",
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "map_path": str(args.map_path.resolve()),
        "json_dir": str(args.json_dir.resolve()),
        "counts": {
            "selected_map_records": len(selected),
            "json_html_pairs_checked": checked,
            "clean": status_counts.get("clean", 0),
            "issues": status_counts.get("issues", 0),
            "json_missing": missing_json,
            "compare_failed": status_counts.get("compare_failed", 0),
        },
        "issue_counts": dict(issue_counts),
        "items": report_items,
    }
    atomic_json(args.report, report)
    print(json.dumps(report["counts"], ensure_ascii=False))
    print(json.dumps(report["issue_counts"], ensure_ascii=False))
    print(f"逐文件核对报告: {args.report}" f" / File-by-file check report: {args.report} / ファイルごとの照合レポート：{args.report}")
    return 0 if not issue_counts else 2


if __name__ == "__main__":
    raise SystemExit(main())
