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
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = _rc.project_root()
PDF_ROOT = PROJECT_ROOT / _rc.dirname("complete-transfered-htmls") / "pdf"
DEFAULT_JSON_ROOT = PROJECT_ROOT / _rc.dirname("complete-transfered-jsons") / "pdf" / "new"
DEFAULT_MAP = PDF_ROOT / "rebuild-work" / "pdf_rebuild_map.v2.json"
DEFAULT_REPORT = PDF_ROOT / "rebuild-reports" / "pdf_json_strict_audit.v2.json"
DEFAULT_CSV = PDF_ROOT / "rebuild-reports" / "pdf_json_strict_audit.v2.csv"
VERSION = "pdf-json-strict-audit-v2.0.0"

SEVERITY = {"low": 1, "medium": 2, "high": 3, "critical": 4}
EMAIL_RE = re.compile(r"^[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}$", re.I)
HTML_LEAK_RE = re.compile(r"</?[a-z][^>]*>|data-[a-z-]+\s*=|\blabel\s*=|&(?:nbsp|lt|gt|amp);", re.I)
COMPANY_SUFFIX_RE = re.compile(r"有限公司|有限责任公司|股份有限公司|株式会社|有限会社|会社|公司|\b(?:Co\.?|Ltd\.?|Inc\.?|Corp\.?|Corporation|Company|GmbH|AG)\b", re.I)
SCHOOL_RE = re.compile(r"大学|学院|学校|高校|中学|小学|研究科|研究院|University|College|School|Institute|Academy|Université|Universität", re.I)
DEGREE_MAJOR_RE = re.compile(r"专业|専攻|学科|学部|本科|硕士|博士|学士|Master|Bachelor|Ph\.?D|Major", re.I)
WORK_HEADING_RE = re.compile(r"工作经历|工作经验|职业经历|職歴|職務経歴|Work(?:ing)?\s+Experience|Employment|Berufserfahrung", re.I)
EDU_HEADING_RE = re.compile(r"教育经历|教育背景|学历|学歴|Education|Academic|Ausbildung", re.I)
BAD_ENTITY_RE = re.compile(
    r"^(?:公司名(?:称)?|会社名|学校名|school|company|毕业|卒業|离职原因|退職理由|履歴書|職歴|学歴|"
    r"工作经历|教育经历|部门|部署|所属|职位|職位|役職|Principal|Post/Wages|School Honors|Graduate Info\.?|～|-|—|\d{1,2})$",
    re.I,
)
BAD_SCHOOL_CONTENT_RE = re.compile(r"工作经历|職歴|公司名|会社名|离职原因|退職理由|项目|プロジェクト|奖学金|奨学金|自我评价|自己PR|Career|Responsibilities", re.I)
BAD_COMPANY_CONTENT_RE = re.compile(r"学历|学歴|教育经历|毕业|卒業|学校名|履歴書|离职原因|退職理由|Job Responsibility", re.I)
# Match 10-12 before 1-9; otherwise regex alternation parses December as month 1.
DATE_RE = re.compile(r"(?P<year>(?:19|20)\d{2})\D{0,4}(?P<month>1[0-2]|0?[1-9])?")
GENERIC_NAME_RE = re.compile(r"履歴書|職務経歴書|简历|resume|curriculum|vitae|日文|中文|英文|基本情報|个人资料|Akademische Laufbahn|待确认|未知", re.I)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="严格审计 PDF 候选人 JSON 的字段、结构、语义和源证据" " / Strictly audit the fields, structure, semantics and source evidence of the PDF candidate JSON / PDF 候補者 JSON のフィールド、構造、意味、元ファイルの証拠を厳密に監査する")
    parser.add_argument("--json-root", type=Path, default=DEFAULT_JSON_ROOT)
    parser.add_argument("--map", type=Path, default=DEFAULT_MAP)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    return parser.parse_args()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".tmp", dir=path.parent, delete=False) as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
        temporary = Path(stream.name)
    temporary.replace(path)


def text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def compact(value: Any) -> str:
    value = unicodedata.normalize("NFKC", text(value)).casefold()
    return re.sub(r"[^0-9a-z\u3400-\u9fff\u3040-\u30ff]", "", value)


