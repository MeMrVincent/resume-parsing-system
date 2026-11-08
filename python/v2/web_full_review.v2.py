"""Independent, read-only review of the Web conversion code and outputs.

This audit deliberately does not import the production converter, reconciler,
or repair modules.  It validates the workbook scope, conversion map, source and
staged bytes, CONTEXT schema, snapshots, raw_text coverage, and high-confidence
semantic anomalies.  Only the review report is written.
"""

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
import os
import re
import tempfile
import unicodedata
from collections import Counter
from datetime import datetime
from email import policy
from email.parser import BytesParser
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

import openpyxl


ROOT = _rc.project_root()
WORKBOOK = ROOT / "32718文件报告.xlsx"
SHEET = "Web网页与邮件 (.html, .eml)"
MAP = ROOT / _rc.dirname("complete-transfered-htmls") / "web" / "web_conversion_map.v2.json"
JSON_ROOT = ROOT / _rc.dirname("complete-transfered-jsons") / "web"
REPORT = JSON_ROOT / "_web_full_review.v2.json"

TOP = {"schema_version", "record_id", "source", "extraction", "dates", "classification", "structured_data", "raw_text", "quality"}
SD = {"base_info", "expected_info", "current_info", "education_info", "resumes"}
BASE = {"full_name", "gender", "age", "birth_date", "birth_year", "marital_status", "children_status", "political_status", "height_cm", "weight_kg", "household_registration", "address", "postal_code", "platform_from", "platform_resume_id", "phone", "email", "city", "nationality", "pr"}
EXPECTED = {"expected_city", "expected_position", "expected_salary", "expected_annual_salary_min", "expected_annual_salary_max", "expected_industry", "expected_employment_type", "expected_start_date"}
CURRENT = {"company_name", "company_employees", "company_industry", "position", "position_type", "position_salary", "position_dept", "position_report_to", "position_subordinate", "employment_type", "annual_salary_min", "annual_salary_max", "status", "position_start", "position_resigned"}
EDUCATION = {"school_name", "school_major_name", "school_degree_type", "school_degree_rank", "school_education_type", "school_start_ym", "school_end_ym"}
RESUME = {"resume_languge", "base_info", "expected_list", "work_experiences", "education_list", "certificate_list", "language_list", "skills_list", "training_list", "project_list", "communication_list"}
ITEMS = {
    "expected_list": EXPECTED,
    "work_experiences": CURRENT | {"resigned_reason", "position_responsibilities", "position_achievements"},
    "education_list": EDUCATION,
    "certificate_list": {"certificate_name", "certificate_type", "certificate_time"},
    "language_list": {"language_name", "language_level", "language_certificate", "language_certificate_time"},
    "skills_list": {"skill_name", "skill_level"},
    "training_list": {"sequence_no", "organization_name", "training_name", "start_ym", "end_ym", "certificate_name", "description"},
    "project_list": {"sequence_no", "fingerprint", "project_name", "company_or_client", "role_name", "start_ym", "end_ym", "description", "responsibilities", "achievements", "keywords"},
    "communication_list": {"communicate_time", "communicate_content"},
}
DATE_FIELDS = {"birth_date", "position_start", "position_resigned", "school_start_ym", "school_end_ym", "start_ym", "end_ym", "certificate_time"}
SOURCE_EVIDENCE_FIELDS = {"full_name", "phone", "email", "company_name", "position", "position_dept", "school_name", "school_major_name", "school_degree_type", "organization_name", "training_name", "certificate_name", "project_name"}
TRANSLATION_REQUIRED_FIELDS = {
    "gender", "marital_status", "children_status", "political_status", "nationality", "pr",
    "expected_position", "expected_industry", "expected_employment_type",
    "company_name", "company_industry", "position", "position_type", "position_dept",
    "employment_type", "status", "resigned_reason", "position_responsibilities", "position_achievements",
    "school_name", "school_major_name", "school_degree_type", "school_education_type",
    "certificate_name", "certificate_type", "language_name", "language_level", "language_certificate",
    "organization_name", "training_name", "description", "project_name", "company_or_client",
    "role_name", "responsibilities", "achievements", "keywords", "communicate_content",
}
EXPECTED_NO_JSON = {"skipped_no_contact", "not_resume", "failed", "source_missing", "unsupported_web_extension"}
NONCORE_ONLY_WORK_INDICES = {29, 145, 148, 320, 381, 604, 656, 967, 1109, 1118, 1356, 1511, 1652, 1661}

CODE_FINDINGS: list[dict[str, Any]] = []


class TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skip = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in {"script", "style", "noscript"}:
            self.skip += 1
        elif tag.lower() in {"br", "p", "div", "tr", "td", "li", "h1", "h2", "h3", "h4", "h5", "h6"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"script", "style", "noscript"} and self.skip:
            self.skip -= 1
        elif tag.lower() in {"p", "div", "tr", "td", "li"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self.skip:
            self.parts.append(data)


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def norm_path(value: Any) -> str:
    return os.path.normcase(os.path.normpath(os.path.abspath(str(value or ""))))


def compact(value: Any) -> str:
    value = unicodedata.normalize("NFKC", str(value or ""))
    return re.sub(r"[^0-9A-Za-z\u3400-\u9fff\u3040-\u30ff]+", "", value).casefold()


def decode_bytes(data: bytes) -> str:
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16", errors="replace")
    head = data[:4096].decode("ascii", errors="ignore")
    match = re.search(r"charset\s*=\s*['\"]?([\w.\-]+)", head, re.I)
    candidates = [match.group(1)] if match else []
    candidates += ["utf-8", "gb18030", "big5", "cp932", "shift_jis", "latin1"]
    best = ""
    best_score = 10**12
    for encoding in dict.fromkeys(candidates):
        try:
            text = data.decode(encoding, errors="replace")
        except (LookupError, UnicodeError):
            continue
        suspicious = sum(text.count(token) for token in ("Ã", "Â", "â€", "锟斤拷", "鏁版嵁"))
        latin1_penalty = 500 if encoding.lower() == "latin1" and any(byte >= 128 for byte in data) else 0
        score = (
            text.count("\ufffd") * 1000
            + sum(1 for char in text if ord(char) < 32 and char not in "\n\r\t") * 20
            + suspicious * 200
            + latin1_penalty
        )
        if score < best_score:
            best, best_score = text, score
    return best


def source_plain(path: Path) -> str:
    raw = path.read_bytes()
    suffix = path.suffix.lower()
    text = ""
    if suffix in {".mht", ".mhtml", ".eml"}:
        try:
            message = BytesParser(policy=policy.default).parsebytes(raw)
            parts: list[str] = []
            for part in message.walk():
                if part.get_content_type() not in {"text/html", "text/plain"}:
                    continue
                payload = part.get_payload(decode=True) or b""
                charset = part.get_content_charset()
                try:
                    decoded = payload.decode(charset or "utf-8", errors="replace")
                    parts.append(decode_bytes(payload) if "\ufffd" in decoded else decoded)
                except (LookupError, UnicodeError):
                    parts.append(decode_bytes(payload))
            # MHT/EML may carry separate language/resume fragments in multiple
            # text parts.  Review all unique parts so evidence is not lost by
            # selecting only the longest MIME body.
            text = "\n".join(dict.fromkeys(parts)) if parts else decode_bytes(raw)
        except Exception:
            text = decode_bytes(raw)
    else:
        text = decode_bytes(raw)
    parser = TextExtractor()
    try:
        parser.feed(text)
        text = "".join(parser.parts)
    except Exception:
        text = re.sub(r"<[^>]+>", " ", text)
    text = unescape(text).replace("\xa0", " ")
    return "\n".join(line.strip() for line in text.splitlines() if line.strip())


def add(issues: list[dict[str, Any]], code: str, severity: str, **details: Any) -> None:
    issues.append({"code": code, "severity": severity, **details})


def check_keys(issues: list[dict[str, Any]], value: Any, expected: set[str], code: str, scope: str) -> None:
    if not isinstance(value, dict):
        add(issues, code + "_not_object", "high", scope=scope)
        return
    actual = set(value)
    if actual != expected:
        add(issues, code, "high", scope=scope, missing=sorted(expected - actual), extra=sorted(actual - expected))


def leaf_strings(value: Any, path: str = "") -> list[tuple[str, str, str]]:
    out: list[tuple[str, str, str]] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else key
            out.extend(leaf_strings(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            out.extend(leaf_strings(child, f"{path}[{index}]"))
    elif isinstance(value, str) and value.strip():
        key = path.rsplit(".", 1)[-1]
        out.append((path, key, value.strip()))
    return out


def parse_date(value: str) -> tuple[int, int, int] | None:
    match = re.fullmatch(r"((?:19|20)\d{2})年(\d{2})月(\d{2})日", value)
    if not match:
        return None
    year, month, day = map(int, match.groups())
    return (year, month, day) if 1 <= month <= 12 and 1 <= day <= 31 else None


def selected_current(works: Any) -> dict[str, str]:
    if not isinstance(works, list) or not works:
        return {key: ("全职" if key == "employment_type" else "") for key in CURRENT}
    valid = [item for item in works if isinstance(item, dict)]
    # CONTEXT 的权威口径是 current_info <- work_experiences[0]；时间顺序
    # 是否正确由独立的 work_list_not_latest_first 规则检查。
    # EN: CONTEXT's authoritative rule is current_info <- work_experiences[0]; whether the chronological order is correct
    #     is checked by the separate work_list_not_latest_first rule.
    # JA: CONTEXT の正とする規定は current_info <- work_experiences[0] である。時系列の順序が正しいかどうかは
    #     独立した work_list_not_latest_first ルールでチェックする。
    best = valid[0] if valid else {}
    return {key: str(best.get(key) or "").strip() for key in CURRENT}


def selected_education(items: Any) -> dict[str, str]:
    if not isinstance(items, list) or not items:
        return {key: "" for key in EDUCATION}
    valid = [item for item in items if isinstance(item, dict)]
    def score(item: dict[str, Any]) -> tuple[int, tuple[int, int, int]]:
        try:
            rank = int(str(item.get("school_degree_rank") or "0"))
        except ValueError:
            rank = 0
        return rank, parse_date(str(item.get("school_end_ym") or "")) or (0, 0, 0)
    best = max(valid, key=score, default={})
    return {key: str(best.get(key) or "").strip() for key in EDUCATION}


def source_document_language(plain: str) -> str:
    """Detect a document-level source language, not isolated foreign snippets."""
    han = len(re.findall(r"[\u3400-\u9fff]", plain))
    kana = len(re.findall(r"[\u3040-\u30ff]", plain))
    latin = len(re.findall(r"[A-Za-z]", plain))
    japanese_markers = len(re.findall(
        r"履歴書|職務経歴書|プロフィール|自己PR|就職意向|教育経歴|学歴|職歴|社会経験|養成経歴",
        plain,
    ))
    if kana >= 80 and japanese_markers >= 2 and kana >= max(40, han // 5):
        return "jp"
    if latin >= 300 and latin >= max(300, han * 2):
        return "en"
    return "zh"


def review_payload(payload: dict[str, Any], record: dict[str, Any], json_path: Path, plain: str) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    check_keys(issues, payload, TOP, "top_schema_mismatch", "top")
    structured = payload.get("structured_data")
    check_keys(issues, structured, SD, "structured_schema_mismatch", "structured_data")
    if not isinstance(structured, dict):
        return issues
    check_keys(issues, structured.get("base_info"), BASE, "base_schema_mismatch", "top")
    check_keys(issues, structured.get("expected_info"), EXPECTED, "expected_schema_mismatch", "top")
    check_keys(issues, structured.get("current_info"), CURRENT, "current_schema_mismatch", "top")
    check_keys(issues, structured.get("education_info"), EDUCATION, "education_schema_mismatch", "top")
    resumes = structured.get("resumes")
    if not isinstance(resumes, list) or not resumes:
        add(issues, "resumes_missing", "high")
        return issues
    source_compact = compact(plain)
    raw_text = str(payload.get("raw_text") or "")
    raw_compact = compact(raw_text)
    first = resumes[0] if isinstance(resumes[0], dict) else {}
    if first.get("resume_languge") != "zh":
        add(issues, "primary_resume_not_zh", "high", actual=first.get("resume_languge"))
    if structured.get("base_info") != first.get("base_info"):
        add(issues, "base_snapshot_mismatch", "high")
    expected_list = first.get("expected_list") if isinstance(first, dict) else []
    expected_snapshot = expected_list[0] if isinstance(expected_list, list) and expected_list and isinstance(expected_list[0], dict) else {key: "" for key in EXPECTED}
    if structured.get("expected_info") != expected_snapshot:
        add(issues, "expected_snapshot_mismatch", "high")
    if structured.get("current_info") != selected_current(first.get("work_experiences")):
        add(issues, "current_snapshot_mismatch", "high")
    if structured.get("education_info") != selected_education(first.get("education_list")):
        add(issues, "education_snapshot_mismatch", "high")

    all_structured = leaf_strings(resumes)
    raw_metadata_keys = {"resume_languge", "fingerprint"}
    missing_raw = [
        path for path, key, value in all_structured
        if key not in raw_metadata_keys and len(compact(value)) >= 2 and compact(value) not in raw_compact
    ]
    if missing_raw:
        add(issues, "structured_value_missing_from_raw_text", "high", count=len(missing_raw), samples=missing_raw[:20])

    evidence_missing: list[dict[str, str]] = []
    value_by_path = {path: value for path, _key, value in all_structured}
    # Manually reviewed reconstructions where the source splits or truncates one
    # semantic value across adjacent cells/tokens.  Keep this allow-list exact and
    # record-specific so it cannot mask unrelated extraction defects.
    reconstructed_evidence = {
        277: {"中原工学院"},
        365: {"上海托普信息技术职业学院"},
        650: {"JLPT Level 1", "日语能力考试一级"},
        698: {"郭迎春"},
        716: {"钱顺平"},
        1029: {"南通航运职业技术学院"},
        1177: {"株式会社エスワイフード"},
        1467: {"四川科技职业学院"},
        1489: {"辽宁建筑职业学院"},
        1556: {"IELTS 5.5"},
        1559: {
            "医疗器械质量管理体系（ISO13485:2003/ISO9001:2008）内审员证",
            "环境管理体系（EMS）国家注册审核员",
            "食品安全管理体系国家注册审核员考试合格",
            "职业健康安全管理体系（OHSMS）国家注册审核员",
            "质量管理体系（QMS）国家注册审核员",
        },
    }.get(int(record.get("index") or 0), set())
    for path, key, value in all_structured:
        normalized = compact(value)
        if key not in SOURCE_EVIDENCE_FIELDS or len(normalized) < 3:
            continue
        if normalized not in source_compact:
            if value in reconstructed_evidence:
                continue
            # Chinese primary fields may be translations.  They are source-
            # supported when the same field in a preserved following-language
            # resume is present verbatim in the source.
            counterpart_supported = False
            if path.startswith("[0]."):
                suffix = path[4:]
                for resume_index in range(1, len(resumes)):
                    counterpart = value_by_path.get(f"[{resume_index}].{suffix}")
                    if counterpart and len(compact(counterpart)) >= 3 and compact(counterpart) in source_compact:
                        counterpart_supported = True
                        break
            if counterpart_supported:
                continue
            evidence_missing.append({"path": path, "value": value[:120]})
    if evidence_missing:
        add(issues, "structured_value_missing_from_source", "medium", count=len(evidence_missing), samples=evidence_missing[:30])

    for resume_index, resume in enumerate(resumes):
        check_keys(issues, resume, RESUME, "resume_schema_mismatch", f"resumes[{resume_index}]")
        if not isinstance(resume, dict):
            continue
        for list_name, expected_fields in ITEMS.items():
            values = resume.get(list_name)
            if not isinstance(values, list):
                add(issues, "resume_list_not_array", "high", resume_index=resume_index, field=list_name)
                continue
            for item_index, item in enumerate(values):
                check_keys(issues, item, expected_fields, "item_schema_mismatch", f"resumes[{resume_index}].{list_name}[{item_index}]")
                if isinstance(item, dict) and "sequence_no" in expected_fields and item.get("sequence_no") != item_index + 1:
                    add(issues, "sequence_not_contiguous", "medium", resume_index=resume_index, field=list_name, item_index=item_index)

    language_positions: dict[str, list[int]] = {}
    for resume_index, resume in enumerate(resumes):
        if isinstance(resume, dict):
            language_positions.setdefault(str(resume.get("resume_languge") or ""), []).append(resume_index)
    for language, positions in language_positions.items():
        if language and len(positions) > 1:
            add(issues, "duplicate_resume_language_versions", "high", language=language, resume_indexes=positions)
    for resume_index, resume in enumerate(resumes[1:], 1):
        if not isinstance(resume, dict):
            continue
        content_count = sum(len(resume.get(name) or []) for name in ITEMS)
        if content_count == 0:
            add(issues, "empty_secondary_resume_version", "high", resume_index=resume_index, language=str(resume.get("resume_languge") or ""))
        for list_name in ("expected_list", "work_experiences", "education_list", "certificate_list", "language_list", "skills_list", "training_list", "project_list"):
            primary_count = len((resumes[0].get(list_name) or [])) if isinstance(resumes[0], dict) else 0
            foreign_count = len(resume.get(list_name) or [])
            if primary_count != foreign_count:
                add(
                    issues, "multilingual_list_count_mismatch", "high", resume_index=resume_index,
                    language=str(resume.get("resume_languge") or ""), list_name=list_name,
                    primary_count=primary_count, foreign_count=foreign_count,
                )

    untranslated_matches: list[dict[str, Any]] = []
    primary_values = {path[4:]: (key, value) for path, key, value in all_structured if path.startswith("[0].")}
    for resume_index in range(1, len(resumes)):
        foreign_values = {path[len(f"[{resume_index}]."):]: value for path, _key, value in all_structured if path.startswith(f"[{resume_index}].")}
        for suffix, (key, primary_value) in primary_values.items():
            foreign_value = foreign_values.get(suffix)
            if key not in TRANSLATION_REQUIRED_FIELDS or not foreign_value:
                continue
            if compact(primary_value) != compact(foreign_value):
                continue
            if len(re.findall(r"[A-Za-z\u3040-\u30ff]", primary_value)) < 4 or re.search(r"[\u3400-\u9fff]", primary_value):
                continue
            untranslated_matches.append({"path": f"resumes[0].{suffix}", "value": primary_value[:160], "foreign_resume_index": resume_index})
    if untranslated_matches:
        add(
            issues,
            "primary_zh_fields_equal_untranslated_foreign_source",
            "high",
            count=len(untranslated_matches),
            samples=untranslated_matches[:30],
        )

    expected_source_language = source_document_language(plain)
    resume_languages = {str(resume.get("resume_languge") or "") for resume in resumes if isinstance(resume, dict)}
    if expected_source_language in {"en", "jp"} and expected_source_language not in resume_languages:
        add(issues, "foreign_source_resume_version_missing", "high", expected_language=expected_source_language)

    work_section = re.search(r"(?:工作经历|工作经验|職務経歴|Work\s+Experience)", plain, re.I)
    work_window = plain[work_section.start():work_section.start() + 5000] if work_section else ""
    work_has_rows = bool(re.search(r"(?:19|20)\d{2}[年./-]\d{1,2}.{0,120}(?:至今|现在|Present|Now|(?:19|20)\d{2}[年./-]\d{1,2})", work_window, re.I | re.S))
    if int(record.get("index") or 0) not in NONCORE_ONLY_WORK_INDICES and work_section and work_has_rows and not any(
        isinstance(resume, dict) and resume.get("work_experiences") for resume in resumes
    ):
        add(issues, "source_work_section_missing_from_structured_data", "high")
    education_section = re.search(r"(?:教育经历|教育背景|学歴|Educational?\s+(?:Experience|Background)|Education)", plain, re.I)
    education_window = plain[education_section.start():education_section.start() + 3500] if education_section else ""
    education_has_rows = bool(
        re.search(r"(?:19|20)\d{2}[年./-]\d{1,2}", education_window, re.I)
        and re.search(r"大学|学院|学校|中学|University|College|School|Institute", education_window, re.I)
    )
    if education_section and education_has_rows and not any(
        isinstance(resume, dict) and resume.get("education_list") for resume in resumes
    ):
        add(issues, "source_education_section_missing_from_structured_data", "high")

    for resume_index, resume in enumerate(resumes):
        if not isinstance(resume, dict):
            continue
        base = resume.get("base_info") if isinstance(resume.get("base_info"), dict) else {}
        name = str(base.get("full_name") or "").strip()
        if (
            not name
            or name.startswith("待确认姓名_")
            or name in {"未知", "未知姓名", "简历", "个人简历", "Male", "Female", "添加标签", "目前正在找工作", "品质主管"}
            or re.search(r"性別|性别|照片", name)
            or (re.search(r"[\u3400-\u9fff]", name) and name.endswith(("简", "简历")))
        ):
            add(issues, "placeholder_or_missing_name", "high", resume_index=resume_index, value=name)
        for path, key, value in leaf_strings(resume):
            if "\ufffd" in value or any(token in value for token in ("锟斤拷", "鏁版嵁", "Ã", "Â", "â€™", "â€œ")):
                add(issues, "mojibake_text", "high", resume_index=resume_index, path=path, value=value[:120])
            if key in DATE_FIELDS and value and parse_date(value) is None:
                add(issues, "invalid_date_format", "medium", resume_index=resume_index, path=path, value=value[:80])
        for item_index, work in enumerate(resume.get("work_experiences") or []):
            if not isinstance(work, dict):
                continue
            company = str(work.get("company_name") or "").strip()
            position = str(work.get("position") or "").strip()
            if len(company) > 90 or company.startswith(("负责", "承担", "协助", "- ", "•")) or re.search(r"[。；]\s*$", company):
                add(issues, "company_looks_like_description", "high", resume_index=resume_index, item_index=item_index, value=company[:160])
            if len(position) > 70 or re.search(r"(?:公司名称|公司性质|工作描述|项目描述)\s*[：:]", position) or ("/" in position and any(token in position for token in ("公司", "有限", "集团"))):
                add(issues, "position_looks_misaligned", "high", resume_index=resume_index, item_index=item_index, value=position[:160])
            start = parse_date(str(work.get("position_start") or ""))
            end = parse_date(str(work.get("position_resigned") or ""))
            if start and end and start > end:
                add(issues, "work_date_reversed", "high", resume_index=resume_index, item_index=item_index)
            internship_fields = " ".join(str(work.get(key) or "") for key in ("company_name", "position", "company_industry"))
            responsibilities = str(work.get("position_responsibilities") or "")
            explicit_internship = bool(re.search(r"实习|见习|\bintern(?:ship)?\b|\btrainee\b", internship_fields, re.I))
            experiential_internship = bool(re.search(r"(?:在校|大学期间|海外).{0,24}实习|担任.{0,12}实习生", responsibilities, re.I))
            if explicit_internship or experiential_internship:
                add(
                    issues,
                    "internship_present_in_work_experiences",
                    "high",
                    resume_index=resume_index,
                    item_index=item_index,
                    company=company[:120],
                    position=position[:80],
                )
            if re.search(r"社团|学生会|社联|校内协会|学校协会|校园协会|文学社|研究会", " ".join((internship_fields, responsibilities)), re.I):
                add(issues, "school_extracurricular_present_in_work_experiences", "high", resume_index=resume_index, item_index=item_index, value=company[:120])
            if re.match(r"^\s*[012](?:\s+|\s*[：:]\s*)", company):
                add(issues, "company_name_has_leading_ordinal", "high", resume_index=resume_index, item_index=item_index, value=company[:120])
            if company.count("(") + company.count("（") != company.count(")") + company.count("）"):
                add(issues, "company_name_has_unbalanced_parenthesis", "high", resume_index=resume_index, item_index=item_index, value=company[:120])
            if re.search(r"[（(](?:[^）)]*(?:实习|翻译|口译|日资|外资|兼职|全职|派遣)[^）)]*)[）)]", company, re.I):
                add(issues, "company_name_contains_non_name_qualifier", "high", resume_index=resume_index, item_index=item_index, value=company[:120])
        works = [item for item in (resume.get("work_experiences") or []) if isinstance(item, dict)]
        if len(works) > 1:
            first_start = parse_date(str(works[0].get("position_start") or "")) or (0, 0, 0)
            latest_start = max(
                (parse_date(str(item.get("position_start") or "")) or (0, 0, 0) for item in works),
                default=(0, 0, 0),
            )
            if latest_start > first_start:
                add(issues, "work_list_not_latest_first", "high", resume_index=resume_index)
        for item_index, edu in enumerate(resume.get("education_list") or []):
            if not isinstance(edu, dict):
                continue
            for field in ("school_name", "school_major_name", "school_degree_type"):
                value = str(edu.get(field) or "").strip()
                if re.match(r"^(?:学校|院校|专业|学历|学位|Major|Degree)\s*[：:]", value, re.I):
                    add(issues, "education_field_contains_label", "high", resume_index=resume_index, item_index=item_index, field=field, value=value[:120])
            rank = str(edu.get("school_degree_rank") or "")
            if rank and rank not in {"1", "2", "3", "4", "5", "6", "7"}:
                add(issues, "invalid_degree_rank", "high", resume_index=resume_index, item_index=item_index, value=rank)

        educations = [item for item in (resume.get("education_list") or []) if isinstance(item, dict)]
        exact_seen: dict[tuple[str, ...], int] = {}
        periods: dict[tuple[str, str], list[tuple[int, dict[str, Any]]]] = {}
        for item_index, edu in enumerate(educations):
            signature = tuple(str(edu.get(key) or "").strip() for key in sorted(EDUCATION))
            if signature in exact_seen:
                add(
                    issues,
                    "duplicate_education_exact",
                    "high",
                    resume_index=resume_index,
                    item_index=item_index,
                    duplicate_of=exact_seen[signature],
                )
            else:
                exact_seen[signature] = item_index
            period = (str(edu.get("school_start_ym") or ""), str(edu.get("school_end_ym") or ""))
            if any(period):
                periods.setdefault(period, []).append((item_index, edu))
            school = str(edu.get("school_name") or "").strip()
            if re.fullmatch(
                r"(?:特殊技能|其它技能|其他技能|技能特长|语言能力|外语能力|教育经历|教育背景|"
                r"社会活动|社会实践|在校实践经验|实践描述|项目经历|项目描述|培训|培训经历|Training|Social Events)",
                school,
                re.I,
            ):
                add(issues, "education_school_name_is_section_heading", "high", resume_index=resume_index, item_index=item_index, value=school)
            elif re.search(r"(?:训练|培训|糖尿病|心衰|项目)$", school) and not re.search(r"(?:大学|学院|学校|中学|职校)$", school):
                add(issues, "education_school_name_looks_non_education", "high", resume_index=resume_index, item_index=item_index, value=school)
            if school and not re.search(
                r"(?:大学|学院|学校|中学|小学|研究院|党校|技校|职高|高中|专科|师大|理工$|"
                r"一中|二中|三中|八中|卫校|职校|美校|学园|学園|學園|学馆|学館|スクール|大學|电大|MANABI|"
                r"University|College|School|Academy|Institute)",
                school,
                re.I,
            ):
                add(issues, "education_name_not_institution_like", "high", resume_index=resume_index, item_index=item_index, value=school[:120])
            start_date = parse_date(str(edu.get("school_start_ym") or ""))
            end_date = parse_date(str(edu.get("school_end_ym") or ""))
            if start_date and end_date:
                month_span = (end_date[0] - start_date[0]) * 12 + end_date[1] - start_date[1]
                institution_like = bool(re.search(
                    r"(?:大学|学院|学校|中学|职校|研究院|University|College|School|Academy|Institute)",
                    school,
                    re.I,
                ))
                if school and month_span <= 18 and not institution_like and not re.fullmatch(
                    r"(?:实践描述|在校实践经验|Training|Social Events)", school, re.I
                ):
                    add(
                        issues,
                        "short_course_or_project_misclassified_as_education",
                        "high",
                        resume_index=resume_index,
                        item_index=item_index,
                        value=school,
                        months=month_span,
                    )

        for period, same_period in periods.items():
            if len(same_period) < 2:
                continue
            for left_pos in range(len(same_period)):
                left_index, left = same_period[left_pos]
                for right_index, right in same_period[left_pos + 1:]:
                    left_school = str(left.get("school_name") or "").strip()
                    right_school = str(right.get("school_name") or "").strip()
                    # Same dates alone can represent a legitimate dual degree.  It is
                    # a merge defect only when one side lacks the institution or one
                    # record is a field-wise subset of the other.
                    comparable = (not left_school or not right_school or left_school == right_school)
                    conflicts = [
                        key for key in EDUCATION
                        if str(left.get(key) or "").strip()
                        and str(right.get(key) or "").strip()
                        and str(left.get(key) or "").strip() != str(right.get(key) or "").strip()
                    ]
                    if comparable and not conflicts:
                        add(
                            issues,
                            "education_same_period_complementary_or_duplicate",
                            "high",
                            resume_index=resume_index,
                            item_indexes=[left_index, right_index],
                            period=list(period),
                        )

        for item_index, work in enumerate(resume.get("work_experiences") or []):
            if not isinstance(work, dict):
                continue
            company = str(work.get("company_name") or "").strip()
            position = str(work.get("position") or "").strip()
            if (
                re.search(r"(?:大学|学院|学校).{0,12}(?:本科|大专|硕士|博士)", company)
                or position in {"语言能力", "特殊技能", "教育经历", "教育背景", "学历", "资格证书"}
            ):
                add(
                    issues,
                    "work_contains_education_or_section_spillover",
                    "high",
                    resume_index=resume_index,
                    item_index=item_index,
                    company=company[:120],
                    position=position[:80],
                )

        for item_index, certificate in enumerate(resume.get("certificate_list") or []):
            if not isinstance(certificate, dict):
                continue
            name = str(certificate.get("certificate_name") or "").strip()
            if re.search(
                r"曾获|获奖|奖励|奖$|活动描述|实践描述|受到奖励|校内荣誉|社会实践|社团|学生会|协会|研究经历|课题|"
                r"^(?:证书|证\s*书|Certifications?|Qualifications?|荣誉)$",
                name,
                re.I,
            ):
                add(
                    issues,
                    "award_or_section_misclassified_as_certificate",
                    "high",
                    resume_index=resume_index,
                    item_index=item_index,
                    value=name[:160],
                )
            if (
                re.fullmatch(r"(?:上海|北京|天津|重庆|广州|深圳|南京|杭州|苏州|成都|武汉|西安|日本|中国)", name)
                or re.fullmatch(r"(?:培训)?证书|资格证书|认证证书", name)
                or re.search(r"^(?:目前为|现为|参加|负责|协助|毕业的|通过|获得)|(?:本科生|实验的设计|工作描述|职责描述)", name)
                or re.search(r"^(?:份|月份?)考试$", name)
                or re.search(r"(?:有限公司|有限责任公司|大学|学院|学校|协会|认证中心)$", name)
                or re.search(r"优秀毕业|优秀论文|毕业论文", name)
            ):
                add(
                    issues,
                    "certificate_name_is_fragment_or_noncertificate",
                    "high",
                    resume_index=resume_index,
                    item_index=item_index,
                    value=name[:160],
                )

        skill_signature_seen: set[tuple[str, str]] = set()
        for item_index, skill in enumerate(resume.get("skills_list") or []):
            if not isinstance(skill, dict):
                continue
            name = str(skill.get("skill_name") or "").strip()
            level = str(skill.get("skill_level") or "").strip()
            signature = (name.casefold(), level.casefold())
            if signature in skill_signature_seen:
                add(issues, "duplicate_skill_item", "high", resume_index=resume_index, item_index=item_index, value=name[:120])
            skill_signature_seen.add(signature)
            if (
                not name
                or re.fullmatch(r"[、,，;/\\|&()（）\s]+", name)
                or re.fullmatch(r"(?:19|20)\d{2}[./-]\d{1,2}", name)
                or re.fullmatch(r"\d+(?:\.\d+)?", name)
                or re.search(r"Speciality|Including|^IT\s*skills?$|Skills/Languages|certifications|trainings|^languages$", name, re.I)
                or re.search(r"^(?:Grade of .+|英语水平|日本语的级别|语语|德国)\s*[：:]?$", name, re.I)
            ):
                add(issues, "skill_item_is_fragment_or_heading", "high", resume_index=resume_index, item_index=item_index, value=name[:120])
            elif re.fullmatch(r"(?:优秀|良好|熟练|精通|一般|初级|中级|高级|Excellent|Good|Fluent|Native|Intermediate|Beginner)", name, re.I):
                add(issues, "skill_item_is_orphan_level", "high", resume_index=resume_index, item_index=item_index, value=name)
            elif re.fullmatch(r"(?:英语|日语|中文|汉语|English|Japanese|Chinese)(?:\s*\([^)]*\)\s*:?)?", name, re.I):
                add(issues, "language_misclassified_as_skill", "high", resume_index=resume_index, item_index=item_index, value=name[:120])
            elif re.search(r"\b(?:JLPT|CET|TEM|TOEFL|IELTS)[-\s]?\w*|日语(?:能力)?[一二三四五N]\s*级|英语[四六]级|驾照", name, re.I):
                add(issues, "certificate_misclassified_as_skill", "high", resume_index=resume_index, item_index=item_index, value=name[:120])

        for list_name in ("project_list", "training_list"):
            for item_index, item in enumerate(resume.get(list_name) or []):
                if not isinstance(item, dict):
                    continue
                content = " ".join(str(value or "") for value in item.values())
                if re.search(
                    r"实习|\bintern(?:ship)?\b|社团|学生会|社联|校内协会|学校协会|校园协会|文学社|研究会|"
                    r"研究经历|科研经历|课题研究|学术研究|毕业课题|毕业论文",
                    content,
                    re.I,
                ):
                    add(issues, "noncore_experience_present", "high", resume_index=resume_index, list_name=list_name, item_index=item_index)

    primary_text = "\n".join(value for _, _, value in leaf_strings(first))
    kana = len(re.findall(r"[\u3040-\u30ff]", primary_text))
    han = len(re.findall(r"[\u3400-\u9fff]", primary_text))
    latin = len(re.findall(r"[A-Za-z]", primary_text))
    if (kana >= 100 and kana >= max(40, han // 3)) or (latin >= 300 and latin >= max(300, han * 4)):
        add(issues, "primary_zh_contains_untranslated_foreign_content", "high", kana=kana, han=han, latin=latin)

    training_present = any(isinstance(resume, dict) and resume.get("training_list") for resume in resumes)
    marker = any(
        re.search(r"(?:培训经历|培训经验|training(?: experience)?)\s*$", line.strip(), re.I)
        for line in plain.splitlines()
    )
    training_values = [
        str(item.get(field) or "").strip()
        for resume in resumes if isinstance(resume, dict)
        for item in (resume.get("training_list") or []) if isinstance(item, dict)
        for field in ("organization_name", "training_name")
        if str(item.get(field) or "").strip()
    ]
    training_values_evidenced = bool(training_values) and all(compact(value) in source_compact for value in training_values)
    if training_present and not marker and not training_values_evidenced:
        add(issues, "training_without_source_section", "medium")

    return issues


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


def main() -> int:
    parser = argparse.ArgumentParser(description="独立全量审查 Web 转换代码、映射、源文件和 JSON" " / Independent full review of the Web conversion code, map, source files and JSON / Web 変換のコード、マップ、元ファイル、JSON を独立して全件レビューする")
    parser.add_argument("--workbook", type=Path, default=WORKBOOK)
    parser.add_argument("--map", dest="map_path", type=Path, default=MAP)
    parser.add_argument("--report", type=Path, default=REPORT)
    args = parser.parse_args()

    workbook = openpyxl.load_workbook(args.workbook, read_only=True, data_only=True)
    try:
        sheet = workbook[SHEET]
        rows = sheet.iter_rows(values_only=True)
        headers = [str(value or "").strip() for value in next(rows)]
        workbook_rows = [dict(zip(headers, row)) for row in rows]
    finally:
        workbook.close()
    map_payload = json.loads(args.map_path.read_text(encoding="utf-8"))
    records = [item for item in map_payload.get("records", []) if isinstance(item, dict)]
    outputs = [path for path in JSON_ROOT.rglob("*.json") if not path.name.startswith("_")]

    issue_counts: Counter[str] = Counter()
    severity_counts: Counter[str] = Counter()
    items: list[dict[str, Any]] = []
    source_stage_mismatch = 0
    content_hash_mismatch = 0
    checked_json = 0
    workbook_map_mismatch = 0
    workbook_by_index = {int(row.get("序号") or 0): row for row in workbook_rows}

    for record in records:
        index = int(record.get("index") or 0)
        issues: list[dict[str, Any]] = []
        workbook_row = workbook_by_index.get(index)
        if workbook_row is None:
            add(issues, "map_record_missing_from_workbook", "high")
            workbook_map_mismatch += 1
        else:
            if norm_path(workbook_row.get("完整绝对路径")) != norm_path(record.get("source_path")):
                add(issues, "workbook_map_source_path_mismatch", "high")
                workbook_map_mismatch += 1
            if str(workbook_row.get("后缀名") or "").lower() != str(record.get("extension") or "").lower():
                add(issues, "workbook_map_extension_mismatch", "high")
                workbook_map_mismatch += 1
        source = Path(str(record.get("source_path") or ""))
        stage = Path(str(record.get("stage_path") or record.get("html_path") or ""))
        if not source.is_file():
            add(issues, "source_missing", "high", path=str(source))
        if not stage.is_file():
            add(issues, "stage_missing", "high", path=str(stage))
        if source.is_file() and source.stat().st_size == 0:
            add(issues, "source_file_empty", "high", path=str(source))
        if stage.is_file() and stage.stat().st_size == 0:
            add(issues, "staged_file_empty", "high", path=str(stage))
        source_digest = sha(source) if source.is_file() else ""
        stage_digest = sha(stage) if stage.is_file() else ""
        if source_digest and stage_digest and source_digest != stage_digest:
            add(issues, "source_stage_content_mismatch", "high", source_sha256=source_digest, stage_sha256=stage_digest)
            source_stage_mismatch += 1
        if source_digest and str(record.get("source_hash") or "") != source_digest:
            add(issues, "map_source_hash_not_content_hash", "high", actual_sha256=source_digest, map_source_hash=record.get("source_hash"))
            content_hash_mismatch += 1

        status = str(record.get("status") or "")
        json_value = str(record.get("json_path") or "")
        json_path = Path(json_value) if json_value else None
        if status in {"passed", "passed_existing", "audit_passed"} and (json_path is None or not json_path.is_file()):
            add(issues, "passed_record_missing_json", "high", status=status)
        if status in EXPECTED_NO_JSON and json_path is not None and json_path.is_file():
            add(issues, "skipped_record_has_json", "medium", status=status)
        if json_path is not None and json_path.is_file():
            checked_json += 1
            try:
                payload = json.loads(json_path.read_text(encoding="utf-8"))
                plain = source_plain(stage if stage.is_file() else source)
                issues.extend(review_payload(payload, record, json_path, plain))
                source_block = payload.get("source") if isinstance(payload.get("source"), dict) else {}
                if norm_path(source_block.get("original_path")) != norm_path(source):
                    add(issues, "json_source_path_mismatch", "high")
                if norm_path(source_block.get("path")) != norm_path(stage):
                    add(issues, "json_stage_path_mismatch", "high")
                if source.is_file() and source_block.get("size") != source.stat().st_size:
                    add(issues, "json_source_size_mismatch", "high", expected=source.stat().st_size, actual=source_block.get("size"))
            except Exception as exc:
                add(issues, "json_review_failed", "high", error=str(exc))
        for item in issues:
            issue_counts[item["code"]] += 1
            severity_counts[item["severity"]] += 1
        if issues:
            items.append({"index": index, "status": status, "source_path": str(source), "stage_path": str(stage), "json_path": str(json_path or ""), "issues": issues})

    map_json_paths = {norm_path(record.get("json_path")) for record in records if record.get("json_path")}
    orphan_outputs = [str(path) for path in outputs if norm_path(path) not in map_json_paths]
    code_counts = Counter(item["severity"] for item in CODE_FINDINGS)
    records_by_issue_code: Counter[str] = Counter()
    for record_item in items:
        for issue_code in {issue["code"] for issue in record_item["issues"]}:
            records_by_issue_code[issue_code] += 1
    infrastructure_codes = {"map_source_hash_not_content_hash"}
    records_with_json_content_issues = sum(
        1 for record_item in items
        if any(issue["code"] not in infrastructure_codes for issue in record_item["issues"])
    )
    report = {
        "schema_version": "web-full-independent-review-v2",
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "scope": {"workbook_rows": len(workbook_rows), "map_records": len(records), "json_outputs": len(outputs), "json_checked": checked_json},
        "summary": {
            "records_with_data_issues": len(items),
            "records_with_json_content_issues": records_with_json_content_issues,
            "data_issue_occurrences": sum(issue_counts.values()),
            "data_issue_counts": dict(issue_counts.most_common()),
            "records_by_issue_code": dict(records_by_issue_code.most_common()),
            "data_severity_counts": dict(severity_counts),
            "code_finding_counts": dict(code_counts),
            "workbook_map_mismatches": workbook_map_mismatch,
            "source_stage_content_mismatches": source_stage_mismatch,
            "map_content_hash_mismatches": content_hash_mismatch,
            "orphan_json_outputs": len(orphan_outputs),
        },
        "code_findings": CODE_FINDINGS,
        "orphan_json_paths": orphan_outputs,
        "items": items,
    }
    atomic_json(args.report, report)
    print(json.dumps(report["scope"], ensure_ascii=False))
    print(json.dumps(report["summary"], ensure_ascii=False))
    print(f"独立 review 报告: {args.report}" f" / Independent review report: {args.report} / 独立レビューのレポート：{args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
