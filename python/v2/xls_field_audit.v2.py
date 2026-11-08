"""Strict field-by-field DOM -> JSON audit for the XLS batch."""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path

from bs4 import BeautifulSoup

from process_word_html_to_json import normalize_name

SKIP_FIELDS = {
    "education_degree", "resume_index", "candidate_key", "sequence_no",
}
DERIVED_FIELDS = {
    "birth_year", "city", "platform_from", "platform_resume_id",
    "status", "employment_type", "certificate_type", "school_education_type",
    "language_certificate", "language_certificate_time",
}
HEADER_RE = re.compile(r"(?:姓名|氏名|学校名|学校名称|专业|専攻|学历|学歴|时间|期間|公司名称|会社名|取得年|取得年月|资格证书|資格/証書|技能资格|ソフト名)")
LANGUAGE_CANONICAL = {
    "日本語": "日语", "日语": "日语", "japanese": "日语",
    "英語": "英语", "英语": "英语", "english": "英语",
    "中国語": "中文", "中文": "中文", "chinese": "中文",
}


def flat(value: object) -> str:
    text = re.sub(r"\s+", "", str(value or "")).casefold()
    return re.sub(r"[^0-9a-z\u3400-\u9fff\u3040-\u30ff\uac00-\ud7a3]", "", text)


def date_flat(value: object) -> str:
    text = str(value or "")
    m = re.search(r"((?:19|20)\d{2})\D{0,3}(\d{1,2})?", text)
    if not m:
        return ""
    return f"{m.group(1)}{int(m.group(2) or 1):02d}"


def equivalent(field: str, left: object, right: object) -> bool:
    if field == "language_name":
        left = LANGUAGE_CANONICAL.get(str(left).strip(), str(left).strip())
        right = LANGUAGE_CANONICAL.get(str(right).strip(), str(right).strip())
    if field.endswith("_ym") or field in {"position_start", "position_resigned", "birth_date", "certificate_time"}:
        ld, rd = date_flat(left), date_flat(right)
        if ld and rd and ld == rd:
            return True
    a, b = flat(left), flat(right)
    return bool(a and b and (a == b or a in b or b in a))


def dom_fields(soup: BeautifulSoup) -> dict[str, dict[str, list[str]]]:
    result: dict[str, dict[str, list[str]]] = {}
    for section in soup.find_all("section"):
        code = str(section.get("data-language-code") or section.get("data-language") or "").casefold()
        if not code:
            continue
        bucket = result.setdefault("jp" if code == "ja" else code, {})
        for node in section.find_all(attrs={"data-field": True}):
            field = str(node.get("data-field") or "")
            if not field or field in SKIP_FIELDS:
                continue
            if node.find(attrs={"data-field": True}):
                continue
            value = node.get_text(" ", strip=True)
            if not value or HEADER_RE.fullmatch(value.strip()):
                continue
            if value.strip().endswith((":", "：")):
                continue
            bucket.setdefault(field, []).append(value)
    return result


def json_fields(resume: dict) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    base = resume.get("base_info") or {}
    for field, value in base.items():
        if field in SKIP_FIELDS or field in DERIVED_FIELDS:
            continue
        if str(value or "").strip():
            out.setdefault(field, []).append(str(value))
    for collection in (
        "expected_list", "work_experiences", "education_list", "certificate_list",
        "language_list", "skills_list", "training_list", "project_list", "communication_list",
    ):
        for row in resume.get(collection) or []:
            for field, value in row.items():
                if field in SKIP_FIELDS or not str(value or "").strip():
                    continue
                out.setdefault(field, []).append(str(value))
    return out


