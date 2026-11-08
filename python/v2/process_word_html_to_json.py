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
import json
import os
import re
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup, Tag


PROJECT_ROOT = _rc.project_root()
PYTHON_ROOT = _rc.PYTHON_DIR / "v2"
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from codex_word_html_json_100 import extend_schema, updated_date
from process_word_to_html import GENERATOR_VERSION, SCHEMA_VERSION, strip_tags
from resume_importer.classifier import DocumentClassifier
from resume_importer.codex_gemini_html_schema_parser import CodexGeminiHtmlSchemaParser


PARSER_VERSION = "semantic-dom-complete-v1-1.1.0"
RESUME_LISTS = (
    "expected_list",
    "work_experiences",
    "education_list",
    "certificate_list",
    "language_list",
    "skills_list",
    "training_list",
    "project_list",
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
    "company_name", "company_employees", "company_industry", "position",
    "position_type", "position_salary", "position_dept", "position_report_to",
    "position_subordinate", "employment_type", "annual_salary_min",
    "annual_salary_max", "status", "position_start", "position_resigned",
    "resigned_reason", "position_responsibilities", "position_achievements",
    "company_nature",
)
CURRENT_FIELDS = WORK_FIELDS[:15]
EDUCATION_FIELDS = (
    "school_name", "school_major_name", "school_degree_type", "school_degree_rank",
    "school_education_type", "school_start_ym", "school_end_ym",
)
COLLECTION_FIELDS = {
    "expected_list": EXPECTED_FIELDS,
    "work_experiences": WORK_FIELDS,
    "education_list": EDUCATION_FIELDS,
    "certificate_list": ("certificate_name", "certificate_type", "certificate_time"),
    "language_list": ("language_name", "language_level", "language_certificate", "language_certificate_time"),
    "skills_list": ("skill_name", "skill_level"),
    "training_list": ("sequence_no", "organization_name", "training_name", "start_ym", "end_ym", "certificate_name", "description"),
    "project_list": ("sequence_no", "fingerprint", "project_name", "company_or_client", "role_name", "start_ym", "end_ym", "description", "responsibilities", "achievements", "keywords"),
    "communication_list": ("communicate_time", "communicate_content"),
}
PRIMARY_FIELDS = {
    "expected_list": ("expected_position", "expected_city"),
    "work_experiences": ("company_name", "position_start", "position"),
    "education_list": ("school_name", "school_start_ym"),
    "certificate_list": ("certificate_name",),
    "language_list": ("language_name",),
    "skills_list": ("skill_name",),
    "training_list": ("training_name", "organization_name"),
    "project_list": ("project_name",),
    "communication_list": ("communicate_time", "communicate_content"),
}


def semantic_resume_roots(soup: BeautifulSoup) -> list[Tag]:
    """Return the semantic resume records, with a safe single-document fallback.

    The XLS rebuild pipeline imports ``parse_html_record`` from this module.
    That function already depended on this helper, but the helper was missing
    from the Word implementation (while the PDF implementation retained it),
    causing every real source re-extraction to fail with ``NameError``.
    """
    records = soup.find_all("article", attrs={"class": "resume-record"})
    if not records:
        records = soup.find_all("article", attrs={"data-role": "resume"})
    if not records:
        main = soup.find("main") or soup.find("body") or soup
        return [main]
    return records
LANGUAGE_CERTIFICATE_RE = re.compile(
    r"\b(?:CET[- ]?[46]|JLPT[- ]?N?[1-5]|J[.-]?TEST|TOEIC|TOEFL|IELTS|BEC)\b|"
    r"(?:大学英语[四六]级|英语[四六]级|日语[一二三四五]级|日本語能力試験)",
    re.IGNORECASE,
)
COMMON_CHINESE_SURNAMES = set(
    "肖赵钱孙李周吴郑王冯陈褚卫蒋沈韩杨朱秦尤许何吕施张孔曹严华金魏陶姜"
    "戚谢邹喻柏水窦章云苏潘葛奚范彭郎鲁韦昌马苗凤花方俞任袁柳鲍史唐"
    "费廉岑薛雷贺倪汤滕殷罗毕郝邬安常乐于傅皮卞齐康伍余元顾孟平黄和"
    "穆萧尹姚邵湛汪祁毛禹狄米贝明臧计伏成戴谈宋茅庞熊纪舒屈项祝董梁"
    "杜阮蓝闵席季麻强贾路娄危江童颜郭梅盛林钟徐邱骆高夏蔡田樊胡凌霍"
    "虞万支柯管卢莫房裘缪解应宗丁宣邓郁单杭洪包左石崔吉龚程嵇邢裴陆"
    "荣翁荀羊甄家封芮羿储靳汲邴糜松井段富巫乌焦巴弓牧隗山谷车侯宓蓬"
    "全郗班仰秋仲伊宫宁仇栾暴甘钭厉戎祖武符刘景詹束龙叶幸司韶黎乔苍"
    "双闻莘党翟谭贡劳姬申扶堵冉宰郦雍郤璩桑桂濮牛寿通边燕冀郏浦尚农"
    "温别庄晏柴瞿阎充慕连茹习艾鱼容向古易慎戈廖庾终暨居衡步都耿满弘"
    "匡国文寇广禄阙东欧殳沃利蔚越夔隆师巩厍聂晁勾敖融冷訾辛阚那简饶"
    "空曾毋沙乜养鞠须丰巢关蒯相查后荆红游竺权逯盖益桓公"
)
# Traditional-character variants are common in Japanese/Chinese Excel
# templates.  Keep the same surname gate, but do not reject valid names such
# as 陳誠, 劉婉瑩, 張世佳, 鄭和平 and 馬海佳.
COMMON_CHINESE_SURNAMES.update(set(
    "趙錢孫吳鄭馮陳褚衛蔣韓楊許呂張曹嚴華魏戚謝鄒竇章雲蘇彭魯韋馬鳳鮑"
    "費薛賀湯滕羅畢郝鄔樂齊顧黃穆蕭姚湛汪禹貝臧戴談茅龐紀屈項祝董樑"
    "藍閔強賈婁童顏盛鐘邱駱夏蔡樊凌萬柯盧裘繆解應宣鄧單洪龔嵇邢裴陸"
    "榮荀甄芮儲靳汲邴糜烏焦牧隗車侯宓蓬郗仰宮寧欒厲符劉龍葉喬蒼黨翟"
    "譚酈雍璩壽邊冀郟尚農莊晏瞿閻慕連習魚慎戈廖庾耿滿匡廣祿聶融闞簡"
    "養須豐巢關遊竺權蓋"
))
NAME_NOISE_RE = re.compile(
    r"简历|履歴書|職務経歴书|職務経歴書|resume|curriculum|vitae|系统|番号|编号|ID|代码|"
    r"システム番号|受付番号|会員番号|管理番号|登録番号|照会番号|"
    r"实施|运维|工程师|工作|个人|基本信息|资料|职位|招聘|人才|日文|日本語|中文|英文|项目|申请表|"
    r"career|objective|experience|education|background|skills|certificates|profile|"
    r"akademische|ausbildung|lebenslauf|assessment|report|basic\s*info|personal\s*info|"
    r"current\s*company|current\s*position|family\s*name|first\s*name|last\s*name|"
    r"university|college|school|institut|academy|engineering|technology|gmbh|co\.,?\s*ltd|corporation|company",
    re.IGNORECASE,
)


