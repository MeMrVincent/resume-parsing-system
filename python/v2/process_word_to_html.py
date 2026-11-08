from __future__ import annotations
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1] / "common"))
import rc_config as _rc  # noqa: E402  项目统一配置（python/common/rc_config.py）
# EN: noqa: E402  project-wide configuration (python/common/rc_config.py)
# JA: noqa: E402  プロジェクト共通設定（python/common/rc_config.py）

import argparse
import hashlib
import html
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime
from email import policy
from email.parser import BytesParser
from pathlib import Path
from typing import Any

import openpyxl
from bs4 import BeautifulSoup, Comment, NavigableString, Tag


PROJECT_ROOT = _rc.project_root()
PYTHON_ROOT = _rc.PYTHON_DIR / "v2"
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

GENERATOR_VERSION = "2.4.2"
SCHEMA_VERSION = "resume-dom-v1"
TARGET_DATA_SCHEMA = "complete-v1"
OVERRIDES_PATH = PYTHON_ROOT / "word_conversion_overrides.json"

CANDIDATE_ID_RE = re.compile(
    r"(?:^|\s)(?:候选人(?:简历)?\s*ID|简历\s*ID|Resume\s*ID|ID)\s*[:：#]\s*(\d{6,})",
    re.IGNORECASE,
)


def _path_key(value: str | Path) -> str:
    return str(Path(value).resolve()).replace("/", "\\").casefold()


def load_conversion_overrides() -> dict[str, dict[str, Any]]:
    if not OVERRIDES_PATH.is_file():
        return {}
    payload = json.loads(OVERRIDES_PATH.read_text(encoding="utf-8"))
    return {_path_key(path): dict(rule) for path, rule in payload.items()}


CONVERSION_OVERRIDES = load_conversion_overrides()

EMAIL_STANDARD_RE = re.compile(
    r"[A-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?(?:\.[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?)+",
    re.IGNORECASE,
)
EMAIL_FUZZY_RE = re.compile(
    r"([A-Z0-9.!#$%&'*+/=?^_`{|}~-]{2,40})\s*(?:@|＠|\ufffd|\[at\]|\(at\))\s*([A-Z0-9-]{1,30}\.(?:com|cn|net|org|jp|edu|gov|co\.jp|163|qq|gmail|126|sina|sohu|foxmail|hotmail|outlook|yahoo)[a-z]*)\b",
    re.IGNORECASE,
)
CN_MOBILE_RE = re.compile(r"(?<!\d)(?:\+?86[-\s]?)?1[3-9]\d(?:[-\s]?\d){8}(?!\d)")
JP_MOBILE_RE = re.compile(r"(?<!\d)0[789]0[-\s]?\d{4}[-\s]?\d{4}(?!\d)")
INT_MOBILE_RE = re.compile(r"(?<!\d)\+(?:\d[-\s().]?){8,15}(?!\d)")
TEL_KEYWORD_RE = re.compile(
    r"(?:电话|電話|手機|手机|TEL|携帯|連絡先|联系方式)[：:\s]*([+\d\-\s().]{7,20})",
    re.IGNORECASE,
)

ALLOWED_TAGS = {
    "a", "article", "aside", "blockquote", "br", "caption", "code", "col",
    "colgroup", "dd", "div", "dl", "dt", "em", "figcaption", "figure",
    "footer", "h1", "h2", "h3", "h4", "h5", "h6", "header", "hr",
    "li", "main", "ol", "p", "pre", "section", "small", "span", "strong",
    "sub", "sup", "table", "tbody", "td", "tfoot", "th", "thead", "tr", "ul",
}
GLOBAL_SAFE_ATTRS = {"id", "lang", "dir", "title"}
TAG_SAFE_ATTRS = {
    "a": {"href", "rel"},
    "ol": {"start", "reversed", "type"},
    "li": {"value"},
    "td": {"rowspan", "colspan", "headers"},
    "th": {"rowspan", "colspan", "headers", "scope", "abbr"},
    "col": {"span"},
    "colgroup": {"span"},
}

SECTION_ALIASES = {
    "base_info": {
        "个人信息", "基本信息", "个人资料", "基本资料", "个人概况", "基本情况",
        "個人情報", "基本情報", "personal information", "personal details", "profile",
    },
    "expected_list": {
        "求职意向", "职业目标", "期望职位", "希望職種", "志望動機", "career objective",
        "objective", "desired position", "job objective",
    },
    "work_experiences": {
        "工作经历", "工作经验", "职业经历", "任职经历", "工作履历", "職務経歴",
        "職歴", "勤務経歴", "work experience", "employment history", "professional experience",
    },
    "project_list": {
        "项目经历", "项目经验", "プロジェクト経験", "project experience", "projects",
    },
    "education_list": {
        "教育经历", "教育背景", "统招教育经历", "学历", "学历信息", "学历背景", "学歴", "教育経歴", "education",
        "education background", "academic background",
    },
    "skills_list": {
        "专业技能", "技能特长", "职业技能", "技术能力", "能力特长", "スキル",
        "skills", "technical skills", "core competencies",
    },
    "language_list": {
        "语言能力", "语言技能", "外语能力", "語学力", "言語", "languages", "language skills",
    },
    "certificate_list": {
        "证书", "资格证书", "所获证书", "資格", "免許・資格", "certifications",
        "certificates", "licenses",
    },
    "self_evaluation": {
        "自我评价", "自我介绍", "个人评价", "自我总结", "自己評価", "自己紹介",
        "summary", "professional summary", "self evaluation", "self-assessment", "about me",
    },
    "communication_list": {
        "获奖情况", "荣誉奖励", "受賞歴", "awards", "honors", "顾问评价", "猎头评语",
        "推荐意见", "headhunter's evaluation", "consultant comments",
    },
    "training_list": {"培训经历", "培训经验", "研修", "training", "training experience"},
}
SECTION_LOOKUP = {
    re.sub(r"[\s:：·・•|｜_\-【】\[\]（）()]+", "", alias).casefold(): section_type
    for section_type, aliases in SECTION_ALIASES.items()
    for alias in aliases
}

# Only exact, explicit labels are annotated. Ambiguous free text remains untouched.
COMMON_FIELD_ALIASES = {
    "full_name": {"姓名", "名字", "氏名", "name", "full name"},
    "gender": {"性别", "性別", "sex", "gender"},
    "age": {"年龄", "年齢", "age"},
    "birth_date": {"出生日期", "出生年月日", "生年月日", "date of birth", "birthday"},
    "birth_year": {"出生年份", "出生年", "birth year"},
    "marital_status": {"婚姻状况", "婚姻状況", "婚姻状態", "配偶者", "marital status"},
    "children_status": {"子女状况", "子女情况", "children"},
    "political_status": {"政治面貌", "政治身份"},
    "height_cm": {"身高", "height"},
    "weight_kg": {"体重", "weight"},
    "household_registration": {"户籍", "戶籍", "戸籍", "户口", "籍贯", "本籍", "出身地", "household registration", "hukou"},
    "address": {"地址", "现居住地", "居住地", "住址", "住所", "address"},
    "postal_code": {"邮编", "邮政编码", "郵便番号", "postal code", "zip code"},
    "platform_from": {"简历来源", "来源平台", "platform"},
    "platform_resume_id": {"简历id", "resume id", "candidate id"},
    "phone": {"电话", "手机", "联系电话", "联系方式", "電話", "携帯", "携帯電話番号", "連絡先", "phone", "mobile", "tel"},
    "email": {"邮箱", "电子邮箱", "邮件", "メールアドレス", "email", "e-mail", "e-mai"},
    "city": {"城市", "所在城市", "现居城市", "居住城市", "city", "current city"},
    "nationality": {"国籍", "nationality"},
    "pr": {"自我评价", "自我介绍", "个人评价", "自己評価", "自己紹介", "professional summary", "summary"},
}

FIELD_DISPLAY_LABELS = {
    "full_name": "姓名",
    "gender": "性别",
    "age": "年龄",
    "birth_date": "生日",
    "birth_year": "出生年份",
    "marital_status": "婚姻",
    "household_registration": "户籍",
    "phone": "手机",
    "email": "邮箱",
    "city": "城市",
    "nationality": "国籍",
}

