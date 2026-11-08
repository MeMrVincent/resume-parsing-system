"""Audit the XLS source -> semantic HTML -> JSON chain for the 100-row batch."""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path

from bs4 import BeautifulSoup

from process_word_html_to_json import source_hash


DATE_TOKEN = re.compile(
    r"(?:19|20)\d{2}\s*(?:[./-]\s*\d{1,2}(?:\s*[./-]\s*\d{1,2}(?!\d))?|年\s*\d{1,2}\s*月?)"
)
CERT_HEADER = re.compile(r"^(?:取得年月|取得年/月|資格名|证书名称?|证书时间|发证时间)$")
CHECK_FIELDS = {
    "company_name", "position_start", "position_resigned", "school_name",
    "school_start_ym", "school_end_ym",
}


def norm(value: object) -> str:
    return re.sub(r"\s+", "", str(value or "")).strip()


def compact(value: object) -> str:
    return re.sub(r"[^\w\u3400-\u9fff\u3040-\u30ff]", "", str(value or "")).casefold()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--map", type=Path, required=True)
    ap.add_argument("--report", type=Path, required=True)
    ap.add_argument("--semantic", action="store_true", help="also run conservative value-presence checks")
    args = ap.parse_args()
    rows = json.loads(args.map.read_text(encoding="utf-8"))
    report = json.loads(args.report.read_text(encoding="utf-8"))
    by_source = {str(item.get("source_path")): item for item in report.get("items", [])}
    counts: Counter[str] = Counter()
    examples: dict[str, list[str]] = {}

    def add(kind: str, item: dict, detail: str = "") -> None:
        counts[kind] += 1
        if detail and len(examples.setdefault(kind, [])) < 5:
            examples[kind].append(f"{item.get('output_path')}: {detail}")

    for row in rows:
        item = by_source.get(str(row.get("source_path")))
        if not item:
            add("missing_report", row)
            continue
        source = Path(str(row.get("source_path") or ""))
        html_path = Path(str(item.get("html_path") or ""))
        json_path = Path(str(item.get("output_path") or ""))
        if not source.is_file():
            add("source_missing", item)
            continue
        if not html_path.is_file():
            if item.get("status") == "not_resume":
                continue
            add("html_missing", item)
            continue
        if not json_path.is_file():
            add("json_missing", item)
            continue
        soup = BeautifulSoup(html_path.read_text(encoding="utf-8", errors="replace"), "html.parser")
        if soup.find("section", attrs={"data-collection": "training_list"}):
            add("nonformal_training_dom", item)
        for section in soup.find_all("section", attrs={"data-collection": "education_list"}):
            for node in section.find_all("tr"):
                text_value = node.get_text(" ", strip=True)
                if re.search(r"实习经历|实习经验|兼职|兼職|社团|社團|学生会|學生會|校内社团|社会实践|活動名|社團", text_value):
                    add("nonformal_education_dom", item, text_value[:80])
        article = soup.find("article", attrs={"data-source-hash": True})
        if not article or str(article.get("data-source-hash")) != source_hash(source):
            add("source_hash_mismatch", item)
        payload = json.loads(json_path.read_text(encoding="utf-8"))
        structured = payload.get("structured_data") or {}
        for resume in structured.get("resumes") or []:
            code = str(resume.get("resume_languge") or resume.get("resume_language") or "").casefold()
            json_text = compact(json.dumps(structured, ensure_ascii=False))
            works = resume.get("work_experiences") or []
            fingerprints = [
                (norm(w.get("company_name")), norm(w.get("position_start")),
                 norm(w.get("position_resigned")), norm(w.get("position_responsibilities")))
                for w in works
            ]
            if len(fingerprints) != len(set(fingerprints)):
                add("duplicate_work_json", item, code)
            sections = [
                section for section in soup.find_all("section")
                if str(section.get("data-language-code") or section.get("data-language") or "").casefold() == code
                and str(section.get("data-section-type") or section.get("data-collection") or "").casefold() in {"work_experiences", "training_list"}
            ]
            for section in sections:
                for row_node in section.find_all("tr"):
                    text = row_node.get_text(" ", strip=True)
                    if row_node.get("data-record-type") != "work_experience" or not DATE_TOKEN.search(text):
                        continue
                    fields = {str(n.get("data-field")) for n in row_node.find_all(attrs={"data-field": True})}
                    if not ({"position_start", "position_resigned"} & fields) and not re.search(r"(?:工作内容|工作描述|仕事内容|職務内容|業務内容)", text):
                        add("work_date_unbound", item, text[:80])
                    if any(token in text for token in ("公司", "有限公司", "株式会社", "有限会社", "会社")) and "company_name" not in fields:
                        # In expanded work tables the company cell is in the
                        # preceding header row of the same record tbody.
                        parent_rows = row_node.find_parent("tbody")
                        prior_has_company = False
                        if parent_rows is not None:
                            prior_rows = parent_rows.find_all("tr")
                            try:
                                current_index = prior_rows.index(row_node)
                            except ValueError:
                                current_index = 0
                            prior_has_company = any(r.find(attrs={"data-field": "company_name"}) for r in prior_rows[:current_index])
                        if not prior_has_company:
                            add("work_company_unbound", item, text[:80])
            for section in soup.find_all("section", attrs={"data-collection": "education_list"}):
                if str(section.get("data-language-code") or section.get("data-language") or "").casefold() != code:
                    continue
                for row_node in section.find_all("tr"):
                    fields = {str(n.get("data-field")) for n in row_node.find_all(attrs={"data-field": True})}
                    if "school_name" in fields and not ({"school_start_ym", "school_end_ym"} & fields) and not re.search(r"(?:学校|学校名|学校名称|时间|期間|時期|卒業状況|毕业情况)", row_node.get_text(" ", strip=True)):
                        add("education_date_unbound", item, row_node.get_text(" ", strip=True)[:80])
            if not args.semantic:
                continue
            for section in soup.find_all("section"):
                section_code = str(section.get("data-language-code") or section.get("data-language") or "").casefold()
                if section_code != code:
                    continue
                for node in section.find_all(attrs={"data-field": True}):
                    field = str(node.get("data-field") or "")
                    value = node.get_text(" ", strip=True)
                    if field not in CHECK_FIELDS or len(compact(value)) < 2:
                        continue
                    needle = compact(value)
                    if needle not in json_text and not (re.sub(r"\D", "", value) and re.sub(r"\D", "", value) in json_text):
                        add("semantic_value_missing", item, f"{code}:{field}:{value[:60]}")
            for work in works:
                company = norm(work.get("company_name"))
                if company and CERT_HEADER.match(company):
                    add("work_company_header", item, company)
        for resume in structured.get("resumes") or []:
            for cert in resume.get("certificate_list") or []:
                for key in ("certificate_name", "certificate_time"):
                    value = str(cert.get(key) or "").strip()
                    if CERT_HEADER.match(value):
                        add("certificate_header_value", item, value)
        if not payload.get("raw_text"):
            add("raw_text_missing", item)
    print(json.dumps({"total": len(rows), "counts": counts, "examples": examples}, ensure_ascii=False, indent=2))
    return 0 if not any(counts.get(k) for k in ("missing_report", "source_missing", "html_missing", "json_missing", "source_hash_mismatch", "duplicate_work_json", "work_date_unbound", "work_company_unbound", "work_company_header", "certificate_header_value", "raw_text_missing")) else 2


if __name__ == "__main__":
    raise SystemExit(main())
