from __future__ import annotations
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1] / "common"))
import rc_config as _rc  # noqa: E402  项目统一配置（python/common/rc_config.py）
# EN: noqa: E402  project-wide configuration (python/common/rc_config.py)
# JA: noqa: E402  プロジェクト共通設定（python/common/rc_config.py）

import argparse
import json
import re
import tempfile
import unicodedata
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup
from pypdf import PdfReader


PROJECT_ROOT = _rc.project_root()
PDF_ROOT = PROJECT_ROOT / _rc.dirname("complete-transfered-htmls") / "pdf"
DEFAULT_REVIEW = PDF_ROOT / "rebuild-reports" / "pdf_gpt_translation_review.v2.json"
DEFAULT_MAP = PDF_ROOT / "rebuild-work" / "pdf_rebuild_map.v2.json"
DEFAULT_REPORT = PDF_ROOT / "rebuild-reports" / "pdf_gpt_four_way_comparison.v2.json"
VERSION = "pdf-gpt-four-way-comparison-v2.0.0"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="对照 PDF、Word、GPT 与候选 JSON 的工作/学历结构" " / Compare the work/education structure of PDF, Word, GPT and the candidate JSON / PDF、Word、GPT、候補者 JSON の職歴／学歴の構造を突き合わせる")
    parser.add_argument("--review", type=Path, default=DEFAULT_REVIEW)
    parser.add_argument("--map", type=Path, default=DEFAULT_MAP)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
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


def compact(value: Any) -> str:
    value = unicodedata.normalize("NFKC", str(value or "")).casefold()
    return re.sub(r"[^0-9a-z\u3400-\u9fff\u3040-\u30ff]", "", value)


def language(resume: dict[str, Any]) -> str:
    value = str(resume.get("resume_language") or resume.get("resume_languge") or "").casefold()
    return {"jp": "ja", "jpn": "ja", "eng": "en"}.get(value, value)


def date_tokens(row: dict[str, Any], collection: str) -> list[str]:
    fields = ("position_start", "position_resigned") if collection == "work_experiences" else ("school_start_ym", "school_end_ym")
    output: list[str] = []
    for field in fields:
        value = unicodedata.normalize("NFKC", str(row.get(field) or ""))
        match = re.search(r"((?:19|20)\d{2})\D{0,3}(\d{1,2})?", value)
        if match:
            output.append(match.group(1) + (f"{int(match.group(2)):02d}" if match.group(2) else ""))
    return output


def evidence_terms(row: dict[str, Any], collection: str) -> list[str]:
    fields = ("company_name", "position", "position_dept") if collection == "work_experiences" else ("school_name", "school_major_name", "school_degree_type")
    terms: list[str] = []
    for field in fields:
        value = compact(row.get(field))
        if len(value) >= 3:
            terms.append(value)
        chunks = re.findall(r"[a-z]{4,}|[\u3400-\u9fff]{2,}", value)
        terms.extend(chunk for chunk in chunks if len(chunk) >= 2)
    return list(dict.fromkeys(terms))


def token_in_text(token: str, normalized_text: str) -> bool:
    if not token:
        return False
    if token in normalized_text:
        return True
    # A YYYYMM token may appear in the source with punctuation or only as YYYY.
    return len(token) == 6 and token[:4] in normalized_text and token[4:] in normalized_text


def row_support(row: dict[str, Any], collection: str, word_text: str, pdf_text: str) -> dict[str, Any]:
    dates = date_tokens(row, collection)
    terms = evidence_terms(row, collection)
    word_norm, pdf_norm = compact(word_text), compact(pdf_text)
    date_word = [token for token in dates if token_in_text(token, word_norm)]
    date_pdf = [token for token in dates if token_in_text(token, pdf_norm)]
    term_word = [token for token in terms if token_in_text(token, word_norm)]
    term_pdf = [token for token in terms if token_in_text(token, pdf_norm)]
    supported = bool(date_word or date_pdf or term_word or term_pdf)
    strong = bool((date_word or date_pdf) and (term_word or term_pdf)) or len(term_word + term_pdf) >= 2
    return {
        "dates": dates,
        "terms": terms,
        "date_hits_word": date_word,
        "date_hits_pdf": date_pdf,
        "term_hits_word": term_word,
        "term_hits_pdf": term_pdf,
        "supported": supported,
        "strong_support": strong,
    }


def row_summary(row: dict[str, Any], collection: str) -> dict[str, Any]:
    if collection == "work_experiences":
        fields = ("position_start", "position_resigned", "company_name", "position")
    else:
        fields = ("school_start_ym", "school_end_ym", "school_name", "school_major_name", "school_degree_type")
    return {field: row.get(field, "") for field in fields}


def semantic_issues(row: dict[str, Any], collection: str) -> list[str]:
    issues: list[str] = []
    if collection == "work_experiences":
        company = str(row.get("company_name") or "").strip()
        if not company:
            issues.append("missing_company")
        if re.search(r"\bproject\b|プロジェクト|项目", company, re.I) and not re.search(r"公司|会社|company|co[., ]|ltd", company, re.I):
            issues.append("project_misclassified_as_employer")
        if len(company) > 140:
            issues.append("company_text_too_long")
    else:
        school = str(row.get("school_name") or "").strip()
        if not school:
            issues.append("missing_school")
        if school and not re.search(r"大学|学院|学校|高校|中学|University|College|School|Institute|Academy|Université|Universität", school, re.I):
            issues.append("school_name_not_educational_institution")
        if re.search(r"Scholarship|奖学金|制作|会社|公司|自己|Project", school, re.I):
            issues.append("non_education_text_misclassified")
    return issues


