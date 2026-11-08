"""complete-transfered-htmls\\web 目录 HTML -> JSON 专用转换脚本。

核心原则（严格执行，宁严勿松）：
1. 顶层 JSON 只 6 个字段：schema_version / source / extraction / dates / structured_data / raw_text
2. structured_data 顶层只 5 个字段：base_info / expected_info / current_info / education_info / resumes
   → ❌ 禁止出现：work_experiences / education_list / project_list / training_list
                / certificate_list / language_list / skills_list / communication_list
                / project_experiences / communication_assessment / training_experiences
3. raw_text 仅存在于最外层（structured_data 的 sibling）；所有子对象不得有 raw_text 字段
4. education_info 严格 7 字段；expected_info 严格 8 字段；current_info 严格 12 字段空结构兜底
5. school_degree_rank ∈ "1"~"7"（字符串）
6. skills_list：个人素质词 → base_info.pr；过滤动作短语「负责…/每天…/上交…」
7. resumes[0].resume_language == "zh"；中文主版本固定
8. 所有子列表 item 内不得含 raw_text 字段

复用：CodexGeminiHtmlSchemaParser + DocumentClassifier + 四大平台通用后处理工具函数。

EN: Dedicated HTML -> JSON conversion script for the complete-transfered-htmls\\web directory.

Core principles (strictly enforced, better too strict than too loose):
1. The top-level JSON has only 6 fields: schema_version / source / extraction / dates / structured_data / raw_text
2. The top level of structured_data has only 5 fields: base_info / expected_info / current_info / education_info / resumes
   → ❌ Forbidden: work_experiences / education_list / project_list / training_list
                / certificate_list / language_list / skills_list / communication_list
                / project_experiences / communication_assessment / training_experiences
3. raw_text exists only at the outermost level (a sibling of structured_data); no sub-object may have a raw_text field
4. education_info strictly 7 fields; expected_info strictly 8 fields; current_info falls back to an empty structure of strictly 12 fields
5. school_degree_rank ∈ "1"~"7" (strings)
6. skills_list: personal-quality words → base_info.pr; filter action phrases "负责… / 每天… / 上交…"
7. resumes[0].resume_language == "zh"; the Chinese primary version is fixed
8. No item in any sub-list may contain a raw_text field

Reuses: CodexGeminiHtmlSchemaParser + DocumentClassifier + the generic post-processing helpers of the four major platforms.

JA: complete-transfered-htmls\\web ディレクトリ専用の HTML -> JSON 変換スクリプト。

中核の原則（厳格に実行し、緩すぎるより厳しすぎる方がよい）：
1. トップレベルの JSON は 6 フィールドだけ：schema_version / source / extraction / dates / structured_data / raw_text
2. structured_data のトップレベルは 5 フィールドだけ：base_info / expected_info / current_info / education_info / resumes
   → ❌ 禁止：work_experiences / education_list / project_list / training_list
                / certificate_list / language_list / skills_list / communication_list
                / project_experiences / communication_assessment / training_experiences
3. raw_text は最も外側（structured_data の兄弟要素）にだけ存在し、どのサブオブジェクトも raw_text フィールドを持ってはならない
4. education_info は厳密に 7 フィールド、expected_info は厳密に 8 フィールド、current_info は厳密に 12 フィールドの空の構造で補う
5. school_degree_rank ∈ "1"〜"7"（文字列）
6. skills_list：個人の資質の語 → base_info.pr。動作の語句「负责…／每天…／上交…」を除外する
7. resumes[0].resume_language == "zh"。中国語主版は固定
8. どのサブリストの要素にも raw_text フィールドがあってはならない

再利用：CodexGeminiHtmlSchemaParser + DocumentClassifier + 4 大プラットフォーム共通の後処理ツール関数。
"""

from __future__ import annotations
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1] / "common"))
import rc_config as _rc  # noqa: E402  项目统一配置（python/common/rc_config.py）
# EN: noqa: E402  project-wide configuration (python/common/rc_config.py)
# JA: noqa: E402  プロジェクト共通設定（python/common/rc_config.py）

import argparse
import copy
import hashlib
import json
import os
import re
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

PROJECT_ROOT = _rc.project_root()
PYTHON_ROOT = _rc.PYTHON_DIR / "v2"
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from resume_importer.codex_gemini_html_schema_parser import CodexGeminiHtmlSchemaParser
from resume_importer.classifier import DocumentClassifier

# 复用 run_zhilian_html_to_json.py 的现成解析器（求职意向/工作/教育/证书/语言/技能）
# EN: Reuse the existing parsers of run_zhilian_html_to_json.py (job preferences / work / education / certificates / languages / skills)
# JA: run_zhilian_html_to_json.py の既存のパーサー（希望条件・職歴・学歴・資格・語学・スキル）を再利用する
from run_zhilian_html_to_json import (
    _parse_zhilian_expected_info,
    _parse_zhilian_work_experiences,
    _parse_zhilian_education,
    _parse_zhilian_certificates,
    _parse_zhilian_languages,
    _parse_zhilian_skills,
)
# 复用中英文语义解析器的现成工具（plain_text/dom_summary/parse_resume_dates）
# EN: Reuse the existing tools of the Chinese-English semantic parser (plain_text / dom_summary / parse_resume_dates)
# JA: 中英の意味解析器の既存のツール（plain_text / dom_summary / parse_resume_dates）を再利用する
from run_chinese_english_html_to_json import (
    plain_text as liepin_plain_text,
    dom_summary,
    parse_resume_dates as liepin_parse_resume_dates,
)

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None

TZ_JST = timezone(timedelta(hours=9))

if os.name == "nt":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

# =============================================================================
# 基础 I/O
# =============================================================================
# EN: =============================================================================
#     Basic I/O
#     =============================================================================
# JA: =============================================================================
#     基本の I/O
#     =============================================================================

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="web 目录 HTML -> JSON 转换（严格 6 顶层字段约束版）" " / Web directory HTML -> JSON conversion (strict 6-top-level-field version) / web ディレクトリの HTML -> JSON 変換（トップレベル 6 フィールドの厳密版）")
    p.add_argument(
        "--html-dir",
        type=Path,
        default=PROJECT_ROOT / _rc.dirname("complete-transfered-htmls") / "web",
    )
    p.add_argument(
        "--json-dir",
        type=Path,
        default=PROJECT_ROOT / _rc.dirname("complete-transfered-jsons") / "web",
    )
    p.add_argument("--limit", type=int, default=0, help="0=全部" " / 0 = all / 0 は全件")
    p.add_argument("--force", action="store_true", help="覆盖已存在 JSON" " / Overwrite existing JSON / 既存の JSON を上書きする")
    p.add_argument("--progress-interval", type=int, default=10)
    p.add_argument("--random", action="store_true", dest="random_sample",
                   help="从目录中随机抽样（需配合 --limit 使用）" " / Random sampling from the directory (use together with --limit) / ディレクトリからランダムにサンプリングする（--limit と併用）")
    p.add_argument("--seed", type=int, default=20260804,
                   help="随机抽样种子（默认 20260804，可复现）" " / Random sampling seed (default 20260804, reproducible) / ランダムサンプリングのシード（既定 20260804、再現可能）")
    return p.parse_args()


def read_html_text(html_path: Path) -> str:
    """统一 HTML 解码：优先探测 meta charset，UTF-8 优先，避开 GB18030 霸道误解。

    EN: Unified HTML decoding: detect meta charset first, prefer UTF-8, and avoid GB18030's overbearing misinterpretation.

    JA: HTML のデコードの統一：まず meta charset を検出し、UTF-8 を優先して、GB18030 による強引な誤解釈を避ける。
    """
    raw_bytes = html_path.read_bytes()
    meta_m = re.search(rb"""<meta[^>]+charset=['"]?\s*([a-zA-Z0-9\-]+)""", raw_bytes, re.I)
    if meta_m:
        meta_enc = meta_m.group(1).decode("ascii", errors="ignore").lower()
        if meta_enc in ("utf-8", "utf8", "utf8-sig"):
            meta_enc = "utf-8"
        elif meta_enc in ("gbk", "gb2312", "gb18030"):
            meta_enc = "gb18030"
        try:
            t = raw_bytes.decode(meta_enc)
            if "\ufffd" not in t[:500]:
                return t
        except Exception:
            pass
    for enc in ("utf-8", "utf-8-sig", "gb18030", "gbk", "big5", "utf-16"):
        try:
            t = raw_bytes.decode(enc)
            if "\ufffd" in t[:200]:
                continue
            if "个人信息" in t or "简历" in t or "姓名" in t or "求职意向" in t or "工作经历" in t:
                return t
        except Exception:
            continue
    return raw_bytes.decode("utf-8", errors="replace")


def html_record_id(html_path: Path) -> str:
    stat = html_path.stat()
    value = f"{html_path.resolve()}|{stat.st_size}|{stat.st_mtime_ns}"
    return hashlib.sha256(value.encode("utf-8", "surrogatepass")).hexdigest()


def date_from_mtime(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime, tz=TZ_JST).strftime("%Y-%m-%d %H:%M:%S")


def standardize_datetime(raw: str) -> str:
    raw = raw.replace("年", "-").replace("月", "-").replace("日", "").replace(".", "-").replace("/", "-")
    raw = re.sub(r"\s+", " ", raw).strip()
    parts = raw.split(" ")
    date_part = parts[0]
    time_part = parts[1] if len(parts) > 1 else "00:00:00"
    d_parts = date_part.split("-")
    if len(d_parts) >= 3:
        try:
            y, m, d = d_parts[0], d_parts[1], d_parts[2]
            date_str = f"{int(y):04d}-{int(m):02d}-{int(d):02d}"
        except Exception:
            date_str = date_part
    else:
        date_str = date_part
    t_parts = time_part.split(":")
    if len(t_parts) == 2:
        time_str = f"{int(t_parts[0]):02d}:{int(t_parts[1]):02d}:00"
    elif len(t_parts) == 3:
        try:
            time_str = f"{int(t_parts[0]):02d}:{int(t_parts[1]):02d}:{int(t_parts[2]):02d}"
        except Exception:
            time_str = "00:00:00"
    else:
        time_str = "00:00:00"
    return f"{date_str} {time_str}"


def parse_resume_dates(text: str, fallback_date: str) -> tuple[str, str, str, str]:
    m_up = re.search(r"(?:简历)?更新[日时]?[期间]?[：\s]*((?:19|20)\d{2}[./年-]\d{1,2}[./年-]\d{1,2}(?:\s+\d{1,2}:\d{1,2}(?::\d{1,2})?)?)", text, re.I)
    if not m_up:
        m_up = re.search(r"((?:19|20)\d{2}-\d{2}-\d{2}\s+\d{2}:\d{2}(?::\d{2})?)", text[:500])
    if m_up:
        raw_up = m_up.group(1).strip()
        updated_date = standardize_datetime(raw_up)
        updated_source = "文档正文更新时间"
    else:
        updated_date = fallback_date
        updated_source = "HTML文件修改时间（历史资料替代）"
    m_dl = re.search(r"(?:简历)?(?:下载|投递)[日时]?[期间]?[：\s]*((?:19|20)\d{2}[./年-]\d{1,2}[./年-]\d{1,2}(?:\s+\d{1,2}:\d{1,2}(?::\d{1,2})?)?)", text, re.I)
    if m_dl:
        raw_dl = m_dl.group(1).strip()
        download_date = standardize_datetime(raw_dl)
        download_source = "文档正文下载/投递时间"
    else:
        download_date = fallback_date
        download_source = "HTML文件修改时间（历史资料替代）"
    return updated_date, download_date, updated_source, download_source


# =============================================================================
# 文本预处理三连：宏清理 / 51job 日期断行合并 / 智联粘连拆分
# =============================================================================
# EN: =============================================================================
#     Three text pre-processing steps: macro cleanup / 51job date line-break joining / Zhaopin unsticking
#     =============================================================================
# JA: =============================================================================
#     テキストの前処理 3 段階：マクロの除去 / 51job の日付の改行の結合 / Zhaopin のくっつきの分離
#     =============================================================================

def html_to_plain_text(html_text: str) -> str:
    if not html_text:
        return ""
    # Step 1: BeautifulSoup 基本 DOM→文本
    # EN: Step 1: basic BeautifulSoup DOM → text
    # JA: Step 1：BeautifulSoup による基本的な DOM → テキスト
    if BeautifulSoup is not None:
        try:
            soup = BeautifulSoup(html_text, "html.parser")
            for tag in soup(["script", "style", "xml", "meta", "link", "head"]):
                tag.decompose()
            for td in soup.find_all(["td", "th"]):
                td.append("  ")
            for tr in soup.find_all("tr"):
                tr.append("\n")
            for p in soup.find_all(["p", "div", "h1", "h2", "h3", "h4", "li", "br"]):
                p.append("\n")
            raw = soup.get_text("\n")
        except Exception:
            raw = re.sub(r"<[^>]+>", "\n", html_text)
    else:
        raw = re.sub(r"<[^>]+>", "\n", html_text)
    # 清理 Word 宏残留
    # EN: Clean Word macro leftovers
    # JA: Word マクロの残骸を除去する
    raw = re.sub(r'INCLUDEPICTURE\s+"cid:[^"]*"\s+\\\*\s*MERGEFORMAT\s*', "", raw)
    raw = re.sub(r'PAGE\s+\\\*\s*MERGEFORMAT\s*\d*', "", raw)
    raw = re.sub(r'HYPERLINK\s+"[^"]*"\s+\\o\s+"[^"]*"\s*', "", raw)
    raw = re.sub(r'HYPERLINK\s+"[^"]*"\s+\\l\s+"[^"]*"\s+\\t\s+"[^"]*"\s*', "", raw)
    raw = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", raw)
    raw = raw.translate(str.maketrans("０１２３４５６７８９", "0123456789"))
    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    text = "\n".join(lines)
    # Step 2: 51job 日期断行合并
    # EN: Step 2: 51job date line-break joining
    # JA: Step 2：51job の日付の改行の結合
    text = _merge_51job_date_breaks(text)
    # Step 3: 智联粘连文本拆分（板块标题/字段标签前插换行）
    # EN: Step 3: Zhaopin stuck-text splitting (insert line breaks before section headings / field labels)
    # JA: Step 3：Zhaopin のくっついたテキストの分離（セクション見出し・フィールドのラベルの前に改行を入れる）
    text = _preprocess_glued_text(text)
    # Step 4: 通用日期规范化
    # EN: Step 4: generic date normalisation
    # JA: Step 4：汎用的な日付の正規化
    text = re.sub(r"(\d{4}[./．]\d{1,2})([A-Za-z])", r"\1 \2", text)
    text = re.sub(r"(\d{4}\.\d{2})\s*[-—–~～至到]+\s*(\d{4}\.\d{2})", r"\1 - \2", text)
    text = re.sub(
        r"(\d{4}\.\d{2})\s*[-—–~～至到]+\s*(至今|现在|目前|Present|Current)",
        r"\1 - 至今", text, flags=re.I,
    )
    return text


def _merge_51job_date_breaks(text: str) -> str:
    lines = text.split("\n")
    merged: list[str] = []
    i = 0
    while i < len(lines):
        cur = lines[i]
        if i + 1 < len(lines) and re.fullmatch(r"(?:19|20)\d{2}", cur):
            nxt = lines[i + 1]
            if re.match(r"/\d", nxt):
                cur = cur + nxt
                i += 1
        m = re.search(r"(?:--|[-—–~～至到一])(?:19|20)\d{2}$", cur)
        if m and i + 1 < len(lines) and re.match(r"/\d", lines[i + 1]):
            cur = cur + lines[i + 1]
            i += 1
        if re.fullmatch(r"(?:19|20)\d{2}", cur) and i + 2 < len(lines):
            mid = lines[i + 1]
            tail = lines[i + 2]
            if re.match(r"/\d.+(?:19|20)\d{2}$", mid) and re.match(r"/\d", tail):
                cur = cur + mid + tail
                i += 2
        # 新增：日期断行合并（只在「YYYY.MM」后接「- YYYY.MM」+下一行是学校/公司名（非另一个日期行）时合并）
        # 当前行是「YYYY.MM」
        # EN: New: date line-break joining (only when "YYYY.MM" is followed by "- YYYY.MM" and the next line is a school/company name (not another date line))
        #     The current line is "YYYY.MM"
        # JA: 追加：日付の改行の結合（「YYYY.MM」の後に「- YYYY.MM」が続き、次の行が学校名・会社名（別の日付行ではない）の場合だけ結合）
        #     現在の行が「YYYY.MM」
        if re.fullmatch(r"(?:19|20)\d{2}[./]\d{1,2}", cur):
            if i + 1 < len(lines):
                nxt1 = lines[i + 1]
                m_dash = re.match(
                    r"^[-—–~～]+\s*((?:19|20)\d{2}[./]\d{1,2}|至今|现在|目前)$",
                    nxt1,
                )
                if m_dash:
                    # i+2 必须存在，且不是另一个 YYYY.MM 日期行（避免把刘孝乐的两个独立教育段粘一起）
                    # EN: i+2 must exist and must not be another YYYY.MM date line (to avoid gluing together two independent education entries, as in a past case)
                    # JA: i+2 が存在し、別の YYYY.MM の日付行ではないこと（過去の事例のように独立した 2 件の学歴をつなげてしまうのを防ぐ）
                    if (
                        i + 2 < len(lines)
                        and not re.fullmatch(r"(?:19|20)\d{2}[./]\d{1,2}", lines[i + 2])
                        and not re.match(
                            r"^[-—–~～]+\s*(?:(?:19|20)\d{2}[./]\d{1,2}|至今|现在|目前)$",
                            lines[i + 2],
                        )
                    ):
                        cur = cur + " " + nxt1 + " " + lines[i + 2]
                        i += 2
                    else:
                        cur = cur + " " + nxt1
                        i += 1
        # 新增2：「YYYY.MM - YYYY.MM」或「YYYY.MM - 至今」独占行 + 下一行是学校/公司信息（非日期段）时，合并
        # 对应格式：
        #   2013.04 - 2015.03
        #   東京スクールオブビジネス其他 大专
        # 两行一组。
        # EN: New 2: a line containing only "YYYY.MM - YYYY.MM" or "YYYY.MM - 至今" + the next line is school/company info (not a date range) → merge
        #     Corresponding format:
        #       2013.04 - 2015.03
        #       東京スクールオブビジネス其他 大专
        #     Two lines form a group.
        # JA: 追加 2：「YYYY.MM - YYYY.MM」か「YYYY.MM - 至今」だけの行 + 次の行が学校・会社の情報（期間ではない）→ 結合
        #     対応する形式：
        #       2013.04 - 2015.03
        #       東京スクールオブビジネス其他 大专
        #     2 行で 1 組。
        if re.fullmatch(
            r"(?:19|20)\d{2}[./]\d{1,2}\s*[-—–~～]+\s*((?:19|20)\d{2}[./]\d{1,2}|至今|现在|目前)",
            cur,
        ):
            if (
                i + 1 < len(lines)
                and not re.fullmatch(
                    r"(?:19|20)\d{2}[./]\d{1,2}\s*[-—–~～]+\s*((?:19|20)\d{2}[./]\d{1,2}|至今|现在|目前)",
                    lines[i + 1],
                )
                and not re.fullmatch(r"(?:19|20)\d{2}[./]\d{1,2}", lines[i + 1])
            ):
                cur = cur + " " + lines[i + 1]
                i += 1
        merged.append(cur)
        i += 1
    return "\n".join(merged)


def _preprocess_glued_text(text: str) -> str:
    if not text:
        return text
    section_headers = [
        "在校学习情况", "在校实践经历", "特长职业目标", "所获证书",
        "工作经历", "教育经历", "项目经历", "语言能力", "专业技能",
        "自我评价", "求职意向", "培训经历", "活动描述", "兴趣爱好", "特长",
    ]
    field_labels = [
        "期望工作地区", "期望工作性质", "期望从事职业", "期望从事行业",
        "期望月薪", "目前状况",
        "简历更新时间", "简历下载时间", "简历名称",
        "工作描述", "证书说明", "企业性质", "规模", "分数",
        "培训机构", "培训地点", "培训描述",
    ]
    lang_names = ["西班牙语", "意大利语", "葡萄牙语", "阿拉伯语",
                  "英语", "日语", "德语", "法语", "韩语", "俄语", "普通话", "粤语"]
    result = text
    headers_sorted = sorted(section_headers, key=len, reverse=True)
    header_pattern = "|".join(re.escape(h) for h in headers_sorted)
    result = re.sub(rf"(?<=[^\n])[ \t]*({header_pattern})(?=\s|$)", r"\n\1", result)
    labels_sorted = sorted(field_labels, key=len, reverse=True)
    label_pattern = "|".join(re.escape(l) for l in labels_sorted)
    result = re.sub(rf"(?<=[^\n])[ \t]*({label_pattern})([：:])", r"\n\1\2", result)
    langs_sorted = sorted(lang_names, key=len, reverse=True)
    lang_pattern = "|".join(re.escape(l) for l in langs_sorted)
    result = re.sub(rf"(?<=[^\n])[ \t]*({lang_pattern})([：:])", r"\n\1\2", result)
    result = re.sub(r"([。．\.]\s*)证书(?=\n|$)", r"\1\n证书", result)
    return result