def strict_semantic_checks(soup: BeautifulSoup, payload: dict, row: dict, item: dict) -> list[str]:
    """Checks that cannot be established by a flat value comparison."""
    issues: list[str] = []
    structured = payload.get("structured_data") or {}
    resumes = structured.get("resumes") or []
    main = soup.find("main", attrs={"data-role": "document-content"}) or soup
    body_text = main.get_text(" ", strip=True)
    # A usable resume must have an applicant contact in the body.  The source
    # metadata header is intentionally excluded because it may be an agency.
    contacts = []
    for resume in resumes:
        base = resume.get("base_info") or {}
        phone = str(base.get("phone") or "").strip()
        email = str(base.get("email") or "").strip()
        if phone or email:
            contacts.append((phone, email))
            if phone and re.sub(r"\D", "", phone) not in re.sub(r"\D", "", body_text):
                issues.append("personal_contact_not_in_dom:phone")
            if email and email.replace(" ", "").casefold() not in body_text.replace(" ", "").casefold():
                issues.append("personal_contact_not_in_dom:email")
    if resumes and not contacts:
        issues.append("contact_missing_personal")

    # Address must not contain the following profile labels; this catches the
    # common horizontal-row bleed where address absorbs age/nationality/etc.
    contamination = re.compile(r"(?:年龄|年齢|最终学历|最終学歴|国籍|民族|勤务状况|勤務状況|户籍|戸籍|婚姻状况|婚姻状況|电话|電話|邮箱|メール)")
    for resume in resumes:
        base = resume.get("base_info") or {}
        for field in ("address", "household_registration", "city", "nationality"):
            value = str(base.get(field) or "")
            if contamination.search(value):
                issues.append(f"profile_contamination:{field}")

        certs = {flat(x.get("certificate_name")) for x in resume.get("certificate_list") or [] if x.get("certificate_name")}
        skills = {flat(x.get("skill_name")) for x in resume.get("skills_list") or [] if x.get("skill_name")}
        overlap = certs & skills
        if overlap:
            issues.append("skill_certificate_overlap")
        for cert in resume.get("certificate_list") or []:
            name = str(cert.get("certificate_name") or "")
            if re.fullmatch(r"(?i)(word|excel|powerpoint|photoshop|illustrator|autocad|solidworks)", name.strip()):
                issues.append("skill_as_certificate")

        pr = str((resume.get("base_info") or {}).get("pr") or "")
        if pr and re.search(r"(?:技能资格|资格证书|希望职种|履歴書|学历|教育经历)\s*$", pr.strip()):
            issues.append("pr_is_heading_only")

    # Every language variant in JSON must have a corresponding core DOM layer;
    # otherwise it is a synthetic bilingual record.
    active = set()
    for section in soup.find_all("section"):
        code = str(section.get("data-language-code") or section.get("data-language") or "").casefold()
        kind = str(section.get("data-section-type") or section.get("data-collection") or "").casefold()
        if code == "ja":
            code = "jp"
        if code in {"zh", "jp", "en"} and kind in {
            "document-body", "base_info", "education_list", "work_experiences",
            "expected_list", "self_evaluation",
        }:
            active.add(code)
    for resume in resumes:
        code = str(resume.get("resume_languge") or resume.get("resume_language") or "").casefold()
        if code == "ja":
            code = "jp"
        if code and code not in active:
            issues.append(f"language_variant_without_core_dom:{code}")

    # Provenance must remain traceable for later source/html/json comparison.
    source_meta = payload.get("source") or {}
    if row.get("source_path") and str(source_meta.get("original_path") or "").casefold() != str(row.get("source_path") or "").casefold():
        issues.append("source_path_mismatch")
    if row.get("download_date") and str(source_meta.get("source_landing_time") or "") != str(row.get("download_date") or ""):
        issues.append("source_landing_time_mismatch")
    return list(dict.fromkeys(issues))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--map", type=Path, required=True)
    ap.add_argument("--report", type=Path, required=True)
    ap.add_argument("--output", type=Path, default=None)
    args = ap.parse_args()
    rows = json.loads(args.map.read_text(encoding="utf-8"))
    report = json.loads(args.report.read_text(encoding="utf-8"))
    by_source = {str(item.get("source_path")): item for item in report.get("items", [])}
    counts: Counter[str] = Counter()
    field_counts: Counter[str] = Counter()
    file_counts: Counter[str] = Counter()
    examples: dict[str, list[str]] = {}
    field_examples: dict[str, list[str]] = {}

    def add(kind: str, path: str, detail: str) -> None:
        counts[kind] += 1
        field = detail.split(":", 2)[1] if detail.count(":") >= 2 else ""
        if field:
            field_counts[f"{kind}:{field}"] += 1
        file_counts[f"{kind}:{Path(path).name}"] += 1
        if len(examples.setdefault(kind, [])) < 10:
            examples[kind].append(f"{path}: {detail}")
        field = detail.split(":", 2)[1] if detail.count(":") >= 2 else ""
        if field and len(field_examples.setdefault(f"{kind}:{field}", [])) < 12:
            field_examples[f"{kind}:{field}"].append(f"{path}: {detail}")

    for row in rows:
        item = by_source.get(str(row.get("source_path"))) or {}
        hp = Path(str(item.get("html_path") or ""))
        jp = Path(str(item.get("output_path") or ""))
        if not hp.is_file() or not jp.is_file():
            if item.get("status") == "not_resume":
                add("rejected_without_contact", str(row.get("source_path")), "no_personal_phone_or_email")
            else:
                add("artifact_missing", str(row.get("source_path")), "html/json")
            continue
        soup = BeautifulSoup(hp.read_text(encoding="utf-8", errors="replace"), "html.parser")
        payload = json.loads(jp.read_text(encoding="utf-8"))
        dom = dom_fields(soup)
        resumes = (payload.get("structured_data") or {}).get("resumes") or []
        for check in strict_semantic_checks(soup, payload, row, item):
            add("strict_check", str(jp), check)
        json_by_code = {str(r.get("resume_languge") or r.get("resume_language") or "").casefold(): json_fields(r) for r in resumes}
        common_fields: dict[str, list[str]] = {}
        for fields in json_by_code.values():
            for field, values in fields.items():
                if field in {"full_name", "phone", "email", "birth_date", "gender", "age", "marital_status", "nationality", "address", "household_registration", "language_name", "language_level", "company_employees"}:
                    common_fields.setdefault(field, []).extend(values)
        for code, fields in dom.items():
            target = {field: list(values) for field, values in json_by_code.get(code, {}).items()}
            for field, values in common_fields.items():
                target.setdefault(field, []).extend(values)
            for field, values in fields.items():
                for value in values:
                    if not any(equivalent(field, value, candidate) for candidate in target.get(field, [])):
                        add("dom_value_missing_in_json", str(jp), f"{code}:{field}:{value[:80]}")
        for code, fields in json_by_code.items():
            if not code:
                continue
            source_fields = {field: list(values) for field, values in dom.get(code, {}).items()}
            for field, values in common_fields.items():
                source_fields.setdefault(field, []).extend(values)
            for field, values in fields.items():
                if field in DERIVED_FIELDS:
                    continue
                for value in values:
                    # Long raw descriptions and PR text must have an explicit
                    # DOM node; short scalar values are checked as well.
                    if not any(equivalent(field, value, candidate) for candidate in source_fields.get(field, [])):
                        add("json_value_missing_in_dom", str(jp), f"{code}:{field}:{value[:80]}")
    result = {"total": len(rows), "counts": counts, "field_counts": field_counts.most_common(), "file_counts": file_counts.most_common(30), "examples": examples, "field_examples": field_examples}
    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if not counts else 2


if __name__ == "__main__":
    raise SystemExit(main())
