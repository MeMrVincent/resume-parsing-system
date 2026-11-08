from __future__ import annotations
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1] / "common"))
import rc_config as _rc  # noqa: E402  项目统一配置（python/common/rc_config.py）
# EN: noqa: E402  project-wide configuration (python/common/rc_config.py)
# JA: noqa: E402  プロジェクト共通設定（python/common/rc_config.py）

import argparse
import copy
import html
import json
import re
import tempfile
import unicodedata
import zipfile
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

try:
    import fitz
except ImportError:  # pragma: no cover
    fitz = None

from pdf_raw_text_v2 import (
    build_source_text_index,
    detect_document_type,
    detect_resume_languages,
    payload_raw_text,
)


PROJECT_ROOT = _rc.project_root()
PDF_ROOT = PROJECT_ROOT / _rc.dirname("complete-transfered-htmls") / "pdf"
DEFAULT_ROOT = PDF_ROOT / "rebuild-work" / "json-by-candidate"
DEFAULT_MAP = PDF_ROOT / "rebuild-work" / "pdf_rebuild_map.v2.json"
DEFAULT_OVERRIDES = PDF_ROOT / "rebuild-reports" / "pdf_semantic_overrides.v2.json"
DEFAULT_REPORT = PDF_ROOT / "rebuild-reports" / "pdf_semantic_repair.v2.json"
VERSION = "pdf-rebuild-semantic-repair-v2.0.0"
W_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

RESUME_LISTS = (
    "expected_list", "work_experiences", "education_list", "certificate_list",
    "language_list", "skills_list", "training_list", "project_list", "communication_list",
)
BASE_FIELDS = (
    "full_name", "gender", "age", "birth_date", "birth_year", "marital_status",
    "children_status", "political_status", "height_cm", "weight_kg",
    "household_registration", "address", "postal_code", "platform_from",
    "platform_resume_id", "phone", "email", "city", "nationality", "pr",
)
EXPECTED_FIELDS = (
    "expected_city", "expected_position", "expected_salary",
    "expected_annual_salary_min", "expected_annual_salary_max", "expected_industry",
    "expected_employment_type", "expected_start_date",
)
WORK_FIELDS = (
    "company_name", "company_employees", "company_industry", "position", "position_type",
    "position_salary", "position_dept", "position_report_to", "position_subordinate",
    "employment_type", "annual_salary_min", "annual_salary_max", "status", "position_start",
    "position_resigned", "resigned_reason", "position_responsibilities", "position_achievements",
)
CURRENT_FIELDS = WORK_FIELDS[:15]
EDU_FIELDS = (
    "school_name", "school_major_name", "school_degree_type", "school_degree_rank",
    "school_education_type", "school_start_ym", "school_end_ym",
)
PROJECT_FIELDS = (
    "sequence_no", "fingerprint", "project_name", "company_or_client", "role_name",
    "start_ym", "end_ym", "description", "responsibilities", "achievements", "keywords",
)
TRAINING_FIELDS = (
    "sequence_no", "organization_name", "training_name", "start_ym", "end_ym",
    "certificate_name", "description",
)
CERTIFICATE_FIELDS = ("certificate_name", "certificate_type", "certificate_time")
LANGUAGE_FIELDS = ("language_name", "language_level", "language_certificate", "language_certificate_time")
SKILL_FIELDS = ("skill_name", "skill_level")
COMMUNICATION_FIELDS = ("communicate_time", "communicate_content")
COLLECTION_FIELDS = {
    "expected_list": EXPECTED_FIELDS,
    "work_experiences": WORK_FIELDS,
    "education_list": EDU_FIELDS,
    "certificate_list": CERTIFICATE_FIELDS,
    "language_list": LANGUAGE_FIELDS,
    "skills_list": SKILL_FIELDS,
    "training_list": TRAINING_FIELDS,
    "project_list": PROJECT_FIELDS,
    "communication_list": COMMUNICATION_FIELDS,
}
COLLECTION_ALIGNMENT = {
    "work_experiences": (WORK_FIELDS, "company_name", "position_start", "position_resigned"),
    "education_list": (EDU_FIELDS, "school_name", "school_start_ym", "school_end_ym"),
    "project_list": (PROJECT_FIELDS, "project_name", "start_ym", "end_ym"),
    "training_list": (TRAINING_FIELDS, "training_name", "start_ym", "end_ym"),
}

HTML_RE = re.compile(r"</?[a-z][^>]*(?:>|$)|data-[a-z-]+\s*=|&(?:nbsp|lt|gt|amp);", re.I)
COMPANY_RE = re.compile(
    r"有限公司|有限责任公司|股份有限公司|株式会社|有限会社|会社|公司|"
    r"\b(?:Co\.?\s*,?\s*Ltd\.?|Co\.?|Ltd\.?|Inc\.?|Corp\.?|Corporation|Company|GmbH|AG)\b",
    re.I,
)
SCHOOL_RE = re.compile(
    r"大学|学院|学校|高校|中学|研究科|研究院|University|College|School|Institute|Academy|"
    r"Université|Universität",
    re.I,
)
DEGREE_RE = re.compile(r"专业|本科|硕士|博士|学士|修士|学部|学科|専攻|Bachelor|Master|Ph\.?D|Major", re.I)
PLACEHOLDER_RE = re.compile(
    r"^(?:公司名(?:称)?|会社名|学校名|school|company|毕业|卒業|离职原因|退職理由|履歴書|"
    r"職歴|学歴|工作经历|教育经历|部门|部署|所属|职位|職位|役職|Principal|Post/Wages|"
    r"School Honors|Graduate Info\.?|学校|高校|専門学校|大学|学院|卒業学校|大学学士|年|担当|職種|～|-|—|\d{1,2})$",
    re.I,
)
GENERIC_NAME_RE = re.compile(
    r"履歴書|職務経歴書|简历|resume|curriculum|vitae|日文|中文|英文|基本情報|个人资料|"
    r"Akademische Laufbahn|待确认|未知|看图王|WPS|Microsoft Word|PDF|^(?:ふりがな|フリガナ|氏名|姓名|name)$",
    re.I,
)
DATE_TOKEN_RE = re.compile(
    r"(?P<year>(?:19|20)\d{2})\s*(?:年|[./\-])?\s*(?P<month>1[0-2]|0?[1-9])?\s*(?:月|[./\-])?\s*(?P<day>[0-3]?\d)?\s*日?"
)
PRESENT_RE = re.compile(r"至今|现在|目前|現今|現在|Present|Current|Now|heute", re.I)
SCHOOL_NOISE_RE = re.compile(r"工作经历|仕事内容|项目|奖学金|奨学金|荣誉|受賞|求职|期望|职责|负责|自我评价|EDUCATION|career|WordOOXMLTable|OpenXMLTable|"
                             r"大学英语|大学英語|CET[- ]?[46]|TOEFL|IELTS|JLPT|技能证书|資格|学校名称|大学主修课程|"
                             r"大学を卒業してから|講師として|働き", re.I)
COMPANY_NOISE_RE = re.compile(
    r"履歴書|退職理由|证书|学历|毕业|卒業|入学|毕业设计|研究生毕业|职责|负责|带领|保证|外派|工作属性|"
    r"产品团队|客户|职位|岗位|工作经历|公司业务范围|公司性质|所在公司|任职公司|此时公司|受上级单位|发表论文|"
    r"项目描述|项目职责|项目总负责|Scholarship|Prize|Competition|竞赛|大赛|WordOOXMLTable|OpenXMLTable",
    re.I,
)
ENTITY_PLACEHOLDER_RE = re.compile(
    r"^(?:公司名(?:称)?|会社名|公司|会社|Company|单位|学校名|学校|School|大学|学院|高校|専門学校|职位|职务|職種|担当|"
    r"专业|専攻|学歴|職歴|工作经历|教育经历|项目经历|项目|培训经历|培训|证书|資格|年|月|日|至今|现在|"
    r"公司业务范围|公司性质|所在公司|任职公司|此时公司|学校名称|大学主修课程|大学英语(?:四|六)级|专业\s*[：:]?.*|"
    r"无|暂无|N/?A|看图王|WPS|Word|PDF|messag(?:e)?|Skill|Company Rotation Learning|Oct\.?|Jun\.?|正社員|契約社員|派遣社員|アルバイト|"
    r"\[?\d+(?:年|个月|か月|ヶ月)\]?|\d{1,2}\s*月|[-—–~～]+)$",
    re.I,
)
FIELD_LABEL_RE = re.compile(
    r"(?:公司名|会社名|学校名|职位|职务|職種|工作描述|工作职责|项目描述|项目职责|离职原因|退職理由|"
    r"姓名|氏名|电话|電話|手机|携帯|邮箱|E-?mail|出生日期|生年月日|婚姻状况|求职意向|出資状況|業界|社員数)\s*[：:]",
    re.I,
)
SENTENCE_ENTITY_RE = re.compile(
    r"^(?:本人|自我|希望|能够|具有|负责|主要负责|参与|协助|并作为|对集团|主修课程|技术部|设备|项目业绩|"
    r"大学を卒業|働き|担当業務|仕事内容|業務内容)\s*[：:]?",
    re.I,
)
SUSPICIOUS_COMPANY_START_RE = re.compile(
    r"^(?:[●•◆■]+\s*|[（(]?[一二三四五六七八九十\d]+[）).、]\s*)|"
    r"^(?:(?:19|20)\d{2}\s*(?:年\s*\d{1,2}\s*月|[./-]\s*\d{1,2})|"
    r"\d{1,2}[./]\d{2,4}|月\s*[～~-]?|公司业务范围|公司性质|所在公司|任职公司|此时公司|受上级单位|"
    r"专业\s*[：:]|至今|現在|WordOOXML|\d{1,2}:\d{2}:\d{2}|Position\s*[：:])",
    re.I,
)
SUSPICIOUS_SCHOOL_START_RE = re.compile(
    r"^(?:[●•◆■]+\s*|(?:19|20)?\d{1,4}[./]\d{1,2}\s*|\d{1,2}\.\d{2,4}\s*|"
    r"学校名(?:称)?\s*[：:]?|学历\s*[：:（(]?|专业\s*[：:]|大学英语|大学英語|大学主修课程|类化合物)",
    re.I,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="修复 PDF v2 候选人 JSON 中可确定的字段边界和错分问题" " / Repair determinable field-boundary and misclassification problems in PDF v2 candidate JSON / PDF v2 の候補者 JSON で確定できるフィールドの境界・取り違えの問題を修復する")
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--map", type=Path, default=DEFAULT_MAP)
    parser.add_argument("--overrides", type=Path, default=DEFAULT_OVERRIDES)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--apply", action="store_true")
    return parser.parse_args()


def text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def compact(value: Any) -> str:
    value = unicodedata.normalize("NFKC", text(value)).casefold()
    return re.sub(r"[^0-9a-z\u3400-\u9fff\u3040-\u30ff]", "", value)


def clean_email(value: Any) -> str:
    value = unicodedata.normalize("NFKC", text(value)).replace(" ", "")
    if not value or value.casefold() in {"不公开", "非公開", "none", "n/a"}:
        return ""
    # Prefer a complete address ending at a known public suffix. This prevents
    # adjacent OCR text (for example "@qq.comsalesvolume") from becoming part
    # of the email, and trims phone/e-mail labels concatenated before it.
    matches = re.findall(
        r"[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.(?:com\.cn|net\.cn|org\.cn|co\.jp|co\.uk|com|net|org|edu|gov|cn|jp|de|fr|io|me)",
        value,
        re.I,
    )
    if not matches:
        return ""
    candidate = matches[-1]
    candidate = re.sub(r"^.*?(?:e-?mail[:：]?)", "", candidate, flags=re.I)
    if candidate.startswith("_") or "*" in candidate:
        return ""
    return candidate


def clean_nationality(value: Any) -> str:
    current = text(value)
    if not current:
        return ""
    aliases = (
        (r"中国|中华人民共和国|China|Chinese", "中国"),
        (r"日本|Japan|Japanese", "日本"),
        (r"韩国|韓国|Korea|Korean", "韩国"),
        (r"美国|米国|USA|U\.S\.|American", "美国"),
        (r"加拿大|Canada|Canadian", "加拿大"),
        (r"英国|UK|British", "英国"),
        (r"法国|France|French", "法国"),
        (r"德国|Germany|German", "德国"),
        (r"俄罗斯|Russia|Russian", "俄罗斯"),
        (r"澳大利亚|Australia|Australian", "澳大利亚"),
        (r"新加坡|Singapore|Singaporean", "新加坡"),
    )
    for pattern, canonical in aliases:
        if re.search(pattern, current, re.I):
            return canonical
    return ""


def clean_numeric_text(value: Any, *, minimum: float = 0, maximum: float = 1000) -> str:
    current = unicodedata.normalize("NFKC", text(value))
    match = re.search(r"\d+(?:\.\d+)?", current)
    if not match:
        return ""
    number = float(match.group())
    if not minimum <= number <= maximum:
        return ""
    return str(int(number)) if number.is_integer() else str(number)


def strip_markup(value: Any) -> str:
    value = unicodedata.normalize("NFKC", str(value or ""))
    if not value:
        return ""
    value = re.sub(r"<script\b[^>]*>.*?</script>|<style\b[^>]*>.*?</style>", " ", value, flags=re.I | re.S)
    value = re.sub(r"<[^>]*(?:>|$)", "\n", value)
    value = re.sub(r"\b(?:data-[a-z-]+|label)\s*=\s*[\"'][^\"']*[\"']", " ", value, flags=re.I)
    value = re.sub(r"\b(?:data-[a-z-]+|label)\s*=\s*[^\s>]+", " ", value, flags=re.I)
    value = value.replace(">", " ")
    value = html.unescape(value)
    return re.sub(r"\s+", " ", value).strip(" \t\r\n|｜:：,，;；")


def scrub_tree(value: Any, normalize_text: bool = False) -> Any:
    if isinstance(value, dict):
        return {key: scrub_tree(child, normalize_text) for key, child in value.items()}
    if isinstance(value, list):
        return [scrub_tree(child, normalize_text) for child in value]
    if isinstance(value, str) and HTML_RE.search(value):
        return strip_markup(value)
    if isinstance(value, str) and normalize_text:
        normalized = unicodedata.normalize("NFKC", value)
        controls = sum(
            ord(char) < 32 and char not in "\r\n\t" or 0x7F <= ord(char) <= 0x9F or unicodedata.category(char) == "Cf"
            for char in normalized
        )
        unusual = sum(
            ord(char) > 255
            and not re.match(r"[\u3000-\u30ff\u3400-\u9fff]", char)
            and unicodedata.category(char)[0] not in {"P", "Z", "N"}
            for char in normalized
        )
        visible = max(1, sum(not char.isspace() for char in normalized))
        if controls >= 3 and unusual / visible >= 0.06:
            return ""
        normalized = "".join(
            " " if (ord(char) < 32 and char not in "\r\n\t") or 0x7F <= ord(char) <= 0x9F or unicodedata.category(char) == "Cf" else char
            for char in normalized
        )
        normalized = normalized.replace("\ufffd", " ")
        normalized = re.sub(r"(?:WordOOXMLTable|OpenXMLTable)\s*\d*", " ", normalized, flags=re.I)
        return re.sub(r"[ \t]+", " ", normalized).strip()
    return value


