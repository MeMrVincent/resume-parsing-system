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
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup


PROJECT_ROOT = _rc.project_root()
DEFAULT_PASSED = PROJECT_ROOT / _rc.dirname("complete-transfered-htmls") / "docs" / "passed"
DEFAULT_MAP = PROJECT_ROOT / _rc.dirname("complete-transfered-htmls") / "docs" / "word_conversion_map.json"

LANG_ORDER = ("中", "英", "日", "德", "法", "韩", "俄")
SINGLE_FOLDER = {
    "中": "中文", "英": "英文", "日": "日文", "德": "德文",
    "法": "法文", "韩": "韩文", "俄": "俄文",
}

ZH_STRONG_CHARS = set("这为国个们与发后里时过从对将于业门书历学专级实习现应职务经贸资车电东华龙陈张刘赵杨吴孙马黄周郑许邓叶苏汉语简历")
ZH_KEYWORDS = re.compile(
    r"个人信息|基本信息|求职意向|工作经历|工作经验|教育经历|教育背景|"
    r"自我评价|期望薪资|现居住|户籍|婚姻状况|手机|邮箱|有限公司"
)
JA_KEYWORDS = re.compile(
    r"履\s*歴\s*書|職務経歴|学歴|職歴|生年月日|氏名|現住所|自己PR|"
    r"希望給与|所属部門|業務内容|退職理由|日本語"
)
EN_KEYWORDS = re.compile(
    r"\b(?:curriculum vitae|resume|work experience|professional experience|"
    r"education|personal information|career objective|employment history|skills)\b",
    re.IGNORECASE,
)
DE_KEYWORDS = re.compile(r"\b(?:Lebenslauf|Geburtsdatum|Berufserfahrung|Schulbildung|Kenntnisse|Ausbildung)\b", re.IGNORECASE)
FR_KEYWORDS = re.compile(r"\b(?:Curriculum vitae|Expérience professionnelle|Formation|Compétences|Langues|Éducation)\b", re.IGNORECASE)


def semantic_text(path: Path) -> tuple[str, str]:
    soup = BeautifulSoup(path.read_text(encoding="utf-8", errors="replace"), "html.parser")
    main = soup.find("main", attrs={"data-role": "document-content"}) or soup.body or soup
    text = re.sub(r"\s+", " ", main.get_text(" ", strip=True)).strip()
    lang = str((soup.html or {}).get("lang") or "").casefold()
    return text, lang


def detect_languages(text: str, html_lang: str = "") -> tuple[list[str], dict[str, int | float | bool]]:
    han = len(re.findall(r"[\u4e00-\u9fff]", text))
    kana = len(re.findall(r"[\u3040-\u30ff]", text))
    hangul = len(re.findall(r"[\uac00-\ud7af]", text))
    cyrillic = len(re.findall(r"[\u0400-\u04ff]", text))
    latin_chars = len(re.findall(r"[A-Za-z]", text))
    meaningful = max(1, len(re.findall(r"[A-Za-z\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af\u0400-\u04ff]", text)))
    english_words = re.findall(r"\b[A-Za-z]{2,}\b", text)
    zh_strong = sum(char in ZH_STRONG_CHARS for char in text)
    zh_keywords = len(ZH_KEYWORDS.findall(text))
    ja_keywords = len(JA_KEYWORDS.findall(text))
    en_keywords = len(EN_KEYWORDS.findall(text))
    de_keywords = len(DE_KEYWORDS.findall(text))
    fr_keywords = len(FR_KEYWORDS.findall(text))
    latin_ratio = latin_chars / meaningful

    has_ja = kana >= 15 or ja_keywords >= 2
    if has_ja:
        # Japanese contains many Han characters. Require independent Chinese
        # prose/section evidence rather than treating every Han character as Chinese.
        has_zh = han >= 40 and ((zh_keywords >= 3 and zh_strong >= 20) or zh_strong >= 45)
    else:
        has_zh = han >= 40 or zh_keywords >= 2

    has_de = de_keywords >= 2
    has_fr = fr_keywords >= 2
    has_en = (
        (len(english_words) >= 60 and latin_chars >= 300 and latin_ratio >= 0.22)
        or en_keywords >= 3
        or (html_lang.startswith("en") and len(english_words) >= 20)
    )
    # German/French resumes inevitably contain Latin words; only keep English as
    # a second language when English evidence is substantial beyond that script.
    if (has_de or has_fr) and en_keywords < 3:
        has_en = False

    flags = {
        "中": has_zh, "英": has_en, "日": has_ja, "德": has_de,
        "法": has_fr, "韩": hangul >= 30, "俄": cyrillic >= 40,
    }
    languages = [language for language in LANG_ORDER if flags[language]]
    evidence: dict[str, int | float | bool] = {
        "han": han, "kana": kana, "hangul": hangul, "cyrillic": cyrillic,
        "latin_chars": latin_chars, "latin_ratio": round(latin_ratio, 4),
        "english_words": len(english_words), "zh_strong": zh_strong,
        "zh_keywords": zh_keywords, "ja_keywords": ja_keywords,
        "en_keywords": en_keywords, "de_keywords": de_keywords,
        "fr_keywords": fr_keywords,
    }
    return languages, evidence