def language(resume: dict[str, Any]) -> str:
    value = text(resume.get("resume_language") or resume.get("resume_languge")).casefold()
    return {"jp": "ja", "jpn": "ja", "cn": "zh", "ch": "zh", "eng": "en"}.get(value, value)


def date_value(value: Any) -> tuple[int, int] | None:
    value = unicodedata.normalize("NFKC", text(value))
    if not value:
        return None
    match = DATE_RE.search(value)
    if not match:
        return None
    return int(match.group("year")), int(match.group("month") or 1)


def strip_html(value: str) -> str:
    value = re.sub(r"<script\b[^>]*>.*?</script>|<style\b[^>]*>.*?</style>", " ", value, flags=re.I | re.S)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", value))).strip()


def source_text_index(mapping: dict[str, Any]) -> dict[str, str]:
    output: dict[str, str] = {}
    for row in mapping.get("records") or []:
        filename = text(row.get("input_filename"))
        html_path = Path(text((row.get("processing") or {}).get("html_path")))
        if not filename or not html_path.is_file():
            continue
        output[filename.casefold()] = strip_html(html_path.read_text(encoding="utf-8", errors="replace"))
    return output


def issue(code: str, severity: str, path: str, value: Any, message: str) -> dict[str, Any]:
    return {"code": code, "severity": severity, "path": path, "value": text(value)[:300], "message": message}


def validate_contact(base: dict[str, Any], path: str, issues: list[dict[str, Any]]) -> None:
    email = text(base.get("email"))
    if email and not EMAIL_RE.fullmatch(email):
        issues.append(issue("invalid_email", "high", f"{path}.email", email, "邮箱格式非法或含空格"))
    phone = text(base.get("phone"))
    digits = re.sub(r"\D", "", phone)
    if phone and not (8 <= len(digits) <= 16):
        issues.append(issue("invalid_phone", "high", f"{path}.phone", phone, "电话号码数字长度不在 8-16 位"))


def validate_name(name: Any, path: str, issues: list[dict[str, Any]]) -> None:
    value = text(name)
    normalized = compact(value)
    if not normalized:
        issues.append(issue("missing_name", "critical", path, value, "姓名为空"))
    elif len(normalized) > 40 or GENERIC_NAME_RE.search(value):
        issues.append(issue("unreliable_name", "high", path, value, "姓名疑似标题、语言标签或非人名"))


def validate_date_pair(start: Any, end: Any, path: str, issues: list[dict[str, Any]], education: bool = False) -> None:
    start_text, end_text = text(start), text(end)
    start_date, end_date = date_value(start_text), date_value(end_text)
    if start_text and start_date is None:
        issues.append(issue("invalid_start_date", "high", f"{path}.start", start_text, "开始日期无法解析"))
    if end_text and end_date is None:
        severity = "high" if education or end_text not in {"至今", "现在", "今", "Present", "Current", "Now"} else "medium"
        issues.append(issue("invalid_end_date", severity, f"{path}.end", end_text, "结束日期未按标准格式保存"))
    if start_date and end_date and start_date > end_date:
        issues.append(issue("reversed_date_range", "high", path, f"{start_text} -> {end_text}", "开始日期晚于结束日期"))


def validate_entity(value: Any, path: str, kind: str, issues: list[dict[str, Any]]) -> None:
    current = text(value)
    if not current:
        issues.append(issue(f"missing_{kind}", "high", path, current, f"{kind} 为空"))
        return
    if HTML_LEAK_RE.search(current):
        issues.append(issue("html_markup_leak", "critical", path, current, "业务字段中泄漏 HTML/DOM 标记"))
    if BAD_ENTITY_RE.fullmatch(current):
        issues.append(issue("template_placeholder_entity", "critical", path, current, "实体字段是模板占位词或章节标题"))
    if kind == "school" and (
        re.search(r"携帯番号|手机|電話|身份证|身分証|職\s*歴|現在状況|入学のため退職|大学を卒業してから|講師として|働き", current, re.I)
        or re.match(r"^\s*[-—–]?\s*(?:19|20)\d{2}[./年]", current)
        or re.fullmatch(r"(?:大学|学院|学校|高校|専門学校|卒業学校|大学学士|学歴(?:\s*[（(].*)?)", current, re.I)
    ):
        issues.append(issue("invalid_school_entity", "critical", path, current, "学校字段是标签、日期、联系方式或叙述句，不是学校实体"))
    if kind == "company" and re.fullmatch(r"(?:年|担当|職種|職歴|会社名|公司名|WordOOXMLTable\d+)", current, re.I):
        issues.append(issue("invalid_company_entity", "critical", path, current, "公司字段是表头或解析标记，不是公司实体"))
    limit = 120 if kind == "company" else 100
    if len(current) > limit:
        issues.append(issue("entity_text_too_long", "high", path, current, f"{kind} 字段过长，疑似整段正文串入"))
    if kind == "company" and BAD_COMPANY_CONTENT_RE.search(current) and not re.search(r"毕业生就业指导中心", current):
        issues.append(issue("non_company_text_in_company", "high", path, current, "公司字段包含学历、模板或职责文本"))
    if kind == "school" and BAD_SCHOOL_CONTENT_RE.search(current):
        issues.append(issue("non_school_text_in_school", "high", path, current, "学校字段包含工作、项目、奖励或自我评价文本"))