def clean_pr(value: Any, counters: Counter[str]) -> str:
    current = unicodedata.normalize("NFKC", str(value or "")).strip()
    if not current:
        return ""
    if current.count("Ì") >= 2 or len(re.findall(r"[�□■]", current)) >= 2:
        counters["clear_garbled_pr"] += 1
        return ""
    if re.search(r"WordOOXMLTable|OpenXMLTable", current, re.I):
        prefix = re.split(r"WordOOXMLTable|OpenXMLTable", current, maxsplit=1, flags=re.I)[0]
        if re.search(r"<例>|经验年数|業務範囲|会社名称|時間\s*会社", prefix, re.I):
            counters["clear_template_pr"] += 1
            return ""
        evaluation = re.search(r"(?:自我评价|自己評価|評価)\s*[：:]?\s*(.+)$", prefix, re.I | re.S)
        if evaluation and len(compact(evaluation.group(1))) >= 12:
            counters["extract_pr_before_table_dump"] += 1
            return text(evaluation.group(1))
        counters["clear_table_dump_pr"] += 1
        return ""
    if re.search(r"フリガナ|学歴・資格|希望職種\s*勤務可能日", current):
        counters["clear_table_dump_pr"] += 1
        return ""
    boundary = re.search(
        r"(?:^|[\n\r ]{1,3})(?:通勤時間|写真をはる位置|写真を貼る位置|免許・資格|アルバイト|"
        r"学歴・資格|本人希望記入欄|本人希望記入入欄欄|学歴|職歴|希望給与|希望職種)(?:[\n\r :：]|$)",
        current, re.I,
    )
    if boundary and len(compact(current[:boundary.start()])) >= 20:
        counters["truncate_pr_at_section_boundary"] += 1
        return text(current[:boundary.start()])
    return text(current)


def split_compound_education(row: dict[str, str], counters: Counter[str]) -> dict[str, str]:
    school = unicodedata.normalize("NFKC", text(row.get("school_name")))
    match = re.match(
        r"^(?P<start>(?:19|20)\d{2})年\s*[-~～—–至]\s*(?P<end>(?:19|20)\d{2})年\s*[：:]\s*"
        r"(?P<degree>[^、,，]{1,30})\s*[、,，]\s*(?P<school>[^、,，]{2,80})"
        r"(?:\s*[、,，]\s*(?P<major>.+))?$",
        school,
    )
    if not match:
        return row
    degree_text = text(match.group("degree"))
    row["school_name"] = text(match.group("school"))
    row["school_major_name"] = re.sub(r"(?:专业|専攻)\s*$", "", text(match.group("major")))
    row["school_start_ym"] = f'{match.group("start")}年01月01日'
    row["school_end_ym"] = f'{match.group("end")}年01月01日'
    if re.search(r"硕士|修士|Master", degree_text, re.I):
        row["school_degree_type"] = "硕士"
        row["school_degree_rank"] = "5"
        row["school_education_type"] = "在职研究生" if re.search(r"在职|在職", degree_text) else "全日制研究生"
    elif re.search(r"本科|学士|Bachelor", degree_text, re.I):
        row["school_degree_type"] = "本科"
        row["school_degree_rank"] = "4"
        row["school_education_type"] = "全日制大学" if re.search(r"全日制", degree_text) else "大学"
    counters["split_compound_education"] += 1
    return row


def sanitize_language_list(resume: dict[str, Any], counters: Counter[str]) -> None:
    output: list[dict[str, Any]] = []
    for source in resume.get("language_list") or []:
        if not isinstance(source, dict):
            counters["drop_nonobject_language"] += 1
            continue
        row = scrub_tree(copy.deepcopy(source), True)
        level = unicodedata.normalize("NFKC", text(row.get("language_level")))
        certificate = unicodedata.normalize("NFKC", text(row.get("language_certificate")))
        combined = " ".join((level, certificate))
        normalized_levels: list[str] = []
        patterns = (
            (r"J\.?\s*TEST\s*(?:準|准)?\s*([A-F]|[1-9])(?:\s*級|\s*级)?", lambda m: f"J.TEST {m.group(1).upper()}级"),
            (r"CET\s*[- ]?\s*([46])(?:\s*級|\s*级)?", lambda m: f"CET-{m.group(1)}"),
            (r"(?:JLPT|日本語能力(?:試験|考试|考試)?|日语能力(?:考试)?)\s*[- ]?\s*(N?[1-5]|[一二三四五])(?:\s*級|\s*级)?", lambda m: f"N{({'一':'1','二':'2','三':'3','四':'4','五':'5'}.get(m.group(1), m.group(1))).lstrip('Nn')}") ,
            (r"TOEIC\s*([0-9]{3,4})(?:\s*点|\s*分)?", lambda m: f"TOEIC {m.group(1)}"),
            (r"TOEFL\s*([0-9]{2,3})(?:\s*点|\s*分)?", lambda m: f"TOEFL {m.group(1)}"),
            (r"IELTS\s*([0-9](?:\.[05])?)", lambda m: f"IELTS {m.group(1)}"),
            (r"BEC\s*(初级|中级|高级|Preliminary|Vantage|Higher)", lambda m: f"BEC {m.group(1)}"),
        )
        remainder = combined
        for pattern, formatter in patterns:
            for match in re.finditer(pattern, combined, re.I):
                normalized_levels.append(formatter(match))
            remainder = re.sub(pattern, " ", remainder, flags=re.I)
        remainder = re.sub(r"\b(?:Pass(?:ed)?|Qualified)\b|合格|通过|通過", " ", remainder, flags=re.I)
        remainder = re.sub(r"(?:^|[ /、,，;；]+)(?:有|无|無)(?=$|[ /、,，;；]+)", " ", remainder)
        remainder = text(remainder).strip(" .。;；,，/")
        if normalized_levels:
            row["language_level"] = " / ".join(dict.fromkeys(normalized_levels))
            row["language_certificate"] = "有"
            counters["normalize_language_certificate_semantics"] += 1
        else:
            row["language_level"] = remainder or level
            if certificate in {"有", "无", "無"}:
                row["language_certificate"] = "无" if certificate in {"无", "無"} else "有"
            elif certificate:
                row["language_level"] = text(" / ".join(filter(None, (row["language_level"], certificate))))
                row["language_certificate"] = "有"
                counters["normalize_language_certificate_flag"] += 1
            else:
                row["language_certificate"] = ""
        if text(row.get("language_certificate_time")):
            row["language_certificate_time"] = clean_date(row.get("language_certificate_time"))
        output.append(row)
    resume["language_list"] = output


def move_language_certificates(resume: dict[str, Any], counters: Counter[str]) -> None:
    language_rows = [row for row in (resume.get("language_list") or []) if isinstance(row, dict)]
    certificates = []
    for source in resume.get("certificate_list") or []:
        if not isinstance(source, dict):
            continue
        name = unicodedata.normalize("NFKC", text(source.get("certificate_name")))
        if not re.search(r"CET|TEM|JLPT|J\.?TEST|TOEIC|TOEFL|IELTS|BEC|日本語能力|日语能力|英語能力|英语等级", name, re.I):
            certificates.append(source)
            continue
        language_name = "英语" if re.search(r"CET|TEM|TOEIC|TOEFL|IELTS|BEC|英語|英语", name, re.I) else "日语"
        level = name
        numerals = {"一": "1", "二": "2", "三": "3", "四": "4", "五": "5"}
        match = re.search(r"(?:JLPT|日本語能力(?:試験|考试)?|日语能力(?:考试)?)\s*(?:N)?\s*([1-5一二三四五])\s*(?:级|級)?", name, re.I)
        if match:
            level = "N" + numerals.get(match.group(1), match.group(1))
        else:
            match = re.search(r"(CET|TEM)\s*[- ]?\s*([468])", name, re.I)
            if match:
                level = f"{match.group(1).upper()}-{match.group(2)}"
        existing = next((row for row in language_rows if compact(row.get("language_name")) == compact(language_name)), None)
        if existing is None:
            existing = {field: "" for field in LANGUAGE_FIELDS}
            existing["language_name"] = language_name
            language_rows.append(existing)
        levels = [text(value) for value in re.split(r"\s*/\s*", text(existing.get("language_level"))) if text(value)]
        if level and level not in levels:
            levels.append(level)
        existing["language_level"] = " / ".join(levels)
        existing["language_certificate"] = "有"
        if not text(existing.get("language_certificate_time")):
            existing["language_certificate_time"] = clean_date(source.get("certificate_time"))
        counters["move_language_certificate_to_language_list"] += 1
    resume["certificate_list"] = certificates
    resume["language_list"] = language_rows


def normalize_collection_sequences(resume: dict[str, Any], counters: Counter[str]) -> None:
    """Apply the 1-based numeric sequence contract from CONTEXT.md."""
    for collection in ("project_list", "training_list"):
        for index, row in enumerate(resume.get(collection) or [], 1):
            if not isinstance(row, dict):
                continue
            if row.get("sequence_no") != index:
                row["sequence_no"] = index
                counters[f"normalize_{collection}_sequence"] += 1


def normalize_resume_schema(resume: dict[str, Any], counters: Counter[str]) -> None:
    """Remove parser-only keys and fill every CONTEXT.md-defined field."""
    resume["base_info"] = normalize_row(resume.get("base_info") or {}, BASE_FIELDS)
    for collection, fields in COLLECTION_FIELDS.items():
        normalized = []
        for row in resume.get(collection) or []:
            if isinstance(row, dict):
                current = normalize_row(row, fields)
                meaningful_fields = [field for field in fields if field not in {"sequence_no", "fingerprint"}]
                if collection == "expected_list":
                    # A lone parser default of "全职" is not an evidenced job
                    # intention and must not create an otherwise empty row.
                    meaningful_fields = [field for field in meaningful_fields if field != "expected_employment_type"]
                if not any(text(current.get(field)) for field in meaningful_fields):
                    counters[f"drop_empty_{collection}_row"] += 1
                    continue
                normalized.append(current)
        resume[collection] = normalized
    language = text(resume.get("resume_language")) or "zh"
    base = resume["base_info"]
    household = text(base.get("household_registration"))
    if household:
        household = re.sub(r"^(?:户籍|籍贯|户口|地)\s*[：:]\s*", "", household)
        household = re.split(r"证书|資格|certificate|婚姻状况|自我评价|工作内容", household, maxsplit=1, flags=re.I)[0]
        household = text(household).strip(" :：,，;；")
        if len(household) > 40:
            location = re.search(r"(?:北京|上海|天津|重庆|[\u3400-\u9fff]{2,8}(?:省|市))[\u3400-\u9fff]{0,12}", household)
            household = text(location.group(0)) if location else ""
        if household != text(base.get("household_registration")):
            counters["clean_household_registration"] += 1
        base["household_registration"] = household
    if language == "zh":
        gender = text(base.get("gender"))
        match = re.search(r"(?:^|\b)(男|女)(?:\b|$)", gender)
        if not match and gender.casefold() in {"male", "female"}:
            base["gender"] = "男" if gender.casefold() == "male" else "女"
        elif match:
            base["gender"] = match.group(1)
        elif gender:
            base["gender"] = ""
        if gender and base["gender"] != gender:
            counters["normalize_primary_gender"] += 1
    for row in resume["expected_list"]:
        if text(row.get("expected_employment_type")) not in {"", "全职", "兼职", "实习", "remote", "混合办公"}:
            row["expected_employment_type"] = ""
            counters["clear_invalid_expected_employment_type"] += 1
    for row in resume["work_experiences"]:
        position = text(row.get("position"))
        # Only split an explicit department prefix.  A role such as
        # "日语翻译兼部长助理" contains 部 but is not "department + role".
        department_role = re.search(
            r"^(?:(?:隶属|所属)\s*([^，。;；]{1,30}?部)\s*(?:担任)?\s*|([^，。;；]{1,30}?部)\s{1,})([^，。;；]{1,40}?)(?:职务)?(?:主要工作内容|主要内容|$)",
            position,
        )
        if department_role:
            if not text(row.get("position_dept")):
                row["position_dept"] = text(department_role.group(1) or department_role.group(2))
            position = text(department_role.group(3))
        position = re.sub(r"^[（(]?\d{1,2}\s*月[）)]?\s*", "", position)
        position = re.sub(r"^(?:日系\s+)?所属部署\s*$", "", position)
        if re.fullmatch(r"(?:\d{1,2}\s*月\s*)?[-~～至]*\s*(?:19|20)\d{2}\s*年?\s*\d{1,2}\s*月?", position):
            position = ""
        if position != text(row.get("position")):
            counters["clean_contaminated_position"] += 1
        row["position"] = position
        if language == "zh" and text(row.get("employment_type")) not in {"", "全职", "兼职", "实习"}:
            row["employment_type"] = ""
            counters["clear_invalid_employment_type"] += 1
        if language == "zh" and text(row.get("status")) not in {"", "在职", "离职"}:
            row["status"] = ""
            counters["clear_invalid_status"] += 1
        subordinate = text(row.get("position_subordinate"))
        if subordinate:
            row["position_subordinate"] = clean_numeric_text(subordinate, maximum=100000)
        employees = text(row.get("company_employees"))
        match = re.search(r"\d+\s*(?:-|~|～|—|至)\s*\d+人|\d+人以上|少于\d+人|未填写", employees)
        if employees and (not match or match.group(0) != employees):
            row["company_employees"] = match.group(0) if match else ""
            counters["normalize_company_employees"] += 1
        industry = text(row.get("company_industry"))
        if re.search(r"(?:元|円|RMB|CNY|JPY|月薪|年薪|/月|per month)", industry, re.I):
            if not text(row.get("position_salary")):
                row["position_salary"] = re.sub(r"^(?:薪酬状况|薪资|月薪)\s*[：:]\s*", "", industry)
            row["company_industry"] = ""
            counters["move_salary_from_industry"] += 1
    for row in resume["language_list"]:
        level = text(row.get("language_level"))
        if level and re.fullmatch(r"(?:普通话|日语|英语)?(?:等级|能力)?证书(?:\s*/\s*(?:普通话|日语|英语)?(?:等级|能力)?证书)*", level):
            row["language_level"] = ""
            row["language_certificate"] = "有"
            counters["clear_generic_language_certificate_level"] += 1
    allowed = {"resume_language", "base_info", *RESUME_LISTS}
    for key in list(resume):
        if key not in allowed:
            resume.pop(key, None)
            counters["drop_non_schema_resume_key"] += 1
    resume["resume_language"] = language
    normalize_collection_sequences(resume, counters)


