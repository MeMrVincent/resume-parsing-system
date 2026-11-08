"""中日混合目录 HTML -> complete-v1 JSON 专用解析器。

一个 DOM resume-record 只生成一个真实语言版本；禁止仅因正文出现日语技能、
日企名称或少量日文自我介绍，就复制出内容相同的 zh/jp 两份履历。

EN: Dedicated parser for HTML in the mixed Chinese-Japanese directory -> complete-v1 JSON.

One DOM resume-record produces only one real language version; copying out identical zh/jp résumés
just because the body mentions Japanese skills, Japanese company names or a short Japanese self-introduction is forbidden.

JA: 中日混在ディレクトリの HTML -> complete-v1 JSON 専用のパーサー。

1 つの DOM の resume-record からは実際の言語の版を 1 つだけ生成する。本文に日本語のスキル、
日系企業の名前、少しの日本語の自己紹介が出てくるというだけで、内容が同じ zh/jp の 2 つの履歴書を複製することは禁止。
"""

from __future__ import annotations
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1] / "common"))
import rc_config as _rc  # noqa: E402  项目统一配置（python/common/rc_config.py）
# EN: noqa: E402  project-wide configuration (python/common/rc_config.py)
# JA: noqa: E402  プロジェクト共通設定（python/common/rc_config.py）

import json
import re
import sys
from pathlib import Path

from bs4 import BeautifulSoup

from run_chinese_html_to_json import canonicalize_complete_schema, main as core_main, rebuild_raw_text


PROJECT_ROOT = _rc.project_root()
NON_RESUME_TITLES = ("面试邀请", "面試邀請", "面试通知", "面試通知")


def option_path(name: str, default: Path) -> Path:
    try:
        index = sys.argv.index(name)
        return Path(sys.argv[index + 1]).resolve()
    except (ValueError, IndexError):
        return default.resolve()


def html_language(path: Path) -> tuple[str, int, int, int]:
    raw = path.read_text(encoding="utf-8", errors="replace")
    soup = BeautifulSoup(raw, "html.parser")
    content = soup.select_one('main[data-role="document-content"]') or soup.body or soup
    text = content.get_text(" ", strip=True)
    kana = len(re.findall(r"[\u3040-\u30ff]", text))
    ideographs = len(re.findall(r"[\u3400-\u9fff]", text))
    record_count = len(content.select('[data-role="resume"]')) or 1
    ratio = kana / max(kana + ideographs, 1)
    language = "jp" if kana >= 40 and ratio >= 0.12 else "zh"
    return language, kana, ideographs, record_count


def rename_json(path: Path, base: dict) -> Path:
    name = re.sub(r'[\\/:*?"<>|]', "", str(base.get("full_name") or "未知")).strip()
    phone = re.sub(r"\D", "", str(base.get("phone") or ""))
    email = re.sub(r'[\\/:*?"<>|]', "", str(base.get("email") or "").strip().casefold())
    contact = phone or email or "无联系方式"
    target = path.with_name(f"{name}_{contact}.json")
    if target == path:
        return path
    suffix = 2
    while target.exists():
        target = path.with_name(f"{name}_{contact}_{suffix}.json")
        suffix += 1
    path.replace(target)
    return target


def normalize_record(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    html_path = Path(str((payload.get("source") or {}).get("path") or ""))
    language, kana, ideographs, record_count = html_language(html_path)
    structured = canonicalize_complete_schema(payload.get("structured_data") or {})
    resumes = structured.get("resumes") or []
    selected = next(
        (resume for resume in resumes if str(resume.get("resume_language") or "").casefold() == language),
        None,
    )
    if selected is None and resumes:
        selected = resumes[0]
    if selected is None:
        raise ValueError("missing_resume")
    selected["resume_language"] = language
    structured["resumes"] = [selected]
    structured["base_info"] = dict(selected.get("base_info") or {})
    structured["expected_info"] = dict((selected.get("expected_list") or [{}])[0]) if selected.get("expected_list") else {}
    structured["current_info"] = dict((selected.get("work_experiences") or [{}])[0]) if selected.get("work_experiences") else {}
    structured["education_info"] = dict((selected.get("education_list") or [{}])[0]) if selected.get("education_list") else {}
    payload["structured_data"] = structured
    payload["raw_text"] = rebuild_raw_text([selected])
    source = payload.setdefault("source", {})
    source["converter"] = "run_chinese_japanese_html_to_json.py"
    source["actual_resume_languages"] = [language]
    source["resume_record_count"] = record_count
    source["language_evidence"] = {"kana": kana, "ideographs": ideographs}
    addition = "中日目录专用解析：单一 DOM 履历只保留一个真实语言版本，不复制伪造 zh/jp。"
    source["note"] = (str(source.get("note") or "") + " " + addition).strip()
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    renamed = rename_json(path, structured["base_info"])
    return {"json": str(renamed), "language": language, "kana": kana, "ideographs": ideographs}


def main() -> int:
    json_dir = option_path("--json-dir", PROJECT_ROOT / _rc.dirname("complete-transfered-jsons") / "docs" / "中日文")
    map_path = option_path("--map", PROJECT_ROOT / _rc.dirname("complete-transfered-htmls") / "docs" / "word_conversion_map.json")
    result = core_main()
    normalized = []
    removed_non_resume = []
    for path in list(json_dir.glob("*.json")):
        if path.name.startswith("_"):
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            html_name = str((payload.get("source") or {}).get("filename") or "")
            if any(token in html_name for token in NON_RESUME_TITLES):
                original_path = str((payload.get("source") or {}).get("original_path") or "")
                path.unlink()
                removed_non_resume.append({"html_filename": html_name, "source_path": original_path})
                continue
            normalized.append(normalize_record(path))
        except Exception as exc:
            normalized.append({"json": str(path), "error": str(exc)})
    if removed_non_resume and map_path.is_file():
        map_rows = json.loads(map_path.read_text(encoding="utf-8"))
        removed_sources = {row["source_path"] for row in removed_non_resume}
        for map_row in map_rows:
            if str(map_row.get("source_path") or "") in removed_sources:
                map_row["status"] = "non_resume"
                map_row["error_reason"] = "人工规则核验：面试邀请/通知合集，不是候选人简历"
                map_row["terminal_classification"] = "non_resume_interview_notice"
        map_path.write_text(json.dumps(map_rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report = {
        "workflow": "chinese_japanese_html_to_json",
        "normalized": len([row for row in normalized if not row.get("error")]),
        "removed_non_resume": removed_non_resume,
        "items": normalized,
    }
    (json_dir / "_chinese_japanese_semantic_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"normalized": report["normalized"], "non_resume": len(removed_non_resume)}, ensure_ascii=False))
    return result


if __name__ == "__main__":
    raise SystemExit(main())