SCOPED_FIELD_ALIASES = {
    "expected_list": {
        "expected_city": {"期望城市", "希望城市", "希望勤務地", "desired city", "preferred location"},
        "expected_position": {"期望职位", "求职职位", "希望職種", "desired position", "position desired", "preferred function"},
        "expected_salary": {"期望薪资", "希望薪资", "希望給料", "expected salary", "desired salary"},
        "expected_annual_salary_min": {"期望年薪下限", "最低年薪"},
        "expected_annual_salary_max": {"期望年薪上限", "最高年薪"},
        "expected_industry": {"期望行业", "希望行业", "desired industry", "preferred industry"},
        "expected_employment_type": {"期望工作性质", "期望雇佣类型", "employment type", "job type"},
        "expected_start_date": {"到岗时间", "可入职时间", "入社可能日", "available date", "job status"},
    },
    "work_experiences": {
        "company_name": {"公司", "公司名", "公司名称", "单位名称", "勤務先", "会社名", "company", "employer"},
        "company_employees": {"公司规模", "员工人数", "员工数量", "従業員数", "社員数", "規模", "company size"},
        "company_industry": {
            "行业", "行业/事业内容", "所属行业", "公司行业", "業界", "業種", "業種/事業内容", "事業内容", "industry",
        },
        "company_nature": {
            "公司性质", "公司性質", "企业性质", "企业类型", "会社形態", "会社性質",
            "資本", "資本形態", "company type", "type of company", "ownership",
        },
        "position": {"职位", "职位名称", "职务", "職位", "職位名", "役職", "ポジション", "position", "job title"},
        "position_type": {"职位类别", "职能类别", "職種", "position type"},
        "position_salary": {"月薪", "职位薪资", "monthly salary"},
        "position_dept": {"部门", "部门名称", "部署", "所属部署", "所属部门", "所属部門", "所属", "department"},
        "position_report_to": {"汇报对象", "上司", "reports to"},
        "position_subordinate": {"下属人数", "部下人数", "subordinates"},
        "employment_type": {"雇佣类型", "工作性质", "雇用形態", "employment type"},
        "annual_salary_min": {"年薪下限", "最低年薪"},
        "annual_salary_max": {"年薪上限", "最高年薪"},
        "status": {"在职状态", "任职状态", "勤务状况", "勤務状況", "就業状況", "status"},
        "position_start": {"入职时间", "入职年月", "入社年月", "开始时间", "勤務開始", "start date"},
        "position_resigned": {"离职时间", "离职年月", "退社年月", "结束时间", "退職日", "end date"},
        "resigned_reason": {"离职原因", "离职理由", "退职原因", "退职理由", "退職理由", "reason for leaving"},
        "position_responsibilities": {
            "工作职责", "职责描述", "工作描述", "工作内容", "职务内容", "业务内容", "仕事内容", "職務内容", "業務内容",
            "responsibilities", "job description",
        },
        "position_achievements": {"工作业绩", "主要业绩", "成果", "achievements"},
    },
    "education_list": {
        "school_name": {"学校", "学校名", "学校名称", "院校", "毕业院校", "卒業学校", "大学", "school", "school name", "university"},
        "school_major_name": {"专业", "专 业", "专业名称", "学科", "専攻", "学部/学科/専攻", "major"},
        "school_degree_type": {"学历", "学位", "学历＆学位", "学歴＆学位", "学历类型", "degree", "education level"},
        "school_degree_rank": {"学历等级", "degree rank"},
        "school_education_type": {"培养方式", "学习形式", "education type"},
        "school_start_ym": {"入学时间", "教育开始时间", "start date"},
        "school_end_ym": {"毕业时间", "结业时间", "教育结束时间", "graduation date", "end date"},
    },
    "certificate_list": {
        "certificate_name": {"证书名称", "资格证书", "資格", "certificate"},
        "certificate_type": {"证书类型", "certificate type"},
        "certificate_time": {"取得时间", "证书时间", "取得年月", "certificate date"},
    },
    "language_list": {
        "language_name": {"语言", "语言名称", "語学", "言語", "language"},
        "language_level": {"语言水平", "熟练程度", "語学レベル", "language level", "proficiency"},
        "language_certificate": {"语言证书", "語学資格", "language certificate"},
        "language_certificate_time": {"证书取得时间", "資格取得年月", "certificate date"},
    },
    "skills_list": {
        "skill_name": {"技能", "技能名称", "スキル", "skill"},
        "skill_level": {"熟练度", "技能水平", "レベル", "skill level", "proficiency"},
    },
    "training_list": {
        "organization_name": {"培训机构", "培训组织", "研修機関", "organization"},
        "training_name": {"培训名称", "课程名称", "研修名", "training name"},
        "start_ym": {"开始时间", "培训开始时间", "start date"},
        "end_ym": {"结束时间", "培训结束时间", "end date"},
        "certificate_name": {"所获证书", "证书名称", "certificate"},
        "description": {"培训内容", "培训描述", "研修内容", "description"},
    },
    "project_list": {
        "project_name": {"项目名称", "プロジェクト名", "project name"},
        "company_or_client": {"所在公司", "客户", "顧客", "client"},
        "role_name": {"项目角色", "担任角色", "役割", "role"},
        "start_ym": {"开始时间", "项目开始时间", "start date"},
        "end_ym": {"结束时间", "项目结束时间", "end date"},
        "description": {"项目描述", "项目介绍", "概要", "description"},
        "responsibilities": {"项目职责", "担当業務", "responsibilities"},
        "achievements": {"项目业绩", "项目成果", "成果", "achievements"},
        "keywords": {"关键词", "关键技术", "keywords"},
    },
    "communication_list": {
        "communicate_time": {"沟通时间", "评价时间", "面談日時", "communication time"},
        "communicate_content": {"沟通内容", "顾问评价", "猎头评语", "推荐意见", "自己評価", "communication"},
    },
}


def _normalized_label(value: str) -> str:
    return re.sub(r"[\s:：·•|｜_\-]+", "", value).casefold()


COMMON_FIELD_LOOKUP = {
    _normalized_label(alias): field
    for field, aliases in COMMON_FIELD_ALIASES.items()
    for alias in aliases
}
SCOPED_FIELD_LOOKUP = {
    scope: {
        _normalized_label(alias): field
        for field, aliases in fields.items()
        for alias in aliases
    }
    for scope, fields in SCOPED_FIELD_ALIASES.items()
}


def source_path_hash(path_str: str) -> str:
    normalized = str(Path(path_str).resolve()).replace("/", "\\").casefold()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:12]


def safe_stem(value: str) -> str:
    cleaned = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", value).strip(" ._")
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned[:120] or "document"


def normalize_fullwidth_digits(text: str) -> str:
    table = str.maketrans("０１２３４５６７８９＠－", "0123456789@-")
    return text.translate(table)


def extract_contacts(text: str) -> tuple[str, str]:
    norm_text = normalize_fullwidth_digits(text)
    email_match = EMAIL_STANDARD_RE.search(norm_text)
    email = email_match.group(0).strip() if email_match else ""
    if not email:
        fuzzy_match = EMAIL_FUZZY_RE.search(norm_text)
        if fuzzy_match:
            email = f"{fuzzy_match.group(1).strip()}@{fuzzy_match.group(2).strip()}"

    # Word 表格导出时手机与邮箱可能没有任何分隔：
    # 13800000010 + user1@example.com。
    # EN: When Word tables are exported, phone and e-mail may have no separator at all:
    #     13800000010 + user1@example.com.
    # JA: Word の表をエクスポートすると、電話番号とメールの間に区切りが一切ないことがある：
    #     13800000010 + user1@example.com。
    glued = re.fullmatch(r"(1[3-9]\d{9})([A-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Z0-9.-]+\.[A-Z]{2,})", email, re.I)
    glued_phone = ""
    if glued:
        glued_phone, email = glued.group(1), glued.group(2)

    phone_match = CN_MOBILE_RE.search(norm_text) or JP_MOBILE_RE.search(norm_text) or INT_MOBILE_RE.search(norm_text)
    phone = phone_match.group(0).strip() if phone_match else glued_phone
    if not phone:
        tel_kw_match = TEL_KEYWORD_RE.search(norm_text)
        if tel_kw_match:
            raw_phone = tel_kw_match.group(1).strip()
            if len(re.sub(r"[^\d+]", "", raw_phone)) >= 7:
                phone = raw_phone
    return phone, email


def looks_like_mhtml(raw_bytes: bytes) -> bool:
    head = raw_bytes[:8192].lower()
    return b"mime-version:" in head and (b"multipart/" in head or b"content-transfer-encoding:" in head)


def decode_bytes(payload: bytes, declared_charset: str = "") -> str:
    charset = declared_charset.lower().strip().replace("unicode", "utf-16")
    if payload.startswith((b"\xff\xfe", b"\xfe\xff")) or payload[:200].count(b"\x00") > 20:
        candidates = ("utf-16", "utf-16-le", "utf-16-be", "utf-8", "gb18030", "big5")
    else:
        candidates = tuple(x for x in (charset, "utf-8", "gb18030", "big5") if x)
    for encoding in dict.fromkeys(candidates):
        try:
            return payload.decode(encoding)
        except (LookupError, UnicodeDecodeError):
            continue
    return payload.decode("utf-8", errors="replace")


def decode_mhtml(raw_bytes: bytes) -> str:
    message = BytesParser(policy=policy.default).parsebytes(raw_bytes)
    html_parts: list[str] = []
    for part in message.walk():
        if part.get_content_type().lower() != "text/html":
            continue
        payload = part.get_payload(decode=True)
        if payload is None:
            value = part.get_payload()
            if isinstance(value, str):
                html_parts.append(value)
        else:
            html_parts.append(decode_bytes(payload, part.get_content_charset() or ""))
    if not html_parts:
        raise ValueError("MHTML 中没有 text/html 部分")
    return max(html_parts, key=len)


def read_file_text_safe(path_p: Path) -> str:
    if not path_p.exists():
        return ""
    try:
        raw_bytes = path_p.read_bytes()
    except OSError:
        return ""
    if not raw_bytes:
        return ""
    if looks_like_mhtml(raw_bytes):
        try:
            return decode_mhtml(raw_bytes)
        except Exception:
            pass
    charset_match = re.search(rb"charset=[\"']?\s*([a-zA-Z0-9_\-]+)", raw_bytes[:4096], re.IGNORECASE)
    declared = charset_match.group(1).decode("ascii", errors="ignore") if charset_match else ""
    return decode_bytes(raw_bytes, declared)


def _safe_url(value: str, *, image: bool = False) -> str:
    candidate = html.unescape(value or "").strip()
    lowered = candidate.casefold()
    allowed = ("http://", "https://", "mailto:", "tel:", "#")
    if image:
        allowed = allowed + ("data:image/", "cid:")
    if candidate and (lowered.startswith(allowed) or ":" not in candidate.split("/", 1)[0]):
        return candidate
    return ""