def empty_object(fields: tuple[str, ...], defaults: dict[str, Any] | None = None) -> dict[str, Any]:
    result = {field: "" for field in fields}
    result.update(defaults or {})
    return result


def source_hash(path: str) -> str:
    normalized = str(Path(path).resolve()).replace("/", "\\").casefold()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:12]


def safe_output_name(value: str) -> str:
    clean = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "", value or "").strip(" ._")
    return re.sub(r"\s+", " ", clean)[:80] or "待确认姓名"


def atomic_write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    finally:
        Path(temp_name).unlink(missing_ok=True)


ETHNIC_GROUPS = {
    "汉族", "满族", "回族", "苗族", "维吾尔族", "壮族", "彝族", "土家族", "藏族", "蒙古族",
    "布依族", "侗族", "瑶族", "朝鲜族", "白族", "哈尼族", "哈萨克族", "黎族", "傣族", "畲族",
    "高山族", "水族", "东乡族", "纳西族", "景颇族", "柯尔克孜族", "土族", "达斡尔族", "仫佬族", "羌族",
    "布朗族", "撒拉族", "毛南族", "仡佬族", "锡伯族", "阿昌族", "普米族", "塔吉克族", "怒族", "乌孜别克族",
    "俄罗斯族", "鄂温克族", "德昂族", "保安族", "裕固族", "京族", "塔塔尔族", "独龙族", "鄂伦春族", "赫哲族",
    "门巴族", "珞巴族", "基诺族", "荣誉证书", "获奖证书", "政治面貌", "基本信息", "个人简历", "求职意向",
    "Akademische Ausbildung", "Akademische", "Ausbildung", "Lebenslauf", "Assessment Report", "Basic Info", "Thyssenkrupp",
    "Basic Information", "Personal Information", "Current Company", "Current Position", "Family Name"
}

DIR_SYSTEM_NOISE = re.compile(
    r"需要采集|老婆|资料|表格|电脑|人才|智联|猎聘|Basic\s*Info|Personal\s*Info|Current\s*Company|Current\s*Position|简历|履历|Resume|CV|市场|销售|技术|研发|药业|生物|科技|工程|公司|大学|学院",
    re.I
)

def plausible_name(value: str) -> bool:
    name = re.sub(r"\s+", " ", str(value or "")).strip(" -_.,，。:：()（）")
    if not name or DIR_SYSTEM_NOISE.search(name) or any(char.isdigit() for char in name):
        return False
    if re.fullmatch(r"[\u4e00-\u9fff]{2,4}", name):
        return name[0] in COMMON_CHINESE_SURNAMES or name[0] == "肖" or name[:2] in {"欧阳", "诸葛", "司徒", "皇甫", "上官"}
    if re.fullmatch(r"[\u3040-\u30ff\u4e00-\u9fff]{2,8}", name):
        return True
    if re.fullmatch(r"[A-Z][a-z]{1,20}(?:\s+[A-Z][a-z]{1,20}){1,3}", name):
        return True
    return False


def normalize_name(value: str) -> str:
    text = re.sub(r"^(?:姓名|氏名|Name)\s*[:：]?\s*", "", str(value or ""), flags=re.I)
    text = re.sub(r"\s+", " ", text).strip(" ：:|｜_-.()（）")
    return text if plausible_name(text) else ""


def filename_name_hint(path: Path) -> str:
    for part in (item.strip() for item in re.split(r"[-_—–\s]+", path.stem)):
        candidate = normalize_name(part)
        if candidate and not NAME_NOISE_RE.search(candidate):
            return candidate
    return ""

def semantic_name_hint(main: Tag) -> str:
    candidates: list[str] = []
    first_section = main.find("section") or main
    for node in first_section.find_all(["p", "td", "th", "h1", "h2"], limit=16):
        value = clean_value(node)
        if value and len(value) <= 60:
            candidates.append(value)
    return next((value for value in candidates if plausible_name(value)), "")


def _extract_pr(self, text: str) -> str:
    # 简历版块标题通常没有空行，不能只依赖空行作为结束条件。
    # EN: Résumé section headings usually have no blank line before them, so a blank line cannot be the only end condition.
    # JA: 履歴書の項目見出しの前には通常空行がないため、空行だけを終了条件にはできない。
    section_stops = (
        r"工作经验|工作经历|工作背景|职业概况|仕事経験|職歴|勤務履歴|勤務歴|"
        r"教育经历|教育背景|学历|学歴|项目经历|项目经验|研究经历|"
        r"培训经历|培训背景|语言能力|外语水平|技能标签|专业技能|计算机水平|"
        r"证书|资格证书|附加信息|附加消息|求职意向|职业意向|个人信息|基本信息|"
        r"希望職|求職希望|自己PR|個人PR|个人优势|兴趣爱好|趣味"
    )
    pr_val = ""
    m = re.search(
        rf"(?:自我评价|个人总结|个人评价|自己PR|个人自述|概要＆ポイント|自\s*评|自己アピール)"
        rf"\s*[:：\t\s]*([\s\S]{10,800}?)(?=\n\s*(?:{section_stops})\s*[:：]?\s*(?:\n|$)|声明：|\Z)",
        text,
        re.IGNORECASE,
    )
    if m:
        pr_val = m.group(1).strip()
    else:
        # 降级截取
        # EN: Fallback truncation
        # JA: 代替の切り出し
        m_fallback = re.search(r"(?:自我评价|个人总结|个人评价|自\s*评)\s*[:：\t\s]*([\s\S]+)", text, re.IGNORECASE)
        if m_fallback:
            pr_val = m_fallback.group(1).strip()

    # 某些模板把下一个标题直接接在上一行之后，统一截断一次。
    # EN: Some templates put the next heading directly after the previous line; truncate once uniformly.
    # JA: テンプレートによっては次の見出しが前の行の直後に続くため、一律に 1 回切り詰める。
    if pr_val:
        stop_match = re.search(rf"\n\s*(?:{section_stops})\s*[:：]?\s*(?:\n|$)", "\n" + pr_val, re.IGNORECASE)
        if stop_match:
            pr_val = pr_val[:max(0, stop_match.start() - 1)].strip()
            
    # 彻底剥离版权声明、操作时间及操作人（猎聘/智联尾部固定文本块）
    # EN: Completely strip copyright notices, operation times and operators (the fixed trailing text block of Liepin/Zhaopin)
    # JA: 著作権表示・操作日時・操作者（Liepin・Zhaopinの末尾にある定型テキストブロック）を完全に除去する
    pr_val = re.sub(r"声明：[\s\S]*$", "", pr_val).strip()
    pr_val = re.sub(r"操作时间[\s\S]*$", "", pr_val).strip()
    pr_val = re.sub(r"操作人[:：\s]*\d+[\s\S]*$", "", pr_val).strip()
    
    # 核心必保：通过 BeautifulSoup 滤掉所有残留的 HTML 标签，只保留纯文本！
    # EN: Must keep: use BeautifulSoup to filter out all remaining HTML tags and keep only plain text!
    # JA: 必須：BeautifulSoup で残っている HTML タグをすべて除去し、プレーンテキストだけを残す！
    if "<" in pr_val and ">" in pr_val:
        pr_val = BeautifulSoup(pr_val, "html.parser").get_text("\n", strip=True)
        
    return pr_val[:600].strip()




