from __future__ import annotations
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1] / "common"))
import rc_config as _rc  # noqa: E402  项目统一配置（python/common/rc_config.py）
# EN: noqa: E402  project-wide configuration (python/common/rc_config.py)
# JA: noqa: E402  プロジェクト共通設定（python/common/rc_config.py）

import argparse
import json
import os
import re
import tempfile
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Iterable

from bs4 import BeautifulSoup, NavigableString, Tag

from process_word_to_html import (
    EMAIL_STANDARD_RE,
    SCHEMA_VERSION,
    extract_contacts,
    validate_semantic_html,
)


PROJECT_ROOT = _rc.project_root()
DEFAULT_PASSED = PROJECT_ROOT / _rc.dirname("complete-transfered-htmls") / "docs" / "passed"
DEFAULT_MAP = PROJECT_ROOT / _rc.dirname("complete-transfered-htmls") / "docs" / "word_conversion_map.json"
DEFAULT_REPORT = PROJECT_ROOT / _rc.dirname("complete-transfered-htmls") / "docs" / "dom_repair_report.json"
REPAIR_VERSION = "resume-dom-repair-1.2.4"

COLLECTIONS = {
    "expected_list", "work_experiences", "education_list", "certificate_list",
    "language_list", "skills_list", "training_list", "project_list",
    "communication_list",
}

SECTION_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("work_experiences", re.compile(r"工作经历|工作经验|職歴|職務経歴|職歴・職務経歴|work experience|employment history", re.I)),
    ("education_list", re.compile(r"教育经历|教育背景|学歴|学歴・留学|education|academic background", re.I)),
    ("certificate_list", re.compile(r"资格证书|所获证书|資格|免許|certificates?|qualifications?", re.I)),
    ("language_list", re.compile(r"语言能力|外语能力|語学力|language skills?|languages?", re.I)),
    ("expected_list", re.compile(r"求职意向|职业期望|希望条件|希望給与|希望職種|career objective|job objective", re.I)),
    ("self_evaluation", re.compile(r"自我评价|自我介绍|自己PR|自己評価|self evaluation|professional summary", re.I)),
    ("project_list", re.compile(r"项目经历|プロジェクト|project experience", re.I)),
    ("training_list", re.compile(r"培训经历|研修|training experience", re.I)),
    ("skills_list", re.compile(r"专业技能|技能特长|スキル|skills", re.I)),
    ("communication_list", re.compile(r"顾问评价|推荐意见|コミュニケーション|consultant comments", re.I)),
)

FIELD_ALIASES: dict[str, set[str]] = {
    "full_name": {"姓名", "名字", "氏名", "中文姓名", "name", "full name"},
    "gender": {"性别", "性別", "sex", "gender"},
    "age": {"年龄", "年齢", "age"},
    "birth_date": {"出生日期", "出生年月日", "生年月日", "生日", "date of birth", "birthday"},
    "birth_year": {"出生年份", "出生年", "birth year"},
    "marital_status": {"婚姻", "婚姻状况", "婚姻状況", "婚姻状態", "配偶者", "marital status"},
    "household_registration": {"户籍", "戶籍", "戸籍", "户口", "籍贯", "本籍", "出身地", "hukou"},
    "address": {"地址", "现居住地", "現住所", "现住所", "居住地", "住址", "住所", "address"},
    "postal_code": {"邮编", "郵便番号", "postal code", "zip code"},
    "phone": {"电话", "手机", "联系电话", "電話", "携帯", "携帯電話", "携帯電話番号", "連絡先", "phone", "mobile", "tel"},
    "email": {"邮箱", "电子邮箱", "メール", "メールアドレス", "email", "e-mail", "e-mai"},
    "city": {"城市", "所在城市", "现居城市", "居住城市", "city", "current city"},
    "nationality": {"国籍", "nationality"},
    "expected_city": {"期望城市", "期望地点", "希望勤務地", "desired city", "preferred location"},
    "expected_position": {"期望职位", "求职职位", "希望職種", "desired position", "preferred function"},
    "expected_salary": {"期望薪资", "希望薪资", "希望給与", "希望給料", "expected salary", "desired salary"},
    "current_salary": {"目前薪资", "当前薪资", "現在の給与", "現在給与", "current salary"},
    "company_name": {"公司", "公司名称", "单位名称", "企業名", "勤務先", "会社名", "company", "employer"},
    "company_industry": {"所属行业", "公司行业", "業界", "industry"},
    "position": {"职位", "职位名称", "职务", "職位名", "役職", "position", "job title"},
    "position_salary": {"月薪", "职位薪资", "monthly salary"},
    "position_dept": {"部门", "所属部门", "所属部門", "所属", "department"},
    "position_report_to": {"汇报对象", "上司", "reports to"},
    "position_subordinate": {"下属人数", "部下人数", "subordinates"},
    "position_start": {"入职时间", "开始时间", "勤務開始", "start date"},
    "position_resigned": {"离职时间", "结束时间", "退職日", "end date"},
    "resigned_reason": {"离职原因", "退職理由", "reason for leaving"},
    "position_responsibilities": {"工作职责", "职责描述", "工作内容", "仕事内容", "業務内容", "responsibilities"},
    "position_achievements": {"工作业绩", "主要业绩", "成果", "achievements"},
    "school_name": {"学校", "学校名称", "毕业院校", "卒業学校", "大学", "school", "university"},
    "school_major_name": {"专业", "专业名称", "学科", "専攻", "major"},
    "school_degree_type": {"学历", "学位", "学历类型", "degree", "education level"},
    "school_start_ym": {"入学时间", "教育开始时间", "start date"},
    "school_end_ym": {"毕业时间", "结业时间", "教育结束时间", "graduation date", "end date"},
    "certificate_name": {"证书名称", "资格证书", "資格", "certificate"},
    "certificate_time": {"取得时间", "证书时间", "取得年月", "certificate date"},
    "language_name": {"语言", "语言名称", "語学", "言語", "language"},
    "language_level": {"语言水平", "熟练程度", "語学レベル", "language level", "proficiency"},
    "language_certificate": {"语言证书", "語学資格", "language certificate"},
}

DISPLAY_LABELS = {
    "full_name": "姓名", "gender": "性别", "age": "年龄", "birth_date": "生日",
    "birth_year": "出生年份", "marital_status": "婚姻", "household_registration": "户籍",
    "address": "地址", "phone": "手机", "email": "邮箱", "city": "城市",
    "nationality": "国籍", "current_salary": "当前薪资",
}

RECORD_PRIMARY_FIELDS = {
    "work_experience": {"company_name", "position", "position_start", "position_responsibilities"},
    "education": {"school_name", "school_start_ym"},
    "certificate": {"certificate_name"},
}

COLLECTION_RECORD_CONFIG = {
    "work_experiences": ("work_experience", {
        "company_name", "company_employees", "company_industry", "position", "position_type",
        "position_salary", "position_dept", "position_report_to", "position_subordinate",
        "employment_type", "annual_salary_min", "annual_salary_max", "status",
        "position_start", "position_resigned", "resigned_reason",
        "position_responsibilities", "position_achievements",
    }, {"company_name", "position_start"}),
    "education_list": ("education", {
        "school_name", "school_major_name", "school_degree_type", "school_degree_rank",
        "school_education_type", "school_start_ym", "school_end_ym",
    }, {"school_name", "school_start_ym"}),
    "certificate_list": ("certificate", {"certificate_name", "certificate_type", "certificate_time"}, {"certificate_name"}),
    "language_list": ("language", {"language_name", "language_level", "language_certificate", "language_certificate_time"}, {"language_name"}),
    "skills_list": ("skill", {"skill_name", "skill_level"}, {"skill_name"}),
    "expected_list": ("expected", {
        "expected_city", "expected_position", "expected_salary", "expected_annual_salary_min",
        "expected_annual_salary_max", "expected_industry", "expected_employment_type", "expected_start_date",
    }, {"expected_position", "expected_city", "expected_salary"}),
}