# =============================================================================
# 平台来源自动识别（从 raw_text 关键词判断）
# =============================================================================
# EN: =============================================================================
#     Automatic detection of the source platform (judged from raw_text keywords)
#     =============================================================================
# JA: =============================================================================
#     取得元プラットフォームの自動識別（raw_text のキーワードから判定）
#     =============================================================================

def detect_platform(text: str, filename: str) -> str:
    fn = filename.lower()
    t_lower = text[:3000].lower()
    if "liepin" in fn or "猎聘" in text:
        return "猎聘网"
    if "51job" in fn or "前程无忧" in text or "job.51job.com" in t_lower:
        return "51job"
    if "智联" in text or "zhaopin" in fn:
        return "智联招聘"
    if "newpage" in fn or "newpage" in t_lower:
        return "Newpage"
    return "Web"


# =============================================================================
# 学历 rank 归一化（1-7）
# =============================================================================
# EN: =============================================================================
#     Degree rank normalisation (1-7)
#     =============================================================================
# JA: =============================================================================
#     学歴ランクの正規化（1〜7）
#     =============================================================================

def normalize_degree_rank(deg: str) -> tuple[str, str]:
    degree_rank = {
        "博士后": "7", "博士": "6", "phd": "6", "doctor": "6",
        "硕士": "5", "修士": "5", "研究生": "5", "mba": "5", "emba": "5", "master": "5", "ma": "5", "ms": "5", "大学院": "5",
        "本科": "4", "学士": "4", "大卒": "4", "bachelor": "4", "bs": "4", "ba": "4",
        "大专": "3", "专科": "3", "短大": "3", "大専": "3", "associate": "3", "diploma": "3",
        "高中": "2", "中专": "2", "职高": "2", "中学": "2", "high school": "2", "中級専門学校": "2", "専門学校": "2",
        "初中": "1", "小学": "1",
    }
    etype_map = {
        "7": "全日制研究生", "6": "全日制研究生", "5": "全日制研究生",
        "4": "全日制大学", "3": "全日制大专", "2": "全日制高中", "1": "全日制初中及以下",
    }
    deg_clean = re.sub(r"[（(].*?[)）]", "", deg or "").strip().lower()
    rank = degree_rank.get(deg_clean, "")
    if not rank:
        for key, val in degree_rank.items():
            if key in deg_clean:
                rank = val
                break
    etype = etype_map.get(rank, "")
    return rank, etype


# =============================================================================
# 个人素质关键词 → 移入 base_info.pr；动作短语过滤
# =============================================================================
# EN: =============================================================================
#     Personal-quality keywords → move into base_info.pr; action-phrase filtering
#     =============================================================================
# JA: =============================================================================
#     個人の資質のキーワード → base_info.pr に移す。動作の語句の除外
#     =============================================================================

PERSONAL_QUALITY_ZH = (
    "沟通能力", "团队精神", "团队协作", "责任心", "责任感", "抗压能力", "学习能力",
    "适应能力", "执行力", "创新能力", "逻辑思维", "分析能力", "解决问题",
    "人际沟通", "表达能力", "组织协调", "时间管理", "自我驱动", "积极主动",
    "认真负责", "细心严谨", "诚实守信", "吃苦耐劳", "踏实肯干", "敬业精神",
    "服务意识", "客户导向", "结果导向", "成本意识", "质量意识", "安全意识",
    "沟通", "协作", "负责", "细心", "耐心", "主动", "热情", "乐观", "开朗",
)

ACTION_PHRASE_RE = re.compile(
    r"^(负责|每天|上交|主导|牵头|跟进|推进|协助|组织|制定|编写|撰写|设计|开发|测试|"
    r"维护|管理|协调|完成|参与|建立|收集|提供|推广|改善|提高|拓展|沟通|策划|运营|"
    r"建设|预算|参加|支持|调研|分析|汇报|上报|交给|提交|报送|安排|布置|督促|检查|"
    r"落实|执行|实施|处理|解决|优化|改造|升级|部署|培训|指导|带领|招聘|面试)\s*[.。,，、]?"
)

LONG_SENTENCE_RE = re.compile(r"[，,。.；;！!？?]")


def filter_skills_and_move_pr(
    skills_list: list[dict[str, Any]],
    base_info: dict[str, Any],
    platform: str,
) -> list[dict[str, Any]]:
    """① 51job → 强制返回 []；② 个人素质词移到 base_info.pr；③ 动作短语过滤；④ 长句过滤。

    EN: ① 51job → force []; ② move personal-quality words to base_info.pr; ③ filter action phrases; ④ filter long sentences.

    JA: ① 51job → [] を強制、② 個人の資質の語を base_info.pr に移す、③ 動作の語句を除外、④ 長い文を除外。
    """
    if platform == "51job":
        return []
    pr_existing = (base_info.get("pr") or "").strip()
    pr_items: list[str] = [x for x in pr_existing.split("、") if x] if pr_existing else []
    kept: list[dict[str, Any]] = []
    for sk in skills_list or []:
        if not isinstance(sk, dict):
            continue
        # 移除子对象中的 raw_text
        # EN: Remove raw_text from sub-objects
        # JA: サブオブジェクトから raw_text を削除する
        sk.pop("raw_text", None)
        name = (sk.get("skill_name") or "").strip()
        if not name:
            continue
        # ① 是否是个人素质关键词（全词或包含匹配）
        # EN: ① Whether it is a personal-quality keyword (whole-word or containment match)
        # JA: ① 個人の資質のキーワードか（完全一致または包含でのマッチ）
        is_pq = False
        for kw in PERSONAL_QUALITY_ZH:
            if name == kw or (len(kw) >= 4 and kw in name):
                is_pq = True
                break
        if is_pq:
            if name not in pr_items:
                pr_items.append(name)
            continue
        # ② 动作短语开头（负责…每天…上交…）
        # EN: ② Starts with an action phrase (负责… 每天… 上交…: responsible for… / every day… / handed in…)
        # JA: ② 動作の語句で始まる（负责… 每天… 上交…：〜を担当／毎日〜／〜を提出）
        if ACTION_PHRASE_RE.match(name):
            continue
        # ③ 句子含多个标点（长句/职责句，非技能名）
        # EN: ③ The sentence contains several punctuation marks (a long/duty sentence, not a skill name)
        # JA: ③ 文に複数の句読点がある（長い文・職務の文で、スキル名ではない）
        if len(LONG_SENTENCE_RE.findall(name)) >= 1 and len(name) > 15:
            continue
        # ④ 长度 1-30 字兜底过滤
        # EN: ④ Fallback filter on length 1-30 characters
        # JA: ④ 長さ 1〜30 文字による最終手段のフィルター
        if len(name) > 40 or len(name) < 1:
            continue
        kept.append(sk)
    base_info["pr"] = "、".join(pr_items)
    return kept


# =============================================================================
# 递归清理：删除所有子对象中的 raw_text 字段
# =============================================================================
# EN: =============================================================================
#     Recursive cleanup: delete the raw_text field from all sub-objects
#     =============================================================================
# JA: =============================================================================
#     再帰的な整理：すべてのサブオブジェクトから raw_text フィールドを削除する
#     =============================================================================

def _recursive_strip_raw_text(obj: Any) -> None:
    if isinstance(obj, dict):
        obj.pop("raw_text", None)
        for v in obj.values():
            _recursive_strip_raw_text(v)
    elif isinstance(obj, list):
        for item in obj:
            _recursive_strip_raw_text(item)


# =============================================================================
# 顶层结构强制重构（最关键的质量闸门）
# =============================================================================
# EN: =============================================================================
#     Forced rebuild of the top-level structure (the most critical quality gate)
#     =============================================================================
# JA: =============================================================================
#     トップレベル構造の強制的な再構築（最も重要な品質ゲート）
#     =============================================================================

EMPTY_EDUCATION_INFO = {
    "school_name": "",
    "school_major_name": "",
    "school_degree_type": "",
    "school_degree_rank": "",
    "school_education_type": "",
    "school_start_ym": "",
    "school_end_ym": "",
}

EMPTY_CURRENT_INFO = {
    "company_name": "",
    "company_employees": "",
    "company_industry": "",
    "position": "",
    "position_type": "",
    "position_salary": "",
    "position_dept": "",
    "position_report_to": "",
    "position_subordinate": "",
    "employment_type": "全职",
    "annual_salary_min": "",
    "annual_salary_max": "",
    "status": "",
    "position_start": "",
    "position_resigned": "",
}

EXPECTED_INFO_8_KEYS = [
    "expected_city", "expected_position", "expected_salary",
    "expected_annual_salary_min", "expected_annual_salary_max",
    "expected_industry", "expected_employment_type", "expected_start_date",
]


def _is_only_punct_noise(s: str) -> bool:
    """判断 s 是否「全是标点/括号/空白/符号」无任何实质内容（中文/数字/英文字母）。长度<=10 快速短路。

    EN: Decide whether s is "all punctuation/brackets/whitespace/symbols" with no substantive content (Chinese/digits/English letters). Fast short-circuit for length <= 10.

    JA: s が「句読点・括弧・空白・記号だけ」で実質的な内容（漢字・数字・英字）がないかを判定する。長さ 10 以下は高速に判定を打ち切る。
    """
    if not s:
        return True
    s = s.strip()
    if not s:
        return True
    if len(s) > 10:
        # 过长一般不是噪声（防止误伤真实专业/学校名带标点）
        # EN: Overly long values are usually not noise (to avoid harming real major/school names with punctuation)
        # JA: 長すぎる値は通常ノイズではない（句読点を含む本当の専攻名・学校名を誤って傷つけないため）
        return False
    for ch in s:
        if ("\u4e00" <= ch <= "\u9fff") or ch.isdigit() or ("a" <= ch.lower() <= "z"):
            return False
    return True


def _clean_edu_school_major_noise(e: dict[str, Any]) -> dict[str, Any]:
    """对 7 字段教育条目做一轮「短噪声」清理：school/major/degree 里只有括号/标点 → 置空；再 fallback 从 school 尾部扒专业。

    EN: Run one round of "short noise" cleanup on 7-field education entries: school/major/degree consisting only of brackets/punctuation → clear; then fall back to digging the major out of the tail of school.

    JA: 7 フィールドの学歴の項目に「短いノイズ」の除去を 1 回行う：school/major/degree が括弧・句読点だけ → 空にする。その後 school の末尾から専攻を取り出す最終手段を行う。
    """
    MAJOR_KEYWORDS = ("专业", "文学", "工程", "管理", "技术", "系", "经济", "法学", "理学", "医学", "艺术", "教育", "金融", "会计", "计算机", "软件", "机械", "电子", "自动化")
    SCHOOL_SUFFIXES = ("大学", "学院", "学校", "分校", "高中", "中学", "小学")
    DEGREE_WORDS = ("博士后", "博士", "硕士", "本科", "大专", "专科", "中专", "职高", "高中", "初中", "小学")
    e = dict(e)
    # 1) 噪声清洗
    # EN: 1) Noise cleaning
    # JA: 1) ノイズのクレンジング
    for k in ("school_name", "school_major_name", "school_degree_type", "school_education_type"):
        v = (e.get(k) or "").strip()
        if _is_only_punct_noise(v):
            e[k] = ""
    school = (e.get("school_name") or "").strip()
    major = (e.get("school_major_name") or "").strip()
    degree = (e.get("school_degree_type") or "").strip()
    # 2) 从 school_name 尾部 fallback 扒专业（如果专业空且 school 长）
    # EN: 2) Fall back to digging the major out of the tail of school_name (if the major is empty and school is long)
    # JA: 2) school_name の末尾から専攻を取り出す最終手段（専攻が空で school が長い場合）
    if (not major) and school and any(suf in school for suf in SCHOOL_SUFFIXES):
        m = re.match(r"^(.*?(?:大学|学院|学校|分校|高中|中学|小学))\s*(.*)$", school)
        if m and m.group(2).strip():
            tail = m.group(2).strip()
            tail_deg = ""
            # 从 tail 里剥学位词
            # EN: Strip degree words from the tail
            # JA: tail から学位の語を除く
            tail_clean = tail
            for dw in sorted(DEGREE_WORDS, key=len, reverse=True):
                if tail_clean.endswith(dw):
                    tail_deg = dw
                    tail_clean = tail_clean[: -len(dw)].strip(" ·|｜-—_\t,，、()（）")
                    break
            if tail_clean and tail_clean not in ("统招", "全日制", "自考", "成教", "其他", "在职", "脱产", "业余"):
                major = tail_clean
                e["school_major_name"] = major
            if tail_deg and not degree:
                e["school_degree_type"] = tail_deg
            e["school_name"] = m.group(1).strip()
    # 3) major 里若仍有学位词，剥掉
    # EN: 3) If the major still contains degree words, strip them
    # JA: 3) major にまだ学位の語があれば除く
    cur_major = (e.get("school_major_name") or "").strip()
    if cur_major:
        for dw in sorted(DEGREE_WORDS, key=len, reverse=True):
            if cur_major.endswith(dw):
                cur_major = cur_major[: -len(dw)].strip(" ·|｜-—_\t,，、()（）")
                break
        if _is_only_punct_noise(cur_major):
            cur_major = ""
        e["school_major_name"] = cur_major
    # 4) 再跑一次 degree → rank/etype（如果原先 degree 被噪声清空又 fallback 补回来）
    # EN: 4) Run degree → rank/etype once more (if degree was cleared by noise cleaning and then filled back by the fallback)
    # JA: 4) degree → rank/etype をもう一度実行する（degree がノイズ除去で空にされ、最終手段で補い戻された場合）
    deg2 = (e.get("school_degree_type") or "").strip()
    if deg2:
        r2, et2 = normalize_degree_rank(deg2)
        if r2:
            e["school_degree_rank"] = r2
            if not (e.get("school_education_type") or "").strip() or e.get("school_education_type") in ("全日制", "全日制大学", "全日制研究生"):
                e["school_education_type"] = et2
    return e


def _pick_highest_education(education_list: list[dict[str, Any]]) -> dict[str, Any]:
    """从 education_list 中按 school_degree_rank 取最高，rank 相同按时间**最新**优先（end_ym 大的在前）。

    EN: From education_list take the highest by school_degree_rank; for equal ranks prefer the **newest** by time (larger end_ym first).

    JA: education_list から school_degree_rank が最も高いものを取り、rank が同じなら時期が**最新**のもの（end_ym が大きいもの）を優先する。
    """
    if not education_list:
        return copy.deepcopy(EMPTY_EDUCATION_INFO)
    def _sort_key(e: dict[str, Any]):
        r = (e.get("school_degree_rank") or "").strip()
        rank_val = int(r) if r.isdigit() else 0
        # end_ym 如果有 norm_date_str 就转成可比的月整数 YYYY*12+MM；没有就 0
        # EN: If end_ym has a norm_date_str, convert it to a comparable month integer YYYY*12+MM; otherwise 0
        # JA: end_ym に norm_date_str があれば比較可能な月の整数 YYYY*12+MM に変換し、なければ 0
        end_key = 0
        nd = norm_date_str(e.get("school_end_ym") or "")
        if nd:
            try:
                end_key = int(nd[:4]) * 12 + int(nd[5:7])
            except Exception:
                end_key = 0
        # 负 rank 升序 → rank 高前；负 end_key 升序 → end 大前
        # EN: Negative rank ascending → higher rank first; negative end_key ascending → later end first
        # JA: rank の符号を反転して昇順 → rank の高いものが先、end_key の符号を反転して昇順 → end の遅いものが先
        return (-rank_val, -end_key)
    sorted_edu = sorted(education_list, key=_sort_key)
    best = sorted_edu[0]
    result = copy.deepcopy(EMPTY_EDUCATION_INFO)
    for k in result.keys():
        v = best.get(k)
        if v is not None:
            result[k] = str(v).strip() if isinstance(v, (str, int, float)) else v
    # 最终确保 7 字段齐全，不多不少
    # EN: Finally make sure exactly the 7 fields are present, no more, no less
    # JA: 最後に 7 フィールドが過不足なく揃っていることを保証する
    result = {k: result.get(k, "") for k in EMPTY_EDUCATION_INFO.keys()}
    # sd.education_info 双保险：噪声清理 + 尾部扒专业
    # EN: Double safety for sd.education_info: noise cleaning + digging the major out of the tail
    # JA: sd.education_info の二重の保険：ノイズの除去 + 末尾から専攻を取り出す
    result = _clean_edu_school_major_noise(result)
    return {k: result.get(k, "") for k in EMPTY_EDUCATION_INFO.keys()}


def _pick_latest_work(work_experiences: list[dict[str, Any]]) -> dict[str, Any]:
    if not work_experiences:
        return copy.deepcopy(EMPTY_CURRENT_INFO)
    # 默认第一段就是最新（解析器通常按时间倒序）
    # EN: By default the first entry is the newest (parsers usually order by time descending)
    # JA: 既定では最初の項目が最新（パーサーは通常新しい順に並べる）
    latest = work_experiences[0]
    result = copy.deepcopy(EMPTY_CURRENT_INFO)
    for k in result.keys():
        if k in latest and latest[k] is not None:
            result[k] = latest[k]
    return {k: result.get(k, (EMPTY_CURRENT_INFO.get(k, ""))) for k in EMPTY_CURRENT_INFO.keys()}


def _normalize_expected_info(raw_expected: dict[str, Any], raw_text_for_extract: str) -> dict[str, Any]:
    """补齐 8 字段；从 plain 直接提取求职意向表格（期望工作地区/月薪/从事职业/从事行业/工作性质/目前状况）。

    EN: Complete the 8 fields; extract the job-preference table directly from plain (desired work region / monthly salary / occupation / industry / job nature / current status).

    JA: 8 フィールドを補完する。plain から希望条件の表（希望勤務地・月給・職種・業界・雇用形態・現在の状況）を直接抽出する。
    """
    result = {k: "" for k in EXPECTED_INFO_8_KEYS}
    if isinstance(raw_expected, dict):
        for k in EXPECTED_INFO_8_KEYS:
            v = raw_expected.get(k)
            if v is not None and str(v).strip():
                result[k] = str(v).strip()
    # ============ 从 raw_text_for_extract 直接重新提取（智联招聘/51job/猎聘网通用） ============
    # EN: ============ Re-extract directly from raw_text_for_extract (shared by Zhaopin/51job/Liepin) ============
    # JA: ============ raw_text_for_extract から直接再抽出する（Zhaopin／51job／Liepin 共通）============
    def _pick(tag: str) -> str:
        m = re.search(rf"{tag}\s*[:：]\s*([^\n]+)", raw_text_for_extract)
        if m:
            val = m.group(1).strip()
            val = re.sub(r"\s+", " ", val).strip(" |｜/·\t\r\n")
            return val
        return ""
    # 期望城市
    # EN: Desired city
    # JA: 希望勤務地
    if not result["expected_city"]:
        result["expected_city"] = _pick("期望工作地区")
    # 期望从事职业
    # EN: Desired occupation
    # JA: 希望職種
    if not result["expected_position"]:
        result["expected_position"] = _pick("期望从事职业") or _pick("期望职位")
    # 期望月薪
    # EN: Desired monthly salary
    # JA: 希望月給
    if not result["expected_salary"]:
        result["expected_salary"] = _pick("期望月薪")
    # 期望行业
    # EN: Desired industry
    # JA: 希望業界
    if not result["expected_industry"]:
        result["expected_industry"] = _pick("期望从事行业") or _pick("期望行业")
    # 期望工作性质 → employment_type
    # EN: Desired job nature → employment_type
    # JA: 希望する雇用形態 → employment_type
    if not result["expected_employment_type"]:
        result["expected_employment_type"] = _pick("期望工作性质")
    # 期望年薪（从月薪估算）
    # EN: Desired annual salary (estimated from the monthly salary)
    # JA: 希望年収（月給から推定）
    sal_text = result["expected_salary"]
    if sal_text and (not result["expected_annual_salary_min"] or not result["expected_annual_salary_max"]):
        nums = re.findall(r"\d+", sal_text.replace(",", ""))
        if len(nums) >= 2 and "元/月" in sal_text:
            try:
                low, high = int(nums[-2]), int(nums[-1])
                if low < 1000: low *= 1000
                if high < 1000: high *= 1000
                result["expected_annual_salary_min"] = str(low * 12)
                result["expected_annual_salary_max"] = str(high * 12)
            except Exception:
                pass
    # 到岗时间兜底：从「目前状况：XXX」提取
    # EN: Start-date fallback: extract from "目前状况：XXX" (current status: XXX)
    # JA: 入社可能時期の最終手段：「目前状况：XXX」（現在の状況：XXX）から抽出する
    if not result["expected_start_date"]:
        status_val = _pick("目前状况") or _pick("当前状态") or _pick("到岗时间")
        if status_val:
            if status_val in ("可立即上岗", "随时到岗", "即时到岗", "立即到岗", "随时上岗"):
                result["expected_start_date"] = "随时到岗"
            elif "一个月" in status_val or "1个月" in status_val or "1 个月" in status_val:
                result["expected_start_date"] = "1个月内到岗"
            elif "两周" in status_val or "2周" in status_val or "半个月" in status_val:
                result["expected_start_date"] = "两周内到岗"
            elif "三个月" in status_val or "3个月" in status_val:
                result["expected_start_date"] = "3个月内到岗"
            else:
                result["expected_start_date"] = status_val[:20]
    return result