def normalize_education_metadata(row: dict[str, str], counters: Counter[str]) -> dict[str, str]:
    degree = text(row.get("school_degree_type"))
    joined = degree or " ".join((text(row.get("school_name")), text(row.get("school_major_name"))))
    expected_rank = ""
    if re.search(r"博士|Ph\.?D|Doctor", joined, re.I):
        expected_rank = "6"
    elif re.search(r"硕士|修士|Master|MBA", joined, re.I):
        expected_rank = "5"
    elif re.search(r"本科|学士|Bachelor", joined, re.I):
        expected_rank = "4"
    elif re.search(r"大专|专科|短大|Associate", joined, re.I):
        expected_rank = "3"
    if expected_rank and text(row.get("school_degree_rank")) != expected_rank:
        row["school_degree_rank"] = expected_rank
        counters["normalize_degree_rank"] += 1
    if re.search(r"在职学习|在職|在职", joined, re.I) and re.search(r"全日制", text(row.get("school_education_type"))):
        row["school_education_type"] = "在职研究生" if expected_rank in {"5", "6"} else "在职大学"
        counters["normalize_inservice_education_type"] += 1
    return row


def normalize_school_components(row: dict[str, str], counters: Counter[str]) -> dict[str, str]:
    school = text(row.get("school_name"))
    date_range = re.search(
        r"(?P<start>(?:19|20)\d{2})\s*年\s*(?P<sm>1[0-2]|0?[1-9])?\s*月?\s*[-~～—–至]\s*"
        r"(?P<end>(?:19|20)\d{2})\s*年\s*(?P<em>1[0-2]|0?[1-9])?\s*月?",
        school,
    )
    if date_range:
        if not text(row.get("school_start_ym")):
            row["school_start_ym"] = f"{date_range.group('start')}年{int(date_range.group('sm') or 1):02d}月01日"
        if not text(row.get("school_end_ym")):
            row["school_end_ym"] = f"{date_range.group('end')}年{int(date_range.group('em') or 1):02d}月01日"
        school = text(school[:date_range.start()] + " " + school[date_range.end():]).strip(" |丨｜、,，:：")
        row["school_name"] = school
        counters["strip_date_range_from_school"] += 1
    numbered = re.sub(r"^\d{1,2}\s+(?=\S)", "", school)
    if numbered != school:
        school = numbered
        row["school_name"] = school
        counters["strip_school_line_number"] += 1
    reverse = re.match(r"^(?:Major\s*[:：]\s*)?(?P<major>[^/]{2,100})\s*/\s*(?P<school>.+?(?:University|College))(?:\s+.*)?$", school, re.I)
    if reverse:
        row["school_name"] = text(reverse.group("school"))
        row["school_major_name"] = text(reverse.group("major"))
        school = row["school_name"]
        counters["split_reversed_school_major"] += 1
    if re.search(r"入学|卒業|卒業|修了|毕业", school) or re.search(r"\s[/、,，]\s", school):
        match = re.match(r"^(?P<school>.+?(?:大学|学院|専門学校|职业学校|University|College))(?:\s+|\s*[/、,，]\s*)?(?P<rest>.*)$", school, re.I)
        if match:
            row["school_name"] = text(match.group("school"))
            rest = re.sub(r"(?:入学|卒業|卒業|修了|毕业)\s*$", "", text(match.group("rest")))
            rest = re.sub(r"(?:专业|専攻|学科|学部|学位)\s*$", "", rest)
            if rest and (not text(row.get("school_major_name")) or text(row.get("school_major_name")) in {"自己紹介", ")", "教育背景"}):
                row["school_major_name"] = rest
            counters["split_school_major_event"] += 1
    school = text(row.get("school_name"))
    plain = re.match(
        r"^(?P<school>.+?(?:大学院大学|大学|学院|専門学校|职业学校|University|College))(?:\s+|\s*[丨｜|]\s*)"
        r"(?P<rest>.+)$",
        school,
        re.I,
    )
    if plain:
        rest = text(plain.group("rest"))
        if re.search(r"(?:19|20)\d{2}\s*年", rest) or re.search(r"本科|学士|硕士|修士|博士|Bachelor|Master|Ph\.?D", rest, re.I):
            row["school_name"] = text(plain.group("school"))
            major = re.sub(r"(?:19|20)\d{2}\s*年.*$", "", rest)
            major = re.sub(r"(?:本科|学士|硕士|修士|博士|Bachelor|Master|Ph\.?D).*$", "", major, flags=re.I)
            major = text(major).strip(" /、,，()（）丨｜|")
            if major and not text(row.get("school_major_name")):
                row["school_major_name"] = major
            counters["split_plain_school_details"] += 1
    return row


def recover_project_name(row: dict[str, Any], source_text: str, counters: Counter[str]) -> dict[str, Any] | None:
    name = text(row.get("project_name"))
    description = text(row.get("description"))
    dated_name = re.fullmatch(r"(?:(?:19|20)?\d{2})[./-]\d{1,2}", name)
    if name and not (
        PLACEHOLDER_RE.fullmatch(name) or ENTITY_PLACEHOLDER_RE.fullmatch(name)
        or re.fullmatch(r"项目职务\s*[：:]?", name) or dated_name
        or re.fullmatch(r"项目|Project|项目经历|主要项目|重点项目", name, re.I)
    ):
        return row
    if dated_name:
        start = date_tuple(row.get("start_ym"))
        if start:
            start_pattern = rf"(?:{start[0]}|{str(start[0])[2:]})\s*[./年-]\s*0?{start[1]}(?:\s*月)?"
            for line in [text(value) for value in (source_text or "").splitlines() if text(value)]:
                match = re.search(start_pattern, unicodedata.normalize("NFKC", line), re.I)
                if not match:
                    continue
                candidate = text(line[:match.start()])
                candidate = re.split(
                    r"(?:19|20)\d{2}\s*[./年-]\s*\d{1,2}.*?[-~～至]\s*(?:19|20)?\d{2}\s*[./年-]\s*\d{1,2}",
                    candidate,
                )[-1]
                candidate = re.split(r"职责业绩|项目经历|项目经验|[。；;]", candidate)[-1]
                candidate = re.sub(r"^(?:项目名称|项目名|Project\s*Name)\s*[：:]\s*", "", candidate, flags=re.I)
                candidate = text(candidate).strip(" |｜:：,，-—")
                if (
                    2 <= len(compact(candidate)) <= 100
                    and not re.fullmatch(r"项目|Project", candidate, re.I)
                    and not re.fullmatch(r"(?:(?:19|20)?\d{2})[./-]\d{1,2}", candidate)
                ):
                    row["project_name"] = candidate
                    end_match = re.fullmatch(r"(?P<year>(?:19|20)?\d{2})[./-](?P<month>\d{1,2})", name)
                    if end_match and not text(row.get("end_ym")):
                        year = int(end_match.group("year"))
                        if year < 100:
                            year += 2000
                        row["end_ym"] = f"{year:04d}年{int(end_match.group('month')):02d}月01日"
                    counters["recover_dated_project_name_from_source"] += 1
                    return row
    name = ""
    row["project_name"] = ""
    if not description:
        counters["drop_empty_project"] += 1
        return None
    explicit = re.search(r"Project\s*Name\s*[：:]\s*([^\r\n]{2,120})", description, re.I)
    if explicit:
        row["project_name"] = text(explicit.group(1))
        counters["recover_project_name_inline"] += 1
        return row
    numbered = re.match(r"^\s*\d+[.、)]\s*(.{2,100}?)\s+(?:项目目标|Project\s*(?:Goal|Objective))\s*[：:]", description, re.I)
    if numbered:
        row["project_name"] = text(numbered.group(1))
        counters["recover_project_name_numbered"] += 1
        return row
    needle = compact(description)[:40]
    lines = [text(line) for line in (source_text or "").splitlines() if text(line)]
    for index, line in enumerate(lines):
        if len(needle) < 12 or needle not in compact(line):
            continue
        for offset in (1, 2, 3):
            if index - offset < 0:
                break
            candidate = text(lines[index - offset])
            candidate = re.sub(r"^(?:项目名称|Project\s*Name)\s*[：:]\s*", "", candidate, flags=re.I)
            if not candidate or len(candidate) > 120:
                continue
            if PLACEHOLDER_RE.fullmatch(candidate) or ENTITY_PLACEHOLDER_RE.fullmatch(candidate):
                continue
            if re.fullmatch(r"项目经历|项目经验|辅料研究|制剂项目|Projects? Experience", candidate, re.I):
                continue
            if re.match(r"^(?:项目描述|个人职责|项目职责|职责|Description|Responsibilit)", candidate, re.I):
                continue
            if re.search(r"[。；;]", candidate) or len(compact(candidate)) < 2:
                continue
            row["project_name"] = candidate
            counters["recover_project_name_from_source"] += 1
            return row
    counters["drop_unnamed_project"] += 1
    return None


def read_pdf_text(path: Path) -> str:
    if fitz is None or not path.is_file():
        return ""
    try:
        with fitz.open(str(path)) as document:
            return "\n".join(page.get_text("text") for page in document)
    except Exception:
        return ""


def read_docx_text(path: Path) -> str:
    if not path.is_file():
        return ""
    try:
        with zipfile.ZipFile(path) as archive:
            root = ET.fromstring(archive.read("word/document.xml"))
        paragraphs = []
        for paragraph in root.iter(W_NS + "p"):
            value = "".join(node.text or "" for node in paragraph.iter(W_NS + "t")).strip()
            if value:
                paragraphs.append(value)
        return "\n".join(paragraphs)
    except Exception:
        return ""


def normalize_source_block(value: str) -> str:
    value = unicodedata.normalize("NFKC", value or "").replace("\r", "\n")
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in value.split("\n")]
    return "\n".join(line for line in lines if line)


def source_text_index(mapping: dict[str, Any]) -> dict[str, str]:
    return build_source_text_index(mapping)


def payload_source_texts(payload: dict[str, Any], index: dict[str, str]) -> list[str]:
    value = payload_raw_text(payload, index)
    return [value] if value else []


def date_tuple(value: Any) -> tuple[int, int, int] | None:
    current = unicodedata.normalize("NFKC", text(value))
    era = re.search(r"(昭和|平成|令和)\s*(元|\d{1,2})\s*年?\s*(\d{1,2})?\s*月?\s*(\d{1,2})?", current)
    if era:
        era_name, era_year = era.group(1), 1 if era.group(2) == "元" else int(era.group(2))
        base = {"昭和": 1925, "平成": 1988, "令和": 2018}[era_name]
        return base + era_year, int(era.group(3) or 1), max(1, int(era.group(4) or 1))
    match = DATE_TOKEN_RE.search(current)
    if not match:
        return None
    return int(match.group("year")), int(match.group("month") or 1), max(1, int(match.group("day") or 1))


def clean_date(value: Any, *, end: bool = False) -> str:
    current = text(value)
    if not current or (end and PRESENT_RE.search(current)):
        return ""
    parsed = date_tuple(current)
    if not parsed:
        return ""
    year, month, day = parsed
    return f"{year:04d}年{month:02d}月{day:02d}日"


def clean_month_date(value: Any, *, end: bool = False) -> str:
    cleaned = clean_date(value, end=end)
    parsed = date_tuple(cleaned)
    return f"{parsed[0]:04d}年{parsed[1]:02d}月01日" if parsed else ""


def named_segments(value: Any) -> list[str]:
    raw = str(value or "")
    raw = re.sub(r"<[^>]+>", "\n", raw)
    raw = html.unescape(raw)
    pieces = re.split(r"[\r\n|｜;；]+|(?=(?:19|20)\d{2}[年./-])", raw)
    return [text(re.sub(r"\b(?:data-[a-z-]+|label)\s*=\s*[\"'][^\"']*[\"']", " ", piece, flags=re.I)) for piece in pieces if text(piece)]


def embedded_entity_candidates(value: Any, kind: str) -> list[str]:
    cleaned = strip_markup(value)
    cleaned = re.sub(
        r"(?:毕业院校|毕业大学|卒業学校|教育经历|教育背景|学歴|学校|公司名称|会社名|勤務先)\s*[:：]",
        "\n", cleaned, flags=re.I,
    )
    pieces = re.split(r"[\n|｜;；,，]|\s{2,}", cleaned)
    output: list[str] = []
    if kind == "school":
        zh_pattern = re.compile(r"[\u3400-\u9fff·]{2,16}(?:大学|学院|学校|中学|研究院)")
        latin_pattern = re.compile(r"[A-Z][A-Za-zÀ-ÿ&.'()\- ]{2,60}(?:University|College|School|Institute|Academy)", re.I)
        noise = SCHOOL_NOISE_RE
        patterns = (zh_pattern, latin_pattern)
    else:
        zh_pattern = re.compile(r"[\u3400-\u9fffA-Za-z0-9（）()·&\-]{2,36}(?:有限公司|有限责任公司|股份有限公司|株式会社|有限会社|公司|会社)")
        jp_prefix_pattern = re.compile(r"(?:株式会社|有限会社)\s*[\u3400-\u9fff\u3040-\u30ffA-Za-z0-9（）()·&\- ]{2,50}")
        jp_suffix_pattern = re.compile(r"[\u3400-\u9fff\u3040-\u30ffA-Za-z0-9（）()·&\- ]{2,50}(?:株式会社|有限会社)")
        latin_pattern = re.compile(r"[A-Z][A-Za-z0-9&.,'()\- ]{2,60}(?:Co\.?\s*,?\s*Ltd\.?|Ltd\.?|Inc\.?|Corp\.?|Corporation|Company|GmbH|AG)\b", re.I)
        noise = COMPANY_NOISE_RE
        patterns = (zh_pattern, jp_prefix_pattern, jp_suffix_pattern, latin_pattern)
    for piece in pieces + [cleaned]:
        for pattern in patterns:
            for match in pattern.finditer(piece):
                candidate = text(match.group(0))
                candidate = re.sub(r"^(?:年|月|本科|硕士|博士|毕业|卒業|项目|奖学金|受賞|荣誉)+", "", candidate)
                candidate = re.sub(r"^(?:Bachelor|Master|Ph\.?D|Diploma)(?:\s+in)?\s+", "", candidate, flags=re.I)
                candidate = re.split(r"\s*(?:入社|退社|职位|職位|役職)\b", candidate, maxsplit=1, flags=re.I)[0]
                if candidate in {"株式会社", "有限会社", "公司", "会社"}:
                    continue
                if candidate and not noise.search(candidate):
                    output.append(candidate)
    return output