def normalized_label(value: str) -> str:
    return re.sub(r"[\s:：·•|｜_\-]+", "", value).casefold()


ALIAS_LOOKUP = {
    normalized_label(alias): field
    for field, aliases in FIELD_ALIASES.items()
    for alias in aliases
}
ALIASES_SORTED = sorted(
    ((alias, field) for field, aliases in FIELD_ALIASES.items() for alias in aliases),
    key=lambda item: len(normalized_label(item[0])),
    reverse=True,
)

# Reuse one tag factory. Creating a new BeautifulSoup document for every
# generated <span>/<i>/<section> dominates runtime on large batches.
_TAG_FACTORY = BeautifulSoup("", "lxml")


def make_tag(name: str) -> Tag:
    return _TAG_FACTORY.new_tag(name)


def clean_text(node: Tag) -> str:
    return re.sub(r"\s+", " ", node.get_text(" ", strip=True)).strip()


def field_for_label(value: str) -> str:
    return ALIAS_LOOKUP.get(normalized_label(value), "")


def alias_regex(alias: str) -> str:
    if re.search(r"[\u3040-\u30ff\u3400-\u9fff]", alias):
        return r"\s*".join(re.escape(char) for char in alias if not char.isspace())
    return re.escape(alias).replace(r"\ ", r"\s+")


def label_matches(text: str, allow_prefix_without_colon: bool = False) -> list[tuple[int, int, str, str]]:
    candidates: list[tuple[int, int, str, str, int]] = []
    for alias, field in ALIASES_SORTED:
        pattern = alias_regex(alias)
        colon_re = re.compile(pattern + r"\s*[:：]", re.I)
        for match in colon_re.finditer(text):
            candidates.append((match.start(), match.end(), field, alias, len(normalized_label(alias))))
        # 无冒号前缀很容易把正文中的“大学… / 公司…”误认成字段。
        # 这里只为姓名保留兼容，用于“氏 名 陳逸納”这类日文表格。
        # EN: Without a colon prefix it is easy to mistake "大学… / 公司…" (university… / company…) in the body for fields.
        #     Compatibility is kept here only for names, for Japanese tables like "氏 名 <name>".
        # JA: コロンの接頭辞がないと、本文中の「大学…／公司…」をフィールドと誤認しやすい。
        #     ここでは氏名に限って互換を残し、「氏 名 <氏名>」のような日本語の表に使う。
        if allow_prefix_without_colon and field in {"full_name", "address"}:
            prefix = re.compile(r"^\s*" + pattern + r"(?:\s+|(?=[\u3040-\u30ff\u3400-\u9fffA-Za-z0-9]))", re.I)
            match = prefix.match(text)
            if match and text[match.end():].strip():
                candidates.append((match.start(), match.end(), field, alias, len(normalized_label(alias))))
    selected: list[tuple[int, int, str, str]] = []
    occupied = -1
    for start, end, field, alias, _length in sorted(candidates, key=lambda row: (row[0], -row[4], row[1])):
        if start < occupied:
            continue
        selected.append((start, end, field, alias))
        occupied = end
    return selected


def infer_section_type(text: str) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    for section_type, pattern in SECTION_PATTERNS:
        if pattern.search(compact):
            return section_type
    label_fields = {field_for_label(part.rstrip("：:")) for part in re.split(r"[|｜]", compact)}
    base_fields = {"full_name", "gender", "birth_date", "marital_status", "phone", "email", "address", "nationality", "household_registration"}
    if len(label_fields & base_fields) >= 2:
        return "base_info"
    return ""


def table_section_type(table: Tag) -> str:
    rows = table.find_all("tr")[:3]
    header = " ".join(clean_text(row) for row in rows)
    return infer_section_type(header[:600])


def has_bad_binding(root: Tag) -> bool:
    for node in root.find_all(attrs={"data-field": True}):
        # 已经记录化的数据是权威值，不再用标签启发式重新判断。
        # EN: Data already turned into records is authoritative and is no longer re-judged by label heuristics.
        # JA: すでにレコード化したデータを正とし、ラベルによるヒューリスティックで判定し直さない。
        if node.find_parent(attrs={"data-record-type": True}):
            continue
        value = clean_text(node)
        actual_field = field_for_label(value.rstrip("：:"))
        if actual_field and actual_field != str(node.get("data-field") or ""):
            return True
    return False


def has_fragmented_label(root: Tag) -> bool:
    for table in root.find_all("table"):
        rows = table.find_all("tr")
        for row_index, row in enumerate(rows[:-1]):
            cells = row.find_all(["th", "td"], recursive=False)
            next_cells = rows[row_index + 1].find_all(["th", "td"], recursive=False)
            for column, cell in enumerate(cells):
                first = clean_text(cell)
                if not first or len(first) > 16 or column >= len(next_cells):
                    continue
                if field_for_label(first.rstrip("：:")):
                    continue
                second = clean_text(next_cells[column])
                if (
                    second
                    and len(second) <= 8
                    and not field_for_label(second.rstrip("：:"))
                    and field_for_label(first + second)
                ):
                    return True
                if column + 1 < len(cells):
                    adjacent = clean_text(cells[column + 1])
                    suffix = adjacent.split()[-1] if adjacent else ""
                    if suffix and len(suffix) <= 3 and field_for_label(first + suffix):
                        return True
    return False


def has_untyped_business_tables(record: Tag) -> bool:
    for section in record.find_all("section", recursive=False):
        if str(section.get("data-section-type") or "") != "document-body":
            continue
        if any(table_section_type(table) for table in section.find_all("table")):
            return True
    return False


def has_unannotated_multi_field_blocks(record: Tag) -> bool:
    for node in record.find_all(["p", "td", "th"]):
        if node.find_parent(attrs={"data-record-type": True}):
            continue
        if node.name in {"td", "th"} and node.find(["p", "div", "table", "ul", "ol"]):
            continue
        text = clean_text(node)
        matches = label_matches(text)
        if len(matches) >= 2:
            annotated = len(node.find_all(attrs={"data-field": True}))
            if annotated < len(matches):
                return True
        if re.search(r"[|｜]", text):
            identifiable = sum(bool(classify_profile_segment(part)) for part in re.split(r"[|｜]", text))
            if identifiable >= 2 and len(node.find_all(attrs={"data-field": True})) < identifiable:
                return True
    return False