def clean_value(node: Any) -> str:
    if not node:
        return ""
    text = getattr(node, "text", str(node))
    return re.sub(r"\s+", " ", text).strip()


def dom_field_values(main: Tag) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for node in main.find_all(attrs={"data-field": True}):
        field = str(node.get("data-field") or "")
        value = clean_value(node)
        if field and value:
            result.setdefault(field, []).append(value)
    return result


DATE_TOKEN = r"(?:(?:19|20)\d{2}[\s./年\-]{1,3}(?:0?[1-9]|1[0-2])(?:[\s./月\-]{1,3}(?:0?[1-9]|[12]\d|3[01])日?)?|(?:19|20)\d{2}年?|(?:0?[1-9]|1[0-2])/(?:19|20)\d{2})"
DATE_RANGE_RE = re.compile(
    rf"^\s*(?P<start>{DATE_TOKEN})\s*[-—–~～〜至到/]\s*(?P<end>{DATE_TOKEN}|至今|现在|目前|Present|Current|heute|今迄|現在)?\s*[:：|｜\s]*(?P<rest>.*)$",
    re.I
)

def normalized_month(val: Any) -> str:
    if not val:
        return ""
    m = re.search(r"((?:19|20)\d{2})[\s./年\-]+(0?[1-9]|1[0-2])", str(val))
    if m:
        return f"{m.group(1)}年{int(m.group(2)):02d}月01日"
    m_yr = re.search(r"((?:19|20)\d{2})", str(val))
    if m_yr:
        return f"{m_yr.group(1)}年01月01日"
    return str(val)

def section_lines(section: Tag) -> list[str]:
    lines = []
    for node in section.find_all(["p", "h1", "h2", "h3", "h4", "h5", "h6", "li", "tr", "div"]):
        txt = clean_value(node)
        if txt and txt not in lines:
            lines.append(txt)
    return lines

def semantic_work_records(main: Tag) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for section in main.find_all("section", attrs={"data-collection": "work_experiences"}):
        lines = section_lines(section)
        starts = [(index, DATE_RANGE_RE.match(line)) for index, line in enumerate(lines)]
        starts = [(index, match) for index, match in starts if match]
        for record_index, (line_index, match) in enumerate(starts):
            assert match is not None
            end_index = starts[record_index + 1][0] if record_index + 1 < len(starts) else len(lines)
            block = [re.sub(r"\s+", " ", line).strip(" |") for line in lines[line_index:end_index]]
            rest = match.group("rest").strip(" |")
            company = rest
            body_lines = block[1:]
            RESP_START_RE = re.compile(
                r"^(?:负责|参与|主持|协助|从事|主要负责|主要工作|在.+公司|任职|工作职责|岗位职责|"
                r"Wirkt|Verantwortlich|Entwicklung|Beschädigung|Erreichen|Analyse|Regelmäßiges|Eskalation|Einhaltung|"
                r"•|·|-|—)\b",
                re.I
            )
            while body_lines and re.match(r"^[•·\-\s,，.、/\|｜]+$", body_lines[0]):
                body_lines.pop(0)
            if not company and body_lines:
                if not RESP_START_RE.search(body_lines[0]) and len(body_lines[0]) <= 70:
                    company = body_lines.pop(0)
            while body_lines and re.match(r"^[•·\-\s,，.、/\|｜]+$", body_lines[0]):
                body_lines.pop(0)
            if company and RESP_START_RE.search(company):
                body_lines.insert(0, company)
                company = ""
            position = ""
            industry = ""
            if body_lines:
                first = body_lines[0]
                labeled = re.match(r"^(?:职位|职务|Position|Job Title|役職)\s*[:：]\s*(.+)$", first, flags=re.I)
                if labeled:
                    position = labeled.group(1).strip()
                    body_lines.pop(0)
                elif (
                    len(first) <= 45
                    and not re.search(r"[。；;\n]", first)
                    and not RESP_START_RE.search(first)
                ):
                    position = body_lines.pop(0)
            if position and RESP_START_RE.search(position):
                body_lines.insert(0, position)
                position = ""
            if body_lines and (
                "/" in body_lines[0]
                or re.search(r"贸易|制造|医药|制药|互联网|金融|咨询|technology|pharma|trade|manufactur", body_lines[0], re.I)
            ) and len(body_lines[0]) <= 40:
                industry = body_lines.pop(0)
            report_to = ""
            subordinate = ""
            report_match = re.search(r"(?:汇报|报告先|Reports?\s+to)\s*[:：]\s*([^|（）()]+)", position, re.I)
            if report_match:
                report_to = report_match.group(1).strip()
            subordinate_match = re.search(r"下属\s*(\d+)\s*人", position)
            if subordinate_match:
                subordinate = subordinate_match.group(1)
            position = re.sub(r"[（(](?:无?下属|下属\s*\d+\s*人)[^）)]*[）)]", "", position).strip()
            position = re.sub(r"\s*(?:汇报|报告先|Reports?\s+to)\s*[:：].*$", "", position, flags=re.I).strip()
            responsibility = "\n".join(body_lines)
            responsibility = re.sub(r"^(?:Job\s+description|工作职责|工作内容|仕事内容|職務内容)\s*[:：|]?\s*", "", responsibility, flags=re.I)
            end_value = match.group("end") or ""
            current = not end_value or bool(re.search(r"至今|现在|目前|Present|Current|今迄|現在|heute|today|ongoing", end_value, re.I))
            if company or position or match.group("start") or responsibility:
                records.append(normalize_row({
                    "company_name": company,
                    "company_industry": industry,
                    "position": position,
                    "position_report_to": report_to,
                    "position_subordinate": subordinate,
                    "employment_type": "全职",
                    "status": "在职" if current else "离职",
                    "position_start": normalized_month(match.group("start")),
                    "position_resigned": "" if current else normalized_month(end_value),
                    "position_responsibilities": responsibility,
                }, WORK_FIELDS))
    return records


