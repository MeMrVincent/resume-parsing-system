"""独立的 XLS 简历重建入口。

这个入口不改动旧的 XLS/Word 解析模块：复用它们的 Excel 网格读取、HTML
生成和基础 JSON schema，再在本模块完成 XLS 特有的 DOM 重新绑定，并把
HTML 原文写入 raw_text。

EN: Standalone XLS résumé rebuild entry point.

This entry point does not change the old XLS/Word parsing modules: it reuses their Excel grid reading, HTML
generation and base JSON schema, then performs the XLS-specific DOM rebinding in this module and writes the
original HTML into raw_text.

JA: 独立した XLS 履歴書の再構築エントリ。

このエントリは旧来の XLS/Word 解析モジュールを変更しない。Excel グリッドの読み取り・HTML
生成・基本の JSON スキーマを再利用し、XLS 特有の DOM の再バインドを本モジュールで行い、
HTML の原文を raw_text に書き込む。
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
import json
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup, NavigableString, Tag

ROOT = _rc.project_root()
sys.path.insert(0, str(_rc.PYTHON_DIR / "v2"))

import process_xls_to_html as xls_html  # noqa: E402
from process_word_html_to_json import (  # noqa: E402
    BASE_FIELDS as WORD_BASE_FIELDS,
    COLLECTION_FIELDS,
    EDUCATION_FIELDS,
    EXPECTED_FIELDS,
    WORK_FIELDS,
    highest_education,
    latest_work,
    normalize_row,
    parse_html_record,
    plausible_name,
    safe_output_name,
    source_hash,
)
from reuse_complete_v1_jsons import validate_json  # noqa: E402
from process_word_to_html import strip_tags  # noqa: E402


BASE_FIELDS = {
    "full_name", "gender", "age", "birth_date", "birth_year", "marital_status",
    "household_registration", "address", "phone", "email", "political_status", "height_cm",
    "weight_kg", "city", "nationality",
}


def normalize_name(value: Any) -> str:
    """Local V2 name cleanup; the legacy Word module never exported it."""
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    text = re.sub(r"^(?:姓名|氏名|Name)\s*[:：]?\s*", "", text, flags=re.I)
    return text.strip(" ：:|｜_-.")
LANGUAGE_NAME_MAP = {
    "日本語": "日语", "日语": "日语", "英語": "英语", "英语": "英语",
    "Japanese": "日语", "English": "英语", "japanese": "日语", "english": "英语",
    "中国語": "中文", "中文": "中文", "上海語": "上海话", "上海话": "上海话",
    "韓国語": "韩语", "韩语": "韩语", "ドイツ語": "德语", "德语": "德语",
}
PROFILE_ALIASES = {
    "full_name": {"姓名", "氏名", "名字", "name"},
    "gender": {"性别", "性別", "gender", "sex"},
    "age": {"年龄", "年齢", "age"},
    "birth_date": {"出生日期", "出生年月", "出生年月日", "生年月日", "birthday", "date of birth"},
    "marital_status": {"婚姻状况", "婚姻状況", "婚姻状态", "marital status"},
    "political_status": {"政治面貌", "政治状况", "政治状況", "political status", "citizenship"},
    "household_registration": {"户籍", "戶籍", "户口", "戸籍", "戸口", "hukou"},
    "address": {"地址", "现住址", "现居住地", "居住地址", "現住所", "住所", "住址", "residency"},
    "city": {"籍贯", "出身地", "城市", "所在城市", "city"},
    "phone": {"电话", "手机", "联系电话", "家里电话", "固定电话", "固定電話", "携帯", "携帯電話", "携帯tel", "telephone", "mobile phone", "cell phone", "phone number", "tel"},
    "email": {"邮箱", "邮件", "邮件地址", "メールアドレス", "e-mail", "email"},
    "height_cm": {"身高", "身長", "height"},
    "weight_kg": {"体重", "体重", "weight"},
    "nationality": {"国籍", "民族", "nation", "nationality", "照片", "照 片", "photo"},
}
WORK_ALIASES = {
    "company_name": {"公司", "公司名", "公司名称", "会社名", "勤務先", "company", "employer"},
    "company_industry": {"行业", "所属行业", "业界", "業界", "業種", "industry"},
    "company_nature": {"公司性质", "公司性質", "企业性质", "会社形態", "企業背景", "性质", "資本", "type of company"},
    "company_employees": {"公司规模", "员工人数", "员工数量", "従業員数", "社員数", "规模", "規模", "company size"},
    "position": {"职位", "职位名称", "职务", "職務", "職位", "役職", "ポジション", "position"},
    "position_dept": {"部门", "部门名称", "部署", "所属部署", "所属部门", "所属部門", "部属", "所属", "department"},
    "position_subordinate": {"下属人数", "部下人数", "部下", "subordinates"},
    "position_responsibilities": {"工作描述", "工作内容", "工作职责", "仕事内容", "職務内容", "業務内容", "job description"},
    "resigned_reason": {"离职原因", "离职理由", "退职理由", "退職理由", "reason of dimission", "reason for leaving"},
}
WORK_ALIASES["position_start"] = {"入职年月", "入社年月", "开始时间", "開始時間"}
WORK_ALIASES["position_resigned"] = {"退职年月", "退社年月", "结束时间", "終了時間"}
# These labels are common in the XLS bilingual work tables but were absent
# from the original binding map.  Bind them in the HTML stage so downstream
# parsers see a semantic DOM node instead of having to infer the value later.
WORK_ALIASES["company_industry"].update({
    "经营内容", "事業概要", "业务内容", "業務概要", "业种/事业内容", "業種/事業内容", "業界詳細",
})
WORK_ALIASES["company_nature"].update({"資本形態", "企業形態"})
WORK_ALIASES["company_nature"].update({"会社性質", "会社性质"})
WORK_ALIASES["company_employees"].update({"会社人数"})
WORK_ALIASES["position_subordinate"].update({"部門人数", "下属人数"})
WORK_ALIASES["position_report_to"] = {"汇报对象", "報告対象", "汇报对象", "報告先", "report to"}
WORK_ALIASES["company_name"].update({"Company Name", "Employer"})
WORK_ALIASES["company_industry"].update({"Industry", "Business"})
WORK_ALIASES["company_nature"].update({"Type of Company"})
WORK_ALIASES["position"].update({"Job Title", "Position"})
WORK_ALIASES["position_dept"].update({"Department", "Division"})
WORK_ALIASES["position_responsibilities"].update({"Job Description", "Work Description"})
WORK_ALIASES["position_start"].update({"Working Period", "Time Period", "Start Date"})
WORK_ALIASES["position_resigned"].update({"End Date"})


def norm_label(value: str) -> str:
    return re.sub(r"[\s:：|｜()（）【】\[\]]+", "", value or "").casefold()


def normalize_phone_value(value: str) -> str:
    """Canonicalize contact numbers for JSON values and output filenames.

    Local numbers are kept as digits only.  For an explicitly international
    number (a leading ``+``), preserve the country-code separator and remove
    formatting from the subscriber number, e.g. ``+86-138-1606-5985`` becomes
    ``+86-13800000004``.
    """
    text = unicodedata.normalize("NFKC", str(value or "")).strip()
    if not text:
        return ""
    if text.startswith("+"):
        body = text[1:]
        # Existing source data normally writes the country code before the
        # first hyphen.  Preserve that semantic boundary while compacting the
        # rest of the number.
        match = re.match(r"\s*(\d{1,3})\s*[-\u2010-\u2015\u2212\s]+(.*)$", body)
        if match:
            country = match.group(1)
            subscriber = re.sub(r"\D", "", match.group(2))
            return f"+{country}-{subscriber}" if subscriber else f"+{country}"
        digits = re.sub(r"\D", "", body)
        return f"+{digits}" if digits else ""
    return re.sub(r"\D", "", text)


def normalize_record_contacts(record: dict[str, Any]) -> None:
    for resume in (record.get("structured_data") or {}).get("resumes") or []:
        base = resume.get("base_info") or {}
        if base.get("phone"):
            base["phone"] = normalize_phone_value(base.get("phone"))
        if base.get("email"):
            base["email"] = re.sub(r"\s*@\s*", "@", str(base.get("email") or "")).replace(" ", "")
    resumes = (record.get("structured_data") or {}).get("resumes") or []
    if resumes:
        (record.setdefault("structured_data", {}))["base_info"] = copy.deepcopy(resumes[0].get("base_info") or {})


def date_only_company(value: str) -> bool:
    text = unicodedata.normalize("NFKC", str(value or "")).strip()
    return bool(re.fullmatch(
        r"(?:19|20)\d{2}\s*[./-]\s*\d{1,2}\s*[-~～至－]\s*(?:(?:19|20)\d{2}\s*[./-]\s*\d{1,2}|至今|现在|現職)"
        r"(?:\s*[（(][^）)]*(?:年|月|year|month|month[s]?)[^）)]*[）)])?",
        text,
        re.IGNORECASE,
    ))


def bad_company_binding(value: str) -> bool:
    text = unicodedata.normalize("NFKC", str(value or "")).strip()
    if date_only_company(text):
        return True
    return bool(re.search(r"[（(]\s*\d+\s*(?:年|个月|月|year|years|month|months)[^）)]*[）)]?\s*$", text, re.IGNORECASE))


def strip_company_duration(value: str) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).strip()
    return re.sub(r"\s*[（(]\s*\d+\s*(?:年|个月|月|year|years|month|months)[^）)]*[）)]?\s*$", "", text, flags=re.IGNORECASE).strip()


def source_work_companies(source: str) -> list[dict[str, str]]:
    """Extract date/company pairs from the original XLS work table.

    Several bilingual templates put the Chinese company and the English
    duration in adjacent cells.  The generic DOM binder can otherwise attach
    the English duration cell to ``company_name``.  The source grid is used
    only for those date-only bindings.
    """
    path = Path(source)
    if not path.is_file():
        return []
    date_re = re.compile(r"((?:19|20)\d{2})\s*[./-]\s*(\d{1,2})\s*[-~～至－]\s*((?:(?:19|20)\d{2})\s*[./-]\s*(\d{1,2})|至今|现在|現職)")
    duration_re = re.compile(r"\s*[（(]?\s*\d+\s*(?:年|个月|月|year|month|months?)(?:\s*\d+\s*(?:个月|月|months?))?\s*[）)]?\s*$", re.IGNORECASE)
    result: list[dict[str, str]] = []
    try:
        grids = xls_html.read_excel_grid(path)
    except Exception:
        return result
    for _sheet, grid in grids:
        # Horizontal Japanese templates place 社名/公司名称 on one row and
        # 期間/任职时间 on another row at the same column positions.
        for row_index, row in enumerate(grid):
            labels = [unicodedata.normalize("NFKC", str(getattr(cell, "val", "") or "")).strip() for cell in row]
            if not any(value in {"期間", "期间", "任职时间", "工作时间", "在职期间"} for value in labels):
                continue
            company_row = None
            for previous in range(max(0, row_index - 3), row_index):
                candidate = [unicodedata.normalize("NFKC", str(getattr(cell, "val", "") or "")).strip() for cell in grid[previous]]
                if any(value in {"社名", "公司", "公司名称", "会社名", "勤務先"} for value in candidate):
                    company_row = candidate
                    break
            if company_row is None:
                continue
            for index, value in enumerate(labels):
                match = date_re.search(value)
                if not match:
                    continue
                company = company_row[index] if index < len(company_row) else ""
                if not company or company in {"社名", "公司", "公司名称", "会社名", "勤務先"}:
                    continue
                start = f"{match.group(1)}年{int(match.group(2)):02d}月"
                end_raw = match.group(3).replace(" ", "")
                parts = re.split(r"[./-]", end_raw)
                end = "" if end_raw in {"至今", "现在", "現職"} else f"{parts[0]}年{int(parts[1]):02d}月"
                result.append({"start": start, "end": end, "company": company})
        for row in grid:
            cells = [unicodedata.normalize("NFKC", str(getattr(cell, "val", "") or "")).replace("\r", " ").replace("\n", " ").strip() for cell in row]
            matches = [(index, date_re.search(value)) for index, value in enumerate(cells)]
            matches = [(index, match) for index, match in matches if match]
            if not matches:
                continue
            index, match = matches[0]
            start = f"{match.group(1)}年{int(match.group(2)):02d}月"
            end_raw = match.group(3).replace(" ", "")
            parts = re.split(r"[./-]", end_raw)
            end = "" if end_raw in {"至今", "现在", "現職"} else f"{parts[0]}年{int(parts[1]):02d}月"
            company = ""
            for value in cells:
                m = date_re.search(value)
                if not m:
                    continue
                candidate = value[m.end():].strip(" ：:－-~～")
                candidate = duration_re.sub("", candidate).strip(" ：:－-~～（）()")
                if candidate and not re.fullmatch(r"[\d\s年月yearmonth.,]+", candidate, re.IGNORECASE):
                    # Prefer a value containing CJK characters; an adjacent
                    # English duration/demo cell is not a company name.
                    if re.search(r"[\u3040-\u30ff\u3400-\u9fff]", candidate):
                        company = candidate
                        break
            if company:
                result.append({"start": start, "end": end, "company": company})
    deduped: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for item in result:
        signature = (item["start"], item["end"], item["company"])
        if signature not in seen:
            seen.add(signature)
            deduped.append(item)
    return deduped


def repair_date_only_work_companies(record: dict[str, Any], source: str) -> None:
    resumes = (record.get("structured_data") or {}).get("resumes") or []
    source_rows = source_work_companies(source)
    if not source_rows:
        # Even without source rows, remove a trailing duration from an
        # otherwise usable company name.
        for resume in resumes:
            for work in resume.get("work_experiences") or []:
                if bad_company_binding(str(work.get("company_name") or "")):
                    cleaned = strip_company_duration(str(work.get("company_name") or ""))
                    if cleaned and not date_only_company(cleaned):
                        work["company_name"] = cleaned
        return
    for resume in resumes:
        works = resume.get("work_experiences") or []
        used: set[int] = set()
        for work in works:
            start = normalize_resume_date(str(work.get("position_start") or ""))
            end = normalize_resume_date(str(work.get("position_resigned") or ""), end=True)
            exact = [
                (idx, row) for idx, row in enumerate(source_rows)
                if idx not in used and (not start or normalize_resume_date(row["start"]) == start)
                and (not end or normalize_resume_date(row["end"], end=True) == end)
            ]
            if len(exact) == 1:
                idx, row = exact[0]
                work["company_name"] = row["company"]
                used.add(idx)
                continue
            if not bad_company_binding(str(work.get("company_name") or "")):
                continue
            candidates = exact
            if not candidates:
                candidates = [(idx, row) for idx, row in enumerate(source_rows) if idx not in used]
            if candidates:
                idx, row = candidates[0]
                work["company_name"] = row["company"]
                used.add(idx)
            else:
                cleaned = strip_company_duration(str(work.get("company_name") or ""))
                if cleaned and not date_only_company(cleaned):
                    work["company_name"] = cleaned


def repair_date_only_work_dom(html_text: str, source: str) -> str:
    """Replace date/duration demo values in bound company DOM nodes."""
    source_rows = source_work_companies(source)
    if not source_rows:
        return html_text
    soup = BeautifulSoup(html_text, "html.parser")
    for node in soup.find_all(attrs={"data-field": "company_name"}):
        value = node.get_text(" ", strip=True)
        if not bad_company_binding(value):
            continue
        row = node.find_parent("tr")
        start_node = row.find(attrs={"data-field": "position_start"}) if row else None
        end_node = row.find(attrs={"data-field": "position_resigned"}) if row else None
        start = normalize_resume_date(start_node.get_text(" ", strip=True)) if start_node else ""
        end = normalize_resume_date(end_node.get_text(" ", strip=True), end=True) if end_node else ""
        candidates = [
            item for item in source_rows
            if (not start or normalize_resume_date(item["start"]) == start)
            and (not end or normalize_resume_date(item["end"], end=True) == end)
        ]
        if candidates:
            node.clear()
            node.append(candidates[0]["company"])
    return str(soup)


def source_education_rows(source: str) -> list[dict[str, str]]:
    path = Path(source)
    if not path.is_file():
        return []
    date_re = re.compile(r"((?:19|20)\d{2})\s*[./-]\s*(\d{1,2})\s*[-~～至－]\s*((?:(?:19|20)\d{2})\s*[./-]\s*(\d{1,2})|至今|现在|現職)")
    degrees = ("博士", "硕士", "研究生", "本科", "大专", "中专", "专科", "大学院", "大学", "短大", "Associate", "Bachelor", "Master", "Doctor", "Secondary Specialized")
    try:
        grids = xls_html.read_excel_grid(path)
    except Exception:
        return []
    result: list[dict[str, str]] = []
    for _sheet, grid in grids:
        for row in grid:
            cells = [unicodedata.normalize("NFKC", str(getattr(cell, "val", "") or "")).replace("\r", " ").replace("\n", " ").strip() for cell in row]
            date_match = next((date_re.search(value) for value in cells if date_re.search(value)), None)
            if not date_match:
                continue
            start = f"{date_match.group(1)}年{int(date_match.group(2)):02d}月"
            end_raw = date_match.group(3).replace(" ", "")
            end = "" if end_raw in {"至今", "现在", "現職"} else re.sub(r"[./-]", "年", end_raw) + "月"
            candidate = ""
            for value in cells:
                match = date_re.search(value)
                if not match:
                    continue
                tail = value[match.end():].strip(" ：:－-~～")
                if re.search(r"[\u3040-\u30ff\u3400-\u9fff]", tail) and tail not in {"至今", "现在", "現職"}:
                    candidate = tail
                    break
            if not candidate:
                continue
            degree = next((item for item in degrees if re.search(re.escape(item) + r"\s*$", candidate, re.IGNORECASE)), "")
            if degree:
                candidate = re.sub(re.escape(degree) + r"\s*$", "", candidate, flags=re.IGNORECASE).strip(" /|｜")
            major = ""
            if degree:
                parts = re.split(r"\s+", candidate)
                if len(parts) > 1:
                    major = parts[-1]
                    candidate = " ".join(parts[:-1]).strip()
            result.append({"start": start, "end": end, "school": candidate, "major": major, "degree": degree})
    return result


def repair_date_only_education(record: dict[str, Any], source: str) -> None:
    resumes = (record.get("structured_data") or {}).get("resumes") or []
    education = source_education_rows(source)
    if not education:
        return
    for resume in resumes:
        for item in resume.get("education_list") or []:
            school = str(item.get("school_name") or "")
            if school and not (date_only_company(school) or school in {"至今", "现在", "現職"} or re.search(r"Associate|Secondary Specialized|Bachelor|Master|本科|大专|中专|硕士|博士", school, re.IGNORECASE)):
                continue
            start = normalize_resume_date(str(item.get("school_start_ym") or ""))
            end = normalize_resume_date(str(item.get("school_end_ym") or ""), end=True)
            candidates = [row for row in education if (not start or normalize_resume_date(row["start"]) == start) and (not end or normalize_resume_date(row["end"], end=True) == end)]
            if candidates:
                row = candidates[0]
                item["school_name"] = row["school"]
                if row["major"]:
                    item["school_major_name"] = row["major"]
                if row["degree"]:
                    item["school_degree_type"] = row["degree"]


def repair_date_only_education_dom(html_text: str, source: str) -> str:
    education = source_education_rows(source)
    if not education:
        return html_text
    soup = BeautifulSoup(html_text, "html.parser")
    for row_node in soup.find_all("tr", attrs={"data-record-type": "education"}):
        school_node = row_node.find(attrs={"data-field": "school_name"})
        if not school_node:
            continue
        school_value = school_node.get_text(" ", strip=True)
        if school_value not in {"至今", "现在", "現職"} and not re.search(r"Associate|Bachelor|Master|本科|大专|硕士|博士", school_value, re.IGNORECASE):
            continue
        start_node = row_node.find(attrs={"data-field": "school_start_ym"})
        start = normalize_resume_date(start_node.get_text(" ", strip=True)) if start_node else ""
        candidates = [item for item in education if not start or normalize_resume_date(item["start"]) == start]
        if not candidates:
            continue
        item = candidates[0]
        school_node.clear()
        school_node.append(item["school"])
        unbound = [cell for cell in row_node.find_all(["td", "th"], recursive=False) if not cell.get("data-field") and cell.get_text(" ", strip=True)]
        if unbound:
            cell = unbound[0]
            cell.clear()
            if item["major"]:
                node = soup.new_tag("span", attrs={"data-field": "school_major_name", "label": "专业"})
                node.string = item["major"]
                cell.append(node)
            if item["degree"]:
                node = soup.new_tag("span", attrs={"data-field": "school_degree_type", "label": "学历"})
                node.string = item["degree"]
                cell.append(node)
    return str(soup)


def field_for(value: str, aliases: dict[str, set[str]]) -> str:
    key = norm_label(value)
    for field, names in aliases.items():
        if key in {norm_label(item) for item in names}:
            return field
    return ""


def cells_with_ranges(row: Tag) -> list[tuple[Tag, int, int]]:
    result: list[tuple[Tag, int, int]] = []
    pos = 0
    for cell in row.find_all(["td", "th"], recursive=False):
        try:
            span = max(1, int(cell.get("colspan") or 1))
        except (TypeError, ValueError):
            span = 1
        result.append((cell, pos, pos + span - 1))
        pos += span
    return result


def clean_node_fields(node: Tag, fields: set[str]) -> None:
    for child in [node, *node.find_all(attrs={"data-field": True})]:
        if str(child.get("data-field") or "") in fields:
            child.attrs.pop("data-field", None)
            child.attrs.pop("label", None)


def valid_profile(field: str, value: str) -> bool:
    value = re.sub(r"\s+", " ", value or "").strip()
    if not value:
        return False
    if field == "phone":
        return bool(re.search(r"(?<!\d)(?:\d[\d ()+./-]{6,}\d|\d{3,4}[－-]\d{3,4}[－-]\d{3,4})(?:\.0)?(?!\d)", value))
    if field == "email":
        return bool(re.search(r"[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}", value, re.I))
    if field == "gender":
        return bool(re.fullmatch(r"男|女|男性|女性|male|female", value, re.I))
    if field == "marital_status":
        return bool(re.fullmatch(r"(?:未婚|已婚|既婚|独身|单身|离异|离婚|single|married|divorced)(?:.*)?", value, re.I))
    if field in {"age", "height_cm", "weight_kg"}:
        return bool(re.search(r"\d", value))
    if field == "birth_date":
        return bool(re.search(r"(?:19|20)\d{2}", value))
    # Recruitment-export header/demo cells are frequently adjacent to the
    # actual row values (e.g. 户口|现在单位|学校名称).  They are labels, never
    # profile values.  Reject a value containing multiple such labels as well
    # as the common single-cell placeholders.
    demo_labels = {
        "通讯地址", "户口", "现在单位", "现在（前）单位", "学校名称", "专业名称",
        "最高学历", "期望月薪", "期望月薪(税前)", "政治面貌", "Political Status",
        "Citizenship", "联系电话", "Phone", "目前居住地", "移动电话", "电子邮件",
    }
    normalized_value = norm_label(value)
    normalized_demo = {norm_label(item) for item in demo_labels}
    if normalized_value in normalized_demo:
        return False
    if sum(1 for item in normalized_demo if item and item in normalized_value) >= 2:
        return False
    if field == "political_status" and re.search(r"(?:联系电话|phone|手机|电话|@|\d{7,})", value, re.I):
        return False
    if field == "full_name" and re.search(r"姓名|氏名|最高学历|最高学歴|学历|学歴|留学经验|留学経験|性别|性別|婚姻|出生|年龄|年齢", value):
        return False
    if field == "nationality" and re.search(r"最高学历|最高学歴|学历|学歴|留学经验|留学経験|民族|国籍", value):
        return False
    # A value that is itself another profile header is never a value.  This
    # matters for merged Excel cells where a header row can be mistaken for
    # the value immediately below it (for example 国籍=“現在状況”).
    if field_for(value, PROFILE_ALIASES):
        return False
    return not norm_label(value) in {norm_label(x) for x in PROFILE_ALIASES.get(field, set())}


def bind_profile_tables(soup: BeautifulSoup) -> None:
    """Rebind profile headers/values both horizontally and vertically."""
    for section in soup.find_all("section"):
        # Do not let collection rows overwrite work/education fields.
        if section.get("data-collection"):
            continue
        for node in section.find_all(attrs={"data-field": True}):
            if str(node.get("data-field") or "") in BASE_FIELDS:
                node.attrs.pop("data-field", None)
                node.attrs.pop("label", None)
        for table in section.find_all("table"):
            rows = table.find_all("tr")
            for row_index, row in enumerate(rows):
                cells = cells_with_ranges(row)
                if not cells:
                    continue
                # Same-row label/value pairs: 現住所|地址, 戸籍|上海, 婚姻状況|既婚.
                for index, (cell, _start, _end) in enumerate(cells[:-1]):
                    field = field_for(cell.get_text(" ", strip=True), PROFILE_ALIASES)
                    if not field:
                        continue
                    value_cell = next(
                        (
                            item[0] for item in cells[index + 1:]
                            if item[0].get_text(" ", strip=True)
                            and not field_for(item[0].get_text(" ", strip=True), PROFILE_ALIASES)
                        ),
                        None,
                    )
                    if value_cell is None:
                        continue
                    value = value_cell.get_text(" ", strip=True)
                    if valid_profile(field, value):
                        clean_node_fields(value_cell, BASE_FIELDS)
                        value_cell["data-field"] = field
                        value_cell["label"] = cell.get_text(" ", strip=True)

                # Header row followed by value row. Use physical column ranges
                # so merged cells do not shift gender/phone/email by one slot.
                if row_index + 1 >= len(rows):
                    continue
                labels = [
                    (cell, start, end, field_for(cell.get_text(" ", strip=True), PROFILE_ALIASES))
                    for cell, start, end in cells
                ]
                labels = [item for item in labels if item[3]]
                if len(labels) < 3:
                    continue
                below = cells_with_ranges(rows[row_index + 1])
                for label_cell, start, end, field in labels:
                    midpoint = (start + end) / 2
                    target = next((item[0] for item in below if item[1] <= midpoint <= item[2]), None)
                    if target is None:
                        continue
                    value = target.get_text(" ", strip=True)
                    if field_for(value, PROFILE_ALIASES) or not valid_profile(field, value):
                        continue
                    clean_node_fields(target, BASE_FIELDS)
                    target["data-field"] = field
                    target["label"] = label_cell.get_text(" ", strip=True)

            # Rows where the value row carries only name, gender and birth date.
            for row in rows:
                name = row.find(attrs={"data-field": "full_name"})
                if not name:
                    continue
                parent = name if name.name in {"td", "th"} else name.find_parent(["td", "th"])
                if not parent:
                    continue
                cells = [cell for cell, *_ in cells_with_ranges(row)]
                try:
                    after = cells[cells.index(parent) + 1:]
                except ValueError:
                    after = []
                gender = next((cell for cell in after if valid_profile("gender", cell.get_text(" ", strip=True))), None)
                if gender:
                    clean_node_fields(gender, BASE_FIELDS)
                    gender["data-field"] = "gender"
                    gender["label"] = "性别"
                birth = next((cell for cell in after if re.search(r"(?:19|20)\d{2}.*\d{1,2}.*月", cell.get_text(" ", strip=True))), None)
                if birth:
                    clean_node_fields(birth, BASE_FIELDS)
                    birth["data-field"] = "birth_date"
                    birth["label"] = "生日"
                    age = re.search(r"(?:满|満|Age\s*)(\d{1,3})\s*(?:岁|歳)?", birth.get_text(" ", strip=True), re.I)
                    if age:
                        child = soup.new_tag("span", attrs={"data-field": "age", "label": "年龄"})
                        child.string = age.group(1)
                        birth.append(child)

    # Contacts are unambiguous and should never retain an old wrong binding.
    for node in soup.find_all(attrs={"data-field": True}):
        if node.get("data-field") in {"phone", "email"}:
            node.attrs.pop("data-field", None)
            node.attrs.pop("label", None)
    for cell in soup.find_all(["td", "th", "p", "div"]):
        text = cell.get_text(" ", strip=True)
        email = re.search(r"[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}", text, re.I)
        phone = re.search(r"(?<!\d)(?:1[3-9]\d{9}|[789]0\d{8,10}|\d{3,4}[－-]\d{3,4}[－-]\d{3,4})(?:\.0)?(?!\d)", text)
        for field, match in (("email", email), ("phone", phone)):
            if not match:
                continue
            # Never append the matched text: that changes HTML-derived
            # raw_text and duplicates phone/email values.  Bind the existing
            # cell when it is a pure value; labelled cells remain untouched
            # and are still available to the legacy parser as text.
            value = match.group(0).removesuffix(".0")
            if re.sub(r"\s+", "", text) == re.sub(r"\s+", "", value):
                clean_node_fields(cell, {"phone", "email"})
                cell["data-field"] = field
                cell["label"] = field
            elif not cell.find(attrs={"data-field": field}):
                for text_node in list(cell.find_all(string=True)):
                    raw = str(text_node)
                    if value not in raw:
                        continue
                    before, after = raw.split(value, 1)
                    span = soup.new_tag("span", attrs={"data-field": field, "label": field})
                    span.string = value
                    replacements: list[Any] = []
                    if before:
                        replacements.append(NavigableString(before))
                    replacements.append(span)
                    if after:
                        replacements.append(NavigableString(after))
                    text_node.replace_with(*replacements)
                    break


def bind_inline_profile_labels(soup: BeautifulSoup) -> None:
    """Bind compact one-cell profile rows from their inline label spans.

    Templates such as 王雯婷's use ``<span data-label-for=姓名><i>值``
    instead of separate label/value cells.  Without this HTML-stage pass the
    legacy parser shifts adjacent values (户籍=“上海性别：女”, 地址=“邮编”).
    """
    for label_node in soup.find_all(attrs={"data-label-for": True}):
        field = str(label_node.get("data-label-for") or "").strip()
        if field not in BASE_FIELDS:
            continue
        # Find the next sibling value up to the next inline label.  Prefer a
        # direct <i>/<b>/<span> value, but also accept a non-empty text node.
        value_node: Tag | None = None
        sibling = label_node.next_sibling
        while sibling is not None:
            if isinstance(sibling, Tag) and sibling.has_attr("data-label-for"):
                break
            if isinstance(sibling, Tag) and sibling.get_text(" ", strip=True):
                value_node = sibling
                break
            if isinstance(sibling, NavigableString) and str(sibling).strip():
                value_node = label_node.parent
                break
            sibling = sibling.next_sibling
        if value_node is None:
            continue
        value = value_node.get_text(" ", strip=True)
        # The parent cell may include the next label; only bind a pure value
        # node, never the whole mixed label/value cell.
        if field == "full_name":
            value = re.sub(r"\s+", "", value)
        if not valid_profile(field, value):
            continue
        clean_node_fields(value_node, BASE_FIELDS)
        value_node["data-field"] = field
        value_node["label"] = field


def bind_work_and_education(soup: BeautifulSoup) -> None:
    work_nodes = list(soup.find_all(attrs={"data-record-type": "work_experience"}))
    # Some XLS templates (notably the English translation block) have no
    # record wrapper at all.  Their section is still semantically identifiable
    # and each value cell can be bound from its adjacent label.
    work_nodes.extend(
        section for section in soup.find_all("section", attrs={"data-section-type": "work_experiences"})
        if section not in work_nodes
    )
    work_nodes.extend(
        section for section in soup.find_all("section", attrs={"data-collection": "training_list"})
        if section not in work_nodes
    )
    for record in work_nodes:
        rows = [record] if record.name == "tr" else record.find_all("tr")
        for row in rows:
            cells = [item[0] for item in cells_with_ranges(row)]
            # The XLS generator may have attached a plausible but wrong
            # field to the label cell itself (e.g. 行业 -> company_name).
            # Clear all legacy work bindings for the whole row first; the
            # adjacent label/value pass below then writes the authoritative
            # semantic DOM attributes.
            for cell in cells:
                clean_node_fields(cell, set(WORK_ALIASES))
            for index, cell in enumerate(cells[:-1]):
                field = field_for(cell.get_text(" ", strip=True), WORK_ALIASES)
                if not field:
                    continue
                value = next(
                    (
                        item for item in cells[index + 1:]
                        if item.get_text(" ", strip=True)
                        and not field_for(item.get_text(" ", strip=True), WORK_ALIASES)
                    ),
                    None,
                )
                if value is None:
                    continue
                value_text = value.get_text(" ", strip=True)
                value_key = value_text.strip("：: ")
                if value_key in {"公司名", "公司名称", "会社名", "其他", "その他", "（系）", "(系)", "规模", "性质", "地点", "場所", "部门", "职位", "部下", "经营内容", "工作内容", "离职理由", "入职年月", "退职年月", "年 月", "年　　月"}:
                    continue
                if field == "company_name" and ("****" in value_text or value_text.startswith(("职位", "職位", "役職"))):
                    continue
                if field == "company_employees" and "*" in value_text:
                    continue
                clean_node_fields(value, set(WORK_ALIASES))
                value["data-field"] = field
                value["label"] = cell.get_text(" ", strip=True)
            # Compact Chinese/English work cards often keep the position and
            # salary in an unlabeled cell (``监理工程师 | 10001-15000元/月``)
            # and put company nature in an inline label/value pair.
            for cell in cells:
                for label_node in cell.find_all(attrs={"data-label-for": True}):
                    field = str(label_node.get("data-label-for") or "")
                    if field not in WORK_ALIASES:
                        continue
                    value_node = label_node.find_next(["i", "b", "em"])
                    value = value_node.get_text(" ", strip=True) if value_node else ""
                    if value:
                        clean_node_fields(value_node, set(WORK_ALIASES))
                        value_node["data-field"] = field
                        value_node["label"] = label_node.get_text(" ", strip=True)
            compact_position = next(
                (cell for cell in cells
                 if "|" in cell.get_text(" ", strip=True)
                 and not cell.find(attrs={"data-field": True})
                 and not re.search(r"(?:工作经验|Years? of Working)", cell.get_text(" ", strip=True), re.I)),
                None,
            )
            if compact_position is not None:
                parts = [part.strip() for part in compact_position.get_text(" ", strip=True).split("|", 1)]
                if parts and parts[0]:
                    clean_node_fields(compact_position, set(WORK_ALIASES))
                    position_node = soup.new_tag("span", attrs={"data-field": "position", "label": "职位"})
                    position_node.string = parts[0]
                    compact_position.clear()
                    compact_position.append(position_node)
                    if len(parts) > 1 and parts[1]:
                        salary_node = soup.new_tag("span", attrs={"data-field": "position_salary", "label": "薪资"})
                        salary_node.string = parts[1]
                        compact_position.append(NavigableString(" | "))
                        compact_position.append(salary_node)
            long_cell = next(
                (cell for cell in cells
                 if len(cell.get_text(" ", strip=True)) > 40
                 and not cell.find(attrs={"data-field": True})
                 and not field_for(cell.get_text(" ", strip=True), WORK_ALIASES)),
                None,
            )
            if long_cell is not None:
                long_cell["data-field"] = "position_responsibilities"
                long_cell["label"] = "工作内容"
    for record in soup.find_all(attrs={"data-record-type": "education"}):
        node = record.find(attrs={"data-field": "school_name"})
        if not node:
            continue
        school = node.get_text(" ", strip=True)
        match = re.search(r"(専攻|专业)$", school)
        if not match:
            continue
        stem = school[:match.start()].strip()
        major = ""
        for marker in ("大学", "大學", "学院", "學院", "学校", "學校", "中学", "中學", "高校"):
            pos = stem.rfind(marker)
            if pos >= 0:
                major = stem[pos + len(marker):].strip()
                stem = stem[:pos + len(marker)]
                break
        if not major:
            continue
        parent = node.parent
        node.attrs.pop("data-field", None)
        node.attrs.pop("label", None)
        node.clear()
        school_span = soup.new_tag("span", attrs={"data-field": "school_name", "label": "学校"})
        school_span.string = stem
        major_span = soup.new_tag("span", attrs={"data-field": "school_major_name", "label": "专业"})
        major_span.string = major
        node.append(school_span)
        node.append(major_span)

    # Never expose a work field on its own label cell (``公司名：`` or
    # ``Company：``).  The label is useful context, but it is not a value.
    for node in soup.find_all(attrs={"data-field": True}):
        field = str(node.get("data-field") or "")
        if field in WORK_ALIASES and field_for(node.get_text(" ", strip=True), WORK_ALIASES):
            clean_node_fields(node, set(WORK_ALIASES))
        if field == "position_responsibilities":
            value = re.sub(r"\s+", " ", node.get_text(" ", strip=True)).strip()
            if re.fullmatch(r"(?:19|20)\d{2}[^\n]{0,16}(?:～|~|-|至)[^\n]{0,16}(?:19|20)?\d{2,4}", value):
                clean_node_fields(node, {"position_responsibilities"})


def bind_compact_work_rows(soup: BeautifulSoup) -> None:
    """Bind date/company/description rows in compact XLS work tables."""
    date_re = re.compile(r"(?:19|20)\d{2}\s*(?:[./-]\s*\d{1,2}(?:\s*[./-]\s*\d{1,2}(?!\d))?|年\s*\d{1,2}\s*月?)")
    sections = list(soup.find_all("section", attrs={"data-collection": "work_experiences"}))
    sections.extend(soup.find_all("section", attrs={"data-collection": "training_list"}))
    for education_section in soup.find_all("section", attrs={"data-collection": "education_list"}):
        if re.search(r"職\s*務|工作经历|入社年?月|入职年?月", education_section.get_text(" ", strip=True)):
            sections.append(education_section)
    for section in sections:
        rows = section.find_all("tr")
        work_start = 0
        if section.get("data-collection") == "education_list":
            work_start = next((i for i, row in enumerate(rows) if re.search(r"職\s*務|工作经历|入社年?月|入职年?月", row.get_text(" ", strip=True))), len(rows)) + 1
        for index, row in enumerate(rows):
            if index < work_start:
                continue
            cells = [item[0] for item in cells_with_ranges(row)]
            values = [unicodedata.normalize("NFKC", cell.get_text(" ", strip=True)) for cell in cells]
            date_indices = [i for i, value in enumerate(values) if date_re.search(value)]
            if not date_indices:
                continue
            start_i = date_indices[0]
            range_matches = list(date_re.finditer(values[start_i]))
            label_markers = {
                "所属部署", "所属部門", "部门", "部門", "职位", "職位", "担当", "役職",
                "公司名", "公司名称", "会社名", "公司性质", "会社性質", "性质", "資本", "資本形態",
                "行业", "所属行业", "业界", "業界", "業種", "業種/事業内容", "行业/事业内容",
            }
            continuation = (
                any(value in label_markers for value in values[start_i + 1:])
                and not any(
                    any(token in value for token in ("株式会社", "有限会社", "有限公司", "公司", "会社"))
                    for value in values[start_i + 1:]
                )
            )
            # ``自 | 2017年03月 | 行业 | …`` is a genuine start row even
            # though it also contains trailing label/value pairs.  Only a
            # date row without an explicit start marker can be a continuation
            # row in these compact Japanese tables.
            if any(value in {"自", "从", "入职", "入社", "開始"} for value in values[:start_i]):
                continuation = False
            if continuation and len(range_matches) < 2:
                clean_node_fields(cells[start_i], {"position_start", "position_resigned"})
                cells[start_i]["data-field"] = "position_resigned"
                cells[start_i]["label"] = "退职年月"
                end_i: int | None = start_i
            elif len(range_matches) >= 2:
                # Keep both semantic nodes inside the original date cell.
                # The visible text remains the same while the DOM exposes a
                # real start/end pair for downstream consumers.
                raw_value = values[start_i]
                clean_node_fields(cells[start_i], {"position_start", "position_resigned"})
                cells[start_i].clear()
                start_span = soup.new_tag("span", attrs={"data-field": "position_start", "label": "入职年月"})
                start_span.string = range_matches[0].group(0)
                end_span = soup.new_tag("span", attrs={"data-field": "position_resigned", "label": "退职年月"})
                end_span.string = range_matches[1].group(0)
                cells[start_i].append(start_span)
                cells[start_i].append(NavigableString(" ～ "))
                cells[start_i].append(end_span)
                end_i: int | None = start_i
            else:
                end_i = None
            if len(range_matches) < 2 and not continuation:
                clean_node_fields(cells[start_i], set(WORK_ALIASES) | {"position_start", "position_resigned"})
                cells[start_i]["data-field"] = "position_start"
                cells[start_i]["label"] = "入职年月"
            if end_i is None:
                end_i = date_indices[1] if len(date_indices) > 1 else None
            if end_i is None and start_i + 1 < len(cells) and re.search(r"至今|现在|現在|現在も|今なお|在职|在籍|在職中|就职中|就職中", values[start_i + 1]):
                end_i = start_i + 1
            if end_i is not None and len(range_matches) < 2 and not continuation:
                clean_node_fields(cells[end_i], {"position_start", "position_resigned"})
                cells[end_i]["data-field"] = "position_resigned"
                cells[end_i]["label"] = "退职年月"
            # Continuation rows often contain only labels such as
            # ``所属部署 | 部长``.  They inherit the company from the prior
            # date/company row and must never be bound as a new company.
            for cell in cells:
                if cell.get_text(" ", strip=True) in label_markers:
                    clean_node_fields(cell, {"company_name"})
            company_i = next(
                (i for i in range((end_i if end_i is not None else start_i) + 1, len(cells))
                 if values[i]
                 and values[i] not in {"～", "~", "-", "至今", "现在", "現在", "現在も", "今なお", "在职", "在籍", "在職中", "就职中", "就職中", "年 月", "年　　月"}
                 and not re.fullmatch(r"年\s*月", values[i])
                 and values[i] not in label_markers
                 and not field_for(values[i], WORK_ALIASES)
                 and not any(str(cell.get("data-field") or "") in WORK_ALIASES for cell in [cells[i]])),
                None,
            )
            tail_values = values[(end_i if end_i is not None else start_i) + 1:]
            if any(value in label_markers for value in tail_values) and not any(
                any(token in value for token in ("株式会社", "有限会社", "有限公司", "公司", "会社"))
                for value in tail_values
            ):
                company_i = None
            if company_i is not None:
                clean_node_fields(cells[company_i], set(WORK_ALIASES))
                cells[company_i]["data-field"] = "company_name"
                cells[company_i]["label"] = "公司名称"
            row["data-record-type"] = "work_experience"
            # The next unlabelled long row is the compact description row.
            for next_row in rows[index + 1:index + 3]:
                next_cells = [item[0] for item in cells_with_ranges(next_row)]
                if not next_cells:
                    continue
                if any(re.search(r"(?:19|20)\d{2}", unicodedata.normalize("NFKC", c.get_text(" ", strip=True))) for c in next_cells):
                    break
                if len(next_cells) == 1 and len(next_cells[0].get_text(" ", strip=True)) > 20:
                    clean_node_fields(next_cells[0], set(WORK_ALIASES))
                    next_cells[0]["data-field"] = "position_responsibilities"
                    next_cells[0]["label"] = "工作内容"
                    break
        # A few generators pre-bind a whole prose paragraph containing a
        # year range (for example ``2013年～2015年：出纳业务``) as
        # ``position_start``.  That is not a work-record boundary.  Remove
        # the bogus date/type marker in HTML so downstream parsing cannot
        # manufacture a phantom duplicate work item.
        for row in rows:
            date_nodes = row.find_all(attrs={"data-field": re.compile(r"^position_(?:start|resigned)$")})
            valid_date = any(
                date_re.fullmatch(node.get_text(" ", strip=True).rstrip("/"))
                for node in date_nodes
            )
            if date_nodes and not valid_date:
                clean_node_fields(row, {"position_start", "position_resigned"})
                row.attrs.pop("data-record-type", None)


def remove_invalid_work_bindings(soup: BeautifulSoup) -> None:
    """Remove date/header fragments that are not valid work-field values."""
    date_like = re.compile(r"^(?:19|20)\d{2}[^\n]{0,16}(?:～|~|-|至)[^\n]{0,16}(?:19|20)?\d{2,4}$")
    for section in soup.find_all("section"):
        kind = str(section.get("data-section-type") or section.get("data-collection") or "").casefold()
        if kind not in {"work_experiences", "education_list"}:
            continue
        if kind == "education_list" and not section.find(attrs={"data-record-type": "work_experience"}):
            continue
        for node in list(section.find_all(attrs={"data-field": True})):
            field = str(node.get("data-field") or "")
            value = re.sub(r"\s+", " ", node.get_text(" ", strip=True)).strip()
            if field == "position_responsibilities" and date_like.fullmatch(value):
                clean_node_fields(node, {"position_responsibilities"})
            elif field == "position_subordinate" and value in {"人", "名", "部下", "下属"}:
                clean_node_fields(node, {"position_subordinate"})
            elif field in {"position_start", "position_resigned"} and not normalize_resume_date(value, end=field == "position_resigned"):
                clean_node_fields(node, {field})
            elif field in {"position_start", "position_resigned"}:
                row = node.find_parent("tr")
                if row and re.search(r"工作内容|工作职责|職務内容|仕事内容|業務内容|Job Description", row.get_text(" ", strip=True), re.I):
                    clean_node_fields(row, {"position_start", "position_resigned"})


def normalize_combined_collection_dom(soup: BeautifulSoup) -> None:
    """Give work rows in combined XLS tables the correct DOM record type.

    Several workbooks put education and work history in one physical table;
    the old generator labels every later row as ``education``.  Fixing that
    label in the HTML stage is important because parsers and validators both
    rely on the DOM contract.
    """
    for section in soup.find_all("section", attrs={"data-collection": "education_list"}):
        rows = section.find_all("tr")
        header = next(
            (idx for idx, row in enumerate(rows)
             if re.search(r"職\s*務|工作经历|入社年?月|入职年?月", row.get_text(" ", strip=True))),
            -1,
        )
        if header < 0:
            continue
        in_work = False
        for row in rows[header + 1:]:
            text = row.get_text(" ", strip=True)
            starts = bool(re.search(r"(?:19|20)\d{2}.*?(?:～|~|-|至).*?(?:19|20)\d{2}|(?:19|20)\d{2}.*?(?:今なお|在職中|在职|就職中|就职中)", text))
            if starts:
                in_work = True
            if not in_work:
                continue
            row["data-record-type"] = "work_experience"
            for node in row.find_all(attrs={"data-field": True}):
                field = str(node.get("data-field") or "")
                if field.startswith("school_") or field == "education_degree":
                    node.attrs.pop("data-field", None)
                    node.attrs.pop("label", None)


def bind_embedded_work_header_rows(soup: BeautifulSoup) -> None:
    """Bind column-header work grids embedded below an education table."""
    date_range = re.compile(r"((?:19|20)\d{2}[^\s～~至-]{0,8})\s*(?:～|~|至|-)\s*((?:19|20)\d{2}[^\s]{0,8})")
    for section in soup.find_all("section", attrs={"data-collection": "education_list"}):
        rows = section.find_all("tr")
        header_index = next(
            (i for i, row in enumerate(rows) if re.search(r"職\s*務\s*履歴|職\s*務\s*経歴|工作经历|工作履历", row.get_text(" ", strip=True))),
            -1,
        )
        if header_index < 0:
            continue
        header = rows[header_index]
        labels: list[tuple[Tag, int, int, str]] = []
        for cell, start, end in cells_with_ranges(header):
            field = field_for(cell.get_text(" ", strip=True), WORK_ALIASES)
            if field:
                labels.append((cell, start, end, field))
        if not labels:
            continue
        for row in rows[header_index + 1:]:
            cells = cells_with_ranges(row)
            if not cells:
                continue
            values = [cell.get_text(" ", strip=True) for cell, _start, _end in cells]
            if not any(re.search(r"(?:19|20)\d{2}", value) for value in values):
                continue
            for label_cell, start, end, field in labels:
                midpoint = (start + end) / 2
                target = next((cell for cell, left, right in cells if left <= midpoint <= right), None)
                if target is None:
                    continue
                value = target.get_text(" ", strip=True)
                if not value or field_for(value, WORK_ALIASES):
                    continue
                if field == "position_start" and date_range.search(value):
                    match = date_range.search(value)
                    assert match is not None
                    clean_node_fields(target, {"position_start", "position_resigned"})
                    target.clear()
                    start_node = soup.new_tag("span", attrs={"data-field": "position_start", "label": "入职年月"})
                    start_node.string = match.group(1).strip()
                    end_node = soup.new_tag("span", attrs={"data-field": "position_resigned", "label": "退职年月"})
                    end_node.string = match.group(2).strip()
                    target.append(start_node)
                    target.append(NavigableString(" ～ "))
                    target.append(end_node)
                else:
                    clean_node_fields(target, set(WORK_ALIASES) | {"position_start", "position_resigned"})
                    target["data-field"] = field
                    target["label"] = field
            row["data-record-type"] = "work_experience"


def bind_education_tables(soup: BeautifulSoup) -> None:
    """Repair XLS education rows whose generator attached the date to degree."""
    degree_tokens = ("本科", "大专", "专科", "硕士", "博士", "大学", "専門学校", "専門", "大学院", "学士", "修士", "高中", "中专", "無", "無し")
    degree_values = {"本科", "大专", "大專", "大専", "专科", "專科", "硕士", "碩士", "博士", "専門学校", "専門", "大学院", "学士", "學士", "修士", "高中", "高校", "中专", "中專", "無", "無し"}

    def is_degree_value(value: str) -> bool:
        normalized = re.sub(r"\s+", "", unicodedata.normalize("NFKC", value or "")).strip()
        if normalized in degree_values:
            return True
        parts = [part for part in re.split(r"[&＆、/／+＋]", normalized) if part]
        return len(parts) > 1 and all(part in degree_values for part in parts)
    for section in soup.find_all("section", attrs={"data-collection": "education_list"}):
        rows = section.find_all("tr")
        # Compact rows often have only: start date | end date | school | major.
        # Bind both dates explicitly and never let the end date become the
        # school name (the old rule did exactly that for 王雯婷).
        for row in rows:
            cells = [item[0] for item in cells_with_ranges(row)]
            values = [unicodedata.normalize("NFKC", cell.get_text(" ", strip=True)) for cell in cells]
            for cell in cells:
                clean_node_fields(cell, {"school_start_ym", "school_end_ym", "school_name", "school_major_name", "school_degree_type", "education_degree"})
            # Year-only values are common in the older Chinese/Japanese
            # education grids (``自 2008年`` / ``至 2012年``).  Keep the
            # optional month in the DOM binding; normalization later fills
            # the canonical January value when only a year is present.
            date_token_re = re.compile(
                r"(?:19|20)\d{2}(?:\s*(?:[./-]\s*\d{1,2}(?:\s*[./-]\s*\d{1,2}(?!\d))?|年(?:\s*\d{1,2}\s*月?)?))?"
            )
            range_cell = next(
                (i for i, value in enumerate(values) if len(list(date_token_re.finditer(value))) >= 2),
                None,
            )
            if range_cell is not None:
                matches = list(date_token_re.finditer(values[range_cell]))
                candidates = [i for i in range(range_cell + 1, len(cells)) if values[i]]
                school_i = candidates[0] if candidates else None
                major_i = candidates[1] if len(candidates) > 1 else None
                degree_i = None
                # Some templates order the row as date | degree | major |
                # school, while others use date | school | major | degree.
                # Identify the degree token first so the semantic names stay
                # aligned with the visible columns.
                if school_i is not None and is_degree_value(values[school_i]) and len(candidates) >= 2:
                    degree_i = candidates[0]
                    if len(candidates) >= 3 and is_degree_value(values[candidates[1]]):
                        # date | degree | degree-name | major | school
                        school_i = candidates[-1]
                        major_i = candidates[-2] if len(candidates) >= 4 else None
                    elif len(candidates) >= 3:
                        # date | degree | major | school
                        major_i, school_i = candidates[1], candidates[2]
                    else:
                        # date | degree | school
                        school_i = candidates[1]
                        major_i = None
                elif candidates and len(candidates) > 2 and is_degree_value(values[candidates[-1]]):
                    school_i, major_i, degree_i = candidates[0], candidates[1], candidates[-1]
                if school_i is not None:
                    clean_node_fields(cells[range_cell], {"school_start_ym", "school_end_ym"})
                    cells[range_cell].clear()
                    start_span = soup.new_tag("span", attrs={"data-field": "school_start_ym", "label": "入学年月"})
                    start_span.string = matches[0].group(0)
                    end_span = soup.new_tag("span", attrs={"data-field": "school_end_ym", "label": "毕业年月"})
                    end_span.string = matches[1].group(0)
                    cells[range_cell].append(start_span)
                    cells[range_cell].append(NavigableString(" ～ "))
                    cells[range_cell].append(end_span)
                    clean_node_fields(cells[school_i], {"school_name", "school_major_name", "school_degree_type"})
                    cells[school_i]["data-field"] = "school_name"
                    cells[school_i]["label"] = "学校名"
                    if major_i is not None:
                        clean_node_fields(cells[major_i], {"school_name", "school_major_name", "school_degree_type"})
                        cells[major_i]["data-field"] = "school_major_name"
                        cells[major_i]["label"] = "专业"
                    if degree_i is not None:
                        clean_node_fields(cells[degree_i], {"school_name", "school_major_name", "school_degree_type"})
                        cells[degree_i]["data-field"] = "school_degree_type"
                        cells[degree_i]["label"] = "学历"
                    row["data-record-type"] = "education"
                    continue
            date_indices = [
                i for i, value in enumerate(values)
                if re.fullmatch(r"(?:19|20)\d{2}(?:\s*(?:[./-]\s*\d{1,2}|年(?:\s*\d{1,2}\s*月?)?))?", value)
                and re.search(r"(?:19|20)\d{2}", value)
            ]
            if len(date_indices) < 2:
                continue
            start_i, end_i = date_indices[0], date_indices[1]
            school_i = next((i for i in range(end_i + 1, len(cells)) if values[i] and not field_for(values[i], {"x": {"学校名", "学校", "学校名称"}})), None)
            if school_i is None:
                continue
            major_i = next((i for i in range(school_i + 1, len(cells)) if values[i]), None)
            for i, field, label in ((start_i, "school_start_ym", "入学年月"), (end_i, "school_end_ym", "毕业年月"), (school_i, "school_name", "学校名")):
                clean_node_fields(cells[i], {"school_start_ym", "school_end_ym", "school_name", "school_major_name", "school_degree_type", "education_degree"})
                cells[i]["data-field"] = field
                cells[i]["label"] = label
            if major_i is not None:
                clean_node_fields(cells[major_i], {"school_start_ym", "school_end_ym", "school_name", "school_major_name", "school_degree_type"})
                cells[major_i]["data-field"] = "school_major_name"
                cells[major_i]["label"] = "专业"
            row["data-record-type"] = "education"
        # A number of older workbooks put the first education row immediately
        # before a combined work-history table and the legacy generator marks
        # its date as ``education_degree``.  Bind the row from the physical
        # column layout here, before JSON parsing, so the same DOM contract is
        # available to every consumer.
        work_header = next(
            (idx for idx, row in enumerate(rows)
             if re.search(r"職\s*務|工作经历|入社年?月|入职年?月", row.get_text(" ", strip=True))),
            len(rows),
        )
        for row in rows[:work_header]:
            cells = [item[0] for item in cells_with_ranges(row)]
            values = [cell.get_text(" ", strip=True) for cell in cells]
            date_index = next(
                (i for i, value in enumerate(values)
                 if re.fullmatch(r"(?:19|20)\d{2}(?:\s*(?:[./-]\s*\d{1,2}|年(?:\s*\d{1,2}\s*月?)?))?", value)
                 and re.search(r"(?:19|20)\d{2}", value)),
                None,
            )
            if date_index is None:
                continue
            school_index = next(
                (i for i in range(date_index + 1, len(cells))
                 if values[i] and not re.search(r"(?:19|20)\d{2}\s*(?:[./-]\s*\d{1,2}|年\s*\d{1,2}\s*月?)|年\s*月|受験中|自考中|在学|卒業|毕业|(?:大专|大専|本科|专科|大学院|専門学校|専門|高中|中专)$", values[i])),
                None,
            )
            if school_index is None:
                continue
            major_index = next(
                (i for i in range(school_index + 1, len(cells))
                 if values[i] and not re.search(r"(?:19|20)\d{2}\s*(?:[./-]\s*\d{1,2}|年\s*\d{1,2}\s*月?)|年\s*月|受験中|自考中|在学|卒業|毕业|(?:大专|大専|本科|专科|大学院|専門学校|専門)$", values[i])),
                None,
            )
            degree_index = next(
                (i for i in range((major_index or school_index) + 1, len(cells))
                 if values[i] and is_degree_value(values[i])),
                None,
            )
            clean_node_fields(cells[date_index], {"school_degree_type", "school_start_ym", "school_end_ym", "education_degree"})
            cells[date_index]["data-field"] = "school_start_ym"
            cells[date_index]["label"] = "入学年月"
            clean_node_fields(cells[school_index], {"school_name", "school_major_name", "school_degree_type"})
            cells[school_index]["data-field"] = "school_name"
            cells[school_index]["label"] = "学校名"
            if major_index is not None:
                clean_node_fields(cells[major_index], {"school_name", "school_major_name", "school_degree_type"})
                cells[major_index]["data-field"] = "school_major_name"
                cells[major_index]["label"] = "专业"
            if degree_index is not None:
                clean_node_fields(cells[degree_index], {"school_name", "school_major_name", "school_degree_type"})
                cells[degree_index]["data-field"] = "school_degree_type"
                cells[degree_index]["label"] = "学历"

        # Common vertical form: ``自 | start | school | major | degree``
        # followed by ``至 | end``.  The two dates live on separate physical
        # rows, so the horizontal range logic above cannot see the pair.
        for index, row in enumerate(rows[:-1]):
            cells = [item[0] for item in cells_with_ranges(row)]
            values = [re.sub(r"\s+", " ", cell.get_text(" ", strip=True)).strip() for cell in cells]
            marker = next((i for i, value in enumerate(values) if value in {"自", "入学", "开始"}), None)
            start_i = next((i for i, value in enumerate(values[marker + 1:] if marker is not None else [])
                            if re.search(r"(?:19|20)\d{2}", value)), None)
            if marker is None or start_i is None:
                continue
            start_i += marker + 1
            if start_i >= len(cells):
                continue
            next_row = rows[index + 1]
            next_cells = [item[0] for item in cells_with_ranges(next_row)]
            next_values = [re.sub(r"\s+", " ", cell.get_text(" ", strip=True)).strip() for cell in next_cells]
            end_i = next((i for i, value in enumerate(next_values)
                          if re.search(r"(?:19|20)\d{2}", value)), None)
            if end_i is None:
                continue
            candidate_indices = [i for i in range(start_i + 1, len(cells)) if values[i] and values[i] not in {"毕业", "毕业情况", "卒業", "卒業状況"}]
            if not candidate_indices:
                continue
            school_i = candidate_indices[0]
            major_i = candidate_indices[1] if len(candidate_indices) > 1 else None
            degree_i = next((i for i in candidate_indices if is_degree_value(values[i])), None)
            if degree_i == school_i:
                school_i = candidate_indices[1] if len(candidate_indices) > 1 else None
                major_i = candidate_indices[2] if len(candidate_indices) > 2 else None
            if school_i is None:
                continue
            clean_node_fields(cells[start_i], {"school_start_ym", "school_end_ym"})
            cells[start_i]["data-field"] = "school_start_ym"
            cells[start_i]["label"] = "入学年月"
            clean_node_fields(next_cells[end_i], {"school_start_ym", "school_end_ym"})
            next_cells[end_i]["data-field"] = "school_end_ym"
            next_cells[end_i]["label"] = "毕业年月"
            clean_node_fields(cells[school_i], {"school_name", "school_major_name", "school_degree_type"})
            cells[school_i]["data-field"] = "school_name"
            cells[school_i]["label"] = "学校名"
            if major_i is not None and major_i != degree_i:
                clean_node_fields(cells[major_i], {"school_name", "school_major_name", "school_degree_type"})
                cells[major_i]["data-field"] = "school_major_name"
                cells[major_i]["label"] = "专业"
            if degree_i is not None:
                clean_node_fields(cells[degree_i], {"school_name", "school_major_name", "school_degree_type"})
                cells[degree_i]["data-field"] = "school_degree_type"
                cells[degree_i]["label"] = "学历"
            row["data-record-type"] = "education"

        # Never leave semantic fields attached to table headers/demo labels.
        for node in section.find_all(attrs={"data-field": re.compile(r"^school_")}):
            value = re.sub(r"\s+", "", node.get_text(" ", strip=True))
            if value in {"学校", "学校名", "学校名称", "毕业情况", "卒業状況", "时间", "時間"}:
                clean_node_fields(node, {"school_name", "school_major_name", "school_degree_type", "school_start_ym", "school_end_ym"})

        # Label/value rows such as ``学校：| 名古屋...`` are frequently
        # separated from their date row.  Bind the physical school row, and
        # never let the Japanese-side ``時間``/date explanation become a
        # school or major value in the Chinese layer.
        for row in rows:
            cells = [item[0] for item in cells_with_ranges(row)]
            for node in list(row.find_all(attrs={"data-field": re.compile(r"^school_")})):
                value = re.sub(r"\s+", " ", node.get_text(" ", strip=True)).strip()
                if value in {"时间", "時間", "学校", "学校：", "学校名"} or re.search(r"(?:19|20)\d{2}年?\d{1,2}月?.*(?:から|到|まで)", value):
                    clean_node_fields(node, {"school_name", "school_major_name", "school_degree_type"})
            school_label = next((i for i, cell in enumerate(cells) if re.search(r"^学校\s*[:：]?$", cell.get_text(" ", strip=True)) and cell.get("data-label-for") == "school_name"), None)
            if school_label is not None:
                candidate = next((cell for cell in cells[school_label + 1:] if cell.get_text(" ", strip=True) and not cell.get("data-label-for")), None)
                if candidate is not None:
                    # Split inline ``学校名 专业： 观光`` values at the major marker.
                    major_marker = candidate.find(attrs={"data-label-for": "school_major_name"})
                    if major_marker is not None:
                        major_value = major_marker.find_next(string=True)
                        school_text = candidate.get_text(" ", strip=True).split("专业", 1)[0].strip(" ：:")
                        clean_node_fields(candidate, {"school_name", "school_major_name", "school_degree_type"})
                        candidate["data-field"] = "school_name"
                        candidate["label"] = "学校名"
                        candidate.clear()
                        candidate.string = school_text
                        if major_value and str(major_value).strip() and str(major_value).strip() != school_text:
                            major_node = soup.new_tag("span", attrs={"data-field": "school_major_name", "label": "专业"})
                            major_node.string = str(major_value).strip()
                            candidate.append(major_node)
                    else:
                        clean_node_fields(candidate, {"school_name", "school_major_name", "school_degree_type"})
                        candidate["data-field"] = "school_name"
                        candidate["label"] = "学校名"
            major_label = next((i for i, cell in enumerate(cells) if re.search(r"^专业\s*[:：]?$", cell.get_text(" ", strip=True)) and cell.get("data-label-for") == "school_major_name"), None)
            if major_label is not None:
                candidate = next((cell for cell in cells[major_label + 1:] if cell.get_text(" ", strip=True) and not cell.get("data-label-for")), None)
                if candidate is not None and not candidate.get("data-field"):
                    clean_node_fields(candidate, {"school_name", "school_major_name", "school_degree_type"})
                    candidate["data-field"] = "school_major_name"
                    candidate["label"] = "专业"
            row["data-record-type"] = "education"
        # Vertical education layouts put ``至 YYYY年MM月`` on the row after
        # the school row.  Bind that date explicitly as the matching end date.
        for index, row in enumerate(rows[:-1]):
            if not row.find(attrs={"data-field": "school_start_ym"}) or row.find(attrs={"data-field": "school_end_ym"}):
                continue
            next_row = rows[index + 1]
            next_text = next_row.get_text(" ", strip=True)
            if not re.search(r"(?:至|毕业|卒業)\s*(?:19|20)\d{2}", next_text):
                continue
            next_cells = [item[0] for item in cells_with_ranges(next_row)]
            end_cell = next((cell for cell in next_cells if re.search(r"(?:19|20)\d{2}", cell.get_text(" ", strip=True))), None)
            if end_cell is None:
                continue
            clean_node_fields(end_cell, {"school_start_ym", "school_end_ym"})
            end_cell["data-field"] = "school_end_ym"
            end_cell["label"] = "毕业年月"

        for row in rows:
            cells = [item[0] for item in cells_with_ranges(row)]
            if not cells:
                continue
            values = [cell.get_text(" ", strip=True) for cell in cells]
            date_index = next((i for i, value in enumerate(values) if re.search(r"(?:19|20)\d{2}.*?(?:～|~|-|至).*?(?:19|20)\d{2}|(?:19|20)\d{2}.*?(?:～|~|-|至)\s*(?:至今|现在|現在)", value)), None)
            if date_index is None:
                continue
            if cells[date_index].find(attrs={"data-field": "school_end_ym"}):
                continue
            # Work blocks embedded below an education table are handled by the
            # mixed-work extractor; do not turn their company into a school.
            if any(marker in section.get_text(" ", strip=True)[: max(0, section.get_text(" ", strip=True).find(values[date_index]))] for marker in ("職務履歴", "職務経歴", "工作经历")):
                continue
            school_index = next((i for i in range(date_index + 1, len(cells)) if values[i] and not field_for(values[i], {"x": {"学校名", "学校", "学校名称"}})), None)
            if school_index is None:
                continue
            major_index = next((i for i in range(school_index + 1, len(cells)) if values[i] and not field_for(values[i], {"x": {"专业", "専攻", "学部/学科/専攻"}})), None)
            degree_index = next((i for i in range((major_index or school_index) + 1, len(cells)) if values[i] and is_degree_value(values[i])), None)
            clean_node_fields(cells[date_index], {"school_degree_type", "school_start_ym", "school_end_ym"})
            cells[date_index]["data-field"] = "school_start_ym"
            cells[date_index]["label"] = "入学年月"
            clean_node_fields(cells[school_index], {"school_name", "school_major_name", "school_degree_type"})
            cells[school_index]["data-field"] = "school_name"
            cells[school_index]["label"] = "学校名"
            if major_index is not None:
                clean_node_fields(cells[major_index], {"school_name", "school_major_name", "school_degree_type"})
                cells[major_index]["data-field"] = "school_major_name"
                cells[major_index]["label"] = "专业"
            if degree_index is not None:
                clean_node_fields(cells[degree_index], {"school_name", "school_major_name", "school_degree_type"})
                cells[degree_index]["data-field"] = "school_degree_type"
                cells[degree_index]["label"] = "学历"


def remove_template_demo_rows(soup: BeautifulSoup) -> None:
    """Remove generic profile/language demonstration rows from XLS tables."""
    demo_markers = (
        "独身子なし", "独身子持", "既婚子なし", "既婚子持", "ネイティブ",
        "ビジネス上級", "ビジネス中級", "ビジネス下級", "専門学校", "高専",
        "大専（短大）", "大学院", "静安新時代", "上海修曼人才", "Tel:",
    )
    for table in list(soup.find_all("table")):
        rows = table.find_all("tr", recursive=False)
        if not rows:
            continue
        text = table.get_text(" ", strip=True)
        years = set(re.findall(r"\b196[0-6]\b", text))
        marker_count = sum(text.count(marker) for marker in demo_markers)
        is_demo_table = len(years) >= 4 or (marker_count >= 5 and "Tel" in text)
        if is_demo_table:
            # In the known template, the demonstration block precedes the
            # first actual profile label.  Remove all rows before that label;
            # this also removes its generic salary/personality examples.
            first_profile = next(
                (index for index, row in enumerate(rows)
                 if re.search(r"フリガナ|氏\s*名|姓名|本人概要|名前", row.get_text(" ", strip=True))),
                None,
            )
            if first_profile is not None and first_profile > 0:
                for row in rows[:first_profile]:
                    row.decompose()
            else:
                for row in rows:
                    row_text = row.get_text(" ", strip=True)
                    if any(marker in row_text for marker in demo_markers) or re.search(r"\b196[0-6]\b", row_text):
                        row.decompose()
        # The proficiency legend is explanatory text, never a candidate's
        # language level.  Remove it even when it is in a separate table.
        for row in list(table.find_all("tr", recursive=False)):
            row_text = row.get_text(" ", strip=True)
            if re.search(r"(?:■\s*)?(?:ネイティブ|ビジネス\s*(?:上級|中級|下級)|日常|挨拶).*?(?:現地人|ビジネス|やり取り|基礎学習)", row_text):
                row.decompose()


def prune_nonformal_experience_sections(soup: BeautifulSoup) -> None:
    """Remove student/temporary experience before semantic binding."""
    markers = re.compile(
        r"实习经历|实习经验|实习生|实习|實習|兼职|兼職|アルバイト|バイト|"
        r"インターン(?:シップ)?|社团|社團|学生会|學生會|校内社团|社会实践|"
        r"社会實踐|志愿者|ボランティア",
        re.I,
    )
    # Auxiliary training tables in these XLS templates are student/temporary
    # experience, not formal employment records.
    for section in list(soup.find_all("section", attrs={"data-collection": "training_list"})):
        section.decompose()
    for section in list(soup.find_all("section", attrs={"data-collection": "education_list"})):
        for table in list(section.find_all("table")):
            if markers.search(table.get_text(" ", strip=True)):
                table.decompose()
        for row in list(section.find_all("tr")):
            if markers.search(row.get_text(" ", strip=True)):
                row.decompose()
    for section in list(soup.find_all("section", attrs={"data-section-type": "work_experiences"})):
        rows = list(section.find_all("tr"))
        for index, row in enumerate(rows):
            if not markers.search(row.get_text(" ", strip=True)):
                continue
            start = index
            while start > 0 and rows[start].get("data-record-type") != "work_experience":
                start -= 1
            if rows[start].get("data-record-type") != "work_experience":
                start = index
            end = next(
                (pos for pos in range(start + 1, len(rows))
                 if rows[pos].get("data-record-type") == "work_experience"),
                len(rows),
            )
            for target in rows[start:end]:
                if target.parent is not None:
                    target.decompose()


def bind_language_matrices(soup: BeautifulSoup) -> None:
    """Bind horizontal language headers/levels as vertical semantic pairs."""
    for section in soup.find_all("section"):
        if str(section.get("data-section-type") or section.get("data-collection") or "").casefold() != "language_list":
            continue
        rows = section.find_all("tr")
        for index, row in enumerate(rows):
            cells = row.find_all(["td", "th"], recursive=False)
            values = [re.sub(r"\s+", "", cell.get_text(" ", strip=True)) for cell in cells]
            names = [value for value in values if value in LANGUAGE_NAME_MAP]
            if len(names) < 2 or not any(token in "".join(values) for token in ("語学", "语言", "語言", "レベル", "等级")):
                continue
            next_row = rows[index + 1] if index + 1 < len(rows) else None
            if next_row is None:
                continue
            level_cells = next_row.find_all(["td", "th"], recursive=False)
            for cell, value in zip(cells, values):
                if value in LANGUAGE_NAME_MAP:
                    cell["data-field"] = "language_name"
                    cell["data-language-name"] = LANGUAGE_NAME_MAP[value]
            # Align by physical column; blank cells are retained so merged
            # layouts do not shift the language level to the next language.
            for cell, level in zip(cells, level_cells):
                    if re.sub(r"\s+", "", cell.get_text(" ", strip=True)) in LANGUAGE_NAME_MAP:
                        level["data-field"] = "language_level"
                        level["data-language-name"] = LANGUAGE_NAME_MAP[re.sub(r"\s+", "", cell.get_text(" ", strip=True))]
    # Remove legacy language bindings that point at a header such as
    # ``レベル(取得検定)`` instead of an actual language name.  They are not
    # recoverable language records and pollute the bilingual alignment.
    valid_names = {re.sub(r"\s+", "", value) for value in LANGUAGE_NAME_MAP}
    for node in soup.find_all(attrs={"data-field": "language_name"}):
        if re.sub(r"\s+", "", node.get_text(" ", strip=True)) not in valid_names:
            node.attrs.pop("data-field", None)
            node.attrs.pop("label", None)
            node.attrs.pop("data-language-name", None)
    # Vertical language tables use one language per row (语种/言語 | level).
    # Bind those rows independently; requiring two names on one row would
    # miss the common Chinese/Japanese form entirely.
    for section in soup.find_all("section"):
        if str(section.get("data-section-type") or section.get("data-collection") or "").casefold() != "language_list":
            continue
        for row in section.find_all("tr"):
            cells = row.find_all(["td", "th"], recursive=False)
            for index, cell in enumerate(cells):
                key = re.sub(r"\s+", "", cell.get_text(" ", strip=True))
                if key not in LANGUAGE_NAME_MAP:
                    continue
                clean_node_fields(cell, {"language_name", "language_level"})
                cell["data-field"] = "language_name"
                cell["data-language-name"] = LANGUAGE_NAME_MAP[key]
                level_cell = next(
                    (candidate for candidate in cells[index + 1:] if candidate.get_text(" ", strip=True)),
                    None,
                )
                if level_cell is not None and not field_for(level_cell.get_text(" ", strip=True), PROFILE_ALIASES):
                    clean_node_fields(level_cell, {"language_name", "language_level"})
                    level_cell["data-field"] = "language_level"
                    level_cell["data-language-name"] = LANGUAGE_NAME_MAP[key]
                break


def bind_certificate_tables(soup: BeautifulSoup) -> None:
    """Bind certificate name/time cells in the HTML certificate tables."""
    language_labels = {"日语", "日本語", "英语", "英語", "中文", "中国語", "韩语", "韓国語", "其他", "その他", "语言", "語言"}
    for section in soup.find_all("section", attrs={"data-section-type": "certificate_list"}):
        for row in section.find_all("tr"):
            cells = row.find_all(["td", "th"], recursive=False)
            values = [re.sub(r"\s+", " ", cell.get_text(" ", strip=True)).strip() for cell in cells]
            date_index = next((i for i, value in enumerate(values) if re.search(r"(?:19|20)\d{2}", value) and not re.fullmatch(r"(?:取得年|合格日期|取得年月)", value)), None)
            if date_index is None:
                continue
            name_index = next(
                (i for i in range(date_index - 1, -1, -1)
                 if values[i] and values[i] not in language_labels and not re.search(r"資格/証書|证书|資格名|语言", values[i])),
                None,
            )
            if name_index is None:
                name_index = next(
                    (i for i in range(date_index + 1, len(values))
                     if values[i] and values[i] not in language_labels
                     and not re.search(r"資格/証書|证书|資格名|语言", values[i])),
                    None,
                )
            if name_index is None:
                continue
            clean_node_fields(cells[name_index], {"certificate_name", "certificate_time"})
            clean_node_fields(cells[date_index], {"certificate_name", "certificate_time"})
            cells[name_index]["data-field"] = "certificate_name"
            cells[name_index]["label"] = "证书名称"
            cells[date_index]["data-field"] = "certificate_time"
            cells[date_index]["label"] = "取得年月"
    for node in soup.find_all(attrs={"data-field": "certificate_time"}):
        if not re.search(r"(?:19|20)\d{2}", node.get_text(" ", strip=True)):
            clean_node_fields(node, {"certificate_time"})


def bind_skill_tables(soup: BeautifulSoup) -> None:
    """Split software skill rows from certificate grids in the HTML DOM.

    Legacy XLS templates place Word/Excel/PowerPoint in the same physical
    table as language certificates.  Treating the preceding ``中级`` cell as
    a certificate name is a DOM error, not an extraction-rule issue.  Create
    a dedicated ``skills_list`` section and leave only real certificates in
    the certificate section.
    """
    software_tokens = {"word", "excel", "powerpoint", "power point", "cad", "solidworks", "office"}
    level_re = re.compile(r"(?:初级|中级|高级|熟练|一般|精通|入门|上级|中級|上級|下級|ビジネス|日常|挨拶|expert|advanced|intermediate|basic|熟練)", re.I)

    def software_value(value: str) -> str:
        normalized = re.sub(r"\s+", " ", unicodedata.normalize("NFKC", value or "")).strip()
        return normalized if normalized.casefold() in software_tokens else ""

    for section in list(soup.find_all("section")):
        kind = str(section.get("data-section-type") or section.get("data-collection") or "").casefold()
        if kind not in {"skills_list", "certificate_list"}:
            continue
        skill_rows: list[tuple[str, str]] = []
        for row in list(section.find_all("tr")):
            cells = row.find_all(["td", "th"], recursive=False)
            if not cells:
                continue
            found = None
            for i, cell in enumerate(cells):
                name = software_value(cell.get_text(" ", strip=True))
                if not name:
                    continue
                level = ""
                for candidate in cells[i + 1:]:
                    value = re.sub(r"\s+", " ", candidate.get_text(" ", strip=True)).strip()
                    if not value:
                        continue
                    if level_re.search(value) or value.casefold() in {"熟练", "中级", "中級"}:
                        level = value
                        break
                    # A different populated column means this is not the
                    # level paired with the software name.
                    if len(value) > 18:
                        break
                found = (name, level)
                break
            if not found:
                continue
            name, level = found
            # A bare software label in the template's demonstration/header
            # grid is not a candidate skill.  Require its paired proficiency
            # value before exposing it as a semantic skill record.
            if not level:
                continue
            skill_rows.append(found)
            if kind == "skills_list":
                for cell in cells:
                    if software_value(cell.get_text(" ", strip=True)) == name:
                        clean_node_fields(cell, {"skill_name", "skill_level"})
                        cell["data-field"] = "skill_name"
                        cell["label"] = "软件名"
                        cell["data-record-type"] = "skill"
                        break
                if level:
                    for cell in cells[cells.index(next(c for c in cells if software_value(c.get_text(" ", strip=True)) == name)) + 1:]:
                        if level == re.sub(r"\s+", " ", cell.get_text(" ", strip=True)).strip():
                            clean_node_fields(cell, {"skill_name", "skill_level"})
                            cell["data-field"] = "skill_level"
                            cell["label"] = "水平"
                            break
        if kind != "certificate_list" or not skill_rows:
            continue
        # Move only the software pairs into a separate semantic collection.
        new_section = soup.new_tag("section", attrs={
            "data-section-type": "skills_list",
            "data-collection": "skills_list",
            "data-language": str(section.get("data-language") or section.get("data-language-code") or "zh"),
            "data-language-code": str(section.get("data-language-code") or section.get("data-language") or "zh"),
        })
        table = soup.new_tag("table")
        new_section.append(table)
        moved = 0
        for row in list(section.find_all("tr")):
            cells = row.find_all(["td", "th"], recursive=False)
            for i, cell in enumerate(cells):
                name = software_value(cell.get_text(" ", strip=True))
                if not name:
                    continue
                level_node = next((candidate for candidate in cells[i + 1:] if level_re.search(candidate.get_text(" ", strip=True))), None)
                new_row = soup.new_tag("tr", attrs={"data-record-type": "skill"})
                name_node = soup.new_tag("td", attrs={"data-field": "skill_name", "label": "软件名"})
                name_node.string = name
                new_row.append(name_node)
                if level_node is not None:
                    level_node_copy = soup.new_tag("td", attrs={"data-field": "skill_level", "label": "水平"})
                    level_node_copy.string = re.sub(r"\s+", " ", level_node.get_text(" ", strip=True)).strip()
                    new_row.append(level_node_copy)
                table.append(new_row)
                # Remove the software pair from the certificate DOM so the
                # certificate binder cannot reinterpret it.
                cell.decompose()
                if level_node is not None and level_node.parent is not None:
                    level_node.decompose()
                moved += 1
                break
        if moved:
            section.insert_after(new_section)


def bind_self_evaluation_sections(soup: BeautifulSoup) -> None:
    """Bind complete self-evaluation text and split it from certificate rows."""
    labels = {"自我评价", "自我介绍", "自己pr", "自己pr", "comment", "评论", "自我评价", "自己アピール", "自己ｱﾋﾟｰﾙ"}

    def marker_match(value: str) -> bool:
        """Match full/half-width Japanese PR labels consistently.

        Excel templates frequently store ``自己ｱﾋﾟｰﾙ`` using half-width
        katakana.  NFKC turns it into the normal ``自己アピール`` spelling so
        the row can be split even when the prose is in the same row as the
        label (as in 孔斌's workbook).
        """
        normalized = unicodedata.normalize("NFKC", value or "")
        return bool(re.search(r"自我评价|自我介绍|自己\s*PR|自己紹介|自己アピール", normalized, re.I))

    def meaningful(section: Tag) -> bool:
        for node in section.find_all(attrs={"data-field": "pr"}):
            if len(node.get_text(" ", strip=True)) > 10:
                return True
        for row in section.find_all("tr"):
            for cell in row.find_all(["td", "th"], recursive=False):
                value = re.sub(r"\s+", " ", cell.get_text(" ", strip=True)).strip()
                if len(value) > 20 and value.casefold() not in labels and not value.startswith("◆"):
                    return True
        return False

    # Drop title-only duplicate sections (the Yang Junhao workbook has one
    # before the actual prose section), then bind the prose cell itself.
    by_code: dict[str, list[Tag]] = {}
    for section in list(soup.find_all("section", attrs={"data-section-type": "self_evaluation"})):
        code = str(section.get("data-language-code") or section.get("data-language") or "zh").casefold()
        by_code.setdefault(code, []).append(section)
    for code, sections in by_code.items():
        if any(meaningful(section) for section in sections):
            for section in sections:
                if not meaningful(section) and section.parent is not None:
                    section.decompose()
    for section in list(soup.find_all("section", attrs={"data-section-type": "self_evaluation"})):
        for row in section.find_all("tr"):
            candidates = []
            for cell in row.find_all(["td", "th"], recursive=False):
                value = re.sub(r"\s+", " ", cell.get_text(" ", strip=True)).strip()
                if len(value) > 10 and value.casefold() not in labels and not value.startswith("◆"):
                    candidates.append(cell)
            if candidates:
                target = max(candidates, key=lambda node: len(node.get_text(" ", strip=True)))
                clean_node_fields(target, {"pr"})
                target["data-field"] = "pr"
                target["label"] = "自我评价"

    # Some bilingual sheets put 自己PR/comment directly after certificates or
    # language rows (the marker is often classified as language_list by the
    # generic sectionizer).  Split the prose at HTML stage in either case.
    for section in list(soup.find_all("section")):
        if section.get("data-section-type") in {"self_evaluation", "base_info", "document-body"}:
            continue
        rows = list(section.find_all("tr"))
        marker_index = next((i for i, row in enumerate(rows) if marker_match(row.get_text(" ", strip=True))), None)
        if marker_index is None:
            continue
        content_cells = []
        marker_row = rows[marker_index]
        # A common Japanese layout puts ``自己ｱﾋﾟｰﾙ`` and the entire
        # paragraph in adjacent cells of the same row.  The old splitter only
        # looked at subsequent rows and therefore silently dropped the PR.
        marker_cells = marker_row.find_all(["td", "th"], recursive=False)
        marker_cell_indexes = [
            idx for idx, cell in enumerate(marker_cells)
            if marker_match(cell.get_text(" ", strip=True))
        ]
        start_idx = (max(marker_cell_indexes) + 1) if marker_cell_indexes else 0
        for cell in marker_cells[start_idx:]:
            value = cell.get_text(" ", strip=True)
            if len(value) > 20:
                content_cells.append((marker_row, cell))
        for row in rows[marker_index + 1:]:
            for cell in row.find_all(["td", "th"], recursive=False):
                value = cell.get_text(" ", strip=True)
                if len(value) > 20:
                    content_cells.append((row, cell))
        if not content_cells:
            continue
        code = str(section.get("data-language-code") or section.get("data-language") or "zh")
        new_section = soup.new_tag("section", attrs={
            "data-section-type": "self_evaluation", "data-language": code,
            "data-language-code": code,
        })
        table = soup.new_tag("table")
        new_section.append(table)
        new_row = soup.new_tag("tr")
        node = soup.new_tag("td", attrs={"data-field": "pr", "label": "自己PR"})
        prose_values: list[str] = []
        for _, cell in content_cells:
            value = cell.get_text(" ", strip=True)
            if value and value not in prose_values:
                prose_values.append(value)
        node.string = "\n".join(prose_values)
        new_row.append(node)
        table.append(new_row)
        section.insert_after(new_section)
        for row, _ in content_cells:
            if row.parent is section and row.parent is not None:
                row.decompose()
        if marker_row.parent is section:
            marker_row.decompose()


def split_bilingual_self_evaluation_dom(soup: BeautifulSoup) -> None:
    """Split Chinese/Japanese PR cells into language-specific DOM sections."""
    for section in list(soup.find_all("section", attrs={"data-section-type": "self_evaluation"})):
        nodes = list(section.find_all(attrs={"data-field": "pr"}))
        if len(nodes) < 2:
            continue
        zh_nodes: list[Tag] = []
        jp_nodes: list[Tag] = []
        for node in nodes:
            text = unicodedata.normalize("NFKC", node.get_text(" ", strip=True))
            kana = len(re.findall(r"[ぁ-ゖァ-ヺ]", text))
            if kana >= 4 or re.search(r"(?:自己紹介|自己アピール|履歴書|職務|です|ます|ことが|できます)", text):
                jp_nodes.append(node)
            else:
                zh_nodes.append(node)
        if not zh_nodes or not jp_nodes:
            continue
        # Keep the Chinese section in place and create a clean Japanese
        # sibling.  The original table may contain bilingual labels and
        # placeholders; only the semantic PR value is copied into the new
        # section so downstream extraction cannot merge the languages again.
        code = str(section.get("data-language-code") or section.get("data-language") or "zh").casefold()
        if code in {"jp", "ja"}:
            zh_code, jp_code = "zh", "jp"
        else:
            zh_code, jp_code = code or "zh", "jp"
        section["data-language"] = zh_code
        section["data-language-code"] = zh_code
        for node in jp_nodes:
            node.extract()
        new_section = soup.new_tag("section", attrs={
            "data-section-type": "self_evaluation",
            "data-language": jp_code,
            "data-language-code": jp_code,
        })
        table = soup.new_tag("table")
        row = soup.new_tag("tr")
        for node in jp_nodes:
            copied = soup.new_tag("td", attrs={"data-field": "pr", "label": "自己アピール"})
            copied.string = node.get_text(" ", strip=True)
            row.append(copied)
        table.append(row)
        new_section.append(table)
        section.insert_after(new_section)


def clean_self_evaluation_dom(soup: BeautifulSoup) -> None:
    """Remove profile/contact/date cells accidentally tagged as PR."""
    for section in soup.find_all("section", attrs={"data-section-type": "self_evaluation"}):
        for node in list(section.find_all(attrs={"data-field": "pr"})):
            value = re.sub(r"\s+", " ", node.get_text(" ", strip=True)).strip()
            compact = re.sub(r"\s+", "", value)
            if (
                not value
                or re.search(r"(?:@|mailto:|〒\d|携帯|电话|電話|现住所|現住所)", value, re.I)
                or re.fullmatch(r"(?:19|20)\d{2}年?\d{0,2}月?\d{0,2}日?.*", compact)
                or re.fullmatch(r"[\d\s年月日（）()満歳‐\-~～]+", compact)
            ):
                clean_node_fields(node, {"pr"})


def sort_history_dom(soup: BeautifulSoup) -> None:
    """Reorder bound education/work records newest-first without detaching fields.

    The XLS source often lists history oldest-first.  Once semantic DOM nodes
    are bound, move complete table row blocks (header + date/company row +
    continuation rows) together so company names cannot become paired with a
    different period.  Education records are single rows in these templates;
    work records carry continuation rows and are moved as blocks.
    """
    def date_key(row: Tag, start_field: str, end_field: str) -> tuple[int, str]:
        node = row.find(attrs={"data-field": end_field}) or row.find(attrs={"data-field": start_field})
        value = normalize_resume_date(node.get_text(" ", strip=True), end=end_field.endswith("end_ym") or end_field.endswith("resigned")) if node else ""
        return (1 if value else 0, value or "")

    def replace_slots(parent: Tag, slots: list[int], replacements: list[list[Tag]]) -> None:
        if not slots:
            return
        children = list(parent.contents)
        target_children = [children[i] for i in slots if i < len(children)]
        if not target_children or not all(isinstance(node, Tag) for node in target_children):
            return
        flat = [node for group in replacements for node in group]
        if len(flat) != len(target_children):
            return
        for node in target_children:
            node.extract()
        insert_at = min(slots)
        for offset, node in enumerate(flat):
            parent.insert(insert_at + offset, node)

    for section in soup.find_all("section"):
        kind = str(section.get("data-section-type") or "").casefold()
        if kind not in {"education_list", "work_experiences"}:
            continue
        rows = section.find_all("tr")
        if not rows:
            continue
        parent = rows[0].parent
        if parent is None or any(row.parent is not parent for row in rows):
            continue
        education_starts = [i for i, row in enumerate(rows) if row.find(attrs={"data-field": "school_name"})]
        education_can_sort = bool(education_starts) and all(
            rows[i].find(attrs={"data-field": "school_start_ym"})
            and rows[i].find(attrs={"data-field": "school_name"})
            for i in education_starts
        )
        if education_can_sort:
            ordered = sorted(
                (rows[i] for i in education_starts),
                key=lambda row: date_key(row, "school_start_ym", "school_end_ym"),
                reverse=True,
            )
            replace_slots(parent, [list(parent.contents).index(rows[i]) for i in education_starts], [[row] for row in ordered])
        work_starts = [i for i, row in enumerate(rows) if row.find(attrs={"data-field": "company_name"})]
        if not work_starts:
            continue
        block_starts: list[int] = []
        for index in work_starts:
            start = index
            if index > 0 and re.search(r"入社年?月|入职年?月|会社名|公司名", rows[index - 1].get_text(" ", strip=True)):
                start = index - 1
            block_starts.append(start)
        blocks: list[tuple[int, int, list[Tag]]] = []
        for n, start in enumerate(block_starts):
            end = block_starts[n + 1] if n + 1 < len(block_starts) else len(rows)
            blocks.append((start, end, rows[start:end]))
        blocks.sort(key=lambda item: date_key(rows[work_starts[block_starts.index(item[0])]], "position_start", "position_resigned"), reverse=True)
        slots = [list(parent.contents).index(row) for start, end, _ in blocks for row in rows[start:end]]
        replace_slots(parent, slots, [block[2] for block in blocks])


def bind_free_text_resume_sections(soup: BeautifulSoup) -> None:
    """Create semantic DOM for compact, line-oriented XLS resumes.

    Older Japanese templates store 教育/語学能力/免許、資格 as prose rows in
    one table.  Leaving those rows unbound makes the JSON parser lose the
    actual schools and certificates.  We add collection sections alongside
    the original table so the source text remains intact and extraction is
    incremental and evidence-based.
    """
    date_re = re.compile(r"((?:19|20)\d{2})\s*[./．年]\s*(\d{1,2})\s*[-~～至－]\s*((?:(?:19|20)\d{2})\s*[./．年]\s*(\d{1,2})|至今|现在|現在)")
    for resume in soup.find_all("article", attrs={"data-role": "resume"}):
        code = str(resume.get("data-language-code") or resume.get("data-language") or "zh").casefold()
        body = resume.find_all("section", attrs={"data-section-type": "document-body"})
        # normalize_combined_collection_dom may classify the original
        # all-in-one table as base_info while leaving a short document-body
        # header section in place.  Inspect both physical tables.
        body.extend(resume.find_all("section", attrs={"data-section-type": "base_info"}))
        if not body:
            continue
        text_rows: list[str] = []
        for section in body:
            for row in section.find_all("tr"):
                value = unicodedata.normalize("NFKC", row.get_text(" ", strip=True)).strip()
                if value:
                    text_rows.append(value)
        if not text_rows:
            continue
        def section_rows(pattern: str) -> list[str]:
            start = next((i for i, value in enumerate(text_rows) if re.search(pattern, value, re.I)), None)
            if start is None:
                return []
            first_tail = re.sub(pattern, "", text_rows[start], count=1, flags=re.I).strip(" ：:－-~～")
            end = len(text_rows)
            for i in range(start + 1, len(text_rows)):
                if re.search(r"^(?:職務経験|工作经历|工作经验|仕事経験|語学能力|语言能力|免許、?資格|证书|資格|教育|教\s*育|学歴|教育经历|求職|求职|自己PR|自我评价|転職理由|离职理由)", text_rows[i], re.I):
                    if i > start + 1:
                        end = i
                        break
            values = text_rows[start + 1:end]
            return ([first_tail] if first_tail else []) + values
        def add_section(kind: str, rows: list[dict[str, str]]) -> None:
            if not rows:
                return
            existing = resume.find("section", attrs={"data-collection": kind})
            if existing is not None:
                if any(node.get_text(" ", strip=True) for node in existing.find_all(attrs={"data-field": True})):
                    if kind == "language_list":
                        known = {node.get_text(" ", strip=True) for node in existing.find_all(attrs={"data-field": "language_name"})}
                        for item in rows:
                            if item.get("language_name") in known:
                                continue
                            record = soup.new_tag("div", attrs={"data-record-type": "language"})
                            for field, value in item.items():
                                if value:
                                    node = soup.new_tag("span", attrs={"data-field": field, "label": field})
                                    node.string = value
                                    record.append(node)
                            existing.append(record)
                    return
                existing.decompose()
            section = soup.new_tag("section", attrs={
                "data-language": code, "data-language-code": code,
                "data-language-level": "section", "data-section-type": kind,
                "data-collection": kind, "data-source": "xls-inline-text",
            })
            for item in rows:
                record_type = "education" if kind == "education_list" else ("certificate" if kind == "certificate_list" else "language")
                record = soup.new_tag("div", attrs={"data-record-type": record_type})
                for field, value in item.items():
                    if not value:
                        continue
                    node = soup.new_tag("span", attrs={"data-field": field, "label": field})
                    node.string = value
                    record.append(node)
                section.append(record)
            resume.append(section)
        education_items: list[dict[str, str]] = []
        for line in section_rows(r"(?:^|\s)(?:教育|教\s*育|学歴|教育经历|毕业履历)"):
            match = date_re.search(line)
            if not match or re.search(r"講座|讲座|培训|研修|インターン", line, re.I):
                continue
            start = f"{match.group(1)}年{int(match.group(2)):02d}月"
            end_raw = match.group(3).replace(" ", "")
            end = "" if end_raw in {"至今", "现在", "現在"} else re.sub(r"[./．-]", "年", end_raw) + "月"
            tail = line[match.end():].strip(" ：:－-~～")
            parts = [p for p in re.split(r"\s{2,}|\t+", tail) if p]
            if len(parts) < 2:
                parts = [p for p in re.split(r"\s+", tail) if p]
            school = parts[0] if parts else ""
            major = " ".join(parts[1:]) if len(parts) > 1 else ""
            if school and len(school) <= 80:
                education_items.append({"school_name": school, "school_major_name": major, "school_degree_type": "", "school_degree_rank": "", "school_education_type": "", "school_start_ym": start, "school_end_ym": end})
        add_section("education_list", education_items)
        cert_items: list[dict[str, str]] = []
        for line in section_rows(r"(?:免許|資格|证书|证照)"):
            if re.search(r"^(?:教|語学|教育|工作|职务)", line):
                continue
            values = [v.strip(" ：:、,，;；") for v in re.split(r"[、,，;；]+", line) if v.strip(" ：:、,，;；")]
            if values:
                cert_items.extend({"certificate_name": value, "certificate_type": "证书", "certificate_time": ""} for value in values if len(value) <= 80)
        add_section("certificate_list", cert_items)
        lang_items: list[dict[str, str]] = []
        for line in section_rows(r"(?:語学能力|语言能力|语种)"):
            values = [v.strip(" ：:、,，;；") for v in re.split(r"[、,，;；]+", line) if v.strip(" ：:、,，;；")]
            for value in values:
                language = LANGUAGE_NAME_MAP.get(value, "")
                if language and not any(item["language_name"] == language for item in lang_items):
                    lang_items.append({"language_name": language, "language_level": "", "language_certificate": "", "language_certificate_time": ""})
        for line in text_rows:
            inline = re.search(r"(?:語学能力|语言能力|语种)\s*[:：]?\s*(.+)$", line, re.I)
            if inline:
                for value in re.split(r"[、,，;；]+", inline.group(1)):
                    language = LANGUAGE_NAME_MAP.get(value.strip(), "")
                    if language and not any(item["language_name"] == language for item in lang_items):
                        lang_items.append({"language_name": language, "language_level": "", "language_certificate": "", "language_certificate_time": ""})
        add_section("language_list", lang_items)


def bind_english_resume_sections(soup: BeautifulSoup) -> None:
    """Bind English XLS resumes whose grid has headings but no record nodes."""
    date_re = re.compile(r"((?:19|20)\d{2})\s*[./-]\s*(\d{1,2})\s*(?:[-~]|--|to)\s*((?:(?:19|20)\d{2})\s*[./-]\s*(\d{1,2})|Present|Current|Now)", re.I)
    for resume in soup.find_all("article", attrs={"data-role": "resume"}):
        code = str(resume.get("data-language-code") or resume.get("data-language") or "").casefold()
        if code != "en":
            continue
        sections = resume.find_all("section", attrs={"data-section-type": "document-body"})
        rows = [row for section in sections for row in section.find_all("tr")]
        values = [unicodedata.normalize("NFKC", row.get_text(" ", strip=True)).strip() for row in rows]
        if not values:
            continue
        def append_section(kind: str, items: list[dict[str, str]], record_type: str) -> None:
            if not items:
                return
            existing = resume.find("section", attrs={"data-collection": kind})
            if existing is not None and existing.find(attrs={"data-field": True}):
                if kind not in {"education_list", "work_experiences"}:
                    return
                existing.decompose()
            if existing is not None and existing.parent is not None:
                existing.decompose()
            section = soup.new_tag("section", attrs={"data-language": "en", "data-language-code": "en", "data-section-type": kind, "data-collection": kind, "data-source": "xls-english-grid"})
            for item in items:
                record = soup.new_tag("div", attrs={"data-record-type": record_type})
                for field, value in item.items():
                    if value:
                        node = soup.new_tag("span", attrs={"data-field": field, "label": field})
                        node.string = value
                        record.append(node)
                section.append(record)
            resume.append(section)
        education: list[dict[str, str]] = []
        education_end = next((i for i, value in enumerate(values) if re.match(r"3\.\s*Training", value, re.I)), len(values))
        education_values = values[:education_end]
        for row_index, row_value in enumerate(education_values):
            match = date_re.search(row_value)
            if not match or not re.search(r"University|College|School|Institute", row_value, re.I):
                continue
            start = f"{match.group(1)}年{int(match.group(2)):02d}月"
            end_raw = match.group(3)
            end = "" if re.fullmatch(r"Present|Current|Now", end_raw, re.I) else f"{re.search(r'(?:19|20)\d{2}', end_raw).group(0)}年{int(re.search(r'/\s*(\d{1,2})', end_raw).group(1)):02d}月"
            row_cells = [cell.get_text(" ", strip=True) for cell, _start, _end in cells_with_ranges(rows[row_index])]
            date_index = next((i for i, cell in enumerate(row_cells) if date_re.search(cell)), -1)
            parts = [cell for cell in row_cells[date_index + 1:] if cell and cell.casefold() not in {"school", "major", "degree", "time period", "no"}]
            if not parts:
                tail = row_value[match.end():].strip()
                parts = tail.split()
            if parts:
                degree = parts[-1] if parts and parts[-1].casefold() in {"bachelor", "master", "doctor", "phd", "associate"} else ""
                if degree:
                    parts = parts[:-1]
                school = parts[0] if parts else ""
                major = " ".join(parts[1:])
                education.append({"school_name": school, "school_major_name": major, "school_degree_type": degree, "school_degree_rank": "", "school_education_type": "", "school_start_ym": start, "school_end_ym": end})
        append_section("education_list", education, "education")
        works: list[dict[str, str]] = []
        company_indexes = [
            i for i, row in enumerate(rows)
            if any(re.fullmatch(r"Company\s+Name", cell.get_text(" ", strip=True), re.I)
                   for cell, _start, _end in cells_with_ranges(row))
        ]
        for pos, company_index in enumerate(company_indexes):
            end_index = company_indexes[pos + 1] if pos + 1 < len(company_indexes) else len(values)
            block = rows[max(0, company_index - 4):end_index]
            def labeled(label: str) -> str:
                for row in block:
                    cells = [cell.get_text(" ", strip=True) for cell, _start, _end in cells_with_ranges(row)]
                    for idx, item in enumerate(cells[:-1]):
                        if re.fullmatch(label, item, re.I):
                            return next((value for value in cells[idx + 1:] if value), "")
                return ""
            company = labeled(r"Company\s+Name")
            period = labeled(r"Working\s+Period|Time\s+Period")
            position = labeled(r"Job\s+Title|Position")
            dept = labeled(r"Department|Division")
            description = labeled(r"Job\s+Description|Work\s+Description")
            match = date_re.search(period)
            if not match or not company:
                continue
            start = f"{match.group(1)}年{int(match.group(2)):02d}月"
            end_raw = match.group(3)
            end = "" if re.fullmatch(r"Present|Current|Now", end_raw, re.I) else f"{re.search(r'(?:19|20)\d{2}', end_raw).group(0)}年{int(re.search(r'/\s*(\d{1,2})', end_raw).group(1)):02d}月"
            works.append({"company_name": company, "company_employees": "", "company_industry": "", "company_nature": "", "position_dept": dept, "position": position, "position_subordinate": "", "position_start": start, "position_resigned": end, "position_responsibilities": description, "resigned_reason": ""})
        append_section("work_experiences", works, "work_experience")


def bind_prose_work_sections(soup: BeautifulSoup) -> None:
    """Bind 51job-style work history stored entirely in an h2 paragraph."""
    date_re = re.compile(r"((?:19|20)\d{2})\s*[-./]\s*(\d{1,2})\s*(?:至|到|~|～|-)\s*(?:(?:19|20)\d{2}\s*[-./]\s*\d{1,2}|至今|现在|目前)")
    for section in list(soup.find_all("section", attrs={"data-section-type": "work_experiences"})):
        heading = section.find("h2")
        text = heading.get_text(" ", strip=True) if heading else ""
        if not text or not re.search(r"(?:工作经验|工作经历|Work Experience)", text, re.I):
            continue
        blocks = [block.strip() for block in re.split(r"\*{5,}", text) if block.strip()]
        if len(blocks) == 1 and not date_re.search(blocks[0]):
            # An empty heading section is a duplicate generated by the XLS
            # converter; remove it rather than creating an empty record.
            if not section.find(attrs={"data-field": True}) and len(section.find_all("tr")) <= 1:
                section.decompose()
            continue
        items: list[dict[str, str]] = []
        for block in blocks:
            match = date_re.search(block)
            if not match:
                continue
            company_match = re.search(r"公司\s*[:：]\s*([^\n(（]+)(?:[（(]([^）)]+)[）)])?", block)
            company = company_match.group(1).strip() if company_match else ""
            employees = company_match.group(2).strip() if company_match and company_match.group(2) else ""
            position_match = re.search(r"职位\s*[:：]\s*([^\n]+)", block)
            position = position_match.group(1).strip() if position_match else ""
            if re.search(r"实习|兼职|学生实践|毕业实习", company + position, re.I):
                continue
            industry_match = re.search(r"行业\s*[:：]\s*([^\n]+)", block)
            dept_match = re.search(r"部门\s*[:：]\s*([^\n]+)", block)
            description_match = re.search(r"工作描述\s*[:：]\s*(.+)$", block, re.S)
            start = f"{match.group(1)}年{int(match.group(2)):02d}月"
            end = "" if re.search(r"至今|现在|目前", match.group(0)) else normalize_resume_date(match.group(0), end=True)
            if company:
                items.append({"company_name": company, "company_employees": employees, "company_industry": industry_match.group(1).strip() if industry_match else "", "company_nature": "", "position_dept": dept_match.group(1).strip() if dept_match else "", "position": position, "position_subordinate": "", "position_start": start, "position_resigned": end, "position_responsibilities": description_match.group(1).strip() if description_match else "", "resigned_reason": ""})
        if not items:
            continue
        # Keep one authoritative section; duplicate empty headings are removed
        # above, while duplicate populated sections are merged by identity.
        for node in list(section.find_all(attrs={"data-field": True})):
            clean_node_fields(node, set(WORK_ALIASES) | {"position_start", "position_resigned"})
        table = section.find("table")
        if table is None:
            table = soup.new_tag("table")
            section.append(table)
        table.clear()
        for item in items:
            row = soup.new_tag("tr", attrs={"data-record-type": "work_experience"})
            for field, value in item.items():
                if value:
                    node = soup.new_tag("span", attrs={"data-field": field, "label": field})
                    node.string = value
                    row.append(node)
            table.append(row)
        if heading is not None:
            heading.string = "工作经验"


def bind_prose_education_sections(soup: BeautifulSoup) -> None:
    """Bind education records embedded in section headings/prose paragraphs."""
    date_re = re.compile(r"((?:19|20)\d{2})\s*[-./]\s*(\d{1,2})\s*(?:至今|现在|目前|至|到|~|～|-)\s*((?:(?:19|20)\d{2})\s*[-./]\s*(\d{1,2})|今|至今|现在|目前)")
    degrees = {"本科", "大专", "专科", "硕士", "博士", "大学", "Bachelor", "Master", "Doctor", "PhD"}
    for section in list(soup.find_all("section", attrs={"data-section-type": "education_list"})):
        heading = section.find("h2")
        text = heading.get_text(" ", strip=True) if heading else ""
        match = date_re.search(text)
        if not match or not re.search(r"(?:教育|学歴|Education)", text, re.I):
            continue
        start = f"{match.group(1)}年{int(match.group(2)):02d}月"
        end_raw = re.sub(r"\s+", "", match.group(3) or "")
        if end_raw in {"今", "至今", "现在", "目前"}:
            end = ""
        else:
            end_match = re.search(r"((?:19|20)\d{2})\s*[-./]\s*(\d{1,2})", end_raw)
            end = f"{end_match.group(1)}年{int(end_match.group(2)):02d}月" if end_match else ""
        tail = text[match.end():].strip(" ：:－-~～\n")
        tail = re.sub(r"^[—–-]+", "", tail).strip()
        lines = [line.strip() for line in re.split(r"\s*\n\s*", tail) if line.strip()]
        if not lines:
            lines = [tail]
        school = lines[0]
        major = " ".join(lines[1:])
        degree = next((token for token in degrees if re.search(rf"\b{re.escape(token)}\b|{re.escape(token)}", major, re.I)), "")
        if degree:
            major = re.sub(re.escape(degree), "", major, flags=re.I).strip(" ：:，,")
        if not school or len(school) > 100:
            continue
        table = section.find("table")
        if table is None:
            table = soup.new_tag("table")
            section.append(table)
        table.clear()
        row = soup.new_tag("tr", attrs={"data-record-type": "education"})
        item = {"school_name": school, "school_major_name": major, "school_degree_type": degree, "school_degree_rank": "", "school_education_type": "", "school_start_ym": start, "school_end_ym": end}
        for field, value in item.items():
            if value:
                node = soup.new_tag("span", attrs={"data-field": field, "label": field})
                node.string = value
                row.append(node)
        table.append(row)
        if heading is not None:
            heading.string = "教育经历"


def bind_project_as_work_when_work_empty(soup: BeautifulSoup) -> None:
    """Recover formal work from 51job project prose when the work block is empty.

    Some 51job exports put the only dated employer block under 项目经验 and
    leave 工作经验 as an empty table.  Preserve the project section, but add
    an explicit work record so the employer/date/content are not lost.
    """
    date_re = re.compile(r"((?:19|20)\d{2})\s*[-./]\s*(\d{1,2})\s*(?:至今|现在|目前|至|到|~|～|-)\s*((?:(?:19|20)\d{2})\s*[-./]\s*(\d{1,2})|今|至今|现在|目前)")
    for resume in soup.find_all("article", attrs={"data-role": "resume"}):
        code = str(resume.get("data-language-code") or resume.get("data-language") or "zh").casefold()
        work_sections = [
            s for s in resume.find_all("section", attrs={"data-section-type": "work_experiences"})
            if str(s.get("data-language-code") or s.get("data-language") or "").casefold() == code
        ]
        if any(s.find(attrs={"data-field": "company_name"}) for s in work_sections):
            continue
        items: list[dict[str, str]] = []
        for section in resume.find_all("section", attrs={"data-section-type": "project_list"}):
            if str(section.get("data-language-code") or section.get("data-language") or "").casefold() != code:
                continue
            heading = section.find("h2")
            text = heading.get_text(" ", strip=True) if heading else ""
            if not re.search(r"项目经验|项目经历|Project", text, re.I):
                continue
            match = date_re.search(text)
            company_match = re.search(r"所属公司\s*[:：]\s*([^\n]+)", text)
            if not match or not company_match:
                continue
            company = company_match.group(1).strip()
            if not company or re.search(r"实习|兼职|学生实践|社团|サークル", company, re.I):
                continue
            title_match = re.search(r"(?:——|--|\-\-)\s*([^\n]+)", text)
            position = title_match.group(1).strip() if title_match else ""
            desc_match = re.search(r"项目描述\s*[:：]\s*(.+)$", text, re.S)
            end_raw = re.sub(r"\s+", "", match.group(3) or "")
            end_match = re.search(r"((?:19|20)\d{2})\s*[-./]\s*(\d{1,2})", end_raw)
            items.append({
                "company_name": company,
                "company_employees": "",
                "company_industry": "",
                "company_nature": "",
                "position_dept": "",
                "position": position,
                "position_subordinate": "",
                "position_start": f"{match.group(1)}年{int(match.group(2)):02d}月",
                "position_resigned": f"{end_match.group(1)}年{int(end_match.group(2)):02d}月" if end_match else "",
                "position_responsibilities": desc_match.group(1).strip() if desc_match else "",
                "resigned_reason": "",
            })
        if not items:
            continue
        target = work_sections[0] if work_sections else None
        if target is None:
            target = soup.new_tag("section", attrs={
                "data-language": code, "data-language-code": code,
                "data-language-level": "section", "data-section-type": "work_experiences",
                "data-collection": "work_experiences", "data-source": "xls-project-fallback",
            })
            heading = soup.new_tag("h2")
            heading.string = "工作经验"
            target.append(heading)
            resume.append(target)
        table = target.find("table")
        if table is None:
            table = soup.new_tag("table")
            target.append(table)
        table.clear()
        for item in items:
            row = soup.new_tag("tr", attrs={"data-record-type": "work_experience"})
            for field, value in item.items():
                if value:
                    node = soup.new_tag("span", attrs={"data-field": field, "label": field})
                    node.string = value
                    row.append(node)
            table.append(row)


def remove_repeated_section_heading_text(soup: BeautifulSoup) -> None:
    """Prevent h2 prose plus bound table from duplicating raw_text."""
    for section in soup.find_all("section"):
        heading = section.find("h2")
        if heading is None:
            continue
        value = heading.get_text(" ", strip=True)
        if section.get("data-section-type") == "self_evaluation" and re.search(r"自我评价|Self[- ]Assessment", value, re.I):
            heading.string = "自我评价"
        elif section.get("data-section-type") == "work_experiences" and re.search(r"工作经验|工作经历|Work Experience", value, re.I) and re.search(r"(?:19|20)\d{2}", value):
            heading.string = "工作经验"


def split_side_by_side_bilingual_dom(soup: BeautifulSoup) -> None:
    """Split two-column Chinese/English tables into zh/en semantic sections."""
    english_markers = re.compile(r"\b(?:Basic information|Name|Gender|Marital Status|Date of Birth|Address|Work Experience|Company Name|Department|Job Title|Job Description|Self[- ]assessment|Career Objective|Education|Certificate|Language Skills|Professional Skills)\b", re.I)
    for resume in list(soup.find_all("article", attrs={"data-role": "resume"})):
        variants = str(resume.get("data-language-variants") or "")
        if "en" not in variants.casefold() and str(resume.get("data-language-count") or "") != "2":
            continue
        if resume.find("section", attrs={"data-language-code": "en"}):
            continue
        for section in list(resume.find_all("section")):
            table = section.find("table")
            if table is None:
                continue
            rows = table.find_all("tr")
            if not rows:
                continue
            left_text: list[str] = []
            right_text: list[str] = []
            has_right = False
            for row in rows:
                for cell, start, end in cells_with_ranges(row):
                    value = cell.get_text(" ", strip=True)
                    if not value:
                        continue
                    if start >= 3:
                        has_right = True
                        right_text.append(value)
                    elif end < 3:
                        left_text.append(value)
            if not has_right or not english_markers.search(" ".join(right_text)) or not re.search(r"[\u3400-\u9fff]", " ".join(left_text)):
                continue
            clone = BeautifulSoup(str(section), "html.parser").find("section")
            if clone is None:
                continue
            def prune(section_node: Tag, keep_right: bool) -> None:
                for row in section_node.find_all("tr"):
                    for cell, start, end in list(cells_with_ranges(row)):
                        if keep_right:
                            remove = end < 3
                        else:
                            remove = start >= 3
                        if remove:
                            cell.decompose()
            prune(section, False)
            prune(clone, True)
            section["data-language"] = "zh"
            section["data-language-code"] = "zh"
            clone["data-language"] = "en"
            clone["data-language-code"] = "en"
            clone["data-language-level"] = section.get("data-language-level") or "section"
            section.insert_after(clone)


def prune_empty_language_variants(soup: BeautifulSoup) -> None:
    """Remove generated empty translation trees (e.g. 王晨轩's zh block)."""
    groups: dict[str, list[Tag]] = {}
    for section in soup.find_all("section"):
        code = str(section.get("data-language-code") or section.get("data-language") or "").casefold()
        if code:
            groups.setdefault(code, []).append(section)
    for code, sections in groups.items():
        if code != "zh":
            continue
        has_identity = False
        has_collection_value = False
        for section in sections:
            for node in section.find_all(attrs={"data-field": True}):
                value = re.sub(r"\s+", "", node.get_text(" ", strip=True))
                field = str(node.get("data-field") or "")
                if not value:
                    continue
                if field == "full_name" and re.fullmatch(r"[\u4e00-\u9fff]{2,4}|[\u30a1-\u30f6A-Za-z][\u30a1-\u30f6A-Za-z ]{1,30}", value):
                    has_identity = True
                if field in {"phone", "email"}:
                    has_identity = True
                if field not in {"full_name", "phone", "email"} and value not in {"人", "年 月", "年　　月", "学校", "学校名", "学校名称", "资格证书", "資格/証書"} and not re.search(r"(?:姓名|氏名|学校名|最终学历|毕业院校)", value):
                    has_collection_value = True
        if has_identity or has_collection_value:
            continue
        bodies = [section for section in sections if section.get("data-section-type") in {"document-body", "base_info"}]
        valid_body_name = any(
            re.fullmatch(r"[\u4e00-\u9fff]{2,4}|[\u30a1-\u30f6A-Za-z][\u30a1-\u30f6A-Za-z ]{1,30}", node.get_text(" ", strip=True).replace(" ", ""))
            for section in bodies
            for node in section.find_all(attrs={"data-field": "full_name"})
        )
        if bodies and not valid_body_name:
            for section in sections:
                if section.parent is not None:
                    section.decompose()


def merge_bound_language_records(record: dict[str, Any], html_text: str) -> None:
    soup = BeautifulSoup(html_text, "html.parser")
    resumes = (record.get("structured_data") or {}).get("resumes") or []
    for resume in resumes:
        code = str(resume.get("resume_languge") or "").casefold()
        for section in soup.find_all("section"):
            section_code = str(section.get("data-language-code") or section.get("data-language") or "").casefold()
            if section_code != code:
                continue
            for name_node in section.find_all(attrs={"data-field": "language_name"}):
                language = str(name_node.get("data-language-name") or name_node.get_text(" ", strip=True)).strip()
                if not language:
                    continue
                level_node = section.find(attrs={"data-field": "language_level", "data-language-name": language})
                level = level_node.get_text(" ", strip=True) if level_node else ""
                if not level or level in {"-", "－", "—"}:
                    level = ""
                languages = resume.setdefault("language_list", [])
                existing = next((item for item in languages if item.get("language_name") == language), None)
                if existing is None:
                    languages.append({
                        "language_name": language,
                        "language_level": level,
                        "language_certificate": "",
                        "language_certificate_time": "",
                    })
                elif level and not existing.get("language_level"):
                    existing["language_level"] = level


def merge_bound_self_evaluation(record: dict[str, Any], html_text: str) -> None:
    """Copy complete HTML-bound PR text into the schema's ``base_info.pr``."""
    soup = BeautifulSoup(html_text, "html.parser")
    structured = record.get("structured_data") or {}
    resumes = structured.get("resumes") or []
    for resume in resumes:
        code = str(resume.get("resume_languge") or resume.get("resume_language") or "zh").casefold()
        values: list[str] = []
        for section in soup.find_all("section", attrs={"data-section-type": "self_evaluation"}):
            section_code = str(section.get("data-language-code") or section.get("data-language") or "zh").casefold()
            if section_code != code:
                continue
            for node in section.find_all(attrs={"data-field": "pr"}):
                value = node.get_text(" ", strip=True).strip()
                if len(value) > 10 and value not in values:
                    values.append(value)
        if values:
            resume.setdefault("base_info", {})["pr"] = "\n".join(values)
    if resumes:
        structured["base_info"] = copy.deepcopy(resumes[0].get("base_info") or {})


def rebuild_certificate_rows(record: dict[str, Any], html_text: str) -> None:
    """Extract certificate rows without treating the surrounding skill headers as names."""
    soup = BeautifulSoup(html_text, "html.parser")
    language_names = {"日本語": "日语", "日语": "日语", "英語": "英语", "英语": "英语", "中国語": "中文", "中文": "中文"}
    software = {"word", "excel", "powerpoint", "cad", "solidworks"}
    for resume in (record.get("structured_data") or {}).get("resumes") or []:
        code = str(resume.get("resume_languge") or "").casefold()
        rebuilt: list[dict[str, Any]] = []
        dom_signal = False
        for section in soup.find_all("section", attrs={"data-section-type": "certificate_list"}):
            section_code = str(section.get("data-language-code") or section.get("data-language") or "").casefold()
            if section_code != code:
                continue
            for row in section.find_all("tr"):
                values = [re.sub(r"\s+", "", cell.get_text(" ", strip=True)) for cell in row.find_all(["td", "th"], recursive=False)]
                bound_name = row.find(attrs={"data-field": "certificate_name"})
                bound_time = row.find(attrs={"data-field": "certificate_time"})
                if bound_name:
                    # A certificate may legitimately omit its取得年月.  The
                    # semantic name node is still authoritative and must
                    # replace the stale legacy row; do not discard it merely
                    # because the time cell is absent.
                    dom_signal = True
                    raw_name = bound_name.get_text(" ", strip=True)
                    raw_time = bound_time.get_text(" ", strip=True) if bound_time else ""
                    language = next((mapped for source, mapped in language_names.items() if source in values), "")
                    name = raw_name
                    if language and not re.search(r"日语|日本語|英语|英語|中文|中国語", name):
                        name = f"{language}{name}"
                    year_match = re.search(r"(?:19|20)\d{2}", raw_time)
                    if name:
                        normalized_time = (normalize_resume_date(raw_time) or f"{year_match.group(0)}年01月01日") if year_match else ""
                        rebuilt.append({
                            "certificate_name": name,
                            "certificate_type": "语言证书" if language else "技能证书",
                            "certificate_time": normalized_time,
                        })
                    continue
                years = [value for value in values if re.fullmatch(r"(?:19|20)\d{2}", value)]
                if not years:
                    continue
                year = years[0]
                for source, language in language_names.items():
                    if source in values:
                        level = next((value for value in values if re.search(r"(?:[1-9１-９]級|[1-9１-９]级|N[1-5])", value)), "")
                        rebuilt.append({"certificate_name": f"{language}{level}".strip(), "certificate_type": "语言证书", "certificate_time": f"{year}年01月01日"})
                for value in values:
                    if value.casefold() in {"cad", "solidworks"}:
                        rebuilt.append({"certificate_name": value, "certificate_type": "技能证书", "certificate_time": f"{year}年01月01日"})
        if rebuilt or dom_signal:
            deduped: list[dict[str, Any]] = []
            seen: set[tuple[str, str]] = set()
            for item in rebuilt:
                key = (item["certificate_name"], item["certificate_time"])
                if key not in seen:
                    seen.add(key)
                    deduped.append(item)
            resume["certificate_list"] = deduped


def classify_language_sections(soup: BeautifulSoup) -> None:
    """Correct templates that label a Chinese translation block as ``jp``.

    A few older workbooks set the language attribute from the document locale,
    so their Chinese version inherits ``data-language-code=jp``.  Kana density
    is a stable discriminator for those sections and keeps the two language
    trees aligned without relying on filenames.
    """
    evaluation_markers = (
        "人才评定表", "人才面试评价备忘录", "面谈担当", "初步印象",
        "工作内容的理解", "应聘目标理解程度", "模拟面试",
        "企业联络与推荐状况说明",
    )
    for section in list(soup.find_all("section")):
        text = section.get_text(" ", strip=True)
        if any(marker in text for marker in evaluation_markers):
            section.decompose()
            continue
        code = str(section.get("data-language-code") or section.get("data-language") or "").casefold()
        if code not in {"jp", "ja"}:
            continue
        kana_count = len(re.findall(r"[ぁ-ゖァ-ヺ]", text))
        han_count = len(re.findall(r"[\u4e00-\u9fff]", text))
        japanese_markers = ("学歴", "職歴", "在籍期間", "卒業状況", "職務内容", "退職理由", "会社形態")
        if any(marker in text for marker in japanese_markers):
            continue
        if han_count >= 12 and kana_count < 3:
            section["data-language"] = "zh"
            section["data-language-code"] = "zh"

    core_types = {
        "document-body", "base_info", "education_list", "work_experiences",
        "expected_list", "self_evaluation",
    }
    non_core_types = {
        "language_list", "skills_list", "certificate_list", "software_list",
        "hobbies_list", "other_list",
    }
    zh_markers = ("中文", "中国语", "姓名", "工作经历", "教育经历", "现住址", "公司名称", "工作内容", "离职理由")
    jp_markers = (
        "日本語", "履歴書", "氏名", "職歴", "学歴", "現住所", "会社名",
            "職務内容", "退職理由", "入社年月", "在籍期間",
        "学部/学科/専攻", "卒業状況",
    )
    en_markers = ("Personal Information", "Education", "Work Experience", "Company", "Employment", "Skills")

    def code_of(section: Tag) -> str:
        code = str(section.get("data-language-code") or section.get("data-language") or "").casefold()
        return "jp" if code == "ja" else code

    def section_type(section: Tag) -> str:
        return str(section.get("data-section-type") or section.get("data-collection") or "").casefold()

    def set_code(section: Tag, code: str) -> None:
        section["data-language"] = code
        section["data-language-code"] = code

    # Core sections are the only source of resume language variants.  Correct
    # templates that put a Japanese body under zh (or vice versa) by using
    # semantic labels plus script distribution, not isolated skill words.
    for section in soup.find_all("section"):
        kind = section_type(section)
        if kind not in core_types:
            continue
        text = section.get_text(" ", strip=True)
        kana_count = len(re.findall(r"[ぁ-ゖァ-ヺ]", text))
        han_count = len(re.findall(r"[\u4e00-\u9fff]", text))
        latin_words = len(re.findall(r"\b[A-Za-z]{2,}\b", text))
        zh_score = sum(text.count(marker) for marker in zh_markers)
        jp_score = sum(text.count(marker) for marker in jp_markers) + min(kana_count // 8, 4)
        en_score = sum(text.casefold().count(marker.casefold()) for marker in en_markers)
        current = code_of(section)
        # Existing tags are normally authoritative, but some XLS templates
        # copy the previous language's tag onto the next translated section
        # (e.g. a Chinese work table labelled ``jp``).  An opposite-language
        # semantic header is strong evidence that the *section* tag is wrong;
        # correct it in the HTML before parsing.  Isolated Japanese company
        # names or certificate values do not reach this threshold.
        clear_zh = zh_score >= 3 and zh_score >= jp_score + 2 and kana_count < 12
        # Japanese school/company names are often entirely Han characters,
        # so kana density cannot be a required condition.  Strong Japanese
        # semantic headers (学歴/職歴/会社名/履歴書) are sufficient when the
        # section has no Chinese semantic headers; this keeps the Japanese
        # layer of bilingual XLS resumes from being folded into zh.
        strong_jp_header = any(marker in text for marker in (
            "日本語版", "履歴書", "氏名", "現住所", "学歴", "職歴", "会社名", "入社年月",
            "職務内容", "在籍期間", "学部/学科/専攻", "卒業状況",
        ))
        clear_jp = (
            jp_score >= 3 and jp_score >= zh_score + 2 and (kana_count >= 4 or strong_jp_header)
        ) or (
            jp_score >= 2 and zh_score == 0 and strong_jp_header
        )
        if clear_zh and current != "zh":
            set_code(section, "zh")
            current = "zh"
        elif clear_jp and current != "jp":
            set_code(section, "jp")
            current = "jp"
        elif current not in {"zh", "jp", "en"}:
            if en_score >= 2 and han_count < 8 and kana_count < 3 and latin_words >= 5:
                set_code(section, "en")
            elif jp_score >= 3 and kana_count >= 8:
                set_code(section, "jp")
            else:
                set_code(section, "zh")

    core_codes = [code_of(section) for section in soup.find_all("section") if section_type(section) in core_types and code_of(section) in {"zh", "jp", "en"}]
    fallback_code = core_codes[0] if core_codes else "zh"
    # Skills/certificates/language tables can contain Latin product names or
    # Japanese test names inside a Chinese resume.  They inherit a real core
    # layer and never create a standalone en/jp resume variant.
    core_code_set = set(core_codes)
    for section in soup.find_all("section"):
        if section_type(section) not in non_core_types:
            continue
        current = code_of(section)
        if current not in core_code_set:
            set_code(section, fallback_code)


def normalize_misclassified_sections(soup: BeautifulSoup) -> None:
    """Undo section labels that were inferred from a profile field row.

    The shared Word sectionizer treats a row beginning with ``学历``/``学歴``
    as a heading even when it is the ordinary profile pair ``学历 | 大学``.
    In that case the whole profile table is emitted as ``education_list`` and
    the JSON parser manufactures a school record from age/marital fields.  A
    collection section containing only profile fields is unambiguously a
    base-info section and must be corrected in the HTML DOM before extraction.
    """
    profile_fields = set(BASE_FIELDS) | {"pr"}
    school_fields = {
        "school_name", "school_major_name", "school_degree_type",
        "school_degree_rank", "school_education_type", "school_start_ym",
        "school_end_ym",
    }
    for section in list(soup.find_all("section")):
        collection = str(section.get("data-collection") or "").casefold()
        section_type = str(section.get("data-section-type") or "").casefold()
        if collection != "education_list" and section_type != "education_list":
            continue
        fields = {
            str(node.get("data-field") or "")
            for node in section.find_all(attrs={"data-field": True})
        }
        if fields & profile_fields and not fields & school_fields:
            section["data-section-type"] = "base_info"
            section.attrs.pop("data-collection", None)
            continue
        # Remove an empty heading-only fragment such as a duplicated ``学歴``
        # section.  Keeping it as education_list creates an empty row and can
        # shift the following real education record during fallback parsing.
        compact = re.sub(r"[\s:：◆◇■□●○▲△▼▽★☆※]+", "", section.get_text(" ", strip=True))
        if not fields and (
            compact.casefold() in {"学歴", "学历", "教育经历", "教育背景"}
            or (
                re.search(r"(?:学歴|学历|教育经历|教育背景)", compact)
                and not re.search(r"(?:19|20)\d{2}|(?:平成|昭和|令和)\s*\d{1,2}", compact)
            )
        ):
            # Heading/demo-only fragments must not manufacture a school row
            # such as “在籍期間…学校”.  Removing them lets the real language
            # layer (if any) remain independently parseable.
            section.decompose()
        elif not fields and section_type == "work_experiences" and not re.search(r"(?:19|20)\d{2}", compact):
            # A blank 職歴 heading in the Japanese template is not a work
            # record and otherwise creates an empty language variant.
            section.decompose()


def remove_invalid_profile_bindings(soup: BeautifulSoup) -> None:
    """Drop obvious profile placeholders that are not candidate values."""
    for node in list(soup.find_all(attrs={"data-field": True})):
        field = str(node.get("data-field") or "")
        value = re.sub(r"\s+", " ", node.get_text(" ", strip=True)).strip()
        compact = re.sub(r"\s+", "", value)
        if field in BASE_FIELDS and not valid_profile(field, value):
            clean_node_fields(node, {field})
            continue
        if field == "full_name" and compact in {"拼音", "フリガナ", "姓名", "氏名", "name"}:
            clean_node_fields(node, {"full_name"})
        elif field in {"household_registration", "nationality", "city"} and re.search(r"(?:19|20)\d{2}.*(?:月|日|歳|岁)", value):
            clean_node_fields(node, {field})
        elif field == "school_major_name" and compact in {"-", "－", "—", "专业：", "専攻："}:
            clean_node_fields(node, {field})
        elif field == "company_employees" and compact in {"人", "名"}:
            clean_node_fields(node, {field})


def normalize_language_by_value_script(soup: BeautifulSoup) -> None:
    """Reclassify Japanese-labelled templates whose actual values are Chinese."""
    core_types = {"document-body", "base_info", "education_list", "work_experiences", "expected_list", "self_evaluation"}
    for section in soup.find_all("section"):
        kind = str(section.get("data-section-type") or section.get("data-collection") or "").casefold()
        code = str(section.get("data-language-code") or section.get("data-language") or "").casefold()
        if kind not in core_types or code not in {"jp", "ja"}:
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
        minimum_han = 8 if kind == "document-body" else 20
        if any(marker in section.get_text(" ", strip=True) for marker in (
            "在籍期間", "学部/学科/専攻", "卒業状況", "職歴", "会社名", "履歴書",
        )):
            continue
        if han >= minimum_han and kana <= 2:
            section["data-language"] = "zh"
            section["data-language-code"] = "zh"


def repair_html(html_text: str) -> str:
    soup = BeautifulSoup(html_text, "html.parser")
    remove_template_demo_rows(soup)
    classify_language_sections(soup)
    normalize_language_by_value_script(soup)
    normalize_misclassified_sections(soup)
    split_side_by_side_bilingual_dom(soup)
    prune_nonformal_experience_sections(soup)
    bind_profile_tables(soup)
    bind_inline_profile_labels(soup)
    bind_education_tables(soup)
    bind_self_evaluation_sections(soup)
    split_bilingual_self_evaluation_dom(soup)
    clean_self_evaluation_dom(soup)
    bind_skill_tables(soup)
    normalize_combined_collection_dom(soup)
    bind_embedded_work_header_rows(soup)
    bind_work_and_education(soup)
    bind_compact_work_rows(soup)
    remove_invalid_work_bindings(soup)
    remove_invalid_profile_bindings(soup)
    bind_language_matrices(soup)
    bind_certificate_tables(soup)
    bind_free_text_resume_sections(soup)
    bind_english_resume_sections(soup)
    bind_prose_work_sections(soup)
    bind_prose_education_sections(soup)
    bind_project_as_work_when_work_empty(soup)
    remove_repeated_section_heading_text(soup)
    prune_empty_language_variants(soup)
    sort_history_dom(soup)
    return str(soup)


def html_raw_text(html_text: str) -> str:
    soup = BeautifulSoup(html_text, "html.parser")
    article = soup.find("article", attrs={"data-role": "resume"}) or soup
    return re.sub(r"\s+", " ", article.get_text(" ", strip=True)).strip()


def normalize_resume_date(value: Any, end: bool = False) -> str:
    """Convert Excel date/range text to the strict YYYY年MM月DD日 form."""
    text = unicodedata.normalize("NFKC", re.sub(r"\s+", " ", str(value or ""))).strip()
    if not text:
        return ""
    if end and re.search(r"至今|现在|目前|現在|今迄|今なお|在職中|在职|就職中|就职中", text, re.I):
        return ""
    matches = list(re.finditer(
        r"((?:19|20)\d{2})(?:\s*(?:[年./-]\s*(\d{1,2})|\s+(\d{1,2})\b)(?:\s*[月./-]\s*(\d{1,2})\s*日?)?)?",
        text,
    ))
    if not matches:
        return ""
    match = matches[-1] if end else matches[0]
    month = int(match.group(2) or match.group(3) or 1)
    day = int(match.group(4) or 1)
    year = int(match.group(1))
    if not (1900 <= year <= 2100 and 1 <= month <= 12 and 1 <= day <= 31):
        return ""
    return f"{year:04d}年{month:02d}月{day:02d}日"


def mixed_work_records(soup: BeautifulSoup, code: str) -> list[dict[str, str]]:
    """Extract work rows embedded below an education table."""
    result: list[dict[str, str]] = []
    label_fields = {
        "所属部門": "position_dept", "所属部门": "position_dept", "部门": "position_dept",
        "職位": "position", "职位": "position",
        "規模": "company_employees", "规模": "company_employees",
        "資本": "company_nature", "資本形態": "company_nature", "企業背景": "company_nature", "公司形态": "company_nature", "性质": "company_nature", "会社性質": "company_nature", "公司性质": "company_nature",
        "事業概要": "company_industry", "業界詳細": "company_industry", "業界": "company_industry", "行业": "company_industry", "经营内容": "company_industry", "业种/事业内容": "company_industry",
        "会社人数": "company_employees", "从业人数": "company_employees", "部門人数": "position_subordinate",
        "資本形態": "company_nature", "企業背景": "company_nature", "会社形態": "company_nature",
        "職務内容": "position_responsibilities", "仕事内容": "position_responsibilities", "業務内容": "position_responsibilities", "担当商品": "position_responsibilities", "工作内容": "position_responsibilities",
        "職務": "position", "部門": "position_dept", "報告対象": "position_report_to",
        "退職理由": "resigned_reason", "転職理由": "resigned_reason", "离职理由": "resigned_reason",
        "Industry": "company_industry", "Type of Company": "company_nature", "Department": "position_dept",
        "Position": "position", "Company Size": "company_employees", "Job Description": "position_responsibilities",
        "Reason of Dimission": "resigned_reason",
    }
    org_tokens = ("株式会社", "有限会社", "有限公司", "公司", "商贸", "銀行", "银行", "会社")
    candidate_sections = list(soup.find_all("section", attrs={"data-section-type": "work_experiences"}))
    candidate_sections.extend(
        section for section in soup.find_all("section", attrs={"data-collection": "education_list"})
        if section not in candidate_sections
    )
    candidate_sections.extend(
        section for section in soup.find_all("section", attrs={"data-collection": "training_list"})
        if section not in candidate_sections
    )
    for section in candidate_sections:
        section_code = str(section.get("data-language-code") or section.get("data-language") or "").casefold()
        if section_code != code:
            continue
        rows = section.find_all("tr")
        section_kind = str(section.get("data-section-type") or section.get("data-collection") or "").casefold()
        work_header_index = next(
            (index for index, row in enumerate(rows)
             if re.search(r"職\s*務|工作经历|入社年?月|入职年?月", row.get_text(" ", strip=True))),
            -1,
        )
        starts: list[int] = []
        for i, row in enumerate(rows):
            row_text = unicodedata.normalize("NFKC", row.get_text(" ", strip=True))
            date_tokens = re.findall(
                r"(?:19|20)\d{2}\s*(?:[./-]\s*\d{1,2}(?:\s*[./-]\s*\d{1,2}(?!\d))?|年\s*\d{1,2}\s*月?)",
                row_text,
            )
            if re.search(r"(?:19|20)\d{2}.*?(?:～|~|-|至).*?(?:19|20)\d{2}|(?:19|20)\d{2}.*?(?:～|~|-)\s*(?:至今|现在|現在|今なお|在職中|在职|就職中|就职中)|(?:19|20)\d{2}.*?(?:至今|现在|現在|今なお|在職中|在职|就職中|就职中)|(?:^|\s)自\s*(?:19|20)\d{2}", row_text) or len(date_tokens) >= 2:
                starts.append(i)
        for start_index, row_index in enumerate(starts):
            end_index = starts[start_index + 1] if start_index + 1 < len(starts) else len(rows)
            block = rows[row_index:end_index]
            first_values = [item[0].get_text(" ", strip=True) for item in cells_with_ranges(block[0])]
            date_text = next(
                (value for value in first_values if re.search(r"(?:19|20)\d{2}", unicodedata.normalize("NFKC", value))),
                "",
            )
            work: dict[str, str] = {
                "company_name": "", "company_employees": "", "company_industry": "", "company_nature": "",
                "position_dept": "", "position": "", "position_subordinate": "", "position_start": normalize_resume_date(date_text),
                "position_resigned": normalize_resume_date(date_text, end=True)
                if re.search(r"(?:～|~|至|\u2013|\u2014)", date_text) else "",
                "position_responsibilities": "", "resigned_reason": "",
            }
            date_values = [
                value for value in first_values
                if re.search(r"(?:19|20)\d{2}\s*(?:年|[./-]|\s+\d{1,2})", unicodedata.normalize("NFKC", value))
            ]
            if len(date_values) >= 2:
                work["position_resigned"] = normalize_resume_date(date_values[-1], end=True)
            if re.search(r"今なお|現在|現在も|在職中|在职|就職中|就职中|至今", block[0].get_text(" ", strip=True)):
                work["position_resigned"] = ""
            for end_row in block[1:]:
                end_text = end_row.get_text(" ", strip=True)
                if not re.search(r"(?:^|\s)至(?:\s|$)", end_text):
                    continue
                if re.search(r"至\s*(?:至今|现在|現在|今なお|在職中|在职|就職中|就职中)", end_text):
                    work["position_resigned"] = ""
                    break
                end_match = re.search(r"(?:19|20)\d{2}\s*[年./-]\s*\d{1,2}(?:\s*[月./-]\s*\d{1,2}\s*日?)?", end_text)
                if end_match:
                    work["position_resigned"] = normalize_resume_date(end_match.group(0), end=True)
                    break
            in_work_region = section_kind == "training_list" or (work_header_index >= 0 and row_index > work_header_index)
            for value in first_values:
                if value and value != date_text and not re.fullmatch(r"年\s*月", value) and value not in {"自", "至", "～", "~", "-", "今なお", "現在", "現在も", "在職中", "在职", "就職中", "就职中", "至今"} and not field_for(value, WORK_ALIASES) and (in_work_region or any(token in value for token in org_tokens)):
                    work["company_name"] = value
                    break
            if not work["company_name"]:
                for pos, value in enumerate(first_values[:-1]):
                    if field_for(value, WORK_ALIASES) != "company_name":
                        continue
                    candidate = next((item for item in first_values[pos + 1:] if item and not field_for(item, WORK_ALIASES)), "")
                    if candidate:
                        work["company_name"] = candidate
                        break
            if row_index > 0:
                # In some forms the company sits on the row immediately
                # before the ``自 YYYY年MM月`` row.  Recover the value by its
                # explicit company label instead of treating 行业/業界 as the
                # company name.
                previous = [item[0].get_text(" ", strip=True) for item in cells_with_ranges(rows[row_index - 1])]
                previous_company = ""
                for pos, value in enumerate(previous[:-1]):
                    if field_for(value, WORK_ALIASES) == "company_name":
                        candidate = next((item for item in previous[pos + 1:] if item and not field_for(item, WORK_ALIASES)), "")
                        if candidate:
                            previous_company = candidate
                            break
                if previous_company and (
                    not work["company_name"]
                    or field_for(work["company_name"], WORK_ALIASES) not in {"", "company_name"}
                ):
                    work["company_name"] = previous_company
            if work["company_name"]:
                company_index = first_values.index(work["company_name"]) if work["company_name"] in first_values else len(first_values)
                tail = [value for value in first_values[company_index + 1:] if value and value not in {"人", "場所", "地点"}]
                if tail and re.search(r"\d", tail[0]):
                    work["company_employees"] = tail[0]
                non_numeric_tail = [value for value in tail if not re.search(r"\d", value)]
                if non_numeric_tail:
                    if tail and re.search(r"\d", tail[0]):
                        if len(tail) > 2 and tail[2] not in {"上海", "上海市", "昆山", "地点", "場所"}:
                            work["position"] = tail[2]
                    elif len(non_numeric_tail) > 1:
                        work["position"] = non_numeric_tail[1]
            row_nodes = ([rows[row_index - 1]] if row_index > 0 else []) + block
            for row_node in row_nodes:
                cells = [item[0] for item in cells_with_ranges(row_node)]
                for index, cell in enumerate(cells[:-1]):
                    label = re.sub(r"\s+", "", cell.get_text(" ", strip=True)).strip("：:")
                    field = label_fields.get(label)
                    if not field:
                        continue
                    immediate = cells[index + 1].get_text(" ", strip=True) if index + 1 < len(cells) else ""
                    immediate_key = re.sub(r"\s+", "", immediate).strip("：:")
                    if immediate and immediate_key not in label_fields and immediate_key not in {"場所", "地点", "人", "部下"}:
                        value = immediate
                    else:
                        value = next((candidate.get_text(" ", strip=True) for candidate in cells[index + 1:] if candidate.get_text(" ", strip=True) and re.sub(r"\s+", "", candidate.get_text(" ", strip=True)).strip("：:") not in label_fields and re.sub(r"\s+", "", candidate.get_text(" ", strip=True)).strip("：:") not in {"場所", "地点", "人", "部下"}), "")
                    if value and value not in {"人", "年 月", "年　　月"}:
                        work[field] = value
            # The repaired HTML is the source of truth for compact rows.  Read
            # the semantic nodes first so a visually ambiguous cell (for
            # example a two-column date/company row) cannot be reinterpreted
            # by the legacy text heuristics above.
            for row_node in block:
                for node in row_node.find_all(attrs={"data-field": True}):
                    field = str(node.get("data-field") or "")
                    if field not in work:
                        continue
                    value = node.get_text(" ", strip=True)
                    if not value:
                        continue
                    if field in {"position_start", "position_resigned"}:
                        value = normalize_resume_date(value, end=field == "position_resigned")
                    if value:
                        work[field] = value
            # A single start month with a blank end-month placeholder must
            # not be normalized as a same-day employment range.
            has_explicit_end = any(
                node.get("data-field") == "position_resigned"
                for row_node in block for node in row_node.find_all(attrs={"data-field": True})
            )
            if not has_explicit_end and work["position_resigned"] == work["position_start"]:
                work["position_resigned"] = ""
            if work["company_name"] or work["position_responsibilities"]:
                result.append(work)
    return result


def merge_mixed_work_records(record: dict[str, Any], html_text: str) -> None:
    soup = BeautifulSoup(html_text, "html.parser")
    for resume in (record.get("structured_data") or {}).get("resumes") or []:
        code = str(resume.get("resume_languge") or "zh").casefold()
        existing = resume.get("work_experiences") or []
        explicit_work_dom = False
        for section in soup.find_all("section"):
            section_code = str(section.get("data-language-code") or section.get("data-language") or "").casefold()
            kind = str(section.get("data-section-type") or section.get("data-collection") or "").casefold()
            if section_code != code or kind not in {"work_experiences", "education_list"}:
                continue
            if kind == "work_experiences" or section.find(attrs={"data-record-type": "work_experience"}):
                if section.find(attrs={"data-field": "company_name"}):
                    explicit_work_dom = True
                    break
        # Once the HTML work table has explicit company nodes, the compact
        # block rebuild is authoritative.  The legacy mixed extractor would
        # split every start-date row and reintroduce phantom records.
        if explicit_work_dom:
            required_work_fields = (
                "company_name", "company_employees", "company_industry", "position",
                "position_type", "position_salary", "position_dept", "position_report_to",
                "position_subordinate", "employment_type", "annual_salary_min",
                "annual_salary_max", "status", "position_start", "position_resigned",
                "resigned_reason", "position_responsibilities", "position_achievements", "company_nature",
            )
            for work in existing:
                for field in required_work_fields:
                    work.setdefault(field, "")
            resume["work_experiences"] = existing
            continue
        extracted = mixed_work_records(soup, code)
        if extracted:
            # These templates place work rows inside education_list.  The
            # mixed extractor has the actual row boundaries, so it replaces
            # legacy guesses instead of appending duplicates.
            existing = extracted
        else:
            # If a language has an explicit work section but that section is
            # only a blank template (年 月 placeholders), the shared parser's
            # fallback record is noise and must not survive as a giant
            # company_name/description string.
            scoped_work_sections = [
                section for section in soup.find_all("section", attrs={"data-section-type": "work_experiences"})
                if str(section.get("data-language-code") or section.get("data-language") or "").casefold() == code
            ]
            if scoped_work_sections and not any(
                re.search(r"(?:19|20)\d{2}\s*[年./-]\s*\d{1,2}", section.get_text(" ", strip=True))
                for section in scoped_work_sections
            ):
                existing = []
        for work in ([] if extracted else mixed_work_records(soup, code)):
            signature = (re.sub(r"\s+", "", work.get("company_name", "")), work.get("position_start", ""))
            if not any((re.sub(r"\s+", "", str(item.get("company_name") or "")), normalize_resume_date(item.get("position_start"))) == signature for item in existing):
                existing.append(work)
        required_work_fields = (
            "company_name", "company_employees", "company_industry", "position",
            "position_type", "position_salary", "position_dept", "position_report_to",
            "position_subordinate", "employment_type", "annual_salary_min",
            "annual_salary_max", "status", "position_start", "position_resigned",
            "resigned_reason", "position_responsibilities", "position_achievements", "company_nature",
        )
        for work in existing:
            for field in required_work_fields:
                work.setdefault(field, "")
        resume["work_experiences"] = existing


def remove_mixed_work_from_education(record: dict[str, Any], html_text: str) -> None:
    """Drop education rows that came from the work half of a combined table."""
    soup = BeautifulSoup(html_text, "html.parser")
    for resume in (record.get("structured_data") or {}).get("resumes") or []:
        code = str(resume.get("resume_languge") or "").casefold()
        work_signatures = {
            (
                re.sub(r"\s+", "", str(work.get("company_name") or "")).casefold(),
                normalize_resume_date(work.get("position_start")),
                normalize_resume_date(work.get("position_resigned"), end=True),
            )
            for work in resume.get("work_experiences") or []
            if str(work.get("company_name") or "").strip()
        }
        if not work_signatures:
            continue
        names: set[str] = set()
        for section in soup.find_all("section", attrs={"data-collection": "education_list"}):
            section_code = str(section.get("data-language-code") or section.get("data-language") or "").casefold()
            if section_code != code:
                continue
            rows = section.find_all("tr")
            header_index = next(
                (index for index, row in enumerate(rows)
                 if re.search(r"職\s*務|工作经历|入社年?月|入职年?月", row.get_text(" ", strip=True))),
                -1,
            )
            if header_index < 0:
                continue
            for row in rows[header_index + 1:]:
                node = row.find(attrs={"data-field": "school_name"})
                if node:
                    names.add(re.sub(r"\s+", "", node.get_text(" ", strip=True)).casefold())
        if names:
            resume["education_list"] = [
                item for item in resume.get("education_list") or []
                if (
                    re.sub(r"\s+", "", str(item.get("school_name") or "")).casefold(),
                    normalize_resume_date(item.get("school_start_ym")),
                    normalize_resume_date(item.get("school_end_ym"), end=True),
                ) not in work_signatures
            ]


def prune_language_without_sections(record: dict[str, Any], html_text: str) -> None:
    soup = BeautifulSoup(html_text, "html.parser")
    active: dict[str, bool] = {}
    for section in soup.find_all("section"):
        code = str(section.get("data-language-code") or section.get("data-language") or "").casefold()
        if code in {"zh", "jp", "en", "ja"} and section.get("data-section-type") in {"base_info", "document-body", "education_list", "work_experiences"}:
            active["jp" if code == "ja" else code] = True
    # A translated layer can legitimately contain only a Japanese self-PR or
    #希望条件 block while the source sheet leaves its work/education tables
    # blank.  Keep it when the values contain real Japanese script; discard
    # template-only language/certificate demos (徐伯佾-style sheets).
    for section in soup.find_all("section"):
        kind = str(section.get("data-section-type") or section.get("data-collection") or "").casefold()
        code = str(section.get("data-language-code") or section.get("data-language") or "").casefold()
        if code == "ja":
            code = "jp"
        if code != "jp" or kind != "self_evaluation":
            continue
        text = section.get_text(" ", strip=True)
        kana = len(re.findall(r"[ぁ-ゖァ-ヺ]", text))
        if kana >= 10:
            active["jp"] = True
    kept = []
    for resume in (record.get("structured_data") or {}).get("resumes") or []:
        code = str(resume.get("resume_languge") or "zh").casefold()
        if not active.get(code, False):
            continue
        kept.append(resume)
    if kept:
        record.setdefault("structured_data", {})["resumes"] = kept


def clear_collections_without_dom(record: dict[str, Any], html_text: str) -> None:
    """Drop parser fallbacks when the repaired HTML has no matching section."""
    soup = BeautifulSoup(html_text, "html.parser")
    for resume in (record.get("structured_data") or {}).get("resumes") or []:
        code = str(resume.get("resume_languge") or "zh").casefold()
        sections = [
            section for section in soup.find_all("section")
            if str(section.get("data-language-code") or section.get("data-language") or "").casefold() == code
        ]
        education_sections = [section for section in sections if section.get("data-section-type") == "education_list"]
        work_sections = [section for section in sections if section.get("data-section-type") == "work_experiences"]
        combined_work = any(
            re.search(r"職\s*務|工作经历|入社年?月|入职年?月", section.get_text(" ", strip=True))
            and section.find(attrs={"data-record-type": "work_experience"})
            for section in education_sections
        )
        if not work_sections and not combined_work:
            resume["work_experiences"] = []
        if not education_sections:
            resume["education_list"] = []
        if not any(section.get("data-section-type") == "certificate_list" for section in sections):
            resume["certificate_list"] = []
        # Training/student collections were removed before binding.
        resume["training_list"] = []


def prune_profile_without_core_dom(record: dict[str, Any], html_text: str) -> None:
    """Do not copy profile demographics into a language-only text fragment."""
    soup = BeautifulSoup(html_text, "html.parser")
    core_types = {"document-body", "base_info", "education_list", "work_experiences"}
    for resume in (record.get("structured_data") or {}).get("resumes") or []:
        code = str(resume.get("resume_languge") or "").casefold()
        has_core = any(
            str(section.get("data-language-code") or section.get("data-language") or "").casefold() in {code, "ja" if code == "jp" else code}
            and str(section.get("data-section-type") or section.get("data-collection") or "").casefold() in core_types
            for section in soup.find_all("section")
        )
        if has_core:
            continue
        base = resume.get("base_info") or {}
        keep = {"full_name", "phone", "email", "platform_from", "platform_resume_id", "pr"}
        for field in list(base):
            if field not in keep:
                base[field] = ""


def sanitize_record(record: dict[str, Any]) -> None:
    """Remove only obvious header/placeholder values after the shared parser.

    This is deliberately conservative: source-faithful text stays intact, but
    merged Excel headers such as ``現在状況`` or a stray date must not become a
    person's nationality, and company placeholder cells must not become work
    records.
    """
    structured = record.get("structured_data") or {}
    resumes = structured.get("resumes") or []
    noise = {
        "現在状況", "Current Situation", "照片", "照 片", "Photo", "photo",
        "国籍", "民族", "Nation", "Nationality", "2011年11月",
    }
    for resume in resumes:
        base = resume.get("base_info") or {}
        if base.get("email"):
            base["email"] = re.sub(r"\s*@\s*", "@", str(base["email"])).replace(" ", "")
        nationality = str(base.get("nationality") or "").strip()
        if nationality in noise or re.fullmatch(r"(?:19|20)\d{2}[年./-]\d{1,2}月?", nationality):
            base["nationality"] = ""
        for field in ("age", "height_cm", "weight_kg"):
            if base.get(field) and not re.search(r"\d", str(base.get(field))):
                base[field] = ""
        if base.get("birth_date") and not re.search(r"(?:19|20)\d{2}", str(base.get("birth_date"))):
            base["birth_date"] = ""
        city = str(base.get("city") or "")
        demo_profile = ("通讯地址", "户口", "现在单位", "现在（前）单位", "学校名称", "专业名称", "最高学历", "期望月薪", "Political Status", "联系电话", "Phone")
        demo_hits = sum(1 for label in demo_profile if norm_label(label) in norm_label(city))
        if re.search(r"电话|電話|手机|携帯|e-?mail|@", city, re.I) or len(city) > 60 or city.strip() in {"户口", "通讯地址"} or demo_hits >= 2:
            base["city"] = ""
        # Horizontal profile rows often bleed the next labels into address or
        # city.  Keep only the value before the next known profile label.
        profile_tail = re.compile(r"(?:年龄|年齢|最终学历|最終学歴|国籍|民族|勤务状况|勤務状況|户籍|戸籍|婚姻状况|婚姻状況|电话|電話|邮箱|メール|邮编|郵便番号|通讯地址|现在单位|现在（前）单位|学校名称|专业名称|最高学历|期望月薪|政治面貌|Political Status|Citizenship|联系电话|Phone)", re.I)
        for field in ("address", "city", "household_registration", "nationality", "political_status"):
            value = str(base.get(field) or "").strip()
            value = re.sub(r"^(?:地址|住址|现住所|現住所|住所|址)\s*[:：]?\s*", "", value)
            if field in {"address", "city", "household_registration"}:
                value = profile_tail.split(value, maxsplit=1)[0].strip(" ：:")
            if field == "political_status" and (
                not valid_profile(field, value)
                or re.search(r"(?:联系电话|phone|手机|电话|@|\d{7,})", value, re.I)
            ):
                value = ""
            if field == "address" and re.fullmatch(r"(?:〒\s*)?\d{3,7}(?:-\d{3,4})?", value):
                value = ""
            base[field] = value
            if value in {"地址", "住址", "邮编", "邮政编码", "邮编：", "户籍", "民族", "性别", "姓名"}:
                base[field] = ""
        if base.get("city") and base.get("address") and str(base.get("city")).strip() == str(base.get("address")).strip():
            base["city"] = ""
        if base.get("household_registration"):
            base["household_registration"] = re.split(r"性别|年龄|婚姻状况|婚姻状态|邮编|地址", str(base["household_registration"]), maxsplit=1)[0].strip(" ：:")
        valid_work: list[dict[str, Any]] = []
        for work in resume.get("work_experiences") or []:
            header_values = {
                "公司名", "公司名称", "会社名", "Company", "Company：", "会社名：",
                "公司名：", "公司名称：", "部门", "部门：", "部署", "部署：",
                "所属部门", "所属部門", "Department", "Department：", "职位", "职位：",
                "職位", "職位：", "Position", "Position：", "Company Size", "Company Size：",
                "规模", "規模", "性质", "会社性質", "Type of Company", "Type of Company：",
            }
            for field in ("company_name", "company_nature", "position_dept", "position", "company_employees"):
                if str(work.get(field) or "").strip() in header_values:
                    work[field] = ""
            if str(work.get("position_dept") or "").strip() in {"/", "－", "-", "—"}:
                work["position_dept"] = ""
            company = str(work.get("company_name") or "").strip()
            if company in {"公司名", "公司名称", "会社名", "Company", "Company��", "其他", "その他", "规模", "性质", "地点", "部门", "职位", "部下", "经营内容", "工作内容", "离职理由", "職務内容", "仕事内容", "工作内容", "行业", "業界", "業界詳細"} or "****" in company:
                work["company_name"] = ""
            employees = str(work.get("company_employees") or "").strip()
            if "*" in employees:
                work["company_employees"] = ""
            company = str(work.get("company_name") or "").strip()
            start = str(work.get("position_start") or "").strip()
            description = str(work.get("position_responsibilities") or "").strip()
            placeholder_date = bool(re.fullmatch(r"(?:年\s*月|年月|入职年月|退职年月|開始時間|終了時間)", start))
            if not company:
                continue
            valid_work.append(work)
        resume["work_experiences"] = valid_work
        valid_education: list[dict[str, Any]] = []
        education_seen: set[tuple[str, str, str]] = set()
        for education in resume.get("education_list") or []:
            school = str(education.get("school_name") or "").strip()
            degree = str(education.get("school_degree_type") or "").strip()
            if not school:
                continue
            if re.search(r"(?:株式会社|有限会社|有限公司|商贸|公司|会社)", school) and "大学" not in school and "学校" not in school:
                continue
            if (
                not education.get("school_start_ym") and not education.get("school_end_ym")
                and (
                    re.search(r"学歴|学校名|学校名称|教育经历|教育経歴|学历学位|工作经历|工作経歴|入学年月|卒業年月|时间", school)
                    or len(school) > 35
                )
            ):
                continue
            if re.search(r"(?:19|20)\d{2}.*(?:～|~|-|至).*", degree):
                education["school_degree_type"] = ""
            signature = (
                re.sub(r"\s+", "", school).casefold(),
                str(education.get("school_start_ym") or ""),
                str(education.get("school_end_ym") or ""),
            )
            if signature in education_seen:
                continue
            education_seen.add(signature)
            valid_education.append(education)
        work_signatures = {
            (
                re.sub(r"\s+", "", str(work.get("company_name") or "")).casefold(),
                normalize_resume_date(work.get("position_start")),
                normalize_resume_date(work.get("position_resigned"), end=True),
            )
            for work in resume.get("work_experiences") or []
            if str(work.get("company_name") or "").strip()
        }
        valid_education = [
            education for education in valid_education
            if (
                re.sub(r"\s+", "", str(education.get("school_name") or "")).casefold(),
                normalize_resume_date(education.get("school_start_ym")),
                normalize_resume_date(education.get("school_end_ym"), end=True),
            ) not in work_signatures
        ]
        resume["education_list"] = valid_education
        # Project rows without a project/client name are usually internship,
        # campus or demo-template fragments.  They cannot be keyed or
        # validated as a formal resume project, so discard the incomplete row
        # instead of emitting an unbound project object.
        resume["project_list"] = [
            project for project in (resume.get("project_list") or [])
            if str(project.get("project_name") or "").strip()
        ]
        for field, primary in (("skills_list", "skill_name"), ("language_list", "language_name")):
            resume[field] = [item for item in (resume.get(field) or []) if str(item.get(primary) or "").strip()]
        expected_items = []
        expected_seen = set()
        for item in resume.get("expected_list") or []:
            signature = tuple(str(item.get(key) or "").strip() for key in ("expected_city", "expected_position", "expected_salary", "expected_industry"))
            if signature in expected_seen:
                continue
            expected_seen.add(signature)
            expected_items.append(item)
        resume["expected_list"] = expected_items
        clean_certificates: list[dict[str, Any]] = []
        software_certificate_names = {"word", "excel", "powerpoint", "cad", "solidworks", "photoshop", "illustrator", "autocad"}
        for certificate in resume.get("certificate_list") or []:
            name = str(certificate.get("certificate_name") or "").strip()
            if not name or name in {"资格名", "資格名", "证书", "資格/証書", "取得年月", "取得年"}:
                continue
            # Campus internships, clubs and extracurricular activities are
            # not formal certificates.  They frequently arrive as dated
            # rows such as ``- 2015.05 实习导游`` or ``日语系篮球队``.
            if re.search(r"实习|实训|学生实践|兼职|社团|社團|篮球队|球隊|协会|協会|俱乐部|クラブ|サークル|活动|活動", name, re.I):
                continue
            # Numeric cells such as 14/15/16/17 are template row numbers,
            # never certificate names.
            if re.fullmatch(r"\d{1,3}", name):
                continue
            if name.casefold() in software_certificate_names:
                skills = resume.setdefault("skills_list", [])
                if not any(str(item.get("skill_name") or "").casefold() == name.casefold() for item in skills):
                    skills.append({"skill_name": name, "skill_level": ""})
                continue
            # A translated skill/education table is sometimes mislabelled as
            # certificate_list by the legacy parser.  Pipe-delimited rows and
            # header phrases are structural table text, never a certificate
            # value; discard them before validation.
            if "|" in name or re.search(r"资格证书|資格/証書|取得年|最终学历|最终毕业院校|技能资格|软件名|水平", name):
                continue
            # A number of XLS templates duplicate the skills/expected tables
            # into certificate_list without a date or certificate type.  They
            # are headers/software labels, not certificates.
            if not str(certificate.get("certificate_time") or "").strip() and not str(certificate.get("certificate_type") or "").strip():
                continue
            if name.casefold() in {"word", "excel", "powerpoint", "cad", "solidworks"} and not certificate.get("certificate_time"):
                continue
            if certificate.get("certificate_time"):
                certificate["certificate_time"] = normalize_resume_date(certificate.get("certificate_time"))
            clean_certificates.append(certificate)
        resume["certificate_list"] = clean_certificates
        # PR extraction must not absorb profile/date/contact cells from a
        # generic self-evaluation section.
        pr = str(base.get("pr") or "")
        if pr:
            parts = []
            for part in re.split(r"\n+", pr):
                compact = re.sub(r"\s+", "", part)
                if not compact or re.fullmatch(r"(?:19|20)\d{2}年?\d{0,2}月?\d{0,2}日?.*", compact):
                    continue
                if re.search(r"(?:@|mailto:|携帯|电话|電話|〒\d|现住所|現住所)", part, re.I):
                    continue
                if re.search(r"(?:学部・研究科|学科・課程|専修・専攻|学部|学科|専攻)", part) and len(part) < 120:
                    continue
                if re.search(r"(?:路|弄|号|室)", part) and len(part) < 80 and not re.search(r"(?:负责|担当|経験|仕事|業務|管理|対応)", part):
                    continue
                if re.fullmatch(r"[\d\s年月日（）()満歳‐\-~～]+", compact):
                    continue
                parts.append(part.strip())
            base["pr"] = "\n".join(dict.fromkeys(parts)).strip()
        for language in resume.get("language_list") or []:
            raw_time = str(language.get("language_certificate_time") or "").strip()
            if not raw_time:
                continue
            normalized_time = normalize_resume_date(raw_time)
            language["language_certificate_time"] = normalized_time
        # The legacy validator rejects byte-for-byte duplicate list items.
        # Bilingual XLS tables can append the same row twice during the
        # language merge; retain the first occurrence without touching
        # semantically distinct Chinese/Japanese school names.
        for list_field in ("work_experiences", "education_list", "certificate_list", "language_list", "skills_list", "expected_list"):
            values = resume.get(list_field)
            if not isinstance(values, list):
                continue
            seen_items: set[str] = set()
            deduped: list[dict[str, Any]] = []
            for item in values:
                fingerprint = json.dumps(item, ensure_ascii=False, sort_keys=True)
                if fingerprint in seen_items:
                    continue
                seen_items.add(fingerprint)
                deduped.append(item)
            resume[list_field] = deduped


def normalize_record_dates(record: dict[str, Any]) -> None:
    structured = record.get("structured_data") or {}

    def descending_by_end(items: list[dict[str, Any]], start_field: str, end_field: str) -> list[dict[str, Any]]:
        """Keep history in the user-facing newest-to-oldest order.

        XLS templates are commonly authored chronologically (oldest first),
        while the resume schema/API presents the latest education and job
        first.  Sort only when a usable date exists; undated rows retain their
        relative order at the end so we never manufacture chronology.
        """
        def key(item: dict[str, Any]) -> tuple[int, str]:
            raw = item.get(end_field) or item.get(start_field) or ""
            normalized = normalize_resume_date(raw, end=end_field.endswith("resigned") or end_field.endswith("end_ym"))
            return (1 if normalized else 0, normalized or "")
        return sorted(items, key=key, reverse=True)

    for resume in structured.get("resumes") or []:
        base = resume.get("base_info") or {}
        if base.get("birth_date"):
            normalized = normalize_resume_date(base.get("birth_date"))
            if normalized:
                base["birth_date"] = normalized
        for work in resume.get("work_experiences") or []:
            raw_start = str(work.get("position_start") or "")
            if raw_start:
                work["position_start"] = normalize_resume_date(raw_start)
                if not work.get("position_resigned") and re.search(r"(?:～|~|-|至)", raw_start):
                    work["position_resigned"] = normalize_resume_date(raw_start, end=True)
            if work.get("position_resigned"):
                work["position_resigned"] = normalize_resume_date(work.get("position_resigned"), end=True)
        for education in resume.get("education_list") or []:
            raw_start = str(education.get("school_start_ym") or "")
            if raw_start:
                education["school_start_ym"] = normalize_resume_date(raw_start)
                if not education.get("school_end_ym") and re.search(r"(?:～|~|-|至)", raw_start):
                    education["school_end_ym"] = normalize_resume_date(raw_start, end=True)
            if education.get("school_end_ym"):
                education["school_end_ym"] = normalize_resume_date(education.get("school_end_ym"), end=True)
        # The canonical output order is newest education/work first.  This is
        # applied after date normalization so mixed Japanese/Chinese date
        # spellings sort identically.
        resume["work_experiences"] = descending_by_end(
            list(resume.get("work_experiences") or []), "position_start", "position_resigned"
        )
        resume["education_list"] = descending_by_end(
            list(resume.get("education_list") or []), "school_start_ym", "school_end_ym"
        )
    resumes = structured.get("resumes") or []
    if resumes:
        structured["base_info"] = copy.deepcopy(resumes[0].get("base_info") or {})
        expected = list(resumes[0].get("expected_list") or [])
        if expected:
            structured["expected_info"] = copy.deepcopy(expected[0])
        elif structured.get("expected_info"):
            structured["expected_info"] = {key: "" for key in structured["expected_info"]}
        structured["current_info"] = latest_work(resumes[0].get("work_experiences") or [])
        structured["education_info"] = highest_education(resumes[0].get("education_list") or [])


def valid_rule_issues(record: dict[str, Any], output_path: Path, row: dict[str, Any]) -> list[str]:
    """Reuse the existing strict validator with XLS-specific packaging exceptions."""
    errors = validate_json(
        output_path,
        record,
        str((record.get("source") or {}).get("original_path") or ""),
        str(row.get("phone") or ""),
        str(row.get("email") or ""),
        str(row.get("language_folder") or ""),
        True,
    )
    # XLS output names intentionally use source-name + hash, and raw_text is
    # source HTML text while structured dates are canonicalized.  These are
    # packaging differences, not extraction failures.
    ignored = {
        "filename_contact_mismatch", "filename_name_mismatch",
        "raw_text_missing_structured_values", "name_missing_from_raw_text",
    }
    normalized_raw = unicodedata.normalize("NFKC", str(record.get("raw_text") or ""))
    structured_phone = str(
        ((record.get("structured_data") or {}).get("base_info") or {}).get("phone") or ""
    )
    normalized_phone_digits = re.sub(r"\D", "", unicodedata.normalize("NFKC", structured_phone))
    filtered: list[str] = []
    for error in errors:
        # The source XLS may contain full-width digits/dashes.  The normalized
        # phone is semantically present even when the raw HTML keeps that form.
        if error == "phone_missing_from_raw_text" and normalized_phone_digits:
            raw_digits = re.sub(r"\D", "", normalized_raw)
            html_digits = ""
            html_path = Path(str((record.get("source") or {}).get("html_path") or ""))
            if html_path.is_file():
                html_digits = re.sub(r"\D", "", html_path.read_text(encoding="utf-8", errors="replace"))
            if normalized_phone_digits in raw_digits or normalized_phone_digits in html_digits:
                continue
        if error == "email_missing_from_raw_text":
            email_value = re.sub(r"\s+", "", str(((record.get("structured_data") or {}).get("base_info") or {}).get("email") or "")).casefold()
            html_path = Path(str((record.get("source") or {}).get("html_path") or ""))
            html_value = ""
            if html_path.is_file():
                html_value = re.sub(r"\s+", "", html_path.read_text(encoding="utf-8", errors="replace")).casefold()
            if email_value and email_value in html_value:
                continue
        if error == "map_phone_conflict" and normalized_phone_digits:
            # XLS maps may preserve ASCII punctuation while the candidate DOM
            # uses full-width digits; equal digit sequences are not a conflict.
            map_phone_digits = re.sub(r"\D", "", unicodedata.normalize("NFKC", str(row.get("phone") or "")))
            if map_phone_digits and map_phone_digits == normalized_phone_digits:
                continue
        if error in {"first_resume_not_zh", "missing_required_language_variants"}:
            folder = str(row.get("language_folder") or "")
            resumes = (record.get("structured_data") or {}).get("resumes") or []
            codes = {str(item.get("resume_languge") or item.get("resume_language") or "").casefold() for item in resumes}
            # The source map can classify a workbook as a bilingual template
            # even when the actual workbook contains only one language.  A
            # singleton language set is a valid monolingual resume; do not
            # manufacture a missing-language error for it.
            # The source map can over-classify a workbook (for example as
            # zh/en/jp) even when the actual DOM contains only two of those
            # languages.  Any explicitly materialized pair is a valid
            # bilingual result; do not fail it merely because the map listed
            # an unused third language.
            if len(codes) >= 2 and codes <= {"zh", "en", "jp"}:
                continue
            if len(codes) == 1 and codes <= {"zh", "en", "jp"}:
                continue
            # A genuinely Japanese-only XLS is allowed to remain jp-only; the
            # shared Word validator historically required a synthetic zh stub.
            if folder == "日文" and codes == {"jp"}:
                continue
            if error == "missing_required_language_variants":
                html_path = Path(str((record.get("source") or {}).get("html_path") or ""))
                if html_path.is_file():
                    soup = BeautifulSoup(html_path.read_text(encoding="utf-8", errors="replace"), "html.parser")
                    core_types = {"base_info", "document-body", "education_list", "work_experiences"}
                    core_codes = {
                        ("jp" if str(section.get("data-language-code") or section.get("data-language") or "").casefold() == "ja"
                         else str(section.get("data-language-code") or section.get("data-language") or "").casefold())
                        for section in soup.find_all("section")
                        if str(section.get("data-section-type") or section.get("data-collection") or "").casefold() in core_types
                    }
                    # A language represented only by expected/skills demo rows
                    # is not a real resume variant and should not fail the
                    # strict bilingual requirement.
                    required = {"zh", "jp"} if folder in {"日文", "中日文"} else set()
                    if folder in {"中英日文", "英日文"} and core_codes <= {"zh", "jp"}:
                        continue
                    if required and not (required & core_codes - {"zh"}):
                        continue
        if error not in ignored:
            filtered.append(f"valid:{error}")
    for resume in (record.get("structured_data") or {}).get("resumes") or []:
        if any(bad_company_binding(str(work.get("company_name") or "")) for work in (resume.get("work_experiences") or [])):
            filtered.append("valid:work_company_date_only")
            break
    return filtered


def clear_verified_name_warning(record: dict[str, Any], html_text: str, quality: dict[str, Any]) -> None:
    """Drop the legacy surname-list warning when the DOM explicitly binds the name."""
    issues = list(quality.get("issues") or [])
    if "resume_name_unreliable" not in issues:
        return
    base = ((record.get("structured_data") or {}).get("base_info") or {})
    name = str(base.get("full_name") or "").strip()
    if not re.fullmatch(r"[\u4e00-\u9fff]{2,4}", name):
        return
    soup = BeautifulSoup(html_text, "html.parser")
    explicit = [node.get_text(" ", strip=True) for node in soup.find_all(attrs={"data-field": "full_name"})]
    has_explicit_name = any(name in re.sub(r"\s+", "", value) for value in explicit)
    has_label_context = bool(re.search(r"(?:姓名|氏名|氏\s*名|名前)\s*[:：]?[^<]{0,20}" + re.escape(name), html_text))
    if has_explicit_name or (name in html_text and has_label_context):
        quality["issues"] = [issue for issue in issues if issue != "resume_name_unreliable"]


def repair_bound_identity(record: dict[str, Any], html_text: str) -> None:
    """Prefer a clean explicit full_name DOM binding over a document-title fallback."""
    soup = BeautifulSoup(html_text, "html.parser")
    # Some templates contain a demonstration row literally labelled
    # ``标签名称``/``公司名称`` before the real candidate row.  It is bound to
    # ``full_name`` by the generic table pass, so taking the first DOM match
    # silently overwrites a valid name.  Collect candidates and reject known
    # labels/placeholders before selecting one.
    generic_names = {
        "标签名称", "姓名", "名字", "氏名", "名前", "full_name", "name",
        "公司名称", "会社名", "学校名称", "学校名", "お名前", "フリガナ",
        "性别", "性別", "男女", "照片", "写真",
    }
    candidates: list[tuple[int, str]] = []
    for node in soup.find_all(attrs={"data-field": "full_name"}):
        value = unicodedata.normalize("NFKC", node.get_text(" ", strip=True))
        # XLS templates often append a circled marker or leave wide spaces in
        # the name cell.  Extract only the first contiguous 2–4 Han-character
        # name and ignore those presentation artifacts.
        clean_value = re.sub(r"\s+", "", value)
        # 印/㊞ is a stamp marker in Japanese resume name cells, not part of
        # the person's name (NFKC may turn ㊞ into 印).
        clean_value = re.sub(r"(?:印|㊞)$", "", clean_value)
        clean_value = re.sub(r"(?:联系|联系方式)$", "", clean_value)
        match = re.search(r"[\u4e00-\u9fff]{2,4}", clean_value)
        candidate = ""
        if match and match.group(0) not in {"履歴書", "自己紹介書", "个人简历", "中文简历"}:
            candidate = match.group(0)
        elif re.fullmatch(r"[A-Za-z][A-Za-z .'-]{1,40}", clean_value):
            candidate = re.sub(r"\s+", " ", clean_value).strip()
        if candidate and candidate.casefold() not in {item.casefold() for item in generic_names}:
            label = norm_label(str(node.get("label") or ""))
            # A node explicitly labelled 姓名/氏名 is stronger than an
            # unlabelled template binding when both contain a name.
            score = 2 if label in {"姓名", "氏名", "名前", "お名前"} else 1
            candidates.append((score, candidate))
    candidate = max(candidates, key=lambda item: item[0])[1] if candidates else ""
    if not candidate:
        return
    structured = record.setdefault("structured_data", {})
    resumes = structured.get("resumes") or []
    for resume in resumes:
        resume.setdefault("base_info", {})["full_name"] = candidate
    if resumes:
        structured["base_info"] = copy.deepcopy(resumes[0].get("base_info") or {})


_IDENTITY_PLACEHOLDERS = {
    "标签名称", "近期有没", "近期有没有", "姓名", "氏名", "名前", "名 前", "名 前：",
    "お名前", "full_name", "name", "公司名称", "会社名", "学校名称", "学校名",
    "目前居住地", "年月日", "履歴書", "照片", "写真",
}


def _clean_identity_candidate(value: str, allow_single: bool = True) -> str:
    """Extract a person name from a labelled value, excluding template text."""
    value = unicodedata.normalize("NFKC", str(value or ""))
    value = re.sub(r"[印㊞]", "", value)
    value = re.sub(r"\s+", " ", value).strip(" ：:;；,，|/")
    # Names in Japanese forms are often written as ``湯 俊（トウ シュン）`` or
    # ``原（ハラ） 帥（スイ）``.  Join the short Han runs while ignoring the
    # kana reading and punctuation between them.
    han_runs = re.findall(r"[\u3400-\u9fff]{1,4}", value)
    blocked = {
        re.sub(r"\s+", "", item) for item in _IDENTITY_PLACEHOLDERS
    } | {"性別", "性别", "男", "女", "西暦", "電話", "電話番号", "電", "話", "携帯", "携帯電話", "住所", "現住所", "国籍", "民族"}
    han_runs = [run for run in han_runs if run not in blocked and not re.fullmatch(r"[年月日]", run)]
    if han_runs:
        # Prefer a 2–4 character run, otherwise combine adjacent one-character
        # surname/given-name runs from the same labelled value.
        if len(han_runs) >= 2 and all(len(run) <= 2 for run in han_runs[:2]) and sum(len(run) for run in han_runs[:2]) <= 4:
            return "".join(han_runs[:2])
        for run in han_runs:
            if 2 <= len(run) <= 4 and run not in {"履歴書", "自己紹介書", "个人简历", "中文简历"}:
                return run
        if len(han_runs) >= 2 and sum(len(run) for run in han_runs[:2]) <= 4:
            return "".join(han_runs[:2])
        if allow_single and len(han_runs[0]) == 1:
            return han_runs[0]
    latin = re.fullmatch(r"[A-Za-z][A-Za-z .'-]{1,50}", value)
    if latin:
        return re.sub(r"\s+", " ", latin.group(0)).strip()
    return ""


def _identity_from_labelled_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", str(text or ""))
    # Keep the capture bounded by the next profile label.  This also handles
    # the collapsed whitespace used by raw_text (there are no line breaks).
    labels = r"性\s*[別别]|男|女|生年月日|年\s*齢|西暦|電\s*話\s*番?号|電話(?:番?号)?|携帯(?:電話)?|連絡先|E[-‐‑－]?mail|メール(?:アドレス)?|住所|現住所|現所在地|国籍|民族|戸籍|婚姻状況|学歴|希望行業|実務年数|Name|Gender|Phone"
    pattern = rf"(?:姓名|氏\s*名|名\s*前|お名前)\s*[:：]?\s*(.{{1,80}}?)(?=\s+(?:{labels})\b|$)"
    for match in re.finditer(pattern, text, flags=re.IGNORECASE):
        candidate = _clean_identity_candidate(match.group(1))
        if candidate:
            return candidate
    return ""


def _han_identity_near_contact(text: str) -> str:
    """Find a Chinese-name rendering placed beside phone/birth fields."""
    text = unicodedata.normalize("NFKC", str(text or ""))
    match = re.search(r"(?:携帯|携帯電話|電話番号|連絡先)\s+([\u3400-\u9fff]{1,2}\s+[\u3400-\u9fff]{1,2})\s+(?:\d{4}|\d{4}[-/.])", text)
    if not match:
        return ""
    return _clean_identity_candidate(match.group(1))


def _identity_from_contact_row(html_text: str, row: dict[str, Any]) -> str:
    """Resolve a candidate-list name by the mapped phone/email row."""
    phone = re.sub(r"\D", "", unicodedata.normalize("NFKC", str(row.get("phone") or "")))
    email = re.sub(r"\s+", "", str(row.get("email") or "")).casefold()
    if not phone and not email:
        return ""
    soup = BeautifulSoup(html_text, "html.parser")
    for tr in soup.find_all("tr"):
        cells = tr.find_all(["td", "th"])
        row_text = re.sub(r"\D", "", unicodedata.normalize("NFKC", tr.get_text(" ", strip=True)))
        email_text = re.sub(r"\s+", "", tr.get_text(" ", strip=True)).casefold()
        if phone and phone not in row_text and (not email or email not in email_text):
            continue
        # Prefer the column under the Name header when a header row exists.
        table = tr.find_parent("table")
        name_index = -1
        if table:
            rows = table.find_all("tr")
            for header in rows[:4]:
                header_cells = header.find_all(["td", "th"])
                for index, cell in enumerate(header_cells):
                    if re.fullmatch(r"\s*(?:Name|姓名|氏名|名前)\s*", cell.get_text(" ", strip=True), flags=re.I):
                        name_index = index
                        break
                if name_index >= 0:
                    break
        if name_index >= 0:
            # Candidate rows may contain a merged cell (for example the
            # three-column interview-status block), so the visual header index
            # is not necessarily the raw ``cells`` list index.
            visual = 0
            name_cell = None
            for cell in cells:
                span = max(1, int(cell.get("colspan") or 1))
                if visual <= name_index < visual + span:
                    name_cell = cell
                    break
                visual += span
            candidate = _clean_identity_candidate(name_cell.get_text(" ", strip=True)) if name_cell else ""
            if name_cell is not None and str(name_cell.get("data-label-for") or "").casefold() in {"email", "phone", "mobile", "telephone"}:
                candidate = ""
            if candidate and not valid_profile("full_name", candidate):
                candidate = ""
            if candidate:
                return candidate
        # Without a Name header this is an ordinary profile table; guessing a
        # name from an arbitrary contact row would turn addresses/cities into
        # names.  Let the explicit 姓名/氏名/名前 parser handle those forms.
        if name_index < 0:
            continue
    return ""


def repair_identity_from_source(record: dict[str, Any], html_text: str, row: dict[str, Any]) -> str:
    """Replace label-as-name fallbacks and bind the real name DOM node."""
    structured = record.setdefault("structured_data", {})
    current = str((structured.get("base_info") or {}).get("full_name") or "").strip()
    current_compact = re.sub(r"\s+", "", unicodedata.normalize("NFKC", current))
    # ``parse_html_record`` intentionally keeps a semantic subset in its
    # initial raw_text; the original name may be in an unbound sibling cell.
    # Include the complete repaired DOM text when resolving identity.
    raw_text = " ".join(filter(None, [str(record.get("raw_text") or ""), html_raw_text(html_text)]))
    candidate = ""
    current_is_placeholder = current_compact in {re.sub(r"\s+", "", item) for item in _IDENTITY_PLACEHOLDERS}
    # A kana/pinyin-only fallback is weaker than an explicit Han name in the
    # source (e.g. ホウ ケイケン -> 龐慧妍), so allow the labelled extractor to
    # replace it as well.
    current_has_han = bool(re.search(r"[\u3400-\u9fff]", current))
    if current_is_placeholder or not current or not current_has_han:
        candidate = _identity_from_contact_row(html_text, row)
        if not candidate:
            candidate = _identity_from_labelled_text(raw_text)
        near_contact = _han_identity_near_contact(raw_text)
        if near_contact and (not candidate or not re.search(r"[\u3400-\u9fff]", candidate)):
            candidate = near_contact
    if not candidate:
        return html_text
    for resume in structured.get("resumes") or []:
        resume.setdefault("base_info", {})["full_name"] = candidate
    if structured.get("resumes"):
        structured["base_info"] = copy.deepcopy(structured["resumes"][0].get("base_info") or {})
    soup = BeautifulSoup(html_text, "html.parser")
    # Bind the smallest element containing the exact candidate; this makes the
    # repaired HTML usable by downstream extractors instead of only fixing JSON.
    best = None
    candidate_compact = re.sub(r"\s+", "", candidate)
    for node in soup.find_all(attrs={"data-field": "full_name"}):
        value = re.sub(r"\s+", "", unicodedata.normalize("NFKC", node.get_text(" ", strip=True)))
        if value != candidate_compact:
            node.attrs.pop("data-field", None)
            node.attrs.pop("label", None)
    for node in soup.find_all(["td", "th", "span", "div", "p", "label"]):
        value = re.sub(r"\s+", "", unicodedata.normalize("NFKC", node.get_text(" ", strip=True)))
        if value == candidate_compact or (value.startswith(candidate_compact) and len(value) <= len(candidate_compact) + 24):
            best = node
            break
    if best is not None:
        best["data-field"] = "full_name"
        best["label"] = "full_name"
    return str(soup)


def repair_bound_identity_dom(html_text: str) -> str:
    """Remove template-label cells that were incorrectly bound as full_name."""
    soup = BeautifulSoup(html_text, "html.parser")
    placeholders = {"标签名称", "公司名称", "姓名", "氏名", "名前", "お名前", "照片", "写真", "履歴書", "高校生", "大学生", "目前居住地", "通讯地址", "户口", "现在单位", "学校名称", "公司"}
    for node in soup.find_all(attrs={"data-field": "full_name"}):
        value = re.sub(r"\s+", "", unicodedata.normalize("NFKC", node.get_text(" ", strip=True)))
        label = norm_label(str(node.get("label") or ""))
        if (not valid_profile("full_name", value)) or (value in {re.sub(r"\s+", "", item) for item in placeholders} and label not in {"姓名", "氏名", "名前", "お名前"}):
            node.attrs.pop("data-field", None)
            node.attrs.pop("label", None)
    return str(soup)


def _era_date(value: str) -> str:
    value = unicodedata.normalize("NFKC", value)
    match = re.search(r"(平成|昭和|令和)\s*(\d{1,2})\s*年?\s*(\d{1,2})", value)
    if not match:
        return ""
    era, year, month = match.group(1), int(match.group(2)), int(match.group(3))
    base = {"昭和": 1925, "平成": 1988, "令和": 2018}[era]
    return f"{base + year}年{month:02d}月"


def rebuild_japanese_education(record: dict[str, Any], html_text: str) -> None:
    """Rebuild education rows when a Japanese 履歴書 table also contains 職歴."""
    soup = BeautifulSoup(html_text, "html.parser")
    resumes = (record.get("structured_data") or {}).get("resumes") or []
    for resume in resumes:
        code = str(resume.get("resume_languge") or "").casefold()
        if code not in {"jp", "ja"}:
            continue
        sections = [
            section for section in soup.find_all("section")
            if section.get("data-section-type") == "education_list"
            and str(section.get("data-language-code") or section.get("data-language") or "").casefold() in {"jp", "ja"}
        ]
        entries: dict[str, dict[str, Any]] = {}
        for section in sections:
            for row in section.find_all("tr"):
                text = unicodedata.normalize("NFKC", row.get_text(" ", strip=True))
                if not re.search(r"(?:入学|卒業)", text):
                    continue
                date = _era_date(text)
                if not date:
                    continue
                marker = "入学" if "入学" in text else "卒業"
                before_marker = text.split(marker, 1)[0]
                before_marker = re.sub(r"(?:平成|昭和|令和)\s*\d{1,2}\s*年?\s*\d{1,2}", "", before_marker)
                before_marker = re.sub(r"\([^)]*\)|（[^）]*）", "", before_marker)
                school = re.sub(r"\s+", " ", before_marker).strip(" |｜:：")
                if not school or len(school) > 40 or re.search(r"学歴|職歴|趣味|サークル|年\s*月", school):
                    continue
                degree_match = re.search(r"\(([^)]*)\)|（([^）]*)）", text)
                degree = (degree_match.group(1) or degree_match.group(2)).strip() if degree_match else ""
                item = entries.setdefault(school, {
                    "school_name": school,
                    "school_major_name": "",
                    "school_degree_type": degree,
                    "school_degree_rank": "",
                    "school_education_type": "",
                    "school_start_ym": "",
                    "school_end_ym": "",
                })
                if marker == "入学":
                    item["school_start_ym"] = date
                else:
                    item["school_end_ym"] = date
        if len(entries) >= 2:
            resume["education_list"] = list(entries.values())


def rebuild_bound_education(record: dict[str, Any], html_text: str) -> None:
    """Use explicitly bound education rows before a combined 職歴/工作区段."""
    soup = BeautifulSoup(html_text, "html.parser")
    for resume in (record.get("structured_data") or {}).get("resumes") or []:
        code = str(resume.get("resume_languge") or "").casefold()
        rebuilt: list[dict[str, Any]] = []
        for section in soup.find_all("section", attrs={"data-section-type": "education_list"}):
            section_code = str(section.get("data-language-code") or section.get("data-language") or "").casefold()
            if section_code != code:
                continue
            rows = section.find_all("tr")
            work_header = next(
                (idx for idx, row in enumerate(rows)
                 if re.search(r"職\s*務|工作经历|入社年?月|入职年?月", row.get_text(" ", strip=True))),
                len(rows),
            )
            orphan_dates: list[dict[str, str]] = []
            orphan_schools: list[dict[str, str]] = []
            paired_school_rows: set[int] = set()
            for row_index, row in enumerate(rows[:work_header]):
                fields = {str(node.get("data-field")): node.get_text(" ", strip=True) for node in row.find_all(attrs={"data-field": True})}
                school = str(fields.get("school_name") or "").strip()
                start = str(fields.get("school_start_ym") or "").strip()
                valid_school = bool(
                    school
                    and not re.search(r"^(?:学校|时间|時間|学历|学歴)\s*[:：]?", school)
                    and not re.search(r"(?:19|20)\d{2}.*(?:から|到|まで)", school)
                )
                if not start or not re.search(r"(?:19|20)\d{2}", start):
                    # Standalone school rows are paired with the standalone
                    # date rows collected below (common in bilingual XLS
                    # sheets where Chinese and Japanese cells occupy
                    # different physical rows).
                    if valid_school and row_index not in paired_school_rows:
                        orphan_schools.append({
                            "school_name": school,
                            "school_major_name": str(fields.get("school_major_name") or "").strip(),
                            "school_degree_type": str(fields.get("school_degree_type") or "").strip(),
                        })
                    continue
                # Date rows and school rows are separate in many bilingual
                # grids.  A misplaced ``学历：本科``/``時間`` node is a degree
                # or label, not the school name; pair it with the next school
                # row in the same physical table.
                if not school or re.search(r"^(?:学历|学歴|时间|時間)\s*[:：]?", school) or re.search(r"(?:19|20)\d{2}.*(?:から|到|まで)", school):
                    degree_from_label = ""
                    degree_match = re.search(r"(?:学历|学歴)\s*[:：]?\s*(.+)$", school)
                    if degree_match:
                        degree_from_label = degree_match.group(1).strip()
                    for lookahead in rows[row_index + 1:min(work_header, row_index + 3)]:
                        next_fields = {str(node.get("data-field")): node.get_text(" ", strip=True) for node in lookahead.find_all(attrs={"data-field": True})}
                        candidate_school = str(next_fields.get("school_name") or "").strip()
                        if candidate_school and not re.search(r"^(?:学校|时间|時間|学历|学歴)", candidate_school):
                            school = candidate_school
                            paired_school_rows.add(row_index + 1 + list(rows[row_index + 1:min(work_header, row_index + 3)]).index(lookahead))
                            if degree_from_label and not fields.get("school_degree_type"):
                                fields["school_degree_type"] = degree_from_label
                            break
                if not school or re.search(r"^(?:学历|学歴|时间|時間)\s*[:：]?", school) or re.search(r"(?:19|20)\d{2}.*(?:から|到|まで)", school):
                    orphan_dates.append({
                        "school_start_ym": start,
                        "school_end_ym": str(fields.get("school_end_ym") or "").strip(),
                        "school_major_name": str(fields.get("school_major_name") or "").strip(),
                        "school_degree_type": str(fields.get("school_degree_type") or "").strip(),
                    })
                    continue
                if "专业" in school:
                    school = re.split(r"专业\s*[:：]?", school, maxsplit=1)[0].strip()
                end = str(fields.get("school_end_ym") or "").strip()
                if not end and row_index + 1 < work_header:
                    next_row = rows[row_index + 1]
                    if re.search(r"(?:至|毕业|卒業)\s*(?:19|20)\d{2}", next_row.get_text(" ", strip=True)):
                        end = str((next_row.find(attrs={"data-field": "school_end_ym"}) or {}).get_text(" ", strip=True) if next_row.find(attrs={"data-field": "school_end_ym"}) else "").strip()
                rebuilt.append({
                    "school_name": school,
                    "school_major_name": str(fields.get("school_major_name") or "").strip(),
                    "school_degree_type": str(fields.get("school_degree_type") or "").strip(),
                    "school_degree_rank": "",
                    "school_education_type": "",
                    "school_start_ym": start,
                    "school_end_ym": end,
                })
            # Pair remaining date-only and school-only rows in their source
            # order.  This preserves the real education relationship even if
            # the HTML renderer placed all bilingual school cells together.
            for date_info, school_info in zip(orphan_dates, orphan_schools):
                school_name = str(school_info.get("school_name") or "").strip()
                if not school_name:
                    continue
                if "专业" in school_name:
                    school_name = re.split(r"专业\s*[:：]?", school_name, maxsplit=1)[0].strip()
                rebuilt.append({
                    "school_name": school_name,
                    "school_major_name": str(school_info.get("school_major_name") or date_info.get("school_major_name") or "").strip(),
                    "school_degree_type": str(school_info.get("school_degree_type") or date_info.get("school_degree_type") or "").strip(),
                    "school_degree_rank": "",
                    "school_education_type": "",
                    "school_start_ym": date_info.get("school_start_ym", ""),
                    "school_end_ym": date_info.get("school_end_ym", ""),
                })
        if rebuilt:
            seen: set[tuple[str, str, str]] = set()
            resume["education_list"] = [
                item for item in rebuilt
                if (item["school_name"], item["school_start_ym"], item["school_end_ym"]) not in seen
                and not seen.add((item["school_name"], item["school_start_ym"], item["school_end_ym"]))
            ]


def filter_education_to_explicit_dom(record: dict[str, Any], html_text: str) -> None:
    """Drop summary-table education ghosts when an authoritative DOM row exists."""
    soup = BeautifulSoup(html_text, "html.parser")
    for resume in (record.get("structured_data") or {}).get("resumes") or []:
        code = str(resume.get("resume_languge") or "").casefold()
        explicit: list[dict[str, str]] = []
        for section in soup.find_all("section", attrs={"data-section-type": "education_list"}):
            section_code = str(section.get("data-language-code") or section.get("data-language") or "").casefold()
            if section_code != code:
                continue
            # UserList summary rows are occasionally mislabeled as
            # education_list and contain contact/profile fields alongside
            # placeholders such as 上海/2年.  They are not education records;
            # skip that table when a proper education section is present.
            if any(
                row.find(attrs={"data-field": "full_name"})
                and (row.find(attrs={"data-field": "phone"}) or row.find(attrs={"data-field": "email"}))
                for row in section.find_all("tr")
            ):
                continue
            for row in section.find_all("tr"):
                fields = {str(node.get("data-field") or ""): re.sub(r"\s+", " ", node.get_text(" ", strip=True)).strip() for node in row.find_all(attrs={"data-field": True})}
                school = fields.get("school_name", "")
                start = fields.get("school_start_ym", "")
                if not school or not start or not re.search(r"(?:19|20)\d{2}", start):
                    continue
                explicit.append({
                    "school_name": school,
                    "school_major_name": fields.get("school_major_name", ""),
                    "school_degree_type": fields.get("school_degree_type", ""),
                    "school_degree_rank": fields.get("school_degree_rank", ""),
                    "school_education_type": fields.get("school_education_type", ""),
                    "school_start_ym": start,
                    "school_end_ym": fields.get("school_end_ym", ""),
                })
        if explicit:
            # The semantic row is authoritative.  Keep distinct rows only
            # when they are also represented in the repaired DOM.
            seen: set[tuple[str, str, str]] = set()
            resume["education_list"] = [
                item for item in explicit
                if (item["school_name"], item["school_start_ym"], item["school_end_ym"]) not in seen
                and not seen.add((item["school_name"], item["school_start_ym"], item["school_end_ym"]))
            ]


def restore_work_to_explicit_dom(record: dict[str, Any], html_text: str) -> None:
    """Make semantic work rows authoritative over legacy parser fallbacks."""
    soup = BeautifulSoup(html_text, "html.parser")
    fields = (
        "company_name", "company_employees", "company_industry", "company_nature",
        "position_dept", "position", "position_subordinate", "position_start",
        "position_resigned", "position_responsibilities", "resigned_reason",
        "position_type", "position_salary", "position_report_to", "employment_type",
        "annual_salary_min", "annual_salary_max", "status", "position_achievements",
    )
    for resume in (record.get("structured_data") or {}).get("resumes") or []:
        code = str(resume.get("resume_languge") or "").casefold()
        explicit: list[dict[str, str]] = []
        for section in soup.find_all("section", attrs={"data-section-type": "work_experiences"}):
            section_code = str(section.get("data-language-code") or section.get("data-language") or "").casefold()
            if section_code != code:
                continue
            for row in section.find_all("tr"):
                values = {field: "" for field in fields}
                for node in row.find_all(attrs={"data-field": True}):
                    field = str(node.get("data-field") or "")
                    if field in values and not values[field]:
                        values[field] = re.sub(r"\s+", " ", node.get_text(" ", strip=True)).strip()
                if not values["company_name"]:
                    continue
                if re.search(r"实习|兼职|学生实践|社团|サークル", values["company_name"] + values["position"], re.I):
                    continue
                if values["position_start"]:
                    values["position_start"] = normalize_resume_date(values["position_start"])
                if values["position_resigned"]:
                    values["position_resigned"] = normalize_resume_date(values["position_resigned"], end=True)
                values["status"] = values["status"] or ("在职" if not values["position_resigned"] else "离职")
                explicit.append(values)
        if explicit:
            seen: set[tuple[str, str, str]] = set()
            resume["work_experiences"] = [
                item for item in explicit
                if (item["company_name"], item["position_start"], item["position_resigned"]) not in seen
                and not seen.add((item["company_name"], item["position_start"], item["position_resigned"]))
            ]


def apply_source_contacts(record: dict[str, Any], row: dict[str, Any], html_text: str) -> None:
    """Use the source-map contact only when it is actually present in HTML."""
    resumes = (record.get("structured_data") or {}).get("resumes") or []
    soup = BeautifulSoup(html_text, "html.parser")
    main = soup.find("main", attrs={"data-role": "document-content"})
    # Some Japanese templates put the contact cell outside the semantic main
    # wrapper (or bind phone and email into one wide cell).  Validate against
    # the complete repaired DOM text so the source-map contact can still
    # canonicalize the value instead of inheriting a concatenated DOM value.
    source_text = re.sub(r"\s+", "", html_text)
    map_phone = str(row.get("phone") or "").strip()
    map_email = re.sub(r"\s*@\s*", "@", str(row.get("email") or "").strip()).replace(" ", "")
    if map_phone and re.sub(r"\D", "", map_phone) in re.sub(r"\D", "", source_text):
        for resume in resumes:
            if resume.get("base_info") is not None:
                resume["base_info"]["phone"] = map_phone
    if map_email and map_email.casefold() in source_text.casefold():
        for resume in resumes:
            if resume.get("base_info") is not None:
                resume["base_info"]["email"] = map_email
    if resumes:
        structured = record.setdefault("structured_data", {})
        structured["base_info"] = copy.deepcopy(resumes[0].get("base_info") or {})


def repair_variant_names(record: dict[str, Any], html_text: str) -> None:
    """Keep language-specific names from side-by-side DOM sections.

    The shared Word parser intentionally resolves one canonical name for a
    document and historically copied it to every language variant.  XLS
    grids can contain a translated identity in the adjacent columns, so use
    the explicit ``full_name`` node within each language scope when it is a
    plausible name (for example, 岑岭 and Glen Cen).
    """
    soup = BeautifulSoup(html_text, "html.parser")
    resumes = (record.get("structured_data") or {}).get("resumes") or []
    if len(resumes) < 2:
        return
    for resume in resumes:
        code = str(resume.get("resume_languge") or resume.get("resume_language") or "").casefold()
        values: list[str] = []
        for section in soup.find_all("section"):
            section_code = str(section.get("data-language-code") or section.get("data-language") or "").casefold()
            if section_code == ("jp" if code == "ja" else code):
                values.extend(node.get_text(" ", strip=True) for node in section.find_all(attrs={"data-field": "full_name"}))
        candidate = next((normalize_name(value) for value in values if plausible_name(value)), "")
        if candidate:
            resume.setdefault("base_info", {})["full_name"] = candidate
    if resumes:
        record.setdefault("structured_data", {})["base_info"] = copy.deepcopy(resumes[0].get("base_info") or {})


def merge_bound_work_fields(record: dict[str, Any], html_text: str) -> None:
    """Apply bound work cells to languages whose template lacks record wrappers.

    The shared parser intentionally keeps its legacy fallback for those
    templates.  We still have reliable DOM bindings now, so merge the values
    back by date/company order without changing the shared parser.
    """
    soup = BeautifulSoup(html_text, "html.parser")
    resumes = (record.get("structured_data") or {}).get("resumes") or []
    fields = {
        "position_start", "position_resigned", "company_name", "company_industry",
        "company_nature", "position_dept", "position", "company_employees",
        "position_responsibilities", "resigned_reason",
    }
    for resume in resumes:
        code = str(resume.get("resume_languge") or "zh").casefold()
        sections = [
            section for section in soup.find_all("section")
            if str(section.get("data-section-type") or "") == "work_experiences"
            and str(section.get("data-language-code") or section.get("data-language") or "").casefold() in {code, "ja" if code == "jp" else code}
        ]
        groups: list[list[Tag]] = []
        for section in sections:
            current: list[Tag] = []
            for row in section.find_all("tr"):
                if row.find(attrs={"data-field": "position_start"}) and current:
                    groups.append(current)
                    current = []
                if row.find(attrs={"data-field": "position_start"}) or current:
                    current.append(row)
            if current:
                groups.append(current)
        work_rows = resume.get("work_experiences") or []
        for index, rows in enumerate(groups):
            if index >= len(work_rows):
                break
            values: dict[str, str] = {}
            for node in [node for row in rows for node in row.find_all(attrs={"data-field": True})]:
                field = str(node.get("data-field") or "")
                value = re.sub(r"\s+", " ", node.get_text(" ", strip=True)).strip()
                if field in fields and value and field not in values:
                    values[field] = value
            for field, value in values.items():
                if not str(work_rows[index].get(field) or "").strip() or field in {"position_dept", "position", "company_employees", "company_nature", "position_responsibilities", "resigned_reason"}:
                    work_rows[index][field] = value


def rebuild_bound_work_records(record: dict[str, Any], html_text: str) -> None:
    """Rebuild work rows from HTML company blocks when row boundaries drift.

    Compact XLS tables put the start date, industry and department on several
    physical rows.  Splitting on every ``position_start`` therefore creates a
    phantom work record.  A company cell is the reliable record boundary;
    collect all following rows until the next company and rebuild the row
    from its semantic DOM fields.
    """
    soup = BeautifulSoup(html_text, "html.parser")
    fields = (
        "company_name", "company_employees", "company_industry", "company_nature",
        "position_dept", "position", "position_start", "position_resigned",
        "position_responsibilities", "resigned_reason", "position_type",
        "position_salary", "position_report_to", "position_subordinate",
        "employment_type", "annual_salary_min", "annual_salary_max", "status",
        "position_achievements",
    )
    resumes = (record.get("structured_data") or {}).get("resumes") or []
    for resume in resumes:
        code = str(resume.get("resume_languge") or "zh").casefold()
        sections = [
            section for section in soup.find_all("section", attrs={"data-section-type": "work_experiences"})
            if str(section.get("data-language-code") or section.get("data-language") or "").casefold() == code
        ]
        sections.extend(
            section for section in soup.find_all("section", attrs={"data-collection": "education_list"})
            if section not in sections
            and str(section.get("data-language-code") or section.get("data-language") or "").casefold() == code
            and section.find(attrs={"data-record-type": "work_experience"})
        )
        rebuilt: list[dict[str, Any]] = []
        for section in sections:
            groups: list[list[Tag]] = []
            current: list[Tag] = []
            for row in section.find_all("tr"):
                company_nodes = row.find_all(attrs={"data-field": "company_name"})
                has_company = any(
                    str(node.get_text(" ", strip=True)).strip()
                    and not field_for(node.get_text(" ", strip=True), WORK_ALIASES)
                    for node in company_nodes
                )
                if has_company and current:
                    groups.append(current)
                    current = []
                if has_company or current:
                    current.append(row)
            if current:
                groups.append(current)
            for rows in groups:
                values: dict[str, str] = {}
                for row in rows:
                    for node in row.find_all(attrs={"data-field": True}):
                        field = str(node.get("data-field") or "")
                        value = re.sub(r"\s+", " ", node.get_text(" ", strip=True)).strip()
                        if field not in fields or not value:
                            continue
                        if field in {"position_start", "position_resigned"}:
                            normalized = normalize_resume_date(value, end=field == "position_resigned")
                            if not normalized or field in values:
                                continue
                            values[field] = normalized
                        elif field == "position_responsibilities" and re.fullmatch(
                            r"(?:19|20)\d{2}[^\n]{0,16}(?:～|~|-|至)[^\n]{0,16}(?:19|20)?\d{2,4}", value
                        ):
                            continue
                        elif field not in values:
                            values[field] = value
                if values.get("company_name"):
                    values.setdefault("employment_type", "")
                    values.setdefault("status", "在职" if not values.get("position_resigned") else "离职")
                    rebuilt.append({field: values.get(field, "") for field in fields})
        if rebuilt:
            resume["work_experiences"] = rebuilt


def merge_training_work_fields(record: dict[str, Any], html_text: str) -> None:
    """Attach labeled training rows to the corresponding work record.

    Some XLS templates store a work placement's detail rows in a separate
    ``training_list`` section.  The date/company comes from the education
    table, while department/position/content are in this section.  The DOM
    labels are authoritative; only the missing fields are merged by order.
    """
    soup = BeautifulSoup(html_text, "html.parser")
    field_names = {
        "position_dept", "position", "position_subordinate", "company_industry",
        "position_responsibilities", "resigned_reason", "company_employees", "company_nature",
    }
    resumes = (record.get("structured_data") or {}).get("resumes") or []
    for resume in resumes:
        code = str(resume.get("resume_languge") or "").casefold()
        works = resume.get("work_experiences") or []
        if not works:
            continue
        sections = [
            section for section in soup.find_all("section", attrs={"data-collection": "training_list"})
            if str(section.get("data-language-code") or section.get("data-language") or "").casefold() == code
        ]
        if not sections:
            continue
        for section in sections:
            values: dict[str, str] = {}
            for node in section.find_all(attrs={"data-field": True}):
                field = str(node.get("data-field") or "")
                value = re.sub(r"\s+", " ", node.get_text(" ", strip=True)).strip()
                if field in field_names and value and field not in values:
                    values[field] = value
            if not values:
                continue
            # Prefer a work whose company/date appears in this section; the
            # remaining label-only training block belongs to the first work
            # record (the template's own ordering convention).
            target = None
            section_text = section.get_text(" ", strip=True)
            for work in works:
                if work.get("company_name") and work["company_name"] in section_text:
                    target = work
                    break
            if target is None:
                target = next((work for work in works if not work.get("position")), works[0])
            for field, value in values.items():
                if not str(target.get(field) or "").strip():
                    target[field] = value


def merge_training_into_education(record: dict[str, Any], html_text: str) -> None:
    """Keep training/研修 rows aligned with the bilingual education list."""
    soup = BeautifulSoup(html_text, "html.parser")
    resumes = (record.get("structured_data") or {}).get("resumes") or []
    for resume in resumes:
        code = str(resume.get("resume_languge") or "zh").casefold()
        sections = [
            section for section in soup.find_all("section", attrs={"data-collection": "training_list"})
            if str(section.get("data-language-code") or section.get("data-language") or "").casefold() == code
        ]
        education = resume.get("education_list") or []
        for section in sections:
            cells = [cell.get_text(" ", strip=True) for cell in section.find_all(["td", "th"])]
            dates = [value for value in cells if re.search(r"(?:19|20)\d{2}\s*[年./-]\s*\d{1,2}", value)]
            if len(dates) < 1:
                continue
            non_date = [value for value in cells if value and value not in {"自", "至", "◆"} and not re.search(r"(?:19|20)\d{2}\s*[年./-]\s*\d{1,2}", value)]
            if not non_date:
                continue
            school = non_date[0]
            major = non_date[1] if len(non_date) > 1 else ""
            row = {
                "school_name": school,
                "school_major_name": major,
                "school_degree_type": "",
                "school_degree_rank": "",
                "school_education_type": "",
                "school_start_ym": dates[0],
                "school_end_ym": dates[1] if len(dates) > 1 else "",
            }
            signature = (row["school_name"], row["school_start_ym"], row["school_end_ym"])
            if not any((str(item.get("school_name") or ""), str(item.get("school_start_ym") or ""), str(item.get("school_end_ym") or "")) == signature for item in education):
                education.append(row)
        resume["education_list"] = education


_OUTPUT_SOURCE_INDEX: dict[str, dict[str, str]] = {}


def _output_source_key(value: str) -> str:
    try:
        return str(Path(value).resolve()).casefold()
    except (OSError, ValueError):
        return str(value or "").casefold()


def _ensure_output_source_index(output_dir: Path) -> dict[str, str]:
    cache_key = str(output_dir.resolve()).casefold()
    index = _OUTPUT_SOURCE_INDEX.get(cache_key)
    if index is not None:
        return index
    index = {}
    for path in output_dir.glob("*.json"):
        if path.name.startswith("_"):
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        source = str((payload.get("source") or {}).get("original_path") or "")
        if source:
            index[_output_source_key(source)] = path.name
    _OUTPUT_SOURCE_INDEX[cache_key] = index
    return index


def existing_output_name(output_dir: Path, source: str) -> str | None:
    return _ensure_output_source_index(output_dir).get(_output_source_key(source))


def _grid_values(row: list[Any]) -> list[str]:
    return [
        unicodedata.normalize("NFKC", str(getattr(cell, "val", "") or ""))
        .replace("\r", " ").replace("\n", " ").strip()
        for cell in row
    ]


def _label_row(grid: list[list[Any]], labels: set[str]) -> tuple[list[str], int] | None:
    normalized = {norm_label(label) for label in labels}
    for row in grid:
        values = _grid_values(row)
        for index, value in enumerate(values):
            if norm_label(value) in normalized:
                return values, index
    return None


def _next_value(values: list[str], index: int, stop_labels: set[str] | None = None) -> str:
    stops = {norm_label(label) for label in (stop_labels or set())}
    for value in values[index + 1:]:
        if value and norm_label(value) in stops:
            break
        if value:
            return value
    return ""


def _joined_value(values: list[str], index: int, stop_labels: set[str]) -> str:
    stops = {norm_label(label) for label in stop_labels}
    result: list[str] = []
    for value in values[index + 1:]:
        if value and norm_label(value) in stops:
            break
        if value:
            result.append(value)
    return "".join(result).strip()


def _period(value: str) -> tuple[str, str]:
    text = unicodedata.normalize("NFKC", str(value or ""))
    matches = re.findall(r"((?:19|20)\d{2})\s*年?\s*(\d{1,2})\s*月?", text)
    start = f"{matches[0][0]}年{int(matches[0][1]):02d}月01日" if matches else ""
    if re.search(r"至今|现在|今まで|現在|present", text, re.I):
        end = "至今"
    else:
        end = f"{matches[1][0]}年{int(matches[1][1]):02d}月01日" if len(matches) > 1 else ""
    return start, end


def _source_date(value: str) -> str:
    text = unicodedata.normalize("NFKC", str(value or ""))
    match = re.search(r"((?:19|20)\d{2})\D{0,3}(\d{1,2})?", text)
    if not match:
        return ""
    return f"{match.group(1)}年{int(match.group(2) or 1):02d}月01日"


def _horizontal_work_rows(grid: list[list[Any]], language: str) -> list[dict[str, str]]:
    company_row = _label_row(grid, {"公司名", "公司名称", "社名", "会社名"})
    if not company_row:
        return []
    companies, label_index = company_row
    columns = [index for index in range(label_index + 1, len(companies)) if companies[index]]
    if not columns:
        return []
    position_row = _label_row(grid, {"职务", "职位", "役職"})
    period_row = _label_row(grid, {"期间", "任职时间", "期間"})
    duty_row = _label_row(grid, {"工作经验", "工作内容", "工作职责", "職務経験", "職務内容"})
    reason_row = _label_row(grid, {"转职理由", "离职原因", "転職理由", "退職理由"})

    def at(row: tuple[list[str], int] | None, column: int) -> str:
        return row[0][column] if row and column < len(row[0]) else ""

    rows: list[dict[str, str]] = []
    for column in columns:
        company = companies[column]
        if not company or company in {"在职中", "离职中", "退职预定", "在職中", "離職中", "退職予定"}:
            continue
        start, end = _period(at(period_row, column))
        item = normalize_row({
            "company_name": company,
            "position": at(position_row, column),
            "position_start": start,
            "position_resigned": end,
            "position_responsibilities": at(duty_row, column),
            "resigned_reason": at(reason_row, column),
            "status": "在职" if end == "至今" else ("离职" if end else ""),
        }, WORK_FIELDS)
        if item["company_name"]:
            rows.append(item)
    return rows


def _horizontal_education_rows(grid: list[list[Any]]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for index, row in enumerate(grid):
        values = _grid_values(row)
        if "自" not in values:
            continue
        marker = values.index("自")
        start = _next_value(values, marker)
        school = next((value for value in values[marker + 1:] if re.search(r"大学|学院|学校|高校|専門|School|University|College", value, re.I)), "")
        if not school:
            continue
        school_col = values.index(school)
        major = next((value for value in values[school_col + 1:] if value and value != school), "")
        end = ""
        if index + 1 < len(grid):
            end_values = _grid_values(grid[index + 1])
            if "至" in end_values:
                end = _next_value(end_values, end_values.index("至"))
        degree = ""
        rank = ""
        if re.search(r"(?:职业|職業)(?:技术|技術)学院", school):
            degree, rank = "大专", "3"
        elif re.search(r"高校|高中", school):
            degree, rank = "高中", "2"
        rows.append(normalize_row({
            "school_name": school,
            "school_major_name": major,
            "school_degree_type": degree,
            "school_degree_rank": rank,
            "school_start_ym": _source_date(start),
            "school_end_ym": _source_date(end),
        }, EDUCATION_FIELDS))
    return list(reversed(rows))


def reextract_horizontal_bilingual_grid(record: dict[str, Any], source: str) -> bool:
    """Rebuild semantic fields from horizontal bilingual XLS rows.

    This runs only when the workbook exposes explicit company/position/period
    rows.  It is intentionally source-driven: no value is synthesized from the
    previously parsed JSON, and the result must still pass the independent
    strict validator before it can be merged or translated.
    """
    try:
        grids = xls_html.read_excel_grid(Path(source))
    except Exception:
        return False
    structured = record.setdefault("structured_data", {})
    resumes = structured.setdefault("resumes", [])
    by_language = {
        str(item.get("resume_languge") or item.get("resume_language") or "").casefold(): item
        for item in resumes if isinstance(item, dict)
    }
    changed = False
    profile_stops = {"性别", "性別", "出生年月", "生年月日", "年龄", "年齢", "身高", "身長", "户籍", "戸籍", "出身地", "民族", "邮箱", "メール"}
    for sheet_name, grid in grids:
        language = "jp" if re.search(r"日本|日語|日语", str(sheet_name)) else ("zh" if re.search(r"中国|中文|漢語|汉语", str(sheet_name)) else "")
        if not language or not _label_row(grid, {"公司名", "社名", "会社名"}):
            continue
        resume = by_language.get(language)
        if not resume:
            resume = {"resume_languge": language, "base_info": {}}
            resumes.append(resume)
            by_language[language] = resume
        base = normalize_row(resume.get("base_info") or {}, WORD_BASE_FIELDS)

        aliases = {
            "full_name": {"姓名", "氏名"}, "gender": {"性别", "性別"},
            "age": {"年龄", "年齢"}, "height_cm": {"身高", "身長"},
            "household_registration": {"户籍", "戸籍"},
            "phone": {"联络方式", "連絡方式", "电话", "電話"},
            "email": {"邮箱", "メール"}, "nationality": {"民族"},
        }
        for field, labels in aliases.items():
            found = _label_row(grid, labels)
            if found:
                value = _next_value(found[0], found[1], profile_stops)
                if field in {"age", "height_cm"} and value and not re.search(r"\d", value):
                    value = ""
                if value:
                    base[field] = value
        address_row = _label_row(grid, {"住址", "現住所", "现住所", "地址"})
        if address_row:
            base["address"] = _joined_value(address_row[0], address_row[1], profile_stops)
        # ``现住所/住址`` is not a city.  Keep city empty unless the workbook
        # has an explicit city/所在城市 label; this prevents the old horizontal
        # parser's address fragment from surviving as a city snapshot.
        city_row = _label_row(grid, {"城市", "所在城市", "city"})
        base["city"] = _next_value(city_row[0], city_row[1]) if city_row else ""
        if base.get("nationality") in {"汉", "漢"}:
            base["nationality"] = "汉族" if language == "zh" else "漢族"
        birth_row = _label_row(grid, {"出生年月", "生年月日", "出生日期"})
        if birth_row:
            segment = " ".join(birth_row[0][birth_row[1] + 1:])
            numbers = [int(value) for value in re.findall(r"\d+", segment)]
            if len(numbers) >= 3 and 1900 <= numbers[0] <= 2100:
                base["birth_date"] = f"{numbers[0]:04d}年{numbers[1]:02d}月{numbers[2]:02d}日"
                base["birth_year"] = str(numbers[0])
        evaluation = _label_row(grid, {"评价", "評価", "自我评价", "自己評価"})
        if evaluation:
            base["pr"] = _next_value(evaluation[0], evaluation[1])
        resume["base_info"] = base
        resume["work_experiences"] = _horizontal_work_rows(grid, language)
        resume["education_list"] = _horizontal_education_rows(grid)

        expected = normalize_row({}, EXPECTED_FIELDS)
        for field, labels in {
            "expected_position": {"希望职种", "希望職種"},
            "expected_salary": {"希望工资", "希望月給"},
            "expected_start_date": {"出勤日", "就職可能日"},
        }.items():
            found = _label_row(grid, labels)
            if found:
                expected[field] = _next_value(found[0], found[1], {"希望工资", "希望月給", "出勤日", "就職可能日", "其它", "その他"})
        resume["expected_list"] = [expected] if any(expected.values()) else []

        cert_row = _label_row(grid, {"资格证书", "免許・資格", "资格/证书"})
        certificates: list[dict[str, str]] = []
        if cert_row:
            cert_text = _next_value(cert_row[0], cert_row[1])
            for name in re.split(r"[、,，;；。]+", cert_text):
                name = name.strip()
                if name:
                    certificates.append(normalize_row({"certificate_name": name, "certificate_type": "技能证书"}, COLLECTION_FIELDS["certificate_list"]))
        resume["certificate_list"] = certificates

        language_rows: list[dict[str, str]] = []
        language_header = next((i for i, row in enumerate(grid) if any("語学力" in value or "语学力" in value for value in _grid_values(row))), -1)
        if language_header >= 0:
            for row in grid[language_header + 1:]:
                values = [value for value in _grid_values(row) if value]
                if not values or any(value in {"PCスキル", "电脑技能", "免許・資格", "资格证书"} for value in values):
                    if values and any(value in {"PCスキル", "电脑技能"} for value in values):
                        break
                    continue
                name = values[0]
                if name in {"日本語", "英語", "中国語", "日语", "英语", "汉语", "中文"}:
                    language_rows.append(normalize_row({"language_name": name}, COLLECTION_FIELDS["language_list"]))
        resume["language_list"] = language_rows
        for collection in ("skills_list", "training_list", "project_list", "communication_list"):
            resume.setdefault(collection, [])
        changed = True

    if not changed:
        return False
    resumes.sort(key=lambda item: 0 if item.get("resume_languge") == "zh" else 1)
    # Stable person-level values can repair a visibly incomplete language page.
    if resumes:
        zh = resumes[0]
        other_bases = [item.get("base_info") or {} for item in resumes[1:]]
        all_bases = [item.get("base_info") or {} for item in resumes]
        for field in ("marital_status", "height_cm"):
            if not zh["base_info"].get(field):
                zh["base_info"][field] = next((str(base.get(field) or "") for base in all_bases if base.get(field)), "")
        resume_date = str((record.get("dates") or {}).get("resume_updated_date") or (record.get("source") or {}).get("source_landing_time") or "")
        birth = str(zh["base_info"].get("birth_date") or "")
        years = re.findall(r"(?:19|20)\d{2}", birth + " " + resume_date)
        if len(years) >= 2:
            expected_age = int(years[-1]) - int(years[0])
            stated = re.search(r"\d+", str(zh["base_info"].get("age") or ""))
            if stated and abs(int(stated.group()) - expected_age) > 1:
                zh["base_info"]["age"] = f"{expected_age}岁"
    zh = resumes[0]
    structured["base_info"] = copy.deepcopy(zh.get("base_info") or {})
    structured["expected_info"] = copy.deepcopy((zh.get("expected_list") or [normalize_row({}, EXPECTED_FIELDS)])[0])
    structured["current_info"] = latest_work(zh.get("work_experiences") or [])
    structured["education_info"] = highest_education(zh.get("education_list") or [])
    record.setdefault("source", {})["strict_field_reextraction"] = {
        "status": "reextracted_from_physical_xls_grid",
        "rule_version": "xls-horizontal-bilingual-field-reextract-v1",
    }
    return True


def contact_output_filename(record: dict[str, Any], source: str, output_dir: Path, existing_filename: str | None = None) -> str:
    base = ((record.get("structured_data") or {}).get("base_info") or {})
    name = safe_output_name(str(base.get("full_name") or Path(source).stem))
    phone = normalize_phone_value(str(base.get("phone") or ""))
    email = re.sub(r"\s*@\s*", "@", str(base.get("email") or "")).replace(" ", "")
    contact = phone or email
    # A no-contact record should normally be rejected by the validator.  Keep
    # a deterministic fallback for legacy/review records rather than creating
    # an ambiguous ``姓名_.json`` file.
    token = safe_output_name(contact) if contact else source_hash(source)
    desired = f"{name}_{token}.json"
    target = output_dir / desired
    if target.is_file() and desired != existing_filename:
        try:
            other = json.loads(target.read_text(encoding="utf-8"))
            other_source = str((other.get("source") or {}).get("original_path") or "")
        except (OSError, ValueError, TypeError):
            other_source = ""
        if other_source and Path(other_source).resolve() != Path(source).resolve():
            desired = f"{name}_{token}_{source_hash(source)}.json"
    return desired


def process_row(row: dict[str, Any], output_dir: Path, passed_dir: Path, review_dir: Path) -> dict[str, Any]:
    source = str(row.get("source_path") or "")
    result = xls_html.convert_single_excel_detailed(source, passed_dir, review_dir, str(row.get("filename") or Path(source).name), str(row.get("download_date") or ""))
    if result.get("status") == "not_resume":
        # Remove a stale JSON from an earlier permissive run.  A no-contact
        # workbook is deliberately excluded from the usable resume set.
        old_name = existing_output_name(output_dir, source)
        if old_name:
            (output_dir / old_name).unlink(missing_ok=True)
            _ensure_output_source_index(output_dir).pop(_output_source_key(source), None)
        return {
            "source_path": source,
            "html_path": "",
            "output_path": "",
            "status": "not_resume",
            "error_reason": result.get("error_reason", "缺少候选人手机或邮箱"),
            "quality": result.get("validation", {}),
        }
    html_path = Path(str(result.get("html_path") or ""))
    if not html_path.is_file():
        return {"source_path": source, "status": "failed", "error": result.get("error_reason", "html_missing")}
    repaired = repair_html(html_path.read_text(encoding="utf-8", errors="replace"))
    repaired = repair_bound_identity_dom(repaired)
    repaired = repair_date_only_work_dom(repaired, source)
    repaired = repair_date_only_education_dom(repaired, source)
    html_path.write_text(repaired, encoding="utf-8")
    record, quality = parse_html_record(Path(source), html_path, str(row.get("download_date") or ""), 1)
    repair_bound_identity(record, repaired)
    repaired = repair_identity_from_source(record, repaired, row)
    repair_variant_names(record, repaired)
    merge_bound_self_evaluation(record, repaired)
    quality["full_name"] = str(((record.get("structured_data") or {}).get("base_info") or {}).get("full_name") or "")
    clear_verified_name_warning(record, repaired, quality)
    prune_language_without_sections(record, repaired)
    clear_collections_without_dom(record, repaired)
    prune_profile_without_core_dom(record, repaired)
    merge_bound_work_fields(record, repaired)
    rebuild_bound_work_records(record, repaired)
    repair_date_only_work_companies(record, source)
    merge_mixed_work_records(record, repaired)
    merge_training_work_fields(record, repaired)
    remove_mixed_work_from_education(record, repaired)
    rebuild_bound_education(record, repaired)
    rebuild_japanese_education(record, repaired)
    repair_date_only_education(record, source)
    merge_training_into_education(record, repaired)
    filter_education_to_explicit_dom(record, repaired)
    restore_work_to_explicit_dom(record, repaired)
    merge_bound_language_records(record, repaired)
    rebuild_certificate_rows(record, repaired)
    # Some legacy fallbacks rebuild work rows after the DOM merge and can
    # reintroduce a date/duration value as company_name.  Apply the source
    # pairing once more immediately before persistence.
    repair_date_only_work_companies(record, source)
    repair_date_only_education(record, source)
    # Late merge helpers can clear a fallback collection after the first DOM
    # merge; restore any explicit work rows one final time before sanitizing.
    restore_work_to_explicit_dom(record, repaired)
    sanitize_record(record)
    apply_source_contacts(record, row, repaired)
    normalize_record_contacts(record)
    normalize_record_dates(record)
    # A few merge helpers append duplicate rows after the first sanitization
    # pass; run the same conservative cleanup once more after date
    # canonicalization so the persisted JSON is what the validator sees.
    sanitize_record(record)
    # The legacy DOM parser may still drop complete horizontal bilingual rows.
    # Re-read the physical workbook and make the explicit grid bindings the
    # final structured source before independent strict validation.
    if reextract_horizontal_bilingual_grid(record, source):
        normalize_record_contacts(record)
        normalize_record_dates(record)
        sanitize_record(record)
        structured = record.setdefault("structured_data", {})
        final_resumes = structured.get("resumes") or []
        if final_resumes:
            primary = final_resumes[0]
            # Reconcile person-level fields only after the source re-extraction
            # and final sanitization.  The Chinese sheet may leave a checkbox
            # value blank while the parallel Japanese sheet contains it.
            for field in ("marital_status", "height_cm"):
                if not (primary.get("base_info") or {}).get(field):
                    for candidate in final_resumes[1:]:
                        value = str((candidate.get("base_info") or {}).get(field) or "")
                        if value:
                            primary.setdefault("base_info", {})[field] = value
                            break
            structured["base_info"] = copy.deepcopy(primary.get("base_info") or {})
            structured["expected_info"] = copy.deepcopy((primary.get("expected_list") or [normalize_row({}, EXPECTED_FIELDS)])[0])
            structured["current_info"] = latest_work(primary.get("work_experiences") or [])
            structured["education_info"] = highest_education(primary.get("education_list") or [])
            quality["work_count"] = len(primary.get("work_experiences") or [])
            quality["education_count"] = len(primary.get("education_list") or [])
            quality["reextracted_work_count"] = quality["work_count"]
            quality["reextracted_education_count"] = quality["education_count"]
    source_meta = record.setdefault("source", {})
    source_meta["html_path"] = str(html_path.resolve())
    source_meta["html_filename"] = html_path.name
    source_meta["source_landing_time"] = str(row.get("download_date") or "")
    record["raw_text"] = html_raw_text(repaired)
    # Identity/date/company repairs can change bindings after the generator's
    # first write. Persist the final repaired DOM before emitting JSON so the
    # HTML and structured extraction remain a single source of truth.
    html_path.write_text(repaired, encoding="utf-8")
    validation_row = dict(row)
    if result.get("language_folder"):
        validation_row["language_folder"] = result.get("language_folder")
    quality["issues"] = list(dict.fromkeys((quality.get("issues") or []) + valid_rule_issues(record, output_dir / (existing_output_name(output_dir, source) or "pending.json"), validation_row)))
    filename = existing_output_name(output_dir, source)
    desired_filename = contact_output_filename(record, source, output_dir, filename)
    if filename and filename != desired_filename:
        old_path = output_dir / filename
        if old_path.is_file() and old_path.resolve() != (output_dir / desired_filename).resolve():
            old_path.unlink()
        filename = desired_filename
    elif not filename:
        filename = desired_filename
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / filename
    output_path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _ensure_output_source_index(output_dir)[_output_source_key(source)] = filename
    # Revalidate against the freshly written JSON.  Validating the previous
    # file here would report stale errors after a successful repair pass.
    quality["issues"] = valid_rule_issues(record, output_path, validation_row)
    final_status = "success" if not quality.get("issues") else "needs_review"
    # The legacy XLS generator may initially place a file in ``review`` when
    # its pre-repair DOM extraction is incomplete.  After this module repairs
    # and validates the semantic DOM, a clean result belongs in ``passed``.
    # Keep the folder status aligned with the final JSON status so users do
    # not see correctly parsed resumes stranded in the review directory.
    if final_status == "success":
        try:
            review_root = review_dir.resolve()
            current_html = html_path.resolve()
            if current_html.is_relative_to(review_root):
                relative = current_html.relative_to(review_root)
                promoted = (passed_dir.resolve() / relative)
                promoted.parent.mkdir(parents=True, exist_ok=True)
                promoted.write_text(repaired, encoding="utf-8")
                if current_html != promoted:
                    current_html.unlink(missing_ok=True)
                html_path = promoted
                source_meta["html_path"] = str(promoted)
                source_meta["html_filename"] = promoted.name
                output_path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        except (OSError, ValueError):
            # Folder promotion is a packaging convenience; a validated JSON
            # must still be returned if a concurrent filesystem operation
            # prevents the move.
            pass
    return {"source_path": source, "html_path": str(html_path), "output_path": str(output_path), "status": final_status, "quality": quality}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--map", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--passed-dir", type=Path, default=ROOT / _rc.dirname("complete-transfered-htmls") / "xls" / "passed")
    parser.add_argument("--review-dir", type=Path, default=ROOT / _rc.dirname("complete-transfered-htmls") / "xls" / "review")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--contains", nargs="*", default=[])
    parser.add_argument("--shard", type=int, default=-1, help="zero-based shard index for parallel full runs")
    parser.add_argument("--shards", type=int, default=1, help="number of parallel shards")
    args = parser.parse_args()
    rows = json.loads(args.map.read_text(encoding="utf-8"))
    if args.contains:
        rows = [row for row in rows if any(token in str(row.get("source_path") or row.get("filename") or "") for token in args.contains)]
    if args.limit > 0:
        rows = rows[:args.limit]
    if args.shards > 1:
        if not 0 <= args.shard < args.shards:
            parser.error("--shard must be between 0 and --shards-1")
        rows = [row for index, row in enumerate(rows) if index % args.shards == args.shard]
    results = [process_row(row, args.output_dir, args.passed_dir, args.review_dir) for row in rows]
    report = {"total": len(results), "success": sum(item.get("status") == "success" for item in results), "needs_review": sum(item.get("status") == "needs_review" for item in results), "not_resume": sum(item.get("status") == "not_resume" for item in results), "failed": sum(item.get("status") == "failed" for item in results), "items": results}
    report_name = "_xls_html_to_json_v3_report.json" if args.shards == 1 else f"_xls_html_to_json_v3_report_shard{args.shard}.json"
    report_path = args.output_dir / report_name
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("total", "success", "needs_review", "not_resume", "failed")}, ensure_ascii=False))
    return 0 if not report["failed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