def audit_record(record: Tag) -> list[str]:
    issues: list[str] = []
    if has_bad_binding(record):
        issues.append("bad_field_binding")
    if has_fragmented_label(record):
        issues.append("fragmented_label")
    if has_untyped_business_tables(record):
        issues.append("untyped_business_table")
    if has_unannotated_multi_field_blocks(record):
        issues.append("unannotated_multi_field_block")
    for node in record.find_all(attrs={"data-field": True}):
        field = str(node.get("data-field") or "")
        if not field.endswith(("_ym", "_date", "_time")):
            continue
        value = clean_text(node)
        months = re.findall(r"(?:19|20)\d{2}[-/.年](\d{1,2})", value)
        if any(not 1 <= int(month) <= 12 for month in months):
            issues.append("invalid_date_field")
            break
    for item in record.find_all(attrs={"data-record-type": True}):
        fields = {str(node.get("data-field") or "") for node in item.find_all(attrs={"data-field": True})}
        kind = str(item.get("data-record-type") or "")
        invalid_month = any(
            re.search(r"年(?:1[3-9]|[2-9]\d)月", clean_text(node))
            for node in item.find_all(attrs={"data-field": True})
            if re.search(r"(?:_ym|_start|_resigned|_time)$", str(node.get("data-field") or ""))
        )
        if (kind in RECORD_PRIMARY_FIELDS and not fields.intersection(RECORD_PRIMARY_FIELDS[kind])) or invalid_month:
            issues.append("invalid_collection_record")
            break
    for section in record.find_all("section", recursive=False):
        section_type = str(section.get("data-section-type") or "")
        if section_type not in {"work_experiences", "education_list", "certificate_list"}:
            continue
        if section.find(attrs={"data-record-type": True}):
            continue
        header = clean_text(section.find("table") or section)[:300]
        if re.search(r"職歴|職務経歴|学歴|留学先|資格|免許", header):
            issues.append("ungrouped_collection_records")
            break
    for collection in record.find_all(attrs={"data-collection": True}):
        indices_by_type: dict[str, list[int]] = {}
        for item in collection.find_all(attrs={"data-record-type": True}):
            if item.find_parent(attrs={"data-collection": True}) is not collection:
                continue
            kind = str(item.get("data-record-type") or "")
            try:
                index = int(item.get("data-record-index") or 0)
            except (TypeError, ValueError):
                index = 0
            indices_by_type.setdefault(kind, []).append(index)
        if any(indices != list(range(1, len(indices) + 1)) for indices in indices_by_type.values()):
            issues.append("bad_record_indices")
            break
    return issues


def clear_machine_annotations(record: Tag) -> None:
    for node in record.find_all(True):
        if node.get("data-record-type") or node.find_parent(attrs={"data-record-type": True}):
            continue
        for attribute in ("data-field", "data-label-for", "data-field-group", "label"):
            node.attrs.pop(attribute, None)
        if node.name in {"span", "i"} and not node.attrs:
            node.unwrap()


def merge_fragmented_labels(table: Tag) -> int:
    changes = 0
    rows = table.find_all("tr")
    for row_index, row in enumerate(rows):
        cells = row.find_all(["th", "td"], recursive=False)
        next_cells = rows[row_index + 1].find_all(["th", "td"], recursive=False) if row_index + 1 < len(rows) else []
        for column, cell in enumerate(cells):
            first = clean_text(cell)
            if not first or len(first) > 16:
                continue
            if field_for_label(first.rstrip("：:")):
                continue
            if column < len(next_cells):
                second = clean_text(next_cells[column])
                combined = first + second
                if (
                    second
                    and len(second) <= 8
                    and not field_for_label(second.rstrip("：:"))
                    and field_for_label(combined)
                ):
                    cell.clear()
                    cell.string = combined
                    next_cells[column].clear()
                    changes += 1
                    first = combined
            if column + 1 < len(cells):
                value_cell = cells[column + 1]
                value = clean_text(value_cell)
                parts = value.split()
                suffix = parts[-1] if parts else ""
                if suffix and len(suffix) <= 3 and field_for_label(first + suffix):
                    cell.clear()
                    cell.string = first + suffix
                    value_cell.clear()
                    value_cell.string = " ".join(parts[:-1])
                    changes += 1
    return changes


def remove_empty_template_rows(table: Tag) -> int:
    removed = 0
    patterns = (
        re.compile(r"^年\s*月\s*企業名[:：]?\s*所属部門[:：]?\s*業務内容[:：]?$"),
        re.compile(r"^年\s*月\s*退職理由[:：]?$"),
        re.compile(r"^年\s*月\s*$"),
    )
    for row in list(table.find_all("tr")):
        value = clean_text(row)
        if any(pattern.match(value) for pattern in patterns):
            row.decompose()
            removed += 1
    return removed


def annotate_inline(node: Tag) -> int:
    raw = clean_text(node)
    # 完整标签单元格由表格相邻关系负责，不能先把“婚姻 状況”拆成
    # label=婚姻、value=状況。
    # EN: Complete label cells are handled by table adjacency; "婚姻 状況" (marital status) must not first be split into
    #     label=婚姻, value=状況.
    # JA: 完全なラベルのセルは表の隣接関係で処理する。「婚姻 状況」を先に
    #     label=婚姻、value=状況 と分割してはならない。
    if field_for_label(raw.rstrip("：:")):
        return 0
    matches = label_matches(raw, allow_prefix_without_colon=True)
    if not matches:
        return 0
    node.clear()
    if len(matches) == 1:
        node["label"] = DISPLAY_LABELS.get(matches[0][2], matches[0][3])
    cursor = 0
    fields = 0
    for index, (start, end, field, alias) in enumerate(matches):
        if start > cursor:
            node.append(NavigableString(raw[cursor:start]))
        label = make_tag("span")
        label["data-label-for"] = field
        label.string = raw[start:end].strip() or alias
        node.append(label)
        value_end = matches[index + 1][0] if index + 1 < len(matches) else len(raw)
        value = raw[end:value_end].strip(" ：:|｜")
        if value:
            field_node = make_tag("i")
            field_node["data-field"] = field
            field_node["label"] = DISPLAY_LABELS.get(field, alias)
            field_node.string = value
            node.append(field_node)
            fields += 1
        cursor = value_end
    return fields


def classify_profile_segment(segment: str) -> tuple[str, str] | None:
    value = segment.strip()
    if re.fullmatch(r"男|女|男性|女性|male|female", value, re.I):
        return "gender", value
    if re.fullmatch(r"未婚|已婚|离异|離婚|单身|既婚|独身|single|married|divorced", value, re.I):
        return "marital_status", value
    if re.fullmatch(r"\d{1,3}\s*岁", value):
        return "age", value
    birth = re.search(
        r"(?<!\d)((?:19|20)\d{2})\s*(年|[./-])\s*(\d{1,2})"
        r"(?:\s*(?:月|[./-])\s*(\d{1,2})\s*日?)?(?!\d)",
        value,
    )
    if birth and 1 <= int(birth.group(3)) <= 12:
        day = birth.group(4)
        if day is None or 1 <= int(day) <= 31:
            return "birth_date", birth.group(0)
    city = re.match(r"(?:现居住|現居住|现居|居住地)\s*[:：]?\s*(.+)", value)
    if city and city.group(1).strip():
        return "city", city.group(1).strip()
    explicit = label_matches(value)
    if len(explicit) == 1 and explicit[0][0] == 0:
        _start, end, field, _alias = explicit[0]
        result = value[end:].strip(" ：:")
        if result:
            return field, result
    return None


def annotate_composite(node: Tag) -> int:
    raw = clean_text(node)
    if not re.search(r"[|｜]", raw):
        return 0
    parts = re.split(r"([|｜])", raw)
    classified = {index: classify_profile_segment(parts[index]) for index in range(0, len(parts), 2)}
    classified = {index: value for index, value in classified.items() if value}
    if len(classified) < 2:
        return 0
    node.clear()
    node["label"] = "个人信息"
    node["data-field-group"] = "base_info"
    for index, part in enumerate(parts):
        result = classified.get(index)
        if not result:
            node.append(NavigableString(part))
            continue
        field, value = result
        field_node = make_tag("i")
        field_node["data-field"] = field
        field_node["label"] = DISPLAY_LABELS.get(field, field)
        field_node.string = value
        node.append(field_node)
    return len(classified)


