from __future__ import annotations
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1] / "common"))
import rc_config as _rc  # noqa: E402  项目统一配置（python/common/rc_config.py）
# EN: noqa: E402  project-wide configuration (python/common/rc_config.py)
# JA: noqa: E402  プロジェクト共通設定（python/common/rc_config.py）

import argparse
import datetime
import hashlib
import html
import json
import os
import re
import sys
import tempfile
import time
from datetime import datetime as dt_cls
from pathlib import Path
from typing import Any

import openpyxl
import xlrd
from bs4 import BeautifulSoup

sys.stdout.reconfigure(encoding="utf-8")

PROJECT_ROOT = _rc.project_root()
PYTHON_ROOT = _rc.PYTHON_DIR / "v2"
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

import process_word_to_html as word_html
from classify_passed_html_by_language import detect_languages, folder_for

# Excel 只维护工作簿网格读取；语义 HTML 的生成、解析、校验和版本判断
# 全部复用最新版 Word -> HTML 实现，避免两条流水线继续漂移。
# EN: Excel only maintains workbook grid reading; generation, parsing, validation and version checks of the semantic HTML
#     all reuse the latest Word -> HTML implementation, so the two pipelines stop drifting apart.
# JA: Excel 側はワークブックのグリッド読み取りだけを保守し、セマンティック HTML の生成・解析・検証・バージョン判定は
#     すべて最新の Word -> HTML 実装を再利用して、2 つのパイプラインがこれ以上ずれていかないようにする。
GENERATOR_VERSION = word_html.GENERATOR_VERSION
SCHEMA_VERSION = word_html.SCHEMA_VERSION
TARGET_DATA_SCHEMA = word_html.TARGET_DATA_SCHEMA
# Language classification follows the docs pipeline.  Bump this whenever the
# output layout/metadata changes so an old flat artifact is never reused.
XLS_RULE_VERSION = "xls-word-dom-3-language"

OUTPUT_ROOT = PROJECT_ROOT / _rc.dirname("complete-transfered-htmls") / "xls"
PASSED_DIR = OUTPUT_ROOT / "passed"
REVIEW_DIR = OUTPUT_ROOT / "review"
MAP_JSON_PATH = OUTPUT_ROOT / "xls_conversion_map.json"

# 正则表达式
# EN: Regular expressions
# JA: 正規表現
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
    r"(?:电话|電話|手機|手机|TEL|Tel|携帯|連絡先|联系方式)[：:\s]*([+\d\-\s().]{7,20})",
    re.IGNORECASE,
)

EXCEL_ERRORS = frozenset({
    "#ref!", "#value!", "#n/a", "#div/0!", "#name?",
    "#num!", "#null!", "#error!", "#getting_data",
})
BLANK_RE = re.compile(r"^[\s\x00-\x1f\xa0\u3000]*$")

# ──────────────────────────────────────────────────────────────────────────────
# 日本年号（和暦）转公历常量与函数
# ──────────────────────────────────────────────────────────────────────────────
# EN: ──────────────────────────────────────────────────────────────────────────────
#     Constants and functions for converting Japanese era years (wareki) to the Gregorian calendar
#     ──────────────────────────────────────────────────────────────────────────────
# JA: ──────────────────────────────────────────────────────────────────────────────
#     和暦（日本の元号）を西暦に変換する定数と関数
#     ──────────────────────────────────────────────────────────────────────────────
JAPANESE_ERA_MAP = {
    "令和": 2018,  # 令和元年 = 2019年, 令和N年 = 2018 + N
    # EN: Reiwa 1 = 2019, Reiwa N = 2018 + N
    # JA: 令和元年 = 2019年、令和N年 = 2018 + N
    "平成": 1988,  # 平成元年 = 1989年, 平成N年 = 1988 + N
    # EN: Heisei 1 = 1989, Heisei N = 1988 + N
    # JA: 平成元年 = 1989年、平成N年 = 1988 + N
    "昭和": 1925,  # 昭和元年 = 1926年, 昭和N年 = 1925 + N
    # EN: Showa 1 = 1926, Showa N = 1925 + N
    # JA: 昭和元年 = 1926年、昭和N年 = 1925 + N
    "大正": 1911,  # 大正元年 = 1912年, 大正N年 = 1911 + N
    # EN: Taisho 1 = 1912, Taisho N = 1911 + N
    # JA: 大正元年 = 1912年、大正N年 = 1911 + N
    "明治": 1867,  # 明治元年 = 1868年, 明治N年 = 1867 + N
    # EN: Meiji 1 = 1868, Meiji N = 1867 + N
    # JA: 明治元年 = 1868年、明治N年 = 1867 + N
}

# 匹配 "平成27年01月22日" / "昭和 59 年 6 月" / "令和3年" / "平成8年1月" 等
# EN: Matches "平成27年01月22日" / "昭和 59 年 6 月" / "令和3年" / "平成8年1月", etc.
# JA: 「平成27年01月22日」／「昭和 59 年 6 月」／「令和3年」／「平成8年1月」などにマッチする
WAREKI_RE = re.compile(
    r"(令和|平成|昭和|大正|明治)\s*(\d{1,2}|元)\s*年"
    r"(?:\s*(\d{1,2})\s*月(?:\s*(\d{1,2})\s*日)?)?",
)


def convert_wareki_to_gregorian(text: str) -> str:
    """将文本中的日本年号日期（和暦）转换为公历日期（西暦）

    EN: Convert Japanese era dates (wareki) in the text to Gregorian dates (seireki)

    JA: テキスト中の和暦の日付を西暦の日付に変換する
    """
    def _replace(m: re.Match) -> str:
        era = m.group(1)
        year_str = m.group(2)
        year_num = 1 if year_str == "元" else int(year_str)
        base = JAPANESE_ERA_MAP.get(era, 0)
        if base == 0:
            return m.group(0)  # 未知年号，保持原样
            # EN: Unknown era name; keep as is
            # JA: 未知の元号はそのまま残す
        greg_year = base + year_num
        month = m.group(3)
        day = m.group(4)
        if day and month:
            return f"{greg_year}年{int(month)}月{int(day)}日"
        elif month:
            return f"{greg_year}年{int(month)}月"
        else:
            return f"{greg_year}年"
    return WAREKI_RE.sub(_replace, text)


# 模块别名字典
# EN: Module alias dictionary
# JA: モジュールの別名辞書
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
    "training_list": {"培训经历", "培训经验", "研修", "training", "training experience"},
}

SECTION_LOOKUP = {
    re.sub(r"[\s:：·・•|｜_\-【】\[\]（）()]+", "", alias).casefold(): section_type
    for section_type, aliases in SECTION_ALIASES.items()
    for alias in aliases
}

# 非简历文件排除正则（如考核表、绩效、求人票、通讯录、开票信息等）
# EN: Regex excluding non-résumé files (e.g. appraisal forms, performance reviews, job postings, address books, invoicing info)
# JA: 非履歴書ファイルを除外する正規表現（評価表、業績評価、求人票、連絡先一覧、請求書情報など）
NON_RESUME_HARD_PATTERNS = [
    re.compile(r"評価シート|業績管理表|業績表|評価表|绩效考核|绩效评估|考核表|评分表|评价表|\bKPI\b|目标责任书", re.I),
    re.compile(r"职位要求|任职要求|任职资格|岗位要求|职位说明|需求表|岗位说明书|招聘说明书|求人票|求人募集|募集要項|募集要件|採用情報", re.I),
    re.compile(r"招聘(?:信息|启事|简章|需求|计划|岗位|职位|JD|公告)|急聘|招贤纳士", re.I),
    re.compile(r"\b(?:job\s*description|job\s*specification|vacancy\s*announcement|hiring\s*notice)\b", re.I),
    re.compile(r"(?:^|[\s_\-.])JD(?:$|[\s_\-.])", re.I),
    re.compile(r"通讯录|名簿|連絡先|電話帳|名单|联络表|员工名册|社員名簿|开票信息|发票|考勤表|签到表", re.I),
    re.compile(r"面试名单|面接(?:名单|者|候補)|应聘人员清单|简历库列表|简历列表|人才库", re.I),
    re.compile(r"休暇申請|有給申請|早退申請|遅刻申請|请假申请|休假申请|休暇届", re.I),
    re.compile(r"振り返りシート|月振り返り|月次振り返り|月度复盘|月度復盤|个人复盘", re.I),
    re.compile(r"应聘人员面试表|應聘人員面試表|候选人面试表|候選人面試表|面试评价表|面接評価表", re.I),
]

RESUME_TITLE_RE = re.compile(r"職務経歴書|履歴書|履历书|简历|resume|curriculum vitae|cv\b|経歴書|个人简历|个人履历", re.I)
RESUME_MARKERS_RE = re.compile(r"个人信息|基本信息|姓名|性别|出生日期|出生年月|求职意向|工作经验|教育经历|工作经历|学歴|職歴|最終学歴|履歴書|職務経歴書|简历|履历书|resume|curriculum vitae|氏名|名前|住所|地址|住址|電話番号|邮箱|メールアドレス|e-?mail", re.I)
HR_ADMIN_FILENAME_RE = re.compile(
    r"新员工登记表|员工登记表|员工信息表|员工档案|人事档案|人事台账|员工花名册|社員名簿|従業員名簿|employee\s+roster",
    re.I,
)
HR_ADMIN_MARKERS = (
    "入职日期", "入职职位", "试用期", "合同签订", "合同到期", "工资账号",
    "开户行", "绩效评价", "奖惩记录", "离职日期", "緊急連絡先", "入社日",
)

# ──────────────────────────────────────────────────────────────────────────────
# 空模版行/块判定正则（参考 repair_semantic_html_dom.py）
# ──────────────────────────────────────────────────────────────────────────────
# EN: ──────────────────────────────────────────────────────────────────────────────
#     Regexes for detecting empty template rows/blocks (see repair_semantic_html_dom.py)
#     ──────────────────────────────────────────────────────────────────────────────
# JA: ──────────────────────────────────────────────────────────────────────────────
#     空のテンプレート行・ブロックを判定する正規表現（repair_semantic_html_dom.py を参照）
#     ──────────────────────────────────────────────────────────────────────────────
EMPTY_TEMPLATE_ROW_PATTERNS = [
    re.compile(r"^年\s*月\s*企業名[:：]?\s*所属部門[:：]?\s*業務内容[:：]?$"),
    re.compile(r"^年\s*月\s*退職理由[:：]?$"),
    re.compile(r"^年\s*月\s*$"),
]

# 日式简历中常见的纯模版标签词（当整行仅包含这些词时视为空模版行）
# EN: Pure template label words common in Japanese-style résumés (a row containing only these words is treated as an empty template row)
# JA: 日本式の履歴書によくあるテンプレートのラベル語（行がこれらの語だけを含む場合は空のテンプレート行とみなす）
TEMPLATE_LABEL_KEYWORDS = frozenset({
    "年", "月", "勤務期間", "会社名", "仕事内容", "退職理由",
    "経営資本", "国営", "日系", "欧米", "その他", "担当部署：役職",
    "勤務地", "給与（税込or手取り）", "期間", "学校名及び専攻", "学位",
    "～", "フリガナ",
})

# 匹配 "N．勤務期間" 格式的块标题行
# EN: Matches block heading lines in the "N．勤務期間" format
# JA: 「N．勤務期間」形式のブロック見出し行にマッチする
TEMPLATE_BLOCK_HEADER_RE = re.compile(r"^\d+[．.\s]*勤務期間$")


# ──────────────────────────────────────────────────────────────────────────────
# 强化的手机号与邮箱严格合规验证
# ──────────────────────────────────────────────────────────────────────────────
# EN: ──────────────────────────────────────────────────────────────────────────────
#     Strengthened strict validation of phone numbers and e-mail addresses
#     ──────────────────────────────────────────────────────────────────────────────
# JA: ──────────────────────────────────────────────────────────────────────────────
#     電話番号とメールアドレスの強化された厳格な検証
#     ──────────────────────────────────────────────────────────────────────────────
CN_VALID_PREFIXES = frozenset({
    "130", "131", "132", "133", "134", "135", "136", "137", "138", "139",
    "145", "147", "149",
    "150", "151", "152", "153", "155", "156", "157", "158", "159",
    "166", "167",
    "170", "171", "172", "173", "175", "176", "177", "178",
    "180", "181", "182", "183", "184", "185", "186", "187", "188", "189",
    "191", "193", "195", "198", "199",
})

# 排除全重复或简单等差数列构成的假号码
# EN: Exclude fake numbers made of all repeated digits or simple arithmetic sequences
# JA: すべて同じ数字や単純な等差数列でできた偽の番号を除外する
FAKE_PHONE_NUMS = frozenset({
    "13800000000", "13888888888", "13900000000", "12345678901",
    "11111111111", "22222222222", "33333333333", "44444444444",
    "55555555555", "66666666666", "77777777777", "88888888888",
    "99999999999", "00000000000", "10000000000", "12345678900",
})

FAKE_EMAIL_PATTERNS = [
    re.compile(r"^(?:test|sample|admin|info|user|xxx|aaa|123456)@(?:test|sample|qq|163|gmail)\.com$", re.I),
]


def validate_phone(phone: str) -> bool:
    """严格验证提取到的电话号码合法性

    EN: Strictly validate extracted phone numbers

    JA: 抽出した電話番号の妥当性を厳格に検証する
    """
    if not phone:
        return False
    digits = re.sub(r"[^\d]", "", phone)
    if digits in FAKE_PHONE_NUMS:
        return False
    # 检查中国手机号 (11位)
    # EN: Check Chinese mobile numbers (11 digits)
    # JA: 中国の携帯電話番号（11 桁）をチェックする
    if len(digits) == 11 and digits.startswith("1"):
        if digits[:3] in CN_VALID_PREFIXES:
            return True
        return False
    # 检查带 +86 的中国手机号
    # EN: Check Chinese mobile numbers with +86
    # JA: +86 付きの中国の携帯電話番号をチェックする
    if phone.startswith("+86") and len(digits) == 13 and digits[2:5] in CN_VALID_PREFIXES:
        return True
    # 检查日本手机号 (070/080/090 开头 11 位)
    # EN: Check Japanese mobile numbers (11 digits starting with 070/080/090)
    # JA: 日本の携帯電話番号（070/080/090 で始まる 11 桁）をチェックする
    if re.match(r"^0[789]0\d{8}$", digits):
        return True
    # 检查带 +81 的日本手机号
    # EN: Check Japanese mobile numbers with +81
    # JA: +81 付きの日本の携帯電話番号をチェックする
    if phone.startswith("+81") and re.match(r"^81[789]0\d{8}$", digits):
        return True
    # 国际通用号码格式 (+开头 8-15 位)
    # EN: International number format (starting with +, 8-15 digits)
    # JA: 国際的な番号形式（+ で始まる 8〜15 桁）
    if phone.startswith("+") and 8 <= len(digits) <= 15:
        return True
    return False


def validate_email(email: str) -> bool:
    """严格验证电子邮箱合法性

    EN: Strictly validate e-mail addresses

    JA: メールアドレスの妥当性を厳格に検証する
    """
    if not email or len(email) < 6:
        return False
    if not EMAIL_STANDARD_RE.match(email):
        return False
    for pat in FAKE_EMAIL_PATTERNS:
        if pat.match(email):
            return False
    return True


def normalize_fullwidth_digits(text: str) -> str:
    table = str.maketrans("０１２３４５６７８９＠－", "0123456789@-")
    return text.translate(table)


class GridCell:
    def __init__(self, val: str = "", rs: int = 1, cs: int = 1, is_covered: bool = False):
        self.val = val
        self.rs = rs
        self.cs = cs
        self.is_covered = is_covered


def source_path_hash(path_str: str) -> str:
    normalized = str(Path(path_str).resolve()).replace("/", "\\").casefold()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:12]


def safe_stem(value: str) -> str:
    cleaned = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", value).strip(" ._")
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned[:120] or "document"



