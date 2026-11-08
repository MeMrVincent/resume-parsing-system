"""以源 Word、语义 HTML 双重证据审计多语言暂存 JSON。

EN: Audit staged multilingual JSON with double evidence from the source Word file and the semantic HTML.

JA: 元の Word とセマンティック HTML の二重の証拠で、多言語の一時 JSON を監査する。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup

from audit_chinese_json_against_sources import EMAIL_RE, read_source_lines


MOBILE_RE = re.compile(r"(?<!\d)(?:\+?86[- ]?)?(1[3-9]\d{9})(?!\d)")
LANGUAGE_REQUIREMENTS = {
    "日文": {"jp"},
    "英文": {"en"},
    "中日文": {"zh", "jp"},
    "中英文": {"zh", "en"},
    "中英日文": {"zh", "en", "jp"},
    "英日文": {"zh", "en", "jp"},
    "中法文": {"zh", "fr"},
    "中英法文": {"zh", "en", "fr"},
    "德文": {"de"},
}
TRADITIONAL_EQUIVALENTS = str.maketrans({
    "衛": "卫", "華": "华", "聞": "闻", "謝": "谢", "燁": "烨",
    "陳": "陈", "鳴": "鸣", "潔": "洁", "張": "张", "孫": "孙",
    "楊": "杨", "駿": "骏", "親": "亲", "趙": "赵", "薇": "薇",
    "麗": "丽", "呉": "吴", "瓊": "琼", "啓": "启", "龍": "龙",
    "靜": "静", "魯": "鲁", "鵬": "鹏", "鐘": "钟", "遊": "游",
    "漢": "汉", "曉": "晓", "暁": "晓", "劉": "刘", "億": "忆",
    "陸": "陆", "関": "关", "瑩": "莹", "艷": "艳", "穎": "颖",
    "鄔": "邬", "劍": "剑", "飛": "飞", "國": "国", "譽": "誉",
    "學": "学", "歴": "历", "職": "职", "會": "会", "電": "电",
    "語": "语", "斉": "齐", "齊": "齐", "偉": "伟", "長": "长",
})


def path_key(value: str) -> str:
    return os.path.normcase(os.path.normpath(str(value or "")))


def compact(value: Any) -> str:
    normalized = unicodedata.normalize("NFKC", str(value or "")).translate(TRADITIONAL_EQUIVALENTS).casefold()
    return re.sub(r"[^\w\u3040-\u30ff\u3400-\u9fff]+", "", normalized, flags=re.UNICODE)


def evidenced(value: Any, text: str) -> bool:
    needle = compact(value)
    haystack = compact(text)
    if not needle:
        return True
    if needle in haystack:
        return True
    if len(needle) >= 12 and (needle[:10] in haystack or needle[-10:] in haystack):
        return True
    latin_tokens = re.findall(r"[a-z0-9]{4,}", str(value or "").casefold())
    return len(latin_tokens) >= 2 and sum(token in haystack for token in latin_tokens) >= min(2, len(latin_tokens))


def identity_evidenced(name: str, text: str, source_path: str) -> bool:
    if evidenced(name, text):
        return True
    tokens = re.findall(r"[a-z]{2,}|[\u3400-\u9fff]{2,}", name.casefold())
    target = compact(text)
    return bool(tokens) and all(compact(token) in target for token in tokens[:3])


def invalid_name_semantics(name: str) -> bool:
    value = re.sub(r"\s+", "", str(name or ""))
    if not value or len(re.findall(r"[\u3400-\u9fff]", value)) == 1 or value.endswith(("表", "性", "的")):
        return True
    return bool(re.search(
        r"履歴|简历|日文|日语|日本語|個人情報|基本情報|氏名|姓名|名前|公司|全称|全稱|通勤時間|連絡先|現住所|生年月日|"
        r"学歴|職歴|希望|資格|電話|携帯|メール|勤務|本人|配偶者|扶養|以上|現在|関係|关系|"
        r"新区|自治區|自治区|行政区|开发区|開発区|市辖区|市轄區",
        value,
        re.I,
    ))


def semantic_html_names(html_path: Path) -> set[str]:
    """读取生成器已标注的姓名节点；用于阻止父目录/地址/学历污染身份。

    EN: Read the name node already tagged by the generator; used to stop parent directories/addresses/degrees from polluting identity.

    JA: 生成器がタグ付けした氏名ノードを読む。親ディレクトリ・住所・学歴が本人情報を汚染するのを防ぐため。
    """
    if not html_path.is_file():
        return set()
    try:
        soup = BeautifulSoup(html_path.read_text(encoding="utf-8", errors="replace"), "html.parser")
    except Exception:
        return set()
    values: set[str] = set()
    for node in soup.select('[data-field="full_name"]'):
        value = node.get_text(" ", strip=True)
        if re.search(r"eqjc|font|hps\d|mspmincho", value, re.I):
            continue
        value = re.sub(r"[（(].*?[）)]", "", value).strip()
        value = re.sub(r"[\u3040-\u30ff].*$", "", value).strip()
        if len(re.findall(r"[\u3400-\u9fff]", value)) >= 2 and not invalid_name_semantics(value):
            values.add(compact(value))
    return {value for value in values if value}


def date_evidenced(value: Any, text: str) -> bool:
    match = re.search(r"((?:19|20)\d{2})年(\d{2})月", str(value or ""))
    if not match:
        return False
    year, month = match.groups()
    return bool(re.search(rf"{year}\s*(?:年|[./-])\s*0?{int(month)}", text))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repair-report", type=Path, required=True)
    parser.add_argument("--map", type=Path, required=True)
    parser.add_argument("--extra-map-root", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    repaired = json.loads(args.repair_report.read_text(encoding="utf-8"))
    map_rows = json.loads(args.map.read_text(encoding="utf-8"))
    by_source = {path_key(row.get("source_path", "")): row for row in map_rows}
    if args.extra_map_root:
        for extra_map in args.extra_map_root.glob("*/word_conversion_map.json"):
            try:
                extra_rows = json.loads(extra_map.read_text(encoding="utf-8"))
            except Exception:
                continue
            for extra_row in extra_rows:
                key = path_key(extra_row.get("source_path", ""))
                extra_html = Path(str(extra_row.get("html_path") or ""))
                current_html = Path(str((by_source.get(key) or {}).get("html_path") or ""))
                if key and extra_html.is_file() and not current_html.is_file():
                    by_source[key] = extra_row
    results: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()

    for item in repaired.get("items") or []:
        if item.get("status") != "repaired_valid":
            continue
        folder = str(item.get("language_folder") or "")
        required = LANGUAGE_REQUIREMENTS.get(folder)
        if not required:
            continue
        payload = json.loads(Path(item["output_json"]).read_text(encoding="utf-8"))
        declared_actual_languages = {
            str(value).casefold()
            for value in ((payload.get("source") or {}).get("actual_resume_languages") or [])
            if str(value).strip()
        }
        if declared_actual_languages:
            required = declared_actual_languages
        languages = {
            str(resume.get("resume_language") or resume.get("resume_languge") or "").casefold()
            for resume in ((payload.get("structured_data") or {}).get("resumes") or [])
            if str(resume.get("resume_language") or resume.get("resume_languge") or "").strip()
        }
        missing_languages = sorted(required - languages)

        source_path = str(item.get("source_path") or "")
        map_row = by_source.get(path_key(source_path), {})
        html_path = Path(str(map_row.get("html_path") or ""))
        source = Path(source_path)
        source_lines: list[str] = []
        html_lines: list[str] = []
        try:
            source_lines = read_source_lines(source) if source.is_file() else []
        except Exception:
            source_lines = []
        try:
            html_lines = read_source_lines(html_path) if html_path.is_file() else []
        except Exception:
            html_lines = []
        source_text = "\n".join(source_lines)
        html_text = "\n".join(html_lines)
        # 两种读取器各有损失：antiword 可能丢日文字符，语义 HTML 可能归一化空格。
        # 证据应取并集，不能在源文本非空时忽略 HTML。
        # EN: Each reader loses something: antiword may drop Japanese characters, and semantic HTML may normalise spaces.
        #     Evidence must be the union of both; HTML cannot be ignored just because the source text is non-empty.
        # JA: どちらのリーダーにも欠損がある：antiword は日本語の文字を落とすことがあり、セマンティック HTML は空白を正規化することがある。
        #     証拠は両者の和集合を取るべきで、ソーステキストが空でないからといって HTML を無視してはならない。
        evidence_text = "\n".join(part for part in (source_text, html_text) if part)
        source_meta = payload.get("source") or {}
        manually_verified_values = {
            compact(value) for value in (source_meta.get("manual_verified_values") or []) if compact(value)
        }
        manually_verified_identity = bool(source_meta.get("manual_verified_identity"))
        issues: list[dict[str, Any]] = []
        source_note = str((payload.get("source") or {}).get("note") or "")
        manually_word_verified = "人工使用 Word 只读打开源" in source_note
        if missing_languages and "单一中日混排履历" not in source_note:
            issues.append({"code": "missing_language_variants", "missing": missing_languages})
        structured = payload.get("structured_data") or {}
        base = structured.get("base_info") or {}

        # 旧 .doc 可能无法被 antiword 直接读取；由同一源文件成功重建的语义 HTML
        # 是可接受的源证据。只有两者都不可读才阻塞。
        # EN: Old .doc files may not be readable by antiword directly; semantic HTML successfully rebuilt from the same source file
        #     is acceptable source evidence. Block only when neither is readable.
        # JA: 旧 .doc は antiword で直接読めないことがある。同じソースファイルから正常に再構築されたセマンティック HTML は
        #     ソース証拠として認められる。両方とも読めない場合だけブロックする。
        if not source_text and not html_text and not manually_word_verified:
            issues.append({"code": "source_unreadable", "path": source_path})
        if not html_text and not source_text and not manually_word_verified:
            issues.append({"code": "html_unreadable", "path": str(html_path)})
        if source_text and html_text:
            source_phones = set(MOBILE_RE.findall(source_text))
            html_phones = set(MOBILE_RE.findall(html_text))
            if source_phones and html_phones and not source_phones.intersection(html_phones):
                issues.append({"code": "source_html_phone_disagree", "source": sorted(source_phones), "html": sorted(html_phones)})

        phone = re.sub(r"\D", "", str(base.get("phone") or ""))
        phone = phone[-11:] if len(phone) >= 11 else phone
        evidence_phones = set(MOBILE_RE.findall(evidence_text))
        if phone and evidence_phones and phone not in evidence_phones:
            issues.append({"code": "phone_not_in_source", "actual": phone, "evidence": sorted(evidence_phones)[:8]})
        email = str(base.get("email") or "").strip().casefold()
        evidence_emails = {value.casefold() for value in EMAIL_RE.findall(evidence_text)}
        if email and evidence_emails and email not in evidence_emails:
            issues.append({"code": "email_not_in_source", "actual": email, "evidence": sorted(evidence_emails)[:8]})
        name = str(base.get("full_name") or "").strip()
        if invalid_name_semantics(name):
            issues.append({"code": "invalid_full_name_semantics", "actual": name})
        explicit_html_names = semantic_html_names(html_path)
        compact_name = compact(name)
        semantic_name_agrees = any(
            candidate == compact_name
            or candidate.startswith(compact_name)
            or compact_name.startswith(candidate)
            for candidate in explicit_html_names
        )
        if name and explicit_html_names and not semantic_name_agrees:
            issues.append({
                "code": "full_name_disagrees_with_semantic_html",
                "actual": name,
                "semantic_html_names": sorted(explicit_html_names),
            })
        if name and not manually_verified_identity and not identity_evidenced(name, evidence_text, source_path):
            issues.append({"code": "name_not_in_source", "actual": name})

        all_resumes = structured.get("resumes") or []
        zh_resume = next(
            (row for row in all_resumes if str(row.get("resume_language") or row.get("resume_languge") or "") == "zh"),
            None,
        )
        for resume_index, resume in enumerate(all_resumes):
            language = str(resume.get("resume_language") or resume.get("resume_languge") or "")
            if language == "zh":
                # 外文源文件的中文版本可能是 complete-v1 中的人工翻译，不能要求逐字出现在源文。
                # EN: The Chinese version of a foreign-language source may be a manual translation from complete-v1, so it cannot be required to appear verbatim in the source.
                # JA: 外国語ソースの中国語版は complete-v1 の人手翻訳である場合があり、原文に一字一句現れることを要求できない。
                continue
            resume_text = json.dumps(resume, ensure_ascii=False)
            if language == "jp" and not re.search(r"[\u3040-\u30ff]", resume_text + evidence_text):
                issues.append({"code": "jp_resume_without_japanese_signal", "resume_index": resume_index})
            if language in {"en", "de", "fr"} and len(re.findall(r"\b[A-Za-z]{4,}\b", resume_text)) < 3:
                issues.append({"code": f"{language}_resume_without_latin_signal", "resume_index": resume_index})
            for list_name, key in (("work_experiences", "company_name"), ("education_list", "school_name")):
                for row_index, row in enumerate(resume.get(list_name) or []):
                    value = str((row or {}).get(key) or "").strip()
                    translated_counterpart_ok = False
                    if value and zh_resume and language != "zh":
                        zh_rows = zh_resume.get(list_name) or []
                        date_fields = (
                            ("position_start", "position_resigned")
                            if list_name == "work_experiences"
                            else ("school_start_ym", "school_end_ym")
                        )
                        for zh_index, counterpart in enumerate(zh_rows):
                            counterpart = counterpart or {}
                            comparable_dates = [
                                field for field in date_fields
                                if str((row or {}).get(field) or "") and str(counterpart.get(field) or "")
                            ]
                            dates_do_not_conflict = all(
                                str((row or {}).get(field) or "") == str(counterpart.get(field) or "")
                                for field in comparable_dates
                            )
                            aligned = (bool(comparable_dates) and dates_do_not_conflict) or zh_index == row_index
                            source_dates_ok = any(
                                date_evidenced((row or {}).get(field), evidence_text)
                                for field in date_fields
                            )
                            if aligned and (evidenced(counterpart.get(key), evidence_text) or source_dates_ok):
                                translated_counterpart_ok = True
                                break
                    if value and compact(value) not in manually_verified_values and not evidenced(value, evidence_text) and not translated_counterpart_ok and not (manually_word_verified and not evidence_text):
                        issues.append({
                            "code": f"{list_name}_{key}_not_in_source",
                            "resume_index": resume_index,
                            "row_index": row_index,
                            "actual": value,
                        })

        status = "passed" if not issues else "needs_review"
        counts[status] += 1
        for issue in issues:
            counts[issue["code"]] += 1
        results.append({
            "status": status,
            "language_folder": folder,
            "source_path": source_path,
            "html_path": str(html_path),
            "json_path": item["output_json"],
            "resume_languages": item.get("resume_languages") or [],
            "issues": issues,
        })

    report = {"summary": dict(counts), "items": results}
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"summary": dict(counts), "report": str(args.report)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