def extract_entity(value: Any, kind: str) -> tuple[str, str]:
    original = str(value or "")
    cleaned = strip_markup(original)
    matcher = COMPANY_RE if kind == "company" else SCHOOL_RE
    limit = 100 if kind == "company" else 90
    candidates = []
    for segment in named_segments(original) + re.split(r"[。!?！？]", cleaned):
        segment = text(segment)
        segment = re.sub(
            r"^(?:公司名(?:称)?|会社名|学校名|社名|单位|勤務先|教育背景|学歴|School|Company)\s*[:：]?\s*",
            "", segment, flags=re.I,
        )
        segment = re.sub(r"^(?:19|20)\d{2}[^\s]{0,15}\s+", "", segment)
        if matcher.search(segment) and 2 <= len(segment) <= limit:
            candidates.append(segment)
    candidates.extend(embedded_entity_candidates(original, kind))
    noise = COMPANY_NOISE_RE if kind == "company" else SCHOOL_NOISE_RE
    candidates = [
        candidate for candidate in candidates
        if candidate not in {"株式会社", "有限会社", "公司", "会社"} and not noise.search(candidate)
    ]
    if candidates:
        def entity_score(item: str) -> tuple[int, int, str]:
            strong = bool(re.search(r"有限公司|有限责任公司|股份有限公司|株式会社|有限会社|University|College|Institute", item, re.I))
            return (0 if strong else 1, len(item), item)
        entity = min(candidates, key=entity_score)
    elif matcher.search(cleaned) and len(cleaned) <= limit and not noise.search(cleaned) and not ENTITY_PLACEHOLDER_RE.fullmatch(cleaned):
        entity = cleaned
    else:
        entity = ""
    remainder = cleaned
    if entity and entity in remainder:
        remainder = text(remainder.replace(entity, " ", 1))
    return entity, remainder


def normalize_row(row: dict[str, Any], fields: tuple[str, ...]) -> dict[str, str]:
    return {field: text(row.get(field)) for field in fields}


def clean_labeled_value(value: Any, field: str) -> str:
    current = strip_markup(value)
    if not current or ENTITY_PLACEHOLDER_RE.fullmatch(current):
        return ""
    if field == "position":
        if re.fullmatch(r"(?:公司|会社|有限公司|株式会社|Co\.?|Ltd\.?|Inc\.?)", current, re.I):
            return ""
        labeled = re.search(r"(?:职位|职务|職種|役職|具体职位)\s*[：:]\s*([^|｜;；。]{1,80})", current, re.I)
        if labeled:
            current = labeled.group(1)
        current = re.split(r"\s*(?:工作描述|工作职责|仕事内容|業務内容|出資状況|業界|社員数|证书)\s*[：:]?", current, maxsplit=1, flags=re.I)[0]
        current = re.sub(r"^(?:部门|部署)\s*[：:]\s*[^：:]{1,60}(?:职位|职务|職種)\s*[：:]\s*", "", current, flags=re.I)
    elif field == "school_major_name":
        labeled = re.search(r"(?:专业|専攻|学科|Major)\s*[：:]\s*([^|｜;；。]{1,80})", current, re.I)
        if labeled:
            current = labeled.group(1)
        elif FIELD_LABEL_RE.search(current) or len(current) > 140:
            return ""
    elif field == "project_name":
        current = re.split(r"\s*(?:项目职位|项目描述|项目职责|Project Role|Description)\s*[：:]", current, maxsplit=1, flags=re.I)[0]
    elif field in {"training_name", "certificate_name"}:
        if FIELD_LABEL_RE.search(current) or SENTENCE_ENTITY_RE.search(current):
            return ""
    current = text(current).strip(" ,，:：|｜")
    return "" if ENTITY_PLACEHOLDER_RE.fullmatch(current) else current


def split_company_and_remainder(value: Any) -> tuple[str, str]:
    current = strip_markup(value)
    candidates = embedded_entity_candidates(current, "company")
    if not candidates:
        return "", current
    company = min(candidates, key=len)
    remainder = text(current.replace(company, " ", 1))
    remainder = re.sub(
        r"^(?:(?:19|20)\d{2}[./年-]\d{1,2}[^\s]{0,18}|\(?\d+\s*(?:年|个月|か月|ヶ月)\)?|[|｜/、,，:：\s])+",
        "", remainder,
    )
    return company, remainder


def sanitize_named_collections(resume: dict[str, Any], counters: Counter[str]) -> None:
    configs = {
        "project_list": ("project_name", 140),
        "training_list": ("training_name", 140),
        "certificate_list": ("certificate_name", 100),
    }
    for collection, (field, limit) in configs.items():
        output: list[dict[str, Any]] = []
        for source in resume.get(collection) or []:
            if not isinstance(source, dict):
                counters[f"drop_nonobject_{collection}"] += 1
                continue
            row = scrub_tree(copy.deepcopy(source), True)
            original = text(row.get(field))
            if collection == "training_list" and not original:
                organization = text(row.get("organization_name"))
                description = text(row.get("description"))
                if re.search(r"会社名|公司名|職務|仕事内容|工作经历|语言能力|免許[·・]?資格", description, re.I) or len(description) > 220:
                    counters["drop_misclassified_training"] += 1
                    continue
                if organization and not description:
                    original = organization
                    row["organization_name"] = ""
                    counters["move_training_name_from_organization"] += 1
                elif description and len(description) <= 220:
                    original = description
                    row["description"] = ""
                    counters["move_training_name_from_description"] += 1
                else:
                    counters["drop_unrecoverable_training"] += 1
                    continue
            if collection == "project_list":
                if re.match(r"^(?:出生日期|生年月日|联系电话|電話番号|电子邮箱|E-?mail)\s*[：:]", original, re.I):
                    counters["drop_personal_label_project"] += 1
                    continue
                if re.match(r"^项目职务\s*[：:]", original):
                    counters["drop_role_only_project"] += 1
                    continue
                role_match = re.search(r"\s*项目职务\s*[：:]\s*(.+)$", original)
                if role_match:
                    if not text(row.get("role_name")):
                        row["role_name"] = text(role_match.group(1))
                    original = text(original[:role_match.start()])
                original = re.sub(
                    r"\s*[（(]?(?:19|20)\d{2}\s*[./年]\s*\d{1,2}\s*(?:月)?\s*[-—–～~至]\s*(?:19|20)\d{2}\s*[./年]\s*\d{1,2}\s*(?:月)?[）)]?\s*$",
                    "", original,
                )
            cleaned = clean_labeled_value(original, field)
            if not cleaned:
                if original:
                    counters[f"clear_bad_{field}"] += 1
                row[field] = ""
                if collection == "certificate_list":
                    counters["drop_empty_certificate"] += 1
                    continue
            elif len(cleaned) <= limit:
                row[field] = cleaned
            elif field == "certificate_name":
                pieces = [text(piece) for piece in re.split(
                    r"[\r\n;；•·]|(?=\b(?:CET|JLPT|TOEFL|IELTS|Office|Microsoft|Adobe|普通机动车|一级小型船舶))",
                    cleaned, flags=re.I,
                ) if 2 <= len(text(piece)) <= limit]
                if pieces:
                    for index, piece in enumerate(dict.fromkeys(pieces)):
                        clone = copy.deepcopy(row)
                        clone[field] = piece
                        if index:
                            for date_field in ("certificate_time",):
                                if date_field in clone:
                                    clone[date_field] = ""
                        output.append(clone)
                    counters["split_long_certificate"] += 1
                    continue
                row[field] = ""
                counters["clear_long_certificate"] += 1
            else:
                row[field] = ""
                counters[f"clear_long_{field}"] += 1
            if field == "certificate_name" and "certificate_time" in row:
                row["certificate_time"] = clean_date(row.get("certificate_time"))
            if collection == "project_list":
                row = normalize_row(row, PROJECT_FIELDS)
                row["start_ym"] = clean_month_date(row.get("start_ym"))
                row["end_ym"] = clean_month_date(row.get("end_ym"), end=True)
            elif collection == "training_list":
                row = normalize_row(row, TRAINING_FIELDS)
                row["start_ym"] = clean_month_date(row.get("start_ym"))
                row["end_ym"] = clean_month_date(row.get("end_ym"), end=True)
                # Section-boundary leakage: awards following a training section
                # are not training records and must not survive as such.
                if re.search(r"优秀员工|優秀社員|奖学金|奨学金|获奖情况|受賞歴", text(row.get("training_name")), re.I):
                    counters["drop_award_as_training"] += 1
                    continue
                if re.fullmatch(r"(?:获奖情况|受賞歴)?\s*\d+[)）.]?", text(row.get("description")), re.I):
                    row["description"] = ""
                    counters["clear_award_heading_from_training"] += 1
            if collection in {"project_list", "training_list"}:
                start, end = date_tuple(row.get("start_ym")), date_tuple(row.get("end_ym"))
                if start and end and start > end:
                    row["start_ym"], row["end_ym"] = row["end_ym"], row["start_ym"]
                    counters[f"swap_{collection}_dates"] += 1
            output.append(row)
        deduped: list[dict[str, Any]] = []
        seen: set[str] = set()
        for row in output:
            key = compact(row.get(field))
            fingerprint = key or json.dumps(row, ensure_ascii=False, sort_keys=True)
            if fingerprint in seen:
                counters[f"dedupe_{collection}"] += 1
                continue
            seen.add(fingerprint)
            deduped.append(row)
        resume[collection] = deduped


def reconcile_single_source_variants(
    resumes: list[dict[str, Any]], source_texts: list[str], counters: Counter[str], *, prefer_primary: bool = False
) -> None:
    """Align row identity and dates across translations of one source file."""
    if len(resumes) < 2:
        return
    source_language = detected_language("\n".join(source_texts))
    native = resumes[0] if prefer_primary else next(
        (row for row in resumes if text(row.get("resume_language")) == source_language), None
    )

    for collection, (fields, entity_field, start_field, end_field) in COLLECTION_ALIGNMENT.items():
        candidates = [row for row in resumes if isinstance(row.get(collection), list)]
        if not candidates:
            continue
        reference_resume = native if native in candidates and native.get(collection) else max(
            candidates,
            key=lambda row: sum(
                bool(text(item.get(entity_field))) + bool(text(item.get(start_field))) + bool(text(item.get(end_field)))
                for item in (row.get(collection) or []) if isinstance(item, dict)
            ),
        )
        reference = [normalize_row(item, fields) for item in (reference_resume.get(collection) or []) if isinstance(item, dict)]
        if not reference:
            continue
        reference_signature = [(text(item.get(start_field)), text(item.get(end_field))) for item in reference]
        for resume in resumes:
            if resume is reference_resume:
                resume[collection] = reference
                continue
            target = [normalize_row(item, fields) for item in (resume.get(collection) or []) if isinstance(item, dict)]
            target_signature = [(text(item.get(start_field)), text(item.get(end_field))) for item in target]
            if target_signature == reference_signature:
                continue
            unused = set(range(len(target)))
            aligned: list[dict[str, str]] = []
            for reference_row in reference:
                ref_start = text(reference_row.get(start_field))
                ref_end = text(reference_row.get(end_field))
                best_index, best_score = None, -1
                for target_index in unused:
                    target_row = target[target_index]
                    score = 0
                    if ref_start and ref_start == text(target_row.get(start_field)):
                        score += 4
                    if ref_end and ref_end == text(target_row.get(end_field)):
                        score += 4
                    ref_entity = compact(reference_row.get(entity_field))
                    target_entity = compact(target_row.get(entity_field))
                    if ref_entity and target_entity and (ref_entity in target_entity or target_entity in ref_entity):
                        score += 2
                    if score > best_score:
                        best_index, best_score = target_index, score
                if best_index is None or best_score <= 0:
                    chosen = normalize_row({}, fields)
                else:
                    chosen = copy.deepcopy(target[best_index])
                    unused.discard(best_index)
                # Keep row identity aligned, but never copy narrative fields
                # across languages merely to make a translated row look full.
                if not text(chosen.get(entity_field)):
                    chosen[entity_field] = reference_row.get(entity_field, "")
                chosen[start_field] = reference_row.get(start_field, "")
                chosen[end_field] = reference_row.get(end_field, "")
                aligned.append(chosen)
            resume[collection] = aligned
            counters[f"align_single_source_{collection}"] += 1
    for resume in resumes:
        language_code = text(resume.get("resume_language"))
        for row in resume.get("work_experiences") or []:
            if not isinstance(row, dict) or not text(row.get("position_resigned")):
                continue
            if text(row.get("status")).casefold() in {"在职", "在籍", "就职中", "勤務中", "current", "present"}:
                row["status"] = {"ja": "退職", "en": "Former", "de": "Beendet"}.get(language_code, "离职")
                counters["repair_aligned_ended_work_status"] += 1


