from __future__ import annotations
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1] / "common"))
import rc_config as _rc  # noqa: E402  项目统一配置（python/common/rc_config.py）
# EN: noqa: E402  project-wide configuration (python/common/rc_config.py)
# JA: noqa: E402  プロジェクト共通設定（python/common/rc_config.py）

import argparse
import csv
import html
import json
import re
import tempfile
import unicodedata
import zipfile
import math
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

try:
    import fitz
except ImportError:  # pragma: no cover
    fitz = None

from pdf_raw_text_v2 import build_source_text_index, payload_raw_text


ROOT = _rc.project_root()
PDF_ROOT = ROOT / _rc.dirname("complete-transfered-htmls") / "pdf"
DEFAULT_JSON_ROOT = ROOT / _rc.dirname("complete-transfered-jsons") / "pdf" / "new"
DEFAULT_MAP = PDF_ROOT / "rebuild-work" / "pdf_rebuild_map.v2.json"
DEFAULT_REPORT = PDF_ROOT / "rebuild-reports" / "pdf_json_field_strict_audit.v2.json"
DEFAULT_CSV = PDF_ROOT / "rebuild-reports" / "pdf_json_field_strict_audit.v2.csv"
VERSION = "pdf-json-field-strict-audit-v2.0.0"

RESUME_LISTS = (
    "expected_list", "work_experiences", "education_list", "certificate_list",
    "language_list", "skills_list", "training_list", "project_list",
    "communication_list",
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
    "employment_type", "annual_salary_min", "annual_salary_max", "status",
    "position_start", "position_resigned", "resigned_reason",
    "position_responsibilities", "position_achievements",
)
CURRENT_FIELDS = WORK_FIELDS[:15]
EDUCATION_FIELDS = (
    "school_name", "school_major_name", "school_degree_type", "school_degree_rank",
    "school_education_type", "school_start_ym", "school_end_ym",
)
CERTIFICATE_FIELDS = ("certificate_name", "certificate_type", "certificate_time")
LANGUAGE_FIELDS = ("language_name", "language_level", "language_certificate", "language_certificate_time")
SKILL_FIELDS = ("skill_name", "skill_level")
TRAINING_FIELDS = ("sequence_no", "organization_name", "training_name", "start_ym", "end_ym", "certificate_name", "description")
PROJECT_FIELDS = ("sequence_no", "fingerprint", "project_name", "company_or_client", "role_name", "start_ym", "end_ym", "description", "responsibilities", "achievements", "keywords")
COMMUNICATION_FIELDS = ("communicate_time", "communicate_content")
COLLECTION_FIELDS = {
    "expected_list": EXPECTED_FIELDS,
    "work_experiences": WORK_FIELDS,
    "education_list": EDUCATION_FIELDS,
    "certificate_list": CERTIFICATE_FIELDS,
    "language_list": LANGUAGE_FIELDS,
    "skills_list": SKILL_FIELDS,
    "training_list": TRAINING_FIELDS,
    "project_list": PROJECT_FIELDS,
    "communication_list": COMMUNICATION_FIELDS,
}

SEVERITY = {"low": 1, "medium": 2, "high": 3, "critical": 4}
W_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
DATE_RE = re.compile(r"^(?:19|20)\d{2}年(?:0[1-9]|1[0-2])月(?:0[1-9]|[12]\d|3[01])日$")
COMMUNICATION_DATE_RE = re.compile(r"^(?:19|20)\d{2}年(?:0[1-9]|1[0-2])月(?:0[1-9]|[12]\d|3[01])日 (?:[01]\d|2[0-3]):[0-5]\d:[0-5]\d$")
EMAIL_RE = re.compile(r"^[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.(?:com\.cn|net\.cn|org\.cn|co\.jp|co\.uk|com|net|org|edu|gov|cn|jp|de|fr|io|me)$", re.I)
HTML_RE = re.compile(r"</?[a-z][^>]*(?:>|$)|data-[a-z-]+\s*=|&(?:nbsp|lt|gt|amp);", re.I)
LABEL_ONLY_RE = re.compile(
    r"^(?:公司名(?:称)?|会社名|公司|会社|Company|单位|学校名|学校|School|大学|学院|高校|専門学校|职位|职务|職種|担当|"
    r"专业|専攻|学歴|職歴|工作经历|教育经历|项目经历|培训经历|证书|資格|School\s*Name|University\s*education|大学教育|高校生|公司性质|会社性質|组织公司|年|月|日|至今|现在|无|暂无|N/?A|[-—–~～]+)$",
    re.I,
)
FIELD_LABEL_RE = re.compile(
    r"(?:公司名|会社名|学校名|职位|职务|職種|工作描述|工作职责|项目描述|项目职责|离职原因|退職理由|"
    r"姓名|氏名|电话|電話|手机|携帯|邮箱|E-?mail|出生日期|生年月日|婚姻状况|求职意向)\s*[：:]",
    re.I,
)
SENTENCE_RE = re.compile(
    r"^(?:本人|自我|希望|能够|具有|负责|主要负责|参与|协助|大学を卒業|働き|担当業務|仕事内容|志望動機)"
    r"|(?:工作职责|工作内容|项目职责|项目描述|業務内容|職務内容)\s*[：:]",
    re.I,
)
SCHOOL_RE = re.compile(r"大学|学院|学校|高校|中学|小学|研究科|研究院|University|College|School|Institute|Academy", re.I)
COMPANY_RE = re.compile(r"有限公司|有限责任公司|股份有限公司|株式会社|有限会社|会社|公司|集团|银行|事务所|事務所|GmbH|\b(?:Co\.?|Ltd\.?|Inc\.?|Corp\.?)\b", re.I)
ORGANIZATION_RE = re.compile(
    r"有限公司|有限责任公司|股份有限公司|株式会社|有限会社|会社|公司|集团|银行|事务所|事務所|中心|研究所|研究院|"
    r"医院|委员会|协会|政府|学校|大学|学院|高校|实验室|研究室|工厂|商店|酒店|报社|市民会馆|"
    r"GmbH|\b(?:Co\.?|Ltd\.?|Inc\.?|Corp\.?|Corporation|Company|Group|Bank|Center|Centre|Institute|University|College|School|Laboratory|Lab)\b",
    re.I,
)
ROLE_AS_COMPANY_RE = re.compile(
    r"(?:项目经理|产品经理|工程师|研究员|顾问|咨询师|专员|助理|主管|经理|部长|主任|翻译|担当|营业|销售|技术员|"
    r"Project Manager|Product Manager|Engineer|Researcher|Consultant|Specialist|Assistant|Supervisor|Manager|Director|Department|Technician)$",
    re.I,
)
WORK_ROLE_RE = re.compile(
    r"教师|教師|讲师|講師|教练|コーチ|教授|研究员|研究員|研究|助教|培训师|负责人|責任者|管理|经理|主管|主任|担当|工程师|営業|销售|访谈员|助理|实习|実習|翻译|翻訳|通訳|秘书|秘書|成员|メンバー|"
    r"Teacher|Trainer|Lecturer|Professor|Researcher|Assistant|Manager|Engineer|Translator|Interpreter|Member|Visiting|Visting|Intern\b|Internship|Intership|TA\b",
    re.I,
)