def resume_rows(payload: dict[str, Any], lang: str, collection: str) -> list[dict[str, Any]]:
    resumes = [row for row in ((payload.get("structured_data") or {}).get("resumes") or []) if isinstance(row, dict) and language(row) == lang]
    if not resumes:
        return []
    selected = max(resumes, key=lambda row: len(row.get(collection) or []))
    return [row for row in (selected.get(collection) or []) if isinstance(row, dict)]


def pdf_text(path: Path) -> tuple[str, list[int]]:
    reader = PdfReader(path)
    texts = [(page.extract_text() or "") for page in reader.pages]
    return "\n".join(texts), [len(compact(value)) for value in texts]


def main() -> int:
    cfg = parse_args()
    review = read_json(cfg.review)
    mapping = read_json(cfg.map)
    by_filename = {row["input_filename"]: row for row in mapping.get("records") or []}
    results: list[dict[str, Any]] = []
    status_counts: Counter[str] = Counter()
    for review_row in review.get("records") or []:
        gpt_path = Path(str(review_row.get("gpt_json") or "").removeprefix("gpt_reference:"))
        candidate_path = Path(review_row["candidate_json"])
        gpt = read_json(gpt_path)
        candidate = read_json(candidate_path)
        source_rows = []
        all_word_text: list[str] = []
        all_pdf_text: list[str] = []
        for filename in review_row.get("input_files") or []:
            map_row = by_filename[filename]
            html_path = Path((map_row.get("processing") or {}).get("html_path") or "")
            html_text = ""
            if html_path.is_file():
                html_text = BeautifulSoup(html_path.read_text(encoding="utf-8", errors="replace"), "html.parser").get_text("\n", strip=True)
            current_pdf_text, page_chars = pdf_text(Path(map_row["input_path"]))
            all_word_text.append(html_text)
            all_pdf_text.append(current_pdf_text)
            source_rows.append({
                "pdf": map_row["input_path"],
                "word": map_row.get("word_path", ""),
                "html": str(html_path),
                "pdf_page_count": map_row.get("pdf_profile", {}).get("page_count", 0),
                "pdf_page_text_chars": page_chars,
                "word_text_chars": len(compact(html_text)),
            })
        word_text = "\n".join(all_word_text)
        original_pdf_text = "\n".join(all_pdf_text)
        collections: dict[str, Any] = {}
        unsupported_total = 0
        weak_total = 0
        semantic_issue_total = 0
        for collection in ("work_experiences", "education_list"):
            gpt_zh = resume_rows(gpt, "zh", collection)
            gpt_foreign_by_language = {
                lang: resume_rows(gpt, lang, collection)
                for lang in ("ja", "en", "de")
                if resume_rows(gpt, lang, collection)
            }
            candidate_zh = resume_rows(candidate, "zh", collection)
            candidate_foreign_by_language = {
                lang: resume_rows(candidate, lang, collection)
                for lang in ("ja", "en", "de")
                if resume_rows(candidate, lang, collection)
            }
            supported_rows = []
            lifecycle_keys: Counter[str] = Counter()
            for row in gpt_zh:
                support = row_support(row, collection, word_text, original_pdf_text)
                row_semantic_issues = semantic_issues(row, collection)
                unsupported_total += int(not support["supported"])
                weak_total += int(support["supported"] and not support["strong_support"])
                semantic_issue_total += len(row_semantic_issues)
                supported_rows.append({"row": row_summary(row, collection), "support": support, "semantic_issues": row_semantic_issues})
                if collection == "education_list":
                    lifecycle_key = compact(re.sub(r"入学|卒業|毕业|畢業|修了|结业|結業", "", str(row.get("school_name") or "")))
                    if lifecycle_key:
                        lifecycle_keys[lifecycle_key] += 1
            lifecycle_duplicates = [key for key, count in lifecycle_keys.items() if count > 1]
            semantic_issue_total += len(lifecycle_duplicates)
            collections[collection] = {
                "counts": {
                    "gpt_zh": len(gpt_zh),
                    "gpt_foreign": {key: len(value) for key, value in gpt_foreign_by_language.items()},
                    "candidate_zh": len(candidate_zh),
                    "candidate_foreign": {key: len(value) for key, value in candidate_foreign_by_language.items()},
                },
                "gpt_zh_rows": supported_rows,
                "gpt_foreign_rows": {key: [row_summary(row, collection) for row in value] for key, value in gpt_foreign_by_language.items()},
                "candidate_foreign_rows": {key: [row_summary(row, collection) for row in value] for key, value in candidate_foreign_by_language.items()},
                "split_school_lifecycle_keys": lifecycle_duplicates,
            }
        if unsupported_total or semantic_issue_total:
            status = "visual_review_required"
        elif weak_total:
            status = "supported_with_weak_rows"
        else:
            status = "source_supported"
        status_counts[status] += 1
        results.append({
            "candidate_name": review_row["candidate_name"],
            "status": status,
            "unsupported_gpt_zh_rows": unsupported_total,
            "weak_gpt_zh_rows": weak_total,
            "semantic_issue_count": semantic_issue_total,
            "gpt_json": str(gpt_path),
            "candidate_json": str(candidate_path),
            "sources": source_rows,
            "collections": collections,
        })
    report = {
        "version": VERSION,
        "generated_at": datetime.now().astimezone().isoformat(),
        "total": len(results),
        "status_counts": dict(status_counts),
        "records": results,
    }
    atomic_json(cfg.report, report)
    print(json.dumps({key: value for key, value in report.items() if key != "records"}, ensure_ascii=False, indent=2))
    print(f"report={cfg.report.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
