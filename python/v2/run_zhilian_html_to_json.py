"""智联招聘简历 HTML -> JSON 专用转换脚本。

复用 CodexGeminiHtmlSchemaParser + DocumentClassifier，
处理智联招聘两种 HTML 格式：
  1. App 导出格式（单行 HTML，<p>+<table> 结构，文件名: 智联简历_姓名_...）
  2. Word 转换格式（多表格结构，文件名: 智联招聘_姓名_中文_日期_ID...）

输出 JSON 严格遵循 CONTEXT.md 规范：
  - resumes[0] 固定中文主版本
  - 顶层 base_info/current_info/education_info 从 resumes[0] 重构
  - 顶层不再保留列表字段（certificate_list 等只在 resumes 内）
  - 内部对象不保留 raw_text，仅最外层 record.raw_text
  - 日期标准化、学历 rank 归一化、平台标识为 "智联招聘"

EN: Dedicated conversion script for Zhaopin résumé HTML -> JSON.

Reuses CodexGeminiHtmlSchemaParser + DocumentClassifier,
handling Zhaopin's two HTML formats:
  1. App export format (single-line HTML, <p>+<table> structure, file name: 智联简历_name_...)
  2. Word conversion format (multi-table structure, file name: 智联招聘_name_中文_date_ID...)

The output JSON strictly follows the CONTEXT.md spec:
  - resumes[0] is always the Chinese primary version
  - the top-level base_info/current_info/education_info are rebuilt from resumes[0]
  - no list fields are kept at the top level (certificate_list etc. only inside resumes)
  - inner objects keep no raw_text; only the outermost record.raw_text
  - dates standardised, degree rank normalised, platform label "智联招聘" (Zhaopin)

JA: Zhaopin の履歴書 HTML -> JSON 専用の変換スクリプト。

CodexGeminiHtmlSchemaParser + DocumentClassifier を再利用し、
Zhaopin の 2 種類の HTML の形式を処理する：
  1. アプリのエクスポート形式（1 行の HTML、<p>+<table> の構造、ファイル名：智联简历_氏名_...）
  2. Word 変換の形式（複数の表の構造、ファイル名：智联招聘_氏名_中文_日付_ID...）

出力する JSON は CONTEXT.md の仕様に厳密に従う：
  - resumes[0] は常に中国語主版
  - トップレベルの base_info/current_info/education_info は resumes[0] から再構築する
  - トップレベルにはリストのフィールドを残さない（certificate_list などは resumes 内だけ）
  - 内部のオブジェクトには raw_text を残さず、最も外側の record.raw_text だけ
  - 日付の標準化、学歴ランクの正規化、プラットフォームの表示は「智联招聘」（Zhaopin）
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
# 参数与基础 IO
# =============================================================================
# EN: =============================================================================
#     Arguments and basic IO
#     =============================================================================
# JA: =============================================================================
#     引数と基本の IO
#     =============================================================================

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="智联招聘 HTML -> JSON 转换" " / Zhaopin HTML -> JSON conversion / 智聯招聘の HTML -> JSON 変換")
    p.add_argument(
        "--html-dir",
        type=Path,
        default=PROJECT_ROOT / _rc.dirname("complete-transfered-htmls") / "docs" / "智联招聘",
    )
    p.add_argument(
        "--json-dir",
        type=Path,
        default=PROJECT_ROOT / _rc.dirname("complete-transfered-jsons") / "docs" / "智联招聘",
    )
    p.add_argument("--limit", type=int, default=0, help="0=全部" " / 0 = all / 0 は全件")
    p.add_argument("--force", action="store_true", help="覆盖已存在 JSON" " / Overwrite existing JSON / 既存の JSON を上書きする")
    p.add_argument("--progress-interval", type=int, default=20)
    return p.parse_args()


def read_html_text(html_path: Path) -> str:
    """自动检测并用最佳编码读取 HTML 文本

    EN: Automatically detect and read HTML text with the best encoding

    JA: 最適なエンコーディングを自動検出して HTML のテキストを読む
    """
    raw_bytes = html_path.read_bytes()
    for enc in ("utf-8", "gb18030", "gbk"):
        try:
            t = raw_bytes.decode(enc)
            if "智联" in t or "简历" in t or "姓名" in t:
                return t
        except Exception:
            continue
    return raw_bytes.decode("utf-8", errors="replace")


def plain_text(html_text: str) -> str:
    """提取纯文本并清理控制字符与多余空格

    EN: Extract plain text and clean control characters and extra spaces

    JA: プレーンテキストを抽出し、制御文字と余分な空白を除く
    """
    if not html_text:
        return ""
    if BeautifulSoup is None:
        raw = re.sub(r"<[^>]+>", "\n", html_text)
    else:
        soup = BeautifulSoup(html_text, "html.parser")
        for tag in soup(["script", "style", "xml", "meta", "link"]):
            tag.decompose()
        for p in soup.find_all(["p", "div", "h1", "h2", "h3", "h4", "li", "tr", "br"]):
            p.append("\n")
        raw = soup.get_text("\n")

    raw = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", raw)
    raw = raw.translate(str.maketrans("０１２３４５６７８９", "0123456789"))
    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    return "\n".join(lines)


def _preprocess_glued_text(text: str) -> str:
    """预处理粘连文本：在板块标题和字段标签前插入换行。

    智联招聘部分 HTML 文件中，多个字段粘连在单个 <p> 标签内，字段间只有
    空格没有换行（如「期望工作地区：...期望月薪：...自我评价」）。现有解析器
    依赖「按行切分」与「行首板块标题匹配」，在这种粘连格式下全部失效。

    本函数在已知的板块标题、字段标签、语言名前插入换行，将粘连文本重新分割
    成独立行，使现有解析器能正确工作。对正常格式（标签已在行首）无影响：
    行首标签前是 \\n，lookbehind 不触发，不插入换行。

    规则：
      1. 板块标题（后跟空白或行尾）前插入换行
      2. 字段标签（后跟冒号）前插入换行
      3. 语言名（后跟冒号）前插入换行

    EN: Pre-process stuck text: insert line breaks before section headings and field labels.

    In some Zhaopin HTML files, several fields are stuck together inside a single <p> tag, with only
    spaces and no line breaks between them (e.g. "期望工作地区：...期望月薪：...自我评价"). The existing parsers
    rely on "splitting by line" and "matching section headings at the start of a line", and all fail on this stuck format.

    This function inserts line breaks before known section headings, field labels and language names, re-splitting the stuck text
    into separate lines so the existing parsers work correctly. It has no effect on normal formats (labels already at the start of a line):
    a label at the start of a line is preceded by \\n, so the lookbehind does not fire and no line break is inserted.

    Rules:
      1. insert a line break before section headings (followed by whitespace or end of line)
      2. insert a line break before field labels (followed by a colon)
      3. insert a line break before language names (followed by a colon)

    JA: くっついたテキストを前処理する：セクション見出しとフィールドのラベルの前に改行を入れる。

    Zhaopin の一部の HTML ファイルでは、複数のフィールドが 1 つの <p> タグ内にくっつき、間に
    空白しかなく改行がない（例：「期望工作地区：...期望月薪：...自我评价」）。既存のパーサーは
    「行単位の分割」と「行頭のセクション見出しのマッチ」に頼っているため、このくっついた形式ではすべて失敗する。

    この関数は既知のセクション見出し・フィールドのラベル・言語名の前に改行を入れ、くっついたテキストを
    独立した行に分け直して、既存のパーサーが正しく動くようにする。通常の形式（ラベルがすでに行頭にある）には影響しない：
    行頭のラベルの前は \\n なので lookbehind が発動せず、改行は入らない。

    ルール：
      1. セクション見出し（後ろが空白か行末）の前に改行を入れる
      2. フィールドのラベル（後ろにコロン）の前に改行を入れる
      3. 言語名（後ろにコロン）の前に改行を入れる
    """
    if not text:
        return text

    # 板块标题（按长度降序，避免短词匹配到长词内部；re.sub 一次性扫描，
    # 长词先消费，短词不会再匹配已被消费的子串）
    # EN: Section headings (sorted by length descending, so short words do not match inside long ones; re.sub scans once,
    #     long words are consumed first, and short words will not match substrings already consumed)
    # JA: セクション見出し（長さの降順に並べ、短い語が長い語の内部にマッチしないようにする。re.sub は 1 回でスキャンし、
    #     長い語が先に消費されるので、短い語はすでに消費された部分文字列にはマッチしない）
    section_headers = [
        "在校学习情况", "在校实践经历", "特长职业目标", "所获证书",
        "工作经历", "教育经历", "项目经历", "语言能力", "专业技能",
        "自我评价", "求职意向", "培训经历", "活动描述", "兴趣爱好",
        "特长",
    ]
    # 字段标签（字段名后跟冒号）
    # EN: Field labels (field name followed by a colon)
    # JA: フィールドのラベル（フィールド名の後にコロンが続く）
    field_labels = [
        "期望工作地区", "期望工作性质", "期望从事职业", "期望从事行业",
        "期望月薪", "目前状况",
        "简历更新时间", "简历下载时间", "简历名称",
        "工作描述", "证书说明", "企业性质", "规模", "分数",
        # 培训经历字段标签（粘连格式中这些标签会挤在同一行）
        # EN: Training-history field labels (in the stuck format these labels are squeezed onto the same line)
        # JA: 研修歴のフィールドのラベル（くっついた形式ではこれらのラベルが同じ行に詰め込まれる）
        "培训机构", "培训地点", "所获证书", "培训描述",
    ]
    # 语言名（后跟冒号）
    # EN: Language names (followed by a colon)
    # JA: 言語名（後ろにコロンが続く）
    lang_names = ["西班牙语", "意大利语", "葡萄牙语", "阿拉伯语",
                  "英语", "日语", "德语", "法语", "韩语", "俄语", "普通话", "粤语"]

    result = text

    # 1. 板块标题前插入换行（标题前有非换行字符，标题后是空白或行尾）
    # EN: 1. Insert a line break before section headings (a non-newline character before the heading, whitespace or end of line after it)
    # JA: 1. セクション見出しの前に改行を入れる（見出しの前に改行以外の文字があり、見出しの後が空白か行末）
    headers_sorted = sorted(section_headers, key=len, reverse=True)
    header_pattern = "|".join(re.escape(h) for h in headers_sorted)
    result = re.sub(
        rf"(?<=[^\n])[ \t]*({header_pattern})(?=\s|$)",
        r"\n\1",
        result,
    )

    # 2. 字段标签前插入换行（标签前有非换行字符，标签后跟冒号）
    # EN: 2. Insert a line break before field labels (a non-newline character before the label, a colon after it)
    # JA: 2. フィールドのラベルの前に改行を入れる（ラベルの前に改行以外の文字があり、ラベルの後にコロンが続く）
    labels_sorted = sorted(field_labels, key=len, reverse=True)
    label_pattern = "|".join(re.escape(l) for l in labels_sorted)
    result = re.sub(
        rf"(?<=[^\n])[ \t]*({label_pattern})([：:])",
        r"\n\1\2",
        result,
    )

    # 3. 语言名前插入换行（语言名前有非换行字符，后跟冒号）
    # EN: 3. Insert a line break before language names (a non-newline character before, a colon after)
    # JA: 3. 言語名の前に改行を入れる（前に改行以外の文字があり、後ろにコロンが続く）
    langs_sorted = sorted(lang_names, key=len, reverse=True)
    lang_pattern = "|".join(re.escape(l) for l in langs_sorted)
    result = re.sub(
        rf"(?<=[^\n])[ \t]*({lang_pattern})([：:])",
        r"\n\1\2",
        result,
    )

    # 4. 「证书」板块标题粘连处理：句号后的「证书」在行尾时拆分为独立行
    #    安全：证书名如「日语一级证书」中「证书」前是「级」而非句号
    # EN: 4. Handle a stuck "证书" (certificates) section heading: when "证书" after a full stop is at the end of a line, split it into its own line
    #        Safe: in certificate names like "日语一级证书" (Japanese level 1 certificate), "证书" is preceded by "级", not a full stop
    # JA: 4. くっついた「证书」（資格）のセクション見出しの処理：句点の後の「证书」が行末にある場合は独立した行に分ける
    #        安全性：「日语一级证书」（日本語 1 級資格）のような資格名では「证书」の前は句点ではなく「级」
    result = re.sub(r"([。．\.]\s*)证书(?=\n|$)", r"\1\n证书", result)

    return result


def html_record_id(html_path: Path) -> str:
    stat = html_path.stat()
    value = f"{html_path.resolve()}|{stat.st_size}|{stat.st_mtime_ns}"
    return hashlib.sha256(value.encode("utf-8", "surrogatepass")).hexdigest()


def date_from_mtime(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime, tz=TZ_JST).strftime(
        "%Y-%m-%d %H:%M:%S"
    )


# =============================================================================
# 学历与日期归一化（与 liepin 脚本保持一致）
# =============================================================================
# EN: =============================================================================
#     Degree and date normalisation (kept consistent with the liepin script)
#     =============================================================================
# JA: =============================================================================
#     学歴と日付の正規化（liepin のスクリプトと一致させる）
#     =============================================================================

def normalize_degree_rank(deg: str) -> tuple[str, str]:
    """归一化学历名称到 rank + education_type。

    EN: Normalise degree names to rank + education_type.

    JA: 学歴名を rank + education_type に正規化する。
    """
    degree_rank = {
        "博士后": "7", "博士": "6", "phd": "6", "doctor": "6",
        "硕士": "5", "修士": "5", "研究生": "5", "mba": "5", "emba": "5", "master": "5", "ma": "5", "ms": "5",
        "大学院": "5",
        "本科": "4", "学士": "4", "大卒": "4", "bachelor": "4", "bs": "4", "ba": "4",
        "大专": "3", "专科": "3", "短大": "3", "大専": "3", "associate": "3", "diploma": "3",
        "高中": "2", "中专": "2", "职高": "2", "中学": "2", "high school": "2",
        "中級専門学校": "2", "専門学校": "2",
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


def normalize_education_list(edu_list: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """对教育经历列表进行后处理：重新校准 rank + school_education_type。

    EN: Post-process the education list: recalibrate rank + school_education_type.

    JA: 学歴の一覧を後処理する：rank と school_education_type を補正し直す。
    """
    for edu in edu_list:
        deg = edu.get("school_degree_type", "")
        rank, etype = normalize_degree_rank(deg)
        if rank:
            edu["school_degree_rank"] = rank
            if not edu.get("school_education_type") or edu.get("school_education_type") in ("全日制", "全日制大学", "全日制研究生"):
                edu["school_education_type"] = etype
    return edu_list


def _format_ym(s: str) -> str:
    """将 2015.09 或 2015年09月 统一为 2015年09月01日

    EN: Unify 2015.09 or 2015年09月 into 2015年09月01日

    JA: 2015.09 や 2015年09月 を 2015年09月01日 に統一する
    """
    if not s:
        return ""
    m = re.search(r"((?:19|20)\d{2})[./年\-]?(\d{1,2})?", s)
    if m:
        y = m.group(1)
        m_str = m.group(2) or "01"
        return f"{y}年{int(m_str):02d}月01日"
    return ""


def standardize_datetime(raw: str) -> str:
    """将各种乱序/年月格式日期统一洗净标准化为 YYYY-MM-DD HH:MM:SS 规范格式。

    支持格式：
      - 2022年10月31日11:36:28（日与时间无空格）
      - 2013年10月08日 11:52:08（日与时间有空格）
      - 2013.09.29（仅日期）
      - 2013-09-29 11:52:08（标准格式）

    EN: Clean and normalise dates in all kinds of jumbled/year-month formats into the standard YYYY-MM-DD HH:MM:SS format.

    Supported formats:
      - 2022年10月31日11:36:28 (no space between day and time)
      - 2013年10月08日 11:52:08 (space between day and time)
      - 2013.09.29 (date only)
      - 2013-09-29 11:52:08 (standard format)

    JA: さまざまな順序・年月形式の日付を、標準の YYYY-MM-DD HH:MM:SS 形式に統一して正規化する。

    対応する形式：
      - 2022年10月31日11:36:28（日と時刻の間に空白なし）
      - 2013年10月08日 11:52:08（日と時刻の間に空白あり）
      - 2013.09.29（日付のみ）
      - 2013-09-29 11:52:08（標準の形式）
    """
    raw = raw.replace("年", "-").replace("月", "-").replace("日", " ").replace(".", "-").replace("/", "-")
    raw = re.sub(r"\s+", " ", raw).strip()
    parts = raw.split(" ")
    date_part = parts[0]
    time_part = parts[1] if len(parts) > 1 else "00:00:00"

    d_parts = date_part.split("-")
    if len(d_parts) >= 3:
        y, m, d = d_parts[0], d_parts[1], d_parts[2]
        try:
            date_str = f"{int(y):04d}-{int(m):02d}-{int(d):02d}"
        except ValueError:
            date_str = date_part
    else:
        date_str = date_part

    t_parts = time_part.split(":")
    try:
        if len(t_parts) == 2:
            time_str = f"{int(t_parts[0]):02d}:{int(t_parts[1]):02d}:00"
        elif len(t_parts) == 3:
            time_str = f"{int(t_parts[0]):02d}:{int(t_parts[1]):02d}:{int(t_parts[2]):02d}"
        else:
            time_str = "00:00:00"
    except ValueError:
        time_str = "00:00:00"

    return f"{date_str} {time_str}"


def parse_resume_dates(text: str, fallback_date: str) -> tuple[str, str, str, str]:
    """通用精准提取 resume_updated_date 与 resume_download_date 及其权威来源说明。

    支持多种日期标签写法：
      - 更新时间/更新日期/更新于
      - 下载时间/下载日期/下载于/投递时间
    支持多种日期值格式：
      - 2022年10月31日11:36:28（App 格式，日与时间无空格）
      - 2013年10月08日 11:52:08（Word 格式，日与时间有空格）
      - 2013.09.29（仅日期）

    EN: General precise extraction of resume_updated_date and resume_download_date and the description of their authoritative source.

    Supports many ways of writing the date label:
      - 更新时间/更新日期/更新于 (updated time/date/on)
      - 下载时间/下载日期/下载于/投递时间 (downloaded time/date/on, application time)
    Supports many date value formats:
      - 2022年10月31日11:36:28 (App format, no space between day and time)
      - 2013年10月08日 11:52:08 (Word format, space between day and time)
      - 2013.09.29 (date only)

    JA: resume_updated_date と resume_download_date、およびその根拠となる取得元の説明を汎用的に正確に抽出する。

    日付のラベルの多様な書き方に対応する：
      - 更新时间／更新日期／更新于（更新日時・更新日・〜に更新）
      - 下载时间／下载日期／下载于／投递时间（ダウンロード日時・ダウンロード日・〜にダウンロード・応募日時）
    日付の値の多様な形式に対応する：
      - 2022年10月31日11:36:28（アプリの形式、日と時刻の間に空白なし）
      - 2013年10月08日 11:52:08（Word の形式、日と時刻の間に空白あり）
      - 2013.09.29（日付のみ）
    """
    # 日期值正则：支持 年月日 / . / - 分隔，日期与时间之间可有可无空格
    # EN: Date value regex: supports 年月日 / . / - separators, with or without a space between date and time
    # JA: 日付の値の正規表現：年月日・.・- の区切りに対応し、日付と時刻の間の空白はあってもなくてもよい
    date_val = r"(?:19|20)\d{2}[年./\-]\d{1,2}(?:[月./\-]\d{1,2}日?)?(?:[ T]?\d{1,2}:\d{1,2}(?::\d{1,2})?)?"

    m_up = re.search(rf"(?:简历)?更新(?:于|[日时]?[期间]?)[：:\s]*({date_val})", text, re.I)
    if m_up:
        raw_up = m_up.group(1).strip()
        updated_date = standardize_datetime(raw_up)
        updated_source = "文档正文更新时间"
    else:
        updated_date = fallback_date
        updated_source = "HTML文件修改时间（历史资料替代）"

    m_dl = re.search(rf"(?:简历)?(?:下载|投递)(?:于|[日时]?[期间]?)[：:\s]*({date_val})", text, re.I)
    if m_dl:
        raw_dl = m_dl.group(1).strip()
        download_date = standardize_datetime(raw_dl)
        download_source = "文档正文下载/投递时间"
    else:
        download_date = fallback_date
        download_source = "HTML文件修改时间（历史资料替代）"

    return updated_date, download_date, updated_source, download_source


# =============================================================================
# 智联招聘专属解析
# =============================================================================
# EN: =============================================================================
#     Zhaopin-specific parsing
#     =============================================================================
# JA: =============================================================================
#     Zhaopin 専用の解析
#     =============================================================================

ZHILIAN_PLATFORM = "智联招聘"

# 日期范围正则：支持 - – — ~ ～ 至 到 等多种连接符
# EN: Date-range regex: supports many connectors such as - – — ~ ～ 至 到
# JA: 期間の正規表現：- – — ~ ～ 至 到 など多くの接続記号に対応する
DATE_RANGE_RE = re.compile(
    r"((?:19|20)\d{2}[./年\-]\d{1,2})\s*[\-\u2010-\u2015~～至到‒―〜]{1,4}\s*((?:19|20)\d{2}[./年\-]\d{1,2}|至今|现在|目前|Present)",
    re.I,
)
# 单日期点
# EN: A single date point
# JA: 単一の日付
SINGLE_DATE_RE = re.compile(r"((?:19|20)\d{2})[./年\-](\d{1,2})")


def _is_app_format(text: str) -> bool:
    """检测是否为 App 导出格式（含「扫码联系TA」「智联招聘App」等标志）。

    EN: Detect whether it is the App export format (with markers like "扫码联系TA" (scan to contact), "智联招聘App" (Zhaopin App)).

    JA: アプリのエクスポート形式か（「扫码联系TA」（スキャンして連絡）「智联招聘App」（Zhaopin アプリ）などの目印がある）を検出する。
    """
    return bool(re.search(r"扫码联系TA|智联招聘App|点击此处联系候选人", text))


def _extract_zhilian_name(text: str, filename: str) -> str:
    """从正文或文件名提取候选人姓名。

    优先级：
      1. App 格式：「查看详情」与「点击此处联系候选人」之间的独立中文名行
      2. Word 格式：ID 行与手机/Mobile 行之间的姓名行（支持中英文）
      3. Word 格式：简历名称后若为纯中文姓名
      4. 正文前 40 行首个独立姓名行（排除平台名等）
      5. 文件名兜底

    EN: Extract the candidate name from the body or the file name.

    Priority:
      1. App format: a standalone Chinese name line between "查看详情" (view details) and "点击此处联系候选人" (click here to contact the candidate)
      2. Word format: the name line between the ID line and the phone/Mobile line (Chinese and English supported)
      3. Word format: a pure Chinese name after the résumé title
      4. The first standalone name line in the first 40 lines of the body (excluding platform names etc.)
      5. File-name fallback

    JA: 本文またはファイル名から候補者名を抽出する。

    優先順位：
      1. アプリの形式：「查看详情」（詳細を見る）と「点击此处联系候选人」（候補者に連絡する）の間にある独立した中国語名の行
      2. Word の形式：ID の行と電話／Mobile の行の間にある氏名の行（中国語・英語に対応）
      3. Word の形式：履歴書名の後にある漢字だけの氏名
      4. 本文の最初の 40 行のうち最初の独立した氏名の行（プラットフォーム名などは除く）
      5. ファイル名による最終手段
    """
    _EXCLUDE_NAMES = {"智联招聘", "前程无忧", "猎聘", "简历", "ID", "求职意向",
                      "自我评价", "工作经历", "教育经历", "项目经历", "语言能力",
                      "专业技能", "培训经历", "所获证书", "所获", "证书", "基本信息",
                      "未知", "无关联职", "职位", "扫码联系TA"}
    _ZH_NAME_RE = r"[\u4e00-\u9fff]{2,5}"
    _EN_NAME_RE = r"[A-Za-z][A-Za-z\s\.\-]{1,29}"

    def _valid_name(s: str) -> bool:
        s = s.strip()
        if not s or s in _EXCLUDE_NAMES:
            return False
        return bool(re.fullmatch(_ZH_NAME_RE, s) or re.fullmatch(_EN_NAME_RE, s))

    lines = text.splitlines()

    # 1. App 格式：姓名位于「查看详情」与「点击此处联系候选人」之间的独立行
    # EN: 1. App format: the name is on its own line between "查看详情" (view details) and "点击此处联系候选人" (click here to contact the candidate)
    # JA: 1. アプリの形式：氏名は「查看详情」（詳細を見る）と「点击此处联系候选人」（候補者に連絡する）の間の独立した行にある
    m = re.search(r"查看详情\s*\n\s*([\u4e00-\u9fff]{2,5})\s*\n\s*点击此处联系候选人", text)
    if m:
        return m.group(1)

    # 1.5 App 格式兜底：姓名在「扫码联系TA」与「应聘职位」之间，可能粘连杂质词
    # EN: 1.5 App format fallback: the name is between "扫码联系TA" (scan to contact) and "应聘职位" (position applied for), possibly with noise words stuck to it
    # JA: 1.5 アプリの形式の最終手段：氏名は「扫码联系TA」（スキャンして連絡）と「应聘职位」（応募職位）の間にあり、不要な語がくっついていることがある
    m = re.search(r"(?:扫码联系TA|点击此处联系候选人)\n?(.+?)\n?应聘职位", text, re.S)
    if m:
        cand = m.group(1).strip()
        cand = re.sub(r"位图@2x|icon@2x|点击此处联系候选人|扫码联系TA|用「智联招聘App」扫码|或点击此处登录查看详情|点击此处登录|查看详情|或", "", cand)
        cand = cand.strip()
        if cand and re.fullmatch(_ZH_NAME_RE, cand):
            return cand
        m_zh = re.search(r"([\u4e00-\u9fff]{2,5})", cand)
        if m_zh:
            return m_zh.group(1)

    # 1.6 从文件名提取姓名（最可靠的来源）
    #    文件名格式：智联招聘_{name}_中文_{date}_{id}__{hash}.html
    #    或 智联简历_{name}_...（App 格式）
    # EN: 1.6 Extract the name from the file name (the most reliable source)
    #        File name format: 智联招聘_{name}_中文_{date}_{id}__{hash}.html
    #        or 智联简历_{name}_... (App format)
    # JA: 1.6 ファイル名から氏名を抽出する（最も信頼できるソース）
    #        ファイル名の形式：智联招聘_{name}_中文_{date}_{id}__{hash}.html
    #        または 智联简历_{name}_...（アプリの形式）
    m_file = re.match(r"智联(?:简历|招聘)_(.+?)_(?:\d+岁|中文|英文)", filename)
    if m_file:
        fname = m_file.group(1).strip()
        # 去除「的简历」后缀（如「段健的简历」→「段健」）
        # EN: Remove the "的简历" ('s résumé) suffix (e.g. "<name>的简历" → "<name>")
        # JA: 「的简历」（〜の履歴書）の接尾辞を除く（例：「<氏名>的简历」→「<氏名>」）
        fname = re.sub(r"的简历$", "", fname).strip()
        if fname and _valid_name(fname) and fname not in _EXCLUDE_NAMES:
            return fname

    # 2. Word 格式：简历名称后若为纯中文姓名（优先使用中文名）
    #    注意：简历名称可能是职位名（如「电气工程师」）或含「的简历」后缀，
    #    需过滤后才作为兜底
    # EN: 2. Word format: if the résumé title is followed by a pure Chinese name (prefer the Chinese name)
    #        Note: the résumé title may be a position name (e.g. "电气工程师" (electrical engineer)) or carry the "的简历" suffix,
    #        so it must be filtered before being used as a fallback
    # JA: 2. Word の形式：履歴書名の後が漢字だけの氏名の場合（中国語名を優先）
    #        注意：履歴書名は職位名（例：「电气工程师」（電気エンジニア））の場合や「的简历」の接尾辞が付く場合があるため、
    #        フィルターしてから最終手段として使う
    m = re.search(r"简历名称[：:]\s*\n([^\n]+)", text)
    if m:
        cand = m.group(1).strip()
        cand = re.sub(r"^[ \t]+", "", cand)
        # 去除「的简历」后缀
        # EN: Remove the "的简历" suffix
        # JA: 「的简历」の接尾辞を除く
        cand = re.sub(r"的简历$", "", cand).strip()
        # 排除职位名称（如「电气工程师」「销售经理」等）
        # EN: Exclude position names (e.g. "电气工程师" (electrical engineer), "销售经理" (sales manager))
        # JA: 職位名を除外する（例：「电气工程师」（電気エンジニア）、「销售经理」（営業マネージャー））
        _JOB_TITLE_SUFFIXES = ("工程师", "经理", "主管", "总监", "专员", "助理", "代表",
                               "老师", "教师", "医生", "护士", "设计师", "分析师",
                               "顾问", "主任", "科长", "班长", "组长", "实习生", "操作员",
                               "编辑", "翻译", "会计", "出纳", "审计", "策划", "文员",
                               "前台", "客服", "司机", "厨师", "电工", "焊工", "木工",
                               "采购", "销售", "运营", "产品", "测试", "运维")
        if (cand and re.fullmatch(_ZH_NAME_RE, cand) and cand not in _EXCLUDE_NAMES
                and not any(cand.endswith(suf) for suf in _JOB_TITLE_SUFFIXES)):
            return cand

    # 3. Word 格式：ID 行与手机/Mobile 行之间的姓名行（支持中英文）
    # EN: 3. Word format: the name line between the ID line and the phone/Mobile line (Chinese and English supported)
    # JA: 3. Word の形式：ID の行と電話／Mobile の行の間にある氏名の行（中国語・英語に対応）
    for i, line in enumerate(lines):
        if re.search(r"(?:手机|Mobile|Tel)[：:]", line, re.I) and i > 0:
            prev = lines[i - 1].strip()
            if _valid_name(prev):
                return prev

    # 3.5 粘连格式：姓名与「手机：」粘连在同一行（如「张三手机：13800000012」）
    # EN: 3.5 Stuck format: the name is stuck to "手机：" (mobile:) on the same line (e.g. "张三手机：13800000012")
    # JA: 3.5 くっついた形式：氏名が「手机：」（携帯：）と同じ行にくっついている（例：「张三手机：13800000012」）
    for line in lines:
        m = re.search(r"^([\u4e00-\u9fff]{2,5})\s*手机[：:]", line)
        if m:
            cand = m.group(1)
            if cand not in _EXCLUDE_NAMES:
                return cand

    # 4. 从正文前 40 行提取首个独立姓名行（遇到板块标题即停止，避免误取自我评价等）
    # EN: 4. Extract the first standalone name line from the first 40 lines of the body (stop at a section heading to avoid picking up self-assessment, etc.)
    # JA: 4. 本文の最初の 40 行から最初の独立した氏名の行を抽出する（セクション見出しに達したら止め、自己評価などを誤って取らないようにする）
    _SECTION_HEADERS = {"自我评价", "工作经历", "教育经历", "项目经历", "语言能力",
                        "专业技能", "培训经历", "所获证书", "证书", "求职意向",
                        "在校学习情况", "在校实践经历", "活动描述", "特长职业目标",
                        "特长", "Self-Assessment", "Self-Evaluation", "Work Experience",
                        "Education", "Project", "Language", "Skills", "Training",
                        "Certificates", "Awards"}
    for line in lines[:40]:
        line = line.strip()
        if line in _SECTION_HEADERS:
            break
        if _valid_name(line):
            return line

    # 5. 兜底：从文件名提取
    # EN: 5. Fallback: extract from the file name
    # JA: 5. 最終手段：ファイル名から抽出する
    m = re.match(r"智联(?:简历|招聘)_(.+?)_(?:\d+岁|中文|英文)", filename)
    if m:
        name = m.group(1).strip()
        if name and name not in _EXCLUDE_NAMES:
            return name

    return ""


def _parse_base_info_line(text: str) -> dict[str, str]:
    """解析基本信息行。

    App 格式：男｜24岁(1997年1月)｜3年工作经验｜本科｜离职-正在找工作
    Word 格式（有工作年限）：女    31岁(1982年6月)    9年工作经验    大专    已婚
    Word 格式（无工作年限）：男    35岁(1978年11月)    本科    未婚

    EN: Parse the basic info line.

    App format: 男｜24岁(1997年1月)｜3年工作经验｜本科｜离职-正在找工作 (male | 24 years old (Jan 1997) | 3 years of experience | bachelor | left - looking for work)
    Word format (with years of work): 女    31岁(1982年6月)    9年工作经验    大专    已婚 (female, 31, 9 years of experience, junior college, married)
    Word format (without years of work): 男    35岁(1978年11月)    本科    未婚 (male, 35, bachelor, single)

    JA: 基本情報の行を解析する。

    アプリの形式：男｜24岁(1997年1月)｜3年工作经验｜本科｜离职-正在找工作（男性｜24 歳（1997 年 1 月）｜経験 3 年｜学士｜退職済み・求職中）
    Word の形式（勤続年数あり）：女    31岁(1982年6月)    9年工作经验    大专    已婚（女性・31 歳・経験 9 年・短大・既婚）
    Word の形式（勤続年数なし）：男    35岁(1978年11月)    本科    未婚（男性・35 歳・学士・未婚）
    """
    info: dict[str, str] = {}
    degree_pat = r"(博士后|博士|硕士|本科|大专|专科|高中|中专|职高|初中|小学)"

    # 匹配 App 格式基本信息行（含工作年限，｜分隔）
    # 支持「3年工作经验」「工作11年」两种工作年限写法
    # EN: Match the App-format basic info line (with years of work, ｜-separated)
    #     Supports both ways of writing years of work, "3年工作经验" (3 years of experience) and "工作11年" (worked 11 years)
    # JA: アプリの形式の基本情報の行にマッチする（勤続年数を含み、｜区切り）
    #     勤続年数の書き方「3年工作经验」（経験 3 年）と「工作11年」（勤続 11 年）の両方に対応する
    m = re.search(
        rf"(男|女)[｜|\s]+(\d+)岁\((\d{{4}})年(\d{{1,2}})月\)[｜|\s]+(?:工作)?(\d+)年(?:工作经验|经验)?[｜|\s]+{degree_pat}[｜|\s]*(.*)",
        text,
    )
    if m:
        info["gender"] = m.group(1)
        info["age"] = m.group(2)
        info["birth_year"] = m.group(3)
        info["birth_date"] = f"{m.group(3)}年{int(m.group(4)):02d}月01日"
        info["work_years"] = m.group(5)
        info["degree"] = m.group(6)
        status_raw = m.group(7).strip()
        if "在职" in status_raw:
            info["status"] = "在职"
        elif "离职" in status_raw:
            info["status"] = "离职"
        return info

    # Word 格式（有工作年限，多空格分隔）
    # EN: Word format (with years of work, separated by multiple spaces)
    # JA: Word の形式（勤続年数あり、複数の空白で区切る）
    m = re.search(
        rf"(男|女)\s+(\d+)岁\((\d{{4}})年(\d{{1,2}})月\)\s+(?:工作)?(\d+)年工作经验\s+{degree_pat}\s*([已婚未婚离异]*)",
        text,
    )
    if m:
        info["gender"] = m.group(1)
        info["age"] = m.group(2)
        info["birth_year"] = m.group(3)
        info["birth_date"] = f"{m.group(3)}年{int(m.group(4)):02d}月01日"
        info["work_years"] = m.group(5)
        info["degree"] = m.group(6)
        if m.group(7):
            info["marital_status"] = m.group(7)
        return info

    # Word 格式（无工作年限，多空格分隔）
    # EN: Word format (without years of work, separated by multiple spaces)
    # JA: Word の形式（勤続年数なし、複数の空白で区切る）
    m = re.search(
        rf"(男|女)\s+(\d+)岁\((\d{{4}})年(\d{{1,2}})月\)\s+{degree_pat}\s*([已婚未婚离异]*)",
        text,
    )
    if m:
        info["gender"] = m.group(1)
        info["age"] = m.group(2)
        info["birth_year"] = m.group(3)
        info["birth_date"] = f"{m.group(3)}年{int(m.group(4)):02d}月01日"
        info["degree"] = m.group(5)
        if m.group(6):
            info["marital_status"] = m.group(6)
        return info

    # 英文格式：Male    Age28(1986.6)    7years working experience    Master    Married
    # EN: English format: Male    Age28(1986.6)    7years working experience    Master    Married
    # JA: 英語の形式：Male    Age28(1986.6)    7years working experience    Master    Married
    en_degree = r"(Master|Bachelor|Doctor|PhD|Associate|Diploma|MBA|EMBA|High School)"
    m = re.search(
        rf"(Male|Female)\s+Age(\d+)\((\d{{4}})\.(\d{{1,2}})\)\s+\d+years?\s+working experience\s+{en_degree}\s+(Single|Married|Divorced|Widowed)?",
        text,
    )
    if m:
        info["gender"] = "男" if m.group(1) == "Male" else "女"
        info["age"] = m.group(2)
        info["birth_year"] = m.group(3)
        info["birth_date"] = f"{m.group(3)}年{int(m.group(4)):02d}月01日"
        en_deg = m.group(5)
        deg_map = {"Master": "硕士", "Bachelor": "本科", "Doctor": "博士", "PhD": "博士",
                   "Associate": "大专", "Diploma": "大专", "MBA": "硕士", "EMBA": "硕士", "High School": "高中"}
        info["degree"] = deg_map.get(en_deg, en_deg)
        if m.group(6):
            ms_map = {"Single": "未婚", "Married": "已婚", "Divorced": "离异", "Widowed": "丧偶"}
            info["marital_status"] = ms_map.get(m.group(6), m.group(6))
        return info

    return info


def _extract_phone(text: str) -> str:
    """提取手机号

    EN: Extract the mobile number

    JA: 携帯電話番号を抽出する
    """
    # App 格式：手机：13800000013 或 电话：184 0063 1597 分机号...
    # EN: App format: 手机：13800000013 or 电话：<number> 分机号... (mobile / phone / extension)
    # JA: アプリの形式：手机：13800000013 または 电话：<番号> 分机号...（携帯・電話・内線）
    m = re.search(r"(?:手机|电话)[：:]\s*([\d\s]+?)(?:\s*(?:分机号|该虚拟号|将于|$))", text)
    if m:
        phone = re.sub(r"\s+", "", m.group(1))
        phone = re.sub(r"[^\d]", "", phone)
        if len(phone) >= 11:
            return phone[:11]
    # 通用手机号正则
    # EN: Generic mobile-number regex
    # JA: 汎用の携帯電話番号の正規表現
    m = re.search(r"1[3-9]\d{9}", text)
    if m:
        return m.group(0)
    return ""


def _extract_email(text: str) -> str:
    """提取邮箱。

    处理智联招聘 Word 格式中常见的 HYPERLINK 宏残留：
      E-mail： HYPERLINK "mailto:user2@example.com"  user2@example.com
    此时直接用 [Ee]?-?mail[：:]\\s*([^\\s<]+) 会误提取到 HYPERLINK，
    因此优先从 mailto: 与标准邮箱格式提取。

    EN: Extract the e-mail.

    Handles the HYPERLINK macro leftovers common in the Zhaopin Word format:
      E-mail： HYPERLINK "mailto:user2@example.com"  user2@example.com
    Using [Ee]?-?mail[：:]\\s*([^\\s<]+) directly here would wrongly extract HYPERLINK,
    so extraction from mailto: and the standard e-mail format comes first.

    JA: メールを抽出する。

    Zhaopin の Word の形式によくある HYPERLINK マクロの残骸に対処する：
      E-mail： HYPERLINK "mailto:user2@example.com"  user2@example.com
    この場合 [Ee]?-?mail[：:]\\s*([^\\s<]+) をそのまま使うと HYPERLINK を誤って抽出してしまうため、
    mailto: と標準のメールの形式からの抽出を優先する。
    """
    # 1. 优先从 mailto: 提取
    # EN: 1. Prefer extracting from mailto:
    # JA: 1. mailto: からの抽出を優先する
    m = re.search(r'mailto:([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})', text)
    if m:
        return m.group(1)
    # 2. 标准邮箱格式（排除 HYPERLINK 这种残留）
    # EN: 2. Standard e-mail format (excluding leftovers like HYPERLINK)
    # JA: 2. 標準のメールの形式（HYPERLINK などの残骸は除く）
    m = re.search(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', text)
    if m:
        return m.group(0)
    # 3. E-mail：xxx 格式（排除 HYPERLINK 等宏残留）
    # EN: 3. "E-mail：xxx" format (excluding macro leftovers such as HYPERLINK)
    # JA: 3. 「E-mail：xxx」の形式（HYPERLINK などのマクロの残骸は除く）
    m = re.search(r'[Ee]?-?mail[：:]\s*([^\s<]+)', text)
    if m and m.group(1) not in ("HYPERLINK", "hyperlink"):
        return m.group(1).strip()
    m = re.search(r"邮箱[：:]\s*([^\s]+)", text)
    if m:
        return m.group(1).strip()
    return ""


def _extract_address(text: str) -> str:
    """提取现居住地

    EN: Extract the current place of residence

    JA: 現住所を抽出する
    """
    m = re.search(r"现居住地[：:]\s*([^\n｜|]+)", text)
    if m:
        return m.group(1).strip()
    return ""


def _extract_household(text: str) -> str:
    """提取户口

    EN: Extract the hukou (household registration)

    JA: 戸籍を抽出する
    """
    m = re.search(r"户口[：:]\s*([^\n｜|]+)", text)
    if m:
        return m.group(1).strip()
    return ""


def _extract_start_date_from_status(text: str) -> str:
    """从「目前状况」提取到岗时间。

    智联招聘「目前状况」字段常含到岗时间信息，如：
      - 我目前处于离职状态，可立即上岗 → 随时到岗
      - 我目前在职，正考虑换个新环境（到岗时间一个月左右） → 1个月内到岗
      - 我目前在职，暂无跳槽打算 → 在职，到岗时间需协商

    EN: Extract the start date from "目前状况" (current status).

    Zhaopin's "目前状况" field often contains start-date information, e.g.:
      - 我目前处于离职状态，可立即上岗 (I have left my job and can start immediately) → 随时到岗 (available any time)
      - 我目前在职，正考虑换个新环境（到岗时间一个月左右） (currently employed, considering a change (start in about a month)) → 1个月内到岗 (within a month)
      - 我目前在职，暂无跳槽打算 (currently employed, no plan to change jobs for now) → 在职，到岗时间需协商 (employed, start date negotiable)

    JA: 「目前状况」（現在の状況）から入社可能時期を抽出する。

    Zhaopin の「目前状况」のフィールドには入社可能時期の情報が含まれることが多い。例：
      - 我目前处于离职状态，可立即上岗（退職済みで即時勤務可能）→ 随时到岗（いつでも可）
      - 我目前在职，正考虑换个新环境（到岗时间一个月左右）（在職中で転職を検討中（入社は 1 か月ほど後））→ 1个月内到岗（1 か月以内）
      - 我目前在职，暂无跳槽打算（在職中で当面転職の予定なし）→ 在职，到岗时间需协商（在職中、入社時期は要相談）
    """
    m = re.search(r"目前状况[：:]\s*([^\n]+)", text)
    if not m:
        return ""
    status = m.group(1).strip()
    if "立即" in status or "随时" in status:
        return "随时到岗"
    if re.search(r"一个月|1个月|一月", status):
        return "1个月内到岗"
    if re.search(r"两周|2周|半月|半个月", status):
        return "2周内到岗"
    if re.search(r"一周|1周", status):
        return "1周内到岗"
    if "离职" in status and "在职" not in status:
        return "已离职，可随时到岗"
    if "在职" in status:
        return "在职，到岗时间需协商"
    return status[:50]


def _parse_zhilian_expected_info(text: str) -> list[dict[str, Any]]:
    """解析求职意向。

    按 CONTEXT.md 7.2 规范生成 8 个字段：
      expected_city/expected_position/expected_salary/expected_annual_salary_min/
      expected_annual_salary_max/expected_industry/expected_employment_type/
      expected_start_date

    EN: Parse job preferences.

    Generate the 8 fields according to CONTEXT.md 7.2:
      expected_city/expected_position/expected_salary/expected_annual_salary_min/
      expected_annual_salary_max/expected_industry/expected_employment_type/
      expected_start_date

    JA: 希望条件を解析する。

    CONTEXT.md 7.2 の仕様に従って 8 フィールドを生成する：
      expected_city/expected_position/expected_salary/expected_annual_salary_min/
      expected_annual_salary_max/expected_industry/expected_employment_type/
      expected_start_date
    """
    result: list[dict[str, Any]] = []

    # App 格式：<strong>职位 城市</strong> 后跟 薪资｜行业｜全职
    # 匹配多个求职意向
    # EN: App format: <strong>position city</strong> followed by salary｜industry｜full-time
    #     Match multiple job preferences
    # JA: アプリの形式：<strong>職位 都市</strong> の後に 給与｜業界｜正社員 が続く
    #     複数の希望条件にマッチさせる
    pattern = re.compile(
        r"([\u4e00-\u9fffA-Za-z/]+)\s+([\u4e00-\u9fff]+)\n([\d千万元\-至]+/[月年])[｜|\s]*([^｜|\n]*)[｜|\s]*(全职|兼职|实习|全职、兼职/临时|远程)",
        re.M,
    )
    start_date = _extract_start_date_from_status(text)
    for m in pattern.finditer(text):
        result.append({
            "expected_position": m.group(1).strip(),
            "expected_city": m.group(2).strip(),
            "expected_salary": m.group(3).strip(),
            "expected_annual_salary_min": "",
            "expected_annual_salary_max": "",
            "expected_industry": m.group(4).strip(),
            "expected_employment_type": m.group(5).strip(),
            "expected_start_date": start_date,
        })

    # Word 格式：期望工作地区/期望月薪/期望工作性质/期望从事职业/期望从事行业
    # EN: Word format: 期望工作地区/期望月薪/期望工作性质/期望从事职业/期望从事行业 (desired region / monthly salary / job nature / occupation / industry)
    # JA: Word の形式：期望工作地区／期望月薪／期望工作性质／期望从事职业／期望从事行业（希望勤務地・月給・雇用形態・職種・業界）
    if not result:
        m_city = re.search(r"期望工作地区[：:]\s*([^\n]+)", text)
        m_salary = re.search(r"期望月薪[：:]\s*([^\n]+)", text)
        m_type = re.search(r"期望工作性质[：:]\s*([^\n]+)", text)
        m_pos = re.search(r"期望从事职业[：:]\s*([^\n]+)", text)
        m_ind = re.search(r"期望从事行业[：:]\s*([^\n]+)", text)
        if m_pos or m_city:
            result.append({
                "expected_position": m_pos.group(1).strip() if m_pos else "",
                "expected_city": m_city.group(1).strip() if m_city else "",
                "expected_salary": m_salary.group(1).strip() if m_salary else "",
                "expected_annual_salary_min": "",
                "expected_annual_salary_max": "",
                "expected_industry": m_ind.group(1).strip() if m_ind else "",
                "expected_employment_type": m_type.group(1).strip() if m_type else "",
                "expected_start_date": _extract_start_date_from_status(text),
            })

    # 英文格式：Desired Location / Desired Salary / Type of Employment / Desired Position / Desired Industry
    # EN: English format: Desired Location / Desired Salary / Type of Employment / Desired Position / Desired Industry
    # JA: 英語の形式：Desired Location / Desired Salary / Type of Employment / Desired Position / Desired Industry
    if not result:
        m_city = re.search(r"Desired Location[：:]\s*([^\n]+)", text, re.I)
        m_salary = re.search(r"Desired Salary[：:]\s*([^\n]+)", text, re.I)
        m_type = re.search(r"Type of Employment[：:]\s*([^\n]+)", text, re.I)
        m_pos = re.search(r"Desired Position[：:]\s*([^\n]+)", text, re.I)
        m_ind = re.search(r"Desired Industry[：:]\s*([^\n]+)", text, re.I)
        if m_pos or m_city:
            result.append({
                "expected_position": m_pos.group(1).strip() if m_pos else "",
                "expected_city": m_city.group(1).strip() if m_city else "",
                "expected_salary": m_salary.group(1).strip() if m_salary else "",
                "expected_annual_salary_min": "",
                "expected_annual_salary_max": "",
                "expected_industry": m_ind.group(1).strip() if m_ind else "",
                "expected_employment_type": m_type.group(1).strip() if m_type else "",
                "expected_start_date": _extract_start_date_from_status(text),
            })

    return result


def _section_block(text: str, start_headers: list[str], stop_headers: list[str]) -> str:
    """从 text 中截取某个板块（开始标题到下一个停止标题之间）。

    开始和停止关键词都在行首匹配（section header 独占一行），
    避免误匹配描述文本中的词汇（如「9年工作经验」中的「工作经验」、
    「学历证书」中的「证书」）。

    匹配时要求标题后跟空白或行尾（(?=\\s|$)），防止字段标签
    （如「证书说明：」「所获证书：」）被误匹配为板块标题。

    EN: Cut a section out of text (from its start heading to the next stop heading).

    Both start and stop keywords are matched at the start of a line (a section header occupies its own line),
    to avoid wrongly matching words in descriptive text (e.g. "工作经验" in "9年工作经验" (9 years of experience),
    "证书" in "学历证书" (degree certificate)).

    Matching requires the heading to be followed by whitespace or end of line ((?=\\s|$)), to prevent field labels
    (e.g. "证书说明：" (certificate notes:), "所获证书：" (certificates obtained:)) being matched as section headings.

    JA: text からあるセクション（開始見出しから次の停止見出しまで）を切り出す。

    開始と停止のキーワードはどちらも行頭でマッチさせ（セクション見出しは 1 行を占める）、
    説明文中の語（例：「9年工作经验」（経験 9 年）の「工作经验」、
    「学历证书」（学位証明書）の「证书」）に誤ってマッチしないようにする。

    マッチでは見出しの後が空白か行末であること（(?=\\s|$)）を求め、フィールドのラベル
    （例：「证书说明：」（資格の説明：）、「所获证书：」（取得資格：））がセクション見出しとして誤ってマッチするのを防ぐ。
    """
    start_pat = "|".join(re.escape(h) for h in start_headers)
    stop_pat = "|".join(re.escape(h) for h in stop_headers)
    # 开始关键词在行首匹配，且后跟空白或行尾（排除字段标签如「证书说明：」）
    # EN: Start keywords are matched at the start of the line and followed by whitespace or end of line (excluding field labels like "证书说明：" (certificate notes:))
    # JA: 開始のキーワードは行頭でマッチし、後ろが空白か行末であること（「证书说明：」（資格の説明：）のようなフィールドのラベルは除く）
    m_start = re.search(rf"^\s*(?:{start_pat})(?=\s|$)", text, re.M)
    if not m_start:
        return ""
    rest = text[m_start.end():]
    # 停止关键词在行首匹配，且后跟空白或行尾
    # EN: Stop keywords are matched at the start of the line and followed by whitespace or end of line
    # JA: 停止のキーワードは行頭でマッチし、後ろが空白か行末であること
    m_stop = re.search(rf"^\s*(?:{stop_pat})(?=\s|$)", rest, re.M)
    if m_stop:
        return rest[: m_stop.start()].strip()
    return rest.strip()


def _parse_zhilian_work_experiences(soup: Any, text: str) -> list[dict[str, Any]]:
    """解析智联招聘工作经历，支持 App 格式与 Word 格式。

    EN: Parse Zhaopin work history, supporting both the App format and the Word format.

    JA: Zhaopin の職歴を解析する。アプリの形式と Word の形式の両方に対応する。
    """
    works: list[dict[str, Any]] = []

    if soup is not None:
        works = _parse_zhilian_work_from_dom(soup)
    if not works:
        works = _parse_zhilian_work_from_text(text)

    # 补齐 position_achievements 字段
    # EN: Fill the position_achievements field
    # JA: position_achievements フィールドを補う
    for w in works:
        w.setdefault("position_achievements", "")
    return works


def _parse_zhilian_work_from_dom(soup: Any) -> list[dict[str, Any]]:
    """从 DOM 解析工作经历。

    EN: Parse work history from the DOM.

    JA: DOM から職歴を解析する。
    """
    works: list[dict[str, Any]] = []

    # 定位「工作经历」标题（支持中英文）
    # 使用 startswith 避免误匹配「9年工作经验」等非标题文本
    # EN: Locate the "工作经历" (work history) heading (Chinese and English supported)
    #     Use startswith to avoid wrongly matching non-heading text like "9年工作经验" (9 years of experience)
    # JA: 「工作经历」（職歴）の見出しの位置を特定する（中国語・英語に対応）
    #     「9年工作经验」（経験 9 年）のような見出しでないテキストに誤ってマッチしないよう startswith を使う
    work_header_tag = None
    for tag in soup.find_all(["p", "b", "strong"]):
        t = tag.get_text(strip=True)
        if t.startswith("工作经历") or t.startswith("工作经验") or \
           t.startswith("Work Experience") or t.startswith("Work History"):
            work_header_tag = tag
            break
    if not work_header_tag:
        return []

    # 找到标题后的所有 table（直到下一个板块标题）
    # EN: Find all tables after the heading (up to the next section heading)
    # JA: 見出しの後のすべての table を探す（次のセクション見出しまで）
    stop_keywords = ["项目经历", "教育经历", "语言能力", "自我评价", "培训经历", "专业技能", "证书", "所获",
                      "在校学习情况", "在校实践经历", "活动描述", "兴趣爱好",
                      "Project", "Education", "Language", "Self-Assessment", "Training", "Skills", "Certificates", "Awards"]
    tables: list[Any] = []
    node = work_header_tag.find_next(["table", "p", "b", "strong"])
    while node:
        node_text = node.get_text(strip=True)
        if any(kw in node_text for kw in stop_keywords) and node.name in ("p", "b", "strong"):
            break
        if node.name == "table":
            tables.append(node)
        node = node.find_next(["table", "p", "b", "strong"])

    for tbl in tables:
        rows = tbl.find_all("tr")
        if not rows:
            continue

        # 判断格式：App（单 table 多 tr 分组）vs Word（每 table 一段）
        # EN: Determine the format: App (one table with tr groups) vs Word (one table per entry)
        # JA: 形式を判定する：アプリ（1 つの table に tr のグループ）か Word（項目ごとに 1 つの table）か
        first_row_text = rows[0].get_text(strip=True)

        # App 格式：第一个 tr 是「公司 职位」，第二个 tr 是「薪资 日期」
        # EN: App format: the first tr is "company position", the second tr is "salary dates"
        # JA: アプリの形式：最初の tr が「会社 職位」、2 つ目の tr が「給与 期間」
        if _looks_like_app_work_row(first_row_text):
            works.extend(_parse_app_work_table(rows))
        else:
            # Word 格式：第一个 tr 是「日期 公司 (时长)」
            # EN: Word format: the first tr is "dates company (tenure)"
            # JA: Word の形式：最初の tr が「期間 会社 (在職期間)」
            w = _parse_word_work_table(rows)
            if w:
                works.append(w)

    return works


def _looks_like_app_work_row(text: str) -> bool:
    """判断是否为 App 格式的工作经历首行（公司名 + 职位，无日期）。

    EN: Decide whether this is the first line of an App-format work entry (company name + position, no dates).

    JA: アプリの形式の職歴の先頭行（会社名 + 職位、日付なし）かどうかを判定する。
    """
    # 不含日期范围，且含中文公司特征
    # EN: Contains no date range and has Chinese company features
    # JA: 期間を含まず、中国語の会社の特徴がある
    if DATE_RANGE_RE.search(text):
        return False
    # 含「工作描述」则是描述行不是首行
    # EN: If it contains "工作描述" (job description), it is a description line, not the first line
    # JA: 「工作描述」（職務説明）を含めば説明の行であり、先頭の行ではない
    if "工作描述" in text:
        return False
    return bool(re.search(r"[\u4e00-\u9fff]", text))


def _parse_app_work_table(rows: list[Any]) -> list[dict[str, Any]]:
    """解析 App 格式工作经历 table（多段在一个 table 内）。

    每段结构：
      tr[0]: 公司名   职位
      tr[1]: 薪资   日期(时长)
      tr[2]: 工作描述： + 描述
      tr[3]: 技能标签（可选，跳过）

    EN: Parse an App-format work-history table (several entries in one table).

    Structure of each entry:
      tr[0]: company name   position
      tr[1]: salary   dates (tenure)
      tr[2]: 工作描述： (job description:) + description
      tr[3]: skill tags (optional, skipped)

    JA: アプリの形式の職歴の table を解析する（1 つの table に複数の項目）。

    各項目の構造：
      tr[0]: 会社名   職位
      tr[1]: 給与   期間（在職期間）
      tr[2]: 工作描述：（職務説明：）+ 説明
      tr[3]: スキルのタグ（任意。スキップする）
    """
    works: list[dict[str, Any]] = []
    i = 0
    while i < len(rows):
        row_text = rows[i].get_text(strip=True)

        # 检测是否为公司+职位行（不含日期、不含工作描述）
        # EN: Detect whether it is a company + position line (no dates, no job description)
        # JA: 会社 + 職位の行か（日付も職務説明も含まない）を検出する
        if not _looks_like_app_work_row(row_text):
            i += 1
            continue

        # 必须验证：下一行含日期范围或薪资，才确认是公司行（过滤技能标签行）
        # EN: Must verify: only if the next line contains a date range or salary is it confirmed as a company line (filtering skill-tag lines)
        # JA: 必ず検証する：次の行に期間か給与がある場合だけ会社の行と確定する（スキルのタグの行を除外するため）
        next_text = rows[i + 1].get_text(strip=True) if i + 1 < len(rows) else ""
        has_date_next = bool(re.search(r"(?:19|20)\d{2}[./\-]\d{1,2}", next_text))
        has_salary_next = "元/月" in next_text or "元/年" in next_text
        if not has_date_next and not has_salary_next:
            i += 1
            continue

        # 解析公司名与职位（多空格分隔）
        # EN: Parse the company name and position (separated by multiple spaces)
        # JA: 会社名と職位を解析する（複数の空白で区切られている）
        company = ""
        position = ""
        parts = re.split(r"\s{2,}|\s{3,}", row_text)
        parts = [p.strip() for p in parts if p.strip()]
        if len(parts) >= 2:
            company = parts[0]
            position = parts[-1]
        elif parts:
            company = parts[0]

        salary = ""
        position_start = ""
        position_resigned = ""
        status = ""
        responsibilities = ""

        # 下一行：薪资 + 日期
        # EN: Next line: salary + dates
        # JA: 次の行：給与 + 期間
        if i + 1 < len(rows):
            next_text = rows[i + 1].get_text(strip=True)
            # 提取薪资
            # EN: Extract the salary
            # JA: 給与を抽出する
            m_sal = re.search(r"([\d,千万元\-至]+元?/月)", next_text)
            if m_sal:
                salary = m_sal.group(1)
            # 提取日期范围
            # EN: Extract the date range
            # JA: 期間を抽出する
            m_date = re.search(
                r"((?:19|20)\d{2}[./\-]\d{1,2})\s*[\-\u2010-\u2015~～至到]{1,4}\s*((?:19|20)\d{2}[./\-]\d{1,2}|至今|现在|目前)",
                next_text,
                re.I,
            )
            if m_date:
                position_start = _format_ym(m_date.group(1))
                end_raw = m_date.group(2)
                if end_raw in ("至今", "现在", "目前"):
                    position_resigned = ""
                    status = "在职"
                else:
                    position_resigned = _format_ym(end_raw)
                    status = "离职"

        # 下下行：工作描述
        # EN: The line after next: job description
        # JA: 次の次の行：職務説明
        if i + 2 < len(rows):
            desc_text = rows[i + 2].get_text(strip=True)
            desc_text = re.sub(r"^工作描述[：:]?\s*", "", desc_text)
            responsibilities = desc_text

        works.append({
            "company_name": company,
            "company_employees": "",
            "company_industry": "",
            "position": position,
            "position_type": "",
            "position_salary": salary,
            "position_dept": "",
            "position_report_to": "",
            "position_subordinate": "",
            "employment_type": "全职",
            "annual_salary_min": "",
            "annual_salary_max": "",
            "status": status,
            "position_start": position_start,
            "position_resigned": position_resigned,
            "resigned_reason": "",
            "position_responsibilities": responsibilities,
            "position_achievements": "",
        })

        # 跳过已处理的行（薪资行、描述行、可能的标签行）
        # EN: Skip lines already processed (salary line, description line, possible tag lines)
        # JA: 処理済みの行（給与の行・説明の行・タグの行かもしれないもの）をスキップする
        i += 3
        # 跳过技能标签行（不含日期、不含工作描述、不含元/月薪资）
        # 技能标签行特征：多个短词，无日期范围，无薪资，无工作描述
        # EN: Skip skill-tag lines (no dates, no job description, no 元/月 salary)
        #     Features of skill-tag lines: several short words, no date range, no salary, no job description
        # JA: スキルのタグの行をスキップする（日付・職務説明・元/月の給与を含まない）
        #     スキルのタグの行の特徴：短い語が複数あり、期間・給与・職務説明がない
        while i < len(rows):
            rt = rows[i].get_text(strip=True)
            if not rt:
                i += 1
                continue
            # 若是新的公司行（下一行紧跟日期），停止跳过
            # EN: If it is a new company line (immediately followed by dates on the next line), stop skipping
            # JA: 新しい会社の行（次の行にすぐ日付が続く）なら、スキップをやめる
            if _looks_like_app_work_row(rt) and i + 1 < len(rows):
                next_rt = rows[i + 1].get_text(strip=True)
                # 下一行含日期范围或薪资，则当前行是新公司行
                # EN: If the next line contains a date range or salary, the current line is a new company line
                # JA: 次の行に期間か給与があれば、現在の行は新しい会社の行
                if re.search(r"(?:19|20)\d{2}[./\-]\d{1,2}", next_rt) or "元/月" in next_rt:
                    break
            if _looks_like_app_work_row(rt) and not DATE_RANGE_RE.search(rt) and "元/月" not in rt and "工作描述" not in rt:
                # 可能是技能标签行，跳过
                # EN: Probably a skill-tag line; skip
                # JA: スキルのタグの行と思われるのでスキップする
                i += 1
                continue
            # 含日期的行，停止
            # EN: A line containing dates: stop
            # JA: 日付を含む行：止める
            if DATE_RANGE_RE.search(rt) or "元/月" in rt:
                break
            i += 1

    return works


def _clean_company_name(name: str) -> str:
    """清理公司名称：去除时长括号、控制字符、字段分隔符、尾部教育信息。

    LLM 解析器（CodexGeminiHtmlSchemaParser）在处理含日文内容的中文简历时，
    可能将 \xa0（不间断空格）、时长括号 (N年M个月)、\x07（字段分隔符）等
    遗留在 company_name 中。本函数对所有来源的 company_name 做统一清理。

    EN: Clean company names: remove tenure brackets, control characters, field separators and trailing education information.

    When handling Chinese résumés with Japanese content, the LLM parser (CodexGeminiHtmlSchemaParser)
    may leave non-breaking spaces, tenure brackets (N年M个月), field separators etc.
    in company_name. This function cleans company_name from all sources uniformly.

    JA: 会社名のクレンジング：在職期間の括弧・制御文字・フィールドの区切り・末尾の学歴情報を除く。

    日本語の内容を含む中国語の履歴書を処理する際、LLM のパーサー（CodexGeminiHtmlSchemaParser）は
    ノーブレークスペース・在職期間の括弧 (N年M个月)・フィールドの区切りなどを
    company_name に残すことがある。この関数はすべての出所の company_name を一律に整理する。
    """
    if not name:
        return ""
    # 1. 替换不间断空格
    # EN: 1. Replace non-breaking spaces
    # JA: 1. ノーブレークスペースを置き換える
    name = name.replace("\xa0", " ")
    # 2. 按 \x07（bell 字段分隔符）切分，只取第一段（公司名）
    # EN: 2. Split on \x07 (the bell field separator) and take only the first segment (the company name)
    # JA: 2. \x07（ベルのフィールド区切り）で分割し、最初の部分（会社名）だけを取る
    if "\x07" in name:
        name = name.split("\x07")[0]
    # 3. 替换换行和控制字符
    # EN: 3. Replace line breaks and control characters
    # JA: 3. 改行と制御文字を置き換える
    name = name.replace("\r", " ").replace("\n", " ")
    # 4. 去掉时长括号（全角半角，支持「7年 5个月」中间有空格）
    # EN: 4. Remove tenure brackets (full- and half-width, supporting a space inside like "7年 5个月")
    # JA: 4. 在職期間の括弧を除く（全角・半角。「7年 5个月」のように途中に空白がある場合にも対応）
    name = re.sub(r"[（(]\s*\d+年\s*\d+个月\s*[）)]", "", name)
    name = re.sub(r"[（(]\s*\d+个月\s*[）)]", "", name)
    name = re.sub(r"[（(]\s*\d+年\s*[）)]", "", name)
    name = re.sub(r"[（(]\s*[）)]", "", name)
    # 5. 去掉尾部教育信息（如「日语 本科」「其他 大专」——LLM 误将教育条目放入工作经历）
    # EN: 5. Remove trailing education information (e.g. "日语 本科" (Japanese, bachelor), "其他 大专" — the LLM put education entries into work history)
    # JA: 5. 末尾の学歴情報を除く（例：「日语 本科」（日本語・学士）、「其他 大专」— LLM が学歴の項目を職歴に入れたもの）
    name = re.sub(
        r"\s+[\u4e00-\u9fffA-Za-z]{1,10}\s+(本科|大专|硕士|博士|专科|中专|高中|学士)$",
        "",
        name,
    )
    # 6. 折叠多余空白
    # EN: 6. Collapse extra whitespace
    # JA: 6. 余分な空白をまとめる
    name = re.sub(r"\s+", " ", name)
    return name.strip(" 　\t\n\r\xa0-—–*·")


def _parse_word_work_table(rows: list[Any]) -> dict[str, Any] | None:
    """解析 Word 格式工作经历 table（每段一个 table）。

    结构变体：
      tr[0]: 「日期 公司 (时长)」或「日期 公司 (时长)」
      tr[1]: 「行业 | 职位 | 薪资」或「部门 | 职位」或纯「职位」
      tr[2]: 「行业 | 企业性质：xxx | 规模：xxx」
      tr[3]: 「工作描述：」| 描述

    EN: Parse a Word-format work-history table (one table per entry).

    Structural variants:
      tr[0]: "dates company (tenure)" or "dates company (tenure)"
      tr[1]: "industry | position | salary" or "department | position" or just "position"
      tr[2]: "industry | 企业性质：xxx | 规模：xxx" (enterprise type / size)
      tr[3]: "工作描述：" (job description:) | description

    JA: Word の形式の職歴の table を解析する（項目ごとに 1 つの table）。

    構造の変種：
      tr[0]:「期間 会社 (在職期間)」または「期間 会社 (在職期間)」
      tr[1]:「業界 | 職位 | 給与」または「部署 | 職位」または「職位」だけ
      tr[2]:「業界 | 企业性质：xxx | 规模：xxx」（企業の性質・規模）
      tr[3]:「工作描述：」（職務説明：）| 説明
    """
    if not rows:
        return None

    first_text = rows[0].get_text(strip=True)
    # 规范化：将不间断空格(\xa0)和\r替换为普通空格，避免时长括号正则失配
    # EN: Normalise: replace non-breaking spaces (\xa0) and \r with ordinary spaces, so the tenure-bracket regex does not fail to match
    # JA: 正規化：ノーブレークスペース（\xa0）と \r を普通の空白に置き換え、在職期間の括弧の正規表現がマッチし損なわないようにする
    first_text = first_text.replace("\xa0", " ").replace("\r", "")
    first_text = re.sub(r"[ \t]{2,}", "  ", first_text)

    # 提取日期范围与公司名
    # EN: Extract the date range and company name
    # JA: 期間と会社名を抽出する
    position_start = ""
    position_resigned = ""
    status = ""
    company = ""

    m_date = re.search(
        r"((?:19|20)\d{2}[./\-]\d{1,2})\s*[\-\u2010-\u2015~～至到]{1,4}\s*((?:19|20)\d{2}[./\-]\d{1,2}|至今|现在|目前)",
        first_text,
        re.I,
    )
    if m_date:
        position_start = _format_ym(m_date.group(1))
        end_raw = m_date.group(2)
        if end_raw in ("至今", "现在", "目前"):
            position_resigned = ""
            status = "在职"
        else:
            position_resigned = _format_ym(end_raw)
            status = "离职"

    # 公司名：去掉日期范围与时长括号
    # EN: Company name: remove the date range and tenure brackets
    # JA: 会社名：期間と在職期間の括弧を除く
    company = first_text
    # 去掉日期范围
    # EN: Remove the date range
    # JA: 期間を除く
    company = re.sub(
        r"(?:19|20)\d{2}[./\-]\d{1,2}\s*[\-\u2010-\u2015~～至到]{1,4}\s*(?:(?:19|20)\d{2}[./\-]\d{1,2}|至今|现在|目前)",
        "",
        company,
    )
    # 去掉时长括号（含全角半角，支持「7年 5个月」中间有空格的写法）
    # EN: Remove tenure brackets (full- and half-width, supporting forms with a space inside like "7年 5个月")
    # JA: 在職期間の括弧を除く（全角・半角。「7年 5个月」のように途中に空白がある書き方にも対応）
    company = re.sub(r"[（(]\s*\d+年\s*\d+个月\s*[）)]", "", company)
    company = re.sub(r"[（(]\s*\d+个月\s*[）)]", "", company)
    company = re.sub(r"[（(]\s*\d+年\s*[）)]", "", company)
    company = re.sub(r"[（(]\s*[）)]", "", company)
    company = company.strip(" 　\t\n\r\xa0-—–*·")

    position = ""
    salary = ""
    industry = ""
    company_employees = ""
    company_type = ""
    position_dept = ""
    responsibilities = ""

    for r in rows[1:]:
        r_text = r.get_text(strip=True)
        if not r_text:
            continue

        # 部门 | 职位 | 薪资  或  行业 | 职位 | 薪资（含竖线与元/月）
        # 智联 Word 格式顺序固定为 [部门/行业, 职位, 薪资]，职位为薪资前一段
        # EN: department | position | salary  or  industry | position | salary (with pipes and 元/月)
        #     The Zhaopin Word format order is fixed as [department/industry, position, salary]; the position is the segment before the salary
        # JA: 部署 | 職位 | 給与 または 業界 | 職位 | 給与（縦線と 元/月 を含む）
        #     Zhaopin の Word の形式は順序が [部署／業界, 職位, 給与] に固定されており、職位は給与の 1 つ前の部分
        if "|" in r_text and ("元/月" in r_text or "元/年" in r_text):
            segs = [s.strip() for s in r_text.split("|")]
            non_salary = [s for s in segs if s and "元/月" not in s and "元/年" not in s]
            for seg in segs:
                if "元/月" in seg or "元/年" in seg:
                    salary = seg
            if len(non_salary) >= 2:
                # [部门, 职位, 薪资]：中间为职位，第一段为部门
                # EN: [department, position, salary]: the middle is the position, the first segment is the department
                # JA: [部署, 職位, 給与]：中央が職位、最初の部分が部署
                position = non_salary[1]
                if not position_dept:
                    position_dept = non_salary[0]
            elif len(non_salary) == 1 and not position:
                position = non_salary[0]
            continue

        # 部门 | 职位（含竖线但无元/月）
        # EN: department | position (with pipes but no 元/月)
        # JA: 部署 | 職位（縦線はあるが 元/月 はない）
        if "|" in r_text and not position:
            segs = [s.strip() for s in r_text.split("|") if s.strip()]
            if len(segs) >= 2:
                position = segs[-1]
                # 第一个是部门
                # EN: The first is the department
                # JA: 最初のものが部署
                if not position_dept:
                    position_dept = segs[0]
            continue

        # 行业 | 企业性质 | 规模
        # EN: industry | enterprise type | size
        # JA: 業界 | 企業の性質 | 規模
        if "企业性质" in r_text or "规模" in r_text:
            m_emp = re.search(r"规模[：:]\s*([^|\n]+)", r_text)
            if m_emp:
                company_employees = m_emp.group(1).strip()
            m_ct = re.search(r"企业性质[：:]\s*([^|\n]+)", r_text)
            if m_ct:
                company_type = m_ct.group(1).strip()
            # 行业在竖线前
            # EN: The industry is before the pipe
            # JA: 業界は縦線の前にある
            m_ind = re.match(r"^([^|]+?)\s*\|", r_text)
            if m_ind and not industry:
                industry = m_ind.group(1).strip()
            continue

        # 工作描述
        # EN: Job description
        # JA: 職務説明
        if "工作描述" in r_text:
            desc = re.sub(r"^.*?工作描述[：:]?\s*", "", r_text)
            responsibilities = desc.strip()
            continue

        # 纯职位行（无竖线、无元/月、无工作描述、无企业性质）
        # EN: A pure position line (no pipes, no 元/月, no job description, no enterprise type)
        # JA: 職位だけの行（縦線・元/月・職務説明・企業の性質がない）
        if not position and r_text and "企业性质" not in r_text and "工作描述" not in r_text and "元/月" not in r_text:
            # 避免把行业行当职位
            # EN: Avoid taking an industry line as the position
            # JA: 業界の行を職位にしないようにする
            if not re.search(r"[/｜|]", r_text) and len(r_text) <= 30:
                position = r_text
            continue

        # 含元/月但无竖线（纯薪资行）
        # EN: Contains 元/月 but no pipe (a pure salary line)
        # JA: 元/月 を含むが縦線がない（給与だけの行）
        if "元/月" in r_text and not salary:
            salary = r_text.strip()
            continue

    if not company and not position_start:
        return None

    return {
        "company_name": company.strip(),
        "company_employees": company_employees,
        "company_industry": industry,
        "position": position,
        "position_type": "",
        "position_salary": salary,
        "position_dept": position_dept,
        "position_report_to": "",
        "position_subordinate": "",
        "employment_type": "全职",
        "annual_salary_min": "",
        "annual_salary_max": "",
        "status": status,
        "position_start": position_start,
        "position_resigned": position_resigned,
        "resigned_reason": "",
        "position_responsibilities": responsibilities,
        "position_achievements": "",
    }


def _parse_work_first_line(line: str) -> dict[str, str]:
    """解析工作经历首行（支持粘连格式）。

    智联 Word 格式首行结构：
      日期  公司名  （时长） 部门 | 职位 | 薪资 行业 | ...
    预处理后「企业性质：」「规模：」「工作描述：」已换行，但首行的
    「部门 | 职位 | 薪资 行业」仍粘连在一行，需精细解析。

    返回 dict: company, dept, position, salary, industry

    EN: Parse the first line of a work entry (supporting the stuck format).

    Structure of the first line in the Zhaopin Word format:
      dates  company name  (tenure) department | position | salary industry | ...
    After pre-processing, "企业性质：" "规模：" "工作描述：" are on new lines, but the first line's
    "department | position | salary industry" is still stuck on one line and needs fine-grained parsing.

    Returns dict: company, dept, position, salary, industry

    JA: 職歴の先頭行を解析する（くっついた形式に対応）。

    Zhaopin の Word の形式の先頭行の構造：
      期間  会社名  （在職期間） 部署 | 職位 | 給与 業界 | ...
    前処理の後「企业性质：」「规模：」「工作描述：」は改行されているが、先頭行の
    「部署 | 職位 | 給与 業界」はまだ 1 行にくっついているため、精密に解析する必要がある。

    戻り値の dict：company, dept, position, salary, industry
    """
    result = {"company": "", "dept": "", "position": "", "salary": "", "industry": ""}

    # 提取日期范围
    # EN: Extract the date range
    # JA: 期間を抽出する
    m_date = DATE_RANGE_RE.search(line)
    if not m_date:
        return result

    remaining = line[m_date.end():]
    # 规范化不间断空格和\r
    # EN: Normalise non-breaking spaces and \r
    # JA: ノーブレークスペースと \r を正規化する
    remaining = remaining.replace("\xa0", " ").replace("\r", "")
    # 去掉时长括号（支持全角半角，支持「7年 5个月」中间有空格的写法）
    # EN: Remove tenure brackets (full- and half-width, supporting forms with a space inside like "7年 5个月")
    # JA: 在職期間の括弧を除く（全角・半角。「7年 5个月」のように途中に空白がある書き方にも対応）
    remaining = re.sub(r"[（(]\s*\d+年\s*\d+个月\s*[）)]", "", remaining)
    remaining = re.sub(r"[（(]\s*\d+个月\s*[）)]", "", remaining)
    remaining = re.sub(r"[（(]\s*\d+年\s*[）)]", "", remaining)
    remaining = remaining.strip(" 　\t\n\r\xa0-—–")

    if "|" in remaining:
        pipe_parts = [p.strip() for p in remaining.split("|")]
        pipe_parts = [p for p in pipe_parts if p]

        # 第1段：公司名 + 部门（按多空格分割）
        # EN: Segment 1: company name + department (split on multiple spaces)
        # JA: 第 1 部分：会社名 + 部署（複数の空白で分割）
        if pipe_parts:
            first = pipe_parts[0]
            space_parts = [p.strip() for p in re.split(r"\s{2,}", first) if p.strip()]
            if space_parts:
                result["company"] = space_parts[0]
            # space_parts[1] 可能是部门
            # EN: space_parts[1] may be the department
            # JA: space_parts[1] は部署かもしれない
            if len(space_parts) > 1:
                result["dept"] = space_parts[1]

        # 第2段：职位
        # EN: Segment 2: position
        # JA: 第 2 部分：職位
        if len(pipe_parts) > 1:
            result["position"] = pipe_parts[1].strip()

        # 第3段：薪资 + 行业
        # EN: Segment 3: salary + industry
        # JA: 第 3 部分：給与 + 業界
        if len(pipe_parts) > 2:
            third = pipe_parts[2]
            m_sal = re.search(r"([\d,千万元\-至]+元?/[月年])", third)
            if m_sal:
                result["salary"] = m_sal.group(1)
                result["industry"] = re.sub(re.escape(m_sal.group(1)), "", third).strip()
            else:
                result["industry"] = third.strip()
    else:
        # 无 | 分隔，按多空格分割
        # EN: No | separator; split on multiple spaces
        # JA: | の区切りがないので、複数の空白で分割する
        space_parts = [p.strip() for p in re.split(r"\s{2,}", remaining) if p.strip()]
        if space_parts:
            result["company"] = space_parts[0]
        if len(space_parts) > 1:
            result["position"] = space_parts[-1]

    return result


def _parse_zhilian_work_from_text(text: str) -> list[dict[str, Any]]:
    """从纯文本解析工作经历（兜底）。

    支持智联 Word 格式（含粘连格式）：日期  公司  （时长） 部门 | 职位 | 薪资 行业
    预处理后的「企业性质：」「规模：」「工作描述：」会独立成行，本函数从中提取。

    EN: Parse work history from plain text (fallback).

    Supports the Zhaopin Word format (including the stuck format): dates  company  (tenure) department | position | salary industry
    After pre-processing, "企业性质：" "规模：" "工作描述：" are on their own lines; this function extracts from them.

    JA: プレーンテキストから職歴を解析する（最終手段）。

    Zhaopin の Word の形式（くっついた形式を含む）に対応：期間  会社  （在職期間） 部署 | 職位 | 給与 業界
    前処理の後「企业性质：」「规模：」「工作描述：」は独立した行になっており、この関数はそこから抽出する。
    """
    block = _section_block(
        text,
        ["工作经历", "工作经验", "Work Experience", "Work History", "Employment"],
        ["项目经历", "教育经历", "语言能力", "自我评价", "培训经历", "专业技能", "所获证书", "证书",
         "在校学习情况", "在校实践经历", "活动描述", "兴趣爱好",
         "Project", "Education", "Language", "Self-Assessment", "Self-Evaluation",
         "Training", "Professional Skills", "Skills", "Certificates", "Awards"],
    )
    if not block:
        return []

    # 学历关键词：用于排除教育行被误识别为工作经历
    # （如「2007.09 - 2011.06  徐州师范大学  日语  本科」会被 DATE_RANGE_RE 匹配）
    # EN: Degree keywords: used to exclude education lines misidentified as work history
    #     (e.g. "2007.09 - 2011.06  徐州师范大学  日语  本科" would be matched by DATE_RANGE_RE)
    # JA: 学歴のキーワード：職歴と誤認された学歴の行を除外するために使う
    #     （例：「2007.09 - 2011.06  徐州师范大学  日语  本科」は DATE_RANGE_RE にマッチしてしまう）
    degree_keywords_re = re.compile(r"(博士后|博士|硕士|本科|大专|专科|高中|中专|职高|初中|小学)")

    works: list[dict[str, Any]] = []
    lines = [l.strip() for l in block.splitlines() if l.strip()]
    i = 0
    while i < len(lines):
        line = lines[i]
        m = DATE_RANGE_RE.search(line)
        if m:
            # 排除教育行（含学历关键词）
            # EN: Exclude education lines (containing degree keywords)
            # JA: 学歴の行（学歴のキーワードを含む）を除外する
            if degree_keywords_re.search(line):
                i += 1
                continue

            start_ym = _format_ym(m.group(1))
            end_raw = m.group(2)
            if end_raw in ("至今", "现在", "目前", "Present"):
                end_ym = ""
                status = "在职"
            else:
                end_ym = _format_ym(end_raw)
                status = "离职"

            # 解析首行（粘连格式：公司名 部门 | 职位 | 薪资 行业）
            # EN: Parse the first line (stuck format: company name department | position | salary industry)
            # JA: 先頭の行を解析する（くっついた形式：会社名 部署 | 職位 | 給与 業界）
            info = _parse_work_first_line(line)
            company = info["company"]
            position = info["position"]
            salary = info["salary"]
            industry = info["industry"]
            position_dept = info["dept"]
            employees = ""
            responsibilities = ""

            # 从下一行找企业性质/规模/工作描述
            # EN: Look in the next lines for enterprise type / size / job description
            # JA: 次の行から企業の性質・規模・職務説明を探す
            j = i + 1
            while j < len(lines):
                c = lines[j]
                if DATE_RANGE_RE.search(c):
                    break
                # 遇到教育行停止
                # EN: Stop at an education line
                # JA: 学歴の行に達したら止める
                if degree_keywords_re.search(c):
                    break
                if "工作描述" in c:
                    # 收集描述
                    # EN: Collect the description
                    # JA: 説明を集める
                    desc = re.sub(r"^.*?工作描述[：:]?\s*", "", c)
                    k = j + 1
                    while k < len(lines) and not DATE_RANGE_RE.search(lines[k]) and not degree_keywords_re.search(lines[k]):
                        desc += "\n" + lines[k]
                        k += 1
                    responsibilities = desc.strip()
                    j = k
                    continue
                # 行业 | 职位 | 薪资（首行未提取到时的兜底）
                # EN: industry | position | salary (fallback when the first line yielded nothing)
                # JA: 業界 | 職位 | 給与（先頭の行で取れなかった場合の最終手段）
                if "|" in c and ("元/月" in c or "元/年" in c) and not salary:
                    segs = [s.strip() for s in c.split("|")]
                    for seg in segs:
                        if "元/月" in seg or "元/年" in seg:
                            salary = seg
                        elif seg and not position:
                            position = seg
                        elif seg and not industry:
                            industry = seg
                    j += 1
                    continue
                # 规模/企业性质行
                # EN: Size / enterprise-type line
                # JA: 規模・企業の性質の行
                if "企业性质" in c:
                    j += 1
                    continue
                if "规模" in c:
                    m_emp = re.search(r"规模[：:]\s*([^|\n]+)", c)
                    if m_emp:
                        employees = m_emp.group(1).strip()
                    j += 1
                    continue
                j += 1

            if not company and not position:
                i += 1
                continue

            works.append({
                "company_name": company,
                "company_employees": employees,
                "company_industry": industry,
                "position": position,
                "position_type": "",
                "position_salary": salary,
                "position_dept": position_dept,
                "position_report_to": "",
                "position_subordinate": "",
                "employment_type": "全职",
                "annual_salary_min": "",
                "annual_salary_max": "",
                "status": status,
                "position_start": start_ym,
                "position_resigned": end_ym,
                "resigned_reason": "",
                "position_responsibilities": responsibilities,
                "position_achievements": "",
            })
            i = j
        else:
            i += 1

    return works


def _parse_zhilian_education(text: str) -> list[dict[str, Any]]:
    """解析教育经历。

    App 格式：
      <strong>四川文理学院   计算机科学与技术（应用技术）</strong>
      2015.09 - 2019.06    本科    统招
    Word 格式：
      2002.07 - 2004.07  辽宁科技大学  财政学  大专

    EN: Parse education history.

    App format:
      <strong>四川文理学院   计算机科学与技术（应用技术）</strong>
      2015.09 - 2019.06    本科    统招
    Word format:
      2002.07 - 2004.07  辽宁科技大学  财政学  大专

    JA: 学歴を解析する。

    アプリの形式：
      <strong>四川文理学院   计算机科学与技术（应用技术）</strong>
      2015.09 - 2019.06    本科    统招
    Word の形式：
      2002.07 - 2004.07  辽宁科技大学  财政学  大专
    """
    block = _section_block(
        text,
        ["教育经历", "教育背景", "Education"],
        ["语言能力", "技能", "自我评价", "培训经历", "专业技能", "证书", "所获", "项目经历", "工作经历",
         "在校学习情况", "在校实践经历", "在校实践", "在校经历", "活动描述", "实践描述", "兴趣爱好",
         "Language", "Self-Assessment", "Training", "Skills", "Certificates", "Awards",
         "Project", "Work Experience"],
    )
    if not block:
        return []

    edus: list[dict[str, Any]] = []
    lines = [l.strip() for l in block.splitlines() if l.strip()]

    i = 0
    while i < len(lines):
        line = lines[i]

        # 尝试匹配日期行（Word 格式：日期在前）
        # EN: Try matching a date line (Word format: date first)
        # JA: 日付の行へのマッチを試みる（Word の形式：日付が先）
        m_date_first = re.match(
            r"((?:19|20)\d{2}[./\-]\d{1,2})\s*[\-\u2010-\u2015~～至到]{1,4}\s*((?:19|20)\d{2}[./\-]\d{1,2})\s+(.+)",
            line,
        )
        if m_date_first:
            start_ym = _format_ym(m_date_first.group(1))
            end_ym = _format_ym(m_date_first.group(2))
            rest = m_date_first.group(3).strip()
            # rest: 学校 专业 学历
            # EN: rest: school major degree
            # JA: rest：学校 専攻 学歴
            school, major, degree = _split_school_major_degree(rest)
            edus.append({
                "school_name": school,
                "school_major_name": major,
                "school_degree_type": degree,
                "school_degree_rank": "",
                "school_education_type": "",
                "school_start_ym": start_ym,
                "school_end_ym": end_ym,
            })
            i += 1
            continue

        # App 格式：学校+专业行，下一行是 日期 学历 统招
        # EN: App format: a school + major line, with "dates degree unified enrolment" on the next line
        # JA: アプリの形式：学校 + 専攻の行の次の行に「期間 学歴 統一入試」がある
        m_school = re.match(r"^([\u4e00-\u9fffA-Za-z（）()]+大学|[\u4e00-\u9fffA-Za-z（）()]+学院|[\u4e00-\u9fffA-Za-z（）()]+学校)", line)
        if m_school and i + 1 < len(lines):
            next_line = lines[i + 1]
            m_date = re.match(
                r"((?:19|20)\d{2}[./\-]\d{1,2})\s*[\-\u2010-\u2015~～至到]{1,4}\s*((?:19|20)\d{2}[./\-]\d{1,2})\s+(博士后|博士|硕士|本科|大专|专科|高中|中专|职高|初中|小学)?",
                next_line,
            )
            if m_date:
                start_ym = _format_ym(m_date.group(1))
                end_ym = _format_ym(m_date.group(2))
                degree = m_date.group(3) or ""

                # 当前行：学校 专业
                # EN: Current line: school major
                # JA: 現在の行：学校 専攻
                school_line = line.strip()
                school, major, _ = _split_school_major(school_line)

                edus.append({
                    "school_name": school,
                    "school_major_name": major,
                    "school_degree_type": degree,
                    "school_degree_rank": "",
                    "school_education_type": "",
                    "school_start_ym": start_ym,
                    "school_end_ym": end_ym,
                })
                i += 2
                continue

        i += 1

    return edus


def _split_school_major_degree(text: str) -> tuple[str, str, str]:
    """拆分「学校 专业 学历」文本。

    智联招聘教育行顺序固定为「学校 专业 学历」，先剔除学历段，
    剩余部分按顺序：第一段为学校、第二段为专业。
    之前的实现用「大学|学院|学校」关键词识别学校，但部分学校名
    （如「沃特福德理工（爱尔兰）」「山东大学（威海）」外的分校、
    海外院校）不含这些关键词导致学校/专业互换，故改为顺序法。

    EN: Split "school major degree" text.

    The order of Zhaopin education lines is fixed as "school major degree": first remove the degree segment,
    then in order the first remaining segment is the school and the second the major.
    The previous implementation recognised schools by the keywords "大学|学院|学校", but some school names
    (e.g. "沃特福德理工（爱尔兰）", branch campuses other than "山东大学（威海）",
    overseas institutions) lack these keywords, causing school/major swaps; hence the switch to the order-based method.

    JA: 「学校 専攻 学歴」のテキストを分割する。

    Zhaopin の学歴の行は「学校 専攻 学歴」の順に固定されているため、まず学歴の部分を取り除き、
    残りを順に、1 つ目を学校、2 つ目を専攻とする。
    以前の実装は「大学|学院|学校」のキーワードで学校を識別していたが、一部の学校名
    （「沃特福德理工（爱尔兰）」、「山东大学（威海）」以外の分校、
    海外の教育機関など）はこれらのキーワードを含まず学校と専攻が入れ替わったため、順序による方法に改めた。
    """
    parts = [p.strip() for p in re.split(r"\s{2,}", text) if p.strip()]
    school = ""
    major = ""
    degree = ""
    degree_keywords = ("博士后", "博士", "硕士", "本科", "大专", "专科", "高中", "中专", "职高", "初中", "小学")

    non_degree: list[str] = []
    for p in parts:
        if any(d in p for d in degree_keywords) and not degree:
            degree = p
        else:
            non_degree.append(p)

    # 顺序：学校在前，专业在后
    # EN: Order: school first, major after
    # JA: 順序：学校が先、専攻が後
    if non_degree:
        school = non_degree[0]
    if len(non_degree) > 1:
        major = non_degree[1]

    return school, major, degree


def _split_school_major(text: str) -> tuple[str, str, str]:
    """拆分「学校 专业」文本（App 格式学校行）。

    EN: Split "school major" text (the App-format school line).

    JA: 「学校 専攻」のテキストを分割する（アプリの形式の学校の行）。
    """
    parts = [p.strip() for p in re.split(r"\s{2,}", text) if p.strip()]
    school = ""
    major = ""
    for p in parts:
        if not school and re.search(r"大学|学院|学校", p):
            school = p
        elif not major:
            major = p
    if not school and parts:
        school = parts[0]
        if len(parts) > 1:
            major = parts[1]
    return school, major, ""


def _parse_zhilian_projects(text: str) -> list[dict[str, Any]]:
    """解析项目经历。

    支持两种格式：
      App 格式：<p>项目名</p><p>日期(时长)</p><p>描述</p>（项目名与日期分行）
      Word 格式：日期  项目名（同一行），后接 责任描述/项目描述 段落

    EN: Parse project history.

    Supports two formats:
      App format: <p>project name</p><p>dates (duration)</p><p>description</p> (project name and dates on separate lines)
      Word format: dates  project name (on the same line), followed by 责任描述/项目描述 (responsibility / project description) paragraphs

    JA: プロジェクト経験を解析する。

    2 つの形式に対応する：
      アプリの形式：<p>プロジェクト名</p><p>期間（期間の長さ）</p><p>説明</p>（プロジェクト名と期間は別の行）
      Word の形式：期間  プロジェクト名（同じ行）、その後に 责任描述／项目描述（担当業務の説明・プロジェクトの説明）の段落
    """
    block = _section_block(
        text,
        ["项目经历", "项目经验", "Project"],
        ["教育经历", "语言能力", "自我评价", "培训经历", "专业技能", "证书", "所获", "工作经历",
         "在校学习情况", "在校实践经历", "活动描述", "兴趣爱好",
         "Education", "Language", "Self-Assessment", "Training", "Skills", "Certificates", "Awards",
         "Work Experience"],
    )
    if not block:
        return []

    # 预处理粘连格式：项目间无换行，日期范围和「责任描述/项目描述」粘连在项目名同一行
    # 在「责任描述：」「项目描述：」「职责：」前插入换行
    # EN: Pre-process the stuck format: no line breaks between projects, and the date range and "责任描述/项目描述" (responsibility / project description) are stuck on the same line as the project name
    #     Insert line breaks before "责任描述：", "项目描述：", "职责："
    # JA: くっついた形式を前処理する：プロジェクト間に改行がなく、期間と「责任描述／项目描述」（担当業務の説明・プロジェクトの説明）がプロジェクト名と同じ行にくっついている
    #     「责任描述：」「项目描述：」「职责：」の前に改行を入れる
    block = re.sub(r"(?<=[^\n])(责任描述|项目描述|项目介绍|职责)([：:])", r"\n\1\2", block)
    # 在日期范围前插入换行（当日期范围不在行首时，处理项目间粘连）
    # EN: Insert a line break before date ranges (when a date range is not at the start of a line, to handle projects stuck together)
    # JA: 期間の前に改行を入れる（期間が行頭にない場合。プロジェクト同士のくっつきに対処する）
    block = re.sub(
        r"(?<=[^\n])\s*((?:19|20)\d{2}[./\-]\d{1,2}\s*[\-\u2010-\u2015~～至到]{1,4}\s*"
        r"(?:(?:19|20)\d{2}[./\-]\d{1,2}|至今|现在|目前))",
        r"\n\1",
        block,
    )

    projects: list[dict[str, Any]] = []
    lines = [l.strip() for l in block.splitlines() if l.strip()]

    # Word 格式：行首日期范围 + 项目名（同一行）
    # EN: Word format: date range at the start of the line + project name (on the same line)
    # JA: Word の形式：行頭の期間 + プロジェクト名（同じ行）
    word_date_re = re.compile(
        r"^((?:19|20)\d{2}[./\-]\d{1,2})\s*[\-\u2010-\u2015~～至到]{1,4}\s*"
        r"((?:19|20)\d{2}[./\-]\d{1,2}|至今|现在|目前)\s*(?:\([^)]*\))?\s+(.+)"
    )
    # App 格式：日期范围独占一行
    # EN: App format: the date range is on its own line
    # JA: アプリの形式：期間が単独の行にある
    app_date_re = re.compile(
        r"^((?:19|20)\d{2}[./\-]\d{1,2})\s*[\-\u2010-\u2015~～至到]{1,4}\s*"
        r"((?:19|20)\d{2}[./\-]\d{1,2}|至今|现在|目前)\s*(?:\([^)]*\))?$"
    )

    def _is_project_start(idx: int) -> bool:
        """判断第 idx 行是否为项目起始行（Word 或 App 格式）。

        EN: Decide whether line idx is the start line of a project (Word or App format).

        JA: idx 行目がプロジェクトの開始行（Word またはアプリの形式）かどうかを判定する。
        """
        if idx >= len(lines):
            return False
        if word_date_re.match(lines[idx]):
            return True
        if app_date_re.match(lines[idx]):
            return True
        # App 格式：当前行为项目名，下一行为日期
        # EN: App format: the current line is the project name, the next line the dates
        # JA: アプリの形式：現在の行がプロジェクト名、次の行が日付
        if idx + 1 < len(lines) and app_date_re.match(lines[idx + 1]):
            return True
        return False

    def _make_project(name: str, start_ym: str, end_ym: str,
                      description: str, responsibilities: str) -> dict[str, Any]:
        return {
            "sequence_no": len(projects) + 1,
            "fingerprint": "",
            "project_name": name[:160],
            "company_or_client": "",
            "role_name": "",
            "start_ym": start_ym,
            "end_ym": end_ym,
            "description": description.strip(),
            "responsibilities": responsibilities.strip(),
            "achievements": "",
            "keywords": "",
        }

    i = 0
    while i < len(lines):
        line = lines[i]

        # Word 格式：日期  项目名（同一行）
        # EN: Word format: dates  project name (on the same line)
        # JA: Word の形式：期間  プロジェクト名（同じ行）
        m_word = word_date_re.match(line)
        if m_word:
            start_ym = _format_ym(m_word.group(1))
            end_raw = m_word.group(2)
            end_ym = "" if end_raw in ("至今", "现在", "目前") else _format_ym(end_raw)
            project_name = m_word.group(3).strip()
            description = ""
            responsibilities = ""
            cur_section = "desc"  # 默认归入 description
            # EN: Put into description by default
            # JA: 既定では description に入れる
            j = i + 1
            while j < len(lines):
                c = lines[j]
                # 遇到下一个项目起始行停止
                # EN: Stop at the start line of the next project
                # JA: 次のプロジェクトの開始行で止める
                if _is_project_start(j):
                    break
                if c.startswith("责任描述") or c.startswith("职责"):
                    cur_section = "resp"
                    rest = re.sub(r"^责任描述[：:]?\s*|^职责[：:]?\s*", "", c)
                    if rest:
                        responsibilities += rest + "\n"
                elif c.startswith("项目描述") or c.startswith("项目介绍"):
                    cur_section = "desc"
                    rest = re.sub(r"^项目描述[：:]?\s*|^项目介绍[：:]?\s*", "", c)
                    if rest:
                        description += rest + "\n"
                else:
                    if cur_section == "resp":
                        responsibilities += c + "\n"
                    else:
                        description += c + "\n"
                j += 1
            projects.append(_make_project(project_name, start_ym, end_ym, description, responsibilities))
            i = j
            continue

        # App 格式：项目名一行，下一行是日期
        # EN: App format: the project name on one line, the dates on the next
        # JA: アプリの形式：プロジェクト名が 1 行、次の行が日付
        if i + 1 < len(lines) and app_date_re.match(lines[i + 1]):
            project_name = line
            m_date = app_date_re.match(lines[i + 1])
            start_ym = _format_ym(m_date.group(1))
            end_raw = m_date.group(2)
            end_ym = "" if end_raw in ("至今", "现在", "目前") else _format_ym(end_raw)
            description = ""
            responsibilities = ""
            cur_section = "desc"
            j = i + 2
            while j < len(lines):
                c = lines[j]
                if _is_project_start(j):
                    break
                if c.startswith("责任描述") or c.startswith("职责"):
                    cur_section = "resp"
                    rest = re.sub(r"^责任描述[：:]?\s*|^职责[：:]?\s*", "", c)
                    if rest:
                        responsibilities += rest + "\n"
                elif c.startswith("项目描述") or c.startswith("项目介绍"):
                    cur_section = "desc"
                    rest = re.sub(r"^项目描述[：:]?\s*|^项目介绍[：:]?\s*", "", c)
                    if rest:
                        description += rest + "\n"
                else:
                    if cur_section == "resp":
                        responsibilities += c + "\n"
                    else:
                        description += c + "\n"
                j += 1
            projects.append(_make_project(project_name, start_ym, end_ym, description, responsibilities))
            i = j
            continue

        i += 1

    return projects


# 培训字段标签拆分正则（用于粘连格式兜底）
# EN: Regex for splitting training field labels (fallback for the stuck format)
# JA: 研修のフィールドのラベルを分割する正規表現（くっついた形式の最終手段）
_TRAIN_LABEL_SPLIT_RE = re.compile(
    r"(培训机构[：:]|培训地点[：:]|所获证书[：:]|证书名[：:]|培训描述[：:])"
)

# 描述末尾板块标题残留清理
# EN: Clean leftover section headings at the end of descriptions
# JA: 説明の末尾に残ったセクション見出しを除去する
_TRAILING_SECTION_RE = re.compile(
    r"\s*(证书|语言能力|专业技能|自我评价|教育经历|工作经历|"
    r"项目经历|培训经历|在校学习情况|在校实践经历|活动描述|兴趣爱好)$"
)


def _split_training_fields(raw: str) -> tuple[str, str, str, str]:
    """从粘连文本中拆分培训字段。

    输入如：「日本语 培训机构：日本东京都银星日本语学校培训地点：日本东京所获证书：日本语能力一级 培训描述：...描述内容」
    输出：(training_name, organization, certificate, description)

    EN: Split training fields out of stuck text.

    Input like: "日本语 培训机构：日本东京都银星日本语学校培训地点：日本东京所获证书：日本语能力一级 培训描述：...description" (Japanese, training institution: ..., place: Tokyo, certificate: JLPT level 1, description: ...)
    Output: (training_name, organization, certificate, description)

    JA: くっついたテキストから研修のフィールドを分割する。

    入力の例：「日本语 培训机构：日本东京都银星日本语学校培训地点：日本东京所获证书：日本语能力一级 培训描述：...説明の内容」（日本語・研修機関：…・場所：東京・取得資格：日本語能力 1 級・説明：…）
    出力：(training_name, organization, certificate, description)
    """
    parts = _TRAIN_LABEL_SPLIT_RE.split(raw)
    # parts[0] 是培训名，后续是 [标签, 值, 标签, 值, ...] 交替
    # EN: parts[0] is the training name, followed by alternating [label, value, label, value, ...]
    # JA: parts[0] が研修名で、その後に [ラベル, 値, ラベル, 値, ...] が交互に続く
    training_name = parts[0].strip()
    organization = ""
    certificate = ""
    description = ""

    k = 1
    while k + 1 < len(parts):
        label = parts[k]
        value = parts[k + 1].strip()
        if label.startswith("培训机构"):
            if not organization:
                organization = value
        elif label.startswith("培训地点"):
            pass  # 培训地点不存入输出结构，忽略
            # EN: The training place is not stored in the output structure; ignore it
            # JA: 研修場所は出力構造に保存しないので無視する
        elif label.startswith("所获证书") or label.startswith("证书名"):
            if not certificate:
                certificate = value
        elif label.startswith("培训描述"):
            if not description:
                description = value
        k += 2

    # 清理描述末尾的板块标题残留（如「证书」「语言能力」等）
    # EN: Clean leftover section headings at the end of descriptions (e.g. "证书" (certificates), "语言能力" (language skills))
    # JA: 説明の末尾に残ったセクション見出し（例：「证书」（資格）、「语言能力」（語学力））を除去する
    description = _TRAILING_SECTION_RE.sub("", description.strip())

    return training_name, organization, certificate, description


def _parse_zhilian_training(text: str) -> list[dict[str, Any]]:
    """解析培训经历。

    支持两种格式：
      格式1（App）：日期 培训机构：名称（同一行），上一行为培训名
      格式2（Word）：日期  培训名（首行），后续行：培训机构：/培训地点：/所获证书：/培训描述：
        标签和值可能同行（「培训机构：AOTS」）或分行（「培训机构：\\nAOTS」）

    EN: Parse training history.

    Supports two formats:
      Format 1 (App): date 培训机构：name (training institution:) on the same line, with the training name on the previous line
      Format 2 (Word): date  training name (first line), followed by lines: 培训机构：/培训地点：/所获证书：/培训描述： (institution / place / certificate / description)
        labels and values may be on the same line ("培训机构：AOTS") or on separate lines ("培训机构：\\nAOTS")

    JA: 研修歴を解析する。

    2 つの形式に対応する：
      形式 1（アプリ）：日付 培训机构：名称（研修機関：）が同じ行にあり、前の行が研修名
      形式 2（Word）：日付  研修名（先頭行）、続く行：培训机构：／培训地点：／所获证书：／培训描述：（研修機関・場所・取得資格・説明）
        ラベルと値は同じ行（「培训机构：AOTS」）のことも、別の行（「培训机构：\\nAOTS」）のこともある
    """
    block = _section_block(
        text,
        ["培训经历", "培训经验", "Training"],
        ["语言能力", "技能", "自我评价", "专业技能", "证书", "所获", "教育经历", "项目经历", "工作经历",
         "在校学习情况", "在校实践经历", "活动描述", "兴趣爱好",
         "Language", "Self-Assessment", "Skills", "Certificates", "Awards",
         "Education", "Project", "Work Experience"],
    )
    if not block:
        return []

    trainings: list[dict[str, Any]] = []
    lines = [l.strip() for l in block.splitlines() if l.strip()]

    # 日期范围正则
    # EN: Date-range regex
    # JA: 期間の正規表現
    date_range_re = re.compile(
        r"((?:19|20)\d{2}[./\-]\d{1,2})\s*[\-\u2010-\u2015~～至到]{1,4}\s*"
        r"((?:19|20)\d{2}[./\-]\d{1,2}|至今|现在|目前)"
    )

    i = 0
    while i < len(lines):
        line = lines[i]
        m_date = date_range_re.search(line)
        if m_date:
            start_ym = _format_ym(m_date.group(1))
            end_raw = m_date.group(2)
            end_ym = "" if end_raw in ("至今", "现在", "目前") else _format_ym(end_raw)

            # 培训名：日期后的剩余文本
            # EN: Training name: the remaining text after the dates
            # JA: 研修名：日付の後の残りのテキスト
            training_name = line[m_date.end():].strip()
            organization = ""
            training_location = ""
            certificate = ""
            description = ""

            # 格式1：剩余文本是「培训机构：xxx」，培训名取上一行
            # EN: Format 1: the remaining text is "培训机构：xxx" (training institution: xxx); the training name is taken from the previous line
            # JA: 形式 1：残りのテキストが「培训机构：xxx」（研修機関：xxx）なら、研修名は前の行から取る
            if training_name.startswith("培训机构"):
                org_val = re.sub(r"^培训机构[：:]\s*", "", training_name)
                training_name = lines[i - 1].strip() if i > 0 else ""
                organization = org_val
            elif training_name and any(
                # 格式3（粘连兜底）：training_name 中仍含字段标签时，拆分出各字段
                # （预处理未拆分的极端粘连情况，如「日本语 培训机构：xxx培训描述：yyy」）
                # EN: Format 3 (stuck fallback): when training_name still contains field labels, split out each field
                #     (extreme stuck cases the pre-processing did not split, e.g. "日本语 培训机构：xxx培训描述：yyy")
                # JA: 形式 3（くっつきの最終手段）：training_name にまだフィールドのラベルがあれば、各フィールドを分ける
                #     （前処理で分割できなかった極端なくっつき。例：「日本语 培训机构：xxx培训描述：yyy」）
                lbl in training_name
                for lbl in ("培训机构：", "培训机构:", "培训描述：", "培训描述:",
                            "所获证书：", "所获证书:", "培训地点：", "培训地点:")
            ):
                training_name, organization, certificate, description = (
                    _split_training_fields(training_name)
                )

            # 从下一行找培训机构/培训地点/所获证书/培训描述
            # EN: Look in the next lines for training institution / training place / certificate obtained / training description
            # JA: 次の行から研修機関・研修場所・取得資格・研修の説明を探す
            j = i + 1
            while j < len(lines):
                c = lines[j]
                # 遇到下一个日期范围停止
                # EN: Stop at the next date range
                # JA: 次の期間に達したら止める
                if date_range_re.search(c):
                    break
                # 跳过单独的「证书」噪音行（板块标题残留）
                # EN: Skip a standalone "证书" (certificates) noise line (a leftover section heading)
                # JA: 単独の「证书」（資格）のノイズの行（セクション見出しの残り）をスキップする
                if c == "证书":
                    j += 1
                    continue
                if c.startswith("培训机构"):
                    if not organization:
                        val = re.sub(r"^培训机构[：:]\s*", "", c)
                        if val:
                            organization = val
                        elif j + 1 < len(lines) and not date_range_re.search(lines[j + 1]) and not lines[j + 1].startswith("培训"):
                            organization = lines[j + 1]
                            j += 1
                    j += 1
                    continue
                if c.startswith("培训地点"):
                    val = re.sub(r"^培训地点[：:]\s*", "", c)
                    if val:
                        training_location = val
                    elif j + 1 < len(lines) and not date_range_re.search(lines[j + 1]):
                        training_location = lines[j + 1]
                        j += 1
                    j += 1
                    continue
                if c.startswith("所获证书") or c.startswith("证书名"):
                    val = re.sub(r"^(所获证书|证书名)[：:]\s*", "", c)
                    if val:
                        certificate = val
                    elif j + 1 < len(lines) and not date_range_re.search(lines[j + 1]):
                        certificate = lines[j + 1]
                        j += 1
                    j += 1
                    continue
                if c.startswith("培训描述"):
                    val = re.sub(r"^培训描述[：:]\s*", "", c)
                    if val:
                        description = val
                    # 收集后续描述行
                    # EN: Collect the following description lines
                    # JA: 後続の説明の行を集める
                    k = j + 1
                    while k < len(lines) and not date_range_re.search(lines[k]):
                        nxt = lines[k]
                        if nxt.startswith("培训") or nxt.startswith("所获") or nxt == "证书":
                            break
                        description += "\n" + nxt
                        k += 1
                    j = k
                    continue
                j += 1

            # 清理描述末尾的板块标题残留（如「证书」「语言能力」等）
            # EN: Clean leftover section headings at the end of descriptions (e.g. "证书" (certificates), "语言能力" (language skills))
            # JA: 説明の末尾に残ったセクション見出し（例：「证书」（資格）、「语言能力」（語学力））を除去する
            description = _TRAILING_SECTION_RE.sub("", description.strip())

            trainings.append({
                "sequence_no": len(trainings) + 1,
                "organization_name": organization,
                "training_name": training_name,
                "start_ym": start_ym,
                "end_ym": end_ym,
                "certificate_name": certificate,
                "description": description,
            })
            i = j
        else:
            i += 1

    return trainings


def _parse_zhilian_practice(text: str) -> list[dict[str, Any]]:
    """解析在校实践经历 → 合并到 training_list。

    在校实践经历格式与培训经历类似：
      日期范围  实践单位
      实践描述：
      描述内容

    EN: Parse campus practice experience → merged into training_list.

    The format of campus practice experience is similar to training history:
      date range  practice organisation
      实践描述： (practice description:)
      description content

    JA: 在学中の実践経験を解析する → training_list に統合する。

    在学中の実践経験の形式は研修歴と似ている：
      期間  実践先
      实践描述：（実践の説明：）
      説明の内容
    """
    block = _section_block(
        text,
        ["在校实践经历", "社会实践", "实习经历", "Internship", "Practice"],
        ["语言能力", "技能", "自我评价", "专业技能", "证书", "所获", "教育经历", "项目经历", "工作经历",
         "在校学习情况", "活动描述", "兴趣爱好", "培训经历",
         "Language", "Self-Assessment", "Skills", "Certificates", "Awards",
         "Education", "Project", "Work Experience", "Training"],
    )
    if not block:
        return []

    practices: list[dict[str, Any]] = []
    lines = [l.strip() for l in block.splitlines() if l.strip()]

    date_range_re = re.compile(
        r"((?:19|20)\d{2}[./\-]\d{1,2})\s*[\-\u2010-\u2015~～至到]{1,4}\s*"
        r"((?:19|20)\d{2}[./\-]\d{1,2}|至今|现在|目前)"
    )

    i = 0
    while i < len(lines):
        line = lines[i]
        m_date = date_range_re.search(line)
        if m_date:
            start_ym = _format_ym(m_date.group(1))
            end_raw = m_date.group(2)
            end_ym = "" if end_raw in ("至今", "现在", "目前") else _format_ym(end_raw)

            # 实践单位名：日期后的剩余文本
            # EN: Practice organisation name: the remaining text after the dates
            # JA: 実践先の名前：日付の後の残りのテキスト
            org_name = line[m_date.end():].strip()
            # 去掉时长括号
            # EN: Remove tenure brackets
            # JA: 在職期間の括弧を除く
            org_name = re.sub(r"[（(]\s*\d+年\d+个月\s*[）)]", "", org_name)
            org_name = re.sub(r"[（(]\s*\d+个月\s*[）)]", "", org_name)
            org_name = re.sub(r"[（(]\s*\d+年\s*[）)]", "", org_name)
            org_name = org_name.strip(" 　\t\n-—–*·")

            description = ""

            # 从下一行找实践描述
            # EN: Look in the next lines for the practice description
            # JA: 次の行から実践の説明を探す
            j = i + 1
            while j < len(lines):
                c = lines[j]
                if date_range_re.search(c):
                    break
                if c.startswith("实践描述"):
                    val = re.sub(r"^实践描述[：:]?\s*", "", c)
                    if val:
                        description = val
                    # 收集后续描述行
                    # EN: Collect the following description lines
                    # JA: 後続の説明の行を集める
                    k = j + 1
                    while k < len(lines) and not date_range_re.search(lines[k]):
                        nxt = lines[k]
                        if nxt.startswith("实践"):
                            break
                        description += "\n" + nxt
                        k += 1
                    j = k
                    continue
                j += 1

            # 清理描述末尾的板块标题残留
            # EN: Clean leftover section headings at the end of the description
            # JA: 説明の末尾に残ったセクション見出しを除去する
            description = _TRAILING_SECTION_RE.sub("", description.strip())

            practices.append({
                "sequence_no": 0,  # 合并时重新编号
                # EN: Renumber when merging
                # JA: 統合するときに番号を振り直す
                "organization_name": org_name,
                "training_name": "在校实践经历",
                "start_ym": start_ym,
                "end_ym": end_ym,
                "certificate_name": "",
                "description": description,
            })
            i = j
        else:
            i += 1

    return practices


def _parse_zhilian_languages(text: str, soup: Any) -> list[dict[str, Any]]:
    """解析语言能力。

    App 格式：table 内 英语/日语 读写/听说 等级
    Word 格式：英语：读写能力一般 | 听说能力一般

    EN: Parse language skills.

    App format: in a table, English/Japanese  reading-writing/listening-speaking  level
    Word format: 英语：读写能力一般 | 听说能力一般 (English: reading/writing basic | listening/speaking basic)

    JA: 語学力を解析する。

    アプリの形式：table 内に 英語／日本語 読み書き／聞き話す レベル
    Word の形式：英语：读写能力一般 | 听说能力一般（英語：読み書き普通 | 聞き話す普通）
    """
    languages: list[dict[str, Any]] = []

    # Word 格式
    # EN: Word format
    # JA: Word の形式
    for m in re.finditer(r"(英语|日语|德语|法语|韩语|俄语|西班牙语|意大利语|葡萄牙语|阿拉伯语|普通话|粤语)[：:]\s*([^|\n]+)(?:\|\s*([^|\n]+))?", text):
        lang_name = m.group(1)
        level = (m.group(2) or "").strip()
        if m.group(3):
            level += " | " + m.group(3).strip()
        languages.append({
            "language_name": lang_name,
            "language_level": level,
            "language_certificate": "",
            "language_certificate_time": "",
        })

    # App 格式：从 DOM table 解析
    # EN: App format: parse from the DOM table
    # JA: アプリの形式：DOM の table から解析する
    if not languages and soup is not None:
        lang_header = None
        for tag in soup.find_all(["p", "b", "strong"]):
            if "语言能力" in tag.get_text(strip=True):
                lang_header = tag
                break
        if lang_header:
            tbl = lang_header.find_next("table")
            if tbl:
                languages = _parse_app_language_table(tbl)

    # 去重
    # EN: Dedup
    # JA: 重複排除
    seen = set()
    unique: list[dict[str, Any]] = []
    for l in languages:
        key = l["language_name"]
        if key not in seen:
            seen.add(key)
            unique.append(l)

    return unique


def _parse_app_language_table(tbl: Any) -> list[dict[str, Any]]:
    """解析 App 格式语言能力 table。

    实际 HTML 结构（过滤空单元格后）：
      Row 0: [英语, 日语]              → 语言名称
      Row 1: [读写, 一般, 读写, 精通]  → 每语言占 2 列（类型+等级）
      Row 2: [听说, 一般, 听说, 精通]

    EN: Parse the App-format language skills table.

    Actual HTML structure (after filtering empty cells):
      Row 0: [英语, 日语]              → language names
      Row 1: [读写, 一般, 读写, 精通]  → each language takes 2 columns (type + level)
      Row 2: [听说, 一般, 听说, 精通]

    JA: アプリの形式の語学力の table を解析する。

    実際の HTML の構造（空のセルを除いた後）：
      Row 0: [英语, 日语]              → 言語名
      Row 1: [读写, 一般, 读写, 精通]  → 各言語が 2 列（種類 + レベル）を使う
      Row 2: [听说, 一般, 听说, 精通]
    """
    LANG_NAMES = ("英语", "日语", "德语", "法语", "韩语", "俄语", "普通话", "粤语",
                  "西班牙语", "意大利语", "葡萄牙语", "阿拉伯语")
    TYPE_WORDS = ("读写", "听说", "读写能力", "听说能力")

    languages: list[dict[str, Any]] = []
    rows = tbl.find_all("tr")
    if not rows:
        return languages

    # 第一行：语言名称（过滤空单元格）
    # EN: First row: language names (filter empty cells)
    # JA: 1 行目：言語名（空のセルを除外）
    header_cells = [c.get_text(strip=True) for c in rows[0].find_all(["td", "th"])]
    header_cells = [c for c in header_cells if c]
    lang_names: list[str] = [c for c in header_cells if c in LANG_NAMES]

    if not lang_names:
        return languages

    # 按语言收集 类型+等级 对：lang_pairs[i] = ["读写一般", "听说一般", ...]
    # EN: Collect type + level pairs per language: lang_pairs[i] = ["读写一般", "听说一般", ...] (reading/writing basic, listening/speaking basic, ...)
    # JA: 言語ごとに 種類 + レベル のペアを集める：lang_pairs[i] = ["读写一般", "听说一般", ...]（読み書き普通・聞き話す普通…）
    lang_pairs: dict[int, list[str]] = {i: [] for i in range(len(lang_names))}

    for row in rows[1:]:
        cells = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
        cells = [c for c in cells if c]  # 过滤空单元格
        # EN: Filter empty cells
        # JA: 空のセルを除外する
        if not cells:
            continue

        # 每语言占 2 列：类型 + 等级
        # EN: Each language takes 2 columns: type + level
        # JA: 各言語は 2 列を使う：種類 + レベル
        for i in range(len(lang_names)):
            base = 2 * i
            if base + 1 < len(cells):
                type_val = cells[base]
                level_val = cells[base + 1]
                if type_val in TYPE_WORDS and level_val:
                    lang_pairs[i].append(f"{type_val}{level_val}")

    for idx, name in enumerate(lang_names):
        level_str = " ".join(lang_pairs.get(idx, []))
        languages.append({
            "language_name": name,
            "language_level": level_str,
            "language_certificate": "",
            "language_certificate_time": "",
        })

    return languages


def _parse_zhilian_certificates(text: str, soup: Any) -> list[dict[str, Any]]:
    """解析证书。

    支持两种格式：
      App 格式：所获证书 table，含证书名 + 获得时间
      Word 格式：「YYYY.MM  证书名」每行一个，后接可选「证书说明：」段落

    EN: Parse certificates.

    Supports two formats:
      App format: a 所获证书 (certificates obtained) table with certificate name + date obtained
      Word format: "YYYY.MM  certificate name", one per line, optionally followed by a "证书说明：" (certificate notes:) paragraph

    JA: 資格を解析する。

    2 つの形式に対応する：
      アプリの形式：所获证书（取得資格）の table で、資格名 + 取得日
      Word の形式：「YYYY.MM  資格名」が 1 行に 1 つ、その後に任意で「证书说明：」（資格の説明：）の段落
    """
    certificates: list[dict[str, Any]] = []

    if soup is not None:
        cert_header = None
        for tag in soup.find_all(["p", "b", "strong"]):
            t = tag.get_text(strip=True)
            if ("所获" in t and "证书" in t) or t == "证书" or "Awards" in t or "Certificates" in t:
                cert_header = tag
                break
        if cert_header:
            tbl = cert_header.find_next("table")
            if tbl:
                app_certs = _parse_app_certificate_table(tbl)
                # 验证：App 格式证书名不应以日期开头
                # （否则是 Word 格式单列表被误判，应改用文本解析）
                # EN: Validate: App-format certificate names should not start with a date
                #     (otherwise it is a misjudged single-column Word-format table, and text parsing should be used instead)
                # JA: 検証：アプリの形式の資格名は日付で始まってはならない
                #     （そうであれば Word の形式の 1 列の表を誤判定したもので、テキストの解析を使うべき）
                valid = all(
                    not re.match(r"^\d{4}[./\-年]", c.get("certificate_name", ""))
                    for c in app_certs
                )
                if valid:
                    certificates = app_certs

    # Word 格式：从文本提取「YYYY.MM  证书名」
    # EN: Word format: extract "YYYY.MM  certificate name" from the text
    # JA: Word の形式：テキストから「YYYY.MM  資格名」を抽出する
    if not certificates:
        block = _section_block(
            text,
            ["证书", "所获证书", "所获", "Certificates", "Awards"],
            ["语言能力", "专业技能", "自我评价", "培训经历", "项目经历", "教育经历", "工作经历",
             "特长", "职业目标", "在校学习情况", "在校实践经历", "活动描述", "兴趣爱好",
             "Language", "Skills", "Self-Assessment", "Training", "Project", "Education", "Work Experience"],
        )
        if block:
            lines = [l.strip() for l in block.splitlines() if l.strip()]
            # 预处理：将「日期单独一行」与下一行合并
            # （如「2010.02\n日语一级证书」→「2010.02 日语一级证书」）
            # EN: Pre-process: merge "a date on its own line" with the next line
            #     (e.g. "2010.02\n日语一级证书" → "2010.02 日语一级证书")
            # JA: 前処理：「単独の行にある日付」を次の行と結合する
            #     （例：「2010.02\n日语一级证书」→「2010.02 日语一级证书」）
            merged_lines = []
            idx = 0
            while idx < len(lines):
                line = lines[idx]
                if re.match(r"^((?:19|20)\d{2})[./\-年](\d{1,2})月?$", line) and idx + 1 < len(lines):
                    merged_lines.append(f"{line} {lines[idx + 1]}")
                    idx += 2
                else:
                    merged_lines.append(line)
                    idx += 1
            lines = merged_lines
            for line in lines:
                # 跳过日期范围行（如「2012.03 - 2012.04  重庆科学技术委员会」），
                # 这些是实践/工作经历不是证书
                # EN: Skip date-range lines (e.g. "2012.03 - 2012.04  重庆科学技术委员会");
                #     these are practice/work experiences, not certificates
                # JA: 期間の行（例：「2012.03 - 2012.04  重庆科学技术委员会」）はスキップする。
                #     これらは実践・職歴であり資格ではない
                if re.search(r"^\d{4}[./\-年]\d{1,2}\s*[\-\u2010-\u2015~～至到]", line):
                    continue
                # 「YYYY.MM  证书名」或「YYYY年MM月  证书名」
                # EN: "YYYY.MM  certificate name" or "YYYY年MM月  certificate name"
                # JA: 「YYYY.MM  資格名」または「YYYY年MM月  資格名」
                m = re.match(
                    r"((?:19|20)\d{2})[./\-年](\d{1,2})月?\s+(.+)",
                    line,
                )
                if m:
                    cert_time = f"{m.group(1)}年{int(m.group(2)):02d}月01日"
                    cert_name = m.group(3).strip()
                    # 跳过「证书说明」等非证书名
                    # 跳过证书名本身是日期的（两个日期行被合并的情况）
                    # EN: Skip non-certificate names such as "证书说明" (certificate notes)
                    #     Skip certificate names that are themselves dates (when two date lines were merged)
                    # JA: 「证书说明」（資格の説明）などの資格名でないものはスキップする
                    #     資格名そのものが日付のもの（2 つの日付行が結合された場合）はスキップする
                    if (cert_name
                            and cert_name not in ("证书说明", "证书名", "分数")
                            and len(cert_name) < 80
                            and not re.match(r"^\d{4}[./\-年]\d{1,2}", cert_name)):
                        certificates.append({
                            "certificate_name": cert_name,
                            "certificate_type": "证书",
                            "certificate_time": cert_time,
                        })

    # 兜底：从全文提取「YYYY年MM月获得 证书名」
    # EN: Fallback: extract "YYYY年MM月获得 certificate name" (obtained in ...) from the full text
    # JA: 最終手段：全文から「YYYY年MM月获得 資格名」（〜年〜月に取得）を抽出する
    if not certificates:
        for m in re.finditer(r"([^\n]+?)\n(\d{4}年\d{1,2}月(?:获得|取得))", text):
            cert_name = m.group(1).strip()
            time_str = m.group(2).replace("获得", "").replace("取得", "").strip()
            if cert_name and len(cert_name) < 60:
                certificates.append({
                    "certificate_name": cert_name,
                    "certificate_type": "证书",
                    "certificate_time": _format_ym(time_str),
                })

    return certificates


def _parse_app_certificate_table(tbl: Any) -> list[dict[str, Any]]:
    """解析 App 格式证书 table。

    结构：
      tr[0]: 证书名1 | 证书名2 | 证书名3
      tr[1]: 时间1 | 时间2 | 时间3

    EN: Parse the App-format certificate table.

    Structure:
      tr[0]: certificate 1 | certificate 2 | certificate 3
      tr[1]: date 1 | date 2 | date 3

    JA: アプリの形式の資格の table を解析する。

    構造：
      tr[0]: 資格名 1 | 資格名 2 | 資格名 3
      tr[1]: 日付 1 | 日付 2 | 日付 3
    """
    certificates: list[dict[str, Any]] = []
    rows = tbl.find_all("tr")
    if len(rows) < 2:
        return certificates

    # 第一行：证书名
    # EN: First line: certificate name
    # JA: 1 行目：資格名
    name_cells = rows[0].find_all(["td", "th"])
    names = [c.get_text(strip=True) for c in name_cells if c.get_text(strip=True)]

    # 第二行：获得时间
    # EN: Second line: date obtained
    # JA: 2 行目：取得日
    time_cells = rows[1].find_all(["td", "th"])
    times = [c.get_text(strip=True) for c in time_cells if c.get_text(strip=True)]

    for idx, name in enumerate(names):
        time_str = times[idx] if idx < len(times) else ""
        # 提取日期
        # EN: Extract the date
        # JA: 日付を抽出する
        m_date = re.search(r"(\d{4})年(\d{1,2})月", time_str)
        cert_time = f"{m_date.group(1)}年{int(m_date.group(2)):02d}月01日" if m_date else ""
        certificates.append({
            "certificate_name": name,
            "certificate_type": "证书",
            "certificate_time": cert_time,
        })

    return certificates


def _parse_zhilian_self_evaluation(text: str) -> list[dict[str, Any]]:
    """解析自我评价 → communication_list。

    EN: Parse self-assessment → communication_list.

    JA: 自己評価を解析する → communication_list。
    """
    block = _section_block(
        text,
        ["自我评价", "自我描述", "个人评价", "Self"],
        ["工作经历", "教育经历", "项目经历", "语言能力", "培训经历", "专业技能", "证书", "所获",
         "在校学习情况", "在校实践经历", "活动描述", "兴趣爱好",
         "Work Experience", "Education", "Project", "Language", "Training", "Skills", "Certificates", "Awards"],
    )
    if not block:
        return []

    # 清理多余空行
    # EN: Clean extra empty lines
    # JA: 余分な空行を除く
    content = re.sub(r"\n{2,}", "\n", block).strip()
    if not content:
        return []

    return [{
        "communicate_time": "",
        "communicate_content": content,
    }]


def _parse_zhilian_skills(text: str) -> list[dict[str, Any]]:
    """解析专业技能。

    支持格式：
      App 格式：table 内技能名 + 熟练度
      Word 格式：「技能名：等级 | 时长」每行一条（如「计算机／IT：良好 | 36个月」）

    EN: Parse professional skills.

    Supported formats:
      App format: skill name + proficiency in a table
      Word format: "skill name: level | duration", one per line (e.g. "计算机／IT：良好 | 36个月")

    JA: 専門スキルを解析する。

    対応する形式：
      アプリの形式：table 内のスキル名 + 習熟度
      Word の形式：「スキル名：レベル | 期間」が 1 行に 1 件（例：「计算机／IT：良好 | 36个月」）
    """
    skills: list[dict[str, Any]] = []

    block = _section_block(
        text,
        ["专业技能", "技能特长", "Professional Skills", "Skills"],
        ["证书", "所获", "自我评价", "语言能力", "工作经历", "教育经历", "项目经历", "培训经历",
         "特长", "职业目标", "特长职业目标", "求职意向",
         "在校学习情况", "在校实践经历", "活动描述", "兴趣爱好",
         "Certificates", "Awards", "Self-Assessment", "Language", "Work Experience", "Education", "Project", "Training"],
    )
    if not block:
        # 兜底：扫描全文「技能名称：xxx  技能水平：yyy」格式
        # （部分简历使用「语言/技能/证书」合并板块，无法被 section_block 截取）
        # EN: Fallback: scan the full text for the format "技能名称：xxx  技能水平：yyy" (skill name / skill level)
        #     (some résumés use a combined "language/skills/certificates" section that section_block cannot cut out)
        # JA: 最終手段：全文から「技能名称：xxx  技能水平：yyy」（スキル名・スキルレベル）の形式をスキャンする
        #     （「語学／スキル／資格」をまとめた欄を使う履歴書もあり、section_block では切り出せない）
        for m in re.finditer(
            r"技能名称[：:]\s*(.+?)\s*技能水平[：:]\s*(.+?)(?:\n|$)",
            text,
        ):
            sname = m.group(1).strip()
            slevel = m.group(2).strip()
            if sname:
                skills.append({"skill_name": sname[:100], "skill_level": slevel})
        return skills

    # 等级关键词
    # EN: Level keywords
    # JA: レベルのキーワード
    level_keywords = ("精通", "熟练", "良好", "一般", "掌握", "入门", "初级", "中级", "高级", "专家")

    lines = [l.strip() for l in block.splitlines() if l.strip()]
    for line in lines:
        # 跳过纯等级行
        # EN: Skip pure level lines
        # JA: レベルだけの行をスキップする
        if line in ("熟练", "精通", "良好", "一般", "掌握", "使用1个月", "使用3个月", "使用6个月", "使用12个月", "使用24个月"):
            continue
        # 跳过空行或分隔符
        # EN: Skip empty lines or separators
        # JA: 空行や区切りをスキップする
        if not line or line == "|":
            continue
        # 跳过章节标题/非技能行
        # EN: Skip section headings / non-skill lines
        # JA: 章見出し・スキルでない行をスキップする
        if line in ("专业技能", "技能特长", "技能", "特长", "职业目标", "特长职业目标"):
            continue

        skill_name = line
        skill_level = ""

        # App 格式：「技能名称：xxx\t技能水平：yyy 附加」
        # EN: App format: "技能名称：xxx\t技能水平：yyy extra"
        # JA: アプリの形式：「技能名称：xxx\t技能水平：yyy 付記」
        m_app = re.match(r"^技能名称[：:]\s*(.+?)\s*技能水平[：:]\s*(.+)$", line)
        if m_app:
            skill_name = m_app.group(1).strip()
            skill_level = m_app.group(2).strip()
        else:
            # Word 格式：「技能名：等级 | 时长」
            # 例：计算机／IT：良好 | 36个月 / 日语翻译：熟练 | 24个月
            # EN: Word format: "skill name: level | duration"
            #     e.g.: 计算机／IT：良好 | 36个月 / 日语翻译：熟练 | 24个月
            # JA: Word の形式：「スキル名：レベル | 期間」
            #     例：计算机／IT：良好 | 36个月 / 日语翻译：熟练 | 24个月
            m_colon = re.match(r"^(.+?)[：:]\s*([^|]+?)(?:\s*\|.*)?$", line)
            if m_colon:
                cand_name = m_colon.group(1).strip()
                cand_level = m_colon.group(2).strip()
                # 确认 cand_level 是等级词（避免误拆「http://xxx」之类）
                # EN: Confirm cand_level is a level word (to avoid mis-splitting things like "http://xxx")
                # JA: cand_level がレベルの語であることを確認する（「http://xxx」のようなものを誤って分割しないため）
                if any(lk in cand_level for lk in level_keywords) or re.fullmatch(r"[\u4e00-\u9fff]{1,6}", cand_level):
                    skill_name = cand_name
                    skill_level = cand_level

        # 清理 skill_name 末尾残留的时长/等级
        # EN: Clean leftover duration/level at the end of skill_name
        # JA: skill_name の末尾に残った期間・レベルを除く
        skill_name = re.sub(r"\s*[|｜].*$", "", skill_name).strip()

        # 跳过明显非技能的描述句（含句号、逗号且过长）
        # EN: Skip descriptive sentences that are obviously not skills (containing full stops and commas, and too long)
        # JA: 明らかにスキルではない説明文（句点・読点を含み長すぎるもの）をスキップする
        if len(skill_name) > 50 and ("。" in skill_name or "，" in skill_name):
            continue
        # 跳过个人目标/描述类（以动词开头且过长）
        # EN: Skip personal goals/descriptions (starting with a verb and too long)
        # JA: 個人の目標・説明の類（動詞で始まり長すぎるもの）をスキップする
        if len(skill_name) > 20 and re.match(r"^(根据|通过|具备|负责|参与|制定|完成)", skill_name):
            continue

        if skill_name:
            skills.append({
                "skill_name": skill_name[:100],
                "skill_level": skill_level,
            })

    return skills


# =============================================================================
# 简历语言检测
# =============================================================================
# EN: =============================================================================
#     Résumé language detection
#     =============================================================================
# JA: =============================================================================
#     履歴書の言語の検出
#     =============================================================================

def _detect_resume_language(text: str) -> str:
    """检测简历正文真实语言。

    注意：英文简历的 HTML 头部含中文元数据（源文件路径、简历下载时间等），
    需要适当放宽 zh_chars 阈值以正确识别英文简历。

    EN: Detect the real language of the résumé body.

    Note: the HTML header of English résumés contains Chinese metadata (source file path, résumé download time, etc.),
    so the zh_chars threshold must be relaxed appropriately to recognise English résumés correctly.

    JA: 履歴書の本文の実際の言語を検出する。

    注意：英語の履歴書の HTML ヘッダーには中国語のメタデータ（ソースファイルのパス・履歴書のダウンロード日時など）があるため、
    英語の履歴書を正しく識別できるよう zh_chars のしきい値を適度に緩める必要がある。
    """
    if not text:
        return "zh"
    # 日文假名检测
    # EN: Japanese kana detection
    # JA: 日本語のかなの検出
    hira = len(re.findall(r"[\u3040-\u309f]", text))
    kata = len(re.findall(r"[\u30a0-\u30ff]", text))
    kana_count = hira + kata
    if kana_count >= 5:
        return "jp"
    zh_chars = len(re.findall(r"[\u4e00-\u9fff]", text))
    en_words = len(re.findall(r"\b[A-Za-z]{2,}\b", text))
    # 英文简历：英文单词较多，中文字符数 < 100（中文元数据约 50-60 字）
    # EN: English résumé: many English words, Chinese characters < 100 (Chinese metadata is about 50-60 characters)
    # JA: 英語の履歴書：英単語が多く、漢字が 100 文字未満（中国語のメタデータは約 50〜60 文字）
    if en_words > 50 and zh_chars < 100:
        return "en"
    if zh_chars >= 10:
        return "zh"
    return "en" if en_words > zh_chars else "zh"


# =============================================================================
# 主组装函数
# =============================================================================
# EN: =============================================================================
#     Main assembly function
#     =============================================================================
# JA: =============================================================================
#     メインの組み立て関数
#     =============================================================================

def _build_empty_current_info() -> dict[str, Any]:
    return {
        "company_name": "", "company_employees": "", "company_industry": "",
        "position": "", "position_type": "", "position_salary": "",
        "position_dept": "", "position_report_to": "", "position_subordinate": "",
        "employment_type": "全职", "annual_salary_min": "", "annual_salary_max": "",
        "status": "", "position_start": "", "position_resigned": "",
    }


def _build_empty_education_info() -> dict[str, Any]:
    return {
        "school_name": "", "school_major_name": "", "school_degree_type": "",
        "school_degree_rank": "", "school_education_type": "",
        "school_start_ym": "", "school_end_ym": "",
    }


def build_record_from_html(
    html_path: Path,
    parser: CodexGeminiHtmlSchemaParser,
    classifier: DocumentClassifier,
) -> tuple[dict[str, Any] | None, str]:
    try:
        html_text = read_html_text(html_path)
    except Exception as exc:
        return None, f"read_error:{exc}"

    text = plain_text(html_text)
    if len(text) < 10:
        return None, "empty_text"

    # 预处理粘连文本：在板块标题/字段标签前插入换行，使现有解析器能处理
    # 单 <p> 标签内多字段粘连的变形格式（如「期望工作地区：...期望月薪：...自我评价」全粘在一行）
    # EN: Pre-process stuck text: insert line breaks before section headings/field labels, so the existing parsers can handle
    #     variants where several fields are stuck in a single <p> tag (e.g. "期望工作地区：...期望月薪：...自我评价" all on one line)
    # JA: くっついたテキストを前処理する：セクション見出し・フィールドのラベルの前に改行を入れ、既存のパーサーが
    #     1 つの <p> タグに複数のフィールドがくっついた変形の形式（例：「期望工作地区：...期望月薪：...自我评价」がすべて 1 行）を処理できるようにする
    text = _preprocess_glued_text(text)

    try:
        classification = classifier.classify(text, filename=html_path.name)
    except Exception:
        classification = type("C", (), {"document_type": "ambiguous_resume", "reason": "classifier_exception"})()

    if classification.document_type not in {"resume", "ambiguous_resume"}:
        return None, f"non_resume:{classification.document_type}"

    fake_source_path = str(html_path.resolve())
    try:
        parsed = parser.parse(html_text, filename=html_path.name, source_path=fake_source_path)
    except Exception as exc:
        return None, f"parser_error:{exc}"

    structured_data = parsed

    # 准备 DOM（用于工作经历等板块解析）
    # EN: Prepare the DOM (used for parsing work history and other sections)
    # JA: DOM を準備する（職歴などのセクションの解析に使う）
    soup = BeautifulSoup(html_text, "html.parser") if BeautifulSoup is not None else None

    # 1. 智联专属解析
    # EN: 1. Zhaopin-specific parsing
    # JA: 1. Zhaopin 専用の解析
    zhilian_name = _extract_zhilian_name(text, html_path.name)
    base_info_line = _parse_base_info_line(text)
    zhilian_works = _parse_zhilian_work_experiences(soup, text)
    zhilian_edus = _parse_zhilian_education(text)
    zhilian_projects = _parse_zhilian_projects(text)
    zhilian_trainings = _parse_zhilian_training(text)
    # 在校实践经历合并到 training_list
    # EN: Merge campus practice experience into training_list
    # JA: 在学中の実践経験を training_list に統合する
    zhilian_practices = _parse_zhilian_practice(text)
    if zhilian_practices:
        zhilian_trainings.extend(zhilian_practices)
        for idx, t in enumerate(zhilian_trainings):
            t["sequence_no"] = idx + 1
    zhilian_languages = _parse_zhilian_languages(text, soup)
    zhilian_certificates = _parse_zhilian_certificates(text, soup)
    zhilian_expected = _parse_zhilian_expected_info(text)
    zhilian_communication = _parse_zhilian_self_evaluation(text)
    zhilian_skills = _parse_zhilian_skills(text)

    # 教育经历归一化 rank
    # EN: Normalise the rank of education history
    # JA: 学歴の rank を正規化する
    if zhilian_edus:
        zhilian_edus = normalize_education_list(zhilian_edus)

    # 2. 检测简历真实语言
    # EN: 2. Detect the résumé's real language
    # JA: 2. 履歴書の実際の言語を検出する
    real_lang = _detect_resume_language(text)
    resumes = structured_data.get("resumes") or []

    # 3. 构建中文主版本 resumes[0]
    # EN: 3. Build the Chinese primary version resumes[0]
    # JA: 3. 中国語主版 resumes[0] を組み立てる
    if resumes:
        # 已有 resumes，取第一个作为基础
        # EN: resumes already exist; take the first as the base
        # JA: すでに resumes があるので、最初のものを基礎とする
        zh_resume = resumes[0]
        zh_resume["resume_language"] = "zh"
    else:
        zh_resume = {
            "resume_language": "zh",
            "base_info": {},
            "expected_info": [],
            "work_experiences": [],
            "education_list": [],
            "certificate_list": [],
            "language_list": [],
            "skills_list": [],
            "training_list": [],
            "project_list": [],
            "communication_list": [],
        }
        resumes = [zh_resume]
        structured_data["resumes"] = resumes

    # 4. 填充智联专属解析结果到 zh_resume
    # base_info
    # EN: 4. Fill the Zhaopin-specific parse results into zh_resume
    #     base_info
    # JA: 4. Zhaopin 専用の解析結果を zh_resume に入れる
    #     base_info
    base_info = zh_resume.get("base_info") or {}
    if zhilian_name:
        base_info["full_name"] = zhilian_name
    if base_info_line:
        if base_info_line.get("gender"):
            base_info["gender"] = base_info_line["gender"]
        if base_info_line.get("age"):
            base_info["age"] = base_info_line["age"]
        if base_info_line.get("birth_date"):
            base_info["birth_date"] = base_info_line["birth_date"]
        if base_info_line.get("birth_year"):
            base_info["birth_year"] = base_info_line["birth_year"]
        if base_info_line.get("marital_status"):
            base_info["marital_status"] = base_info_line["marital_status"]
    base_info["platform_from"] = ZHILIAN_PLATFORM
    # 提取联系方式
    # EN: Extract contact details
    # JA: 連絡先を抽出する
    phone = _extract_phone(text)
    email = _extract_email(text)
    if phone:
        base_info["phone"] = phone
    if email:
        base_info["email"] = email
    address = _extract_address(text)
    if address:
        base_info["address"] = address
    household = _extract_household(text)
    if household:
        base_info["household_registration"] = household

    # 提取平台简历 ID（从文件名 hash 前 12 位或正文 ID）
    # EN: Extract the platform résumé ID (from the first 12 characters of the file-name hash or the ID in the body)
    # JA: プラットフォームの履歴書 ID を抽出する（ファイル名のハッシュの先頭 12 文字か本文中の ID から）
    m_rid = re.search(r"__([0-9a-fA-F]{12})\.html$", html_path.name)
    platform_resume_id = m_rid.group(1) if m_rid else ""
    # 也尝试从正文提取智联 ID
    # EN: Also try extracting the Zhaopin ID from the body
    # JA: 本文から Zhaopin の ID の抽出も試みる
    if not platform_resume_id:
        m_id = re.search(r"ID[：:]\s*([A-Za-z0-9]+)", text)
        if m_id:
            platform_resume_id = m_id.group(1)[:50]
    base_info["platform_resume_id"] = platform_resume_id

    # 确保所有标准字段存在
    # EN: Make sure all standard fields exist
    # JA: すべての標準フィールドが存在するようにする
    for k in ("full_name", "gender", "age", "birth_date", "birth_year", "marital_status",
              "children_status", "political_status", "height_cm", "weight_kg",
              "household_registration", "address", "postal_code", "platform_from",
              "platform_resume_id", "phone", "email", "city", "nationality", "pr"):
        base_info.setdefault(k, "")

    zh_resume["base_info"] = base_info

    # 挂载各列表
    # 中文简历：始终优先使用 zhilian 专属解析结果（更精准）
    # 英文简历：仅在 base parser 为空时使用 zhilian 结果（base parser 对英文更可靠）
    # EN: Attach each list
    #     Chinese résumés: always prefer the zhilian-specific parse results (more precise)
    #     English résumés: use the zhilian results only when the base parser is empty (the base parser is more reliable for English)
    # JA: 各リストを取り付ける
    #     中国語の履歴書：常に zhilian 専用の解析結果を優先する（より正確）
    #     英語の履歴書：base parser が空の場合だけ zhilian の結果を使う（英語には base parser の方が信頼できる）
    prefer_zhilian = (real_lang == "zh")

    def _should_override(zhilian_list: list, base_key: str) -> bool:
        if not zhilian_list:
            return False
        if prefer_zhilian:
            return True  # 中文：zhilian 非空即覆盖
            # EN: Chinese: overwrite whenever zhilian is non-empty
            # JA: 中国語：zhilian が空でなければ上書きする
        base = zh_resume.get(base_key) or []
        return not base  # 英文：仅 base 为空时覆盖
        # EN: English: overwrite only when base is empty
        # JA: 英語：base が空の場合だけ上書きする

    if zhilian_expected:
        zh_resume["expected_info"] = zhilian_expected
    if _should_override(zhilian_works, "work_experiences"):
        zh_resume["work_experiences"] = zhilian_works
    if _should_override(zhilian_edus, "education_list"):
        zh_resume["education_list"] = zhilian_edus
    if _should_override(zhilian_certificates, "certificate_list"):
        zh_resume["certificate_list"] = zhilian_certificates
    if _should_override(zhilian_languages, "language_list"):
        zh_resume["language_list"] = zhilian_languages
    if _should_override(zhilian_skills, "skills_list"):
        zh_resume["skills_list"] = zhilian_skills
    if _should_override(zhilian_trainings, "training_list"):
        zh_resume["training_list"] = zhilian_trainings
    if _should_override(zhilian_projects, "project_list"):
        zh_resume["project_list"] = zhilian_projects
    if zhilian_communication:
        zh_resume["communication_list"] = zhilian_communication

    # 兜底补齐列表字段
    # EN: Fallback completion of list fields
    # JA: リストのフィールドを最終手段で補う
    zh_resume.setdefault("expected_info", [])
    zh_resume.setdefault("work_experiences", [])
    zh_resume.setdefault("education_list", [])
    zh_resume.setdefault("certificate_list", [])
    zh_resume.setdefault("language_list", [])
    zh_resume.setdefault("skills_list", [])
    zh_resume.setdefault("training_list", [])
    zh_resume.setdefault("project_list", [])
    zh_resume.setdefault("communication_list", [])

    # 后处理：清理 work_experiences 中的公司名称
    # （LLM 解析器可能遗留 \xa0、时长括号 (N年M个月)、\x07 字段分隔符等，
    #   尤其在含日文内容的中文简历被误判为 jp 语言时 zhilian 解析结果未覆盖）
    # EN: Post-processing: clean company names in work_experiences
    #     (the LLM parser may leave \xa0, tenure brackets (N年M个月), \x07 field separators, etc.,
    #       especially when a Chinese résumé with Japanese content was misjudged as jp and the zhilian results did not override it)
    # JA: 後処理：work_experiences の会社名を整理する
    #     （LLM のパーサーは \xa0、在職期間の括弧 (N年M个月)、\x07 のフィールド区切りなどを残すことがある。
    #       特に日本語の内容を含む中国語の履歴書が jp と誤判定され、zhilian の結果で上書きされなかった場合）
    for w in zh_resume.get("work_experiences", []):
        cn = w.get("company_name", "")
        if cn:
            w["company_name"] = _clean_company_name(cn)

    # 后处理：清理 certificate_list 中非证书条目
    # （base parser 可能在校实践经历/实践描述等误判为证书）
    # EN: Post-processing: clean non-certificate entries in certificate_list
    #     (the base parser may misjudge campus practice experience / practice descriptions as certificates)
    # JA: 後処理：certificate_list の資格でない項目を除去する
    #     （base parser は在学中の実践経験・実践の説明などを資格と誤判定することがある）
    _NON_CERT_NAMES = {"在校实践经历", "在校学习情况", "活动描述", "兴趣爱好", "社会实践",
                       "社会活动", "特长职业目标", "职业目标", "自我评价", "所获证书",
                       "实践描述：", "实践描述", "证书说明：", "证书说明", "证书名",
                       "工作描述：", "工作描述", "分数", "证书", "培训经历", "项目经历"}
    _NON_CERT_KEYWORDS = ("实践描述", "工作描述", "项目描述", "责任描述", "培训描述",
                          "奖项描述", "活动描述")
    raw_certs = zh_resume.get("certificate_list") or []
    cleaned_certs: list[dict[str, Any]] = []
    for c in raw_certs:
        cname = (c.get("certificate_name") or "").strip()
        if not cname:
            continue
        if cname in _NON_CERT_NAMES:
            continue
        if any(kw in cname for kw in _NON_CERT_KEYWORDS):
            continue
        if cname.startswith("- "):
            continue
        if re.search(r"^\d{4}[./\-年]\d{1,2}\s*[\-\u2010-\u2015~～至到]", cname):
            continue
        cleaned_certs.append(c)
    zh_resume["certificate_list"] = cleaned_certs

    # 后处理：清理 skills_list 中明显非技能的条目
    # （base parser 可能将奖项/描述误判为技能）
    # EN: Post-processing: clean entries in skills_list that are obviously not skills
    #     (the base parser may misjudge awards/descriptions as skills)
    # JA: 後処理：skills_list の明らかにスキルでない項目を除去する
    #     （base parser は受賞・説明をスキルと誤判定することがある）
    _PLATFORM_NAMES = {"智联招聘", "前程无忧", "猎聘", "简历", "未知", "扫码联系TA"}
    _MACRO_KEYWORDS = ("INCLUDEPICTURE", "HYPERLINK", "MERGEFORMAT", "mailto:", "http://", "https://", "ftp://")
    raw_skills = zh_resume.get("skills_list") or []
    cleaned_skills: list[dict[str, Any]] = []
    for s in raw_skills:
        sname = (s.get("skill_name") or "").strip()
        if not sname:
            continue
        # 跳过以年份开头的（奖项/证书描述，如「2015年3月获得...」）
        # EN: Skip those starting with a year (award/certificate descriptions, e.g. "2015年3月获得..." (obtained in March 2015 ...))
        # JA: 年で始まるもの（受賞・資格の説明。例：「2015年3月获得...」（2015 年 3 月に取得…））はスキップする
        if re.match(r"^\d{4}年", sname):
            continue
        # 跳过过长的描述句（含句号/逗号且超过 40 字）
        # EN: Skip overly long descriptive sentences (containing full stops/commas and over 40 characters)
        # JA: 長すぎる説明文（句点・読点を含み 40 文字超）はスキップする
        if len(sname) > 40 and ("。" in sname or "，" in sname or "获得" in sname):
            continue
        # 跳过平台名（智联招聘、前程无忧等）
        # EN: Skip platform names (智联招聘 (Zhaopin), 前程无忧 (51job), etc.)
        # JA: プラットフォーム名（智联招聘（Zhaopin）、前程无忧（51job）など）をスキップする
        if sname in _PLATFORM_NAMES:
            continue
        # 跳过 Word 宏残留/URL（INCLUDEPICTURE、HYPERLINK、mailto:、http:// 等）
        # EN: Skip Word macro leftovers / URLs (INCLUDEPICTURE, HYPERLINK, mailto:, http://, etc.)
        # JA: Word マクロの残骸・URL（INCLUDEPICTURE、HYPERLINK、mailto:、http:// など）をスキップする
        if any(kw in sname for kw in _MACRO_KEYWORDS):
            continue
        cleaned_skills.append(s)
    zh_resume["skills_list"] = cleaned_skills

    # 确保所有 work_experiences 包含 position_achievements
    # EN: Make sure all work_experiences include position_achievements
    # JA: すべての work_experiences に position_achievements が含まれるようにする
    for w in zh_resume.get("work_experiences") or []:
        w.setdefault("position_achievements", "")

    structured_data["resumes"] = resumes

    # 5. 外文简历处理：若真实语言非 zh，将原始版本放到 resumes[1]
    # EN: 5. Foreign-language résumé handling: if the real language is not zh, put the original version into resumes[1]
    # JA: 5. 外国語の履歴書の処理：実際の言語が zh でなければ、元の版を resumes[1] に置く
    if real_lang in ("en", "jp") and len(resumes) == 1:
        foreign_resume = copy.deepcopy(zh_resume)
        foreign_resume["resume_language"] = real_lang
        resumes.append(foreign_resume)

    # 6. 基于 resumes[0]（中文主版本）重构顶层字段
    # EN: 6. Rebuild the top-level fields based on resumes[0] (the Chinese primary version)
    # JA: 6. resumes[0]（中国語主版）に基づいてトップレベルのフィールドを再構築する
    r0 = resumes[0]
    r0_base = r0.get("base_info") or {}
    structured_data["base_info"] = dict(r0_base)

    # 顶层 expected_info 同步
    # EN: Sync the top-level expected_info
    # JA: トップレベルの expected_info を同期する
    r0_expected = r0.get("expected_info") or []
    structured_data["expected_info"] = copy.deepcopy(r0_expected) if r0_expected else []

    # 顶层 education_info：取 rank 最高的一条
    # EN: Top-level education_info: take the entry with the highest rank
    # JA: トップレベルの education_info：rank が最も高い 1 件を取る
    r0_edus = r0.get("education_list") or []
    if r0_edus:
        top_edu = max(r0_edus, key=lambda e: int(e.get("school_degree_rank", "1") or "1"))
        structured_data["education_info"] = {
            "school_name": top_edu.get("school_name", ""),
            "school_major_name": top_edu.get("school_major_name", ""),
            "school_degree_type": top_edu.get("school_degree_type", ""),
            "school_degree_rank": top_edu.get("school_degree_rank", ""),
            "school_education_type": top_edu.get("school_education_type", ""),
            "school_start_ym": top_edu.get("school_start_ym", ""),
            "school_end_ym": top_edu.get("school_end_ym", ""),
        }
    else:
        structured_data["education_info"] = _build_empty_education_info()

    # 顶层 current_info：取最新工作经历
    # EN: Top-level current_info: take the latest work experience
    # JA: トップレベルの current_info：最新の職歴を取る
    r0_works = r0.get("work_experiences") or []
    if r0_works:
        w = r0_works[0]
        structured_data["current_info"] = {
            "company_name": w.get("company_name", ""),
            "company_employees": w.get("company_employees", ""),
            "company_industry": w.get("company_industry", ""),
            "position": w.get("position", ""),
            "position_type": w.get("position_type", ""),
            "position_salary": w.get("position_salary", ""),
            "position_dept": w.get("position_dept", ""),
            "position_report_to": w.get("position_report_to", ""),
            "position_subordinate": w.get("position_subordinate", ""),
            "employment_type": w.get("employment_type", "全职"),
            "annual_salary_min": w.get("annual_salary_min", ""),
            "annual_salary_max": w.get("annual_salary_max", ""),
            "status": w.get("status", ""),
            "position_start": w.get("position_start", ""),
            "position_resigned": w.get("position_resigned", ""),
        }
    else:
        structured_data["current_info"] = _build_empty_current_info()

    # 7. 向后兼容：迁移旧字段名到新字段名（始终删除旧字段）
    # EN: 7. Backward compatibility: migrate old field names to new ones (always deleting the old fields)
    # JA: 7. 後方互換：旧フィールド名を新しい名前に移行する（旧フィールドは常に削除）
    for r in structured_data.get("resumes") or []:
        _compat_map = {
            "project_experiences": "project_list",
            "training_experiences": "training_list",
            "certificate_info": "certificate_list",
            "language_info": "language_list",
            "skills_info": "skills_list",
            "communication_assessment": "communication_list",
            "resume_languge": "resume_language",
        }
        for old, new in _compat_map.items():
            if old in r:
                if new not in r:
                    r[new] = r[old]
                r.pop(old)

    # 8. 递归删除 structured_data 内部所有 raw_text 字段（仅保留最外层 record 的 raw_text）
    # EN: 8. Recursively delete every raw_text field inside structured_data (keep only the outermost record's raw_text)
    # JA: 8. structured_data 内部の raw_text フィールドを再帰的にすべて削除する（最も外側のレコードの raw_text だけを残す）
    def _strip_inner_raw_text(obj):
        if isinstance(obj, dict):
            obj.pop("raw_text", None)
            for v in obj.values():
                _strip_inner_raw_text(v)
        elif isinstance(obj, list):
            for item in obj:
                _strip_inner_raw_text(item)
    _strip_inner_raw_text(structured_data)

    # 9. 清除顶层冗余列表字段（明细保留在 resumes 内）
    # EN: 9. Remove redundant top-level list fields (the details stay in resumes)
    # JA: 9. 冗長なトップレベルのリストフィールドを削除する（明細は resumes 内に残す）
    _top_level_blacklist = {"work_experiences", "education_list", "project_experiences",
                            "communication_assessment", "training_experiences",
                            "certificate_list", "language_list", "skills_list",
                            "training_list", "project_list", "communication_list"}
    structured_data = {k: v for k, v in structured_data.items() if k not in _top_level_blacklist}

    # 10. 日期提取
    # EN: 10. Date extraction
    # JA: 10. 日付の抽出
    fallback_date = date_from_mtime(html_path)
    up_date, dl_date, up_src, dl_src = parse_resume_dates(text, fallback_date)

    now = datetime.now(TZ_JST).isoformat(timespec="seconds")
    rec_id = html_record_id(html_path)
    stat = html_path.stat()

    w_count = len((structured_data.get("resumes") or [{}])[0].get("work_experiences") or [])
    e_count = len((structured_data.get("resumes") or [{}])[0].get("education_list") or [])

    record = {
        "schema_version": "codex-resume-json-1.0",
        "record_id": rec_id,
        "source": {
            "path": fake_source_path,
            "original_path": fake_source_path,
            "filename": html_path.name,
            "extension": ".html",
            "size": stat.st_size,
            "html_filename": html_path.name,
            "note": "由 run_zhilian_html_to_json.py 从智联招聘 HTML 转换",
        },
        "dates": {
            "resume_updated_date": up_date,
            "resume_download_date": dl_date,
            "resume_updated_date_source": up_src,
            "resume_download_date_source": dl_src,
            "sys_created_date": now,
            "sys_updated_date": now,
        },
        "extraction": {
            "reader_group": "zhilian_html_dom",
            "converter": "run_zhilian_html_to_json.py",
            "parser": "codex_gemini_html_schema_parser",
            "status": "success",
            "html_path": str(html_path.resolve()),
        },
        "classification": {
            "document_type": classification.document_type,
            "reason": getattr(classification, "reason", ""),
        },
        "structured_data": structured_data,
        "raw_text": text,
        "quality": {
            "full_name": (structured_data.get("base_info") or {}).get("full_name", ""),
            "has_work": w_count > 0,
            "work_count": w_count,
            "has_education": e_count > 0,
            "education_count": e_count,
            "raw_text_length": len(text),
        },
    }
    return record, "success"


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
    if os.name == "nt":
        os.system("title 智联招聘 HTML -> JSON")

    html_dir = args.html_dir.resolve()
    json_dir = args.json_dir.resolve()
    json_dir.mkdir(parents=True, exist_ok=True)

    print(f"源 HTML 目录: {html_dir}" f" / Source HTML directory: {html_dir} / 元の HTML ディレクトリ：{html_dir}")
    print(f"输出 JSON 目录: {json_dir}" f" / Output JSON directory: {json_dir} / 出力する JSON のディレクトリ：{json_dir}")

    if not html_dir.exists():
        print(f"错误: 目录不存在 -> {html_dir}" f" / Error: directory does not exist -> {html_dir} / エラー：ディレクトリが存在しません -> {html_dir}")
        return 1

    html_files = sorted(html_dir.glob("*.html"))
    if not html_files:
        print("未找到 HTML 文件。" " / No HTML files found. / HTML ファイルが見つかりません。")
        return 0

    if args.limit > 0:
        html_files = html_files[: args.limit]

    print(f"共发现 {len(html_files)} 个智联招聘 HTML 文件。" f" / Found {len(html_files)} Zhaopin HTML files. / 智聯招聘の HTML ファイルを {len(html_files)} 個検出しました。")

    parser = CodexGeminiHtmlSchemaParser()
    classifier = DocumentClassifier()

    success_count = 0
    failed_count = 0
    skipped_count = 0
    non_resume_count = 0
    items_report: list[dict[str, Any]] = []

    start_time = time.time()

    for idx, html_path in enumerate(html_files, 1):
        rec_id = html_record_id(html_path)
        record, status = build_record_from_html(html_path, parser, classifier)

        if not record or status.startswith("non_resume"):
            non_resume_count += 1
            print(f"[{idx:04d}/{len(html_files):04d}] SKIP(非简历) {html_path.name} -> {status}" f" / [{idx:04d}/{len(html_files):04d}] SKIP (non-résumé) {html_path.name} -> {status} / [{idx:04d}/{len(html_files):04d}] SKIP（履歴書でない） {html_path.name} -> {status}")
            items_report.append({
                "index": idx,
                "html": str(html_path),
                "status": status,
            })
            continue

        full_name = record["quality"].get("full_name", "") or "未知"
        safe_name = re.sub(r'[\\/:*?"<>|]', "", full_name) or "未知"
        work_cnt = record["quality"].get("work_count", 0)

        json_filename = f"{safe_name}_{rec_id[:8]}.json"
        json_path = json_dir / json_filename

        if json_path.exists() and not args.force:
            skipped_count += 1
            if idx % args.progress_interval == 0:
                print(f"[{idx:04d}/{len(html_files):04d}] EXIST {html_path.name}")
            continue

        try:
            json_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
            success_count += 1
            items_report.append({
                "index": idx,
                "html": str(html_path),
                "json": str(json_path),
                "status": "success",
                "full_name": full_name,
                "work_count": work_cnt,
            })
            if idx % args.progress_interval == 0 or idx == len(html_files):
                print(f"[{idx:04d}/{len(html_files):04d}] OK    {html_path.name} → {full_name} (工作{work_cnt}段)" f" / [{idx:04d}/{len(html_files):04d}] OK    {html_path.name} → {full_name} ({work_cnt} work entries) / [{idx:04d}/{len(html_files):04d}] OK    {html_path.name} → {full_name}（職歴 {work_cnt} 件）", flush=True)
        except Exception as exc:
            failed_count += 1
            items_report.append({
                "index": idx,
                "html": str(html_path),
                "status": f"write_error:{exc}",
            })
            print(f"[{idx:04d}/{len(html_files):04d}] FAIL  {html_path.name} -> {exc}", flush=True)

    elapsed = time.time() - start_time
    report = {
        "workflow": "zhilian_html_to_json",
        "html_dir": str(html_dir),
        "json_dir": str(json_dir),
        "total": len(html_files),
        "success": success_count,
        "failed": failed_count,
        "skipped": skipped_count,
        "non_resume_count": non_resume_count,
        "elapsed_seconds": round(elapsed, 2),
        "items": items_report,
    }
    report_path = json_dir / "_zhilian_batch_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print()
    print("=== 智联招聘 HTML→JSON 批处理完成 ===" " / === Zhaopin HTML→JSON batch finished === / === 智聯招聘の HTML→JSON 一括処理が完了しました ===")
    print(f"总计: {len(html_files)}；成功: {success_count}；失败: {failed_count}；跳过: {skipped_count}；非简历: {non_resume_count}" f" / Total: {len(html_files)}; success: {success_count}; failed: {failed_count}; skipped: {skipped_count}; non-résumé: {non_resume_count} / 合計：{len(html_files)}、成功：{success_count}、失敗：{failed_count}、スキップ：{skipped_count}、履歴書でない：{non_resume_count}")
    print(f"耗时: {elapsed:.2f} 秒；报告: {report_path}" f" / Elapsed: {elapsed:.2f} s; report: {report_path} / 所要時間：{elapsed:.2f} 秒、レポート：{report_path}")
    return 0 if failed_count == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