def _normalize_education_list_and_fix_rank(raw_list: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """① 学校/专业颠倒智能纠偏；② 7字段强制；③ rank 1-7 归一化；④ 删除 raw_text；⑤ 学校名含"培训机构"时只保留带后缀的学校；⑥ 去掉公司/单位/协会/职务等非学历条目（zhilian fallback 误抽工作段）。

    EN: ① smart correction of swapped school/major; ② force 7 fields; ③ normalise rank to 1-7; ④ delete raw_text; ⑤ when the school name contains "培训机构" (training institution), keep only schools with a suffix; ⑥ remove non-education entries such as companies/units/associations/posts (work entries mis-extracted by the zhilian fallback).

    JA: ① 学校と専攻の取り違えを賢く補正、② 7 フィールドを強制、③ rank を 1〜7 に正規化、④ raw_text を削除、⑤ 学校名に「培训机构」（研修機関）を含む場合は接尾辞付きの学校だけを残す、⑥ 会社・団体・協会・役職などの学歴でない項目を除く（zhilian の最終手段が職歴を誤抽出したもの）。
    """
    if not raw_list:
        return []
    fixed_list = []
    MAJOR_KEYWORDS = ("专业", "文学", "工程", "管理", "技术", "系", "经济", "法学", "理学", "医学", "艺术", "教育", "金融", "会计", "计算机", "软件", "机械", "电子", "自动化")
    SCHOOL_SUFFIXES = ("大学", "学院", "学校", "分校", "高中", "中学", "小学")
    DEGREE_WORDS = ("博士后", "博士", "硕士", "本科", "大专", "专科", "中专", "职高", "高中", "初中", "小学")
    # 企业/单位/组织后缀 — school_name 里含这些且不含 SCHOOL_SUFFIXES → 判为工作段/单位误抽
    # EN: Enterprise/unit/organisation suffixes — if school_name contains these and not SCHOOL_SUFFIXES → judged a work entry / employer extracted by mistake
    # JA: 企業・団体・組織の接尾辞 — school_name にこれらがあり SCHOOL_SUFFIXES がない → 職歴・勤務先の誤抽出と判定する
    COMPANY_OR_ORG_SUFFIXES = (
        "有限公司", "有限责任公司", "股份有限公司", "集团", "公司", "银行", "医院", "学校",  # "学校" 可能和 SCHOOL_SUFFIXES 冲突，前面先判 SCHOOL 优先
        # EN: "学校" (school) may conflict with SCHOOL_SUFFIXES; SCHOOL is checked first and takes priority
        # JA: 「学校」は SCHOOL_SUFFIXES と衝突することがあるため、先に SCHOOL を判定して優先する
        "厂", "店", "宾馆", "酒店", "超市", "商场", "出版社", "报社", "杂志社", "电视台", "电台",
        "事务所", "律师所", "工作室", "中心", "站", "队", "局", "院", "所", "部", "厅",
        "协会", "学会", "研究会", "商会", "联合会", "基金会", "工会", "委员会", "团委会", "团委",
        "科技", "贸易", "商贸", "实业", "投资", "咨询", "广告", "传媒", "文化",
    )
    # 典型校园/学生组织职务词（school_name 或 major 里命中时，若没 SCHOOL_SUFFIXES → 整条丢）
    # EN: Typical campus/student-organisation post words (on a hit in school_name or major, if there are no SCHOOL_SUFFIXES → drop the whole entry)
    # JA: 典型的な学内・学生団体の役職の語（school_name か major にヒットし、SCHOOL_SUFFIXES がなければ → 項目全体を捨てる）
    OFFICE_TITLE_KEYWORDS = (
        "楼长", "副楼长", "班长", "副班长", "团支书", "团支部书记", "会长", "副会长", "部长",
        "副部长", "社长", "副社长", "主席", "副主席", "委员", "干事", "课代表",
        "组长", "副组长", "队长", "副队长", "部长助理", "办公室主任", "秘书长", "理事长",
        "副会长兼", "学生会", "社团",
    )
    for e in raw_list:
        if not isinstance(e, dict):
            continue
        e = dict(e)
        e.pop("raw_text", None)
        # 删除冗余字段：major_name / degree / school_start_date / school_end_date
        # EN: Delete redundant fields: major_name / degree / school_start_date / school_end_date
        # JA: 冗長なフィールドを削除する：major_name / degree / school_start_date / school_end_date
        for bad_key in ("major_name", "degree", "school_start_date", "school_end_date"):
            e.pop(bad_key, None)
        school = (e.get("school_name") or "").strip()
        major = (e.get("school_major_name") or "").strip()
        degree = (e.get("school_degree_type") or "").strip()

        # ============= 0.1) 整条丢弃：school_name 没 SCHOOL_SUFFIXES 但有公司/单位后缀 → zhilian 把工作段当教育（张连强：K.A.K / 宁波碧海服饰...）
        # EN: ============= 0.1) Drop the whole entry: school_name has no SCHOOL_SUFFIXES but has a company/unit suffix → zhilian took a work entry as education (a past case: K.A.K / 宁波碧海服饰...)
        # JA: ============= 0.1) 項目全体を捨てる：school_name に SCHOOL_SUFFIXES がなく会社・団体の接尾辞がある → zhilian が職歴を学歴と誤認（過去の事例：K.A.K / 宁波碧海服饰...）
        _has_school_suf = any(suf in school for suf in SCHOOL_SUFFIXES)
        _has_company_suf = False
        if not _has_school_suf:
            _has_company_suf = any(
                (school.endswith(suf) or suf + "有限" in school or school.find(suf) >= 0)
                for suf in COMPANY_OR_ORG_SUFFIXES
                if suf not in ("学校",)  # 学校后缀是 SCHOOL，不在这里算
                # EN: School suffixes are SCHOOL, not counted here
                # JA: 学校の接尾辞は SCHOOL なので、ここでは数えない
            )
        if _has_company_suf and not _has_school_suf:
            continue
        # ============= 0.2) 整条丢弃：school_name / major_name 是职务词 且 非 SCHOOL 后缀
        # EN: ============= 0.2) Drop the whole entry: school_name / major_name is a post word and not a SCHOOL suffix
        # JA: ============= 0.2) 項目全体を捨てる：school_name / major_name が役職の語で、SCHOOL の接尾辞ではない
        if not _has_school_suf:
            if any(kw in school for kw in OFFICE_TITLE_KEYWORDS):
                continue
            if any(kw in major for kw in OFFICE_TITLE_KEYWORDS):
                continue
        # ============= 0.2b) 即便 school 有学校后缀（真实学校），但 major 是校内职务词 且 degree_type/rank 全空 且 major 不含任何专业关键词 → 更像"上海大学 机器人协会副会长"这种校园经历误抽为教育，整条丢
        # EN: ============= 0.2b) Even if school has a school suffix (a real school), when major is a campus post word, degree_type/rank are all empty and major contains no major keyword → more like a campus experience such as "上海大学 机器人协会副会长" (Shanghai University, vice-president of the robotics association) mis-extracted as education; drop the whole entry
        # JA: ============= 0.2b) school に学校の接尾辞がある（本当の学校）場合でも、major が学内の役職の語で、degree_type/rank がすべて空、major に専攻のキーワードがまったくない → 「上海大学 机器人协会副会长」（上海大学 ロボット協会副会長）のような学内の経験が学歴として誤抽出されたものに近いので、項目全体を捨てる
        if _has_school_suf and major and any(kw in major for kw in OFFICE_TITLE_KEYWORDS) and not degree and not (e.get("school_degree_rank") or "").strip():
            if not any(mk in major for mk in MAJOR_KEYWORDS):
                continue
        # ============= 0.2c) 即便有学校后缀，major 是 section 头/简历头壳（如"在校情况"/"校内职务"）→ 丢
        # EN: ============= 0.2c) Even with a school suffix, if major is a section header / résumé header shell (e.g. "在校情况" (on-campus situation) / "校内职务" (campus posts)) → drop
        # JA: ============= 0.2c) 学校の接尾辞があっても、major がセクション見出しや履歴書の見出しの殻（例：「在校情况」（在学中の状況）／「校内职务」（学内の役職））→ 捨てる
        if _has_school_suf and major in ("在校情况", "在校学习情况", "校内职务", "校园职务", "学生会", "社团职务", "社团活动", "在校职务"):
            continue

        # ============= 0.3) 整条丢弃：school 是 "简历/简历内容/基本信息/个人信息" 等 section 壳
        # EN: ============= 0.3) Drop the whole entry: school is a section shell such as "简历/简历内容/基本信息/个人信息" (résumé / résumé content / basic info / personal info)
        # JA: ============= 0.3) 項目全体を捨てる：school が「简历／简历内容／基本信息／个人信息」（履歴書・履歴書の内容・基本情報・個人情報）などのセクションの殻
        _SHELL_NAMES = (
            "简历", "简历内容", "简 历", "个人简历", "个人信息", "基本信息", "个人资料", "基本资料", "简表",
            "校内职务", "校园职务", "社团职务", "学生会", "社团活动", "在校职务", "自我评价", "求职意向",
        )
        if school in _SHELL_NAMES or school.startswith("简 历"):
            continue

        # ============= 0) school_name 里出现 "培训机构" 但不含 SCHOOL_SUFFIXES → 这是培训段/语言培训误抽，这条丢（樱花日语培训机构 这种）
        # EN: ============= 0) school_name contains "培训机构" (training institution) but not SCHOOL_SUFFIXES → a training / language-training entry mis-extracted; drop this one (like a Japanese-language training institution)
        # JA: ============= 0) school_name に「培训机构」（研修機関）があり SCHOOL_SUFFIXES がない → 研修・語学研修の誤抽出なので、この項目を捨てる（日本語研修機関のようなもの）
        if (
            ("培训机构" in school or "培训学校" in school or "培训中心" in school)
            and not _has_school_suf
        ):
            continue
        # 另外：school 里有 "机构" 且不含 SCHOOL_SUFFIXES → 丢弃
        # EN: Also: school contains "机构" (institution) and not SCHOOL_SUFFIXES → drop
        # JA: さらに：school に「机构」（機関）があり SCHOOL_SUFFIXES がない → 捨てる
        if "机构" in school and not _has_school_suf:
            continue

        # ============= 1) 从 degree_type 里扒 school/major/degree（当 school 空，但 degree 含学校关键词）=============
        # EN: ============= 1) Dig school/major/degree out of degree_type (when school is empty but degree contains school keywords) =============
        # JA: ============= 1) degree_type から学校・専攻・学位を取り出す（school が空で degree に学校のキーワードがある場合）=============
        if not school and degree and any(suf in degree for suf in SCHOOL_SUFFIXES):
            # 先切 degree 尾部
            # EN: First cut the tail of degree
            # JA: まず degree の末尾を切る
            deg_tail = ""
            deg_remain = degree
            for dw in sorted(DEGREE_WORDS, key=len, reverse=True):
                if deg_remain.endswith(dw):
                    deg_tail = dw
                    deg_remain = deg_remain[: -len(dw)].strip(" ·|｜-—_\t")
                    break
            m_s = re.match(r"^(.*?(?:大学|学院|学校|分校|高中|中学|小学))\s*(.*)$", deg_remain)
            if m_s:
                s_tail = m_s.group(2).strip()
                e["school_name"] = m_s.group(1).strip()
                if s_tail == "其他":
                    s_tail = ""
                if s_tail and not major:
                    e["school_major_name"] = s_tail
                if deg_tail:
                    e["school_degree_type"] = deg_tail
            else:
                if deg_tail:
                    e["school_degree_type"] = deg_tail
        # 1b) 若 degree_type 里嵌了「姓名：... 学历：... 专业：...」这种表头（张连强类） → 直接从中抽出 degree / major，school 保留 (若 school 仍壳，则后面 fallback 会重跑)
        # EN: 1b) If degree_type has an embedded header like "姓名：... 学历：... 专业：..." (name/degree/major) (as in a past case) → extract degree / major directly from it and keep school (if school is still a shell, the later fallback reruns)
        # JA: 1b) degree_type に「姓名：... 学历：... 专业：...」（氏名・学歴・専攻）のような見出しが埋め込まれている場合（過去の事例）→ そこから degree / major を直接取り出し、school は残す（school がまだ殻なら後の最終手段で再実行する）
        if sum(1 for tag in ("姓名：", "学历：", "专业：", "年龄：", "身高：", "政治面貌：", "性别：", "电话：") if tag in degree) >= 2:
            m_d = re.search(r"学历[：:]\s*([^ 　\t\n\r|｜·/]+)", degree)
            if m_d:
                e["school_degree_type"] = m_d.group(1).strip()
            m_m = re.search(r"专业[：:]\s*([^ 　\t\n\r|｜·/]+(?:\s*[^ 　\t\n\r|｜·/]*)*)", degree)
            if m_m:
                e["school_major_name"] = m_m.group(1).strip()

        school = (e.get("school_name") or "").strip()
        major = (e.get("school_major_name") or "").strip()

        # 颠倒纠偏
        # EN: Correct swapped values
        # JA: 取り違えを補正する
        school_looks_major = (
            any(k in school for k in MAJOR_KEYWORDS)
            and not any(s.endswith(suf) for suf in SCHOOL_SUFFIXES for s in [school])
        )
        major_looks_school = any(major.endswith(suf) for suf in SCHOOL_SUFFIXES)
        if school_looks_major and major_looks_school:
            e["school_name"], e["school_major_name"] = major, school
        # 粘连拆分（山东交通学院 计算机科学与技术·本科·统招）
        # EN: Split stuck values (山东交通学院 计算机科学与技术·本科·统招)
        # JA: くっついた値を分ける（山东交通学院 计算机科学与技术·本科·统招）
        name = (e.get("school_name") or "").strip()
        if name and any(suf in name for suf in SCHOOL_SUFFIXES):
            m_split = re.match(r"^(.*?(?:大学|学院|学校|分校|高中|中学|小学))\s*(.*)$", name)
            if m_split and m_split.group(2).strip():
                tail = m_split.group(2).strip()
                tail_deg = ""
                tail_major = ""
                # 去掉"其他"伪专业词
                # EN: Remove the pseudo-major word "其他" (other)
                # JA: 偽の専攻の語「其他」（その他）を除く
                if tail == "其他":
                    tail = ""
                for sep in ("·", "｜", "|", " ", "-", "—"):
                    parts = [p.strip() for p in tail.split(sep) if p.strip()]
                    if len(parts) >= 2:
                        for p in parts:
                            if p in ("本科", "大专", "硕士", "博士", "专科", "中专", "高中", "统招", "全日制", "自考", "成教"):
                                tail_deg = p if p not in ("统招", "全日制", "自考", "成教") else (e.get("school_degree_type") or "")
                            elif p != "其他":
                                tail_major = p
                        break
                # 如果 parts 只有 1 个但没匹配学位，就是专业
                # EN: If parts has only 1 element and no degree matched, it is the major
                # JA: parts が 1 つだけで学位にマッチしなければ、それは専攻
                if not tail_major and tail and not any(
                    tail == kw
                    for kw in ("统招", "全日制", "自考", "成教", "其他", "")
                ):
                    if tail not in ("本科", "大专", "硕士", "博士", "专科", "中专", "高中"):
                        tail_major = tail
                if tail_major and not e.get("school_major_name"):
                    e["school_major_name"] = tail_major
                if tail_deg and not e.get("school_degree_type"):
                    e["school_degree_type"] = tail_deg
                e["school_name"] = m_split.group(1).strip()

        # ============= 2) school_name 正常 school_major_name 空时，从 school_name 的 tail 再扒一次（针对华东理工大学 生物化学与分子生物学 硕士 这种没空格切的） =============
        # EN: ============= 2) When school_name is normal and school_major_name is empty, dig once more from the tail of school_name (for cases without spaces like 华东理工大学 生物化学与分子生物学 硕士) =============
        # JA: ============= 2) school_name が正常で school_major_name が空の場合は、school_name の末尾からもう一度取り出す（「华东理工大学 生物化学与分子生物学 硕士」のように空白で切れていない場合向け）=============
        if (not (e.get("school_major_name") or "").strip()) and (
            e.get("school_degree_type") or ""
        ).strip():
            name2 = (e.get("school_name") or "").strip()
            if name2 and any(suf in name2 for suf in SCHOOL_SUFFIXES):
                m_split2 = re.match(
                    r"^(.*?(?:大学|学院|学校|分校|高中|中学|小学))\s*(.*)$", name2
                )
                if m_split2 and m_split2.group(2).strip():
                    tail2 = m_split2.group(2).strip()
                    if tail2 and tail2 not in ("其他",):
                        e["school_major_name"] = tail2
                        e["school_name"] = m_split2.group(1).strip()

        # ============= 3) major 尾部带 degree 词（如「生物化学与分子生物学硕士」）剥掉 degree 词 =============
        # EN: ============= 3) The major ends with a degree word (e.g. "生物化学与分子生物学硕士" — biochemistry and molecular biology + master); strip the degree word =============
        # JA: ============= 3) major の末尾に学位の語がある（例：「生物化学与分子生物学硕士」— 生化学・分子生物学 + 修士）→ 学位の語を除く =============
        cur_major = (e.get("school_major_name") or "").strip()
        if cur_major:
            for dw in sorted(DEGREE_WORDS, key=len, reverse=True):
                if cur_major.endswith(dw):
                    cur_major = cur_major[: -len(dw)].strip(" ·|｜-—_\t,，、")
                    break
            e["school_major_name"] = cur_major

        # degree_type → rank + education_type 归一化
        # EN: degree_type → normalise rank + education_type
        # JA: degree_type → rank と education_type を正規化する
        deg_type = (e.get("school_degree_type") or "").strip()
        rank, etype = normalize_degree_rank(deg_type)
        if rank:
            e["school_degree_rank"] = rank
            if not (e.get("school_education_type") or "").strip() or e.get("school_education_type") in ("全日制", "全日制大学", "全日制研究生"):
                e["school_education_type"] = etype
        else:
            # 已有的 rank 如果不是数字 1-7 则置空
            # EN: Clear an existing rank if it is not a digit 1-7
            # JA: 既存の rank が 1〜7 の数字でなければ空にする
            existing_rank = str(e.get("school_degree_rank") or "").strip()
            if existing_rank and existing_rank not in "1234567":
                e["school_degree_rank"] = ""
        # 最终强制 7 字段，不多不少
        # EN: Finally force exactly 7 fields, no more, no less
        # JA: 最後に 7 フィールドを過不足なく強制する
        final = {k: e.get(k, EMPTY_EDUCATION_INFO[k]) for k in EMPTY_EDUCATION_INFO.keys()}
        # 日期格式宽松归一化（YYYY.MM → YYYY-MM）
        # EN: Lenient date-format normalisation (YYYY.MM → YYYY-MM)
        # JA: 日付の形式の緩い正規化（YYYY.MM → YYYY-MM）
        for dk in ("school_start_ym", "school_end_ym"):
            v = str(final.get(dk) or "").strip()
            if v:
                m = re.fullmatch(r"((?:19|20)\d{2})[\./年](\d{1,2})(?:月)?", v)
                if m:
                    final[dk] = f"{int(m.group(1)):04d}-{int(m.group(2)):02d}"
        # ============= 最后一轮：短噪声清理（只有括号/标点的 school_name/major/degree → 清掉） =============
        # EN: ============= Last round: short-noise cleanup (school_name/major/degree consisting only of brackets/punctuation → clear) =============
        # JA: ============= 最後の段階：短いノイズの除去（括弧・句読点だけの school_name／major／degree → 空にする）=============
        final = _clean_edu_school_major_noise(final)
        fixed_list.append(final)
    return fixed_list


def norm_date_str(v: str) -> str:
    """宽松日期归一化：只取 YYYY-MM 部分；解析失败返回 ""。

    EN: Lenient date normalisation: take only the YYYY-MM part; returns "" if parsing fails.

    JA: 日付の緩い正規化：YYYY-MM の部分だけを取る。解析に失敗したら "" を返す。
    """
    if not v: return ""
    v = str(v).strip()
    # YYYY年MM月DD日 / YYYY年MM月
    # EN: YYYY年MM月DD日 / YYYY年MM月
    # JA: YYYY年MM月DD日 / YYYY年MM月
    m = re.match(r"^\s*((?:19|20)\d{2})\s*年\s*(\d{1,2})\s*月(?:\s*(\d{1,2})\s*日?)?\s*$", v)
    if m:
        return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}"
    m = re.match(r"^\s*((?:19|20)\d{2})[\./-](\d{1,2})(?:[\./-](\d{1,2}))?\s*$", v)
    if m:
        return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}"
    mm = re.search(r"((?:19|20)\d{2})\s*[/\-.年]\s*(\d{1,2})", v)
    if mm:
        return f"{int(mm.group(1)):04d}-{int(mm.group(2)):02d}"
    return ""


