"""按正文语言段证据筛选通用解析结果；缺少真实语言段的结果不进入审计。

EN: Filter generic parse results by evidence of language sections in the body; results lacking a real language section do not enter the audit.

JA: 本文の言語の段落の証拠で汎用の解析結果を絞り込む。実際の言語の段落がない結果は監査に入れない。
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


def language_signals(html_path: Path) -> tuple[set[str], dict[str, int]]:
    soup = BeautifulSoup(html_path.read_text(encoding="utf-8", errors="replace"), "html.parser")
    content = soup.select_one('main[data-role="document-content"]') or soup.body or soup
    text = content.get_text(" ", strip=True)
    kana = len(re.findall(r"[\u3040-\u30ff]", text))
    han = len(re.findall(r"[\u3400-\u9fff]", text))
    latin_words = len(re.findall(r"\b[A-Za-z]{4,}\b", text))
    zh_headings = len(re.findall(r"个人(?:简历|资料|信息)|中文简历|工作经历|教育经历|自我评价|求职意向", text, re.I))
    jp_headings = len(re.findall(r"履歴書|職務経歴書|学歴|職歴|自己\s*PR|志望動機", text, re.I))
    en_headings = len(re.findall(r"PERSONAL\s+RESUME|CURRICULUM\s+VITAE|WORK\s+EXPERIENCE|EDUCATION|CAREER\s+OBJECTIVE|SELF\s+(?:ASSESSMENT|EVALUATION)", text, re.I))
    signals: set[str] = set()
    if zh_headings >= 2 or (han >= 250 and kana < 25):
        signals.add("zh")
    if jp_headings >= 1 and kana >= 35 or kana >= 140:
        signals.add("jp")
    if en_headings >= 2 and latin_words >= 60:
        signals.add("en")
    if not signals:
        signals.add("zh")
    return signals, {
        "kana": kana, "han": han, "latin_words": latin_words,
        "zh_headings": zh_headings, "jp_headings": jp_headings, "en_headings": en_headings,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--parser-json-dir", type=Path, required=True)
    parser.add_argument("--map", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    rows = json.loads(args.map.read_text(encoding="utf-8"))
    by_source = {key(row.get("source_path")): row for row in rows}
    args.output_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for path in args.parser_json_dir.glob("*.json"):
        if path.name.startswith("_"):
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        source_path = str((payload.get("source") or {}).get("original_path") or "")
        row = by_source.get(key(source_path), {})
        html_path = Path(str(row.get("html_path") or ""))
        result = {"source_path": source_path, "parser_json": str(path), "html_path": str(html_path)}
        if not html_path.is_file():
            result["status"] = "missing_html"
            results.append(result)
            continue
        signals, evidence = language_signals(html_path)
        resumes = (payload.get("structured_data") or {}).get("resumes") or []
        parsed_languages = {
            str(resume.get("resume_language") or resume.get("resume_languge") or "").casefold()
            for resume in resumes
        }
        missing = sorted(signals - parsed_languages)
        result.update(language_signals=sorted(signals), parsed_languages=sorted(parsed_languages), evidence=evidence)
        if missing:
            result.update(status="missing_detected_language", missing=missing)
            results.append(result)
            continue
        staged = copy.deepcopy(payload)
        staged["structured_data"]["resumes"] = [
            resume for resume in resumes
            if str(resume.get("resume_language") or resume.get("resume_languge") or "").casefold() in signals
        ]
        source = staged.setdefault("source", {})
        source["converter"] = "run_chinese_english_japanese_html_to_json.py"
        source["actual_resume_languages"] = sorted(signals)
        source["note"] = (str(source.get("note") or "") + " 已按当前 HTML 的独立语言段标题与字符证据保留真实语言版本。").strip()
        target = args.output_dir / path.name
        target.write_text(json.dumps(staged, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        result.update(status="staged", output_json=str(target))
        results.append(result)

    report = {
        "staged": sum(row.get("status") == "staged" for row in results),
        "not_staged": sum(row.get("status") != "staged" for row in results),
        "items": results,
    }
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key != "items"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