DEGREE_MAP = (
    ("7", "博士后", r"博士后|postdoc"),
    ("6", "博士", r"博士|ph\.?d|doctor|promotion|dr\.-ing"),
    ("5", "硕士", r"硕士|修士|master|mba|emba|m\.sc|m\.eng|magister"),
    ("4", "本科", r"本科|学士|bachelor|\bba\b|\bbs\b|b\.sc|b\.eng|diplom-ingenieur|dipl\.-ing"),
    ("3", "大专", r"大专|专科|短大|associate|diploma"),
    ("2", "高中", r"高中|中专|high school|gymnasium"),
)


def semantic_education_records(main: Tag) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for section in main.find_all("section", attrs={"data-collection": "education_list"}):
        lines = section_lines(section)
        starts = [(index, DATE_RANGE_RE.match(line)) for index, line in enumerate(lines)]
        starts = [(index, match) for index, match in starts if match]
        for record_index, (line_index, match) in enumerate(starts):
            assert match is not None
            end_index = starts[record_index + 1][0] if record_index + 1 < len(starts) else min(line_index + 6, len(lines))
            block = [re.sub(r"\s+", " ", l).strip(" |") for l in lines[line_index:end_index]]
            rest = match.group("rest").strip(" |")
            body_lines = block[1:]
            parts = [part.strip() for part in rest.split("|") if part.strip()]
            school = parts[0] if parts else rest
            major = parts[1] if len(parts) > 1 else ""
            NOISE_SCHOOL_RE = re.compile(
                r"^(?:Familienstand|Führscheinklasse|Geboren|Adresse|Kontaktdaten|Verheiratet|Ledig|Deutsch|Chinesisch|"
                r"婚姻状况|驾照|籍贯|出生年月|政治面貌|性别|年龄|民族|户口|现居地|联系方式|求职意向)\b",
                re.I
            )
            if not school and body_lines:
                while body_lines and NOISE_SCHOOL_RE.search(body_lines[0]):
                    body_lines.pop(0)
                if body_lines:
                    school = body_lines.pop(0)
            if not major and body_lines:
                for b_line in body_lines:
                    if len(b_line) <= 60 and not re.search(r"^[•·\-]|Abschluss|Schwerpunkt|Master|Bachelor", b_line, re.I) and not NOISE_SCHOOL_RE.search(b_line):
                        major = b_line
                        break
            nearby = " ".join(block)
            rank = degree = ""
            for rank_value, degree_value, pattern in DEGREE_MAP:
                if re.search(pattern, nearby, re.I):
                    rank, degree = rank_value, degree_value
                    break
            if degree:
                major = re.sub(
                    r"\b(?:Bachelor|Master|Doctor|Ph\.?D|MBA|EMBA|Associate|Diploma|M\.Sc|B\.Sc)\b|"
                    r"本科|硕士|博士|大专|学士|修士|Abschluss",
                    "",
                    major,
                    flags=re.I,
                ).strip(" |,:：，")
            education_type = {
                "7": "全日制研究生", "6": "全日制研究生", "5": "全日制研究生",
                "4": "全日制大学", "3": "全日制大专", "2": "全日制高中",
            }.get(rank, "")
            records.append(normalize_row({
                "school_name": school,
                "school_major_name": major,
                "school_degree_type": degree,
                "school_degree_rank": rank,
                "school_education_type": education_type,
                "school_start_ym": normalized_month(match.group("start")),
                "school_end_ym": normalized_month(match.group("end")),
            }, EDUCATION_FIELDS))
    return records


def semantic_language_records(main: Tag) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    names = {
        "japanese": "日语", "日本語": "日语", "日语": "日语",
        "english": "英语", "英語": "英语", "英语": "英语",
        "german": "德语", "deutsch": "德语", "ドイツ語": "德语", "德语": "德语",
        "chinese": "中文", "中国語": "中文", "中文": "中文",
    }
    for section in main.find_all("section", attrs={"data-collection": "language_list"}):
        for line in section_lines(section):
            match = re.match(r"^([^:：|]{2,20})\s*[:：]\s*(.+)$", line)
            if not match:
                continue
            label = match.group(1).strip()
            language = names.get(label.casefold()) or names.get(label)
            if language:
                rows.append(normalize_row({
                    "language_name": language,
                    "language_level": match.group(2).strip(" |"),
                }, COLLECTION_FIELDS["language_list"]))
    for section in main.find_all("section", attrs={"data-collection": "certificate_list"}):
        for line in section_lines(section):
            match = re.search(rf"(?P<date>{DATE_TOKEN})\s+(?P<name>.+)", line)
            if not match or not LANGUAGE_CERTIFICATE_RE.search(match.group("name")):
                continue
            certificate = match.group("name").strip(" |")
            language = "日语" if re.search(r"JLPT|J[.-]?TEST|日语|日本語", certificate, re.I) else "英语"
            target = next((row for row in rows if row.get("language_name") == language), None)
            if target is None:
                target = normalize_row({"language_name": language}, COLLECTION_FIELDS["language_list"])
                rows.append(target)
            target["language_certificate"] = "有"
            target["language_certificate_time"] = normalized_month(match.group("date"))
            if certificate not in target["language_level"]:
                target["language_level"] = " / ".join(value for value in [target["language_level"], certificate] if value)
    return rows


def semantic_certificate_records(main: Tag) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    full_text = main.get_text()
    cert_matches = ["日语一级证书", "英语六级证书", "日语二级证书", "英语四级证书", "计算机二级证书", "日语N1", "英语CET6", "日语1级", "英语6级"]
    for cm in cert_matches:
        if cm in full_text and not any(r.get("certificate_name") == cm for r in rows):
            rows.append(normalize_row({
                "certificate_name": cm,
                "certificate_type": "证书",
                "certificate_time": "",
            }, COLLECTION_FIELDS["certificate_list"]))

    sections = list(main.find_all("section", attrs={"data-collection": "certificate_list"}))
    if not sections:
        sections = [sec for sec in main.find_all("section") if any(k in sec.get_text() for k in ["证书", "执照", "资格"])]
    for section in sections:
        for line in section_lines(section):
            if any(award in line for award in ["三好学生", "奖学金", "优秀学生", "优秀干部"]):
                continue
            for node in section.find_all(attrs={"data-field": "certificate_name"}):
                val = clean_value(node)
                if val and not any(award in val for award in ["三好学生", "奖学金"]) and not any(r.get("certificate_name") == val for r in rows):
                    rows.append(normalize_row({
                        "certificate_name": val,
                        "certificate_type": "证书",
                        "certificate_time": "",
                    }, COLLECTION_FIELDS["certificate_list"]))
            matches = re.finditer(rf"(?:(?P<date>{DATE_TOKEN})\s+)?(?P<name>[^\s,，|:：]+(?:证书|执照|六级|四级|一级|二级|三级|资格))", line)
            for match in matches:
                c_name = match.group("name").strip(" |:：")
                if c_name and not any(award in c_name for award in ["三好学生", "奖学金", "技能"]) and not any(r.get("certificate_name") == c_name for r in rows):
                    rows.append(normalize_row({
                        "certificate_name": c_name,
                        "certificate_type": "证书",
                        "certificate_time": normalized_month(match.group("date")) if match.group("date") else "",
                    }, COLLECTION_FIELDS["certificate_list"]))
    return rows