def clean_html_styles(html_text: str) -> str:
    """Return a safe HTML fragment while preserving document structure."""
    if not html_text:
        return ""
    soup = BeautifulSoup(html_text, "html.parser")
    for node in soup.find_all(string=lambda value: isinstance(value, Comment)):
        node.extract()
    for node in soup.find_all(string=True):
        if isinstance(node, Comment):
            continue
        cleaned = re.sub(r"\[\s*pic\s*\]", "", str(node), flags=re.I)
        if cleaned != str(node):
            node.replace_with(cleaned)
    for tag in soup.find_all(["script", "style", "xml", "link", "meta", "title", "head", "iframe", "object", "embed", "img"]):
        tag.decompose()

    root: Tag | BeautifulSoup = soup.body or soup
    for tag in list(root.find_all(True)):
        name = tag.name.casefold()
        if name in {"b", "i"}:
            tag.name = "strong" if name == "b" else "em"
            name = tag.name
        if ":" in name or name not in ALLOWED_TAGS:
            tag.unwrap()
            continue
        keep = GLOBAL_SAFE_ATTRS | TAG_SAFE_ATTRS.get(name, set())
        attrs = {key.casefold(): value for key, value in tag.attrs.items() if key.casefold() in keep}
        if name == "a" and "href" in attrs:
            href = _safe_url(str(attrs["href"]))
            if href:
                attrs["href"] = href
                attrs["rel"] = "noopener noreferrer" if href.startswith(("http://", "https://")) else attrs.get("rel", "")
            else:
                attrs.pop("href", None)
                attrs.pop("rel", None)
        tag.attrs = {key: value for key, value in attrs.items() if value not in (None, "")}

    contents = list(root.contents)
    return "".join(str(node) for node in contents).strip()


def strip_tags(html_text: str) -> str:
    soup = BeautifulSoup(html_text or "", "html.parser")
    return re.sub(r"\s+", " ", soup.get_text(" ", strip=True)).strip()


def detect_language(text: str) -> str:
    if re.search(r"[\u3040-\u30ff]", text):
        return "ja"
    if re.search(r"[\u4e00-\u9fff]", text):
        return "zh-CN"
    return "en"


def section_type_for(text: str) -> str:
    key = re.sub(r"[\s:：·・•|｜_\-【】\[\]（）()]+", "", text).casefold()
    special = {
        "資格取得": "certificate_list",
        "免許資格": "certificate_list",
        "資格証書": "certificate_list",
        "資格証明書": "certificate_list",
        "学歴高校入学から": "education_list",
        "職務経歴": "work_experiences",
    }
    if re.match(r"^職歴シート\d*$", key, re.I):
        return "work_experiences"
    if key in special:
        return special[key]
    exact = SECTION_LOOKUP.get(key, "")
    if exact:
        return exact
    # Japanese/Excel headings commonly append instructions to the canonical
    # section label (e.g. 職歴（現職から入力してください）).  Keep the
    # prefix match narrow so ordinary labels such as 工作内容 are untouched.
    for alias, section_type in sorted(SECTION_LOOKUP.items(), key=lambda item: len(item[0]), reverse=True):
        if key.startswith(alias) and len(key) <= len(alias) + 32:
            return section_type
    return ""


def _only_meaningful_child(tag: Tag) -> Tag | None:
    children = [child for child in tag.children if isinstance(child, Tag)]
    text_nodes = [child for child in tag.children if isinstance(child, NavigableString) and child.strip()]
    return children[0] if len(children) == 1 and not text_nodes else None


def _make_tag(name: str) -> Tag:
    return BeautifulSoup("", "html.parser").new_tag(name)


def promote_known_headings(container: Tag) -> None:
    for paragraph in list(container.find_all("p")):
        text = paragraph.get_text(" ", strip=True)
        section_type = section_type_for(text)
        if not section_type:
            continue
        child = _only_meaningful_child(paragraph)
        if child is not None and child.name not in {"strong", "em", "span"}:
            continue
        heading = _make_tag("h2")
        heading.string = text.rstrip("：:")
        heading["data-section-type"] = section_type
        paragraph.replace_with(heading)
    for heading in container.find_all(["h1", "h2", "h3", "h4", "h5", "h6"]):
        section_type = section_type_for(heading.get_text(" ", strip=True))
        if section_type:
            heading["data-section-type"] = section_type


def normalize_tables(container: Tag) -> None:
    for table_index, table in enumerate(container.find_all("table"), 1):
        table["data-table-index"] = str(table_index)
        rows = table.find_all("tr")
        for row_index, row in enumerate(rows, 1):
            row["data-row-index"] = str(row_index)
            cells = row.find_all(["th", "td"], recursive=False)
            for column_index, cell in enumerate(cells, 1):
                cell["data-column-index"] = str(column_index)
                if cell.name == "th" and "scope" not in cell.attrs:
                    cell["scope"] = "col" if row_index == 1 else "row"


EMBEDDED_SECTION_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("education_list", re.compile(r"^(?:学歴|学历|教育经历|教育背景)$", re.I)),
    ("work_experiences", re.compile(r"^(?:職歴|工作经历|工作经验|職務経歴)$", re.I)),
    ("expected_list", re.compile(r"^(?:本人希望記入欄|求职意向|希望条件).*$", re.I)),
    ("certificate_list", re.compile(r"^(?:資格|资格|資格・免許|证书).*$", re.I)),
    ("self_evaluation", re.compile(r"^(?:自己PR|自己ＰＲ|自我评价|自我介绍)[:：]?(?:\s.*)?$", re.I)),
)


def embedded_section_type(row: Tag) -> str:
    text = re.sub(r"\s+", "", row.get_text(" ", strip=True)).strip()
    # Spreadsheet-derived tables often retain a leading blank cell, so the
    # section marker is not necessarily the first physical ``td``.  The marker
    # cell may also contain an instruction after the title, for example
    # ``◆職歴 ★職務内容は…``.  Inspect meaningful direct cells and anchor the
    # match at the beginning of the cell instead of requiring whole-row equality.
    for cell in row.find_all(["th", "td"], recursive=False):
        cell_text = re.sub(
            r"^[\s◆◇■□●○▲△▼▽★☆※]+", "", cell.get_text(" ", strip=True)
        ).strip()
        if not cell_text:
            continue
        first_compact = _normalized_label(cell_text)
        if first_compact in {"学歴", "学历", "教育经历", "教育背景"} or re.match(
            r"^(?:学\s*歴|学历|教育经历|教育背景)(?:\s|[:：]|[★☆※])", cell_text, re.I
        ):
            return "education_list"
        if first_compact in {"職歴", "职历", "工作经历", "工作经验", "职业经历", "職務経歴"} or re.match(
            r"^(?:職\s*歴|职历|工作经历|工作经验|职业经历|職務経歴)(?:\s|[:：]|[★☆※])", cell_text, re.I
        ):
            return "work_experiences"
        cell_section = section_type_for(cell_text)
        if cell_section:
            return cell_section
    direct_labels = {
        re.sub(
            r"[\s:：·・•|｜_/／【】\[\]（）()]+", "",
            cell.get_text(" ", strip=True).rstrip("：:"),
        )
        for cell in row.find_all(["th", "td"], recursive=False)
        if cell.get_text(" ", strip=True)
    }
    if (
        {"学校名", "学部学科専攻"}.issubset(direct_labels)
        and any(label.startswith("在籍期間") for label in direct_labels)
    ):
        return "education_list"
    if {"取得年月", "資格名"}.issubset(direct_labels):
        return "certificate_list"
    if re.search(r"学歴(?:・留学先|・職歴|・専攻)|年月.*学歴", text, re.I):
        return "education_list"
    if re.search(r"職歴・職務経歴|年月.*職歴", text, re.I):
        return "work_experiences"
    compact = re.sub(r"[\s:：·・•|｜_\-【】\[\]（）()]+", "", text).casefold()
    if compact in {"資格取得", "免許資格", "資格証書", "資格証明書", "価資格証明書"}:
        return "certificate_list"
    if compact in {"学歴高校入学から", "学歴", "職歴", "職務経歴"}:
        return "education_list" if compact.startswith("学歴") else "work_experiences"
    for section_type, pattern in EMBEDDED_SECTION_PATTERNS:
        if pattern.match(text):
            return section_type
    return section_type_for(text)


def split_embedded_table_sections(container: Tag) -> None:
    """把 Word 表格内部的章节标题行提升为真正的 DOM section 边界。

    EN: Promote section heading rows inside Word tables to real DOM section boundaries.

    JA: Word の表内にある章見出し行を、実際の DOM の section 境界に格上げする。
    """
    for table in list(container.find_all("table")):
        # 日文履歴書常把“学 歴/職 歴”塞在日期行或总表头的末尾。
        # 先把这个尾部标题拆成独立行，同时保留同一行中的毕业日期等数据。
        # EN: Japanese rirekisho often cram the "学 歴/職 歴" (education/work history) heading at the end of a date line or the main table header.
        #     First split this trailing heading into its own line, while keeping data such as the graduation date on the same line.
        # JA: 日本の履歴書では「学 歴／職 歴」の見出しが日付行や表全体のヘッダーの末尾に詰め込まれていることが多い。
        #     まずこの末尾の見出しを独立した行に分け、同じ行にある卒業日などのデータは残す。
        for row in list(_direct_table_rows(table)):
            row_text = row.get_text(" ", strip=True)
            for marker, before in (("学歴", True), ("職歴", False)):
                spaced = r"\s*".join(re.escape(char) for char in marker)
                if not re.search(spaced + r"\s*$", row_text) or _normalized_label(row_text) == marker:
                    continue
                target_cell = next(
                    (cell for cell in reversed(row.find_all(["th", "td"], recursive=False)) if re.search(spaced + r"\s*$", cell.get_text(" ", strip=True))),
                    None,
                )
                if target_cell is None:
                    continue
                remaining = re.sub(spaced + r"\s*$", "", target_cell.get_text(" ", strip=True)).strip()
                target_cell.clear()
                if remaining:
                    target_cell.string = remaining
                marker_row = _make_tag("tr")
                marker_cell = _make_tag("td")
                marker_cell.string = marker
                marker_row.append(marker_cell)
                if before:
                    row.insert_before(marker_row)
                else:
                    row.insert_after(marker_row)
                break
        rows = _direct_table_rows(table)
        boundaries = [(index, embedded_section_type(row)) for index, row in enumerate(rows)]
        boundaries = [(index, kind) for index, kind in boundaries if kind]
        # ``工作内容/業務内容`` is normally a field inside each employment
        # record, not a new top-level section.  Use its first occurrence only as
        # a fallback when the table has no explicit work-history heading at all.
        if not any(kind == "work_experiences" for _index, kind in boundaries):
            fallback_work_index = next(
                (
                    index
                    for index, row in enumerate(rows)
                    if _normalized_label(row.get_text(" ", strip=True).rstrip("：:"))
                    in {"工作内容", "仕事内容", "業務内容"}
                ),
                None,
            )
            if fallback_work_index is not None:
                boundaries.append((fallback_work_index, "work_experiences"))
                boundaries.sort(key=lambda item: item[0])
        if not boundaries:
            continue
        replacement: list[Tag] = []
        first_boundary = boundaries[0][0]
        if first_boundary:
            prefix = _make_tag("table")
            prefix.attrs = dict(table.attrs)
            for row in rows[:first_boundary]:
                prefix.append(row.extract())
            replacement.append(prefix)
        for boundary_index, (start, section_type) in enumerate(boundaries):
            end = boundaries[boundary_index + 1][0] if boundary_index + 1 < len(boundaries) else len(rows)
            marker = rows[start]
            heading = _make_tag("h2")
            heading["data-section-type"] = section_type
            heading.string = marker.get_text(" ", strip=True).rstrip("：:")
            replacement.append(heading)
            fragment = _make_tag("table")
            fragment.attrs = dict(table.attrs)
            # 纯标题行不重复进入数据表；包含其他字段/值的复合行予以保留。
            # EN: Pure heading rows are not repeated in the data table; composite rows that contain other fields/values are kept.
            # JA: 見出しだけの行はデータ表に重複して入れない。他のフィールドや値を含む複合行は残す。
            marker_cells = marker.find_all(["th", "td"], recursive=False)
            marker_text = re.sub(r"\s+", "", marker.get_text(" ", strip=True))
            pure_marker = len(marker_cells) <= 1 and marker_text in {
                "学歴", "学历", "教育经历", "教育背景", "職歴", "工作经历",
                "工作经验", "職務経歴", "工作内容：", "工作内容", "仕事内容", "業務内容",
            }
            data_start = start + 1 if pure_marker else start
            for row in rows[data_start:end]:
                fragment.append(row.extract())
            if fragment.find("tr"):
                replacement.append(fragment)
        for node in replacement:
            table.insert_before(node)
        table.decompose()