def annotate_table(table: Tag) -> int:
    fields = 0
    rows = table.find_all("tr")
    for row_index, row in enumerate(rows):
        cells = row.find_all(["th", "td"], recursive=False)
        for cell in cells:
            if (
                not cell.find(["p", "div", "table", "ul", "ol"])
                and not field_for_label(clean_text(cell).rstrip("：:"))
            ):
                fields += annotate_composite(cell) or annotate_inline(cell)

        for column, cell in enumerate(cells):
            label_text = clean_text(cell).rstrip("：:")
            field = field_for_label(label_text)
            if not field:
                continue
            cell["data-label-for"] = field
            value_cell: Tag | None = None
            if column + 1 < len(cells):
                candidate = cells[column + 1]
                candidate_text = clean_text(candidate)
                if candidate_text and not field_for_label(candidate_text.rstrip("：:")):
                    value_cell = candidate
            if value_cell is None and row_index + 1 < len(rows):
                below_cells = rows[row_index + 1].find_all(["th", "td"], recursive=False)
                if column < len(below_cells):
                    candidate = below_cells[column]
                    candidate_text = clean_text(candidate)
                    if candidate_text and not field_for_label(candidate_text.rstrip("：:")):
                        value_cell = candidate
            if value_cell is not None and not value_cell.get("data-field"):
                value_cell["data-field"] = field
                value_cell["label"] = DISPLAY_LABELS.get(field, label_text)
                fields += 1
    for paragraph in table.find_all("p"):
        fields += annotate_composite(paragraph) or annotate_inline(paragraph)
    return fields


def annotate_table_nonmutating(table: Tag) -> int:
    """只给明确的相邻标签/值单元格加属性，不改节点或文字。

    EN: Add attributes only to clearly adjacent label/value cells, without changing nodes or text.

    JA: 明確に隣接するラベル・値のセルだけに属性を付け、ノードやテキストは変えない。
    """
    fields = 0
    rows = table.find_all("tr")
    for row_index, row in enumerate(rows):
        cells = row.find_all(["th", "td"], recursive=False)
        for column, cell in enumerate(cells):
            label_text = clean_text(cell).rstrip("：:")
            field = field_for_label(label_text)
            if not field:
                continue
            cell["data-label-for"] = field
            value_cell: Tag | None = None
            if column + 1 < len(cells):
                candidate = cells[column + 1]
                candidate_text = clean_text(candidate)
                if candidate_text and not field_for_label(candidate_text.rstrip("：:")):
                    value_cell = candidate
            if value_cell is None and row_index + 1 < len(rows):
                below_cells = rows[row_index + 1].find_all(["th", "td"], recursive=False)
                if column < len(below_cells):
                    candidate = below_cells[column]
                    candidate_text = clean_text(candidate)
                    if candidate_text and not field_for_label(candidate_text.rstrip("：:")):
                        value_cell = candidate
            if value_cell is not None and not value_cell.get("data-field"):
                value_cell["data-field"] = field
                value_cell["label"] = DISPLAY_LABELS.get(field, label_text)
                fields += 1
    return fields


def direct_table_rows(table: Tag) -> list[Tag]:
    rows: list[Tag] = []
    for child in table.find_all(recursive=False):
        if child.name == "tr":
            rows.append(child)
        elif child.name in {"thead", "tbody", "tfoot"}:
            rows.extend(child.find_all("tr", recursive=False))
    return rows


def group_explicit_table_records(table: Tag, section_type: str) -> int:
    """用明确 data-field 分组，保留原始行文字，不做内容推断。

    EN: Group by explicit data-field, keep the original row text, and make no content inference.

    JA: 明確な data-field でグループ化し、元の行のテキストを残して、内容の推測はしない。
    """
    if table.find(attrs={"data-record-type": True}) or section_type not in COLLECTION_RECORD_CONFIG:
        return 0
    record_type, allowed_fields, primary_fields = COLLECTION_RECORD_CONFIG[section_type]
    rows = direct_table_rows(table)
    if not rows:
        return 0
    groups: list[list[Tag]] = []
    prefix: list[Tag] = []
    current: list[Tag] = []
    current_fields: set[str] = set()
    seen_data = False
    for row in rows:
        fields = {
            str(node.get("data-field") or "")
            for node in row.find_all(attrs={"data-field": True})
            if str(node.get("data-field") or "") in allowed_fields
        }
        if not seen_data and not fields:
            prefix.append(row)
            continue
        if fields:
            seen_data = True
        starts_new = bool(current and fields & primary_fields and current_fields & primary_fields)
        if starts_new:
            groups.append(current)
            current = []
            current_fields = set()
        current.append(row)
        current_fields.update(fields)
    if current:
        groups.append(current)
    valid_groups = [group for group in groups if any(
        str(node.get("data-field") or "") in primary_fields
        for row in group for node in row.find_all(attrs={"data-field": True})
    )]
    if not valid_groups:
        return 0

    for child in list(table.find_all(recursive=False)):
        child.extract()
    if prefix:
        thead = make_tag("thead")
        for row in prefix:
            thead.append(row.extract())
        table.append(thead)
    for index, group in enumerate(valid_groups, 1):
        body = make_tag("tbody")
        body["data-record-type"] = record_type
        body["data-record-index"] = str(index)
        for row in group:
            body.append(row.extract())
        table.append(body)
    return len(valid_groups)


def append_field(parent: Tag, field: str, value: str, label: str | None = None) -> Tag | None:
    value = re.sub(r"\s+", " ", value).strip()
    if not value:
        return None
    node = make_tag("i")
    node["data-field"] = field
    node["label"] = label or DISPLAY_LABELS.get(field, field)
    node.string = value
    parent.append(node)
    return node


def append_labeled_field(parent: Tag, field: str, value: str, label: str) -> None:
    if not value.strip():
        return
    paragraph = make_tag("p")
    label_node = make_tag("span")
    label_node["data-label-for"] = field
    label_node.string = label
    paragraph.append(label_node)
    append_field(paragraph, field, value, label)
    parent.append(paragraph)


def table_date_parts(row: Tag) -> tuple[str, str, str]:
    cells = row.find_all(["th", "td"], recursive=False)
    if len(cells) < 3:
        return "", "", ""
    year = clean_text(cells[0]).strip()
    month = clean_text(cells[1]).strip()
    body = clean_text(cells[2]).strip()
    if not re.search(r"(?:19|20)\d{2}", year):
        return "", "", body
    year_match = re.search(r"((?:19|20)\d{2})", year)
    month_match = re.search(r"(\d{1,2})", month)
    if not year_match or not month_match:
        return "", "", body
    normalized = f"{year_match.group(1)}年{int(month_match.group(1)):02d}月"
    return normalized, body, clean_text(row)


def normalize_year_month(value: str) -> str:
    match = re.search(r"((?:19|20)\d{2})\D{0,4}(0?[1-9]|1[0-2])(?=\D|$)", value)
    return f"{match.group(1)}年{int(match.group(2)):02d}月" if match else ""


def table_period_parts(row: Tag) -> tuple[str, str, str]:
    """支持原始“年/月/内容”和标准“开始/结束/内容”两种表格。

    EN: Supports both the original "year / month / content" tables and the standard "start / end / content" tables.

    JA: 元の「年／月／内容」の表と、標準の「開始／終了／内容」の表の両方に対応する。
    """
    cells = row.find_all(["th", "td"], recursive=False)
    if len(cells) >= 3:
        first = clean_text(cells[0])
        second = clean_text(cells[1])
        body = clean_text(cells[2])
        start = normalize_year_month(first)
        end = normalize_year_month(second)
        if start and (end or not second or re.search(r"至今|現在|今迄|present|current", second, re.I)):
            return start, end or second, body
    start, body, _raw = table_date_parts(row)
    return start, "", body


def split_school_major(value: str) -> tuple[str, str]:
    value = re.sub(r"\s+", " ", value).strip()
    match = re.match(
        r"(.+?(?:大学|学院|学校|カレッジ|専門学校|高校|中学|University|College|Institute))\s+(.+)$",
        value,
        flags=re.I,
    )
    if match:
        return match.group(1).strip(), match.group(2).strip()
    return value, ""