def explicit_base_info(main: Tag) -> dict[str, str]:
    result = empty_object(BASE_FIELDS)
    values = dom_field_values(main)
    for field in BASE_FIELDS:
        if values.get(field):
            result[field] = values[field][0]
    first_section = main.find("section")
    if first_section:
        for line in section_lines(first_section)[:5]:
            match = re.search(
                r"\b(?P<gender>Male|Female|男|女)\b\s*(?P<age>\d{1,2})\s*"
                r"[（(](?P<year>(?:19|20)\d{2})[./年-](?P<month>\d{1,2})",
                line,
                flags=re.IGNORECASE,
            )
            if match:
                result["gender"] = "女" if match.group("gender").casefold() in {"female", "女"} else "男"
                result["age"] = match.group("age")
                result["birth_year"] = match.group("year")
                result["birth_date"] = f"{int(match.group('year')):04d}年{int(match.group('month')):02d}月01日"
                break
    evaluation = main.find("section", attrs={"data-section-type": "self_evaluation"})
    if evaluation:
        result["pr"] = "\n".join(section_lines(evaluation)).strip()
    if not result.get("pr"):
        for sec in main.find_all("section"):
            sec_text = sec.get_text(" ", strip=True)
            if any(k in sec_text for k in ["个人总结", "自我评价", "个人评价"]):
                lines = section_lines(sec)
                pr_lines = [l for l in lines if l not in ["个人总结", "自我评价", "个人评价", "其他", "技能"]]
                if pr_lines:
                    result["pr"] = "\n".join(pr_lines).strip()
                    break
    if len(result["address"]) > 120 or re.search(r"\border to\b|\bdata in\b|responsibilit", result["address"], re.I):
        result["address"] = ""
    if len(result["city"]) > 60 or re.search(r"\border to\b|\bdata in\b|responsibilit", result["city"], re.I):
        result["city"] = ""
    return result


def explicit_collection(main: Tag, collection: str) -> list[dict[str, Any]]:
    allowed = set(COLLECTION_FIELDS[collection])
    primary = set(PRIMARY_FIELDS[collection])
    # 新 DOM 标准：一条经历一个 data-record-type 容器。优先按容器读取，
    # 不再依赖字段出现顺序猜测记录边界。
    # EN: New DOM standard: one data-record-type container per experience. Read by container first,
    #     instead of guessing record boundaries from the order in which fields appear.
    # JA: 新しい DOM 標準：1 件の経歴につき 1 つの data-record-type コンテナ。コンテナ単位での読み取りを優先し、
    #     フィールドの出現順からレコード境界を推測することはもうしない。
    grouped_records: list[dict[str, Any]] = []
    for section in main.find_all("section", attrs={"data-collection": collection}):
        for record_node in section.find_all(attrs={"data-record-type": True}):
            row: dict[str, Any] = {}
            field_values: dict[str, list[str]] = {}
            for node in record_node.find_all(attrs={"data-field": True}):
                field = str(node.get("data-field") or "")
                value = clean_value(node)
                if field in allowed and value:
                    field_values.setdefault(field, []).append(value)
            for field, values in field_values.items():
                # Excel templates sometimes emit a header placeholder first
                # (e.g. company_name=“その他”) and the actual value later in
                # the same record.  Prefer the last non-placeholder value;
                # preserve the old first-value behavior for all other fields.
                if field == "company_name":
                    usable = [v for v in values if v.strip() not in {"公司名", "公司名称", "会社名", "その他"}]
                    row[field] = usable[-1] if usable else values[-1]
                elif field == "school_name":
                    usable = [v for v in values if v.strip() not in {"学校", "学校名", "学校名称"}]
                    row[field] = usable[-1] if usable else values[-1]
                else:
                    row[field] = values[0]
            if row:
                grouped_records.append(row)
    if grouped_records:
        return grouped_records

    nodes: list[Tag] = []
    for section in main.find_all("section", attrs={"data-collection": collection}):
        nodes.extend(
            node for node in section.find_all(attrs={"data-field": True})
            if str(node.get("data-field") or "") in allowed
        )
    records: list[dict[str, Any]] = []
    current: dict[str, Any] = {}
    for node in nodes:
        field = str(node.get("data-field"))
        value = clean_value(node)
        if not value:
            continue
        should_split = field in current and current[field] != value
        if field in primary and field in current:
            should_split = True
        if should_split and current:
            records.append(current)
            current = {}
        if field not in current:
            current[field] = value
    if current:
        records.append(current)
    return [record for record in records if any(str(value).strip() for value in record.values())]


def normalize_row(row: dict[str, Any], fields: tuple[str, ...]) -> dict[str, Any]:
    return {field: row.get(field, "") if row.get(field) is not None else "" for field in fields}


def merge_records(
    legacy: list[dict[str, Any]],
    explicit: list[dict[str, Any]],
    fields: tuple[str, ...],
) -> list[dict[str, Any]]:
    result = [normalize_row(dict(row), fields) for row in (legacy or []) if isinstance(row, dict)]
    for index, explicit_row in enumerate(explicit):
        if index < len(result):
            for field, value in explicit_row.items():
                if field in fields and str(value).strip():
                    result[index][field] = value
        else:
            result.append(normalize_row(explicit_row, fields))
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for row in result:
        if not any(str(value).strip() for value in row.values()):
            continue
        signature = json.dumps(row, ensure_ascii=False, sort_keys=True)
        if signature not in seen:
            seen.add(signature)
            unique.append(row)
    return unique