def promote_table_section_headings(container: Tag) -> None:
    """为独立表格的列标题补充 section 边界。

    EN: Add section boundaries for the column headings of standalone tables.

    JA: 独立した表の列見出しに section 境界を補う。
    """
    rules = (
        ("certificate_list", r"^(?:年月)?(?:資格|资格|证书|資格・免許)"),
        ("self_evaluation", r"^(?:自己PR|自己ＰＲ|自我评价|自我介绍)"),
        ("expected_list", r"^(?:希望給与|希望条件|求职意向|期望薪资)"),
        ("skills_list", r"^(?:IT技能|技能|スキル)"),
    )
    for table in list(container.find_all("table")):
        first_row = next(iter(_direct_table_rows(table)), None)
        if first_row is None:
            continue
        text = re.sub(r"\s+", "", first_row.get_text(" ", strip=True))
        section_type = next((kind for kind, pattern in rules if re.search(pattern, text, re.I)), "")
        if not section_type:
            continue
        previous = table.find_previous_sibling()
        if isinstance(previous, Tag) and previous.get("data-section-type") == section_type:
            continue
        heading = _make_tag("h2")
        heading["data-section-type"] = section_type
        heading.string = first_row.get_text(" ", strip=True).rstrip("：:")
        table.insert_before(heading)


def promote_nested_semantic_tables(container: Tag) -> None:
    """将以明确标题开头的内层小表格提升到 resume 直属层。

    EN: Promote inner small tables that start with an explicit heading to direct children of resume.

    JA: 明確な見出しで始まる内側の小さな表を、resume の直下に格上げする。
    """
    anchors: dict[int, Tag] = {}
    for heading in list(container.find_all(["h1", "h2", "h3", "h4", "h5", "h6"])):
        section_type = section_type_for(heading.get_text(" ", strip=True))
        table = heading.find_parent("table")
        if not section_type or table is None or table.parent is container:
            continue
        heading_text = re.sub(r"\s+", "", heading.get_text(" ", strip=True))
        table_text = re.sub(r"\s+", "", table.get_text(" ", strip=True))
        if not table_text.startswith(heading_text):
            continue
        top: Tag = table
        while isinstance(top.parent, Tag) and top.parent is not container:
            top = top.parent
        anchor = anchors.get(id(top), top)
        promoted_heading = _make_tag("h2")
        promoted_heading["data-section-type"] = section_type
        promoted_heading.string = heading.get_text(" ", strip=True).rstrip("：:")
        heading.decompose()
        table.extract()
        anchor.insert_after(promoted_heading)
        promoted_heading.insert_after(table)
        anchors[id(top)] = table


def add_semantic_sections(main: Tag) -> None:
    children = [node for node in list(main.contents) if not isinstance(node, NavigableString) or node.strip()]
    main.clear()
    current: Tag | None = None
    section_index = 0
    for node in children:
        is_heading = isinstance(node, Tag) and node.name in {"h1", "h2", "h3", "h4", "h5", "h6"}
        if current is None or is_heading:
            section_index += 1
            current = _make_tag("section")
            current["data-section-index"] = str(section_index)
            current["data-section-type"] = (
                str(node.get("data-section-type")) if is_heading and node.get("data-section-type") else "document-body"
            )
            main.append(current)
        current.append(node)
    for section in main.find_all("section", recursive=False):
        heading = section.find(["h1", "h2", "h3", "h4", "h5", "h6"], recursive=False)
        if heading:
            heading_id = f"section-{section['data-section-index']}-heading"
            heading["id"] = heading_id
            section["aria-labelledby"] = heading_id
        for block_index, block in enumerate(section.find_all(recursive=False), 1):
            if isinstance(block, Tag):
                block["data-block-index"] = str(block_index)
                block["data-block-type"] = block.name


def canonical_field_for(label: str, scope: str) -> str:
    key = _normalized_label(label)
    return SCOPED_FIELD_LOOKUP.get(scope, {}).get(key) or COMMON_FIELD_LOOKUP.get(key, "")


def _inline_label_matches(text: str, scope: str) -> list[tuple[int, int, str, str]]:
    """Find exact known labels followed by a colon; never infer labels from free text."""
    aliases: list[tuple[str, str, int]] = []
    for field, values in COMMON_FIELD_ALIASES.items():
        aliases.extend((alias, field, 0) for alias in values)
    for field, values in SCOPED_FIELD_ALIASES.get(scope, {}).items():
        aliases.extend((alias, field, 1) for alias in values)

    candidates: list[tuple[int, int, str, str, int, int]] = []
    for alias, field, priority in aliases:
        escaped = re.escape(alias).replace(r"\ ", r"\s+")
        ascii_boundary = r"(?<![A-Za-z0-9])" if re.fullmatch(r"[A-Za-z0-9 ._-]+", alias) else ""
        pattern = re.compile(ascii_boundary + escaped + r"\s*[:：]", re.IGNORECASE)
        for match in pattern.finditer(text):
            candidates.append((match.start(), match.end(), field, match.group(0), priority, len(alias)))

    # At the same offset prefer scoped labels and the longest exact alias.
    selected: list[tuple[int, int, str, str]] = []
    occupied_until = -1
    for start, end, field, label, _priority, _length in sorted(
        candidates, key=lambda item: (item[0], -item[4], -item[5], item[1])
    ):
        if start < occupied_until:
            continue
        selected.append((start, end, field, label))
        occupied_until = end
    return selected


def _annotate_inline_text(tag: Tag, scope: str) -> bool:
    raw = tag.get_text(" ", strip=True)
    matches = _inline_label_matches(raw, scope)
    if not matches:
        return False
    # A single label is still useful when its value is empty. Multiple labels are
    # split independently so "手机： 邮箱：" cannot turn 邮箱 into a phone value.
    tag.clear()
    if len(matches) == 1:
        tag["label"] = FIELD_DISPLAY_LABELS.get(matches[0][2], matches[0][3].rstrip("：:").strip())
    cursor = 0
    for index, (start, end, field, label) in enumerate(matches):
        if start > cursor:
            tag.append(raw[cursor:start])
        label_span = _make_tag("span")
        label_span["data-label-for"] = field
        label_span.string = label.strip()
        tag.append(label_span)
        value_end = matches[index + 1][0] if index + 1 < len(matches) else len(raw)
        value = raw[end:value_end].strip()
        if value:
            value_span = _make_tag("i")
            value_span["data-field"] = field
            value_span["label"] = FIELD_DISPLAY_LABELS.get(field, label.rstrip("：:").strip())
            value_span.string = value
            tag.append(value_span)
        cursor = value_end
    return True


def _profile_segment_field(segment: str, scope: str) -> tuple[str, str, str] | None:
    """Conservatively classify common pipe-delimited profile values."""
    value = segment.strip()
    explicit = _inline_label_matches(value, scope)
    if len(explicit) == 1 and explicit[0][0] == 0:
        _start, end, field, raw_label = explicit[0]
        field_value = value[end:].strip()
        if field_value:
            return field, FIELD_DISPLAY_LABELS.get(field, raw_label.rstrip("：:").strip()), field_value
    if re.fullmatch(r"(?:男|女|男性|女性|male|female)", value, re.IGNORECASE):
        return "gender", FIELD_DISPLAY_LABELS["gender"], value
    if re.fullmatch(r"(?:未婚|已婚|离异|离婚|单身|既婚|独身|single|married|divorced)", value, re.IGNORECASE):
        return "marital_status", FIELD_DISPLAY_LABELS["marital_status"], value
    if re.fullmatch(r"\d{1,3}\s*岁", value):
        return "age", FIELD_DISPLAY_LABELS["age"], value
    if re.search(r"(?:19|20)\d{2}\s*(?:年|[./-])\s*\d{1,2}(?:\s*(?:月|[./-])\s*\d{1,2}\s*日?)?", value):
        return "birth_date", FIELD_DISPLAY_LABELS["birth_date"], value.rstrip("生").strip()
    return None