def normalize_japanese_education_table(table: Tag) -> int:
    if not re.search(r"学歴|留学先", clean_text(table)[:250]):
        return 0
    events: list[tuple[str, str]] = []
    records: list[dict[str, str]] = []
    for row in table.find_all("tr"):
        date, explicit_end, body = table_period_parts(row)
        if date and not body:
            events.append((date, ""))
        elif date and body and body not in {"以上", "同"}:
            if explicit_end:
                school = field_value(row, "school_name")
                major = field_value(row, "school_major_name")
                degree = field_value(row, "school_degree_type")
                rank = field_value(row, "school_degree_rank")
                if not school:
                    school, inferred_major = split_school_major(body)
                    major = major or inferred_major
                records.append({
                    "school_start_ym": date,
                    "school_end_ym": explicit_end,
                    "school_name": school,
                    "school_major_name": major,
                    "school_degree_type": degree,
                    "school_degree_rank": rank,
                })
            else:
                events.append((date, body))
    if len(events) < 2 and not records:
        return 0
    index = 0
    while index < len(events):
        start, first_body = events[index]
        if re.fullmatch(r"(?:同\s*)?(?:入学|卒業|修了|退学).*$", first_body):
            index += 1
            continue
        school, major = split_school_major(first_body)
        end = ""
        if index + 1 < len(events):
            possible_end, end_body = events[index + 1]
            if not end_body or re.search(r"卒業|修了|退学|入学\s*同\s*卒業", end_body):
                end = possible_end
                extra = re.sub(r"(?:入学\s*)?(?:同\s*)?(?:卒業|修了|退学).*$", "", end_body).strip()
                if extra and not major:
                    major = extra
                index += 1
        records.append({
            "school_start_ym": start,
            "school_end_ym": end,
            "school_name": school,
            "school_major_name": major,
            "school_degree_type": "",
            "school_degree_rank": "",
        })
        index += 1
    if not records:
        return 0

    table.clear()
    thead = make_tag("thead")
    header_row = make_tag("tr")
    for label in ("开始时间", "结束时间", "学歴"):
        cell = make_tag("th")
        cell.string = label
        header_row.append(cell)
    thead.append(header_row)
    table.append(thead)
    for record_index, record in enumerate(records, 1):
        body = make_tag("tbody")
        body["data-record-type"] = "education"
        body["data-record-index"] = str(record_index)
        row = make_tag("tr")
        for field in ("school_start_ym", "school_end_ym"):
            cell = make_tag("td")
            append_field(cell, field, record[field], "开始时间" if field.endswith("start_ym") else "结束时间")
            row.append(cell)
        detail = make_tag("td")
        append_field(detail, "school_name", record["school_name"], "学校名称")
        append_field(detail, "school_major_name", record["school_major_name"], "专业名称")
        append_field(detail, "school_degree_type", record.get("school_degree_type", ""), "学历类型")
        append_field(detail, "school_degree_rank", record.get("school_degree_rank", ""), "学历等级")
        row.append(detail)
        body.append(row)
        table.append(body)
    return len(records)


def field_value(row: Tag, field: str) -> str:
    node = row.find(attrs={"data-field": field})
    return clean_text(node) if isinstance(node, Tag) else ""


def normalize_japanese_work_table(table: Tag) -> int:
    table_text = clean_text(table)
    if not re.search(r"職歴|職務経歴", table_text[:250]) and not (
        re.search(r"(?:19|20)\d{2}", table_text) and re.search(r"会社|有限公司|株式会社", table_text)
    ):
        return 0
    rows = table.find_all("tr")
    starts = [index for index, row in enumerate(rows) if row.find(attrs={"data-field": "company_name"})]
    if not starts:
        dated: list[tuple[str, str]] = []
        for row in rows:
            date, _explicit_end, body = table_period_parts(row)
            if date:
                dated.append((date, re.sub(r"\s*以上\s*$", "", body).strip()))
        first = next(((date, body) for date, body in dated if body), None)
        if first is None:
            return 0
        start_date, body = first
        end_date = next((date for date, value in dated[dated.index(first) + 1:] if not value), "")
        company_match = re.match(r"(.+?(?:株式会社|有限会社|有限公司|会社))\s*(.*)$", body)
        company = company_match.group(1).strip() if company_match else body
        remainder = company_match.group(2).strip() if company_match else ""
        position = ""
        department = remainder
        role_match = re.search(r"(アシスタント|助手|助理|担当|営業|経理|人事|総務)$", remainder)
        if role_match:
            position = role_match.group(1)
            department = remainder[:role_match.start()].strip()
        records = [{
            "position_start": start_date,
            "position_resigned": end_date,
            "company_name": company,
            "position": position,
            "position_dept": department,
            "position_responsibilities": "",
            "resigned_reason": "",
        }]
        starts = []
    else:
        records = []
    for record_index, start_index in enumerate(starts):
        end_index = starts[record_index + 1] if record_index + 1 < len(starts) else len(rows)
        group = rows[start_index:end_index]
        start_date, explicit_end, _body = table_period_parts(group[0])
        end_date = explicit_end
        for row in group[1:]:
            date, _explicit_end, _row_body = table_period_parts(row)
            if date:
                end_date = date
                break
        combined = " ".join(clean_text(row.find_all(["td", "th"], recursive=False)[-1]) for row in group if row.find_all(["td", "th"], recursive=False))
        company = field_value(group[0], "company_name")
        department = field_value(group[0], "position_dept")
        responsibility_match = re.search(r"業務内容\s*[:：]?\s*(.*?)(?=退職理由\s*[:：]?|$)", combined)
        reason_match = re.search(r"退職理由\s*[:：]?\s*(.*)$", combined)
        responsibility = responsibility_match.group(1).strip() if responsibility_match else field_value(group[0], "position_responsibilities")
        reason = reason_match.group(1).strip() if reason_match else ""
        records.append({
            "position_start": start_date,
            "position_resigned": end_date,
            "company_name": company,
            "position_dept": department,
            "position_responsibilities": responsibility,
            "resigned_reason": reason,
        })

    for index, record in enumerate(records):
        if record.get("position_resigned"):
            continue
        if index + 1 < len(records):
            record["position_resigned"] = records[index + 1].get("position_start", "")
        elif starts:
            trailing_dates: list[str] = []
            for row in rows[starts[-1] + 1:]:
                date, _explicit_end, body = table_period_parts(row)
                if date and not body:
                    trailing_dates.append(date)
            if trailing_dates:
                record["position_resigned"] = trailing_dates[-1]

    table.clear()
    thead = make_tag("thead")
    header_row = make_tag("tr")
    for label in ("开始时间", "结束时间", "職歴・職務経歴"):
        cell = make_tag("th")
        cell.string = label
        header_row.append(cell)
    thead.append(header_row)
    table.append(thead)
    for record_index, record in enumerate(records, 1):
        body = make_tag("tbody")
        body["data-record-type"] = "work_experience"
        body["data-record-index"] = str(record_index)
        row = make_tag("tr")
        for field in ("position_start", "position_resigned"):
            cell = make_tag("td")
            append_field(cell, field, record[field], "开始时间" if field == "position_start" else "结束时间")
            row.append(cell)
        detail = make_tag("td")
        append_labeled_field(detail, "company_name", record["company_name"], "企業名")
        append_labeled_field(detail, "position", record.get("position", ""), "職位")
        append_labeled_field(detail, "position_dept", record["position_dept"], "所属部門")
        append_labeled_field(detail, "position_responsibilities", record["position_responsibilities"], "業務内容")
        append_labeled_field(detail, "resigned_reason", record["resigned_reason"], "退職理由")
        row.append(detail)
        body.append(row)
        table.append(body)
    return len(records)