def separate_language_certificates(resume: dict[str, Any]) -> None:
    certificates: list[dict[str, Any]] = []
    languages = list(resume.get("language_list") or [])
    for certificate in resume.get("certificate_list") or []:
        name = str(certificate.get("certificate_name") or "")
        if LANGUAGE_CERTIFICATE_RE.search(name):
            language_name = "日语" if re.search(r"JLPT|J[.-]?TEST|日语|日本語", name, re.I) else "英语"
            if not any(item.get("language_name") == language_name and name in str(item.get("language_level") or "") for item in languages):
                languages.append({
                    "language_name": language_name,
                    "language_level": name,
                    "language_certificate": "有",
                    "language_certificate_time": certificate.get("certificate_time", ""),
                })
            certificates.append(certificate)
        else:
            certificates.append(certificate)
    resume["certificate_list"] = certificates
    resume["language_list"] = [normalize_row(item, COLLECTION_FIELDS["language_list"]) for item in languages]


def degree_rank(value: str, degree_type: str = "", school_name: str = "") -> int:
    try:
        if value and str(value).isdigit():
            v = int(value)
            if v > 0:
                return v
    except (TypeError, ValueError):
        pass
    dt = str(degree_type or "").casefold()
    sn = str(school_name or "").casefold()
    if any(k in dt or k in sn for k in ["博士", "ph.d", "phd"]):
        return 5
    if any(k in dt or k in sn for k in ["硕士", "修士", "master", "大学院"]):
        return 4
    if any(k in dt or k in sn for k in ["本科", "学士", "bachelor", "大学", "学部"]):
        return 3
    if any(k in dt or k in sn for k in ["专科", "大专", "短期大学", "短大", "高专"]):
        return 2
    if any(k in dt or k in sn for k in ["高中", "高等学校", "高校", "中学"]):
        return 1
    if any(k in dt or k in sn for k in ["小学"]):
        return 0
    return 1


def normalize_resume(resume: dict[str, Any], main: Tag, apply_dom: bool) -> dict[str, Any]:
    language = str(resume.get("resume_languge") or resume.get("resume_language") or "").strip() or "zh"
    normalized: dict[str, Any] = {
        "resume_languge": "jp" if language == "ja" else language,
        "base_info": normalize_row(dict(resume.get("base_info") or {}), BASE_FIELDS),
    }
    explicit_base = explicit_base_info(main) if apply_dom else empty_object(BASE_FIELDS)
    for field, value in explicit_base.items():
        if value:
            normalized["base_info"][field] = value
    for field in ("address", "city"):
        value = str(normalized["base_info"].get(field) or "")
        if len(value) > (120 if field == "address" else 60) or re.search(r"\border to\b|\bdata in\b|responsibilit", value, re.I):
            normalized["base_info"][field] = ""
    for collection in RESUME_LISTS:
        fields = COLLECTION_FIELDS[collection]
        legacy_rows = resume.get(collection) or []
        explicit_rows = explicit_collection(main, collection) if apply_dom else []
        structural_rows: list[dict[str, Any]] = []
        if apply_dom and collection == "work_experiences":
            structural_rows = semantic_work_records(main)
        elif apply_dom and collection == "education_list":
            structural_rows = semantic_education_records(main)
        elif apply_dom and collection == "language_list":
            structural_rows = semantic_language_records(main)
        elif apply_dom and collection == "certificate_list":
            structural_rows = semantic_certificate_records(main)
        if explicit_rows and any(
            any(str(row.get(primary) or "").strip() for primary in PRIMARY_FIELDS.get(collection, ()))
            for row in explicit_rows
        ):
            # Explicit record containers are the authoritative DOM binding;
            # text-line reconstruction is only a fallback when the DOM lacks
            # usable primary fields.  This prevents labels such as
            # “公司名：|公司性质：” from becoming a company value.
            normalized[collection] = [normalize_row(row, fields) for row in explicit_rows]
        elif structural_rows:
            normalized[collection] = [normalize_row(row, fields) for row in structural_rows]
        else:
            normalized[collection] = merge_records(legacy_rows, explicit_rows, fields)
    separate_language_certificates(normalized)
    return normalized