def _annotate_composite_profile(paragraph: Tag, scope: str) -> bool:
    if scope not in {"document-body", "base_info"}:
        return False
    raw = paragraph.get_text(" ", strip=True)
    if len(raw) > 240 or not re.search(r"[|｜]", raw):
        return False
    parts = re.split(r"([|｜])", raw)
    classified: dict[int, tuple[str, str, str]] = {}
    for index in range(0, len(parts), 2):
        result = _profile_segment_field(parts[index], scope)
        if result:
            classified[index] = result
    if len(classified) < 2:
        return False

    paragraph.clear()
    paragraph["label"] = "个人信息"
    paragraph["data-field-group"] = "base_info"
    for index, part in enumerate(parts):
        if index not in classified:
            paragraph.append(part)
            continue
        field, display_label, value = classified[index]
        value_tag = _make_tag("i")
        value_tag["data-field"] = field
        value_tag["label"] = display_label
        value_tag.string = value
        paragraph.append(value_tag)
    return True


def annotate_schema_fields(main: Tag) -> None:
    """Annotate only explicit label/value pairs with complete-v1 canonical field names."""
    for section in main.find_all("section", recursive=False):
        scope = str(section.get("data-section-type") or "document-body")
        if scope in SCOPED_FIELD_LOOKUP:
            section["data-collection"] = scope

        for row in section.find_all("tr"):
            cells = row.find_all(["th", "td"], recursive=False)
            for cell in cells:
                # Nested paragraphs are annotated below, preserving table structure.
                if not cell.find(["p", "div", "ul", "ol", "table"]):
                    _annotate_inline_text(cell, scope)
            for index, cell in enumerate(cells[:-1]):
                label = cell.get_text(" ", strip=True).rstrip("：:")
                field = canonical_field_for(label, scope)
                next_text = cells[index + 1].get_text(" ", strip=True)
                next_is_label = bool(canonical_field_for(next_text.rstrip("：:"), scope))
                if field and next_text and not next_is_label and not cells[index + 1].get("data-label-for"):
                    cell["data-label-for"] = field
                    cells[index + 1]["data-field"] = field
                    cells[index + 1]["label"] = label

        for term in section.find_all("dt"):
            sibling = term.find_next_sibling("dd")
            if sibling is None:
                continue
            field = canonical_field_for(term.get_text(" ", strip=True).rstrip("：:"), scope)
            if field:
                term["data-label-for"] = field
                sibling["data-field"] = field
                sibling["label"] = term.get_text(" ", strip=True).rstrip("：:")

        for paragraph in section.find_all("p"):
            if not _annotate_composite_profile(paragraph, scope):
                _annotate_inline_text(paragraph, scope)


def _direct_table_rows(table: Tag) -> list[Tag]:
    rows: list[Tag] = []
    for child in table.find_all(recursive=False):
        if child.name == "tr":
            rows.append(child)
        elif child.name in {"thead", "tbody", "tfoot"}:
            rows.extend(child.find_all("tr", recursive=False))
    return rows


def _resume_structure_score(text: str) -> int:
    groups = (
        r"个人信息|基本信息|个人资料|personal information|基本情報",
        r"求职意向|职业期望|期望职位|job objective|希望職種",
        r"工作经历|工作经验|职业经历|work experience|職務経歴",
        r"教育经历|教育背景|教育经验|education|学歴",
    )
    return sum(bool(re.search(pattern, text, re.IGNORECASE)) for pattern in groups)


def _high_confidence_row_boundaries(rows: list[Tag]) -> list[tuple[int, str]]:
    """Return candidate starts only for repeated, complete platform-resume blocks."""
    starts: list[tuple[int, str]] = []
    for index, row in enumerate(rows):
        row_text = row.get_text(" ", strip=True)
        match = CANDIDATE_ID_RE.search(row_text[:120])
        if not match:
            continue
        window = " ".join(item.get_text(" ", strip=True) for item in rows[index : index + 18])
        start_markers = sum(
            token in window
            for token in ("下载简历", "剩余下载数", "最近工作", "最高学历", "求职意向")
        )
        has_profile_line = bool(re.search(r"\d{1,3}\s*岁|(?:男|女)\s*[|｜]", window))
        if start_markers >= 2 and has_profile_line:
            candidate_id = match.group(1)
            if not starts or starts[-1][1] != candidate_id:
                starts.append((index, candidate_id))

    if len(starts) < 2 or len({candidate_id for _, candidate_id in starts}) < 2:
        return []
    boundaries = [(0, starts[0][1]), *starts[1:]]
    for position, (start, _candidate_id) in enumerate(boundaries):
        end = boundaries[position + 1][0] if position + 1 < len(boundaries) else len(rows)
        chunk_text = " ".join(row.get_text(" ", strip=True) for row in rows[start:end])
        if len(re.sub(r"\s+", "", chunk_text)) < 500 or _resume_structure_score(chunk_text) < 2:
            return []
    return boundaries


def _high_confidence_node_boundaries(nodes: list[Tag | NavigableString]) -> list[tuple[int, str]]:
    starts: list[tuple[int, str]] = []
    for index, node in enumerate(nodes):
        node_text = node.get_text(" ", strip=True) if isinstance(node, Tag) else str(node).strip()
        match = CANDIDATE_ID_RE.search(node_text[:160])
        if not match:
            continue
        window_parts: list[str] = []
        for item in nodes[index : index + 16]:
            window_parts.append(item.get_text(" ", strip=True) if isinstance(item, Tag) else str(item).strip())
        window = " ".join(window_parts)
        start_markers = sum(
            token in window
            for token in ("下载简历", "剩余下载数", "最近工作", "最高学历", "求职意向")
        )
        has_profile_line = bool(re.search(r"\d{1,3}\s*岁|(?:男|女)\s*[|｜]", window))
        if start_markers >= 2 and has_profile_line:
            candidate_id = match.group(1)
            if not starts or starts[-1][1] != candidate_id:
                starts.append((index, candidate_id))
    if len(starts) < 2 or len({candidate_id for _, candidate_id in starts}) < 2:
        return []
    boundaries = [(0, starts[0][1]), *starts[1:]]
    for position, (start, _candidate_id) in enumerate(boundaries):
        end = boundaries[position + 1][0] if position + 1 < len(boundaries) else len(nodes)
        chunk_text = " ".join(
            node.get_text(" ", strip=True) if isinstance(node, Tag) else str(node).strip()
            for node in nodes[start:end]
        )
        if len(re.sub(r"\s+", "", chunk_text)) < 500 or _resume_structure_score(chunk_text) < 2:
            return []
    return boundaries


def wrap_resume_records(main: Tag) -> list[dict[str, str]]:
    """Wrap one or more people in independent semantic resume articles."""
    direct_nodes = [node for node in list(main.contents) if not isinstance(node, NavigableString) or node.strip()]
    node_boundaries = _high_confidence_node_boundaries(direct_nodes)
    if node_boundaries:
        metadata: list[dict[str, str]] = []
        main.clear()
        for sequence, (start, candidate_id) in enumerate(node_boundaries, 1):
            end = node_boundaries[sequence][0] if sequence < len(node_boundaries) else len(direct_nodes)
            record = _make_tag("article")
            record["class"] = "resume-record"
            record["data-role"] = "resume"
            record["data-resume-index"] = str(sequence)
            record["data-candidate-key"] = f"platform-id:{candidate_id}"
            for node in direct_nodes[start:end]:
                record.append(node.extract())
            main.append(record)
            metadata.append({"index": str(sequence), "candidate_key": f"platform-id:{candidate_id}"})
        main["data-resume-count"] = str(len(metadata))
        for record in main.find_all("article", attrs={"data-role": "resume"}, recursive=False):
            promote_known_headings(record)
            normalize_tables(record)
            split_embedded_table_sections(record)
            promote_table_section_headings(record)
            promote_nested_semantic_tables(record)
            add_semantic_sections(record)
            annotate_schema_fields(record)
        return metadata

    split_table: Tag | None = None
    boundaries: list[tuple[int, str]] = []
    rows: list[Tag] = []
    for node in direct_nodes:
        if not isinstance(node, Tag) or node.name != "table":
            continue
        candidate_rows = _direct_table_rows(node)
        candidate_boundaries = _high_confidence_row_boundaries(candidate_rows)
        if candidate_boundaries:
            split_table, boundaries, rows = node, candidate_boundaries, candidate_rows
            break

    records: list[Tag] = []
    metadata: list[dict[str, str]] = []
    if split_table is not None:
        before: list[Tag | NavigableString] = []
        after: list[Tag | NavigableString] = []
        seen_table = False
        for node in direct_nodes:
            if node is split_table:
                seen_table = True
            elif not seen_table:
                before.append(node)
            else:
                after.append(node)
        main.clear()
        for sequence, (start, candidate_id) in enumerate(boundaries, 1):
            end = boundaries[sequence][0] if sequence < len(boundaries) else len(rows)
            record = _make_tag("article")
            record["class"] = "resume-record"
            record["data-role"] = "resume"
            record["data-resume-index"] = str(sequence)
            record["data-candidate-key"] = f"platform-id:{candidate_id}"
            if sequence == 1:
                for node in before:
                    record.append(node.extract())
            new_table = _make_tag("table")
            new_table.attrs = dict(split_table.attrs)
            for row in rows[start:end]:
                new_table.append(row.extract())
            record.append(new_table)
            if sequence == len(boundaries):
                for node in after:
                    record.append(node.extract())
            main.append(record)
            records.append(record)
            metadata.append({"index": str(sequence), "candidate_key": f"platform-id:{candidate_id}"})
        split_table.decompose()
    else:
        record = _make_tag("article")
        record["class"] = "resume-record"
        record["data-role"] = "resume"
        record["data-resume-index"] = "1"
        main.clear()
        for node in direct_nodes:
            record.append(node.extract())
        main.append(record)
        records.append(record)
        metadata.append({"index": "1", "candidate_key": ""})

    main["data-resume-count"] = str(len(records))
    for record in records:
        promote_known_headings(record)
        normalize_tables(record)
        split_embedded_table_sections(record)
        promote_table_section_headings(record)
        promote_nested_semantic_tables(record)
        add_semantic_sections(record)
        annotate_schema_fields(record)
    return metadata