def month_distance(a: str, b: str) -> int:
    """a-b 月数差，解析失败返回 0。

    EN: Difference in months a-b; returns 0 if parsing fails.

    JA: a-b の月数の差。解析に失敗したら 0 を返す。
    """
    a = norm_date_str(a); b = norm_date_str(b)
    if not a or not b: return 0
    ay, am = int(a[:4]), int(a[5:7])
    by, bm = int(b[:4]), int(b[5:7])
    return (ay * 12 + am) - (by * 12 + bm)


def _swap_end_start_when_reversed(start: str, end: str, status: str = "") -> tuple[str, str]:
    """日期规范化 + start > end 时交换；若 status=在职且 end<start，不交换（end 空为"至今"）。

    EN: Normalise dates + swap when start > end; if status = 在职 (employed) and end < start, do not swap (an empty end means "至今" (present)).

    JA: 日付の正規化 + start > end なら入れ替える。status が 在职（在職中）で end < start の場合は入れ替えない（end が空なら「至今」（現在））。
    """
    if not start or not end:
        return start, end
    a = norm_date_str(start); b = norm_date_str(end)
    if not a or not b:
        return start, end
    if month_distance(b, a) < 0 and status not in ("在职", "在職", "on job", "employed"):
        # 交换
        # EN: Swap
        # JA: 入れ替える
        return end, start
    return start, end