def row_source_supported(row: dict[str, Any], fields: tuple[str, ...], dates: tuple[str, ...], source_norm: str) -> bool:
    terms = [compact(row.get(field)) for field in fields]
    terms = [term for term in terms if len(term) >= 4]
    if any(term in source_norm for term in terms):
        return True
    for field in dates:
        parsed = date_value(row.get(field))
        if parsed and str(parsed[0]) in source_norm:
            return True
    return False


def source_has_work_records(value: str) -> bool:
    if not WORK_HEADING_RE.search(value):
        return False
    has_date = bool(re.search(r"(?:19|20)\d{2}\s*(?:年|[./-])?\s*(?:1[0-2]|0?[1-9])?", value))
    has_employer = bool(
        COMPANY_SUFFIX_RE.search(value)
        or re.search(r"银行|中心|病院|事务所|事務所|科技|集团|商事|入社|入職|Working experience", value, re.I)
    )
    has_job_label = bool(re.search(r"职位|職位|职务|岗位|役職|Job Title|Position|仕事内容|工作描述", value, re.I))
    return has_date and has_employer and (has_job_label or bool(re.search(r"入社|入職", value)))


def source_has_education_records(value: str) -> bool:
    return bool(EDU_HEADING_RE.search(value) and SCHOOL_RE.search(value))