def extract_contacts(text: str) -> tuple[str, str]:
    """抽取并严格清洗合规的手机号与邮箱

    EN: Extract and strictly clean valid phone numbers and e-mail addresses

    JA: 有効な電話番号とメールアドレスを抽出し、厳格にクレンジングする
    """
    norm_text = normalize_fullwidth_digits(text)

    # 1. 抽取邮箱
    # EN: 1. Extract e-mail addresses
    # JA: 1. メールアドレスを抽出する
    email = ""
    email_match = EMAIL_STANDARD_RE.search(norm_text)
    if email_match:
        cand_email = email_match.group(0).strip()
        if validate_email(cand_email):
            email = cand_email
    if not email:
        fuzzy_match = EMAIL_FUZZY_RE.search(norm_text)
        if fuzzy_match:
            cand_email = f"{fuzzy_match.group(1).strip()}@{fuzzy_match.group(2).strip()}"
            if validate_email(cand_email):
                email = cand_email

    # 2. 抽取手机号
    # EN: 2. Extract phone numbers
    # JA: 2. 電話番号を抽出する
    phone = ""
    # 优先在带有“手机/电话/携帯”等标签上下文的邻近区域匹配
    # EN: Prefer matching in the area near labels such as "手机/电话/携帯" (mobile/phone)
    # JA: 「手机／电话／携帯」などのラベルの近くの範囲でのマッチを優先する
    tel_kw_match = TEL_KEYWORD_RE.search(norm_text)
    if tel_kw_match:
        raw_phone = tel_kw_match.group(1).strip()
        cleaned_cand = re.sub(r"[^\d+]", "", raw_phone)
        if validate_phone(cleaned_cand):
            phone = raw_phone

    if not phone:
        # 全文匹配手机号正则，并校验前后边界
        # EN: Match the phone regex over the full text and validate the boundaries before and after
        # JA: 全文に電話番号の正規表現を当て、前後の境界を検証する
        for m in CN_MOBILE_RE.finditer(norm_text):
            cand = m.group(0).strip()
            if validate_phone(cand):
                phone = cand
                break

    if not phone:
        for m in JP_MOBILE_RE.finditer(norm_text):
            cand = m.group(0).strip()
            if validate_phone(cand):
                phone = cand
                break

    if not phone:
        for m in INT_MOBILE_RE.finditer(norm_text):
            cand = m.group(0).strip()
            if validate_phone(cand):
                phone = cand
                break

    return phone, email


def extract_candidate_contacts_from_html(content: str) -> tuple[str, str]:
    """Extract contacts only from the candidate body, never source metadata.

    XLS files frequently contain the recruiting agency's telephone number in
    the first rows (for example 上海修曼人才有限公司).  That number is useful
    provenance, but it is not the applicant's contact and must not make a
    non-contact workbook pass the resume gate.
    """
    soup = BeautifulSoup(content, "html.parser")
    main = soup.find("main", attrs={"data-role": "document-content"})
    if main is None:
        return "", ""
    return extract_contacts(main.get_text(" ", strip=True))


def set_source_contact_fields(content: str, phone: str, email: str) -> str:
    """Synchronize the provenance header with verified candidate contacts."""
    soup = BeautifulSoup(content, "html.parser")
    header = soup.find("header", attrs={"data-role": "source-metadata"})
    if header is None:
        return str(soup)
    for field, label, value in (("phone", "联系电话：", phone), ("email", "电子邮箱：", email)):
        nodes = header.find_all(attrs={"data-field": field})
        for node in nodes:
            node.decompose()
        if value:
            p = soup.new_tag("p")
            p["data-field"] = field
            p.append(soup.new_tag("b"))
            p.b.string = label
            p.append(value)
            header.append(p)
    return str(soup)


def is_resume_document(filename: str, text: str) -> tuple[bool, str]:
    """强化版简历文档前置判定算法

    EN: Strengthened algorithm for pre-judging whether a document is a résumé

    JA: 文書が履歴書かどうかを事前判定する強化版アルゴリズム
    """
    sample = (filename + "\n" + text[:15000]).strip()

    # 员工主数据、人事台账即使包含姓名、学历、工作经历和联系方式，也不是求职简历。
    # EN: Employee master data and HR ledgers are not job-seeker résumés, even if they contain name, degree, work history and contact details.
    # JA: 従業員マスターや人事台帳は、氏名・学歴・職歴・連絡先を含んでいても求職者の履歴書ではない。
    explicit_resume_title = bool(RESUME_TITLE_RE.search(filename))
    admin_marker_count = sum(marker in sample for marker in HR_ADMIN_MARKERS)
    if not explicit_resume_title and HR_ADMIN_FILENAME_RE.search(filename):
        return False, "文件名匹配员工登记/人事台账"
    if not explicit_resume_title and admin_marker_count >= 3:
        return False, f"正文命中 {admin_marker_count} 个人事管理字段"

    # 1. 检查硬性非简历模式 (考核表、绩效表、JD、招募公告、通讯录、签到表)
    # EN: 1. Check hard non-résumé patterns (appraisal forms, performance sheets, JDs, recruitment notices, address books, sign-in sheets)
    # JA: 1. 明確な非履歴書のパターンをチェックする（評価表、業績表、JD、募集告知、連絡先一覧、出席表）
    for pat in NON_RESUME_HARD_PATTERNS:
        if pat.search(filename):
            if not RESUME_TITLE_RE.search(filename):
                return False, f"文件名匹配非简历/JD模式: {pat.pattern}"

    for pat in NON_RESUME_HARD_PATTERNS:
        if len(pat.findall(sample[:3000])) >= 2:
            if not RESUME_TITLE_RE.search(sample[:1000]):
                return False, f"正文高频命中非简历/JD特征: {pat.pattern}"

    # 2. 检查简历标题特征
    # EN: 2. Check résumé title features
    # JA: 2. 履歴書のタイトルの特徴をチェックする
    has_explicit_title = bool(RESUME_TITLE_RE.search(sample))

    # 3. 统计简历结构特征词
    # EN: 3. Count résumé structure keywords
    # JA: 3. 履歴書の構造を示す語を数える
    markers = RESUME_MARKERS_RE.findall(sample)
    marker_count = len(markers)

    # 4. 检查是否包含个人基本信息与经历模块
    # EN: 4. Check whether personal basic information and experience sections are present
    # JA: 4. 個人の基本情報と経歴のセクションがあるかをチェックする
    has_person_info = any(k in sample for k in ("姓名", "氏名", "出生", "性别", "性別", "生年月日", "现居", "住址"))
    has_experience = any(k in sample for k in ("工作经历", "工作经验", "職歴", "職務経歴", "教育经历", "学歴", "学校", "求职意向", "志望"))

    if has_explicit_title:
        if marker_count >= 1 or (has_person_info and has_experience):
            return True, ""
        return False, "包含简历标题但缺乏实际个人信息或履历内容"

    # 无明确简历标题时，要求更高的结构密集度和特征组合
    # EN: Without an explicit résumé title, require higher structural density and a combination of features
    # JA: 明確な履歴書のタイトルがない場合は、より高い構造の密度と特徴の組み合わせを要求する
    if marker_count >= 3 and has_person_info and has_experience:
        return True, ""

    return False, "缺少简历关键字段与履历结构标志"


# 字段别名字典 (用于匹配单元格表头打属性)
# EN: Field alias dictionary (used to match cell headers to attributes)
# JA: フィールドの別名辞書（セルの見出しを属性に対応付けるために使う）
COMMON_FIELD_ALIASES = {
    "full_name": {"姓名", "名字", "氏名", "name", "full name"},
    "gender": {"性别", "性別", "sex", "gender"},
    "age": {"年龄", "年齢", "age"},
    "birth_date": {"出生日期", "出生年月日", "生年月日", "date of birth", "birthday"},
    "phone": {"电话", "手机", "联系电话", "联系方式", "電話", "携帯", "携帯電話番号", "連絡先", "phone", "mobile", "tel"},
    "email": {"邮箱", "电子邮箱", "邮件", "メールアドレス", "email", "e-mail"},
    "city": {"城市", "所在城市", "现居城市", "居住城市", "city", "current city"},
    "address": {"地址", "现居住地", "居住地", "居住地址", "住址", "住所", "address"},
    "household_registration": {"户籍", "戶籍", "戸籍", "户口", "籍贯", "本籍", "出身地"},
    "marital_status": {"婚姻状况", "婚姻状況", "婚姻状態", "配偶者", "marital status"},
    "education_degree": {"最高学历", "学历", "学歴", "degree", "education degree"},
    "school_name": {"毕业院校", "毕业学校", "学校", "学校名", "school", "university"},
    "major": {"专业", "専攻", "major"},
}




def parse_excel_date(val: float, datemode: int = 0) -> str:
    try:
        dt = xlrd.xldate_as_datetime(val, datemode)
        if dt.day == 1 and dt.hour == 0 and dt.minute == 0:
            return dt.strftime("%Y年%m月")
        return dt.strftime("%Y-%m-%d")
    except Exception:
        if 10000 <= val <= 60000:
            try:
                epoch = datetime.datetime(1899, 12, 30)
                dt = epoch + datetime.timedelta(days=val)
                return dt.strftime("%Y年%m月")
            except Exception:
                pass
        return str(val)


def clean_cell_value(val: Any, ctype: int = 0, datemode: int = 0, is_date_format: bool = False) -> str:
    if val is None:
        return ""
    if isinstance(val, (datetime.datetime, datetime.date)):
        if hasattr(val, "day") and val.day == 1 and hasattr(val, "hour") and val.hour == 0:
            return val.strftime("%Y年%m月")
        return val.strftime("%Y-%m-%d")
    if (ctype == xlrd.XL_CELL_DATE or is_date_format) and isinstance(val, (int, float)):
        return parse_excel_date(float(val), datemode)

    # 针对 Excel 序列号日期的强力还原 (如 43922.0 或 43922 对应的 2020年4月)
    # EN: Robust restoration of Excel serial-number dates (e.g. 43922.0 or 43922 corresponds to April 2020)
    # JA: Excel のシリアル値の日付を確実に復元する（例：43922.0 や 43922 は 2020年4月に対応）
    if isinstance(val, (int, float)) and 30000 <= val <= 60000:
        try:
            dt_str = parse_excel_date(float(val), datemode)
            if re.match(r"^\d{4}年\d{1,2}月$", dt_str) or re.match(r"^\d{4}-\d{2}-\d{2}$", dt_str):
                return dt_str
        except Exception:
            pass

    s = str(val).strip()
    if not s or BLANK_RE.match(s):
        return ""
    if s.lower() in EXCEL_ERRORS:
        return ""
    if s.startswith("="):
        return ""

    # 去除多余浮点数 ".0" (如 13800000014.0 -> 13800000014)
    # EN: Remove a superfluous float ".0" (e.g. 13800000014.0 -> 13800000014)
    # JA: 余分な浮動小数点の「.0」を除去する（例：13800000014.0 -> 13800000014）
    if isinstance(val, float) and val.is_integer():
        s = str(int(val))
    elif s.endswith(".0"):
        s = s[:-2]

    # 尝试还原 5 位序列号日期
    # EN: Try to restore 5-digit serial-number dates
    # JA: 5 桁のシリアル値の日付の復元を試みる
    if re.match(r"^\d{5}$", s):
        try:
            num = float(s)
            if 30000 <= num <= 60000:
                dt_str = parse_excel_date(num, datemode)
                if re.match(r"^\d{4}年\d{1,2}月$", dt_str) or re.match(r"^\d{4}-\d{2}-\d{2}$", dt_str):
                    return dt_str
        except Exception:
            pass

    s = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", s)
    # 日本年号（和暦）自动转换为公历（西暦）
    # EN: Automatically convert Japanese era years (wareki) to Gregorian years (seireki)
    # JA: 和暦を西暦に自動変換する
    if WAREKI_RE.search(s):
        s = convert_wareki_to_gregorian(s)
    return s



def _read_xlsx_grid(path: Path) -> list[tuple[str, list[list[GridCell]]]]:
    wb = openpyxl.load_workbook(str(path), data_only=True)
    result = []
    for ws in wb.worksheets:
        max_r = ws.max_row
        max_c = ws.max_column
        if not max_r or not max_c:
            continue

        grid = [[GridCell() for _ in range(max_c)] for _ in range(max_r)]
        merge_map = {}
        covered_set = set()

        for rng in ws.merged_cells.ranges:
            r1, r2 = rng.min_row - 1, rng.max_row - 1
            c1, c2 = rng.min_col - 1, rng.max_col - 1
            rs = r2 - r1 + 1
            cs = c2 - c1 + 1
            merge_map[(r1, c1)] = (rs, cs)
            for r in range(r1, r2 + 1):
                for c in range(c1, c2 + 1):
                    if r != r1 or c != c1:
                        covered_set.add((r, c))

        for r_idx, row in enumerate(ws.iter_rows(max_row=max_r, max_col=max_c)):
            for c_idx, cell_obj in enumerate(row):
                if (r_idx, c_idx) in covered_set:
                    grid[r_idx][c_idx] = GridCell(is_covered=True)
                else:
                    is_date_fmt = bool(
                        getattr(cell_obj, "is_date", False) or (
                            cell_obj.number_format and any(
                                k in cell_obj.number_format.lower()
                                for k in ("y", "m", "d", "年", "月", "日")
                            )
                        )
                    )
                    val = clean_cell_value(cell_obj.value, is_date_format=is_date_fmt)
                    rs, cs = merge_map.get((r_idx, c_idx), (1, 1))
                    grid[r_idx][c_idx] = GridCell(val=val, rs=rs, cs=cs)

        cleaned_grid = _trim_outer_grid(grid)
        if cleaned_grid and not _is_empty_grid(cleaned_grid):
            result.append((ws.title or "", cleaned_grid))

    wb.close()
    return result


def _read_xls_grid(path: Path) -> list[tuple[str, list[list[GridCell]]]]:
    wb = xlrd.open_workbook(str(path), formatting_info=True, on_demand=False)
    result = []
    for sh in wb.sheets():
        max_r = sh.nrows
        max_c = sh.ncols
        if not max_r or not max_c:
            continue

        grid = [[GridCell() for _ in range(max_c)] for _ in range(max_r)]
        merge_map = {}
        covered_set = set()

        for rlo, rhi, clo, chi in sh.merged_cells:
            rs = rhi - rlo
            cs = chi - clo
            merge_map[(rlo, clo)] = (rs, cs)
            for r in range(rlo, rhi):
                for c in range(clo, chi):
                    if r != rlo or c != clo:
                        covered_set.add((r, c))

        for r in range(max_r):
            for c in range(max_c):
                if (r, c) in covered_set:
                    grid[r][c] = GridCell(is_covered=True)
                else:
                    raw_val = sh.cell_value(r, c)
                    ctype = sh.cell_type(r, c)
                    val = clean_cell_value(raw_val, ctype, wb.datemode)
                    rs, cs = merge_map.get((r, c), (1, 1))
                    grid[r][c] = GridCell(val=val, rs=rs, cs=cs)

        cleaned_grid = _trim_outer_grid(grid)
        if cleaned_grid and not _is_empty_grid(cleaned_grid):
            result.append((sh.name or "", cleaned_grid))

    return result


