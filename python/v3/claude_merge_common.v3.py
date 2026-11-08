#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
claude_merge_common.v3.py —— merge v3 公共模块：字段规范、联系方式/日期/名称规范化、语种判定、快照与 raw_text 重建。

被 claude_merge.v3.py、claude_merge_checks.v3.py、claude_merge_audit.v3.py 按文件路径加载（带点文件名不能普通 import）。
字段契约以 CONTEXT.md “2026-08-02 最新覆盖规则”与“2026-08-10 列表字段全量审计”为准。

EN: claude_merge_common.v3.py -- shared module of merge v3: field spec, normalisation of contacts/dates/names, language detection, rebuilding snapshots and raw_text.

Loaded by file path by claude_merge.v3.py, claude_merge_checks.v3.py and claude_merge_audit.v3.py (file names with dots cannot be imported normally).
The field contract follows the CONTEXT.md sections "2026-08-02 latest override rules" and "2026-08-10 full audit of list fields".

JA: claude_merge_common.v3.py —— merge v3 の共通モジュール：フィールドの仕様、連絡先・日付・名前の正規化、言語の判定、スナップショットと raw_text の再構築。

claude_merge.v3.py、claude_merge_checks.v3.py、claude_merge_audit.v3.py からファイルパスで読み込まれる（ドットを含むファイル名は通常の import ができない）。
フィールドの約束は CONTEXT.md の「2026-08-02 最新の上書きルール」と「2026-08-10 リストフィールドの全件監査」に従う。
"""

import hashlib
import importlib.util
import re
import unicodedata
from pathlib import Path

RULE_VERSION = "merge-v3.0-contact-key"

# ---------------------------------------------------------------- 字段契约
# EN: ---------------------------------------------------------------- Field contract
# JA: ---------------------------------------------------------------- フィールドの約束
BASE_FIELDS = [
    "full_name", "gender", "age", "birth_date", "birth_year", "marital_status", "children_status",
    "political_status", "height_cm", "weight_kg", "household_registration", "address", "postal_code",
    "platform_from", "platform_resume_id", "phone", "email", "city", "nationality", "pr",
]
LIST_FIELDS = {
    "expected_list": ["expected_city", "expected_position", "expected_salary", "expected_annual_salary_min",
                      "expected_annual_salary_max", "expected_industry", "expected_employment_type", "expected_start_date"],
    "work_experiences": ["company_name", "company_employees", "company_industry", "position", "position_type",
                         "position_salary", "position_dept", "position_report_to", "position_subordinate",
                         "employment_type", "annual_salary_min", "annual_salary_max", "status", "position_start",
                         "position_resigned", "resigned_reason", "position_responsibilities", "position_achievements"],
    "education_list": ["school_name", "school_major_name", "school_degree_type", "school_degree_rank",
                       "school_education_type", "school_start_ym", "school_end_ym"],
    "certificate_list": ["certificate_name", "certificate_type", "certificate_time"],
    "language_list": ["language_name", "language_level", "language_certificate", "language_certificate_time"],
    "skills_list": ["skill_name", "skill_level"],
    "training_list": ["sequence_no", "organization_name", "training_name", "start_ym", "end_ym", "certificate_name", "description"],
    "project_list": ["sequence_no", "fingerprint", "project_name", "company_or_client", "role_name", "start_ym", "end_ym",
                     "description", "responsibilities", "achievements", "keywords"],
    "communication_list": ["communicate_time", "communicate_content"],
}
LIST_ORDER = list(LIST_FIELDS.keys())
CURRENT_FIELDS = LIST_FIELDS["work_experiences"][:15]
EDU_FIELDS = LIST_FIELDS["education_list"]
EXPECTED_FIELDS = LIST_FIELDS["expected_list"]

# 历史别名 → 标准字段（仅读取时兼容）
# EN: Historical aliases → standard fields (compatibility only when reading)
# JA: 過去の別名 → 標準フィールド（読み込み時の互換のみ）
ALIASES = {
    "certificate_list": {"certificate_tpye": "certificate_type"},
    "skills_list": {"skills_name": "skill_name"},
    "project_list": {"project_start": "start_ym", "project_end": "end_ym"},
    "training_list": {"training_institution": "organization_name"},
}

DATE_FIELDS = {
    "work_experiences": ["position_start", "position_resigned"],
    "education_list": ["school_start_ym", "school_end_ym"],
    "certificate_list": ["certificate_time"],
    "language_list": ["language_certificate_time"],
    "training_list": ["start_ym", "end_ym"],
    "project_list": ["start_ym", "end_ym"],
}

PLACEHOLDERS = {"未填写", "无", "暂无", "null", "none", "n/a", "na", "-", "--", "—", "/", "未知", "不详", "保密", "空"}
PRESENT_WORDS = {"至今", "今", "现在", "目前", "present", "now", "current", "現在", "現在まで", "heute", "至今在职"}

NAME_JUNK = {"部门", "行业", "职位", "公司", "专业", "学校", "待沟通", "保密", "匿名", 
    "表格", "简历", "个人简历", "履历", "履历书", "履歴書", "职务经历书", "職務経歴書", "未知", "待确认", "待确认姓名", "姓名",
    "resume", "cv", "curriculum vitae", "name", "address", "编号", "班车", "无联系方式", "联系方式", "应聘", "应聘人员",
    "面试表", "推荐报告", "候选人", "求职者", "先生", "女士", "小姐", "同学", "胖子", "张三", "張三", "李四", "中文", "個人", "详情", "詳細", "人事", "日语", "日語", "英语", "英語",
    # 地名（只按整名比较，不作前缀，避免误伤“金山林”“安庆华”这类真名）
    # EN: Place names (compared only as whole names, not as prefixes, to avoid harming real names like "金山林", "安庆华")
    # JA: 地名（名前全体でだけ比較し、接頭辞としては使わない。「金山林」「安庆华」のような実在の氏名を誤って傷つけないため）
    "朝阳", "双鸭山", "白云", "丰台", "南阳", "哈尔滨", "石家庄", "桂林", "黄冈", "金山", "成华", "南昌", "宁德", "安庆", "海淀", "邵阳",
    "云浮", "毕节", "延边", "大兴", "内江", "孝感", "淮南", "四平", "抚州", "盐城", "威海", "通化", "枣庄", "菏泽", "临沂", "顺义", "屯昌",
    "泉州", "越秀", "渭南", "泰兴", "随州", "东城", "西城", "日照", "密云", "沧州", "闸北", "亳州", "绵阳", "佳木斯", "汕头", "台州", "昌平",
    "海外", "家庭", "会计", "会计师", "移动", "金融", "地址", "其他", "其它", "无党派",
}
PLACE_NAME_SET = {"北京", "上海", "天津", "重庆", "广州", "深圳", "杭州", "南京", "苏州", "成都", "武汉", "西安", "大连", "青岛", "厦门",
                  "宁波", "无锡", "沈阳", "长沙", "郑州", "济南", "合肥", "福州", "昆山", "东莞", "佛山", "珠海", "日本", "中国", "香港", "台湾",
                  "东京", "大阪", "个人", "本人", "猎聘网", "前程无忧", "智联招聘",
                  "河北", "山西", "辽宁", "吉林", "黑龙江", "江苏", "浙江", "安徽", "福建", "江西", "山东", "河南", "湖北", "湖南", "广东", "海南",
                  "四川", "贵州", "云南", "陕西", "甘肃", "青海", "内蒙古", "广西", "西藏", "宁夏", "新疆", "澳门", "南通", "泰州", "乐山", "芜湖",
                  "常州", "扬州", "徐州", "绍兴", "嘉兴", "温州", "黄浦", "普陀", "浦东", "闵行", "徐汇", "长宁", "静安", "虹口", "杨浦", "宝山",
                  "嘉定", "松江", "青浦", "奉贤", "崇明", "安徽芜湖", "江苏南通", "上海外国", "氏名", "宛先", "一面", "关系", "广告", "高校生",
                  "请联系", "求职信", "职业状态", "未婚", "已婚", "离异", "群众", "团员", "党员", "本科", "硕士", "博士", "大专", "中专", "高中", "基本概况", "服务业", "中文简", "日本語", "日本语", "电子", "数据分析", "品牌营销"}
NAME_JUNK_PARTS = ("简历", "履歴", "履历", "招聘", "猎聘", "前程", "智联", "51job", "面试", "推荐", "报告", "公司", "工程师",
                   "经理", "主管", "专员", "助理", "销售", "职位", "表格", "模板", "应聘",
                   "記入", "记入", "资源", "資源", "奖励", "奨励", "工程", "下载", "导出", "考虑", "略暦", "略历", "名称", "住所", "找工",
                   "部门", "市场部", "资料", "概况", "团员", "党员", "共青", "群众", "个人信息", "個人情報", "基本信息", "基本情報", "自我评价", "自己評価", "付费",
                   "性别", "性別", "翻译", "翻訳", "供应链", "汽车", "技能", "荣誉", "兼职", "顾问", "顧問", "职场", "船务", "教务", "专业", "専門",
                   "基础", "既婚", "有無", "有无", "电话", "電話", "查看", "更多", "经历", "経歴", "信息", "評語", "评语", "連絡", "联络", "最近工作", "匹配度", "流程", "学制", "跟单", "供应商", "近期", "有没", "管理", "技术", "技術", "邮编", "郵便", "語学", "语学", "経験", "经验", "标签", "頭像", "头像", "投递", "筛选", "第一批", "誕生", "诞生", "党派", "漢字", "汉字", "婚姻", "国籍", "民族", "籍贯", "出生", "学历", "学歴", "职务", "職務", "照片", "写真")

# ---------------------------------------------------------------- 基础工具
# EN: ---------------------------------------------------------------- Basic utilities
# JA: ---------------------------------------------------------------- 基本のツール
CTRL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
HAN_RE = re.compile(r"[一-鿿㐀-䶿]")
KANA_RE = re.compile(r"[ぁ-ゖァ-ヺㇰ-ㇿ]")
HANGUL_RE = re.compile(r"[가-힯]")
LATIN_RE = re.compile(r"[A-Za-zÀ-ɏ]")
GERMAN_RE = re.compile(r"[äöüÄÖÜß]|\b(Lebenslauf|Berufserfahrung|Ausbildung|Kenntnisse|Studium|Sprachen)\b")


def load_module(name: str, filename: str):
    path = Path(__file__).resolve().parent / filename
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def s(v) -> str:
    """任意值 → 去首尾空白的字符串；None → ""。

    EN: Any value → a string with surrounding whitespace removed; None → "".

    JA: 任意の値 → 前後の空白を除いた文字列。None → ""。
    """
    if v is None:
        return ""
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return str(v)
    if isinstance(v, str):
        return v.strip()
    return str(v).strip()


def clean_value(v):
    """确定性、可逆的清洗。返回 (新值, [动作])。

    EN: Deterministic, reversible cleaning. Returns (new value, [actions]).

    JA: 確定的で元に戻せるクレンジング。戻り値：(新しい値, [処理内容])。
    """
    if not isinstance(v, str):
        return v, []
    actions = []
    new = v
    if CTRL_RE.search(new):
        new = CTRL_RE.sub("", new)
        actions.append("remove_control_chars")
    if "\u00ad" in new or "\u200b" in new or "\ufeff" in new:
        new = new.replace("\u00ad", "").replace("\u200b", "").replace("\ufeff", "")
        actions.append("remove_invisible_chars")
    if re.search(r"[\u2002\u2003\u2009]", new):
        new = re.sub(r"[\u2002\u2003\u2009]", " ", new)
        actions.append("wide_space_to_space")
    if "\n" not in new and re.search(r" {2,}", new.replace("　", " ").strip()):
        new = re.sub(r"[ 　]{2,}", " ", new)
        actions.append("collapse_spaces")
    if "\u00a0" in new:
        new = new.replace("\u00a0", " ")
        actions.append("nbsp_to_space")
    stripped = new.replace("　", " ").strip()
    if stripped != new:
        new = stripped
        if new != v.strip():
            actions.append("strip_whitespace")
    if "\n" not in new and len(new) < 80 and re.search(r"^[|｜]\s*|\s*[|｜]$", new):
        new = re.sub(r"^[|｜\s]+|[|｜\s]+$", "", new)
        actions.append("strip_edge_separator")
    if new.lower() in PLACEHOLDERS:
        actions.append(f"clear_placeholder:{new}")
        new = ""
    return new, actions


PR_HEAD_RE = re.compile(r"^\s*[/／]?\s*(自我评价|个人评价|自我介绍|自我描述|自己PR|自己ＰＲ|自己紹介|Self[- ]?Evaluation|Summary)\s*[:：]?\s*(\n|\s)+", re.I)


def strip_pr_heading(v: str) -> str:
    """去掉自我评价开头的栏目标题（可重复出现，如“/自己PR 自我评价 ……”）。

    EN: Remove section headings at the start of the self-assessment (they may repeat, e.g. "/自己PR 自我评价 ……").

    JA: 自己評価の先頭にある欄の見出しを除く（繰り返し現れることがある。例：「/自己PR 自我评价 ……」）。
    """
    prev = None
    while prev != v:
        prev = v
        v = PR_HEAD_RE.sub("", v, count=1)
    return v.strip()


def norm_text(v: str) -> str:
    """比较用：全角转半角、小写、去空白与标点。

    EN: For comparison: full-width to half-width, lowercase, remove whitespace and punctuation.

    JA: 比較用：全角を半角に、小文字にし、空白と句読点を除く。
    """
    t = unicodedata.normalize("NFKC", s(v)).lower()
    return re.sub(r"[\s\W_]+", "", t)


COMPANY_SUFFIX = re.compile(r"(股份有限公司|有限责任公司|有限公司|集团|分公司|株式会社|co\.?,?\s*ltd\.?|co\.?|ltd\.?|inc\.?|corporation|corp\.?|limited|gmbh|\(中国\)|（中国）)", re.I)


def norm_entity(v: str) -> str:
    t = unicodedata.normalize("NFKC", s(v)).lower()
    t = COMPANY_SUFFIX.sub("", t)
    return re.sub(r"[\s\W_]+", "", t)


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def sha256_text(t: str) -> str:
    return hashlib.sha256(t.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------- 联系方式
# EN: ---------------------------------------------------------------- Contact details
# JA: ---------------------------------------------------------------- 連絡先
MASK_RE = re.compile(r"[*＊xX×]{3,}|\*{2,}")
EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(\.[A-Za-z0-9\-]+)*\.[A-Za-z]{2,}$")
EMAIL_FIND = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)*\.[A-Za-z]{2,}")
MOBILE_FIND = re.compile(r"(?<![\dA-Za-z_])(?:\+?86[\s\-]?)?1[3-9]\d[\s\-]?\d{4}[\s\-]?\d{4}(?![\d])")
EMAIL_PLACEHOLDER = {"xxx@xxx.com", "test@test.com", "example@example.com", "none@none.com"}
SPLIT_RE = re.compile(r"[;；,，/、|\n]+|\s{2,}")


def classify_phone(raw: str):
    """返回 (kind, normalized)。kind: mobile | intl_mobile | landline | masked | invalid | empty。

    EN: Returns (kind, normalized). kind: mobile | intl_mobile | landline | masked | invalid | empty.

    JA: 戻り値：(kind, normalized)。kind：mobile | intl_mobile | landline | masked | invalid | empty。
    """
    t = unicodedata.normalize("NFKC", s(raw))
    if not t:
        return "empty", ""
    if MASK_RE.search(t):
        return "masked", t
    plus = t.startswith("+") or t.startswith("00")
    digits = re.sub(r"\D", "", t)
    if t.startswith("00"):
        digits = digits[2:]
    if not digits:
        return "invalid", t
    # 中国手机
    # EN: Chinese mobiles
    # JA: 中国の携帯電話
    if len(digits) == 13 and digits.startswith("86") and re.fullmatch(r"1[3-9]\d{9}", digits[2:]):
        return "mobile", digits[2:]
    if len(digits) == 11 and re.fullmatch(r"1[3-9]\d{9}", digits):
        return "mobile", digits
    # 国际号码（明确带 + 或 00 前缀，且不是 +86 固话）
    # EN: International numbers (explicitly prefixed with + or 00, and not a +86 landline)
    # JA: 国際番号（明示的に + か 00 の接頭辞があり、+86 の固定電話ではないもの）
    if plus and 8 <= len(digits) <= 15 and not digits.startswith("86"):
        cc_mobile = {"81": ("7", "8", "9"), "82": ("1",), "1": None, "65": ("8", "9"), "852": ("5", "6", "9"), "886": ("9",)}
        for cc, pref in cc_mobile.items():
            if digits.startswith(cc):
                rest = digits[len(cc):].lstrip("0")
                if pref is None or rest.startswith(pref):
                    return "intl_mobile", f"+{cc}-{rest}"
        return "landline", "+" + digits
    # 固话 / 其他
    # EN: Landlines / other
    # JA: 固定電話・その他
    if 7 <= len(digits) <= 12:
        return "landline", digits
    return "invalid", t


def classify_email(raw: str):
    t = unicodedata.normalize("NFKC", s(raw)).strip().strip("<>").lower()
    t = t.replace("mailto:", "")
    if not t:
        return "empty", ""
    if MASK_RE.search(t):
        return "masked", t
    if t in EMAIL_PLACEHOLDER or not EMAIL_RE.match(t):
        return "invalid", t
    return "email", t


def split_contact_values(raw: str):
    t = s(raw)
    if not t:
        return []
    parts = [p.strip() for p in SPLIT_RE.split(t) if p and p.strip()]
    return parts or [t]


GLUED_RE = re.compile(r"^(1[3-9]\d{9})([A-Za-z0-9._%+\-]{3,}@.+)$")


def split_glued(part: str):
    """'13800000016xxx@qq.com' → ['13817665009', 'xxx@qq.com']；否则原样。

    EN: '13800000016xxx@qq.com' → ['13817665009', 'xxx@qq.com']; otherwise returned unchanged.

    JA: '13800000016xxx@qq.com' → ['13817665009', 'xxx@qq.com']。それ以外はそのまま返す。
    """
    t = unicodedata.normalize("NFKC", s(part)).strip()
    m = GLUED_RE.match(t)
    return [m.group(1), m.group(2)] if m else [part]


def contacts_from_base(base: dict):
    """从一个 base_info 中提取 [(field, kind, normalized, raw)]。手机号字段里写的邮箱、邮箱字段里写的手机号、粘连的手机+邮箱都识别。

    EN: Extract [(field, kind, normalized, raw)] from a base_info. E-mails written in the phone field, phone numbers in the e-mail field, and stuck-together phone + e-mail are all recognised.

    JA: 1 つの base_info から [(field, kind, normalized, raw)] を抽出する。電話番号のフィールドに書かれたメール、メールのフィールドに書かれた電話番号、くっついた電話番号 + メールもすべて識別する。
    """
    out = []
    for field in ("phone", "email"):
        for part0 in split_contact_values((base or {}).get(field)):
            for part in split_glued(part0):
                if "@" in part:
                    kind, val = classify_email(part)
                else:
                    kind, val = classify_phone(part)
                out.append((field, kind, val, part0))
    return out


def contacts_in_text(text: str):
    t = unicodedata.normalize("NFKC", s(text))
    mobiles = sorted({classify_phone(m)[1] for m in MOBILE_FIND.findall(t) if classify_phone(m)[0] == "mobile"})
    emails = sorted({classify_email(m)[1] for m in EMAIL_FIND.findall(t) if classify_email(m)[0] == "email"})
    return mobiles, emails


# ---------------------------------------------------------------- 日期
# EN: ---------------------------------------------------------------- Dates
# JA: ---------------------------------------------------------------- 日付
YM_RE = re.compile(r"((?:19|20)\d{2})\s*[年./\-／]\s*(\d{1,2})(?:\s*[月./\-／]\s*(\d{1,2}))?")
Y_RE = re.compile(r"^\s*((?:19|20)\d{2})\s*年?\s*$")


def parse_ym(v: str):
    """返回 (year, month, day) 或 None。只接受含年+月的写法。

    EN: Returns (year, month, day) or None. Only forms containing year + month are accepted.

    JA: 戻り値：(year, month, day) または None。年 + 月を含む書き方だけを受け入れる。
    """
    t = unicodedata.normalize("NFKC", s(v))
    m = YM_RE.search(t)
    if not m:
        m2 = re.fullmatch(r"\s*((?:19|20)\d{2})(\d{2})(\d{2})?\s*", t)
        if not m2:
            return None
        y, mo, d = int(m2.group(1)), int(m2.group(2)), int(m2.group(3) or 1)
    else:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3) or 1)
    if not (1 <= mo <= 12 and 1 <= d <= 31):
        return None
    return y, mo, d


def ym_key(v: str) -> str:
    p = parse_ym(v)
    if p:
        return f"{p[0]:04d}{p[1]:02d}"
    m = re.search(r"(19|20)\d{2}", s(v))
    return m.group(0) if m else ""


def format_cn_date(v: str):
    """规范为 YYYY年MM月DD日；无法确定年+月时返回 None（不臆造）。

    EN: Normalise to YYYY年MM月DD日; returns None when year + month cannot be determined (nothing is invented).

    JA: YYYY年MM月DD日 に正規化する。年 + 月が確定できなければ None を返す（推測で作らない）。
    """
    p = parse_ym(v)
    if not p:
        return None
    return f"{p[0]:04d}年{p[1]:02d}月{p[2]:02d}日"


def is_present_word(v: str) -> bool:
    return norm_text(v) in {norm_text(x) for x in PRESENT_WORDS}


def norm_datetime(v: str) -> str:
    """dates.* 规范为 YYYY-MM-DD HH:MM:SS；无法解析则原样返回。

    EN: Normalise dates.* to YYYY-MM-DD HH:MM:SS; return unchanged if it cannot be parsed.

    JA: dates.* を YYYY-MM-DD HH:MM:SS に正規化する。解析できなければそのまま返す。
    """
    t = s(v)
    m = re.match(r"((?:19|20)\d{2})[-/.年](\d{1,2})[-/.月](\d{1,2})日?(?:[ T](\d{1,2}):(\d{2})(?::(\d{2}))?)?", t)
    if not m:
        return t
    y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
    hh, mm, ss = int(m.group(4) or 0), int(m.group(5) or 0), int(m.group(6) or 0)
    return f"{y:04d}-{mo:02d}-{d:02d} {hh:02d}:{mm:02d}:{ss:02d}"


# ---------------------------------------------------------------- 语种
# EN: ---------------------------------------------------------------- Language
# JA: ---------------------------------------------------------------- 言語
LANG_ALIASES = {"ja": "jp", "jpn": "jp", "japanese": "jp", "zh-cn": "zh", "cn": "zh", "chinese": "zh", "english": "en",
                "ko": "kr", "korean": "kr", "german": "de"}

BUSINESS_TEXT_FIELDS = {
    "expected_list": ["expected_position", "expected_city", "expected_industry"],
    "work_experiences": ["company_name", "position", "position_dept", "position_responsibilities", "position_achievements", "resigned_reason"],
    "education_list": ["school_name", "school_major_name", "school_degree_type"],
    "certificate_list": ["certificate_name"],
    "skills_list": ["skill_name"],
    "training_list": ["organization_name", "training_name", "description"],
    "project_list": ["project_name", "description", "responsibilities"],
}


def resume_label(res: dict) -> str:
    raw = s(res.get("resume_languge") or res.get("resume_language")).lower()
    return LANG_ALIASES.get(raw, raw)


def resume_business_text(res: dict) -> str:
    parts = [s((res.get("base_info") or {}).get("full_name")), s((res.get("base_info") or {}).get("pr"))]
    for lst, fields in BUSINESS_TEXT_FIELDS.items():
        for it in res.get(lst) or []:
            if isinstance(it, dict):
                parts += [s(it.get(f)) for f in fields]
    return "\n".join(p for p in parts if p)


def text_script_counts(text: str):
    return {
        "han": len(HAN_RE.findall(text)),
        "kana": len(KANA_RE.findall(text)),
        "hangul": len(HANGUL_RE.findall(text)),
        "latin": len(LATIN_RE.findall(text)),
    }


def detect_language(res: dict):
    """按业务字段内容判定真实语种，不信任标签。返回 (lang, counts)。

    EN: Determine the real language from the content of business fields, not trusting labels. Returns (lang, counts).

    JA: ラベルを信用せず、業務フィールドの内容から実際の言語を判定する。戻り値：(lang, counts)。
    """
    text = resume_business_text(res)
    c = text_script_counts(text)
    label = resume_label(res)
    total = c["han"] + c["kana"] + c["hangul"] + c["latin"]
    if total == 0:
        return (label or "zh"), c
    cjk = c["han"] + c["kana"]
    if c["kana"] >= 10 and c["kana"] >= 0.12 * cjk:
        return "jp", c
    if c["hangul"] >= 10 and c["hangul"] >= 0.1 * total:
        return "kr", c
    han_weight = c["han"] / (c["han"] + c["latin"] / 3.0) if (c["han"] + c["latin"]) else 0
    if han_weight >= 0.35:
        return "zh", c
    if GERMAN_RE.search(text):
        return "de", c
    if label in ("fr", "es", "de"):
        return label, c
    return "en", c


# ---------------------------------------------------------------- 姓名
# EN: ---------------------------------------------------------------- Names
# JA: ---------------------------------------------------------------- 氏名
CN_NAME_RE = re.compile(r"^[一-鿿]{2,4}$|^[一-鿿]{1,6}[·•・][一-鿿]{1,10}$")
EN_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z.'\-]*(?:[ ,]+[A-Za-z][A-Za-z.'\-]*){0,3}$")


def name_quality(name: str):
    """返回 (quality, kind)。quality: valid | suspect | invalid；kind: cn | en | other。

    EN: Returns (quality, kind). quality: valid | suspect | invalid; kind: cn | en | other.

    JA: 戻り値：(quality, kind)。quality：valid | suspect | invalid、kind：cn | en | other。
    """
    n = s(name)
    if not n:
        return "invalid", "other"
    low = n.lower()
    if low in NAME_JUNK or n in NAME_JUNK:
        return "invalid", "other"
    if re.search(r"\d", n) or re.search(r"[*＊]", n):  # 数字、平台打码（“刘**”）
    # EN: Digits, platform masking ("刘**")
    # JA: 数字、プラットフォームによるマスク（「刘**」）
        return "invalid", "other"
    if n in PLACE_NAME_SET or (len(n) >= 3 and n[:2] in PLACE_NAME_SET and n[:2] not in ("中国", "日本")):
        return "invalid", "cn"
    if re.fullmatch(r"[一-鿿]{2,5}(部|课|課|科|处|處|室|组|組)", n) and re.search(r"(企划|企画|市场|营业|営業|人事|总务|総務|财务|財務|技术|技術|品质|品質|生产|生産|采购|購買|管理|销售|开发|開発)", n):
        return "invalid", "cn"
    if re.fullmatch(r"[一-鿿]{1,4}[一二三四五六七八九]?(部|课|課|室|组|組|处|處)", n) and len(n) >= 3:
        return "invalid", "cn"
    if re.search(r"(求职|状态|概况|联系|营销|分析|服务业|简介|简$)", n):
        return "invalid", "cn"
    if CN_NAME_RE.match(n):
        if any(p in n for p in NAME_JUNK_PARTS):
            return "invalid", "cn"
        if re.search(r"(先生|女士|小姐)", n):
            return "suspect", "cn"
        return "valid", "cn"
    if EN_NAME_RE.match(n) and 2 <= len(n) <= 40:
        return "valid", "en"
    if HAN_RE.search(n) and len(n) <= 10 and not any(p in n for p in NAME_JUNK_PARTS):
        return "suspect", "cn"
    return "suspect", "other"


# 姓名里的繁体字 / 日文新字体 → 简体。只收数据里实际出现、且对应关系明确的字；
# 珺玥赟旻喆祎劼彧垚珅昳堃甦昇珮濛頔韡鋆等本身就是规范用字或无明确简体，不转换。
# EN: Traditional / Japanese shinjitai characters in names → simplified. Only characters that actually occur in the data and have a clear correspondence are included;
#     characters like 珺玥赟旻喆祎劼彧垚珅昳堃甦昇珮濛頔韡鋆 are standard characters themselves or have no clear simplified form, and are not converted.
# JA: 氏名の繁体字・日本の新字体 → 簡体字。データに実際に現れ、対応関係が明確な字だけを収録する。
#     珺玥赟旻喆祎劼彧垚珅昳堃甦昇珮濛頔韡鋆 などはそれ自体が規範の字であるか明確な簡体字がないため、変換しない。
_SIMP_PAIRS = (
    "張张陳陈劉刘孫孙楊杨華华趙赵麗丽偉伟馬马紅红潔洁傑杰夢梦飛飞輝辉鳳凤慶庆鵬鹏陸陆強强龍龙陽阳鄭郑顧顾許许謝谢軍军"
    "寧宁寜宁東东葉叶贇赟興兴馮冯雲云衛卫錫锡鐘钟凱凯瑋玮剛刚棟栋羅罗遠远誠诚曄晔驥骥穎颖頴颖喬乔堅坚維维勝胜瓊琼駿骏"
    "純纯憶忆澤泽沢泽蘭兰黃黄鳴鸣軒轩長长銘铭愛爱韓韩競竞鄒邹錦锦暉晖暘旸領领湯汤瑩莹嶸嵘漢汉聖圣時时綺绮葦苇達达宮宫"
    "詩诗湧涌鄧邓嬌娇語语談谈倫伦灝灏魯鲁順顺貝贝別别樑梁賀贺儀仪鋒锋燦灿賢贤錚铮書书龔龚記记個个瀟潇贈赠呂吕賈贾"
    "範范誕诞塵尘嘯啸吳吴呉吴爾尔盧卢鶴鹤帥帅遊游嵐岚鮑鲍鈞钧紀纪潤润濤涛苧苎賽赛銀银驊骅聞闻蘇苏靚靓禇褚億亿駸骎"
    "連连萬万費费龐庞簡简儂侬藍蓝譚谭濱滨叢丛務务況况釗钊嶽岳諍诤諝谞煒炜藹蔼藝艺歐欧馳驰鈺钰燁烨禕祎凃涂幹干報报"
    "碩硕項项駱骆鶯莺軼轶職职絡络蓮莲楓枫顔颜嬋婵開开進进禎祯絹绢業业閻阎義义韻韵鴻鸿欒栾門门練练饒饶懌怿揚扬"
    "煬炀闞阚納纳統统嬰婴術术現现詣诣誌志懐怀麥麦頌颂電电話话樹树無无諸诸園园竝并淵渊篠筱"
    "暁晓楽乐栄荣亜亚剣剑広广歓欢銭钱厳严恵惠鋭锐尭尧啓启兪俞鴎鸥氷冰権权黙默頼赖斉齐単单歴历顕显霊灵専专"
    "絵绘鉄铁験验経经荘庄暦历遅迟徳德為为艶艳櫻樱蕓芸鐿镱嶢峣瀋沈"
)
SIMP_MAP = {_SIMP_PAIRS[i]: _SIMP_PAIRS[i + 1] for i in range(0, len(_SIMP_PAIRS), 2)}


def to_simplified_name(name: str) -> str:
    return "".join(SIMP_MAP.get(c, c) for c in s(name))


NAME_GLUE_RE = re.compile(r"^([\u4e00-\u9fff]{2,4})\s*(性别|性別|年龄|年齢|出生|生年月日|男|女)$")


def strip_name_label(name: str):
    """'熊强性別' → '熊强'；无法确定时原样返回。

    EN: '熊强性別' → '熊强'; returned unchanged when it cannot be determined.

    JA: '熊强性別' → '熊强'。確定できなければそのまま返す。
    """
    m = NAME_GLUE_RE.match(s(name))
    return m.group(1) if m else s(name)


AGE_RE = re.compile(r"^(\d{1,3})\s*(岁|歳|歲|才|周岁|years?\s*old)?$", re.I)


def normalize_age(v: str) -> str:
    t = unicodedata.normalize("NFKC", s(v))
    m = AGE_RE.match(t)
    return m.group(1) if m else s(v)


def name_key(name: str) -> str:
    return norm_text(name)


# ---------------------------------------------------------------- 快照与 raw_text
# EN: ---------------------------------------------------------------- Snapshots and raw_text
# JA: ---------------------------------------------------------------- スナップショットと raw_text
def empty_obj(fields, overrides=None):
    o = {f: "" for f in fields}
    if overrides:
        o.update(overrides)
    return o


def rank_int(v) -> int:
    try:
        return int(s(v))
    except ValueError:
        return 0


def pick_current(work_list):
    if not work_list:
        return empty_obj(CURRENT_FIELDS, {"employment_type": "全职"})
    current = [w for w in work_list if s(w.get("status")) == "在职" or (s(w.get("position_start")) and not s(w.get("position_resigned")))]
    pool = current or work_list
    best = sorted(pool, key=lambda w: ym_key(w.get("position_start")), reverse=True)[0]
    return {f: s(best.get(f)) for f in CURRENT_FIELDS}


def pick_education(edu_list):
    if not edu_list:
        return empty_obj(EDU_FIELDS)
    best = sorted(edu_list, key=lambda e: (rank_int(e.get("school_degree_rank")), ym_key(e.get("school_end_ym")) or ym_key(e.get("school_start_ym"))), reverse=True)[0]
    return {f: s(best.get(f)) for f in EDU_FIELDS}


def build_snapshots(resumes):
    r0 = resumes[0] if resumes else {}
    base = {f: s((r0.get("base_info") or {}).get(f)) for f in BASE_FIELDS}
    exp = r0.get("expected_list") or []
    expected = {f: s(exp[0].get(f)) for f in EXPECTED_FIELDS} if exp else empty_obj(EXPECTED_FIELDS)
    return {
        "base_info": base,
        "expected_info": expected,
        "current_info": pick_current(r0.get("work_experiences") or []),
        "education_info": pick_education(r0.get("education_list") or []),
    }


def resume_text_lines(res: dict):
    lines = []
    base = res.get("base_info") or {}
    for f in BASE_FIELDS:
        v = s(base.get(f))
        if v and v.lower() not in PLACEHOLDERS:
            lines.append(v)
    for lst in LIST_ORDER:
        for it in res.get(lst) or []:
            vals = [s(it.get(f)) for f in LIST_FIELDS[lst] if f not in ("sequence_no", "fingerprint")]
            vals = [v for v in vals if v and v.lower() not in PLACEHOLDERS]
            if vals:
                lines.append(" ".join(vals))
    out, seen = [], set()
    for ln in lines:
        if ln not in seen:
            seen.add(ln)
            out.append(ln)
    return out


def build_raw_text_assembled(resumes) -> str:
    """合并/翻译/多语言简历的 raw_text：把各字段直接拼装，每个字段一行，\n 连接；
    顺序为各语言版本依次，每版先基本信息再各个列表；空值、占位符不写，不去重、不加空行。

    EN: raw_text of merged/translated/multilingual résumés: assemble the fields directly, one field per line, joined with newlines;
    the order is each language version in turn, each version with basic info first and then each list; empty values and placeholders are not written, no dedup, no blank lines.

    JA: 統合・翻訳・多言語の履歴書の raw_text：各フィールドをそのまま組み立て、1 フィールド 1 行で改行により連結する。
    順序は言語版ごとに順に、各版は基本情報が先でその後に各リスト。空の値とプレースホルダーは書かず、重複排除も空行の追加もしない。
    """
    lines = []
    for res in resumes:
        base = res.get("base_info") or {}
        for f in BASE_FIELDS:
            v = s(base.get(f))
            if v and v.lower() not in PLACEHOLDERS:
                lines.append(v)
        for lst in LIST_ORDER:
            for it in res.get(lst) or []:
                for f in LIST_FIELDS[lst]:
                    if f in ("sequence_no", "fingerprint"):
                        continue
                    v = s(it.get(f))
                    if v and v.lower() not in PLACEHOLDERS:
                        lines.append(v)
    return "\n".join(lines)


def clean_source_text(text) -> str:
    """原文文本：去掉“### 工作表”标记行，每行去首尾空白，丢掉空行，\n 连接。

    EN: Original text: remove "### 工作表" (worksheet) marker lines, trim each line, drop empty lines, and join with newlines.

    JA: 原文のテキスト：「### 工作表」（ワークシート）の目印の行を除き、各行の前後の空白を除き、空行を捨てて、改行で連結する。
    """
    out = []
    for ln in str(text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        ln = ln.strip()
        if not ln or ln.startswith("### "):
            continue
        out.append(ln)
    return "\n".join(out)


def build_raw_text(resumes) -> str:
    blocks = []
    for res in resumes:
        lines = resume_text_lines(res)
        if lines:
            blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


RADICAL_RE = re.compile(r"[\u2e80-\u2fdf\uf900-\ufaff]")
LABEL_RESIDUE_RE = re.compile(r"(Background|Profile|Summary|Experience|Dept\.|所在地区|目前职位|公司性质|公司规模|公司行业|工作地点|下属人数|汇报对象)\s*[:：]", re.I)
SENT_PUNCT_RE = re.compile(r"[，。；！？;]")
DOUBLE_CJK_RE = re.compile(r"([\u4e00-\u9fff])\1")
ENTITY_FIELDS = {"company_name", "position", "position_dept", "school_name", "school_major_name", "school_degree_type",
                 "certificate_name", "language_name", "skill_name", "project_name", "organization_name", "training_name",
                 "full_name", "city", "expected_position", "expected_city"}
GARBLE_MARK_RE = re.compile(r"\ufffd|锟斤拷|烫烫烫")


def value_penalty(v: str, field: str) -> int:
    """值质量惩罚分，越小越好。用于同一字段多个来源候选值的选择。

    EN: Value-quality penalty score; smaller is better. Used to choose among candidate values for the same field from several sources.

    JA: 値の品質の減点。小さいほどよい。同じフィールドに複数のソースの候補値がある場合の選択に使う。
    """
    t = s(v)
    if not t:
        return 99
    p = 0
    if GARBLE_MARK_RE.search(t):
        p += 20
    if RADICAL_RE.search(t):
        p += 8
    if re.fullmatch(r"[\s\W_]+", t):
        p += 20
    if LABEL_RESIDUE_RE.search(t):
        p += 4
    if field in ENTITY_FIELDS:
        if len(t) > 40 or SENT_PUNCT_RE.search(t):
            p += 4
        if re.search(r"\d{3,}\s*元|元\s*/\s*月", t):
            p += 3
        if len(norm_text(t)) <= 1:
            p += 6
        if field != "full_name":
            p += len(DOUBLE_CJK_RE.findall(t))
        if re.search(r"[:：]", t):
            p += 3
    return p


def resume_garble_score(res: dict) -> int:
    return len(RADICAL_RE.findall(resume_business_text(res)))


def safe_filename_part(t: str) -> str:
    t = re.sub(r'[\\/:*?"<>|\r\n\t]+', "_", s(t))
    t = t.strip(" .")
    return t or "待确认姓名"