ENTITY_FIELDS = {
    "company_name": 90,
    "school_name": 90,
    "project_name": 140,
    "training_name": 140,
    "certificate_name": 100,
    "position": 140,
    "school_major_name": 140,
}
LONG_TEXT_FIELDS = {
    "pr", "position_responsibilities", "position_achievements", "description",
    "responsibilities", "achievements", "communicate_content",
}
DATE_FIELDS = {
    "birth_date", "position_start", "position_resigned", "school_start_ym", "school_end_ym",
    "project_start", "project_end", "training_start", "training_end", "start_ym", "end_ym", "certificate_time",
    "language_certificate_time",
}
SOURCE_REQUIRED_FIELDS = {
    "full_name", "phone", "email", "birth_date", "position_start",
    "position_resigned", "school_start_ym", "school_end_ym",
}
DIRECT_TRACE_FIELDS = {
    "full_name", "gender", "birth_date", "marital_status", "children_status",
    "political_status", "height_cm", "weight_kg", "household_registration", "address",
    "postal_code", "phone", "email", "city", "nationality", "pr",
    *EXPECTED_FIELDS,
    "company_name", "company_employees", "company_industry", "position", "position_type",
    "position_salary", "position_dept", "position_report_to", "position_subordinate",
    "annual_salary_min", "annual_salary_max", "resigned_reason",
    "position_responsibilities", "position_achievements",
    "school_name", "school_major_name", "school_degree_type", "school_start_ym", "school_end_ym",
    "certificate_name", "certificate_time", "language_name", "language_level",
    "language_certificate_time", "skill_name", "skill_level", "organization_name",
    "training_name", "project_name", "company_or_client", "role_name", "start_ym", "end_ym",
    "description", "responsibilities", "achievements", "communicate_time", "communicate_content",
}
SUSPICIOUS_ENTITY_RE = re.compile(
    r"^(?:看图王|WPS|Word|PDF|messag(?:e)?|Skill|Oct\.?|Jun\.?|正社員|契約社員|派遣社員|アルバイト|"
    r"\[?\d+(?:年|个月|か月|ヶ月)\]?|\d{1,2}\s*月|（?正社員）?)$",
    re.I,
)
SUSPICIOUS_ENTITY_START_RE = re.compile(
    r"^(?:本人|负责|主要负责|参与|协助|并作为|对集团|主修课程|技术部|设备管理|项目业绩|"
    r"专业\s*[：:]|学校名(?:称)?\s*[：:]?|公司业务范围|公司性质|所在公司|任职公司|此时公司|薪酬状况|工作地点|受上级单位|"
    r"类化合物|大学英(?:语)?|大学主修课程|技能证书|英语等级|WordOOXML|[●•◆■]+|\d+\s*[).、]|"
    r"\d{1,2}:\d{2}:\d{2}|Position\s*[：:]|(?:19|20)\d{2}\s*年?\s*\d{1,2}\s*月|月\s*[～~-])",
    re.I,
)
NON_ENTITY_PHRASE_RE = re.compile(
    r"^(?:公司业务范围|公司性质|所在公司|任职公司|此时公司|薪酬状况|工作地点|学校名称|专业|学历|工作职责|工作内容|"
    r"项目描述|项目职责|项目职务|责任描述|受上级单位|奖学金|技能证书|大学英语|大学主修课程)\b",
    re.I,
)
DEGREE_IN_MAJOR_RE = re.compile(
    r"^(?:本科|专科|大专|硕士|博士|学士|修士|Bachelor|Master|Doctor|Ph\.?D\.?)\s+(?:in|of|于|在)\b",
    re.I,
)
DEPARTMENT_ONLY_RE = re.compile(
    r"^(?:[^，。；;]{0,35})(?:部|課|科|处|室|中心|本部|部门)(?:[、・/][^，。；;]{0,35}(?:部|課|科|处|室|中心|本部|部门))*$"
)
ROLE_WORD_RE = re.compile(
    r"经理|主管|主任|专员|助理|工程师|教师|翻译|口译|笔译|销售|营业担当|担当|研究员|顾问|总务|会计|"
    r"Manager|Engineer|Teacher|Translator|Interpreter|Sales|Assistant|Specialist|Researcher|Consultant",
    re.I,
)
NATIONALITY_RE = re.compile(
    r"^(?:中国|中国大陆|中华人民共和国|日本|韩国|朝鲜|美国|加拿大|英国|法国|德国|意大利|西班牙|葡萄牙|"
    r"俄罗斯|澳大利亚|新西兰|新加坡|马来西亚|印度|泰国|越南|菲律宾|印度尼西亚|巴西|墨西哥|"
    r"China|Chinese|Japan|Japanese|Korea|Korean|USA|US|American|Canada|Canadian|UK|British|France|French|"
    r"Germany|German|Russia|Russian|Australia|Australian|Singapore|Singaporean)$",
    re.I,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="PDF JSON 全字段严格审计（源证据不使用 JSON raw_text）" " / Strict all-field audit of PDF JSON (source evidence does not use the JSON raw_text) / PDF JSON の全フィールド厳密監査（元ファイルの証拠として JSON の raw_text は使わない）")
    parser.add_argument("--json-root", type=Path, default=DEFAULT_JSON_ROOT)
    parser.add_argument("--map", type=Path, default=DEFAULT_MAP)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    return parser.parse_args()


def text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def compact(value: Any) -> str:
    value = unicodedata.normalize("NFKC", text(value)).casefold()
    value = value.translate(str.maketrans({
        "語": "语", "學": "学", "國": "国", "際": "际", "機": "机", "関": "关",
        "龍": "龙", "華": "华", "東": "东", "業": "业", "職": "职", "験": "验",
        "級": "级", "會": "会", "體": "体", "鐵": "铁", "鋼": "钢", "粧": "妆",
        "済": "济", "慶": "庆", "應": "应", "義": "义", "陽": "阳", "邊": "边",
        "輕": "轻", "換": "换", "營": "营", "總": "总", "務": "务", "習": "习",
    }))
    value = value.replace("情报安全", "信息安全").replace("日本文学", "日本文学")
    return re.sub(r"[^0-9a-z\u3400-\u9fff\u3040-\u30ff]", "", value)


def strip_html(value: str) -> str:
    value = re.sub(r"<script\b[^>]*>.*?</script>|<style\b[^>]*>.*?</style>", " ", value, flags=re.I | re.S)
    value = re.sub(r"<[^>]*(?:>|$)", "\n", value)
    return re.sub(r"\s+", " ", html.unescape(value)).strip()


def read_docx(path: Path) -> str:
    try:
        with zipfile.ZipFile(path) as archive:
            root = ET.fromstring(archive.read("word/document.xml"))
        parts = [node.text or "" for node in root.iter(W_NS + "t")]
        return " ".join(parts)
    except Exception:
        return ""


def read_pdf(path: Path) -> str:
    if fitz is None or not path.is_file():
        return ""
    try:
        with fitz.open(str(path)) as document:
            return "\n".join(page.get_text("text") for page in document)
    except Exception:
        return ""


def source_index(mapping: dict[str, Any]) -> dict[str, str]:
    return build_source_text_index(mapping)


def issue(code: str, severity: str, path: str, value: Any, message: str) -> dict[str, Any]:
    return {"code": code, "severity": severity, "path": path, "value": text(value)[:500], "message": message}


