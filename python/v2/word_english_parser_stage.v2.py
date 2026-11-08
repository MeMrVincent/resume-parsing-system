"""筛选英文解析结果：排除图片型猎聘，并阻止有工作/教育标题却解析为空的 JSON。

EN: Filter English parse results: exclude image-based Liepin files, and block JSON that parsed empty despite having work/education headings.

JA: 英語の解析結果を絞り込む：画像形式の Liepin を除外し、職歴・学歴の見出しがあるのに空として解析された JSON を阻止する。
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import re
from pathlib import Path

from bs4 import BeautifulSoup


def key(value: object) -> str:
    return os.path.normcase(os.path.normpath(str(value or "")))


def visible_text(path: Path) -> str:
    soup = BeautifulSoup(path.read_text(encoding="utf-8", errors="replace"), "html.parser")
    for node in soup(["style", "script", "head", "meta", "link"]):
        node.decompose()
    return soup.get_text(" ", strip=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json-dir", type=Path, required=True)
    parser.add_argument("--map", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    rows = json.loads(args.map.read_text(encoding="utf-8"))
    by_source = {key(row.get("source_path")): row for row in rows}
    args.output_dir.mkdir(parents=True, exist_ok=True)
    results = []
    invalid_name = re.compile(
        r"(?:\b(?:sex|male|female|resume|cv|cfo|sh)\b|工程师|程序员|经理|主管|专员|助理|财务|会计|策划|文案|信贷|出纳|薪酬|高级工程|女士葛$)", re.I
    )
    for path in args.json_dir.glob("*.json"):
        if path.name.startswith("_"):
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        source_path = str((payload.get("source") or {}).get("original_path") or "")
        row = by_source.get(key(source_path), {})
        html_path = Path(str(row.get("html_path") or ""))
        result = {"source_path": source_path, "json_path": str(path), "html_path": str(html_path)}
        if "猎聘" in html_path.name or "猎聘" in source_path:
            result["status"] = "image_liepin_deferred"
            results.append(result)
            continue
        if not html_path.is_file():
            result["status"] = "missing_html"
            results.append(result)
            continue
        text = visible_text(html_path)
        structured = payload.get("structured_data") or {}
        name = str((structured.get("base_info") or {}).get("full_name") or "").strip()
        if invalid_name.search(name) or not name:
            result.update(status="invalid_name", name=name)
            results.append(result)
            continue
        resumes = structured.get("resumes") or []
        en_resume = next((resume for resume in resumes if str(resume.get("resume_language") or "").casefold() == "en"), None)
        chosen = en_resume or (resumes[0] if resumes else {})
        work_count = len(chosen.get("work_experiences") or [])
        education_count = len(chosen.get("education_list") or [])
        has_work_heading = bool(re.search(r"\b(?:work|professional|employment|career)\s+(?:experience|history)|Berufserfahrung\b", text, re.I))
        has_education_heading = bool(re.search(r"\b(?:education|academic background|educational background|qualification)s?\b", text, re.I))
        issues = []
        if has_work_heading and work_count == 0:
            issues.append("work_heading_but_empty")
        if has_education_heading and education_count == 0:
            issues.append("education_heading_but_empty")
        if issues:
            result.update(status="incomplete", issues=issues, work_count=work_count, education_count=education_count)
            results.append(result)
            continue
        staged = copy.deepcopy(payload)
        selected = copy.deepcopy(chosen)
        selected["resume_language"] = "en"
        staged["structured_data"]["resumes"] = [selected]
        staged["structured_data"]["base_info"] = copy.deepcopy(selected.get("base_info") or structured.get("base_info") or {})
        source = staged.setdefault("source", {})
        source["converter"] = "run_english_html_to_json.py"
        source["actual_resume_languages"] = ["en"]
        source["note"] = (str(source.get("note") or "") + " 已通过英文工作/教育标题完整性检查。").strip()
        target = args.output_dir / path.name
        target.write_text(json.dumps(staged, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        result.update(status="staged", output_json=str(target), work_count=work_count, education_count=education_count)
        results.append(result)
    report = {"summary": {}, "items": results}
    for row in results:
        status = row["status"]
        report["summary"][status] = report["summary"].get(status, 0) + 1
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False))


if __name__ == "__main__":
    main()