def validate_resume(
    resume: dict[str, Any], index: int, source_norm: str, issues: list[dict[str, Any]],
    semantic_review: dict[str, Any] | None = None,
) -> None:
    semantic_review = semantic_review or {}
    prefix = f"structured_data.resumes[{index}]"
    lang = language(resume)
    if lang not in {"zh", "ja", "en", "de", "fr", "ko", "ru", "es", "pt"}:
        issues.append(issue("invalid_resume_language", "high", f"{prefix}.resume_language", lang, "语言代码不受支持"))
    base = resume.get("base_info") or {}
    validate_name(base.get("full_name"), f"{prefix}.base_info.full_name", issues)
    validate_contact(base, f"{prefix}.base_info", issues)

    works = [row for row in (resume.get("work_experiences") or []) if isinstance(row, dict)]
    work_keys: Counter[tuple[str, str, str, str]] = Counter()
    for row_index, row in enumerate(works):
        path = f"{prefix}.work_experiences[{row_index}]"
        company, position = text(row.get("company_name")), text(row.get("position"))
        validate_entity(company, f"{path}.company_name", "company", issues)
        if len(position) > 140 or HTML_LEAK_RE.search(position):
            issues.append(issue("contaminated_position", "high", f"{path}.position", position, "职位字段过长或含 HTML 标记"))
        school_employment = re.search(
            r"助教|讲师|講師|教师|教師|培训师|教练|コーチ|教授|研究员|研究員|研究生|大学院生|学生研究|管理员|管理員|TA\b|Assistant|Professor|Lecturer|Researcher|Graduate Student|Student Research|Trainer",
            position,
            re.I,
        )
        if SCHOOL_RE.search(company) and DEGREE_MAJOR_RE.search(company + " " + position) and not COMPANY_SUFFIX_RE.search(company) and not school_employment:
            issues.append(issue("education_misclassified_as_work", "critical", path, company, "学历机构/专业被归入工作经历"))
        validate_date_pair(row.get("position_start"), row.get("position_resigned"), path, issues)
        key = (compact(company), compact(row.get("position_start")), compact(row.get("position_resigned")), compact(position))
        if key[0]:
            work_keys[key] += 1
        if source_norm and not semantic_review.get("pdf_verified_work") and not row_source_supported(row, ("company_name", "position"), ("position_start", "position_resigned"), source_norm):
            issues.append(issue("work_not_supported_by_source", "medium", path, company, "公司、职位和日期均未在 Word 源文本中命中"))
    for key, count in work_keys.items():
        if count > 1:
            issues.append(issue("duplicate_work_row", "high", prefix, key[0], f"同一工作记录重复 {count} 次"))

    education_rows = [row for row in (resume.get("education_list") or []) if isinstance(row, dict)]
    education_keys: Counter[tuple[str, str, str]] = Counter()
    for row_index, row in enumerate(education_rows):
        path = f"{prefix}.education_list[{row_index}]"
        school, major = text(row.get("school_name")), text(row.get("school_major_name"))
        validate_entity(school, f"{path}.school_name", "school", issues)
        if len(major) > 140 or HTML_LEAK_RE.search(major):
            issues.append(issue("contaminated_major", "high", f"{path}.school_major_name", major, "专业字段过长或含 HTML 标记"))
        if COMPANY_SUFFIX_RE.search(school) and not SCHOOL_RE.search(school):
            issues.append(issue("work_misclassified_as_education", "critical", path, school, "公司被归入教育经历"))
        validate_date_pair(row.get("school_start_ym"), row.get("school_end_ym"), path, issues, education=True)
        key = (compact(school), compact(row.get("school_start_ym")), compact(row.get("school_end_ym")))
        if key[0]:
            education_keys[key] += 1
        if source_norm and not semantic_review.get("pdf_verified_education") and not row_source_supported(row, ("school_name", "school_major_name"), ("school_start_ym", "school_end_ym"), source_norm):
            issues.append(issue("education_not_supported_by_source", "medium", path, school, "学校、专业和日期均未在 Word 源文本中命中"))
    for key, count in education_keys.items():
        if count > 1:
            issues.append(issue("duplicate_education_row", "high", prefix, key[0], f"同一教育记录重复 {count} 次"))

    work_by_entity = {compact(row.get("company_name")): row for row in works if compact(row.get("company_name"))}
    school_by_entity = {compact(row.get("school_name")): row for row in education_rows if compact(row.get("school_name"))}
    overlap = set(work_by_entity) & set(school_by_entity)
    overlap = {
        key for key in overlap
        if not re.search(
            r"助教|讲师|講師|教师|教師|培训师|教练|コーチ|教授|研究员|研究員|管理员|管理員|TA\b|Assistant|Professor|Lecturer|Researcher",
            text(work_by_entity[key].get("position")), re.I,
        )
    }
    if overlap:
        issues.append(issue("same_entity_in_work_and_education", "high", prefix, ",".join(sorted(overlap)), "同一实体同时出现在工作和教育列表"))