def supported(value: Any, source_norm: str) -> bool:
    needle = compact(value)
    if not needle:
        return True
    if needle in source_norm:
        return True
    semantic_needle = needle.replace("与", "和")
    semantic_source = source_norm.replace("与", "和")
    if semantic_needle in semantic_source:
        return True
    # Long translated/normalized values may differ around punctuation or suffixes.
    if len(needle) >= 8 and (needle[:6] in source_norm or needle[-6:] in source_norm):
        return True
    # Composite labels such as "CET-6 / CET-4" or "SPS/PLC编程" are
    # traceable when each meaningful component is independently present.
    components = [compact(part) for part in re.split(r"[/、,，;；|]+", text(value)) if compact(part)]
    if len(components) > 1 and all(part in source_norm for part in components):
        return True
    # Translated concise labels often remove connecting words from a longer
    # source sentence. Require two distinctive three-character anchors rather
    # than accepting a single generic word.
    if len(semantic_needle) >= 7:
        starts = (0, max(0, len(semantic_needle) // 2 - 1), max(0, len(semantic_needle) - 3))
        chunks = {semantic_needle[start:start + 3] for start in starts if len(semantic_needle[start:start + 3]) == 3}
        if sum(chunk in semantic_source for chunk in chunks) >= 2:
            return True
        trigrams = {semantic_needle[index:index + 3] for index in range(len(semantic_needle) - 2)}
        if sum(chunk in semantic_source for chunk in trigrams) >= max(2, math.ceil(len(trigrams) * 0.20)):
            return True
    parsed = date_tuple(value)
    if parsed:
        year, month, day = parsed
        date_tokens = {
            f"{year:04d}{month:02d}{day:02d}", f"{year:04d}{month:02d}",
            f"{year:04d}{month}", f"{year:04d}",
        }
        if any(token in source_norm for token in date_tokens):
            return True
        for era, base in (("昭和", 1925), ("平成", 1988), ("令和", 2018)):
            era_year = year - base
            if era_year >= 1 and compact(f"{era}{era_year}年{month}月") in source_norm:
                return True
    return False


def date_tuple(value: Any) -> tuple[int, int, int] | None:
    match = re.match(r"^((?:19|20)\d{2})年(\d{2})月(\d{2})日$", text(value))
    return tuple(map(int, match.groups())) if match else None


def school_core(value: Any) -> str:
    current = compact(value)
    current = re.sub(r"^\d{1,2}", "", current)
    current = current.translate(str.maketrans({"語": "语", "學": "学", "國": "国", "陸": "陆", "東": "东", "業": "业", "職": "职"}))
    for token in (
        "日本", "中国", "四年制", "大学院", "研究科", "学院", "大学", "専門学校",
        "高等学校", "高级中学", "中学", "学校", "附属", "附属",
    ):
        current = current.replace(compact(token), "")
    return current


def degree_value(row: dict[str, Any]) -> int:
    rank = text(row.get("school_degree_rank"))
    if rank.isdigit():
        return int(rank)
    joined = " ".join((text(row.get("school_degree_type")), text(row.get("school_name"))))
    if re.search(r"博士|Ph\.?D|Doctor", joined, re.I): return 6
    if re.search(r"硕士|修士|Master|MBA", joined, re.I): return 5
    if re.search(r"本科|学士|Bachelor|大学|学部", joined, re.I): return 4
    if re.search(r"大专|专科|短大|Associate", joined, re.I): return 3
    return 0


def scalar_checks(field: str, value: Any, path: str, source_norm: str, issues: list[dict[str, Any]]) -> None:
    current = text(value)
    # Private-use glyphs are often ordinary PDF bullet icons.  Font-mapping
    # corruption in this corpus instead appears as sustained runs of unrelated
    # Indic/Tibetan/Georgian/Canadian-syllabic characters.
    exotic = re.findall(r"[\u0E00-\u1FFF\u2C00-\u2DFF\uA000-\uAFFF�]", current)
    greek = re.findall(r"[\u0370-\u03FF]", current)
    if current and (len(exotic) >= 4 or len(greek) >= 6):
        issues.append(issue("garbled_text", "critical", path, current, "字段包含明显的字体映射乱码或异常 Unicode 文本"))
    if not current:
        return
    if HTML_RE.search(current):
        issues.append(issue("html_leak", "critical", path, current, "字段含 HTML/DOM 残片"))
    if "�" in current or "\x00" in current:
        issues.append(issue("encoding_corruption", "critical", path, current, "字段含乱码或 NUL"))
    if any(
        (ord(char) < 32 and char not in "\r\n\t") or 0x7F <= ord(char) <= 0x9F or unicodedata.category(char) == "Cf"
        for char in current
    ):
        issues.append(issue("control_character_corruption", "critical", path, current, "结构化字段含 DEL、C0/C1 或不可见格式控制字符"))
    if re.search(r"WordOOXMLTable|OpenXMLTable", current, re.I):
        issues.append(issue("document_conversion_marker", "critical", path, current, "Word 表格转换标记泄漏到结构化字段"))
    if field == "pr" and re.search(r"(?:^|\n)\s*(?:通勤時間|写真をはる位置|写真を貼る位置|免許・資格|アルバイト|学歴・資格|職歴|希望給与)\s*(?:\n|$)", current, re.I):
        issues.append(issue("pr_section_contamination", "critical", path, current, "自我介绍字段串入其他表格或章节"))
    if field in LONG_TEXT_FIELDS and re.search(
        r"(?:WordOOXMLTable|OpenXMLTable|写真をはる位置|フリガナ\s+性別\s+氏名|"
        r"(?:^|\n)\s*(?:学歴・資格|教育经历|工作经历|職歴|希望職種|希望給与)\s*(?:\n|$))",
        current, re.I,
    ):
        issues.append(issue("section_dump_in_text_field", "critical", path, current, "描述字段串入模板、表格或其他完整章节"))
    if re.search(r"[Ａ-Ｚａ-ｚ０-９]", current):
        issues.append(issue("fullwidth_alphanumeric", "high", path, current, "结构化字段含全角英文字母或数字，必须规范为半角"))
    if field in ENTITY_FIELDS:
        if re.search(r"(?:工程师|经理|教师|讲师|专员|助理|主管|研究员|顾问|翻译)[a-z]{2,}\b", current, re.I):
            issues.append(issue("hybrid_word_corruption", "critical", path, current, "字段含中文词与英文后缀拼接的伪翻译"))
        if field == "school_major_name" and DEGREE_IN_MAJOR_RE.search(current):
            issues.append(issue("degree_leaked_into_major", "high", path, current, "专业字段混入学位表达"))
        if LABEL_ONLY_RE.fullmatch(current):
            issues.append(issue("placeholder_entity", "critical", path, current, "实体字段是模板标签或占位词"))
        if len(current) > ENTITY_FIELDS[field]:
            issues.append(issue("entity_too_long", "high", path, current, "实体字段过长，疑似正文串位"))
        if FIELD_LABEL_RE.search(current):
            issues.append(issue("label_in_entity", "high", path, current, "实体字段混入其他字段标签"))
        if SUSPICIOUS_ENTITY_RE.fullmatch(current):
            issues.append(issue("suspicious_entity_token", "critical", path, current, "实体字段是时长、文件工具名或雇佣类型等非实体值"))
        if field in {"company_name", "school_name"} and SUSPICIOUS_ENTITY_START_RE.search(current):
            issues.append(issue("suspicious_entity_prefix", "high", path, current, "公司/学校字段以正文、日期或模板内容开头"))
        if field in {"company_name", "school_name"} and NON_ENTITY_PHRASE_RE.search(current):
            issues.append(issue("non_entity_phrase", "critical", path, current, "公司/学校字段是字段说明、职责或正文短语"))
        if field == "school_name" and re.search(r"奖学金|奨学金|竞赛|大赛|比赛|受賞|優秀|称号|大会\s*\d*位|Prize|Scholarship|Award", current, re.I):
            issues.append(issue("award_as_school", "high", path, current, "荣誉或奖学金误入学校字段"))
        if field == "school_name" and re.search(r"记者站|(?:就业|就業)指导中心|校友会|助教|学生干部|干部/干事|主席团|汉语助教|孔子学院", current, re.I):
            issues.append(issue("activity_as_school", "high", path, current, "校园职务、社团或活动误入学校字段"))
        if field == "school_major_name" and re.search(r"浏览量|微信公众号|获奖经历|学生干部|主席团成员", current, re.I):
            issues.append(issue("activity_as_major", "high", path, current, "活动、荣誉或浏览数据误入专业字段"))
        if field == "company_name" and ROLE_AS_COMPANY_RE.search(current) and not ORGANIZATION_RE.search(current):
            issues.append(issue("role_as_company", "high", path, current, "职位名称误入公司字段"))
        if field == "company_name" and re.search(
            r"(?:有限公司|株式会社|有限会社|\b(?:Co\.?|Ltd\.?|Inc\.?)\b).{0,50}(?:工程师|经理|主管|专员|助理|担当|Manager|Engineer|Specialist)$",
            current, re.I,
        ):
            issues.append(issue("role_suffix_in_company", "high", path, current, "公司字段尾部混入职位"))
        if field == "position" and re.search(
            r"有限公司|有限责任公司|股份有限公司|株式会社|有限会社|(?:律师|会计)事务所|"
            r"\b(?:Co\.?\s*,?\s*Ltd\.?|Ltd\.?|Inc\.?|GmbH|Corporation|Company)\b",
            current, re.I,
        ):
            issues.append(issue("company_in_position", "high", path, current, "职位字段混入公司名称"))
        if field == "position" and (
            re.match(r"^(?:\(?\d{1,2}\s*月\)?|(?:19|20)\d{2}[./年]\d{1,2}|日系\s+所属部署|所属部署|部署\s*[：:])", current)
            or re.search(r"所属部署\s*$", current)
        ):
            issues.append(issue("contaminated_position", "critical", path, current, "职位字段混入月份、日期或部门标签"))
        if field == "company_name" and re.fullmatch(r"(?:This company|the company|provinc\w*|mainly inc|pleadings.*|工作单位|任职公司|公司性质|会社性質|组织公司|Company Locations?(?::.*)?)", current, re.I):
            issues.append(issue("fragment_as_company", "critical", path, current, "正文残片或泛称误入公司字段"))
        if field == "company_name" and re.match(r"^(?:Native|Nationality|Residence|Address|籍贯|户籍|现居地)\s*[：:]", current, re.I):
            issues.append(issue("personal_info_as_company", "critical", path, current, "籍贯、住址或个人信息误入公司字段"))
        if field == "company_name" and re.search(r"(?:。|；|;)\s*(?:[^。；;]{2,})?(?:有限公司|株式会社|有限会社|Co\.?\s*,?\s*Ltd\.?)$", current, re.I):
            issues.append(issue("sentence_prefixed_company", "critical", path, current, "公司字段前拼接了职责或正文句子"))
        if field == "company_name" and re.search(r"项目(?:总负责|描述|职责)|合同派遣至|毕业|论文|学位", current, re.I) and not COMPANY_RE.search(current):
            issues.append(issue("project_or_education_as_company", "high", path, current, "项目、学历或说明文字误入公司字段"))
        if field == "school_name" and re.match(r"^(?:Master|Bachelor|硕士|本科|学士|修士)\b", current, re.I) and not SCHOOL_RE.search(current):
            issues.append(issue("degree_as_school", "high", path, current, "学位或专业描述误入学校字段"))
        if field == "school_name" and re.search(r"(?:CET[- ]?[46]|JLPT|TOEFL|IELTS|英语[四六]级|日语[一二三四八]级|证书|資格)", current, re.I) and not SCHOOL_RE.search(current):
            issues.append(issue("certificate_as_school", "critical", path, current, "证书或语言成绩误入学校字段"))
        if field in {"company_name", "school_name"} and SENTENCE_RE.search(current) and not (field == "company_name" and re.search(r"就业指导中心", current)):
            issues.append(issue("sentence_in_entity", "high", path, current, "公司/学校字段疑似整句正文"))
        if field == "company_name" and SCHOOL_RE.search(current) and not COMPANY_RE.search(current):
            issues.append(issue("school_as_company", "high", path, current, "学校实体出现在公司字段"))
        if field == "school_name" and COMPANY_RE.search(current) and not SCHOOL_RE.search(current):
            issues.append(issue("company_as_school", "high", path, current, "公司实体出现在学校字段"))
        if field == "school_name" and re.match(r"^(?:19|20)\d{2}年\s*[-~～—–至]\s*(?:19|20)\d{2}年", unicodedata.normalize("NFKC", current)):
            issues.append(issue("compound_education_in_school", "critical", path, current, "年份、学历、学校和专业整行文本未拆分"))
        if field == "school_name" and re.search(r"(?:19|20)\d{2}\s*年.{0,20}(?:19|20)\d{2}\s*年", unicodedata.normalize("NFKC", current)):
            issues.append(issue("date_range_in_school_name", "critical", path, current, "学校名称混入起止年份"))
        if field == "school_name" and (
            re.match(r"^(?:私は|我(?:是|在|从)|本人|自己紹介|卒業から|今まで)", current, re.I)
            or re.search(r"(?:工程操作員|工程师|经理|担当|調査員|作業員|负责人)$", current)
        ):
            issues.append(issue("non_school_entity", "critical", path, current, "工作职位、自我介绍或句子残片误入学校字段"))
        if field == "project_name" and re.fullmatch(r"(?:19|20)?\d{2}(?:[./-]\d{1,2}){0,2}", current):
            issues.append(issue("date_as_project_name", "critical", path, current, "日期或年月误入项目名称"))
        if field == "project_name" and re.fullmatch(r"(?:项目|Project|项目经历|主要项目|重点项目)\s*[：:]?", current, re.I):
            issues.append(issue("generic_project_name", "critical", path, current, "项目名称只是章节标签或泛称"))
        if field == "position" and re.search(r"(?:\||｜)\s*\d[\d,.]*\s*(?:元|円|RMB|CNY|JPY)?\s*(?:/月|每月|月薪)?$", current, re.I):
            issues.append(issue("salary_leaked_into_position", "critical", path, current, "职位字段混入薪资，必须拆入薪资字段"))
        if field == "position" and re.search(
            r"(?:\||｜).*(?:\d+\s*[-~～至]\s*\d+\s*(?:人|people)|外资|合资|民营|国有|Private Comp|Foreign Comp|State-Owned Comp|元/月|円/月)",
            current, re.I,
        ):
            issues.append(issue("company_profile_leaked_into_position", "critical", path, current, "职位字段混入行业、公司性质、规模或薪资"))
        if field == "position" and re.match(r"^(?:er|or|ion|ment|ist)\s*[,，]", current, re.I):
            issues.append(issue("truncated_position", "critical", path, current, "职位以单词残片开头，疑似提取截断"))
        if field == "school_major_name" and re.fullmatch(r"(?:E\s*x\s*p\s*e\s*r\s*i\s*e\s*n\s*c\s*e|Experience|Education|Resume|CV|Professional Experiences?)", current, re.I):
            issues.append(issue("section_heading_as_major", "critical", path, current, "章节标题误入专业字段"))
    if field in DATE_FIELDS and current and not DATE_RE.fullmatch(current):
        issues.append(issue("invalid_date", "high", path, current, "日期未使用 YYYY年MM月DD日"))
    parsed_date = date_tuple(current) if field in DATE_FIELDS else None
    if parsed_date and field.endswith("_ym") and parsed_date[2] != 1:
        issues.append(issue("non_month_precision_date", "high", path, current, "经历类日期字段为年月粒度，日必须规范为01"))
    if field == "nationality" and current and not NATIONALITY_RE.fullmatch(current):
        issues.append(issue("invalid_nationality", "high", path, current, "国籍字段不是国家或国籍名称，疑似串位"))
    if field == "email" and not EMAIL_RE.fullmatch(current):
        issues.append(issue("invalid_email", "critical", path, current, "邮箱格式非法或混入相邻文本"))
    if field == "phone":
        normalized = unicodedata.normalize("NFKC", current)
        digits = re.sub(r"\D", "", normalized)
        china_mobile = bool(re.fullmatch(r"(?:86)?1[3-9]\d{9}", digits))
        japan_mobile = bool(re.fullmatch(r"(?:81)?0?[789]0\d{8}", digits))
        general_phone = 8 <= len(digits) <= 15 and not (len(digits) == 11 and digits.startswith("1"))
        if not (china_mobile or japan_mobile or general_phone):
            issues.append(issue("invalid_phone", "critical", path, current, "电话数字长度或号段非法"))
    if field == "language_certificate" and current not in {"有", "无"}:
        issues.append(issue("invalid_language_certificate_flag", "critical", path, current, "language_certificate 按 CONTEXT.md 只能为有、无或空字符串"))
    if field == "language_level" and re.fullmatch(r"(?:Pass(?:ed)?|Qualified|合格|通过|通過)", current, re.I):
        issues.append(issue("language_level_only_pass", "high", path, current, "语言等级不能只有合格/通过，必须保留考试或水平名称"))
    if field == "school_degree_rank" and current not in {"1", "2", "3", "4", "5", "6", "7"}:
        issues.append(issue("invalid_degree_rank", "critical", path, current, "学历等级只能是 1-7 或空字符串"))
    if field == "communicate_time" and current and not COMMUNICATION_DATE_RE.fullmatch(current):
        issues.append(issue("invalid_communication_time", "high", path, current, "沟通时间未使用 YYYY年MM月DD日 HH:mm:ss"))
    if field == "company_industry" and re.search(r"(?:元|円|RMB|CNY|JPY|月薪|年薪|/月|per month)", current, re.I):
        issues.append(issue("salary_as_company_industry", "critical", path, current, "薪资值误入公司行业字段"))
    if field == "company_employees" and current != "未填写" and not re.fullmatch(r"\d+\s*(?:-|~|～|—|至)\s*\d+人|\d+人以上|少于\d+人", current):
        issues.append(issue("invalid_company_employees", "high", path, current, "公司规模不是人数范围或未填写"))
    if field in {"age", "height_cm", "weight_kg", "position_subordinate"} and current and not re.fullmatch(r"\d+(?:\.\d+)?", current):
        issues.append(issue("invalid_numeric_text", "high", path, current, "应为数字字符串的字段混入其他文本"))
    if field == "household_registration" and re.search(r"证书|資格|certificate|邮箱|电话", current, re.I):
        issues.append(issue("contaminated_household_registration", "critical", path, current, "户籍字段混入证书或联系方式文本"))
    if field == "pr" and (current.count("Ì") >= 2 or len(re.findall(r"[�□■]", current)) >= 2):
        issues.append(issue("garbled_pr", "critical", path, current, "自我评价包含明显乱码，不能作为有效结构化字段"))
    if field == "language_level" and re.search(r"等级证书|能力证书|certificate", current, re.I):
        issues.append(issue("certificate_title_as_language_level", "high", path, current, "语言等级字段仍是证书泛称，未提取实际等级或水平"))
    if field in SOURCE_REQUIRED_FIELDS and not supported(current, source_norm):
        # Dates translated from era formats and translated entity names are reviewed,
        # not failed, unless another semantic rule already proves corruption.
        issues.append(issue("field_not_supported_by_source", "medium", path, current, "字段未在 Word/语义 HTML 源证据中命中"))


def walk(value: Any, path: str, source_norm: str, issues: list[dict[str, Any]]) -> None:
    if isinstance(value, dict):
        for field, child in value.items():
            child_path = f"{path}.{field}" if path else field
            if isinstance(child, (dict, list)):
                walk(child, child_path, source_norm, issues)
            else:
                scalar_checks(field, child, child_path, source_norm, issues)
    elif isinstance(value, list):
        seen: Counter[str] = Counter()
        for index, child in enumerate(value):
            if isinstance(child, dict):
                key = json.dumps(child, ensure_ascii=False, sort_keys=True)
                seen[key] += 1
            walk(child, f"{path}[{index}]", source_norm, issues)
        if any(count > 1 for count in seen.values()):
            issues.append(issue("duplicate_list_row", "high", path, "", "列表含完全重复记录"))


def check_object_schema(value: Any, required: tuple[str, ...], path: str, issues: list[dict[str, Any]]) -> None:
    if not isinstance(value, dict):
        issues.append(issue("invalid_object_type", "critical", path, type(value).__name__, "字段必须是对象"))
        return
    actual = set(value)
    expected = set(required)
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    if missing:
        issues.append(issue("missing_schema_fields", "critical", path, ", ".join(missing), "对象缺少 CONTEXT.md 规定字段"))
    if extra:
        issues.append(issue("extra_schema_fields", "high", path, ", ".join(extra), "对象含 CONTEXT.md 未定义字段"))
    for field in expected & actual:
        if field == "sequence_no":
            if not isinstance(value[field], int) or isinstance(value[field], bool):
                issues.append(issue("invalid_scalar_type", "critical", f"{path}.{field}", type(value[field]).__name__, "sequence_no 必须是数字"))
        elif not isinstance(value[field], str):
            issues.append(issue("invalid_scalar_type", "critical", f"{path}.{field}", type(value[field]).__name__, "字段必须是字符串，空值使用空字符串"))


def validate_resume_schema(resume: Any, resume_index: int, issues: list[dict[str, Any]]) -> None:
    path = f"structured_data.resumes[{resume_index}]"
    if not isinstance(resume, dict):
        issues.append(issue("invalid_resume_type", "critical", path, type(resume).__name__, "语言简历必须是对象"))
        return
    expected_keys = {"resume_language", "base_info", *RESUME_LISTS}
    missing = sorted(expected_keys - set(resume))
    extra = sorted(set(resume) - expected_keys)
    if missing:
        issues.append(issue("missing_resume_fields", "critical", path, ", ".join(missing), "语言简历缺少标准字段"))
    if extra:
        issues.append(issue("extra_resume_fields", "high", path, ", ".join(extra), "语言简历含非标准字段"))
    language = resume.get("resume_language")
    if not isinstance(language, str) or not language:
        issues.append(issue("invalid_resume_language", "critical", f"{path}.resume_language", language, "必须填写语言代码"))
    check_object_schema(resume.get("base_info"), BASE_FIELDS, f"{path}.base_info", issues)
    required_entities = {
        "work_experiences": "company_name",
        "education_list": "school_name",
        "certificate_list": "certificate_name",
        "language_list": "language_name",
        "skills_list": "skill_name",
        "training_list": "training_name",
        "project_list": "project_name",
        "communication_list": "communicate_content",
    }
    for collection, fields in COLLECTION_FIELDS.items():
        rows = resume.get(collection)
        collection_path = f"{path}.{collection}"
        if not isinstance(rows, list):
            issues.append(issue("invalid_list_type", "critical", collection_path, type(rows).__name__, "列表字段必须是数组，无数据使用 []"))
            continue
        for row_index, row in enumerate(rows):
            row_path = f"{collection_path}[{row_index}]"
            check_object_schema(row, fields, row_path, issues)
            if not isinstance(row, dict):
                continue
            entity = required_entities.get(collection)
            if entity and not text(row.get(entity)):
                issues.append(issue("missing_required_entity", "critical", f"{row_path}.{entity}", "", "记录缺少核心实体，不能仅凭其他字段保留"))
            if not any(text(row.get(field)) for field in fields if field != "sequence_no"):
                issues.append(issue("empty_list_row", "critical", row_path, "", "列表含纯空占位记录"))
            if collection in {"project_list", "training_list"} and row.get("sequence_no") != row_index + 1:
                issues.append(issue("invalid_sequence_no", "critical", f"{row_path}.sequence_no", row.get("sequence_no"), "序号必须为从 1 开始的数字并与列表顺序一致"))


def validate_primary_enums(resume: dict[str, Any], issues: list[dict[str, Any]]) -> None:
    base = resume.get("base_info") or {}
    gender = text(base.get("gender"))
    if gender and gender not in {"男", "女"}:
        issues.append(issue("invalid_gender", "high", "structured_data.resumes[0].base_info.gender", gender, "中文主简历性别只能为男、女或空字符串"))
    for row_index, row in enumerate(resume.get("expected_list") or []):
        value = text((row or {}).get("expected_employment_type"))
        if value and value not in {"全职", "兼职", "实习", "remote", "混合办公"}:
            issues.append(issue("invalid_employment_type", "high", f"structured_data.resumes[0].expected_list[{row_index}].expected_employment_type", value, "中文主简历求职性质不符合 CONTEXT.md"))
    for row_index, row in enumerate(resume.get("work_experiences") or []):
        row = row or {}
        employment = text(row.get("employment_type"))
        status = text(row.get("status"))
        if employment and employment not in {"全职", "兼职", "实习"}:
            issues.append(issue("invalid_employment_type", "high", f"structured_data.resumes[0].work_experiences[{row_index}].employment_type", employment, "中文主简历雇佣类型不符合 CONTEXT.md"))
        if status and status not in {"在职", "离职"}:
            issues.append(issue("invalid_work_status", "high", f"structured_data.resumes[0].work_experiences[{row_index}].status", status, "中文主简历状态只能为在职或离职"))


def validate_row_source_anchors(resume: dict[str, Any], resume_index: int, source_norm: str, issues: list[dict[str, Any]]) -> None:
    """Every retained row needs at least one independently traceable source anchor."""
    specs = {
        "expected_list": ("expected_city", "expected_position", "expected_salary", "expected_industry"),
        "work_experiences": ("company_name", "position", "position_start", "position_resigned"),
        "education_list": ("school_name", "school_major_name", "school_start_ym", "school_end_ym"),
        "certificate_list": ("certificate_name", "certificate_time"),
        "language_list": ("language_name", "language_level", "language_certificate_time"),
        "skills_list": ("skill_name",),
        "training_list": ("organization_name", "training_name", "start_ym", "end_ym"),
        "project_list": ("project_name", "company_or_client", "start_ym", "end_ym"),
        "communication_list": ("communicate_time", "communicate_content"),
    }
    for collection, anchors in specs.items():
        for row_index, row in enumerate(resume.get(collection) or []):
            if not isinstance(row, dict):
                continue
            populated = [row.get(field) for field in anchors if text(row.get(field))]
            traceable = any(supported(value, source_norm) for value in populated)
            if collection == "language_list" and isinstance(row, dict):
                aliases = {
                    "日语": ("日语", "日本语", "日本語", "japanese"),
                    "英语": ("英语", "英語", "english"),
                    "德语": ("德语", "德語", "ドイツ語", "german"),
                    "法语": ("法语", "法語", "フランス語", "french"),
                    "中文": ("中文", "汉语", "漢語", "中国語", "chinese"),
                    "普通话": ("普通话", "普通話", "mandarin"),
                    "粤语": ("粤语", "広東語", "cantonese"),
                    "韩语": ("韩语", "韓国語", "韩国语", "korean"),
                    "上海话": ("上海话", "上海語", "shanghainese"),
                }
                language = text(row.get("language_name"))
                candidates = aliases.get(language, (language,))
                traceable = traceable or any(compact(alias) in source_norm for alias in candidates if alias)
                level_parts = [part for part in re.split(r"[/、,，;；|]+", text(row.get("language_level"))) if text(part)]
                traceable = traceable or any(supported(part, source_norm) for part in level_parts)
            if populated and not traceable:
                issues.append(issue(
                    "row_not_traceable_to_source", "high",
                    f"structured_data.resumes[{resume_index}].{collection}[{row_index}]",
                    " | ".join(text(value) for value in populated),
                    "该条记录的实体、日期和关键字段均无法追溯到 PDF/Word 源文本",
                ))


def trace_supported(field: str, value: Any, source_norm: str) -> bool:
    if supported(value, source_norm):
        return True
    current = text(value)
    aliases = {
        "日语": ("日本語", "japanese"), "英语": ("英語", "english"),
        "德语": ("ドイツ語", "german"), "法语": ("フランス語", "french"),
        "中文": ("中国語", "汉语", "漢語", "chinese"),
        "普通话": ("標準語", "mandarin"), "粤语": ("広東語", "cantonese"),
        "韩语": ("韓国語", "korean"), "上海话": ("上海語", "shanghainese"),
        "男": ("男性", "male"), "女": ("女性", "female"),
        "未婚": ("单身", "独身", "single"), "已婚": ("既婚", "married"),
        "已育": ("有子女", "子持", "children"), "未育": ("无子女", "子供なし", "nochildren"),
        "中国": ("中国籍", "china", "chinese"), "日本": ("日本籍", "japan", "japanese"),
        "本科": ("学士", "大学", "bachelor"), "硕士": ("修士", "master"),
        "博士": ("博士", "phd", "doctor"), "大专": ("专科", "短大", "associate"),
        "实习生": ("实习", "インターン", "intern"), "销售助理": ("营业助理", "営業アシスタント", "salesassistant"),
        "销售": ("营业", "営業", "sales"), "翻译": ("通訳", "翻訳", "translator", "interpreter"),
        "良好": ("良", "business", "workingproficiency"), "流利": ("上手", "熟練", "fluent"),
        "熟练": ("熟練", "proficient"), "精通": ("精通", "native", "advanced"), "入门": ("入門", "beginner"),
    }
    if current in aliases and any(compact(alias) in source_norm for alias in aliases[current]):
        return True
    if field in {"city", "expected_city"}:
        core = compact(current).removesuffix("市")
        if len(core) >= 2 and core in source_norm:
            return True
    if field == "language_level":
        normalized = unicodedata.normalize("NFKC", current)
        test_aliases = {
            "N1": ("一级", "1级"), "N2": ("二级", "2级"), "N3": ("三级", "3级"),
            "N4": ("四级", "4级"), "N5": ("五级", "5级"),
            "CET-4": ("cet4", "英语四级", "大学英语四级"),
            "CET-6": ("cet6", "英语六级", "大学英语六级"),
            "母语级": ("母语", "native", "ネイティブ"),
            "日常交流": ("日常会话", "日常会話", "conversation"),
            "商务初级": ("business", "商务", "ビジネス"),
        }
        parts = [text(part) for part in re.split(r"[/、,，;；|]+", normalized) if text(part)]
        if parts and all(
            supported(part, source_norm) or any(compact(alias) in source_norm for alias in test_aliases.get(part, (part,)))
            for part in parts
        ):
            return True
    if field == "school_major_name":
        major_aliases = {
            "信息安全": ("情报安全", "informationsecurity"),
            "国际商务与贸易": ("国际商务", "internationalbusiness", "internationaltrade"),
            "商务英语": ("businessenglish",), "计算机应用技术": ("computerapplication",),
            "计算机软件": ("computersoftware",), "交换留学": ("交换", "交換留学", "exchange"),
            "留学生别科": ("留学生別科",), "轻化工程": ("軽化工程",),
            "日本文学": ("日本文学",), "经济金融": ("经济", "金融", "economics", "finance"),
            "经营学": ("経営学", "management"), "短期语言留学": ("短期", "語学留学"),
            "教学助理": ("助教", "teachingassistant"),
        }
        if current in major_aliases and any(compact(alias) in source_norm for alias in major_aliases[current]):
            return True
    if field == "company_name":
        brand_aliases = {
            "Kanebo": ("カネボウ",), "Saizeriya": ("サイゼリヤ",), "Lawson": ("ローソン",),
            "Don Quijote株式会社": ("ドンキホーテ株式会社", "ドンキホーテ"),
        }
        if current in brand_aliases and any(compact(alias) in source_norm for alias in brand_aliases[current]):
            return True
    if field == "position":
        role_aliases = {
            "助理": ("アシスタント", "assistant"), "主管": ("責任者", "主任", "supervisor"),
            "经理": ("マネージャー", "manager"), "总监": ("ディレクター", "director"),
            "教师": ("教師", "講師", "teacher"), "讲师": ("講師", "lecturer"),
            "翻译": ("通訳", "翻訳", "translator", "interpreter"), "销售": ("営業", "sales"),
            "客服": ("顧客対応", "カスタマー", "customer"), "收银": ("レジ", "cashier"),
            "实习": ("インターン", "intern"), "设计": ("設計", "design"),
            "顾问": ("コンサル", "consultant"), "秘书": ("秘書", "secretary"),
            "物流": ("物流", "logistics"), "店主": ("店主", "owner"), "摊主": ("露店", "vendor"),
            "项目": ("プロジェクト", "project"), "技术": ("技術", "technical"),
            "研究": ("研究", "research"), "财务": ("財務", "finance"), "行政": ("行政", "admin"),
        }
        tokens = [token for token in role_aliases if token in current]
        if tokens and all(any(compact(alias) in source_norm for alias in role_aliases[token]) for token in tokens):
            return True
        role_core = re.sub(r"[（(].*?[）)]|(?:实习生|实习|兼职|专员|职员|人员|员工|担当|员|生)$", "", current)
        role_core = compact(role_core)
        if len(role_core) >= 2 and role_core in source_norm:
            return True
    if field in {"expected_salary", "position_salary", "annual_salary_min", "annual_salary_max"}:
        digits = re.findall(r"\d+", unicodedata.normalize("NFKC", current))
        if digits and all(number in source_norm for number in digits):
            return True
    return False


def validate_field_traceability(resumes: list[dict[str, Any]], source_norm: str, issues: list[dict[str, Any]]) -> None:
    """Trace every nonempty semantic field, not merely one anchor per row."""
    for resume_index, resume in enumerate(resumes):
        base = resume.get("base_info") or {}
        for field in BASE_FIELDS:
            value = base.get(field)
            if field not in DIRECT_TRACE_FIELDS or not text(value):
                continue
            paired = [((other.get("base_info") or {}).get(field)) for other in resumes if other is not resume]
            if not trace_supported(field, value, source_norm) and not any(trace_supported(field, candidate, source_norm) for candidate in paired if text(candidate)):
                issues.append(issue("field_not_traceable_to_source", "high", f"structured_data.resumes[{resume_index}].base_info.{field}", value, "非空字段无法从 PDF/Word 原文或对应原语言字段追溯"))
        for collection, fields in COLLECTION_FIELDS.items():
            rows = resume.get(collection) or []
            for row_index, row in enumerate(rows):
                if not isinstance(row, dict):
                    continue
                for field in fields:
                    value = row.get(field)
                    if field in {"school_degree_type", "language_name", "expected_annual_salary_min", "expected_annual_salary_max"}:
                        continue
                    if field not in DIRECT_TRACE_FIELDS or not text(value):
                        continue
                    paired_values = []
                    for other in resumes:
                        if other is resume:
                            continue
                        other_rows = other.get(collection) or []
                        if row_index < len(other_rows) and isinstance(other_rows[row_index], dict):
                            paired_values.append(other_rows[row_index].get(field))
                    if trace_supported(field, value, source_norm) or any(
                        trace_supported(field, candidate, source_norm) for candidate in paired_values if text(candidate)
                    ):
                        continue
                    issues.append(issue(
                        "field_not_traceable_to_source", "high",
                        f"structured_data.resumes[{resume_index}].{collection}[{row_index}].{field}", value,
                        "非空字段无法从 PDF/Word 原文或对应原语言字段追溯",
                    ))


def validate(path: Path, payload: dict[str, Any], sources: dict[str, str]) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    source_files = [row for row in ((payload.get("source") or {}).get("source_files") or []) if isinstance(row, dict)]
    merge_trace = [row for row in ((payload.get("source") or {}).get("merge_trace") or []) if isinstance(row, dict)]
    if len(merge_trace) != len(source_files):
        issues.append(issue("merge_trace_count_mismatch", "critical", "source.merge_trace", len(merge_trace), "合并追溯清单与原始文件数量不一致"))
    trace_names = {str(row.get("filename") or "").strip().casefold() for row in merge_trace}
    for source_row_index, source_row in enumerate(source_files):
        source_filename = str(source_row.get("filename") or Path(str(source_row.get("input_path") or "")).name).strip()
        languages = source_row.get("resume_languages")
        if not isinstance(languages, list) or not languages or any(value not in {"zh", "ja", "en", "de", "fr"} for value in languages):
            issues.append(issue("source_language_trace_missing", "critical", f"source.source_files[{source_row_index}].resume_languages", languages, "原始简历文件缺少语言追溯"))
        if not text(source_row.get("document_type")):
            issues.append(issue("source_document_type_missing", "high", f"source.source_files[{source_row_index}].document_type", "", "原始简历文件缺少文档类型追溯"))
        if source_filename.casefold() not in trace_names:
            issues.append(issue("source_missing_from_merge_trace", "critical", f"source.source_files[{source_row_index}]", source_filename, "原始文件未进入合并追溯清单"))
    source_contents = []
    seen_source_hashes: set[str] = set()
    for row in source_files:
        source_hash = text(row.get("sha256")).casefold()
        if source_hash and source_hash in seen_source_hashes:
            continue
        if source_hash:
            seen_source_hashes.add(source_hash)
        source_filename = str(row.get("filename") or Path(str(row.get("input_path") or "")).name).strip()
        source_contents.append(sources.get(source_filename.casefold(), ""))
    source_text = " ".join(source_contents)
    source_content_norm = compact(source_text)
    candidate_name_evidence = path.stem.split("_", 1)[0]
    source_norm = compact(source_text + " " + " ".join(text(row.get("filename")) for row in source_files) + " " + candidate_name_evidence)
    if not source_norm:
        issues.append(issue("source_text_unavailable", "high", "source.source_files", "", "无法读取任何 Word/语义 HTML 源证据"))
    raw_text = str(payload.get("raw_text") or "")
    if text((payload.get("extraction") or {}).get("raw_text_source")) != "canonical_deduplicated_pdf_word_html_text":
        issues.append(issue("raw_text_source_invalid", "critical", "extraction.raw_text_source", (payload.get("extraction") or {}).get("raw_text_source"), "raw_text 未声明为独立 PDF/Word/HTML 原文"))
    expected_raw_text = payload_raw_text(payload, sources)
    if raw_text.strip() != expected_raw_text.strip():
        issues.append(issue("raw_text_not_canonical", "critical", "raw_text", f"actual={len(raw_text)} expected={len(expected_raw_text)}", "raw_text 与去重后的完整 PDF/Word/HTML 证据文本不一致"))
    raw_norm = compact(raw_text)
    if source_content_norm:
        # Validate each source independently. Sampling the artificial string
        # formed by joining several documents crosses document boundaries and
        # incorrectly rejects a complete raw_text that contains source labels.
        incomplete_sources = []
        for source_index, source_content in enumerate(source_contents):
            current = compact(source_content)
            if not current:
                continue
            sample_size = min(160, max(40, len(current) // 20))
            starts = [int((len(current) - sample_size) * ratio / 4) for ratio in range(5)]
            matched_samples = sum(current[start:start + sample_size] in raw_norm for start in starts)
            if matched_samples < 3:
                incomplete_sources.append(f"{source_index + 1}:{matched_samples}/5")
        if incomplete_sources:
            issues.append(issue(
                "raw_text_incomplete", "critical", "raw_text",
                f"raw={len(raw_norm)}, sources={','.join(incomplete_sources)}",
                "raw_text 未完整覆盖 PDF/Word/HTML 源文本",
            ))
    structured = payload.get("structured_data") or {}
    for collection in RESUME_LISTS:
        if collection in structured:
            issues.append(issue(
                "unexpected_outer_list", "critical", f"structured_data.{collection}", "",
                "列表只能位于 structured_data.resumes[] 内，主对象不得保留重复快照",
            ))
    resumes = [row for row in (structured.get("resumes") or []) if isinstance(row, dict)]
    if not resumes:
        issues.append(issue("missing_resumes", "critical", "structured_data.resumes", "", "缺少语言简历"))
    else:
        primary = resumes[0]
        if text(primary.get("resume_language")) != "zh":
            issues.append(issue("primary_resume_not_chinese", "critical", "structured_data.resumes[0].resume_language", primary.get("resume_language"), "第一份简历必须是中文主版本"))
        if (structured.get("base_info") or {}) != (primary.get("base_info") or {}):
            issues.append(issue("snapshot_base_mismatch", "critical", "structured_data.base_info", "", "外层基本信息与主简历不一致"))
        expected_snapshot = (primary.get("expected_list") or [{}])[0] if primary.get("expected_list") else {field: "" for field in EXPECTED_FIELDS}
        if (structured.get("expected_info") or {}) != expected_snapshot:
            issues.append(issue("snapshot_expected_mismatch", "critical", "structured_data.expected_info", "", "求职意向快照与中文主简历第一条不一致"))
        work_rows = [row for row in (primary.get("work_experiences") or []) if isinstance(row, dict)]
        current_snapshot = max(
            work_rows,
            key=lambda row: date_tuple(row.get("position_resigned")) or date_tuple(row.get("position_start")) or (0, 0, 0),
            default={field: "" for field in CURRENT_FIELDS},
        )
        current_snapshot = {field: current_snapshot.get(field, "") for field in CURRENT_FIELDS}
        if (structured.get("current_info") or {}) != current_snapshot:
            issues.append(issue("snapshot_current_mismatch", "critical", "structured_data.current_info", "", "当前工作快照不是中文主简历最近一段的 15 字段对象"))
        education_rows = [row for row in (primary.get("education_list") or []) if isinstance(row, dict)]
        expected_education = max(
            education_rows,
            key=lambda row: (degree_value(row), date_tuple(row.get("school_end_ym")) or (0, 0, 0)),
            default={field: "" for field in EDUCATION_FIELDS},
        )
        expected_education = {field: expected_education.get(field, "") for field in EDUCATION_FIELDS}
        if (structured.get("education_info") or {}) != expected_education:
            issues.append(issue("snapshot_education_mismatch", "critical", "structured_data.education_info", "", "最高学历快照与中文主简历不一致"))
        check_object_schema(structured.get("base_info"), BASE_FIELDS, "structured_data.base_info", issues)
        check_object_schema(structured.get("expected_info"), EXPECTED_FIELDS, "structured_data.expected_info", issues)
        check_object_schema(structured.get("current_info"), CURRENT_FIELDS, "structured_data.current_info", issues)
        check_object_schema(structured.get("education_info"), EDUCATION_FIELDS, "structured_data.education_info", issues)
        validate_primary_enums(primary, issues)
    # The top-level collections are snapshots of the primary resume. Validate
    # their equality above, then inspect each language resume exactly once.
    for resume_index, resume in enumerate(resumes):
        validate_resume_schema(resume, resume_index, issues)
        walk(resume, f"structured_data.resumes[{resume_index}]", source_norm, issues)
        validate_row_source_anchors(resume, resume_index, source_norm, issues)
        language = text(resume.get("resume_language"))
        if language in {"ja", "en"}:
            prose_values = [("base_info.pr", text((resume.get("base_info") or {}).get("pr")))]
            for collection in ("work_experiences", "project_list", "training_list"):
                for row_index, row in enumerate(resume.get(collection) or []):
                    if not isinstance(row, dict):
                        continue
                    for field in ("position_responsibilities", "position_achievements", "description", "responsibilities", "achievements"):
                        if field in row:
                            prose_values.append((f"{collection}[{row_index}].{field}", text(row.get(field))))
            for relative_path, current in prose_values:
                han_count = len(re.findall(r"[\u3400-\u9fff]", current))
                kana_count = len(re.findall(r"[\u3040-\u30ff]", current))
                if han_count >= 20 and kana_count < 3:
                    issues.append(issue(
                        "foreign_variant_chinese_prose", "critical",
                        f"structured_data.resumes[{resume_index}].{relative_path}", current,
                        "英文/日文版本残留中文长段落，未保持语言版本纯净",
                    ))
    validate_field_traceability(resumes, source_norm, issues)
    for resume_index, resume in enumerate(resumes):
        for row_index, row in enumerate(resume.get("certificate_list") or []):
            if isinstance(row, dict) and not text(row.get("certificate_name")):
                issues.append(issue("empty_certificate_entity", "critical", f"structured_data.resumes[{resume_index}].certificate_list[{row_index}]", row.get("certificate_time"), "证书记录缺少证书名称"))
        for row_index, row in enumerate(resume.get("project_list") or []):
            if isinstance(row, dict) and not text(row.get("project_name")):
                issues.append(issue("empty_project_entity", "critical", f"structured_data.resumes[{resume_index}].project_list[{row_index}]", row.get("description"), "项目记录缺少项目名称"))
        for list_name, start_field, end_field in (
            ("work_experiences", "position_start", "position_resigned"),
            ("education_list", "school_start_ym", "school_end_ym"),
            ("project_list", "start_ym", "end_ym"),
            ("training_list", "start_ym", "end_ym"),
        ):
            for row_index, row in enumerate(resume.get(list_name) or []):
                if not isinstance(row, dict):
                    continue
                start, end = date_tuple(row.get(start_field)), date_tuple(row.get(end_field))
                if start and end and start > end:
                    issues.append(issue("reversed_date_range", "high", f"structured_data.resumes[{resume_index}].{list_name}[{row_index}]", "", "开始日期晚于结束日期"))
                if list_name == "work_experiences":
                    company, position = text(row.get("company_name")), text(row.get("position"))
                    status = text(row.get("status"))
                    if end and status in {"在职", "在籍", "就职中", "勤務中", "current", "present"}:
                        issues.append(issue("ended_work_marked_active", "high", f"structured_data.resumes[{resume_index}].{list_name}[{row_index}].status", status, "已有离职日期却标记为在职"))
                    if position and DEPARTMENT_ONLY_RE.fullmatch(position) and not ROLE_WORD_RE.search(position):
                        issues.append(issue("department_as_position", "high", f"structured_data.resumes[{resume_index}].{list_name}[{row_index}].position", position, "部门名称误入职位字段"))
                    if re.search(r"校园经历|学生会|社团经历|志愿者服务|义工|義工", company) and not COMPANY_RE.search(company):
                        issues.append(issue("campus_activity_as_work", "critical", f"structured_data.resumes[{resume_index}].{list_name}[{row_index}].company_name", company, "校园活动或志愿服务误入工作经历"))
                    if re.fullmatch(r"(?:外商投资企业|外资企业|日资企业|日系企业|民营企业|国有企业|政府机关|事业单位|合资企业|独资企业|company nature)", position, re.I):
                        issues.append(issue("company_nature_as_position", "critical", f"structured_data.resumes[{resume_index}].{list_name}[{row_index}].position", position, "公司性质误入职位字段"))
                    work_context = position + " " + text(row.get("position_responsibilities"))
                    if SCHOOL_RE.search(company) and not COMPANY_RE.search(company) and WORK_ROLE_RE.search(work_context):
                        issues[:] = [item for item in issues if not (item["code"] == "school_as_company" and item["path"] == f"structured_data.resumes[{resume_index}].{list_name}[{row_index}].company_name")]
                if list_name == "education_list":
                    school = text(row.get("school_name"))
                    education_type = text(row.get("school_education_type"))
                    degree_type = text(row.get("school_degree_type"))
                    education_context = " ".join((school, education_type, degree_type))
                    if re.search(r"小学|初中|中学|中學|中学校|中专|中等专业学校|高中|高级中学|高等学校|高校生", education_context):
                        issues.append(issue("low_education_not_allowed", "critical", f"structured_data.resumes[{resume_index}].{list_name}[{row_index}]", education_context, "高中、中专、初中或小学经历不得进入教育列表"))
                    if re.search(r"^(?:日本)?[^大学学院]{0,35}(?:幼稚园|幼稚園|幼儿园|保育園)", school) or (re.search(r"幼稚园|幼稚園|幼儿园|保育園", school) and not re.search(r"大学|学院", school)):
                        issues.append(issue("internship_as_education", "critical", f"structured_data.resumes[{resume_index}].{list_name}[{row_index}]", school, "幼儿园或实习经历误入教育列表"))
                    degree = text(row.get("school_degree_type"))
                    rank = text(row.get("school_degree_rank"))
                    if (re.search(r"本科|学士|Bachelor", degree, re.I) and rank not in {"", "4"}) or (re.search(r"硕士|修士|Master", degree, re.I) and rank not in {"", "5"}):
                        issues.append(issue("degree_rank_conflict", "critical", f"structured_data.resumes[{resume_index}].{list_name}[{row_index}]", f"{degree}/{rank}", "学历与等级编码冲突"))
                    if re.search(r"在职|在職", education_context) and re.search(r"全日制", education_type):
                        issues.append(issue("education_type_conflict", "critical", f"structured_data.resumes[{resume_index}].{list_name}[{row_index}]", education_context, "在职学历被标记为全日制"))
        education_rows = [row for row in (resume.get("education_list") or []) if isinstance(row, dict)]
        for left_index, left in enumerate(education_rows):
            left_core = school_core(left.get("school_name"))
            if len(left_core) < 2:
                continue
            for right_index in range(left_index + 1, len(education_rows)):
                right = education_rows[right_index]
                right_core = school_core(right.get("school_name"))
                same_core = left_core == right_core or (len(left_core) >= 3 and len(right_core) >= 3 and (left_core in right_core or right_core in left_core))
                if not same_core:
                    continue
                left_dates = (text(left.get("school_start_ym")), text(left.get("school_end_ym")))
                right_dates = (text(right.get("school_start_ym")), text(right.get("school_end_ym")))
                sparse = not all(left_dates) or not all(right_dates)
                overlapping = left_dates == right_dates or sparse
                left_degree = compact(left.get("school_degree_type"))
                right_degree = compact(right.get("school_degree_type"))
                same_degree = left_degree == right_degree or not left_degree or not right_degree
                if overlapping and same_degree:
                    issues.append(issue("semantic_duplicate_education", "critical", f"structured_data.resumes[{resume_index}].education_list[{right_index}]", right.get("school_name"), "同一学校的稀疏或同日期记录发生语义重复"))
    # A translated resume may localize names and descriptions, but it must not
    # invent or lose dated education/work/project/training rows from the same
    # source document.
    if len(resumes) > 1 and len(source_files) == 1:
        for list_name, start_field, end_field in (
            ("work_experiences", "position_start", "position_resigned"),
            ("education_list", "school_start_ym", "school_end_ym"),
            ("project_list", "start_ym", "end_ym"),
            ("training_list", "start_ym", "end_ym"),
        ):
            signatures = []
            for resume in resumes:
                signatures.append(sorted(
                    (text(row.get(start_field)), text(row.get(end_field)))
                    for row in (resume.get(list_name) or []) if isinstance(row, dict)
                ))
            if any(signature != signatures[0] for signature in signatures[1:]):
                issues.append(issue(
                    "cross_language_structure_mismatch", "critical", f"structured_data.resumes[].{list_name}",
                    json.dumps(signatures, ensure_ascii=False), "同一源文件的多语言版本存在记录数量或日期结构差异",
                ))
        primary_name = text((resumes[0].get("base_info") or {}).get("full_name"))
        for resume_index, resume in enumerate(resumes[1:], 1):
            variant_name = text((resume.get("base_info") or {}).get("full_name"))
            if LABEL_ONLY_RE.fullmatch(variant_name) or re.fullmatch(r"ふりがな|フリガナ|氏名|姓名|name", variant_name, re.I):
                issues.append(issue("name_label_as_value", "critical", f"structured_data.resumes[{resume_index}].base_info.full_name", variant_name, "姓名字段误取模板标签"))
            primary_phone = re.sub(r"\D", "", text((resumes[0].get("base_info") or {}).get("phone"))).removeprefix("86")
            variant_phone = re.sub(r"\D", "", text((resume.get("base_info") or {}).get("phone"))).removeprefix("86")
            if primary_phone and variant_phone and primary_phone != variant_phone:
                issues.append(issue("cross_language_phone_mismatch", "critical", f"structured_data.resumes[{resume_index}].base_info.phone", variant_phone, "同一源文件多语言版本手机号不一致"))
    unique: dict[tuple[str, str, str], dict[str, Any]] = {}
    for item in issues:
        unique[(item["code"], item["path"], item["value"])] = item
    issues = sorted(unique.values(), key=lambda row: (-SEVERITY[row["severity"]], row["code"], row["path"]))
    verified = (payload.get("extraction") or {}).get("semantic_review") or {}
    def is_verified_source_exception(item: dict[str, Any]) -> bool:
        item_code = item["code"]
        item_path = item["path"]
        if item_code == "school_as_company" and ".work_experiences[" in item_path and verified.get("pdf_verified_work"):
            return True
        if item_code not in {"field_not_supported_by_source", "field_not_traceable_to_source", "row_not_traceable_to_source"}:
            return False
        return bool(
            (".education_list[" in item_path and verified.get("pdf_verified_education"))
            or (".work_experiences[" in item_path and verified.get("pdf_verified_work"))
            or (".expected_list[" in item_path and verified.get("pdf_verified_expected"))
            or (".certificate_list[" in item_path and verified.get("pdf_verified_certificates"))
            or (".language_list[" in item_path and verified.get("pdf_verified_languages"))
            or (".skills_list[" in item_path and verified.get("pdf_verified_skills"))
            or (".training_list[" in item_path and verified.get("pdf_verified_training"))
            or (".project_list[" in item_path and verified.get("pdf_verified_projects"))
            or (".base_info." in item_path and verified.get("pdf_verified_base"))
            or (item_path.endswith(".base_info.full_name") and verified.get("pdf_verified_name"))
            or (item_path.endswith(".base_info.phone") and verified.get("pdf_verified_phone"))
            or (item_path.endswith(".base_info.email") and verified.get("pdf_verified_email"))
        )
    issues = [item for item in issues if not is_verified_source_exception(item)]
    maximum = max((SEVERITY[row["severity"]] for row in issues), default=0)
    max_severity = next((name for name, rank in SEVERITY.items() if rank == maximum), "clean")
    return {
        "json_file": str(path.resolve()), "filename": path.name,
        "full_name": text((structured.get("base_info") or {}).get("full_name")),
        "source_files": [text(row.get("filename")) for row in source_files],
        "source_text_chars": len(source_norm), "max_severity": max_severity,
        "strict_status": "failed" if maximum >= SEVERITY["high"] else ("review" if maximum else "clean"),
        "issue_count": len(issues), "issues": issues,
    }


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
    sources = source_index(mapping)
    records: list[dict[str, Any]] = []
    unreadable: list[dict[str, str]] = []
    for path in sorted(cfg.json_root.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8-sig"))
            records.append(validate(path, payload, sources))
        except Exception as exc:
            unreadable.append({"file": str(path.resolve()), "error": str(exc)})
    status_counts = Counter(row["strict_status"] for row in records)
    code_counts = Counter(item["code"] for row in records for item in row["issues"])
    severity_counts = Counter(item["severity"] for row in records for item in row["issues"])
    report = {
        "version": VERSION, "generated_at": datetime.now().astimezone().isoformat(),
        "json_root": str(cfg.json_root.resolve()), "json_count": len(records) + len(unreadable),
        "parsed_count": len(records), "unreadable_count": len(unreadable),
        "clean_file_count": status_counts["clean"], "review_file_count": status_counts["review"],
        "strict_failure_file_count": status_counts["failed"] + len(unreadable),
        "total_issue_count": sum(code_counts.values()) + len(unreadable),
        "status_counts": dict(status_counts), "issue_severity_counts": dict(severity_counts),
        "issue_code_counts": dict(code_counts.most_common()), "unreadable": unreadable, "records": records,
    }
    atomic_json(cfg.report, report)
    cfg.csv.parent.mkdir(parents=True, exist_ok=True)
    with cfg.csv.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=("filename", "full_name", "status", "severity", "code", "path", "value", "message"))
        writer.writeheader()
        for row in records:
            for item in row["issues"]:
                writer.writerow({"filename": row["filename"], "full_name": row["full_name"], "status": row["strict_status"], "severity": item["severity"], **item})
    print(json.dumps({key: value for key, value in report.items() if key not in {"records", "unreadable"}}, ensure_ascii=False, indent=2))
    print(f"report={cfg.report.resolve()}")
    print(f"csv={cfg.csv.resolve()}")
    return 1 if report["strict_failure_file_count"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
