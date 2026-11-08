"""中文主版 + 英文独立版 HTML -> JSON 语义解析器。

只做 codex_word_html_json_100.py 的第二阶段：读取已有 HTML DOM，
调用 CodexGeminiHtmlSchemaParser + extend_schema，输出到
complete-transfered-jsons/docs/51job/。

源 Word 文件可能不存在，因此：
- 文件级时间/大小用 HTML 文件属性代替；
- 原始路径/文件名从 HTML 文件名反向推断（保存在 source 字段中供溯源）。

EN: Chinese primary + separate English version HTML -> JSON semantic parser.

Only does the second stage of codex_word_html_json_100.py: reads the existing HTML DOM,
calls CodexGeminiHtmlSchemaParser + extend_schema, and outputs to
complete-transfered-jsons/docs/51job/.

The source Word file may not exist, therefore:
- file-level time/size use the HTML file's attributes instead;
- the original path/file name is inferred back from the HTML file name (stored in the source field for traceability).

JA: 中国語主版 + 独立した英語版の HTML -> JSON 意味解析器。

codex_word_html_json_100.py の第 2 段階だけを行う：既存の HTML DOM を読み、
CodexGeminiHtmlSchemaParser + extend_schema を呼び出して、
complete-transfered-jsons/docs/51job/ に出力する。

元の Word ファイルが存在しないことがあるため：
- ファイル単位の日時・サイズは HTML ファイルの属性で代用する。
- 元のパス・ファイル名は HTML のファイル名から逆に推定する（追跡用に source フィールドに保存）。
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

from resume_importer.codex_gemini_html_schema_parser import (
    CodexGeminiHtmlSchemaParser,
    EDUCATION_RANKS_ORDERED,
    EDUCATION_TYPE_MAP,
)
from resume_importer.classifier import DocumentClassifier
from run_chinese_html_to_json import extract_candidate_name

try:
    from bs4 import BeautifulSoup, Comment
except ImportError:  # pragma: no cover
    BeautifulSoup = None
    Comment = ()

TZ_JST = timezone(timedelta(hours=9))

if os.name == "nt":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="中文 + 英文语义 HTML -> JSON 转换" " / Chinese + English semantic HTML -> JSON conversion / 中国語 + 英語の意味付き HTML -> JSON 変換")
    p.add_argument(
        "--html-dir",
        type=Path,
        default=PROJECT_ROOT / _rc.dirname("complete-transfered-htmls") / "docs" / "51job",
    )
    p.add_argument(
        "--json-dir",
        type=Path,
        default=PROJECT_ROOT / _rc.dirname("complete-transfered-jsons") / "docs" / "51job",
    )
    p.add_argument("--limit", type=int, default=0, help="0=全部" " / 0 = all / 0 は全件")
    p.add_argument("--force", action="store_true", help="覆盖已存在 JSON" " / Overwrite existing JSON / 既存の JSON を上書きする")
    p.add_argument("--progress-interval", type=int, default=20)
    p.add_argument(
        "--map",
        type=Path,
        default=PROJECT_ROOT / _rc.dirname("complete-transfered-htmls") / "docs" / "word_conversion_map.json",
        help="用于恢复原始 Word 路径和权威联系方式" " / Used to restore the original Word path and authoritative contact details / 元の Word のパスと権威ある連絡先を復元するために使う",
    )
    p.add_argument("--file-timeout", type=int, default=60, help="兼容统一批处理接口；当前解析器不启子进程" " / Compatible with the unified batch interface; the current parser does not start subprocesses / 統一された一括処理インターフェースとの互換用（現在のパーサーはサブプロセスを起動しない）")
    return p.parse_args()


def plain_text(html_text: str) -> str:
    if not html_text:
        return ""
    if BeautifulSoup is None:
        raw = re.sub(r"<[^>]+>", "\n", html_text)
    else:
        soup = BeautifulSoup(html_text, "html.parser")
        for tag in soup(["script", "style", "xml", "meta", "link"]):
            tag.decompose()
        raw = soup.get_text("\n")
    raw = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", raw)
    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    # 修复 51job 等来源中日期被换行切断的问题：
    #   "2013\n/3--至今：公司名"   → "2013/3--至今：公司名"
    #   "2008\n/2--2011\n/5：..." → "2008/2--2011/5：..."
    #   "2004\n/9--2008\n/7      华东师范大学 ..."
    # EN: Fix dates broken by line breaks in sources such as 51job:
    #       "2013\n/3--至今：公司名"   → "2013/3--至今：公司名"
    #       "2008\n/2--2011\n/5：..." → "2008/2--2011/5：..."
    #       "2004\n/9--2008\n/7      华东师范大学 ..."
    # JA: 51job などのソースで改行により分断された日付を修復する：
    #       "2013\n/3--至今：公司名"   → "2013/3--至今：公司名"
    #       "2008\n/2--2011\n/5：..." → "2008/2--2011/5：..."
    #       "2004\n/9--2008\n/7      华东师范大学 ..."
    merged: list[str] = []
    i = 0
    while i < len(lines):
        cur = lines[i]
        # 规则1：当前行是纯4位年份（允许前后空白），下一行以 /数字 开头
        # EN: Rule 1: the current line is a bare 4-digit year (whitespace allowed around it) and the next line starts with /digits
        # JA: ルール 1：現在の行が 4 桁の年だけ（前後の空白は可）で、次の行が /数字 で始まる
        if i + 1 < len(lines) and re.fullmatch(r"(?:19|20)\d{2}", cur):
            nxt = lines[i + 1]
            if re.match(r"/\d", nxt):
                cur = cur + nxt
                i += 1
        # 规则2：当前行以 /数字 开头，上一行是 (年份--年份) 或 年份 末尾的情况 — 已经在规则1中合并了
        # 规则3：处理 -- 后面的第二个日期也被切断："2013/3--2013\n/3"
        # 检查当前 cur 是否以 4位年份 结束，但 下一行 以 /数字 开头 且 cur 包含 --|至|到|一
        # EN: Rule 2: the current line starts with /digits and the previous line ends with (year--year) or a year — already merged by rule 1
        #     Rule 3: handle the second date after -- also being cut: "2013/3--2013\n/3"
        #     Check whether the current cur ends with a 4-digit year, the next line starts with /digits, and cur contains --|至|到|一
        # JA: ルール 2：現在の行が /数字 で始まり、前の行が (年--年) または年で終わる場合 — すでにルール 1 で結合済み
        #     ルール 3：-- の後の 2 つ目の日付も分断されている場合の処理："2013/3--2013\n/3"
        #     現在の cur が 4 桁の年で終わり、次の行が /数字 で始まり、かつ cur が --|至|到|一 を含むかを確認する
        m = re.search(r"(?:--|[-—–~～至到一])(?:19|20)\d{2}$", cur)
        if m and i + 1 < len(lines) and re.match(r"/\d", lines[i + 1]):
            cur = cur + lines[i + 1]
            i += 1
        # 规则4：教育经历等 "2004\n/9--2008\n/7" 这种中间有 -- 跨两行的
        # 例 当前行 "2004" 下一行 "/9--2008" 再下一行 "/7"
        # EN: Rule 4: cases like "2004\n/9--2008\n/7" in education history, where a -- in the middle spans two lines
        #     e.g. current line "2004", next line "/9--2008", the line after that "/7"
        # JA: ルール 4：学歴などで "2004\n/9--2008\n/7" のように途中の -- が 2 行にまたがる場合
        #     例：現在の行 "2004"、次の行 "/9--2008"、その次の行 "/7"
        if re.fullmatch(r"(?:19|20)\d{2}", cur) and i + 2 < len(lines):
            mid = lines[i + 1]
            tail = lines[i + 2]
            if re.match(r"/\d.+(?:19|20)\d{2}$", mid) and re.match(r"/\d", tail):
                cur = cur + mid + tail
                i += 2
        merged.append(cur)
        i += 1
    return "\n".join(merged)


def standardize_datetime(raw: str) -> str:
    """将各种乱序/年月格式日期统一洗净标准化为 YYYY-MM-DD HH:MM:SS 规范格式。

    EN: Clean and normalise dates in all kinds of jumbled/year-month formats to the standard YYYY-MM-DD HH:MM:SS format.

    JA: さまざまな順序・年月形式の日付を、標準の YYYY-MM-DD HH:MM:SS 形式に統一して正規化する。
    """
    raw = raw.replace("年", "-").replace("月", "-").replace("日", "").replace(".", "-").replace("/", "-")
    raw = re.sub(r"\s+", " ", raw).strip()
    parts = raw.split(" ")
    date_part = parts[0]
    time_part = parts[1] if len(parts) > 1 else "00:00:00"

    d_parts = date_part.split("-")
    if len(d_parts) >= 3:
        y, m, d = d_parts[0], d_parts[1], d_parts[2]
        date_str = f"{int(y):04d}-{int(m):02d}-{int(d):02d}"
    else:
        date_str = date_part

    t_parts = time_part.split(":")
    if len(t_parts) == 2:
        time_str = f"{int(t_parts[0]):02d}:{int(t_parts[1]):02d}:00"
    elif len(t_parts) == 3:
        time_str = f"{int(t_parts[0]):02d}:{int(t_parts[1]):02d}:{int(t_parts[2]):02d}"
    else:
        time_str = "00:00:00"

    return f"{date_str} {time_str}"


def parse_resume_dates(text: str, fallback_date: str) -> tuple[str, str, str, str]:
    """通用精准提取 resume_updated_date 与 resume_download_date 及其权威来源说明。

    EN: General precise extraction of resume_updated_date and resume_download_date and the description of their authoritative source.

    JA: resume_updated_date と resume_download_date、およびその根拠となる取得元の説明を汎用的に正確に抽出する。
    """
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


def _extract_51job_name(text: str, filename: str, parsed_name: str) -> str:
    """三重防护提取 51job 候选人真实姓名（解决如姜世雄等被误判为未知的 Bug）。

    EN: Triple-guarded extraction of the 51job candidate's real name (fixes the bug where some names were misjudged as unknown).

    JA: 3 重の防御で 51job の候補者の実名を抽出する（一部の氏名が不明と誤判定されるバグを解消）。
    """
    parsed_name = (parsed_name or "").strip()
    if parsed_name and parsed_name not in ("待确认姓名", "未知", "简历", "无关联职位简历") and not re.search(r"(?:工程师|经理|主管|专员|开发|运营|总监|销售|翻译)", parsed_name):
        return parsed_name

    # 1. raw_text 特征：姓名下一行是 XX年工作经验 或 男/女 或 XX岁
    # EN: 1. raw_text features: the line after the name is "XX年工作经验" (XX years of experience), 男/女 (male/female) or XX岁 (age)
    # JA: 1. raw_text の特徴：氏名の次の行が「XX年工作经验」（経験 XX 年）、男／女、または XX岁（年齢）
    m_raw = re.search(r"\n\s*([^\s\n:：|│]{2,8})\s*\n\s*(?:\d+[-～~]\d+年工作经验|\d+年工作经验|[男女]\s*[|│]|[\d]{1,2}岁)", text)
    if m_raw:
        cand = m_raw.group(1).strip()
        if not re.search(r"(?:更新时间|简历关键字|最近工作|最高学历|自我评价|工作经验|工作经历|项目经历|教育经历|语言能力)", cand):
            return cand

    # 2. 文件名穿透 51job_姓名_数字ID
    # EN: 2. Look through the file name 51job_<name>_<numeric ID>
    # JA: 2. ファイル名 51job_<氏名>_<数字 ID> から取得する
    m_file = re.match(r"^51job_([^\s\-_0-9]{2,8})_\d+", filename, re.I)
    if m_file:
        return m_file.group(1).strip()

    # 3. 文件名连字符 姓名-XX岁
    # EN: 3. File name with a hyphen: <name>-XX岁 (age)
    # JA: 3. ハイフン付きのファイル名：<氏名>-XX岁（年齢）
    m_file2 = re.search(r"([^\s\-_0-9]{2,8})-\d{1,2}岁", filename)
    if m_file2:
        return m_file2.group(1).strip()

    return parsed_name or "未知"


def dom_summary(html: str) -> dict[str, Any]:
    if BeautifulSoup is None:
        return {"heading_count": 0, "table_count": 0, "row_count": 0, "headings": []}
    soup = BeautifulSoup(html, "html.parser")
    headings = [
        node.get_text(" ", strip=True)
        for node in soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"])
        if node.get_text(strip=True)
    ]
    return {
        "heading_count": len(headings),
        "table_count": len(soup.find_all("table")),
        "row_count": len(soup.find_all("tr")),
        "paragraph_count": len(soup.find_all("p")),
        "headings": headings[:80],
    }


def html_record_id(html_path: Path) -> str:
    stat = html_path.stat()
    value = f"{html_path.resolve()}|{stat.st_size}|{stat.st_mtime_ns}"
    return hashlib.sha256(value.encode("utf-8", "surrogatepass")).hexdigest()


def date_from_mtime(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime, tz=TZ_JST).strftime(
        "%Y-%m-%d %H:%M:%S"
    )


def updated_date(text: str, fallback: str) -> str:
    patterns = (
        r"(?:更新时间|更新日期|简历更新时间|履历更新|履历更新时间|最后更新)\s*[:：]?\s*((?:19|20)\d{2}[./年-]\d{1,2}[./月-]\d{1,2}(?:\s+\d{1,2}:\d{1,2}(?::\d{1,2})?)?)",
        r"(?:更新时间|更新日期|履历更新)[^\d]{0,80}((?:19|20)\d{2}[./年-]\d{1,2}[./月-]\d{1,2}(?:\s+\d{1,2}:\d{1,2}(?::\d{1,2})?)?)",
    )
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            raw = match.group(1).strip()
            date_part, _, time_part = raw.partition(" ")
            value = re.sub(r"[年/.]", "-", date_part).replace("月", "-").replace("日", "")
            parts = [part for part in value.split("-") if part]
            if len(parts) == 3:
                if time_part:
                    tm = [int(x) for x in re.findall(r"\d+", time_part)[:3]]
                    while len(tm) < 3:
                        tm.append(0)
                    return f"{int(parts[0]):04d}-{int(parts[1]):02d}-{int(parts[2]):02d} {tm[0]:02d}:{tm[1]:02d}:{tm[2]:02d}"
                return f"{int(parts[0]):04d}-{int(parts[1]):02d}-{int(parts[2]):02d} 00:00:00"
    return fallback


# ---------- 从 codex_word_html_json_100.py 拷贝 extend_schema 及依赖 ----------
# EN: ---------- extend_schema and its dependencies copied from codex_word_html_json_100.py ----------
# JA: ---------- codex_word_html_json_100.py から extend_schema とその依存部分をコピー ----------
SUSPICIOUS_NAME_WORDS = {
    "未知", "目前", "未婚", "已婚", "副总经理", "基本资料", "个人简历",
    "销售和回款", "高速梯", "共青团员", "销售部经理", "工作经历",
}
company_suffix = r"(?:有限公司|有限责任公司|股份有限公司|集团(?:公司)?|研究所|研究中心|研究院|中心|公司|株式会社|会社|Corporation|Company|Consulting|Institute|Center|银行|監査法人)"


def name_quality_flags(name: str) -> list[str]:
    value = re.sub(r"\s+", " ", str(name or "")).strip()
    flags: list[str] = []
    if not value or value in SUSPICIOUS_NAME_WORDS:
        flags.append("姓名缺失或疑似为职位/章节文字")
    if re.search(r"简历|资料|工作经历|教育经历|自我评价|求职意向|销售和回款|高速梯|共青团员", value, re.I):
        flags.append("姓名包含简历章节、职位或其他非姓名关键词")
    if len(re.sub(r"[^\u4e00-\u9fff]", "", value)) > 6:
        flags.append("中文姓名长度异常，需回看原文")
    return list(dict.fromkeys(flags))


def extract_company_name(value: str) -> str:
    from resume_importer.structured_parser import StructuredResumeParser
    value = re.sub(r"\s+", " ", str(value or "")).strip(" ：:|│")
    value = re.sub(r"\s*[\[【［(（][^\]】］)）]*(?:\d+\s*(?:年|个月|月)|合作|外包|兼职|代接)[^\]】］)）]*[\]】］)）]\s*$", "", value, flags=re.I).strip()
    match = re.search(rf"(?P<company>.{{2,140}}?{company_suffix})", value, re.I)
    return (match.group("company") if match else value).strip(" ：:|│")


def extend_schema(parsed: dict[str, Any], clean_text: str, filename: str, source_path: str) -> dict[str, Any]:
    """直接复用 codex_word_html_json_100.py 的 extend_schema。

    实现与原文件一致，避免从原 import（原文件 main 入口会执行 Word→HTML）。
    这里完整复制一份逻辑，保证工作经历清洗规则与主批次一致。

    EN: Directly reuse extend_schema from codex_word_html_json_100.py.

    The implementation matches the original file and avoids importing from it (the original file's main entry would run Word→HTML).
    A full copy of the logic is kept here so the work-history cleaning rules match the main batch.

    JA: codex_word_html_json_100.py の extend_schema をそのまま再利用する。

    実装は元のファイルと同じで、元ファイルからの import は避ける（元ファイルの main エントリは Word→HTML を実行してしまう）。
    ここにロジックを丸ごと複製し、職歴のクレンジングルールをメインバッチと一致させる。
    """
    from resume_importer.structured_parser import StructuredResumeParser

    data = dict(parsed or {})
    resumes = list(data.get("resumes") or [])
    helper = StructuredResumeParser()
    fallback = helper.parse(clean_text, filename, source_path)

    applied_match = re.search(r"(?:Applied Position|申请职位)\s*[:：]?\s*([^\n]+)", clean_text, re.I)
    applied_position = (applied_match.group(1).strip() if applied_match else "")
    applied_position = re.sub(r"^(?:申请职位|Applied Position)\s*[:：]?\s*", "", applied_position, flags=re.I).strip()
    for item in data.get("expected_info") or []:
        position_value = str(item.get("expected_position") or "").strip()
        compact_position = re.sub(r"[\s|｜:：#]+", "", position_value).casefold()
        if compact_position in {"申请表", "职位申请表", "applicationform", "申请职位"}:
            item["expected_position"] = applied_position
        elif compact_position in {"姓名", "姓 名", "目标"} or ("姓" in position_value and "名" in position_value):
            item["expected_position"] = ""
        elif position_value:
            item["expected_position"] = position_value.strip(" |｜")
        city_value = str(item.get("expected_city") or "").strip()
        known_cities = r"北京|上海|广州|深圳|杭州|南京|苏州|天津|武汉|成都|重庆|西安|厦门|大连|青岛|无锡|合肥|宁波|芜湖|昆山|南通|郑州|济南|福州|佛山|东莞|珠海|沈阳|长春|哈尔滨|石家庄|太原|贵阳|昆明|海口|兰州|乌鲁木齐|香港|澳门|东京|大阪|名古屋|Singapore|Singapore"
        if city_value and not re.search(known_cities, city_value, re.I):
            item["expected_city"] = ""
        full_name = str((data.get("base_info") or {}).get("full_name") or "").strip()
        if item.get("expected_position") and (re.search(r"男|女|岁\s*[（(]", str(item.get("expected_position"))) or (full_name and full_name in str(item.get("expected_position")))):
            item["expected_position"] = ""
        salary_value = str(item.get("expected_salary") or "").strip()
        if salary_value and (re.search(r"岁|出生|工作经验", salary_value) or not re.search(r"\d|面议|不限", salary_value)):
            item["expected_salary"] = ""

    def infer_work_context(row: dict[str, Any]) -> tuple[str, str]:
        start = str(row.get("position_start") or "")
        year_month = re.search(r"((?:19|20)\d{2})\s*[年./-]\s*(\d{1,2})", start)
        if not year_month:
            return "", ""
        year, month = year_month.group(1), int(year_month.group(2))
        date_pattern = rf"{year}\s*(?:年|[./-])\s*{month:02d}(?:\s*月)?"
        match = re.search(date_pattern, clean_text, re.I)
        if not match:
            return "", ""
        window = clean_text[match.end(): match.end() + 1400]
        company_match = re.search(
            rf"(?m)^\s*(?!公司(?:性质|规模|行业|描述)|所在|汇报|下属|职位类别|工作职责|工作内容|工作描述)"
            rf"(?P<company>.{{2,120}}?{company_suffix})\s*$",
            window, re.I,
        )
        if not company_match:
            return "", ""
        company = company_match.group("company").strip(" \t|│：:")
        after_company = window[company_match.end(): company_match.end() + 600]
        role = ""
        for line in after_company.splitlines():
            line = line.strip(" \t|│：:")
            if not line or len(line) > 60:
                continue
            if re.search(r"公司(?:性质|规模|行业|描述)|所在|汇报对象|下属人数|职位类别|薪资|工作职责|工作内容|工作描述|^\d+[年月日]", line):
                continue
            if re.search(r"经理|总监|工程师|主管|专员|代表|分析师|开发|测试|架构师|产品|销售|设计员|部长|担当|顾问|助理|技术员|采购", line):
                role = line
                break
        return company, role

    def clean_work_item(item: dict[str, Any]) -> dict[str, Any]:
        row = dict(item)
        raw = str(row.get("raw_text") or "") or clean_text
        original_company = str(row.get("company_name") or "").strip()
        company = re.sub(r"^(?:名称|公司|单位|企业)\s*[:：]\s*", "", original_company).strip()
        company = re.sub(r"\s*[\[【［(（][^\]】］)）]*(?:年|个月|month|year|代接|合作|外包|兼职)[^\]】］)）]*[\]】］)）]\s*$", "", company, flags=re.I).strip()
        company = re.sub(r"^\s*(?:\d+年\d*个月?|\d+个月?|\d+月)\s*(?:[一至到\-—~～]+\s*(?:至今|现在)?)?\s*", "", company)
        company = re.sub(r"^.*?(?:至今|现在|至現在|現在)\s+", "", company).strip()
        bank_name = re.match(r"^(.+?(?:銀行|银行))", company, re.I)
        if bank_name:
            company = bank_name.group(1).strip()
        if "KPMG監査法人" in company:
            company = "KPMG監査法人"
        company = re.sub(r"\s*\.\s*(?:VP|Vice President|Director|Manager|内部审计|internal audit).*$", "", company, flags=re.I).strip()
        if not row.get("position_start"):
            date_company = re.search(r"((?:19|20)\d{2})\s*年\s*(\d{1,2})\s*月[^\n]{0,30}" + re.escape(original_company.split(" ")[-1]), clean_text)
            if date_company:
                row["position_start"] = f"{date_company.group(1)}年{int(date_company.group(2)):02d}月01日"
                row["position_resigned"] = ""
                row["status"] = "在职"
        position = str(row.get("position") or "").strip()
        position = re.sub(r"\s*[（(](?:全职|兼职|正社員|契約社員)[）)]", "", position, flags=re.I).strip()
        if re.match(r"^(?:汇报对象|报告对象|所在部门|工作描述|工作职责|主要工作内容|职责业绩|工作业绩)\s*[:：]", position, re.I):
            position = ""
        inline_position = re.search(rf"^(?:\s*\d+\s*(?:月)?\s*)?(?P<company>.{{2,120}}?{company_suffix})\s+(?P<role>[^\n|｜]+)$", company, re.I)
        if inline_position:
            company = inline_position.group("company").strip()
            if not position or position in {company, "担当"} or len(position) > 40:
                position = inline_position.group("role").strip()
        inline_position = re.search(rf"^(?P<company>.{{2,120}}?{company_suffix})\s+(?P<role>[^\n|｜]+)$", position, re.I)
        if inline_position:
            position = inline_position.group("role").strip()
            if not company or company == position:
                company = inline_position.group("company").strip()
        inline = re.search(rf"^(?:\s*\d+\s*(?:月)?\s*)?(?P<company>.{{2,120}}?{company_suffix})(?:\s+|\s*\|\s*)(?P<role>[^\n|｜]+)?$", company, re.I)
        if inline:
            company = inline.group("company").strip()
            if inline.group("role") and (not position or position == company or position == "担当"):
                position = inline.group("role").strip()
        inferred_company, inferred_position = infer_work_context(row)
        if inferred_company and (
            not re.search(re.escape(company), clean_text, re.I)
            or (len(inferred_company) > len(company) and inferred_company.endswith(company.rstrip("（(")))
        ):
            company = inferred_company
        if re.search(r"銀行|監査法人|Consulting", company, re.I):
            source_role = ""
            company_pat = re.escape(company)
            rm = re.search(company_pat + r"(?:内部監査部)?\s*[,，]?\s*(?P<role>[^、，,。\n]{2,30})", clean_text, re.I)
            if rm:
                source_role = rm.group("role").strip()
            if not source_role and re.search(r"監査法人", company, re.I):
                rm = re.search(r"監査法人[、,，]\s*(?P<role>監査員|監査担当|会計士)", clean_text, re.I)
                if rm:
                    source_role = rm.group("role").strip()
            if source_role and (not position or len(position) > 30 or re.search(r"輸出輸入|各支店|与信|預金|内部統制|不正", position)):
                position = source_role
        if re.search(r"主要工作内容|工作描述|工作职责|职责业绩|职位", position or "", re.I) or not position:
            date_role = re.search(r"(?:19|20)\d{2}[./年]\s*\d{1,2}(?:月)?\s*[-—~至到一]+\s*(?:至今|现在|目前|(?:19|20)\d{2}[./年]\s*\d{1,2}(?:月)?)\s+" + re.escape(company) + r"(?:内部审计部|内部監査部)?\s+(?P<role>[^\s\n]{2,30})", clean_text, re.I)
            if date_role:
                position = date_role.group("role").strip()
        suspect_company = (
            len(company) > 60
            or not re.search(company_suffix, company, re.I)
            or company.startswith(("公司性质", "公司规模", "公司行业", "工作内容", "工作职责"))
            or re.search(r"物联网行业|积累了|企业本质|行业应用|工作描述|工作内容|项目简介|推行|负责|成立于|客户|公司描述", company)
        )
        if suspect_company and inferred_company:
            company = inferred_company
        if (not position or position == company or re.search(company_suffix, position, re.I) or len(position) > 60) and inferred_position:
            position = inferred_position
        responsibility = str(row.get("position_responsibilities") or "").replace("\r", "").strip()
        if responsibility:
            first_lines = [line.strip(" \t|│") for line in responsibility.splitlines() if line.strip()]
            if first_lines:
                first = first_lines[0]
                first = re.sub(r"\s*[\[【［(（][^\]】］)）]*(?:年|个月|month|year)[^\]】］)）]*[\]】］)）]\s*$", "", first, flags=re.I).strip()
                if not re.search(r"公司性质|公司规模|公司行业|工作描述|工作职责", first):
                    company_match = re.search(rf"(?P<company>.{{2,100}}?{company_suffix})(?=\s*[，,：:|｜ ]|$)", first, re.I)
                    if company_match and (not company or len(company) > 80 or not re.search(company_suffix, company, re.I) or not re.search(re.escape(company), first, re.I)):
                        company = company_match.group("company").strip()
                        tail = first[company_match.end():].strip(" ，,：:|｜")
                        if tail and (not position or position.isdigit() or position == "担当") and re.search(r"经理|工程师|主管|专员|代表|分析师|开发|测试|产品|销售|设计|担当|课长", tail):
                            position = re.split(r"[。；;]", tail, maxsplit=1)[0].strip()
                    elif not position or position.isdigit() or len(position) < 2:
                        position = first
                for line in first_lines[:5]:
                    if (not position or position.isdigit() or position in {"担当", "全职"}) and 2 <= len(line) <= 40 and re.search(r"经理|总监|工程师|主管|专员|代表|分析师|开发|测试|架构师|产品|销售|设计员|部长|担当|课长|施工员", line) and not re.search(r"公司|工作描述|公司性质|公司规模|行业", line):
                        position = line
                        break
                cleaned_resp = responsibility
                if company:
                    cleaned_resp = re.sub(r"^\s*" + re.escape(company) + r"\s*(?:\[[^\]]+\]|【[^】]+】|［[^］]+］|\([^)]*个月?[^)]*\))?\s*", "", cleaned_resp, flags=re.I)
                cleaned_resp = re.sub(r"^\s*(?:建筑/建材/工程|电子技术/半导体/集成电路|机械制造/机电/重工|汽车)(?:\|[^\n]+)?\s*", "", cleaned_resp, flags=re.I)
                cleaned_resp = re.sub(r"^\s*(?:公司性质|公司规模|公司行业|公司描述|所在地区|所在部门|汇报对象|下属人数|薪酬情况|职业业绩|职务业绩)\s*[:：]?\s*", "", cleaned_resp, flags=re.I)
                row["position_responsibilities"] = cleaned_resp.strip()
        if len(company) > 80 or not re.search(company_suffix, company, re.I):
            candidates = []
            for line in raw.splitlines():
                line = line.strip(" \t|│")
                m = re.search(rf"(?P<company>.{{2,120}}?{company_suffix})", line, re.I)
                if m and len(m.group("company")) <= 80 and not any(bad in line for bad in ["工作描述", "工作职责", "工作内容", "行业应用", "企业本质", "项目简介", "推行", "负责", "成立于", "客户"]):
                    candidates.append(m.group("company").strip())
            if candidates:
                company = candidates[0]
        company = re.sub(r"^[\s\d./-]+", "", company).strip(" ：:|│")
        row["company_name"] = company
        if position.strip() == company or re.search(company_suffix, position, re.I):
            position = ""
        if not position:
            for line in raw.splitlines():
                line = line.strip(" \t|│")
                if (2 <= len(line) <= 40 and line != company and re.search(r"工程师|经理|主管|专员|代表|分析师|开发|测试|架构师|产品|办事员|销售|职位", line) and not re.search(r"公司|有限公司|工作描述|职责|行业", line)):
                    position = line
                    break
        if position and re.search(r"監査|財務|経理|法務|Consultant|担当|部長|課長|主任|係長", position, re.I):
            position = re.split(r"[、，,。；;：:]", position, maxsplit=1)[0].strip()
        if len(position) > 60 or (re.search(r"[，。；;]", position) and not re.search(r"经理|工程师|主管|专员|代表|分析师|开发|测试|架构师|产品|销售|设计|部长|担当|課長", position)):
            position = ""
        if not position:
            role_from_raw = re.search(r"(?:任职|担任|任)\s*(?P<role>[^，,。；;\n]{2,40})", raw, re.I)
            if role_from_raw:
                candidate_role = role_from_raw.group("role").strip(" ：:，,")
                if candidate_role and len(candidate_role) <= 40:
                    position = candidate_role
        raw_lines = [re.sub(r"\s+", " ", x).strip(" |│") for x in raw.replace("\r", "").splitlines()]
        raw_lines = [x for x in raw_lines if x]
        if not position or re.match(r"^(?:汇报对象|报告对象|所在部门|工作描述|工作职责|主要工作内容|职责业绩|工作业绩)\s*[:：]", position, re.I):
            for candidate in raw_lines:
                if re.search(r"^(?:公司性质|公司规模|公司行业|所在地区|所在部门|汇报对象|报告对象|下属人数|薪酬情况|工作描述|工作职责|主要工作内容|职责业绩|工作业绩)\s*[:：]?", candidate, re.I):
                    continue
                if re.search(r"经理|总监|工程师|主管|专员|代表|分析师|开发|测试|架构师|产品|销售|设计|部长|科长|副总裁|監査|Consultant|担当|部長|課長", candidate, re.I) and len(candidate) <= 50:
                    position = candidate.strip(" ：:|│")
                    break
        def raw_label(*names: str) -> str:
            pattern = r"^(?:" + "|".join(re.escape(n) for n in names) + r")\s*[:：]?\s*(.*)$"
            for i, line in enumerate(raw_lines):
                m = re.match(pattern, line, re.I)
                if m:
                    value = m.group(1).strip(" ：:|│")
                    if value:
                        return value
                    if i + 1 < len(raw_lines):
                        nxt = raw_lines[i + 1].strip(" ：:|│")
                        if nxt and not re.match(r"^(?:工作描述|职责业绩|工作职责和业绩|汇报对象|离职原因|工作业绩|工作地点|所在部门|下属人数|薪酬状况|薪资)\s*[:：]?", nxt, re.I):
                            return nxt
            return ""
        label_map = {
            "position_salary": ("薪酬状况", "薪资", "薪酬情况", "目前薪资", "月 薪", "月薪"),
            "position_dept": ("所在部门", "工作部门", "所属部门"),
            "position_report_to": ("汇报对象", "报告对象", "直属上级"),
            "position_subordinate": ("下属人数", "下属", "下属员工"),
            "company_industry": ("所属行业", "公司行业"),
        }
        for field, names in label_map.items():
            if not str(row.get(field) or "").strip():
                value = raw_label(*names)
                if value:
                    row[field] = value
        if not str(row.get("position_salary") or "").strip():
            salary_match = re.search(r"(?:薪酬状况|薪酬情况|薪资)\s*[:：]?\s*([^\n]{1,40})", raw, re.I)
            if salary_match:
                salary_value = salary_match.group(1).strip(" ：:|│")
                if not re.match(r"^(?:工作地点|所在部门|汇报对象|下属人数|职责业绩|工作描述)\s*[:：]?", salary_value, re.I):
                    row["position_salary"] = salary_value
        if str(row.get("position_subordinate") or "").strip() in {"0", "0人"}:
            value = raw_label("下属人数", "下属", "下属员工")
            if value:
                row["position_subordinate"] = value
        row["position"] = position
        return row

    def valid_work_item(item: dict[str, Any]) -> bool:
        company = str(item.get("company_name") or "").strip()
        if len(company) < 2 or company in {"）", ")", "公司", "单位"}:
            return False
        if re.search(r"(?:[A-Za-z]:[\\/]|源文件路径|简历下载|专业\s*[:：]|学历\s*[:：]|教育经历|工作经历)", company):
            return False
        if re.search(r"公司性质|公司规模|公司行业|工作职责|工作内容|企业本质|物联网行业|大学|学院|学校|专业\s*[:：]|学历\s*[:：]|项目经验|项目描述|推行|负责|客户|成立于|项目简介|下属：|所在职务：", company):
            return False
        if re.match(r"^(?:公司名称|名称|所在公司|所属公司)\s*[:：]", company) or re.search(r"担任职务|项目经验|项目描述", str(item.get("position") or "")):
            return False
        if re.match(r"^(?:汇报对象|报告对象|所在部门|工作描述|工作职责|主要工作内容|职责业绩|工作业绩|下\s*属|所在\s*职务|应聘职位|期望职位)\s*[:：]", str(item.get("position") or ""), re.I):
            return False
        if re.match(r"^[、，,;；:：]", company) or (len(company) > 40 and not re.search(company_suffix, company, re.I)):
            return False
        if "|" in company or re.search(r"\d+\s*[-~～]\s*\d+人", company):
            return False
        return True

    def work_item(item: dict[str, Any]) -> dict[str, Any]:
        result = {
            "company_name": item.get("company_name") or "",
            "company_employees": "",
            "company_industry": item.get("industry_name") or "",
            "position": item.get("position_name") or "",
            "position_type": "",
            "position_salary": "",
            "position_dept": item.get("department_name") or "",
            "position_report_to": item.get("report_to") or "",
            "position_subordinate": item.get("subordinate_count") or "",
            "employment_type": "全职",
            "annual_salary_min": "",
            "annual_salary_max": "",
            "status": "在职" if item.get("is_current") else "离职",
            "position_start": item.get("start_ym") or "",
            "position_resigned": item.get("end_ym") or "",
            "resigned_reason": "",
            "position_responsibilities": item.get("responsibilities") or "",
            "position_achievements": item.get("achievements") or "",
            "raw_text": item.get("raw_text") or "",
        }
        return clean_work_item(result)

    def education_item(item: dict[str, Any]) -> dict[str, Any]:
        school = str(item.get("school_name") or "").replace("\xa0", " ").strip()
        start_ym = item.get("start_ym") or item.get("school_start_ym") or ""
        end_ym = item.get("end_ym") or item.get("school_end_ym") or ""
        embedded = re.search(r"((?:19|20)\d{2}[./年-]\d{1,2}月?)\s*[-—–~～〜至到－]+\s*((?:19|20)\d{2}[./年-]\d{1,2}月?)", school)
        if embedded:
            start_ym = start_ym or embedded.group(1)
            end_ym = end_ym or embedded.group(2)
            school = school[embedded.end():].strip(" \t\r\n\xa0:：|│·•▲()（）[]【】")
        school = re.sub(r"^[^|｜]*[|｜]\s*(?:19|20)\d{2}[^|｜]*[|｜]\s*", "", school).strip()
        school = re.sub(r"^[^|｜]*[|｜]\s*[^|｜]*[|｜]\s*", "", school).strip(" \t\r\n\xa0:：|│")
        school = re.sub(r"^(?:学士|硕士|博士|MBA|EMBA|辅修学位)\s*[|｜]\s*", "", school, flags=re.I).strip()
        school = re.split(r"\s*(?:GPA|相关课程|荣誉奖项)\s*[:：]", school, maxsplit=1, flags=re.I)[0].strip()
        school = school.strip()
        degree = str(item.get("education_level") or item.get("school_degree_type") or "").split("|", 1)[0].strip()
        major = str(item.get("major_name") or item.get("school_major_name") or "").strip()
        raw_value = str(item.get("raw_text") or "").strip()
        raw_head = re.match(r"^(MBA|EMBA|博士|硕士|学士|本科|大专|专科|辅修学位)\s*[|｜]", raw_value, re.I)
        if raw_head:
            degree = raw_head.group(1)
        if "|" in major or "｜" in major:
            parts = [p.strip() for p in re.split(r"[|｜]", major) if p.strip()]
            if parts:
                if not degree and parts[0] in {"专科", "大专", "本科", "学士", "硕士", "博士", "MBA", "EMBA", "辅修学位"}:
                    degree = parts.pop(0)
                major = " | ".join(parts)
        if not major:
            school_tail = re.match(r"^(?P<school>.*?(?:大学院|大学|学院|学校))\s+(?P<major>[^\n]{2,40})$", school)
            if school_tail and not re.search(r"GPA|相关课程|荣誉奖项", school_tail.group("major"), re.I):
                school = school_tail.group("school").strip()
                major = school_tail.group("major").strip()
        major = re.sub(r"\s+(?:大学|大学院|大学校|本科|学士|硕士|博士)\s*$", "", major, flags=re.I).strip()
        if len(major) > 40 or re.search(r"GPA|荣誉奖项|相关课程|是研究|主要目标|创造出|在校|毕业日期|语言能力|外语水平", major, re.I):
            major = ""
        if major:
            major = re.split(r"\s*(?:GPA|荣誉奖项|相关课程)\s*[:：]", major, maxsplit=1, flags=re.I)[0].strip()
        return {
            "school_name": school,
            "school_major_name": major,
            "school_degree_type": degree,
            "school_degree_rank": str(item.get("education_rank") or ""),
            "school_education_type": item.get("education_type") or "",
            "school_start_ym": start_ym,
            "school_end_ym": end_ym,
            "raw_text": item.get("raw_text") or "",
        }

    # —— 以下两个函数移植自 codex_word_html_json_100.py，复用现成的学历等级与教育形式后处理 ——
    # EN: —— The following two functions are ported from codex_word_html_json_100.py, reusing the existing post-processing of degree rank and mode of study ——
    # JA: —— 以下の 2 つの関数は codex_word_html_json_100.py から移植したもので、既存の学歴ランクと就学形態の後処理を再利用する ——
    def normalize_degree_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """补齐可推断的学历等级，并把“专业·硕士/本科”拆干净。

        EN: Fill in inferable degree ranks and split "major·master's/bachelor's" cleanly.

        JA: 推定できる学歴ランクを補い、「専攻・修士／学士」をきれいに分割する。
        """
        degree_rank = {"博士后": "7", "博士": "6", "硕士": "5", "修士": "5", "研究生": "5", "MBA": "5", "EMBA": "5", "本科": "4", "学士": "4", "大专": "3", "专科": "3", "高中": "2", "中专": "2", "职高": "2", "中学": "2", "初中": "1", "小学": "1"}
        result = []
        for item in rows or []:
            row = dict(item)
            degree = str(row.get("school_degree_type") or "").strip()
            major = str(row.get("school_major_name") or "").strip()
            if not degree:
                match = re.search(r"(博士后|博士|硕士|修士|研究生|MBA|EMBA|本科|学士|大专|专科|高中|中专)", major, re.I)
                if match:
                    degree = match.group(1)
                    row["school_degree_type"] = degree
                    major = (major[:match.start()] + major[match.end():]).strip(" ·•/／|｜,，")
                    row["school_major_name"] = major
            if not row.get("school_degree_rank") and degree:
                for label, rank in degree_rank.items():
                    if label.lower() in degree.lower():
                        row["school_degree_rank"] = rank
                        break
            result.append(row)
        return result

    def normalize_education_annotation(item: dict[str, Any]) -> dict[str, Any]:
        """从 school_name/major 中恢复“学校 专业·学历·教育形式”的独立字段。

        EN: Restore separate fields for "school major·degree·mode of study" from school_name/major.

        JA: school_name/major から「学校 専攻・学歴・就学形態」を個別のフィールドに復元する。
        """
        row = dict(item)
        major = str(row.get("school_major_name") or "").strip()
        # 猎聘模板有时把“学校 专业·学历·教育形式 起止日期”整体放进
        # school_name。必须先恢复为独立字段，不能把整行当学校名称。
        # EN: Liepin templates sometimes put "school major·degree·mode of study start-end date" as a whole into
        #     school_name. It must first be restored into separate fields; the whole line cannot be the school name.
        # JA: Liepin テンプレートは「学校 専攻・学歴・就学形態 期間」を丸ごと school_name に入れることがある。
        #     まず個別のフィールドに復元する必要があり、行全体を学校名にしてはならない。
        school_value = re.sub(r"\s+", " ", str(row.get("school_name") or "")).strip()
        combined = " ".join(x for x in (school_value, major) if x).strip()
        combined_re = re.compile(
            r"^(?P<school>.+?(?:大学院|大学|学院|学校))\s+"
            r"(?P<details>.+?)\s+"
            r"(?P<start>(?:19|20)\d{2}[./-]\d{1,2})\s*[-—–~～至到]+\s*"
            r"(?P<end>(?:19|20)\d{2}[./-]\d{1,2})$",
            re.I,
        )
        cm = combined_re.match(combined)
        if cm:
            row["school_name"] = cm.group("school").strip()
            details = cm.group("details").strip(" ·•/／|｜")
            degree_m = re.search(r"(博士后|博士|硕士|修士|研究生|MBA|EMBA|本科|学士|大专|专科|高中|中专)", details, re.I)
            if degree_m:
                row["school_degree_type"] = row.get("school_degree_type") or degree_m.group(1)
                left = details[:degree_m.start()].strip(" ·•/／|｜")
                right = details[degree_m.end():].strip(" ·•/／|｜")
                row["school_major_name"] = left
                if right and not row.get("school_education_type"):
                    row["school_education_type"] = right
            else:
                row["school_major_name"] = details
            row["school_start_ym"] = re.sub(r"[./-]", "年", cm.group("start")) + "月01日" if re.match(r"^\d{4}年\d{1,2}$", re.sub(r"[./-]", "年", cm.group("start"))) else row.get("school_start_ym") or cm.group("start")
            row["school_end_ym"] = re.sub(r"[./-]", "年", cm.group("end")) + "月01日" if re.match(r"^\d{4}年\d{1,2}$", re.sub(r"[./-]", "年", cm.group("end"))) else row.get("school_end_ym") or cm.group("end")
        elif not major:
            # 日期已经由表格列单独提取时，school_name 仍可能是
            # “华东理工大学 工程管理·本科·统招”。
            # EN: Even when the dates were already extracted from a separate table column, school_name may still be
            #     "华东理工大学 工程管理·本科·统招".
            # JA: 日付が表の列から個別に抽出済みでも、school_name が
            #     「华东理工大学 工程管理·本科·统招」のままになっていることがある。
            school_only = re.match(r"^(?P<school>.+?(?:大学院|大学|学院|学校))\s+(?P<details>.+)$", school_value, re.I)
            if school_only and re.search(r"本科|大专|专科|学士|硕士|博士|MBA|EMBA", school_only.group("details"), re.I):
                row["school_name"] = school_only.group("school").strip()
                details = school_only.group("details").strip(" ·•/／|｜")
                degree_m = re.search(r"(博士后|博士|硕士|修士|研究生|MBA|EMBA|本科|学士|大专|专科|高中|中专)", details, re.I)
                if degree_m:
                    row["school_degree_type"] = row.get("school_degree_type") or degree_m.group(1)
                    row["school_major_name"] = details[:degree_m.start()].strip(" ·•/／|｜")
                    right = details[degree_m.end():].strip(" ·•/／|｜")
                    if right and not row.get("school_education_type"):
                        row["school_education_type"] = right
        # “法律 本科（成人自考）”应拆为专业、学历和教育形式。
        # EN: "法律 本科（成人自考）" (law, bachelor (adult self-study exam)) should be split into major, degree and mode of study.
        # JA: 「法律 本科（成人自考）」（法律、学士（成人独学試験））は専攻・学歴・就学形態に分ける。
        m = re.match(r"^(?P<major>.+?)\s+(?P<degree>本科|大专|专科|学士|硕士|博士|MBA|EMBA)\s*[（(](?P<etype>[^）)]{2,20})[）)]$", major, re.I)
        if m:
            row["school_major_name"] = m.group("major").strip()
            if not row.get("school_degree_type"): row["school_degree_type"] = m.group("degree")
            if not row.get("school_education_type"): row["school_education_type"] = m.group("etype").strip()
        return row

    def strip_project_leading_date(value: Any) -> str:
        text = str(value or "").replace("\r\n", "\n").replace("\r", "\n").strip()
        if not text:
            return ""
        date_prefix = r"(?:19|20)\d{2}\s*(?:(?:[./-]\s*\d{1,2})|年\s*(?:\d{1,2}\s*月)?)?"
        date_range = rf"{date_prefix}\s*(?:(?:至今|现在|目前)|[-—–~～至到]\s*{date_prefix})?"
        return re.sub(
            rf"^\s*[（(]?{date_range}\s*[）)]?\s*(?:[,，、:：]|\s+|\n+)+",
            "", text, count=1,
        ).strip()

    projects = []
    for item in (fallback.get("project_experiences") or []):
        row = dict(item)
        row["description"] = strip_project_leading_date(row.get("description"))
        row["raw_text"] = strip_project_leading_date(row.get("raw_text"))
        projects.append(row)
    trainings = fallback.get("training_experiences") or []
    communication = fallback.get("communication_assessment") or ""
    existing_projects = data.get("project_experiences") or []
    cleaned_existing = []
    for item in existing_projects:
        row = dict(item)
        project_name = str(row.get("project_name") or "").replace("\xa0", " ").strip()
        project_desc = str(row.get("description") or "")
        if len(project_name) > 90 or re.match(r"^[\-–—~至到]?\s*(?:19|20)\d{2}", project_name):
            candidate = re.sub(r"^[\-–—~至到]?\s*(?:19|20)\d{2}(?:年|[./-])\s*\d{1,2}(?:月)?\s*(?:至今|[-—~至到]\s*(?:19|20)\d{2}[^\n]*)?\s*[,，、:]?\s*", "", project_name).strip()
            if "负责" in candidate:
                candidate = candidate.split("负责", 1)[1].strip()
            candidate = re.split(r"[（(。；;]", candidate, maxsplit=1)[0].strip()
            if candidate:
                project_name = candidate[:100]
        if not project_name:
            first_line = next((x.strip() for x in project_desc.splitlines() if x.strip()), "")
            project_name = first_line[:100]
        if project_name and project_desc.strip().startswith(project_name):
            project_desc = project_desc.strip()[len(project_name):].lstrip(" \t\r\n:：")
        row["project_name"] = project_name
        row["description"] = project_desc
        row["description"] = strip_project_leading_date(row.get("description"))
        row["raw_text"] = strip_project_leading_date(row.get("raw_text"))
        cleaned_existing.append(row)

    def normalize_project_row(row: dict[str, Any]) -> dict[str, Any]:
        row = dict(row)
        name = str(row.get("project_name") or "").replace("\xa0", " ").strip()
        desc = str(row.get("description") or "")
        if len(name) > 90 or re.match(r"^[\-–—~至到]?\s*(?:19|20)\d{2}", name):
            candidate = re.sub(r"^[\-–—~至到]?\s*(?:19|20)\d{2}(?:年|[./-])\s*\d{1,2}(?:月)?\s*(?:至今|[-—~至到]\s*(?:19|20)\d{2}[^\n]*)?\s*[,，、:]?\s*", "", name).strip()
            if "负责" in candidate:
                candidate = candidate.split("负责", 1)[1].strip()
            candidate = re.split(r"[（(。；;]", candidate, maxsplit=1)[0].strip()
            if candidate:
                name = candidate[:100]
        if not name:
            name = next((x.strip() for x in desc.splitlines() if x.strip()), "")[:100]
        if name and desc.strip().startswith(name):
            desc = desc.strip()[len(name):].lstrip(" \t\r\n:：")
        row["project_name"] = name
        row["description"] = strip_project_leading_date(desc)
        row["raw_text"] = strip_project_leading_date(row.get("raw_text"))
        return row

    data["project_experiences"] = [normalize_project_row(row) for row in (cleaned_existing or projects)]
    data["training_experiences"] = data.get("training_experiences") or trainings
    existing = data.get("communication_assessment")
    if existing is None:
        data["communication_assessment"] = ([{"content": communication, "raw_text": communication}] if communication else [])
    elif isinstance(existing, str):
        data["communication_assessment"] = ([{"content": existing, "raw_text": existing}] if existing else [])

    fallback_works = [
        work_item(item) for item in (fallback.get("work_experiences") or [])
        if (item.get("company_name") or item.get("start_ym") or item.get("end_ym"))
    ]

    def text_work_items() -> list[dict[str, Any]]:
        normalized = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", clean_text.replace("\r", ""))
        normalized = re.sub(r"(?<=\d)[-./]\s*\n\s*(?=\d)", "-", normalized)
        normalized = re.sub(r"((?:19|20)\d{2}[./-]\d{1,2})\s*\n\s*((?:19|20)\d{2}[./-]\d{1,2})", r"\1-\2", normalized)
        lines = [x.strip(" \t|│") for x in normalized.splitlines()]
        date_re = re.compile(
            r"(?P<start>(?:19|20)\d{2}\s*(?:[./-]|年)\s*\d{1,2}\s*月?)\s*"
            r"(?:[-—–~～至到一]+)\s*(?P<end>(?:(?:19|20)\d{2}\s*(?:[./-]|年)\s*\d{1,2}\s*月?)|至今|现在|目前|現在)", re.I)
        found = []
        for idx, line in enumerate(lines):
            m = date_re.search(line)
            if not m:
                continue
            rest = line[m.end():].strip(" \t:-—–~～|│")
            company_m = re.match(r"(?P<company>.+?(?:有限公司|有限责任公司|股份有限公司|公司|中药厂|药厂|集团|研究所|中心|厂|银行[^\s，、]*|銀行[^\s，、]*|監査法人|Consulting|KPMG))\s*[,，、 ]*\s*(?P<role>.*)$", rest, re.I)
            if not company_m:
                continue
            company = company_m.group("company").strip()
            role = company_m.group("role").strip()
            role_tail = ""
            if re.search(r"[，、]", role):
                role, role_tail = re.split(r"[，、]", role, maxsplit=1)
                role = role.strip()
                role_tail = role_tail.strip(" ，、")
            if "KPMG" in rest.upper():
                km = re.search(r"KPMG監査法人", rest, re.I)
                if km:
                    company = km.group(0)
                    after = rest[km.end():].strip(" ，,、")
                    role = (re.match(r"([^，,、。]+)", after) or [""])[0].strip()
            found.append((idx, m, company, role))
        rows = []
        for n, (idx, m, company, role) in enumerate(found):
            end_idx = found[n + 1][0] if n + 1 < len(found) else len(lines)
            body = "\n".join(x for x in lines[idx + 1:end_idx] if x)
            if role_tail:
                body = role_tail + ("\n" + body if body else "")
            start = re.sub(r"\s+", "", m.group("start"))
            end = re.sub(r"\s+", "", m.group("end"))
            start = re.sub(r"^(\d{4})[年./-]?(\d{1,2})月?$", r"\1年\2月01日", start)
            end = "" if end in {"至今", "现在", "目前", "現在"} else re.sub(r"^(\d{4})[年./-]?(\d{1,2})月?$", r"\1年\2月01日", end)
            rows.append({
                "company_name": company, "company_employees": "", "company_industry": "",
                "position": role, "position_type": "", "position_salary": "",
                "position_dept": "", "position_report_to": "", "position_subordinate": "",
                "employment_type": "全职", "annual_salary_min": "", "annual_salary_max": "",
                "status": "在职" if not end else "离职",
                "position_start": start, "position_resigned": end, "resigned_reason": "",
                "position_responsibilities": body, "position_achievements": "", "raw_text": body,
            })
        return rows

    text_works = text_work_items()

    def text_work_items_v2() -> list[dict[str, Any]]:
        normalized = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", clean_text.replace("\r", ""))
        normalized = re.sub(r"(?<=\d)[-./]\s*\n\s*(?=\d)", "-", normalized)
        normalized = re.sub(r"((?:19|20)\d{2}[./-]\d{1,2})\s*\n\s*((?:19|20)\d{2}[./-]\d{1,2})", r"\1-\2", normalized)
        lines = [x.strip(" \t|│") for x in normalized.splitlines()]
        date_re = re.compile(r"(?P<start>(?:19|20)\d{2}\s*(?:[./-]|年)\s*\d{1,2})\s*(?:至今|现在|目前|現在|[-—–~～至到一]+)\s*(?P<end>(?:(?:19|20)\d{2}\s*(?:[./-]|年)\s*\d{1,2})|至今|现在|目前|現在)?", re.I)
        pair_re = re.compile(r"(?P<start>(?:19|20)\d{2}\s*[./-]\s*\d{1,2})\s+(?P<end>(?:19|20)\d{2}\s*[./-]\s*\d{1,2})\s+(?P<rest>.+)")
        company_pat = re.compile(r"(?:有限公司|有限责任公司|股份有限公司|公司|中药厂|药厂|集团|研究所|中心|厂|银行|銀行|監査法人|Consulting|KPMG|迪士尼)", re.I)
        role_pat = re.compile(r"经理|总监|主管|工程师|专员|代表|分析师|开发|测试|架构师|产品|办事员|销售|Leader|Consultant|監査|审计|实习生|助理|课长|部长|主任|软件", re.I)
        events = []
        for idx, line in enumerate(lines):
            m = date_re.search(line)
            pair = None
            if not m:
                pair = pair_re.search(line)
            if not m and not pair:
                continue
            if pair:
                start, end, rest = pair.group("start"), pair.group("end"), pair.group("rest").strip()
            else:
                start, end = m.group("start"), m.group("end") or ""
                rest = line[m.end():].strip(" \t:-—–~～|│,，、")
            header_idx = idx
            prev = lines[idx - 1] if idx else ""
            if (not rest or not company_pat.search(rest)) and company_pat.search(prev) and len(prev) < 120:
                rest = prev
                header_idx = idx - 1
            next_line = lines[idx + 1] if idx + 1 < len(lines) else ""
            if (not rest or not company_pat.search(rest)) and company_pat.search(next_line) and len(next_line) < 120:
                rest = next_line
            if not company_pat.search(rest):
                continue
            cm = re.match(r"(?P<company>.+?(?:有限公司|有限责任公司|股份有限公司|公司|中药厂|药厂|集团|研究所|中心|厂|银行[^\s，、]*|銀行[^\s，、]*|監査法人|Consulting|KPMG|迪士尼))\s*[,，、 ]*\s*(?P<tail>.*)$", rest, re.I)
            if not cm:
                continue
            company, tail = cm.group("company").strip(), cm.group("tail").strip()
            role, prefix_body = "", ""
            if tail:
                role = re.split(r"[，、。]", tail, maxsplit=1)[0].strip()
                if len(role) > 45 or not role_pat.search(role):
                    role = ""
                if role:
                    prefix_body = tail[len(role):].lstrip(" ，、。")
                else:
                    prefix_body = tail
            search_from = idx + (2 if rest == next_line and next_line else 1)
            role_idx = None
            for j in range(search_from, min(len(lines), search_from + 12)):
                candidate = lines[j].strip()
                if not candidate or re.search(r"工作描述|职责业绩|工作内容|所在部门|工作地点|薪资|汇报对象|下属人数|公司规模|公司行业", candidate, re.I):
                    continue
                if role_pat.search(candidate) and len(candidate) <= 60:
                    role = role or candidate
                    role_idx = j
                    break
            body_start = (role_idx + 1) if role_idx is not None else search_from
            body = "\n".join(x for x in lines[body_start:] if x)
            events.append({"idx": header_idx, "start": start, "end": end, "company": company, "role": role, "prefix": prefix_body, "body": body})
        rows = []
        for n, event in enumerate(events):
            next_idx = events[n + 1]["idx"] if n + 1 < len(events) else len(lines)
            segment = "\n".join(lines[event["idx"] + 1:next_idx])
            body = ((event["prefix"] + "\n") if event["prefix"] else "") + segment
            start = re.sub(r"\s+", "", event["start"])
            end = re.sub(r"\s+", "", event["end"])
            start = re.sub(r"^(\d{4})[年./-](\d{1,2})$", r"\1年\2月01日", start)
            end = "" if end in {"至今", "现在", "目前", "現在"} else re.sub(r"^(\d{4})[年./-](\d{1,2})$", r"\1年\2月01日", end)
            rows.append({"company_name": event["company"], "company_employees": "", "company_industry": "", "position": event["role"], "position_type": "", "position_salary": "", "position_dept": "", "position_report_to": "", "position_subordinate": "", "employment_type": "全职", "annual_salary_min": "", "annual_salary_max": "", "status": "在职" if not end else "离职", "position_start": start, "position_resigned": end, "resigned_reason": "", "position_responsibilities": body.strip(), "position_achievements": "", "raw_text": body.strip()})
        return rows

    text_works_v2 = text_work_items_v2()

    def text_work_items_labelled() -> list[dict[str, Any]]:
        normalized = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", clean_text.replace("\r", ""))
        lines = [x.strip(" |│") for x in normalized.splitlines() if x.strip()]
        date_re = re.compile(r"(?P<start>(?:19|20)\d{2}\s*年\s*\d{1,2}\s*月?)\s*[-—–~～至到]+\s*(?P<end>(?:19|20)\d{2}\s*年\s*\d{1,2}\s*月?|至今|现在|目前)")
        events = []
        for idx, line in enumerate(lines):
            m = re.search(r"(?:时间|任职时间|工作时间)\s*[:：]?\s*" + date_re.pattern, line, re.I)
            if not m:
                continue
            company = ""
            role = ""
            company_idx = role_idx = None
            for j in range(idx + 1, min(idx + 6, len(lines))):
                if re.match(r"(?:公司|单位|企业)\s*[:：]", lines[j], re.I):
                    company = re.sub(r"^(?:公司|单位|企业)\s*[:：]\s*", "", lines[j], flags=re.I).strip()
                    company_idx = j
                elif re.match(r"(?:职位|职务|岗位)\s*[:：]", lines[j], re.I):
                    role = re.sub(r"^(?:职位|职务|岗位)\s*[:：]\s*", "", lines[j], flags=re.I).strip()
                    role_idx = j
                if company and role:
                    break
            if company:
                events.append((idx, m, company, role, company_idx or idx, role_idx or idx))
        rows = []
        for n, (idx, m, company, role, company_idx, role_idx) in enumerate(events):
            next_idx = events[n + 1][0] if n + 1 < len(events) else len(lines)
            segment = lines[role_idx + 1:next_idx]
            body = "\n".join(x for x in segment if not re.match(r"^(?:时间|公司|职位|职务|岗位)\s*[:：]", x, re.I)).strip()
            start = re.sub(r"\s+", "", m.group("start"))
            end = re.sub(r"\s+", "", m.group("end"))
            start = re.sub(r"^(\d{4})年(\d{1,2})月?$", r"\1年\2月01日", start)
            end = "" if end in {"至今", "现在", "目前"} else re.sub(r"^(\d{4})年(\d{1,2})月?$", r"\1年\2月01日", end)
            rows.append({"company_name": company, "company_employees": "", "company_industry": "", "position": role, "position_type": "", "position_salary": "", "position_dept": "", "position_report_to": "", "position_subordinate": "", "employment_type": "全职", "annual_salary_min": "", "annual_salary_max": "", "status": "在职" if not end else "离职", "position_start": start, "position_resigned": end, "resigned_reason": "", "position_responsibilities": body, "position_achievements": "", "raw_text": body})
        return rows

    text_works_labelled = text_work_items_labelled()

    def text_work_items_structured() -> list[dict[str, Any]]:
        if not re.search(r"公司(?:性质|规模|行业)\s*[:：]|工作职责和业绩\s*[:：]", clean_text, re.I):
            return []
        normalized = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", clean_text.replace("\r", ""))
        lines = [re.sub(r"\s+", " ", x).strip(" |│") for x in normalized.splitlines() if x.strip(" |│")]
        date_re = re.compile(r"^(?P<start>(?:19|20)\d{2}\s*[./年]\s*\d{1,2})\s*[-—–~～至到]+\s*(?P<end>(?:19|20)\d{2}\s*[./年]\s*\d{1,2}|至今|现在|目前)$")
        events = [(i, date_re.match(line)) for i, line in enumerate(lines) if date_re.match(line)]
        rows = []
        for n, (idx, dm) in enumerate(events):
            end_idx = events[n + 1][0] if n + 1 < len(events) else len(lines)
            block = lines[idx + 1:end_idx]
            if not block:
                continue
            company_i = 0 if block and not re.match(r"^(?:公司(?:性质|规模|行业|描述)|职位类别|所在地区|所在部门|工作职责和业绩)\s*[:：]?", block[0], re.I) else next((j for j, x in enumerate(block) if x and not re.match(r"^(?:公司(?:性质|规模|行业|描述)|职位类别|所在地区|所在部门|工作职责和业绩)\s*[:：]?", x, re.I)), None)
            if company_i is None:
                continue
            company = re.sub(r"^(?:公司名称|公司|单位)\s*[:：]\s*", "", block[company_i], flags=re.I).strip()
            meta_i = next((j for j, x in enumerate(block[company_i + 1:], company_i + 1) if re.match(r"^职位类别\s*[:：]", x, re.I)), None)
            search_end = meta_i if meta_i is not None else len(block)
            role = ""
            if meta_i is not None:
                k = meta_i - 1
                while k > company_i and (not block[k] or block[k] == "|"):
                    k -= 1
                role = block[k].strip() if k > company_i else ""
            if not role:
                for x in block[company_i + 1:search_end]:
                    if x and not re.match(r"^(?:公司(?:性质|规模|行业|描述)|所在地区|所在部门|工作职责和业绩)\s*[:：]?|^\|$|^[A-ZＡ-Ｚ][.．、]", x, re.I):
                        role = x.strip(); break
            if role in {"未填写", "负责", "担当", "工作"} or not role or re.match(r"^[\d\-~～]+(?:人|个月)?$", role):
                role_candidates = [x for x in block[company_i + 1:] if len(x) <= 30 and re.search(r"工程师|经理|主管|专员|代表|分析师|开发|设计师|产品|销售|顾问|教师|研究员|部长|担当", x, re.I) and not re.search(r"公司描述|工作职责|公司行业|所在地区|所在部门|^[0-9一二三四五六七八九十]+[.．、]|^(?:提供|负责|收集|为公司)", x, re.I)]
                if role_candidates:
                    role = role_candidates[0].strip()
            dept = ""
            for x in block:
                if re.match(r"^所在部门\s*[:：]", x, re.I):
                    dept = re.sub(r"^所在部门\s*[:：]\s*", "", x, flags=re.I).strip(); break
            employees = industry = ""
            for x in block:
                if re.match(r"^公司规模\s*[:：]", x, re.I): employees = re.sub(r"^公司规模\s*[:：]\s*", "", x, flags=re.I).strip()
                if re.match(r"^公司行业\s*[:：]", x, re.I): industry = re.sub(r"^公司行业\s*[:：]\s*", "", x, flags=re.I).strip()
            body_i = next((j for j, x in enumerate(block) if re.match(r"^工作职责和业绩\s*[:：]", x, re.I)), None)
            body = "\n".join(block[body_i + 1:]) if body_i is not None else ""
            start = re.sub(r"\s+", "", dm.group("start")).replace(".", "年").replace("/", "年")
            end = re.sub(r"\s+", "", dm.group("end"))
            if end not in {"至今", "现在", "目前"}: end = end.replace(".", "年").replace("/", "年")
            start = re.sub(r"^(\d{4})年(\d{1,2})$", r"\1年\2月01日", start)
            end = "" if end in {"至今", "现在", "目前"} else re.sub(r"^(\d{4})年(\d{1,2})$", r"\1年\2月01日", end)
            rows.append({"company_name": company, "company_employees": employees, "company_industry": industry, "position": role, "position_type": "", "position_salary": "", "position_dept": dept, "position_report_to": "", "position_subordinate": "", "employment_type": "全职", "annual_salary_min": "", "annual_salary_max": "", "status": "在职" if not end else "离职", "position_start": start, "position_resigned": end, "resigned_reason": "", "position_responsibilities": body.strip(), "position_achievements": "", "raw_text": body.strip()})
        dedup = {}
        for row in rows:
            key = (re.sub(r"[（）]", lambda m: "(" if m.group(0) == "（" else ")", row["company_name"]), row.get("position", ""), row["position_start"], row["position_resigned"])
            if key not in dedup:
                dedup[key] = row
            else:
                old = dedup[key]
                old_role = str(old.get("position") or "")
                new_role = str(row.get("position") or "")
                old_bad = (not old_role or old_role in {"未填写", "负责", "担当", "工作"} or len(old_role) > 30 or re.search(r"[；;。]", old_role) or re.match(r"^[\d\-~～]+(?:人|个月)?$", old_role) or re.match(r"^\d+[.．、]", old_role) or re.match(r"^(?:提供|负责|收集|为公司)", old_role, re.I))
                new_good = (new_role and new_role not in {"未填写", "担当"} and not re.match(r"^[\d\-~～]+(?:人|个月)?$", new_role) and not re.match(r"^\d+[.．、]", new_role))
                if old_bad and new_good:
                    row["position_responsibilities"] = max((old.get("position_responsibilities", ""), row.get("position_responsibilities", "")), key=len)
                    dedup[key] = row
                elif len(row["position_responsibilities"]) > len(old["position_responsibilities"]):
                    old["position_responsibilities"] = row["position_responsibilities"]
        return list(dedup.values())

    text_works_structured = text_work_items_structured()

    def text_work_items_inline() -> list[dict[str, Any]]:
        rows = []
        inline_date = re.compile(r"^(?P<start>(?:19|20)\d{2}[./年]\s*\d{1,2})\s*[-—–~～至到]+\s*(?P<end>(?:19|20)\d{2}[./年]\s*\d{1,2}|至今|现在|目前)\s+(?P<rest>.+)$")
        for line in clean_text.replace("\r", "").splitlines():
            line = re.sub(r"\s+", " ", line).strip()
            m = inline_date.match(line)
            if not m or not re.search(r"[:：]", m.group("rest")):
                continue
            before, body = re.split(r"[:：]", m.group("rest"), maxsplit=1)
            role_m = re.match(r"(?P<role>.*?(?:工程师|负责人|经理|主管|专员|代表|分析师|设计师|总监))\s+(?P<company>.+)$", before.strip(), re.I)
            if not role_m:
                continue
            start = re.sub(r"\s+", "", m.group("start")).replace(".", "年").replace("/", "年")
            end = re.sub(r"\s+", "", m.group("end"))
            if end not in {"至今", "现在", "目前"}: end = end.replace(".", "年").replace("/", "年")
            start = re.sub(r"^(\d{4})年(\d{1,2})$", r"\1年\2月01日", start)
            end = "" if end in {"至今", "现在", "目前"} else re.sub(r"^(\d{4})年(\d{1,2})$", r"\1年\2月01日", end)
            rows.append({"company_name": role_m.group("company").strip(), "company_employees": "", "company_industry": "", "position": role_m.group("role").strip(), "position_type": "", "position_salary": "", "position_dept": "", "position_report_to": "", "position_subordinate": "", "employment_type": "全职", "annual_salary_min": "", "annual_salary_max": "", "status": "在职" if not end else "离职", "position_start": start, "position_resigned": end, "resigned_reason": "", "position_responsibilities": body.strip(), "position_achievements": "", "raw_text": body.strip()})
        return rows

    text_works_inline = text_work_items_inline()

    def text_work_items_labelled_v2() -> list[dict[str, Any]]:
        if not re.search(r"工作部门\s*[:：]|工作职位\s*[:：]|汇报对象\s*[:：]", clean_text):
            return []
        lines = [re.sub(r"\s+", " ", x).strip(" |│") for x in clean_text.replace("\r", "").splitlines() if x.strip(" |│")]
        section_start = next((i for i, x in enumerate(lines) if re.search(r"^(?:工作经历|工作经验|工作/实习经历|工作实习经历|职务经历|職務経歴|職務經歷|仕事経験|職務履歴|職歴|経歴|Work Experience)", x, re.I)), None)
        if section_start is not None:
            section_end = next((i for i in range(section_start + 1, len(lines)) if re.search(r"^(?:教育经历|教育背景|教育程度|教育經歷|项目经历|项目经验|项目经验|语言能力|技能及其他|证书|资格|培训|自我评价|自己PR|附加信息)", lines[i], re.I)), len(lines))
            lines = lines[section_start + 1:section_end]
        date_line = re.compile(r"^(?P<start>(?:19|20)\d{2}\s*年\s*\d{1,2}\s*月?)\s*(?:一|至|到|-|—|~|～)\s*(?P<end>(?:19|20)\d{2}\s*年\s*\d{1,2}\s*月?|至今|现在|目前)\s*(?P<rest>.+)$")
        events = [(i, date_line.match(x)) for i, x in enumerate(lines) if date_line.match(x)]
        rows = []
        for n, (idx, m) in enumerate(events):
            end_idx = events[n + 1][0] if n + 1 < len(events) else len(lines)
            company = re.split(r"\s*[（(]", m.group("rest"), maxsplit=1)[0].strip()
            if len(company) < 2 or re.search(r"教育经历|工作经历|工作描述", company):
                continue
            block = lines[idx + 1:end_idx]
            def label(name: str) -> str:
                for j, x in enumerate(block):
                    if re.match(r"^" + name + r"\s*[:：]", x):
                        value = re.sub(r"^" + name + r"\s*[:：]\s*", "", x).strip()
                        return value or (block[j + 1].strip() if j + 1 < len(block) else "")
                return ""
            dept, position, report_to, industry = label("工作部门"), label("工作职位"), label("汇报对象"), label("所属行业")
            body_i = next((j for j, x in enumerate(block) if re.match(r"^工作描述\s*[:：]", x)), None)
            body_end = next((j for j, x in enumerate(block) if body_i is not None and j > body_i and re.match(r"^(?:汇报对象|离职原因|工作业绩)\s*[:：]", x)), len(block))
            body = "\n".join(block[body_i + 1:body_end]) if body_i is not None else ""
            ach_i = next((j for j, x in enumerate(block) if re.match(r"^工作业绩\s*[:：]", x)), None)
            achievements = "\n".join(block[ach_i + 1:]) if ach_i is not None else ""
            start = re.sub(r"\s+", "", m.group("start")); end = re.sub(r"\s+", "", m.group("end"))
            start = re.sub(r"^(\d{4})年(\d{1,2})月?$", r"\1年\2月01日", start)
            end = "" if end in {"至今", "现在", "目前"} else re.sub(r"^(\d{4})年(\d{1,2})月?$", r"\1年\2月01日", end)
            position = re.sub(r"\s*[（(]全职[）)]", "", position).strip()
            rows.append({"company_name": company, "company_employees": "", "company_industry": industry, "position": position, "position_type": "", "position_salary": "", "position_dept": dept, "position_report_to": report_to, "position_subordinate": "", "employment_type": "全职", "annual_salary_min": "", "annual_salary_max": "", "status": "在职" if not end else "离职", "position_start": start, "position_resigned": end, "resigned_reason": "", "position_responsibilities": body.strip(), "position_achievements": achievements.strip(), "raw_text": "\n".join(block)})
        return rows

    text_works_labelled_v2_rows = text_work_items_labelled_v2()

    def text_work_items_explicit_v3() -> list[dict[str, Any]]:
        lines = [re.sub(r"\s+", " ", x).strip(" |│") for x in clean_text.replace("\r", "").splitlines() if x.strip(" |│")]
        section_start = next((i for i, x in enumerate(lines) if re.search(r"^(?:工作经历|工作经验|工作/实习经历|工作实习经历|职务经历|職務経歴|職務經歷|仕事経験|職務履歴|職歴|経歴|Work Experience)", x, re.I)), None)
        if section_start is not None:
            section_end = next((i for i in range(section_start + 1, len(lines)) if re.search(r"^(?:教育经历|教育背景|教育程度|教育經歷|项目经历|项目经验|语言能力|技能及其他|证书|资格|培训|自我评价|自己PR|附加信息)", lines[i], re.I)), len(lines))
            lines = lines[section_start + 1:section_end]
        date_re = re.compile(r"^[（(]?\s*(?P<start>(?:19|20)\d{2}\s*(?:年|[./-])\s*\d{1,2}\s*月?)\s*(?:一|至|到|-|—|–|~|～|〜)\s*(?P<end>(?:19|20)\d{2}\s*(?:年|[./-])\s*\d{1,2}\s*月?|至今|现在|目前|現在|現在まで)?(?:\s*[，,、][^）)]*)?\s*[）)]?\s*(?P<rest>.*)$", re.I)
        date_only = re.compile(r"^[（(]?\s*(?P<start>(?:19|20)\d{2}\s*(?:年|[./-])\s*\d{1,2}\s*月?)\s*(?:一|至|到|-|—|–|~|～|〜)\s*(?P<end>至今|现在|目前|現在|現在まで|(?:19|20)\d{2}\s*(?:年|[./-])\s*\d{1,2}\s*月?)\s*(?:[，,、][^）)]*)?\s*[）)]?\s*$", re.I)
        events = []
        for i, line in enumerate(lines):
            m = date_re.match(line) or date_only.match(line)
            if m:
                events.append((i, m))
        rows: list[dict[str, Any]] = []
        def norm_date(value: str, current: bool = False) -> str:
            value = re.sub(r"\s+", "", value or "")
            if value in {"至今", "现在", "目前", "現在", "現在まで"}: return ""
            value = value.replace(".", "年").replace("/", "年").replace("-", "年")
            return re.sub(r"^(\d{4})年(\d{1,2})月?$", r"\1年\2月01日", value)
        def is_company(value: str) -> bool:
            value = re.sub(r"\s+", " ", str(value or "")).strip(" ：:|-—–~～")
            if not value or len(value) > 140:
                return False
            return bool(re.search(company_suffix, value, re.I) or re.search(r"(?:銀行|銀行本店|監査法人|Consulting|Corporation|Company)", value, re.I))
        inline_events = []
        inline_re = re.compile(r"^(?P<role>[^|｜]{1,80})\s*[|｜]\s*(?P<company>[^|｜]{2,140})\s*[|｜]\s*(?P<start>(?:19|20)\d{2}\s*年\s*\d{1,2}\s*月?)\s*(?:(?:至|到|一|-|—|~|～)\s*(?P<end>(?:19|20)\d{2}\s*年\s*\d{1,2}\s*月?)|(?P<current>至今|现在|目前))\s*$", re.I)
        for i, line in enumerate(lines):
            mm = inline_re.match(line)
            if mm and is_company(mm.group("company")):
                inline_events.append((i, mm))
        for n, (idx, mm) in enumerate(inline_events):
            stop = inline_events[n + 1][0] if n + 1 < len(inline_events) else len(lines)
            body = "\n".join(lines[idx + 1:stop]).strip()
            end_value = mm.group("end") or mm.group("current") or ""
            rows.append({"company_name": mm.group("company").strip(), "company_employees": "", "company_industry": "", "position": mm.group("role").strip(), "position_type": "", "position_salary": "", "position_dept": "", "position_report_to": "", "position_subordinate": "", "employment_type": "全职", "annual_salary_min": "", "annual_salary_max": "", "status": "在职" if mm.group("current") else "离职", "position_start": norm_date(mm.group("start")), "position_resigned": norm_date(end_value), "resigned_reason": "", "position_responsibilities": body, "position_achievements": "", "raw_text": body})
        for n, (idx, m) in enumerate(events):
            stop = events[n + 1][0] if n + 1 < len(events) else len(lines)
            rest = (m.groupdict().get("rest") or "").strip(" ：:|-—–~～")
            rest = re.sub(r"^(?:在|于|任职于|就职于)\s*", "", rest)
            rest = re.sub(r"^[（(\[][^）)\]]*(?:年|月|year|month)[^）)\]]*[）)\]]\s*", "", rest, flags=re.I).strip()
            following = lines[idx + 1:stop]
            company, role, consumed = "", "", 0
            if is_company(rest):
                company_match = re.match(rf"(?P<company>.{{2,120}}?{company_suffix})", rest, re.I)
                company = company_match.group("company").strip() if company_match else re.split(r"\s*[（(]", rest, maxsplit=1)[0].strip()
                bank_split = re.match(r"^(.+?銀行)(.*)$", company, re.I)
                if bank_split and bank_split.group(2).strip():
                    company, role = bank_split.group(1).strip(), bank_split.group(2).strip()
                consulting_split = re.match(r"^(.+?Consulting)\s*[,，]\s*(.+)$", company, re.I)
                if consulting_split:
                    company, role = consulting_split.group(1).strip(), consulting_split.group(2).strip()
                jp_split = re.match(r"^(.+?(?:銀行|監査法人))(?:\s+|)(.+)$", company, re.I)
                tokens = company.split(None, 1)
                if not role and jp_split and jp_split.group(2).strip():
                    company, role = jp_split.group(1).strip(), jp_split.group(2).strip()
                elif not role and len(tokens) == 2 and re.search(r"(?:銀行|監査法人|Consulting|Corporation|Company)$", tokens[0], re.I):
                    company, role = tokens[0].strip(), tokens[1].strip()
                tail = rest[len(company):].strip(" ：:|-—–~～")
                if tail and not role and not re.search(r"公司性质|公司规模|公司行业|国有企业|人\s*[|｜]|芜湖|贵阳", tail): role = tail
                elif following and len(following[0]) <= 50 and not re.search(r"^(?:工作|职责|项目|事業|売上|従業員|所在|薪酬|汇报|下属|所属|公司)", following[0], re.I) and not is_company(following[0]):
                    role, consumed = following[0].strip(" ：:"), 1
            elif rest and not re.search(r"^(?:工作|职责|项目|事業|売上|従業員|所在|薪酬|汇报|下属|所属|公司)", rest, re.I):
                role = rest
                if following and is_company(following[0]):
                    company, consumed = extract_company_name(following[0]), 1
            else:
                if idx > 0 and is_company(lines[idx - 1]):
                    company = extract_company_name(lines[idx - 1])
                    if following and len(following[0]) <= 60 and not is_company(following[0]):
                        role, consumed = following[0].strip(" ：:"), 1
                if following and not is_company(following[0]) and len(following[0]) <= 60:
                    if not role:
                        role, consumed = following[0].strip(" ：:"), 1
                    if not company and len(following) > consumed and is_company(following[consumed]):
                        company = extract_company_name(following[consumed]); consumed += 1
                elif following and is_company(following[0]):
                    company, consumed = extract_company_name(following[0]), 1
            if not company or not is_company(company):
                continue
            block = following[consumed:]
            raw = "\n".join(block)
            def lab(*names: str) -> str:
                pat = r"^(?:" + "|".join(re.escape(x) for x in names) + r")\s*[:：]?\s*(.*)$"
                for j, line in enumerate(block):
                    mm = re.match(pat, line, re.I)
            role = ""
            if meta_i is not None:
                k = meta_i - 1
                while k > company_i and (not block[k] or block[k] == "|"):
                    k -= 1
                role = block[k].strip() if k > company_i else ""
            if not role:
                for x in block[company_i + 1:search_end]:
                    if x and not re.match(r"^(?:公司(?:性质|规模|行业|描述)|所在地区|所在部门|工作职责和业绩)\s*[:：]?|^\|$|^[A-ZＡ-Ｚ][.．、]", x, re.I):
                        role = x.strip(); break
            if role in {"未填写", "负责", "担当", "工作"} or not role or re.match(r"^[\d\-~～]+(?:人|个月)?$", role):
                role_candidates = [x for x in block[company_i + 1:] if len(x) <= 30 and re.search(r"工程师|经理|主管|专员|代表|分析师|开发|设计师|产品|销售|顾问|教师|研究员|部长|担当", x, re.I) and not re.search(r"公司描述|工作职责|公司行业|所在地区|所在部门|^[0-9一二三四五六七八九十]+[.．、]|^(?:提供|负责|收集|为公司)", x, re.I)]
                if role_candidates:
                    role = role_candidates[0].strip()
            dept = ""
            for x in block:
                if re.match(r"^所在部门\s*[:：]", x, re.I):
                    dept = re.sub(r"^所在部门\s*[:：]\s*", "", x, flags=re.I).strip(); break
            employees = industry = ""
            for x in block:
                if re.match(r"^公司规模\s*[:：]", x, re.I): employees = re.sub(r"^公司规模\s*[:：]\s*", "", x, flags=re.I).strip()
                if re.match(r"^公司行业\s*[:：]", x, re.I): industry = re.sub(r"^公司行业\s*[:：]\s*", "", x, flags=re.I).strip()
            body_i = next((j for j, x in enumerate(block) if re.match(r"^工作职责和业绩\s*[:：]", x, re.I)), None)
            body = "\n".join(block[body_i + 1:]) if body_i is not None else ""
            start = re.sub(r"\s+", "", dm.group("start")).replace(".", "年").replace("/", "年")
            end = re.sub(r"\s+", "", dm.group("end"))
            if end not in {"至今", "现在", "目前"}: end = end.replace(".", "年").replace("/", "年")
            start = re.sub(r"^(\d{4})年(\d{1,2})$", r"\1年\2月01日", start)
            end = "" if end in {"至今", "现在", "目前"} else re.sub(r"^(\d{4})年(\d{1,2})$", r"\1年\2月01日", end)
            rows.append({"company_name": company, "company_employees": employees, "company_industry": industry, "position": role, "position_type": "", "position_salary": "", "position_dept": dept, "position_report_to": "", "position_subordinate": "", "employment_type": "全职", "annual_salary_min": "", "annual_salary_max": "", "status": "在职" if not end else "离职", "position_start": start, "position_resigned": end, "resigned_reason": "", "position_responsibilities": body.strip(), "position_achievements": "", "raw_text": body.strip()})
        dedup = {}
        for row in rows:
            key = (re.sub(r"[（）]", lambda m: "(" if m.group(0) == "（" else ")", row["company_name"]), row.get("position", ""), row["position_start"], row["position_resigned"])
            if key not in dedup:
                dedup[key] = row
            else:
                old = dedup[key]
                old_role = str(old.get("position") or "")
                new_role = str(row.get("position") or "")
                old_bad = (not old_role or old_role in {"未填写", "负责", "担当", "工作"} or len(old_role) > 30 or re.search(r"[；;。]", old_role) or re.match(r"^[\d\-~～]+(?:人|个月)?$", old_role) or re.match(r"^\d+[.．、]", old_role) or re.match(r"^(?:提供|负责|收集|为公司)", old_role, re.I))
                new_good = (new_role and new_role not in {"未填写", "担当"} and not re.match(r"^[\d\-~～]+(?:人|个月)?$", new_role) and not re.match(r"^\d+[.．、]", new_role))
                if old_bad and new_good:
                    row["position_responsibilities"] = max((old.get("position_responsibilities", ""), row.get("position_responsibilities", "")), key=len)
                    dedup[key] = row
                elif len(row["position_responsibilities"]) > len(old["position_responsibilities"]):
                    old["position_responsibilities"] = row["position_responsibilities"]
        return list(dedup.values())

    text_works_structured = text_work_items_structured()

    def text_work_items_inline() -> list[dict[str, Any]]:
        rows = []
        inline_date = re.compile(r"^(?P<start>(?:19|20)\d{2}[./年]\s*\d{1,2})\s*[-—–~～至到]+\s*(?P<end>(?:19|20)\d{2}[./年]\s*\d{1,2}|至今|现在|目前)\s+(?P<rest>.+)$")
        for line in clean_text.replace("\r", "").splitlines():
            line = re.sub(r"\s+", " ", line).strip()
            m = inline_date.match(line)
            if not m or not re.search(r"[:：]", m.group("rest")):
                continue
            before, body = re.split(r"[:：]", m.group("rest"), maxsplit=1)
            role_m = re.match(r"(?P<role>.*?(?:工程师|负责人|经理|主管|专员|代表|分析师|设计师|总监))\s+(?P<company>.+)$", before.strip(), re.I)
            if not role_m:
                continue
            start = re.sub(r"\s+", "", m.group("start")).replace(".", "年").replace("/", "年")
            end = re.sub(r"\s+", "", m.group("end"))
            if end not in {"至今", "现在", "目前"}: end = end.replace(".", "年").replace("/", "年")
            start = re.sub(r"^(\d{4})年(\d{1,2})$", r"\1年\2月01日", start)
            end = "" if end in {"至今", "现在", "目前"} else re.sub(r"^(\d{4})年(\d{1,2})$", r"\1年\2月01日", end)
            rows.append({"company_name": role_m.group("company").strip(), "company_employees": "", "company_industry": "", "position": role_m.group("role").strip(), "position_type": "", "position_salary": "", "position_dept": "", "position_report_to": "", "position_subordinate": "", "employment_type": "全职", "annual_salary_min": "", "annual_salary_max": "", "status": "在职" if not end else "离职", "position_start": start, "position_resigned": end, "resigned_reason": "", "position_responsibilities": body.strip(), "position_achievements": "", "raw_text": body.strip()})
        return rows

    text_works_inline = text_work_items_inline()

    def text_work_items_labelled_v2() -> list[dict[str, Any]]:
        if not re.search(r"工作部门\s*[:：]|工作职位\s*[:：]|汇报对象\s*[:：]", clean_text):
            return []
        lines = [re.sub(r"\s+", " ", x).strip(" |│") for x in clean_text.replace("\r", "").splitlines() if x.strip(" |│")]
        section_start = next((i for i, x in enumerate(lines) if re.search(r"^(?:工作经历|工作经验|工作/实习经历|工作实习经历|职务经历|職務経歴|職務經歷|仕事経験|職務履歴|職歴|経歴|Work Experience)", x, re.I)), None)
        if section_start is not None:
            section_end = next((i for i in range(section_start + 1, len(lines)) if re.search(r"^(?:教育经历|教育背景|教育程度|教育經歷|项目经历|项目经验|项目经验|语言能力|技能及其他|证书|资格|培训|自我评价|自己PR|附加信息)", lines[i], re.I)), len(lines))
            lines = lines[section_start + 1:section_end]
        date_line = re.compile(r"^(?P<start>(?:19|20)\d{2}\s*年\s*\d{1,2}\s*月?)\s*(?:一|至|到|-|—|~|～)\s*(?P<end>(?:19|20)\d{2}\s*年\s*\d{1,2}\s*月?|至今|现在|目前)\s*(?P<rest>.+)$")
        events = [(i, date_line.match(x)) for i, x in enumerate(lines) if date_line.match(x)]
        rows = []
        for n, (idx, m) in enumerate(events):
            end_idx = events[n + 1][0] if n + 1 < len(events) else len(lines)
            company = re.split(r"\s*[（(]", m.group("rest"), maxsplit=1)[0].strip()
            if len(company) < 2 or re.search(r"教育经历|工作经历|工作描述", company):
                continue
            block = lines[idx + 1:end_idx]
            def label(name: str) -> str:
                for j, x in enumerate(block):
                    if re.match(r"^" + name + r"\s*[:：]", x):
                        value = re.sub(r"^" + name + r"\s*[:：]\s*", "", x).strip()
                        return value or (block[j + 1].strip() if j + 1 < len(block) else "")
                return ""
            dept, position, report_to, industry = label("工作部门"), label("工作职位"), label("汇报对象"), label("所属行业")
            body_i = next((j for j, x in enumerate(block) if re.match(r"^工作描述\s*[:：]", x)), None)
            body_end = next((j for j, x in enumerate(block) if body_i is not None and j > body_i and re.match(r"^(?:汇报对象|离职原因|工作业绩)\s*[:：]", x)), len(block))
            body = "\n".join(block[body_i + 1:body_end]) if body_i is not None else ""
            ach_i = next((j for j, x in enumerate(block) if re.match(r"^工作业绩\s*[:：]", x)), None)
            achievements = "\n".join(block[ach_i + 1:]) if ach_i is not None else ""
            start = re.sub(r"\s+", "", m.group("start")); end = re.sub(r"\s+", "", m.group("end"))
            start = re.sub(r"^(\d{4})年(\d{1,2})月?$", r"\1年\2月01日", start)
            end = "" if end in {"至今", "现在", "目前"} else re.sub(r"^(\d{4})年(\d{1,2})月?$", r"\1年\2月01日", end)
            position = re.sub(r"\s*[（(]全职[）)]", "", position).strip()
            rows.append({"company_name": company, "company_employees": "", "company_industry": industry, "position": position, "position_type": "", "position_salary": "", "position_dept": dept, "position_report_to": report_to, "position_subordinate": "", "employment_type": "全职", "annual_salary_min": "", "annual_salary_max": "", "status": "在职" if not end else "离职", "position_start": start, "position_resigned": end, "resigned_reason": "", "position_responsibilities": body.strip(), "position_achievements": achievements.strip(), "raw_text": "\n".join(block)})
        return rows

    text_works_labelled_v2_rows = text_work_items_labelled_v2()

    def text_work_items_explicit_v3() -> list[dict[str, Any]]:
        lines = [re.sub(r"\s+", " ", x).strip(" |│") for x in clean_text.replace("\r", "").splitlines() if x.strip(" |│")]
        section_start = next((i for i, x in enumerate(lines) if re.search(r"^(?:工作经历|工作经验|工作/实习经历|工作实习经历|职务经历|職務経歴|職務經歷|仕事経験|職務履歴|職歴|経歴|Work Experience)", x, re.I)), None)
        if section_start is not None:
            section_end = next((i for i in range(section_start + 1, len(lines)) if re.search(r"^(?:教育经历|教育背景|教育程度|教育經歷|项目经历|项目经验|语言能力|技能及其他|证书|资格|培训|自我评价|自己PR|附加信息)", lines[i], re.I)), len(lines))
            lines = lines[section_start + 1:section_end]
        date_re = re.compile(r"^[（(]?\s*(?P<start>(?:19|20)\d{2}\s*(?:年|[./-])\s*\d{1,2}\s*月?)\s*(?:一|至|到|-|—|–|~|～|〜)\s*(?P<end>(?:19|20)\d{2}\s*(?:年|[./-])\s*\d{1,2}\s*月?|至今|现在|目前|現在|現在まで)?(?:\s*[，,、][^）)]*)?\s*[）)]?\s*(?P<rest>.*)$", re.I)
        date_only = re.compile(r"^[（(]?\s*(?P<start>(?:19|20)\d{2}\s*(?:年|[./-])\s*\d{1,2}\s*月?)\s*(?:一|至|到|-|—|–|~|～|〜)\s*(?P<end>至今|现在|目前|現在|現在まで|(?:19|20)\d{2}\s*(?:年|[./-])\s*\d{1,2}\s*月?)\s*(?:[，,、][^）)]*)?\s*[）)]?\s*$", re.I)
        events = []
        for i, line in enumerate(lines):
            m = date_re.match(line) or date_only.match(line)
            if m:
                events.append((i, m))
        rows: list[dict[str, Any]] = []
        def norm_date(value: str, current: bool = False) -> str:
            value = re.sub(r"\s+", "", value or "")
            if value in {"至今", "现在", "目前", "現在", "現在まで"}: return ""
            value = value.replace(".", "年").replace("/", "年").replace("-", "年")
            return re.sub(r"^(\d{4})年(\d{1,2})月?$", r"\1年\2月01日", value)
        def is_company(value: str) -> bool:
            value = re.sub(r"\s+", " ", str(value or "")).strip(" ：:|-—–~～")
            if not value or len(value) > 140:
                return False
            return bool(re.search(company_suffix, value, re.I) or re.search(r"(?:銀行|銀行本店|監査法人|Consulting|Corporation|Company)", value, re.I))
        inline_events = []
        inline_re = re.compile(r"^(?P<role>[^|｜]{1,80})\s*[|｜]\s*(?P<company>[^|｜]{2,140})\s*[|｜]\s*(?P<start>(?:19|20)\d{2}\s*年\s*\d{1,2}\s*月?)\s*(?:(?:至|到|一|-|—|~|～)\s*(?P<end>(?:19|20)\d{2}\s*年\s*\d{1,2}\s*月?)|(?P<current>至今|现在|目前))\s*$", re.I)
        for i, line in enumerate(lines):
            mm = inline_re.match(line)
            if mm and is_company(mm.group("company")):
                inline_events.append((i, mm))
        for n, (idx, mm) in enumerate(inline_events):
            stop = inline_events[n + 1][0] if n + 1 < len(inline_events) else len(lines)
            body = "\n".join(lines[idx + 1:stop]).strip()
            end_value = mm.group("end") or mm.group("current") or ""
            rows.append({"company_name": mm.group("company").strip(), "company_employees": "", "company_industry": "", "position": mm.group("role").strip(), "position_type": "", "position_salary": "", "position_dept": "", "position_report_to": "", "position_subordinate": "", "employment_type": "全职", "annual_salary_min": "", "annual_salary_max": "", "status": "在职" if mm.group("current") else "离职", "position_start": norm_date(mm.group("start")), "position_resigned": norm_date(end_value), "resigned_reason": "", "position_responsibilities": body, "position_achievements": "", "raw_text": body})
        for n, (idx, m) in enumerate(events):
            stop = events[n + 1][0] if n + 1 < len(events) else len(lines)
            rest = (m.groupdict().get("rest") or "").strip(" ：:|-—–~～")
            rest = re.sub(r"^(?:在|于|任职于|就职于)\s*", "", rest)
            rest = re.sub(r"^[（(\[][^）)\]]*(?:年|月|year|month)[^）)\]]*[）)\]]\s*", "", rest, flags=re.I).strip()
            following = lines[idx + 1:stop]
            company, role, consumed = "", "", 0
            if is_company(rest):
                company_match = re.match(rf"(?P<company>.{{2,120}}?{company_suffix})", rest, re.I)
                company = company_match.group("company").strip() if company_match else re.split(r"\s*[（(]", rest, maxsplit=1)[0].strip()
                bank_split = re.match(r"^(.+?銀行)(.*)$", company, re.I)
                if bank_split and bank_split.group(2).strip():
                    company, role = bank_split.group(1).strip(), bank_split.group(2).strip()
                consulting_split = re.match(r"^(.+?Consulting)\s*[,，]\s*(.+)$", company, re.I)
                if consulting_split:
                    company, role = consulting_split.group(1).strip(), consulting_split.group(2).strip()
                jp_split = re.match(r"^(.+?(?:銀行|監査法人))(?:\s+|)(.+)$", company, re.I)
                tokens = company.split(None, 1)
                if not role and jp_split and jp_split.group(2).strip():
                    company, role = jp_split.group(1).strip(), jp_split.group(2).strip()
                elif not role and len(tokens) == 2 and re.search(r"(?:銀行|監査法人|Consulting|Corporation|Company)$", tokens[0], re.I):
                    company, role = tokens[0].strip(), tokens[1].strip()
                tail = rest[len(company):].strip(" ：:|-—–~～")
                if tail and not role and not re.search(r"公司性质|公司规模|公司行业|国有企业|人\s*[|｜]|芜湖|贵阳", tail): role = tail
                elif following and len(following[0]) <= 50 and not re.search(r"^(?:工作|职责|项目|事業|売上|従業員|所在|薪酬|汇报|下属|所属|公司)", following[0], re.I) and not is_company(following[0]):
                    role, consumed = following[0].strip(" ：:"), 1
            elif rest and not re.search(r"^(?:工作|职责|项目|事業|売上|従業員|所在|薪酬|汇报|下属|所属|公司)", rest, re.I):
                role = rest
                if following and is_company(following[0]):
                    company, consumed = extract_company_name(following[0]), 1
            else:
                if idx > 0 and is_company(lines[idx - 1]):
                    company = extract_company_name(lines[idx - 1])
                    if following and len(following[0]) <= 60 and not is_company(following[0]):
                        role, consumed = following[0].strip(" ：:"), 1
                if following and not is_company(following[0]) and len(following[0]) <= 60:
                    if not role:
                        role, consumed = following[0].strip(" ：:"), 1
                    if not company and len(following) > consumed and is_company(following[consumed]):
                        company = extract_company_name(following[consumed]); consumed += 1
                elif following and is_company(following[0]):
                    company, consumed = extract_company_name(following[0]), 1
            if not company or not is_company(company):
                continue
            block = following[consumed:]
            raw = "\n".join(block)
            def lab(*names: str) -> str:
                pat = r"^(?:" + "|".join(re.escape(x) for x in names) + r")\s*[:：]?\s*(.*)$"
                for j, line in enumerate(block):
                    mm = re.match(pat, line, re.I)
                    if mm:
                        v = mm.group(1).strip(" ：:|│")
                        if v: return v
                        if j + 1 < len(block):
                            nxt = block[j + 1].strip(" ：:|│")
                            if not re.match(r"^(?:工作描述|职责业绩|工作职责和业绩|汇报对象|离职原因|工作业绩|工作地点|所在部门|下属人数|薪酬状况|薪资)\s*[:：]?", nxt, re.I):
                                return nxt
                return ""
            if not role:
                role = lab("工作职位", "职位", "岗位", "職位", "職種", "担当業務")
            role = role.strip(" 、,，。；;：:")
            if re.search(r"監査|財務|経理|法務|担当|部長|課長|主任|係長", role, re.I) and re.search(r"[、，,。；;]", role):
                role = re.split(r"[、，,。；;]", role, maxsplit=1)[0].strip()
            if len(role) > 60:
                role = re.split(r"[、，,。；;：:]", role, maxsplit=1)[0].strip()
            body = raw
            for marker in ("工作描述", "职责业绩", "职责和业绩", "主な業務", "業務内容", "仕事内容"):
                mm = re.search(re.escape(marker) + r"\s*[:：]?", body, re.I)
                if mm: body = body[mm.end():]
            body = re.split(r"(?:汇报对象|下属人数|所在部门|工作部门|离职原因|工作业绩)\s*[:：]?", body, maxsplit=1, flags=re.I)[0].strip()
            row = {"company_name": company, "company_employees": lab("公司规模", "従業員数"), "company_industry": lab("所属行业", "公司行业", "事業内容"), "position": role, "position_type": "", "position_salary": lab("薪酬状况", "薪资", "薪酬情况", "月 薪", "月薪"), "position_dept": lab("所在部门", "工作部门"), "position_report_to": lab("汇报对象", "報告先"), "position_subordinate": lab("下属人数", "下属"), "employment_type": "全职", "annual_salary_min": "", "annual_salary_max": "", "status": "在职" if not norm_date(m.group("end")) else "离职", "position_start": norm_date(m.group("start")), "position_resigned": norm_date(m.group("end")), "resigned_reason": lab("离职原因", "退職理由"), "position_responsibilities": body, "position_achievements": lab("工作业绩", "職務実績", "実績"), "raw_text": raw}
            sub_events = []
            standalone = re.compile(r"^(?:19|20)\d{2}\s*年\s*\d{1,2}\s*月?$")
            for j in range(len(block) - 3):
                if standalone.match(block[j]) and block[j + 1] in {"～", "~", "至", "一", "-"} and (standalone.match(block[j + 2]) or block[j + 2] in {"現在", "現在まで", "至今"}):
                    sub_events.append((j, block[j], block[j + 2], block[j + 3]))
            if sub_events:
                for si, (sj, ss, se, sr) in enumerate(sub_events):
                    s_end = sub_events[si + 1][0] if si + 1 < len(sub_events) else len(block)
                    sbody = "\n".join(block[sj + 4:s_end]).strip()
                    rows.append({**row, "position": sr.strip(), "position_start": norm_date(ss), "position_resigned": norm_date(se), "status": "在职" if not norm_date(se) else "离职", "position_responsibilities": sbody, "raw_text": "\n".join(block[sj:s_end])})
            else:
                rows.append(row)
        unique, seen = [], set()
        for row in rows:
            key = (row["company_name"], row.get("position", ""), row["position_start"], row["position_resigned"])
            if key not in seen: seen.add(key); unique.append(row)
        return unique

    text_works_explicit_v3_rows = text_work_items_explicit_v3()

    def text_work_items_dom_v4() -> list[dict[str, Any]]:
        normalized = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", clean_text.replace("\r", ""))
        normalized = re.sub(r"((?:19|20)\d{2}\s*[./-]\s*\d{1,2})\s*[-—–~～]\s*\n\s*(?=(?:至今|现在|目前|現在))", r"\1-至今\n", normalized)
        normalized = re.sub(r"((?:19|20)\d{2}\s*[./-]\s*\d{1,2})\s*[-—–~～]\s*\n\s*((?:19|20)\d{2}\s*[./-]\s*\d{1,2})", r"\1-\2", normalized)
        lines = [re.sub(r"\s+", " ", x).strip(" |│") for x in normalized.splitlines() if x.strip(" |│")]
        start_idx = next((i for i, x in enumerate(lines) if re.search(r"^(?:工作经历|工作经验|工作/实习经历|Work Experience)$", x, re.I)), None)
        if start_idx is not None:
            stop = next((i for i in range(start_idx + 1, len(lines)) if re.search(r"^(?:项目经历|项目经验|教育经历|教育背景|培训经历|语言能力|技能|证书|自我评价|个人优势)", lines[i], re.I)), len(lines))
            lines = lines[start_idx + 1:stop]
        date_re = re.compile(r"^(?P<start>(?:19|20)\d{2}\s*[./-]\s*\d{1,2})\s*[-—–~～至到]+\s*(?P<end>(?:19|20)\d{2}\s*[./-]\s*\d{1,2}|至今|现在|目前|現在)$", re.I)
        events = [(i, m) for i, line in enumerate(lines) if (m := date_re.match(line))]
        company_re = re.compile(r"(?:有限公司|有限责任公司|股份有限公司|集团|公司|研究所|研究院|设计院|半导体|电子商务|学院|银行|銀行|監査法人|Corporation|Company|Consulting|医院|大学)", re.I)
        role_re = re.compile(r"工程|经理|主管|总监|专员|代表|分析师|开发|设计|测试|销售|助理|顾问|负责人|职位|担当|技师|产品|采购|审计|财务|运营", re.I)
        rows: list[dict[str, Any]] = []
        for n, (idx, dm) in enumerate(events):
            stop = events[n + 1][0] if n + 1 < len(events) else len(lines)
            block = lines[idx + 1:stop]
            if not block:
                continue
            company_i = next((j for j, value in enumerate(block) if company_re.search(value) and len(value) <= 160), None)
            if company_i is None:
                continue
            company = re.sub(r"\s*[\[【（(][^\]】）)]*(?:个月|年|月)[^\]】）)]*[\]】）)]", "", block[company_i]).strip(" ：:|│")
            company = re.split(r"\s*[|｜]", company, maxsplit=1)[0].strip()
            role = ""
            for value in block[:company_i]:
                value = value.strip(" ：:|│")
                if value and not re.search(r"^(?:公司|行业|地点|工作描述|工作内容|职位类别|部门|汇报|下属|薪酬)", value, re.I) and len(value) <= 80 and role_re.search(value):
                    role = value
                    break
            if not role and company_i > 0:
                role = block[company_i - 1].strip(" ：:|│")
            body = block[company_i + 1:]
            marker = next((j for j, value in enumerate(body) if re.match(r"^(?:工作描述|工作内容|工作职责|职责业绩)\s*[:：]?", value, re.I)), None)
            if marker is not None:
                body = body[marker + 1:]
            body_text = "\n".join(body).strip()
            start = re.sub(r"\s+", "", dm.group("start")).replace(".", "-").replace("/", "-")
            start = re.sub(r"^(\d{4})-(\d{1,2})$", lambda m: f"{m.group(1)}年{int(m.group(2)):02d}月01日", start)
            end_raw = dm.group("end")
            end = "" if end_raw in {"至今", "现在", "目前", "現在"} else re.sub(r"\s+", "", end_raw).replace(".", "-").replace("/", "-")
            end = re.sub(r"^(\d{4})-(\d{1,2})$", lambda m: f"{m.group(1)}年{int(m.group(2)):02d}月01日", end)
            rows.append({
                "company_name": company, "company_employees": "", "company_industry": "",
                "position": role, "position_type": "", "position_salary": "", "position_dept": "",
                "position_report_to": "", "position_subordinate": "", "employment_type": "全职",
                "annual_salary_min": "", "annual_salary_max": "", "status": "在职" if not end else "离职",
                "position_start": start, "position_resigned": end, "resigned_reason": "",
                "position_responsibilities": body_text, "position_achievements": "", "raw_text": body_text,
            })
        unique: list[dict[str, Any]] = []
        seen: set[tuple[str, str, str, str]] = set()
        for row in rows:
            key = (row["company_name"], row["position"], row["position_start"], row["position_resigned"])
            if key not in seen:
                seen.add(key); unique.append(row)
        return unique

    text_works_dom_v4_rows = text_work_items_dom_v4()

    if len(text_works_dom_v4_rows) > len(text_works_labelled):
        text_works_labelled = text_works_dom_v4_rows

    def text_work_items_51job() -> list[dict[str, Any]]:
        """51job 专用解析器：匹配 '日期--日期：公司名(员工数)' 格式。

        EN: 51job-specific parser: matches the format 'date--date: company name (number of employees)'.

        JA: 51job 専用パーサー：'日付--日付：会社名(従業員数)' の形式にマッチする。
        """
        lines = [x.strip() for x in clean_text.splitlines() if x.strip()]
        work_start = None
        for i, ln in enumerate(lines):
            if re.search(r"^工作(?:经验|经历)$", ln):
                work_start = i
                break
        if work_start is None:
            return []
        stop_pat = re.compile(r"^(?:教育经历|教育背景|自我评价|项目经验|语言能力|技能|求职意向|联系方式|基本信息|个人信息)")
        section_lines = []
        for ln in lines[work_start + 1:]:
            if stop_pat.match(ln):
                break
            section_lines.append(ln)
        header_re = re.compile(
            r"^(?P<start>\d{4}\s*/\s*\d{1,2})\s*[-—–~～至到一]+\s*(?P<end>至今|\d{4}\s*/\s*\d{1,2})\s*[：:]\s*(?P<company>.+?)\s*(?:\((?P<employees>[^)]+)\))?\s*(?:\s*\[\s*[^\]]+\s*\])?\s*$"
        )
        headers: list[tuple[int, dict]] = []
        for idx, ln in enumerate(section_lines):
            m = header_re.match(ln)
            if m:
                headers.append((idx, m.groupdict()))
        if len(headers) < 1:
            return []
        def parse_ym(s: str) -> str:
            m = re.match(r"(\d{4})\s*/\s*(\d{1,2})", s)
            if not m:
                return ""
            return f"{m.group(1)}年{int(m.group(2)):02d}月01日"
        def parse_date_to_end(s: str) -> tuple[str, str]:
            if s == "至今":
                return "", "在职"
            ym = parse_ym(s)
            return (ym, "在职" if ym else "离职") if ym else ("", "在职")
        def extract_position_and_dept(block_lines: list[str]) -> tuple[str, str, str, int]:
            industry, dept, position, idx = "", "", "", 0
            if idx < len(block_lines) and re.match(r"^\[\s*\d+.*?\]$", block_lines[idx]):
                idx += 1
            if idx < len(block_lines) and block_lines[idx].startswith("所属行业"):
                idx += 1
                if idx < len(block_lines):
                    industry = block_lines[idx]
                    idx += 1
            if idx < len(block_lines):
                candidate = block_lines[idx]
                if idx + 1 < len(block_lines):
                    next_ln = block_lines[idx + 1]
                    if re.search(r"(?:部|处|组|中心|科|室|课|team|group|division|department|management)", candidate, re.I):
                        dept = candidate
                        idx += 1
                        if idx < len(block_lines):
                            position = block_lines[idx]
                            idx += 1
                    else:
                        position = candidate
                        idx += 1
                else:
                    position = candidate
                    idx += 1
            return industry, dept, position, idx
        rows: list[dict[str, Any]] = []
        for i, (hdr_idx, hdr) in enumerate(headers):
            block_start = hdr_idx + 1
            block_end = headers[i + 1][0] if i + 1 < len(headers) else len(section_lines)
            block_lines = section_lines[block_start:block_end]
            industry, dept, position, consumed_idx = extract_position_and_dept(block_lines)
            body_lines = [ln for ln in block_lines[consumed_idx:] if ln.strip()]
            body_text = "\n".join(body_lines)
            start_ym = parse_ym(hdr["start"])
            end_ym, status = parse_date_to_end(hdr["end"])
            if hdr["end"] != "至今":
                status = "离职"
            rows.append({
                "company_name": hdr["company"].strip(),
                "company_employees": (hdr.get("employees") or "").strip(),
                "company_industry": industry,
                "position": position,
                "position_type": "",
                "position_salary": "",
                "position_dept": dept,
                "position_report_to": "",
                "position_subordinate": "",
                "employment_type": "全职",
                "annual_salary_min": "",
                "annual_salary_max": "",
                "status": status,
                "position_start": start_ym,
                "position_resigned": end_ym,
                "resigned_reason": "",
                "position_responsibilities": body_text,
                "position_achievements": "",
                "raw_text": section_lines[hdr_idx:block_end],
            })
        return rows

    def text_work_items_51job_en() -> list[dict[str, Any]]:
        lines = [x.strip() for x in clean_text.splitlines() if x.strip()]
        work_start = None
        for i, ln in enumerate(lines):
            if re.search(r"^Work\s*/?\s*Experience$", ln, re.I):
                work_start = i
                break
        if work_start is None:
            return []
        stop_pat = re.compile(r"^(?:Education|Training|Certifications?|Language\s*Skills?|IT\s*Skills?|Attachments?|Career\s*Objective|Self\s*Evaluation|Personal\s*Information)")
        section_lines = []
        for ln in lines[work_start + 1:]:
            if stop_pat.match(ln):
                break
            section_lines.append(ln)
        header_re = re.compile(
            r"^(?P<start>\d{4}/\d{1,2})\s*[-—–~～至到一]+\s*(?P<end>Present|至今|\d{4}/\d{1,2})\s*[：:]\s*(?P<company>.+?)\s*(?:\((?P<employees>[^)]+)\))?\s*$",
            re.I,
        )
        headers: list[tuple[int, dict]] = []
        for idx, ln in enumerate(section_lines):
            m = header_re.match(ln)
            if m:
                headers.append((idx, m.groupdict()))
        if len(headers) < 1:
            return []
        def parse_ym(s: str) -> str:
            m = re.match(r"(\d{4})/(\d{1,2})", s)
            if not m:
                return ""
            return f"{m.group(1)}年{int(m.group(2)):02d}月01日"
        def parse_date_to_end(s: str) -> tuple[str, str]:
            if s.lower() in ("present", "至今"):
                return "", "在职"
            ym = parse_ym(s)
            return (ym, "在职" if ym else "离职") if ym else ("", "在职")
        def extract_position_and_dept_en(block_lines: list[str]) -> tuple[str, str, str, int]:
            industry, dept, position, idx = "", "", "", 0
            if idx < len(block_lines) and re.match(r"^\[\s*\d+.*?\]$", block_lines[idx], re.I):
                idx += 1
            if idx < len(block_lines) and re.match(r"^Industry\s*[:：]?\s*$", block_lines[idx], re.I):
                idx += 1
                if idx < len(block_lines):
                    industry = block_lines[idx]
                    idx += 1
            if idx < len(block_lines):
                candidate = block_lines[idx]
                if idx + 1 < len(block_lines):
                    next_ln = block_lines[idx + 1]
                    if re.search(r"Department|Division|Team|Group|Account|Section|Unit", candidate, re.I):
                        dept = candidate
                        idx += 1
                        if idx < len(block_lines):
                            position = block_lines[idx]
                            idx += 1
                    else:
                        position = candidate
                        idx += 1
                else:
                    position = candidate
                    idx += 1
            return industry, dept, position, idx
        rows: list[dict[str, Any]] = []
        for i, (hdr_idx, hdr) in enumerate(headers):
            block_start = hdr_idx + 1
            block_end = headers[i + 1][0] if i + 1 < len(headers) else len(section_lines)
            block_lines = section_lines[block_start:block_end]
            industry, dept, position, consumed_idx = extract_position_and_dept_en(block_lines)
            body_lines = [ln for ln in block_lines[consumed_idx:] if ln.strip()]
            body_text = "\n".join(body_lines)
            start_ym = parse_ym(hdr["start"])
            end_ym, status = parse_date_to_end(hdr["end"])
            if hdr["end"].lower() not in ("present", "至今"):
                status = "离职"
            rows.append({
                "company_name": hdr["company"].strip(),
                "company_employees": (hdr.get("employees") or "").strip(),
                "company_industry": industry,
                "position": position,
                "position_type": "",
                "position_salary": "",
                "position_dept": dept,
                "position_report_to": "",
                "position_subordinate": "",
                "employment_type": "全职",
                "annual_salary_min": "",
                "annual_salary_max": "",
                "status": status,
                "position_start": start_ym,
                "position_resigned": end_ym,
                "resigned_reason": "",
                "position_responsibilities": body_text,
                "position_achievements": "",
                "raw_text": section_lines[hdr_idx:block_end],
            })
        return rows

    text_works_51job_rows = text_work_items_51job()
    text_works_51job_en_rows = text_work_items_51job_en()

    def text_work_items_narrative_v5() -> list[dict[str, Any]]:
        normalized = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", clean_text.replace("\r", ""))
        lines = [re.sub(r"\s+", " ", x).strip() for x in normalized.splitlines() if x.strip()]
        start_idx = next((i for i, x in enumerate(lines) if re.search(r"工作(?:/实习)?经历|Work/Internship Experience", x, re.I)), None)
        if start_idx is None:
            return []
        stop_re = re.compile(r"教育经历|教育背景|请简述本次离职|Main reason|项目经历|语言能力|技能", re.I)
        section = []
        for line in lines[start_idx + 1:]:
            if stop_re.search(line):
                break
            section.append(line)
        range_re = re.compile(r"(?P<start>(?:19|20)\d{2})\s*年\s*(?P<sm>\d{1,2})\s*月\s*(?:至|到|[-—])\s*(?P<end>(?:19|20)\d{2})\s*年\s*(?P<em>\d{1,2})\s*月")
        single_re = re.compile(r"(?P<start>(?:19|20)\d{2})\s*年\s*(?P<sm>\d{1,2})\s*月")
        company_re = re.compile(r"(?:在|于|进入)\s*(?P<company>[^，,。；;\n]{2,100}?(?:有限公司|有限责任公司|股份有限公司|公司|集团|汽车|研究所|中心))")
        rows: list[dict[str, Any]] = []
        for line in section:
            ranges = list(range_re.finditer(line))
            if ranges:
                for match in ranges:
                    tail = line[match.end():]
                    company_m = company_re.search(tail)
                    if not company_m:
                        continue
                    company = company_m.group("company").strip(" ：:，,")
                    after_company = tail[company_m.end():]
                    role_m = re.search(r"(?:任职|担任|任)\s*(?P<role>[^，,。；;\n]{2,60})", after_company)
                    role = (role_m.group("role") if role_m else "").strip(" ：:，,")
                    body = after_company[role_m.end():] if role_m else after_company
                    start = f"{match.group('start')}年{int(match.group('sm')):02d}月01日"
                    end = f"{match.group('end')}年{int(match.group('em')):02d}月01日"
                    rows.append({"company_name": company, "company_employees": "", "company_industry": "", "position": role, "position_type": "", "position_salary": "", "position_dept": "", "position_report_to": "", "position_subordinate": "", "employment_type": "全职", "annual_salary_min": "", "annual_salary_max": "", "status": "离职", "position_start": start, "position_resigned": end, "resigned_reason": "", "position_responsibilities": body.strip(" ：:，,"), "position_achievements": "", "raw_text": line})
                continue
            if "进入" in line:
                dates = list(single_re.finditer(line))
                if not dates:
                    continue
                company_m = company_re.search(line[dates[0].end():])
                if not company_m:
                    continue
                company = company_m.group("company").strip(" ：:，,")
                end_value = dates[1] if len(dates) > 1 else None
                start = f"{dates[0].group('start')}年{int(dates[0].group('sm')):02d}月01日"
                end = f"{end_value.group('start')}年{int(end_value.group('sm')):02d}月01日" if end_value else ""
                rows.append({"company_name": company, "company_employees": "", "company_industry": "", "position": "实习生" if "实习" in line else "", "position_type": "", "position_salary": "", "position_dept": "", "position_report_to": "", "position_subordinate": "", "employment_type": "全职", "annual_salary_min": "", "annual_salary_max": "", "status": "离职" if end else "在职", "position_start": start, "position_resigned": end, "resigned_reason": "", "position_responsibilities": line, "position_achievements": "", "raw_text": line})
        unique, seen = [], set()
        for row in rows:
            key = (row["company_name"], row["position"], row["position_start"], row["position_resigned"])
            if key not in seen:
                seen.add(key); unique.append(row)
        return unique


    text_works_narrative_v5_rows = text_work_items_narrative_v5()

    # === 51job 专用解析器：若命中则直接采用，跳过所有优先级覆盖链 ===
    # EN: === 51job-specific parser: if it matches, use it directly and skip the whole priority override chain ===
    # JA: === 51job 専用パーサー：マッチしたらそのまま採用し、優先度による上書きの連鎖をすべてスキップする ===
    if text_works_51job_rows:
        # 有效性校验：company_name 和 position_start 都要有
        # EN: Validity check: both company_name and position_start are required
        # JA: 妥当性チェック：company_name と position_start の両方が必要
        credible_51job = [r for r in text_works_51job_rows
                          if r.get("company_name") and r.get("position_start")]
        if credible_51job:
            text_works_labelled = credible_51job
            # 跳过后续所有覆盖逻辑，直接使用 51job 结果
            # EN: Skip all subsequent override logic and use the 51job result directly
            # JA: 以降の上書きロジックをすべてスキップし、51job の結果をそのまま使う
            text_works = list(credible_51job)
            # 工作经历板块的公司信息，也用于 current_info / expected_info 等
            # EN: Company information from the work-history section is also used for current_info / expected_info etc.
            # JA: 職歴欄の会社情報は current_info / expected_info などにも使う
            for wr in text_works:
                pass  # 已在上方统一设置
                # EN: Already set uniformly above
                # JA: 上ですでに一括設定済み
        # 无论是否通过有效性校验，都跳过低效的优先级链
        # EN: Whether or not the validity check passes, skip the inefficient priority chain
        # JA: 妥当性チェックに合格したかどうかに関係なく、非効率な優先度の連鎖はスキップする
        pass  # placeholder, will be continued below

    # 如果 51job 解析器未命中或无有效条目，执行原有优先级链
    # EN: If the 51job parser did not match or produced no valid entries, run the original priority chain
    # JA: 51job パーサーがマッチしないか有効な項目がない場合は、元の優先度の連鎖を実行する
    if not text_works_51job_rows or not text_works_labelled:
        if len(text_works_narrative_v5_rows) >= len(text_works_labelled):
            text_works_labelled = text_works_narrative_v5_rows
        if len(text_works_explicit_v3_rows) >= 1:
            text_works_labelled = text_works_explicit_v3_rows
        if len(text_works_narrative_v5_rows) > len(text_works_labelled):
            text_works_labelled = text_works_narrative_v5_rows
        if len(text_works_dom_v4_rows) > len(text_works_labelled):
            text_works_labelled = text_works_dom_v4_rows
        if len(text_works_labelled_v2_rows) >= 1:
            text_works_labelled = text_works_labelled_v2_rows
        if len(text_works_inline) >= 1:
            text_works_structured = text_works_inline
        if text_works_structured:
            text_works_labelled = text_works_structured
        if len(text_works_labelled_v2_rows) >= 1:
            text_works_labelled = text_works_labelled_v2_rows
        if len(text_works_explicit_v3_rows) >= 1:
            text_works_labelled = text_works_explicit_v3_rows
        if len(text_works_narrative_v5_rows) >= len(text_works_labelled):
            text_works_labelled = text_works_narrative_v5_rows
        if len(text_works_dom_v4_rows) >= len(text_works_labelled):
            text_works_labelled = text_works_dom_v4_rows
        if text_works_explicit_v3_rows:
            text_works_labelled = text_works_explicit_v3_rows
        try:
            schema_works = CodexGeminiHtmlSchemaParser()._extract_work_experiences(clean_text, "zh")
        except Exception:
            schema_works = []
        schema_works = [clean_work_item(item) for item in schema_works if valid_work_item(clean_work_item(item))]
        if schema_works:
            bad_tokens = ("作为", "主要使用", "制定公司", "工作内容", "公司行业", "公司规模")
            credible = [item for item in schema_works if not any(t in str(item.get("company_name") or "") for t in bad_tokens)
                        and str(item.get("position") or "") not in {"", "担当", "职位"}]
            if credible:
                text_works_labelled = credible
    dom_valid_count = sum(1 for item in text_works_dom_v4_rows if valid_work_item(clean_work_item(item)))
    labelled_valid_count = sum(1 for item in text_works_labelled if valid_work_item(clean_work_item(item)))
    if dom_valid_count and not labelled_valid_count:
        text_works_labelled = text_works_dom_v4_rows
    if len(text_works_labelled) > len(text_works_v2):
        text_works_v2 = text_works_labelled
    if len(text_works_v2) > len(text_works):
        text_works = text_works_v2
    if len(text_works) > len(fallback_works):
        fallback_works = text_works
    if len(text_works_labelled) >= 2:
        fallback_works = text_works_labelled
    fallback_edus = [education_item(item) for item in (fallback.get("education_experiences") or [])]
    fallback_edus = [item for item in fallback_edus if item.get("school_name") and re.search(r"大学|学院|学校|大学院|中学|高中|高等学校|University|College|Institute", item.get("school_name", ""), re.I)]

    # ===== 51job 专用板块解析器 =====
    # EN: ===== 51job-specific section parser =====
    # JA: ===== 51job 専用のセクションパーサー =====

    def _extract_51job_section(header_text: str, stop_headers: list[str]) -> list[str]:
        """从 clean_text 中提取指定板块的行，遇到停止标题结束。

        EN: Extract the lines of the given section from clean_text, ending at a stop heading.

        JA: clean_text から指定セクションの行を抽出し、停止見出しで終える。
        """
        lines = [x.strip() for x in clean_text.splitlines() if x.strip()]
        start_idx = None
        for i, ln in enumerate(lines):
            if re.search(re.escape(header_text), ln):
                start_idx = i
                break
        if start_idx is None:
            return []
        stop_re = re.compile(r"^\s*(?:" + "|".join(re.escape(h) for h in stop_headers) + r")")
        # 51job 特殊处理："证书" 标题可能被 <img/> 拆成 "证" 和 "书" 两行
        # 遇到 "证" 后面紧跟 "书" 时，也视为板块边界
        # EN: 51job special case: the "证书" (certificates) heading may be split by <img/> into two lines, "证" and "书"
        #     When "证" is immediately followed by "书", also treat it as a section boundary
        # JA: 51job の特別処理：「证书」（資格）の見出しが <img/> により「证」と「书」の 2 行に分かれることがある
        #     「证」の直後に「书」が続く場合もセクションの境界とみなす
        section = []
        for idx, ln in enumerate(lines[start_idx + 1:], start=start_idx + 1):
            if stop_re.match(ln):
                break
            # 检测拆分的 "证书" 标题
            # EN: Detect a split "证书" heading
            # JA: 分割された「证书」の見出しを検出する
            if ln == "证" and idx + 1 < len(lines) and lines[idx + 1] == "书":
                break
            if ln == "书" and idx > 0 and lines[idx - 1] == "证":
                break
            section.append(ln)
        return section

    _51job_stop_headers = [
        "教育经历", "教育背景", "教育程度", "学历",
        "工作经历", "工作经验",
        "语言能力", "外语水平", "语言水平",
        "证书", "资格", "技能", "自我评价", "项目经历", "项目经验", "培训经历",
        "求职意向", "联系方式", "基本信息", "个人信息",
    ]

    def text_education_items_51job() -> list[dict[str, Any]]:
        """51job 专用教育经历解析：只扫描 "教育经历" 板块。

        EN: 51job-specific education parsing: scans only the "教育经历" (education) section.

        JA: 51job 専用の学歴解析：「教育经历」（学歴）欄だけをスキャンする。
        """
        section = _extract_51job_section("教育经历", _51job_stop_headers)
        if not section:
            return []

        # 预处理：合并跨行日期。51job 日期可能被拆成 2-3 行：
        #   2002
        #   /9--2006
        #   /7  上海理工大学  机械设计制造  本科
        # 合并为一行：2002/9--2006/7  上海理工大学  机械设计制造  本科
        # EN: Pre-processing: merge dates that span lines. 51job dates may be split over 2-3 lines:
        #       2002
        #       /9--2006
        #       /7  上海理工大学  机械设计制造  本科
        #     Merged into one line: 2002/9--2006/7  上海理工大学  机械设计制造  本科
        # JA: 前処理：行をまたぐ日付を結合する。51job の日付は 2〜3 行に分かれることがある：
        #       2002
        #       /9--2006
        #       /7  上海理工大学  机械设计制造  本科
        #     1 行に結合：2002/9--2006/7  上海理工大学  机械设计制造  本科
        normalized: list[str] = []
        idx = 0
        while idx < len(section):
            line = section[idx]
            # 如果当前行是单独的年份（4位数字）
            # EN: If the current line is a standalone year (4 digits)
            # JA: 現在の行が単独の年（4 桁の数字）の場合
            if re.match(r"^(?:19|20)\d{2}$", line.strip()):
                combined = line.strip()
                next_idx = idx + 1
                # 向后合并最多 3 行（日期可能跨 2-3 行）
                # EN: Merge up to 3 following lines (a date may span 2-3 lines)
                # JA: 後続の最大 3 行を結合する（日付は 2〜3 行にまたがることがある）
                for _ in range(3):
                    if next_idx >= len(section):
                        break
                    nxt = section[next_idx].strip()
                    # 下一行以 "/数字" 开头（日期延续）
                    # EN: The next line starts with "/digits" (date continuation)
                    # JA: 次の行が「/数字」で始まる（日付の続き）
                    if re.match(r"^/\s*\d{1,2}", nxt) or re.match(r"^/\s*\d{1,2}\s*[-—–~～至到]+", nxt):
                        combined += nxt
                        next_idx += 1
                    else:
                        break
                normalized.append(combined)
                idx = next_idx
            else:
                normalized.append(line)
                idx += 1

        rows = []
        # 51job 教育经历格式：日期行 + 学校行 + 专业行 + 学历行
        # 例：  2004/2--2008/1
        #       同济大学
        #       日语
        #       本科
        # EN: 51job education format: date line + school line + major line + degree line
        #     e.g.:  2004/2--2008/1
        #           同济大学
        #           日语
        #           本科
        # JA: 51job の学歴の形式：日付行 + 学校行 + 専攻行 + 学歴行
        #     例：  2004/2--2008/1
        #           同济大学
        #           日语
        #           本科
        date_range = re.compile(
            r"(?P<start>(?:19|20)\d{2}[./-]\s*\d{1,2})\s*[-—–~～至到]+\s*(?P<end>(?:19|20)\d{2}[./-]\s*\d{1,2})"
        )
        # degree_re 匹配整行（避免"新仓中学"中的"中学"被误判为学历）
        # EN: degree_re matches the whole line (so "中学" in "新仓中学" is not mistaken for a degree)
        # JA: degree_re は行全体にマッチさせる（「新仓中学」の「中学」を学歴と誤認しないため）
        degree_re = re.compile(r"^\s*(博士后|博士|硕士|修士|研究生|MBA|EMBA|本科|学士|大专|专科|高中|中专|职高|中技|技校|职校|初中|小学)\s*$", re.I)
        school_re = re.compile(r"(大学院|大学|学院|高等学校|中学|高中|学校|理工|University|College|Institute)", re.I)

        i = 0
        while i < len(normalized):
            line = normalized[i]
            m = date_range.search(line)
            if m:
                start = re.sub(r"\s+", "", m.group("start"))
                end = re.sub(r"\s+", "", m.group("end"))
                # 从下一行开始找学校/专业/学历
                # EN: Look for school/major/degree starting from the next line
                # JA: 次の行から学校・専攻・学歴を探す
                school = ""
                major = ""
                degree = ""
                j = i + 1
                # 先收集所有可能的字段行（到下一个日期行或板块结束）
                # EN: First collect all possible field lines (up to the next date line or the end of the section)
                # JA: まず考えられるフィールドの行をすべて集める（次の日付行またはセクションの終わりまで）
                candidates = []
                while j < len(normalized):
                    c = normalized[j]
                    # 遇到另一个日期开头就停
                    # EN: Stop at another line starting with a date
                    # JA: 別の日付で始まる行が来たら止める
                    if date_range.match(c):
                        break
                    # 跳过明显的专业介绍/描述长文（51job 教育板块有时带专业说明）
                    # EN: Skip obvious long major introductions/descriptions (the 51job education section sometimes includes a major description)
                    # JA: 明らかな専攻の紹介・説明の長文はスキップする（51job の学歴欄には専攻の説明が付くことがある）
                    if len(c) > 50 and not re.search(r"大学|学院|学校|本科|大专|专科|学士|硕士|博士|高中|中专|职高", c, re.I):
                        break
                    candidates.append(c)
                    j += 1
                # 智能分配：先找学历关键词，再找学校关键词
                # EN: Smart assignment: look for degree keywords first, then school keywords
                # JA: 賢い割り当て：まず学歴のキーワード、次に学校のキーワードを探す
                for c in candidates:
                    dm = degree_re.search(c)
                    if dm and not degree:
                        degree = dm.group(1)
                        continue
                    sm = school_re.search(c)
                    if sm and not school:
                        school = c
                        continue
                    if not major and school:
                        major = c
                if school:
                    # 日期格式化
                    # EN: Date formatting
                    # JA: 日付の整形
                    start_fmt = re.sub(r"(\d{4})[./-](\d{1,2})", lambda m2: f"{m2.group(1)}年{int(m2.group(2)):02d}月01日", start)
                    end_fmt = re.sub(r"(\d{4})[./-](\d{1,2})", lambda m2: f"{m2.group(1)}年{int(m2.group(2)):02d}月01日", end)
                    raw = "\n".join(normalized[i:j])
                    rows.append(education_item({
                        "school_name": school,
                        "school_major_name": major,
                        "school_degree_type": degree,
                        "school_start_ym": start_fmt,
                        "school_end_ym": end_fmt,
                        "raw_text": raw,
                    }))
                i = j
            else:
                i += 1
        # 复用 codex_word_html_json_100.py 现成后处理：恢复“学校/专业/学历/教育形式”独立字段，再补齐学历等级
        # EN: Reuse the existing post-processing in codex_word_html_json_100.py: restore separate "school/major/degree/mode of study" fields, then fill in the degree rank
        # JA: codex_word_html_json_100.py の既存の後処理を再利用する：「学校／専攻／学歴／就学形態」を個別のフィールドに復元し、学歴ランクを補う
        rows = [normalize_education_annotation(r) for r in rows]
        rows = normalize_degree_rows(rows)
        # 51job 板块无“是否统招”字段，教育形式提取不到时用 EDUCATION_TYPE_MAP 兜底
        # EN: The 51job section has no "是否统招" (unified enrolment or not) field; when the mode of study cannot be extracted, fall back to EDUCATION_TYPE_MAP
        # JA: 51job の欄には「是否统招」（統一入試か否か）のフィールドがないため、就学形態が取れない場合は EDUCATION_TYPE_MAP で補う
        for r in rows:
            if not str(r.get("school_education_type") or "").strip():
                rank = str(r.get("school_degree_rank") or "")
                if rank:
                    r["school_education_type"] = EDUCATION_TYPE_MAP.get(rank, "")
        return rows

    def text_certificate_items_51job() -> list[dict[str, Any]]:
        """51job 专用证书解析：只扫描 "证书" 板块。

        51job 证书格式（证书标题可能被 <img/> 拆成两行 "证" "书"）：
            证
            书
            2008/11    实用日本语鉴定证书（J.TEST）    准B级
            2008/2     日语一级证书                   日语一级

        EN: 51job-specific certificate parsing: scans only the "证书" (certificates) section.

        51job certificate format (the heading may be split by <img/> into two lines "证" "书"):
            证
            书
            2008/11    实用日本语鉴定证书（J.TEST）    准B级
            2008/2     日语一级证书                   日语一级

        JA: 51job 専用の資格解析：「证书」（資格）欄だけをスキャンする。

        51job の資格の形式（見出しが <img/> で「证」「书」の 2 行に分かれることがある）：
            证
            书
            2008/11    实用日本语鉴定证书（J.TEST）    准B级
            2008/2     日语一级证书                   日语一级
        """
        # 51job 中 "证书" 标题有时会被拆成两行
        # EN: In 51job the "证书" (certificates) heading is sometimes split over two lines
        # JA: 51job では「证书」（資格）の見出しが 2 行に分かれることがある
        lines_raw = [x.strip() for x in clean_text.splitlines() if x.strip()]
        # 找到证书板块起始（"证书" 可能是一行，也可能是 "证" 然后 "书" 两行）
        # EN: Find the start of the certificate section ("证书" may be one line, or "证" then "书" on two lines)
        # JA: 資格欄の開始を探す（「证书」は 1 行のことも、「证」と「书」の 2 行のこともある）
        cert_start = None
        for i in range(len(lines_raw)):
            ln = lines_raw[i]
            if ln in ("证书", "证 书", "証書"):
                cert_start = i
                break
            # 处理被 <img/> 拆分的情况：上一行是 "证" 下一行是 "书"
            # EN: Handle the case split by <img/>: the previous line is "证" and the next line is "书"
            # JA: <img/> で分割された場合の処理：前の行が「证」、次の行が「书」
            if ln == "书" and i > 0 and lines_raw[i - 1] == "证":
                cert_start = i
                break
        if cert_start is None:
            return []
        # 找到板块结束（用 match 锚定行首，避免内容行误判）
        # EN: Find the end of the section (anchor with match at the start of the line so content lines are not misjudged)
        # JA: セクションの終わりを探す（match で行頭に固定し、内容の行を誤判定しないようにする）
        stop_re = re.compile(r"^\s*(?:" + "|".join(re.escape(h) for h in _51job_stop_headers) + r")")
        section = []
        for ln in lines_raw[cert_start + 1:]:
            if stop_re.match(ln):
                break
            section.append(ln)

        if not section:
            return []

        # 解析证书条目：日期 + 名称 + 级别
        # 51job 格式通常是每行一张证书，或日期/名称/级别各一行
        # EN: Parse certificate entries: date + name + level
        #     The 51job format is usually one certificate per line, or date/name/level each on its own line
        # JA: 資格の項目を解析する：日付 + 名称 + レベル
        #     51job の形式は通常 1 行に 1 つの資格、または日付・名称・レベルがそれぞれ 1 行
        date_re = re.compile(r"^(?:(\d{4})[./-](\d{1,2}))")
        rows = []
        i = 0
        while i < len(section):
            line = section[i]
            dm = date_re.match(line)
            if dm:
                cert_time = f"{dm.group(1)}年{int(dm.group(2)):02d}月01日"
                # 收集后续行作为名称和级别
                # EN: Collect the following lines as the name and level
                # JA: 後続の行を名称とレベルとして集める
                name = ""
                level = ""
                j = i + 1
                while j < len(section):
                    c = section[j]
                    # 遇到另一个日期就停
                    # EN: Stop at another date
                    # JA: 別の日付が来たら止める
                    if date_re.match(c):
                        break
                    if not name:
                        name = c
                    elif not level:
                        level = c
                    j += 1
                if name:
                    full_name = f"{name} {level}".strip() if level else name
                    rows.append({
                        "certificate_name": full_name[:160],
                        "certificate_type": "证书",
                        "certificate_time": cert_time,
                        "raw_text": "\n".join(section[i:j]),
                    })
                i = j
            else:
                i += 1
        return rows

    def text_language_items_51job() -> list[dict[str, Any]]:
        """51job 专用语言能力解析：只扫描 "语言能力" 板块。

        51job 语言能力格式：
            日语（熟练）：
            听说（良好），读写（熟练）
            英语等级：
            未参加
            日语等级：
            一级

        EN: 51job-specific language parsing: scans only the "语言能力" (language skills) section.

        51job language format:
            日语（熟练）：
            听说（良好），读写（熟练）
            英语等级：
            未参加
            日语等级：
            一级

        JA: 51job 専用の語学解析：「语言能力」（語学力）欄だけをスキャンする。

        51job の語学の形式：
            日语（熟练）：
            听说（良好），读写（熟练）
            英语等级：
            未参加
            日语等级：
            一级
        """
        section = _extract_51job_section("语言能力", _51job_stop_headers)
        if not section:
            return []

        # 预处理：合并语言行跨行。51job 语言行偶尔被 HTML 拆成两行：
        #   English(Very Good
        #   ):
        # 合并为：English(Very Good):
        # EN: Pre-processing: merge language lines that span lines. 51job language lines are occasionally split over two lines by HTML:
        #       English(Very Good
        #       ):
        #     Merged into: English(Very Good):
        # JA: 前処理：行をまたぐ語学の行を結合する。51job の語学の行は HTML によりまれに 2 行に分かれる：
        #       English(Very Good
        #       ):
        #     結合後：English(Very Good):
        normalized_section: list[str] = []
        idx = 0
        while idx < len(section):
            line = section[idx]
            # 当前行以 "(文本" 结尾，且下一行以 "):" 开头
            # EN: The current line ends with "(text" and the next line starts with "):"
            # JA: 現在の行が「(テキスト」で終わり、次の行が「):」で始まる
            if re.search(r"[(（][^)）]*$", line) and idx + 1 < len(section) and re.match(r"^[)）][:：]", section[idx + 1]):
                normalized_section.append(line.rstrip() + section[idx + 1].strip())
                idx += 2
            else:
                normalized_section.append(line)
                idx += 1

        rows = []
        lang_re = r"(中文|普通话|汉语|英语|英文|日语|日文|德语|法语|韩语|Japanese|English|German|French|Korean)"
        # 语言板块结束标识（额外的板块标题，在 _51job_stop_headers 基础上补充）
        # EN: Markers for the end of the language section (extra section headings, in addition to _51job_stop_headers)
        # JA: 語学欄の終わりを示す目印（_51job_stop_headers に加える追加のセクション見出し）
        extra_lang_headers = [
            "其他信息", "职业目标", "求职意向", "自我评价", "培训经历", "项目经历",
            "兴趣爱好", "附件", "简历", "Resume", "Curriculum Vitae",
            "基本信息", "个人信息", "联系方式", "应聘职位", "教育背景", "工作经验",
            "Skills", "Skill", "Certifications", "Certification",
            "Awards", "Honors", "Publications", "Volunteer",
            "Summary", "Profile", "Objective", "Career Objective",
        ]
        lang_stop_re = re.compile(r"^\s*(?:" + "|".join(re.escape(h) for h in _51job_stop_headers + extra_lang_headers) + r")\s*[:：]?\s*$", re.I)
        # 51job 语言条目格式：语言名+等级描述（可能跨多行）
        # 策略：找到所有语言名开头的行
        # EN: 51job language entry format: language name + level description (may span several lines)
        #     Strategy: find all lines that start with a language name
        # JA: 51job の語学項目の形式：言語名 + レベルの説明（複数行にまたがることがある）
        #     方針：言語名で始まる行をすべて探す
        i = 0
        while i < len(normalized_section):
            line = normalized_section[i]
            # 尝试匹配 "语言名（等级）：" 或 "语言名：" 格式
            # 排除 "英语等级："、"English Grade:" 等等级标签行
            # EN: Try matching the "language name (level):" or "language name:" format
            #     Exclude level label lines such as "英语等级：" and "English Grade:"
            # JA: 「言語名（レベル）：」または「言語名：」の形式でマッチを試みる
            #     「英语等级：」や「English Grade:」などのレベルのラベル行は除外する
            if re.search(r"等级\s*[：:]", line, re.I) or re.search(r"Grade\s*[：:]", line, re.I):
                i += 1
                continue
            m = re.match(rf"^\s*({lang_re})\s*[（(]?(.*?)[)）]?\s*[：:]?\s*$", line, re.I)
            if m:
                lang_name = m.group(1)
                # 等级信息可能在本行剩余部分或下一行
                # 注意：lang_re 自带括号，导致嵌套后 group 编号为 1=外层, 2=lang_re内层, 3=(.*?)
                # EN: Level information may be in the rest of this line or on the next line
                #     Note: lang_re has its own brackets, so after nesting the group numbers are 1 = outer, 2 = inner lang_re, 3 = (.*?)
                # JA: レベルの情報はこの行の残りか次の行にあることがある
                #     注意：lang_re 自体に括弧があるため、入れ子にした後のグループ番号は 1 = 外側、2 = lang_re の内側、3 = (.*?)
                rest = (m.group(3) or "").strip()
                level_parts = []
                if rest:
                    level_parts.append(rest)
                # 检查下一行是否有听说读写描述
                # EN: Check whether the next line has a listening/speaking/reading/writing description
                # JA: 次の行に聞く・話す・読む・書くの説明があるかを確認する
                j = i + 1
                while j < len(normalized_section):
                    next_line = normalized_section[j]
                    # 遇到另一个语言名开头就停（包括紧跟的下一行）
                    # EN: Stop at a line starting with another language name (including the line immediately following)
                    # JA: 別の言語名で始まる行が来たら止める（直後の行も含む）
                    if re.match(rf"^\s*{lang_re}", next_line, re.I) and j > i:
                        break
                    # 遇到下一个板块标题也停（避免把"其他信息/职业目标"吞进来）
                    # EN: Also stop at the next section heading (so "其他信息/职业目标" (other info / career goal) is not swallowed)
                    # JA: 次のセクション見出しでも止める（「其他信息／职业目标」（その他の情報／キャリア目標）を取り込まないため）
                    if lang_stop_re.match(next_line):
                        break
                    level_parts.append(next_line)
                    j += 1
                level = "，".join(level_parts).strip(" ：:")
                # 清理冗余的 "等级" 前缀
                # EN: Clean up a redundant "等级" (level) prefix
                # JA: 冗長な「等级」（レベル）の接頭辞を除去する
                level = re.sub(r"^等级[，,]", "", level)
                level = re.sub(r"[，,]等级[，,]", "，", level)
                level = re.sub(r"[，,]等级$", "", level)
                rows.append({
                    "language_name": lang_name,
                    "language_level": level[:120],
                    "language_certificate": "",
                    "language_certificate_time": "",
                    "raw_text": "\n".join(normalized_section[i:j]),
                })
                i = j
            else:
                i += 1
        return rows

    def text_skill_items_51job() -> list[dict[str, Any]]:
        """51job 不单独解析 skills — 技能信息已包含在 communication_assessment（自我评价/自己PR）中。

        EN: 51job does not parse skills separately — skill information is already included in communication_assessment (self-assessment / self-PR).

        JA: 51job ではスキルを個別に解析しない — スキル情報はすでに communication_assessment（自己評価・自己 PR）に含まれている。
        """
        return []

    def text_training_items_51job() -> list[dict[str, Any]]:
        """51job 专用培训经历解析：只扫描 "培训经历" 板块。

        51job 培训经历格式：
            培训经历
            2015/5--2015/10：
            兄弟连（上海校区）
            PHP开发
            1）掌握HTML,CSS+DIV布局...
            2）掌握php面向对象编程...

        也支持单行日期+机构格式：
            2015/5--2015/10：兄弟连（上海校区）
            PHP开发

        EN: 51job-specific training parsing: scans only the "培训经历" (training history) section.

        51job training format:
            培训经历
            2015/5--2015/10：
            兄弟连（上海校区）
            PHP开发
            1）掌握HTML,CSS+DIV布局...
            2）掌握php面向对象编程...

        Also supports the single-line date + institution format:
            2015/5--2015/10：兄弟连（上海校区）
            PHP开发

        JA: 51job 専用の研修歴解析：「培训经历」（研修歴）欄だけをスキャンする。

        51job の研修歴の形式：
            培训经历
            2015/5--2015/10：
            兄弟连（上海校区）
            PHP开发
            1）掌握HTML,CSS+DIV布局...
            2）掌握php面向对象编程...

        1 行の「日付 + 機関」形式にも対応する：
            2015/5--2015/10：兄弟连（上海校区）
            PHP开发
        """
        section = _extract_51job_section("培训经历", _51job_stop_headers)
        if not section:
            return []

        date_re = re.compile(
            r"^\s*(?P<start>(?:19|20)\d{2}[./-]\s*\d{1,2})\s*[-—–~～至到]+\s*(?P<end>(?:19|20)\d{2}[./-]\s*\d{1,2}|至今|现在|目前)\s*[：:]?\s*(?P<rest>.*)$"
        )
        rows = []
        i = 0
        while i < len(section):
            line = section[i]
            m = date_re.match(line)
            if m:
                start = re.sub(r"\s+", "", m.group("start"))
                end_raw = m.group("end")
                end = "至今" if end_raw in ("至今", "现在", "目前") else re.sub(r"\s+", "", end_raw)
                rest = m.group("rest").strip()

                # 初始化字段
                # EN: Initialise fields
                # JA: フィールドを初期化する
                org_name = ""
                train_name = ""
                cert_name = ""
                desc_lines = []

                # 如果日期行末尾有机构名（单行格式）
                # EN: If the date line ends with an institution name (single-line format)
                # JA: 日付行の末尾に機関名がある場合（1 行形式）
                if rest:
                    org_name = rest

                # 从下一行开始收集机构、课程、描述
                # EN: Collect institution, course and description starting from the next line
                # JA: 次の行から機関・コース・説明を集める
                j = i + 1
                while j < len(section):
                    c = section[j]
                    # 遇到另一个日期开头就停
                    # EN: Stop at another line starting with a date
                    # JA: 別の日付で始まる行が来たら止める
                    if date_re.match(c):
                        break
                    if not org_name:
                        org_name = c
                    elif not train_name:
                        train_name = c
                    elif not cert_name and re.search(r"证书|级别|资格|NCIE|工程师", c):
                        cert_name = c
                    else:
                        desc_lines.append(c)
                    j += 1

                # 日期格式化
                # EN: Date formatting
                # JA: 日付の整形
                start_fmt = re.sub(r"(\d{4})[./-](\d{1,2})",
                                   lambda m2: f"{m2.group(1)}年{int(m2.group(2)):02d}月01日", start)
                if end == "至今":
                    end_fmt = ""
                else:
                    end_fmt = re.sub(r"(\d{4})[./-](\d{1,2})",
                                     lambda m2: f"{m2.group(1)}年{int(m2.group(2)):02d}月01日", end)

                description = "\n".join(desc_lines).strip()
                raw = "\n".join(section[i:j])

                rows.append({
                    "sequence_no": len(rows) + 1,
                    "organization_name": org_name[:100],
                    "training_name": train_name or org_name[:60],
                    "start_ym": start_fmt,
                    "end_ym": end_fmt,
                    "certificate_name": cert_name,
                    "description": description[:500],
                    "raw_text": raw,
                })
                i = j
            else:
                i += 1
        return rows

    def text_project_items_51job() -> list[dict[str, Any]]:
        """51job 专用项目经验解析：只扫描 "项目经验" 板块。

        51job 项目经验格式：
            项目经验
            2015/9--2015/9：蘑菇街电子商城
            软件环境：WAMP开发环境
            开发工具：PHP
            项目描述：基于MVC模式的蘑菇街电子商城的开发...
            责任描述：负责商城的订单处理...

        EN: 51job-specific project parsing: scans only the "项目经验" (project experience) section.

        51job project format:
            项目经验
            2015/9--2015/9：蘑菇街电子商城
            软件环境：WAMP开发环境
            开发工具：PHP
            项目描述：基于MVC模式的蘑菇街电子商城的开发...
            责任描述：负责商城的订单处理...

        JA: 51job 専用のプロジェクト経験解析：「项目经验」（プロジェクト経験）欄だけをスキャンする。

        51job のプロジェクト経験の形式：
            项目经验
            2015/9--2015/9：蘑菇街电子商城
            软件环境：WAMP开发环境
            开发工具：PHP
            项目描述：基于MVC模式的蘑菇街电子商城的开发...
            责任描述：负责商城的订单处理...
        """
        section = _extract_51job_section("项目经验", _51job_stop_headers)
        if not section:
            return []

        # 项目标题行：日期--日期：项目名 或 项目名（无日期）
        # EN: Project heading line: date--date: project name, or project name (no date)
        # JA: プロジェクトの見出し行：日付--日付：プロジェクト名、またはプロジェクト名（日付なし）
        date_header_re = re.compile(
            r"^\s*(?:(?P<start>(?:19|20)\d{2}[./-]\s*\d{1,2})\s*[-—–~～至到]+\s*(?P<end>(?:19|20)\d{2}[./-]\s*\d{1,2}|至今|现在|目前))?\s*[：:]?\s*(?P<name>.+?)\s*$"
        )
        # 标签化字段
        # EN: Labelled fields
        # JA: ラベル付きのフィールド
        label_map = {
            "软件环境": "software_env",
            "开发工具": "dev_tools",
            "开发环境": "dev_env",
            "项目描述": "project_desc",
            "项目职责": "project_duties",
            "责任描述": "responsibilities",
            "技术栈": "tech_stack",
            "技术要点": "tech_points",
        }
        label_re = re.compile(r"^\s*(软件环境|开发工具|开发环境|项目描述|项目职责|责任描述|技术栈|技术要点)\s*[：:]\s*(.*)$")

        rows = []
        i = 0
        while i < len(section):
            line = section[i]
            m = date_header_re.match(line)
            if not m:
                i += 1
                continue

            start_raw = m.group("start")
            end_raw = m.group("end")
            name = m.group("name").strip().lstrip("：:")

            # 收集后续标签化字段
            # EN: Collect the following labelled fields
            # JA: 後続のラベル付きフィールドを集める
            fields: dict[str, str] = {}
            j = i + 1
            while j < len(section):
                c = section[j]
                # 遇到另一个项目标题（以日期或明显项目名开头）就停
                # EN: Stop at another project heading (starting with a date or an obvious project name)
                # JA: 別のプロジェクト見出し（日付または明らかなプロジェクト名で始まる）が来たら止める
                if date_header_re.match(c) and j > i + 1:
                    # 检查是否真的是下一个项目（不是标签化内容）
                    # EN: Check whether it really is the next project (not labelled content)
                    # JA: 本当に次のプロジェクトか（ラベル付きの内容ではないか）を確認する
                    nm = date_header_re.match(c)
                    if nm and nm.group("start"):
                        break
                lm = label_re.match(c)
                if lm:
                    label = lm.group(1)
                    value = lm.group(2).strip()
                    # 收集该标签下的多行内容
                    # EN: Collect the multi-line content under this label
                    # JA: このラベルの下の複数行の内容を集める
                    k = j + 1
                    while k < len(section):
                        nk = section[k]
                        nk_label = label_re.match(nk)
                        if nk_label:
                            break
                        # 遇到下一个项目标题也停
                        # EN: Also stop at the next project heading
                        # JA: 次のプロジェクト見出しでも止める
                        if date_header_re.match(nk) and nk_label is None and date_header_re.match(nk).group("start"):
                            break
                        if value:
                            value += " " + nk
                        else:
                            value = nk
                        k += 1
                    fields[label_map.get(label, label)] = value
                    j = k
                else:
                    j += 1

            # 日期格式化
            # EN: Date formatting
            # JA: 日付の整形
            if start_raw:
                start_fmt = re.sub(r"(\d{4})[./-](\d{1,2})",
                                   lambda m2: f"{m2.group(1)}年{int(m2.group(2)):02d}月01日",
                                   re.sub(r"\s+", "", start_raw))
            else:
                start_fmt = ""

            if end_raw:
                end_clean = re.sub(r"\s+", "", end_raw)
                end_fmt = "" if end_clean in ("至今", "现在", "目前") else re.sub(
                    r"(\d{4})[./-](\d{1,2})",
                    lambda m2: f"{m2.group(1)}年{int(m2.group(2)):02d}月01日",
                    end_clean)
            else:
                end_fmt = ""

            # 构建描述
            # EN: Build the description
            # JA: 説明を組み立てる
            desc_parts = []
            if "software_env" in fields and fields["software_env"]:
                desc_parts.append(f"软件环境：{fields['software_env']}")
            if "dev_tools" in fields and fields["dev_tools"]:
                desc_parts.append(f"开发工具：{fields['dev_tools']}")
            if "dev_env" in fields and fields["dev_env"]:
                desc_parts.append(f"开发环境：{fields['dev_env']}")
            if "project_desc" in fields and fields["project_desc"]:
                desc_parts.append(f"项目描述：{fields['project_desc']}")
            description = "；".join(desc_parts).strip()

            # 责任描述单独放在 responsibilities
            # EN: The responsibility description goes separately into responsibilities
            # JA: 担当業務の説明は responsibilities に個別に入れる
            responsibilities = fields.get("responsibilities", "") or fields.get("project_duties", "")

            raw = "\n".join(section[i:j])

            rows.append({
                "sequence_no": len(rows) + 1,
                "fingerprint": "",
                "project_name": name[:120],
                "company_or_client": "",
                "role_name": "",
                "start_ym": start_fmt,
                "end_ym": end_fmt,
                "description": description[:600],
                "responsibilities": responsibilities[:500],
                "achievements": "",
                "keywords": fields.get("tech_stack", "")[:200],
                "raw_text": raw,
            })
            i = j

        return rows

    # ===== 51job 专用解析器完成 =====
    # EN: ===== End of the 51job-specific parser =====
    # JA: ===== 51job 専用パーサーここまで =====

    text_edus_51job = text_education_items_51job()
    text_certs_51job = text_certificate_items_51job()
    text_langs_51job = text_language_items_51job()
    text_trainings_51job = text_training_items_51job()
    text_projects_51job = text_project_items_51job()
    text_skills_51job = text_skill_items_51job()

    def text_education_items() -> list[dict[str, Any]]:
        rows = []
        normalized = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", clean_text.replace("\r", ""))
        lines = [re.sub(r"\s+", " ", x).strip(" |│") for x in normalized.splitlines() if x.strip()]
        degree_re = r"(?:本科|大专|专科|学士|硕士|博士|修士|研究生|MBA|EMBA)"
        school_re = r"(?:大学院|大学|学院|高等学校|中学|高中|学校|理工)"
        def append_row(line: str, start: str, end: str, body: str) -> None:
            body = re.sub(r"\s+", " ", body).strip(" |│:：")
            if not body:
                return
            body = re.split(r"(?:语言能力|语言水平|外语水平|工作经历|工作经验|项目经历|项目经验|毕业日期)\s*[:：]?", body, maxsplit=1)[0].strip()
            sm = re.match(rf"(?P<school>.+?{school_re})(?:\s+|/|／|\|)?(?P<rest>.*)$", body, re.I)
            if sm:
                school, rest = sm.group("school").strip(), sm.group("rest").strip()
            else:
                parts = [p for p in re.split(r"\s+|/|／|\|", body) if p]
                school = parts[0] if parts else ""
                rest = " ".join(parts[1:])
            degree = ""
            dm = re.search(rf"(?:^|\s|/|／)({degree_re})\s*$", rest, re.I)
            if dm:
                degree = dm.group(1)
                rest = rest[:dm.start()].strip(" /／|")
            if school and (re.search(school_re, school, re.I) or degree):
                rows.append(education_item({
                    "school_name": school, "school_major_name": rest, "school_degree_type": degree,
                    "school_start_ym": re.sub(r"\s+", "", start or ""),
                    "school_end_ym": re.sub(r"\s+", "", end or ""),
                    "raw_text": line,
                }))
        date_range = re.compile(r"(?P<start>(?:19|20)\d{2}[./-]\s*\d{1,2})\s*[-—–~～至到]+\s*(?P<end>(?:19|20)\d{2}[./-]\s*\d{1,2})\s+(?P<body>.+)")
        for line in lines:
            m = date_range.search(line)
            if m:
                append_row(line, m.group("start"), m.group("end"), m.group("body"))
                continue
            m = re.search(r"(?:学历|教育程度|毕业院校)\s*[:：]?\s*(.+)", line, re.I)
            if m and (re.search(school_re, m.group(1), re.I) or re.search(degree_re, m.group(1), re.I)):
                append_row(line, "", "", m.group(1))
        standalone_date = re.compile(r"^(?P<start>(?:19|20)\d{2}[./-]\s*\d{1,2})\s*[-—–~～至到]+\s*(?P<end>(?:19|20)\d{2}[./-]\s*\d{1,2})$")
        for idx, line in enumerate(lines):
            m = standalone_date.match(line)
            if not m or idx == 0:
                continue
            previous = lines[idx - 1]
            following = lines[idx + 1: idx + 4]
            body = " ".join([previous] + following)
            if re.search(r"本科|大专|专科|学士|硕士|博士", body, re.I) and not re.search(r"工作经历|工作职责|项目经历", body, re.I):
                append_row(line, m.group("start"), m.group("end"), body)
        for idx, line in enumerate(lines):
            if not re.search(r"最終学歴|卒業学校|卒業校", line, re.I):
                continue
            for candidate in lines[idx + 1: idx + 4]:
                if re.search(school_re, candidate, re.I):
                    end = ""
                    dm = re.search(r"((?:19|20)\d{2})年\s*(\d{1,2})月", candidate)
                    if dm:
                        end = f"{dm.group(1)}年{int(dm.group(2)):02d}月01日"
                    append_row(candidate, "", end, re.sub(r"\d{4}年\s*\d{1,2}月\s*(?:卒業)?", "", candidate))
                    break
        unique, seen = [], set()
        for row in rows:
            key = (row.get("school_name", ""), row.get("school_start_ym", ""), row.get("school_end_ym", ""), row.get("school_major_name", ""))
            if key not in seen:
                seen.add(key)
                unique.append(row)
        return [r for r in unique if r.get("school_name")]

    def text_education_table_rows() -> list[dict[str, Any]]:
        lines = [re.sub(r"\s+", " ", x).strip(" |│") for x in clean_text.replace("\r", "").splitlines() if x.strip(" |│")]
        degree_re = r"本科|大专|专科|学士|硕士|博士|修士|研究生|MBA|EMBA"
        school_re = r"大学院|大学|学院|高等学校|中学|高中|学校|Institute|University|College"
        date_re = re.compile(r"(?P<start>(?:19|20)\d{2})[./-](?P<sm>\d{1,2})\s*[-—–~～至到]+\s*(?P<end>(?:19|20)\d{2})[./-](?P<em>\d{1,2})")
        rows = []
        heading_idx = next((i for i, x in enumerate(lines) if re.search(r"^(?:教育经历|教育背景|Education(?:\s+Background|\s+Experience)?)\s*$", x, re.I)), None)
        if heading_idx is not None:
            stop_re = re.compile(r"^(?:语言能力|外语水平|工作经历|工作经验|项目经历|项目经验|培训经历|证书|资格|技能|自我评价|个人优势)", re.I)
            section_end = next((i for i in range(heading_idx + 1, len(lines)) if stop_re.search(lines[i])), len(lines))
            section = lines[heading_idx + 1:section_end]
            standalone = re.compile(r"^[（(]?\s*(?P<start>(?:19|20)\d{2})[./-](?P<sm>\d{1,2})\s*[-—–~～至到]+\s*(?P<end>(?:19|20)\d{2})[./-](?P<em>\d{1,2})\s*[）)]?$")
            for i, school_line in enumerate(section):
                if not re.search(school_re, school_line, re.I) or i + 1 >= len(section):
                    continue
                dm = standalone.match(section[i + 1])
                if not dm:
                    continue
                detail = section[i + 2:i + 7]
                major = next((re.sub(r"^专业\s*[:：]?\s*", "", x, flags=re.I).strip() for x in detail if re.match(r"^专业\s*[:：]", x, re.I)), "")
                degree = next((re.sub(r"^学历\s*[:：]?\s*", "", x, flags=re.I).strip() for x in detail if re.match(r"^学历\s*[:：]", x, re.I)), "")
                etype = next((re.sub(r"^是否统招\s*[:：]?\s*", "", x, flags=re.I).strip() for x in detail if re.match(r"^是否统招\s*[:：]", x, re.I)), "")
                if not (major or degree):
                    continue
                start = f"{dm.group('start')}.{int(dm.group('sm')):02d}"
                end = f"{dm.group('end')}.{int(dm.group('em')):02d}"
                rows.append(education_item({
                    "school_name": school_line.strip(),
                    "school_major_name": major, "school_degree_type": degree,
                    "school_education_type": etype,
                    "school_start_ym": start, "school_end_ym": end,
                    "raw_text": "\n".join([school_line, section[i + 1]] + detail[:3]),
                }))
        def make(body: str, start: str, end: str, raw: str):
            body = re.sub(r"\s+", " ", body).strip(" ：:|│")
            sm = re.search(rf"(?P<school>.+?(?:{school_re}))\s*(?P<rest>.*)$", body, re.I)
            if not sm: return
            school, rest = sm.group("school").strip(), sm.group("rest").strip(" /／|│")
            degree = ""
            dm = re.search(rf"(?:^|[/／|│\s])(?P<degree>{degree_re})(?:$|[/／|│\s])", rest, re.I)
            if dm:
                degree = dm.group("degree"); rest = (rest[:dm.start()] + rest[dm.end():]).strip(" /／|│")
            if school and (degree or rest):
                rows.append(education_item({"school_name": school, "school_major_name": rest, "school_degree_type": degree, "school_start_ym": start, "school_end_ym": end, "raw_text": raw}))
        for i, line in enumerate(lines):
            m = date_re.search(line)
            if not m: continue
            start, end = f"{m.group('start')}.{int(m.group('sm')):02d}", f"{m.group('end')}.{int(m.group('em')):02d}"
            body = (line[:m.start()] + line[m.end():]).strip()
            if body and re.search(school_re, body, re.I):
                make(body, start, end, line); continue
            prev = lines[max(0, i-2):i]
            if len(prev) >= 2:
                make(" ".join(prev[-2:]), start, end, "\n".join(prev[-2:] + [line]))
            elif prev:
                make(prev[-1], start, end, "\n".join(prev + [line]))
        unique, seen = [], set()
        for row in rows:
            key = (row.get("school_name", ""), row.get("school_major_name", ""), row.get("school_start_ym", ""), row.get("school_end_ym", ""))
            if key not in seen: seen.add(key); unique.append(row)
        return unique

    text_edus = text_education_items()
    text_edus_table = text_education_table_rows()
    # === 51job 专用教育解析结果优先 ===
    # EN: === 51job-specific education parse results take priority ===
    # JA: === 51job 専用の学歴解析結果を優先 ===
    if text_edus_51job:
        text_edus = text_edus_51job
        fallback_edus = text_edus_51job
    elif len(text_edus_table) >= 1:
        text_edus = text_edus_table
        fallback_edus = text_edus_table
    elif len(text_edus) > len(fallback_edus):
        fallback_edus = text_edus

    text_projects_local = []
    start_idx_local = next((i for i, x in enumerate([re.sub(r"\s+", " ", line).strip() for line in clean_text.splitlines()]) if re.search(r"项目经历|项目经验|项目案例|Project Experience|プロジェクト", x, re.I)), None)
    if start_idx_local is not None:
        lines_local = [re.sub(r"\s+", " ", x).strip(" |│") for x in clean_text.replace("\r", "").splitlines() if x.strip()]
        stop_re = re.compile(r"教育经历|教育背景|教育程度|学历|工作经历|工作经验|语言能力|外语水平|技能|证书|资格|培训|自我评价|自己PR|附加信息", re.I)
        date_re = re.compile(r"(?P<start>(?:19|20)\d{2}[./-]\s*\d{1,2})\s*[-—–~～至到]+\s*(?P<end>(?:19|20)\d{2}[./-]\s*\d{1,2}|至今|现在|目前)")
        events = []
        for idx in range(start_idx_local + 1, len(lines_local)):
            if stop_re.search(lines_local[idx]) and not date_re.search(lines_local[idx]):
                break
            m = date_re.search(lines_local[idx])
            if m:
                title = lines_local[idx][m.end():].strip(" ：:|-—–~～")
                if not title and idx + 1 < len(lines_local):
                    title = lines_local[idx + 1].strip()
                events.append((idx, m, title))
        for n, (idx, m, title) in enumerate(events):
            end_idx = events[n + 1][0] if n + 1 < len(events) else len(lines_local)
            block = lines_local[idx + 1:end_idx]
            if title and block and block[0] == title:
                block = block[1:]
            role = next((re.sub(r"^项目职务\s*[:：]?\s*", "", x).strip() for x in block if re.search(r"项目职务|项目角色|role", x, re.I)), "")
            company = next((re.sub(r"^(?:所在公司|所属公司|客户)\s*[:：]?\s*", "", x).strip() for x in block if re.search(r"所在公司|所属公司|客户", x, re.I)), "")
            body = "\n".join(x for x in block if not re.search(r"项目职务|项目角色|所在公司|所属公司|客户", x, re.I)).strip()
            text_projects_local.append({"sequence_no": n + 1, "project_name": title[:160], "company_or_client": company, "role_name": role, "start_ym": re.sub(r"\s+", "", m.group("start")), "end_ym": "" if m.group("end") in {"至今", "现在", "目前"} else re.sub(r"\s+", "", m.group("end")), "description": strip_project_leading_date(body), "raw_text": body})
        text_projects_local = [r for r in text_projects_local if r.get("project_name")]
    if text_projects_local and len(data.get("project_experiences") or []) == 0:
        data["project_experiences"] = text_projects_local

    data["work_experiences"] = [clean_work_item(x) for x in fallback_works if valid_work_item(clean_work_item(x))]
    data["education_list"] = fallback_edus

    # === 51job 专用：同步更新顶层 education_info ===
    # EN: === 51job-specific: also update the top-level education_info ===
    # JA: === 51job 専用：トップレベルの education_info も同期して更新 ===
    r0_edus = text_edus_51job or fallback_edus or []
    if r0_edus:
        top_edu = max(r0_edus, key=lambda e: int(e.get("school_degree_rank", "1") or "1"))
        data["education_info"] = {
            "school_name": top_edu.get("school_name", ""),
            "school_major_name": top_edu.get("school_major_name", ""),
            "school_degree_type": top_edu.get("school_degree_type", ""),
            "school_degree_rank": top_edu.get("school_degree_rank", "4"),
            "school_education_type": top_edu.get("school_education_type", "全日制大学"),
            "school_start_ym": top_edu.get("school_start_ym", ""),
            "school_end_ym": top_edu.get("school_end_ym", ""),
        }

    def text_certificate_items() -> list[dict[str, Any]]:
        rows = []
        normalized = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", clean_text.replace("\r", ""))
        for line in normalized.splitlines():
            value = re.sub(r"^\s*[■□•·➢➤➣\-*\d.)]+\s*", "", line).strip(" |│")
            if not value or re.search(r"证书|资格|資格|CET|TOEIC|ACCA|驾照|驾驶证|運転免許|执业药师|簿记|語学能力|能力考试", value, re.I) is None:
                continue
            if re.search(r"^(证书|资格证书|資格|Certificates?)\s*[:：]?\s*$", value, re.I):
                continue
            if re.search(r"^[（(].*(?:包括|包含).*(?:证书|资格|培训).*[）)]$", value, re.I):
                continue
            tm = re.search(r"((?:19|20)\d{2})[年./-]\s*(\d{1,2})月?(?:\s*(?:取得|获得|取得日))?", value, re.I)
            cert_time = f"{tm.group(1)}年{int(tm.group(2)):02d}月01日" if tm else ""
            name = re.sub(r"\s*(?:取得|获得|取得日)\s*", " ", value)
            if tm:
                name = name[:tm.start()].strip(" ：:，,")
            rows.append({"certificate_name": name[:160], "certificate_type": "证书", "certificate_time": cert_time, "raw_text": line})
        unique, seen = [], set()
        for row in rows:
            key = (row["certificate_name"], row["certificate_time"])
            if key not in seen:
                seen.add(key)
                unique.append(row)
        return unique

    def text_language_items() -> list[dict[str, Any]]:
        rows = []
        normalized = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", clean_text.replace("\r", ""))
        lang_re = r"(中文|普通话|汉语|英语|英文|日语|日文|德语|法语|韩语|Japanese|English|German|French|Korean)"
        for line in normalized.splitlines():
            if not re.search(lang_re, line, re.I) or re.search(r"工作描述|工作职责|项目简介|负责", line, re.I):
                continue
            names = re.findall(lang_re, line, re.I)
            for name in names:
                level = line[line.lower().find(name.lower()) + len(name):].strip(" ：:|/／,，、")
                level = re.split(r"[，,；;。|]", level, maxsplit=1)[0].strip()[:60]
                if re.search(r"工作|项目|竞赛|流程|内控|职责|厂房|民用|食堂|宿舍|地址|公司", level, re.I):
                    level = ""
                rows.append({"language_name": name, "language_level": level, "language_certificate": "有" if re.search(r"CET|TOEIC|能力考试|等级|证书", level, re.I) else "", "language_certificate_time": "", "raw_text": line})
        unique, seen = [], set()
        for row in rows:
            key = (row["language_name"], row["language_level"])
            if key not in seen:
                seen.add(key)
                unique.append(row)
        return unique

    text_certs = text_certificate_items()
    text_langs = text_language_items()

    # === 51job 专用证书/语言解析结果优先 ===
    # EN: === 51job-specific certificate/language parse results take priority ===
    # JA: === 51job 専用の資格・語学の解析結果を優先 ===
    if text_certs_51job:
        text_certs = text_certs_51job
    if text_langs_51job:
        text_langs = text_langs_51job

    def clean_certificate_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        cleaned, seen = [], set()
        for item in rows or []:
            row = dict(item)
            if not row.get("certificate_type") and row.get("certificate_tpye"):
                row["certificate_type"] = row.get("certificate_tpye")
            row.pop("certificate_tpye", None)
            name = re.sub(r"\s+", " ", str(row.get("certificate_name") or "")).strip(" ：:，,|│（）()")
            if not name or re.search(r"^(?:证书|资格证书|资格|Certificates?)$", name, re.I) or re.search(r"包括.*(?:证书|培训)", name, re.I):
                continue
            if re.match(r"^(?:英语|英文|日语|日文|中文|普通话|德语|法语|韩语)\s*[（(]?(?:CET|TOEIC|熟练|精通|良好|一般)", name, re.I):
                continue
            row["certificate_name"] = name
            key = (row.get("certificate_name"), row.get("certificate_time"))
            if key in seen:
                continue
            seen.add(key)
            cleaned.append(row)
        return cleaned

    # === 51job 专用结果优先覆盖（即使 parser.parse() 已返回了内容）===
    # EN: === 51job-specific results override first (even if parser.parse() already returned content) ===
    # JA: === 51job 専用の結果を優先して上書き（parser.parse() がすでに内容を返していても）===
    if text_certs_51job:
        data["certificate_list"] = clean_certificate_rows(text_certs_51job)
    elif not data.get("certificate_list"):
        data["certificate_list"] = clean_certificate_rows(text_certs)
    if text_langs_51job:
        data["language_list"] = text_langs_51job
    elif not data.get("language_list"):
        data["language_list"] = text_langs
    # === 51job 培训经历优先覆盖 ===
    # EN: === 51job training history overrides first ===
    # JA: === 51job の研修歴を優先して上書き ===
    if text_trainings_51job:
        data["training_list"] = text_trainings_51job
    # === 51job 项目经验优先覆盖 ===
    # EN: === 51job project experience overrides first ===
    # JA: === 51job のプロジェクト経験を優先して上書き ===
    if text_projects_51job:
        data["project_list"] = text_projects_51job

    # === 51job 技能优先覆盖 ===
    # EN: === 51job skills override first ===
    # JA: === 51job のスキルを優先して上書き ===
    if text_skills_51job:
        data["skills_list"] = text_skills_51job

    # 工作经历最终同步到 resumes
    # 注意：不要用 setdefault，因为 parser.parse() 返回的 resumes 通常已经包含空列表占位符，
    # setdefault 在键已存在时不会覆盖，导致 extend_schema 提取的工作经历丢失。
    # EN: Finally sync work history into resumes
    #     Note: do not use setdefault, because the resumes returned by parser.parse() usually already contain empty list placeholders;
    #     setdefault does not overwrite an existing key, so the work history extracted by extend_schema would be lost.
    # JA: 最後に職歴を resumes に同期する
    #     注意：setdefault は使わないこと。parser.parse() が返す resumes には通常すでに空リストのプレースホルダーがあり、
    #     setdefault はキーがあると上書きしないため、extend_schema が抽出した職歴が失われる。
    top_work = text_works_51job_rows or data.get("work_experiences") or []
    top_edu = data.get("education_list") or []
    top_proj = data.get("project_list") or []
    top_train = data.get("training_list") or []
    top_cert = data.get("certificate_list") or []
    top_lang = data.get("language_list") or []
    top_skill = data.get("skills_list") or []
    top_comm = data.get("communication_list") or []
    # 英文版工作经历（51job 双语简历的 Work Experience 板块）
    # EN: English work history (the Work Experience section of 51job bilingual résumés)
    # JA: 英語版の職歴（51job のバイリンガル履歴書の Work Experience 欄）
    top_work_en = (
        [clean_work_item(x) for x in text_works_51job_en_rows if valid_work_item(clean_work_item(x))]
        if text_works_51job_en_rows else []
    )

    def english_resume_sections() -> tuple[list[dict[str, Any]], str, int]:
        """提取 51job 文档中完整英文版本的教育和自评，并返回英文标题组数量。

        EN: Extract the education and self-assessment of the complete English version in a 51job document, and return the number of English heading groups.

        JA: 51job の文書にある完全な英語版の学歴と自己評価を抽出し、英語の見出しグループの数を返す。
        """
        normalized = clean_text.replace("\\n", "\n").replace("\r", "")
        lines = [re.sub(r"\s+", " ", line).strip() for line in normalized.splitlines() if line.strip()]
        heading_patterns = (
            r"^Personal Information$", r"^Self (?:Evaluation|Assessment)$",
            r"^Career Objective$", r"^Work\s*/?\s*Experience$", r"^Education$",
        )
        heading_count = sum(any(re.match(pattern, line, re.I) for pattern in heading_patterns) for line in lines)

        education_rows: list[dict[str, Any]] = []
        education_indices = [index for index, line in enumerate(lines) if re.match(r"^Education$", line, re.I)]
        if education_indices:
            start = education_indices[-1] + 1
            stop_re = re.compile(
                r"^(?:Certifications?|Training|Language\s*Skills?|IT\s*Skills?|Attachments?|"
                r"Career\s*Objective|Self\s*(?:Evaluation|Assessment)|Work\s*/?\s*Experience)$",
                re.I,
            )
            section = []
            for line in lines[start:]:
                if stop_re.match(line):
                    break
                if not re.match(r"^Education$", line, re.I):
                    section.append(line)
            date_re = re.compile(
                r"^(?:\(Overseas\)\s*)?(?P<sy>(?:19|20)\d{2})/(?P<sm>\d{1,2})\s*[-—–~～]+\s*"
                r"(?:(?P<ey>(?:19|20)\d{2})/(?P<em>\d{1,2})|(?P<present>Present))$",
                re.I,
            )
            index = 0
            while index < len(section):
                match = date_re.match(section[index])
                if not match or index + 3 >= len(section):
                    index += 1
                    continue
                school, major, degree = section[index + 1:index + 4]
                if not re.search(r"University|College|Institute|School|Academy", school, re.I):
                    index += 1
                    continue
                education_rows.append(education_item({
                    "school_name": school,
                    "school_major_name": major,
                    "school_degree_type": degree,
                    "school_start_ym": f"{match.group('sy')}.{int(match.group('sm')):02d}",
                    "school_end_ym": (
                        f"{match.group('ey')}.{int(match.group('em')):02d}" if match.group("ey") else ""
                    ),
                    "raw_text": "\n".join(section[index:index + 4]),
                }))
                index += 4

        self_evaluation = ""
        self_indices = [
            index for index, line in enumerate(lines)
            if re.match(r"^Self (?:Evaluation|Assessment)$", line, re.I)
        ]
        if self_indices:
            start = self_indices[-1] + 1
            stop_re = re.compile(
                r"^(?:Career\s*Objective|Work\s*/?\s*Experience|Education|Training|"
                r"Certifications?|Language\s*Skills?|IT\s*Skills?|Attachments?)$",
                re.I,
            )
            paragraphs = []
            for line in lines[start:]:
                if stop_re.match(line):
                    break
                if not re.match(r"^Self (?:Evaluation|Assessment)$", line, re.I):
                    paragraphs.append(line)
            self_evaluation = "\n".join(paragraphs).strip()
        return education_rows, self_evaluation, heading_count

    top_edu_en, self_evaluation_en, english_heading_count = english_resume_sections()

    def merge_list(prev: list | None, top: list) -> list:
        """若 top 有内容优先 top，否则保留 prev（除非 prev 为空时返回空）。

        EN: If top has content, prefer top; otherwise keep prev (returning empty only when prev is empty).

        JA: top に内容があれば top を優先し、なければ prev を残す（prev が空なら空を返す）。
        """
        if top:
            return top
        return list(prev or [])

    if not data.get("resumes"):
        data["resumes"] = [{
            "resume_language": "zh",
            "base_info": data.get("base_info") or {},
            "expected_info": data.get("expected_info") or [],
            "work_experiences": top_work,
            "education_list": top_edu,
            "project_list": top_proj,
            "training_list": top_train,
            "certificate_list": top_cert,
            "language_list": top_lang,
            "skills_list": top_skill,
            "communication_list": top_comm,
        }]
    else:
        for r_idx, r in enumerate(data["resumes"]):
            # 对英文版 resume（index >= 1）优先使用英文工作经历
            # EN: For the English resume (index >= 1), prefer the English work history
            # JA: 英語版の resume（index >= 1）では英語の職歴を優先する
            work_for_this = top_work_en if (r_idx >= 1 and top_work_en) else top_work
            r["work_experiences"] = merge_list(r.get("work_experiences"), work_for_this)
            r["education_list"] = merge_list(r.get("education_list"), top_edu)
            r["project_list"] = merge_list(r.get("project_list"), top_proj)
            r["training_list"] = merge_list(r.get("training_list"), top_train)
            r["certificate_list"] = merge_list(r.get("certificate_list"), top_cert)
            r["language_list"] = merge_list(r.get("language_list"), top_lang)
            r["skills_list"] = merge_list(r.get("skills_list"), top_skill)
            r["communication_list"] = merge_list(r.get("communication_list"), top_comm)

    # 上游 DOM 解析器常只创建中文 resume；此时英文板块虽然已被提取，却没有承载对象。
    # 只有检测到成组英文履历标题并且存在英文工作/教育内容时，才创建真实英文版本。
    # EN: The upstream DOM parser often creates only the Chinese resume; in that case the English section was extracted but has no object to hold it.
    #     A real English version is created only when a group of English history headings is detected and English work/education content exists.
    # JA: 上流の DOM パーサーは中国語の resume しか作らないことが多く、その場合英語の欄は抽出されても入れ物がない。
    #     英語の経歴見出しがまとまって検出され、かつ英語の職歴・学歴の内容がある場合にだけ、実際の英語版を作る。
    has_en_resume = any(
        str(resume.get("resume_language") or resume.get("resume_languge") or "").casefold() == "en"
        for resume in data.get("resumes") or []
    )
    if not has_en_resume and english_heading_count >= 3 and (top_work_en or top_edu_en):
        english_resume = copy.deepcopy((data.get("resumes") or [{}])[0])
        english_resume["resume_language"] = "en"
        english_resume.pop("resume_languge", None)
        # 第二语言版本只保留该板块真实出现的数据；不能用中文工作/自评填补英文空白。
        # EN: The second-language version keeps only data that actually appears in that section; Chinese work/self-assessment must not fill English gaps.
        # JA: 第 2 言語版にはその欄に実際にあるデータだけを残す。中国語の職歴や自己評価で英語の空白を埋めてはならない。
        english_resume["work_experiences"] = top_work_en
        english_resume["education_list"] = top_edu_en
        english_resume.setdefault("base_info", {})["pr"] = self_evaluation_en
        data.setdefault("resumes", []).append(english_resume)

    # 旧字段名向后兼容迁移
    # EN: Backward-compatible migration of old field names
    # JA: 旧フィールド名の後方互換の移行
    _rename_map = {
        "project_experiences": "project_list",
        "training_experiences": "training_list",
        "certificate_info": "certificate_list",
        "language_info": "language_list",
        "skills_info": "skills_list",
        "communication_assessment": "communication_list",
    }
    for r in data.get("resumes", []):
        for old, new in _rename_map.items():
            if old in r and new not in r:
                r[new] = r.pop(old)

    # 删除顶层冗余字段（数据已同步到 resumes 中）
    # EN: Delete redundant top-level fields (the data has been synced into resumes)
    # JA: 冗長なトップレベルのフィールドを削除する（データは resumes に同期済み）
    for key in ("work_experiences", "education_list", "project_experiences", "project_list",
                "communication_assessment", "communication_list",
                "training_experiences", "training_list",
                "certificate_info", "certificate_list",
                "language_info", "language_list",
                "skills_info", "skills_list"):
        data.pop(key, None)
    return data


# ---------- 主流程 ----------
# EN: ---------- Main flow ----------
# JA: ---------- メインフロー ----------
def build_record_from_html(
    html_path: Path,
    parser: CodexGeminiHtmlSchemaParser,
    classifier: DocumentClassifier,
) -> tuple[dict[str, Any] | None, str]:
    """从 HTML 文件构建完整 JSON 记录。

    返回 (record_or_None, short_status)。

    EN: Build a complete JSON record from an HTML file.

    Returns (record_or_None, short_status).

    JA: HTML ファイルから完全な JSON レコードを組み立てる。

    戻り値：(record_or_None, short_status)。
    """
    try:
        html_text = html_path.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        return None, f"read_error:{exc}"

    text = plain_text(html_text)
    if len(text) < 10:
        return None, "empty_text"

    # 从 HTML 文件名提取候选原始文件名（去掉平台/ID/哈希后缀）
    # 例：51job_刘欣_82937083__793273414b0e.html -> 刘欣
    # EN: Extract the candidate's original file name from the HTML file name (removing platform/ID/hash suffixes)
    #     e.g.: 51job_<name>_<id>__<hash>.html -> <name>
    # JA: HTML のファイル名から候補者の元のファイル名を抽出する（プラットフォーム・ID・ハッシュの接尾辞を除く）
    #     例：51job_<氏名>_<ID>__<ハッシュ>.html -> <氏名>
    m = re.match(r"^51job_(.+?)_\d+__[0-9a-f]+\.html$", html_path.name, re.I)
    fake_original_name = m.group(1) if m else html_path.stem
    fake_source_path = str(html_path.resolve())

    try:
        classification = classifier.classify(text, filename=html_path.name)
    except Exception:
        classification = type("C", (), {"document_type": "ambiguous_resume", "reason": "classifier_exception"})()

    if classification.document_type not in {"resume", "ambiguous_resume"}:
        return None, f"non_resume:{classification.document_type}"

    try:
        parsed = parser.parse(html_text, filename=html_path.name, source_path=fake_source_path)
    except Exception as exc:
        return None, f"parser_error:{exc}"

    parsed_work_snapshot = [
        [dict(item) for item in (resume.get("work_experiences") or [])]
        for resume in (parsed.get("resumes") or [])
    ]
    parsed_base_snapshot = [
        dict(resume.get("base_info") or {})
        for resume in (parsed.get("resumes") or [])
    ]

    try:
        structured = extend_schema(parsed, text, html_path.name, fake_source_path)
    except Exception as exc:
        return None, f"extend_schema_error:{exc}"

    # 最终同步：主解析器 DOM 版本工作经历优先级最高
    # 但对于 51job 文件，text_work_items_51job() 已清理了非职责内容（时长/行业/部门/职位），
    # 不应用 DOM 解析器的原始结果覆盖（DOM 结果可能含杂质）
    # EN: Final sync: the main parser's DOM version of work history has the highest priority
    #     But for 51job files, text_work_items_51job() has already removed non-duty content (tenure/industry/department/position),
    #     so the DOM parser's raw result should not override it (the DOM result may contain noise)
    # JA: 最終同期：メインパーサーの DOM 版の職歴が最優先
    #     ただし 51job のファイルでは text_work_items_51job() がすでに職務以外の内容（在職期間・業界・部署・職位）を除去しているため、
    #     DOM パーサーの生の結果で上書きしない（DOM の結果には不要な情報が混じることがある）
    is_51job = html_path.name.lower().startswith("51job")
    structured_resumes = structured.get("resumes") or []
    for index, parsed_work in enumerate(parsed_work_snapshot):
        if index >= len(structured_resumes):
            break
        if index < len(parsed_base_snapshot):
            stable_base = parsed_base_snapshot[index]
            target_base = dict(structured_resumes[index].get("base_info") or {})
            for key in ("full_name", "platform_from", "platform_resume_id", "phone", "email"):
                if stable_base.get(key):
                    target_base[key] = stable_base[key]
            structured_resumes[index]["base_info"] = target_base
        # 51job 文件：使用 extend_schema 的 51job 专有解析结果，不从 DOM 粗糙快照覆盖
        # EN: 51job files: use extend_schema's 51job-specific parse result, not overridden by the rough DOM snapshot
        # JA: 51job のファイル：extend_schema の 51job 専用の解析結果を使い、粗い DOM のスナップショットで上書きしない
        if parsed_work and not is_51job:
            structured_resumes[index]["work_experiences"] = [
                {k: v for k, v in item.items() if k not in {"raw_text", "fingerprint"}}
                for item in parsed_work
            ]
    if structured_resumes and structured_resumes[0].get("work_experiences"):
        sorted_works = sorted(
            structured_resumes[0]["work_experiences"],
            key=lambda item: (1 if not item.get("position_resigned") else 0, str(item.get("position_start") or "")),
            reverse=True,
        )
        first_work = sorted_works[0]
        current = dict(structured.get("current_info") or {})
        for key in ("company_name", "company_employees", "company_industry", "position", "position_dept",
                    "position_report_to", "position_subordinate", "employment_type", "position_salary",
                    "annual_salary_min", "annual_salary_max", "status", "position_start", "position_resigned"):
            current[key] = first_work.get(key) or ""
        structured["current_info"] = current
    structured["resumes"] = structured_resumes
    if structured_resumes and structured_resumes[0].get("base_info"):
        structured["base_info"] = dict(structured_resumes[0]["base_info"])

    # 全域矫正 51job 候选人姓名
    # EN: Correct 51job candidate names across the board
    # JA: 51job の候補者名を全体的に補正する
    correct_fn = _extract_51job_name(text, html_path.name, (structured.get("base_info") or {}).get("full_name", ""))
    if structured.get("base_info"):
        structured["base_info"]["full_name"] = correct_fn
    for r in structured.get("resumes") or []:
        if r.get("base_info"):
            r["base_info"]["full_name"] = correct_fn

    # === 顶层 structured_data 字段规范对齐 ===
    # 从 resumes[0] 同步最高学历到 education_info（若 extend_schema 未设置）
    # EN: === Align top-level structured_data fields with the spec ===
    #     Sync the highest degree from resumes[0] to education_info (if extend_schema did not set it)
    # JA: === トップレベルの structured_data フィールドを仕様に合わせる ===
    #     resumes[0] から最終学歴を education_info に同期する（extend_schema が設定していない場合）
    if not structured.get("education_info"):
        r0 = (structured.get("resumes") or [{}])[0]
        r0_edus = r0.get("education_list") or []
        if r0_edus:
            top_edu = max(r0_edus, key=lambda e: int(e.get("school_degree_rank", "1") or "1"))
            structured["education_info"] = {
                "school_name": top_edu.get("school_name", ""),
                "school_major_name": top_edu.get("school_major_name", ""),
                "school_degree_type": top_edu.get("school_degree_type", ""),
                "school_degree_rank": top_edu.get("school_degree_rank", "4"),
                "school_education_type": top_edu.get("school_education_type", "全日制大学"),
                "school_start_ym": top_edu.get("school_start_ym", ""),
                "school_end_ym": top_edu.get("school_end_ym", ""),
            }
    # 确保顶层查询快照字段存在
    # EN: Make sure the top-level query snapshot fields exist
    # JA: トップレベルの検索用スナップショットのフィールドが存在するようにする
    if structured_resumes and structured_resumes[0].get("expected_info"):
        structured["expected_info"] = structured_resumes[0]["expected_info"]

    # 顶层列表占位（供查询使用，明细保留在 resumes 内）
    # EN: Top-level list placeholders (for queries; the details stay in resumes)
    # JA: トップレベルのリストのプレースホルダー（検索用。明細は resumes 内に残す）
    for list_key in ("certificate_list", "language_list", "skills_list",
                      "training_list", "project_list", "communication_list"):
        structured.setdefault(list_key, [])

    # 工作经历明细：确保 position_achievements 字段存在
    # EN: Work-history details: make sure the position_achievements field exists
    # JA: 職歴の明細：position_achievements フィールドが存在するようにする
    for r in structured.get("resumes") or []:
        for w in (r.get("work_experiences") or []):
            w.setdefault("position_achievements", "")

    # 旧字段名兼容：若 resumes 中仍有旧名，迁移为新名（始终删除旧字段）
    # EN: Old field-name compatibility: if resumes still use old names, migrate them to the new names (always deleting the old fields)
    # JA: 旧フィールド名の互換：resumes に旧名が残っていれば新名に移行する（旧フィールドは常に削除）
    for r in structured.get("resumes") or []:
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

    # 递归删除 structured_data 内部所有 raw_text 字段（仅保留最外层 record 的 raw_text）
    # EN: Recursively delete every raw_text field inside structured_data (keep only the outermost record's raw_text)
    # JA: structured_data 内部の raw_text フィールドを再帰的にすべて削除する（最も外側のレコードの raw_text だけを残す）
    def _strip_inner_raw_text(obj):
        if isinstance(obj, dict):
            obj.pop("raw_text", None)
            for v in obj.values():
                _strip_inner_raw_text(v)
        elif isinstance(obj, list):
            for item in obj:
                _strip_inner_raw_text(item)
    _strip_inner_raw_text(structured)

    # 清除顶层冗余列表字段（明细保留在 resumes 内）
    # EN: Remove redundant top-level list fields (the details stay in resumes)
    # JA: 冗長なトップレベルのリストフィールドを削除する（明細は resumes 内に残す）
    _top_level_blacklist = {"certificate_list", "language_list", "skills_list",
                             "training_list", "project_list", "communication_list",
                             "work_experiences", "education_list", "project_experiences",
                             "communication_assessment", "training_experiences"}
    structured = {k: v for k, v in structured.items() if k not in _top_level_blacklist}

    fallback_date = date_from_mtime(html_path)
    now = datetime.now(TZ_JST).isoformat(timespec="seconds")
    up_date, dl_date, up_src, dl_src = parse_resume_dates(text, fallback_date)
    rec_id = html_record_id(html_path)

    stat = html_path.stat()
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
        "note": "由 run_chinese_english_html_to_json.py 从中英文 HTML 转换，原始 Word 文件不可用时路径为 HTML 路径",
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
            "reader_group": "word_html_dom",
            "converter": "run_chinese_english_html_to_json.py",
            "parser": "codex_gemini_html_schema_parser",
            "status": "success",
            "html_path": str(html_path.resolve()),
            "dom": dom_summary(html_text),
        },
        "classification": {
            "document_type": classification.document_type,
            "reason": getattr(classification, "reason", ""),
        },
        "structured_data": structured,
        "raw_text": text,
        "quality": {
            "full_name": (structured.get("base_info") or {}).get("full_name", ""),
            "has_work": bool((structured.get("resumes") or [{}])[0].get("work_experiences")),
            "work_count": len((structured.get("resumes") or [{}])[0].get("work_experiences") or []),
            "has_education": bool((structured.get("resumes") or [{}])[0].get("education_list")),
            "education_count": len((structured.get("resumes") or [{}])[0].get("education_list") or []),
            "raw_text_length": len(text),
        },
    }
    return record, "success"


def main() -> int:
    args = parse_args()
    if os.name == "nt":
        os.system("title Chinese-English HTML -> JSON")
    html_dir = args.html_dir.resolve()
    json_dir = args.json_dir.resolve()
    json_dir.mkdir(parents=True, exist_ok=True)
    print(f"源HTML目录: {html_dir}" f" / Source HTML directory: {html_dir} / 元の HTML ディレクトリ：{html_dir}")
    print(f"输出JSON目录: {json_dir}" f" / Output JSON directory: {json_dir} / 出力する JSON のディレクトリ：{json_dir}")

    html_files = sorted(html_dir.glob("*.html"), key=lambda p: p.name.casefold())
    if args.limit > 0:
        html_files = html_files[:args.limit]
    print(f"共 {len(html_files)} 个HTML待处理" f" / {len(html_files)} HTML files to process / 処理待ちの HTML：{len(html_files)} 個", flush=True)

    parser = CodexGeminiHtmlSchemaParser()
    classifier = DocumentClassifier()
    map_rows = json.loads(args.map.read_text(encoding="utf-8")) if args.map.is_file() else []
    map_by_html_name = {
        Path(str(row.get("html_path") or "")).name.casefold(): row
        for row in map_rows
        if str(row.get("html_path") or "")
    }

    def english_identity(html_text: str, plain: str, filename: str, source_path: str) -> str:
        """英文简历姓名：优先语义节点/Name 字段，其次源目录和文件名。

        EN: English résumé name: prefer the semantic node / Name field, then the source directory and file name.

        JA: 英語の履歴書の氏名：意味ノード／Name フィールドを優先し、次にソースのディレクトリ名とファイル名。
        """
        bad = re.compile(
            r"resume|curriculum|vitae|engineer|manager|director|specialist|assistant|accountant|"
            r"developer|programmer|financial|analyst|trainee|personal|profile|unknown|basic|information|\bcv\b|\bname\b|\bcfo\b|"
            r"简历|工程师|经理|主管|专员|助理|财务|会计|策划|文案|信贷|高级工程|未知|无关联",
            re.I,
        )

        def clean(value: str) -> str:
            value = re.sub(r"[（(].*?[）)]", " ", value or "")
            value = re.sub(r"\b(?:Mr|Ms|Mrs|Miss)\.?\s+", "", value, flags=re.I)
            value = re.sub(r"^of\s+", "", value, flags=re.I)
            value = re.sub(r"[^A-Za-zÀ-ÖØ-öø-ÿ' .\-\u3400-\u9fff]", " ", value)
            return re.sub(r"\s+", " ", value).strip(" ._-'\t")

        def valid(value: str) -> bool:
            if not value or bad.search(value):
                return False
            if re.fullmatch(r"[\u3400-\u9fff]{2,4}", value):
                return True
            words = re.findall(r"[A-Za-zÀ-ÖØ-öø-ÿ][A-Za-zÀ-ÖØ-öø-ÿ'.-]*", value)
            return 2 <= len(words) <= 4 and all(1 < len(word.strip(".'-")) <= 24 for word in words)

        try:
            soup = BeautifulSoup(html_text, "html.parser")
            for node in soup.select('[data-field="full_name"]'):
                candidate = clean(node.get_text(" ", strip=True))
                if valid(candidate):
                    return candidate
        except Exception:
            pass
        for pattern in (
            r"(?:Full\s+Name|Candidate\s+Name|Name)\s*[:：]\s*([^\n|]{2,60})",
            r"(?:Resume|CV)\s+(?:of\s+)?([A-Z][A-Za-z'.-]+(?:\s+[A-Z][A-Za-z'.-]+){1,3})",
        ):
            match = re.search(pattern, plain[:3000], re.I)
            if match:
                candidate = clean(match.group(1))
                if valid(candidate):
                    return candidate
        stem = re.sub(r"_[a-f0-9]{12}$", "", Path(filename).stem, flags=re.I)
        stem = re.sub(r"(?i)\b(?:resume|cv|curriculum vitae|english|latest|current|personal)\b", " ", stem)
        stem = re.sub(r"\d+", " ", stem)
        for chunk in re.split(r"[_+–—]+|\s+-\s+", stem):
            candidate = clean(chunk)
            if valid(candidate):
                return candidate
        if source_path:
            folder_blacklist = re.compile(
                r"胖子|徐仁洁|老婆|资料|简历|人才|电脑|英文|英语|招聘|resume|e盘|桌面|文档|孙晓丹|sxd|x280|"
                r"营业|财务|人事|工程师|技术|销售|新卒|企画|翻译|总务|物流|贸易|IT$",
                re.I,
            )
            # 只允许紧邻源文件的两级目录，避免把招聘顾问或归档目录当候选人。
            # EN: Allow only the two directory levels directly above the source file, so recruitment consultants' or archive directories are not taken as candidates.
            # JA: ソースファイルのすぐ上の 2 階層のディレクトリだけを許可し、人材コンサルタントやアーカイブのディレクトリを候補者と誤認しないようにする。
            for part in list(Path(source_path).parts[:-1])[-2:][::-1]:
                candidate = clean(part)
                if valid(candidate) and not folder_blacklist.search(part):
                    return candidate
        return ""

    def valid_output_identity(value: str) -> bool:
        value = str(value or "").strip()
        if not value or value in {"未知", "简历", "个人简历", "无关联职", "无关联职位"}:
            return False
        if re.search(r"工程师|程序员|经理|主管|专员|助理|财务|会计|策划|文案|信贷|高级工程|分析师|trainee|engineer|manager|developer|programmer|resume|curriculum|vitae|\bcv\b|\bcfo\b|basic|information|\bname\b|^of\s", value, re.I):
            return False
        return bool(re.fullmatch(r"[\u3400-\u9fff]{2,4}", value) or re.fullmatch(r"[A-Za-zÀ-ÖØ-öø-ÿ][A-Za-zÀ-ÖØ-öø-ÿ'.-]*(?:\s+[A-Za-zÀ-ÖØ-öø-ÿ][A-Za-zÀ-ÖØ-öø-ÿ'.-]*){1,3}", value))
    manifest: list[dict[str, Any]] = []
    last_heartbeat = time.monotonic()
    success = failed = skipped = 0

    for index, html_path in enumerate(html_files, 1):
        record_id_val = html_record_id(html_path)
        record, status = build_record_from_html(html_path, parser, classifier)
        if record and status == "success":
            html_text_for_identity = html_path.read_text(encoding="utf-8", errors="replace")
            text_for_identity = plain_text(html_text_for_identity)
            structured_for_identity = record.get("structured_data") or {}
            parsed_identity = str((structured_for_identity.get("base_info") or {}).get("full_name") or "")
            resolved_identity = extract_candidate_name(
                text_for_identity,
                html_path.name,
                parsed_identity,
                html_text_for_identity,
            )
            if re.fullmatch(r"[\u3400-\u9fff]{2,4}的", resolved_identity or ""):
                resolved_identity = resolved_identity[:-1]
            if resolved_identity:
                identity_base = structured_for_identity.setdefault("base_info", {})
                identity_base["full_name"] = resolved_identity
                identity_base["name"] = resolved_identity
                for identity_resume in structured_for_identity.get("resumes") or []:
                    resume_base = identity_resume.setdefault("base_info", {})
                    resume_base["full_name"] = resolved_identity
                    resume_base["name"] = resolved_identity
                record["quality"]["full_name"] = resolved_identity
            map_row = map_by_html_name.get(html_path.name.casefold(), {})
            original_path = str(map_row.get("source_path") or "")
            fallback_identity = english_identity(
                html_text_for_identity, text_for_identity, html_path.name, original_path
            )
            if fallback_identity and not valid_output_identity(resolved_identity):
                resolved_identity = fallback_identity
                identity_base = structured_for_identity.setdefault("base_info", {})
                identity_base["full_name"] = resolved_identity
                identity_base["name"] = resolved_identity
                for identity_resume in structured_for_identity.get("resumes") or []:
                    resume_base = identity_resume.setdefault("base_info", {})
                    resume_base["full_name"] = resolved_identity
                    resume_base["name"] = resolved_identity
                record["quality"]["full_name"] = resolved_identity
            if original_path:
                record["source"]["original_path"] = original_path
            record["source"]["converter"] = "run_chinese_english_html_to_json.py"
            record["source"]["actual_resume_languages"] = [
                str(resume.get("resume_language") or "").casefold()
                for resume in ((record.get("structured_data") or {}).get("resumes") or [])
                if str(resume.get("resume_language") or "").strip()
            ]
            base_info = (record.get("structured_data") or {}).setdefault("base_info", {})
            map_phone = re.sub(r"\D", "", str(map_row.get("phone") or ""))
            map_email_match = re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", str(map_row.get("email") or ""))
            if not re.fullmatch(r"1[3-9]\d{9}", re.sub(r"\D", "", str(base_info.get("phone") or ""))) and re.fullmatch(r"1[3-9]\d{9}", map_phone):
                base_info["phone"] = map_phone
            if not str(base_info.get("email") or "").strip() and map_email_match:
                base_info["email"] = map_email_match.group(0).casefold()
            for resume in (record.get("structured_data") or {}).get("resumes") or []:
                resume_base = resume.setdefault("base_info", {})
                if base_info.get("phone"):
                    resume_base["phone"] = base_info["phone"]
                if base_info.get("email"):
                    resume_base["email"] = base_info["email"]
            name = record["quality"]["full_name"] or "未知"
            clean_name = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', name).strip()
            safe_name = re.sub(r'[\\/:*?"<>|]', '', clean_name).strip() or "未知"
            if not valid_output_identity(safe_name) or "采集" in safe_name:
                failed += 1
                manifest.append({"index": index, "html": str(html_path), "status": "failed", "reason": "invalid_full_name", "full_name": safe_name})
                print(f"[{index:04d}/{len(html_files):04d}] FAIL  {html_path.name} → invalid_full_name ({safe_name})", flush=True)
                continue
            phone = re.sub(r"\D", "", str(base_info.get("phone") or ""))
            email = re.sub(r'[\\/:*?"<>|]', "", str(base_info.get("email") or "").strip().casefold())
            contact = phone or email or "无联系方式"
            target = json_dir / f"{safe_name}_{contact}.json"
            suffix = 2
            while target.exists():
                try:
                    existing = json.loads(target.read_text(encoding="utf-8"))
                    existing_source = str((existing.get("source") or {}).get("original_path") or "")
                except Exception:
                    existing_source = ""
                if args.force and existing_source and existing_source == original_path:
                    break
                target = json_dir / f"{safe_name}_{contact}_{suffix}.json"
                suffix += 1
            target.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
            success += 1
            wc = record["quality"].get("work_count", 0)
            manifest.append({"index": index, "html": str(html_path), "json": str(target), "status": "success", "full_name": name, "work_count": wc})
            print(f"[{index:04d}/{len(html_files):04d}] OK    {html_path.name} → {name} (工作{wc}段)" f" / [{index:04d}/{len(html_files):04d}] OK    {html_path.name} → {name} ({wc} work entries) / [{index:04d}/{len(html_files):04d}] OK    {html_path.name} → {name}（職歴 {wc} 件）", flush=True)
        else:
            failed += 1
            manifest.append({"index": index, "html": str(html_path), "status": "failed", "reason": status})
            print(f"[{index:04d}/{len(html_files):04d}] FAIL  {html_path.name} → {status}", flush=True)

        if time.monotonic() - last_heartbeat >= args.progress_interval:
            print(f"[心跳] 进度 {index}/{len(html_files)}，成功{success}，失败{failed}，跳过{skipped}" f" / [heartbeat] progress {index}/{len(html_files)}, success {success}, failed {failed}, skipped {skipped} / [ハートビート] 進捗 {index}/{len(html_files)}、成功 {success}、失敗 {failed}、スキップ {skipped}", flush=True)
            last_heartbeat = time.monotonic()

    report = {
        "workflow": "chinese_english_html_to_json",
        "html_dir": str(html_dir),
        "json_dir": str(json_dir),
        "total": len(html_files),
        "success": success,
        "failed": failed,
        "skipped": skipped,
        "items": manifest,
    }
    report_path = json_dir / "_chinese_english_batch_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n=== 中文 + 英文 HTML→JSON 完成 ===" f" / \n=== Chinese + English HTML→JSON finished === / \n=== 中国語 + 英語の HTML→JSON が完了しました ===")
    print(f"总计: {len(html_files)}；成功: {success}；失败: {failed}；跳过: {skipped}" f" / Total: {len(html_files)}; success: {success}; failed: {failed}; skipped: {skipped} / 合計：{len(html_files)}、成功：{success}、失敗：{failed}、スキップ：{skipped}")
    print(f"报告: {report_path}" f" / Report: {report_path} / レポート：{report_path}")
    return 0 if failed == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