def _detect_format_by_magic(path: Path) -> str:
    try:
        header = path.read_bytes()[:8]
    except Exception:
        return "unknown"
    if header[:4] == b"PK\x03\x04":
        return "xlsx"
    if header[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
        return "xls"
    return "unknown"


def read_excel_grid(path: Path) -> list[tuple[str, list[list[GridCell]]]]:
    ext = path.suffix.lower()
    fmt = _detect_format_by_magic(path)
    errors: list[str] = []
    if ext in {".xlsx", ".xlsm", ".xltx", ".xltm"} or fmt == "xlsx":
        try:
            return _read_xlsx_grid(path)
        except Exception as exc:
            errors.append(f"openpyxl: {type(exc).__name__}: {exc}")
            try:
                return _read_xls_grid(path)
            except Exception as exc:
                errors.append(f"xlrd: {type(exc).__name__}: {exc}")
    else:
        try:
            return _read_xls_grid(path)
        except Exception as exc:
            errors.append(f"xlrd: {type(exc).__name__}: {exc}")
            try:
                return _read_xlsx_grid(path)
            except Exception as exc:
                errors.append(f"openpyxl: {type(exc).__name__}: {exc}")
    raise RuntimeError("；".join(errors) or "无法识别 Excel 文件格式")


def _is_empty_grid(grid: list[list[GridCell]]) -> bool:
    """判断表格是否完全全空或仅含模版标签（过滤无实际内容的空表格）

    EN: Decide whether a table is completely empty or contains only template labels (to filter empty tables without real content)

    JA: 表が完全に空か、テンプレートのラベルしか含まないかを判定する（実内容のない空の表を除外するため）
    """
    non_covered_vals = [cell.val for row in grid for cell in row if cell.val and not cell.is_covered]
    total_len = sum(len(v) for v in non_covered_vals)
    if total_len < 3:
        return True
    actual_data = [v.strip() for v in non_covered_vals if v.strip() and v.strip() not in TEMPLATE_LABEL_KEYWORDS]
    return len(actual_data) == 0


def _trim_outer_grid(grid: list[list[GridCell]]) -> list[list[GridCell]]:
    if not grid or not grid[0]:
        return []
    num_rows = len(grid)
    num_cols = len(grid[0])
    min_r, max_r = num_rows, -1
    min_c, max_c = num_cols, -1

    for r in range(num_rows):
        for c in range(num_cols):
            cell = grid[r][c]
            if cell.val or cell.rs > 1 or cell.cs > 1:
                if r < min_r: min_r = r
                if r + cell.rs - 1 > max_r: max_r = r + cell.rs - 1
                if c < min_c: min_c = c
                if c + cell.cs - 1 > max_c: max_c = c + cell.cs - 1

    if max_r < min_r or max_c < min_c:
        return []

    trimmed = []
    for r in range(min_r, max_r + 1):
        row_cells = []
        for c in range(min_c, max_c + 1):
            row_cells.append(grid[r][c])
        trimmed.append(row_cells)
    return trimmed


TEMPLATE_LABEL_KEYWORDS = frozenset({
    "年", "月", "日", "现在", "管理No", "管理", "申请公司",
    "申请职位", "推荐日期", "人才简历",
    "勤務期間", "会社名", "仕事内容", "退職理由",
    "経営資本", "国営", "日系", "欧米", "その他", "担当部署役職",
    "勤務地", "給与税込or手取り", "期间", "学校名及び専攻", "学位",
    "フリガナ", "1", "2", "3", "4", "5",
    "最近1年内参加过面试的公司", "登录过的其他人才公司", "有关转职的想法和意向",
    "希望就职的行业", "希望从事的工作", "其它取得资格",
})



def _is_empty_template_row(row: list[GridCell]) -> bool:
    """判断表格行是否为空模版行（仅含标签关键词或空序号，无实际数据）

    EN: Decide whether a table row is an empty template row (only label keywords or empty sequence numbers, no real data)

    JA: 表の行が空のテンプレート行か（ラベルの語か空の通し番号だけで実データがない）を判定する
    """
    clean_texts = [re.sub(r"[^\u4e00-\u9fa5a-zA-Z0-9]", "", c.val) for c in row if c.val and not c.is_covered]
    if not clean_texts:
        return True

    template_words = {
        "\u7533\u8bf7\u516c\u53f8",  # 申请公司
        # EN: Company applied to
        # JA: 応募先の会社
        "\u7533\u8bf7\u804c\u4f4d",  # 申请职位
        # EN: Position applied for
        # JA: 応募職位
        "\u63a8\u8350\u65e5\u671f",  # 推荐日期
        # EN: Recommendation date
        # JA: 推薦日
        "\u7ba1\u7406No",          # 管理No
        # EN: Management No.
        # JA: 管理番号
        "\u7ba1\u7406",            # 管理
        # EN: Management
        # JA: 管理
        "\u4eba\u624d\u7b80\u5386",  # 人才简历
        # EN: Talent résumé
        # JA: 人材の履歴書
        "\u7b80\u5386",            # 简历
        # EN: Résumé
        # JA: 履歴書
        "\u5e74", "\u6708", "\u65e5", "\u7b59\u5728", "\u73b0\u5728",

        "\u52e4\u52d9\u671f\u9593", "\u4f1a\u793e\u540d", "\u4ed5\u4e8b\u5185\u5bb9", "\u9000\u8077\u7406\u7531",

        "1", "2", "3", "4", "5",
    }
    return all(v in template_words or re.match(r"^\d+$", v) for v in clean_texts)





def _merge_year_month_fragments(grid: list[list[GridCell]]) -> list[list[GridCell]]:
    """强力合并教育、工作经历、出生年月日年龄及数值单位碎片。

    EN: Aggressively merge fragments of education, work history, birth date/age and number units.

    JA: 学歴・職歴・生年月日と年齢・数値の単位の断片を積極的に結合する。
    """
    for row in grid:
        num_cols = len(row)
        active_cells: list[tuple[int, str]] = []
        for ci in range(num_cols):
            cell = row[ci]
            if not cell.is_covered:
                clean_v = re.sub(r"\s+", "", cell.val)
                if clean_v:
                    active_cells.append((ci, clean_v))

        if len(active_cells) < 2:
            continue

        i = 0
        while i < len(active_cells) - 1:
            # 模式 0-A：出生年月日+年龄全散落 [1990] [年] [6] [月] [11] [日...] [31] [岁...]
            # EN: Pattern 0-A: birth date + age fully scattered [1990] [年] [6] [月] [11] [日...] [31] [岁...]
            # JA: パターン 0-A：生年月日 + 年齢が完全にばらばら [1990] [年] [6] [月] [11] [日...] [31] [岁...]
            if i + 5 < len(active_cells):
                ci0, v0 = active_cells[i]
                ci1, v1 = active_cells[i + 1]
                ci2, v2 = active_cells[i + 2]
                ci3, v3 = active_cells[i + 3]
                ci4, v4 = active_cells[i + 4]
                ci5, v5 = active_cells[i + 5]
                if (re.match(r"^\d{4}$", v0)
                        and re.match(r"^\d{1,2}$", v2)
                        and re.match(r"^\d{1,2}$", v4)):
                    age_text = ""
                    last_k = 5
                    if i + 7 < len(active_cells):
                        v6 = active_cells[i + 6][1]
                        if re.search(r"\d{1,3}", v6):
                            age_text = f"（{re.sub(r'\D', '', v6)}岁）"
                            last_k = 7
                    elif i + 6 < len(active_cells):
                        v6 = active_cells[i + 6][1]
                        if re.search(r"\d{1,3}", v6):
                            age_text = f"（{re.sub(r'\D', '', v6)}岁）"
                            last_k = 6

                    merged = f"{v0}年{int(v2)}月{int(v4)}日{age_text}"
                    end_ci = active_cells[i + last_k][0] + max(1, row[active_cells[i + last_k][0]].cs) - 1
                    total_cs = end_ci - ci0 + 1
                    row[ci0].val = merged
                    row[ci0].cs = total_cs
                    for k in range(1, last_k + 1):
                        c_target = active_cells[i + k][0]
                        row[c_target].is_covered = True
                        row[c_target].val = ""
                    i += (last_k + 1)
                    continue




            # 模式 0-B：6 单元格出生年月日散落 [1990] [年] [6] [月] [11] [日...]
            # EN: Pattern 0-B: birth date scattered over 6 cells [1990] [年] [6] [月] [11] [日...]
            # JA: パターン 0-B：生年月日が 6 セルに分散 [1990] [年] [6] [月] [11] [日...]
            if i + 5 < len(active_cells):
                ci0, v0 = active_cells[i]
                ci1, v1 = active_cells[i + 1]
                ci2, v2 = active_cells[i + 2]
                ci3, v3 = active_cells[i + 3]
                ci4, v4 = active_cells[i + 4]
                ci5, v5 = active_cells[i + 5]
                if (re.match(r"^\d{4}$", v0) and v1 == "年"
                        and re.match(r"^\d{1,2}$", v2) and v3 == "月"
                        and re.match(r"^\d{1,2}$", v4) and v5.startswith("日")):
                    merged = f"{v0}年{int(v2)}月{int(v4)}日"
                    end_ci = ci5 + max(1, row[ci5].cs) - 1
                    total_cs = end_ci - ci0 + 1
                    row[ci0].val = merged
                    row[ci0].cs = total_cs
                    for c_idx in range(ci0 + 1, end_ci + 1):
                        row[c_idx].is_covered = True
                        row[c_idx].val = ""
                    i += 6
                    continue

            # 模式 0-C：4 单元格年月散落 [1990] [年] [6] [月...]
            # EN: Pattern 0-C: year-month scattered over 4 cells [1990] [年] [6] [月...]
            # JA: パターン 0-C：年月が 4 セルに分散 [1990] [年] [6] [月...]
            if i + 3 < len(active_cells):
                ci0, v0 = active_cells[i]
                ci1, v1 = active_cells[i + 1]
                ci2, v2 = active_cells[i + 2]
                ci3, v3 = active_cells[i + 3]
                if (re.match(r"^\d{4}$", v0) and v1 == "年"
                        and re.match(r"^\d{1,2}$", v2) and v3 in ("月", "月生", "月出生")):
                    merged = f"{v0}年{int(v2)}月"
                    end_ci = ci3 + max(1, row[ci3].cs) - 1
                    total_cs = end_ci - ci0 + 1
                    row[ci0].val = merged
                    row[ci0].cs = total_cs
                    for c_idx in range(ci0 + 1, end_ci + 1):
                        row[c_idx].is_covered = True
                        row[c_idx].val = ""
                    i += 4
                    continue

            # 模式 A：完整经历时间段 [2008年] [9月] [～/~/〜/至/-] [2012年] [6月]
            # EN: Pattern A: full experience period [2008年] [9月] [～/~/〜/至/-] [2012年] [6月]
            # JA: パターン A：経歴の期間全体 [2008年] [9月] [～/~/〜/至/-] [2012年] [6月]
            if i + 4 < len(active_cells):
                ci0, v0 = active_cells[i]
                ci1, v1 = active_cells[i + 1]
                ci2, v2 = active_cells[i + 2]
                ci3, v3 = active_cells[i + 3]
                ci4, v4 = active_cells[i + 4]
                if (re.match(r"^\d{4}\D?$", v0) and re.match(r"^\d{1,2}\D?$", v1)
                        and (v2 in ("～", "~", "〜", "-", "−", "至", "—", "-->") or not v2.isalnum())
                        and re.match(r"^\d{4}\D?$", v3) and re.match(r"^\d{1,2}\D?$", v4)):
                    y1 = re.sub(r"\D", "", v0)
                    m1 = re.sub(r"\D", "", v1)
                    y2 = re.sub(r"\D", "", v3)
                    m2 = re.sub(r"\D", "", v4)
                    merged = f"{y1}年{int(m1)}月～{y2}年{int(m2)}月"

                    end_ci = ci4 + max(1, row[ci4].cs) - 1
                    total_cs = end_ci - ci0 + 1

                    row[ci0].val = merged
                    row[ci0].cs = total_cs
                    for c_idx in range(ci0 + 1, end_ci + 1):
                        row[c_idx].is_covered = True
                        row[c_idx].val = ""
                    i += 5
                    continue

            # 模式 B-1：3 单元格带年月时间段 [2016年1月] [～] [2019年3月/至今] (支持 rowspan)
            # EN: Pattern B-1: 3-cell period with year-month [2016年1月] [～] [2019年3月/至今] (rowspan supported)
            # JA: パターン B-1：年月付きの 3 セルの期間 [2016年1月] [～] [2019年3月/至今]（rowspan 対応）
            if i + 2 < len(active_cells):
                ci0, v0 = active_cells[i]
                ci1, v1 = active_cells[i + 1]
                ci2, v2 = active_cells[i + 2]
                if (re.search(r"\d{4}年\d{1,2}月?", v0)
                        and (v1 in ("～", "~", "〜", "-", "−", "至", "—") or not v1.isalnum())
                        and (re.search(r"\d{4}年\d{1,2}月?", v2) or v2 in ("今", "现在", "至今", "在職中", "Present"))):
                    v0_clean = re.sub(r"\s+", "", v0)
                    v2_clean = re.sub(r"\s+", "", v2)
                    merged = f"{v0_clean}～{v2_clean}"

                    end_ci = ci2 + max(1, row[ci2].cs) - 1
                    total_cs = end_ci - ci0 + 1
                    max_rs = max(row[ci0].rs, row[ci1].rs, row[ci2].rs)

                    row[ci0].val = merged
                    row[ci0].cs = total_cs
                    row[ci0].rs = max_rs
                    for c_idx in range(ci0 + 1, end_ci + 1):
                        row[c_idx].is_covered = True
                        row[c_idx].val = ""
                    i += 3
                    continue

            # 模式 B-1-2：2 单元格直接起止时间段 [2019年6月] [2020年4月/至今] (无波浪号隔离)
            # EN: Pattern B-1-2: 2-cell direct start/end period [2019年6月] [2020年4月/至今] (no tilde separator)
            # JA: パターン B-1-2：2 セルで直接の開始・終了 [2019年6月] [2020年4月/至今]（波線の区切りなし）
            if i + 1 < len(active_cells):
                ci0, v0 = active_cells[i]
                ci1, v1 = active_cells[i + 1]
                if (re.search(r"\d{4}年\d{1,2}月?", v0)
                        and (re.search(r"\d{4}年\d{1,2}月?", v1) or v1 in ("今", "现在", "至今", "在職中", "Present"))):
                    v0_clean = re.sub(r"\s+", "", v0)
                    v1_clean = re.sub(r"\s+", "", v1)
                    merged = f"{v0_clean}～{v1_clean}"

                    end_ci = ci1 + max(1, row[ci1].cs) - 1
                    total_cs = end_ci - ci0 + 1
                    max_rs = max(row[ci0].rs, row[ci1].rs)

                    row[ci0].val = merged
                    row[ci0].cs = total_cs
                    row[ci0].rs = max_rs
                    for c_idx in range(ci0 + 1, end_ci + 1):
                        row[c_idx].is_covered = True
                        row[c_idx].val = ""
                    i += 2
                    continue

            # 模式 D：数值与单位合并 [168] [CM/KG/型/厘米/公斤]
            # EN: Pattern D: number merged with unit [168] [CM/KG/型/厘米/公斤]
            # JA: パターン D：数値と単位の結合 [168] [CM/KG/型/厘米/公斤]
            ci0, v0 = active_cells[i]
            ci1, v1 = active_cells[i + 1]
            if (re.match(r"^\d{1,3}$", v0) and v1.upper() in ("CM", "KG", "型", "厘米", "公斤", "岁", "歳", "才", "岁）", "歳）")) or (v0.upper() in ("A", "B", "O", "AB") and v1 == "型"):
                end_ci = ci1 + max(1, row[ci1].cs) - 1
                total_cs = end_ci - ci0 + 1
                row[ci0].val = f"{v0}{v1}"
                row[ci0].cs = total_cs
                for c_idx in range(ci0 + 1, end_ci + 1):
                    row[c_idx].is_covered = True
                    row[c_idx].val = ""
                i += 2
                continue
            # 当前相邻单元格未命中任何合并模式时必须前进；否则普通行会死循环。
            # EN: When the current adjacent cells match no merge pattern we must advance; otherwise ordinary rows loop forever.
            # JA: 現在の隣接セルがどの結合パターンにもマッチしない場合は必ず先に進む。さもないと通常の行で無限ループになる。
            i += 1
    return grid





def _is_empty_record_block(rows: list[list[GridCell]], start_idx: int) -> tuple[bool, int]:
    """检测从 start_idx 开始的连续行是否构成一个空的日式工作经历记录块。
    返回 (是否为空块, 块的行数)。
    一个典型的日式勤務記録块包含：勤務期間 / 会社名 / 経営資本 / 仕事内容 / 退職理由

    EN: Detect whether the consecutive rows starting at start_idx form an empty Japanese-style work record block.
    Returns (whether it is an empty block, number of rows in the block).
    A typical Japanese work record block contains: 勤務期間 / 会社名 / 経営資本 / 仕事内容 / 退職理由

    JA: start_idx から始まる連続した行が、空の日本式職歴レコードブロックになっているかを検出する。
    戻り値：(空のブロックかどうか, ブロックの行数)。
    典型的な日本式の勤務記録ブロックは次を含む：勤務期間 / 会社名 / 経営資本 / 仕事内容 / 退職理由
    """
    if start_idx >= len(rows):
        return False, 0
    first_row = rows[start_idx]
    first_text = " ".join(c.val for c in first_row if c.val and not c.is_covered).strip()
    # 检查是否为 "N．勤務期間" 格式的块头
    # EN: Check whether this is a block header in the "N．勤務期間" format
    # JA: 「N．勤務期間」形式のブロック見出しかどうかをチェックする
    if not TEMPLATE_BLOCK_HEADER_RE.match(first_text):
        return False, 0
    # 检查该块头后的值列是否为空（勤務期間后面跟的是时间段）
    # EN: Check whether the value column after this block header is empty (勤務期間 is followed by a period)
    # JA: このブロック見出しの後の値の列が空かどうかをチェックする（勤務期間の後には期間が続く）
    data_vals = [c.val for c in first_row if c.val and not c.is_covered]
    # 如果数据列有非标签值，该块不是空的
    # EN: If the data column has a non-label value, the block is not empty
    # JA: データ列にラベル以外の値があれば、そのブロックは空ではない
    non_label = [v for v in data_vals if not TEMPLATE_BLOCK_HEADER_RE.match(v.strip())]
    if non_label:
        return False, 0
    # 向下扫描：检查后续行是否全部值为空（仅含标签）
    # EN: Scan downwards: check whether all following rows have empty values (labels only)
    # JA: 下方向にスキャンし、後続の行がすべて空の値（ラベルのみ）かどうかを確認する
    block_size = 1
    for i in range(start_idx + 1, min(start_idx + 8, len(rows))):
        row = rows[i]
        row_vals = [c.val for c in row if c.val and not c.is_covered]
        row_text = " ".join(row_vals).strip()
        # 如果碰到下一个块头或章节标题，停止
        # EN: Stop when the next block header or section heading is reached
        # JA: 次のブロック見出しまたは章見出しに達したら止める
        if TEMPLATE_BLOCK_HEADER_RE.match(row_text) or detect_section_type(row_text):
            break
        # 检查该行是否有非标签的实际数据
        # EN: Check whether this row has actual non-label data
        # JA: この行にラベル以外の実データがあるかどうかを確認する
        has_data = any(
            v.strip() and v.strip() not in TEMPLATE_LABEL_KEYWORDS
            for v in row_vals
        )
        if has_data:
            return False, 0  # 发现实际数据，整个块不是空的
            # EN: Found actual data, so the whole block is not empty
            # JA: 実データが見つかったため、ブロック全体は空ではない
        block_size += 1
    return True, block_size


def _is_empty_education_row(row: list[GridCell]) -> bool:
    """判断学歴行是否为空（序号 + 日期格 + 学校名 + 学位格全空）

    EN: Decide whether an education row is empty (sequence number + date cells + school name + degree cells all empty)

    JA: 学歴の行が空か（通し番号 + 日付のセル + 学校名 + 学位のセルがすべて空）を判定する
    """
    vals = [c.val.strip() for c in row if c.val and not c.is_covered]
    if not vals:
        return True
    # 如果仅包含序号（纯数字）或 "～" 分隔符，视为空
    # EN: If it contains only sequence numbers (pure digits) or the "～" separator, treat it as empty
    # JA: 通し番号（数字のみ）や「～」区切りしか含まない場合は空とみなす
    actual = [v for v in vals if not re.match(r"^\d+$", v) and v not in ("～", "~", "-", "−")]
    return len(actual) == 0


def _is_valid_field_value(field_name: str, val: str) -> bool:
    """语义字段值的严格强校验（防止跨列误吸）

    EN: Strict validation of semantic field values (prevents mistakenly absorbing values across columns)

    JA: 意味フィールドの値の厳格な検証（列をまたいで誤って値を取り込むのを防ぐ）
    """
    v = val.strip()
    if not v:
        return False
    if field_name == "gender":
        return v in {"男", "女", "Male", "Female", "M", "F", "男性", "女性"}
    if field_name == "marital_status":
        return any(k in v for k in ("已婚", "未婚", "独身", "单身", "离异", "既婚", "未婚", "配偶者"))
    if field_name == "age":
        return bool(re.match(r"^\d{1,3}\s*(?:岁|歳|才)?$", v)) or "满" in v
    if field_name == "birth_date":
        return bool(re.search(r"\d{4}|\d{2}年|\d{1,2}月", v))
    return True


def _filter_empty_template_rows(grid: list[list[GridCell]]) -> list[list[GridCell]]:
    """过滤 grid 中的空模版行、空记录块和纯全空行

    EN: Filter empty template rows, empty record blocks and completely empty rows in the grid

    JA: グリッド内の空のテンプレート行・空のレコードブロック・完全な空行を除外する
    """
    filtered: list[list[GridCell]] = []
    i = 0
    in_education = False
    header_started = False

    while i < len(grid):

        row = grid[i]

        # 0. 彻底过滤纯全空行 (整行无任何文本内容)
        # EN: 0. Thoroughly filter completely empty rows (rows with no text at all)
        # JA: 0. 完全に空の行（テキストがまったくない行）を徹底的に除外する
        row_text_all = "".join(c.val.strip() for c in row if c.val and not c.is_covered).strip()
        if not row_text_all:
            i += 1
            continue

        # 1. 顶部表头清理机制：在遇到拼音、姓名、联系方式等首个核心数据行之前，抹平所有模版占位行
        # EN: 1. Top header clean-up: before the first core data row (pinyin, name, contact, etc.), flatten all template placeholder rows
        # JA: 1. 上部ヘッダーの整理：ピンイン・氏名・連絡先などの最初の主要データ行が現れるまで、テンプレートのプレースホルダー行をすべて取り除く
        clean_row_str = re.sub(r"[^\u4e00-\u9fa5a-zA-Z0-9]", "", row_text_all)
        if not header_started:
            if any(k in clean_row_str for k in ("\u62fc\u97f3", "\u59d3\u540d", "\u6c0f\u540d", "\u57fa\u672c\u4fe1\u606f", "\u4e2a\u4eba\u7b80\u5386", "\u4e2a\u4eba\u4fe1\u606f")):
                header_started = True
            elif _is_empty_template_row(row) or any(k in clean_row_str for k in ("\u7533\u8bf7\u516c\u53f8", "\u7533\u8bf7\u804c\u4f4d", "\u63a8\u8350\u65e5\u671f", "\u7ba1\u7406No", "\u7ba1\u7406", "\u5e74\u6708\u73b0\u5728", "\u5e74\u6708", "\u4eba\u624d\u7b80\u5386")):
                i += 1
                continue


        # 2. 检查是否为空模版行
        # EN: 2. Check whether it is an empty template row
        # JA: 2. 空のテンプレート行かどうかを確認する
        if _is_empty_template_row(row):
            i += 1
            continue


        # 2. 检查是否为空记录块
        # EN: 2. Check whether it is an empty record block
        # JA: 2. 空のレコードブロックかどうかを確認する
        is_empty_block, block_size = _is_empty_record_block(grid, i)
        if is_empty_block:
            i += block_size
            continue

        # 3. 学歴区域的空行过滤
        # EN: 3. Filter empty rows in the 学歴 (education) area
        # JA: 3. 学歴エリアの空行を除外する
        sec = detect_section_type(row_text_all)
        if sec == "education_list":
            in_education = True
        elif sec and sec != "education_list":
            in_education = False

        if in_education and _is_empty_education_row(row):
            i += 1
            continue

        filtered.append(row)
        i += 1
    return filtered


def _annotate_grid_semantics(grid: list[list[GridCell]]) -> dict[tuple[int, int], dict[str, str]]:
    """二维物理网格 Label-Value 语义绑定引擎 (支持精准中点匹配与强类型值校验)

    EN: Label-Value semantic binding engine for the 2D physical grid (supports precise midpoint matching and strongly typed value validation)

    JA: 2D 物理グリッドの Label-Value 意味バインドエンジン（中点による精密マッチングと型に基づく値の厳格な検証に対応）
    """
    if not grid or not grid[0]:
        return {}

    num_rows = len(grid)
    num_cols = len(grid[0])

    span_map: dict[tuple[int, int], tuple[int, int]] = {}
    for r in range(num_rows):
        cur_c = 0
        for c in range(num_cols):
            cell = grid[r][c]
            if not cell.is_covered:
                cs = max(1, cell.cs)
                span_map[(r, c)] = (cur_c, cur_c + cs - 1)
                cur_c += cs
            else:
                cur_c += 1

    cell_attrs: dict[tuple[int, int], dict[str, str]] = {}
    bound_values: set[tuple[int, int]] = set()

    # 1. 纵向 Label -> Value 匹配 (针对紧邻下一行的精细中点匹配)
    # EN: 1. Vertical Label -> Value matching (fine midpoint matching against the row immediately below)
    # JA: 1. 縦方向の Label -> Value マッチング（すぐ下の行との中点による精密マッチング）
    for r in range(num_rows - 1):
        for c in range(num_cols):
            cell = grid[r][c]
            if cell.is_covered or not cell.val:
                continue

            fn = detect_field_name(cell.val)
            if not fn:
                continue

            l_start, l_end = span_map.get((r, c), (c, c))
            l_mid = (l_start + l_end) / 2.0  # 计算中点物理坐标
            # EN: Compute the physical midpoint coordinates
            # JA: 中点の物理座標を計算する

            best_bot: tuple[int, int] | None = None
            min_dist = 999.0

            for bot_c in range(num_cols):
                bot_cell = grid[r + 1][bot_c]
                if bot_cell.is_covered or not bot_cell.val:
                    continue
                b_start, b_end = span_map.get((r + 1, bot_c), (bot_c, bot_c))
                b_mid = (b_start + b_end) / 2.0

                # 必须在中点距离阈值范围内 (<= 3 列)
                # EN: Must be within the midpoint distance threshold (<= 3 columns)
                # JA: 中点の距離のしきい値（3 列以内）に収まっていなければならない
                dist = abs(l_mid - b_mid)
                if dist <= 3.5 and dist < min_dist:
                    # 关键强校验：值必须符合字段类型约定！
                    # EN: Key strict check: the value must match the field type convention!
                    # JA: 重要な厳格チェック：値はフィールドの型の規約に合っていなければならない！
                    if _is_valid_field_value(fn, bot_cell.val):
                        min_dist = dist
                        best_bot = (r + 1, bot_c)

            if best_bot:
                cell_attrs[(r, c)] = {"data-label-for": fn}
                cell_attrs[best_bot] = {"data-field": fn, "label": fn}
                bound_values.add(best_bot)

    # 2. 横向 Label -> Value 匹配 (同行右侧匹配)
    # EN: 2. Horizontal Label -> Value matching (matching to the right on the same row)
    # JA: 2. 横方向の Label -> Value マッチング（同じ行の右側とのマッチング）
    for r in range(num_rows):
        for c in range(num_cols):
            cell = grid[r][c]
            if cell.is_covered or not cell.val:
                continue

            fn = detect_field_name(cell.val)
            if not fn:
                continue

            if (r, c) not in cell_attrs:
                cell_attrs[(r, c)] = {"data-label-for": fn}

            for next_c in range(c + 1, num_cols):
                n_cell = grid[r][next_c]
                if n_cell.is_covered:
                    continue
                if detect_field_name(n_cell.val):
                    break
                if n_cell.val and (r, next_c) not in bound_values:
                    if _is_valid_field_value(fn, n_cell.val):
                        cell_attrs[(r, next_c)] = {"data-field": fn, "label": fn}
                        bound_values.add((r, next_c))
                        break

    return cell_attrs










def detect_field_name(cell_val: str) -> str:
    clean_val = re.sub(r"[\s:：·・•|｜_\-【】\[\]（）()]+", "", cell_val).casefold()
    for field_name, aliases in COMMON_FIELD_ALIASES.items():
        if clean_val in aliases:
            return field_name
    return ""


def detect_section_type(row_text: str) -> str:
    raw_text = str(row_text or "").strip()
    clean_text = re.sub(r"[\s:：·・•|｜_\-【】\[\]（）()]+", "", raw_text).casefold()
    exact = SECTION_LOOKUP.get(clean_text)
    if exact:
        return exact

    # Excel/Japanese templates append instructions to section headings, e.g.
    # ``学歴（高校入学から）`` and ``職歴（現職から入力してください）``.
    # Exact lookup misses these and the following work table is swallowed by
    # the preceding education section.  Treat an alias at the beginning of a
    # reasonably short heading as the section marker, while deliberately not
    # matching ordinary field labels such as ``工作内容``.
    for alias, section_type in sorted(SECTION_LOOKUP.items(), key=lambda item: len(item[0]), reverse=True):
        if not clean_text.startswith(alias):
            continue
        # A section heading may append an instruction in parentheses or
        # after a colon (``学歴（高校入学から）``), but a normal data row can
        # also start with a field label (``学历 | 大学``).  The latter must
        # stay in the current section; otherwise a profile row is promoted
        # to an education section and its value is parsed as school_name.
        raw_suffix = raw_text[len(alias):].lstrip() if len(raw_text) >= len(alias) else ""
        if raw_suffix and raw_suffix[0] not in "（(:：【[\u3000 \t\r\n-—–|｜":
            continue
        if len(clean_text) <= len(alias) + 32:
            return section_type
    return ""


def build_semantic_excel_html(
    src_p: Path,
    download_date: str,
    sheets: list[tuple[str, list[list[GridCell]]]],
    phone: str,
    email: str,
) -> str:
    """生成与 Word HTML 完全对齐的语义化 DOM 结构。
    标准属性体系：data-schema-version, data-target-schema, data-section-type,
    data-collection, data-label-for, data-field, data-row-index, data-column-index 等。

    EN: Generate a semantic DOM structure fully aligned with Word HTML.
    Standard attribute set: data-schema-version, data-target-schema, data-section-type,
    data-collection, data-label-for, data-field, data-row-index, data-column-index, etc.

    JA: Word HTML と完全に揃ったセマンティックな DOM 構造を生成する。
    標準の属性セット：data-schema-version、data-target-schema、data-section-type、
    data-collection、data-label-for、data-field、data-row-index、data-column-index など。
    """
    filename = src_p.name
    multi = len(sheets) > 1
    src_hash = source_path_hash(str(src_p))

    # 集合型 section 列表（需要 data-collection 属性）
    # EN: List of collection-type sections (need the data-collection attribute)
    # JA: コレクション型の section の一覧（data-collection 属性が必要）
    COLLECTION_SECTIONS = frozenset({
        "work_experiences", "education_list", "expected_list", "project_list",
        "certificate_list", "language_list", "skills_list", "training_list",
    })

    buf = [
        "<!DOCTYPE html>",
        '<html lang="zh-CN">',
        "<head>",
        '  <meta charset="UTF-8">',
        '  <meta name="viewport" content="width=device-width, initial-scale=1.0">',
        f"  <title>{html.escape(safe_stem(Path(filename).stem))}</title>",
        "  <style>",
        "    table {",
        "      border-collapse: collapse;",
        "      table-layout: fixed;",
        "      width: 100%;",
        "      word-break: break-word;",
        "      font-family: system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;",
        "      font-size: 13px;",
        "      margin-bottom: 16px;",
        "    }",
        "    td, th {",
        "      border: 1px solid #aaa !important;",
        "      padding: 6px 8px;",
        "      vertical-align: middle;",
        "      empty-cells: show !important;",
        "      min-height: 24px;",
        "    }",
        "    header.resume-source-header {",
        "      border-bottom: 1px dashed #ccc;",
        "      padding-bottom: 8px;",
        "      margin-bottom: 12px;",
        "      font-size: 12px;",
        "      color: #666;",
        "    }",
        "    section.resume-section {",
        "      margin-bottom: 20px;",
        "    }",
        "  </style>",
        "</head>",
        "<body>",
        # 文档级根容器（对齐 Word HTML 标准）
        # EN: Document-level root container (aligned with the Word HTML standard)
        # JA: 文書レベルのルートコンテナ（Word HTML の標準に合わせる）
        f'  <article class="resume-article"'
        f' data-schema-version="{SCHEMA_VERSION}"'
        f' data-target-schema="complete-v1"'
        f' data-generator-version="{GENERATOR_VERSION}"'
        f' data-converter="xls-grid"'
        f' data-source-hash="{src_hash}">',
        # 源文件元数据头部
        # EN: Source file metadata header
        # JA: ソースファイルのメタデータヘッダー
        '    <header class="resume-source-header" data-role="source-metadata">',
        f'      <h1 class="document-title" data-field="document-title">{html.escape(safe_stem(Path(filename).stem))}</h1>',
        f'      <p data-field="source-path"><b>源文件路径：</b>{html.escape(str(src_p))}</p>',
        f'      <p data-field="download-date"><b>简历落地时间：</b>{html.escape(download_date)}</p>',
    ]
    # 可选联系方式元数据
    # EN: Optional contact metadata
    # JA: 任意の連絡先メタデータ
    if phone:
        buf.append(f'      <p data-field="phone"><b>联系电话：</b>{html.escape(phone)}</p>')
    if email:
        buf.append(f'      <p data-field="email"><b>电子邮箱：</b>{html.escape(email)}</p>')
    buf.extend([
        "    </header>",
        # 正文容器
        # EN: Body container
        # JA: 本文コンテナ
        '    <main class="document-content" data-role="document-content" data-resume-count="1">',
        # 候选人 Resume Record 包裹
        # EN: Candidate Resume Record wrapper
        # JA: 候補者の Resume Record ラッパー
        '      <article class="resume-record" data-role="resume" data-resume-index="1">',
    ])

    section_index = 0
    current_section = "base_info"
    table_index = 0

    # 开启第一个 section
    # EN: Open the first section
    # JA: 最初の section を開く
    section_index += 1
    collection_attr = f' data-collection="{current_section}"' if current_section in COLLECTION_SECTIONS else ""
    buf.append(
        f'        <section class="resume-section"'
        f' data-section-index="{section_index}"'
        f' data-section-type="{current_section}"'
        f'{collection_attr}'
        f' aria-labelledby="section-{section_index}-heading">'
    )

    for sheet_name, grid in sheets:
        if not grid or not grid[0]:
            continue

        # 空表格过滤
        # EN: Filter empty tables
        # JA: 空の表を除外する
        if _is_empty_grid(grid):
            continue

        # 1. 优先强力合并年月经历时间段、出生年月日年龄及数值单位碎片
        # EN: 1. First aggressively merge fragments of year-month experience periods, birth date/age and number units
        # JA: 1. まず年月の経歴期間・生年月日と年齢・数値の単位の断片を積極的に結合する
        grid = _merge_year_month_fragments(grid)

        # 2. 过滤空模版行和空记录块
        # EN: 2. Filter empty template rows and empty record blocks
        # JA: 2. 空のテンプレート行と空のレコードブロックを除外する
        grid = _filter_empty_template_rows(grid)
        if not grid:
            continue



        # 合并年月碎片列
        # EN: Merge year-month fragment columns
        # JA: 年月の断片の列を結合する
        grid = _merge_year_month_fragments(grid)

        if multi and sheet_name:
            buf.append(f"          <h3>Sheet: {html.escape(sheet_name)}</h3>")

        # 2D 网格物理坐标语义标注（智能识别竖着读与横着读模式）
        # EN: Semantic annotation by physical coordinates in the 2D grid (smart detection of vertical vs. horizontal reading)
        # JA: 2D グリッドの物理座標による意味付け（縦読み・横読みを自動判別）
        grid_semantic_map = _annotate_grid_semantics(grid)

        table_index += 1
        buf.append(f'          <table data-table-index="{table_index}">')
        buf.append("            <tbody>")

        for r_idx, row in enumerate(grid):
            row_str = "".join(c.val for c in row if c.val and not c.is_covered).strip()
            sec_type = detect_section_type(row_str)
            if sec_type and sec_type != current_section:
                # 关闭当前表格和 section
                # EN: Close the current table and section
                # JA: 現在の表と section を閉じる
                buf.append("            </tbody>")
                buf.append("          </table>")
                buf.append("        </section>")
                # 开启新 section
                # EN: Open a new section
                # JA: 新しい section を開く
                current_section = sec_type
                section_index += 1
                collection_attr = f' data-collection="{current_section}"' if current_section in COLLECTION_SECTIONS else ""
                buf.append(
                    f'        <section class="resume-section"'
                    f' data-section-index="{section_index}"'
                    f' data-section-type="{current_section}"'
                    f'{collection_attr}'
                    f' aria-labelledby="section-{section_index}-heading">'
                )
                # 将检测到的章节标题行输出为 h2
                # EN: Output detected section heading rows as h2
                # JA: 検出した章見出しの行を h2 として出力する
                buf.append(
                    f'          <h2 id="section-{section_index}-heading"'
                    f' data-section-type="{current_section}">{html.escape(row_str)}</h2>'
                )
                table_index += 1
                buf.append(f'          <table data-table-index="{table_index}">')
                buf.append("            <tbody>")
                continue  # 跳过标题行本身的表格渲染
                # EN: Skip table rendering of the heading row itself
                # JA: 見出し行そのものの表の描画はスキップする

            buf.append(f'              <tr data-row-index="{r_idx + 1}">')
            c = 0
            num_cols = len(row)
            col_render_idx = 0

            while c < num_cols:
                cell = row[c]
                if cell.is_covered:
                    c += 1
                    continue

                col_render_idx += 1
                if cell.val or cell.rs > 1 or cell.cs > 1:
                    attrs = f' data-column-index="{col_render_idx}"'
                    if cell.rs > 1:
                        attrs += f' rowspan="{cell.rs}"'
                    if cell.cs > 1:
                        attrs += f' colspan="{cell.cs}"'

                    # 应用 2D 语义引擎生成的精确属性（包含竖着读、横着读模式）
                    # EN: Apply the precise attributes produced by the 2D semantic engine (including vertical and horizontal reading)
                    # JA: 2D 意味エンジンが生成した正確な属性を適用する（縦読み・横読みを含む）
                    cell_key = (r_idx, c)
                    if cell_key in grid_semantic_map:
                        for k, v in grid_semantic_map[cell_key].items():
                            attrs += f' {k}="{html.escape(v)}"'

                    buf.append(f"                <td{attrs}>{html.escape(cell.val)}</td>")
                    c += 1
                else:
                    blank_k = 0
                    temp_c = c
                    while temp_c < num_cols:
                        tc = row[temp_c]
                        if not tc.is_covered and not tc.val and tc.rs == 1 and tc.cs == 1:
                            blank_k += 1
                            temp_c += 1
                        else:
                            break
                    attrs = f' data-column-index="{col_render_idx}"'
                    if blank_k > 1:
                        attrs += f' colspan="{blank_k}"'
                    buf.append(f"                <td{attrs}></td>")
                    c += blank_k

            buf.append("              </tr>")


        buf.append("            </tbody>")
        buf.append("          </table>")

    buf.extend([
        "        </section>",
        "      </article>",
        "    </main>",
        "  </article>",
        "</body>",
        "</html>",
    ])

    return "\n".join(buf)



def build_excel_table_fragment(
    sheets: list[tuple[str, list[list[GridCell]]]],
) -> str:
    """Render Excel's physical grid as a safe fragment for the Word DOM pipeline."""
    multi = len(sheets) > 1
    buf: list[str] = []
    for sheet_name, grid in sheets:
        if not grid or not grid[0]:
            continue
        if multi and sheet_name:
            buf.append(f"<h2>{html.escape(sheet_name)}</h2>")
        buf.extend(["<table>", "<tbody>"])
        for row in grid:
            buf.append("<tr>")
            column = 0
            while column < len(row):
                cell = row[column]
                if cell.is_covered:
                    column += 1
                    continue
                if cell.val or cell.rs > 1 or cell.cs > 1:
                    attrs = ""
                    if cell.rs > 1:
                        attrs += f' rowspan="{cell.rs}"'
                    if cell.cs > 1:
                        attrs += f' colspan="{cell.cs}"'
                    buf.append(f"<td{attrs}>{html.escape(cell.val)}</td>")
                    column += 1
                    continue

                blank_count = 0
                while column + blank_count < len(row):
                    candidate = row[column + blank_count]
                    if candidate.is_covered or candidate.val or candidate.rs != 1 or candidate.cs != 1:
                        break
                    blank_count += 1
                attrs = f' colspan="{blank_count}"' if blank_count > 1 else ""
                buf.append(f"<td{attrs}></td>")
                column += max(blank_count, 1)
            buf.append("</tr>")
        buf.extend(["</tbody>", "</table>"])
    return "\n".join(buf)


def enhance_excel_dom_annotations(content: str) -> str:
    """Correct wide Excel header tables after the shared Word DOM transformation.

    Word documents commonly use horizontal ``label | value`` pairs. Excel exports
    also use ``header row / value row`` tables; treating those headers horizontally
    binds fields to the next header. This pass detects wide header rows and binds
    each recognized header to the cell directly below it instead.
    """
    soup = BeautifulSoup(content, "html.parser")
    article = soup.find("article", attrs={"data-schema-version": SCHEMA_VERSION})
    if article is not None:
        article["data-xls-rule-version"] = XLS_RULE_VERSION

    def direct_cells(row: Any) -> list[Any]:
        return row.find_all(["th", "td"], recursive=False)

    def ranged_cells(row: Any) -> list[tuple[Any, int, int]]:
        result: list[tuple[Any, int, int]] = []
        position = 0
        for cell in direct_cells(row):
            try:
                colspan = max(1, int(cell.get("colspan") or 1))
            except (TypeError, ValueError):
                colspan = 1
            result.append((cell, position, position + colspan - 1))
            position += colspan
        return result

    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        for row_index, row in enumerate(rows[:-1]):
            # Only the first row of a table can be treated as a column-header row.
            # Later wide rows are frequently ordinary ``label | value`` profile rows.
            if row_index != 0:
                continue
            current = ranged_cells(row)
            if len(current) < 6:
                continue
            section = row.find_parent("section")
            scope = str(section.get("data-section-type") or "document-body") if section else "document-body"
            labels: list[tuple[Any, int, int, str, str]] = []
            for cell, start, end in current:
                label = cell.get_text(" ", strip=True).rstrip("：:")
                field = word_html.canonical_field_for(label, scope) or detect_field_name(label)
                if field:
                    labels.append((cell, start, end, field, label))
            # Wide header rows need at least two known fields; ordinary key/value
            # rows remain under the shared Word horizontal-pair rules.
            if len(labels) < 2:
                continue

            below = ranged_cells(rows[row_index + 1])
            for cell, _start, _end in current:
                cell.attrs.pop("data-field", None)
                cell.attrs.pop("label", None)
                cell.attrs.pop("data-label-for", None)
            for label_cell, start, end, field, label in labels:
                midpoint = (start + end) / 2
                value_cell = next(
                    (cell for cell, value_start, value_end in below if value_start <= midpoint <= value_end),
                    None,
                )
                if value_cell is None:
                    continue
                value = value_cell.get_text(" ", strip=True)
                if not value or detect_field_name(value):
                    continue
                label_cell["data-label-for"] = field
                value_cell["data-field"] = field
                value_cell["label"] = label

    # Some Japanese/Chinese Excel forms place a field label and its real value
    # on consecutive rows, while the cell immediately to the right contains a
    # placeholder (e.g. 姓名 -> 拼音 -> 嵇筱昳, 手机 -> 邮件地址 -> number).
    # The shared horizontal binder used to keep the placeholder as the value.
    # Rebind only these unmistakable placeholders to the vertically aligned
    # value cell; ordinary, already-correct bindings remain untouched.
    placeholder_values = {
        "full_name": {"拼音", "フリガナ", "pin yin", "姓名", "氏名", "name"},
        "gender": {"性别", "性別", "婚姻状态", "婚姻状況", "gender"},
        "household_registration": {"戸口", "户口", "民族", "nation"},
        "weight_kg": {"民族", "nation"},
        "phone": {"邮件地址", "メールアドレス", "e-mail", "email"},
        "email": {"邮件地址", "メールアドレス", "e-mail", "email"},
    }

    def physical_ranges(row: Any) -> list[tuple[Any, int, int]]:
        result: list[tuple[Any, int, int]] = []
        position = 0
        for cell in row.find_all(["td", "th"], recursive=False):
            try:
                span = max(1, int(cell.get("colspan") or 1))
            except (TypeError, ValueError):
                span = 1
            result.append((cell, position, position + span - 1))
            position += span
        return result

    for node in soup.find_all(attrs={"data-field": True}):
        field = str(node.get("data-field") or "")
        value = re.sub(r"\s+", " ", node.get_text(" ", strip=True)).strip().casefold()
        if field not in placeholder_values or value not in placeholder_values[field]:
            continue
        cell = node if node.name in {"td", "th"} else node.find_parent(["td", "th"])
        row = cell.find_parent("tr") if cell else None
        table = row.find_parent("table") if row else None
        if row is None or table is None:
            continue
        current_ranges = physical_ranges(row)
        current = next((item for item in current_ranges if item[0] is cell), None)
        if current is None:
            continue
        rows = table.find_all("tr")
        try:
            row_index = rows.index(row)
        except ValueError:
            continue
        if row_index + 1 >= len(rows):
            continue
        next_ranges = physical_ranges(rows[row_index + 1])
        target = None
        if field == "full_name":
            # Bilingual forms often use ``姓名 | 拼音`` as the label row and
            # ``真实姓名 | Ji XiaoDie`` as the value row.  The placeholder is
            # one column to the right of the actual name.
            target = next(
                (item for item in reversed(next_ranges)
                 if item[2] <= current[1] and item[0].get_text(" ", strip=True)),
                None,
            )
        if target is None:
            target = next(
                (item for item in next_ranges if item[2] >= current[1] and item[1] <= current[2]
                 and item[0].get_text(" ", strip=True)),
                None,
            )
        if target is None:
            continue
        target_cell = target[0]
        target_cell["data-field"] = field
        target_cell["label"] = node.get("label") or field
        node.attrs.pop("data-field", None)
        node.attrs.pop("label", None)

    # Explicit bilingual name-row correction.  This is more reliable than
    # column geometry when the form has ``姓名 | 拼音`` headers followed by
    # ``真实姓名 | 拼音值``.
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        for index, row in enumerate(rows[:-1]):
            labels = [cell.get_text(" ", strip=True) for cell in row.find_all(["td", "th"], recursive=False)]
            if not any(value in {"姓名", "氏名"} for value in labels) or not any(value in {"拼音", "フリガナ", "Pin Yin"} for value in labels):
                continue
            value_cells = [cell for cell in rows[index + 1].find_all(["td", "th"], recursive=False) if cell.get_text(" ", strip=True)]
            if not value_cells:
                continue
            target = value_cells[0]
            for old in table.find_all(attrs={"data-field": "full_name"}):
                old.attrs.pop("data-field", None)
                old.attrs.pop("label", None)
            target["data-field"] = "full_name"
            target["label"] = "姓名"
            break
    return str(soup)


def annotate_excel_language_layers(content: str) -> str:
    """Add two-level language markers for bilingual Excel resumes.

    Level 1 is a language-variant wrapper (``data-language-level=resume``),
    and level 2 is copied onto every semantic section inside that variant
    (``data-language-level=section``).  Sheet headings such as ``中文`` /
    ``日本語`` and ``简历模板`` / ``エントリシート`` define boundaries; later
    sections inherit the current variant.
    """
    soup = BeautifulSoup(content, "html.parser")

    def marker_language(text: str) -> str:
        compact = re.sub(r"\s+", "", text or "")
        if re.search(r"日本語|日本文|日文|日语简历|履歴書|エントリ|職歴|学歴|語学", compact, re.I):
            return "jp"
        if re.search(r"英文|英文简历|english|personalinformation|education|workexperience", compact, re.I):
            return "en"
        if re.search(r"中文|中文简历|简历|工作经历|学历|语言及技能|自我介绍", compact, re.I):
            return "zh"
        return ""

    for record in soup.select('article[data-role="resume"]'):
        sections = record.find_all("section", recursive=False)
        if not sections or record.find(attrs={"data-language-level": True}, recursive=False):
            continue

        groups: list[tuple[str, list[Any]]] = []
        current_code = ""
        current_sections: list[Any] = []
        for section in sections:
            heading = section.find(["h1", "h2", "h3", "h4", "h5", "h6"], recursive=False)
            # Only a document-body heading starts a new language variant.
            # Section headings such as ``◆学歴`` / ``◆職歴`` contain Japanese
            # characters even inside a Chinese variant and must inherit the
            # current language instead of creating false extra variants.
            marker = (
                marker_language(heading.get_text(" ", strip=True))
                if heading and section.get("data-section-type") == "document-body"
                else ""
            )
            if marker and marker != current_code and current_sections:
                groups.append((current_code or marker, current_sections))
                current_sections = []
            if marker:
                current_code = marker
            if not current_code:
                current_code = marker_language(section.get_text(" ", strip=True)) or "zh"
            current_sections.append(section)
        if current_sections:
            groups.append((current_code or "zh", current_sections))

        if len(groups) <= 1:
            code, only_sections = groups[0]
            for section in only_sections:
                section["data-language-level"] = "section"
                section["data-language"] = code
                section["data-language-code"] = code
                section["data-language-index"] = "1"
            record["data-language-count"] = "1"
            continue

        for variant_index, (code, variant_sections) in enumerate(groups, 1):
            wrapper = soup.new_tag("div")
            wrapper["class"] = "resume-language-variant"
            wrapper["data-language-level"] = "resume"
            wrapper["data-language"] = code
            wrapper["data-language-code"] = code
            wrapper["data-language-index"] = str(variant_index)
            variant_sections[0].insert_before(wrapper)
            for section in variant_sections:
                section["data-language-level"] = "section"
                section["data-language"] = code
                section["data-language-code"] = code
                section["data-language-index"] = str(variant_index)
                wrapper.append(section.extract())
        record["data-language-count"] = str(len(groups))

        # The English sheet can contain a second table whose first row is a
        # company/date row.  Generic table heuristics occasionally label that
        # table as education because the industry value contains the word
        # “education”.  The row shape is unambiguous: reclassify it as work.
        for section in record.find_all("section"):
            if str(section.get("data-language-code") or "") != "en":
                continue
            if str(section.get("data-section-type") or "") != "education_list":
                continue
            text = section.get_text(" ", strip=True)
            if re.search(r"Company|Job\s+Description|Reason\s+of\s+Dimission", text, re.I) and re.search(r"(?:19|20)\d{2}\s*\d{1,2}", text):
                section["data-section-type"] = "work_experiences"
                section["data-collection"] = "work_experiences"

    return str(soup)


LANGUAGE_CODE_MAP = {
    "中": "zh", "英": "en", "日": "jp", "德": "de",
    "法": "fr", "韩": "ko", "俄": "ru",
}


def classify_excel_html_language(content: str) -> tuple[str, list[str], dict[str, Any], str]:
    """Classify an XLS semantic document using the same detector as docs.

    The folder name is deliberately the docs convention (中文/日文/中日文/
    英文...), while the HTML receives machine-readable ISO-ish codes for later
    DOM extraction.
    """
    soup = BeautifulSoup(content, "html.parser")
    main = soup.find("main", attrs={"data-role": "document-content"}) or soup
    text = re.sub(r"\s+", " ", main.get_text(" ", strip=True)).strip()
    html_node = soup.find("html")
    html_lang = str((html_node or {}).get("lang") or "").casefold()
    languages, evidence = detect_languages(text, html_lang)
    codes = [LANGUAGE_CODE_MAP.get(item, item) for item in languages]
    # The shared detector can call a Japanese XLS "English" when it sees
    # Latin email/name tokens.  Japanese keyword evidence with no English
    # semantic headings is a stronger signal for the resume language layer.
    if (
        "en" in codes
        and int(evidence.get("en_keywords", 0) or 0) == 0
        and int(evidence.get("ja_keywords", 0) or 0) >= 3
        and len(re.findall(r"[ぁ-ゖァ-ヺ]", text)) >= 20
    ):
        codes = ["jp" if code == "en" else code for code in codes]
        if "jp" not in codes:
            codes.append("jp")
    # Re-score language variants from semantic *values*, not template labels.
    # A Japanese-labelled sheet with Chinese school/work values is still one
    # Chinese resume (徐伯佾); genuine bilingual sheets have distinct value
    # layers and retain both codes.
    value_codes: set[str] = set()
    core_types = {"document-body", "base_info", "education_list", "work_experiences", "expected_list", "self_evaluation"}
    for section in soup.find_all("section"):
        kind = str(section.get("data-section-type") or section.get("data-collection") or "").casefold()
        if kind not in core_types:
            continue
        values = " ".join(
            node.get_text(" ", strip=True)
            for node in section.find_all(attrs={"data-field": True})
            if not node.find(attrs={"data-field": True})
        )
        if len(values) < 20:
            continue
        kana = len(re.findall(r"[ぁ-ゖァ-ヺ]", values))
        han = len(re.findall(r"[\u4e00-\u9fff]", values))
        latin = len(re.findall(r"\b[A-Za-z]{2,}\b", values))
        if kana >= 4 and kana >= han * 0.08:
            value_codes.add("jp")
        elif han >= 8 and (
            any(marker in values for marker in ("中文", "姓名", "工作经历", "教育经历", "学校", "公司", "工作内容", "学历", "离职理由"))
            or (kana == 0 and len(values) > 100)
        ):
            value_codes.add("zh")
        elif latin >= 5:
            value_codes.add("en")
    if value_codes:
        ordered = [code for code in ("zh", "jp", "en") if code in value_codes]
        codes = ordered or codes
    # When every core section is explicitly tagged as Japanese, preserve a
    # single Japanese resume even if Han-heavy names/addresses make the raw
    # script scorer look bilingual (e.g. Japanese 履歴書 with Chinese school
    # names).  Distinct zh+jp core layers remain bilingual.
    core_section_codes = {
        str(section.get("data-language-code") or section.get("data-language") or "").casefold()
        for section in soup.find_all("section")
        if str(section.get("data-section-type") or section.get("data-collection") or "").casefold() in core_types
        and str(section.get("data-language-code") or section.get("data-language") or "").casefold() in {"zh", "jp", "ja", "en"}
    }
    if core_section_codes == {"jp"}:
        codes = ["jp"]
    # Re-apply the detector correction after semantic value re-scoring, which
    # can otherwise reintroduce ``en`` from Latin product/email tokens.
    if (
        "en" in codes
        and "jp" not in codes
        and int(evidence.get("en_keywords", 0) or 0) == 0
        and int(evidence.get("ja_keywords", 0) or 0) >= 3
        and len(re.findall(r"[ぁ-ゖァ-ヺ]", text)) >= 20
    ):
        codes = ["jp" if code == "en" else code for code in codes]
    folder = folder_for([{"zh": "中", "jp": "日", "en": "英"}.get(code, code) for code in codes])

    # Keep the classification on the resume article as well as in the map.
    # This makes a standalone HTML self-describing and avoids re-running the
    # classifier when downstream consumers only have the DOM.
    for article in soup.select('article[data-role="resume"]'):
        article["data-language-folder"] = folder
        article["data-language-variants"] = ",".join(codes) or "unknown"
        article["data-language-count"] = str(max(1, len(codes)))
        if len(codes) == 1:
            article["data-language"] = codes[0]
            article["data-language-code"] = codes[0]
        else:
            article.attrs.pop("data-language", None)
            article.attrs.pop("data-language-code", None)
    return folder, codes, evidence, str(soup)


COLLECTION_DATE_RANGE_RE = re.compile(
    r"^\s*(?P<start>(?:19|20)\d{2}(?:(?:[./-]\d{1,2}(?:[./-]\d{1,2})?)|(?:\s*年\s*\d{1,2}\s*月(?:\s*\d{1,2}\s*日)?)|(?:\s+\d{1,2}))?)"
    r"\s*(?:[-—–~～〜至到]|から)\s*"
    r"(?P<end>(?:(?:19|20)\d{2}(?:(?:[./-]\d{1,2}(?:[./-]\d{1,2})?)|(?:(?:\s*年|\s*至)\s*\d{1,2}\s*月(?:\s*\d{1,2}\s*日)?)|(?:\s+\d{1,2}))?)|至今|现在|目前|現在|在职中|在職中|在职|在職|Present|Current)"
    r"\s*(?P<rest>.*)$",
    re.I,
)

FULLWIDTH_DIGITS = str.maketrans("０１２３４５６７８９", "0123456789")


def normalize_collection_text(value: str) -> str:
    """Normalize full-width dates and common Excel whitespace before matching."""
    return str(value or "").translate(FULLWIDTH_DIGITS).replace("　", " ")
COLLECTION_SINGLE_DATE_RE = re.compile(
    r"^(?:19|20)\d{2}(?:(?:[./-]\d{1,2}(?:[./-]\d{1,2})?)|(?:(?:\s*年|\s*至)(?:\s*\d{1,2}\s*月(?:\s*\d{1,2}\s*日?)?(?:末|左右)?)?)|(?:\s+\d{1,2}))?$",
    re.I,
)

COLLECTION_OPEN_END_RE = re.compile(r"^(?:至今|现在|目前|現在|今まで|在职中|在職中|在职|在職|Present|Current)$", re.I)


def bind_excel_collection_records(content: str) -> str:
    """Bind compact and structured education/work tables to explicit records."""
    soup = BeautifulSoup(content, "html.parser")

    def row_text(row: Any) -> str:
        return re.sub(r"\s+", " ", normalize_collection_text(row.get_text(" ", strip=True))).strip()

    def value_cells(row: Any) -> list[Any]:
        return [
            cell for cell in row.find_all(["td", "th"], recursive=False)
            if cell.get_text(" ", strip=True)
        ]

    def ranged_cells(row: Any) -> list[tuple[Any, int, int]]:
        result: list[tuple[Any, int, int]] = []
        position = 0
        for cell in row.find_all(["td", "th"], recursive=False):
            try:
                span = max(1, int(cell.get("colspan") or 1))
            except (TypeError, ValueError):
                span = 1
            result.append((cell, position, position + span - 1))
            position += span
        return result

    def field_span(field: str, value: str, label: str) -> Any:
        node = soup.new_tag("span")
        node["data-field"] = field
        node["label"] = label
        if value:
            node.string = value
        else:
            node["data-missing"] = "true"
        return node

    def marker_date(row: Any, marker: str) -> tuple[Any, str] | None:
        cells = row.find_all(["td", "th"], recursive=False)
        marker_index = next(
            (index for index, cell in enumerate(cells)
             if re.sub(r"\s+", "", cell.get_text(" ", strip=True)) == marker),
            -1,
        )
        if marker_index < 0:
            return None
        for cell in cells[marker_index + 1:]:
            value = re.sub(r"\s+", "", normalize_collection_text(cell.get_text(" ", strip=True)))
            if COLLECTION_SINGLE_DATE_RE.fullmatch(value) or COLLECTION_OPEN_END_RE.fullmatch(value):
                return cell, value
        return None

    # Repeated wide employment blocks use a header row followed by a value row:
    # ``入社年月 | 退社年月 | 会社名 ...``.  Date-range regexes alone miss
    # open-ended jobs and can merge later jobs into the previous record.  Treat
    # every complete repeated header as an explicit record boundary.
    for section in soup.select('section[data-collection="work_experiences"]'):
        for table in section.find_all("table"):
            rows = table.find_all("tr")

            def work_header_fields(row: Any) -> set[str]:
                return {
                    word_html.canonical_field_for(
                        cell.get_text(" ", strip=True).rstrip("：:"), "work_experiences"
                    )
                    for cell in row.find_all(["td", "th"], recursive=False)
                }

            header_indexes = [
                index
                for index, row in enumerate(rows)
                if {"position_start", "position_resigned", "company_name"}.issubset(
                    work_header_fields(row)
                )
            ]
            if len(header_indexes) < 2:
                continue

            groups = [
                (start, header_indexes[index + 1] if index + 1 < len(header_indexes) else len(rows))
                for index, start in enumerate(header_indexes)
            ]
            prefix_rows = rows[:header_indexes[0]]
            for child in list(table.find_all(["thead", "tbody", "tfoot", "tr"], recursive=False)):
                child.extract()
            if prefix_rows:
                prefix_body = soup.new_tag("tbody")
                prefix_body["data-role"] = "collection-header"
                for row in prefix_rows:
                    prefix_body.append(row.extract())
                table.append(prefix_body)

            for record_index, (start, end) in enumerate(groups, 1):
                group_rows = rows[start:end]
                record_body = soup.new_tag("tbody")
                record_body["data-record-type"] = "work_experience"
                record_body["data-record-index"] = str(record_index)

                for row_index, header_row in enumerate(group_rows[:-1]):
                    labels: list[tuple[Any, int, int, str, str]] = []
                    for cell, cell_start, cell_end in ranged_cells(header_row):
                        label = cell.get_text(" ", strip=True).rstrip("：:")
                        field = word_html.canonical_field_for(label, "work_experiences")
                        if field:
                            labels.append((cell, cell_start, cell_end, field, label))
                    if not labels:
                        continue

                    below_row = group_rows[row_index + 1]
                    below = ranged_cells(below_row)
                    if len(labels) >= 2:
                        assignments: list[tuple[Any, str, Any, str]] = []
                        for label_cell, cell_start, cell_end, field, label in labels:
                            midpoint = (cell_start + cell_end) / 2
                            value_cell = next(
                                (
                                    cell
                                    for cell, value_start, value_end in below
                                    if value_start <= midpoint <= value_end
                                ),
                                None,
                            )
                            if value_cell is None or not value_cell.get_text(" ", strip=True):
                                continue
                            assignments.append((label_cell, field, value_cell, label))

                        date_assignments = {
                            field: (label_cell, value_cell, label)
                            for label_cell, field, value_cell, label in assignments
                            if field in {"position_start", "position_resigned"}
                        }
                        combined_date_cell = None
                        if {"position_start", "position_resigned"}.issubset(date_assignments):
                            start_cell = date_assignments["position_start"][1]
                            end_cell = date_assignments["position_resigned"][1]
                            if start_cell is end_cell:
                                date_match = COLLECTION_DATE_RANGE_RE.match(
                                    normalize_collection_text(start_cell.get_text(" ", strip=True))
                                )
                                if date_match:
                                    combined_date_cell = start_cell
                                    start_cell.clear()
                                    start_cell.append(field_span(
                                        "position_start", date_match.group("start"), "开始时间"
                                    ))
                                    start_cell.append(" ～ ")
                                    start_cell.append(field_span(
                                        "position_resigned", date_match.group("end"), "结束时间"
                                    ))

                        for label_cell, field, value_cell, label in assignments:
                            label_cell.attrs.pop("data-field", None)
                            label_cell["data-label-for"] = field
                            if value_cell is combined_date_cell and field in {
                                "position_start", "position_resigned"
                            }:
                                continue
                            label_cell.attrs.pop("data-field", None)
                            value_cell.attrs.pop("data-label-for", None)
                            value_cell["data-field"] = field
                            value_cell["label"] = label
                    else:
                        label_cell, _cell_start, _cell_end, field, label = labels[0]
                        if field != "position_responsibilities":
                            continue
                        value_cell = next(
                            (
                                cell
                                for cell in below_row.find_all(["td", "th"], recursive=False)
                                if cell.get_text(" ", strip=True)
                            ),
                            None,
                        )
                        if value_cell is not None:
                            label_cell.attrs.pop("data-field", None)
                            label_cell["data-label-for"] = field
                            value_cell["data-field"] = field
                            value_cell["label"] = label

                for row in group_rows:
                    record_body.append(row.extract())
                table.append(record_body)

    education_fields = {
        "school_name", "school_major_name", "school_degree_type",
        "school_degree_rank", "school_education_type",
    }
    for section in soup.select('section[data-collection="education_list"]'):
        record_index = 0
        for table in section.find_all("table"):
            rows = table.find_all("tr")
            header_map: list[tuple[int, int, str, Any]] = []
            for row in rows:
                if COLLECTION_DATE_RANGE_RE.match(row_text(row)):
                    break
                candidate: list[tuple[int, int, str, Any]] = []
                for cell, start, end in ranged_cells(row):
                    label = cell.get_text(" ", strip=True).rstrip("：:")
                    field = word_html.canonical_field_for(label, "education_list")
                    if field in education_fields:
                        candidate.append((start, end, field, cell))
                if len(candidate) > len(header_map):
                    header_map = candidate

            for row in rows:
                match = COLLECTION_DATE_RANGE_RE.match(row_text(row))
                cells = value_cells(row)
                if not match:
                    continue
                record_index += 1
                row["data-record-type"] = "education"
                row["data-record-index"] = str(record_index)
                if len(cells) == 1:
                    rest = match.group("rest").strip(" |")
                    parts = [part.strip() for part in re.split(r"\s*[|｜]\s*", rest) if part.strip()]
                    school = parts[0] if parts else rest
                    major = parts[1] if len(parts) > 1 else ""
                    row.clear()
                    values = (
                        ("school_start_ym", match.group("start"), "入学时间"),
                        ("school_end_ym", match.group("end"), "毕业时间"),
                        ("school_name", school, "学校"),
                        ("school_major_name", major, "专业"),
                    )
                    for field, value, label in values:
                        cell = soup.new_tag("td")
                        cell.append(field_span(field, value, label))
                        row.append(cell)
                    continue

                # Structured education row: split the date cell and bind values
                # vertically using the nearest recognized header row.
                date_bound = False
                for cell in row.find_all(["td", "th"], recursive=False):
                    cell_match = COLLECTION_DATE_RANGE_RE.match(
                        normalize_collection_text(cell.get_text(" ", strip=True))
                    )
                    if cell_match:
                        cell.clear()
                        cell.append(field_span("school_start_ym", cell_match.group("start"), "入学时间"))
                        cell.append(" ～ ")
                        cell.append(field_span("school_end_ym", cell_match.group("end"), "毕业时间"))
                        date_bound = True
                        break
                if not date_bound:
                    date_cells = [
                        cell for cell in row.find_all(["td", "th"], recursive=False)
                        if COLLECTION_SINGLE_DATE_RE.fullmatch(
                            re.sub(r"\s+", " ", normalize_collection_text(cell.get_text(" ", strip=True)))
                        )
                    ]
                    if len(date_cells) >= 2:
                        date_cells[0]["data-field"] = "school_start_ym"
                        date_cells[0]["label"] = "入学时间"
                        date_cells[1]["data-field"] = "school_end_ym"
                        date_cells[1]["label"] = "毕业时间"
                for cell in row.find_all(["td", "th"], recursive=False):
                    if str(cell.get("data-field") or "") in education_fields:
                        cell.attrs.pop("data-field", None)
                        cell.attrs.pop("label", None)
                for start, end, field, header_cell in header_map:
                    midpoint = (start + end) / 2
                    value_cell = next(
                        (cell for cell, value_start, value_end in ranged_cells(row)
                         if value_start <= midpoint <= value_end),
                        None,
                    )
                    if value_cell is not None and value_cell.get_text(" ", strip=True):
                        header_cell["data-label-for"] = field
                        value_cell["data-field"] = field
                        value_cell["label"] = header_cell.get_text(" ", strip=True)
                if not row.find(attrs={"data-field": "school_name"}):
                    start_node = row.find(attrs={"data-field": "school_start_ym"})
                    date_cell = start_node.find_parent(["td", "th"]) if start_node else None
                    ranges = ranged_cells(row)
                    date_range = next((item for item in ranges if item[0] is date_cell), None)
                    if date_range:
                        candidate = next(
                            (item[0] for item in ranges
                             if item[1] > date_range[2] and item[0].get_text(" ", strip=True)
                             and not item[0].find(attrs={"data-field": True})),
                            None,
                        )
                        if candidate is not None:
                            school_value = candidate.get_text(" ", strip=True)
                            major_value = ""
                            split_match = re.match(r"^(.*?)([^\s]+?)(?:専攻|专业)$", school_value)
                            if split_match and split_match.group(1).strip():
                                school_value = split_match.group(1).strip()
                                major_value = split_match.group(2).strip()
                            candidate["data-field"] = "school_name"
                            candidate["label"] = "学校"
                            if major_value:
                                major_node = soup.new_tag("span")
                                major_node["data-field"] = "school_major_name"
                                major_node["label"] = "专业"
                                major_node.string = major_value
                                candidate.append(major_node)

    # Work records begin at a date-range row and continue until the next one.
    for section in soup.select('section[data-collection="work_experiences"]'):
        for table in section.find_all("table"):
            if table.find(attrs={"data-record-type": True}):
                continue
            rows = table.find_all("tr")
            starts = [index for index, row in enumerate(rows) if COLLECTION_DATE_RANGE_RE.match(row_text(row))]
            if not starts:
                continue
            groups: list[tuple[int, int]] = []
            for index, start in enumerate(starts):
                end = starts[index + 1] if index + 1 < len(starts) else len(rows)
                for boundary in range(start + 1, end):
                    section_type = detect_section_type(row_text(rows[boundary]))
                    if section_type and section_type != "work_experiences":
                        end = boundary
                        break
                groups.append((start, end))

            header_rows = rows[:starts[0]]
            for child in list(table.find_all(["tbody", "tr"], recursive=False)):
                child.extract()
            if header_rows:
                header_body = soup.new_tag("tbody")
                header_body["data-role"] = "collection-header"
                for row in header_rows:
                    header_body.append(row.extract())
                table.append(header_body)

            for record_index, (start, end) in enumerate(groups, 1):
                group_rows = rows[start:end]
                match = COLLECTION_DATE_RANGE_RE.match(row_text(group_rows[0]))
                if match is None:
                    continue
                record_body = soup.new_tag("tbody")
                record_body["data-record-type"] = "work_experience"
                record_body["data-record-index"] = str(record_index)
                compact = all(len(value_cells(row)) <= 1 for row in group_rows)
                if compact:
                    summary_row = soup.new_tag("tr")
                    rest = match.group("rest").strip(" |")
                    for field, value, label in (
                        ("position_start", match.group("start"), "开始时间"),
                        ("position_resigned", match.group("end"), "结束时间"),
                        ("company_name", rest, "公司名称"),
                    ):
                        cell = soup.new_tag("td")
                        cell.append(field_span(field, value, label))
                        summary_row.append(cell)
                    record_body.append(summary_row)
                    responsibilities = [row_text(row) for row in group_rows[1:] if row_text(row)]
                    if responsibilities:
                        detail_row = soup.new_tag("tr")
                        detail_cell = soup.new_tag("td")
                        detail_cell["colspan"] = "3"
                        detail_cell.append(field_span(
                            "position_responsibilities", "\n".join(responsibilities), "工作内容",
                        ))
                        detail_row.append(detail_cell)
                        record_body.append(detail_row)
                else:
                    # Preserve structured rows, but bind the date range explicitly.
                    first_row = group_rows[0]
                    date_bound = False
                    for cell in first_row.find_all(["td", "th"], recursive=False):
                        cell_match = COLLECTION_DATE_RANGE_RE.match(
                            normalize_collection_text(cell.get_text(" ", strip=True))
                        )
                        if cell_match:
                            cell.clear()
                            cell.append(field_span("position_start", cell_match.group("start"), "开始时间"))
                            cell.append(" ～ ")
                            cell.append(field_span("position_resigned", cell_match.group("end"), "结束时间"))
                            date_bound = True
                            break
                    if not date_bound:
                        date_cells = [
                            cell for cell in first_row.find_all(["td", "th"], recursive=False)
                            if COLLECTION_SINGLE_DATE_RE.fullmatch(
                                re.sub(r"\s+", " ", normalize_collection_text(cell.get_text(" ", strip=True)))
                            )
                        ]
                        if len(date_cells) >= 2:
                            date_cells[0]["data-field"] = "position_start"
                            date_cells[0]["label"] = "开始时间"
                            date_cells[1]["data-field"] = "position_resigned"
                            date_cells[1]["label"] = "结束时间"
                    if not first_row.find(attrs={"data-field": "company_name"}):
                        start_node = first_row.find(attrs={"data-field": "position_start"})
                        date_cell = start_node.find_parent(["td", "th"]) if start_node else None
                        ranges = ranged_cells(first_row)
                        date_range = next((item for item in ranges if item[0] is date_cell), None)
                        if date_range:
                            candidate = next(
                                (item[0] for item in ranges
                                 if item[1] > date_range[2] and item[0].get_text(" ", strip=True)
                                 and not item[0].find(attrs={"data-field": True})),
                                None,
                            )
                            if candidate is not None and candidate.get_text(" ", strip=True) not in {"公司名", "公司名称", "会社名", "その他", "（系）", "(系)"}:
                                candidate["data-field"] = "company_name"
                                candidate["label"] = "公司名称"
                    for row in group_rows:
                        record_body.append(row.extract())
                table.append(record_body)

            last_end = groups[-1][1]
            if last_end < len(rows):
                tail_body = soup.new_tag("tbody")
                tail_body["data-role"] = "collection-tail"
                for row in rows[last_end:]:
                    tail_body.append(row.extract())
                table.append(tail_body)

    # Japanese resume templates often place ``自 date`` and ``至 date`` on
    # separate rows. Group those rows explicitly as well.
    for collection, record_type, start_field, end_field in (
        ("education_list", "education", "school_start_ym", "school_end_ym"),
        ("work_experiences", "work_experience", "position_start", "position_resigned"),
    ):
        scoped_fields = education_fields if collection == "education_list" else {
            "company_name", "company_industry", "company_nature", "position", "position_dept",
            "position_responsibilities", "resigned_reason", "company_employees",
        }
        for section in soup.select(f'section[data-collection="{collection}"]'):
            for table in section.find_all("table"):
                if table.find(attrs={"data-record-type": True}):
                    continue
                rows = table.find_all("tr")
                starts = [index for index, row in enumerate(rows) if marker_date(row, "自")]
                # Blank Excel templates have the same ``自/至`` record shape
                # but no dates. Add those marker rows alongside dated starts,
                # otherwise an actual first job absorbs all later template
                # blocks into one record.
                marker_starts = [
                    index
                    for index, row in enumerate(rows)
                    if any(
                        re.sub(r"\s+", "", cell.get_text(" ", strip=True)) == "自"
                        for cell in row.find_all(["td", "th"], recursive=False)
                    )
                ]
                starts = sorted(set(starts).union(marker_starts))
                if not starts:
                    continue

                header_map: list[tuple[int, int, str, Any]] = []
                for row in rows[:starts[0]]:
                    candidate: list[tuple[int, int, str, Any]] = []
                    for cell, start, end in ranged_cells(row):
                        label = cell.get_text(" ", strip=True).rstrip("：:")
                        field = word_html.canonical_field_for(label, collection)
                        if field in scoped_fields:
                            candidate.append((start, end, field, cell))
                    if len(candidate) > len(header_map):
                        header_map = candidate

                group_starts = list(starts)
                if collection == "work_experiences":
                    adjusted: list[int] = []
                    previous_start = 0
                    for start in starts:
                        candidate = start
                        for probe in range(previous_start, start):
                            probe_cells = rows[probe].find_all(["td", "th"], recursive=False)
                            if any(
                                word_html.canonical_field_for(cell.get_text(" ", strip=True).rstrip("：:"), collection)
                                == "company_name"
                                for cell in probe_cells
                            ):
                                candidate = probe
                        adjusted.append(candidate)
                        previous_start = start + 1
                    group_starts = adjusted
                groups = [
                    (start, group_starts[index + 1] if index + 1 < len(group_starts) else len(rows))
                    for index, start in enumerate(group_starts)
                ]
                header_rows = rows[:group_starts[0]]
                for child in list(table.find_all(["tbody", "tr"], recursive=False)):
                    child.extract()
                if header_rows:
                    header_body = soup.new_tag("tbody")
                    header_body["data-role"] = "collection-header"
                    for row in header_rows:
                        header_body.append(row.extract())
                    table.append(header_body)

                for record_index, (start, end) in enumerate(groups, 1):
                    group_rows = rows[start:end]
                    record_body = soup.new_tag("tbody")
                    record_body["data-record-type"] = record_type
                    record_body["data-record-index"] = str(record_index)
                    start_row = next((row for row in group_rows if marker_date(row, "自")), None)
                    end_row = next((row for row in group_rows if marker_date(row, "至")), None)

                    def marker_value_cell(row: Any, marker: str) -> Any:
                        if row is None:
                            return None
                        cells = row.find_all(["td", "th"], recursive=False)
                        marker_index = next(
                            (
                                index
                                for index, cell in enumerate(cells)
                                if re.sub(r"\s+", "", cell.get_text(" ", strip=True)) == marker
                            ),
                            -1,
                        )
                        if marker_index < 0:
                            return None
                        return next(
                            (cell for cell in cells[marker_index + 1:] if not cell.get("data-label-for")),
                            None,
                        )

                    if start_row is None:
                        start_row = next(
                            (
                                row
                                for row in group_rows
                                if any(
                                    re.sub(r"\s+", "", cell.get_text(" ", strip=True)) == "自"
                                    for cell in row.find_all(["td", "th"], recursive=False)
                                )
                            ),
                            None,
                        )
                    if end_row is None:
                        end_row = next(
                            (
                                row
                                for row in group_rows
                                if any(
                                    re.sub(r"\s+", "", cell.get_text(" ", strip=True)) == "至"
                                    for cell in row.find_all(["td", "th"], recursive=False)
                                )
                            ),
                            None,
                        )
                    start_pair = marker_date(start_row, "自") if start_row is not None else None
                    end_pair = marker_date(end_row, "至") if end_row is not None else None
                    if start_pair:
                        start_pair[0]["data-field"] = start_field
                        start_pair[0]["label"] = "开始时间"
                    elif start_row is not None:
                        missing_start = marker_value_cell(start_row, "自")
                        if missing_start is not None:
                            missing_start.clear()
                            missing_start.append(field_span(start_field, "", "开始时间"))
                    if end_pair:
                        end_pair[0]["data-field"] = end_field
                        end_pair[0]["label"] = "结束时间"
                    elif end_row is not None:
                        missing_end = marker_value_cell(end_row, "至")
                        if missing_end is not None:
                            missing_end.clear()
                            missing_end.append(field_span(end_field, "", "结束时间"))

                    effective_header_map = header_map
                    if collection == "work_experiences":
                        local_candidates: list[tuple[int, int, str, Any]] = []
                        for candidate_row in group_rows[:3]:
                            candidate = []
                            for cell, cell_start, cell_end in ranged_cells(candidate_row):
                                label = cell.get_text(" ", strip=True).rstrip("：:")
                                field = word_html.canonical_field_for(label, collection)
                                if field in scoped_fields:
                                    candidate.append((cell_start, cell_end, field, cell))
                            if any(field == "company_name" for _, _, field, _ in candidate):
                                local_candidates = candidate
                            elif not local_candidates:
                                local_candidates = candidate
                        if local_candidates:
                            # A repeated employment block commonly has one
                            # header row for ``company_name`` and a later row
                            # with department/position labels.  Do not select
                            # the latter merely because it has more labels;
                            # otherwise the company cell is incorrectly marked
                            # as ``position``.
                            company_header = [
                                item for item in local_candidates if item[2] == "company_name"
                            ]
                            effective_header_map = company_header or local_candidates

                    for header_start, header_end, field, header_cell in effective_header_map:
                        if start_row is None:
                            continue
                        midpoint = (header_start + header_end) / 2
                        value_ranges = ranged_cells(start_row)
                        value_cell = next(
                            (cell for cell, value_start, value_end in value_ranges
                             if value_start <= midpoint <= value_end),
                            None,
                        )
                        if value_cell is None and value_ranges:
                            # Header cells can span a broad range while the
                            # actual value is narrower (for example company
                            # name 7-28 versus company value 7-17 followed by
                            # company nature at 18-20). Select the cell with
                            # the greatest physical overlap instead of losing
                            # the binding at the midpoint boundary.
                            value_cell = max(
                                value_ranges,
                                key=lambda item: max(
                                    0, min(header_end, item[2]) - max(header_start, item[1]) + 1
                                ),
                            )[0]
                        if value_cell is not None:
                            header_cell["data-label-for"] = field
                            if value_cell.get_text(" ", strip=True):
                                value_cell["data-field"] = field
                                value_cell["label"] = header_cell.get_text(" ", strip=True)
                            else:
                                value_cell.clear()
                                value_cell.append(field_span(field, "", header_cell.get_text(" ", strip=True)))

                    if collection == "education_list" and start_pair and start_row is not None:
                        start_cells = start_row.find_all(["td", "th"], recursive=False)
                        date_index = start_cells.index(start_pair[0])
                        trailing = [
                            cell for cell in start_cells[date_index + 1:]
                            if cell.get_text(" ", strip=True)
                            and not word_html.canonical_field_for(
                                cell.get_text(" ", strip=True).rstrip("：:"), collection
                            )
                        ]
                        if trailing and not start_row.find(attrs={"data-field": "school_name"}):
                            trailing[0]["data-field"] = "school_name"
                            trailing[0]["label"] = "学校"
                        if len(trailing) > 1 and not start_row.find(attrs={"data-field": "school_major_name"}):
                            trailing[1]["data-field"] = "school_major_name"
                            trailing[1]["label"] = "专业"
                    if collection == "education_list" and start_row is not None:
                        # Compact Japanese rows use one cell such as
                        # ``上海復旦大学コンピュータ専攻`` instead of separate
                        # school/major columns.  Bind that cell explicitly and
                        # split a trailing 専攻/专业 suffix when possible.
                        if not start_row.find(attrs={"data-field": "school_name"}):
                            start_node = start_row.find(attrs={"data-field": start_field})
                            date_cell = start_node.find_parent(["td", "th"]) if start_node else None
                            ranges = ranged_cells(start_row)
                            date_range = next((item for item in ranges if item[0] is date_cell), None)
                            if date_range:
                                candidate = next(
                                    (item[0] for item in ranges
                                     if item[1] > date_range[2] and item[0].get_text(" ", strip=True)
                                     and not item[0].find(attrs={"data-field": True})),
                                    None,
                                )
                                if candidate is not None:
                                    school_value = candidate.get_text(" ", strip=True)
                                    major_value = ""
                                    split_match = re.match(r"^(.*?)([^\s]+?)(?:専攻|专业)$", school_value)
                                    if split_match and split_match.group(1).strip():
                                        school_value = split_match.group(1).strip()
                                        major_value = split_match.group(2).strip()
                                    candidate["data-field"] = "school_name"
                                    candidate["label"] = "学校"
                                    if major_value:
                                        major_node = soup.new_tag("span")
                                        major_node["data-field"] = "school_major_name"
                                        major_node["label"] = "专业"
                                        major_node.string = major_value
                                        candidate.append(major_node)
                    if collection == "work_experiences" and start_row is not None:
                        # Compact Japanese blocks put the company value beside
                        # the start/end date cell without a visible 会社名 label.
                        # Bind that adjacent value explicitly so it cannot be
                        # mistaken for a position or left completely unbound.
                        for stale in group_rows:
                            for stale_node in stale.find_all(attrs={"data-field": "company_name"}):
                                if stale_node.get_text(" ", strip=True).strip() in {"公司名", "会社名", "公司名称", "その他"}:
                                    stale_node.attrs.pop("data-field", None)
                                    stale_node.attrs.pop("label", None)
                        if not start_row.find(attrs={"data-field": "company_name"}):
                            date_cell = start_pair[0] if start_pair else None
                            date_ranges = ranged_cells(start_row)
                            date_range = next((item for item in date_ranges if item[0] is date_cell), None)
                            if date_range:
                                for candidate, c_start, c_end in date_ranges:
                                    if c_start <= date_range[2]:
                                        continue
                                    candidate_value = candidate.get_text(" ", strip=True)
                                    if not candidate_value or candidate.find(attrs={"data-field": True}):
                                        continue
                                    if candidate_value.strip() in {"公司名", "会社名", "公司名称", "（系）", "(系)", "その他"}:
                                        continue
                                    candidate["data-field"] = "company_name"
                                    candidate["label"] = "公司名称"
                                    break
                    for row in group_rows:
                        record_body.append(row.extract())
                    table.append(record_body)

    # English-sheet employment rows may be classified as ``education`` by
    # the generic date-row binder before the language layer is known.  Their
    # labels are still explicit and can be safely promoted in place.
    for section in soup.find_all("section"):
        if str(section.get("data-collection") or "") not in {"work_experiences", "education_list", ""}:
            continue
        if not any(
            re.search(r"Company\s*[:：]", record.get_text(" ", strip=True), re.I)
            for record in section.find_all(attrs={"data-record-type": "education"})
        ):
            continue
        section["data-section-type"] = "work_experiences"
        section["data-collection"] = "work_experiences"
        for record in section.find_all(attrs={"data-record-type": "education"}):
            text = re.sub(r"\s+", " ", record.get_text(" ", strip=True)).strip()
            if not re.search(r"Company\s*[:：]", text, re.I):
                continue
            record["data-record-type"] = "work_experience"
            for node in record.find_all(attrs={"data-field": True}):
                field = str(node.get("data-field") or "")
                if field == "school_start_ym":
                    node["data-field"] = "position_start"
                    node["label"] = "开始时间"
                elif field == "school_end_ym":
                    node["data-field"] = "position_resigned"
                    node["label"] = "结束时间"
                value = node.get_text(" ", strip=True)
                date_match = re.fullmatch(r"((?:19|20)\d{2})\s+(\d{1,2})", value)
                if date_match:
                    node.string = f"{date_match.group(1)}年{int(date_match.group(2)):02d}月"

            patterns = (
                ("company_name", r"Company\s*[:：]\s*(.+?)(?=\s+Industry\s*[:：]|$)"),
                ("company_industry", r"Industry\s*[:：]\s*(.+?)(?=\s+Type\s+of\s+Company\s*[:：]|$)"),
                ("company_nature", r"Type\s+of\s+Company\s*[:：]\s*(.+?)(?=\s+Department\s*[:：]|$)"),
                ("position_dept", r"Department\s*[:：]\s*(.+?)(?=\s+Position\s*[:：]|$)"),
                ("position", r"Position\s*[:：]\s*(.+?)(?=\s+Company\s+Size\s*[:：]|$)"),
                ("company_employees", r"Company\s+Size\s*[:：]\s*(.+?)(?=\s+Job\s+Description|$)"),
                ("position_responsibilities", r"Job\s+Description\s*(.+?)(?=\s+Reason\s+of\s+Dimission|$)"),
                ("resigned_reason", r"Reason\s+of\s+Dimission\s*(.+)$"),
            )
            existing = {str(node.get("data-field") or "") for node in record.find_all(attrs={"data-field": True})}
            for field, pattern in patterns:
                if field in existing:
                    continue
                match = re.search(pattern, text, re.I)
                if not match:
                    continue
                value = re.sub(r"\s+", " ", match.group(1)).strip(" |")
                if value:
                    node = soup.new_tag("span")
                    node["data-field"] = field
                    node["label"] = field
                    node.string = value
                    record.append(node)

    return str(soup)


def validate_semantic_excel_html(content: str) -> dict[str, Any]:
    """Backward-compatible name backed by the canonical Word DOM validator."""
    return word_html.validate_semantic_html(content)


def excel_dom_extraction_quality(content: str) -> dict[str, Any]:
    """Report whether downstream DOM-only extraction has a stable minimum shape."""
    soup = BeautifulSoup(content, "html.parser")
    main = soup.find("main", attrs={"data-role": "document-content"})
    if main is None:
        return {"ready": False, "issues": ["missing_document_content"], "field_count": 0}
    field_nodes = main.find_all(attrs={"data-field": True})
    names = [
        node.get_text(" ", strip=True)
        for node in main.find_all(attrs={"data-field": "full_name"})
        if node.get_text(" ", strip=True)
    ]
    collection_sections = main.find_all("section", attrs={"data-collection": True})
    issues: list[str] = []
    if not names:
        issues.append("missing_full_name_field")
    if len(field_nodes) < 2 and not collection_sections:
        issues.append("insufficient_semantic_fields")
    return {
        "ready": not issues,
        "issues": issues,
        "field_count": len(field_nodes),
        "full_name_values": names,
        "collection_section_count": len(collection_sections),
    }


def is_current_excel_html(path: Path, filename: str) -> bool:
    """Only reuse an artifact produced by the current Excel classification/DOM rules."""
    if not word_html.is_current_html(path):
        return False
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    if f'data-xls-rule-version="{XLS_RULE_VERSION}"' not in content[:8192]:
        return False
    soup = BeautifulSoup(content, "html.parser")
    main = soup.find("main", attrs={"data-role": "document-content"})
    plain_text = main.get_text(" ", strip=True) if main else word_html.strip_tags(content)
    is_resume, _reason = is_resume_document(filename, plain_text)
    return is_resume and bool(validate_semantic_excel_html(content).get("valid"))


def existing_excel_record(path: Path, base: dict[str, Any], status: str) -> dict[str, Any]:
    record = word_html.existing_record(path, base, status)
    if path.parent.name not in {PASSED_DIR.name, REVIEW_DIR.name}:
        record["language_folder"] = path.parent.name
    content = path.read_text(encoding="utf-8", errors="replace")
    validation = dict(record.get("validation") or {})
    validation["extraction"] = excel_dom_extraction_quality(content)
    record["validation"] = validation
    return record


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


def html_candidates(base_dir: Path, target_name: str) -> list[Path]:
    """Return artifacts in a status directory, including language subfolders."""
    if not base_dir.exists():
        return []
    return [path for path in base_dir.rglob(target_name) if path.is_file()]


def remove_html_candidates(base_dir: Path, target_name: str) -> None:
    for path in html_candidates(base_dir, target_name):
        path.unlink(missing_ok=True)


def convert_single_excel_detailed(
    src_path_str: str,
    passed_dir: Path,
    review_dir: Path,
    filename: str,
    download_date: str,
) -> dict[str, Any]:
    src_p = Path(src_path_str).resolve()
    if not src_p.exists():
        return {"ok": False, "status": "failed", "phone": "", "email": "", "html_path": "", "error_reason": "源文件不存在"}

    try:
        sheets = read_excel_grid(src_p)
        if not sheets:
            raise RuntimeError("读取 Excel 物理网格为空")

        # 过滤抛弃全空的 sheet 表格，并统一预先执行碎片强力合并与空行擦除
        # EN: Filter out and discard completely empty sheet tables, and uniformly run fragment merging and empty-row removal beforehand
        # JA: 完全に空のシートの表を除外して破棄し、断片の結合と空行の除去を事前に一括で行う
        processed_sheets = []
        for name, grid in sheets:
            g_merged = _merge_year_month_fragments(grid)
            g_filtered = _filter_empty_template_rows(g_merged)
            if g_filtered and not _is_empty_grid(g_filtered):
                processed_sheets.append((name, g_filtered))
        sheets = processed_sheets
        if not sheets:
            raise RuntimeError("所有 Sheet 表格均为纯空内容")


        # Excel 只生成物理表格片段；后续清洗、字段标注、章节切分、多简历
        # 切分、联系方式抽取和最终 DOM 包装完全走 Word 的最新版规则。
        # EN: Excel only produces physical table fragments; the subsequent cleaning, field annotation, section splitting, multi-résumé
        #     splitting, contact extraction and final DOM wrapping all follow the latest Word rules.
        # JA: Excel 側は物理的な表の断片を生成するだけで、その後のクレンジング・フィールドの注釈付け・章の分割・複数履歴書の
        #     分割・連絡先の抽出・最終的な DOM のラップはすべて Word の最新ルールに従う。
        raw_fragment = build_excel_table_fragment(sheets)
        cleaned_fragment = word_html.clean_html_styles(raw_fragment)
        plain_text = word_html.strip_tags(cleaned_fragment)
        if len(re.sub(r"\s+", "", plain_text)) < 2:
            raise RuntimeError("清洗后正文为空")
        is_resume, classification_reason = is_resume_document(filename, plain_text)
        target_name = f"{safe_stem(Path(filename).stem)}_{source_path_hash(src_path_str)}.html"
        if not is_resume:
            for stale_dir in (passed_dir, review_dir):
                remove_html_candidates(stale_dir, target_name)
            return {
                "ok": False,
                "status": "not_resume",
                "phone": "",
                "email": "",
                "html_path": "",
                "error_reason": classification_reason,
                "converter": "non-resume-filtered",
                "generator_version": GENERATOR_VERSION,
                "schema_version": SCHEMA_VERSION,
                "resume_count": 0,
                "candidate_keys": [],
                "validation": {},
            }

        # Do not infer a candidate contact from the workbook's agency header.
        # Contacts are extracted again from the final document body below,
        # after semantic HTML has separated provenance metadata from content.
        phone, email = "", ""
        final_html = word_html.build_semantic_html(
            cleaned_fragment,
            src_p,
            download_date,
            phone,
            email,
            "xls-grid",
        )
        final_html = enhance_excel_dom_annotations(final_html)
        final_html = bind_excel_collection_records(final_html)
        final_html = annotate_excel_language_layers(final_html)
        language_folder, language_codes, language_evidence, final_html = classify_excel_html_language(final_html)
        phone, email = extract_candidate_contacts_from_html(final_html)
        final_html = set_source_contact_fields(final_html, phone, email)
        validation = validate_semantic_excel_html(final_html)
        if not validation["valid"]:
            raise RuntimeError("语义 HTML 验证失败：" + "; ".join(validation["errors"]))

        extraction = excel_dom_extraction_quality(final_html)
        validation["extraction"] = extraction
        if phone or email:
            status = "passed" if extraction["ready"] else "needs_review"
        else:
            # A workbook without an applicant phone or email is not a usable
            # resume.  It must not be promoted to JSON merely because the
            # agency/template contact appears in the source header.
            status = "not_resume"
        if not phone and not email:
            error_reason = "缺少手机号或邮箱"
        elif not extraction["ready"]:
            error_reason = "DOM 不满足稳定取数要求：" + ", ".join(extraction["issues"])
        else:
            error_reason = ""
        if status == "not_resume":
            target_name = f"{safe_stem(Path(filename).stem)}_{source_path_hash(src_path_str)}.html"
            for stale_dir in (passed_dir, review_dir):
                remove_html_candidates(stale_dir, target_name)
            return {
                "ok": False,
                "status": "not_resume",
                "phone": "",
                "email": "",
                "html_path": "",
                "error_reason": "缺少候选人手机或邮箱（已排除模板/机构联系方式）",
                "converter": "contact-gated",
                "generator_version": GENERATOR_VERSION,
                "schema_version": SCHEMA_VERSION,
                "resume_count": 0,
                "candidate_keys": [],
                "validation": validation,
            }
        target_root = passed_dir if status == "passed" else review_dir
        target_dir = target_root / language_folder
        stale_dirs = [review_dir if status == "passed" else passed_dir]
        dst_p = str(target_dir / target_name)
        word_html.atomic_write_text(Path(dst_p), final_html)

        # 清理在其他状态目录中的旧 HTML 文件
        # EN: Clean up old HTML files in other status directories
        # JA: 他の状態ディレクトリにある古い HTML ファイルを片付ける
        for s_dir in stale_dirs:
            remove_html_candidates(s_dir, target_name)

        return {
            "ok": True,
            "status": status,
            "phone": phone,
            "email": email,
            "html_path": dst_p,
            "error_reason": error_reason,
            "converter": "xls-grid",
            "generator_version": GENERATOR_VERSION,
            "schema_version": SCHEMA_VERSION,
            "language_folder": language_folder,
            "languages": language_codes,
            "language_evidence": language_evidence,
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
            "converter": "",
            "generator_version": GENERATOR_VERSION,
            "schema_version": SCHEMA_VERSION,
            "validation": {},
        }


def process_excel_files(limit: int = 0, force: bool = False):
    if not MAP_JSON_PATH.exists():
        raise FileNotFoundError(f"未找到 Excel 清单文件: {MAP_JSON_PATH}，请先运行 build_xls_conversion_map.py")

    records: list[dict] = json.loads(MAP_JSON_PATH.read_text(encoding="utf-8"))
    if limit > 0:
        records_to_process = records[:limit]
    else:
        records_to_process = records

    total = len(records_to_process)
    print(f"开始批量转换 Excel 简历，共 {total} 个记录 (limit={limit}, force={force}) ..." f" / Start batch conversion of Excel résumés, {total} records (limit={limit}, force={force}) ... / Excel 履歴書の一括変換を開始します。全 {total} レコード (limit={limit}, force={force}) ...")

    PASSED_DIR.mkdir(parents=True, exist_ok=True)
    REVIEW_DIR.mkdir(parents=True, exist_ok=True)

    counts = {"passed": 0, "needs_review": 0, "not_resume": 0, "failed": 0, "skipped_current": 0}
    converter_counts: dict[str, int] = {}
    start_time = time.monotonic()

    for seq, rec in enumerate(records_to_process, 1):
        filename = rec["filename"]
        source_path = rec["source_path"]
        download_date = rec.get("download_date", "")
        target_name = f"{safe_stem(Path(filename).stem)}_{source_path_hash(source_path)}.html"
        passed_files = html_candidates(PASSED_DIR, target_name)
        review_files = html_candidates(REVIEW_DIR, target_name)
        passed_file = next((path for path in passed_files if is_current_excel_html(path, filename)), None)
        review_file = next((path for path in review_files if is_current_excel_html(path, filename)), None)
        base_record = {
            "index": rec.get("index", seq),
            "filename": filename,
            "source_path": source_path,
            "download_date": download_date,
        }

        if not force and passed_file is not None:
            res = existing_excel_record(passed_file, base_record, "passed")
            counts["skipped_current"] += 1
        elif not force and review_file is not None:
            res = existing_excel_record(review_file, base_record, "needs_review")
            counts["skipped_current"] += 1
        else:
            res = convert_single_excel_detailed(source_path, PASSED_DIR, REVIEW_DIR, filename, download_date)

        rec.update({
            "html_path": res.get("html_path", ""),
            "phone": res.get("phone", ""),
            "email": res.get("email", ""),
            "status": res["status"],
            "error_reason": res.get("error_reason", ""),
            "converter": res.get("converter", ""),
            "generator_version": GENERATOR_VERSION,
            "schema_version": SCHEMA_VERSION,
            "language_folder": res.get("language_folder", ""),
            "languages": res.get("languages", []),
            "language_evidence": res.get("language_evidence", {}),
            "resume_count": res.get("resume_count", res.get("validation", {}).get("resume_count", 0)),
            "candidate_keys": res.get("candidate_keys", res.get("validation", {}).get("candidate_keys", [])),
            "validation": res.get("validation", {}),
        })

        counts[res["status"]] = counts.get(res["status"], 0) + 1
        converter = str(rec.get("converter") or "")
        if converter:
            converter_counts[converter] = converter_counts.get(converter, 0) + 1

        if seq % 10 == 0 or seq == total:
            elapsed = time.monotonic() - start_time
            speed = seq / elapsed if elapsed else 0
            print(
                f"进度 [{seq}/{total}] | passed={counts['passed']} | review={counts['needs_review']} | "
                f"not-resume={counts['not_resume']} | failed={counts['failed']} | "
                f"current-skip={counts['skipped_current']} | {speed:.1f} 文件/秒" f" / Progress [{seq}/{total}] | passed={counts['passed']} | review={counts['needs_review']} | not-resume={counts['not_resume']} | failed={counts['failed']} | current-skip={counts['skipped_current']} | {speed:.1f} files/s / 進捗 [{seq}/{total}] | passed={counts['passed']} | review={counts['needs_review']} | not-resume={counts['not_resume']} | failed={counts['failed']} | current-skip={counts['skipped_current']} | {speed:.1f} ファイル/秒",
                flush=True,
            )

    word_html.atomic_write_text(MAP_JSON_PATH, json.dumps(records, ensure_ascii=False, indent=2))
    summary = {
        "category": "Excel表格 (.xls, .xlsx)",
        "generator_version": GENERATOR_VERSION,
        "schema_version": SCHEMA_VERSION,
        "total_scanned_files": total,
        "passed_with_contact": counts["passed"],
        "needs_review_without_contact": counts["needs_review"],
        "not_resume_files": counts["not_resume"],
        "failed_files": counts["failed"],
        "skipped_current_files": counts["skipped_current"],
        "converter_counts": converter_counts,
        "multi_resume_source_files": sum(1 for rec in records_to_process if int(rec.get("resume_count") or 0) > 1),
        "total_resume_articles": sum(int(rec.get("resume_count") or 0) for rec in records_to_process),
        "passed_html_dir": str(PASSED_DIR),
        "review_html_dir": str(REVIEW_DIR),
        "map_json_file": str(MAP_JSON_PATH),
        "completed_at": datetime.datetime.now().astimezone().isoformat(),
    }
    word_html.atomic_write_text(
        OUTPUT_ROOT / "xls_conversion_summary.json",
        json.dumps(summary, ensure_ascii=False, indent=2),
    )
    print(f"✅ 完成转换！已同步更新清单文件: {MAP_JSON_PATH}" f" / ✅ Conversion complete! List file updated: {MAP_JSON_PATH} / ✅ 変換が完了しました！一覧ファイルを更新しました：{MAP_JSON_PATH}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="批量转换 Excel 表格为语义化 HTML 简历" " / Batch-convert Excel tables into semantic HTML résumés / Excel の表を意味付き HTML の履歴書に一括変換する")
    parser.add_argument("--limit", type=int, default=10, help="限制处理数量（默认试跑前 10 个）" " / Limit on the number processed (default: trial run of the first 10) / 処理する件数の上限（既定は先頭 10 件の試行）")
    parser.add_argument("--force", action="store_true", help="强制重新生成" " / Force regeneration / 強制的に再生成する")
    args = parser.parse_args()

    process_excel_files(limit=args.limit, force=args.force)
