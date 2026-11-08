"""日文语义 HTML -> complete-v1 JSON 解析器。

复用成熟的 DOM 字段抽取，但只保留源文真实存在的日文 resume，避免为日文原稿
自动制造一份内容相同的中文版本。

EN: Japanese semantic HTML -> complete-v1 JSON parser.

Reuses the mature DOM field extraction, but keeps only the Japanese resume that really exists in the source, avoiding
automatically creating an identical Chinese version for a Japanese original.

JA: 日本語のセマンティック HTML -> complete-v1 JSON のパーサー。

成熟した DOM のフィールド抽出を再利用するが、原文に実際にある日本語の resume だけを残し、日本語の原稿に対して
内容が同じ中国語版を自動的に作らないようにする。
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

from run_chinese_html_to_json import canonicalize_complete_schema, main as core_main, rebuild_raw_text


PROJECT_ROOT = _rc.project_root()


def option_path(name: str, default: Path) -> Path:
    try:
        index = sys.argv.index(name)
        return Path(sys.argv[index + 1]).resolve()
    except (ValueError, IndexError):
        return default.resolve()


def japanese_signal(resume: dict) -> int:
    text = json.dumps(resume, ensure_ascii=False)
    return sum(1 for char in text if "\u3040" <= char <= "\u30ff")


def normalize_japanese_record(path: Path) -> bool:
    payload = json.loads(path.read_text(encoding="utf-8"))
    original_raw_text = str(payload.get("raw_text") or "")
    staged_html = Path(str((payload.get("source") or {}).get("path") or ""))
    if staged_html.is_file():
        original_raw_text += "\n" + staged_html.read_text(encoding="utf-8", errors="replace")
    original_base = dict((payload.get("structured_data") or {}).get("base_info") or {})
    structured = canonicalize_complete_schema(payload.get("structured_data") or {})
    resumes = structured.get("resumes") or []
    if not resumes:
        return False
    selected = next((resume for resume in resumes if resume.get("resume_language") == "jp"), None)
    if selected is None:
        selected = max(resumes, key=japanese_signal)
    selected["resume_language"] = "jp"
    selected_base = selected.setdefault("base_info", {})
    for key in ("full_name", "phone", "email", "birth_date", "birth_year", "gender"):
        if not selected_base.get(key) and original_base.get(key):
            selected_base[key] = original_base[key]
    # 文件同时含座机和手机时，正式文件名及默认联系方式统一优先使用手机。
    # EN: When a file has both a landline and a mobile, the formal file name and default contact uniformly prefer the mobile.
    # JA: ファイルに固定電話と携帯電話の両方がある場合、正式なファイル名と既定の連絡先は一律に携帯電話を優先する。
    mobiles = re.findall(r"(?<!\d)1[3-9](?:[\s-]?\d){9}(?!\d)", original_raw_text)
    if mobiles:
        selected_base["phone"] = re.sub(r"\D", "", mobiles[0])
    structured["resumes"] = [selected]
    structured["base_info"] = dict(selected.get("base_info") or {})
    structured["expected_info"] = dict((selected.get("expected_list") or [{}])[0]) if selected.get("expected_list") else {}
    structured["current_info"] = dict((selected.get("work_experiences") or [{}])[0]) if selected.get("work_experiences") else {}
    structured["education_info"] = dict((selected.get("education_list") or [{}])[0]) if selected.get("education_list") else {}
    payload["structured_data"] = structured
    payload["raw_text"] = rebuild_raw_text([selected])
    source = payload.setdefault("source", {})
    source["converter"] = "run_japanese_html_to_json.py"
    source["actual_resume_languages"] = ["jp"]
    note = str(source.get("note") or "").strip()
    addition = "日文专用语义解析：仅保留源文实际存在的 jp resume，不生成重复中文版本。"
    if addition not in note:
        source["note"] = (note + " " + addition).strip()
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    full_name = re.sub(r'[\\/:*?"<>|]', "", str(selected_base.get("full_name") or "未知")).strip()
    phone = re.sub(r"\D", "", str(selected_base.get("phone") or ""))
    email = re.sub(r'[\\/:*?"<>|]', "", str(selected_base.get("email") or "").strip().casefold())
    contact = phone or email or "无联系方式"
    desired = path.with_name(f"{full_name}_{contact}.json")
    if desired != path:
        suffix = 2
        while desired.exists():
            desired = path.with_name(f"{full_name}_{contact}_{suffix}.json")
            suffix += 1
        path.replace(desired)
    return True


def main() -> int:
    json_dir = option_path(
        "--json-dir", PROJECT_ROOT / _rc.dirname("complete-transfered-jsons") / "docs" / "日文"
    )
    result = core_main()
    normalized = 0
    for path in json_dir.glob("*.json"):
        if path.name.startswith("_"):
            continue
        try:
            normalized += int(normalize_japanese_record(path))
        except Exception as exc:
            print(f"[日文规范化失败] {path.name}: {exc}" f" / [Japanese normalization failed] {path.name}: {exc} / [日本語の正規化に失敗] {path.name}：{exc}", flush=True)
    report = {
        "workflow": "japanese_html_to_json",
        "json_dir": str(json_dir),
        "normalized_japanese_records": normalized,
    }
    (json_dir / "_japanese_semantic_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"日文语义规范化完成：{normalized} 份" f" / Japanese semantic normalization done: {normalized} files / 日本語の意味の正規化が完了しました：{normalized} 件", flush=True)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