def build_semantic_html(
    cleaned_fragment: str,
    src_p: Path,
    download_date: str,
    phone: str,
    email_address: str,
    converter: str,
) -> str:
    plain_text = strip_tags(cleaned_fragment)
    language = detect_language(plain_text)
    out = BeautifulSoup("<!DOCTYPE html><html><head></head><body></body></html>", "html.parser")
    html_tag = out.html
    head = out.head
    body = out.body
    assert html_tag is not None and head is not None and body is not None
    html_tag["lang"] = language

    meta_charset = out.new_tag("meta")
    meta_charset["charset"] = "UTF-8"
    head.append(meta_charset)
    viewport = out.new_tag("meta")
    viewport["name"] = "viewport"
    viewport["content"] = "width=device-width, initial-scale=1.0"
    head.append(viewport)
    title = out.new_tag("title")
    title.string = safe_stem(src_p.stem)
    head.append(title)

    article = out.new_tag("article")
    article["class"] = "word-document"
    article["data-schema-version"] = SCHEMA_VERSION
    article["data-target-schema"] = TARGET_DATA_SCHEMA
    article["data-generator-version"] = GENERATOR_VERSION
    article["data-converter"] = converter
    article["data-source-hash"] = source_path_hash(str(src_p))
    body.append(article)

    source_header = out.new_tag("header")
    source_header["class"] = "resume-source-header"
    source_header["data-role"] = "source-metadata"
    article.append(source_header)

    document_title = out.new_tag("h1")
    document_title["class"] = "document-title"
    document_title["data-field"] = "document-title"
    document_title.string = safe_stem(src_p.stem)
    source_header.append(document_title)

    def add_meta(label: str, value: str, field: str) -> None:
        p = out.new_tag("p")
        p["data-field"] = field
        label_tag = out.new_tag("b")
        label_tag.string = f"{label}："
        p.append(label_tag)
        p.append(NavigableString(value))
        source_header.append(p)

    add_meta("源文件路径", str(src_p), "source-path")
    add_meta("简历落地时间", download_date, "download-date")
    if phone:
        add_meta("联系电话", phone, "phone")
    if email_address:
        add_meta("电子邮箱", email_address, "email")

    main = out.new_tag("main")
    main["class"] = "document-content"
    main["data-role"] = "document-content"
    article.append(main)
    fragment = BeautifulSoup(cleaned_fragment, "html.parser")
    for node in list(fragment.contents):
        main.append(node.extract())
    wrap_resume_records(main)
    return str(out)


def validate_semantic_html(html_text: str) -> dict[str, Any]:
    soup = BeautifulSoup(html_text, "html.parser")
    errors: list[str] = []
    warnings: list[str] = []
    article = soup.find("article", attrs={"data-schema-version": SCHEMA_VERSION})
    main = soup.find("main", attrs={"data-role": "document-content"})
    if soup.html is None or soup.body is None:
        errors.append("缺少 html/body")
    if article is None:
        errors.append("缺少版本化 article")
    if main is None:
        errors.append("缺少 main 正文")
    elif not main.get_text(" ", strip=True):
        errors.append("正文为空")
    resume_records = main.find_all("article", attrs={"data-role": "resume"}, recursive=False) if main else []
    if main is not None and not resume_records:
        errors.append("缺少独立 resume article")
    for expected_index, resume_record in enumerate(resume_records, 1):
        if str(resume_record.get("data-resume-index") or "") != str(expected_index):
            errors.append("resume article 索引不连续")
            break
        if not resume_record.get_text(" ", strip=True):
            errors.append(f"第 {expected_index} 个 resume article 为空")
    if not soup.find(attrs={"data-field": "source-path"}):
        errors.append("缺少 source-path 元数据")
    if not soup.find("section"):
        errors.append("缺少正文 section")
    if soup.find(["script", "style", "iframe", "object", "embed"]):
        errors.append("包含危险或非内容节点")
    for tag in soup.find_all(True):
        if any(str(key).casefold().startswith("on") for key in tag.attrs):
            errors.append("包含事件处理属性")
            break
    for table in soup.find_all("table"):
        if not table.find("tr"):
            warnings.append("存在无行表格")
    if soup.find("img"):
        errors.append("图片节点未移除")
    return {
        "valid": not errors,
        "errors": errors,
        "warnings": sorted(set(warnings)),
        "resume_count": len(resume_records),
        "candidate_keys": [str(record.get("data-candidate-key") or "") for record in resume_records],
        "text_length": len(main.get_text(" ", strip=True)) if main else 0,
        "heading_count": len(main.find_all(["h1", "h2", "h3", "h4", "h5", "h6"])) if main else 0,
        "section_count": len(main.find_all("section")) if main else 0,
        "table_count": len(main.find_all("table")) if main else 0,
        "list_count": len(main.find_all(["ul", "ol"])) if main else 0,
        "annotated_field_count": len(main.find_all(attrs={"data-field": True})) if main else 0,
    }


def atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    finally:
        if temp_path.exists():
            temp_path.unlink(missing_ok=True)