def clear_cross_language_clones(resumes: list[dict[str, Any]], counters: Counter[str]) -> None:
    """Remove Chinese semantic prose copied verbatim into ja/en variants."""
    primary = next((row for row in resumes if text(row.get("resume_language")) == "zh"), None)
    if not primary:
        return
    mappings = {
        "ja": {
            "在职": "在職", "离职": "退職", "全职": "正社員", "兼职": "アルバイト", "实习": "インターンシップ",
            "工程师": "エンジニア", "经理": "マネージャー", "助理": "アシスタント", "秘书": "秘書",
            "销售": "営業", "翻译": "通訳", "教师": "教師", "成员": "メンバー",
            "本科": "学士", "硕士": "修士", "博士": "博士", "日语": "日本語", "英语": "英語",
            "德语": "ドイツ語", "法语": "フランス語", "中文": "中国語", "普通话": "標準中国語", "上海话": "上海語",
            "熟练": "熟練", "精通": "上級", "良好": "良好",
        },
        "en": {
            "在职": "Current", "离职": "Former", "全职": "Full-time", "兼职": "Part-time", "实习": "Internship",
            "工程师": "Engineer", "经理": "Manager", "助理": "Assistant", "秘书": "Secretary",
            "销售": "Sales", "翻译": "Interpreter", "教师": "Teacher", "成员": "Member",
            "本科": "Bachelor", "硕士": "Master", "博士": "PhD", "日语": "Japanese", "英语": "English",
            "德语": "German", "法语": "French", "中文": "Chinese", "普通话": "Mandarin", "上海话": "Shanghainese",
            "熟练": "Proficient", "精通": "Advanced", "良好": "Good",
        },
    }
    prose_fields = {
        "position_responsibilities", "position_achievements", "resigned_reason", "description",
        "responsibilities", "achievements", "keywords", "communicate_content", "pr",
    }
    translatable_fields = {
        "position", "position_type", "position_dept", "employment_type", "status",
        "school_major_name", "school_degree_type", "school_education_type", "language_name",
        "language_level", "skill_level", "role_name", "training_name", "certificate_type",
    }
    for variant in resumes:
        lang = text(variant.get("resume_language"))
        if lang not in mappings:
            continue
        base, primary_base = variant.get("base_info") or {}, primary.get("base_info") or {}
        base_pr = text(base.get("pr"))
        base_pr_han = len(re.findall(r"[\u3400-\u9fff]", base_pr))
        base_pr_kana = len(re.findall(r"[\u3040-\u30ff]", base_pr))
        if (base_pr_han >= 20 and base_pr_kana < 3) or (
            compact(base_pr) and compact(base_pr) == compact(primary_base.get("pr"))
        ):
            base["pr"] = ""
            counters["clear_cross_language_cloned_prose"] += 1
        for collection in RESUME_LISTS:
            target_rows = variant.get(collection) or []
            source_rows = primary.get(collection) or []
            for index, target in enumerate(target_rows):
                if not isinstance(target, dict):
                    continue
                source_row = source_rows[index] if index < len(source_rows) and isinstance(source_rows[index], dict) else {}
                for field, value in list(target.items()):
                    current = text(value)
                    han_count = len(re.findall(r"[\u3400-\u9fff]", current))
                    kana_count = len(re.findall(r"[\u3040-\u30ff]", current))
                    if lang in {"ja", "en"} and han_count >= 20 and kana_count < 3:
                        if field in prose_fields or field in {
                            "company_industry", "school_major_name", "language_level", "position_dept",
                            "position_report_to", "position_type", "skill_level",
                        }:
                            target[field] = ""
                            counters["clear_foreign_variant_chinese_prose"] += 1
                            continue
                        if field == "company_name" and (SENTENCE_ENTITY_RE.search(current) or len(current) > 65):
                            recovered, _ = extract_entity(current, "company")
                            if recovered:
                                target[field] = recovered
                                counters["repair_foreign_variant_company"] += 1
                            continue
                    if not current or compact(current) != compact(source_row.get(field)):
                        continue
                    if field in prose_fields:
                        target[field] = ""
                        counters["clear_cross_language_cloned_prose"] += 1
                    elif field in translatable_fields:
                        translated = mappings[lang].get(current)
                        if translated and translated != current:
                            target[field] = translated
                            counters["repair_cross_language_cloned_label"] += 1


def append_text(current: str, addition: str) -> str:
    current, addition = text(current), text(addition)
    if not addition or compact(addition) in compact(current):
        return current
    return text(f"{current}\n{addition}") if current else addition


def work_from_education(row: dict[str, Any]) -> dict[str, str]:
    work = {field: "" for field in WORK_FIELDS}
    work["company_name"] = text(row.get("school_name"))
    work["position"] = text(row.get("school_major_name"))
    work["position_start"] = clean_date(row.get("school_start_ym"))
    work["position_resigned"] = clean_date(row.get("school_end_ym"), end=True)
    return work


def education_from_work(row: dict[str, Any]) -> dict[str, str]:
    education = {field: "" for field in EDU_FIELDS}
    education["school_name"] = text(row.get("company_name"))
    education["school_major_name"] = text(row.get("position"))
    education["school_start_ym"] = clean_date(row.get("position_start"))
    education["school_end_ym"] = clean_date(row.get("position_resigned"), end=True)
    return education


def source_date(value: str) -> str:
    return clean_date(value, end=PRESENT_RE.search(value or "") is not None)


def company_from_block(block: str) -> str:
    labeled = re.search(r"(?:企业名|企業名|公司名(?:称)?|会社名|单位|勤務先)\s*[:：]?\s*(.{2,100})", block, re.I)
    if labeled:
        entity, _ = extract_entity(labeled.group(1), "company")
        if entity:
            return entity
    entity, _ = extract_entity(block[:240], "company")
    if entity:
        return entity
    leading = re.split(r"(?:职位|職位|职务|岗位|役職|POSITION|Job Title|所属行业|公司规模|勤務期間)", block, maxsplit=1, flags=re.I)[0]
    leading = re.sub(r"^\s*\d+[.、\s]+", "", text(leading)).strip(" ,，:：")
    if 2 <= len(leading) <= 80 and re.search(
        r"银行|中心|学校|学院|教育|科技|集团|研究所|事务所|事務所|病院|商事|Corporation|Technology|"
        r"ALFALAVAL|Pall|Flextronics|KEYENCE|キーエンス",
        leading, re.I,
    ) and not COMPANY_NOISE_RE.search(leading):
        return leading
    return ""


def position_from_block(block: str, company: str) -> str:
    labeled = re.search(
        r"(?:职位|職位|职务|岗位|役職|部署/役職)\s*[:：]?\s*(.{1,60}?)"
        r"(?=\s+(?:汇报|工作职责|工作内容|工作属性|業務内容|仕事内容|部署|出資|人数|事業内容)|[|｜;；。]|$)",
        block, re.I,
    )
    if labeled:
        return text(labeled.group(1))
    after = block
    if company and company in after:
        after = after.split(company, 1)[1]
    after = re.split(r"(?:工作职责|工作内容|工作業績|业务内容|業務内容|仕事内容|汇报上级|勤務内容)", after, maxsplit=1, flags=re.I)[0]
    after = re.sub(r"^(?:（[^）]*）|\([^)]*\)|[,，:：\s])+", "", after)
    return text(after)[:50] if 0 < len(text(after)) <= 50 else ""