def validate_payload(path: Path, payload: dict[str, Any], source_index: dict[str, str]) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    structured = payload.get("structured_data") or {}
    resumes = [row for row in (structured.get("resumes") or []) if isinstance(row, dict)]
    if not resumes:
        issues.append(issue("missing_resumes", "critical", "structured_data.resumes", "", "缺少语言简历列表"))
    source_files = [row for row in ((payload.get("source") or {}).get("source_files") or []) if isinstance(row, dict)]
    source_texts = []
    for source in source_files:
        filename = text(source.get("filename") or Path(text(source.get("input_path"))).name)
        if filename.casefold() in source_index:
            source_texts.append(source_index[filename.casefold()])
    source_text = " ".join(source_texts)
    source_norm = compact(source_text)

    primary_base = structured.get("base_info") or {}
    validate_name(primary_base.get("full_name"), "structured_data.base_info.full_name", issues)
    validate_contact(primary_base, "structured_data.base_info", issues)
    semantic_review = ((payload.get("extraction") or {}).get("semantic_review") or {})
    for index, resume in enumerate(resumes):
        validate_resume(resume, index, source_norm, issues, semantic_review)

    zh_rows = [row for row in resumes if language(row) == "zh"]
    primary = zh_rows[0] if zh_rows else (resumes[0] if resumes else {})
    if primary:
        for collection in ("expected_list", "work_experiences", "education_list", "project_list", "training_list", "certificate_list", "language_list", "skills_list", "communication_list"):
            if collection in structured:
                issues.append(issue("forbidden_outer_collection", "critical", f"structured_data.{collection}", "", "经历列表只能位于 resumes[]，外层不得保留查询快照"))
        if compact((primary.get("base_info") or {}).get("full_name")) != compact(primary_base.get("full_name")):
            issues.append(issue("snapshot_name_mismatch", "critical", "structured_data.base_info.full_name", primary_base.get("full_name"), "外层姓名与中文主简历不一致"))

    counts = [(language(row), len(row.get("work_experiences") or []), len(row.get("education_list") or [])) for row in resumes]
    # Independent source resumes may be from different dates and intentionally
    # contain different histories. Count equality is enforced only when all
    # language variants came from the same PDF.
    if counts and len(source_files) <= 1:
        work_counts = [row[1] for row in counts]
        education_counts = [row[2] for row in counts]
        if max(work_counts) - min(work_counts) > 2:
            issues.append(issue("cross_language_work_count_gap", "medium", "structured_data.resumes", counts, "多语言版本工作条数差异超过 2，需结合版本日期复核"))
        if max(education_counts) - min(education_counts) > 3:
            issues.append(issue("cross_language_education_count_gap", "medium", "structured_data.resumes", counts, "多语言版本学历条数差异超过 3，需结合版本日期复核"))
        zh_work = max((row[1] for row in counts if row[0] == "zh"), default=-1)
        zh_education = max((row[2] for row in counts if row[0] == "zh"), default=-1)
        foreign_work = max((row[1] for row in counts if row[0] != "zh"), default=0)
        foreign_education = max((row[2] for row in counts if row[0] != "zh"), default=0)
        if zh_work == 0 and foreign_work >= 2:
            issues.append(issue("chinese_work_missing_vs_foreign", "high", "structured_data.resumes", counts, "中文主版本无工作，但外文版本有多段工作"))
        if zh_education == 0 and foreign_education >= 2:
            issues.append(issue("chinese_education_missing_vs_foreign", "high", "structured_data.resumes", counts, "中文主版本无学历，但外文版本有多段学历"))

    max_work = max((len(row.get("work_experiences") or []) for row in resumes), default=0)
    max_education = max((len(row.get("education_list") or []) for row in resumes), default=0)
    if source_text:
        if max_work == 0 and not semantic_review.get("source_work_absent") and source_has_work_records(source_text):
            issues.append(issue("source_work_section_unparsed", "high", "structured_data.resumes", "", "Word 源文本存在工作章节，但所有语言均未形成工作记录"))
        if max_education == 0 and not semantic_review.get("source_education_absent") and source_has_education_records(source_text):
            issues.append(issue("source_education_section_unparsed", "high", "structured_data.resumes", "", "Word 源文本存在教育章节，但所有语言均未形成教育记录"))
        source_phone = re.sub(r"\D", "", text(primary_base.get("phone")))
        if source_phone and source_phone not in re.sub(r"\D", "", source_text) and not semantic_review.get("pdf_verified_phone"):
            issues.append(issue("phone_not_supported_by_source", "medium", "structured_data.base_info.phone", primary_base.get("phone"), "主手机号未在 Word 源文本中命中"))
        source_email = text(primary_base.get("email")).casefold().replace(" ", "")
        if source_email and source_email not in source_text.casefold().replace(" ", "") and not semantic_review.get("pdf_verified_email"):
            issues.append(issue("email_not_supported_by_source", "medium", "structured_data.base_info.email", primary_base.get("email"), "主邮箱未在 Word 源文本中命中"))

    filename_name = path.stem.split("_", 1)[0]
    if compact(filename_name) != compact(primary_base.get("full_name")) and not semantic_review.get("pdf_verified_name"):
        issues.append(issue("filename_name_mismatch", "medium", "structured_data.base_info.full_name", primary_base.get("full_name"), f"文件名前缀为 {filename_name}"))

    issues.sort(key=lambda row: (-SEVERITY[row["severity"]], row["code"], row["path"]))
    maximum = max((SEVERITY[row["severity"]] for row in issues), default=0)
    max_severity = next((name for name, rank in SEVERITY.items() if rank == maximum), "clean")
    return {
        "json_file": str(path.resolve()),
        "filename": path.name,
        "full_name": text(primary_base.get("full_name")),
        "source_files": [text(row.get("filename") or row.get("input_path")) for row in source_files],
        "max_severity": max_severity,
        "strict_status": "failed" if maximum >= SEVERITY["high"] else ("review" if maximum else "clean"),
        "issue_count": len(issues),
        "issues": issues,
    }