def normalize_japanese_certificate_table(table: Tag) -> int:
    if not re.search(r"資格|免許", clean_text(table)[:250]):
        return 0
    records: list[tuple[str, str]] = []
    for row in table.find_all("tr"):
        cells = row.find_all(["th", "td"], recursive=False)
        first_text = clean_text(cells[0]) if cells else ""
        certificate_with_date = re.match(r"(.+?(?:試験|資格|免許|級))\s*[（(]((?:19|20)\d{2}[./年-]\d{1,2}(?:[./月-]\d{1,2})?)", first_text)
        if certificate_with_date:
            date = normalize_year_month(certificate_with_date.group(2))
            name = certificate_with_date.group(1).strip()
        elif len(cells) == 2 and re.match(r"^\s*(?:19|20)\d{2}", first_text):
            date = normalize_year_month(first_text)
            name = clean_text(cells[1])
        else:
            date, name, _raw = table_date_parts(row)
        name = re.sub(r"\s*以上\s*$", "", name).strip()
        if date and name and not field_for_label(name.rstrip("：:")):
            records.append((date, name))
    if not records:
        return 0
    table.clear()
    thead = make_tag("thead")
    header_row = make_tag("tr")
    for label in ("证书取得年月", "证书・資格名称"):
        cell = make_tag("th")
        cell.string = label
        header_row.append(cell)
    thead.append(header_row)
    table.append(thead)
    for record_index, (date, name) in enumerate(records, 1):
        body = make_tag("tbody")
        body["data-record-type"] = "certificate"
        body["data-record-index"] = str(record_index)
        row = make_tag("tr")
        date_cell = make_tag("td")
        append_field(date_cell, "certificate_time", date, "取得时间")
        row.append(date_cell)
        name_cell = make_tag("td")
        append_field(name_cell, "certificate_name", name, "证书名称")
        row.append(name_cell)
        body.append(row)
        table.append(body)
    return len(records)


def split_certificate_skills(section: Tag) -> int:
    """拆分“資格 / IT技能”并列的日文履歴書单元格。

    EN: Split Japanese rirekisho cells where "資格 / IT技能" (qualifications / IT skills) are side by side.

    JA: 「資格 / IT技能」が並んでいる日本の履歴書のセルを分割する。
    """
    if section.get("data-section-type") != "certificate_list":
        return 0
    for row in section.find_all("tr"):
        cells = row.find_all(["th", "td"], recursive=False)
        if len(cells) < 2:
            continue
        certificate_text = clean_text(cells[0])
        skill_text = clean_text(cells[1])
        if not re.search(r"(?:試験|資格|免許|級)\s*[（(](?:19|20)\d{2}", certificate_text):
            continue
        if not skill_text or field_for_label(skill_text.rstrip("：:")):
            continue
        cells[1].clear()
        skills = make_tag("section")
        skills["data-section-type"] = "skills_list"
        skills["data-collection"] = "skills_list"
        table = make_tag("table")
        body = make_tag("tbody")
        body["data-record-type"] = "skill"
        body["data-record-index"] = "1"
        skill_row = make_tag("tr")
        skill_cell = make_tag("td")
        append_field(skill_cell, "skill_name", skill_text, "技能名称")
        skill_row.append(skill_cell)
        body.append(skill_row)
        table.append(body)
        skills.append(table)
        section.insert_after(skills)
        return 1
    return 0


def merge_detached_work_responsibilities(record: Tag) -> int:
    target = record.find(attrs={"data-record-type": "work_experience"})
    if target is None:
        return 0
    targets = record.find_all(attrs={"data-record-type": "work_experience"})
    target = targets[-1]
    merged = 0
    for section in list(record.find_all("section", recursive=False)):
        if section.get("data-section-type") != "work_experiences" or section.find(attrs={"data-record-type": True}):
            continue
        heading = section.find(["h1", "h2", "h3", "h4", "h5", "h6"], recursive=False)
        if not heading or not re.search(r"工作内容|仕事内容|業務内容", clean_text(heading)):
            continue
        values = [clean_text(block) for block in section.find_all(["p", "tr"], recursive=True)]
        responsibility = " ".join(dict.fromkeys(value for value in values if value and not re.fullmatch(r"工作内容[:：]?|仕事内容[:：]?|業務内容[:：]?", value)))
        detail = target.find("td")
        all_cells = target.find_all("td")
        if all_cells:
            detail = all_cells[-1]
        if detail and responsibility:
            append_labeled_field(detail, "position_responsibilities", responsibility, "業務内容")
            section.decompose()
            merged += 1
    return merged


def rebuild_sections(record: Tag) -> int:
    blocks: list[Tag | NavigableString] = []
    for section in list(record.find_all("section", recursive=False)):
        blocks.extend(node.extract() for node in list(section.contents) if not isinstance(node, NavigableString) or node.strip())
        section.decompose()
    if not blocks:
        return 0

    record.clear()
    sections: list[Tag] = []
    current: Tag | None = None

    def start_section(section_type: str) -> Tag:
        section = make_tag("section")
        section["data-section-type"] = section_type
        if section_type in COLLECTIONS:
            section["data-collection"] = section_type
        record.append(section)
        sections.append(section)
        return section

    for block in blocks:
        block_type = ""
        if isinstance(block, Tag):
            if block.name == "table":
                block_type = table_section_type(block)
            elif block.name in {"h1", "h2", "h3", "h4", "h5", "h6"}:
                block_type = infer_section_type(clean_text(block))
            elif block.name == "p" and len(clean_text(block)) <= 80:
                block_type = infer_section_type(clean_text(block))
        if block_type:
            if current is None or current.get("data-section-type") != block_type or (isinstance(block, Tag) and block.name == "table"):
                current = start_section(block_type)
        elif current is None:
            current = start_section("document-body")
        current.append(block)

    for section_index, section in enumerate(sections, 1):
        section["data-section-index"] = str(section_index)
        heading = section.find(["h1", "h2", "h3", "h4", "h5", "h6"], recursive=False)
        if heading:
            heading_id = f"resume-{record.get('data-resume-index', '1')}-section-{section_index}-heading"
            heading["id"] = heading_id
            section["aria-labelledby"] = heading_id
        for block_index, block in enumerate(section.find_all(recursive=False), 1):
            block["data-block-index"] = str(block_index)
            block["data-block-type"] = block.name
    return len(sections)


def refresh_section_metadata(record: Tag) -> None:
    for section_index, section in enumerate(record.find_all("section", recursive=False), 1):
        section["data-section-index"] = str(section_index)
        if section.get("data-section-type") in COLLECTIONS:
            section["data-collection"] = str(section.get("data-section-type"))
        for block_index, block in enumerate(section.find_all(recursive=False), 1):
            block["data-block-index"] = str(block_index)
            block["data-block-type"] = block.name
    # 子表可以分别生成记录，但索引必须在最近的 collection 边界内统一连续，
    # 否则后续按 data-record-index 遍历会得到多个“第 1 条”。
    # EN: Sub-tables may generate records separately, but indexes must be unified and continuous within the nearest collection boundary,
    #     otherwise later traversal by data-record-index yields several "item 1"s.
    # JA: 子の表はそれぞれレコードを生成してよいが、番号は最も近い collection の境界の中で統一して連続させなければならない。
    #     さもないと後で data-record-index で走査したときに「1 件目」が複数できてしまう。
    for collection in record.find_all(attrs={"data-collection": True}):
        counters: dict[str, int] = {}
        for item in collection.find_all(attrs={"data-record-type": True}):
            if item.find_parent(attrs={"data-collection": True}) is not collection:
                continue
            kind = str(item.get("data-record-type") or "")
            counters[kind] = counters.get(kind, 0) + 1
            item["data-record-index"] = str(counters[kind])