def recover_work_from_source(source: str, counters: Counter[str]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    heading_matches = list(re.finditer(r"工作经历|工作经验|職歴|職務経歴|Work Experience|Employment", source, re.I))
    has_heading = bool(heading_matches)
    body = source[heading_matches[-1].end():] if has_heading else source
    if has_heading:
        body = re.split(r"教育背景|教育经历|学歴|Education|技能证书|免許.?資格|自己.?PR|自我评价", body, maxsplit=1, flags=re.I)[0]
    body = re.sub(
        r"平成\s*(\d{1,2})",
        lambda match: str(1988 + int(match.group(1))), body,
    )
    body = re.sub(
        r"令和\s*(\d{1,2})",
        lambda match: str(2018 + int(match.group(1))), body,
    )
    body = re.sub(r"(?<!\d)(\d)\s+(\d)\s+(\d)\s+(\d)(?=\s+\d{1,2}\b)", r"\1\2\3\4", body)
    range_re = re.compile(
        r"(?P<start>(?:19|20)\d{2}\s*(?:年|[./-])\s*(?:1[0-2]|0?[1-9])(?:\s*月)?)\s*"
        r"(?:[-—–～〜~]{1,3}|至|到|till|to)\s*"
        r"(?P<end>(?:(?:19|20)\d{2}\s*(?:年|[./-])\s*(?:1[0-2]|0?[1-9])(?:\s*月)?)|至今|现在|目前|現今|現在|Present|Current|Now|heute)?",
        re.I,
    )
    matches = list(range_re.finditer(body))
    for index, match in enumerate(matches):
        block = body[match.end(): matches[index + 1].start() if index + 1 < len(matches) else min(len(body), match.end() + 1800)]
        previous_end = matches[index - 1].end() if index else 0
        prefix = body[max(previous_end, match.start() - 140):match.start()]
        before_company = company_from_block(prefix)
        after_company = company_from_block(block[:320])
        labeled_before = bool(re.search(r"企业名|企業名|公司名(?:称)?|会社名|勤務先", prefix, re.I))
        if not has_heading and not labeled_before:
            continue
        company = before_company if labeled_before and before_company else (after_company or before_company)
        if not company:
            continue
        row = {field: "" for field in WORK_FIELDS}
        row["company_name"] = company
        row["position"] = position_from_block(block, company)
        row["position_start"] = source_date(match.group("start"))
        row["position_resigned"] = source_date(match.group("end"))
        description = block
        if company in description:
            description = description.split(company, 1)[1]
        description = re.sub(r"^(?:职位|職位|职务|岗位|役職)\s*[:：]?\s*[^。；;]{0,60}", "", description, flags=re.I)
        row["position_responsibilities"] = text(description)[:1800]
        rows.append(row)

    # Japanese chronological tables often list hire/leave as separate rows.
    event_re = re.compile(
        r"(?P<year>(?:19|20)\d{2})\s*(?:年)?\s*(?P<month>1[0-2]|0?[1-9])\s*(?:月)?\s+"
        r"(?P<company>(?:(?:株式会社|有限会社)[^、，]{2,60}|アリババ[（(]?Alibaba[）)]?|IBM\s+China|"
        r".{2,100}?(?:株式会社|有限会社|会社|Company|Inc\.?)))"
        r"(?P<event>.{0,30}?(?:入社|退社))",
        re.I,
    )
    open_rows: dict[str, dict[str, str]] = {}
    for match in event_re.finditer(body):
        company = text(match.group("company")).strip(" ,，、")
        key = compact(company)
        value = f"{int(match.group('year')):04d}年{int(match.group('month')):02d}月01日"
        if "退社" in match.group("event") and key in open_rows:
            open_rows[key]["position_resigned"] = value
        elif "入社" in match.group("event"):
            row = {field: "" for field in WORK_FIELDS}
            row["company_name"] = company
            row["position_start"] = value
            open_rows[key] = row
            rows.append(row)

    if has_heading:
        generic_event_re = re.compile(
            r"(?P<year>(?:19|20)\d{2})\s*(?:年)?\s*(?P<month>1[0-2]|0?[1-9])\s*(?:月)?\s+"
            r"(?P<company>[^。；;]{2,70}?)\s+(?P<event>入社|入職|就職)", re.I,
        )
        for match in generic_event_re.finditer(body):
            company = text(match.group("company")).strip(" ,，、")
            company = re.sub(r"^(?:職歴\s*)+", "", company)
            if len(company) > 60 or COMPANY_NOISE_RE.search(company):
                continue
            row = {field: "" for field in WORK_FIELDS}
            row["company_name"] = company
            row["position_start"] = f"{int(match.group('year')):04d}年{int(match.group('month')):02d}月01日"
            rows.append(row)

    year_range_re = re.compile(
        r"(?P<start>(?:19|20)\d{2})\s*年?\s*(?:[-—–～〜~]{1,3}|至|到)\s*"
        r"(?P<end>(?:(?:19|20)\d{2})\s*年?|至今|现在|目前|Present|Current)?\s+(?P<block>.{2,180})",
        re.I,
    )
    for match in year_range_re.finditer(body):
        company = company_from_block(match.group("block"))
        if not company:
            continue
        row = {field: "" for field in WORK_FIELDS}
        row["company_name"] = company
        row["position"] = position_from_block(match.group("block"), company)
        row["position_start"] = f"{int(match.group('start')):04d}年01月01日"
        if re.fullmatch(r"(?:19|20)\d{2}\s*年?", text(match.group("end"))):
            row["position_resigned"] = f"{int(re.search(r'\d{4}', match.group('end')).group()):04d}年01月01日"
        rows.append(row)

    before = len(rows)
    rows = dedupe_rows(rows, ("company_name", "position_start", "position_resigned", "position"), counters, "source_work")
    if rows:
        counters["recover_source_work_rows"] += len(rows)
    return rows


def recover_education_from_source(source: str, counters: Counter[str]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    heading_matches = list(re.finditer(r"教育背景|教育经历|学歴|Education", source, re.I))
    has_heading = bool(heading_matches)
    body = source[heading_matches[-1].end():] if has_heading else source
    if has_heading:
        body = re.split(r"工作经历|工作经验|職歴|Work Experience|技能证书|免許.?資格|自己.?PR|自我评价", body, maxsplit=1, flags=re.I)[0]
    range_re = re.compile(
        r"(?P<start>(?:19|20)\d{2}\s*(?:年|[./-])\s*(?:1[0-2]|0?[1-9])(?:\s*月)?)\s*"
        r"(?:-|—|–|～|〜|~|至|到|till|to)\s*"
        r"(?P<end>(?:19|20)\d{2}\s*(?:年|[./-])\s*(?:1[0-2]|0?[1-9])(?:\s*月)?)",
        re.I,
    )
    matches = list(range_re.finditer(body))
    for index, match in enumerate(matches):
        block = body[match.end(): matches[index + 1].start() if index + 1 < len(matches) else min(len(body), match.end() + 600)]
        school, remainder = extract_entity(block[:220], "school")
        if not school:
            continue
        row = {field: "" for field in EDU_FIELDS}
        row["school_name"] = school
        if len(row["school_major_name"]) > 140 or re.search(r"仕事内容|プロジェクト管理|工作职责|项目职责", row["school_major_name"], re.I):
            row["school_major_name"] = ""
            counters["clear_contaminated_major"] += 1
        row["school_start_ym"] = source_date(match.group("start"))
        row["school_end_ym"] = source_date(match.group("end"))
        major_match = re.search(r"(?:专业|専攻|学科|Major)\s*[:：]?\s*([^|｜;；。]{1,60})", block, re.I)
        row["school_major_name"] = text(major_match.group(1)) if major_match else ""
        rows.append(row)
    if not rows:
        schools = []
        seen_schools = set()
        for school in embedded_entity_candidates(body, "school"):
            key = compact(school)
            if key and key not in seen_schools:
                seen_schools.add(key)
                schools.append(school)
        broad_ranges = list(re.finditer(
            r"(?P<start>(?:19|20)\d{2})(?:\s*(?:年|[./-])\s*(?P<sm>1[0-2]|0?[1-9]))?\s*"
            r"(?:[-—–～〜~]{1,3}|至|到)\s*(?P<end>(?:19|20)\d{2})(?:\s*(?:年|[./-])\s*(?P<em>1[0-2]|0?[1-9]))?",
            body, re.I,
        ))
        for index, school in enumerate(schools):
            row = {field: "" for field in EDU_FIELDS}
            row["school_name"] = school
            if index < len(broad_ranges):
                match = broad_ranges[index]
                row["school_start_ym"] = f"{int(match.group('start')):04d}年{int(match.group('sm') or 1):02d}月01日"
                row["school_end_ym"] = f"{int(match.group('end')):04d}年{int(match.group('em') or 1):02d}月01日"
            rows.append(row)
    rows = dedupe_rows(rows, ("school_name", "school_start_ym", "school_end_ym"), counters, "source_education")
    if rows:
        counters["recover_source_education_rows"] += len(rows)
    return rows


def sanitize_resume(resume: dict[str, Any], counters: Counter[str]) -> dict[str, Any]:
    resume = scrub_tree(copy.deepcopy(resume), True)
    base = resume.setdefault("base_info", {})
    if isinstance(base, dict):
        base["pr"] = clean_pr(base.get("pr"), counters)
        for field, bounds in (("age", (14, 100)), ("height_cm", (100, 230)), ("weight_kg", (25, 250))):
            original = text(base.get(field))
            base[field] = clean_numeric_text(original, minimum=bounds[0], maximum=bounds[1])
            if original and base[field] != original:
                counters[f"normalize_{field}"] += 1
        birth = text(base.get("birth_date"))
        if birth:
            normalized_birth = clean_date(birth)
            if normalized_birth != birth:
                counters["normalize_birth_date"] += 1
            base["birth_date"] = normalized_birth
    works: list[dict[str, str]] = []
    moved_education: list[dict[str, str]] = []
    for source in resume.get("work_experiences") or []:
        if not isinstance(source, dict):
            counters["drop_nonobject_work"] += 1
            continue
        row = normalize_row(source, WORK_FIELDS)
        if re.search(r"本科校园经历|硕士校园经历|校园经历|学生会经历|社团经历|志愿者服务|义工|義工", text(row.get("company_name")), re.I) and not COMPANY_RE.search(text(row.get("company_name"))):
            counters["drop_campus_activity_as_work"] += 1
            continue
        if re.fullmatch(r"(?:外商投资企业|外资企业|日资企业|日系企业|民营企业|国有企业|政府机关|事业单位|合资企业|独资企业|company nature)", text(row.get("position")), re.I):
            row["position"] = ""
            counters["clear_company_nature_position"] += 1
        company = row["company_name"]
        if PLACEHOLDER_RE.fullmatch(company) or ENTITY_PLACEHOLDER_RE.fullmatch(company):
            company = ""
            counters["clear_work_placeholder"] += 1
        if SUSPICIOUS_COMPANY_START_RE.search(company):
            recovered, remainder = extract_entity(company, "company")
            company = recovered
            row["position_responsibilities"] = append_text(row["position_responsibilities"], remainder)
            counters["repair_suspicious_company_prefix"] += 1
        mixed_company_role = bool(re.search(
            r"(?:有限公司|株式会社|有限会社|\b(?:Co\.?|Ltd\.?|Inc\.?)\b).{1,60}(?:工程师|经理|主管|专员|助理|担当|Manager|Engineer|Specialist)$",
            company, re.I,
        ))
        if mixed_company_role:
            recovered, remainder = split_company_and_remainder(company)
            if recovered:
                company = recovered
                if not row["position"] or len(row["position"]) > 100:
                    row["position"] = remainder
                else:
                    row["position_responsibilities"] = append_text(row["position_responsibilities"], remainder)
                counters["split_role_suffix_from_company"] += 1
        if FIELD_LABEL_RE.search(company):
            recovered, remainder = extract_entity(company, "company")
            company = recovered or re.sub(r"^(?:公司名(?:称)?|会社名|企业名|企業名)\s*[：:]\s*", "", company, flags=re.I)
            row["position_responsibilities"] = append_text(row["position_responsibilities"], remainder)
            counters["repair_labeled_company"] += 1
        if SENTENCE_ENTITY_RE.search(company):
            recovered, remainder = extract_entity(company, "company")
            company = recovered
            row["position_responsibilities"] = append_text(row["position_responsibilities"], remainder)
            counters["repair_sentence_company"] += 1
        school_job = re.search(r"教师|教師|培训师|講師|教练|コーチ|助教|研究生|大学院生|学生研究|实习|実習|Intern|TA\b", row["position"], re.I)
        school_employer = bool(SCHOOL_RE.search(company) and school_job)
        if HTML_RE.search(str(source.get("company_name") or "")) or (len(company) > 80 and not school_employer):
            recovered, remainder = extract_entity(source.get("company_name"), "company")
            company = recovered
            row["position_responsibilities"] = append_text(row["position_responsibilities"], remainder)
            counters["repair_long_or_html_company"] += 1
        if COMPANY_NOISE_RE.search(company) and not re.search(r"毕业生就业指导中心", company):
            recovered, remainder = extract_entity(company, "company")
            company = recovered
            row["position_responsibilities"] = append_text(row["position_responsibilities"], remainder)
            counters["repair_noisy_company"] += 1
        if SCHOOL_RE.search(company) and (DEGREE_RE.search(company + " " + row["position"]) or not row["position"]) and not COMPANY_RE.search(company) and not re.search(r"医院|病院|Hospital", company, re.I) and not school_job:
            row["company_name"] = company
            moved_education.append(education_from_work(row))
            counters["move_work_to_education"] += 1
            continue
        if not company:
            recovered, remainder = extract_entity(row["position"], "company")
            if not recovered:
                recovered, remainder = extract_entity(row["position_responsibilities"], "company")
            if recovered:
                company = recovered
                row["position_responsibilities"] = append_text(row["position_responsibilities"], remainder)
                counters["recover_missing_company"] += 1
        row["company_name"] = company
        employees = text(row.get("company_employees"))
        employee_match = re.search(r"\d+\s*(?:-|~|～|—|至)\s*\d+人|\d+人以上|少于\d+人|未填写", employees)
        industry_match = re.search(r"(?:公司行业|所属行业|業界)\s*[：:]\s*([^|｜]+)", employees, re.I)
        if industry_match and not text(row.get("company_industry")):
            row["company_industry"] = text(industry_match.group(1))
            counters["move_industry_from_employees"] += 1
        if employees and (not employee_match or employee_match.group(0) != employees):
            row["company_employees"] = employee_match.group(0) if employee_match else ""
            counters["normalize_company_employees"] += 1
        industry = text(row.get("company_industry"))
        if re.search(r"(?:元|円|RMB|CNY|JPY|月薪|年薪|/月|per month)", industry, re.I):
            if not text(row.get("position_salary")):
                row["position_salary"] = re.sub(r"^(?:薪酬状况|薪资|月薪)\s*[：:]\s*", "", industry)
            row["company_industry"] = ""
            counters["move_salary_from_industry"] += 1
        original_position = row["position"]
        embedded_company, position_remainder = split_company_and_remainder(original_position)
        if embedded_company:
            company_is_weak = not COMPANY_RE.search(company) and not re.search(r"中心|研究所|银行|集团|事务所|学校|大学|医院|工厂|商店|酒店", company, re.I)
            if not company or company_is_weak:
                row["company_name"] = company = embedded_company
            row["position"] = position_remainder
            original_position = position_remainder
            counters["split_company_from_position"] += 1
        row["position"] = clean_labeled_value(original_position, "position")
        if row["position"] != original_position:
            counters["clean_position"] += 1
        row["position_start"] = clean_date(row["position_start"])
        row["position_resigned"] = clean_date(row["position_resigned"], end=True)
        start, end = date_tuple(row["position_start"]), date_tuple(row["position_resigned"])
        if start and end and start > end:
            row["position_start"], row["position_resigned"] = row["position_resigned"], row["position_start"]
            counters["swap_work_dates"] += 1
        if not company:
            if works:
                previous = works[-1]
                for field in ("position_responsibilities", "position_achievements", "position"):
                    previous[field] = append_text(previous[field], row[field])
                if not previous["position_start"]:
                    previous["position_start"] = row["position_start"]
                if not previous["position_resigned"]:
                    previous["position_resigned"] = row["position_resigned"]
                counters["merge_companyless_work_fragment"] += 1
            else:
                counters["drop_unrecoverable_companyless_work"] += 1
            continue
        works.append(row)

    education: list[dict[str, str]] = []
    moved_work: list[dict[str, str]] = []
    for source in resume.get("education_list") or []:
        if not isinstance(source, dict):
            counters["drop_nonobject_education"] += 1
            continue
        row = normalize_education_metadata(normalize_school_components(split_compound_education(normalize_row(source, EDU_FIELDS), counters), counters), counters)
        school = row["school_name"]
        if re.search(r"^(?:大学)?日本語社|学生会|学生會|企画部部長|社团|クラブ", school):
            counters["drop_campus_activity_as_education"] += 1
            continue
        if re.search(r"^(?:日本)?[^大学学院]{0,35}(?:幼稚园|幼稚園|幼儿园|保育園)", school, re.I) or (re.search(r"幼稚园|幼稚園|幼儿园|保育園", school, re.I) and not re.search(r"大学|学院", school)):
            moved_work.append(work_from_education(row))
            counters["move_internship_education_to_work"] += 1
            continue
        if PLACEHOLDER_RE.fullmatch(school) or ENTITY_PLACEHOLDER_RE.fullmatch(school):
            school = ""
            counters["clear_education_placeholder"] += 1
        if school and SUSPICIOUS_SCHOOL_START_RE.search(school):
            recovered, remainder = extract_entity(school, "school")
            school = recovered
            if remainder and not row["school_major_name"] and len(remainder) <= 140:
                row["school_major_name"] = remainder
            counters["repair_suspicious_school_prefix"] += 1
        if FIELD_LABEL_RE.search(school) or SENTENCE_ENTITY_RE.search(school):
            recovered, remainder = extract_entity(school, "school")
            school = recovered
            if not row["school_major_name"] and len(remainder) <= 140:
                row["school_major_name"] = remainder
            counters["repair_labeled_or_sentence_school"] += 1
        if HTML_RE.search(str(source.get("school_name") or "")) or len(school) > 100:
            recovered, remainder = extract_entity(source.get("school_name"), "school")
            school = recovered
            if not row["school_major_name"] and len(remainder) <= 140:
                row["school_major_name"] = remainder
            counters["repair_long_or_html_school"] += 1
        if SCHOOL_NOISE_RE.search(school):
            recovered, remainder = extract_entity(school, "school")
            school = recovered
            if not row["school_major_name"] and len(remainder) <= 140:
                row["school_major_name"] = remainder
            counters["repair_noisy_school"] += 1
        row["school_name"] = school
        original_major = row["school_major_name"]
        row["school_major_name"] = clean_labeled_value(original_major, "school_major_name")
        if row["school_major_name"] != original_major:
            counters["clean_school_major"] += 1
        major = text(row.get("school_major_name"))
        degree_major = re.match(
            r"^(?P<degree>Master of (?:Science|Arts|Engineering|Business Administration)|Bachelor of (?:Science|Arts|Engineering))"
            r"(?:\s*,?\s*Major in\s+(?P<major>.+))?$",
            major, re.I,
        )
        if degree_major:
            if not row.get("school_degree_type"):
                row["school_degree_type"] = degree_major.group("degree")
            row["school_major_name"] = text(degree_major.group("major"))
            counters["split_degree_from_major"] += 1
        if COMPANY_RE.search(school) and not SCHOOL_RE.search(school):
            moved_work.append(work_from_education(row))
            counters["move_education_to_work"] += 1
            continue
        if not school:
            recovered, remainder = extract_entity(row["school_major_name"], "school")
            if recovered:
                row["school_name"] = school = recovered
                row["school_major_name"] = remainder
                counters["recover_missing_school"] += 1
        row["school_start_ym"] = clean_month_date(row["school_start_ym"])
        row["school_end_ym"] = clean_month_date(row["school_end_ym"], end=True)
        start, end = date_tuple(row["school_start_ym"]), date_tuple(row["school_end_ym"])
        if start and end and start > end:
            row["school_start_ym"], row["school_end_ym"] = row["school_end_ym"], row["school_start_ym"]
            counters["swap_education_dates"] += 1
        if not school:
            counters["drop_unrecoverable_schoolless_education"] += 1
            continue
        education.append(row)

    works.extend(moved_work)
    education.extend(moved_education)

    # Re-check converted rows; they bypassed the first loop's field-specific checks.
    final_works: list[dict[str, str]] = []
    final_education: list[dict[str, str]] = []
    for row in works:
        company = text(row.get("company_name"))
        if re.search(r"本科校园经历|硕士校园经历|校园经历|学生会经历|社团经历|志愿者服务|義工", company, re.I) and not COMPANY_RE.search(company):
            counters["drop_campus_activity_as_work"] += 1
            continue
        school_job = re.search(r"教师|教師|培训师|講師|教练|コーチ|助教|研究生|大学院生|学生研究|实习|実習|Intern|TA\b", text(row.get("position")), re.I)
        if SCHOOL_RE.search(company) and (DEGREE_RE.search(company + " " + text(row.get("position"))) or not text(row.get("position"))) and not COMPANY_RE.search(company) and not re.search(r"医院|病院|Hospital", company, re.I) and not school_job:
            final_education.append(education_from_work(row))
            counters["final_move_work_to_education"] += 1
            continue
        if (
            (len(company) > 80 and not school_job)
            or SUSPICIOUS_COMPANY_START_RE.search(company)
            or SENTENCE_ENTITY_RE.search(company)
            or ENTITY_PLACEHOLDER_RE.fullmatch(company)
            or (COMPANY_NOISE_RE.search(company) and not re.search(r"毕业生就业指导中心", company))
        ):
            recovered, remainder = extract_entity(company, "company")
            company = recovered
            row["position_responsibilities"] = append_text(row.get("position_responsibilities", ""), remainder)
            counters["final_repair_company"] += 1
        if company and (
            SUSPICIOUS_COMPANY_START_RE.search(company)
            or SENTENCE_ENTITY_RE.search(company)
            or ENTITY_PLACEHOLDER_RE.fullmatch(company)
            or re.match(r"^(?:参与公司|工作内容|公司业务范围|公司性质|所在公司|任职公司|此时公司)\b", company)
        ):
            company = ""
        if not company:
            counters["final_drop_bad_work"] += 1
            continue
        row["company_name"] = company
        start, end = date_tuple(row.get("position_start")), date_tuple(row.get("position_resigned"))
        if start and end and start > end:
            row["position_start"], row["position_resigned"] = row["position_resigned"], row["position_start"]
            counters["final_swap_work_dates"] += 1
        if row.get("position_resigned") and text(row.get("status")).casefold() in {
            "在职", "在籍", "就职中", "勤務中", "current", "present"
        }:
            row["status"] = {"ja": "退職", "en": "Former", "de": "Beendet"}.get(
                text(resume.get("resume_language")), "离职"
            )
            counters["repair_ended_work_status"] += 1
        position = text(row.get("position"))
        if re.fullmatch(r"(?:外商投资企业|外资企业|日资企业|日系企业|民营企业|国有企业|政府机关|事业单位|合资企业|独资企业|company nature)", position, re.I):
            row["position"] = ""
            position = ""
            counters["clear_company_nature_position"] += 1
        if re.fullmatch(r"所在部门|所属部门|部署|部門", position):
            row["position"] = ""
            counters["clear_department_label_position"] += 1
        elif re.match(r"^(?:部署|部门|所属部门)\s*[：:]", position):
            if not text(row.get("position_dept")):
                row["position_dept"] = re.sub(r"^(?:部署|部门|所属部门)\s*[：:]\s*", "", position)
            row["position"] = ""
            counters["move_labeled_department_from_position"] += 1
        elif re.fullmatch(
            r"[^，。；;]{1,45}(?:部|課|科|处|室|中心|本部|部门)(?:[、・/][^，。；;]{1,45}(?:部|課|科|处|室|中心|本部|部门))*",
            position,
        ) and not re.search(
            r"经理|主管|主任|专员|助理|工程师|教师|翻译|销售|担当|研究员|顾问|总务|会计|アシスタント|"
            r"Manager|Engineer|Teacher|Translator|Interpreter|Sales|Assistant|Specialist|Researcher|Consultant",
            position, re.I,
        ):
            if not text(row.get("position_dept")):
                row["position_dept"] = position
            row["position"] = ""
            counters["move_department_from_position"] += 1
        final_works.append(row)
    for row in education:
        school = text(row.get("school_name"))
        if COMPANY_RE.search(school) and not SCHOOL_RE.search(school):
            final_works.append(work_from_education(row))
            counters["final_move_education_to_work"] += 1
            continue
        if len(school) > 90 or SCHOOL_NOISE_RE.search(school) or SUSPICIOUS_SCHOOL_START_RE.search(school):
            recovered, remainder = extract_entity(school, "school")
            school = recovered
            if not row.get("school_major_name") and len(remainder) <= 140:
                row["school_major_name"] = remainder
            counters["final_repair_school"] += 1
        if not school:
            counters["final_drop_bad_education"] += 1
            continue
        if SCHOOL_NOISE_RE.search(school) or SUSPICIOUS_SCHOOL_START_RE.search(school) or ENTITY_PLACEHOLDER_RE.fullmatch(school):
            counters["final_drop_bad_education"] += 1
            continue
        row["school_name"] = school
        start, end = date_tuple(row.get("school_start_ym")), date_tuple(row.get("school_end_ym"))
        if start and end and start > end:
            row["school_start_ym"], row["school_end_ym"] = row["school_end_ym"], row["school_start_ym"]
            counters["final_swap_education_dates"] += 1
        final_education.append(row)
    school_by_key = {compact(row.get("school_name")): row for row in final_education if compact(row.get("school_name"))}
    overlap_cleaned_works: list[dict[str, str]] = []
    for row in final_works:
        key = compact(row.get("company_name"))
        school_row = school_by_key.get(key)
        position = text(row.get("position"))
        legitimate_school_job = bool(re.search(
            r"助教|讲师|講師|教授|研究员|研究員|管理员|管理員|TA\b|Assistant|Professor|Lecturer|Researcher",
            position, re.I,
        ))
        suspicious_overlap = bool(
            school_row
            and not COMPANY_RE.search(text(row.get("company_name")))
            and not legitimate_school_job
            and (
                not text(row.get("position_start"))
                or not position
                or compact(position) == compact(school_row.get("school_major_name"))
                or DEGREE_RE.search(text(row.get("company_name")) + " " + position)
                or len(text(row.get("company_name"))) <= 3
                or not re.search(r"经理|工程师|担当|主管|专员|営業|销售|開発|开发|顾问|研究生|大学院生|学生研究|Consultant|Engineer|Manager", position, re.I)
            )
        )
        if suspicious_overlap:
            counters["drop_education_duplicate_from_work"] += 1
            continue
        overlap_cleaned_works.append(row)
    final_works = overlap_cleaned_works
    post_cleaned_education: list[dict[str, str]] = []
    for row in final_education:
        school = text(row.get("school_name"))
        if re.search(r"奖学金|奨学金", school, re.I):
            school = ""
        elif SCHOOL_NOISE_RE.search(school) or len(school) > 90:
            recovered, _ = extract_entity(school, "school")
            school = recovered
        invalid_school = bool(
            PLACEHOLDER_RE.fullmatch(school)
            or re.search(r"携帯番号|手机|電話|身份证|身分証|職\s*歴|現在状況|入学のため退職|大学を卒業してから|講師として|働き", school, re.I)
            or re.match(r"^\s*[-—–]?\s*(?:19|20)\d{2}[./年]", school)
            or re.fullmatch(r"学歴(?:\s*[（(].*)?", school, re.I)
            or re.fullmatch(r"学校\s*[、,，/]\s*专业", school)
            or (re.search(r"企画部部長|学生会|社团|主席|部长", school) and not SCHOOL_RE.search(school))
            or re.match(r"^(?:私は|我(?:是|在|从)|本人|自己紹介|卒業から|今まで)", school, re.I)
            or re.search(r"(?:工程操作員|工程师|经理|担当|調査員|作業員|负责人)$", school)
            or (not text(row.get("school_start_ym")) and not text(row.get("school_end_ym")) and re.search(r"内容\s*[：:]|について|取り組", school))
        )
        if invalid_school:
            school = ""
        if not school:
            counters["post_drop_bad_education"] += 1
            continue
        row["school_name"] = school
        if len(text(row.get("school_major_name"))) > 140 or re.search(r"仕事内容|プロジェクト管理|工作职责|项目职责", text(row.get("school_major_name")), re.I):
            row["school_major_name"] = ""
            counters["post_clear_contaminated_major"] += 1
        post_cleaned_education.append(row)
    final_education = [row for row in post_cleaned_education if not is_low_education(row, counters)]
    move_language_certificates(resume, counters)
    sanitize_language_list(resume, counters)
    sanitize_named_collections(resume, counters)
    normalize_collection_sequences(resume, counters)
    resume["work_experiences"] = dedupe_rows(final_works, ("company_name", "position_start", "position_resigned", "position"), counters, "work")
    resume["education_list"] = dedupe_semantic_education(
        dedupe_rows(final_education, ("school_name", "school_start_ym", "school_end_ym"), counters, "education"), counters
    )
    for collection in RESUME_LISTS:
        if collection not in {"work_experiences", "education_list"}:
            rows = resume.get(collection)
            resume[collection] = rows if isinstance(rows, list) else []
    normalize_resume_schema(resume, counters)
    return resume


def sanitize_trusted_resume(resume: dict[str, Any], counters: Counter[str]) -> dict[str, Any]:
    """Schema/date cleanup for a reviewed GPT candidate without re-parsing it."""
    resume = scrub_tree(copy.deepcopy(resume), True)
    base = resume.setdefault("base_info", {})
    if isinstance(base, dict):
        base["pr"] = clean_pr(base.get("pr"), counters)
        base["email"] = clean_email(base.get("email"))
        base["nationality"] = clean_nationality(base.get("nationality"))
        if text(base.get("birth_date")):
            base["birth_date"] = clean_date(base.get("birth_date"))
    works = []
    language_code = text(resume.get("resume_language"))
    for source in resume.get("work_experiences") or []:
        if not isinstance(source, dict):
            continue
        row = normalize_row(source, WORK_FIELDS)
        if re.search(r"本科校园经历|硕士校园经历|校园经历|学生会经历|社团经历|志愿者服务|义工|義工", text(row.get("company_name")), re.I) and not COMPANY_RE.search(text(row.get("company_name"))):
            counters["drop_campus_activity_as_work"] += 1
            continue
        if re.fullmatch(r"(?:外商投资企业|外资企业|日资企业|日系企业|民营企业|国有企业|政府机关|事业单位|合资企业|独资企业|company nature)", text(row.get("position")), re.I):
            row["position"] = ""
            counters["clear_company_nature_position"] += 1
        row["position_start"] = clean_date(row.get("position_start"))
        row["position_resigned"] = clean_date(row.get("position_resigned"), end=True)
        if row["position_resigned"] and text(row.get("status")).casefold() in {
            "在职", "在籍", "就职中", "勤務中", "current", "present"
        }:
            row["status"] = {"ja": "退職", "en": "Former", "de": "Beendet"}.get(language_code, "离职")
        works.append(row)
    education = []
    for source in resume.get("education_list") or []:
        if not isinstance(source, dict):
            continue
        row = normalize_education_metadata(normalize_school_components(split_compound_education(normalize_row(source, EDU_FIELDS), counters), counters), counters)
        row["school_start_ym"] = clean_month_date(row.get("school_start_ym"))
        row["school_end_ym"] = clean_month_date(row.get("school_end_ym"), end=True)
        if re.search(r"^(?:日本)?[^大学学院]{0,35}(?:幼稚园|幼稚園|幼儿园|保育園)", text(row.get("school_name")), re.I) or (re.search(r"幼稚园|幼稚園|幼儿园|保育園", text(row.get("school_name")), re.I) and not re.search(r"大学|学院", text(row.get("school_name")))):
            counters["drop_internship_as_education"] += 1
            continue
        if not is_low_education(row, counters):
            education.append(row)
    resume["work_experiences"] = dedupe_rows(works, ("company_name", "position_start", "position_resigned", "position"), counters, "trusted_work")
    resume["education_list"] = dedupe_semantic_education(
        dedupe_rows(education, ("school_name", "school_start_ym", "school_end_ym"), counters, "trusted_education"), counters
    )
    move_language_certificates(resume, counters)
    sanitize_language_list(resume, counters)
    sanitize_named_collections(resume, counters)
    normalize_collection_sequences(resume, counters)
    for collection in RESUME_LISTS:
        if collection not in {"work_experiences", "education_list"}:
            rows = resume.get(collection)
            resume[collection] = rows if isinstance(rows, list) else []
    normalize_resume_schema(resume, counters)
    return resume


def dedupe_rows(rows: list[dict[str, str]], fields: tuple[str, ...], counters: Counter[str], label: str) -> list[dict[str, str]]:
    output: list[dict[str, str]] = []
    by_key: dict[tuple[str, ...], dict[str, str]] = {}
    for row in rows:
        key = tuple(compact(row.get(field)) for field in fields)
        if key in by_key:
            existing = by_key[key]
            for field, value in row.items():
                if not existing.get(field):
                    existing[field] = value
                elif field in {"position_responsibilities", "position_achievements"}:
                    existing[field] = append_text(existing[field], value)
            counters[f"dedupe_{label}"] += 1
            continue
        by_key[key] = row
        output.append(row)
    return output


def is_low_education(row: dict[str, Any], counters: Counter[str] | None = None) -> bool:
    joined = " ".join(text(row.get(field)) for field in ("school_name", "school_degree_type", "school_education_type"))
    low = bool(re.search(r"小学|初中|中学|中學|中学校|中专|中等专(?:业)?学校|高中|高級中学|高级中学|高等学校|高校(?:生)?", joined, re.I))
    if low and counters is not None:
        counters["drop_low_education"] += 1
    return low


def school_core(value: Any) -> str:
    current = compact(value)
    current = current.translate(str.maketrans({"語": "语", "學": "学", "國": "国", "陸": "陆", "東": "东", "業": "业", "職": "职"}))
    current = re.sub(r"^(?:日本|中国)", "", current)
    current = re.sub(r"(?:四年制|4年制)$", "", current)
    return current


def dedupe_semantic_education(rows: list[dict[str, str]], counters: Counter[str]) -> list[dict[str, str]]:
    output: list[dict[str, str]] = []
    for row in rows:
        core = school_core(row.get("school_name"))
        duplicate_index = None
        for index, existing in enumerate(output):
            other = school_core(existing.get("school_name"))
            same_school = core and other and (core == other or (min(len(core), len(other)) >= 4 and (core in other or other in core)))
            row_degree = compact(row.get("school_degree_type"))
            existing_degree = compact(existing.get("school_degree_type"))
            same_degree = row_degree == existing_degree or not row_degree or not existing_degree
            sparse = (
                not text(row.get("school_start_ym")) or not text(existing.get("school_start_ym"))
                or not text(row.get("school_end_ym")) or not text(existing.get("school_end_ym"))
                or not text(row.get("school_major_name")) or not text(existing.get("school_major_name"))
            )
            same_dates = compact(row.get("school_start_ym")) == compact(existing.get("school_start_ym")) and compact(row.get("school_end_ym")) == compact(existing.get("school_end_ym"))
            if same_school and same_degree and (same_dates or sparse):
                duplicate_index = index
                break
        if duplicate_index is None:
            output.append(row)
            continue
        existing = output[duplicate_index]
        existing_score = sum(bool(text(existing.get(field))) for field in ("school_major_name", "school_degree_type", "school_start_ym", "school_end_ym"))
        row_score = sum(bool(text(row.get(field))) for field in ("school_major_name", "school_degree_type", "school_start_ym", "school_end_ym"))
        if row_score > existing_score:
            output[duplicate_index] = row
        counters["dedupe_semantic_education"] += 1
    return output


def degree_rank(row: dict[str, Any]) -> int:
    value = text(row.get("school_degree_rank"))
    if value.isdigit():
        return int(value)
    joined = text(row.get("school_degree_type")) + " " + text(row.get("school_name"))
    if re.search(r"博士|Ph\.?D|Doctor", joined, re.I): return 6
    if re.search(r"硕士|修士|Master|MBA", joined, re.I): return 5
    if re.search(r"本科|学士|Bachelor|大学|学部", joined, re.I): return 4
    if re.search(r"大专|专科|短大|Associate", joined, re.I): return 3
    return 1


def latest_work(rows: list[dict[str, Any]]) -> dict[str, str]:
    empty = {field: "" for field in CURRENT_FIELDS}
    if not rows:
        return empty
    latest = max(rows, key=lambda row: date_tuple(row.get("position_resigned")) or date_tuple(row.get("position_start")) or (0, 0, 0))
    return {field: copy.deepcopy(latest.get(field, "")) for field in CURRENT_FIELDS}


def highest_education(rows: list[dict[str, Any]]) -> dict[str, str]:
    empty = {field: "" for field in EDU_FIELDS}
    if not rows:
        return empty
    return copy.deepcopy(max(rows, key=lambda row: (degree_rank(row), date_tuple(row.get("school_end_ym")) or (0, 0, 0))))


def detected_language(value: str) -> str:
    kana = len(re.findall(r"[\u3040-\u30ff]", value))
    han = len(re.findall(r"[\u3400-\u9fff]", value))
    latin = len(re.findall(r"\b[A-Za-z]{2,}\b", value))
    if kana >= 10:
        return "ja"
    if latin >= 50 and latin > han * 2:
        return "en"
    return "zh"


def repair_payload(
    payload: dict[str, Any], filename: str, counters: Counter[str], source_texts: list[str],
    source_index: dict[str, str],
    override: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = scrub_tree(copy.deepcopy(payload))
    source = payload.setdefault("source", {})
    source_files = [row for row in (source.get("source_files") or []) if isinstance(row, dict)]
    merge_trace = []
    for row in source_files:
        source_filename = str(row.get("filename") or Path(str(row.get("input_path") or "")).name).strip()
        body = source_index.get(source_filename.casefold(), "")
        languages = detect_resume_languages(source_filename, body)
        document_type = detect_document_type(source_filename, body)
        row["resume_languages"] = languages
        row["document_type"] = document_type
        merge_trace.append({
            "filename": source_filename,
            "input_path": text(row.get("input_path")),
            "sha256": text(row.get("sha256")),
            "resume_languages": languages,
            "document_type": document_type,
        })
    source["source_files"] = source_files
    source["is_merged_candidate"] = len(source_files) > 1
    source["merged_document_count"] = len(source_files)
    source["merge_trace"] = merge_trace
    structured = payload.setdefault("structured_data", {})
    selected_zh = text(
        ((payload.get("extraction") or {}).get("selected_language_sources") or {}).get("zh")
    )
    resumes = [
        (sanitize_trusted_resume(row, counters) if index == 0 and selected_zh.startswith("gpt_reference:") else sanitize_resume(row, counters))
        for index, row in enumerate(structured.get("resumes") or []) if isinstance(row, dict)
    ]
    if not resumes:
        return payload
    candidate_name = filename.split("_", 1)[0]
    primary_base = resumes[0].setdefault("base_info", {})
    current_name = text(primary_base.get("full_name"))
    if not current_name or GENERIC_NAME_RE.search(current_name):
        source_names = [text(row.get("filename")) for row in ((payload.get("source") or {}).get("source_files") or []) if isinstance(row, dict)]
        honorific = next((match.group(1) + match.group(2) for source_name in source_names for match in [re.search(r"([\u3400-\u9fff])\s*(先生|女士)", source_name)] if match), "")
        primary_base["full_name"] = honorific or candidate_name
        counters["repair_primary_name"] += 1
    for resume in resumes:
        base = resume.setdefault("base_info", {})
        name = text(base.get("full_name"))
        if not name or GENERIC_NAME_RE.search(name):
            base["full_name"] = primary_base.get("full_name", candidate_name)
            counters["repair_variant_name"] += 1
        base["email"] = clean_email(base.get("email"))
        nationality = text(base.get("nationality"))
        base["nationality"] = clean_nationality(nationality)
        if nationality and not base["nationality"]:
            counters["clear_invalid_nationality"] += 1
        phone_digits = re.sub(r"\D", "", text(base.get("phone")))
        if text(base.get("phone")) and not 8 <= len(phone_digits) <= 16:
            base["phone"] = text(primary_base.get("phone")) if resume is not resumes[0] else ""
        resume_language = text(resume.get("resume_language")) or "zh"
        matching_sources = [value for value in source_texts if detected_language(value) == resume_language]
        matching_sources = matching_sources or source_texts
        if not (resume.get("work_experiences") or []):
            recovered_options = [recover_work_from_source(value, counters) for value in matching_sources]
            recovered = max(recovered_options, key=len, default=[])
            if not recovered and matching_sources != source_texts:
                recovered = max((recover_work_from_source(value, counters) for value in source_texts), key=len, default=[])
            if recovered:
                resume["work_experiences"] = recovered
        if not (resume.get("education_list") or []):
            recovered_options = [recover_education_from_source(value, counters) for value in matching_sources]
            recovered = max(recovered_options, key=len, default=[])
            if not recovered and matching_sources != source_texts:
                recovered = max((recover_education_from_source(value, counters) for value in source_texts), key=len, default=[])
            if recovered:
                resume["education_list"] = recovered
        # Source fallback rows must pass through the same semantic filters as
        # parser rows; otherwise education lines can leak back into work data.
        recleaned = sanitize_resume(resume, counters)
        resume.clear()
        resume.update(recleaned)
    # A translated variant often preserves a contact that was polluted in the
    # primary parsed row. Promote a valid variant contact before snapshots are
    # rebuilt, while leaving genuinely absent contacts empty.
    primary_base = resumes[0].setdefault("base_info", {})
    valid_emails = [clean_email((row.get("base_info") or {}).get("email")) for row in resumes]
    valid_emails = [value for value in valid_emails if value]
    if not clean_email(primary_base.get("email")) and valid_emails:
        primary_base["email"] = valid_emails[0]
        counters["recover_primary_email_from_variant"] += 1
    if override:
        by_language = {text(row.get("resume_language")): row for row in resumes}
        for lang, changes in (override.get("resumes") or {}).items():
            resume = by_language.get(lang)
            if resume is None or not isinstance(changes, dict):
                continue
            for collection, rows in changes.items():
                if collection in RESUME_LISTS and isinstance(rows, list):
                    resume[collection] = copy.deepcopy(rows)
            recleaned = sanitize_resume(resume, counters)
            resume.clear()
            resume.update(recleaned)
            counters["apply_manual_resume_override"] += 1
        for lang, base_changes in (override.get("base_info") or {}).items():
            resume = by_language.get(lang)
            if resume is None or not isinstance(base_changes, dict):
                continue
            base = resume.setdefault("base_info", {})
            for field, value in base_changes.items():
                base[field] = text(value)
            base["email"] = clean_email(base.get("email"))
            counters["apply_manual_base_override"] += 1
        semantic_review = payload.setdefault("extraction", {}).setdefault("semantic_review", {})
        for flag in (
            "source_work_absent", "source_education_absent", "pdf_verified_phone", "pdf_verified_email",
            "pdf_verified_work", "pdf_verified_education", "pdf_verified_name", "pdf_verified_base",
            "pdf_verified_expected", "pdf_verified_certificates", "pdf_verified_languages",
            "pdf_verified_skills", "pdf_verified_training", "pdf_verified_projects",
            "gpt_structure_review_closed",
        ):
            if flag in override:
                semantic_review[flag] = bool(override[flag])
    source_file_count = len([
        row for row in ((payload.get("source") or {}).get("source_files") or []) if isinstance(row, dict)
    ])
    if len(resumes) > 1 and (source_file_count == 1 or selected_zh.startswith("gpt_reference:")):
        reconcile_single_source_variants(
            resumes, source_texts, counters, prefer_primary=selected_zh.startswith("gpt_reference:")
        )
    # Reconciliation can copy sparse translated rows back into a variant. Run
    # one final semantic pass so duplicate schools and misplaced activities do
    # not survive merely because alignment happened after the first cleanup.
    for index, resume in enumerate(resumes):
        cleaned = sanitize_resume(resume, counters)
        resumes[index] = cleaned
    if len(resumes) > 1 and (source_file_count == 1 or selected_zh.startswith("gpt_reference:")):
        reconcile_single_source_variants(resumes, source_texts, counters, prefer_primary=True)
    clear_cross_language_clones(resumes, counters)
    source_evidence = "\n".join(source_texts)
    for resume in resumes:
        base = resume.get("base_info") or {}
        # Do not infer children from marital status or age.  Keep it only when
        # the canonical source contains the actual value.
        children = text(base.get("children_status"))
        if children and compact(children) not in compact(source_evidence):
            base["children_status"] = ""
            counters["clear_untraceable_children_status"] += 1
        for work in resume.get("work_experiences") or []:
            if not isinstance(work, dict):
                continue
            responsibility = text(work.get("position_responsibilities"))
            if responsibility and (re.fullmatch(r"(?:月\)?\s*)?(?:[-—–~～至]\s*)?(?:現在|至今)?\s*(?:中国)?", responsibility, re.I) or re.fullmatch(
                r"月\)?\s*(?:区域经理|區域經理)", responsibility
            )):
                work["position_responsibilities"] = ""
                counters["clear_date_fragment_responsibility"] += 1
            if re.fullmatch(r"日系\s*(?:所属部|所屬部)", text(work.get("position_dept")), re.I):
                work["position_dept"] = ""
                counters["clear_company_nature_department_fragment"] += 1
            position = text(work.get("position"))
            role_location = re.fullmatch(r"(.+?(?:兼职|兼職)\)?)\s+(姬路|神户|神戶)", position)
            if role_location:
                work["position"] = role_location.group(1)
                counters["strip_location_from_position"] += 1
            if re.fullmatch(r"门\s+日本东京", position):
                work["position"] = "程序工程师"
                counters["repair_fragmented_position"] += 1
        repaired_projects = []
        for project in resume.get("project_list") or []:
            if not isinstance(project, dict):
                continue
            recovered = recover_project_name(copy.deepcopy(project), source_evidence, counters)
            if recovered is not None:
                repaired_projects.append(recovered)
        resume["project_list"] = repaired_projects
    # Manual PDF/Word-reviewed rows are authoritative.  Re-apply them after
    # cross-language alignment, which may otherwise replace a reviewed entity
    # with a shorter value copied from another language variant.
    if override:
        by_language = {text(row.get("resume_language")): row for row in resumes}
        for lang, changes in (override.get("resumes") or {}).items():
            resume = by_language.get(lang)
            if resume is None or not isinstance(changes, dict):
                continue
            for collection, rows in changes.items():
                if collection in RESUME_LISTS and isinstance(rows, list):
                    resume[collection] = copy.deepcopy(rows)
            cleaned = sanitize_resume(resume, counters)
            resume.clear()
            resume.update(cleaned)
            counters["reapply_manual_resume_override_final"] += 1
        for lang, base_changes in (override.get("base_info") or {}).items():
            resume = by_language.get(lang)
            if resume is None or not isinstance(base_changes, dict):
                continue
            base = resume.setdefault("base_info", {})
            for field, value in base_changes.items():
                base[field] = text(value)
            base["email"] = clean_email(base.get("email"))
            counters["reapply_manual_base_override_final"] += 1
    # Final schema consistency pass. Overrides and cross-language alignment run
    # after the individual sanitizers, so month-granularity fields must be
    # normalized once more here.
    for resume in resumes:
        for row in resume.get("education_list") or []:
            if isinstance(row, dict):
                row["school_start_ym"] = clean_month_date(row.get("school_start_ym"))
                row["school_end_ym"] = clean_month_date(row.get("school_end_ym"), end=True)
        for collection in ("project_list", "training_list"):
            for row in resume.get(collection) or []:
                if isinstance(row, dict):
                    row["start_ym"] = clean_month_date(row.get("start_ym"))
                    row["end_ym"] = clean_month_date(row.get("end_ym"), end=True)
        normalize_collection_sequences(resume, counters)
    structured["resumes"] = resumes
    primary = resumes[0]
    structured["base_info"] = copy.deepcopy(primary.get("base_info") or {})
    structured["expected_info"] = copy.deepcopy(
        (primary.get("expected_list") or [{}])[0]
        if primary.get("expected_list") else {field: "" for field in EXPECTED_FIELDS}
    )
    structured["current_info"] = latest_work(primary.get("work_experiences") or [])
    structured["education_info"] = highest_education(primary.get("education_list") or [])
    # Lists belong to each language resume.  Keeping another copy beside
    # ``resumes`` creates two competing sources of truth and was never part of
    # the consumer contract.
    for collection in RESUME_LISTS:
        structured.pop(collection, None)
    payload["raw_text"] = "\n\n".join(value for value in source_texts if value).strip()
    payload.setdefault("extraction", {})["semantic_repair_version"] = VERSION
    payload.setdefault("extraction", {})["raw_text_source"] = "canonical_deduplicated_pdf_word_html_text"
    payload.setdefault("dates", {})["sys_updated_date"] = datetime.now().astimezone().isoformat(timespec="seconds")
    quality = payload.setdefault("quality", {})
    if ((payload.get("extraction") or {}).get("semantic_review") or {}).get("gpt_structure_review_closed"):
        quality["warnings"] = [
            value for value in (quality.get("warnings") or [])
            if value != "gpt_translation_structure_mismatch"
        ]
    quality["has_work"] = bool(primary.get("work_experiences"))
    quality["work_count"] = len(primary.get("work_experiences") or [])
    quality["has_education"] = bool(primary.get("education_list"))
    quality["education_count"] = len(primary.get("education_list") or [])
    quality["raw_text_length"] = len(payload.get("raw_text") or "")
    return payload


def atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".tmp", dir=path.parent, delete=False) as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
        temporary = Path(stream.name)
    temporary.replace(path)


def main() -> int:
    cfg = parse_args()
    mapping = json.loads(cfg.map.read_text(encoding="utf-8-sig"))
    source_index = source_text_index(mapping)
    overrides_payload = json.loads(cfg.overrides.read_text(encoding="utf-8-sig")) if cfg.overrides.is_file() else {}
    overrides = overrides_payload.get("records") or {}
    counters: Counter[str] = Counter()
    files = sorted(cfg.root.glob("*.json"), key=lambda path: path.name.casefold())
    changed = 0
    records = []
    for path in files:
        original = json.loads(path.read_text(encoding="utf-8-sig"))
        before = json.dumps(original, ensure_ascii=False, sort_keys=True)
        repaired = repair_payload(
            original, path.name, counters, payload_source_texts(original, source_index),
            source_index,
            overrides.get(path.name),
        )
        after = json.dumps(repaired, ensure_ascii=False, sort_keys=True)
        is_changed = before != after
        if is_changed:
            changed += 1
            if cfg.apply:
                atomic_json(path, repaired)
        records.append({"filename": path.name, "changed": is_changed})
    report = {
        "version": VERSION,
        "generated_at": datetime.now().astimezone().isoformat(),
        "mode": "apply" if cfg.apply else "dry_run",
        "root": str(cfg.root.resolve()),
        "file_count": len(files),
        "changed_file_count": changed,
        "repair_counts": dict(counters.most_common()),
        "records": records,
    }
    atomic_json(cfg.report, report)
    print(json.dumps({key: value for key, value in report.items() if key != "records"}, ensure_ascii=False, indent=2))
    print(f"report={cfg.report.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