def _normalize_training_list_cleanup(raw_list: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """training_list 清理：剥 raw_text、去掉伪条目（shell 条目/活动/奖励误抽为培训）、清理 org/tname 里的壳字段。

    EN: training_list cleanup: strip raw_text, remove pseudo entries (shell entries / activities / awards mis-extracted as training), clean shell fields in org/tname.

    JA: training_list の整理：raw_text を除き、偽の項目（殻の項目・活動・受賞が研修として誤抽出されたもの）を除き、org/tname の殻のフィールドを整理する。
    """
    if not raw_list:
        return []
    _BAD_HEADERS = (
        "活动描述：", "活动描述", "获奖情况", "获奖", "奖励", "荣誉", "实习经历", "在校", "其他", "▲其他",
        "技能/语言", "▲技能", "▲技能/语言", "专业技能", "技能", "证书", "▲证书", "所获证书", "语言能力",
    )
    _SHELL_ORGS = ("培训机构：", "培训机构", "培训机构:")
    _SHELL_TNAMES = ("培训地点：", "培训地点", "培训地点:", "培训描述：", "培训描述", "培训描述:", "培训机构：", "培训机构", "培训机构:")
    out: list[dict[str, Any]] = []
    TRAIN_FIELDS = ("sequence_no", "training_name", "organization_name", "start_ym", "end_ym",
                    "certificate_name", "description")
    for item in raw_list:
        if not isinstance(item, dict):
            continue
        t = dict(item)
        t.pop("raw_text", None)
        org: str = (t.get("organization_name") or "").strip()
        tname: str = (t.get("training_name") or "").strip()
        desc: str = (t.get("description") or "")
        desc_lines = [ln.strip() for ln in desc.splitlines() if ln.strip()]
        _shell_org = org in _SHELL_ORGS or (len(org) <= 10 and any(s in org for s in _SHELL_ORGS))
        _shell_tname = (tname in _SHELL_TNAMES) or (not tname) or (len(tname) <= 10 and any(s in tname for s in _SHELL_TNAMES))
        # 只要 org 或 tname 是壳，一律从 desc 拆真实字段（放宽条件，解决 49 次 shell 残留）
        # EN: Whenever org or tname is a shell, split the real fields out of desc (relaxed condition, fixing 49 leftover shells)
        # JA: org か tname が殻なら、一律に desc から本当のフィールドを分けて取る（条件を緩め、49 件の殻の残りを解消）
        if _shell_org or _shell_tname:
            if desc_lines:
                first_line = desc_lines[0].strip()
                date_prefix_re = re.compile(
                    r"^("
                    r"(?:19|20)\d{2}\s*[/\-.年]\s*\d{1,2}\s*(?:[/\-.]\s*\d{1,2})?\s*月?\s*[-~—至]\s*"
                    r"(?:(?:19|20)\d{2}\s*)?[/\-.年]?\s*\d{1,2}\s*(?:[/\-.]\s*\d{1,2})?\s*月?"
                    r")\s*(.*)$"
                )
                m_dt = date_prefix_re.match(first_line)
                rest = first_line
                start_ym = (t.get("start_ym") or "").strip()
                end_ym = (t.get("end_ym") or "").strip()
                if m_dt:
                    rest = m_dt.group(2).strip()
                    if not start_ym or not end_ym:
                        all_dates = re.findall(
                            r"(?:(?:19|20)\d{2}[/\-.年]\s*\d{1,2}(?:[/\-.]\s*\d{1,2})?|\d{4}[/-]\d{1,2}[/-]\d{1,2})",
                            first_line,
                        )
                        def norm_ym_loc(s: str) -> str:
                            s2 = re.sub(r"[年月]", "", s).replace(".", "-").replace("/", "-")
                            parts = [p for p in s2.split("-") if p]
                            if len(parts) >= 2:
                                return f"{parts[0]}-{parts[1].zfill(2)}"
                            return ""
                        if len(all_dates) >= 1 and not start_ym:
                            start_ym = norm_ym_loc(all_dates[0])
                        if len(all_dates) >= 2 and not end_ym:
                            end_ym = norm_ym_loc(all_dates[1])
                real_tname = rest
                idx_org = idx_place = idx_desc = -1
                for i, ln in enumerate(desc_lines):
                    if ln in _SHELL_ORGS: idx_org = i
                    if ln in ("培训地点：", "培训地点", "培训地点:"): idx_place = i
                    if ln in ("培训描述：", "培训描述", "培训描述:"): idx_desc = i
                real_org = real_place = real_desc_rest = ""
                if idx_org >= 0 and idx_org + 1 < len(desc_lines):
                    real_org = desc_lines[idx_org + 1]
                if idx_place >= 0 and idx_place + 1 < len(desc_lines):
                    real_place = desc_lines[idx_place + 1]
                if idx_desc >= 0 and idx_desc + 1 < len(desc_lines):
                    real_desc_rest = "\n".join(desc_lines[idx_desc + 1:]).strip()
                if real_tname:
                    t["training_name"] = real_tname
                # 机构：优先 real_org；其次 real_place（仅当 real_org 空且 tname 不是纯壳时）
                # EN: Provider: prefer real_org; then real_place (only when real_org is empty and tname is not a pure shell)
                # JA: 機関：real_org を優先し、次に real_place（real_org が空で、tname が純粋な殻でない場合だけ）
                if real_org and real_org not in _SHELL_ORGS:
                    t["organization_name"] = real_org
                # 如果 real_org 还不行，且 training_name 也不是壳，则保留 tname（不要硬塞壳字）
                # EN: If real_org still does not work and training_name is not a shell either, keep tname (do not force shell words in)
                # JA: real_org でもだめで training_name も殻でなければ、tname を残す（殻の語を無理に入れない）
                if t.get("organization_name") in _SHELL_ORGS:
                    t["organization_name"] = ""
                if real_desc_rest:
                    t["description"] = real_desc_rest
                if start_ym:
                    t["start_ym"] = start_ym
                if end_ym:
                    t["end_ym"] = end_ym
        # 2) 丢弃 section 头/伪 training / 技能软件条目
        # EN: 2) Drop section headers / pseudo-training / skill-software entries
        # JA: 2) セクション見出し・偽の研修・スキルやソフトウェアの項目を捨てる
        org = (t.get("organization_name") or "").strip()
        tname = (t.get("training_name") or "").strip()
        merged_shell = org + " " + tname
        _looks_bad = any(h in merged_shell for h in _BAD_HEADERS)
        _sw_skills = re.search(r"(MS\s*WORD|MS\s*Excel|Excel|PowerPoint|PPT|Word|Office)", merged_shell, re.I) is not None
        _empty_content = (not org) and (not tname) and not (t.get("description") or "").strip()
        # 如果 training_name 本身仍是壳字，说明 desc 也没提到，丢弃（否则只留空结构）
        # EN: If training_name itself is still a shell word, desc did not mention it either; drop it (otherwise only an empty structure remains)
        # JA: training_name 自体がまだ殻の語なら、desc にも記載がないということなので捨てる（さもないと空の構造だけが残る）
        if _looks_bad or _sw_skills or _empty_content or (tname in _SHELL_TNAMES):
            continue
        # 日期宽松归一 + 若 end<start 交换
        # EN: Lenient date normalisation + swap if end < start
        # JA: 日付の緩い正規化 + end < start なら入れ替える
        for dk in ("start_ym", "end_ym"):
            v = str(t.get(dk) or "").strip()
            if v:
                m = re.fullmatch(r"((?:19|20)\d{2})[\./年](\d{1,2})(?:月)?", v)
                if m:
                    t[dk] = f"{int(m.group(1)):04d}-{int(m.group(2)):02d}"
                else:
                    mm = re.search(r"((?:19|20)\d{2})\s*[/\-.年]\s*(\d{1,2})", v)
                    if mm:
                        t[dk] = f"{int(mm.group(1)):04d}-{int(mm.group(2)):02d}"
        ns, ne = _swap_end_start_when_reversed(t.get("start_ym") or "", t.get("end_ym") or "", status="")
        t["start_ym"] = ns; t["end_ym"] = ne
        out.append({k: t.get(k, "") for k in TRAIN_FIELDS})
    for i, it in enumerate(out, 1):
        it["sequence_no"] = i
    return out


def _normalize_certificate_list_cleanup(raw_list: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """certificate_list 清理：剥 raw_text + 去掉伪条目（空名/section 头/在校学习情况/描述句粘错 等）+ 日期宽松归一。

    EN: certificate_list cleanup: strip raw_text + remove pseudo entries (empty names / section headers / on-campus study situation / description sentences stuck in by mistake, etc.) + lenient date normalisation.

    JA: certificate_list の整理：raw_text を除く + 偽の項目（空の名前・セクション見出し・在学中の学習状況・誤ってくっついた説明文など）を除く + 日付の緩い正規化。
    """
    if not raw_list:
        return []
    _BAD = (
        "证书", "▲证书", "所获证书", "证书资格", "其他", "▲其他", "培训经历", "▲培训经历",
        "技能", "专业技能", "▲技能", "▲技能/语言", "技能/语言", "语言能力", "▲语言", "自我评价",
        "project", "training", "language", "在校学习情况", "在校", "校园经历", "实践",
        "培训机构", "培训机构：", "培训地点：", "培训地点", "培训描述：", "培训描述",
    )
    _BAD_SHELL_NAMES = (
        "证书说明：", "证书说明:", "证书描述：", "证书描述:", "所获证书：", "所获证书:", "证书名称：", "证书名称:",
        "培训说明：", "培训说明:", "培训描述：", "培训描述:", "获奖说明：", "获奖说明:", "附加信息：", "附加信息:",
    )
    _BAD_HAS = ("培训描述：", "培训机构：", "培训地点：", "培训描述", "培训地点")
    # 句子特征的中文标点 → 描述句粘错 cert_name 的识别：≥ 2 个这类标点或 ≥ 1 个句号/感叹号/问号且长度≥8
    # EN: Chinese punctuation typical of sentences → detect description sentences wrongly stuck into cert_name: ≥ 2 such punctuation marks, or ≥ 1 full stop/exclamation/question mark and length ≥ 8
    # JA: 文に特有の中国語の句読点 → cert_name に誤ってくっついた説明文を識別する：その種の句読点が 2 つ以上、または句点・感嘆符・疑問符が 1 つ以上で長さ 8 以上
    _SENTENCE_PUNCT = ("，", "。", "！", "？", "；", ",", "!", "?", ";")
    # 开头的主语/动词（描述行文特征）→ 不是证书名
    # EN: Starting with a subject/verb (a feature of descriptive prose) → not a certificate name
    # JA: 主語・動詞で始まる（説明文の特徴）→ 資格名ではない
    _SENTENCE_PREFIX = (
        "通过", "经过", "在", "从", "使我", "让我", "掌握", "了解", "学习", "参加", "完成",
        "熟悉", "熟练", "具备", "拥有", "考取", "拿到", "获得", "取得", "通过对",
        "通过这个", "通过该", "通过此", "通过培训",
    )
    CERT_FIELDS = ("certificate_name", "certificate_type", "certificate_time")
    out = []
    seen_key: set[tuple[str, str]] = set()
    for c in raw_list:
        if not isinstance(c, dict):
            continue
        cc = dict(c)
        cc.pop("raw_text", None)
        # 兼容旧字段拼写 certificate_tpye（typeless 的 typo）
        # EN: Compatible with the old field spelling certificate_tpye (a typo of type)
        # JA: 旧フィールドの綴り certificate_tpye（type の誤記）に対応する
        if cc.get("certificate_tpye") and not cc.get("certificate_type"):
            cc["certificate_type"] = cc.pop("certificate_tpye")
        name = (cc.get("certificate_name") or "").strip()
        if not name:
            continue
        # 去掉前缀 /NN, ▲等
        # EN: Remove prefixes like /NN, ▲
        # JA: /NN、▲ などの接頭辞を除く
        name = re.sub(r"^[▲△◆●■\s]+", "", name).strip()
        name = re.sub(r"^/\d{1,2}\s*", "", name).strip()
        # 去掉前缀 "1 " "2  " "3\xa0\xa0" 这种序号
        # EN: Remove sequence-number prefixes like "1 " "2  " "3\xa0\xa0"
        # JA: 「1 」「2  」「3\xa0\xa0」のような通し番号の接頭辞を除く
        name = re.sub(r"^\s*\d{1,2}\s+", "", name, flags=re.U).strip()
        name = re.sub(r"^\s*\d{1,2}[\s\xa0]+", "", name).strip()
        if not name:
            continue
        if name in _BAD or name in _BAD_SHELL_NAMES:
            continue
        # 如果 name 里含 "颁发机构："/"颁发机构:"/"颁奖机构：" 等，从 ":" 截断保留前半（如果前半还有内容≥2字）
        # EN: If name contains "颁发机构："/"颁发机构:"/"颁奖机构：" (issuing authority / awarding body) etc., truncate at ":" and keep the first half (if it still has ≥2 characters)
        # JA: name に「颁发机构：」／「颁发机构:」／「颁奖机构：」（発行機関・授与機関）などがあれば「:」で切って前半を残す（前半に 2 文字以上の内容がある場合）
        for tag in ("颁发机构：", "颁发机构:", "颁奖机构：", "颁奖机构:", "发证单位：", "发证单位:", "颁发单位：", "颁发单位:", "认证机构：", "认证机构:"):
            idx = name.find(tag)
            if idx >= 2:
                name = name[:idx].strip(" 　\t()（）,，、.。·-")
                break
        if any(ss in name for ss in _BAD_HAS) and len(name) <= 10:
            # 短名里带 "培训描述：" 这种壳，抛弃
            # EN: Short names containing a shell like "培训描述：" (training description:) are discarded
            # JA: 「培训描述：」（研修の説明：）のような殻を含む短い名前は捨てる
            continue
        # 句子特征 1：以描述词开头
        # EN: Sentence feature 1: starts with a descriptive word
        # JA: 文の特徴 1：説明の語で始まる
        if len(name) >= 6 and any(name.startswith(p) for p in _SENTENCE_PREFIX):
            continue
        # 句子特征 2：包含多个句子标点
        # EN: Sentence feature 2: contains several sentence punctuation marks
        # JA: 文の特徴 2：文の句読点を複数含む
        punct_count = sum(name.count(p) for p in _SENTENCE_PUNCT)
        if len(name) >= 8 and punct_count >= 2:
            continue
        # 句子特征 3：含句号/感叹号/问号（证书名一般不含这些）
        # EN: Sentence feature 3: contains a full stop / exclamation / question mark (certificate names generally do not)
        # JA: 文の特徴 3：句点・感嘆符・疑問符を含む（資格名には通常含まれない）
        if len(name) >= 8 and any(p in name for p in ("。", "！", "？", "!", "?")):
            continue
        if len(name) > 200:
            # 超长 name 不是证书名（一般是 description 粘错）
            # EN: A very long name is not a certificate name (usually a description stuck in by mistake)
            # JA: 非常に長い name は資格名ではない（通常は説明が誤ってくっついたもの）
            continue
        cc["certificate_name"] = name
        if not (cc.get("certificate_type") or "").strip():
            cc["certificate_type"] = "证书"
        # 日期宽松归一
        # EN: Lenient date normalisation
        # JA: 日付の緩い正規化
        t = str(cc.get("certificate_time") or "").strip()
        if t:
            m = re.search(r"((?:19|20)\d{2})\s*[/\-.年]\s*(\d{1,2})", t)
            if m:
                cc["certificate_time"] = f"{int(m.group(1)):04d}-{int(m.group(2)):02d}"
        item = {k: str(cc.get(k, "")).strip() for k in CERT_FIELDS}
        if not item["certificate_name"]:
            continue
        key = (item["certificate_name"], item["certificate_time"])
        if key in seen_key:
            continue
        seen_key.add(key)
        out.append(item)
    return out


def _normalize_language_list(raw_list: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """猎聘严格 4 字段：language_name / language_level / language_certificate / language_certificate_time。

    EN: Strict Liepin 4 fields: language_name / language_level / language_certificate / language_certificate_time.

    JA: Liepin の厳格な 4 フィールド：language_name / language_level / language_certificate / language_certificate_time。
    """
    LANG_4_KEYS = ["language_name", "language_level", "language_certificate", "language_certificate_time"]
    LANG_NAME_MAP = {
        "English": "英语", "Mandarin": "普通话", "Cantonese": "粤语",
        "Japanese": "日语", "Korean": "韩语", "German": "德语", "French": "法语",
        "Spanish": "西班牙语", "Italian": "意大利语", "Portuguese": "葡萄牙语",
        "Russian": "俄语", "Arabic": "阿拉伯语", "Thai": "泰语", "Chinese": "中文",
    }
    LANG_LEVEL_MAP = {
        "CET-4": "大学英语四级", "CET4": "大学英语四级", "CET-6": "大学英语六级", "CET6": "大学英语六级",
        "TEM-4": "专业英语四级", "TEM4": "专业英语四级", "TEM-8": "专业英语八级", "TEM8": "专业英语八级",
        "TOEFL": "托福", "IELTS": "雅思", "GRE": "GRE", "GMAT": "GMAT",
        "N1": "日语能力一级", "N2": "日语能力二级", "N3": "日语能力三级",
        "Native": "母语", "Mother Tongue": "母语", "Fluent": "流利", "Proficiency": "熟练",
        "Intermediate": "中级", "Basic": "基础", "Conversational": "会话",
    }
    if not raw_list:
        return []
    cleaned = []
    for l in raw_list:
        if not isinstance(l, dict):
            continue
        l = dict(l)
        l.pop("raw_text", None)
        # 删除旧字段：language_listen_speak_level / language_read_write_level
        # EN: Delete old fields: language_listen_speak_level / language_read_write_level
        # JA: 旧フィールドを削除する：language_listen_speak_level / language_read_write_level
        for bad_key in ("language_listen_speak_level", "language_read_write_level"):
            l.pop(bad_key, None)
        # 名称翻译
        # EN: Name translation
        # JA: 名称の変換
        n = (l.get("language_name") or "").strip()
        if n in LANG_NAME_MAP:
            l["language_name"] = LANG_NAME_MAP[n]
        # 级别翻译
        # EN: Level translation
        # JA: レベルの変換
        lv = (l.get("language_level") or "").strip()
        if lv in LANG_LEVEL_MAP:
            l["language_level"] = LANG_LEVEL_MAP[lv]
        # 强制 4 字段，不多不少
        # EN: Force exactly 4 fields, no more, no less
        # JA: 4 フィールドを過不足なく強制する
        item = {k: str(l.get(k, "")).strip() for k in LANG_4_KEYS}
        if item["language_name"]:
            cleaned.append(item)
    return cleaned


def _normalize_list_strip_raw(items: list[Any]) -> list[Any]:
    """通用列表：每个 dict 递归删掉 raw_text。

    EN: Generic lists: recursively delete raw_text from each dict.

    JA: 汎用のリスト：各 dict から raw_text を再帰的に削除する。
    """
    if not items:
        return []
    cleaned = []
    for it in items:
        if isinstance(it, dict):
            it = dict(it)
            _recursive_strip_raw_text(it)
            cleaned.append(it)
        elif it is not None:
            cleaned.append(it)
    return cleaned


# =============================================================================
# Project list: 描述/职责 分离；training_name 兜底映射 project_name
# =============================================================================
# EN: =============================================================================
#     Project list: separate description/duties; fallback mapping training_name → project_name
#     =============================================================================
# JA: =============================================================================
#     Project list：説明と担当業務を分離。training_name → project_name の最終手段の対応付け
#     =============================================================================

def _normalize_project_list(raw_list: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not raw_list:
        return []
    cleaned = []
    for p in raw_list:
        if not isinstance(p, dict):
            continue
        p = dict(p)
        p.pop("raw_text", None)
        # 描述/职责分离：如果 description 中含「责任描述/职责」关键词，则把那部分挪到 responsibilities
        # EN: Separate description/duties: if description contains the keywords "责任描述/职责" (responsibility description / duties), move that part into responsibilities
        # JA: 説明と担当業務の分離：description に「责任描述／职责」（担当業務の説明・職責）のキーワードがあれば、その部分を responsibilities に移す
        desc = (p.get("description") or p.get("project_description") or "").strip()
        resp = (p.get("responsibilities") or p.get("project_responsibilities") or "").strip()
        if not resp and ("责任描述" in desc or "职责" in desc or "工作职责" in desc or "岗位职责" in desc):
            parts = re.split(r"(\n\s*(?:责任描述|项目职责|工作职责|岗位职责|工作内容)[:：]?\s*\n?)", desc, maxsplit=1)
            if len(parts) >= 2:
                new_desc = parts[0].strip()
                new_resp = "".join(parts[2:]).strip() if len(parts) >= 3 else ""
                if not new_resp:
                    # 以关键词为界：后段是职责
                    # EN: Split at the keyword: the latter part is the duties
                    # JA: キーワードで区切る：後半が担当業務
                    idx = -1
                    for kw in ("责任描述", "项目职责", "工作职责", "岗位职责", "工作内容"):
                        i = desc.find(kw)
                        if i >= 0 and (idx < 0 or i < idx):
                            idx = i
                    if idx >= 0:
                        sep_start = idx
                        sep_line_end = desc.find("\n", sep_start)
                        cut = sep_line_end if sep_line_end >= 0 else sep_start + 8
                        new_desc = desc[:sep_start].strip()
                        new_resp = desc[cut:].strip()
                desc, resp = new_desc, new_resp
        p["description"] = desc
        p["responsibilities"] = resp
        # 训练名兜底：training_name 存在但 project_name 为空时，映射过来
        # EN: Training-name fallback: when training_name exists but project_name is empty, map it over
        # JA: 研修名の最終手段：training_name があり project_name が空なら、対応付けて移す
        pname = (p.get("project_name") or "").strip()
        tname = (p.get("training_name") or "").strip()
        if not pname and tname:
            p["project_name"] = tname
        # 去掉 training_name / project_description / project_responsibilities 这种冗余字段
        # EN: Remove redundant fields like training_name / project_description / project_responsibilities
        # JA: training_name / project_description / project_responsibilities などの冗長なフィールドを除く
        for extra in ("training_name", "project_description", "project_responsibilities"):
            p.pop(extra, None)
        cleaned.append(p)
    return cleaned


# =============================================================================
# 构建顶层 raw_text（从 resumes 内所有有效字段的文字汇总）
# =============================================================================
# EN: =============================================================================
#     Build the top-level raw_text (a text summary of all valid fields inside resumes)
#     =============================================================================
# JA: =============================================================================
#     トップレベルの raw_text を組み立てる（resumes 内のすべての有効なフィールドのテキストを集約）
#     =============================================================================

def _build_top_level_raw_text(structured_data: dict[str, Any]) -> str:
    """从 resumes[0]（中文主版本）的所有 list item 纯文本 + base_info/expected_info 关键信息，用 \\n 连接。

    EN: Join with \\n the plain text of all list items of resumes[0] (the Chinese primary version) + key information from base_info/expected_info.

    JA: resumes[0]（中国語主版）のすべてのリスト要素のプレーンテキスト + base_info/expected_info の主要な情報を \\n で連結する。
    """
    lines: list[str] = []
    resumes = structured_data.get("resumes") or []
    if not resumes:
        return ""
    zh = resumes[0]
    # base_info 关键信息
    # EN: Key base_info information
    # JA: base_info の主要な情報
    bi = zh.get("base_info") or {}
    for k in ("full_name", "gender", "birthday", "birth_place", "household_register", "marital_status",
              "mobile_phone", "email", "residence_city", "work_years", "current_city", "pr"):
        v = bi.get(k)
        if v and str(v).strip():
            lines.append(f"{k}: {v}")
    ei_arr = zh.get("expected_info") or []
    if isinstance(ei_arr, list) and ei_arr and isinstance(ei_arr[0], dict):
        ei = ei_arr[0]
    elif isinstance(ei_arr, dict):
        ei = ei_arr
    else:
        ei = {}
    for k in ("expected_position", "expected_city", "expected_salary", "expected_industry", "expected_start_date"):
        v = ei.get(k)
        if v and str(v).strip():
            lines.append(f"{k}: {v}")
    # 所有 list 类型，逐条
    # EN: All list types, item by item
    # JA: すべてのリスト型を 1 件ずつ
    LIST_FIELDS = [
        "work_experiences", "education_list", "project_list", "training_list",
        "certificate_list", "language_list", "skills_list", "communication_list",
    ]
    for fname in LIST_FIELDS:
        items = zh.get(fname) or []
        if not isinstance(items, list):
            continue
        for item in items:
            if isinstance(item, dict):
                for v in item.values():
                    if v is None:
                        continue
                    if isinstance(v, str) and v.strip():
                        lines.append(v.strip())
                    elif isinstance(v, (int, float)):
                        lines.append(str(v))
            elif isinstance(item, str) and item.strip():
                lines.append(item.strip())
    # 去空行，保留顺序
    # EN: Remove empty lines, keeping the order
    # JA: 空行を除き、順序は保つ
    out_lines: list[str] = []
    for l in lines:
        s = l.strip()
        if s:
            out_lines.append(s)
    return "\n".join(out_lines)


# =============================================================================
# communication_list 规范化：[{communicate_time, communicate_content}, ...]
# =============================================================================
# EN: =============================================================================
#     communication_list normalisation: [{communicate_time, communicate_content}, ...]
#     =============================================================================
# JA: =============================================================================
#     communication_list の正規化：[{communicate_time, communicate_content}, ...]
#     =============================================================================

def _normalize_communication_list(raw_list: list[Any]) -> list[dict[str, Any]]:
    if not raw_list:
        return []
    cleaned = []
    for it in raw_list:
        if isinstance(it, dict):
            it = dict(it)
            it.pop("raw_text", None)
            ct = it.get("communicate_time") or it.get("time") or ""
            cc = it.get("communicate_content") or it.get("content") or it.get("assessment") or ""
            # 如果仅有 communicate_assessment 字段
            # EN: If there is only the communicate_assessment field
            # JA: communicate_assessment フィールドしかない場合
            if not cc and "communicate_assessment" in it:
                cc = it["communicate_assessment"]
            if cc:  # 只有内容非空才保留
            # EN: Keep only when the content is non-empty
            # JA: 内容が空でない場合だけ残す
                cleaned.append({
                    "communicate_time": str(ct).strip() if ct else "",
                    "communicate_content": str(cc).strip(),
                })
        elif isinstance(it, str) and it.strip():
            cleaned.append({"communicate_time": "", "communicate_content": it.strip()})
    return cleaned


# =============================================================================
# 强制顶层结构 + 禁止字段 清理（质量闸门核心）
# =============================================================================
# EN: =============================================================================
#     Forced top-level structure + forbidden-field cleanup (the core of the quality gate)
#     =============================================================================
# JA: =============================================================================
#     トップレベル構造の強制 + 禁止フィールドの除去（品質ゲートの中核）
#     =============================================================================

FORBIDDEN_TOP_LEVEL_IN_STRUCTURED = {
    # 旧命名（不允许出现在 SD 顶层任何位置）
    # EN: Old naming (not allowed anywhere at the SD top level)
    # JA: 旧名称（SD のトップレベルのどこにも置いてはならない）
    "project_experiences",  # 旧命名（新命名是 project_list）
    # EN: Old naming (the new name is project_list)
    # JA: 旧名称（新しい名前は project_list）
    "training_experiences",  # 旧命名（新命名是 training_list）
    # EN: Old naming (the new name is training_list)
    # JA: 旧名称（新しい名前は training_list）
    "communication_assessment",  # 旧命名（新命名是 communication_list）
    # EN: Old naming (the new name is communication_list)
    # JA: 旧名称（新しい名前は communication_list）
    "certificate_info", "language_info", "skills_info",  # 旧命名（已改成 *_list）
    # EN: Old naming (now changed to *_list)
    # JA: 旧名称（*_list に変更済み）
    # 不允许放 SD 顶层的大列表（只能在 resumes 内）
    # EN: Large lists not allowed at the SD top level (only inside resumes)
    # JA: SD のトップレベルに置いてはならない大きなリスト（resumes 内にだけ置ける）
    "work_experiences", "education_list",
    # SD 顶层绝对不允许放 6 个 list（只能在 resumes[i] 内）
    # EN: The 6 lists are absolutely not allowed at the SD top level (only inside resumes[i])
    # JA: 6 つのリストは SD のトップレベルに決して置いてはならない（resumes[i] 内にだけ置ける）
    "certificate_list", "language_list", "skills_list",
    "training_list", "project_list", "communication_list",
    "raw_text",
}

# 允许在 structured_data 顶层的 key（白名单）—— 严格 5 大对象，不含 6 lists
# EN: Keys allowed at the top level of structured_data (whitelist) — strictly the 5 main objects, not the 6 lists
# JA: structured_data のトップレベルに置ける key（ホワイトリスト）— 厳密に 5 つの主要オブジェクトで、6 つのリストは含まない
ALLOWED_STRUCTURED_KEYS = {
    "base_info", "expected_info", "current_info", "education_info", "resumes",
}

# 顶层 JSON 白名单 + 参考顺序（schema_version, source, extraction, dates, classification, structured_data, raw_text）
# EN: Top-level JSON whitelist + reference order (schema_version, source, extraction, dates, classification, structured_data, raw_text)
# JA: トップレベルの JSON のホワイトリスト + 参照の順序（schema_version, source, extraction, dates, classification, structured_data, raw_text）
ALLOWED_TOP_LEVEL_KEYS = ["schema_version", "record_id", "source", "extraction",
                          "dates", "classification", "structured_data", "raw_text"]
# 顶层必须字段（6 大字段 + record_id/classification 可选但允许）
# EN: Required top-level fields (the 6 main fields + record_id/classification optional but allowed)
# JA: トップレベルの必須フィールド（6 つの主要フィールド + record_id/classification は任意だが許可）
TOP_MUST = {"schema_version", "source", "extraction", "dates", "structured_data", "raw_text"}


def _force_top_level_schema(record: dict[str, Any]) -> dict[str, Any]:
    """**最后一道闸门**：严格 6 顶层字段 / SD 顶层 5 大对象 / 无 raw_text 泄漏 / expected_info 数组化 / 字段顺序严格对齐参考 JSON。

    EN: **The last gate**: strictly 6 top-level fields / 5 main SD top-level objects / no raw_text leaks / expected_info as an array / field order strictly aligned with the reference JSON.

    JA: **最後のゲート**：トップレベルは厳密に 6 フィールド / SD のトップレベルは 5 つの主要オブジェクト / raw_text の漏れなし / expected_info は配列 / フィールドの順序は参照 JSON に厳密に合わせる。
    """
    # 1) 顶层按参考顺序编排（schema_version → record_id → source → extraction → dates → classification → structured_data → raw_text）
    # EN: 1) Arrange the top level in the reference order (schema_version → record_id → source → extraction → dates → classification → structured_data → raw_text)
    # JA: 1) トップレベルを参照の順序に並べる（schema_version → record_id → source → extraction → dates → classification → structured_data → raw_text）
    top_clean: dict[str, Any] = {}
    for k in ALLOWED_TOP_LEVEL_KEYS:
        if k in record:
            top_clean[k] = record[k]
    # 必须字段补齐
    # EN: Fill in required fields
    # JA: 必須フィールドを補う
    for k in TOP_MUST:
        if k not in top_clean:
            if k == "schema_version":
                top_clean[k] = "codex-resume-json-1.0"
            elif k == "raw_text":
                top_clean[k] = ""
            else:
                top_clean[k] = {}
    # record_id 从 extraction 里拿（如果已有就用）
    # EN: Take record_id from extraction (use it if already present)
    # JA: record_id は extraction から取る（すでにあればそれを使う）
    if "record_id" not in top_clean:
        ext = top_clean.get("extraction") or {}
        if isinstance(ext, dict) and ext.get("record_id"):
            top_clean = {"record_id": ext["record_id"], **top_clean}
    # 2) structured_data 顶层只保留 5 大对象，严格顺序
    # EN: 2) The top level of structured_data keeps only the 5 main objects, in strict order
    # JA: 2) structured_data のトップレベルには 5 つの主要オブジェクトだけを厳密な順序で残す
    sd = record.get("structured_data") or {}
    if not isinstance(sd, dict):
        sd = {}
    SD_ORDER = ["base_info", "expected_info", "current_info", "education_info", "resumes"]
    sd_clean: dict[str, Any] = {}
    for k in SD_ORDER:
        if k in sd:
            sd_clean[k] = sd[k]
    # 5 大对象兜底补齐
    # EN: Fallback completion of the 5 main objects
    # JA: 5 つの主要オブジェクトを最終手段で補完する
    for k in SD_ORDER:
        if k not in sd_clean:
            if k == "base_info":
                sd_clean[k] = {}
            elif k == "expected_info":
                sd_clean[k] = [{x: "" for x in EXPECTED_INFO_8_KEYS}]
            elif k == "current_info":
                sd_clean[k] = copy.deepcopy(EMPTY_CURRENT_INFO)
            elif k == "education_info":
                sd_clean[k] = copy.deepcopy(EMPTY_EDUCATION_INFO)
            elif k == "resumes":
                sd_clean[k] = []
    # expected_info 必须是数组：dict → 1 元素数组
    # EN: expected_info must be an array: dict → 1-element array
    # JA: expected_info は配列でなければならない：dict → 要素 1 つの配列
    if not isinstance(sd_clean.get("expected_info"), list):
        exp_dict = sd_clean["expected_info"] if isinstance(sd_clean["expected_info"], dict) else {}
        sd_clean["expected_info"] = [{k: str(exp_dict.get(k, "") or "").strip() for k in EXPECTED_INFO_8_KEYS}]
    # 数组内元素必须是 8 字段 dict；非 dict 过滤
    # EN: Elements inside the array must be 8-field dicts; non-dicts are filtered
    # JA: 配列内の要素は 8 フィールドの dict でなければならず、dict でないものは除外する
    cleaned_exp_arr = []
    for item in sd_clean["expected_info"]:
        if isinstance(item, dict):
            cleaned_exp_arr.append({k: str(item.get(k, "") or "").strip() for k in EXPECTED_INFO_8_KEYS})
    if not cleaned_exp_arr:
        cleaned_exp_arr.append({x: "" for x in EXPECTED_INFO_8_KEYS})
    sd_clean["expected_info"] = cleaned_exp_arr
    # 绝对禁止：删除 FORBIDDEN 列表中的字段（SD 顶层禁止放 6 lists）
    # EN: Absolutely forbidden: delete the fields in the FORBIDDEN list (the 6 lists are forbidden at the SD top level)
    # JA: 絶対禁止：FORBIDDEN の一覧にあるフィールドを削除する（SD のトップレベルに 6 つのリストを置くことは禁止）
    for k in FORBIDDEN_TOP_LEVEL_IN_STRUCTURED:
        sd_clean.pop(k, None)
    top_clean["structured_data"] = sd_clean
    # 3) classification 按参考格式补齐（放在 dates 和 structured_data 之间）
    # EN: 3) Complete classification according to the reference format (placed between dates and structured_data)
    # JA: 3) classification を参照の形式に従って補う（dates と structured_data の間に置く）
    if "classification" not in top_clean:
        cls_str = (top_clean.get("extraction") or {}).get("classifier_result", "")
        doc_type = "resume"
        reason = "包含候选人履历或个人档案特征，按简历入库"
        if isinstance(cls_str, str) and "document_type=" in cls_str:
            m1 = re.search(r"document_type=['\"]([^'\"]+)", cls_str)
            if m1: doc_type = m1.group(1)
            m2 = re.search(r"reason='([^']+)'", cls_str)
            if m2: reason = m2.group(1)
        # 插入到 dates 后、structured_data 前（利用有序 dict）
        # EN: Insert after dates and before structured_data (using an ordered dict)
        # JA: dates の後、structured_data の前に挿入する（順序付き dict を利用）
        _new_top: dict[str, Any] = {}
        for k, v in top_clean.items():
            _new_top[k] = v
            if k == "dates":
                _new_top["classification"] = {"document_type": doc_type, "reason": reason}
        top_clean = _new_top
    # 4) 二次保险：递归删除所有子对象 raw_text（除了顶层）
    # EN: 4) Second safeguard: recursively delete raw_text from all sub-objects (except the top level)
    # JA: 4) 二重の保険：すべてのサブオブジェクトから raw_text を再帰的に削除する（トップレベルを除く）
    _recursive_strip_raw_text(top_clean["source"])
    _recursive_strip_raw_text(top_clean["extraction"])
    _recursive_strip_raw_text(top_clean["dates"])
    _recursive_strip_raw_text(top_clean.get("classification") or {})
    _recursive_strip_raw_text(top_clean["structured_data"])
    return top_clean


# =============================================================================
# 单文件处理入口
# =============================================================================
# EN: =============================================================================
#     Single-file processing entry point
#     =============================================================================
# JA: =============================================================================
#     単一ファイル処理のエントリ
#     =============================================================================

def process_single_html(
    html_path: Path,
    json_dir: Path,
    force: bool = False,
) -> tuple[bool, str, str | None]:
    """处理单个 HTML → JSON。返回 (成功?, 原因或信息, JSON路径或None)。

    EN: Process a single HTML → JSON. Returns (success?, reason or info, JSON path or None).

    JA: 単一の HTML → JSON を処理する。戻り値：(成功したか, 理由または情報, JSON のパスまたは None)。
    """
    filename = html_path.name
    # 1) 跳过非 HTML 与 JSON 索引文件
    # EN: 1) Skip non-HTML and JSON index files
    # JA: 1) HTML 以外と JSON の索引ファイルをスキップする
    if html_path.suffix.lower() not in (".html", ".htm", ".mht", ".mhtml", ".eml"):
        return False, "非 HTML 文件跳过", None
    if filename.startswith("_"):  # _report / _map 等
    # EN: _report / _map etc.
    # JA: _report / _map など
        return False, "报告/索引文件跳过", None

    try:
        html_text = read_html_text(html_path)
    except Exception as e:
        return False, f"HTML读取失败: {e}", None

    plain = html_to_plain_text(html_text)
    if not plain or len(plain) < 20:
        return False, "正文过短/空简历", None

    rec_id = html_record_id(html_path)
    fallback_date = date_from_mtime(html_path)
    updated_date, download_date, updated_src, download_src = parse_resume_dates(plain, fallback_date)
    platform = detect_platform(plain, filename)

    # 2) 解析器基础解析（复用 liepin 的调用方式：parser.parse(html_cleaned_text, filename, source_path)）
    # EN: 2) Basic parsing by the parser (reusing liepin's calling convention: parser.parse(html_cleaned_text, filename, source_path))
    # JA: 2) パーサーによる基本の解析（liepin の呼び出し方を再利用：parser.parse(html_cleaned_text, filename, source_path)）
    parser = CodexGeminiHtmlSchemaParser()
    classifier = DocumentClassifier()
    fake_source_path = str(html_path.resolve())

    try:
        base_parsed = parser.parse(html_text, filename=html_path.name, source_path=fake_source_path)
    except Exception as e:
        return False, f"Parser 异常: {e}", None

    # 3) 处理多语言：按"数据丰富度"优先排，再调 zh 到 0 号位（防止空 zh 简历占位）
    # EN: 3) Handle multiple languages: sort by "data richness" first, then move zh to slot 0 (to prevent an empty zh résumé from occupying it)
    # JA: 3) 多言語の処理：まず「データの充実度」で並べ、その後 zh を 0 番目に移す（空の zh の履歴書が場所を占めるのを防ぐ）
    resumes_raw = base_parsed.get("resumes") or []
    if not isinstance(resumes_raw, list) or not resumes_raw:
        # 没解析出 resumes → 尝试拿整个 structured_data 当 resumes[0]
        # EN: No resumes parsed → try using the whole structured_data as resumes[0]
        # JA: resumes が解析できなかった → structured_data 全体を resumes[0] として使ってみる
        fallback_resume = {
            "resume_language": "zh",
            "base_info": base_parsed.get("base_info") or {},
            "expected_info": base_parsed.get("expected_info") or {},
            "work_experiences": base_parsed.get("work_experiences") or [],
            "education_list": base_parsed.get("education_list") or [],
            "project_list": base_parsed.get("project_list") or [],
            "training_list": base_parsed.get("training_list") or [],
            "certificate_list": base_parsed.get("certificate_list") or [],
            "language_list": base_parsed.get("language_list") or [],
            "skills_list": base_parsed.get("skills_list") or [],
            "communication_list": base_parsed.get("communication_list")
                                 or base_parsed.get("communication_assessment") or [],
        }
        resumes_raw = [fallback_resume]

    # ========== 计算每个 resume 的数据丰富度，排序（空简历排后） ==========
    # EN: ========== Compute the data richness of each resume and sort (empty résumés last) ==========
    # JA: ========== 各 resume のデータの充実度を計算して並べる（空の履歴書は後ろ）==========
    def _resume_score(r: dict) -> int:
        if not isinstance(r, dict):
            return -999999
        score = 0
        # list 长度加权（最关键）
        # EN: Weighted by list length (the most important)
        # JA: リストの長さで重み付け（最も重要）
        for lk in ("work_experiences", "education_list", "certificate_list",
                   "language_list", "project_list", "training_list",
                   "skills_list", "communication_list"):
            score += len(r.get(lk) or []) * 10
        # base_info 字段数（去掉空值）
        # EN: Number of base_info fields (excluding empty values)
        # JA: base_info のフィールド数（空の値は除く）
        bi = r.get("base_info") or {}
        score += sum(1 for v in bi.values() if v and str(v).strip())
        return score

    resumes_raw = sorted(resumes_raw, key=_resume_score, reverse=True)

    # 主版本 = 第 0 名（最丰富的那条），不管语言，强制 language=zh（parser 标注 jp/en 常出错，因为有外文内容）
    # 如果丰富度排名前 3 内有 zh 版本且数据也丰富，把 zh 也放到 0 号
    # （规则：0 号位必须有内容，绝对不允许把一个空壳 zh 换到 0 号）
    # EN: Primary version = rank 0 (the richest one), regardless of language; force language=zh (the parser often mislabels jp/en because of foreign-language content)
    #     If a zh version is in the top 3 by richness and its data is also rich, also put zh into slot 0
    #     (Rule: slot 0 must have content; never swap an empty-shell zh into slot 0)
    # JA: 主版 = 第 0 位（最も充実したもの）。言語に関係なく language=zh を強制する（外国語の内容があるため、パーサーの jp/en の判定はよく誤る）
    #     充実度の上位 3 位以内に zh 版があり、データも充実していれば、zh も 0 番目に置く
    #     （ルール：0 番目には必ず内容がなければならず、空の殻の zh を 0 番目に入れることは決してしない）
    zh_idx_in_top3 = None
    best_score = _resume_score(resumes_raw[0]) if resumes_raw else 0
    for i, r in enumerate(resumes_raw[:3]):
        if isinstance(r, dict) and str(r.get("resume_language") or r.get("resume_languge") or "").lower() in ("zh", "cn", "chinese", "中文", ""):
            s = _resume_score(r)
            # 只在 zh 版本分数 >= 最佳分数的 50% 以上（也很丰富）时，才调 zh 到 0
            # EN: Move zh into slot 0 only when the zh version's score is >= 50% of the best score (also rich)
            # JA: zh 版の点数が最高点の 50% 以上（十分に充実している）の場合だけ zh を 0 番目に移す
            if s >= max(3, int(best_score * 0.5)):
                zh_idx_in_top3 = i
                break
    if zh_idx_in_top3 is not None and zh_idx_in_top3 != 0:
        resumes_raw[0], resumes_raw[zh_idx_in_top3] = resumes_raw[zh_idx_in_top3], resumes_raw[0]

    resumes_normalized: list[dict[str, Any]] = []
    for idx, r in enumerate(resumes_raw):
        if not isinstance(r, dict):
            continue
        r = copy.deepcopy(r)
        # 修复 parser 拼写错误：resume_languge → resume_language（与 liepin 脚本一致）
        # EN: Fix the parser's spelling mistake: resume_languge → resume_language (consistent with the liepin script)
        # JA: パーサーの綴りの誤りを修正する：resume_languge → resume_language（liepin のスクリプトと一致させる）
        if "resume_languge" in r and "resume_language" not in r:
            r["resume_language"] = r.pop("resume_languge")
        elif "resume_languge" in r and "resume_language" in r:
            r.pop("resume_languge", None)
        # 0 号位强制标 zh
        # EN: Force slot 0 to be labelled zh
        # JA: 0 番目を zh と強制的に表示する
        if idx == 0:
            r["resume_language"] = "zh"
        elif not r.get("resume_language"):
            r["resume_language"] = "zh"

        # 确保所有列表字段存在（兜底 []）
        # EN: Make sure all list fields exist (fallback [])
        # JA: すべてのリストのフィールドが存在するようにする（最終手段で []）
        for list_key in ("work_experiences", "education_list", "project_list", "training_list",
                         "certificate_list", "language_list", "skills_list", "communication_list"):
            if list_key not in r or not isinstance(r[list_key], list):
                r[list_key] = []
        if "base_info" not in r or not isinstance(r["base_info"], dict):
            r["base_info"] = {}
        if "expected_info" not in r or not isinstance(r["expected_info"], dict):
            r["expected_info"] = {}

        # ============ 每个 resume 的后处理 ============
        # EN: ============ Post-processing of each resume ============
        # JA: ============ 各 resume の後処理 ============
        base_info = r["base_info"]
        # 姓名兜底（三重防护）
        # EN: Name fallback (triple protection)
        # JA: 氏名の最終手段（3 重の保護）
        name = (base_info.get("full_name") or "").strip()
        if not name or name in ("待确认姓名", "未知", "简历", "无关联职位简历") or re.search(r"(?:工程师|经理|主管|专员|开发|运营|总监|销售|翻译)", name):
            # 从 raw_text 特征提取：姓名下一行是 XX年工作经验 / 男/女 / XX岁
            # EN: Extract from raw_text features: the line after the name is XX年工作经验 (XX years of experience) / 男/女 (male/female) / XX岁 (age)
            # JA: raw_text の特徴から抽出する：氏名の次の行が XX年工作经验（経験 XX 年）／男／女／XX岁（年齢）
            m_raw = re.search(
                r"\n\s*([^\s\n:：|│]{2,8})\s*\n\s*(?:\d+[-～~]\d+年工作经验|\d+年工作经验|[男女]\s*[|│]|[\d]{1,2}岁)",
                plain,
            )
            if m_raw:
                cand = m_raw.group(1).strip()
                if not re.search(
                    r"(?:更新时间|简历关键字|最近工作|最高学历|自我评价|工作经验|工作经历|项目经历|教育经历|语言能力)",
                    cand,
                ):
                    base_info["full_name"] = cand
                    name = cand
            else:
                # 从文件名提取 {序号}_{姓名}.html
                # EN: Extract from the file name {sequence}_{name}.html
                # JA: ファイル名 {通し番号}_{氏名}.html から抽出する
                m_fn = re.match(r"^\d+_([^\s\-_.]{2,8})", filename)
                if m_fn:
                    base_info["full_name"] = m_fn.group(1).strip()
                    name = base_info["full_name"]

        # platform_from 标识
        # EN: platform_from label
        # JA: platform_from の識別
        if "platform_from" not in base_info or not base_info["platform_from"]:
            base_info["platform_from"] = platform

        # ========== 复用 run_zhilian_html_to_json.py 现成解析器：parser 漏提取时兜底（必须在规范化之前！） ==========
        # EN: ========== Reuse the existing parsers of run_zhilian_html_to_json.py: fallback when the parser missed something (must run before normalisation!) ==========
        # JA: ========== run_zhilian_html_to_json.py の既存のパーサーを再利用：パーサーが取りこぼしたときの最終手段（正規化の前に実行すること！）==========
        try:
            if BeautifulSoup is not None:
                soup = BeautifulSoup(html_text, "html.parser")
            else:
                soup = None
            # 1. expected_info：parser 没抽到值时，用智联的再提一次
            # EN: 1. expected_info: when the parser extracted no value, extract once more with Zhaopin's
            # JA: 1. expected_info：パーサーが値を取れなかった場合は、Zhaopin のものでもう一度抽出する
            cur_ei = r.get("expected_info") or {}
            ei_empty = True
            if isinstance(cur_ei, dict):
                for v in cur_ei.values():
                    if v and str(v).strip():
                        ei_empty = False
                        break
            if ei_empty:
                zhilian_ei = _parse_zhilian_expected_info(plain)
                if zhilian_ei:
                    if isinstance(zhilian_ei, list) and zhilian_ei and isinstance(zhilian_ei[0], dict):
                        r["expected_info"] = zhilian_ei[0]
                    elif isinstance(zhilian_ei, dict):
                        r["expected_info"] = zhilian_ei
            # 2. work_experiences：空 / company_name 空 / position 像"担当"占位 / company_name 含乱（"企业性质""规模""｜"分隔 2+）→ 清坏条目 + 合并智联
            # EN: 2. work_experiences: empty / company_name empty / position looks like a placeholder such as "担当" / company_name is garbled ("企业性质" (enterprise type), "规模" (size), 2+ "｜" separators) → remove bad entries + merge Zhaopin's
            # JA: 2. work_experiences：空 / company_name が空 / position が「担当」のようなプレースホルダー / company_name が乱れている（「企业性质」（企業の性質）「规模」（規模）、「｜」区切りが 2 個以上）→ 悪い項目を除き Zhaopin のものを統合する
            cur_works = r.get("work_experiences") or []
            _bad_work_indices: set[int] = set()
            for _i, w in enumerate(cur_works):
                if not isinstance(w, dict):
                    _bad_work_indices.add(_i)
                    continue
                _cn = (w.get("company_name") or "").strip()
                _pos = (w.get("position") or "").strip()
                _resp = (w.get("position_responsibilities") or "").strip()
                # 条件1: company_name 含明显分隔错配（企业性质/规模/｜出现 >=2 次或含这些关键词且不含"公司/集团/有限/厂")
                # EN: Condition 1: company_name contains obvious separator mismatches (企业性质/规模/｜ appears >= 2 times, or contains these keywords without "公司/集团/有限/厂")
                # JA: 条件 1：company_name に明らかな区切りの不一致がある（企业性质／规模／｜が 2 回以上現れる、またはこれらのキーワードを含み「公司／集团／有限／厂」を含まない）
                _is_company_good = bool(
                    _cn
                    and (
                        "公司" in _cn or "集团" in _cn or "有限" in _cn or "厂" in _cn
                        or "社" in _cn  # 日文"会社"
                        # EN: Japanese "会社" (company)
                        # JA: 日本語の「会社」
                        or "工作室" in _cn or "银行" in _cn or "医院" in _cn
                        or "学校" in _cn or "大学" in _cn or "研究院" in _cn
                    )
                )
                _bad_company_cn = (
                    (not _is_company_good)
                    and any(k in _cn for k in ("企业性质", "规模", "｜", "|", "性质", "民营", "国企", "外资", "上市公司"))
                ) or (
                    # 分隔符2+个 且 不含典型公司词
                    # EN: 2+ separators and no typical company word
                    # JA: 区切りが 2 個以上で、典型的な会社の語を含まない
                    sum(c in _cn for c in ("|", "｜")) >= 2
                    and not _is_company_good
                )
                # 条件2: position 是占位/看起来错（"担当"/空/等，同时 resp 首行有"XX工程师 | XXXX元/月"典型 position+薪资）
                # EN: Condition 2: position is a placeholder / looks wrong ("担当" / empty / etc., while the first resp line has a typical position + salary like "XX工程师 | XXXX元/月")
                # JA: 条件 2：position がプレースホルダーまたは誤りに見える（「担当」・空など。同時に resp の 1 行目に「XX工程师 | XXXX元/月」のような典型的な職位 + 給与がある）
                _bad_position_placeholder = (
                    _pos in ("担当", "负责", "工作", "员工", "职员", "其他", "")
                    and bool(re.search(r"^[^\n]{1,30}\s*\|\s*\d+(?:[\d,\-]*)元", _resp))
                )
                # 条件3: company_name 空
                # EN: Condition 3: company_name empty
                # JA: 条件 3：company_name が空
                _empty_cn = not _cn
                if _bad_company_cn or _bad_position_placeholder or _empty_cn:
                    _bad_work_indices.add(_i)
            if _bad_work_indices:
                cur_works = [w for _i, w in enumerate(cur_works) if _i not in _bad_work_indices]
                r["work_experiences"] = cur_works

            work_needs_fallback = (not cur_works) or any(
                not (w.get("company_name") or "").strip() for w in cur_works if isinstance(w, dict)
            )
            if work_needs_fallback:
                zhilian_works = _parse_zhilian_work_experiences(soup, plain)
                if zhilian_works:
                    if not cur_works:
                        r["work_experiences"] = zhilian_works
                    else:
                        seen_w = set()
                        for w in cur_works:
                            if isinstance(w, dict):
                                seen_w.add(
                                    (
                                        (w.get("company_name") or "").strip(),
                                        (w.get("position_start") or "").strip(),
                                    )
                                )
                        for w in zhilian_works:
                            if not isinstance(w, dict):
                                continue
                            key = (
                                (w.get("company_name") or "").strip(),
                                (w.get("position_start") or "").strip(),
                            )
                            if key not in seen_w:
                                cur_works.append(w)
                                seen_w.add(key)
            # 3. education_list：空 / 存在 school_name 空 / 存在 degree_type 有学校关键词（说明有内容没拆）时，合并智联解析
            # EN: 3. education_list: when empty / some school_name is empty / some degree_type contains school keywords (content not split), merge Zhaopin's parse
            # JA: 3. education_list：空 / school_name が空のものがある / degree_type に学校のキーワードを含むものがある（内容が分割されていない）場合は、Zhaopin の解析結果を統合する
            cur_edus = r.get("education_list") or []
            _SCHOOL_SUFFIXES = ("大学", "学院", "学校", "分校", "高中", "中学", "小学")
            _DEGREE_WORDS = ("博士后", "博士", "硕士", "本科", "大专", "专科", "中专", "职高", "高中", "初中", "小学")
            _BAD_SECTION_NAMES = (
                "培训经历", "培训", "项目经历", "项目", "工作经历", "工作经验",
                "语言能力", "专业技能", "技能", "自我评价", "证书", "所获证书",
                "求职意向", "在校学习情况", "在校情况", "实践经历", "校园经历",
                "实习经历", "培训描述", "附加信息", "其他信息", "▲培训经历",
                "▲技能/语言", "▲证书", "技能/语言", "其他",
                "简历内容", "简历", "个人简历", "个人信息", "基本信息", "个人资料", "基本资料", "简表",
                "校内职务", "校园职务", "社团职务", "学生会", "社团活动", "在校职务",
            )
            # 典型校园/学生组织职务词（出现在 school_name / school_major_name 里时，若不是学校后缀，判为校园经历误抽为教育）
            # EN: Typical campus/student-organisation post words (when they appear in school_name / school_major_name without a school suffix, judged a campus experience mis-extracted as education)
            # JA: 典型的な学内・学生団体の役職の語（school_name / school_major_name に現れ、学校の接尾辞がない場合は、学内の経験が学歴として誤抽出されたと判定する）
            _OFFICE_TITLE_KEYWORDS = (
                "楼长", "副楼长", "班长", "副班长", "团支书", "团支部书记", "会长", "副会长", "部长",
                "副部长", "社长", "副社长", "主席", "副主席", "委员", "干事", "助理", "课代表",
                "组长", "副组长", "队长", "副队长", "部长助理", "办公室主任", "秘书长", "理事长",
            )
            _bad_indices: set[int] = set()
            for _i, e in enumerate(cur_edus):
                if not isinstance(e, dict):
                    _bad_indices.add(_i)
                    continue
                _sn = (e.get("school_name") or "").strip()
                _mn = (e.get("school_major_name") or "").strip()
                _dt = (e.get("school_degree_type") or "").strip()
                # 1) school_name 本身是 section 标题/伪标题（如"培训经历""▲培训经历"）
                # EN: 1) school_name itself is a section heading / pseudo-heading (e.g. "培训经历" "▲培训经历" (training history))
                # JA: 1) school_name 自体がセクション見出し・偽の見出し（例：「培训经历」「▲培训经历」（研修歴））
                _sn_is_bad_header = (
                    _sn in _BAD_SECTION_NAMES
                    or any(h in _sn for h in ("培训机构：", "培训地点：", "培训描述：", "培训机构:", "培训地点:"))
                    or _sn.startswith("▲")
                    or _sn.startswith("简 历")
                )
                # 1b) school_name 含职务关键词 且 **不含** SCHOOL_SUFFIXES → 判成校园职务误抽
                # EN: 1b) school_name contains post keywords and **does not contain** SCHOOL_SUFFIXES → judged a mis-extracted campus post
                # JA: 1b) school_name に役職のキーワードがあり、SCHOOL_SUFFIXES を**含まない** → 学内の役職の誤抽出と判定する
                _sn_office_title = (
                    any(kw in _sn for kw in _OFFICE_TITLE_KEYWORDS)
                    and not any(suf in _sn for suf in _SCHOOL_SUFFIXES)
                )
                # 1c) degree_type 里含「姓名：/学历：/专业：/年龄：/身高：/政治面貌：」这类简历头标签 ≥2 个 → 这条 edu 把整个简历表头塞 degree 里了，整条丢（fallback zhilian）
                # EN: 1c) degree_type contains ≥2 résumé header labels like "姓名：/学历：/专业：/年龄：/身高：/政治面貌：" (name/degree/major/age/height/political status) → this edu entry stuffed the whole résumé header into degree; drop the whole entry (fallback to zhilian)
                # JA: 1c) degree_type に「姓名：／学历：／专业：／年龄：／身高：／政治面貌：」（氏名・学歴・専攻・年齢・身長・政治的身分）のような履歴書の見出しのラベルが 2 個以上ある → この edu は履歴書の見出し全体を degree に入れているので、項目全体を捨てる（zhilian に戻す）
                _resume_header_tags_in_dt = sum(1 for tag in ("姓名：", "姓名:", "学历：", "学历:", "专业：", "专业:",
                                                              "年龄：", "年龄:", "身高：", "身高:", "政治面貌：",
                                                              "政治面貌:", "性别：", "性别:", "电话：", "电话:",
                                                              "手机：", "手机:", "邮箱：", "邮箱:") if tag in _dt)
                _dt_is_resume_header = _resume_header_tags_in_dt >= 2
                # 2) school_major_name 是 section 标签（如"培训机构：""培训机构:"）
                # EN: 2) school_major_name is a section label (e.g. "培训机构：" "培训机构:" (training institution:))
                # JA: 2) school_major_name がセクションのラベル（例：「培训机构：」「培训机构:」（研修機関：））
                _mn_is_bad_header = (
                    _mn in ("培训机构：", "培训机构", "培训地点：", "培训地点",
                            "培训描述：", "培训描述", "培训", "证书", "专业技能：",
                            "在校学习情况", "在校情况", "在校", "实践经历", "校园经历",
                            "实习经历", "自我评价", "求职意向", "附加信息", "其他信息", "其他")
                    or _mn in _BAD_SECTION_NAMES
                    or _mn.startswith("▲")
                )
                # 2b) major 里含职务关键词 且 非 SCHOOL_SUFFIXES → 校园职务误抽
                # EN: 2b) major contains post keywords and no SCHOOL_SUFFIXES → mis-extracted campus post
                # JA: 2b) major に役職のキーワードがあり SCHOOL_SUFFIXES がない → 学内の役職の誤抽出
                _mn_office_title = (
                    any(kw in _mn for kw in _OFFICE_TITLE_KEYWORDS)
                    and not any(suf in _mn for suf in _SCHOOL_SUFFIXES)
                )
                # 3) degree_type 是 section 标签（如"全日制大学"+纯 rank 字 = 4 这种？）
                # 4) degree_type 里塞了多个学校关键词（>=2）→ 解析乱
                # EN: 3) degree_type is a section label (like "全日制大学" + a bare rank character = 4?)
                #     4) degree_type is stuffed with several school keywords (>=2) → garbled parse
                # JA: 3) degree_type がセクションのラベル（「全日制大学」+ rank の文字だけ = 4 のようなもの？）
                #     4) degree_type に学校のキーワードが複数（2 個以上）詰め込まれている → 解析が乱れている
                _suf_count = sum(1 for s in _SCHOOL_SUFFIXES if s in _dt)
                # 5) school_name 里也含学校关键词（非后缀），说明 school_name 可能也没拆干净，和 degree_type 加起来 >=2 也判坏
                # EN: 5) school_name also contains school keywords (not as a suffix), meaning school_name may not be cleanly split either; if it adds up to >=2 together with degree_type, also judge it bad
                # JA: 5) school_name にも学校のキーワード（接尾辞ではない）がある場合は、school_name もきれいに分割されていない可能性がある。degree_type と合わせて 2 個以上なら、これも悪いと判定する
                _suf_count += sum(1 for s in _SCHOOL_SUFFIXES if s in _sn)
                # 6) major_name 里有学校关键词 → 错把学校塞到了 major
                # EN: 6) major_name contains school keywords → a school was wrongly stuffed into major
                # JA: 6) major_name に学校のキーワードがある → 学校が誤って major に入れられている
                _has_school_in_major = any(s in _mn for s in _SCHOOL_SUFFIXES)
                # 7) school_name 里有 degree 词（如"大专""硕士"）→ 也说明错分
                # EN: 7) school_name contains degree words (e.g. "大专" (junior college), "硕士" (master)) → also indicates a wrong split
                # JA: 7) school_name に学位の語（例：「大专」（短大・専門）、「硕士」（修士））がある → これも誤った分割を示す
                _has_deg_in_school = any(dw in _sn for dw in _DEGREE_WORDS)
                # 8) major_name 是"证书"等非专业词 → 也是 parser 分错
                # EN: 8) major_name is a non-major word like "证书" (certificate) → also a parser mis-split
                # JA: 8) major_name が「证书」（資格）などの専攻ではない語 → これもパーサーの誤った分割
                _bad_major = _mn in ("证书", "认证", "执照", "其他", "无", "-", "培训机构", "培训",
                                     "在校学习情况", "在校情况", "在校", "附加信息", "其他信息",
                                     "实践经历", "校园经历", "实习经历", "自我评价", "求职意向")
                # 9) degree_type 含非 degree 词（如"全日制大学/非学历"是允许的，但如果连学历词都没有且 sn/mn 都坏，判坏）
                # 综合判定
                # EN: 9) degree_type contains non-degree words (e.g. "全日制大学/非学历" (full-time university / non-degree) are allowed, but if there is no degree word at all and both sn/mn are bad, judge it bad)
                #     Overall decision
                # JA: 9) degree_type に学位以外の語がある（「全日制大学／非学历」（全日制大学・学歴外）は許可するが、学歴の語がまったくなく sn/mn の両方が悪ければ、悪いと判定する）
                #     総合的な判定
                if (
                    _sn_is_bad_header
                    or _sn_office_title
                    or _mn_is_bad_header
                    or _mn_office_title
                    or _dt_is_resume_header
                    or _suf_count >= 2
                    or _has_school_in_major
                    or _has_deg_in_school
                    or (_bad_major and (not _sn or not _dt or _suf_count >= 1 or _sn_is_bad_header or _mn_is_bad_header))
                ):
                    _bad_indices.add(_i)
            # 剔除已坏的元素
            # EN: Remove the bad elements
            # JA: 悪い要素を取り除く
            if _bad_indices:
                cur_edus = [e for _i, e in enumerate(cur_edus) if _i not in _bad_indices]
                r["education_list"] = cur_edus

            edu_needs_fallback = (not cur_edus) or any(
                (not (e.get("school_name") or "").strip())
                or any(
                    suf in (e.get("school_degree_type") or "")
                    and not (e.get("school_degree_type") or "").endswith(suf)
                    for suf in _SCHOOL_SUFFIXES
                )
                or any(suf in (e.get("school_major_name") or "") for suf in _SCHOOL_SUFFIXES)
                for e in cur_edus
                if isinstance(e, dict)
            )
            if edu_needs_fallback:
                zhilian_edus = _parse_zhilian_education(plain)
                if zhilian_edus:
                    if not cur_edus:
                        r["education_list"] = zhilian_edus
                    else:
                        seen_e = set()
                        for e in cur_edus:
                            if isinstance(e, dict):
                                seen_e.add(
                                    (
                                        (e.get("school_start_ym") or "").strip(),
                                        (e.get("school_end_ym") or "").strip(),
                                    )
                                )
                        for e in zhilian_edus:
                            if not isinstance(e, dict):
                                continue
                            key = (
                                (e.get("school_start_ym") or "").strip(),
                                (e.get("school_end_ym") or "").strip(),
                            )
                            if key not in seen_e:
                                cur_edus.append(e)
                                seen_e.add(key)
            # 3.5 training_list：识别伪条目（把技能/证书区的内容当 training 的 parser 误识别）清除，同时把证书类伪 training 合并到 certificate_list
            # EN: 3.5 training_list: identify and remove pseudo entries (the parser misidentifying skills/certificate content as training), while merging certificate-like pseudo training into certificate_list
            # JA: 3.5 training_list：偽の項目（パーサーがスキル・資格欄の内容を研修と誤認したもの）を識別して除去し、同時に資格のような偽の研修は certificate_list に統合する
            cur_trains = r.get("training_list") or []
            _BAD_TRAIN_HEADERS = (
                "▲技能/语言", "技能/语言", "技能", "专业技能", "▲证书", "证书", "所获证书", "证书资格",
                "其他", "▲其他", "附加信息", "▲培训经历", "工作经历", "项目经历", "教育经历",
                "自我评价", "求职意向", "语言能力",
            )
            _CERT_KEYWORDS = (
                "证书", "资格", "内审员", "审核员", "检验工", "营养师", "工程师",
                "资格证", "执业", "注册", "CFA", "CPA", "PMP", "计算机二级", "计算机三级",
                "CET", "TEM", "雅思", "托福", "会计从业", "会计职称", "医师", "护士",
                "教师", "驾驶证", "驾照", "食品检验", "HACCP", "ISO",
            )
            _bad_train_indices: set[int] = set()
            _candidates_from_trains: list[tuple[str, str]] = []  # (cert_name, time_str)
            for _i, t in enumerate(cur_trains):
                if not isinstance(t, dict):
                    _bad_train_indices.add(_i)
                    continue
                _org = (t.get("organization_name") or "").strip()
                _tname = (t.get("training_name") or "").strip()
                _cname = (t.get("certificate_name") or "").strip()
                _desc = (t.get("description") or "").strip()
                _start = (t.get("start_ym") or "").strip()
                _end = (t.get("end_ym") or "").strip()
                # 1) org 或 tname 是 section 伪标题（▲开头/区名）
                # EN: 1) org or tname is a section pseudo-heading (starting with ▲ / a section name)
                # JA: 1) org か tname がセクションの偽の見出し（▲で始まる・欄の名前）
                _header_bad = (
                    _org in _BAD_TRAIN_HEADERS
                    or _tname in _BAD_TRAIN_HEADERS
                    or any(s in _org for s in ("MS WORD", "MS Excel", "MS Office", "Word", "Excel", "Powerpoint", "PPT"))
                    or any(s in _tname for s in ("MS WORD", "MS Excel", "MS Office", "Word", "Excel", "Powerpoint", "PPT"))
                )
                # 2) org == tname == 证书资格名，没有 start/end（典型 parser 误抽证书为 training）
                # EN: 2) org == tname == a certificate/qualification name, with no start/end (the parser typically mis-extracting a certificate as training)
                # JA: 2) org == tname == 資格名で、start/end がない（パーサーが資格を研修として誤抽出する典型）
                _looks_like_cert = (
                    bool(_org)
                    and _org == _tname
                    and not _start
                    and not _end
                    and any(kw in _org for kw in _CERT_KEYWORDS)
                )
                # 2b) 新放宽：org 空，但 tname 有证书关键词，日期是空或同月 (start==end)，且 (certificate_name='所获证书：'壳 或 desc 有"拿到/考取/获得/自考/自学/通过...考试/获证/拿证/颁发"类证书取得行文) —— 也当伪 training
                # EN: 2b) Newly relaxed: org empty, but tname has certificate keywords, the dates are empty or the same month (start==end), and (certificate_name is the '所获证书：' (certificate obtained:) shell, or desc has certificate-obtaining phrasing like "拿到/考取/获得/自考/自学/通过...考试/获证/拿证/颁发" (obtained / passed / self-study / passed ... exam / certified / issued)) — also treated as pseudo training
                # JA: 2b) 新たに緩めた条件：org が空だが tname に資格のキーワードがあり、日付が空か同じ月（start==end）で、かつ（certificate_name が「所获证书：」（取得資格：）の殻、または desc に「拿到／考取／获得／自考／自学／通过...考试／获证／拿证／颁发」（取得・合格・独学・〜試験に合格・認定・交付）などの資格取得の言い回しがある）— これも偽の研修とする
                _no_or_same_day = (not _start and not _end) or (_start and _end and _start == _end)
                _cname_shell = bool(_cname) and _cname in ("所获证书：", "所获证书:", "证书：", "证书:", "证书说明：", "证书说明:")
                _desc_mentions_cert_get = bool(_desc) and re.search(
                    r"(拿到|考取|获得|取得|自考|自学|通过|考试|获证|拿证|颁发|发证|合格|通过了|通过了.*证书|.*证书|.*一级|.*二级|.*三级|.*四级)",
                    _desc,
                )
                _looks_like_cert_relaxed = (
                    (not _org or _org in ("培训机构：", "培训描述：", "培训地点：", "自学", "自考"))
                    and bool(_tname)
                    and _no_or_same_day
                    and any(kw in _tname for kw in _CERT_KEYWORDS)
                    and (_cname_shell or _desc_mentions_cert_get or (not _start and not _end and not _desc))
                )
                # 2c) tname 前缀序号 "2\xa0\xa0日语一级" → 剥序号后如果首字段是 N1/N2/日语一级 这种语言证书 且 机构=自学/空 → 也当证书
                # EN: 2c) tname with a sequence-number prefix "2\xa0\xa0日语一级" → after stripping the number, if the first field is a language certificate like N1/N2/日语一级 (Japanese level 1) and the provider is self-study/empty → also treat it as a certificate
                # JA: 2c) tname に通し番号の接頭辞がある「2\xa0\xa0日语一级」→ 番号を除いた後、最初のフィールドが N1／N2／日语一级（日本語 1 級）のような語学資格で、機関が独学・空なら → これも資格とする
                if not _looks_like_cert_relaxed and _tname:
                    _tname_stripped = re.sub(r"^\s*\d{1,2}[\s\xa0]+\s*", "", _tname).strip()
                    _tname_stripped2 = _tname_stripped
                    if _tname_stripped2 != _tname and _tname_stripped2:
                        _looks_like_cert_relaxed = (
                            (not _org or _org in ("培训机构：", "自学", "自考", "培训描述：", "培训地点："))
                            and _no_or_same_day
                            and any(kw in _tname_stripped2 for kw in _CERT_KEYWORDS)
                            and (_cname_shell or _desc_mentions_cert_get or not _start)
                        )
                        if _looks_like_cert_relaxed:
                            _tname = _tname_stripped2  # 后面提取 cert_name 就用剥完序的名字
                            # EN: Later, when extracting cert_name, use the name with the number stripped
                            # JA: 後で cert_name を抽出するときは、番号を除いた名前を使う
                # 3) org 是 "▲培训经历" 但后面紧跟着是证书名（四级公共营养师这种资格）
                # EN: 3) org is "▲培训经历" (training history) but is immediately followed by a certificate name (a qualification like level-4 public nutritionist)
                # JA: 3) org が「▲培训经历」（研修歴）だが、すぐ後に資格名が続く（4 級公共栄養士のような資格）
                if _header_bad or _looks_like_cert or _looks_like_cert_relaxed:
                    _bad_train_indices.add(_i)
                    # 尝试把证书类伪条目 提取成 cert
                    # EN: Try extracting certificate-like pseudo entries as cert
                    # JA: 資格のような偽の項目を cert として抽出してみる
                    for src in (_tname, _org, _cname, _desc):
                        if not src:
                            continue
                        # 取首行、去掉 描述里换行
                        # EN: Take the first line and remove line breaks in the description
                        # JA: 1 行目を取り、説明内の改行を除く
                        first = src.splitlines()[0].strip()
                        # 提取前面时间 /NN、/N 去掉
                        # EN: Extract the leading time and remove /NN, /N
                        # JA: 前の時期を取り出し、/NN、/N を除く
                        first_clean = re.sub(r"^/\d{1,2}\s*", "", first).strip()
                        # 去序号 1 / 2\xa0\xa0
                        # EN: Remove sequence numbers 1 / 2\xa0\xa0
                        # JA: 通し番号 1 / 2\xa0\xa0 を除く
                        first_clean = re.sub(r"^\s*\d{1,2}[\s\xa0]+\s*", "", first_clean).strip()
                        # 去掉 「Xxxx体系/xxxx体系/注册审核员（xxx内审员）」里的换行/空格粘字
                        # EN: Remove line breaks/spaces stuck in "Xxxx体系/xxxx体系/注册审核员（xxx内审员）" (XXX system / registered auditor (XXX internal auditor))
                        # JA: 「Xxxx体系／xxxx体系／注册审核员（xxx内审员）」（〜体系・登録審査員（〜内部監査員））にくっついた改行・空白を除く
                        cert_name = first_clean
                        if any(kw in cert_name for kw in _CERT_KEYWORDS) and len(cert_name) >= 2 and len(cert_name) <= 80:
                            # 时间：在 _desc 里找 20xx/N  或 20xx年x月
                            # EN: Time: look for 20xx/N or 20xx年x月 in _desc
                            # JA: 時期：_desc から 20xx/N または 20xx年x月 を探す
                            ttime = ""
                            m_t = re.search(r"(20\d{2})\s*[/\-.年]\s*(\d{1,2})", _desc + " " + _start + " " + _end)
                            if m_t:
                                ttime = f"{int(m_t.group(1)):04d}-{int(m_t.group(2)):02d}"
                            if ttime and (not cert_name.endswith(ttime)):
                                pass
                            _candidates_from_trains.append((cert_name, ttime))
                            break  # 只提一个
                            # EN: Extract only one
                            # JA: 1 つだけ取り出す
            if _bad_train_indices:
                cur_trains = [t for _i, t in enumerate(cur_trains) if _i not in _bad_train_indices]
                r["training_list"] = cur_trains
            # 把伪 training 里提出来的证书 candidates 合并进 certificate_list（不去重，先补空，后面再统一）
            # EN: Merge the certificate candidates extracted from pseudo training into certificate_list (no dedup; fill gaps first, unify later)
            # JA: 偽の研修から取り出した資格の候補を certificate_list に統合する（重複排除はせず、まず空きを埋め、後で一括で整える）
            if _candidates_from_trains:
                existing_certs = r.get("certificate_list") or []
                if not isinstance(existing_certs, list):
                    existing_certs = []
                seen_cert = set()
                for c in existing_certs:
                    if isinstance(c, dict):
                        seen_cert.add(((c.get("certificate_name") or "").strip(), (c.get("certificate_time") or "").strip()))
                for cname, ctime in _candidates_from_trains:
                    key = (cname, ctime)
                    if key in seen_cert:
                        continue
                    seen_cert.add(key)
                    existing_certs.append({
                        "certificate_name": cname,
                        "certificate_type": "证书",
                        "certificate_time": ctime,
                    })
                r["certificate_list"] = existing_certs

            # 4. certificate_list：空时用智联的
            # EN: 4. certificate_list: use Zhaopin's when empty
            # JA: 4. certificate_list：空なら Zhaopin のものを使う
            if not r.get("certificate_list"):
                zhilian_certs = _parse_zhilian_certificates(plain, soup)
                if zhilian_certs:
                    r["certificate_list"] = zhilian_certs
            # 5. language_list：空时用智联的
            # EN: 5. language_list: use Zhaopin's when empty
            # JA: 5. language_list：空なら Zhaopin のものを使う
            if not r.get("language_list"):
                zhilian_langs = _parse_zhilian_languages(plain, soup)
                if zhilian_langs:
                    r["language_list"] = zhilian_langs
            # 6. skills_list：空时用智联的
            # EN: 6. skills_list: use Zhaopin's when empty
            # JA: 6. skills_list：空なら Zhaopin のものを使う
            if not r.get("skills_list"):
                zhilian_skills = _parse_zhilian_skills(plain)
                if zhilian_skills:
                    r["skills_list"] = zhilian_skills
        except Exception:
            # 兜底解析器失败不影响主流程
            # EN: A failure of the fallback parsers does not affect the main flow
            # JA: 最終手段のパーサーが失敗してもメインフローには影響しない
            pass

        # expected_info 规范化（返回 dict → 包成 1 元素数组）
        # EN: Normalise expected_info (returns a dict → wrapped into a 1-element array)
        # JA: expected_info の正規化（dict を返す → 要素 1 つの配列に包む）
        ei_in = r.get("expected_info") or {}
        if isinstance(ei_in, list) and ei_in and isinstance(ei_in[0], dict):
            ei_in = ei_in[0]
        _exp_dict = _normalize_expected_info(ei_in, plain)
        r["expected_info"] = [_exp_dict]

        # education_list 规范化
        # EN: Normalise education_list
        # JA: education_list の正規化
        r["education_list"] = _normalize_education_list_and_fix_rank(r.get("education_list") or [])
        # 再清一次 education 的 end<start（start/end 交换）
        # EN: Clean education end<start once more (swap start/end)
        # JA: 学歴の end<start をもう一度整理する（start と end を入れ替える）
        for e in r.get("education_list") or []:
            if isinstance(e, dict):
                ns, ne = _swap_end_start_when_reversed(e.get("school_start_ym") or "", e.get("school_end_ym") or "", status="")
                e["school_start_ym"] = ns
                e["school_end_ym"] = ne

        # work_experiences 公司名清理 + 剥 raw_text + 补 position_achievements + start/end 交换
        # EN: work_experiences: clean company names + strip raw_text + fill position_achievements + swap start/end
        # JA: work_experiences：会社名の整理 + raw_text の除去 + position_achievements の補完 + start と end の入れ替え
        works = []
        for w in r.get("work_experiences") or []:
            if not isinstance(w, dict):
                continue
            w = dict(w)
            w.pop("raw_text", None)
            cname = (w.get("company_name") or "").strip()
            if cname:
                # 去时长括号 / \xa0 / \r\n
                # EN: Remove tenure brackets / \xa0 / \r\n
                # JA: 在職期間の括弧・\xa0・\r\n を除く
                cname = cname.replace("\xa0", " ")
                cname = re.sub(r"[（(]\s*\d+\s*年?\s*\d*\s*个?月?\s*[）)]", "", cname)
                cname = cname.replace("\r", " ").replace("\n", " ").strip(" 　\t-—–*·")
                # 公司名粘连公司性质/规模/行业时 → 在第一个分隔符 或"公司性质"等前缀 截断
                # 例："计算机软件 | 企业性质：民营..." → 去掉 " | 企业性质..." 及之后 → "计算机软件" 可能还不对，但多数情况下公司名在前
                # 截断策略 1：关键词前缀
                # EN: When the company name has company type/size/industry stuck to it → truncate at the first separator or at prefixes like "公司性质" (company type)
                #     e.g.: "计算机软件 | 企业性质：民营..." → remove " | 企业性质..." and what follows → "计算机软件" may still not be right, but in most cases the company name comes first
                #     Truncation strategy 1: keyword prefixes
                # JA: 会社名に会社の性質・規模・業界がくっついている場合 → 最初の区切りか「公司性质」（会社の性質）などの接頭辞の位置で切る
                #     例："计算机软件 | 企业性质：民营..." → " | 企业性质..." 以降を除く →「计算机软件」でもまだ正しくないことがあるが、多くの場合は会社名が先にある
                #     切断方針 1：キーワードの接頭辞
                TAIL_NOISE = ("少于", "小于", "低于", "不超过", "不足", "不到", "员工", "公司性质",
                              "公司行业", "公司规模", "民营", "外资", "合资", "国企", "上市",
                              "企业性质", "规模：", "规模:", "行业：", "行业:", "性质：", "性质:", "｜企业", "|企业")
                cut = len(cname)
                for pref in TAIL_NOISE:
                    idx = cname.find(pref)
                    if idx > 2:
                        cut = min(cut, idx)
                # 截断策略 2：company_industry 已存在（没塞公司名里）时，如果公司名里还出现 2+ 个｜| 分隔符 → 在第 1 个分隔符截断
                # 一般：真公司名 = "公司/有限/集团"后缀，前面第一个分隔符如果没公司后缀，就在第一个分隔符截断，保留含公司后缀的前缀；否则第一段
                # EN: Truncation strategy 2: when company_industry already exists (not stuffed into the company name), if the company name still has 2+ ｜| separators → truncate at the first separator
                #     In general: the real company name = the one with a "公司/有限/集团" suffix; if the part before the first separator has no company suffix, truncate at the first separator, keeping the prefix with a company suffix; otherwise the first segment
                # JA: 切断方針 2：company_industry がすでにある（会社名に入っていない）のに、会社名にまだ ｜| の区切りが 2 個以上ある → 最初の区切りで切る
                #     一般に：本当の会社名 =「公司／有限／集团」の接尾辞を持つもの。最初の区切りの前に会社の接尾辞がなければ最初の区切りで切り、会社の接尾辞を持つ接頭部分を残す。それ以外は最初の部分
                if sum(c in cname for c in ("|", "｜")) >= 2:
                    has_suffix = any(tok in cname for tok in ("公司", "有限", "集团", "厂", "银行", "医院", "学校", "大学", "社", "事务所", "工作室", "研究院"))
                    parts = re.split(r"[|｜]", cname)
                    parts = [p.strip() for p in parts if p.strip()]
                    if parts:
                        # 找第一个含 公司/集团/有限/社/... 的；找不到就第一个
                        # EN: Find the first one containing 公司/集团/有限/社/...; if none is found, take the first
                        # JA: 公司／集团／有限／社／… を含む最初のものを探し、見つからなければ最初のものを取る
                        pick = parts[0]
                        for p in parts:
                            if any(tok in p for tok in ("公司", "有限", "集团", "厂", "银行", "医院", "学校", "大学", "社", "事务所", "工作室", "研究院")):
                                pick = p
                                break
                        # 如果没找到好后缀且 cut==len(cname)，说明 strategy1 也没切掉；这里用 pick 替换 cname 当更像真公司名
                        # EN: If no good suffix was found and cut==len(cname), strategy 1 did not cut anything either; here replace cname with pick as the more company-like name
                        # JA: よい接尾辞が見つからず cut==len(cname) なら、方針 1 でも切れていない。ここでは cname を、より会社名らしい pick で置き換える
                        if (not has_suffix) or cut < len(cname):
                            pass
                        else:
                            cname = pick
                cname = cname[:cut].strip(" :：|｜-()（）/·*")
                w["company_name"] = cname
            # 补齐 position_achievements（validate_batch.py 强约束）
            # EN: Fill position_achievements (a hard requirement of validate_batch.py)
            # JA: position_achievements を補う（validate_batch.py の必須条件）
            w.setdefault("position_achievements", "")
            # 18 字段白名单（防莫名字段）
            # EN: 18-field whitelist (to prevent unexplained fields)
            # JA: 18 フィールドのホワイトリスト（不明なフィールドを防ぐ）
            WORK_ALLOW = {"company_name","company_employees","company_industry",
                          "position","position_type","position_salary","position_dept",
                          "position_report_to","position_subordinate",
                          "employment_type","annual_salary_min","annual_salary_max",
                          "status","position_start","position_resigned",
                          "resigned_reason","position_responsibilities","position_achievements"}
            w = {k: w.get(k, "") for k in WORK_ALLOW if k in w}
            for k in WORK_ALLOW:
                if k not in w: w[k] = ""
            # date 顺序
            # EN: Date order
            # JA: 日付の順序
            ns, ne = _swap_end_start_when_reversed(w.get("position_start") or "", w.get("position_resigned") or "", status=w.get("status") or "")
            w["position_start"] = ns
            w["position_resigned"] = ne
            works.append(w)
        r["work_experiences"] = works

        # project_list 规范化
        # EN: Normalise project_list
        # JA: project_list の正規化
        r["project_list"] = _normalize_project_list(r.get("project_list") or [])

        # training_list: 去 raw_text + 清理 org/tname 中的"培训机构：""培训地点："壳子 + 去伪条目
        # EN: training_list: remove raw_text + clean shells like "培训机构：" "培训地点：" (training institution / training place:) in org/tname + remove pseudo entries
        # JA: training_list：raw_text を除く + org/tname にある「培训机构：」「培训地点：」（研修機関・研修場所：）の殻を除く + 偽の項目を除く
        r["training_list"] = _normalize_training_list_cleanup(r.get("training_list") or [])

        # ============= 第二阶段：training 已被拆壳+清伪之后，把"证书获得时点被误记为 training"的条目迁移到 certificate_list（彭春辉 日语一级 类）=============
        # EN: ============= Stage 2: after training has been unshelled and cleaned of pseudo entries, migrate entries where "the time a certificate was obtained was mistakenly recorded as training" into certificate_list (like a past case with Japanese level 1) =============
        # JA: ============= 第 2 段階：training の殻を外し偽の項目を除いた後、「資格の取得時点が研修として誤って記録された」項目を certificate_list に移す（日本語 1 級のような過去の事例）=============
        _CERT_KW_POST = (
            "证书", "资格", "资质", "内审员", "审核员", "检验工", "营养师", "工程师",
            "资格证", "执业", "注册", "CFA", "CPA", "PMP", "ACCA", "FRM",
            "计算机二级", "计算机三级", "CET", "TEM", "雅思", "托福", "TOEFL", "IELTS", "GRE", "GMAT",
            "会计从业", "会计职称", "初级会计", "中级会计", "注册会计",
            "医师", "护士", "护师", "教师", "驾驶证", "驾照", "驾驶执照",
            "食品检验", "HACCP", "ISO", "GMP", "QS", "SC",
            "一级", "二级", "三级", "四级", "N1", "N2", "N3",
            "系统集成", "软考", "高项", "网络工程师", "软件设计师",
            "上岗证",
        )
        kept_trains = []
        cert_additions: list[tuple[str, str]] = []
        for t in (r.get("training_list") or []):
            if not isinstance(t, dict):
                continue
            _torg = (t.get("organization_name") or "").strip()
            _tname = (t.get("training_name") or "").strip()
            _tdesc = (t.get("description") or "").strip()
            _ts = (t.get("start_ym") or "").strip()
            _te = (t.get("end_ym") or "").strip()
            _tname_strip = re.sub(r"^\s*\d{1,2}[\s\xa0]+\s*", "", _tname).strip()
            _no_or_same = (not _ts and not _te) or (_ts and _te and _ts == _te)
            _org_ok_for_cert = (not _torg) or _torg in ("自学", "自考", "培训机构", "培训学校") or _torg.endswith(("学院", "学校", "中心"))
            _desc_has_get = bool(_tdesc) and re.search(
                r"(拿到|考取|获得|取得|自考|自学|通过|考试|获证|拿证|颁发|发证|合格|.*证书|.*一级|.*二级|.*三级|.*四级)",
                _tdesc,
            )
            _duration_month = 0
            ns = norm_date_str(_ts); ne = norm_date_str(_te)
            if ns and ne:
                _duration_month = month_distance(ne, ns)
            _long_enough_for_training = _duration_month >= 2  # ≥2 月跨度就算培训（例如会计上岗证培训 4 月课程），不迁移
            # EN: A span of ≥2 months counts as training (e.g. a 4-month accounting qualification course); do not migrate
            # JA: 2 か月以上の期間は研修とみなし（例：会計の就業資格の 4 か月のコース）、移さない
            _hit_cert_key = any(k in _tname_strip for k in _CERT_KW_POST)
            if (
                _hit_cert_key
                and _no_or_same
                and _org_ok_for_cert
                and (_desc_has_get or (not _tdesc))
                and not _long_enough_for_training
            ):
                # 记为证书迁移
                # EN: Record as a certificate migration
                # JA: 資格への移行として記録する
                cname = _tname_strip if _tname_strip else _tname
                ttime = _ts if _ts else _te
                if cname and 1 <= len(cname) <= 80:
                    cert_additions.append((cname, ttime))
                    continue  # 从 training 里去掉
                    # EN: Remove from training
                    # JA: training から取り除く
            kept_trains.append(t)
        if cert_additions:
            cur_certs = r.get("certificate_list") or []
            if not isinstance(cur_certs, list):
                cur_certs = []
            seen_pairs = set()
            for c in cur_certs:
                if isinstance(c, dict):
                    seen_pairs.add(
                        ((c.get("certificate_name") or "").strip(), (c.get("certificate_time") or "").strip())
                    )
            for cn, ct in cert_additions:
                key = (re.sub(r"^\s*\d{1,2}[\s\xa0]+\s*", "", cn).strip(), (ct or "").strip())
                if key in seen_pairs:
                    continue
                seen_pairs.add(key)
                cur_certs.append({
                    "certificate_name": key[0] if key[0] else cn,
                    "certificate_type": "证书",
                    "certificate_time": ct,
                })
            r["certificate_list"] = cur_certs
        r["training_list"] = kept_trains
        # 重排 training 序号
        # EN: Renumber training
        # JA: training の番号を振り直す
        for i, it in enumerate(r["training_list"] or [], 1):
            if isinstance(it, dict):
                it["sequence_no"] = i

        # certificate_list: 去伪条目（空名/section头）+ 去 raw_text
        # EN: certificate_list: remove pseudo entries (empty names / section headers) + remove raw_text
        # JA: certificate_list：偽の項目（空の名前・セクション見出し）を除く + raw_text を除く
        r["certificate_list"] = _normalize_certificate_list_cleanup(r.get("certificate_list") or [])
        # language_list: 4 字段规范化
        # EN: language_list: 4-field normalisation
        # JA: language_list：4 フィールドへの正規化
        r["language_list"] = _normalize_language_list(r.get("language_list") or [])
        # communication_list: {communicate_time, communicate_content}
        r["communication_list"] = _normalize_communication_list(r.get("communication_list") or [])

        # skills_list: 51job→[]；个人素质→base_info.pr；动作短语过滤
        # EN: skills_list: 51job → []; personal qualities → base_info.pr; action-phrase filtering
        # JA: skills_list：51job → []、個人の資質 → base_info.pr、動作の語句の除外
        r["skills_list"] = filter_skills_and_move_pr(
            r.get("skills_list") or [],
            base_info,  # 会就地修改 base_info["pr"]
            # EN: Modifies base_info["pr"] in place
            # JA: base_info["pr"] をその場で変更する
            platform,
        )

        # ========== base_info 二次补齐（从 plain 顶部信息行提取性别/年龄/婚姻/政治面貌/城市/户口） ==========
        # EN: ========== Second base_info completion (extract gender/age/marital status/political status/city/hukou from the information lines at the top of plain) ==========
        # JA: ========== base_info の 2 回目の補完（plain の冒頭の情報行から性別・年齢・婚姻状況・政治的身分・都市・戸籍を抽出）==========
        bi = r.get("base_info") or {}
        if isinstance(bi, dict):
            if not (bi.get("gender") or "").strip():
                m_g = re.search(r"(?:^|\n)[^\n]*?(男|女)\s*\d{1,2}\s*岁", plain)
                if m_g: bi["gender"] = m_g.group(1)
            if not (bi.get("age") or "").strip():
                m_a = re.search(r"(?:^|\n)[^\n]*?[男女]\s*(\d{1,2})\s*岁", plain)
                if m_a: bi["age"] = m_a.group(1)
            if not (bi.get("marital_status") or "").strip():
                m_m = re.search(r"(已婚|未婚|离异|丧偶)", plain)
                if m_m: bi["marital_status"] = m_m.group(1)
            if not (bi.get("political_status") or "").strip():
                m_p = re.search(r"(中共党员|党员|共青团员|团员|群众|民盟|民进|致公党|农工党|九三学社|无党派)", plain)
                if m_p: bi["political_status"] = m_p.group(1)
            if not (bi.get("city") or "").strip():
                m_c = re.search(r"现居住地\s*[:：]\s*([^\n|｜]+)", plain)
                if m_c: bi["city"] = m_c.group(1).strip(" |｜").strip() or ""
            if not (bi.get("household_registration") or "").strip():
                m_h = re.search(r"户口\s*[:：]\s*([^\n|｜]+)", plain)
                if m_h: bi["household_registration"] = m_h.group(1).strip(" |｜").strip() or ""
            if not (bi.get("phone") or "").strip():
                m_p = re.search(r"(?:^|\n)\s*(1[3-9]\d{9})\s*(?:\n|$)", plain)
                if m_p: bi["phone"] = m_p.group(1)
            if not (bi.get("email") or "").strip():
                m_e = re.search(r"([A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,})", plain)
                if m_e: bi["email"] = m_e.group(1)

        resumes_normalized.append(r)

    if not resumes_normalized:
        return False, "解析后无有效 resume 对象", None

    zh_resume = resumes_normalized[0]

    # ============ 顶层 5 大对象（严格参考 JSON：无 6 lists，只有 base/expected/current/education + resumes）============
    # EN: ============ Top-level 5 main objects (strictly following the reference JSON: no 6 lists, only base/expected/current/education + resumes) ============
    # JA: ============ トップレベルの 5 つの主要オブジェクト（参照 JSON に厳密に従う：6 つのリストはなく、base/expected/current/education + resumes だけ）============
    sd_base_info = copy.deepcopy(zh_resume["base_info"])
    sd_expected_info = copy.deepcopy(zh_resume["expected_info"])  # 已是数组
    # EN: Already an array
    # JA: すでに配列
    sd_current_info = _pick_latest_work(zh_resume.get("work_experiences") or [])
    sd_education_info = _pick_highest_education(zh_resume.get("education_list") or [])

    # 构建 structured_data（严格 5 大对象，按顺序）
    # EN: Build structured_data (strictly the 5 main objects, in order)
    # JA: structured_data を組み立てる（厳密に 5 つの主要オブジェクトを順に）
    structured_data = {
        "base_info": sd_base_info,
        "expected_info": sd_expected_info,
        "current_info": sd_current_info,
        "education_info": sd_education_info,
        "resumes": resumes_normalized,
    }

    # ============ 构建记录 ============
    # EN: ============ Build the record ============
    # JA: ============ レコードを組み立てる ============
    safe_name = (sd_base_info.get("full_name") or "未知姓名").strip()
    safe_name = re.sub(r'[\\/:*?"<>|]', "_", safe_name)
    json_name = f"{safe_name}_{rec_id[:8]}.json"
    json_path = json_dir / json_name

    if json_path.exists() and not force:
        return True, "已存在跳过（可--force覆盖）", str(json_path)

    json_dir.mkdir(parents=True, exist_ok=True)

    # 顶层 raw_text 构建（从结构化数据）
    # EN: Build the top-level raw_text (from the structured data)
    # JA: トップレベルの raw_text を組み立てる（構造化データから）
    top_raw_text = _build_top_level_raw_text(structured_data)
    # 兜底：如果结构化数据没抽到文字，就用 plain 前 20000 字
    # EN: Fallback: if no text was extracted into the structured data, use the first 20000 characters of plain
    # JA: 最終手段：構造化データでテキストが取れなかった場合は、plain の先頭 20000 文字を使う
    if not top_raw_text:
        top_raw_text = plain[:20000]

    source_block = {
        "path": str(html_path.resolve()),
        "original_path": str(html_path.resolve()),
        "filename": filename,
        "extension": ".html",
        "size": html_path.stat().st_size,
        "html_filename": filename,
        "note": "由 run_web_html_to_json.py 从 Web 来源 HTML（51job/智联招聘/猎聘网等）转换",
    }
    extraction_block = {
        "reader_group": "web_html_dom",
        "converter": "run_web_html_to_json.py",
        "parser": "codex_gemini_html_schema_parser",
        "status": "success",
        "html_path": str(html_path.resolve()),
        "parser_version": "CodexGeminiHtmlSchemaParser + web_postprocess_v1.0",
        "record_id": rec_id,
        "plain_text_length": len(plain),
        "dom": {
            "heading_count": len(re.findall(r"<h[1-6][^>]*>", str(read_html_text(html_path)), re.I)),
            "table_count": len(re.findall(r"<table[^>]*>", str(read_html_text(html_path)), re.I)),
            "row_count":   len(re.findall(r"<tr[^>]*>",    str(read_html_text(html_path)), re.I)),
            "paragraph_count": len(re.findall(r"<p[^>]*>",  str(read_html_text(html_path)), re.I)),
            "headings": [],
        },
        "classifier_result": "",
    }
    # 分类器跑一次（非简历继续保留，但标记）
    # EN: Run the classifier once (non-résumés are still kept, but flagged)
    # JA: 分類器を 1 回実行する（非履歴書も残すが、印を付ける）
    try:
        cls_res = classifier.classify(plain, filename)
        extraction_block["classifier_result"] = str(cls_res) if cls_res else ""
    except Exception:
        pass

    dates_block = {
        "resume_updated_date": updated_date,
        "resume_download_date": download_date,
        "resume_updated_date_source": updated_src,
        "resume_download_date_source": download_src,
        "sys_created_date": datetime.now(tz=TZ_JST).isoformat(timespec="seconds"),
        "sys_updated_date": datetime.now(tz=TZ_JST).isoformat(timespec="seconds"),
    }

    record = {
        "schema_version": "codex-resume-json-1.0",
        "record_id": rec_id,
        "source": source_block,
        "extraction": extraction_block,
        "dates": dates_block,
        # classification 放在 _force_top_level_schema 里统一插入
        # EN: classification is inserted uniformly in _force_top_level_schema
        # JA: classification は _force_top_level_schema で一括して挿入する
        "structured_data": structured_data,
        "raw_text": top_raw_text,
    }

    # ============== 最关键：强制顶层结构闸门 ==============
    # EN: ============== Most critical: the forced top-level structure gate ==============
    # JA: ============== 最も重要：トップレベル構造を強制するゲート ==============
    record = _force_top_level_schema(record)

    json_path.write_text(
        json.dumps(record, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return True, f"OK name={safe_name}", str(json_path)


# =============================================================================
# 主入口
# =============================================================================
# EN: =============================================================================
#     Main entry point
#     =============================================================================
# JA: =============================================================================
#     メインエントリ
#     =============================================================================

def main() -> int:
    args = parse_args()
    html_dir: Path = args.html_dir
    json_dir: Path = args.json_dir
    json_dir.mkdir(parents=True, exist_ok=True)

    all_htmls = sorted([
        p for p in html_dir.iterdir()
        if p.is_file() and p.suffix.lower() in (".html", ".htm", ".mht", ".mhtml", ".eml")
        and not p.name.startswith("_")
    ])
    total = len(all_htmls)
    if args.limit and args.limit > 0:
        if args.random_sample:
            import random as _rnd
            _rnd.seed(args.seed)
            sample_n = min(args.limit, total)
            all_htmls = _rnd.sample(all_htmls, sample_n)
            print(f"[随机抽样] seed={args.seed}, limit={args.limit}；目录共 {total} 个 HTML，本次随机抽 {len(all_htmls)} 个" f" / [random sampling] seed={args.seed}, limit={args.limit}; {total} HTML in the directory, {len(all_htmls)} drawn at random this time / [ランダムサンプリング] seed={args.seed}, limit={args.limit}、ディレクトリ内に HTML が {total} 個、今回ランダムに {len(all_htmls)} 個を抽出")
        else:
            all_htmls = all_htmls[: args.limit]
            print(f"[抽样模式] limit={args.limit}；目录共 {total} 个 HTML，本次抽样 {len(all_htmls)} 个" f" / [sampling mode] limit={args.limit}; {total} HTML in the directory, {len(all_htmls)} sampled this time / [サンプリングモード] limit={args.limit}、ディレクトリ内に HTML が {total} 個、今回 {len(all_htmls)} 個をサンプリング")
    else:
        print(f"[全量模式] 目录共 {total} 个 HTML" f" / [full mode] {total} HTML in the directory / [全件モード] ディレクトリ内に HTML が {total} 個")

    total_success = 0
    total_failed = 0
    total_skipped = 0
    items_report: list[dict[str, Any]] = []
    t0 = time.time()

    for i, hp in enumerate(all_htmls, 1):
        ok, msg, jpath = process_single_html(hp, json_dir, force=args.force)
        if ok and "跳过" in msg:
            total_skipped += 1
        elif ok:
            total_success += 1
        else:
            total_failed += 1
        items_report.append({
            "seq": i,
            "html": hp.name,
            "success": ok and "跳过" not in msg,
            "skipped": "跳过" in msg,
            "message": msg,
            "json_path": jpath or "",
        })
        if i % args.progress_interval == 0 or i == len(all_htmls):
            elapsed = time.time() - t0
            print(f"  [{i}/{len(all_htmls)}] {hp.name} → {msg}  (已用时 {elapsed:.1f}s)" f" / [{i}/{len(all_htmls)}] {hp.name} → {msg}  (elapsed {elapsed:.1f}s) / [{i}/{len(all_htmls)}] {hp.name} → {msg}  （経過 {elapsed:.1f} 秒）")

    elapsed = time.time() - t0
    report_data = {
        "generated_at": datetime.now(tz=TZ_JST).strftime("%Y-%m-%d %H:%M:%S"),
        "html_dir": str(html_dir),
        "json_dir": str(json_dir),
        "limit": args.limit,
        "force": args.force,
        "counts": {
            "found": len(all_htmls),
            "success": total_success,
            "failed": total_failed,
            "skipped": total_skipped,
        },
        "elapsed_seconds": round(elapsed, 2),
        "items": items_report,
    }
    report_path = json_dir / "_web_batch_report.json"
    report_path.write_text(
        json.dumps(report_data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print("\n=== web 目录 HTML→JSON 批处理完成 ===" " / \n=== web directory HTML→JSON batch finished === / \n=== web ディレクトリの HTML→JSON 一括処理が完了しました ===")
    print(f"总计 发现:{len(all_htmls)} 成功:{total_success} 失败:{total_failed} 跳过:{total_skipped}" f" / Total found:{len(all_htmls)} success:{total_success} failed:{total_failed} skipped:{total_skipped} / 合計 検出:{len(all_htmls)} 成功:{total_success} 失敗:{total_failed} スキップ:{total_skipped}")
    print(f"总耗时: {elapsed:.2f} 秒；报告: {report_path}" f" / Total time: {elapsed:.2f} s; report: {report_path} / 所要時間：{elapsed:.2f} 秒、レポート：{report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