def annotate_record(record: Tag, issues: list[str]) -> dict[str, int]:
    metrics = {
        "merged_labels": 0,
        "removed_template_rows": 0,
        "annotated_fields": 0,
        "sections": 0,
        "grouped_records": 0,
    }
    if set(issues) == {"bad_record_indices"}:
        refresh_section_metadata(record)
        return metrics
    if "invalid_collection_record" in issues:
        for table in record.find_all("table"):
            invalid_items = []
            for item in table.find_all(attrs={"data-record-type": True}):
                kind = str(item.get("data-record-type") or "")
                fields = {str(node.get("data-field") or "") for node in item.find_all(attrs={"data-field": True})}
                invalid_month = any(
                    re.search(r"年(?:1[3-9]|[2-9]\d)月", clean_text(node))
                    for node in item.find_all(attrs={"data-field": True})
                )
                if (kind in RECORD_PRIMARY_FIELDS and not fields.intersection(RECORD_PRIMARY_FIELDS[kind])) or invalid_month:
                    invalid_items.append(item)
            if invalid_items:
                for item in table.find_all(attrs={"data-record-type": True}):
                    item.attrs.pop("data-record-type", None)
                    item.attrs.pop("data-record-index", None)
    for section in list(record.find_all("section", recursive=False)):
        metrics["grouped_records"] += split_certificate_skills(section)
    # 已经明确分区的日文标准表先记录化，保留用户/既有的正确 data-field。
    # EN: Standard Japanese tables that are already clearly partitioned are turned into records first, keeping correct user/existing data-field values.
    # JA: すでに明確に区分された日本語の標準的な表は先にレコード化し、ユーザーや既存の正しい data-field を残す。
    for section in record.find_all("section", recursive=False):
        for table in section.find_all("table"):
            if table.find(attrs={"data-record-type": True}):
                continue
            section_type = str(section.get("data-section-type") or "")
            existing_fields = {str(node.get("data-field") or "") for node in table.find_all(attrs={"data-field": True})}
            if section_type == "work_experiences" and "company_name" in existing_fields:
                metrics["grouped_records"] += normalize_japanese_work_table(table)
            elif section_type == "education_list" and "school_name" in existing_fields:
                metrics["grouped_records"] += normalize_japanese_education_table(table)
            elif section_type == "certificate_list" and "certificate_name" in existing_fields:
                metrics["grouped_records"] += normalize_japanese_certificate_table(table)
    clear_machine_annotations(record)
    for table in record.find_all("table"):
        if table.find(attrs={"data-record-type": True}):
            continue
        metrics["merged_labels"] += merge_fragmented_labels(table)
        metrics["removed_template_rows"] += remove_empty_template_rows(table)
    if "untyped_business_table" in issues:
        metrics["sections"] = rebuild_sections(record)
    else:
        refresh_section_metadata(record)
    for section in record.find_all("section", recursive=False):
        for table in section.find_all("table"):
            if table.find(attrs={"data-record-type": True}):
                continue
            metrics["annotated_fields"] += annotate_table(table)
            section_type = str(section.get("data-section-type") or "")
            if section_type == "work_experiences":
                metrics["grouped_records"] += normalize_japanese_work_table(table)
            elif section_type == "education_list":
                metrics["grouped_records"] += normalize_japanese_education_table(table)
            elif section_type == "certificate_list":
                metrics["grouped_records"] += normalize_japanese_certificate_table(table)
            metrics["grouped_records"] += group_explicit_table_records(table, section_type)
        for paragraph in section.find_all("p"):
            if paragraph.find_parent("table") is None:
                metrics["annotated_fields"] += annotate_composite(paragraph) or annotate_inline(paragraph)
    metrics["grouped_records"] += merge_detached_work_responsibilities(record)
    refresh_section_metadata(record)
    return metrics


def normalized_content_text(root: Tag) -> str:
    return re.sub(r"\s+", "", root.get_text(" ", strip=True))


def contact_value_preserved(phone: str, email: str, after_text: str) -> bool:
    phone_digits = re.sub(r"\D", "", phone)
    all_after_digits = re.sub(r"\D", "", after_text)
    compact_after = re.sub(r"\s+", "", after_text).casefold()
    detected_phone, detected_email = extract_contacts(after_text)
    return (
        (not phone_digits or phone == detected_phone or phone_digits in all_after_digits)
        and (
            not email
            or email.casefold() == detected_email.casefold()
            or re.sub(r"\s+", "", email).casefold() in compact_after
        )
    )


def validate_repaired_soup(soup: BeautifulSoup) -> dict[str, Any]:
    """与第一步校验器相同，但复用当前 DOM，避免每份文件再次完整解析。

    EN: Same as the step-1 validator, but reuses the current DOM to avoid fully parsing each file again.

    JA: 第 1 段階の検証器と同じだが、現在の DOM を再利用し、ファイルごとに完全に解析し直すのを避ける。
    """
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


def repair_html(html_text: str) -> tuple[str, dict[str, Any]]:
    soup = BeautifulSoup(html_text, "lxml")
    main = soup.find("main", attrs={"data-role": "document-content"})
    if main is None:
        return html_text, {"changed": False, "issues": ["missing_main"], "error": "缺少 main"}
    document = soup.find("article", attrs={"data-schema-version": SCHEMA_VERSION})
    if document and document.get("data-dom-repair-version") == REPAIR_VERSION:
        return html_text, {"changed": False, "issues": []}
    records = list(main.find_all("article", attrs={"data-role": "resume"}, recursive=False)) or [main]
    issues_by_record = [audit_record(record) for record in records]
    if not any(issues_by_record):
        return html_text, {"changed": False, "issues": []}

    before_text = normalized_content_text(main)
    before_phone, before_email = extract_contacts(main.get_text(" ", strip=True))
    metrics: list[dict[str, int]] = []
    for record, issues in zip(records, issues_by_record):
        if issues:
            metrics.append(annotate_record(record, issues))
        else:
            metrics.append({
                "merged_labels": 0,
                "removed_template_rows": 0,
                "annotated_fields": 0,
                "sections": 0,
                "grouped_records": 0,
            })
    if document:
        document["data-dom-repair-version"] = REPAIR_VERSION
    validation = validate_repaired_soup(soup)
    output = str(soup)
    after_main = soup.find("main", attrs={"data-role": "document-content"}) or main
    after_text = normalized_content_text(after_main)
    after_plain_text = after_main.get_text(" ", strip=True)
    sequence_retention = SequenceMatcher(None, before_text, after_text).ratio() if before_text else 1.0
    before_chars = Counter(before_text)
    after_chars = Counter(after_text)
    content_retention = (
        sum((before_chars & after_chars).values()) / len(before_text)
        if before_text else 1.0
    )
    grouped_records = sum(metric.get("grouped_records", 0) for metric in metrics)
    # 记录化会把“开始行/结束行”重排到同一条经历中，序列相似度不再适合；
    # 改用字符内容保留率，仍禁止大段正文丢失。
    # EN: Record-ification rearranges "start row / end row" into the same experience, so sequence similarity is no longer suitable;
    #     use the character-content retention rate instead, still forbidding the loss of large chunks of body text.
    # JA: レコード化は「開始行／終了行」を同じ経歴に並べ替えるため、並びの類似度はもう適さない。
    #     代わりに文字の内容の保持率を使い、本文の大きな欠落は引き続き禁止する。
    retention = content_retention if grouped_records else sequence_retention
    contact_preserved = contact_value_preserved(before_phone, before_email, after_plain_text)
    errors: list[str] = []
    if not validation["valid"]:
        errors.extend(validation["errors"])
    retention_floor = 0.90 if grouped_records else 0.94
    if retention < retention_floor:
        errors.append(f"正文保留率过低：{retention:.4f}")
    if not contact_preserved:
        errors.append("联系方式未保持")
    if errors:
        fallback = conservative_repair_html(html_text, issues_by_record)
        if fallback is not None:
            return fallback
        return html_text, {
            "changed": False, "issues": sorted(set(sum(issues_by_record, []))),
            "error": "; ".join(errors), "retention": retention,
        }
    return output, {
        "changed": True, "issues": sorted(set(sum(issues_by_record, []))),
        "retention": round(retention, 6),
        "sequence_retention": round(sequence_retention, 6),
        "content_retention": round(content_retention, 6),
        "metrics": metrics,
        "validation": validation,
    }