def run_word_com_with_timeout(src_p: Path, dst_p: Path, timeout_sec: int = 30) -> bool:
    pid_file = dst_p.with_suffix(dst_p.suffix + ".winword.pid")
    code = r'''
import sys
from pathlib import Path
import win32com.client
import win32process

src = Path(sys.argv[1]).resolve()
dst = Path(sys.argv[2]).resolve()
pid_file = Path(sys.argv[3]).resolve()
word_app = None
doc = None
try:
    word_app = win32com.client.DispatchEx("Word.Application")
    word_app.Visible = False
    word_app.DisplayAlerts = 0
    word_app.AutomationSecurity = 3
    pid = win32process.GetWindowThreadProcessId(word_app.Hwnd)[1]
    pid_file.write_text(str(pid), encoding="ascii")
    word_app.Options.UpdateLinksAtOpen = False
    word_app.Options.UpdateFieldsAtOpen = False
    doc = word_app.Documents.Open(
        FileName=str(src), ConfirmConversions=False, ReadOnly=True,
        AddToRecentFiles=False, OpenAndRepair=True, NoEncodingDialog=True
    )
    doc.SaveAs2(str(dst), FileFormat=10)
    sys.exit(0 if dst.exists() and dst.stat().st_size > 50 else 1)
except Exception as exc:
    print(str(exc), file=sys.stderr)
    sys.exit(1)
finally:
    if doc is not None:
        try: doc.Close(False)
        except Exception: pass
    if word_app is not None:
        try: word_app.Quit()
        except Exception: pass
'''
    try:
        completed = subprocess.run(
            [sys.executable, "-c", code, str(src_p), str(dst_p), str(pid_file)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=timeout_sec,
        )
        return completed.returncode == 0 and dst_p.exists() and dst_p.stat().st_size > 50
    except subprocess.TimeoutExpired:
        if pid_file.exists():
            try:
                pid = int(pid_file.read_text(encoding="ascii").strip())
                subprocess.run(["taskkill", "/F", "/PID", str(pid)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
            except Exception:
                pass
        return False
    except Exception:
        return False
    finally:
        pid_file.unlink(missing_ok=True)


def extract_text_from_binary_doc(doc_path: Path) -> str:
    """Last-resort extraction that keeps all languages and escapes every line."""
    try:
        from resume_importer.extractors import ResumeTextExtractor

        text = ResumeTextExtractor()._extract_doc_without_word(doc_path)
        if text and len(re.sub(r"\s+", "", text)) >= 2:
            paragraphs = [f"<p>{html.escape(line.strip())}</p>" for line in re.split(r"[\r\n]+", text) if line.strip()]
            return "\n".join(paragraphs)
    except Exception:
        pass
    try:
        import olefile

        if olefile.isOleFile(str(doc_path)):
            with olefile.OleFileIO(str(doc_path)) as ole:
                if ole.exists("WordDocument"):
                    data = ole.openstream("WordDocument").read()
                    candidates = [data.decode("utf-16-le", errors="ignore"), data.decode("gb18030", errors="ignore")]
                    text = max(candidates, key=lambda value: len(re.sub(r"[^\w\u3040-\u30ff\u4e00-\u9fff]", "", value)))
                    lines = [line.strip() for line in re.split(r"[\r\n\x00]+", text) if len(line.strip()) >= 2]
                    return "\n".join(f"<p>{html.escape(line)}</p>" for line in lines[:10000])
    except Exception:
        pass
    return ""


def convert_antiword_to_html(doc_path: Path) -> str:
    """Convert legacy .doc to a structural fragment without images or layout CSS."""
    import shutil

    antiword = shutil.which("antiword") or r"C:\Program Files\Git\mingw64\bin\antiword.exe"
    if not Path(antiword).is_file():
        return ""
    try:
        completed = subprocess.run(
            [antiword, "-m", "UTF-8.txt", str(doc_path)],
            capture_output=True,
            timeout=60,
        )
        text = completed.stdout.decode("utf-8", errors="replace")
    except Exception:
        return ""
    if len(re.sub(r"\s+", "", text)) < 2:
        return ""

    pieces: list[str] = []
    table_rows: list[list[str]] = []

    def flush_table() -> None:
        nonlocal table_rows
        if not table_rows:
            return
        merged_rows: list[list[str]] = []
        index = 0
        while index < len(table_rows):
            row = table_rows[index]
            if (
                index + 1 < len(table_rows)
                and len(row) >= 2
                and row[0].casefold() in {"preferred", "job"}
                and len(table_rows[index + 1]) >= 2
                and table_rows[index + 1][0].rstrip().endswith((":", "："))
            ):
                following = table_rows[index + 1]
                merged_rows.append([
                    f"{row[0]} {following[0]}",
                    " ".join(value for value in [*row[1:], *following[1:]] if value).strip(),
                ])
                index += 2
                continue
            if row and not row[0] and merged_rows and len(merged_rows[-1]) >= 2:
                continuation = " ".join(value for value in row[1:] if value).strip()
                if continuation:
                    merged_rows[-1][-1] = f"{merged_rows[-1][-1]} {continuation}".strip()
            else:
                merged_rows.append(row)
            index += 1
        rows = []
        for cells in merged_rows:
            rows.append("<tr>" + "".join(f"<td>{html.escape(cell)}</td>" for cell in cells) + "</tr>")
        pieces.append("<table><tbody>" + "".join(rows) + "</tbody></table>")
        table_rows = []

    for raw_line in text.replace("\r\n", "\n").replace("\r", "\n").splitlines():
        line = raw_line.strip()
        if not line or re.fullmatch(r"[-_=]{5,}", line):
            flush_table()
            continue
        if line.casefold() in {"[pic]", "[picture]", "[image]"}:
            continue
        if line.startswith("|") and line.endswith("|"):
            cells = [re.sub(r"\s+", " ", cell).strip() for cell in line[1:-1].split("|")]
            if any(cells):
                table_rows.append(cells)
            continue
        flush_table()
        value = re.sub(r"[ \t]{2,}", " ", line)
        pieces.append(f"<p>{html.escape(value)}</p>")
    flush_table()
    return "\n".join(pieces)


def convert_docx_ooxml_to_html(src_p: Path) -> str:
    """无第三方依赖地按文档顺序提取 DOCX 段落和表格；图片有意忽略。

    EN: Extract DOCX paragraphs and tables in document order with no third-party dependencies; images are intentionally ignored.

    JA: サードパーティ依存なしで DOCX の段落と表を文書順に抽出する。画像は意図的に無視する。
    """
    word_ns = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    w = f"{{{word_ns}}}"

    with zipfile.ZipFile(src_p) as archive:
        root = ET.fromstring(archive.read("word/document.xml"))
    body = root.find(f"{w}body")
    if body is None:
        return ""

    def paragraph_text(node: ET.Element) -> str:
        values: list[str] = []
        for descendant in node.iter():
            if descendant.tag in {f"{w}t", f"{w}instrText", f"{w}delText"} and descendant.text:
                values.append(descendant.text)
            elif descendant.tag == f"{w}tab":
                values.append("\t")
            elif descendant.tag in {f"{w}br", f"{w}cr"}:
                values.append("\n")
        return "".join(values).strip()

    def render_table(table: ET.Element) -> str:
        rendered_rows: list[str] = []
        for row in table.findall(f"{w}tr"):
            rendered_cells: list[str] = []
            for cell in row.findall(f"{w}tc"):
                cell_parts: list[str] = []
                for child in list(cell):
                    if child.tag == f"{w}p":
                        value = paragraph_text(child)
                        if value:
                            cell_parts.append(html.escape(value).replace("\n", "<br>"))
                    elif child.tag == f"{w}tbl":
                        nested = render_table(child)
                        if nested:
                            cell_parts.append(nested)
                rendered_cells.append("<td>" + "<br>".join(cell_parts) + "</td>")
            if rendered_cells:
                rendered_rows.append("<tr>" + "".join(rendered_cells) + "</tr>")
        return "<table><tbody>" + "".join(rendered_rows) + "</tbody></table>" if rendered_rows else ""

    pieces: list[str] = []
    for child in list(body):
        if child.tag == f"{w}p":
            value = paragraph_text(child)
            if value:
                pieces.append("<p>" + html.escape(value).replace("\n", "<br>") + "</p>")
        elif child.tag == f"{w}tbl":
            rendered = render_table(child)
            if rendered:
                pieces.append(rendered)
    return "\n".join(pieces)


def _convert_source(src_p: Path, temp_dir: Path, timeout_sec: int) -> tuple[str, str]:
    override = CONVERSION_OVERRIDES.get(_path_key(src_p), {})
    ocr_html = str(override.get("ocr_html") or "").strip()
    if ocr_html:
        return ocr_html, "ocr-curated"

    raw_bytes = src_p.read_bytes()
    if looks_like_mhtml(raw_bytes):
        return decode_mhtml(raw_bytes), "mhtml"

    if raw_bytes.startswith(b"PK\x03\x04") or src_p.suffix.casefold() in {".docx", ".docm", ".dotx"}:
        try:
            import mammoth

            def ignore_image(_image: Any) -> dict[str, str]:
                return {}

            with src_p.open("rb") as docx_file:
                result = mammoth.convert_to_html(
                    docx_file,
                    convert_image=mammoth.images.inline(ignore_image),
                )
            if result.value.strip():
                return result.value, "mammoth"
        except Exception:
            pass

        # Mammoth 不可用时，直接读取 DOCX 的 OOXML。只保留文字和表格语义，
        # 不导出图片，避免把可解析的 DOCX 错判为“无正文”。
        # EN: When Mammoth is unavailable, read the DOCX OOXML directly. Keep only text and table semantics,
        #     and do not export images, so a parseable DOCX is not misjudged as "no body text".
        # JA: Mammoth が使えない場合は DOCX の OOXML を直接読む。テキストと表の意味だけを残し、
        #     画像は出力しない。解析可能な DOCX を「本文なし」と誤判定しないため。
        try:
            converted = convert_docx_ooxml_to_html(src_p)
            if converted.strip():
                return converted, "docx-ooxml"
        except Exception:
            pass

    head = raw_bytes[:8192].lower()
    utf16_head = ""
    if head.startswith((b"\xff\xfe", b"\xfe\xff")):
        try:
            utf16_head = raw_bytes[:16384].decode("utf-16", errors="ignore").casefold()
        except Exception:
            utf16_head = ""
    if b"<html" in head or b"<body" in head or b"<table" in head or any(tag in utf16_head for tag in ("<html", "<body", "<table")):
        decoded = read_file_text_safe(src_p)
        if decoded.strip():
            return decoded, "embedded-html-utf16" if utf16_head else "embedded-html"

    temp_dir.mkdir(parents=True, exist_ok=True)
    temp_dst = temp_dir / f"temp_{source_path_hash(str(src_p))}.html"
    if run_word_com_with_timeout(src_p, temp_dst, timeout_sec=timeout_sec):
        converted = read_file_text_safe(temp_dst)
        temp_dst.unlink(missing_ok=True)
        import shutil

        shutil.rmtree(temp_dir / f"{temp_dst.stem}.files", ignore_errors=True)
        if converted.strip():
            return converted, "word-com"

    antiword_html = convert_antiword_to_html(src_p)
    if antiword_html.strip():
        return antiword_html, "antiword"

    fallback = extract_text_from_binary_doc(src_p)
    if fallback.strip():
        return fallback, "binary-text-fallback"
    raise RuntimeError("转换 HTML 失败（没有提取到可读正文）")


def convert_single_word_detailed(
    src_path_str: str,
    passed_dir: Path,
    review_dir: Path,
    filename: str,
    download_date: str,
    timeout_sec: int = 30,
) -> dict[str, Any]:
    src_p = Path(src_path_str).resolve()
    if not src_p.exists():
        return {"ok": False, "status": "failed", "phone": "", "email": "", "html_path": "", "error_reason": "源文件不存在"}
    try:
        raw_html, converter = _convert_source(src_p, passed_dir.parent / "temp", timeout_sec)
        cleaned_html = clean_html_styles(raw_html)
        plain_text = strip_tags(cleaned_html)
        if len(re.sub(r"\s+", "", plain_text)) < 2:
            raise RuntimeError("清洗后正文为空")
        phone, email_address = extract_contacts(plain_text)
        final_html = build_semantic_html(cleaned_html, src_p, download_date, phone, email_address, converter)
        validation = validate_semantic_html(final_html)
        if not validation["valid"]:
            raise RuntimeError("语义 HTML 验证失败：" + "; ".join(validation["errors"]))

        status = "passed" if phone or email_address else "needs_review"
        target_dir = passed_dir if status == "passed" else review_dir
        other_dir = review_dir if status == "passed" else passed_dir
        target_name = f"{safe_stem(Path(filename).stem)}_{source_path_hash(src_path_str)}.html"
        dst_p = target_dir / target_name
        atomic_write_text(dst_p, final_html)
        stale_path = other_dir / target_name
        if stale_path.exists():
            stale_path.unlink()
        return {
            "ok": True,
            "status": status,
            "phone": phone,
            "email": email_address,
            "html_path": str(dst_p),
            "error_reason": "",
            "converter": converter,
            "generator_version": GENERATOR_VERSION,
            "schema_version": SCHEMA_VERSION,
            "resume_count": validation.get("resume_count", 1),
            "candidate_keys": validation.get("candidate_keys", []),
            "validation": validation,
        }
    except Exception as exc:
        return {
            "ok": False,
            "status": "failed",
            "phone": "",
            "email": "",
            "html_path": "",
            "error_reason": str(exc),
            "generator_version": GENERATOR_VERSION,
            "schema_version": SCHEMA_VERSION,
        }


def convert_single_word(
    src_path_str: str,
    passed_dir: Path,
    review_dir: Path,
    filename: str,
    download_date: str,
) -> tuple[bool, str, str, str, str]:
    """Backward-compatible wrapper used by existing maintenance scripts."""
    result = convert_single_word_detailed(src_path_str, passed_dir, review_dir, filename, download_date)
    fifth = result["html_path"] if result["ok"] else result["error_reason"]
    return bool(result["ok"]), str(result["status"]), str(result["phone"]), str(result["email"]), str(fifth)


def is_current_html(path: Path) -> bool:
    if not path.exists() or path.stat().st_size <= 100:
        return False
    try:
        head = path.read_text(encoding="utf-8", errors="replace")[:4096]
        return f'data-generator-version="{GENERATOR_VERSION}"' in head and f'data-schema-version="{SCHEMA_VERSION}"' in head
    except OSError:
        return False


def existing_record(path: Path, base: dict[str, Any], status: str) -> dict[str, Any]:
    content = path.read_text(encoding="utf-8", errors="replace")
    soup = BeautifulSoup(content, "html.parser")
    main = soup.find("main", attrs={"data-role": "document-content"})
    plain_text = re.sub(r"\s+", " ", main.get_text(" ", strip=True)).strip() if main else strip_tags(content)
    phone, email_address = extract_contacts(plain_text)
    validation = validate_semantic_html(content)
    article = soup.find("article", attrs={"data-schema-version": SCHEMA_VERSION})
    converter = str(article.get("data-converter") or "") if article else ""
    return {
        **base,
        "html_path": str(path),
        "phone": phone,
        "email": email_address,
        "status": status,
        "error_reason": "",
        "converter": converter,
        "generator_version": GENERATOR_VERSION,
        "schema_version": SCHEMA_VERSION,
        "resume_count": validation.get("resume_count", 1),
        "candidate_keys": validation.get("candidate_keys", []),
        "validation": validation,
    }


def process_all_word_files(
    excel_path: str,
    base_html_dir: str,
    limit: int = 0,
    force: bool = False,
    timeout_sec: int = 30,
    input_map: str = "",
    language_folder: str = "",
) -> dict[str, Any]:
    if input_map:
        source_records = json.loads(Path(input_map).read_text(encoding="utf-8"))
        rows = [
            {
                "index": record.get("index", index),
                "filename": str(record.get("filename") or Path(str(record.get("source_path") or "")).name),
                "download_date": str(record.get("download_date") or ""),
                "source_path": str(record.get("source_path") or ""),
                "language_folder": str(record.get("language_folder") or ""),
            }
            for index, record in enumerate(source_records, 1)
            if not language_folder or str(record.get("language_folder") or "") == language_folder
        ]
    else:
        workbook = openpyxl.load_workbook(excel_path, read_only=True, data_only=True)
        try:
            sheet = workbook["Word文档 (.doc, .docx)"]
            excel_rows = list(sheet.iter_rows(values_only=True))[1:]
        finally:
            workbook.close()
        rows = [
            {
                "index": index,
                "filename": str(row[2] or ""),
                "download_date": str(row[6] or ""),
                "source_path": str(row[7] or ""),
            }
            for index, row in enumerate(excel_rows, 1)
        ]
    if limit > 0:
        rows = rows[:limit]

    total_files = len(rows)
    print(f"开始处理 Word 文档，共 {total_files} 个；force={force}；生成器={GENERATOR_VERSION}" f" / Start processing Word documents, {total_files} in total; force={force}; generator={GENERATOR_VERSION} / Word 文書の処理を開始します。全 {total_files} 件、force={force}、生成器={GENERATOR_VERSION}", flush=True)
    output_root = Path(base_html_dir)
    passed_dir = output_root / "passed"
    review_dir = output_root / "review"
    passed_dir.mkdir(parents=True, exist_ok=True)
    review_dir.mkdir(parents=True, exist_ok=True)

    records: list[dict[str, Any]] = []
    counts = {"passed": 0, "needs_review": 0, "failed": 0, "superseded": 0, "skipped_current": 0}
    converter_counts: dict[str, int] = {}
    started = time.monotonic()

    for sequence, row in enumerate(rows, 1):
        idx = int(row.get("index") or sequence)
        filename = str(row.get("filename") or "")
        download_date = str(row.get("download_date") or "")
        abs_path = str(row.get("source_path") or "")
        target_name = f"{safe_stem(Path(filename).stem)}_{source_path_hash(abs_path)}.html"
        passed_file = passed_dir / target_name
        review_file = review_dir / target_name
        base_record = {
            "index": idx,
            "filename": filename,
            "source_path": abs_path,
            "download_date": download_date,
        }
        override = CONVERSION_OVERRIDES.get(_path_key(abs_path), {})

        if override.get("status") == "superseded":
            passed_file.unlink(missing_ok=True)
            review_file.unlink(missing_ok=True)
            record = {
                **base_record,
                "html_path": "",
                "phone": "",
                "email": "",
                "status": "superseded",
                "error_reason": str(override.get("reason") or "同一候选人的旧版本"),
                "superseded_by": str(override.get("superseded_by") or ""),
                "converter": "duplicate-superseded",
                "generator_version": GENERATOR_VERSION,
                "schema_version": SCHEMA_VERSION,
                "resume_count": 0,
                "candidate_keys": [],
                "validation": {},
            }
        elif not force and is_current_html(passed_file):
            record = existing_record(passed_file, base_record, "passed")
            counts["skipped_current"] += 1
        elif not force and is_current_html(review_file):
            record = existing_record(review_file, base_record, "needs_review")
            counts["skipped_current"] += 1
        else:
            result = convert_single_word_detailed(abs_path, passed_dir, review_dir, filename, download_date, timeout_sec=timeout_sec)
            record = {
                **base_record,
                "html_path": result.get("html_path", ""),
                "phone": result.get("phone", ""),
                "email": result.get("email", ""),
                "status": result["status"],
                "error_reason": result.get("error_reason", ""),
                "converter": result.get("converter", ""),
                "generator_version": GENERATOR_VERSION,
                "schema_version": SCHEMA_VERSION,
                "resume_count": result.get("resume_count", result.get("validation", {}).get("resume_count", 0)),
                "candidate_keys": result.get("candidate_keys", result.get("validation", {}).get("candidate_keys", [])),
                "validation": result.get("validation", {}),
            }
        counts[record["status"]] += 1
        converter = record.get("converter", "")
        if converter:
            converter_counts[converter] = converter_counts.get(converter, 0) + 1
        records.append(record)

        if sequence % 50 == 0 or sequence == total_files:
            elapsed = time.monotonic() - started
            speed = sequence / elapsed if elapsed else 0
            print(
                f"进度 [{sequence}/{total_files}] | passed={counts['passed']} | review={counts['needs_review']} | "
                f"failed={counts['failed']} | superseded={counts['superseded']} | "
                f"current-skip={counts['skipped_current']} | {speed:.1f} 文件/秒" f" / Progress [{sequence}/{total_files}] | passed={counts['passed']} | review={counts['needs_review']} | failed={counts['failed']} | superseded={counts['superseded']} | current-skip={counts['skipped_current']} | {speed:.1f} files/s / 進捗 [{sequence}/{total_files}] | passed={counts['passed']} | review={counts['needs_review']} | failed={counts['failed']} | superseded={counts['superseded']} | current-skip={counts['skipped_current']} | {speed:.1f} ファイル/秒",
                flush=True,
            )

    map_json_path = output_root / "word_conversion_map.json"
    atomic_write_text(map_json_path, json.dumps(records, ensure_ascii=False, indent=2))
    summary_data = {
        "category": "Word文档 (.doc, .docx)",
        "generator_version": GENERATOR_VERSION,
        "schema_version": SCHEMA_VERSION,
        "total_scanned_files": total_files,
        "passed_with_contact": counts["passed"],
        "needs_review_without_contact": counts["needs_review"],
        "failed_files": counts["failed"],
        "superseded_files": counts["superseded"],
        "skipped_current_files": counts["skipped_current"],
        "converter_counts": converter_counts,
        "multi_resume_source_files": sum(1 for record in records if int(record.get("resume_count") or 0) > 1),
        "total_resume_articles": sum(int(record.get("resume_count") or 0) for record in records),
        "passed_html_dir": str(passed_dir),
        "review_html_dir": str(review_dir),
        "map_json_file": str(map_json_path),
        "completed_at": datetime.now().astimezone().isoformat(),
    }
    atomic_write_text(output_root / "word_conversion_summary.json", json.dumps(summary_data, ensure_ascii=False, indent=2))
    print(json.dumps(summary_data, ensure_ascii=False, indent=2), flush=True)
    return summary_data


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Word 文档全量转换为版本化、可验证的语义 HTML" " / Convert all Word documents into versioned, verifiable semantic HTML / Word 文書をすべて、バージョン管理された検証可能な意味付き HTML に変換する")
    parser.add_argument("--excel", default=str(_rc.project_root() / "32718文件报告.xlsx"), help="全量 Excel 盘点报告路径" " / Path of the full Excel inventory report / Excel 棚卸しレポート（全件）のパス")
    parser.add_argument("--output-dir", default=str(_rc.project_root() / _rc.dirname("complete-transfered-htmls") / "docs"), help="HTML 输出根路径" " / HTML output root path / HTML 出力ルートのパス")
    parser.add_argument("--limit", type=int, default=0, help="测试跑批限制数量（0 为全量）" " / Limit for a test run (0 = all) / 試行実行の件数上限（0 は全件）")
    parser.add_argument("--force", action="store_true", help="忽略旧产物版本并重新转换全部记录" " / Ignore old product versions and re-convert all records / 古い成果物のバージョンを無視して全レコードを再変換する")
    parser.add_argument("--legacy-timeout", type=int, default=30, help="单个旧版 Word COM 转换超时秒数" " / Timeout in seconds for a single legacy Word COM conversion / 旧形式 Word の COM 変換 1 件あたりのタイムアウト秒数")
    parser.add_argument("--input-map", default="", help="严格按已有 word_conversion_map.json 清单重新转换" " / Re-convert strictly according to the existing word_conversion_map.json list / 既存の word_conversion_map.json の一覧に厳密に従って再変換する")
    parser.add_argument("--language-folder", default="", help="使用 input-map 时只转换指定语言文件夹（如 中文）" " / With input-map, convert only the given language folder (e.g. 中文) / input-map 使用時に、指定した言語フォルダ（例：中文）だけを変換する")
    args = parser.parse_args()
    process_all_word_files(
        args.excel,
        args.output_dir,
        args.limit,
        force=args.force,
        timeout_sec=args.legacy_timeout,
        input_map=args.input_map,
        language_folder=args.language_folder,
    )