def ensure_chinese_first(resumes: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    issues: list[str] = []
    chinese = next((resume for resume in resumes if resume.get("resume_languge") == "zh"), None)
    foreign = [resume for resume in resumes if resume is not chinese]
    if chinese is None:
        chinese = {
            "resume_languge": "zh",
            "base_info": empty_object(BASE_FIELDS),
            **{name: [] for name in RESUME_LISTS},
        }
        issues.append("foreign_translation_missing")
    elif foreign and not any(
        value for key, value in chinese["base_info"].items()
        if key not in {"phone", "email", "platform_from", "platform_resume_id"}
    ):
        issues.append("foreign_translation_missing")
    return [copy.deepcopy(chinese), *[copy.deepcopy(resume) for resume in foreign]], issues


def extract_raw_text_from_html(html_str: str) -> str:
    soup = BeautifulSoup(str(html_str or ""), "html.parser")
    for h in soup.find_all(["header", "script", "style"]):
        h.decompose()
        
    main_el = soup.find("article", attrs={"data-role": "resume"}) or soup.find("main") or soup.body or soup
    block_tags = ["h1", "h2", "h3", "h4", "h5", "h6", "p", "tr", "li", "dt", "dd"]
    blocks = []
    
    for tag in main_el.find_all(block_tags):
        if tag.find(block_tags):
            continue
        t_text = re.sub(r"\s+", " ", tag.get_text(separator=" ", strip=True)).strip()
        if t_text:
            blocks.append(t_text)
            
    if not blocks:
        raw_full = main_el.get_text(separator=" | ", strip=True)
        blocks = [b.strip() for b in raw_full.split("|") if b.strip()]
        
    cleaned = []
    seen = set()
    for b in blocks:
        c = re.sub(r"\s+", " ", b).strip()
        if c and c not in seen:
            seen.add(c)
            cleaned.append(c)
            
    return " | ".join(cleaned)

def rebuild_raw_text(resumes: list[dict[str, Any]], html_str: str = "") -> str:
    if html_str:
        return extract_raw_text_from_html(html_str)
    parts: list[str] = []
    seen: set[str] = set()

    def add(value: Any) -> None:
        if isinstance(value, dict):
            for item in value.values():
                add(item)
        elif isinstance(value, list):
            for item in value:
                add(item)
        elif value not in (None, "", [], {}):
            text = re.sub(r"\s+", " ", str(value)).strip()
            if text and text not in seen:
                seen.add(text)
                parts.append(text)

    for resume in resumes:
        add(resume.get("base_info") or {})
        for collection in RESUME_LISTS:
            add(resume.get(collection) or [])
    return " | ".join(parts)


def latest_work(work: list[dict[str, Any]]) -> dict[str, Any]:
    if not work:
        return empty_object(CURRENT_FIELDS, {"employment_type": "全职"})
    selected = sorted(
        work,
        key=lambda row: (1 if not row.get("position_resigned") else 0, str(row.get("position_start") or "")),
        reverse=True,
    )[0]
    return normalize_row(selected, CURRENT_FIELDS)


def highest_education(education: list[dict[str, Any]]) -> dict[str, Any]:
    if not education:
        return empty_object(EDUCATION_FIELDS)
    selected = sorted(
        education,
        key=lambda row: (
            degree_rank(
                str(row.get("school_degree_rank") or ""),
                str(row.get("school_degree_type") or ""),
                str(row.get("school_name") or ""),
            ),
            str(row.get("school_end_ym") or ""),
        ),
        reverse=True,
    )[0]
    return normalize_row(selected, EDUCATION_FIELDS)


def parse_html_record(
    source: Path,
    html_path: Path,
    download_date: str,
    resume_index: int = 1,
) -> tuple[dict[str, Any], dict[str, Any]]:
    html_text = html_path.read_text(encoding="utf-8", errors="replace")
    soup = BeautifulSoup(html_text, "html.parser")
    resume_roots = semantic_resume_roots(soup)
    if resume_index < 1 or resume_index > len(resume_roots):
        raise IndexError(f"resume_index 超出范围：{resume_index}/{len(resume_roots)}")
    main = resume_roots[resume_index - 1]
    main_html = str(main)
    clean_text = strip_tags(main_html)

    legacy_parser = CodexGeminiHtmlSchemaParser()
    legacy = legacy_parser.parse(main_html, filename=source.name, source_path=str(source))
    legacy = extend_schema(legacy, clean_text, source.name, str(source))
    source_resumes = list(legacy.get("resumes") or [])
    if not source_resumes:
        source_resumes = [{"resume_languge": "zh", "base_info": legacy.get("base_info") or {}}]
    document_language = str((soup.html or {}).get("lang", "zh-CN")).casefold()
    language_code = "jp" if document_language.startswith("ja") else ("en" if document_language.startswith("en") else ("de" if document_language.startswith("de") else "zh"))

    # XLS DOMs can contain several language variants in one resume article.
    # The old path applied every explicit DOM field to only the document's
    # <html lang>, which cross-polluted bilingual records (and created fake
    # Chinese work/education rows).  Build a small scoped DOM article per
    # data-language-code and run the existing normalizer against that scope.
    variant_codes: list[str] = []
    for section in main.find_all("section"):
        code = str(section.get("data-language-code") or section.get("data-language") or "").strip().casefold()
        if code and code not in variant_codes:
            variant_codes.append("jp" if code == "ja" else code)
    if variant_codes:
        def legacy_for(code: str) -> dict[str, Any]:
            for candidate in source_resumes:
                candidate_code = str(candidate.get("resume_languge") or candidate.get("resume_language") or "").casefold()
                candidate_code = "jp" if candidate_code == "ja" else candidate_code
                if candidate_code == code:
                    return candidate
            return {"resume_languge": code, "base_info": {}}

        scoped_resumes: list[dict[str, Any]] = []
        for code in variant_codes:
            scoped_soup = BeautifulSoup(str(main), "html.parser")
            scoped_main = scoped_soup.find("article", attrs={"data-role": "resume"}) or scoped_soup
            for section in list(scoped_main.find_all("section")):
                section_code = str(section.get("data-language-code") or section.get("data-language") or "").strip().casefold()
                section_code = "jp" if section_code == "ja" else section_code
                if section_code != code:
                    section.decompose()
            scoped_resumes.append(normalize_resume(legacy_for(code), scoped_main, True))
        resumes = scoped_resumes
    else:
        dom_resume_index = next(
            (
                index for index, resume in enumerate(source_resumes)
                if str(resume.get("resume_languge") or resume.get("resume_language") or "").casefold() == language_code
            ),
            0,
        )
        resumes = [normalize_resume(resume, main, index == dom_resume_index) for index, resume in enumerate(source_resumes)]
    resumes, issues = ensure_chinese_first(resumes)
    if language_code != "zh":
        chinese_text = json.dumps(resumes[0], ensure_ascii=False)
        chinese_signal = len(re.findall(r"[\u4e00-\u9fff]", chinese_text))
        if chinese_signal < 20:
            issues.append("foreign_translation_missing")
            foreign_resume = next((resume for resume in resumes if resume.get("resume_languge") == language_code), resumes[-1])
            translated_identity = empty_object(BASE_FIELDS)
            for field in ("full_name", "age", "birth_date", "birth_year", "phone", "email", "platform_from", "platform_resume_id"):
                translated_identity[field] = foreign_resume.get("base_info", {}).get(field, "")
            gender = str(foreign_resume.get("base_info", {}).get("gender") or "")
            translated_identity["gender"] = "女" if gender.casefold() in {"female", "女"} else ("男" if gender.casefold() in {"male", "男"} else "")
            resumes[0] = {
                "resume_languge": "zh",
                "base_info": translated_identity,
                **{name: [] for name in RESUME_LISTS},
            }
    explicit_name_candidates = dom_field_values(main).get("full_name") or []
    explicit_name = next((value for value in explicit_name_candidates if plausible_name(value)), "")
    document_name = semantic_name_hint(main)
    path_name = filename_name_hint(source)
    resolved_name = normalize_name(explicit_name) if plausible_name(explicit_name) else ""
    if not resolved_name:
        parsed_name = str((resumes[0].get("base_info") or {}).get("full_name") or "")
        resolved_name = normalize_name(document_name or path_name or (parsed_name if plausible_name(parsed_name) else ""))
    if resolved_name:
        source_variant = next((resume for resume in resumes if resume.get("resume_languge") == language_code), resumes[-1])
        for resume in resumes:
            resume["base_info"]["full_name"] = resolved_name
            for field in ("phone", "email", "platform_from", "platform_resume_id"):
                if source_variant.get("base_info", {}).get(field) and not resume["base_info"].get(field):
                    resume["base_info"][field] = source_variant["base_info"][field]
    if not resolved_name:
        issues.append("resume_name_unreliable")
    primary = resumes[0]

    expected_info = (
        normalize_row(primary["expected_list"][0], EXPECTED_FIELDS)
        if primary["expected_list"]
        else empty_object(EXPECTED_FIELDS)
    )
    structured_data = {
        "base_info": copy.deepcopy(primary["base_info"]),
        "expected_info": expected_info,
        "current_info": latest_work(primary["work_experiences"]),
        "education_info": highest_education(primary["education_list"]),
        "resumes": resumes,
    }
    raw_text = extract_raw_text_from_html(main_html)
    fallback_date = download_date or datetime.fromtimestamp(source.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
    resume_date = updated_date(clean_text, fallback_date)
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    record = {
        "source": {
            "original_path": str(source.resolve()),
            "resume_index": resume_index,
            "resume_count": len(resume_roots),
            "candidate_key": str(main.get("data-candidate-key") or ""),
        },
        "dates": {
            "resume_updated_date": resume_date,
            "resume_download_date": fallback_date,
            "sys_created_date": now,
            "sys_updated_date": now,
        },
        "structured_data": structured_data,
        "raw_text": raw_text,
    }
    explicit_count = len(main.find_all(attrs={"data-field": True}))
    quality = {
        "parser_version": PARSER_VERSION,
        "source_resume_index": resume_index,
        "source_resume_count": len(resume_roots),
        "html_generator_version": (soup.find("article") or {}).get("data-generator-version", ""),
        "html_schema_version": (soup.find("article") or {}).get("data-schema-version", ""),
        "explicit_dom_field_count": explicit_count,
        "full_name": primary["base_info"].get("full_name", ""),
        "work_count": len(primary["work_experiences"]),
        "education_count": len(primary["education_list"]),
        "source_work_count": max((len(resume["work_experiences"]) for resume in resumes), default=0),
        "source_education_count": max((len(resume["education_list"]) for resume in resumes), default=0),
        "raw_text_length": len(raw_text),
        "issues": issues,
    }
    if not quality["full_name"] or not plausible_name(str(quality["full_name"])):
        quality["issues"].append("resume_name_unreliable")
    if not quality["source_work_count"] and not quality["source_education_count"]:
        quality["issues"].append("resume_structure_incomplete")
    quality["issues"] = list(dict.fromkeys(quality["issues"]))
    return record, quality


def process_map(map_path: Path, output_dir: Path, force: bool = False, limit: int = 0) -> dict[str, Any]:
    records = json.loads(map_path.read_text(encoding="utf-8"))
    if limit > 0:
        records = records[:limit]
    classifier = DocumentClassifier()
    report: dict[str, Any] = {
        "parser_version": PARSER_VERSION,
        "html_generator_version": GENERATOR_VERSION,
        "html_schema_version": SCHEMA_VERSION,
        "input_map": str(map_path.resolve()),
        "output_dir": str(output_dir.resolve()),
        "total": len(records),
        "total_source_files": len(records),
        "total_resume_articles": 0,
        "success": 0,
        "needs_review": 0,
        "skipped_existing": 0,
        "skipped_non_resume": 0,
        "skipped_superseded": 0,
        "failed": 0,
        "quality_issue_counts": {},
        "items": [],
    }
    started = time.monotonic()
    for index, item in enumerate(records, 1):
        source = Path(str(item.get("source_path") or ""))
        html_path = Path(str(item.get("html_path") or ""))
        row: dict[str, Any] = {"index": item.get("index", index), "source_path": str(source), "html_path": str(html_path)}
        try:
            if item.get("status") == "superseded":
                row.update(
                    status="skipped_superseded",
                    reason=item.get("error_reason") or "同一候选人的旧版本",
                    superseded_by=item.get("superseded_by") or "",
                )
                report["skipped_superseded"] += 1
                report["items"].append(row)
                continue
            if not source.is_file():
                raise FileNotFoundError("源文件不存在")
            if not html_path.is_file():
                raise FileNotFoundError("HTML 不存在")
            html_text = html_path.read_text(encoding="utf-8", errors="replace")
            soup = BeautifulSoup(html_text, "html.parser")
            resume_roots = semantic_resume_roots(soup)
            report["total_resume_articles"] += len(resume_roots)
            outputs: list[dict[str, Any]] = []
            for resume_index, resume_root in enumerate(resume_roots, 1):
                main_text = strip_tags(str(resume_root))
                classification = classifier.classify(main_text, source.name)
                output_row: dict[str, Any] = {
                    "resume_index": resume_index,
                    "candidate_key": str(resume_root.get("data-candidate-key") or ""),
                    "document_type": classification.document_type,
                }
                if classification.document_type not in {"resume", "ambiguous_resume"}:
                    output_row.update(status="skipped_non_resume", reason=classification.reason)
                    report["skipped_non_resume"] += 1
                else:
                    record, quality = parse_html_record(
                        source,
                        html_path,
                        str(item.get("download_date") or ""),
                        resume_index=resume_index,
                    )
                    full_name = str((record["structured_data"]["base_info"] or {}).get("full_name") or "待确认姓名")
                    record_hash = source_hash(f"{source}#resume:{resume_index}")
                    output_path = output_dir / f"{safe_output_name(full_name)}_{record_hash}.json"
                    if output_path.exists() and not force:
                        output_row.update(status="skipped_existing", output_path=str(output_path), quality=quality)
                        report["skipped_existing"] += 1
                    else:
                        atomic_write_json(output_path, record)
                        output_status = "needs_review" if quality["issues"] else "success"
                        output_row.update(status=output_status, output_path=str(output_path), quality=quality)
                        report[output_status] += 1
                    for issue in quality["issues"]:
                        counts = report["quality_issue_counts"]
                        counts[issue] = counts.get(issue, 0) + 1
                outputs.append(output_row)
            row["resume_count"] = len(resume_roots)
            row["outputs"] = outputs
            output_statuses = {str(output.get("status") or "") for output in outputs}
            row["status"] = (
                "failed" if "failed" in output_statuses else
                "needs_review" if "needs_review" in output_statuses else
                "success" if "success" in output_statuses else
                "skipped_existing" if "skipped_existing" in output_statuses else
                "skipped_non_resume"
            )
        except Exception as exc:
            row.update(status="failed", error=str(exc))
            report["failed"] += 1
        report["items"].append(row)
        if index % 50 == 0 or index == len(records):
            elapsed = time.monotonic() - started
            speed = index / elapsed if elapsed else 0
            print(
                f"进度 [{index}/{len(records)}] success={report['success']} review={report['needs_review']} non-resume={report['skipped_non_resume']} "
                f"failed={report['failed']} {speed:.1f} 文件/秒" f" / Progress [{index}/{len(records)}] success={report['success']} review={report['needs_review']} non-resume={report['skipped_non_resume']} failed={report['failed']} {speed:.1f} files/s / 進捗 [{index}/{len(records)}] success={report['success']} review={report['needs_review']} non-resume={report['skipped_non_resume']} failed={report['failed']} {speed:.1f} ファイル/秒",
                flush=True,
            )
    report["completed_at"] = datetime.now().astimezone().isoformat()
    report_path = output_dir / "_word_html_to_json_report.json"
    atomic_write_json(report_path, report)
    print(json.dumps({key: value for key, value in report.items() if key != "items"}, ensure_ascii=False, indent=2))
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="语义 Word HTML → complete-v1 JSON" " / Semantic Word HTML → complete-v1 JSON / 意味付き Word HTML → complete-v1 JSON")
    parser.add_argument(
        "--map",
        type=Path,
        default=PROJECT_ROOT / _rc.dirname("complete-transfered-htmls") / "docs" / "word_conversion_map.json",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / _rc.dirname("complete-transfered-jsons") / _rc.dirname("complete-v1-rebuilt"),
    )
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    process_map(args.map, args.output_dir, force=args.force, limit=args.limit)