def conservative_repair_html(
    html_text: str,
    issues_by_record: list[list[str]],
) -> tuple[str, dict[str, Any]] | None:
    """专用归并失败后的无损降级：不删行、不重排文本。

    EN: Lossless degradation after the dedicated merge fails: no rows deleted, no text reordered.

    JA: 専用の統合が失敗した後の無損失の代替処理：行は削除せず、テキストも並べ替えない。
    """
    soup = BeautifulSoup(html_text, "lxml")
    main = soup.find("main", attrs={"data-role": "document-content"})
    if main is None:
        return None
    before_text = normalized_content_text(main)
    before_phone, before_email = extract_contacts(main.get_text(" ", strip=True))
    records = list(main.find_all("article", attrs={"data-role": "resume"}, recursive=False)) or [main]
    grouped = 0
    annotated = 0
    for record in records:
        for section in record.find_all("section", recursive=False):
            section_type = str(section.get("data-section-type") or "document-body")
            if section_type in COLLECTIONS:
                section["data-collection"] = section_type
            for table in section.find_all("table"):
                if table.find(attrs={"data-record-type": True}):
                    continue
                # 保守降级必须真正保持原始 DOM 的文字和顺序。碎片标签合并会
                # 清空/搬移相邻单元格，即便字符大体保留，也可能改变联系方式
                # 或正文的连续取值；这种结构性操作只允许在主修复路径执行。
                # EN: The conservative degradation must truly preserve the text and order of the original DOM. Merging fragment labels
                #     clears/moves adjacent cells; even if the characters are mostly preserved, it may change the consecutive values of contact details
                #     or body text; such structural operations are allowed only on the main repair path.
                # JA: 保守的な代替処理では、元の DOM のテキストと順序を本当に保たなければならない。断片のラベルの結合は
                #     隣のセルを空にしたり移動したりするため、文字がおおむね保たれていても、連絡先や本文の連続した値が
                #     変わることがある。このような構造的な操作はメインの修復経路でだけ許可する。
                annotated += annotate_table_nonmutating(table)
        refresh_section_metadata(record)
    document = soup.find("article", attrs={"data-schema-version": SCHEMA_VERSION})
    if document:
        document["data-dom-repair-version"] = REPAIR_VERSION
        document["data-dom-repair-mode"] = "conservative"
    validation = validate_repaired_soup(soup)
    after_main = soup.find("main", attrs={"data-role": "document-content"}) or main
    after_text = normalized_content_text(after_main)
    after_plain_text = after_main.get_text(" ", strip=True)
    before_chars = Counter(before_text)
    after_chars = Counter(after_text)
    retention = sum((before_chars & after_chars).values()) / len(before_text) if before_text else 1.0
    contacts_ok = contact_value_preserved(before_phone, before_email, after_plain_text)
    if not validation["valid"] or retention < 0.98 or not contacts_ok:
        return None
    output = str(soup)
    return output, {
        "changed": True,
        "issues": sorted(set(sum(issues_by_record, []))),
        "retention": round(retention, 6),
        "repair_mode": "conservative",
        "metrics": [{"grouped_records": grouped, "annotated_fields": annotated}],
        "validation": validation,
    }


def atomic_write_text(path: Path, value: str) -> None:
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(value)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def atomic_write_json(path: Path, payload: Any) -> None:
    atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def iter_html_files(root: Path, only: Path | None = None) -> Iterable[Path]:
    if only:
        yield only.resolve()
    else:
        yield from sorted(
            path.resolve()
            for path in root.rglob("*.html")
            if path.is_file() and not re.search(r"(?:^|[ _-])demo\.html$", path.name, re.I)
        )


def run(
    root: Path,
    map_path: Path,
    report_path: Path,
    apply: bool,
    only: Path | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    paths = list(iter_html_files(root.resolve(), only))
    if limit:
        paths = paths[:limit]
    report: dict[str, Any] = {
        "repair_version": REPAIR_VERSION, "mode": "apply" if apply else "dry-run",
        "root": str(root.resolve()), "total_scanned": len(paths), "compliant_unchanged": 0,
        "repair_candidates": 0, "changed": 0, "rejected": 0,
        "issue_counts": {}, "items": [],
    }
    records = json.loads(map_path.read_text(encoding="utf-8")) if map_path.is_file() else []
    records_by_html = {str(record.get("html_path") or "").casefold(): record for record in records if record.get("html_path")}
    issue_counts: Counter[str] = Counter()
    for index, path in enumerate(paths, 1):
        try:
            original = path.read_text(encoding="utf-8", errors="replace")
            repaired, result = repair_html(original)
        except Exception as exc:
            repaired = ""
            result = {
                "changed": False,
                "issues": ["processing_error"],
                "error": f"{type(exc).__name__}: {exc}",
            }
        item: dict[str, Any] = {"html_path": str(path), **result}
        if not result.get("issues"):
            report["compliant_unchanged"] += 1
        else:
            report["repair_candidates"] += 1
            issue_counts.update(result["issues"])
            if result.get("changed"):
                if apply:
                    atomic_write_text(path, repaired)
                    record = records_by_html.get(str(path).casefold())
                    if record is not None:
                        record["dom_repair_version"] = REPAIR_VERSION
                        record["dom_repair_issues"] = result["issues"]
                        record["validation"] = result.get("validation", record.get("validation", {}))
                report["changed"] += 1
            else:
                report["rejected"] += 1
        if result.get("issues") or result.get("error"):
            report["items"].append(item)
        if index % 250 == 0 or index == len(paths):
            print(
                f"[{index}/{len(paths)}] compliant={report['compliant_unchanged']} "
                f"candidate={report['repair_candidates']} changed={report['changed']} rejected={report['rejected']}",
                flush=True,
            )
        # 长批次可随时恢复；每个 HTML 已单独原子保存，报告和映射定期落盘。
        # EN: Long batches can resume at any time; each HTML is saved atomically on its own, and reports and maps are flushed to disk periodically.
        # JA: 長いバッチはいつでも再開できる。各 HTML は個別にアトミックに保存し、レポートとマップは定期的にディスクに書き出す。
        if apply and (index % 100 == 0 or index == len(paths)):
            report["issue_counts"] = dict(sorted(issue_counts.items()))
            report["processed"] = index
            atomic_write_json(map_path, records)
            atomic_write_json(report_path, report)
    report["issue_counts"] = dict(sorted(issue_counts.items()))
    if apply:
        atomic_write_json(map_path, records)
    atomic_write_json(report_path, report)
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="选择性修复难解析的 resume DOM；合格 HTML 保持不变" " / Selectively repair résumé DOM that is hard to parse; qualified HTML is left unchanged / 解析しにくい resume の DOM を選択的に修復する（合格した HTML は変更しない）")
    parser.add_argument("--root", type=Path, default=DEFAULT_PASSED)
    parser.add_argument("--map", type=Path, default=DEFAULT_MAP)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--only", type=Path)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--summary-only", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    result = run(args.root, args.map, args.report, args.apply, args.only, args.limit)
    if args.summary_only:
        result = {key: value for key, value in result.items() if key != "items"}
    print(json.dumps(result, ensure_ascii=False, indent=2))