def folder_for(languages: list[str]) -> str:
    if not languages:
        return "其他"
    if len(languages) == 1:
        return SINGLE_FOLDER[languages[0]]
    return "".join(languages) + "文"


def atomic_write_json(path: Path, payload: Any) -> None:
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def run(passed_dir: Path, map_path: Path, apply: bool) -> dict[str, Any]:
    passed_dir = passed_dir.resolve()
    files = sorted(path for path in passed_dir.glob("*.html") if path.is_file())
    assignments: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    for path in files:
        text, html_lang = semantic_text(path)
        languages, evidence = detect_languages(text, html_lang)
        folder = folder_for(languages)
        destination = passed_dir / folder / path.name
        counts[folder] += 1
        assignments.append({
            "source": str(path), "destination": str(destination),
            "folder": folder, "languages": languages, "evidence": evidence,
        })

    collisions = [row for row in assignments if Path(row["destination"]).exists() and Path(row["destination"]) != Path(row["source"])]
    if collisions:
        raise RuntimeError(f"目标目录存在 {len(collisions)} 个同名文件，已停止")

    report: dict[str, Any] = {
        "mode": "apply" if apply else "dry-run",
        "passed_dir": str(passed_dir), "map_path": str(map_path.resolve()),
        "root_html_files": len(files), "category_counts": dict(sorted(counts.items())),
        "samples": {
            folder: [row for row in assignments if row["folder"] == folder][:5]
            for folder in sorted(counts)
        },
    }
    if not apply:
        return report

    records = json.loads(map_path.read_text(encoding="utf-8"))
    path_updates: dict[str, str] = {}
    for row in assignments:
        source = Path(row["source"])
        destination = Path(row["destination"])
        destination.parent.mkdir(parents=True, exist_ok=True)
        source.replace(destination)
        path_updates[str(source).casefold()] = str(destination)
    updated_records = 0
    for record in records:
        old_path = str(record.get("html_path") or "")
        new_path = path_updates.get(old_path.casefold())
        if new_path:
            record["html_path"] = new_path
            record["language_folder"] = Path(new_path).parent.name
            updated_records += 1
    atomic_write_json(map_path, records)
    report["moved_files"] = len(assignments)
    report["updated_map_records"] = updated_records
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="按正文语言细分 passed HTML 并同步映射表" " / Subdivide passed HTML by body language and sync the map table / passed の HTML を本文の言語で細分し、マップ表を同期する")
    parser.add_argument("--passed-dir", type=Path, default=DEFAULT_PASSED)
    parser.add_argument("--map", type=Path, default=DEFAULT_MAP)
    parser.add_argument("--apply", action="store_true", help="实际移动；默认只预览" " / Actually move; by default only preview / 実際に移動する（既定ではプレビューのみ）")
    parser.add_argument("--summary-only", action="store_true", help="预览时不输出分类样本" " / Do not output classification samples when previewing / プレビュー時に分類のサンプルを出力しない")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    result = run(args.passed_dir, args.map, args.apply)
    if args.summary_only:
        result.pop("samples", None)
    print(json.dumps(result, ensure_ascii=False, indent=2))