def main() -> int:
    cfg = parse_args()
    mapping = read_json(cfg.map)
    source_index = source_text_index(mapping)
    records: list[dict[str, Any]] = []
    unreadable: list[dict[str, str]] = []
    for path in sorted(cfg.json_root.glob("*.json"), key=lambda item: item.name.casefold()):
        try:
            payload = read_json(path)
            if not isinstance(payload, dict):
                raise TypeError("JSON root is not an object")
        except Exception as exc:
            unreadable.append({"json_file": str(path.resolve()), "error": f"{type(exc).__name__}: {exc}"})
            continue
        records.append(validate_payload(path, payload, source_index))

    issue_code_counts = Counter(row["code"] for record in records for row in record["issues"])
    issue_code_file_counts = Counter(
        code
        for record in records
        for code in {row["code"] for row in record["issues"]}
    )
    issue_severity_counts = Counter(row["severity"] for record in records for row in record["issues"])
    max_severity_file_counts = Counter(record["max_severity"] for record in records)
    status_counts = Counter(record["strict_status"] for record in records)
    report = {
        "version": VERSION,
        "generated_at": datetime.now().astimezone().isoformat(),
        "json_root": str(cfg.json_root.resolve()),
        "json_count": len(records) + len(unreadable),
        "parsed_count": len(records),
        "unreadable_count": len(unreadable),
        "issue_file_count": sum(record["issue_count"] > 0 for record in records) + len(unreadable),
        "clean_file_count": sum(record["issue_count"] == 0 for record in records),
        "strict_failure_file_count": status_counts["failed"] + len(unreadable),
        "snapshot_mismatch_file_count": issue_code_file_counts["snapshot_mismatch"],
        "content_failure_file_count": sum(
            any(
                SEVERITY[row["severity"]] >= SEVERITY["high"]
                and row["code"] not in {"snapshot_mismatch", "snapshot_name_mismatch"}
                for row in record["issues"]
            )
            for record in records
        ) + len(unreadable),
        "review_file_count": status_counts["review"],
        "total_issue_count": sum(issue_code_counts.values()) + len(unreadable),
        "status_counts": dict(status_counts),
        "max_severity_file_counts": dict(max_severity_file_counts),
        "issue_severity_counts": dict(issue_severity_counts),
        "issue_code_counts": dict(issue_code_counts.most_common()),
        "issue_code_file_counts": dict(issue_code_file_counts.most_common()),
        "unreadable": unreadable,
        "records": records,
    }
    atomic_json(cfg.report, report)
    csv_rows = []
    for record in records:
        for row in record["issues"]:
            csv_rows.append({
                "JSON文件": record["filename"],
                "候选人": record["full_name"],
                "严格状态": record["strict_status"],
                "最高严重度": record["max_severity"],
                "严重度": row["severity"],
                "问题代码": row["code"],
                "字段路径": row["path"],
                "问题值": row["value"],
                "说明": row["message"],
                "来源文件": " | ".join(record["source_files"]),
            })
    cfg.csv.parent.mkdir(parents=True, exist_ok=True)
    fields = ["JSON文件", "候选人", "严格状态", "最高严重度", "严重度", "问题代码", "字段路径", "问题值", "说明", "来源文件"]
    with tempfile.NamedTemporaryFile("w", encoding="utf-8-sig", newline="", suffix=".tmp", dir=cfg.csv.parent, delete=False) as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(csv_rows)
        temporary = Path(stream.name)
    temporary.replace(cfg.csv)
    summary = {key: value for key, value in report.items() if key not in {"records", "unreadable", "issue_code_counts", "issue_code_file_counts"}}
    summary["top_issue_codes"] = dict(issue_code_counts.most_common(20))
    summary["top_issue_file_counts"] = dict(issue_code_file_counts.most_common(20))
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"report={cfg.report.resolve()}")
    print(f"csv={cfg.csv.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
