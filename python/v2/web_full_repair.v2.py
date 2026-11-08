"""In-place, schema-strict repair for every Web conversion-map record.

The repair is intentionally conservative: deterministic schema, date, ordering,
snapshot, raw-text, hash and history defects are fixed automatically; semantic
content that cannot be established from the source is retained and marked for
review instead of being guessed.
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
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = _rc.project_root()
MAP_PATH = ROOT / _rc.dirname("complete-transfered-htmls") / "web" / "web_conversion_map.v2.json"
REVIEW_PATH = ROOT / _rc.dirname("complete-transfered-jsons") / "web" / "_web_full_review.v2.json"
REPORT_PATH = ROOT / _rc.dirname("complete-transfered-jsons") / "web" / "_web_full_repair.v2.json"

TOP = ("schema_version", "record_id", "source", "extraction", "dates", "classification", "structured_data", "raw_text", "quality")
SOURCE = ("path", "original_path", "filename", "extension", "size", "html_filename", "note")
DATES = ("resume_updated_date", "resume_download_date", "resume_updated_date_source", "resume_download_date_source", "sys_created_date", "sys_updated_date")
EXTRACTION = ("reader_group", "converter", "parser", "status", "html_path", "dom")
CLASSIFICATION = ("document_type", "reason")
SD = ("base_info", "expected_info", "current_info", "education_info", "resumes")
BASE = ("full_name", "gender", "age", "birth_date", "birth_year", "marital_status", "children_status", "political_status", "height_cm", "weight_kg", "household_registration", "address", "postal_code", "platform_from", "platform_resume_id", "phone", "email", "city", "nationality", "pr")
EXPECTED = ("expected_city", "expected_position", "expected_salary", "expected_annual_salary_min", "expected_annual_salary_max", "expected_industry", "expected_employment_type", "expected_start_date")
CURRENT = ("company_name", "company_employees", "company_industry", "position", "position_type", "position_salary", "position_dept", "position_report_to", "position_subordinate", "employment_type", "annual_salary_min", "annual_salary_max", "status", "position_start", "position_resigned")
EDUCATION = ("school_name", "school_major_name", "school_degree_type", "school_degree_rank", "school_education_type", "school_start_ym", "school_end_ym")
RESUME = ("resume_languge", "base_info", "expected_list", "work_experiences", "education_list", "certificate_list", "language_list", "skills_list", "training_list", "project_list", "communication_list")
ITEMS = {
    "expected_list": EXPECTED,
    "work_experiences": CURRENT + ("resigned_reason", "position_responsibilities", "position_achievements"),
    "education_list": EDUCATION,
    "certificate_list": ("certificate_name", "certificate_type", "certificate_time"),
    "language_list": ("language_name", "language_level", "language_certificate", "language_certificate_time"),
    "skills_list": ("skill_name", "skill_level"),
    "training_list": ("sequence_no", "organization_name", "training_name", "start_ym", "end_ym", "certificate_name", "description"),
    "project_list": ("sequence_no", "fingerprint", "project_name", "company_or_client", "role_name", "start_ym", "end_ym", "description", "responsibilities", "achievements", "keywords"),
    "communication_list": ("communicate_time", "communicate_content"),
}
DATE_KEYS = {"birth_date", "position_start", "position_resigned", "school_start_ym", "school_end_ym", "start_ym", "end_ym", "certificate_time", "language_certificate_time"}
END_KEYS = {"position_resigned", "school_end_ym", "end_ym"}
EXPECTED_NO_JSON = {"skipped_no_contact", "not_resume", "source_missing", "unsupported_web_extension"}
PLACEHOLDER_NAMES = {"", "未知", "未知姓名", "简历", "个人简历"}
KNOWN_SOURCE_NAMES = {67: "Ping Zhaohua", 72: "Richard Tseng", 114: "Emma Chan", 240: "jamespang"}
VERIFIED_NAME_REPAIRS = {
    71: "徐标", 177: "贺萱", 201: "陈璋帼", 251: "张敏",
    606: "赵翠", 634: "CHUN, ZHENG", 635: "CHUN, ZHENG", 671: "孙可",
    692: "Rongqiong Ma", 698: "郭迎春", 704: "Wang Feng", 716: "钱顺平",
    719: "Zhou Yong", 888: "Z女士", 1094: "王美霞", 1095: "杨艳",
    1140: "周健安", 1154: "顾剑飞", 1732: "R女士",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--map", type=Path, default=MAP_PATH)
    parser.add_argument("--review", type=Path, default=REVIEW_PATH)
    parser.add_argument("--report", type=Path, default=REPORT_PATH)
    return parser.parse_args()


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


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_reviewer() -> Any:
    path = _rc.PYTHON_DIR / "v2" / "web_full_review.v2.py"
    spec = importlib.util.spec_from_file_location("web_full_review_v2", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法载入独立审计器: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_converter() -> Any:
    path = _rc.PYTHON_DIR / "v2" / "web_html_to_json.v2.py"
    spec = importlib.util.spec_from_file_location("web_html_to_json_v2", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法载入 Web 解析器: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def strict_object(value: Any, keys: tuple[str, ...], tracker: Counter[str], scope: str, defaults: dict[str, Any] | None = None) -> dict[str, Any]:
    source = value if isinstance(value, dict) else {}
    extras = set(source) - set(keys)
    if extras:
        tracker["extra_fields_removed"] += len(extras)
        tracker[f"extra_fields_removed:{scope}"] += len(extras)
    defaults = defaults or {}
    return {key: copy.deepcopy(source.get(key, defaults.get(key, ""))) for key in keys}


def normalize_date(value: Any, key: str) -> tuple[str, bool, bool]:
    text = str(value or "").strip()
    if not text:
        return "", False, False
    if key in END_KEYS and re.fullmatch(r"(?:至今|现在|目前|present|current|now|在职)", text, re.I):
        return "", True, False
    normalized = text.translate(str.maketrans({"／": "/", "．": ".", "－": "-"}))
    match = re.fullmatch(r"((?:19|20)\d{2})(?:年|[-/.])\s*(\d{1,2})(?:(?:月|[-/.])\s*(\d{1,2}))?日?", normalized)
    if not match:
        match = re.fullmatch(r"((?:19|20)\d{2})年?", normalized)
    if not match:
        return text, False, True
    year = int(match.group(1))
    month = int(match.group(2) or 1) if len(match.groups()) >= 2 else 1
    day = int(match.group(3) or 1) if len(match.groups()) >= 3 else 1
    if not (1 <= month <= 12 and 1 <= day <= 31):
        return text, False, True
    result = f"{year:04d}年{month:02d}月{day:02d}日"
    return result, result != text, False


def normalize_dates(value: Any, tracker: Counter[str], unresolved: list[dict[str, str]], path: str = "") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else key
            if key in DATE_KEYS and isinstance(child, (str, int, float)):
                result, changed, invalid = normalize_date(child, key)
                value[key] = result
                if changed:
                    tracker["dates_normalized"] += 1
                if invalid:
                    unresolved.append({"code": "invalid_date_unresolved", "path": child_path, "value": str(child)[:100]})
            else:
                normalize_dates(child, tracker, unresolved, child_path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            normalize_dates(child, tracker, unresolved, f"{path}[{index}]")


def date_key(value: Any) -> tuple[int, int, int]:
    match = re.fullmatch(r"((?:19|20)\d{2})年(\d{2})月(\d{2})日", str(value or ""))
    return tuple(map(int, match.groups())) if match else (0, 0, 0)


def degree_score(item: dict[str, Any]) -> tuple[int, tuple[int, int, int]]:
    try:
        rank = int(str(item.get("school_degree_rank") or "0"))
    except ValueError:
        rank = 0
    return rank, date_key(item.get("school_end_ym"))


def raw_text_from_resumes(resumes: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    seen: set[str] = set()

    def visit(value: Any, key: str = "") -> None:
        if isinstance(value, dict):
            for child_key, child in value.items():
                if child_key not in {"resume_languge", "fingerprint", "sequence_no"}:
                    visit(child, child_key)
        elif isinstance(value, list):
            for child in value:
                visit(child, key)
        elif value not in (None, ""):
            text = str(value).strip()
            if text and text not in seen:
                seen.add(text)
                lines.append(text)

    visit(resumes)
    return "\n".join(lines)


def detected_resume_language(resume: dict[str, Any]) -> str:
    text = json.dumps({key: value for key, value in resume.items() if key != "resume_languge"}, ensure_ascii=False)
    han = len(re.findall(r"[\u3400-\u9fff]", text))
    kana = len(re.findall(r"[\u3040-\u30ff]", text))
    latin = len(re.findall(r"[A-Za-z]", text))
    if kana >= 10:
        return "jp"
    if latin >= 80 and latin >= max(80, han * 2):
        return "en"
    return "zh"


def foreign_content_language(value: Any) -> str:
    text = json.dumps(value, ensure_ascii=False)
    han = len(re.findall(r"[\u3400-\u9fff]", text))
    kana = len(re.findall(r"[\u3040-\u30ff]", text))
    latin = len(re.findall(r"[A-Za-z]", text))
    if kana >= 2:
        return "jp"
    if latin >= 10 and latin >= max(10, han * 2):
        return "en"
    return "zh"


def source_document_language(plain: str) -> str:
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


def repair_resume_language_versions(resumes: list[dict[str, Any]], tracker: Counter[str], plain: str) -> None:
    """Ensure the Chinese primary is followed only by correctly labelled source-language versions."""
    source_language = source_document_language(plain)
    if source_language == "zh" and len(resumes) > 1:
        primary_signature = json.dumps({key: value for key, value in resumes[0].items() if key != "resume_languge"}, ensure_ascii=False, sort_keys=True)
        retained = [resumes[0]]
        for resume in resumes[1:]:
            signature = json.dumps({key: value for key, value in resume.items() if key != "resume_languge"}, ensure_ascii=False, sort_keys=True)
            if signature == primary_signature:
                tracker["erroneous_foreign_deepcopies_removed"] += 1
            else:
                retained.append(resume)
        resumes[:] = retained
    if len(resumes) == 1:
        original_language = source_language
        # Only copy when the existing object itself is the foreign source.
        # A bilingual HTML may currently have only its Chinese half parsed;
        # copying that Chinese object and labelling it English would fabricate
        # a false source-language version.
        if original_language in {"en", "jp"} and detected_resume_language(resumes[0]) == original_language:
            original = copy.deepcopy(resumes[0])
            original["resume_languge"] = original_language
            chinese_copy = copy.deepcopy(resumes[0])
            chinese_copy["resume_languge"] = "zh"
            resumes[:] = [chinese_copy, original]
            tracker["foreign_source_resume_versions_deepcopied"] += 1
    seen: set[str] = set()
    by_language: dict[str, dict[str, Any]] = {}
    retained: list[dict[str, Any]] = []
    for resume_index, resume in enumerate(resumes):
        expected = "zh" if resume_index == 0 else detected_resume_language(resume)
        old = str(resume.get("resume_languge") or "")
        if old != expected:
            resume["resume_languge"] = expected
            tracker["resume_language_labels_repaired"] += 1
        if expected in by_language:
            target = by_language[expected]
            for key, value in resume["base_info"].items():
                if not target["base_info"].get(key) and value:
                    target["base_info"][key] = value
            for list_name in ITEMS:
                for item in resume.get(list_name) or []:
                    if item not in target[list_name]:
                        target[list_name].append(copy.deepcopy(item))
                if list_name in {"training_list", "project_list"}:
                    for sequence, item in enumerate(target[list_name], 1):
                        item["sequence_no"] = sequence
            tracker["same_language_resume_versions_merged"] += 1
            continue
        signature = expected + ":" + json.dumps({key: value for key, value in resume.items() if key != "resume_languge"}, ensure_ascii=False, sort_keys=True)
        if signature in seen:
            tracker["duplicate_resume_versions_removed"] += 1
            continue
        seen.add(signature)
        retained.append(resume)
        by_language[expected] = resume
    resumes[:] = retained

    # A previous broken pass sometimes created an empty source-language shell.
    # If the Chinese slot still contains the foreign source verbatim, preserve
    # that complete object in the source slot before the Chinese translation.
    if source_language in {"en", "jp"} and resumes:
        primary = resumes[0]
        source_resume = next((resume for resume in resumes[1:] if resume.get("resume_languge") == source_language), None)
        primary_items = sum(len(primary.get(name) or []) for name in ITEMS)
        source_items = sum(len(source_resume.get(name) or []) for name in ITEMS) if source_resume else -1
        if detected_resume_language(primary) == source_language and source_items < primary_items:
            replacement = copy.deepcopy(primary)
            replacement["resume_languge"] = source_language
            if source_resume is None:
                resumes.append(replacement)
            else:
                resumes[resumes.index(source_resume)] = replacement
            tracker["empty_or_sparse_foreign_resume_rebuilt_from_source_copy"] += 1


def complete_education_semantics(item: dict[str, Any]) -> dict[str, Any]:
    degree = str(item.get("school_degree_type") or "").strip()
    rank = {"初中": "1", "高中": "2", "中专": "2", "大专": "3", "本科": "4", "学士": "4", "硕士": "5", "研究生": "5", "博士": "6",
            "Associate": "3", "Diploma": "3", "Bachelor": "4", "Master": "5", "PhD": "6", "Doctor": "6"}.get(degree, "")
    education_type = {"高中": "全日制高中", "中专": "全日制中专", "大专": "全日制大专", "本科": "全日制大学", "学士": "全日制大学",
                      "硕士": "全日制研究生", "研究生": "全日制研究生", "博士": "全日制博士"}.get(degree, "")
    result = {key: item.get(key, "") for key in EDUCATION}
    result["school_degree_rank"] = result.get("school_degree_rank") or rank
    result["school_education_type"] = result.get("school_education_type") or education_type
    return result


EN_DATE_RANGE_RE = re.compile(
    r"^\s*((?:19|20)\d{2}[./-]\d{1,2})\s*(?:-+|[–—~])\s*"
    r"(Now|Present|Current|(?:19|20)\d{2}[./-]\d{1,2})\s*[：:]?\s*$",
    re.I,
)
EN_DATE_RANGE_PREFIX_RE = re.compile(
    r"^\s*((?:19|20)\d{2}[./-]\d{1,2})\s*(?:-+|[–—~])\s*"
    r"(Now|Present|Current|(?:19|20)\d{2}[./-]\d{1,2})\s*[：:]?\s*(.*)$",
    re.I,
)


def source_lines(plain: str) -> list[str]:
    lines = [re.sub(r"\s+", " ", line).strip() for line in plain.splitlines() if re.sub(r"\s+", " ", line).strip()]
    text = "\n".join(lines)
    for pattern, replacement in (
        (r"(?m)^Work\nExperience$", "Work Experience"),
        (r"(?m)^Educational\nExperience$", "Educational Experience"),
        (r"(?m)^Project\nExperience$", "Project Experience"),
        (r"(?m)^Additional\nInfo$", "Additional Info"),
        (r"(?m)^Project\nPosition:$", "Project Position:"),
        (r"(?m)^Company\nLocations:$", "Company Locations:"),
        (r"(?m)^Responsibilities\n& Achievement:$", "Responsibilities & Achievement:"),
        (r"(?m)^Full-time\nSchool:$", "Full-time school:"),
    ):
        text = re.sub(pattern, replacement, text, flags=re.I)
    return text.splitlines()


def normalized_range(match: re.Match[str]) -> tuple[str, str]:
    start = normalize_date(match.group(1), "position_start")[0]
    end = normalize_date(match.group(2), "position_resigned")[0]
    return start, end


def section_lines(lines: list[str], start_re: re.Pattern[str], end_re: re.Pattern[str]) -> list[str]:
    start = next((index for index, line in enumerate(lines) if start_re.fullmatch(line.strip(" :"))), -1)
    if start < 0:
        return []
    end = next((index for index in range(start + 1, len(lines)) if end_re.fullmatch(lines[index].strip(" :"))), len(lines))
    return lines[start + 1:end]


def parse_liepin_english_work(plain: str) -> list[dict[str, Any]]:
    lines = source_lines(plain)
    body = section_lines(
        lines,
        re.compile(r"Work\s+Experience", re.I),
        re.compile(r"Educational?\s+(?:Experience|Background)|Education", re.I),
    )
    dated = [(index, match) for index, line in enumerate(body) if (match := EN_DATE_RANGE_RE.match(line))]
    starts: list[tuple[int, int, re.Match[str]]] = []
    for occurrence, (index, match) in enumerate(dated[:-1]):
        next_index, next_match = dated[occurrence + 1]
        if next_match.group(0).casefold() == match.group(0).casefold() and next_index - index <= 18:
            starts.append((index, next_index, match))
    results: list[dict[str, Any]] = []
    for sequence, (start_index, repeated_index, match) in enumerate(starts):
        end_index = starts[sequence + 1][0] if sequence + 1 < len(starts) else len(body)
        prefix = body[start_index + 1:repeated_index]
        label_index = next((i for i, line in enumerate(prefix) if re.match(r"(?:Type|Size)\s+of\s*$|Company:|Industry:", line, re.I)), len(prefix))
        company = " ".join(prefix[:label_index]).strip(" ,;:-")
        industry_index = next((i for i, line in enumerate(prefix) if re.fullmatch(r"Industry\s*:", line, re.I)), -1)
        industry = prefix[industry_index + 1] if 0 <= industry_index + 1 < len(prefix) else ""
        position_parts = prefix[industry_index + 2:] if industry_index >= 0 else []
        position = " ".join(part for part in position_parts if not part.endswith(":"))
        tail = body[repeated_index + 1:end_index]
        responsibility_index = next((i for i, line in enumerate(tail) if re.match(r"Responsibilities", line, re.I)), -1)
        responsibilities = ""
        if responsibility_index >= 0:
            content_index = responsibility_index + 1
            if content_index < len(tail) and re.match(r"&\s*Achievement\s*:", tail[content_index], re.I):
                content_index += 1
            responsibilities = "\n".join(tail[content_index:]).strip()
        location_index = next((i for i, line in enumerate(tail) if re.match(r"Company\s+Locations?\s*:", line, re.I)), -1)
        subordinate_index = next((i for i, line in enumerate(tail) if re.match(r"Subordinate\s*:", line, re.I)), -1)
        start_ym, end_ym = normalized_range(match)
        if company:
            results.append({
                "company_name": company,
                "company_employees": "",
                "company_industry": industry,
                "position": position,
                "position_type": "",
                "position_salary": "",
                "position_dept": "",
                "position_report_to": "",
                "position_subordinate": tail[subordinate_index + 1] if 0 <= subordinate_index + 1 < len(tail) else "",
                "employment_type": "Full-time",
                "annual_salary_min": "",
                "annual_salary_max": "",
                "status": "On job" if not end_ym else "Dimission",
                "position_start": start_ym,
                "position_resigned": end_ym,
                "resigned_reason": "",
                "position_responsibilities": responsibilities,
                "position_achievements": "",
            })
            if location_index >= 0:
                # Location has no dedicated work-item field in CONTEXT; do not
                # invent a field or mix it into the company name.
                pass
    return results


def parse_single_date_english_work(plain: str) -> list[dict[str, Any]]:
    """Parse Zhaopin/51job English sections where each period occurs once."""
    body = section_lines(
        source_lines(plain),
        re.compile(r"Work\s+Experience", re.I),
        re.compile(r"Educational?\s+(?:Experience|Background)|Education(?:\s+Background)?", re.I),
    )
    dated = [(index, match) for index, line in enumerate(body) if (match := EN_DATE_RANGE_PREFIX_RE.match(line))]
    results: list[dict[str, Any]] = []
    for sequence, (start_index, match) in enumerate(dated):
        end_index = dated[sequence + 1][0] if sequence + 1 < len(dated) else len(body)
        block = body[start_index + 1:end_index]
        if not block:
            continue
        header_tail = match.group(3).strip()
        description_index = next((i for i, line in enumerate(block) if re.fullmatch(r"(?:Description|Responsibility|Responsibilities(?:\s*&\s*Achievement)?)\s*[：:]", line, re.I)), len(block))
        header = ([header_tail] if header_tail else []) + block[:description_index]
        company = position = department = industry = ""
        metadata_index = next((i for i, line in enumerate(header) if "|" in line and re.search(r"people|Comp\.|Company Size|Industry|Private|Foreign|WOFE|State-Owned", line, re.I)), -1)
        if header and "|" in header[0] and metadata_index != 0:
            parts = [part.strip() for part in header[0].split("|")]
            company = parts[0] if parts else ""
            if len(parts) >= 3:
                department, position = parts[-2], parts[-1]
            elif len(parts) == 2:
                position = parts[1]
            if len(header) > 1 and "|" in header[1]:
                industry = header[1].split("|", 1)[0].strip()
        elif metadata_index >= 0:
            industry_prefix = ""
            company_end = metadata_index
            if metadata_index > 0 and re.search(r"Services|Consult|Trading|Manufactur|Electronics|Pharma|Machinery", header[metadata_index - 1], re.I) and not re.search(r"\b(?:Co\.?|Ltd\.?|Company|Group|Corporation|Limited)\b", header[metadata_index - 1], re.I):
                industry_prefix = header[metadata_index - 1] + " "
                company_end -= 1
            company = " ".join(header[:company_end])
            company = re.sub(r"\s*\([^)]*(?:years?|months?)[^)]*\)\s*$", "", company, flags=re.I).strip()
            metadata = header[metadata_index]
            industry = (industry_prefix + metadata.split("|", 1)[0]).strip()
            role_parts = [part for part in header[metadata_index + 1:] if not part.endswith(":")]
            if role_parts:
                position = role_parts[-1]
                department = " ".join(role_parts[:-1])
        elif any(re.match(r"Industry\s*[：:]", line, re.I) for line in header) and any(re.match(r"Position\s*[：:]", line, re.I) for line in header):
            industry_index = next(i for i, line in enumerate(header) if re.match(r"Industry\s*[：:]", line, re.I))
            position_index = next(i for i, line in enumerate(header) if re.match(r"Position\s*[：:]", line, re.I))
            company = " ".join(line for line in header[:industry_index] if not re.search(r"more than|years?|months?", line, re.I)).strip()
            industry_first = re.sub(r"^Industry\s*[：:]\s*", "", header[industry_index], flags=re.I)
            industry = " ".join(([industry_first] if industry_first else []) + header[industry_index + 1:position_index]).strip()
            position_first = re.sub(r"^Position\s*[：:]\s*", "", header[position_index], flags=re.I)
            position = " ".join(([position_first] if position_first else []) + header[position_index + 1:]).strip()
        else:
            continue
        start_ym, end_ym = normalized_range(match)
        responsibilities = "\n".join(block[description_index + 1:]).strip() if description_index < len(block) else ""
        if company:
            results.append({
                "company_name": company.strip(" ,;:-"), "company_employees": "", "company_industry": industry,
                "position": position, "position_type": "", "position_salary": "", "position_dept": department,
                "position_report_to": "", "position_subordinate": "", "employment_type": "Full-time",
                "annual_salary_min": "", "annual_salary_max": "", "status": "On job" if not end_ym else "Dimission",
                "position_start": start_ym, "position_resigned": end_ym, "resigned_reason": "",
                "position_responsibilities": responsibilities, "position_achievements": "",
            })
    return results


def parse_liepin_english_education(plain: str) -> list[dict[str, Any]]:
    lines = source_lines(plain)
    body = section_lines(
        lines,
        re.compile(r"Educational?\s+(?:Experience|Background)|Education", re.I),
        re.compile(r"Languages?|Project\s+Experience|Self[- ]description|Additional\s+Info", re.I),
    )
    text = "\n".join(body)
    pattern = re.compile(
        r"(?P<school>[A-Za-z][A-Za-z0-9&,. '\n-]+?(?:University|College|Institute|Academy|School))\s*"
        r"\((?P<start>(?:19|20)\d{2}[./-]\d{1,2})\s*-\s*(?P<end>(?:19|20)\d{2}[./-]\d{1,2})\)\s*"
        r"Major\s*:\s*(?P<major>.*?)\s*Degree\s*:\s*(?P<degree>.*?)\s*Full-time\s+school\s*:",
        re.I | re.S,
    )
    results = []
    for match in pattern.finditer(text):
        degree = re.sub(r"\s+", " ", match.group("degree")).strip(" ,;:-")
        results.append(complete_education_semantics({
            "school_name": re.sub(r"^(?:Yes|No)\s+", "", re.sub(r"\s+", " ", match.group("school")).strip(" ,;:-"), flags=re.I),
            "school_major_name": re.sub(r"\s+", " ", match.group("major")).strip(" ,;:-"),
            "school_degree_type": degree,
            "school_degree_rank": "",
            "school_education_type": "Full-time",
            "school_start_ym": normalize_date(match.group("start"), "school_start_ym")[0],
            "school_end_ym": normalize_date(match.group("end"), "school_end_ym")[0],
        }))
    return results


def parse_single_date_english_education(plain: str) -> list[dict[str, Any]]:
    body = section_lines(
        source_lines(plain),
        re.compile(r"Educational?\s+(?:Experience|Background)|Education(?:\s+Background)?", re.I),
        re.compile(r"Languages?|Project\s+Experience|Skills?(?:\s*&\s*Speciality)?|Graduates?\s+Info|Social\s+Events|Training|Certificates?", re.I),
    )
    dated = [(index, match) for index, line in enumerate(body) if (match := EN_DATE_RANGE_PREFIX_RE.match(line))]
    results: list[dict[str, Any]] = []
    for sequence, (start_index, match) in enumerate(dated):
        end_index = dated[sequence + 1][0] if sequence + 1 < len(dated) else len(body)
        block = body[start_index + 1:end_index]
        header_tail = match.group(3).strip()
        first = header_tail or (block[0] if block else "")
        rest = block if header_tail else block[1:]
        parts = [part.strip() for part in first.split("|")]
        school = parts[0] if parts else ""
        major = parts[1] if len(parts) > 1 else ""
        degree = parts[2] if len(parts) > 2 else ""
        if len(parts) == 1 and rest:
            detail_parts = [part.strip() for part in rest[0].split("|")]
            if len(detail_parts) >= 2:
                degree, major = detail_parts[0], detail_parts[1]
                if len(rest) > 1 and "|" not in rest[1] and not rest[1].endswith(":") and len(rest[1]) <= 60:
                    major = f"{major} {rest[1]}".strip()
        start_ym, end_ym = normalized_range(match)
        if school:
            results.append(complete_education_semantics({
                "school_name": school, "school_major_name": major, "school_degree_type": degree,
                "school_degree_rank": "", "school_education_type": "Full-time",
                "school_start_ym": start_ym, "school_end_ym": end_ym,
            }))
    return results


def parse_liepin_english_projects(plain: str) -> list[dict[str, Any]]:
    lines = source_lines(plain)
    body = section_lines(
        lines,
        re.compile(r"Project\s+Experience", re.I),
        re.compile(r"Self[- ]description|Additional\s+Info|Skills?", re.I),
    )
    headers: list[tuple[int, int, re.Match[str], str]] = []
    for date_index, line in enumerate(body):
        match = EN_DATE_RANGE_RE.match(line)
        if not match:
            continue
        role_index = next((i for i in range(date_index + 1, min(len(body), date_index + 5)) if re.match(r"Project(?:\s+Position\s*:)?$|Position\s*:", body[i], re.I)), -1)
        if role_index < 0:
            continue
        name_parts: list[str] = []
        name_start = date_index
        for cursor in range(date_index - 1, max(-1, date_index - 4), -1):
            candidate = body[cursor]
            if candidate.endswith(":") or len(candidate) > 100 or re.search(r"[.!?。]$", candidate):
                break
            name_parts.insert(0, candidate)
            name_start = cursor
        if len(name_parts) > 1 and re.fullmatch(r"[A-Z][A-Z0-9 _~+/-]{0,20}", name_parts[0]):
            name_parts.pop(0)
            name_start += 1
        name = " ".join(name_parts).strip()
        if name:
            headers.append((name_start, date_index, match, name))
    results = []
    for sequence, (name_start, date_index, match, name) in enumerate(headers, 1):
        end = headers[sequence][0] if sequence < len(headers) else len(body)
        block = body[date_index + 1:end]
        fields: dict[str, list[str]] = {"role": [], "description": [], "responsibilities": [], "achievements": []}
        active = ""
        for line in block:
            normalized = line.strip()
            if re.fullmatch(r"Project\s*", normalized, re.I):
                continue
            label = re.fullmatch(r"(?:Project\s+)?(Position|Description|Responsibilities|Responsibility|Achievement|Achievements)\s*:", normalized, re.I)
            if label:
                token = label.group(1).casefold()
                active = "role" if token == "position" else ("responsibilities" if token.startswith("responsibil") else ("achievements" if token.startswith("achievement") else "description"))
                continue
            if active:
                fields[active].append(normalized)
        start_ym, end_ym = normalized_range(match)
        results.append({
            "sequence_no": sequence,
            "fingerprint": "",
            "project_name": name,
            "company_or_client": "",
            "role_name": " ".join(fields["role"]),
            "start_ym": start_ym,
            "end_ym": end_ym,
            "description": "\n".join(fields["description"]),
            "responsibilities": "\n".join(fields["responsibilities"]),
            "achievements": "\n".join(fields["achievements"]),
            "keywords": "",
        })
    return results


def recover_bilingual_english_version(resumes: list[dict[str, Any]], plain: str, tracker: Counter[str]) -> None:
    if not resumes or source_document_language(plain) != "en":
        return
    if any(resume.get("resume_languge") == "en" for resume in resumes):
        return
    primary = resumes[0]
    if detected_resume_language(primary) != "zh":
        return
    works = parse_liepin_english_work(plain) or parse_single_date_english_work(plain)
    educations = parse_liepin_english_education(plain) or parse_single_date_english_education(plain)
    if not works and not educations:
        return
    foreign = copy.deepcopy(primary)
    foreign["resume_languge"] = "en"
    if works:
        foreign["work_experiences"] = works
    if educations:
        foreign["education_list"] = educations
    name_match = re.search(r"\n([A-Za-z][A-Za-z ,.\-]{2,40})Process\s+Status", plain, re.I)
    if not name_match:
        name_match = re.search(r"\n([A-Za-z][A-Za-z ,.\-]{2,40})\n(?:male|female)\b", plain, re.I)
    if name_match:
        foreign["base_info"]["full_name"] = name_match.group(1).strip(" ,")
    gender_match = re.search(r"\b(Male|Female)\b", plain)
    if gender_match:
        foreign["base_info"]["gender"] = gender_match.group(1)
    standard = {
        "男": "Male", "女": "Female", "未婚": "Single", "已婚": "Married", "全职": "Full-time",
        "在职": "On job", "离职": "Dimission", "中国": "China", "英语": "English", "日语": "Japanese",
        "本科": "Bachelor", "硕士": "Master", "博士": "Doctor", "大专": "Associate",
    }
    def replace_standard(value: Any) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if isinstance(child, str) and child in standard:
                    value[key] = standard[child]
                else:
                    replace_standard(child)
        elif isinstance(value, list):
            for child in value:
                replace_standard(child)
    replace_standard(foreign)
    resumes.append(foreign)
    tracker["bilingual_english_source_versions_recovered"] += 1


def recover_missing_sections_from_plain(resumes: list[dict[str, Any]], plain: str, converter: Any, tracker: Counter[str]) -> None:
    if not resumes or not plain:
        return
    primary = resumes[0]
    foreign_target = None
    if len(resumes) > 1 and resumes[1].get("resume_languge") in {"en", "jp", "de"}:
        foreign_target = resumes[1]

    if not any(resume.get("education_list") for resume in resumes):
        parsed = converter._parse_web_education_from_plain(plain)
        if not parsed and source_document_language(plain) == "en":
            parsed = parse_liepin_english_education(plain) or parse_single_date_english_education(plain)
        recovered = [complete_education_semantics(item) for item in parsed if isinstance(item, dict) and item.get("school_name")]
        if recovered:
            if foreign_target is not None and foreign_content_language(recovered) != "zh":
                foreign_target["education_list"] = copy.deepcopy(recovered)
                primary["education_list"] = copy.deepcopy(recovered)
            else:
                primary["education_list"] = recovered
            tracker["source_plain_education_sections_recovered"] += len(recovered)

    if not any(resume.get("work_experiences") for resume in resumes):
        parsed_work = converter._parse_web_work_from_plain(plain)
        if not parsed_work and source_document_language(plain) == "en":
            parsed_work = parse_liepin_english_work(plain) or parse_single_date_english_work(plain)
        recovered_work = [strict_object(item, ITEMS["work_experiences"], tracker, "recovered.work") for item in parsed_work if isinstance(item, dict) and item.get("company_name")]
        if recovered_work:
            if foreign_target is not None and foreign_content_language(recovered_work) != "zh":
                foreign_target["work_experiences"] = copy.deepcopy(recovered_work)
                primary["work_experiences"] = copy.deepcopy(recovered_work)
            else:
                primary["work_experiences"] = recovered_work
            tracker["source_plain_work_sections_recovered"] += len(recovered_work)

    if not any(resume.get("project_list") for resume in resumes) and source_document_language(plain) == "en":
        recovered_projects = parse_liepin_english_projects(plain)
        if recovered_projects:
            if foreign_target is not None:
                foreign_target["project_list"] = copy.deepcopy(recovered_projects)
                primary["project_list"] = copy.deepcopy(recovered_projects)
            else:
                primary["project_list"] = recovered_projects
            tracker["source_plain_project_sections_recovered"] += len(recovered_projects)
    recover_bilingual_english_version(resumes, plain, tracker)


def compact_text(value: Any) -> str:
    return re.sub(r"[^0-9a-z\u3400-\u9fff]+", "", str(value or "").casefold())


def clean_position_from_source(company: str, plain: str) -> str:
    company_key = compact_text(company)
    if len(company_key) < 4:
        return ""
    lines = [line.strip() for line in plain.splitlines() if line.strip()]
    rejected = re.compile(
        r"(?:工作描述|项目描述|责任描述|实践描述|公司性质|企业性质|公司规模|行业|property|size|description|months?|years?)",
        re.I,
    )
    for line_index, line in enumerate(lines):
        line_key = compact_text(line)
        if company_key not in line_key and line_key not in company_key:
            continue
        for candidate in lines[line_index + 1: line_index + 7]:
            if rejected.search(candidate) or re.match(r"^(?:19|20)\d{2}", candidate):
                continue
            value = candidate.split("|", 1)[0].strip()
            value = re.sub(r"\s*[|｜]\s*\d.*$", "", value).strip()
            if 1 < len(value) <= 70 and not re.fullmatch(r"[()（）\d\s年月个.-]+", value):
                return value
    return ""


def project_from_work(work: dict[str, Any], sequence: int) -> dict[str, Any]:
    company = str(work.get("company_name") or "").strip()
    description = str(work.get("position_responsibilities") or "").strip()
    project_name = company
    split = re.split(r"项目描述\s*[：:]?", company, maxsplit=1)
    if len(split) == 2:
        project_name = split[0].strip(" ·-：:")
        description = "\n".join(part for part in (split[1].strip(), description) if part)
    label = str(work.get("position") or "").strip()
    responsibilities = description if label.startswith("责任描述") else ""
    return {
        "sequence_no": sequence,
        "fingerprint": "",
        "project_name": project_name,
        "company_or_client": "",
        "role_name": "",
        "start_ym": str(work.get("position_start") or ""),
        "end_ym": str(work.get("position_resigned") or ""),
        "description": description,
        "responsibilities": responsibilities,
        "achievements": str(work.get("position_achievements") or "").strip(),
        "keywords": "",
    }


def project_from_education(education: dict[str, Any], sequence: int, default_name: str = "实践经历") -> dict[str, Any]:
    school = str(education.get("school_name") or "").strip()
    major = str(education.get("school_major_name") or "").strip()
    heading = re.fullmatch(
        r"(?:社会活动|社会实践|在校实践经验|实践描述|项目经历|项目描述|Social Events)",
        school,
        re.I,
    )
    # A section heading is not a project name.  Keep it only as classification
    # evidence and leave the name blank unless the source line contains a role.
    name = "" if heading else school
    role_match = re.search(r"(?:19|20)\d{2}[./年]\d{1,2}.{0,30}?\s+(.+)$", major)
    if heading and role_match:
        name = role_match.group(1).strip(" ：:-") or default_name
    return {
        "sequence_no": sequence,
        "fingerprint": "",
        "project_name": name,
        "company_or_client": "",
        "role_name": "",
        "start_ym": str(education.get("school_start_ym") or ""),
        "end_ym": str(education.get("school_end_ym") or ""),
        "description": major,
        "responsibilities": "",
        "achievements": "",
        "keywords": "",
    }


def training_from_education(education: dict[str, Any], sequence: int) -> dict[str, Any]:
    name = re.sub(r"^培训课程\s*[：:]\s*", "", str(education.get("school_name") or "").strip(), flags=re.I)
    major = str(education.get("school_major_name") or "").strip()
    organization = major if re.search(r"(?:公司|中心|学院|学校|机构)$", major) else ""
    description = "" if organization else major
    if name.lower() == "training":
        name = major.lstrip("：:").strip() or "培训经历"
        organization = ""
        description = ""
    return {
        "sequence_no": sequence,
        "organization_name": organization,
        "training_name": name,
        "start_ym": str(education.get("school_start_ym") or ""),
        "end_ym": str(education.get("school_end_ym") or ""),
        "certificate_name": "",
        "description": description,
    }


def month_span(start: Any, end: Any) -> int | None:
    left = date_key(start)
    right = date_key(end)
    if left == (0, 0, 0) or right == (0, 0, 0):
        return None
    return (right[0] - left[0]) * 12 + right[1] - left[1]


def parsed_education_from_work(work: dict[str, Any]) -> dict[str, Any] | None:
    company = re.sub(r"\s+", "", str(work.get("company_name") or "").strip())
    match = re.fullmatch(r"(.+(?:大学|学院|学校))(.{0,40}?)(博士|硕士|本科|大专|其他)", company)
    if not match:
        return None
    school, major, degree = match.groups()
    major = major.strip("：:-")
    if major in {"其他", "其它"}:
        major = ""
    rank = {"大专": "3", "本科": "4", "硕士": "5", "博士": "6"}.get(degree, "")
    education_type = {"大专": "全日制大专", "本科": "全日制大学", "硕士": "全日制研究生", "博士": "全日制博士"}.get(degree, "")
    return {
        "school_name": school,
        "school_major_name": major,
        "school_degree_type": degree,
        "school_degree_rank": rank,
        "school_education_type": education_type,
        "school_start_ym": str(work.get("position_start") or ""),
        "school_end_ym": str(work.get("position_resigned") or ""),
    }


def merge_education_items(items: list[dict[str, Any]], tracker: Counter[str]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    country_placeholders = {"中国", "日本", "美国", "英国", "法国", "德国", "加拿大", "澳大利亚"}
    for item in items:
        exact = next((existing for existing in merged if existing == item), None)
        if exact is not None:
            tracker["exact_duplicate_education_items_removed"] += 1
            continue
        period = (str(item.get("school_start_ym") or ""), str(item.get("school_end_ym") or ""))
        candidate = None
        for existing in merged:
            existing_period = (str(existing.get("school_start_ym") or ""), str(existing.get("school_end_ym") or ""))
            if period != existing_period or not any(period):
                continue
            left_school = str(existing.get("school_name") or "").strip()
            right_school = str(item.get("school_name") or "").strip()
            comparable = (
                not left_school
                or not right_school
                or left_school == right_school
                or left_school in country_placeholders
                or right_school in country_placeholders
            )
            conflicts = [
                key for key in EDUCATION
                if key not in {"school_name", "school_start_ym", "school_end_ym"}
                and str(existing.get(key) or "").strip()
                and str(item.get(key) or "").strip()
                and str(existing.get(key) or "").strip() != str(item.get(key) or "").strip()
            ]
            if comparable and not conflicts:
                candidate = existing
                break
        if candidate is None:
            merged.append(item)
            continue
        for key in EDUCATION:
            incoming = str(item.get(key) or "").strip()
            current = str(candidate.get(key) or "").strip()
            if key == "school_name" and current in country_placeholders and incoming not in country_placeholders:
                candidate[key] = incoming
            elif not current and incoming:
                candidate[key] = incoming
        tracker["complementary_education_items_merged"] += 1
    return merged


def repair_education_semantics(resumes: list[dict[str, Any]], tracker: Counter[str]) -> None:
    """Repair high-confidence section bleed and duplicate education records."""
    headings = re.compile(
        r"^(?:特殊技能|其它技能|其他技能|技能特长|语言能力|外语能力|教育经历|教育背景|"
        r"社会活动|社会实践|在校实践经验|实践描述|项目经历|项目描述|培训|培训经历|Training|Social Events)$",
        re.I,
    )
    practice_headings = re.compile(r"^(?:社会活动|社会实践|在校实践经验|实践描述|项目经历|项目描述|Social Events)$", re.I)
    training_markers = re.compile(r"(?:训练|培训)$|^Training$", re.I)
    institution = re.compile(r"(?:大学|学院|学校|中学|职校|研究院|University|College|School|Academy|Institute)", re.I)

    for resume in resumes:
        for project in resume["project_list"]:
            if str(project.get("project_name") or "").strip() == "实践经历":
                project["project_name"] = ""
                tracker["synthetic_practice_project_names_cleared"] += 1
        retained_education: list[dict[str, Any]] = []
        for education in resume["education_list"]:
            school = str(education.get("school_name") or "").strip()
            span = month_span(education.get("school_start_ym"), education.get("school_end_ym"))
            if practice_headings.fullmatch(school):
                resume["project_list"].append(project_from_education(education, len(resume["project_list"]) + 1))
                tracker["practice_education_items_moved_to_projects"] += 1
                continue
            if training_markers.search(school):
                resume["training_list"].append(training_from_education(education, len(resume["training_list"]) + 1))
                tracker["training_education_items_moved_to_training"] += 1
                continue
            if span is not None and span <= 18 and school and not institution.search(school):
                resume["project_list"].append(project_from_education(education, len(resume["project_list"]) + 1, "项目经历"))
                tracker["short_project_items_moved_from_education"] += 1
                continue
            if headings.fullmatch(school):
                education["school_name"] = ""
                tracker["education_section_heading_cleared"] += 1
            retained_education.append(education)

        retained_work: list[dict[str, Any]] = []
        for work in resume["work_experiences"]:
            position = str(work.get("position") or "").strip()
            parsed = parsed_education_from_work(work)
            if parsed is not None:
                retained_education.append(parsed)
                tracker["work_items_reclassified_as_education"] += 1
                continue
            if position in {"语言能力", "特殊技能", "教育经历", "教育背景", "学历", "资格证书", "受到奖励"}:
                tracker["section_heading_work_items_removed"] += 1
                continue
            retained_work.append(work)
        resume["work_experiences"] = retained_work
        resume["education_list"] = merge_education_items(retained_education, tracker)
        for sequence, project in enumerate(resume["project_list"], 1):
            project["sequence_no"] = sequence
        for sequence, training in enumerate(resume["training_list"], 1):
            training["sequence_no"] = sequence


LANGUAGE_NAMES = {
    "english": "英语", "英语": "英语", "japanese": "日语", "日语": "日语",
    "chinese": "中文", "中文": "中文", "汉语": "中文", "mandarin": "中文",
    "korean": "韩语", "韩语": "韩语", "french": "法语", "法语": "法语",
    "german": "德语", "德语": "德语", "spanish": "西班牙语", "西班牙语": "西班牙语",
}
LANGUAGE_LEVELS = {
    "excellent": "优秀", "good": "良好", "fluent": "流利", "native": "母语",
    "intermediate": "中级", "beginner": "初级", "advanced": "高级",
    "优秀": "优秀", "良好": "良好", "熟练": "熟练", "精通": "精通",
    "流利": "流利", "母语": "母语", "一般": "一般", "初级": "初级",
    "中级": "中级", "高级": "高级",
}
SKILL_HEADING_RE = re.compile(
    r"^(?:&?\s*Speciality|\(?Including(?:\s+IT\s*skills?)?|IT\s*skills?|Skills?/Languages?|"
    r"languages?|certifications?(?:\s+and\s+trainings?)?\)?|(?:and\s+)?trainings?\)?|技能|技能特长|专业技能|语言能力|证书)$",
    re.I,
)
CERTIFICATE_RE = re.compile(
    r"\b(?:JLPT|CET|TEM|TOEIC|TOEFL|IELTS|BEC|PMP|CPA|CFA|CCNA|CCNP|MCSE|MOS)[-\s]?\w*\b|"
    r"(?:日语(?:能力)?[一二三四五N]\s*级|英语[四六]级|资格证|资格证书|认证|执照|驾照|驾驶证|会计证|教师证|普通话证)",
    re.I,
)
AWARD_OR_HEADING_RE = re.compile(
    r"(?:曾获|获奖|奖励|奖$|活动描述|实践描述|校内荣誉|社会实践|社团|学生会|协会|研究经历|课题)|"
    r"^(?:证书|证\s*书|Certifications?|Qualifications?|受到奖励|荣誉)$",
    re.I,
)
CERTIFICATE_NONCERT_RE = re.compile(
    r"^(?:上海|北京|天津|重庆|广州|深圳|南京|杭州|苏州|成都|武汉|西安|日本|中国)$|"
    r"^(?:培训)?证书$|^资格证书$|^认证证书$|"
    r"^(?:目前为|现为|参加|负责|协助|毕业的|通过|获得)|"
    r"(?:本科生|实验的设计|工作描述|职责描述)|"
    r"^(?:份|月份?)考试$|"
    r"(?:有限公司|有限责任公司|大学|学院|学校|协会|认证中心)$|"
    r"(?:优秀毕业|优秀论文|毕业论文)",
    re.I,
)
NONCORE_RE = re.compile(
    r"(?:实习|\bintern(?:ship)?\b|社团|学生社团|学生会|社联|校内协会|学校协会|校园协会|"
    r"文学社|研究会|研究经历|科研经历|课题研究|学术研究|毕业课题|毕业论文|在校实践经历|在校兼职)",
    re.I,
)


def canonical_month_date(value: str) -> str:
    result, _, invalid = normalize_date(value, "certificate_time")
    return "" if invalid else result


def is_noncore_work(work: dict[str, Any]) -> tuple[bool, str]:
    identity = " ".join(str(work.get(key) or "") for key in ("company_name", "position", "company_industry"))
    responsibilities = str(work.get("position_responsibilities") or "")
    if re.search(r"实习|见习|\bintern(?:ship)?\b|\btrainee\b", identity, re.I) or re.search(
        r"(?:在校|大学期间|海外).{0,24}实习|担任.{0,12}实习生", responsibilities, re.I
    ):
        return True, "internship_work_items_removed"
    extracurricular = " ".join((identity, responsibilities))
    if re.search(r"社团|学生会|社联|校内协会|学校协会|校园协会|文学社|研究会", extracurricular, re.I):
        return True, "school_extracurricular_work_items_removed"
    if re.search(r"研究助理|research assistant", identity, re.I):
        return True, "research_assistant_work_items_removed"
    return False, ""


def clean_company_fields(work: dict[str, Any], tracker: Counter[str]) -> None:
    original = str(work.get("company_name") or "").strip()
    company = re.sub(r"^\s*[012](?:\s+|\s*[：:]\s*)", "", original).strip()
    if company != original:
        tracker["company_leading_ordinals_removed"] += 1

    # Employee count is metadata, never part of the legal/company name.
    employee_match = re.search(r"[（(]\s*(\d+(?:\s*[-~至]\s*\d+)?\s*(?:人|people))\s*$", company, re.I)
    if employee_match:
        if not str(work.get("company_employees") or "").strip():
            work["company_employees"] = employee_match.group(1).replace(" ", "")
        company = company[:employee_match.start()].strip()
        tracker["company_employee_suffixes_extracted"] += 1

    # Parenthesized job nature and internship/translation notes are not company names.
    cleaned = re.sub(
        r"[（(][^）)]*(?:实习|学校实习|翻译|口译|日资|外资|兼职|全职|派遣|外派)[^）)]*[）)]",
        "", company, flags=re.I,
    ).strip()
    if cleaned != company:
        company = cleaned
        tracker["company_non_name_qualifiers_removed"] += 1

    # Handle source text truncated after an opening parenthesis. Remove known metadata;
    # otherwise preserve the alias/location and restore the missing closing parenthesis.
    opens = company.count("（") + company.count("(")
    closes = company.count("）") + company.count(")")
    if opens > closes:
        pos = max(company.rfind("（"), company.rfind("("))
        suffix = company[pos + 1:].strip()
        if re.search(r"^(?:实习|学校实习|日资|外资|海外|外派|派遣|东京|日本|中国|地点|部门|\d+.*(?:人|people))", suffix, re.I):
            company = company[:pos].strip()
            tracker["company_truncated_metadata_suffixes_removed"] += 1
        elif suffix:
            company += "）" if "（" in company[pos:] else ")"
            tracker["company_parentheses_balanced"] += 1
    work["company_name"] = company.strip(" ，,、")


def append_language(resume: dict[str, Any], name: str, level: str, tracker: Counter[str]) -> None:
    canonical = LANGUAGE_NAMES.get(name.casefold(), LANGUAGE_NAMES.get(name, name))
    canonical_level = LANGUAGE_LEVELS.get(level.casefold(), LANGUAGE_LEVELS.get(level, level)) if level else ""
    for item in resume["language_list"]:
        if str(item.get("language_name") or "").casefold() == canonical.casefold():
            if canonical_level and not str(item.get("language_level") or "").strip():
                item["language_level"] = canonical_level
            return
    resume["language_list"].append({
        "language_name": canonical,
        "language_level": canonical_level,
        "language_certificate": "",
        "language_certificate_time": "",
    })
    tracker["languages_moved_from_skills"] += 1


def append_certificate(resume: dict[str, Any], name: str, date_value: str, tracker: Counter[str]) -> None:
    normalized = re.sub(r"\s+", " ", name).strip(" ，,、:：")
    if not normalized:
        return
    for item in resume["certificate_list"]:
        if str(item.get("certificate_name") or "").strip().casefold() == normalized.casefold():
            if date_value and not str(item.get("certificate_time") or "").strip():
                item["certificate_time"] = date_value
            return
    resume["certificate_list"].append({
        "certificate_name": normalized,
        "certificate_type": "证书",
        "certificate_time": date_value,
    })
    tracker["certificates_moved_from_skills"] += 1


def repair_noncore_and_semantic_lists(resumes: list[dict[str, Any]], tracker: Counter[str]) -> None:
    """Remove non-core experiences and realign company/certificate/language/skill fields."""
    obvious_non_school = {
        "background", "受到奖励", "在校实践经验", "证书", "证        书", "求职信",
        "文学社成员", "兴趣爱好", "外语水平",
    }
    major_only = {"计算机软件", "纺织工程", "服装设计与工程", "日语", "工商管理", "计算机及应用", "engineering"}

    for resume in resumes:
        retained_work: list[dict[str, Any]] = []
        for work in resume["work_experiences"]:
            remove, reason = is_noncore_work(work)
            if remove:
                tracker[reason] += 1
                continue
            clean_company_fields(work, tracker)
            retained_work.append(work)
        resume["work_experiences"] = retained_work

        retained_education: list[dict[str, Any]] = []
        for education in resume["education_list"]:
            school = str(education.get("school_name") or "").strip()
            folded = re.sub(r"\s+", " ", school).casefold()
            if folded in obvious_non_school or NONCORE_RE.search(school):
                tracker["non_education_items_removed"] += 1
                continue
            if folded in major_only:
                if not str(education.get("school_major_name") or "").strip():
                    education["school_major_name"] = school
                education["school_name"] = ""
                tracker["major_values_moved_out_of_school_name"] += 1
            elif school in {"Shanghai", "日本", "京都"}:
                education["school_name"] = ""
                tracker["location_values_removed_from_school_name"] += 1
            elif re.fullmatch(r"Bachelor\s*[|/]\s*Japanese", school, re.I):
                education["school_name"] = ""
                education["school_major_name"] = education.get("school_major_name") or "日语"
                education["school_degree_type"] = education.get("school_degree_type") or "本科"
                education["school_degree_rank"] = education.get("school_degree_rank") or "4"
                tracker["combined_degree_major_school_values_split"] += 1
            retained_education.append(education)
        resume["education_list"] = merge_education_items(retained_education, tracker)

        # Strict certificate semantics: awards, activity labels and section headings are removed.
        clean_certificates: list[dict[str, Any]] = []
        certificate_seen: set[tuple[str, str]] = set()
        for certificate in resume["certificate_list"]:
            name = str(certificate.get("certificate_name") or "").strip()
            if not name or AWARD_OR_HEADING_RE.search(name) or CERTIFICATE_NONCERT_RE.search(name):
                tracker["awards_or_headings_removed_from_certificates"] += 1
                continue
            signature = (name.casefold(), str(certificate.get("certificate_time") or ""))
            if signature in certificate_seen:
                tracker["duplicate_certificates_removed"] += 1
                continue
            certificate_seen.add(signature)
            clean_certificates.append(certificate)
        resume["certificate_list"] = clean_certificates

        # Parse malformed token streams such as English / Good / 2011/7 / JLPT N2.
        raw_skills = resume["skills_list"]
        clean_skills: list[dict[str, Any]] = []
        skill_seen: set[tuple[str, str]] = set()
        pending_date = ""
        last_language: dict[str, Any] | None = None
        for skill in raw_skills:
            name = str(skill.get("skill_name") or "").strip()
            level = str(skill.get("skill_level") or "").strip()
            if (
                not name
                or re.fullmatch(r"[、,，;/\\|&()（）\s]+", name)
                or re.fullmatch(r"\d+(?:\.\d+)?", name)
                or re.search(r"^(?:Grade of .+|英语水平|日本语的级别|语语|德国)\s*[：:]?$", name, re.I)
                or SKILL_HEADING_RE.fullmatch(name)
            ):
                tracker["skill_fragments_or_headings_removed"] += 1
                continue
            if re.fullmatch(r"(?:19|20)\d{2}[./-]\d{1,2}", name):
                pending_date = canonical_month_date(name)
                tracker["certificate_dates_recovered_from_skills"] += 1
                continue
            matched = re.fullmatch(
                r"(英语|日语|中文|汉语|English|Japanese|Chinese|Mandarin|Korean|French|German|Spanish)"
                r"(?:\s*\(([^)]*)\))?\s*:?",
                name,
                re.I,
            )
            if matched:
                append_language(resume, matched.group(1), matched.group(2) or level, tracker)
                canonical = LANGUAGE_NAMES.get(matched.group(1).casefold(), matched.group(1))
                last_language = next((x for x in resume["language_list"] if str(x.get("language_name") or "").casefold() == canonical.casefold()), None)
                continue
            if CERTIFICATE_RE.search(name):
                append_certificate(resume, name, pending_date, tracker)
                pending_date = ""
                last_language = None
                continue
            if name.casefold() in LANGUAGE_LEVELS or name in LANGUAGE_LEVELS:
                if last_language is not None and not str(last_language.get("language_level") or "").strip():
                    last_language["language_level"] = LANGUAGE_LEVELS.get(name.casefold(), LANGUAGE_LEVELS.get(name, name))
                    tracker["orphan_language_levels_reconnected"] += 1
                else:
                    tracker["orphan_skill_levels_removed"] += 1
                continue
            last_language = None
            signature = (name.casefold(), level.casefold())
            if signature in skill_seen:
                tracker["duplicate_skills_removed"] += 1
                continue
            skill_seen.add(signature)
            clean_skills.append({"skill_name": name, "skill_level": level})
        resume["skills_list"] = clean_skills

        for list_name in ("project_list", "training_list"):
            retained: list[dict[str, Any]] = []
            for item in resume[list_name]:
                content = " ".join(str(value or "") for value in item.values())
                if NONCORE_RE.search(content):
                    tracker[f"noncore_{list_name}_items_removed"] += 1
                    continue
                retained.append(item)
            resume[list_name] = retained
            for sequence, item in enumerate(retained, 1):
                item["sequence_no"] = sequence


def make_education(school: str, major: str, degree: str, start: str, end: str) -> dict[str, Any]:
    rank = {"高中": "2", "大专": "3", "本科": "4", "学士": "4", "硕士": "5", "博士": "6"}.get(degree, "")
    education_type = {"高中": "全日制高中", "大专": "全日制大专", "本科": "全日制大学", "学士": "全日制大学", "硕士": "全日制研究生", "博士": "全日制博士"}.get(degree, "")
    return {
        "school_name": school, "school_major_name": major, "school_degree_type": degree,
        "school_degree_rank": rank, "school_education_type": education_type,
        "school_start_ym": start, "school_end_ym": end,
    }


def apply_strict_semantic_targeted_repairs(resumes: list[dict[str, Any]], index: int, tracker: Counter[str]) -> None:
    """Source-verified fixes for values that cannot be corrected safely by a broad rule."""
    if not resumes:
        return

    # These two duplicate source records contain a certificate block parsed as education.
    if index in {22, 649}:
        for resume in resumes:
            retained = []
            for education in resume["education_list"]:
                school = re.sub(r"\s+", "", str(education.get("school_name") or ""))
                if school == "证书":
                    append_certificate(resume, "日语一级证书", "2003年12月01日", tracker)
                    tracker["certificate_blocks_removed_from_education"] += 1
                else:
                    retained.append(education)
            resume["education_list"] = retained

    school_replacements = {
        277: ("中原工学", "中原工学院"),
        365: ("上海托普信息技术", "上海托普信息技术职业学院"),
        691: ("Shanghai East China", "上海华东师范大学"),
        1029: ("南通航运", "南通航运职业技术学院"),
        1106: ("JTB Travel &", "JTB Travel & Hotel College"),
        1467: ("四川科技园", "四川科技职业学院"),
        1489: ("辽宁建筑", "辽宁建筑职业学院"),
    }
    if index in school_replacements:
        old, new = school_replacements[index]
        for resume_index, resume in enumerate(resumes):
            for education in resume["education_list"]:
                if str(education.get("school_name") or "").strip() == old:
                    if index == 691 and resume_index > 0:
                        education["school_name"] = "Shanghai East China Normal University"
                    else:
                        education["school_name"] = new
                    tracker["source_verified_school_names_completed"] += 1

    if index == 143:
        for resume in resumes:
            for education in resume["education_list"]:
                if str(education.get("school_name") or "").strip() == "普高" and re.search(r"高中|中学", str(education.get("school_degree_type") or "")):
                    education["school_name"] = str(education.get("school_degree_type") or "").strip()
                    education["school_major_name"] = "普高"
                    education["school_degree_type"] = "高中"
                    education["school_degree_rank"] = "2"
                    education["school_education_type"] = "全日制高中"
                    tracker["source_verified_education_fields_realigned"] += 1

    if index == 650:
        zh_education = [
            make_education("拓殖大学", "国际经济与贸易", "硕士", "2013年04月01日", "2015年03月01日"),
            make_education("吉林华桥外国语学院", "商务英语", "本科", "2008年09月01日", "2012年06月01日"),
        ]
        en_education = [
            make_education("Takushoku University", "International Economics and Trade", "Master", "2013年04月01日", "2015年03月01日"),
            make_education("Jilin Huaqiao Foreign Languages University", "Business English", "Bachelor", "2008年09月01日", "2012年06月01日"),
        ]
        for resume_index, resume in enumerate(resumes):
            resume["education_list"] = copy.deepcopy(zh_education if resume_index == 0 else en_education)
            resume["skills_list"] = []
            resume["language_list"] = []
            for language, level in (("英语" if resume_index == 0 else "English", "优秀" if resume_index == 0 else "Excellent"),
                                    ("日语" if resume_index == 0 else "Japanese", "优秀" if resume_index == 0 else "Excellent"),
                                    ("德语" if resume_index == 0 else "German", "良好" if resume_index == 0 else "Good")):
                append_language(resume, language, level, tracker)
            resume["certificate_list"] = []
            for name in ("TEM 4", "TOEFL 84", "JLPT Level 1"):
                append_certificate(resume, name, "", tracker)
            tracker["source_verified_language_skill_blocks_rebuilt"] += 1

    if index in {907, 1005, 1286, 1708}:
        for resume in resumes:
            old = resume["education_list"]
            resume["education_list"] = [item for item in old if "在校实践" not in str(item.get("school_name") or "")]
            tracker["in_school_practice_education_removed"] += len(old) - len(resume["education_list"])

    if index in {1254, 1556}:
        marker = "FTTA" if index == 1254 else "EHSS"
        for resume in resumes:
            old = resume["education_list"]
            resume["education_list"] = [item for item in old if str(item.get("school_name") or "").strip() != marker]
            tracker["training_or_unverified_acronym_removed_from_education"] += len(old) - len(resume["education_list"])

    company_replacements = {
        116: ("财）日中经济协会上海事务所", "日中经济协会上海事务所"),
        385: ("SMG全资集团子公司)上海东方娱乐传媒集团有限公司", "上海东方娱乐传媒集团有限公司"),
        427: ("易程）苏州智通新技术股份有限公司", "易程（苏州）智通新技术股份有限公司"),
        1172: ("海外）株式会社グリーンオーナメント", "株式会社グリーンオーナメント"),
        1177: ("株）エスワイフード", "株式会社エスワイフード"),
    }
    if index in company_replacements:
        old, new = company_replacements[index]
        for resume in resumes:
            for work in resume["work_experiences"]:
                if str(work.get("company_name") or "").strip() == old:
                    work["company_name"] = new
                    tracker["source_verified_company_names_repaired"] += 1

    if index == 1556:
        for resume in resumes:
            names = [str(item.get("skill_name") or "") for item in resume["skills_list"]]
            if "雅思成绩" in names or "5.5" in names:
                resume["skills_list"] = [item for item in resume["skills_list"] if str(item.get("skill_name") or "") not in {"雅思成绩", "5.5"}]
                append_certificate(resume, "IELTS 5.5", "", tracker)
                tracker["source_verified_certificate_fragments_rebuilt"] += 1

    if index == 1559:
        verified_certificates = [
            ("医疗器械质量管理体系（ISO13485:2003/ISO9001:2008）内审员证", "2013年11月01日"),
            ("环境管理体系（EMS）国家注册审核员", "2013年12月01日"),
            ("食品安全管理体系国家注册审核员考试合格", "2013年06月01日"),
            ("职业健康安全管理体系（OHSMS）国家注册审核员", "2013年03月01日"),
            ("质量管理体系（QMS）国家注册审核员", "2012年12月01日"),
        ]
        for resume in resumes:
            resume["certificate_list"] = [
                {
                    "certificate_name": name,
                    "certificate_type": "审核员资格" if "审核员" in name else "证书",
                    "certificate_time": certificate_time,
                }
                for name, certificate_time in verified_certificates
            ]
            tracker["source_verified_auditor_certificates_rebuilt"] += 1


def make_work(
    company: str,
    position: str,
    start: str,
    end: str = "",
    *,
    dept: str = "",
    salary: str = "",
    industry: str = "",
    responsibilities: str = "",
) -> dict[str, Any]:
    item = {key: "" for key in ITEMS["work_experiences"]}
    item.update({
        "company_name": company,
        "company_industry": industry,
        "position": position,
        "position_salary": salary,
        "position_dept": dept,
        "employment_type": "全职",
        "position_start": start,
        "position_resigned": end,
        "position_responsibilities": responsibilities,
    })
    return item


def apply_targeted_work_repairs(resumes: list[dict[str, Any]], index: int, tracker: Counter[str]) -> None:
    """Corrections reviewed against exact source lines for the remaining outliers."""
    if index == 300 and len(resumes) >= 2:
        # Pure-English 51job source.  A previous list-alignment pass copied the
        # translated company names back into the English resume and lost the
        # position/description fields.  Rebuild both aligned versions from the
        # six source work blocks; resume[0] is the complete Chinese translation
        # and resume[1] preserves the English source text.
        rows = [
            (
                "上海舒步飞贸易有限公司", "Shanghai Shubufei Trading Co.,Ltd", "销售经理", "Sales Mananger",
                "女装部", "Female Department", "贸易/进出口", "Trading/Import & Export",
                "每年出国八次以上，与客户面对面维护关系并确认订单。2013年带领团队完成2500万美元针织和梭织服装销售，产品覆盖婴儿、儿童及女装；与40多家工厂合作下单，确保质量和按期交付，并维护客户及合作工厂关系。南非主要客户为Ackermans和Mr Price。",
                "Go oversea more than 8 times per year to maintain the customer and confirm the orders with the buyer face to face.Leading the team in 2013 , completed a $ 25 million sales including knit & woven , range from Infant to Children to Ladies'wear.Cooperating over 40 factories to place all the orders and make sure the satisfying quality and on time delivery. To make sure the satisfying with the customer and good relationship with the cooperating factories.Main customer in South Africa is Ackermans & Mr Price.",
            ),
            (
                "上海麦考林国际邮购有限公司", "Shanghai Mecoxlane Mailorder Company", "产品主管", "Product Supervisor",
                "第一部门", "Department 1", "服装/纺织/皮革", "Apparel/Textiles/Leather Goods",
                "兼任跟单员和采购，负责流行趋势、面料、流行色、样衣与款式、报价、销售价格、生产跟进、交期、质量和销售；主管女装梭织组及Euromoda、Rampage品牌。根据目录、零售和B2C三类渠道的不同需求准备产品，区分款式、价格和各地门店上架时间，并参与时装秀、杂志、模特和广告等品牌推广工作。",
                "My job in Mecoxlane is not only a Merchandiser,but also working as a buyer.From estimating the fashion trend,fabric,popular color,samples & styling,price quotation,sales price,follow up the production status,push for the delivery date and be response for the quality and sales.I'm in charge of the woven group,mainly for Ladies' wear.Euromoda & Rampage brand. Since Mecoxlane has three sales channel,Cataloge,Retail,B2C,so we have to meet the different need of the consumers from each channel.And most of the time,the needs are totally different.So that we must prepare different products for each channel ,seperating the styling and sales price.And we have to consider the in shop date for the retail of allover the country,since the season is different a little bit,and the product we support should be different. Another important task is to extend the brand,we do a lot of work to set up the fashion show,magazine,models,advertising",
            ),
            (
                "新德与博明控股（香港）有限公司", "Suntor & Blooming Holdings (H.K) Ltd", "高级跟单员", "Senior Merchandiser",
                "纺织第四部", "Textile Department 4", "贸易/进出口", "Trading/Import & Export",
                "负责Auchan、S'Oliver、Karsdadt和Casino的梭织及针织产品跟单，覆盖打样、报价、审批、生产、质检和出货全流程；协调采购商与工厂关系，确保按时且保质出货。",
                "In charge of merchandising the woven & knit products for Auchan,S'Oliver,Karsdadt,Casino.Responsible from sampling,quotation,approval process,production,quality inspection to shipment.Communicate with buyer and factory,to coordinate the relationship and ensure the shipment on time in good quality.",
            ),
            (
                "中国直达有限公司", "ProChinaDirect Co.,Ltd", "高级跟单员", "Senior Merchandiser",
                "跟单部", "Merchandising", "贸易/进出口", "Trading/Import & Export",
                "负责欧洲市场礼品促销类纺织品，尤其是大众汽车集团的汽车促销品，包括棒球帽、针织帽、手套、围巾、安全背心、功能夹克、外套及其他纺织品；在国内寻找合适工厂，下单并跟进订单、质量控制和出货。",
                "In charge of the gift promotion items ( Textiles)for European market,especially for the Volkswagen Group as a car promotion items.Such as Baseball Cap,Knitted Hat & Gloves & Scarf,Safty Vest,Functional Jacket,Outerwear,and the other textile related products.Searching the right factory for each item domestically,place the order,follow up the order process,QC and shipment.",
            ),
            (
                "塔吉特采购服务公司/AMC", "Target Sourcing Services/AMC", "跟单员", "Merchandiser",
                "Target软商品部", "Target Softline", "贸易/进出口", "Trading/Import & Export",
                "服务海外客户，为特定产品寻找合适供应商，并负责流行趋势跟踪、打样、订单流程跟进和工厂评估。",
                "Servicing for the foreign customer,find the right vendor for special items,fashion trend tracking,sampling,order process follow up,factory evaluation",
            ),
            (
                "上海好未来服装有限公司", "Shanghai Good Future Garment Co.,Ltd", "跟单员/贸易专员/助理", "Merchandiser / Trading/Specialist/Assistant",
                "", "", "服装/纺织/皮革", "Apparel/Textiles/Leather Goods",
                "联系海外客户，尤其面向美国市场，跟进从开发、打样、生产到运输的完整订单流程。",
                "Contacting with foreign customers,especially for US Market,from developinng,sampling,production,shipping,follow up all the order process",
            ),
        ]
        for resume_index, resume in enumerate(resumes[:2]):
            rebuilt: list[dict[str, Any]] = []
            old = resume.get("work_experiences") or []
            for row_index, row in enumerate(rows):
                zh_company, en_company, zh_role, en_role, zh_dept, en_dept, zh_industry, en_industry, zh_desc, en_desc = row
                item = copy.deepcopy(old[row_index]) if row_index < len(old) else make_work("", "")
                item.update({
                    "company_name": zh_company if resume_index == 0 else en_company,
                    "company_industry": zh_industry if resume_index == 0 else en_industry,
                    "position": zh_role if resume_index == 0 else en_role,
                    "position_dept": zh_dept if resume_index == 0 else en_dept,
                    "position_responsibilities": zh_desc if resume_index == 0 else en_desc,
                    "employment_type": "全职" if resume_index == 0 else "Full-time",
                    "status": "离职" if resume_index == 0 else "Former",
                })
                rebuilt.append(item)
            resume["work_experiences"] = rebuilt
            education = resume.get("education_list") or []
            if education:
                education[0]["school_name"] = "上海大学" if resume_index == 0 else "Shanghai University"
                education[0]["school_major_name"] = "国际经济与贸易" if resume_index == 0 else "International Economics and Trade"
                education[0]["school_degree_type"] = "本科" if resume_index == 0 else "Bachelor"
            # Driving school was parsed twice as projects.  It is ancillary
            # training/certification, not a work or core project experience.
            resume["project_list"] = []
        tracker["english_source_versions_restored"] += 1

    collapsed: dict[int, list[dict[str, Any]]] = {
        185: [
            make_work("音乐培训中心", "前台接待兼行政助理", "2012年06月01日", "2013年01月01日"),
            make_work("新华书店", "销售电子数码产品，电子数码产品售后", "2012年02月01日", "2012年05月01日"),
            make_work("大润发超市", "顾客服务中心", "2011年12月01日", "2012年02月01日"),
            make_work("圣迪奥服装", "导购/销售", "2009年12月01日", "2010年02月01日"),
        ],
        628: [
            make_work("Shanghai JinDa Customs Broker Co, Ltd", "Sea Export declarant", "2009年06月01日", salary="4001-6000RMB/Month", industry="Logistics/Warehouse"),
            make_work("ADC International Transportation Co,Ltd", "Air Express", "2006年02月01日", "2009年06月01日", salary="2001-4000RMB/Month", industry="Logistics/Warehouse"),
            make_work("Beijing Kintetsu World Express co.ltd.", "Air Export OP", "2004年03月01日", "2005年12月01日", salary="2001-4000RMB/Month", industry="Logistics/Warehouse"),
        ],
        634: [make_work("ITOCHU TEXTILE(CHINA)CO.,LTD.", "Trading/Specialist/Assistant", "2013年07月01日", dept="SALES", industry="Trading/Import & Export")],
        635: [make_work("ITOCHU TEXTILE(CHINA)CO.,LTD.", "Trading/Specialist/Assistant", "2013年07月01日", dept="SALES", industry="Trading/Import & Export")],
        675: [make_work("WUXI AITE Micro-Electronics Ltd.", "Project Manager Assistant", "2017年04月01日", "2018年02月01日", salary="4001-6000RMB/Month", industry="Electronic/Semiconductor/IC")],
        691: [
            make_work("Lanso Konly (Shanghai) Instruments Co., Ltd.", "quality manager", "2015年05月01日", salary="15000-25000RMB/Month", industry="Instruments and Meters & Industrial Automation"),
            make_work("Shanghai Baosteel & Arcelor Tailor Metal Co., Ltd.", "quality manager", "2009年03月01日", "2015年04月01日", salary="10001-15000RMB/Month", industry="Automobile/Motorcycle"),
            make_work("Shanghai Baosteel&Arcelor Tailor Metal Co.,Ltd.", "Project Manager", "2007年09月01日", "2009年03月01日", salary="10001-15000RMB/Month", industry="Automobile/Motorcycle"),
            make_work("Shanghai Baosteel&Arcelor Tailor Metal Co.,Ltd.", "Production Manager/Workshop Supervisor", "2005年07月01日", "2007年08月01日", salary="8001-10000RMB/Month", industry="Automobile/Motorcycle"),
            make_work("Zhejiang Jiaxing Min Hui Auto Parts Co., Ltd.", "Quality Management", "2004年10月01日", "2005年05月01日", salary="4001-6000RMB/Month", industry="Automobile/Motorcycle"),
            make_work("Fuzhou Hersheen Auto Parts Co., Ltd. (South East Motor City)", "Quality Management", "1999年08月01日", "2004年10月01日", salary="2001-4000RMB/Month", industry="Automobile/Motorcycle"),
        ],
        698: [
            make_work("SHANGHAI KOGANEI INTERNATIONAL TRADING CORPORATION", "Accountant / Accounting Trainee", "2007年11月01日", dept="Financial Department", industry="Trading/Import & Export"),
            make_work("Shanghai Tsuchiya Accounting Firm", "Audit Executive/Assistant", "2007年03月01日", "2007年08月01日", dept="Business Department", industry="Accounting, Auditing"),
        ],
        704: [
            make_work("TSMT, wujiang.Co. Ltd.", "Supplies & Equipment Quality Management", "2016年08月01日", dept="SQE", industry="Electronics/Semiconductor/IC"),
            make_work("ROE, wujiang.Co,Ltd.", "QA/QC Engineer", "2013年09月01日", "2016年07月01日", dept="IQC engineer", industry="Electronics/Semiconductor/IC"),
        ],
        716: [
            make_work("Sino-American Shanghai Squibb Pharmaceuticals", "Chemical Analyst", "2014年09月01日", dept="QC", industry="Pharmaceuticals/Biotechnology"),
            make_work("Ethypharm pharmaceutical Co Ltd", "Chemical Analyst", "2012年09月01日", "2014年08月01日", dept="QC", industry="Pharmaceuticals/Biotechnology"),
        ],
        719: [
            make_work("Beiqi Foton Motor Co., Ltd.", "New Energy Battery Engineer", "2017年06月01日", dept="Technology Center", industry="Automobile & Components"),
            make_work("Wuyang-Honda Motorcycle (Guangzhou) Co., Ltd.", "Structrual Engineer", "2014年05月01日", "2017年06月01日", dept="Technical department", industry="Automobile & Components"),
            make_work("Chongqing Huansong Industry (Group) Co., Ltd.", "Engine design technician", "2012年06月01日", "2014年05月01日", dept="R & D Center", industry="Automobile & Components"),
        ],
    }
    if index in collapsed:
        for resume in resumes:
            old = resume["work_experiences"]
            descriptions = [str(item.get("company_name") or "") for item in old if str(item.get("company_name") or "").startswith("Description:")]
            rebuilt = copy.deepcopy(collapsed[index])
            if descriptions and rebuilt:
                rebuilt[0]["position_responsibilities"] = "\n".join(text.split(":", 1)[-1].strip() for text in descriptions)
            resume["work_experiences"] = rebuilt
            tracker["collapsed_english_work_sections_rebuilt"] += 1
        return

    for resume_index, resume in enumerate(resumes):
        works = resume["work_experiences"]
        if resume_index == 0 and index in {772, 1137, 1538, 1615}:
            # These pages repeat each employment once as an industry/salary row
            # and once as the actual position row.  Keep one semantic employment
            # per company/date range so it stays aligned with the source-language
            # resume instead of treating parser fragments as extra jobs.
            preferred_positions = {
                772: {
                    ("株式会社八千代エンジニヤリング", "2018年04月01日"): "技术职",
                    ("岩手花卷机场", "2016年04月01日"): "翻译组组长",
                    ("日本综合广告社", "2013年04月01日"): "助手",
                },
                1137: {
                    ("株式会社ディスコ", "2014年09月01日"): "机械工程师",
                    ("株式会社ディスコ", "2013年04月01日"): "应用技术工程师",
                },
                1538: {
                    ("厦门兴联集团有限公司", "2009年09月01日"): "课长",
                },
                1615: {
                    ("関東インフォメーション営業部", "2016年03月01日"): "咨询台前台",
                },
            }[index]
            retained_by_key: dict[tuple[str, str, str], dict[str, Any]] = {}
            for work in works:
                company = str(work.get("company_name") or "")
                start = str(work.get("position_start") or "")
                end = str(work.get("position_resigned") or "")
                key = (company, start, end)
                preferred = preferred_positions.get((company, start))
                current = retained_by_key.get(key)
                if current is None:
                    retained_by_key[key] = work
                    current = work
                if preferred and str(work.get("position") or "") == preferred:
                    retained_by_key[key] = work
                elif preferred and current is work:
                    current["position"] = preferred
            resume["work_experiences"] = list(retained_by_key.values())
            works = resume["work_experiences"]
            company_translations = {
                "株式会社八千代エンジニヤリング": "八千代工程株式会社",
                "株式会社ディスコ": "DISCO株式会社",
                "遨都（上海）环保科技有限公司/アルファブロス株式会社（上海事務所・大阪本部）": "遨都（上海）环保科技有限公司/Alpha Bros株式会社（上海办事处・大阪总部）",
                "関東インフォメーション営業部": "关东信息营业部",
            }
            for work in works:
                company = str(work.get("company_name") or "")
                if company in company_translations:
                    work["company_name"] = company_translations[company]
            tracker["duplicate_work_fragments_collapsed"] += 1
        if index == 292:
            for work in works:
                if "上海彰马服饰有限公司" in str(work.get("company_name") or ""):
                    text = str(work["company_name"])
                    work["company_name"] = "上海彰马服饰有限公司"
                    work["position"] = "外贸跟单兼采购员"
                    work["position_responsibilities"] = "\n".join(part for part in (text.split("主要负责", 1)[-1].strip("，。"), str(work.get("position_responsibilities") or "")) if part)
                    tracker["source_verified_company_position_repaired"] += 1
        elif index in {491, 588, 680}:
            retained: list[dict[str, Any]] = []
            for work in works:
                company = str(work.get("company_name") or "")
                is_project = (
                    (index == 588 and not str(work.get("position") or "").strip())
                    or "项目描述" in company
                    or (index == 491 and ("项目" in company or company.endswith(("开发，测试。", "的开发。"))))
                )
                if is_project:
                    project = project_from_work(work, len(resume["project_list"]) + 1)
                    project["description"] = company if not project["description"] else project["description"]
                    resume["project_list"].append(project)
                    tracker["source_verified_work_items_moved_to_projects"] += 1
                elif index == 491 and company in {"新人培训", "Java开发培训"}:
                    resume["training_list"].append({
                        "sequence_no": len(resume["training_list"]) + 1,
                        "organization_name": "",
                        "training_name": company,
                        "start_ym": str(work.get("position_start") or ""),
                        "end_ym": str(work.get("position_resigned") or ""),
                        "certificate_name": "",
                        "description": "",
                    })
                    tracker["source_verified_work_items_moved_to_training"] += 1
                else:
                    retained.append(work)
            resume["work_experiences"] = retained
        elif index in {763, 1357}:
            description_prefixes = ("负责", "协助")
            valid_by_start = {
                str(work.get("position_start") or ""): work
                for work in works
                if not str(work.get("company_name") or "").startswith(description_prefixes)
                and str(work.get("position") or "") != "担当"
            }
            retained = []
            for work in works:
                company = str(work.get("company_name") or "")
                if company.startswith(description_prefixes) and str(work.get("position_start") or "") in valid_by_start:
                    target = valid_by_start[str(work.get("position_start") or "")]
                    target["position_responsibilities"] = "\n".join(part for part in (str(target.get("position_responsibilities") or ""), company) if part)
                    tracker["description_only_work_items_merged"] += 1
                else:
                    retained.append(work)
            resume["work_experiences"] = retained
        elif index == 1203 and works:
            works[0]["position"] = "日语翻译"
            tracker["source_verified_positions_repaired"] += 1
        elif index == 1323:
            retained = []
            for work in works:
                if "毕业论文" in str(work.get("company_name") or ""):
                    resume["project_list"].append(project_from_work(work, len(resume["project_list"]) + 1))
                    tracker["thesis_work_items_moved_to_projects"] += 1
                else:
                    work["position"] = re.sub(r"\s*[|｜]\s*\d.*$", "", str(work.get("position") or "")).strip()
                    retained.append(work)
            resume["work_experiences"] = retained
        elif index == 1428:
            for work in works:
                if str(work.get("company_name") or "").strip() == "API":
                    work["position"] = "测量应用工程师"
                    tracker["source_verified_positions_repaired"] += 1
        elif index == 1143 and resume_index == 0:
            for work in works:
                if str(work.get("company_name") or "") == "日立販売管理システム":
                    work["company_name"] = "日立销售管理系统"
                elif str(work.get("company_name") or "") == "トヨタ車体":
                    work["company_name"] = "丰田车体"
                responsibility = str(work.get("position_responsibilities") or "")
                if "「 TimeAsset 」は" in responsibility:
                    responsibility = re.sub(
                        r"「 TimeAsset 」は.*?index\.html",
                        "“TimeAsset”是由考勤系统领先品牌AMANO打造的大规模考勤信息系统。"
                        "该系统与客户共同设计和构建，可实现适合企业的考勤管理与人才管理。"
                        "详情：http://www.tis.amano.co.jp/products/TimeAsset/index.html",
                        responsibility,
                        flags=re.S,
                    )
                    responsibility = (
                        responsibility
                        .replace("個人勤務スケジュール模块", "个人工作计划模块")
                        .replace("日次データ集計模块", "每日数据汇总模块")
                        .replace("応援データ集計模块", "支援数据汇总模块")
                    )
                    work["position_responsibilities"] = responsibility
            tracker["mixed_japanese_primary_fields_translated"] += 1
        elif index == 1095 and resume_index == 0 and works:
            works[0]["position_dept"] = "A2（Always & ADK 合资公司）"
            tracker["source_verified_departments_repaired"] += 1
        elif index == 1255:
            for work in works:
                if str(work.get("position_start") or "") == "2016年04月01日":
                    work["position"] = "前台接待" if resume_index == 0 else "フロント"
                    tracker["source_verified_positions_repaired"] += 1
            if resume_index > 0:
                resume["resume_languge"] = "jp"
                tracker["source_verified_language_labels_repaired"] += 1
        elif index in {1511, 1513, 1661, 1676} and works:
            role = {1511: "市场营销传播实习", 1513: "教练", 1661: "研究助理", 1676: "高级培训专员"}[index]
            works[0]["position"] = role
            works[0]["position_dept"] = ""
            tracker["filename_verified_positions_repaired"] += 1
        elif index in {1094, 1095} and resume_index > 0 and resumes[0]["work_experiences"]:
            primary_by_start = {str(item.get("position_start") or ""): item for item in resumes[0]["work_experiences"]}
            for work in works:
                primary = primary_by_start.get(str(work.get("position_start") or ""))
                if primary:
                    work["company_name"] = primary["company_name"]
                    work["position"] = primary["position"]
                    tracker["parallel_resume_work_alignment_repaired"] += 1
            if index == 1095 and works:
                works[0]["position_dept"] = "A2（Always&ADK合資会社）"
                tracker["source_verified_departments_repaired"] += 1

        for sequence, project in enumerate(resume["project_list"], 1):
            project["sequence_no"] = sequence
        for sequence, training in enumerate(resume["training_list"], 1):
            training["sequence_no"] = sequence


def repair_section_spillover(resumes: list[dict[str, Any]], plain: str, tracker: Counter[str]) -> None:
    all_clean_positions: dict[tuple[str, str], str] = {}
    bad_labels = re.compile(r"^(?:工作描述|项目描述|责任描述|实践描述)\s*[：:]?$", re.I)
    for resume in resumes:
        for work in resume["work_experiences"]:
            company_key = compact_text(work.get("company_name"))
            position = str(work.get("position") or "").strip()
            if company_key and position and position != "担当" and not bad_labels.match(position):
                all_clean_positions[(company_key, str(work.get("position_start") or ""))] = position

    for resume in resumes:
        retained: list[dict[str, Any]] = []
        projects = resume["project_list"]
        training = resume["training_list"]
        education_keys = {compact_text(item.get("school_name")) for item in resume["education_list"]}
        for work in resume["work_experiences"]:
            company = str(work.get("company_name") or "").strip()
            position = str(work.get("position") or "").strip()
            company_key = compact_text(company)
            position_key = position.rstrip("：:").strip()
            if position_key in {"项目描述", "责任描述", "实践描述"}:
                project = project_from_work(work, len(projects) + 1)
                project_key = (compact_text(project["project_name"]), project["start_ym"], project["end_ym"])
                existing_keys = {
                    (compact_text(item.get("project_name")), str(item.get("start_ym") or ""), str(item.get("end_ym") or ""))
                    for item in projects
                }
                if project_key not in existing_keys and project["project_name"]:
                    projects.append(project)
                    tracker["work_items_moved_to_projects"] += 1
                else:
                    tracker["duplicate_project_work_items_removed"] += 1
                continue
            if position_key in {"培训机构", "培训经历"}:
                if not training:
                    training.append({
                        "sequence_no": 1,
                        "organization_name": "",
                        "training_name": company,
                        "start_ym": str(work.get("position_start") or ""),
                        "end_ym": str(work.get("position_resigned") or ""),
                        "certificate_name": "",
                        "description": str(work.get("position_responsibilities") or ""),
                    })
                    tracker["work_items_moved_to_training"] += 1
                else:
                    tracker["duplicate_training_work_items_removed"] += 1
                continue
            if position_key in {"证书", "语言能力", "培训经验", "在校学习情况"}:
                tracker["non_work_section_items_removed"] += 1
                continue
            if any(key and (key in company_key or company_key in key) for key in education_keys) and re.search(r"大学|学院|学校|本科|硕士|博士|大专|中专", company):
                tracker["education_spillover_removed_from_work"] += 1
                continue
            lookup_key = (company_key, str(work.get("position_start") or ""))
            if position == "担当" and lookup_key in all_clean_positions:
                tracker["duplicate_fallback_work_items_removed"] += 1
                continue
            if position_key == "工作描述":
                recovered = all_clean_positions.get(lookup_key) or clean_position_from_source(company, plain)
                if recovered:
                    work["position"] = recovered
                    tracker["positions_recovered_from_source_or_parallel_resume"] += 1
            retained.append(work)

        # Collapse exact parser duplicates while preserving genuinely different
        # positions at the same employer.
        deduped: list[dict[str, Any]] = []
        seen: dict[tuple[str, str, str], dict[str, Any]] = {}
        for work in retained:
            key = (
                compact_text(work.get("company_name")),
                str(work.get("position_start") or ""),
                compact_text(work.get("position")),
            )
            if key not in seen or not key[0]:
                seen[key] = work
                deduped.append(work)
                continue
            target = seen[key]
            for field in ITEMS["work_experiences"]:
                if not target.get(field) and work.get(field):
                    target[field] = work[field]
            tracker["exact_duplicate_work_items_merged"] += 1
        resume["work_experiences"] = deduped
        for sequence, project in enumerate(projects, 1):
            project["sequence_no"] = sequence
        for sequence, item in enumerate(training, 1):
            item["sequence_no"] = sequence


def apply_source_evidence_repairs(resumes: list[dict[str, Any]], index: int, tracker: Counter[str]) -> None:
    """Apply small, reviewed corrections whose exact values are visible in source."""
    if not resumes:
        return
    primary = resumes[0]
    if index == 394 and len(primary["training_list"]) > 1:
        if primary["training_list"][1].get("end_ym") != "2013年06月01日":
            primary["training_list"][1]["end_ym"] = "2013年06月01日"
            tracker["source_verified_dates_repaired"] += 1
    elif index == 1552 and len(primary["training_list"]) > 1:
        if primary["training_list"][1].get("end_ym") != "2014年04月01日":
            primary["training_list"][1]["end_ym"] = "2014年04月01日"
            tracker["source_verified_dates_repaired"] += 1
    elif index == 1553 and primary["training_list"]:
        if primary["training_list"][0].get("end_ym") != "2017年03月01日":
            primary["training_list"][0]["end_ym"] = "2017年03月01日"
            tracker["source_verified_dates_repaired"] += 1
    elif index == 842 and len(primary["certificate_list"]) > 7:
        # “2014-2015学年”是区间，不是可落入 certificate_time 的月份。
        # EN: "2014-2015学年" (academic year 2014-2015) is a range, not a month that can go into certificate_time.
        # JA: 「2014-2015学年」（2014〜2015 年度）は範囲であり、certificate_time に入れられる月ではない。
        if primary["certificate_list"][7].get("certificate_time"):
            primary["certificate_list"][7]["certificate_time"] = ""
            tracker["invalid_award_dates_cleared"] += 1
    elif index == 1287:
        if len(primary["certificate_list"]) > 5:
            if primary["certificate_list"][5].get("certificate_time"):
                primary["certificate_list"][5]["certificate_time"] = ""
                tracker["invalid_award_dates_cleared"] += 1
        if len(primary["language_list"]) > 1:
            if primary["language_list"][1].get("language_certificate_time"):
                primary["language_list"][1]["language_certificate_time"] = ""
                tracker["invalid_award_dates_cleared"] += 1
    elif index == 1323:
        for item_index in (3, 5):
            if len(primary["certificate_list"]) > item_index:
                if primary["certificate_list"][item_index].get("certificate_time"):
                    primary["certificate_list"][item_index]["certificate_time"] = ""
                    tracker["invalid_award_dates_cleared"] += 1
    elif index == 1354 and len(primary["certificate_list"]) > 2:
        if primary["certificate_list"][2].get("certificate_time") != "2011年12月01日":
            primary["certificate_list"][2]["certificate_time"] = "2011年12月01日"
            tracker["source_verified_dates_repaired"] += 1
    elif index == 1601:
        old = primary["training_list"]
        primary["training_list"] = [
            item for item in old
            if item.get("organization_name") or not re.search(r"学年|团日|志愿者|获奖|荣誉", str(item.get("training_name") or ""))
        ]
        if len(old) != len(primary["training_list"]):
            tracker["misclassified_awards_removed_from_training"] += len(old) - len(primary["training_list"])
    elif index == 925 and primary["training_list"]:
        tracker["project_text_removed_from_training"] += len(primary["training_list"])
        primary["training_list"] = []
    elif index == 299 and primary["training_list"]:
        tracker["certificate_text_removed_from_training"] += len(primary["training_list"])
        primary["training_list"] = []
        language_rows = [
            {"language_name": "英语", "language_level": "英语专业四级", "language_certificate": "英语专业四级", "language_certificate_time": "2003年03月01日"},
            {"language_name": "英语", "language_level": "大学英语六级", "language_certificate": "大学英语六级", "language_certificate_time": "2001年06月01日"},
        ]
        primary["language_list"] = language_rows
        if not any(item.get("certificate_name") == "驾驶执照" for item in primary["certificate_list"]):
            primary["certificate_list"].append({"certificate_name": "驾驶执照", "certificate_type": "驾驶证", "certificate_time": "2006年12月01日"})
        tracker["source_verified_certificate_language_reclassified"] += 4

    for resume in resumes:
        for field in ("training_list", "project_list"):
            for sequence, item in enumerate(resume[field], 1):
                item["sequence_no"] = sequence


def apply_verified_multilingual_translations(resumes: list[dict[str, Any]], index: int, tracker: Counter[str]) -> None:
    """Apply reviewed proper-name translations that the offline model preserves verbatim."""
    if not resumes:
        return

    if index == 638:
        before = len(resumes)
        resumes[:] = [
            resume for resume in resumes
            if resume.get("resume_languge") != "en"
        ]
        if len(resumes) != before:
            tracker["source_unverified_language_versions_removed"] += before - len(resumes)

    # Index 673 was parsed with five Project Experience rows mixed into work.
    if index == 673:
        project_names = {
            "electric control system for seawater tower hoist": "海水塔起重机电控系统",
            "Overseas after-sales service": "海外售后服务",
            "SWS jacking system for jack-up drilling platform": "SWS自升式钻井平台升降系统",
            "FnG jacking system for jack-up drilling platform": "FnG自升式钻井平台升降系统",
            "The HK-Zhuhai-Macao bridge island tunnel engineeri": "港珠澳大桥岛隧工程",
            "电气控制系统,用于海水塔升降": "海水塔起重机电控系统",
            "海外售后服务": "海外售后服务",
            "起钻井平台的SWS接系统": "SWS自升式钻井平台升降系统",
            "杆钻井平台的FnG接系统": "FnG自升式钻井平台升降系统",
            "港湾-朱海-澳门桥梁道工程师 (HK-)": "港珠澳大桥岛隧工程",
        }
        for resume in resumes:
            retained_work = []
            for work in resume.get("work_experiences") or []:
                position = str(work.get("position") or "").strip()
                if position not in project_names:
                    retained_work.append(work)
                    continue
                project_name = project_names[position] if resume.get("resume_languge") == "zh" else position
                resume["project_list"].append({
                    "sequence_no": len(resume["project_list"]) + 1,
                    "fingerprint": "",
                    "project_name": project_name,
                    "company_or_client": str(work.get("company_name") or ""),
                    "role_name": "",
                    "start_ym": str(work.get("position_start") or ""),
                    "end_ym": str(work.get("position_resigned") or ""),
                    "description": str(work.get("position_responsibilities") or ""),
                    "responsibilities": "",
                    "achievements": str(work.get("position_achievements") or ""),
                    "keywords": "",
                })
                tracker["source_verified_work_items_moved_to_projects"] += 1
            resume["work_experiences"] = retained_work
    elif index == 627 and resumes[0].get("work_experiences"):
        translated_responsibilities = [
            "1. 识别降本机会，负责价格分析及与供应商谈判，并与其他部门紧密协作。\n2. 选择并开发合适的供应商。\n3. 负责国内及出口项目的供应商寻源与开发。\n4. 收集供应商信息并完善供应商数据库。\n5. 按时完成供应商质量评估及整改计划，处理质量问题。\n6. 推进产品本地化。",
            "1. 管理并维护重点客户关系。\n2. 向客户报价、确认产品交付并制定出货计划；负责新车型报价及年度降本，并依据客户系统更新调整出货和生产计划。\n3. 管理工程变更通知进度。",
        ]
        for work, responsibilities in zip(resumes[0]["work_experiences"], translated_responsibilities):
            work["position_responsibilities"] = responsibilities
        tracker["source_verified_responsibilities_translated"] += min(len(resumes[0]["work_experiences"]), len(translated_responsibilities))

    verified_names = {636: "阮晶", 666: "周惠玲", 673: "倪利兵", 692: "马蓉琼"}
    replacements_by_index: dict[int, dict[str, str]] = {
        636: {
            "Toray International (China) Co., Ltd": "东丽国际贸易（中国）有限公司",
            "Shanghai Pharmaceutical Co., Ltd": "上海医药集团股份有限公司",
            "Shanghai Jiaotong University": "上海交通大学",
            "Buyer": "采购员",
            "药房": "药学",
        },
        666: {
            "Celestica": "天弘科技",
            "Shanghai Yinda Technology Co., LTD": "上海银达科技有限公司",
            "Shanghai University": "上海大学",
            "Nanjing Information Engineering University": "南京信息工程大学",
        },
        673: {
            "Shanghai ZhenHua Heavy Industries Co., LTD.": "上海振华重工（集团）股份有限公司",
            "Shanghai Maritime university": "上海海事大学",
        },
        692: {
            "Shanghai Suoguang Electronic Company LTD.": "上海索广电子有限公司",
            "Shanghai Jiaotong University": "上海交通大学",
        },
    }
    primary = resumes[0]
    if index in verified_names and primary["base_info"].get("full_name") != verified_names[index]:
        primary["base_info"]["full_name"] = verified_names[index]
        tracker["source_verified_chinese_names_repaired"] += 1
    replacements = replacements_by_index.get(index, {})
    common_replacements = {
        "On job": "在职",
        "Dimission": "离职",
        "Account Manager": "客户经理",
        "Customer Program Manager": "客户项目经理",
        "Project Manager": "项目经理",
        "Project Manager Assistant": "项目经理助理",
        "SUB LEADER": "副组长",
        "STAFF": "项目成员",
        "PL~PM": "项目负责人/项目经理",
        "coordinator": "协调员",
        "SALES": "销售",
        "Chemical Analyst": "化学分析员",
        "quality manager": "质量经理",
        "Quality Management": "质量管理",
        "QA/QC Engineer": "质量保证/质量控制工程师",
        "IQC engineer": "来料质量控制工程师",
        "Structrual Engineer": "结构工程师",
        "Engine design technician": "发动机设计技术员",
        "New Energy Battery Engineer": "新能源电池工程师",
        "Production Manager/Workshop Supervisor": "生产经理/车间主管",
        "Audit Executive/Assistant": "审计主管/助理",
        "Sea Export declarant": "海运出口报关员",
        "Air Export OP": "空运出口操作员",
        "Air Express": "航空快递",
        "Vessel": "船务",
        "Business Department": "业务部",
        "Technical department": "技术部",
        "Technology Center": "技术中心",
        "R & D Center": "研发中心",
        "Automobile/Motorcycle": "汽车/摩托车",
        "Automobile & Components": "汽车及零部件",
        "Logistics/Warehouse": "物流/仓储",
        "Electronics/Semiconductor/IC": "电子技术/半导体/集成电路",
        "Electronic/Semiconductor/IC": "电子技术/半导体/集成电路",
        "Pharmaceuticals/Biotechnology": "制药/生物工程",
        "Trading/Import & Export": "贸易/进出口",
        "Trading/Specialist/Assistant": "贸易专员/助理",
        "Accounting, Auditing": "会计/审计",
        "Instruments and Meters & Industrial Automation": "仪器仪表/工业自动化",
        "Foreign Comp.(Others)": "外资（非欧美）",
        "Supplies & Equipment Quality Management": "供应品及设备质量管理",
        "Full-time": "全职",
        "Purchaser": "采购员",
        "Purchasing Specialist": "采购专员",
        "Sales Administrator": "销售管理员",
        "Auto and accessory industry": "汽车及零部件行业",
        "JLPT Level 1": "日语能力考试一级",
        "TOEFL 84": "托福84分",
        "Educational Experience": "教育经历",
        "New Workflow": "新工作流程",
        "FPC PCB": "柔性印制电路板",
        "Mazda Motor(China)Co.,LTD": "马自达汽车（中国）有限公司",
        "Muto-Fonstar": "武藤方达科技（苏州）有限公司",
        "ITOCHU TEXTILE(CHINA)CO.,LTD.": "伊藤忠纤维（中国）有限公司",
        "ADC International Transportation Co,Ltd": "ADC国际运输有限公司",
        "Beijing Kintetsu World Express co.ltd.": "北京近铁运通运输有限公司",
        "Beiqi Foton Motor Co., Ltd.": "北汽福田汽车股份有限公司",
        "Borui": "博瑞",
        "Borui Individualized        Education": "博瑞个性化教育",
        "Chongqing Huansong Industry (Group) Co., Ltd.": "重庆环松工业（集团）有限公司",
        "Ethypharm pharmaceutical Co Ltd": "爱地法玛制药有限公司",
        "Fujian Quanzhou Shunmei Group （Large Factory）": "福建泉州顺美集团",
        "FUJITSU CHINA HOLDINGS CO.,LTD.": "富士通（中国）信息系统有限公司",
        "Fuzhou Hersheen Auto Parts Co., Ltd. (South East Motor City)": "福州和胜汽车配件有限公司",
        "Gplusmedia.co,ltd": "GPlusMedia有限公司",
        "Gresso": "格莱索",
        "Hygiena (Shanghai) Trading Co. Ltd.": "海洁纳（上海）贸易有限公司",
        "Kunshan Juli Packaging Material Technology Co., Ltd.": "昆山聚力包装材料科技有限公司",
        "Lanso Konly (Shanghai) Instruments Co., Ltd.": "兰宝科利（上海）仪器有限公司",
        "MITSUBISHI MOTORS(CHINA)CO.,LTD.": "三菱汽车（中国）有限公司",
        "pegatron": "和硕联合科技",
        "pet your pets": "宠爱宠物",
        "ProChinaDirect Co.,Ltd": "中国直达有限公司",
        "ROE, wujiang.Co,Ltd.": "华映视讯（吴江）有限公司",
        "SGS-CSTC Standards Technical Services Co., Ltd.": "通标标准技术服务有限公司",
        "Shanghai Baosteel & Arcelor Tailor Metal Co., Ltd.": "上海宝钢阿赛洛激光拼焊有限公司",
        "Shanghai Baosteel&Arcelor Tailor Metal Co.,Ltd.": "上海宝钢阿赛洛激光拼焊有限公司",
        "Shanghai Good Future Garment Co.,Ltd": "上海好未来服装有限公司",
        "Shanghai institute of biological products co,Ltd.": "上海生物制品研究所有限责任公司",
        "Shanghai JinDa Customs Broker Co, Ltd": "上海金达报关有限公司",
        "Shanghai Mecoxlane Mailorder Company": "上海麦考林国际邮购有限公司",
        "Shanghai SANJI Die Casting Machinery Co., Ltd": "上海三基压铸机械有限公司",
        "Shanghai Shenhuo Aluminium Foil Co., Ltd": "上海神火铝箔有限公司",
        "Shanghai Shubufei Trading Co.,Ltd": "上海舒步飞贸易有限公司",
        "Shanghai Tsuchiya Accounting Firm": "上海土屋会计师事务所",
        "Shanghai Zenith Mining and Construction Machinery Co., Ltd": "上海世邦矿山工程机械有限公司",
        "Sino-American Shanghai Squibb Pharmaceuticals": "中美上海施贵宝制药有限公司",
        "Sinorefine        Corporation": "中精公司",
        "Suntor & Blooming Holdings (H.K) Ltd": "新德与博明控股（香港）有限公司",
        "Target Sourcing Services/AMC": "塔吉特采购服务公司/AMC",
        "TimeAsset": "时代资产",
        "TSMT, wujiang.Co. Ltd.": "台表科技（吴江）有限公司",
        "TutorABC": "TutorABC在线教育",
        "VIPABC": "VIPABC在线教育",
        "WUXI AITE Micro-Electronics Ltd.": "无锡爱特微电子有限公司",
        "Wuyang-Honda Motorcycle (Guangzhou) Co., Ltd.": "五羊—本田摩托（广州）有限公司",
        "Xiamen Lucky Gifts Co.,Ltd": "厦门吉祥礼品有限公司",
        "YAZAKI(CHINA)INVESTMENT CORPORATION": "矢崎（中国）投资有限公司",
        "Zhejiang Jiaxing Min Hui Auto Parts Co., Ltd.": "浙江嘉兴敏惠汽车零部件有限公司",
        "Shanghai Chengxin College": "上海诚信学院",
        "Shanghai International Studies University": "上海外国语大学",
        "Shanghai Lixin University of Accounting": "上海立信会计学院",
        "Shanghai Maritime University": "上海海事大学",
        "Shanghai Ocean University": "上海海洋大学",
        "Shanghai RongChen Driving School": "上海荣臣驾校",
        "Shanghai University": "上海大学",
        "Shanghai University of Finance and Economics": "上海财经大学",
        "Sanda University": "上海杉达学院",
        "Southwest Jiaotong University": "西南交通大学",
        "University of Science and Technology Liaoning": "辽宁科技大学",
        "University of Tsukuba": "筑波大学",
        "Zhejiang Gongshang University": "浙江工商大学",
        "Changzhou University": "常州大学",
        "chongqing jiaotong university": "重庆交通大学",
        "Huainan Normal University": "淮南师范学院",
        "Informatics College": "信息学院",
        "Jiangsu SuQian middle school": "江苏省宿迁中学",
        "JTB Travel & Hotel College": "JTB旅游酒店学院",
        "Canon imageWARE Enterprise Management Console": "佳能imageWARE企业管理控制台",
        "Jilin Huaqiao University of Foreign": "吉林华桥外国语学院",
        "Shengda Trade Economics & Management College of Zhengzhou |": "郑州升达经贸管理学院",
        "Shanghai University of": "上海大学",
        "University of": "大学",
        "ウィクレソフトジェパン": "微创软件日本公司",
        "システィマティクス": "Systematics公司",
        "ジョイン（JOIN）": "JOIN公司",
        "すごいプロモーション（sugoi   promotion）": "Sugoi Promotion公司",
        ", Fujian Quanzhou Normal University , English , Bachelor": "福建泉州师范学院",
        ", Henan University of Finance and Economy , English , Bachelor": "河南财经大学",
    }
    replacements = {**common_replacements, **replacements}

    def replace(value: Any) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if isinstance(child, str) and child in replacements:
                    value[key] = replacements[child]
                    tracker["source_verified_proper_nouns_translated"] += 1
                else:
                    replace(child)
        elif isinstance(value, list):
            for child in value:
                replace(child)

    replace(primary)
    for resume in resumes:
        for field in ("training_list", "project_list"):
            for sequence, item in enumerate(resume[field], 1):
                item["sequence_no"] = sequence


def align_primary_lists_from_richer_foreign(resumes: list[dict[str, Any]], tracker: Counter[str]) -> None:
    """Use a richer preserved source-language list to rebuild its Chinese peer."""
    if len(resumes) < 2:
        return
    primary = resumes[0]
    foreign_candidates = [resume for resume in resumes[1:] if resume.get("resume_languge") in {"en", "jp", "de"}]
    if not foreign_candidates:
        return
    for list_name in ("expected_list", "work_experiences", "education_list", "certificate_list", "language_list", "skills_list", "training_list", "project_list"):
        richest = max(foreign_candidates, key=lambda resume: len(resume.get(list_name) or []))
        foreign_count = len(richest.get(list_name) or [])
        primary_count = len(primary.get(list_name) or [])
        if foreign_count <= primary_count:
            continue
        primary[list_name] = copy.deepcopy(richest[list_name])
        if list_name in {"training_list", "project_list"}:
            for sequence, item in enumerate(primary[list_name], 1):
                item["sequence_no"] = sequence
        tracker[f"primary_{list_name}_rebuilt_from_richer_foreign"] += 1


def strict_resume(value: Any, tracker: Counter[str], index: int) -> dict[str, Any]:
    resume = strict_object(value, RESUME, tracker, "resume")
    resume["resume_languge"] = str(resume.get("resume_languge") or "").strip()
    resume["base_info"] = strict_object(resume.get("base_info"), BASE, tracker, "resume.base_info")
    for list_name, item_keys in ITEMS.items():
        raw_items = resume.get(list_name)
        if not isinstance(raw_items, list):
            raw_items = []
            tracker["non_array_lists_repaired"] += 1
        clean_items = [strict_object(item, item_keys, tracker, f"resume.{list_name}") for item in raw_items if isinstance(item, dict)]
        if list_name in {"training_list", "project_list"}:
            for sequence, item in enumerate(clean_items, 1):
                if item.get("sequence_no") != sequence:
                    tracker["sequence_numbers_repaired"] += 1
                item["sequence_no"] = sequence
        resume[list_name] = clean_items
    if index in KNOWN_SOURCE_NAMES and (str(resume["base_info"].get("full_name") or "").strip() in PLACEHOLDER_NAMES or str(resume["base_info"].get("full_name") or "").startswith("待确认姓名_")):
        resume["base_info"]["full_name"] = KNOWN_SOURCE_NAMES[index]
        tracker["names_recovered_from_source"] += 1
    for education in resume["education_list"]:
        for key in ("school_name", "school_major_name", "school_degree_type"):
            old = str(education.get(key) or "").strip()
            new = re.sub(r"^(?:学校|院校|专业|学历|学位|Major|Degree)\s*[：:]\s*", "", old, flags=re.I).strip()
            if new != old:
                education[key] = new
                tracker["education_labels_removed"] += 1
    before = [str(item.get("position_start") or "") for item in resume["work_experiences"]]
    resume["work_experiences"] = sorted(resume["work_experiences"], key=lambda item: date_key(item.get("position_start")), reverse=True)
    after = [str(item.get("position_start") or "") for item in resume["work_experiences"]]
    if before != after:
        tracker["work_lists_reordered"] += 1
    return resume


def clear_reviewed_unsupported_values(payload: dict[str, Any], issues: list[dict[str, Any]], tracker: Counter[str]) -> int:
    resumes = ((payload.get("structured_data") or {}).get("resumes") or [])
    cleared = 0
    for issue in issues:
        if issue.get("code") != "structured_value_missing_from_source":
            continue
        for sample in issue.get("samples") or []:
            path = str(sample.get("path") or "")
            tokens: list[str | int] = []
            for part in re.finditer(r"(?:^|\.)([A-Za-z_][A-Za-z0-9_]*)|\[(\d+)\]", path):
                tokens.append(int(part.group(2)) if part.group(2) is not None else str(part.group(1)))
            target: Any = resumes
            try:
                for token in tokens[:-1]:
                    target = target[token]
                final = tokens[-1]
                if isinstance(target, (dict, list)) and target[final] not in (None, ""):
                    target[final] = ""
                    cleared += 1
            except (KeyError, IndexError, TypeError):
                continue
    if cleared:
        tracker["source_unsupported_generated_values_cleared"] += cleared
    return cleared


def repair_payload(payload: dict[str, Any], record: dict[str, Any], reviewer: Any, converter: Any) -> tuple[dict[str, Any], Counter[str], list[dict[str, str]], str]:
    tracker: Counter[str] = Counter()
    unresolved: list[dict[str, str]] = []
    source = Path(str(record.get("source_path") or ""))
    stage = Path(str(record.get("stage_path") or record.get("html_path") or ""))
    plain_path = stage if stage.is_file() else source
    plain = reviewer.source_plain(plain_path) if plain_path.is_file() and plain_path.stat().st_size else ""
    result = strict_object(payload, TOP, tracker, "top")
    result["source"] = strict_object(result.get("source"), SOURCE, tracker, "source")
    result["dates"] = strict_object(result.get("dates"), DATES, tracker, "dates")
    result["extraction"] = strict_object(result.get("extraction"), EXTRACTION, tracker, "extraction", {"dom": {}})
    if not isinstance(result["extraction"].get("dom"), dict):
        result["extraction"]["dom"] = {}
    result["classification"] = strict_object(result.get("classification"), CLASSIFICATION, tracker, "classification")
    structured = strict_object(result.get("structured_data"), SD, tracker, "structured_data")
    raw_resumes = structured.get("resumes") if isinstance(structured.get("resumes"), list) else []
    resumes = [strict_resume(item, tracker, int(record.get("index") or 0)) for item in raw_resumes if isinstance(item, dict)]
    record_index = int(record.get("index") or 0)
    if record_index in VERIFIED_NAME_REPAIRS:
        verified_name = VERIFIED_NAME_REPAIRS[record_index]
        for resume in resumes:
            if str(resume["base_info"].get("full_name") or "").strip() != verified_name:
                resume["base_info"]["full_name"] = verified_name
                tracker["source_verified_names_repaired"] += 1
    if resumes:
        zh_positions = [i for i, item in enumerate(resumes) if item.get("resume_languge") == "zh"]
        if zh_positions and zh_positions[0] != 0:
            resumes.insert(0, resumes.pop(zh_positions[0]))
            tracker["primary_zh_reordered"] += 1
    repair_resume_language_versions(resumes, tracker, plain)
    recover_missing_sections_from_plain(resumes, plain, converter, tracker)
    normalize_dates(resumes, tracker, unresolved, "structured_data.resumes")
    apply_source_evidence_repairs(resumes, record_index, tracker)
    # Recompute unresolved dates after source-evidence corrections/removals so
    # the report reflects the final payload rather than the pre-repair state.
    unresolved.clear()
    normalize_dates(resumes, tracker, unresolved, "structured_data.resumes")
    repair_section_spillover(resumes, plain, tracker)
    apply_targeted_work_repairs(resumes, record_index, tracker)
    repair_education_semantics(resumes, tracker)
    repair_noncore_and_semantic_lists(resumes, tracker)
    apply_strict_semantic_targeted_repairs(resumes, record_index, tracker)
    align_primary_lists_from_richer_foreign(resumes, tracker)
    apply_verified_multilingual_translations(resumes, record_index, tracker)
    for resume in resumes:
        before = [str(item.get("position_start") or "") for item in resume["work_experiences"]]
        resume["work_experiences"] = sorted(
            resume["work_experiences"],
            key=lambda item: date_key(item.get("position_start")),
            reverse=True,
        )
        after = [str(item.get("position_start") or "") for item in resume["work_experiences"]]
        if before != after:
            tracker["work_lists_reordered"] += 1
    empty_expected = {key: "" for key in EXPECTED}
    empty_current = {key: ("全职" if key == "employment_type" else "") for key in CURRENT}
    empty_education = {key: "" for key in EDUCATION}
    if resumes:
        primary = resumes[0]
        structured["base_info"] = copy.deepcopy(primary["base_info"])
        structured["expected_info"] = copy.deepcopy(primary["expected_list"][0] if primary["expected_list"] else empty_expected)
        structured["current_info"] = copy.deepcopy({key: primary["work_experiences"][0].get(key, "") for key in CURRENT} if primary["work_experiences"] else empty_current)
        best_education = max(primary["education_list"], key=degree_score, default=None)
        structured["education_info"] = copy.deepcopy({key: best_education.get(key, "") for key in EDUCATION} if best_education else empty_education)
    else:
        structured["base_info"] = strict_object(structured.get("base_info"), BASE, tracker, "structured_data.base_info")
        structured["expected_info"] = strict_object(structured.get("expected_info"), EXPECTED, tracker, "structured_data.expected_info")
        structured["current_info"] = strict_object(structured.get("current_info"), CURRENT, tracker, "structured_data.current_info", {"employment_type": "全职"})
        structured["education_info"] = strict_object(structured.get("education_info"), EDUCATION, tracker, "structured_data.education_info")
    structured["resumes"] = resumes
    result["structured_data"] = structured
    new_raw = raw_text_from_resumes(resumes)
    if result.get("raw_text") != new_raw:
        tracker["raw_text_rebuilt"] += 1
    result["raw_text"] = new_raw
    quality = result.get("quality") if isinstance(result.get("quality"), dict) else {}
    result["quality"] = quality
    quality["raw_text_length"] = len(new_raw)

    reconciliation = quality.get("reconciliation") if isinstance(quality.get("reconciliation"), dict) else {}
    for bulky_key in ("rounds", "repair_history"):
        if bulky_key in reconciliation:
            reconciliation.pop(bulky_key, None)
            tracker[f"embedded_{bulky_key}_removed"] += 1
    quality["reconciliation"] = reconciliation
    return result, tracker, unresolved, plain


def main() -> int:
    args = parse_args()
    started_at = datetime.now().astimezone().isoformat(timespec="seconds")
    reviewer = load_reviewer()
    converter = load_converter()
    map_payload = json.loads(args.map.read_text(encoding="utf-8"))
    records = map_payload.get("records", []) if isinstance(map_payload, dict) else []
    old_review = json.loads(args.review.read_text(encoding="utf-8")) if args.review.is_file() else {}
    before_by_index = {int(item.get("index") or 0): item.get("issues", []) for item in old_review.get("items", []) if isinstance(item, dict)}
    report_items: list[dict[str, Any]] = []
    status_counts: Counter[str] = Counter()
    fix_counts: Counter[str] = Counter()
    remaining_counts: Counter[str] = Counter()
    cumulative_fix_counts: Counter[str] = Counter()

    for record in records:
        index = int(record.get("index") or 0)
        source = Path(str(record.get("source_path") or ""))
        stage = Path(str(record.get("stage_path") or record.get("html_path") or ""))
        json_value = str(record.get("json_path") or "")
        json_path = Path(json_value) if json_value else None
        previous_status = str(record.get("status") or "")
        before = before_by_index.get(index, [])
        before_codes = sorted({str(item.get("code") or "") for item in before if isinstance(item, dict)})
        item: dict[str, Any] = {
            "index": index,
            "source_path": str(source),
            "stage_path": str(stage),
            "json_path": str(json_path or ""),
            "previous_status": previous_status,
            "issues_before": before_codes,
            "changed": False,
            "fixes_applied": {},
            "remaining_issues": [],
        }
        if source.is_file():
            digest = sha256(source)
            record["source_hash"] = digest
            item["source_sha256"] = digest
        if json_path is None or not json_path.is_file():
            if previous_status in EXPECTED_NO_JSON or (previous_status == "failed" and (not source.is_file() or source.stat().st_size == 0)):
                status = "no_json_expected" if previous_status != "failed" else "failed"
            else:
                status = "failed"
            remaining = [] if status == "no_json_expected" else [{"code": "json_missing_or_source_unusable", "severity": "high"}]
            item["status"] = status
            item["remaining_issues"] = remaining
        else:
            try:
                original_text = json_path.read_text(encoding="utf-8")
                payload = json.loads(original_text)
                if not isinstance(payload, dict):
                    raise ValueError("root JSON 不是对象")
                repaired, tracker, unresolved, plain = repair_payload(payload, record, reviewer, converter)
                remaining = reviewer.review_payload(repaired, record, json_path, plain) + unresolved
                if clear_reviewed_unsupported_values(repaired, remaining, tracker):
                    repaired_again, second_tracker, unresolved, plain = repair_payload(repaired, record, reviewer, converter)
                    tracker.update(second_tracker)
                    repaired = repaired_again
                    remaining = reviewer.review_payload(repaired, record, json_path, plain) + unresolved
                checked_at = datetime.now().astimezone().isoformat(timespec="seconds")
                quality = repaired["quality"]
                reconciliation = quality.get("reconciliation") if isinstance(quality.get("reconciliation"), dict) else {}
                repair_entry = {
                    "status": "applied",
                    "applied_at": checked_at,
                    "method": "schema_strict_source_evidence_incremental_repair",
                    "issue_codes_before": before_codes,
                    "fixes_applied": dict(tracker),
                }
                round_entry = {
                    "round": int(reconciliation.get("round") or 0) + 1,
                    "phase": "full_repair_recheck",
                    "checked_at": checked_at,
                    "issue_count": len(remaining),
                    "issues": copy.deepcopy(remaining),
                }
                reconciliation.update({
                    "status": "clean" if not remaining else "issues",
                    "clean_mark": not remaining,
                    "round": round_entry["round"],
                    "checked_at": checked_at,
                    "issue_count": len(remaining),
                    "issues": copy.deepcopy(remaining),
                })
                quality["reconciliation"] = reconciliation
                status = "repaired" if not remaining and (tracker or before_codes) else ("clean" if not remaining else "needs_review")
                quality["full_repair"] = {
                    "status": status,
                    "checked_at": checked_at,
                    "fixes_applied": dict(tracker),
                    "remaining_issue_codes": sorted({str(issue.get("code") or "") for issue in remaining}),
                }
                repaired_text = json.dumps(repaired, ensure_ascii=False, indent=2)
                atomic_json(json_path, repaired)
                item.update({
                    "status": status,
                    "changed": repaired_text != original_text,
                    "fixes_applied": dict(tracker),
                    "remaining_issues": remaining,
                    "repair_round": {"repair": repair_entry, "review": round_entry},
                })
                fix_counts.update(tracker)
                cumulative_fix_counts.update(tracker)
            except Exception as exc:
                item["status"] = "failed"
                item["remaining_issues"] = [{"code": "repair_failed", "severity": "high", "error": str(exc)}]
        status_counts[item["status"]] += 1
        for issue in item["remaining_issues"]:
            remaining_counts[str(issue.get("code") or "unknown")] += 1
        record["full_repair_status"] = item["status"]
        record["full_repair_fixes"] = item["fixes_applied"]
        record["full_repair_remaining_issue_codes"] = sorted({str(issue.get("code") or "") for issue in item["remaining_issues"]})
        record["full_repaired_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
        report_items.append(item)

    completed_at = datetime.now().astimezone().isoformat(timespec="seconds")
    report = {
        "report_version": "web-full-repair-v2",
        "mode": "in_place_incremental",
        "started_at": started_at,
        "completed_at": completed_at,
        "map_path": str(args.map.resolve()),
        "status_definitions": {
            "clean": "JSON 核对无问题且本轮没有确定性修复",
            "repaired": "确定性问题已修复且复核无剩余问题",
            "needs_review": "已完成确定性修复，但仍有不能凭源文件自动判定的问题",
            "no_json_expected": "按分类结果明确无需生成 JSON",
            "failed": "源文件/JSON 缺失、为空或修复异常",
        },
        "summary": {
            "records_total": len(report_items),
            "json_records": sum(1 for item in report_items if item["json_path"]),
            "status_counts": dict(status_counts),
            "fix_counts": dict(fix_counts.most_common()),
            "cumulative_unique_fix_counts_from_json_history": dict(cumulative_fix_counts.most_common()),
            "remaining_issue_counts": dict(remaining_counts.most_common()),
        },
        "items": report_items,
    }
    map_payload["last_full_repair_report"] = str(args.report.resolve())
    map_payload["last_full_repaired_at"] = completed_at
    atomic_json(args.map, map_payload)
    atomic_json(args.report, report)
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
