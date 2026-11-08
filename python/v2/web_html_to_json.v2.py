"""complete-transfered-htmls\\web 目录 HTML -> JSON 专用转换脚本。

核心原则（严格执行，宁严勿松）：
1. 顶层 JSON 严格 9 字段：schema_version / record_id / source / extraction / dates /
   classification / structured_data / raw_text / quality
2. structured_data 顶层只 5 个字段：base_info / expected_info / current_info / education_info / resumes
   → ❌ 禁止出现：work_experiences / education_list / project_list / training_list
                / certificate_list / language_list / skills_list / communication_list
                / project_experiences / communication_assessment / training_experiences
3. raw_text 仅存在于最外层（structured_data 的 sibling）；所有子对象不得有 raw_text 字段
4. education_info 严格 7 字段；expected_info 严格 8 字段；current_info 严格 15 字段空结构兜底
5. school_degree_rank ∈ "1"~"7"（字符串）
6. skills_list：个人素质词 → base_info.pr；过滤动作短语「负责…/每天…/上交…」
7. resumes[0].resume_languge == "zh"；中文主版本固定
8. 所有子列表 item 内不得含 raw_text 字段

复用：CodexGeminiHtmlSchemaParser + DocumentClassifier + 四大平台通用后处理工具函数。

EN: Dedicated HTML -> JSON conversion script for the complete-transfered-htmls\\web directory.

Core principles (strictly enforced, better too strict than too loose):
1. The top-level JSON has strictly 9 fields: schema_version / record_id / source / extraction / dates /
   classification / structured_data / raw_text / quality
2. The top level of structured_data has only 5 fields: base_info / expected_info / current_info / education_info / resumes
   → ❌ Forbidden: work_experiences / education_list / project_list / training_list
                / certificate_list / language_list / skills_list / communication_list
                / project_experiences / communication_assessment / training_experiences
3. raw_text exists only at the outermost level (a sibling of structured_data); no sub-object may have a raw_text field
4. education_info strictly 7 fields; expected_info strictly 8 fields; current_info falls back to an empty structure of strictly 15 fields
5. school_degree_rank ∈ "1"~"7" (strings)
6. skills_list: personal-quality words → base_info.pr; filter action phrases "负责… / 每天… / 上交…"
7. resumes[0].resume_languge == "zh"; the Chinese primary version is fixed
8. No item in any sub-list may contain a raw_text field

Reuses: CodexGeminiHtmlSchemaParser + DocumentClassifier + the generic post-processing helpers of the four major platforms.

JA: complete-transfered-htmls\\web ディレクトリ専用の HTML -> JSON 変換スクリプト。

中核の原則（厳格に実行し、緩すぎるより厳しすぎる方がよい）：
1. トップレベルの JSON は厳密に 9 フィールド：schema_version / record_id / source / extraction / dates /
   classification / structured_data / raw_text / quality
2. structured_data のトップレベルは 5 フィールドだけ：base_info / expected_info / current_info / education_info / resumes
   → ❌ 禁止：work_experiences / education_list / project_list / training_list
                / certificate_list / language_list / skills_list / communication_list
                / project_experiences / communication_assessment / training_experiences
3. raw_text は最も外側（structured_data の兄弟要素）にだけ存在し、どのサブオブジェクトも raw_text フィールドを持ってはならない
4. education_info は厳密に 7 フィールド、expected_info は厳密に 8 フィールド、current_info は厳密に 15 フィールドの空の構造で補う
5. school_degree_rank ∈ "1"〜"7"（文字列）
6. skills_list：個人の資質の語 → base_info.pr。動作の語句「负责…／每天…／上交…」を除外する
7. resumes[0].resume_languge == "zh"。中国語主版は固定
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
from email import policy
from email.parser import BytesParser
import hashlib
import importlib.util
import json
import os
import re
import sys
import tempfile
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


def _load_v2_dependency(filename: str, module_name: str) -> Any:
    """Load a Web pipeline dependency whose public filename uses `.v2.py`."""
    path = PYTHON_ROOT / filename
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载 Web v2 依赖: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

# 复用 run_zhilian_html_to_json.py 的现成解析器（求职意向/工作/教育/证书/语言/技能）
# EN: Reuse the existing parsers of run_zhilian_html_to_json.py (job preferences / work / education / certificates / languages / skills)
# JA: run_zhilian_html_to_json.py の既存のパーサー（希望条件・職歴・学歴・資格・語学・スキル）を再利用する
_zhilian_v2 = _load_v2_dependency("c_web_zhilian_rules.v2.py", "c_web_zhilian_rules_dot_v2")
_parse_zhilian_expected_info = _zhilian_v2._parse_zhilian_expected_info
_parse_zhilian_work_experiences = _zhilian_v2._parse_zhilian_work_experiences
_parse_zhilian_education = _zhilian_v2._parse_zhilian_education
_parse_zhilian_certificates = _zhilian_v2._parse_zhilian_certificates
_parse_zhilian_languages = _zhilian_v2._parse_zhilian_languages
_parse_zhilian_skills = _zhilian_v2._parse_zhilian_skills
# 复用中英文语义解析器的现成工具（plain_text/dom_summary/parse_resume_dates）
# EN: Reuse the existing tools of the Chinese-English semantic parser (plain_text / dom_summary / parse_resume_dates)
# JA: 中英の意味解析器の既存のツール（plain_text / dom_summary / parse_resume_dates）を再利用する
_text_rules_v2 = _load_v2_dependency("c_web_text_rules.v2.py", "c_web_text_rules_dot_v2")
liepin_plain_text = _text_rules_v2.plain_text
dom_summary = _text_rules_v2.dom_summary
liepin_parse_resume_dates = _text_rules_v2.parse_resume_dates

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
        default=PROJECT_ROOT / _rc.dirname("complete-transfered-htmls") / "web" / "input",
    )
    p.add_argument(
        "--json-dir",
        type=Path,
        default=PROJECT_ROOT / _rc.dirname("complete-transfered-jsons") / "web",
    )
    p.add_argument(
        "--map",
        dest="map_path",
        type=Path,
        default=PROJECT_ROOT / _rc.dirname("complete-transfered-htmls") / "web" / "web_conversion_map.v2.json",
        help="优先按 Web conversion map 处理；没有 map 时回退到目录扫描" " / Process by the Web conversion map first; fall back to directory scanning if there is no map / まず Web 変換マップに従って処理し、マップがなければディレクトリ走査に切り替える",
    )
    p.add_argument("--limit", type=int, default=0, help="0=全部" " / 0 = all / 0 は全件")
    p.add_argument("--force", action="store_true", help="覆盖已存在 JSON" " / Overwrite existing JSON / 既存の JSON を上書きする")
    p.add_argument("--progress-interval", type=int, default=10)
    p.add_argument("--indices", nargs="+", type=int, default=None,
                   help="仅重跑 map 中指定的序号，供定点修复/复核使用" " / Re-run only the indices given in the map, for targeted repair/review / マップ内の指定した番号だけを再実行する（ピンポイントの修復・確認用）")
    p.add_argument("--random", action="store_true", dest="random_sample",
                   help="从目录中随机抽样（需配合 --limit 使用）" " / Random sampling from the directory (use together with --limit) / ディレクトリからランダムにサンプリングする（--limit と併用）")
    p.add_argument("--seed", type=int, default=20260804,
                   help="随机抽样种子（默认 20260804，可复现）" " / Random sampling seed (default 20260804, reproducible) / ランダムサンプリングのシード（既定 20260804、再現可能）")
    return p.parse_args()


def read_html_text(html_path: Path) -> str:
    """统一 HTML 解码，并对 MHT/EML 先做 MIME 解包。

    EN: Unified HTML decoding, with MIME unpacking first for MHT/EML.

    JA: HTML のデコードを統一し、MHT/EML は先に MIME を展開する。
    """
    raw_bytes = html_path.read_bytes()

    def decode_bytes(data: bytes) -> str:
        if data.startswith(b"\xff\xfe"):
            try:
                return data.decode("utf-16")
            except UnicodeDecodeError:
                pass
        if data.startswith(b"\xfe\xff"):
            try:
                return data.decode("utf-16-be")
            except UnicodeDecodeError:
                pass
        meta_m = re.search(rb"<meta[^>]+charset=['\"]?\s*([a-zA-Z0-9\-]+)", data, re.I)
        if meta_m:
            meta_enc = meta_m.group(1).decode("ascii", errors="ignore").lower()
            if meta_enc in ("utf-8", "utf8", "utf8-sig"):
                meta_enc = "utf-8"
            elif meta_enc in ("gbk", "gb2312", "gb18030"):
                meta_enc = "gb18030"
            try:
                decoded = data.decode(meta_enc)
                if "\ufffd" not in decoded[:500]:
                    return decoded
            except Exception:
                pass
        for enc in ("utf-8", "utf-8-sig", "gb18030", "gbk", "big5", "utf-16"):
            try:
                decoded = data.decode(enc)
                if "\ufffd" in decoded[:200]:
                    continue
                if any(marker in decoded for marker in (
                    "个人信息", "简历", "姓名", "求职意向", "工作经历", "resume", "experience"
                )):
                    return decoded
            except Exception:
                continue
        return data.decode("utf-8", errors="replace")

    suffix = html_path.suffix.lower()
    if suffix in {".mht", ".mhtml", ".eml"}:
        try:
            message = BytesParser(policy=policy.default).parsebytes(raw_bytes)
            html_parts: list[bytes] = []
            text_parts: list[bytes] = []
            parts = message.walk() if message.is_multipart() else [message]
            for part in parts:
                content_type = (part.get_content_type() or "").lower()
                if content_type not in {"text/html", "text/plain"}:
                    continue
                body = part.get_payload(decode=True)
                if not body:
                    continue
                if content_type == "text/html":
                    html_parts.append(body)
                else:
                    text_parts.append(body)
            if html_parts:
                return "\n".join(decode_bytes(part) for part in html_parts)
            if text_parts:
                return "\n".join(decode_bytes(part) for part in text_parts)
        except Exception:
            # 有些 .mht 文件没有合法 MIME 头，继续按普通 HTML/编码探测处理。
            # EN: Some .mht files have no valid MIME header; keep treating them as ordinary HTML with encoding detection.
            # JA: 一部の .mht ファイルには正しい MIME ヘッダーがないため、通常の HTML としてエンコーディングを検出しながら処理を続ける。
            pass
    return decode_bytes(raw_bytes)


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
    def _date_key(item: dict[str, Any]) -> tuple[int, int, int]:
        value = str(item.get("position_start") or "").strip()
        match = re.search(r"((?:19|20)\d{2})[^0-9]?(\d{1,2})?[^0-9]?(\d{1,2})?", value)
        if not match:
            return (0, 0, 0)
        return (int(match.group(1)), int(match.group(2) or 1), int(match.group(3) or 1))

    latest = max(work_experiences, key=_date_key)
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
            # “科技园/科技类学校”这类教育机构没有“大学/学院”后缀，
            # 但日期、专业、学历三者齐全时应保留；不能因“科技”子串
            # 被公司/单位噪声规则误删。
            # EN: Educational institutions like "科技园/科技类学校" (science park / technical school) have no "大学/学院" suffix,
            #     but should be kept when dates, major and degree are all present; they must not be deleted by the company/unit noise rule
            #     just because of the substring "科技" (technology).
            # JA: 「科技园／科技类学校」（サイエンスパーク・技術系学校）のような教育機関には「大学／学院」の接尾辞がないが、
            #     日付・専攻・学歴がすべて揃っていれば残すべきで、「科技」（科学技術）という部分文字列のせいで
            #     会社・団体のノイズのルールにより誤って削除されてはならない。
            if _has_company_suf and degree and major and "科技" in school:
                _has_company_suf = False
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
        # 仅按字段开头/精确值识别板块壳，不能因为机构名含“职业技能”就
        # 把真实培训学校误删。
        # EN: Recognise section shells only by field prefix / exact value; a real training school must not be deleted just because
        #     the institution name contains "职业技能" (vocational skills).
        # JA: セクションの殻はフィールドの先頭・完全一致の値だけで識別する。機関名に「职业技能」（職業技能）が含まれるというだけで
        #     本当の研修学校を誤って削除してはならない。
        _looks_bad = any(
            field == header or field.startswith(header)
            for field in (org, tname)
            for header in _BAD_HEADERS
        )
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
    """按 CONTEXT 的最终 resumes 顺序重建全文搜索缓存，去重且不写字段模板。

    EN: Rebuild the full-text search cache in CONTEXT's final resumes order, deduplicated and without writing field templates.

    JA: CONTEXT の最終的な resumes の順序で全文検索用のキャッシュを作り直す。重複を除き、フィールドのテンプレートは書かない。
    """
    lines: list[str] = []
    seen: set[str] = set()

    def add(value: Any) -> None:
        text = str(value).strip()
        if not text:
            return
        key = re.sub(r"\s+", " ", text).casefold()
        if key in seen:
            return
        seen.add(key)
        lines.append(text)

    resumes = structured_data.get("resumes") or []
    if not resumes:
        return ""
    LIST_FIELDS = [
        "work_experiences", "education_list", "project_list", "training_list",
        "certificate_list", "language_list", "skills_list", "communication_list",
    ]
    for resume in resumes:
        if not isinstance(resume, dict):
            continue
        for key in ("base_info", "expected_list"):
            value = resume.get(key) or {}
            if isinstance(value, list):
                value = value[0] if value and isinstance(value[0], dict) else {}
            if isinstance(value, dict):
                for item_value in value.values():
                    if isinstance(item_value, str) and item_value.strip():
                        add(item_value)
                    elif isinstance(item_value, (int, float)):
                        add(item_value)
        for fname in LIST_FIELDS:
            items = resume.get(fname) or []
            if not isinstance(items, list):
                continue
            for item in items:
                if isinstance(item, dict):
                    for value in item.values():
                        if isinstance(value, str) and value.strip():
                            add(value)
                        elif isinstance(value, (int, float)):
                            add(value)
                elif isinstance(item, str) and item.strip():
                    add(item)
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

# 顶层 JSON 白名单 + 参考顺序
# EN: Top-level JSON whitelist + reference order
# JA: トップレベルの JSON のホワイトリスト + 参照の順序
ALLOWED_TOP_LEVEL_KEYS = ["schema_version", "record_id", "source", "extraction",
                          "dates", "classification", "structured_data", "raw_text", "quality"]
# 顶层必须字段（统一基础字段）
# EN: Required top-level fields (unified base fields)
# JA: トップレベルの必須フィールド（統一した基本フィールド）
TOP_MUST = {"schema_version", "source", "extraction", "dates", "structured_data", "raw_text"}


def _force_top_level_schema(record: dict[str, Any]) -> dict[str, Any]:
    """最后一道闸门：统一顶层字段、SD 五大对象和 raw_text 位置。

    EN: The last gate: unify the top-level fields, the five SD main objects and the position of raw_text.

    JA: 最後のゲート：トップレベルのフィールド、SD の 5 つの主要オブジェクト、raw_text の位置を統一する。
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
                sd_clean[k] = {x: "" for x in EXPECTED_INFO_8_KEYS}
            elif k == "current_info":
                sd_clean[k] = copy.deepcopy(EMPTY_CURRENT_INFO)
            elif k == "education_info":
                sd_clean[k] = copy.deepcopy(EMPTY_EDUCATION_INFO)
            elif k == "resumes":
                sd_clean[k] = []
    # expected_info 是 resumes[0].expected_list[0] 的对象快照。
    # EN: expected_info is an object snapshot of resumes[0].expected_list[0].
    # JA: expected_info は resumes[0].expected_list[0] のオブジェクトのスナップショットである。
    exp_value = sd_clean.get("expected_info")
    if isinstance(exp_value, list):
        exp_value = exp_value[0] if exp_value and isinstance(exp_value[0], dict) else {}
    if not isinstance(exp_value, dict):
        exp_value = {}
    sd_clean["expected_info"] = {
        key: str(exp_value.get(key, "") or "").strip()
        for key in EXPECTED_INFO_8_KEYS
    }
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


def _classification_dict(classification: Any) -> dict[str, Any]:
    if classification is None:
        return {}
    if hasattr(classification, "__dict__"):
        return {str(k): v for k, v in vars(classification).items()}
    if isinstance(classification, dict):
        return dict(classification)
    return {"document_type": str(classification)}


def _is_resume_classification(classification: Any) -> bool:
    value = _classification_dict(classification)
    return str(value.get("document_type") or "").lower() in {"resume", "ambiguous_resume"}


def _contact_values(resumes: list[dict[str, Any]], plain: str) -> tuple[str, str]:
    phone = ""
    email = ""
    for resume in resumes:
        base_info = resume.get("base_info") if isinstance(resume, dict) else {}
        if not isinstance(base_info, dict):
            continue
        phone = phone or str(base_info.get("phone") or base_info.get("mobile_phone") or "").strip()
        email = email or str(base_info.get("email") or "").strip()
    if not phone:
        match = re.search(r"(?<!\d)(1[3-9]\d{9})(?!\d)", plain)
        phone = match.group(1) if match else ""
    if not email:
        match = re.search(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}", plain)
        email = match.group(0) if match else ""
    return phone, email


def _language_folder(resumes: list[dict[str, Any]]) -> str:
    language_names = {
        "zh": "中文", "en": "英文", "ja": "日文", "jp": "日文",
        "ko": "韩文", "de": "德文", "fr": "法文", "es": "西文",
    }
    languages: list[str] = []
    for resume in resumes:
        if not isinstance(resume, dict):
            continue
        value = str(resume.get("resume_language") or resume.get("resume_languge") or "").lower()
        if value and value not in languages:
            languages.append(value)
    if not languages:
        return "待确认语言"
    names = [language_names.get(value, value) for value in languages]
    return "多语言" if len(names) > 1 else names[0]


def _format_month_date(year: str, month: str) -> str:
    return f"{int(year):04d}年{int(month):02d}月01日"


def _section_lines(text: str, starts: tuple[str, ...], stops: tuple[str, ...]) -> list[str]:
    lines = [line.strip() for line in text.splitlines()]
    start_index = -1
    for index, line in enumerate(lines):
        if any(line == marker or line.startswith(marker + "：") or line.startswith(marker + ":") for marker in starts):
            start_index = index + 1
            break
    if start_index < 0:
        return []
    selected: list[str] = []
    for line in lines[start_index:]:
        if any(line == marker or line.startswith(marker + "：") or line.startswith(marker + ":") for marker in stops):
            break
        if line:
            selected.append(line)
    return selected


def _header_name_hint(text: str) -> str:
    """从常见智联/导出 HTML 的 ID 后标题行提取姓名。

    EN: Extract the name from the heading line after the ID in common Zhaopin/export HTML.

    JA: よくある Zhaopin・エクスポートの HTML で、ID の後の見出し行から氏名を抽出する。
    """
    lines = [line.strip().replace("\xa0", " ") for line in text.splitlines()]
    excluded = {
        "智联招聘", "招聘网", "简历", "个人简历", "resume", "cv",
        "姓名", "姓名：", "姓名:", "基本信息", "个人信息",
    }
    for index, line in enumerate(lines):
        if not re.match(r"^(?:ID|编号|简历编号信息|Resume\s*ID)\s*[:：]", line, re.I):
            continue
        for candidate in lines[index + 1:index + 6]:
            candidate = candidate.strip(" |｜")
            if not candidate or candidate in excluded or candidate.casefold() in excluded:
                continue
            if candidate.casefold() in {"male", "female", "男", "女"}:
                continue
            if any(token in candidate for token in ("手机", "电话", "邮箱", "E-mail", "Email", "性别", "工作经验", "期望", "教育经历")):
                continue
            if re.search(r"\d{2,}|[：:]", candidate):
                continue
            compact_name = re.sub(r"\s+", "", candidate)
            if re.fullmatch(r"[\u3400-\u9fffA-Za-z·]{2,20}", compact_name):
                return compact_name
    return ""


def _compact_text(value: Any) -> str:
    return re.sub(r"[^0-9A-Za-z\u3400-\u9fff]+", "", str(value or "")).casefold()


def _filename_name_hint(filename: str) -> str:
    stem = Path(str(filename or "")).stem.strip()
    match = re.match(r"(?:Resume|CV|Curriculum\s+Vitae)[_\-\s]+(.+)$", stem, re.I)
    if match:
        candidate = re.sub(r"[_\-]+[a-f0-9]{8,12}$", "", match.group(1), flags=re.I).strip()
        candidate = re.sub(r"\s+", " ", candidate)
        if candidate and not re.fullmatch(r"(?:resume|cv|简历)", candidate, re.I) and not re.search(r"[：:]|\d{5,}", candidate):
            return candidate

    # Map 中的 filename 通常已经去掉了 staged 文件名前的序号，不能只
    # 依赖“0001_姓名”这个旧格式。对文件名中的独立中文姓名片段做保守兜底，
    # 仅接受 2--8 个连续汉字，并排除平台/性别/简历等通用词，避免把“王女士”
    # 或“中文简历”写成姓名。
    # EN: The filename in the map usually already has the sequence number before the staged file name removed, so we cannot
    #     rely only on the old "0001_name" format. Do a conservative fallback on standalone Chinese name fragments in the file name,
    #     accepting only 2-8 consecutive Han characters and excluding generic words like platform/gender/résumé, so that "王女士" (Ms Wang)
    #     or "中文简历" (Chinese résumé) is not written as the name.
    # JA: マップ中の filename は通常、一時保存したファイル名の前の通し番号がすでに除かれているため、
    #     旧来の「0001_氏名」の形式だけには頼れない。ファイル名中の独立した中国語の氏名の断片に対して保守的な最終手段を取り、
    #     2〜8 文字の連続した漢字だけを受け入れ、プラットフォーム・性別・履歴書などの一般的な語は除いて、「王女士」（王さん）や
    #     「中文简历」（中国語の履歴書）を氏名として書かないようにする。
    generic = {
        "简历", "中文", "英文", "日文", "日语", "日本語", "个人简历", "履历书",
        "履歴書", "招聘", "智联招聘", "前程无忧", "猎聘网", "resume", "cv",
        "先生", "女士", "小姐", "男士", "女性", "男性",
    }
    cleaned = re.sub(r"[_\-]+[a-f0-9]{8,12}$", "", stem, flags=re.I)
    cleaned = re.sub(r"^\d+[_\-]*", "", cleaned)
    honorific_candidate = ""
    for candidate in re.findall(r"[\u3400-\u9fff]{2,8}", cleaned):
        if candidate in generic:
            continue
        if any(candidate.endswith(suffix) for suffix in ("先生", "女士", "小姐", "男士", "女性", "男性")):
            # 当文件名只有“王女士/李先生”这类称呼时，保留完整片段作为
            # 源文件姓名提示；不能让占位姓名覆盖这个可追溯的来源值。
            # EN: When the file name has only a form of address like "王女士/李先生" (Ms Wang / Mr Li), keep the full fragment as the
            #     source-file name hint; a placeholder name must not overwrite this traceable source value.
            # JA: ファイル名に「王女士／李先生」（王さん／李さん）のような呼称しかない場合は、その断片全体を
            #     ソースファイルの氏名のヒントとして残す。プレースホルダーの氏名でこの追跡可能な出所の値を上書きしてはならない。
            honorific_candidate = candidate
            continue
        if candidate in {"工作经历", "教育经历", "培训经历", "项目经历", "自我评价", "基本资料", "个人信息"}:
            continue
        return candidate
    return honorific_candidate


_WEB_DATE_RANGE_RE = re.compile(
    r"^\s*(?P<sy>(?:19|20)\d{2})\s*(?:(?:[./-]\s*(?P<sm>\d{1,3}))|年\s*(?P<sm_cn>\d{1,3})\s*月)"
    r"\s*[-—–~～至到]{1,8}\s*"
    r"(?:(?P<ey>(?:19|20)\d{2})\s*(?:(?:[./-]\s*(?P<em>\d{1,3}))|年\s*(?P<em_cn>\d{1,3})\s*月)|(?P<current>至今|现在|目前|今まで|現職|現在|Now|Present|Current))"
    r"\s*[：:]?\s*(?P<rest>.*)$",
    re.I,
)


def _parse_web_date_range(line: str) -> dict[str, str] | None:
    normalized_line = re.sub(r"(?<=\d)\s+(?=\d)", "", str(line or "").strip())
    match = _WEB_DATE_RANGE_RE.match(normalized_line)
    if not match:
        return None
    start_month = match.group("sm") or match.group("sm_cn") or ""
    current = match.group("current") or ""
    end_raw = current or f"{match.group('ey')}.{match.group('em') or match.group('em_cn')}"
    return {
        "start_year": match.group("sy"),
        "start_month": start_month,
        "end": end_raw,
        "rest": match.group("rest") or "",
    }


def _join_web_date_continuations(lines: list[str]) -> list[str]:
    joined: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index].strip()
        if _parse_web_date_range(line) is None:
            merged = False
            for end_index in range(index + 1, min(len(lines), index + 10)):
                candidate = " ".join(part.strip() for part in lines[index:end_index + 1] if part.strip())
                if _parse_web_date_range(candidate) is not None:
                    line = re.sub(r"(?<=\d)\s+(?=\d)", "", candidate)
                    index = end_index
                    merged = True
                    break
            if merged:
                joined.append(line)
                index += 1
                continue
        if re.match(r"^(?:19|20)\d{2}\s*[./-]\s*\d{1,2}\s*[-—–~～至到]+\s*$", line) and index + 1 < len(lines):
            line = f"{line}{lines[index + 1].strip()}"
            index += 1
        elif (
            _parse_web_date_range(line) is not None
            and index + 1 < len(lines)
            and lines[index + 1].strip().startswith((":", "："))
        ):
            line = f"{line}{lines[index + 1].strip()}"
            index += 1
        joined.append(line)
        index += 1
    return joined


def _text_name_hint(text: str) -> str:
    """兼容 Word/智联/猎聘文本中的姓名标签和首行姓名。

    EN: Supports name labels and first-line names in Word/Zhaopin/Liepin text.

    JA: Word／Zhaopin／Liepin のテキストにある氏名のラベルと 1 行目の氏名に対応する。
    """
    lines = [line.strip().replace("\xa0", " ") for line in text.splitlines() if line.strip()]
    gender_re = re.compile(r"(?:男|女|male|female)\b", re.I)
    excluded = {
        "resume", "cv", "简历", "个人简历", "智联简历", "招聘网", "智联招聘",
        "personal information", "工作经历", "教育经历", "work experience", "education",
    }
    # 一些 51job 外文导出把姓名直接放在正文第一行，下一行才是 ID 或求职状态；
    # 不能等到性别行再判断，否则会把 Male/Female 误认成姓名。
    # EN: Some 51job foreign-language exports put the name directly on the first line of the body, with the ID or job-search status on the next line;
    #     we cannot wait until the gender line to decide, otherwise Male/Female would be mistaken for the name.
    # JA: 51job の外国語のエクスポートの中には、氏名を本文の 1 行目に直接置き、次の行に ID や求職状況を置くものがある。
    #     性別の行まで待って判定すると Male/Female を氏名と誤認してしまう。
    if lines:
        first = re.sub(r"\s+", " ", lines[0]).strip(" |｜")
        if (
            first.casefold() not in excluded
            and not re.search(r"\d|[：:]", first)
            and re.fullmatch(r"[\u3400-\u9fffA-Za-z·,， ]{2,40}", first)
            and (re.search(r"[\u3400-\u9fff]", first) or "," in first or "，" in first or len(first.split()) >= 2)
        ):
            return first
    # Name/名前/姓名 标签可能为“标签<TAB>值”或上下两行。
    # EN: The Name/名前/姓名 label may be "label<TAB>value" or on two lines one above the other.
    # JA: Name／名前／姓名 のラベルは「ラベル<TAB>値」の場合も、上下 2 行に分かれている場合もある。
    for index, line in enumerate(lines[:25]):
        inline = re.split(r"[：:\t]+", line, maxsplit=1)
        if len(inline) == 2 and inline[0].strip().casefold() in {"name", "姓名", "名前"}:
            candidate = inline[1].strip()
            if not candidate and index + 1 < len(lines):
                candidate = lines[index + 1].strip()
                if candidate in {":", "："} and index + 2 < len(lines):
                    candidate = lines[index + 2].strip()
        elif line.casefold() in {"name", "姓名", "名前"} and index + 1 < len(lines):
            candidate = lines[index + 1].strip()
            if candidate in {":", "："} and index + 2 < len(lines):
                candidate = lines[index + 2].strip()
        else:
            continue
        candidate = re.sub(r"\s+", " ", candidate).strip(" |｜")
        if candidate and candidate.casefold() not in excluded and not re.search(r"\d|[：:]", candidate):
            return candidate
    # 多数导出模板把姓名放在首行，下一行是性别/年龄概况。
    # EN: Most export templates put the name on the first line and a gender/age summary on the next.
    # JA: 多くのエクスポートのテンプレートは氏名を 1 行目に置き、次の行に性別・年齢の概要を置く。
    for index, candidate in enumerate(lines[:12]):
        clean = re.sub(r"\s+", " ", candidate).strip(" |｜")
        if clean.casefold() in excluded or re.search(r"\d|[：:]", clean):
            continue
        if not re.fullmatch(r"[\u3400-\u9fffA-Za-z· ]{2,40}", clean):
            continue
        if index + 1 < len(lines) and gender_re.search(lines[index + 1]):
            return clean
        if (
            index + 2 < len(lines)
            and re.fullmatch(r"[A-Za-z·]+", clean)
            and re.fullmatch(r"[A-Za-z·]+", lines[index + 1].strip())
            and gender_re.search(lines[index + 2])
        ):
            return f"{clean} {lines[index + 1].strip()}"
    return ""


def _web_clean_fragment_text(parts: list[str], join_cjk: bool = True) -> str:
    """把 HTML 表格拆出的短片段还原成可读字段，不改变正文内容。

    EN: Restore short fragments split by HTML tables into readable fields, without changing the body content.

    JA: HTML の表で細切れになった短い断片を読みやすいフィールドに戻す。本文の内容は変えない。
    """
    values = [str(part or "").strip() for part in parts if str(part or "").strip()]
    if not values:
        return ""
    value = " ".join(values)
    value = re.sub(r"\s+([,，。；：:、/（）()\[\]【】])", r"\1", value)
    value = re.sub(r"([（(\[【])\s+", r"\1", value)
    value = re.sub(r"\s+([）)\]】])", r"\1", value)
    if join_cjk:
        value = re.sub(r"(?<=[\u3400-\u9fff])\s+(?=[\u3400-\u9fff])", "", value)
    return value.strip(" ：:|｜")


def _web_is_work_label(line: str) -> bool:
    line = str(line or "").strip()
    labels = (
        "工作描述", "工作内容", "职责业绩", "工作职责和业绩", "工作职责",
        "公司描述", "公司性质", "企业性质", "公司规模", "公司行业", "所属行业",
        "公司名称", "任职日期", "职位", "所任职位", "职务", "工作地点",
        "下属人数", "汇报对象", "报告对象", "报 告 对 象", "所在地区", "所在部门",
        "公司", "会社名", "仕事内容",
    )
    return any(line == label or line.startswith(label + "：") or line.startswith(label + ":") for label in labels)


def _web_is_work_metadata_value(value: Any) -> bool:
    """只把字段标签本身（或带冒号的标签）视为元数据，不误伤“专业助理”等真实职位。

    EN: Treat only field labels themselves (or labels with a colon) as metadata, without harming real positions like "专业助理" (professional assistant).

    JA: フィールドのラベルそのもの（またはコロン付きのラベル）だけをメタデータとみなし、「专业助理」（専門アシスタント）のような本当の職位を誤って傷つけない。
    """
    text = str(value or "").strip()
    if not text:
        return True
    labels = (
        "规模", "企业性质", "公司性质", "公司规模", "公司行业", "行业",
        "公司描述", "工作地点", "所在地区", "所在部门", "下属人数",
        "汇报对象", "报告对象", "报 告 对 象", "专业", "学历",
        "Major", "Degree", "公司名称", "任职日期", "公司", "职位", "职务",
    )
    return any(
        text == label or text.startswith(label + "：") or text.startswith(label + ":")
        for label in labels
    )


def _web_clean_work_position(value: Any) -> str:
    """清除职位字段中由薪资列串入的“/元/月”等尾部碎片。

    EN: Remove trailing fragments like "/元/月" (/yuan/month) that leaked from the salary column into the position field.

    JA: 給与の列から職位のフィールドに入り込んだ「/元/月」などの末尾の断片を除く。
    """
    text = str(value or "").replace("\xa0", " ").strip()
    text = re.sub(r"^\s*(?:职位|所任职位|职务)\s*[：:]\s*", "", text, flags=re.I)
    text = re.sub(r"(?:[/／]\s*(?:元|月)\s*)+$", "", text)
    return text.strip(" ：:|｜/")


def _web_trim_work_responsibilities(value: Any) -> str:
    """职责正文只保留工作描述，截掉随后串入的概况/管理字段。

    EN: The duties text keeps only the job description, cutting off overview/management fields that leaked in afterwards.

    JA: 職務の本文には職務説明だけを残し、その後に入り込んだ概要・管理のフィールドを切り落とす。
    """
    text = str(value or "").replace("\xa0", " ").strip()
    text = re.sub(
        r"^\s*(?:工作描述|工作内容|职责业绩|工作职责和业绩|工作职责)\s*[：:]?\s*",
        "",
        text,
        flags=re.I,
    ).strip()
    metadata = (
        "管理经验", "汇报对象", "报告对象", "报 告 对 象", "直接下属", "下属人数",
        "所在地区", "所在部门", "工作地点", "公司性质", "企业性质", "公司规模",
        "公司行业", "公司描述", "所在公司", "离职原因", "工作业绩", "业绩描述",
    )
    pattern = re.compile(
        r"(?:^|\n|(?<=\s))\s*(?:" + "|".join(re.escape(x) for x in metadata) + r")\s*[：:]?",
        re.I,
    )
    match = pattern.search(text)
    if match and match.start() > 0:
        text = text[:match.start()].rstrip(" \t\r\n|｜;；")
    return text.strip()


def _web_is_duration_fragment(line: str) -> bool:
    line = str(line or "").strip()
    if not line:
        return True
    if line in {"(", ")", "（", "）", "[", "]", "【", "】", "|", "｜"}:
        return True
    if line in {"年", "个月", "月", "人", "人以上", "以上"}:
        return True
    return bool(re.match(
        r"^(?:[\[\(（【]?\s*(?:少于|小于|不超过)?\s*\d+(?:\s*[-–]\s*\d+)?\s*"
        r"(?:年|个月|月|人|人以上)?\s*[\]\)）】]?)$",
        line,
        re.I,
    ))


def _web_extract_label_value(lines: list[str], labels: tuple[str, ...], start: int = 0) -> tuple[str, int]:
    """返回某个标签后的值及其所在位置；值可能在下一行。

    EN: Return the value after a label and its position; the value may be on the next line.

    JA: あるラベルの後の値とその位置を返す。値は次の行にあることもある。
    """
    for index in range(max(0, start), len(lines)):
        line = str(lines[index] or "").strip()
        matched = next((label for label in labels if line == label or line.startswith(label + "：") or line.startswith(label + ":")), None)
        if matched is None:
            continue
        value = re.sub(rf"^{re.escape(matched)}\s*[：:]?\s*", "", line).strip()
        if value:
            return value, index
        for next_index in range(index + 1, min(len(lines), index + 5)):
            candidate = str(lines[next_index] or "").strip()
            if candidate and candidate not in {":", "：", "|", "｜"} and not _web_is_work_label(candidate):
                return candidate, next_index
    return "", -1


def _web_date_start_list(lines: list[str]) -> list[tuple[int, dict[str, str]]]:
    starts: list[tuple[int, dict[str, str]]] = []
    for index, line in enumerate(lines):
        info = _parse_web_date_range(line)
        if info:
            starts.append((index, info))
    return starts


def _web_line_is_marker(line: str, markers: set[str] | tuple[str, ...]) -> bool:
    line = str(line or "").strip()
    return any(line == marker or line.startswith(marker + "：") or line.startswith(marker + ":") for marker in markers)


def _web_bounded_section(raw: list[str], marker_index: int, stops: set[str] | tuple[str, ...]) -> list[str]:
    """从某个板块标题开始，截断到下一个板块标题，防止日期串段。

    EN: Start from a section heading and cut at the next section heading, to prevent dates from leaking across sections.

    JA: あるセクション見出しから始めて次のセクション見出しで切り、日付がセクションをまたいでずれ込むのを防ぐ。
    """
    stop_index = next(
        (i for i in range(marker_index + 1, len(raw)) if _web_line_is_marker(raw[i], stops)),
        len(raw),
    )
    return raw[marker_index + 1:stop_index]


def _web_make_work_item(date_info: dict[str, str], company: str, position: str,
                        department: str = "", industry: str = "", employees: str = "",
                        salary: str = "", responsibilities: str = "", report_to: str = "",
                        subordinate: str = "") -> dict[str, str]:
    end_raw = date_info.get("end", "")
    current_markers = {"至今", "现在", "目前", "今まで", "現職", "Now", "Present", "Current"}
    end_match = re.match(r"((?:19|20)\d{2})[./-](\d{1,3})$", end_raw)
    return {
        "company_name": company,
        "company_employees": employees,
        "company_industry": industry,
        "position": position,
        "position_type": "",
        "position_salary": salary,
        "position_dept": department,
        "position_report_to": report_to,
        "position_subordinate": subordinate,
        "employment_type": "全职",
        "annual_salary_min": "",
        "annual_salary_max": "",
        "status": "在职" if end_raw in current_markers else "离职",
        "position_start": _format_month_date(date_info["start_year"], date_info["start_month"]),
        "position_resigned": "" if end_raw in current_markers else _format_month_date(end_match.group(1), end_match.group(2)) if end_match else "",
        "resigned_reason": "",
        "position_responsibilities": responsibilities,
        "position_achievements": "",
    }


def _parse_web_explicit_work_from_plain(text: str) -> list[dict[str, Any]]:
    """解析“任职日期/公司名称/职位”纵向表格，避免标签被当作职责。

    EN: Parse vertical "任职日期/公司名称/职位" (employment dates / company name / position) tables, so labels are not taken as duties.

    JA: 縦型の「任职日期／公司名称／职位」（在職期間・会社名・職位）の表を解析し、ラベルが職務とみなされないようにする。
    """
    raw = [line.strip() for line in str(text or "").splitlines() if line.strip()]
    work_positions = [i for i, line in enumerate(raw) if line in {"工作经历", "工作经验"}]
    if not work_positions:
        return []
    # 同一份导出可能同时有摘要和完整纵向表；只对明确出现表头的板块启用。
    # EN: The same export may have both a summary and a full vertical table; enable this only for sections with an explicit table header.
    # JA: 同じエクスポートに概要と完全な縦型の表の両方があることがある。明確な表見出しがあるセクションだけで有効にする。
    marker_index = next(
        (i for i in work_positions if any(x in raw[i + 1:i + 30] for x in ("任职日期", "公司名称"))),
        -1,
    )
    if marker_index < 0:
        return []
    section_stops = {
        "教育经历", "教育背景", "项目经历", "培训经历", "专业技能", "技能/语言",
        "证书", "语言能力", "自我评价", "工作经历", "工作经验",
    }
    lines = _join_web_date_continuations(_web_bounded_section(raw, marker_index, section_stops))
    starts = _web_date_start_list(lines)
    if not starts:
        return []
    result: list[dict[str, Any]] = []
    for position_index, (line_index, date_info) in enumerate(starts):
        end_index = starts[position_index + 1][0] if position_index + 1 < len(starts) else len(lines)
        window = lines[line_index + 1:end_index]
        values: list[str] = []
        desc_index = -1
        for index, line in enumerate(window):
            if line.startswith(("工作内容", "工作描述", "职责业绩", "工作职责")):
                desc_index = index
                break
            if line in {"任职日期", "公司名称", "职位", "公司", "岗位", "：", ":", "|", "｜"} or _web_is_duration_fragment(line):
                continue
            values.append(line.strip(" ：:"))
        if desc_index >= 0:
            header_values = [x for x in values if x]
            description = _web_clean_fragment_text(window[desc_index + 1:])
        else:
            header_values = values
            description = ""
        if len(header_values) < 2:
            # 某些纵向表把“公司 + 职位”压在同一行（如“有限公司 医生助理检验员”）。
            # EN: Some vertical tables squeeze "company + position" onto one line (e.g. "有限公司 医生助理检验员" (Ltd. doctor's assistant / inspector)).
            # JA: 縦型の表の中には「会社 + 職位」を 1 行に詰め込んだものがある（例：「有限公司 医生助理检验员」（有限会社 医師助手・検査員））。
            if header_values:
                split_match = re.match(
                    r"^(.*?(?:有限公司|有限会社|株式会社|公司|集团|大学|学院|研究院))\s+(.+)$",
                    header_values[0],
                )
                if split_match:
                    header_values = [split_match.group(1), split_match.group(2)]
            if len(header_values) < 2:
                continue
        company = header_values[0]
        position_name = header_values[1]
        if "|" in position_name or "｜" in position_name:
            position_name = re.split(r"[|｜]", position_name, maxsplit=1)[0].strip()
        if not company or not position_name:
            continue
        result.append(_web_make_work_item(date_info, _web_clean_fragment_text([company]), position_name, responsibilities=description))
    def valid_item(item: dict[str, Any]) -> bool:
        position = str(item.get("position") or "").strip()
        company = str(item.get("company_name") or "").strip()
        return bool(company and position and not _web_is_duration_fragment(position) and not _web_is_work_label(position))

    return result if len(result) == len(starts) and all(valid_item(item) for item in result) else []


def _parse_web_51job_work_from_plain(text: str) -> list[dict[str, Any]]:
    """按 51job 纯文本顺序解析：日期→公司→概况→部门/职位→工作描述。

    EN: Parse in 51job plain-text order: dates → company → overview → department/position → job description.

    JA: 51job のプレーンテキストの順序で解析する：期間 → 会社 → 概要 → 部署／職位 → 職務説明。
    """
    raw = [line.strip() for line in str(text or "").splitlines() if line.strip()]
    positions = [i for i, line in enumerate(raw) if line in {"工作经历", "工作经验"}]
    if not positions:
        return []
    # 有完整“任职日期/公司名称”表时交给纵向解析器。
    # EN: When there is a complete "任职日期/公司名称" (employment dates / company name) table, hand it to the vertical parser.
    # JA: 完全な「任职日期／公司名称」（在職期間・会社名）の表がある場合は、縦型のパーサーに任せる。
    if any(x in raw[positions[-1] + 1:positions[-1] + 8] for x in ("任职日期", "公司名称")):
        return []
    marker_index = positions[0]
    section_stops = {
        "教育经历", "教育背景", "项目经历", "培训经历", "专业技能", "技能/语言",
        "证书", "语言能力", "自我评价", "工作经历", "工作经验",
    }
    lines = _join_web_date_continuations(_web_bounded_section(raw, marker_index, section_stops))
    starts = _web_date_start_list(lines)
    if not starts:
        return []
    result: list[dict[str, Any]] = []
    for position_index, (line_index, date_info) in enumerate(starts):
        end_index = starts[position_index + 1][0] if position_index + 1 < len(starts) else len(lines)
        block = lines[line_index + 1:end_index]
        if any(line in section_stops for line in block[:3]):
            continue
        rest = str(date_info.get("rest") or "").strip(" ：:")
        cursor = 0
        company_parts: list[str] = [rest] if rest else []
        if not company_parts:
            while cursor < len(block) and not block[cursor].strip():
                cursor += 1
        # 公司名可能被括号/HTML span 拆成多行；在第一个任职时长或字段标签处截止。
        # EN: The company name may be split over several lines by brackets/HTML spans; stop at the first tenure or field label.
        # JA: 会社名は括弧や HTML の span で複数行に分かれることがある。最初の在職期間かフィールドのラベルで止める。
        while cursor < len(block):
            line = block[cursor].strip()
            if not line:
                cursor += 1
                continue
            if _web_is_work_label(line) or _web_is_duration_fragment(line) or _parse_web_date_range(line):
                break
            if line.startswith(("企业性质", "公司性质", "规模", "所属行业", "公司行业")):
                break
            if company_parts and len(company_parts) >= 8:
                break
            company_parts.append(line.strip(" ：:"))
            cursor += 1
        company = _web_clean_fragment_text(company_parts)
        if not company:
            continue
        # 跳过（500-1000人）/[4个月]等碎片，但保留后面的真实表头。
        # EN: Skip fragments like (500-1000人) / [4个月], but keep the real table header that follows.
        # JA: （500-1000人）／[4个月] などの断片はスキップするが、その後の本当の表見出しは残す。
        header_start = cursor
        while header_start < len(block):
            line = block[header_start].strip()
            if _web_is_work_label(line) and not line.startswith(("所属行业", "公司行业", "规模")):
                break
            if line.startswith(("所属行业", "公司行业", "规模", "工作描述", "工作内容", "职责业绩")):
                break
            if _web_is_duration_fragment(line):
                header_start += 1
                continue
            # (500-1000 / 人 / ) 以及 [4 / 个月 / ]
            # EN: (500-1000 / 人 / ) and [4 / 个月 / ]
            # JA: (500-1000 / 人 / ) と [4 / 个月 / ]
            if line.startswith(("(", "（", "[", "【")) or line in {")", "）", "]", "】"}:
                header_start += 1
                continue
            break
        desc_index = next((i for i, line in enumerate(block) if line.startswith(("工作描述", "工作内容", "职责业绩", "工作职责和业绩"))), -1)
        header_end = desc_index if desc_index >= 0 else len(block)
        header = [(i, block[i].strip()) for i in range(header_start, header_end) if block[i].strip()]
        salary = ""
        employees = ""
        for _, line in header:
            if re.search(r"元\s*/\s*(?:月|年)|RMB", line, re.I):
                salary = line.strip(" |｜")
            employee_match = re.search(r"(?:(?:少于|小于|不超过)\s*)?\d+(?:\s*[-–]\s*\d+)?\s*人(?:以上)?", line)
            if employee_match and not re.search(r"个月|年", line):
                employees = employee_match.group(0).replace(" ", "")
        header_lines = [line for _, line in header]
        industry, industry_value_index = _web_extract_label_value(header_lines, ("所属行业", "公司行业", "行业"))
        industry_explicit = bool(industry)
        industry_index = industry_value_index
        clean_header: list[tuple[int, str]] = []
        skip_next = False
        for local_index, (original_index, line) in enumerate(header):
            if skip_next:
                skip_next = False
                continue
            if line in {"|", "｜", ")", "）", "]", "】"} or _web_is_duration_fragment(line):
                continue
            if any(label in line for label in ("企业性质", "公司性质", "外资", "民营", "国企", "上市")):
                continue
            if re.search(r"元\s*/\s*(?:月|年)|RMB", line, re.I):
                continue
            if re.search(r"(?:(?:少于|小于|不超过)\s*)?\d+(?:\s*[-–]\s*\d+)?\s*人(?:以上)?", line) and not re.search(r"个月|年", line):
                continue
            if line.startswith(("所属行业", "公司行业", "行业")):
                if not industry:
                    inline_value = re.sub(r"^(?:所属行业|公司行业|行业)\s*[：:]?\s*", "", line).strip()
                    if inline_value:
                        industry = inline_value
                # 标签下一行是行业值；行业值不进入职位候选。
                # EN: The line after the label is the industry value; the industry value does not become a position candidate.
                # JA: ラベルの次の行は業界の値であり、業界の値は職位の候補にしない。
                skip_next = not re.search(r"[：:]\s*\S", line)
                continue
            clean_header.append((original_index, line.strip(" |｜")))
        if not industry:
            industry_candidate = next(
                ((idx, line) for idx, line in clean_header if "/" in line or any(k in line for k in ("新能源", "汽车", "机械", "通信", "电子", "贸易", "医药", "医疗", "教育", "环保", "原材料", "消费品"))),
                None,
            )
            if industry_candidate:
                industry = industry_candidate[1]
                clean_header = [(idx, line) for idx, line in clean_header if idx != industry_candidate[0]]
        position_name = ""
        department = ""
        explicit_position, explicit_pos_index = _web_extract_label_value(header_lines, ("职位", "所任职位", "职务"))
        if explicit_position:
            position_name = explicit_position
        elif industry_explicit and industry_value_index >= 0:
            # 行业值可能是“机械 / 设备 / 重工”多行串；消费掉该串后，
            # 紧邻的短文本通常就是部门和职位，后面才是职责正文。
            # EN: The industry value may be a multi-line string like "机械 / 设备 / 重工" (machinery / equipment / heavy industry); after consuming it,
            #     the short text right after is usually the department and position, followed by the duties text.
            # JA: 業界の値は「机械 / 设备 / 重工」（機械・設備・重工業）のような複数行の文字列のことがある。それを消費した後、
            #     すぐ後の短いテキストが通常は部署と職位で、その後に職務の本文が続く。
            post_values: list[tuple[int, str]] = []
            category_end = industry_value_index + 1
            while category_end < len(header_lines):
                token = header_lines[category_end].strip()
                if token in {"/", "｜", "|"}:
                    category_end += 1
                    if category_end < len(header_lines) and header_lines[category_end].strip() not in {"/", "｜", "|"}:
                        category_end += 1
                    continue
                if category_end == industry_value_index + 1:
                    # 行业值的下一行不是分隔符，说明行业只有一个值。
                    # EN: If the line after the industry value is not a separator, the industry has only one value.
                    # JA: 業界の値の次の行が区切りでなければ、業界の値は 1 つだけである。
                    break
                break
            for token in header_lines[category_end:]:
                token = token.strip(" |｜")
                if not token or _web_is_duration_fragment(token) or token in {"/", "｜", "|"}:
                    continue
                if token.startswith(("企业性质", "公司性质", "规模", "公司描述", "所在地区", "所在部门")):
                    continue
                if re.search(r"元\s*/\s*(?:月|年)|RMB", token, re.I):
                    continue
                if len(token) > 80:
                    break
                post_values.append((category_end, token))
                category_end += 1
            if post_values:
                # 51job 的无“工作描述”导出中，行业之后的前两个短值就是
                # “部门、职位”；后面的文本是被 DOM 拆碎的职责正文。
                # EN: In 51job exports without "工作描述" (job description), the first two short values after the industry are
                #     "department, position"; the text after them is the duties text broken up by the DOM.
                # JA: 「工作描述」（職務説明）のない 51job のエクスポートでは、業界の後の最初の 2 つの短い値が
                #     「部署、職位」であり、その後のテキストは DOM によって細切れになった職務の本文である。
                position_name = post_values[1][1] if len(post_values) >= 2 else post_values[0][1]
                if len(post_values) >= 2:
                    department = post_values[0][1]
        elif not explicit_position and not industry_explicit and next(
            (i for i, line in enumerate(header_lines)
             if ("|" in line or "｜" in line) and re.search(r"\d+\s*[-–]\s*\d+", line)),
            -1,
        ) >= 0:
            # 无“所属行业”标签的 51job 模板通常把职位放在第一根“|”前，
            # 后面才是薪资和行业串（如“销售业务跟单 | 4001-6000 元/月 ...”）。
            # EN: 51job templates without an "所属行业" (industry) label usually put the position before the first "|",
            #     followed by the salary and industry string (e.g. "销售业务跟单 | 4001-6000 元/月 ..." (sales order follow-up | 4001-6000 yuan/month ...)).
            # JA: 「所属行业」（所属業界）のラベルのない 51job のテンプレートは、通常、職位を最初の「|」の前に置き、
            #     その後に給与と業界の文字列が続く（例：「销售业务跟单 | 4001-6000 元/月 ...」（営業の受注フォロー | 月 4001〜6000 元 …））。
            salary_line_index = next(
                (i for i, line in enumerate(header_lines)
                 if ("|" in line or "｜" in line) and re.search(r"\d+\s*[-–]\s*\d+", line)),
                -1,
            )
            before_salary = [
                line.strip(" |｜") for line in header_lines[:salary_line_index]
                if line.strip(" |｜") and not _web_is_duration_fragment(line)
            ]
            if before_salary:
                position_tokens = [token for token in before_salary if token not in {"/", "／"}]
                if any(token in before_salary for token in {"/", "／"}):
                    position_name = "/".join(position_tokens)
                    department = ""
                else:
                    position_name = before_salary[-1]
                    if len(before_salary) >= 2:
                        department = before_salary[-2]
        elif clean_header:
            position_name = clean_header[-1][1]
            if len(clean_header) >= 2:
                department = clean_header[-2][1]

        # 上面的通用清理可能仍把行业尾部（如“家电）”）当成职位；
        # 只要能定位到“| 薪资”边界，就以其之前最后一个短值为职位。
        # EN: The generic cleanup above may still take the tail of the industry (e.g. "家电）") as the position;
        #     as long as the "| salary" boundary can be located, take the last short value before it as the position.
        # JA: 上の汎用的な整理では、業界の末尾（例：「家电）」）をまだ職位と誤認することがある。
        #     「| 給与」の境界の位置がわかれば、その前の最後の短い値を職位とする。
        if not explicit_position and not industry_explicit:
            salary_line_index = next(
                (i for i, line in enumerate(header_lines)
                 if ("|" in line or "｜" in line) and re.search(r"\d+\s*[-–]\s*\d+", line)),
                -1,
            )
            if salary_line_index >= 0:
                before_salary = [
                    line.strip(" |｜") for line in header_lines[:salary_line_index]
                    if line.strip(" |｜") and not _web_is_duration_fragment(line)
                ]
                if before_salary:
                    position_tokens = [token for token in before_salary if token not in {"/", "／"}]
                    if any(token in before_salary for token in {"/", "／"}):
                        position_name = "/".join(position_tokens)
                        department = ""
                    else:
                        position_name = before_salary[-1]
                        department = before_salary[-2] if len(before_salary) >= 2 else ""
                industry_line_index = next(
                    (i for i, line in enumerate(header_lines[salary_line_index + 1:], salary_line_index + 1)
                     if any(k in line for k in ("消费品", "汽车", "机械", "通信", "电信", "贸易", "电子", "医药", "医疗", "教育", "环保", "原材料", "服饰", "纺织", "食品", "日化"))),
                    -1,
                )
                if industry_line_index >= 0:
                    industry_tokens: list[str] = []
                    for line in header_lines[industry_line_index:]:
                        value = line.strip(" |｜")
                        if not value or value in {"/", "／"}:
                            continue
                        if value.startswith(("企业性质", "公司性质", "规模", "公司描述")):
                            break
                        industry_tokens.append(value)
                    if industry_tokens:
                        industry = "/".join(industry_tokens)
            else:
                # 没有薪资字段时，51job 会把“职位组”放在行业组之前，
                # 例如“生产主管 / 督导 / 组长 | 快速消费品 / 食品 ...”。
                # EN: Without a salary field, 51job puts the "position group" before the industry group,
                #     e.g. "生产主管 / 督导 / 组长 | 快速消费品 / 食品 ..." (production supervisor / supervisor / team leader | FMCG / food ...).
                # JA: 給与のフィールドがない場合、51job は「職位のグループ」を業界のグループの前に置く。
                #     例：「生产主管 / 督导 / 组长 | 快速消费品 / 食品 ...」（生産主任・監督・班長 | 日用消費財・食品 …）。
                industry_line_index = next(
                    (i for i, line in enumerate(header_lines)
                     if i > 0 and any(k in line for k in ("消费品", "汽车", "机械", "通信", "电信", "贸易", "电子", "医药", "医疗", "教育", "环保", "原材料", "服饰", "纺织", "食品", "日化"))),
                    -1,
                )
                if industry_line_index > 0:
                    position_tokens = [
                        line.strip(" |｜") for line in header_lines[:industry_line_index]
                        if line.strip(" |｜") and not _web_is_duration_fragment(line) and line.strip(" |｜") not in {"/", "／"}
                    ]
                    if position_tokens:
                        position_name = "/".join(position_tokens)
                        department = ""
                    industry_tokens: list[str] = []
                    for line in header_lines[industry_line_index:]:
                        value = line.strip(" |｜")
                        if not value or value in {"/", "／"}:
                            continue
                        if value.startswith(("企业性质", "公司性质", "规模", "公司描述")):
                            break
                        industry_tokens.append(value)
                    if industry_tokens:
                        industry = "/".join(industry_tokens)
        # 无行业字段且只剩两个值时，第一个通常是职位、第二个是行业。
        # EN: With no industry field and only two values left, the first is usually the position and the second the industry.
        # JA: 業界のフィールドがなく値が 2 つだけ残っている場合、通常は 1 つ目が職位、2 つ目が業界である。
        if not explicit_position and not industry_explicit and len(clean_header) == 2 and ("/" in clean_header[1][1] or any(k in clean_header[1][1] for k in ("消费品", "电子技术"))):
            position_name = clean_header[0][1]
            department = ""
        if _web_is_work_metadata_value(position_name) and position_name not in {"担当", "专业助理"}:
            position_name = ""
        if desc_index >= 0:
            first_line = block[desc_index].strip()
            inline_description = re.sub(r"^(?:工作描述|工作内容|职责业绩|工作职责和业绩)\s*[：:]?\s*", "", first_line).strip()
            body = ([inline_description] if inline_description else []) + block[desc_index + 1:]
            responsibilities = _web_clean_fragment_text(body)
        else:
            job_block_index = next((i for i, line in enumerate(block) if line.strip() == position_name), -1)
            responsibilities = _web_clean_fragment_text(block[job_block_index + 1:] if job_block_index >= 0 else [])
        if company and position_name:
            result.append(_web_make_work_item(
                date_info, company, position_name, department, industry, employees, salary, responsibilities,
            ))
    # 只有日期数完全对应、且公司/职位不是时长碎片或标签的候选才作为专用结果。
    # EN: Only candidates whose dates correspond exactly, and whose company/position are not tenure fragments or labels, are used as the dedicated result.
    # JA: 日付の数が完全に対応し、会社・職位が在職期間の断片やラベルでない候補だけを専用の結果として使う。
    def valid_item(item: dict[str, Any]) -> bool:
        company = str(item.get("company_name") or "").strip()
        position = str(item.get("position") or "").strip()
        bad_position = (
            not position or _web_is_duration_fragment(position) or _web_is_work_label(position)
            or _web_is_work_metadata_value(position)
            or any(token in position for token in ("公司描述", "公司性质", "企业性质", "公司规模", "公司行业"))
            or len(position) > 120
        )
        bad_company = (
            not company or _web_is_duration_fragment(company)
            or company in {"教育经历", "培训经历", "项目经历", "技能/语言", "语言能力"}
            or len(company) > 180
        )
        return not bad_company and not bad_position

    return result if len(result) == len(starts) and all(valid_item(item) for item in result) else []


def _parse_web_liepin_work_from_plain(text: str) -> list[dict[str, Any]]:
    """解析猎聘导出中“公司概况→职位→重复日期→职责业绩”的结构。

    EN: Parse the "company overview → position → repeated dates → duties/achievements" structure in Liepin exports.

    JA: Liepin のエクスポートにある「会社概要 → 職位 → 重複した日付 → 職務・実績」の構造を解析する。
    """
    if not any(token in str(text or "") for token in ("公司描述", "职责业绩", "工作职责和业绩")):
        return []
    raw = [line.strip() for line in str(text or "").splitlines() if line.strip()]
    positions = [i for i, line in enumerate(raw) if line in {"工作经历", "工作经验"}]
    if not positions:
        return []
    section_stops = {
        "教育经历", "教育背景", "项目经历", "培训经历", "专业技能", "技能/语言",
        "证书", "语言能力", "自我评价", "工作经历", "工作经验",
    }
    lines = _join_web_date_continuations(_web_bounded_section(raw, positions[-1], section_stops))
    starts = _web_date_start_list(lines)
    # 该模板会在同一段经历的详情区再次输出“薪酬状况/工作地点”日期，
    # 这些不是新的工作记录，必须从经历起点中排除。
    # EN: This template outputs the "薪酬状况/工作地点" (pay / work location) dates again in the details area of the same experience;
    #     these are not new work records and must be excluded from experience start points.
    # JA: このテンプレートは同じ経歴の詳細欄で「薪酬状况／工作地点」（報酬・勤務地）の日付を再度出力する。
    #     これらは新しい職歴ではないため、経歴の開始点から除外しなければならない。
    detail_markers = ("薪酬状况", "工作地点", "薪资状况", "薪资")
    starts = [
        (index, info) for index, info in starts
        if not (
            str(info.get("rest") or "").strip().startswith(detail_markers)
            or (
                index + 1 < len(lines)
                and str(lines[index + 1] or "").strip().startswith(detail_markers)
            )
        )
    ]
    if not starts:
        return []
    # 相同日期连续出现两次时，前一次是概况、后一次是工作详情，合并为一条经历。
    # EN: When the same date appears twice in a row, the first is the overview and the second the job details; merge them into one experience.
    # JA: 同じ日付が 2 回続けて現れた場合、前が概要、後が職務の詳細なので、1 件の経歴に統合する。
    groups: list[tuple[int, int, dict[str, str]]] = []
    index = 0
    while index < len(starts):
        line_index, date_info = starts[index]
        next_index = index + 1
        while next_index < len(starts):
            other_info = starts[next_index][1]
            if (other_info.get("start_year"), other_info.get("start_month"), other_info.get("end")) != (date_info.get("start_year"), date_info.get("start_month"), date_info.get("end")):
                break
            next_index += 1
        group_end = starts[next_index][0] if next_index < len(starts) else len(lines)
        groups.append((line_index, group_end, date_info))
        index = next_index
    result: list[dict[str, Any]] = []
    for line_index, end_index, date_info in groups:
        block = lines[line_index + 1:end_index]
        rest = str(date_info.get("rest") or "").strip(" ：:")
        company_parts: list[str] = [rest] if rest else []
        cursor = 0
        while cursor < len(block):
            line = block[cursor].strip()
            if not line:
                cursor += 1
                continue
            if _web_is_work_label(line) or line.startswith(("工作地点", "下属人数", "职责业绩", "工作职责")):
                break
            if _parse_web_date_range(line):
                break
            # 职位/公司概况前的连续碎片属于公司名（如 Lifetree + asbestos...）。
            # EN: Consecutive fragments before the position/company overview belong to the company name (e.g. Lifetree + asbestos...).
            # JA: 職位・会社の概要の前にある連続した断片は会社名に属する（例：Lifetree + asbestos...）。
            company_parts.append(line.strip(" ：:"))
            cursor += 1
            if len(company_parts) >= 10:
                break
        company = _web_clean_fragment_text(company_parts)
        company = re.sub(r"\s+(?:公司描述|公司性质|公司规模|公司行业)\s*[：:]?.*$", "", company).strip()
        industry, _ = _web_extract_label_value(block, ("公司行业", "所属行业"))
        employees, _ = _web_extract_label_value(block, ("公司规模", "规模"))
        report_to, _ = _web_extract_label_value(block, ("汇报对象", "报告对象", "報告対象"))
        subordinate, _ = _web_extract_label_value(block, ("下属人数", "下属"))
        metadata_values = {
            value.strip() for value in (industry, employees, report_to, subordinate)
            if value and value.strip()
        }
        responsibility_index = next((i for i, line in enumerate(block) if line.startswith(("职责业绩", "工作职责和业绩", "工作职责", "工作描述", "工作内容"))), -1)
        duplicate_date_index = next((i for i, line in enumerate(block) if _parse_web_date_range(line)), -1)
        position_end = duplicate_date_index if duplicate_date_index >= 0 else responsibility_index if responsibility_index >= 0 else len(block)
        # 猎聘公司概况中，行业字段后才是职位；否则“公司描述/性质/规模”
        # 等概况内容会被误拼进职位。行业值可能由“汽车 / 摩托车”多行组成。
        # EN: In the Liepin company overview the position comes after the industry field; otherwise overview content such as "公司描述/性质/规模" (company description/type/size)
        #     would be wrongly spliced into the position. The industry value may consist of several lines like "汽车 / 摩托车" (cars / motorcycles).
        # JA: Liepin の会社概要では職位は業界のフィールドの後にある。そうでないと「公司描述／性质／规模」（会社説明・性質・規模）などの
        #     概要の内容が職位に誤って連結される。業界の値は「汽车 / 摩托车」（自動車・オートバイ）のように複数行のことがある。
        position_start = cursor
        industry_value_index = _web_extract_label_value(block[:position_end], ("公司行业", "所属行业"))[1]
        if industry_value_index >= 0:
            position_start = industry_value_index + 1
            while position_start < position_end:
                token = block[position_start].strip()
                if token in {"/", "／", "|", "｜"}:
                    position_start += 1
                    if position_start < position_end and block[position_start].strip() not in {"/", "／", "|", "｜"}:
                        position_start += 1
                    continue
                break
        position_slice = block[position_start:position_end]
        metadata_boundary = next(
            (i for i, line in enumerate(position_slice) if i > 0 and _web_is_work_label(line)),
            len(position_slice),
        )
        pre_position = [line.strip() for line in position_slice[:metadata_boundary] if line.strip()]
        filtered_position = []
        for line in pre_position:
            if _web_is_work_label(line) or line in {"|", "｜", "公司描述：", "公司性质：", "公司规模：", "公司行业："}:
                continue
            if line.startswith(("公司描述", "公司性质", "公司规模", "公司行业", "规模", "工作地点", "下属人数")):
                continue
            if re.fullmatch(r"(?:未填写|未填|空|暂无)", line):
                continue
            if line in metadata_values or re.fullmatch(r"\d+(?:\s*人|\s*人以上)?", line) or line in {"人", "人以上"}:
                continue
            filtered_position.append(line)
        position_name = ""
        if filtered_position:
            # 行业/公司概况之后的最后一个短片段通常才是职位；前面的
            # “150”“年老牌化工企业”等是公司描述，不能拼进职位。
            # EN: The last short fragment after the industry/company overview is usually the position; earlier ones like
            #     "150", "年老牌化工企业" (a ...-year-old chemical company) are company descriptions and must not be spliced into the position.
            # JA: 業界・会社の概要の後の最後の短い断片が通常は職位である。その前の
            #     「150」「年老牌化工企业」（創業〜年の老舗化学企業）などは会社の説明であり、職位に連結してはならない。
            position_candidates = [x for x in filtered_position if x.strip()]
            if len(position_candidates) > 1:
                tail = position_candidates[-1].strip()
                previous = position_candidates[-2].strip()
                if (
                    len(tail) <= 40
                    and len(previous) <= 40
                    and ("/" in previous or "／" in previous or not re.search(r"[。！？；]", previous))
                    and not re.fullmatch(r"\d+(?:\.\d+)?", previous)
                ):
                    position_candidates = [previous, tail]
                else:
                    position_candidates = [tail]
            position_name = _web_clean_fragment_text(position_candidates)
            position_name = re.sub(r"\s*/\s*", "/", position_name)
            position_name = _web_clean_work_position(position_name)
        if responsibility_index >= 0:
            first_line = block[responsibility_index].strip()
            inline = re.sub(r"^(?:职责业绩|工作职责和业绩|工作职责|工作描述|工作内容)\s*[：:]?\s*", "", first_line).strip()
            responsibilities = _web_clean_fragment_text(([inline] if inline else []) + block[responsibility_index + 1:])
        else:
            responsibilities = ""
        if company and position_name:
            result.append(_web_make_work_item(
                date_info, company, position_name, industry=industry, employees=employees,
                responsibilities=responsibilities, report_to=report_to, subordinate=subordinate,
            ))
    return result if result and all(item.get("company_name") and item.get("position") for item in result) else []


def _parse_web_training_from_plain(text: str) -> list[dict[str, Any]]:
    """按培训段自己的日期/机构/描述边界解析，避免把项目经历当培训。

    EN: Parse by the training section's own date/provider/description boundaries, so project history is not taken as training.

    JA: 研修の段落自身の日付・機関・説明の境界で解析し、プロジェクト経験を研修としないようにする。
    """
    raw = [line.strip() for line in str(text or "").splitlines() if line.strip()]
    positions = [i for i, line in enumerate(raw) if line in {"培训经历", "培训经验"}]
    if not positions:
        return []
    marker_index = positions[-1]
    section_stops = {
        "教育经历", "教育背景", "项目经历", "项目经验", "工作经历", "工作经验",
        "专业技能", "技能/语言", "证书", "语言能力", "自我评价",
        "在校学习情况", "在校情况", "在校实践经历", "兴趣爱好", "附加信息", "其他信息",
    }
    raw_lines = _web_bounded_section(raw, marker_index, section_stops)
    if not raw_lines:
        return []

    single_date_re = re.compile(
        r"^\s*((?:19|20)\d{2})\s*(?:[/\.\-]\s*(\d{1,3})|年\s*(\d{1,3})\s*月)\s*(.*)$",
        re.I,
    )

    def date_info(line: str) -> dict[str, str] | None:
        ranged = _parse_web_date_range(line)
        if ranged:
            return ranged
        match = single_date_re.match(str(line or "").strip())
        if not match:
            return None
        month = match.group(2) or match.group(3) or ""
        return {
            "start_year": match.group(1),
            "start_month": month,
            "end": f"{match.group(1)}.{month}",
            "rest": match.group(4) or "",
        }

    # HTML 表格会把“2018 年 3 月”拆成多个文本节点；局部合并到能识别
    # 日期为止，不能把后面的培训内容一并吞掉。
    # EN: HTML tables split "2018 年 3 月" into several text nodes; merge locally until the date
    #     can be recognised, without swallowing the training content that follows.
    # JA: HTML の表は「2018 年 3 月」を複数のテキストノードに分けてしまう。日付として認識できるところまで局所的に結合し、
    #     後に続く研修の内容まで取り込んではならない。
    lines: list[str] = []
    index = 0
    while index < len(raw_lines):
        current = raw_lines[index]
        if date_info(current):
            lines.append(current)
            index += 1
            continue
        merged = False
        single_candidate: tuple[int, str] | None = None
        for end_index in range(index + 1, min(len(raw_lines), index + 10)):
            candidate = " ".join(raw_lines[index:end_index + 1])
            # 先找完整日期范围；否则“2018 年 01 月 - 2018 年 3 月”会
            # 被提前截成单日期，导致“-2018 年...”串进机构字段。
            # EN: Look for a complete date range first; otherwise "2018 年 01 月 - 2018 年 3 月" would
            #     be cut early into a single date, letting "-2018 年..." slip into the provider field.
            # JA: まず完全な期間を探す。さもないと「2018 年 01 月 - 2018 年 3 月」が
            #     早い段階で単一の日付に切られ、「-2018 年...」が機関のフィールドに入り込んでしまう。
            if _parse_web_date_range(candidate):
                lines.append(candidate)
                index = end_index + 1
                merged = True
                break
            if single_candidate is None and single_date_re.match(candidate):
                single_candidate = (end_index, candidate)
        if not merged and single_candidate is not None:
            end_index, candidate = single_candidate
            lines.append(candidate)
            index = end_index + 1
            merged = True
        if not merged:
            lines.append(current)
            index += 1

    starts = [(i, date_info(line)) for i, line in enumerate(lines)]
    starts = [(i, info) for i, info in starts if info is not None]
    if not starts:
        return []
    result: list[dict[str, Any]] = []
    for pos, (line_index, info) in enumerate(starts):
        end_index = starts[pos + 1][0] if pos + 1 < len(starts) else len(lines)
        window = lines[line_index + 1:end_index]
        rest = str(info.get("rest") or "").strip(" ：:")
        organization, organization_index = _web_extract_label_value(window, ("培训机构", "培训单位", "培训学校"))
        certificate, certificate_index = _web_extract_label_value(window, ("所获证书", "证书"))
        description_index = next(
            (i for i, line in enumerate(window) if line.startswith(("培训描述", "培训内容", "培训说明"))),
            -1,
        )
        candidates: list[str] = []
        # 培训日期行余下内容在不同模板中分别表示“课程名”或“机构名”：
        # 有“培训机构”标签时是课程名；无标签且带“公司/学院/学校”等后缀时是机构名。
        # EN: The rest of a training date line means "course name" or "provider name" depending on the template:
        #     with a "培训机构" (training institution) label it is the course name; without a label and with a suffix like "公司/学院/学校" (company/college/school) it is the provider name.
        # JA: 研修の日付行の残りの内容は、テンプレートによって「コース名」か「機関名」を表す：
        #     「培训机构」（研修機関）のラベルがあればコース名、ラベルがなく「公司／学院／学校」（会社・学院・学校）などの接尾辞があれば機関名。
        if rest and organization and organization != rest:
            candidates.append(rest)
        elif rest and not organization:
            if any(token in rest for token in ("公司", "学院", "学校", "中心", "机构", "株式会社", "有限会社")):
                organization = rest
            else:
                candidates.append(rest)
        skip_indices = {organization_index, certificate_index}
        meta_markers = ("培训机构", "培训单位", "培训学校", "培训地点", "所获证书", "证书", "培训描述", "培训内容", "培训说明")
        first_meta_index = next(
            (i for i, line in enumerate(window) if line.startswith(meta_markers) or line in {"培训时间", "培训内容"}),
            len(window),
        )
        for i, line in enumerate(window[:first_meta_index]):
            if i in skip_indices or line in {"：", ":", "|", "｜"}:
                continue
            if line.startswith(meta_markers):
                continue
            candidates.append(line.strip(" ：:"))
        candidates = [x for x in candidates if x]
        heuristic_title = ""
        heuristic_description = ""
        # 无“培训机构/培训描述”等标签的老模板通常按“机构、课程、说明”
        # 顺序平铺。这里按列顺序拆开，不能把三列整体写入 training_name。
        # EN: Old templates without labels like "培训机构/培训描述" (training institution / description) usually lay out "provider, course, notes"
        #     flat in that order. Split them here by column order; the three columns must not be written into training_name as a whole.
        # JA: 「培训机构／培训描述」（研修機関・研修の説明）などのラベルのない古いテンプレートは、通常「機関・コース・説明」の
        #     順に平らに並べている。ここで列の順に分け、3 列をまとめて training_name に書き込まないようにする。
        if not organization and not certificate and description_index < 0:
            raw_candidates: list[str] = []
            if rest:
                raw_candidates.append(rest)
            raw_candidates.extend(candidates)
            dedup_candidates: list[str] = []
            for candidate in raw_candidates:
                candidate = candidate.strip(" ：:")
                if candidate and candidate not in dedup_candidates:
                    dedup_candidates.append(candidate)
            noise_prefixes = ("曾获", "奖项描述", "活动描述", "校园", "在校学习情况", "在校情况")
            if dedup_candidates and dedup_candidates[0].startswith(noise_prefixes):
                continue
            if len(dedup_candidates) >= 2:
                organization = dedup_candidates[0]
                heuristic_title = dedup_candidates[1]
                heuristic_description = _web_clean_fragment_text(dedup_candidates[2:])
                candidates = []
        # 存在“培训机构”标签时，日期行余下内容就是课程名，即使它
        # 同时也出现在“所获证书”字段中（如“会计上岗证”），仍不能丢弃。
        # EN: When a "培训机构" label exists, the rest of the date line is the course name; even if it
        #     also appears in the "所获证书" (certificates obtained) field (e.g. "会计上岗证" (accounting qualification)), it must not be dropped.
        # JA: 「培训机构」のラベルがある場合、日付行の残りはコース名である。それが
        #     「所获证书」（取得資格）のフィールドにも出ていても（例：「会计上岗证」（会計の就業資格））、捨ててはならない。
        title = heuristic_title or (_web_clean_fragment_text([rest]) if rest and organization and organization != rest else "")
        # 先从带斜杠的“机构/课程”格式拆分。
        # EN: First split the "provider/course" format with a slash.
        # JA: まずスラッシュ付きの「機関／コース」の形式を分割する。
        for candidate in list(candidates) if not title else []:
            if "/" in candidate and not re.search(r"https?://", candidate, re.I):
                left, right = candidate.split("/", 1)
                if not organization and any(token in left for token in ("公司", "学院", "学校", "中心", "机构")):
                    organization = left.strip()
                title = right.strip()
                candidates.remove(candidate)
                break
        if not title:
            useful_candidates = [
                candidate.strip(" /／") for candidate in candidates
                if candidate not in {organization, certificate} and candidate.strip(" /／")
            ]
            # 培训段通常只有“机构 + 课程/培训”两列，所有未被标签消费的
            # 文本都属于同一培训名称，不能只取第一行后丢掉后续内容。
            # EN: A training section usually has only two columns, "provider + course/training"; all text not consumed by labels
            #     belongs to the same training name, so we must not take only the first line and drop the rest.
            # JA: 研修の段落は通常「機関 + コース／研修」の 2 列だけである。ラベルに消費されなかった
            #     テキストはすべて同じ研修名に属するため、1 行目だけを取って残りを捨ててはならない。
            if useful_candidates:
                merged_candidate = " ".join(useful_candidates).strip()
                split_match = re.match(r"^(.*?(?:公司|学院|学校|中心|机构))\s+(.+)$", merged_candidate)
                if split_match and not organization:
                    organization = split_match.group(1).strip()
                    title = split_match.group(2).strip()
                else:
                    title = merged_candidate
        if description_index >= 0:
            first_line = window[description_index].strip()
            inline = re.sub(r"^(?:培训描述|培训内容|培训说明)\s*[：:]?\s*", "", first_line).strip()
            description = _web_clean_fragment_text(([inline] if inline else []) + window[description_index + 1:])
        else:
            description = heuristic_description
        if not title and organization:
            title = organization
            organization = ""
        if not title and not organization:
            continue
        start_ym = _format_month_date(info["start_year"], info["start_month"])
        end_raw = info.get("end") or ""
        end_match = re.match(r"((?:19|20)\d{2})[./-](\d{1,3})$", end_raw)
        end_ym = _format_month_date(end_match.group(1), end_match.group(2)) if end_match else start_ym
        result.append({
            "sequence_no": len(result) + 1,
            "organization_name": organization,
            "training_name": title,
            "start_ym": start_ym,
            "end_ym": end_ym,
            "certificate_name": certificate,
            "description": description,
        })
    return result


def _parse_web_work_from_plain(text: str) -> list[dict[str, Any]]:
    """补齐智联文本日期行带冒号、DOM 表格错位时的工作经历。

    EN: Complete work history when Zhaopin text date lines carry a colon or the DOM table is misaligned.

    JA: Zhaopin のテキストの日付行にコロンが付いている場合や、DOM の表がずれている場合の職歴を補う。
    """
    # 先处理能从 HTML 文本直接确定字段边界的模板；只有候选记录完整时
    # 才返回，避免用低置信结果覆盖通用解析器已有的有效数据。
    # EN: First handle templates whose field boundaries can be determined directly from the HTML text; return only when the candidate record is complete,
    #     so low-confidence results do not overwrite valid data the generic parser already has.
    # JA: まず HTML のテキストから直接フィールドの境界を確定できるテンプレートを処理する。候補のレコードが完全な場合だけ返し、
    #     信頼度の低い結果で汎用パーサーがすでに持つ有効なデータを上書きしないようにする。
    explicit_work = _parse_web_explicit_work_from_plain(text)
    if explicit_work:
        return explicit_work
    liepin_work = _parse_web_liepin_work_from_plain(text)
    if liepin_work:
        return liepin_work
    platform_work = _parse_web_51job_work_from_plain(text)
    if platform_work:
        return platform_work
    lines = _section_lines(
        text,
        ("工作经历", "工作经验"),
        ("教育经历", "教育背景", "项目经历", "语言能力", "培训经历", "专业技能", "证书", "自我评价", "Education", "Project", "Language"),
    )
    lines = _join_web_date_continuations(lines)
    starts: list[tuple[int, dict[str, str]]] = []
    for index, line in enumerate(lines):
        date_info = _parse_web_date_range(line)
        if date_info:
            starts.append((index, date_info))
    works: list[dict[str, Any]] = []
    for position, (line_index, date_info) in enumerate(starts):
        end_index = starts[position + 1][0] if position + 1 < len(starts) else len(lines)
        rest = date_info["rest"].strip()
        header_index = line_index + 1
        header = rest
        company_hint = ""
        if rest and header_index < end_index and "|" not in rest and "｜" not in rest:
            # 智联有时把“公司（任职时长）”放在日期行，把“部门 | 职位 | 薪资”
            # 放在下一行；不能把任职时长误当部门/职位。
            # EN: Zhaopin sometimes puts "company (tenure)" on the date line and "department | position | salary"
            #     on the next line; the tenure must not be taken as the department/position.
            # JA: Zhaopin は「会社（在職期間）」を日付行に、「部署 | 職位 | 給与」を
            #     次の行に置くことがある。在職期間を部署・職位と誤認してはならない。
            next_line = lines[header_index]
            if "|" in next_line or "｜" in next_line:
                company_hint = re.sub(r"\s*[（(][^）)]{1,20}[）)]\s*$", "", rest).strip()
                header = next_line
            elif not _web_is_duration_fragment(next_line) and not next_line.startswith(("公司性质", "企业性质", "规模", "公司行业", "所属行业", "工作描述", "工作内容")):
                # 另一类标准导出把“公司（时长）”放在日期行、把纯职位
                # 放在下一行；若仍把日期行当 header，职位会被置空。
                # EN: Another kind of standard export puts "company (tenure)" on the date line and the bare position
                #     on the next line; if the date line were still treated as the header, the position would be cleared.
                # JA: 別の種類の標準的なエクスポートは「会社（在職期間）」を日付行に、職位だけを
                #     次の行に置く。日付行を header として扱い続けると、職位が空にされてしまう。
                company_hint = re.sub(r"\s*[（(][^）)]{1,20}[）)]\s*$", "", rest).strip()
                header = next_line
        if not header:
            while header_index < end_index and not lines[header_index].strip():
                header_index += 1
            header = lines[header_index] if header_index < end_index else ""
        parts = [part.strip() for part in re.split(r"\s*[|｜]\s*", header) if part.strip()]
        bare_position_after_company = bool(company_hint and header == lines[header_index] and len(parts) == 1 and header.strip())
        if bare_position_after_company:
            company, department, job = company_hint, "", header.strip()
        elif len(parts) >= 3:
            if re.search(r"元/月|元/年|RMB", parts[-1], re.I):
                company, department, job = parts[0], parts[-3], parts[-2]
            else:
                company, department, job = parts[0], parts[-2], parts[-1]
        elif len(parts) == 2:
            if re.search(r"元/月|元/年|RMB", parts[1], re.I):
                company, department, job = "", "", parts[0]
            else:
                company, department, job = parts[0], "", parts[1]
        else:
            tokens = [part.strip() for part in re.split(r"\s{2,}", header) if part.strip()]
            company, department, job = (tokens + ["", "", ""])[:3]
        if company_hint:
            company = company_hint
        if company in {":", "：", "|", "｜"} or job.startswith(("规模", "企业性质", "公司性质")):
            continue
        body_start = header_index + 1 if header else line_index + 1
        body_lines = lines[body_start:end_index]
        salary = ""
        employees = ""
        industry = ""
        responsibilities: list[str] = []
        for body_line in body_lines:
            if body_line.startswith(("规模", "规模:", "规模：")):
                scale_value = re.sub(r"^规模\s*[：:]?\s*", "", body_line).strip()
                scale_parts = [part.strip() for part in scale_value.split("|")]
                employees = scale_parts[0] if scale_parts else ""
                if len(scale_parts) > 1 and re.search(r"元/月|元/年|RMB", scale_parts[1], re.I):
                    salary = scale_parts[1]
            elif body_line.startswith(("公司行业", "行业", "所属行业")):
                industry = re.sub(r"^(?:公司行业|所属行业|行业)\s*[：:]?\s*", "", body_line).strip()
            elif re.search(r"元/月|元/年|RMB", body_line, re.I):
                salary = body_line
            elif "|" in body_line and not body_line.startswith(("企业性质", "公司性质")):
                # 智联导出的公司概况常把“行业 | 企业性质”压成一行。
                # EN: Zhaopin export company overviews often compress "industry | enterprise type" onto one line.
                # JA: Zhaopin のエクスポートの会社概要は「業界 | 企業の性質」を 1 行に詰めることが多い。
                first_part = body_line.split("|", 1)[0].strip()
                if first_part and not industry:
                    industry = first_part
            elif not body_line.startswith(("企业性质", "公司性质")):
                if body_line != job:
                    responsibilities.append(body_line)
        end_raw = date_info["end"]
        end_date_match = re.match(r"((?:19|20)\d{2})[./-](\d{1,3})$", end_raw)
        current_markers = {"至今", "现在", "目前", "今まで", "現職", "現在", "Now", "Present", "Current"}
        works.append({
            "company_name": company,
            "company_employees": employees,
            "company_industry": industry,
            "position": job,
            "position_type": "",
            "position_salary": salary,
            "position_dept": department,
            "position_report_to": "",
            "position_subordinate": "",
            "employment_type": "全职",
            "annual_salary_min": "",
            "annual_salary_max": "",
            "status": "在职" if end_raw in current_markers else "离职",
            "position_start": _format_month_date(date_info["start_year"], date_info["start_month"]),
            "position_resigned": "" if end_raw in current_markers else _format_month_date(end_date_match.group(1), end_date_match.group(2)) if end_date_match else "",
            "resigned_reason": "",
            "position_responsibilities": "\n".join(responsibilities),
            "position_achievements": "",
        })

    # 英文 Word/HTML 导出通常是“日期 → 公司 → Description/Industry → 职位”
    # 的纵向结构，和中文智联表格不同，单独按标签边界提取。日期还可能在
    # 同一份经历中重复一次（summary + detail），以及出现在职责正文内部；
    # 只有后面确实出现 Description/Job Description 的日期才视为经历起点。
    # EN: English Word/HTML exports usually have a vertical structure "dates → company → Description/Industry → position",
    #     unlike the Chinese Zhaopin tables, so they are extracted separately by label boundaries. Dates may also repeat once within
    #     the same experience (summary + detail) and appear inside the duties text;
    #     only dates that are actually followed by Description/Job Description are treated as experience start points.
    # JA: 英語の Word/HTML のエクスポートは通常「期間 → 会社 → Description/Industry → 職位」の縦型の構造で、
    #     中国語の Zhaopin の表とは異なるため、ラベルの境界で個別に抽出する。日付は同じ経歴の中で
    #     1 回繰り返される（summary + detail）こともあり、職務の本文の中に現れることもある。
    #     後ろに実際に Description/Job Description が続く日付だけを経歴の開始点とみなす。
    english_lines = _section_lines(
        text,
        ("Work Experience", "Work History", "Professional Experience"),
        ("Educational Experience", "Education", "Academic Background", "Languages", "Language", "Self-description"),
    )
    english_date_re = re.compile(
        r"\(?\s*((?:19|20)\d{2})[./-](\d{1,3})\s*[-—–~～至到]+\s*(?:(\d{4})[./-](\d{1,3})|(Now|Present|Current|至今|现在|目前|今まで|現職|現在))\s*\)?",
        re.I,
    )
    english_date_lines: list[tuple[int, re.Match[str]]] = []
    for index, line in enumerate(english_lines):
        # 有些导出把公司名直接接在日期后（“2012.05 - 2014.03 COMPANY”），
        # 这里用 match 识别日期前缀，后续再把同一行余下内容作为公司候选。
        # EN: Some exports put the company name directly after the dates ("2012.05 - 2014.03 COMPANY");
        #     here match recognises the date prefix, and the rest of the same line is later taken as the company candidate.
        # JA: エクスポートによっては会社名が日付の直後に続く（「2012.05 - 2014.03 COMPANY」）。
        #     ここでは match で日付の接頭部分を識別し、後で同じ行の残りを会社の候補とする。
        match = english_date_re.match(line.strip())
        if match:
            english_date_lines.append((index, match))

    def _english_is_record_start(index: int) -> bool:
        next_date = next((candidate for candidate, _ in english_date_lines if candidate > index), len(english_lines))
        window = english_lines[index + 1:next_date]
        return any(line.casefold() in {"description:", "description", "job description:", "job description"} for line in window)

    english_starts = [(index, match) for index, match in english_date_lines if _english_is_record_start(index)]
    label_stops = {
        "description:", "description", "job description:", "job description",
        "type of", "type of company:", "type of company", "size of", "size of company:",
        "size of company", "industry:", "industry", "company locations:", "company location:",
        "company locations", "subordinate:", "subordinate", "responsibilities & achievement:",
        "responsibilities & achievement", "responsibilities and achievement:",
        "responsibilities and achievement", "leaving reason:", "leaving reason",
    }
    def _next_value(window: list[str], start: int) -> str:
        for candidate in window[start + 1:]:
            value = candidate.strip()
            if value and value.casefold() not in label_stops and not value.endswith(":"):
                return value
        return ""

    for position, (line_index, match) in enumerate(english_starts):
        end_index = english_starts[position + 1][0] if position + 1 < len(english_starts) else len(english_lines)
        line_text = english_lines[line_index].strip()
        inline_rest = line_text[match.end():].strip(" ：:")
        window = ([inline_rest] if inline_rest else []) + english_lines[line_index + 1:end_index]
        description_index = next((i for i, line in enumerate(window) if line.casefold() in {"description:", "description", "job description:", "job description"}), None)
        company = ""
        employees = ""
        industry = ""
        position_name = ""
        department = ""
        salary = ""

        # 标签化模板（1752 等）
        # EN: Labelled templates (1752 etc.)
        # JA: ラベル付きのテンプレート（1752 など）
        for i, line in enumerate(window):
            lower = line.casefold()
            if lower in {"company:", "company"}:
                company = _next_value(window, i)
            elif lower in {"position:", "position"}:
                position_name = _next_value(window, i)
            elif lower in {"department:", "department"}:
                department = _next_value(window, i)
            elif lower in {"size of", "size of company:", "size of company"}:
                employees = _next_value(window, i)
            elif lower.startswith("size of company:"):
                employees = line.split(":", 1)[1].strip()
            elif lower in {"industry:", "industry"}:
                industry = _next_value(window, i)
            elif lower.startswith("salary:"):
                salary = line.split(":", 1)[1].strip()

        header_end = description_index if description_index is not None else len(window)
        header = window[:header_end]
        meaningful_header = [
            line.strip() for line in header
            if line.strip()
            and line.strip() not in {"|", "｜"}
            and not re.fullmatch(r"\[.*\]", line.strip())
            and not re.search(r"(?:19|20)\d{2}[./-]\d{1,3}", line)
            and line.casefold() not in label_stops
        ]
        company_markers = ("corporation", "company", "co.", "ltd", "inc.", "有限", "株式会社", "会社", "集团", "公司")
        if not company:
            company_candidates = [
                line for line in meaningful_header
                if any(marker in line.casefold() for marker in company_markers)
            ]
            company = max(company_candidates, key=len).strip() if company_candidates else (meaningful_header[-1].strip() if meaningful_header else "")
        # 没有显式 Position 标签的英文模板：公司名前第一行通常是职位，
        # 公司名前紧邻 | 的文字通常是部门。
        # EN: English templates without an explicit Position label: the first line before the company name is usually the position,
        #     and the text right before the company name next to | is usually the department.
        # JA: 明示的な Position ラベルのない英語のテンプレート：会社名の前の最初の行が通常は職位で、
        #     会社名の直前の | に隣接するテキストが通常は部署である。
        company_pos = next((i for i, line in enumerate(meaningful_header) if line.strip() == company.strip()), -1)
        if not position_name:
            before_company = meaningful_header[:company_pos] if company_pos >= 0 else meaningful_header[:2]
            if before_company:
                position_name = before_company[0].strip()
        if not department and company_pos > 0:
            between = meaningful_header[1:company_pos]
            if between:
                department = " ".join(between).strip()
        if not industry:
            industry_candidates = [line for line in meaningful_header if "/" in line and line.strip() != position_name]
            if industry_candidates:
                industry = industry_candidates[-1].strip()
        if not position_name:
            industry_index = next(
                (i for i, line in enumerate(window) if line.casefold() in {"industry:", "industry"}),
                None,
            )
            if industry_index is not None:
                # industry 标签后第一行是行业值，下一行才是职位名。
                # EN: The first line after the industry label is the industry value; the line after that is the position name.
                # JA: industry ラベルの後の 1 行目は業界の値で、その次の行が職位名である。
                for candidate in window[industry_index + 2:]:
                    candidate = candidate.strip()
                    if not candidate or candidate in {"|", "｜"}:
                        continue
                    if candidate.casefold() in label_stops or english_date_re.fullmatch(candidate):
                        break
                    position_name = candidate
                    break
        if not employees:
            size_match = next((re.search(r"(?:\d+\s*[-–]\s*\d+|<\s*\d+|more than\s+\d+)\s*(?:people|persons)?", line, re.I) for line in meaningful_header), None)
            employees = size_match.group(0).strip() if size_match else ""

        description = ""
        responsibility_index = next((i for i, line in enumerate(window) if line.casefold() in {"responsibilities & achievement:", "responsibilities & achievement", "responsibilities and achievement:", "responsibilities and achievement"}), None)
        content_index = responsibility_index if responsibility_index is not None else description_index
        if content_index is not None:
            desc_lines: list[str] = []
            for line in window[content_index + 1:]:
                lower = line.casefold()
                if responsibility_index is None and lower in {"type of", "type of company:", "type of company", "size of", "size of company:", "size of company", "industry:", "industry", "company locations:", "company location:", "company locations", "subordinate:", "subordinate"}:
                    break
                if lower in {"leaving reason:", "leaving reason"}:
                    break
                desc_lines.append(line)
            description = "\n".join(desc_lines).strip()
        start_year, start_month = match.group(1), match.group(2)
        end_year, end_month, end_marker = match.group(3), match.group(4), match.group(5)
        current = bool(end_marker) or not end_year
        if company and position_name:
            works.append({
                "company_name": company,
                "company_employees": employees,
                "company_industry": industry,
                "position": position_name,
                "position_type": "",
                "position_salary": salary,
                "position_dept": department,
                "position_report_to": "",
                "position_subordinate": "",
                "employment_type": "全职",
                "annual_salary_min": "",
                "annual_salary_max": "",
                "status": "在职" if current else "离职",
                "position_start": _format_month_date(start_year, start_month),
                "position_resigned": "" if current else _format_month_date(end_year, end_month),
                "resigned_reason": "",
                "position_responsibilities": description,
                "position_achievements": "",
            })

    # 日文导出（例如“仕事経験 / 会社名 / 仕事内容”）不走中文智联字段名，
    # 但仍遵循同一套 18 字段结构。这里按“日期 + 公司名”识别雇主段，
    # 忽略正文中的“职务：”子段，避免把一个雇主拆成大量伪公司记录。
    # EN: Japanese exports (e.g. "仕事経験 / 会社名 / 仕事内容") do not use the Chinese Zhaopin field names,
    #     but still follow the same 18-field structure. Here employer sections are recognised by "date + company name",
    #     ignoring "职务：" (post:) sub-sections in the body, so one employer is not split into lots of pseudo company records.
    # JA: 日本語のエクスポート（例：「仕事経験 / 会社名 / 仕事内容」）は中国語の Zhaopin のフィールド名を使わないが、
    #     同じ 18 フィールドの構造に従う。ここでは「日付 + 会社名」で勤務先の段落を識別し、
    #     本文中の「职务：」（職務：）の小段落は無視して、1 つの勤務先が大量の偽の会社レコードに分かれないようにする。
    japanese_lines = _section_lines(
        text,
        ("仕事経験", "職務経歴", "職歴", "勤務経験"),
        ("教育履歴", "教育経歴", "学歴", "資格", "スキル", "自己評価", "希望職種", "言語能力"),
    )
    japanese_lines = _join_web_date_continuations(japanese_lines)
    japanese_date_re = re.compile(
        r"\(?\s*((?:19|20)\d{2})[./-](\d{1,3})\s*[-—–~～至到]+\s*(?:(\d{4})[./-](\d{1,3})|(今まで|現在|現職|Now|Present|Current))\s*(.*)\)?",
        re.I,
    )
    japanese_starts: list[tuple[int, re.Match[str]]] = []
    for index, line in enumerate(japanese_lines):
        match = japanese_date_re.fullmatch(line.strip())
        if not match:
            continue
        lookahead = japanese_lines[index + 1:index + 9]
        has_company_label = any("会社名" in candidate or "企業名" in candidate for candidate in lookahead)
        has_company_value = any(
            any(token in candidate for token in ("会社", "株式会社", "有限会社", "事務所", "法人"))
            for candidate in lookahead
        )
        # 正文中的子职位日期通常紧接“职务：”，没有公司名/仕事内容标签。
        # EN: Sub-position dates in the body are usually followed directly by "职务：" (post:), without company name / 仕事内容 labels.
        # JA: 本文中の下位の職位の日付には通常すぐ後に「职务：」（職務：）が続き、会社名や仕事内容のラベルはない。
        if has_company_label or (has_company_value and any("仕事内容" in candidate for candidate in lookahead)):
            japanese_starts.append((index, match))
    for position, (line_index, match) in enumerate(japanese_starts):
        end_index = japanese_starts[position + 1][0] if position + 1 < len(japanese_starts) else len(japanese_lines)
        window = japanese_lines[line_index + 1:end_index]
        rest = (match.group(6) or "").strip()
        company_index = next((i for i, line in enumerate(window) if "会社名" in line or "企業名" in line), None)
        company = ""
        if company_index is not None:
            for candidate in window[company_index + 1:]:
                if candidate not in {"：", ":", "|", "｜"} and candidate.strip():
                    company = candidate.strip(" ：:")
                    break
        if not company:
            company = next(
                (candidate.strip() for candidate in window if any(token in candidate for token in ("会社", "株式会社", "有限会社", "事務所", "法人"))),
                "",
            )
        company = re.sub(r"\s*規模\s*[：:]?.*$", "", company).strip(" ：:")
        department = ""
        if company_index is not None:
            preceding = [candidate.strip() for candidate in window[:company_index] if candidate.strip() and candidate.strip() not in {"：", ":", "|", "｜"}]
            if preceding:
                department = preceding[-1]
        job = rest
        if job.startswith(("職務：", "職務:")):
            job = job.split(":", 1)[-1].strip()
        # 日文履历会在一个公司段内再列出“职务：会计助手/監査助手”；
        # 该标签比日期行后的摘要更接近真实职位，优先使用它。
        # EN: Japanese histories list "职务：会计助手/監査助手" (post: accounting assistant / audit assistant) within one company section;
        #     this label is closer to the real position than the summary after the date line, so use it first.
        # JA: 日本の経歴では 1 つの会社の段落の中に「职务：会计助手／監査助手」（職務：会計補助・監査補助）を列挙することがある。
        #     このラベルは日付行の後の概要より本当の職位に近いため、優先して使う。
        explicit_job = ""
        for candidate in window:
            match_job = re.search(r"職務\s*[：:]\s*(.+)$", candidate.strip())
            if match_job and match_job.group(1).strip():
                explicit_job = match_job.group(1).strip()
                break
        if explicit_job:
            job = explicit_job
        if not job and department:
            job = department
        industry = ""
        for candidate in window[(company_index + 1 if company_index is not None else 0):]:
            if candidate in {"：", ":", "|", "｜"}:
                continue
            if "仕事内容" in candidate or "仕事の内容" in candidate:
                break
            if candidate not in {company, "規模：", "規模:", "企業領域：", "企業領域:"} and "規模" not in candidate:
                industry = re.sub(r"\s*規模\s*[：:]?.*$", "", candidate.strip(" ：:"))
                if industry:
                    break
        content_index = next((i for i, candidate in enumerate(window) if "仕事内容" in candidate or "仕事の内容" in candidate), None)
        responsibilities = ""
        if content_index is not None:
            responsibilities = "\n".join(window[content_index + 1:]).strip()
        end_raw = match.group(5) or f"{match.group(3)}.{match.group(4)}"
        end_match = re.match(r"((?:19|20)\d{2})[./-](\d{1,3})$", end_raw)
        japanese_work = {
            "company_name": company,
            "company_employees": "",
            "company_industry": industry,
            "position": job,
            "position_type": "",
            "position_salary": "",
            "position_dept": department,
            "position_report_to": "",
            "position_subordinate": "",
            "employment_type": "全职",
            "annual_salary_min": "",
            "annual_salary_max": "",
            "status": "在职" if not end_match else "离职",
            "position_start": _format_month_date(match.group(1), match.group(2)),
            "position_resigned": "" if not end_match else _format_month_date(end_match.group(1), end_match.group(2)),
            "resigned_reason": "",
            "position_responsibilities": responsibilities,
            "position_achievements": "",
        }
        if company:
            works.append(japanese_work)
    return works


def _parse_web_education_from_plain(text: str) -> list[dict[str, Any]]:
    """补齐智联教育日期行带冒号或学校/专业/学历用竖线分隔的格式。

    EN: Complete Zhaopin education formats where the date line has a colon or school/major/degree are separated by vertical bars.

    JA: Zhaopin の学歴で、日付行にコロンが付いている形式や学校・専攻・学歴が縦線で区切られた形式を補う。
    """
    lines = _section_lines(
        text,
        ("教育经历", "教育背景", "Educational Experience", "Academic Background", "Education", "教育履历", "教育履歴", "教育経歴", "学歴"),
        ("语言能力", "技能", "自我评价", "培训经历", "专业技能", "证书", "项目经历", "工作经历", "工作经验", "在校情况", "在校实践经验", "在校实践", "实践经历", "校园经历", "校内职务", "Language", "Project", "Work Experience", "Work History", "資格", "スキル", "自己評価", "希望職種"),
    )
    lines = _join_web_date_continuations(lines)
    # 日文模板有时先出现“学歴”摘要，完整的日期学历表在文末“教育履歴”
    # 才出现；另有模板把学校名拆成单字多行。优先使用含日期的完整区块，
    # 并把学校/专业碎片合成为一条可供统一解析器消费的日期行。
    # EN: Japanese templates sometimes show a "学歴" (education) summary first, with the complete dated education table only appearing in "教育履歴"
    #     at the end; other templates split the school name into single characters on many lines. Prefer the complete block with dates,
    #     and combine school/major fragments into one date line the unified parser can consume.
    # JA: 日本語のテンプレートでは先に「学歴」の概要があり、日付付きの完全な学歴の表は末尾の「教育履歴」に
    #     しか出てこないことがある。学校名を 1 文字ずつ複数行に分けるテンプレートもある。日付のある完全なブロックを優先し、
    #     学校・専攻の断片を統一パーサーが処理できる 1 つの日付行に組み立てる。
    if not any(_parse_web_date_range(line) for line in lines):
        japanese_education_lines = _section_lines(
            text,
            ("教育履歴", "教育経歴"),
            ("資格", "スキル", "自己評価", "希望職種", "言語能力", "Language", "Work Experience", "Work History"),
        )
        japanese_education_lines = _join_web_date_continuations(japanese_education_lines)
        if any(_parse_web_date_range(line) for line in japanese_education_lines):
            rebuilt_lines: list[str] = []
            index = 0

            def _collapse_japanese_fragments(values: list[str]) -> str:
                value = "".join(str(item or "").strip() for item in values if str(item or "").strip() not in {"|", "｜"})
                # HTML 表格偶尔把“大学”重复输出两次，去掉结尾重复的学校后缀。
                # EN: HTML tables occasionally output "大学" (university) twice; remove a duplicated school suffix at the end.
                # JA: HTML の表はまれに「大学」を 2 回出力するため、末尾の重複した学校の接尾辞を除く。
                value = re.sub(r"(大学|学院|学校|中学|小学)\1+$", r"\1", value)
                return value.strip()

            while index < len(japanese_education_lines):
                date_info = _parse_web_date_range(japanese_education_lines[index])
                if not date_info:
                    index += 1
                    continue
                school_parts = [date_info["rest"]]
                major_parts: list[str] = []
                cursor = index + 1
                separator_seen = False
                skip_until_separator = False
                while cursor < len(japanese_education_lines):
                    candidate = japanese_education_lines[cursor].strip()
                    if _parse_web_date_range(candidate):
                        break
                    if candidate in {"|", "｜"}:
                        separator_seen = True
                        cursor += 1
                        continue
                    if not separator_seen:
                        joined_school = _collapse_japanese_fragments(school_parts)
                        # 已经形成完整学校名后，后续长句通常是留学/学校说明，
                        # 不应再拼进 school_name；继续扫描到分隔符取专业。
                        # EN: Once a complete school name has formed, the following long sentences are usually study-abroad/school notes
                        #     and should not be spliced into school_name; keep scanning to the separator to get the major.
                        # JA: 完全な学校名ができた後に続く長い文は、通常は留学や学校の説明であり、
                        #     school_name に連結すべきではない。区切りまでスキャンを続けて専攻を取る。
                        if joined_school and any(suffix in joined_school for suffix in ("大学", "学院", "学校", "中学", "小学")) and len(candidate) > 2:
                            skip_until_separator = True
                            cursor += 1
                            continue
                        if not skip_until_separator:
                            school_parts.append(candidate)
                    else:
                        if major_parts and len(candidate) > 2:
                            break
                        if not candidate.endswith(":") and candidate not in {"Detail", "Description"}:
                            major_parts.append(candidate)
                    cursor += 1
                school = _collapse_japanese_fragments(school_parts)
                major = _collapse_japanese_fragments(major_parts)
                synthetic = f"{date_info['start_year']}.{date_info['start_month']} - {date_info['end']} {school}"
                if major:
                    synthetic += f" | {major}"
                rebuilt_lines.append(synthetic)
                index = cursor
            if rebuilt_lines:
                lines = rebuilt_lines
    result: list[dict[str, Any]] = []
    for line_index, line in enumerate(lines):
        date_info = _parse_web_date_range(line)
        if not date_info:
            continue
        parts = [part.strip() for part in re.split(r"\s*[|｜]\s*|\s{2,}", date_info["rest"]) if part.strip()]
        next_date_index = next(
            (candidate_index for candidate_index in range(line_index + 1, len(lines))
             if _parse_web_date_range(lines[candidate_index])),
            len(lines),
        )
        # 日期行只带学校名时，专业和学历会被导出到后续行；即使 parts 已有
        # 一个学校名，也必须继续读取这一段，否则会把下一个日期误当成专业。
        # EN: When the date line carries only the school name, the major and degree are exported on the following lines; even if parts already has
        #     a school name, this section must be read further, otherwise the next date would be mistaken for the major.
        # JA: 日付行に学校名しかない場合、専攻と学歴は後続の行に出力される。parts にすでに
        #     学校名があってもこの段落は読み続ける必要がある。さもないと次の日付を専攻と誤認してしまう。
        if len(parts) <= 1:
            for candidate in lines[line_index + 1:next_date_index]:
                candidate = candidate.strip()
                if (
                    not candidate
                    or candidate in {"|", "｜", "（", ")", "）", "(", "[", "]"}
                    or candidate.casefold() in {"school:", "school", "major:", "major", "degree:", "degree"}
                    or re.fullmatch(r"\[.*\]", candidate)
                ):
                    continue
                # 段落中的说明文字不属于教育主字段；碰到明显的下一节标题即停止。
                # EN: Explanatory text in a paragraph is not a main education field; stop at an obvious next section heading.
                # JA: 段落内の説明文は学歴の主要フィールドに属さない。明らかな次の章見出しに達したら止める。
                if candidate in {"在校情况", "在校学习情况", "校内职务", "实践经历", "在校实践经验"}:
                    break
                parts.append(candidate)
                if len(parts) >= 4:
                    break
        if not parts or all(part in {"(", ")", "（", "）"} for part in parts):
            parts = []
            for candidate in reversed(lines[max(0, line_index - 3):line_index]):
                candidate = candidate.strip()
                if candidate and candidate not in {"(", ")", "（", "）"}:
                    parts.append(candidate)
                    break
            parts.reverse()
        degree = ""
        education_type = ""
        english_degree_words = {
            "bachelor", "bachelor's degree", "master", "master's degree",
            "associate", "associate degree", "doctor", "phd", "ph.d.",
        }
        for part in list(parts):
            if (
                any(word in part for word in ("博士后", "博士", "硕士", "本科", "大专", "专科", "高中", "中专", "初中", "小学"))
                and not any(suffix in part for suffix in ("大学", "学院", "学校", "中学", "小学", "专科学校"))
            ) or part.casefold() in english_degree_words:
                degree = part
                parts.remove(part)
                break
        if not parts:
            continue
        school_index = next(
            (part_index for part_index, part in enumerate(parts)
             if any(suffix in part for suffix in ("大学", "学院", "学校", "分校", "高中", "中学", "小学"))),
            0,
        )
        school = parts[school_index]
        remaining = [part for part_index, part in enumerate(parts) if part_index != school_index]
        for part in list(remaining):
            if part.casefold() in {"overseas", "full-time", "part-time", "yes", "no"}:
                if part.casefold() == "overseas":
                    education_type = part
                remaining.remove(part)
        major = remaining[0] if remaining else ""
        # 纠正“实践描述/工作内容”等导出壳字段，避免它们进入 school_name。
        # EN: Correct export shell fields like "实践描述/工作内容" (practice description / job content) so they do not get into school_name.
        # JA: 「实践描述／工作内容」（実践の説明・業務内容）などのエクスポートの殻のフィールドを補正し、school_name に入らないようにする。
        if school in {"实践描述", "工作内容", "教育经历", "教育背景", "学校", "专业", "学历"}:
            continue
        result.append({
            "school_name": school,
            "school_major_name": major,
            "school_degree_type": degree,
            "school_degree_rank": "",
            "school_education_type": education_type,
            "school_start_ym": _format_month_date(date_info["start_year"], date_info["start_month"]),
            "school_end_ym": date_info["end"] if date_info["end"] in {"至今", "现在", "目前", "今まで", "現職", "現在", "Now", "Present", "Current"} else _format_month_date(*re.match(r"((?:19|20)\d{2})[./-](\d{1,3})$", date_info["end"]).groups()),
        })

    # 英文格式：学校名在日期行之前，专业/学历在日期行之后的标签中。
    # EN: English format: the school name comes before the date line, and the major/degree are in labels after the date line.
    # JA: 英語の形式：学校名は日付行の前にあり、専攻・学歴は日付行の後のラベルにある。
    english_lines = _section_lines(
        text,
        ("Educational Experience", "Academic Background", "Education"),
        ("Languages", "Language", "Self-description", "Work Experience", "Work History"),
    )
    english_date_re = re.compile(r"\(?\s*((?:19|20)\d{2})[./-](\d{1,2})\s*[-—–~～至到]+\s*((?:(?:19|20)\d{2})[./-](\d{1,2})|Now|Present|Current)\s*\)?", re.I)
    for index, line in enumerate(english_lines):
        match = english_date_re.fullmatch(line.strip())
        if not match:
            continue
        preceding: list[str] = []
        cursor = index - 1
        skip_values = {"yes", "no", "true", "false", "master", "bachelor", "bachelor's degree", "master's degree"}
        while cursor >= 0:
            candidate = english_lines[cursor].strip()
            if candidate.casefold() in {"educational experience", "academic background", "education"}:
                break
            if candidate and not candidate.endswith(":") and candidate.casefold() not in skip_values:
                preceding.insert(0, candidate)
                # 完整学校名通常在一行；只有“University / of XXX”这种断行
                # 才继续向前拼接一行。
                # EN: A complete school name is usually on one line; only line breaks like "University / of XXX"
                #     continue joining one line back.
                # JA: 完全な学校名は通常 1 行にある。「University / of XXX」のような改行の場合だけ、
                #     1 行前とさらに連結する。
                if "university" in candidate.casefold() or "college" in candidate.casefold() or "school" in candidate.casefold():
                    break
                if len(preceding) >= 2:
                    break
            cursor -= 1
        school = " ".join(preceding).strip()
        major = ""
        degree = ""
        window_values: list[str] = []
        for cursor in range(index + 1, min(len(english_lines), index + 16)):
            label = english_lines[cursor].casefold()
            if english_date_re.fullmatch(english_lines[cursor].strip()):
                break
            if label in {"major:", "major"} and cursor + 1 < len(english_lines):
                major = english_lines[cursor + 1].strip()
            elif label in {"degree:", "degree"} and cursor + 1 < len(english_lines):
                degree = english_lines[cursor + 1].strip()
            elif english_lines[cursor].strip() not in {"|", "｜"} and not label.endswith(":"):
                window_values.append(english_lines[cursor].strip())
        # 51job 英文导出有一类无标签模板：日期后依次是 Bachelor/Associate、
        # 分隔符、专业名；Overseas 是教育经历说明，不是专业字段。
        # EN: One kind of 51job English export has an unlabelled template: after the date come Bachelor/Associate,
        #     a separator, then the major name; Overseas is an education note, not the major field.
        # JA: 51job の英語のエクスポートにはラベルのないテンプレートがある：日付の後に Bachelor/Associate、
        #     区切り、専攻名が順に続く。Overseas は学歴の説明であり、専攻のフィールドではない。
        if window_values:
            degree_words = {
                "bachelor", "bachelor's degree", "master", "master's degree",
                "associate", "associate degree", "doctor", "phd", "ph.d.",
            }
            degree_index = next(
                (i for i, value in enumerate(window_values) if value.casefold() in degree_words),
                None,
            )
            if not degree and degree_index is not None:
                degree = window_values[degree_index]
            if not major:
                major_candidates = [
                    value for i, value in enumerate(window_values)
                    if value.casefold() not in degree_words
                    and value.casefold() not in {"overseas", "full-time", "part-time", "yes", "no"}
                    and (degree_index is None or i > degree_index)
                ]
                if not major_candidates:
                    major_candidates = [
                        value for value in window_values
                        if value.casefold() not in degree_words
                        and value.casefold() not in {"overseas", "full-time", "part-time", "yes", "no"}
                    ]
                if major_candidates:
                    major = major_candidates[0]
        if school:
            end_raw = match.group(3)
            result.append({
                "school_name": school,
                "school_major_name": major,
                "school_degree_type": degree,
                "school_degree_rank": "",
                "school_education_type": "",
                "school_start_ym": _format_month_date(match.group(1), match.group(2)),
                "school_end_ym": end_raw if end_raw.casefold() in {"now", "present", "current"} else _format_month_date(*re.match(r"((?:19|20)\d{2})[./-](\d{1,2})$", end_raw).groups()),
            })
    return result


def _atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    finally:
        Path(temp_name).unlink(missing_ok=True)


def _load_web_map(map_path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if not map_path.exists():
        return {}, []
    payload = json.loads(map_path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return {"records": payload}, [row for row in payload if isinstance(row, dict)]
    records = payload.get("records", []) if isinstance(payload, dict) else []
    return payload if isinstance(payload, dict) else {}, [row for row in records if isinstance(row, dict)]


def _map_record_for_path(records: list[dict[str, Any]], html_path: Path) -> dict[str, Any] | None:
    resolved = str(html_path.resolve())
    for row in records:
        if str(row.get("stage_path") or row.get("html_path") or "") == resolved:
            return row
    return None


_MULTILINGUAL_RUNTIME: tuple[Any, Any, Any] | None = None


def _resume_content_language(resume: dict[str, Any]) -> str:
    values: list[str] = []

    def collect(value: Any) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if key not in {"resume_language", "resume_languge"}:
                    collect(child)
        elif isinstance(value, list):
            for child in value:
                collect(child)
        elif isinstance(value, str):
            values.append(value)

    collect(resume)
    text = "\n".join(values)
    kana = len(re.findall(r"[\u3040-\u30ff]", text))
    han = len(re.findall(r"[\u3400-\u9fff]", text))
    latin = len(re.findall(r"[A-Za-z]", text))
    if kana >= 10 and kana >= max(10, han // 6):
        return "jp"
    if latin >= 80 and latin >= max(80, han * 2):
        return "en"
    return "zh"


def _translated_chinese_primary(source_resume: dict[str, Any]) -> dict[str, Any]:
    """Build a real field-level Chinese primary; never relabel foreign text."""
    global _MULTILINGUAL_RUNTIME
    if _MULTILINGUAL_RUNTIME is None:
        module = _load_v2_dependency("web_multilingual_repair.v2.py", "web_multilingual_repair_dot_v2")
        support = module.load_translation_support()
        translator = support.OfflineTranslator(enabled=True)
        _MULTILINGUAL_RUNTIME = (module, support, translator)
    module, support, translator = _MULTILINGUAL_RUNTIME
    translated = module.transform_primary(copy.deepcopy(source_resume), support, translator)
    translated["resume_language"] = "zh"
    translated.pop("resume_languge", None)
    return translated


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
    source_path: Path | None = None,
    metadata: dict[str, Any] | None = None,
) -> tuple[bool, str, str | None]:
    """处理单个 HTML-like 文件；metadata 来自全量 Web conversion map。

    EN: Process a single HTML-like file; the metadata comes from the full Web conversion map.

    JA: HTML のようなファイルを 1 件処理する。metadata は Web の全件の変換マップから取る。
    """
    metadata = metadata or {}
    source_file = Path(source_path or metadata.get("source_path") or html_path).resolve()
    filename = str(metadata.get("filename") or source_file.name)
    source_suffix = str(metadata.get("extension") or source_file.suffix).lower()
    # 1) 跳过非 HTML 与 JSON 索引文件
    # EN: 1) Skip non-HTML and JSON index files
    # JA: 1) HTML 以外と JSON の索引ファイルをスキップする
    if source_suffix not in (".html", ".htm", ".mht", ".mhtml", ".eml"):
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

    rec_id = str(metadata.get("record_id") or html_record_id(source_file if source_file.exists() else html_path))
    fallback_date = str(metadata.get("source_landing_time") or "")
    if not fallback_date:
        fallback_date = date_from_mtime(source_file if source_file.exists() else html_path)
    updated_date, download_date, updated_src, download_src = parse_resume_dates(plain, fallback_date)
    platform = detect_platform(plain, filename)
    classifier = DocumentClassifier()
    try:
        classification = classifier.classify(plain, filename)
    except Exception as e:
        return False, f"分类失败: {e}", None
    classification_data = _classification_dict(classification)
    if not _is_resume_classification(classification):
        return True, f"跳过：非简历（{classification_data.get('document_type') or 'other_document'}）", None

    # 2) 解析器基础解析（复用 liepin 的调用方式：parser.parse(html_cleaned_text, filename, source_path)）
    # EN: 2) Basic parsing by the parser (reusing liepin's calling convention: parser.parse(html_cleaned_text, filename, source_path))
    # JA: 2) パーサーによる基本の解析（liepin の呼び出し方を再利用：parser.parse(html_cleaned_text, filename, source_path)）
    parser = CodexGeminiHtmlSchemaParser()
    fake_source_path = str(html_path.resolve())

    try:
        base_parsed = parser.parse(html_text, filename=filename, source_path=fake_source_path)
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
            "expected_list": [base_parsed.get("expected_info") or {}],
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

    # 主版本必须是实际中文内容，不能只把最丰富的外文简历改标为 zh。
    # 有丰富中文版本时直接置顶；纯外文来源则保留外文副本，并通过本地
    # 翻译器生成字段级中文主版本。
    # EN: The primary version must have actual Chinese content; the richest foreign-language résumé cannot simply be relabelled as zh.
    #     When there is a rich Chinese version, put it on top directly; for foreign-only sources keep the foreign copy and generate
    #     a field-level Chinese primary version via the local translator.
    # JA: 主版は実際の中国語の内容でなければならず、最も充実した外国語の履歴書に zh のラベルを付け替えるだけではいけない。
    #     充実した中国語版があればそのまま先頭に置き、外国語だけのソースは外国語のコピーを残したうえで、
    #     ローカルの翻訳器でフィールド単位の中国語主版を生成する。
    zh_idx_in_top3 = None
    best_score = _resume_score(resumes_raw[0]) if resumes_raw else 0
    for i, r in enumerate(resumes_raw[:3]):
        if isinstance(r, dict) and _resume_content_language(r) == "zh":
            s = _resume_score(r)
            # 只在 zh 版本分数 >= 最佳分数的 50% 以上（也很丰富）时，才调 zh 到 0
            # EN: Move zh into slot 0 only when the zh version's score is >= 50% of the best score (also rich)
            # JA: zh 版の点数が最高点の 50% 以上（十分に充実している）の場合だけ zh を 0 番目に移す
            if s >= max(3, int(best_score * 0.5)):
                zh_idx_in_top3 = i
                break
    if zh_idx_in_top3 is not None and zh_idx_in_top3 != 0:
        resumes_raw[0], resumes_raw[zh_idx_in_top3] = resumes_raw[zh_idx_in_top3], resumes_raw[0]
    elif zh_idx_in_top3 is None and resumes_raw:
        source_resume = copy.deepcopy(resumes_raw[0])
        source_resume["resume_language"] = _resume_content_language(source_resume)
        source_resume.pop("resume_languge", None)
        resumes_raw = [_translated_chinese_primary(source_resume), source_resume, *resumes_raw[1:]]

    resumes_normalized: list[dict[str, Any]] = []
    fallback_failures: list[str] = []
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
        if "expected_list" not in r:
            legacy_expected = r.pop("expected_info", {})
            if isinstance(legacy_expected, list):
                r["expected_list"] = legacy_expected
            else:
                r["expected_list"] = [legacy_expected if isinstance(legacy_expected, dict) else {}]
        if not isinstance(r["expected_list"], list):
            r["expected_list"] = [r["expected_list"]]

        # ============ 每个 resume 的后处理 ============
        # EN: ============ Post-processing of each resume ============
        # JA: ============ 各 resume の後処理 ============
        base_info = r["base_info"]
        header_name = _header_name_hint(plain) or _text_name_hint(plain) or _filename_name_hint(filename)
        name_noise = {
            "男", "女", "male", "female", "中文", "英文", "日文", "日语", "日本語",
            "英语", "English", "Japanese", "Chinese", "个人信息", "教育经历", "工作经历",
            "教育履历", "教育履歴", "学歴", "resume", "cv",
        }
        existing_name = (base_info.get("full_name") or "").strip()
        if header_name and (
            not existing_name
            or existing_name.startswith("待确认姓名_")
            or existing_name.casefold() in {value.casefold() for value in name_noise}
            or re.search(r"简$", existing_name)
            or _compact_text(existing_name) not in _compact_text(plain)
        ):
            base_info["full_name"] = header_name
        # 姓名兜底（三重防护）
        # EN: Name fallback (triple protection)
        # JA: 氏名の最終手段（3 重の保護）
        name = (base_info.get("full_name") or "").strip()
        if (
            not name
            or name.startswith("待确认姓名_")
            or name in ("待确认姓名", "未知", "简历", "无关联职位简历")
            or re.search(r"(?:工程师|经理|主管|专员|开发|运营|总监|销售|翻译)", name)
        ):
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
            # 1. expected_list：parser 没抽到值时，用智联的再提一次
            # EN: 1. expected_list: when the parser extracted no value, extract once more with Zhaopin's
            # JA: 1. expected_list：パーサーが値を取れなかった場合は、Zhaopin のものでもう一度抽出する
            cur_ei = r.get("expected_list") or []
            if isinstance(cur_ei, list):
                cur_ei = cur_ei[0] if cur_ei and isinstance(cur_ei[0], dict) else {}
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
                        r["expected_list"] = [zhilian_ei[0]]
                    elif isinstance(zhilian_ei, dict):
                        r["expected_list"] = [zhilian_ei]
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
                _company_has_date = bool(re.search(r"(?:19|20)\d{2}\s*[./-]\s*\d{1,3}", _cn))
                _company_has_parser_label = bool(re.search(
                    r"(?:Description|Work Experience|Responsibilities|Subordinate|Company Locations|公司名称|工作内容|会社名|仕事内容)\s*[:：]?",
                    _cn,
                    re.I,
                ))
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
                    and not any(k in _cn for k in ("公司性质", "企业性质", "公司规模", "公司行业", "规模：", "规模:"))
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
                _separator_only_cn = _cn in (":", "：", "|", "｜", "(", ")", "（", "）")
                _position_is_metadata = _web_is_work_metadata_value(_pos)
                if (
                    _bad_company_cn or _bad_position_placeholder or _empty_cn
                    or _separator_only_cn or _position_is_metadata
                    or _company_has_date or _company_has_parser_label
                    or len(_cn) > 180
                ):
                    _bad_work_indices.add(_i)
            _had_bad_work = bool(_bad_work_indices)
            if _bad_work_indices:
                cur_works = [w for _i, w in enumerate(cur_works) if _i not in _bad_work_indices]
                r["work_experiences"] = cur_works

            work_needs_fallback = _had_bad_work or (not cur_works) or any(
                not (w.get("company_name") or "").strip()
                or (w.get("company_name") or "").strip() in (":", "：", "|", "｜")
                or (w.get("position") or "").strip().startswith(("规模", "企业性质", "公司性质", "行业"))
                for w in cur_works if isinstance(w, dict)
            )
            if work_needs_fallback:
                zhilian_works = _parse_zhilian_work_experiences(soup, plain)
                def _bad_fallback_work(item: Any) -> bool:
                    if not isinstance(item, dict):
                        return True
                    company = (item.get("company_name") or "").strip()
                    position = (item.get("position") or "").strip()
                    return (
                        not company
                        or company in (":", "：", "|", "｜", "(", ")", "（", "）")
                        or any(k in company for k in ("公司性质", "企业性质", "公司规模", "公司行业"))
                        or bool(re.search(r"(?:19|20)\d{2}\s*[./-]\s*\d{1,3}", company))
                        or bool(re.search(r"(?:Description|Work Experience|Responsibilities|Company Locations|Subordinate|公司名称|工作内容|会社名|仕事内容)\s*[:：]?", company, re.I))
                        or len(company) > 180
                        or _web_is_work_metadata_value(position)
                    )
                if not zhilian_works or any(_bad_fallback_work(item) for item in zhilian_works):
                    text_works = _parse_web_work_from_plain(plain)
                    if text_works:
                        zhilian_works = text_works
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
                "培训机构", "所获证书", "培训地点", "培训描述",
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
                _date_like = bool(re.search(r"(?:19|20)\d{2}\s*[./-]\s*\d{1,3}\s*[-—–~～至到]", _mn))
                _degree_contains_date = bool(re.search(r"(?:19|20)\d{2}\s*[./-]\s*\d{1,3}", _dt))
                _sn_is_non_school_label = _sn in {"实践描述", "工作内容", "教育经历", "教育背景", "学校", "专业", "学历"}
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
                # 5) school_name 里出现“大学/学院”本身是正常现象，不能与
                # “全日制大学”等 education_type 重复计数后误删有效学历。
                # 6) major_name 里有学校关键词 → 错把学校塞到了 major
                # EN: 5) "大学/学院" (university/college) appearing in school_name is normal; it must not be double-counted with
                #     an education_type like "全日制大学" (full-time university) and lead to deleting a valid degree.
                #     6) major_name contains school keywords → a school was wrongly stuffed into major
                # JA: 5) school_name に「大学／学院」が現れるのは正常であり、「全日制大学」（全日制大学）などの
                #     education_type と重複して数えて有効な学歴を誤って削除してはならない。
                #     6) major_name に学校のキーワードがある → 学校が誤って major に入れられている
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
                _looks_like_practice_entry = (
                    not any(suf in _sn for suf in _SCHOOL_SUFFIXES)
                    and len(_mn) >= 8
                )
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
                    or _looks_like_practice_entry
                    or _date_like
                    or _degree_contains_date
                    or _sn_is_non_school_label
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
                or bool(re.search(r"(?:19|20)\d{2}\s*[./-]\s*\d{1,3}", (e.get("school_major_name") or "")))
                or bool(re.search(r"(?:19|20)\d{2}\s*[./-]\s*\d{1,3}", (e.get("school_degree_type") or "")))
                or (e.get("school_name") or "").strip() in {"实践描述", "工作内容", "教育经历", "教育背景", "学校", "专业", "学历"}
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
                text_edus = _parse_web_education_from_plain(plain)
                def _fallback_edu_is_bad(item: Any) -> bool:
                    if not isinstance(item, dict):
                        return True
                    school = (item.get("school_name") or "").strip()
                    major = (item.get("school_major_name") or "").strip()
                    degree = (item.get("school_degree_type") or "").strip()
                    return (
                        school in {"", "实践描述", "工作内容", "教育经历", "教育背景", "学校", "专业", "学历"}
                        or bool(re.search(r"(?:19|20)\d{2}\s*[./-]\s*\d{1,3}", major))
                        or bool(re.search(r"(?:19|20)\d{2}\s*[./-]\s*\d{1,3}", degree))
                        or any(label in school for label in ("培训机构", "培训地点", "培训描述"))
                    )
                # 本轮已经确认原解析存在字段错位时，优先使用按 HTML 教育段
                # 重新切分的结果；否则仅“合并”会把旧的日期/专业错位继续保留下来。
                # EN: When this round has already confirmed field misplacement in the original parse, prefer the result re-split by the HTML education section;
                #     otherwise mere "merging" would keep the old date/major misplacement.
                # JA: 今回すでに元の解析でフィールドのずれが確認されている場合は、HTML の学歴の段落で切り直した結果を優先する。
                #     さもないと単なる「統合」では古い日付・専攻のずれが残ってしまう。
                if text_edus:
                    zhilian_edus = text_edus
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
        except Exception as exc:
            # Preserve the primary parse, but surface the failed fallback in
            # quality.issues so affected records are auditable.
            fallback_failures.append(f"resume[{idx}] zhilian_fallback_failed: {type(exc).__name__}: {exc}")

        # ========== Web 文本字段最终对齐兜底 ========== 
        # 共享 parser 对少数 HTML/MHT 导出模板会把日期、学校、专业、学历或
        # 公司概况错位到相邻字段。这里在写出前再次以同一份 plain text 做
        # 结构化重解析；只有候选结果本身通过基本有效性检查，且能修复当前
        # 明显错位/缺失时才替换，避免用一个更差的空结果覆盖已有值。
        # EN: ========== Final alignment fallback for Web text fields ==========
        #     For a few HTML/MHT export templates the shared parser misplaces dates, school, major, degree or
        #     company overview into adjacent fields. Here, before writing out, structured re-parsing is done once more
        #     from the same plain text; a replacement is made only when the candidate itself passes basic validity checks and can fix
        #     an obvious current misplacement/omission, so an existing value is not overwritten by a worse empty result.
        # JA: ========== Web のテキストフィールドの最終的な整合のための最終手段 ==========
        #     共通パーサーは一部の HTML/MHT のエクスポートのテンプレートで、日付・学校・専攻・学歴・
        #     会社の概要を隣のフィールドにずらしてしまう。ここでは書き出しの前に、同じ plain text から
        #     もう一度構造化して解析し直す。候補の結果自体が基本的な妥当性チェックに合格し、
        #     現在の明らかなずれ・欠落を修正できる場合だけ置き換え、既存の値をより悪い空の結果で上書きしないようにする。
        try:
            def _web_bad_education(item: Any) -> bool:
                if not isinstance(item, dict):
                    return True
                school = str(item.get("school_name") or "").strip()
                major = str(item.get("school_major_name") or "").strip()
                degree = str(item.get("school_degree_type") or "").strip()
                if not school or re.search(r"<[^>]+>|(?:19|20)\d{2}[./-]\d{1,2}", school):
                    return True
                if school in {"教育经历", "教育背景", "学校", "专业", "学历", "教育履历", "教育履歴", "学歴"}:
                    return True
                if any(token in school for token in ("工作描述", "工作内容", "工作经历", "工作经验", "项目描述", "项目经验", "培训经历", "仕事メイン", "仕事内容")):
                    return True
                if re.search(r"<[^>]+>|(?:19|20)\d{2}[./-]\d{1,2}", major + " " + degree):
                    return True
                if major in {"教育经历", "教育背景", "学校", "专业", "学历", "Overseas", "海外"}:
                    return True
                return False

            def _web_good_education(item: Any) -> bool:
                if _web_bad_education(item):
                    return False
                school = str(item.get("school_name") or "").strip()
                major = str(item.get("school_major_name") or "").strip()
                degree = str(item.get("school_degree_type") or "").strip()
                return bool(
                    any(token in school.casefold() for token in ("university", "college", "school"))
                    or any(token in school for token in ("大学", "学院", "学校", "中学", "小学"))
                    or (len(school) <= 60 and bool(major) and bool(degree))
                )

            current_edus = r.get("education_list") or []
            web_edus = _parse_web_education_from_plain(plain)
            valid_web_edus = [item for item in web_edus if _web_good_education(item)]
            current_edu_bad = any(not _web_good_education(item) for item in current_edus)
            if valid_web_edus and (
                current_edu_bad
                or len(valid_web_edus) > len(current_edus)
                or (not current_edus and valid_web_edus)
            ):
                r["education_list"] = valid_web_edus

            def _web_bad_work(item: Any) -> bool:
                if not isinstance(item, dict):
                    return True
                company = str(item.get("company_name") or "").strip()
                position = str(item.get("position") or "").strip()
                responsibilities = str(item.get("position_responsibilities") or "").strip()
                if not company or len(company) > 180:
                    return True
                if re.search(r"<[^>]+>|(?:19|20)\d{2}[./-]\d{1,3}", company):
                    return True
                if any(token in company for token in ("公司性质", "企业性质", "公司规模", "公司行业", "規模", "規模：", "規模:")):
                    return True
                if re.search(r"(?:Description|Work Experience|Responsibilities|Company Locations|Subordinate|公司名称|工作内容|会社名|仕事内容)\s*[:：]?", company, re.I):
                    return True
                if not position or _web_is_work_metadata_value(position) or position.startswith(("専門", "学歴", "教育履歴", "教育経歴", "職務", "部下")):
                    return True
                if responsibilities.startswith(("公司描述", "公司性质", "企业性质", "公司规模", "公司行业", "工作地点", "下属人数")):
                    return True
                if "公司描述" in responsibilities[:120] and any(token in responsibilities[:240] for token in ("公司性质", "公司规模", "公司行业", "工作地点", "下属人数")):
                    return True
                return False

            def _web_work_score(items: list[Any]) -> int:
                score = 0
                for item in items:
                    if not isinstance(item, dict) or _web_bad_work(item):
                        continue
                    score += 1
                    if str(item.get("position") or "").strip():
                        score += 2
                    if str(item.get("position_responsibilities") or "").strip():
                        score += 1
                    if str(item.get("position_responsibilities") or "").lstrip().startswith(("公司描述", "公司性质", "企业性质")):
                        score -= 3
                return score

            current_works = r.get("work_experiences") or []
            web_works = _parse_web_work_from_plain(plain)
            valid_web_works = [item for item in web_works if not _web_bad_work(item)]

            def _web_strip_work_label(value: Any) -> str:
                return re.sub(
                    r"^\s*(?:工作描述|工作内容|职责业绩|工作职责和业绩|工作职责)\s*[：:]?\s*",
                    "",
                    str(value or ""),
                    flags=re.I,
                ).strip()

            def _web_work_needs_evidence_repair(item: Any) -> bool:
                if not isinstance(item, dict):
                    return True
                position = str(item.get("position") or "").strip()
                responsibilities = _web_strip_work_label(item.get("position_responsibilities"))
                trimmed = _web_trim_work_responsibilities(responsibilities)
                return bool(
                    not position
                    or _web_is_work_metadata_value(position)
                    or any(token in position for token in ("公司描述", "公司性质", "企业性质", "公司规模", "公司行业"))
                    or "。" in position
                    or len(position) > 40
                    or trimmed != responsibilities
                )

            def _web_work_items_match(left: Any, right: Any) -> bool:
                if not isinstance(left, dict) or not isinstance(right, dict):
                    return False
                left_company = _compact_text(left.get("company_name"))
                right_company = _compact_text(right.get("company_name"))
                left_position = _compact_text(left.get("position"))
                right_position = _compact_text(right.get("position"))
                company_match = bool(left_company and right_company and (left_company in right_company or right_company in left_company))
                position_match = bool(left_position and right_position and (left_position in right_position or right_position in left_position))
                return company_match or position_match

            # 对“公司/职位已经正确，但职责正文被旧 parser 截短或混入标签”
            # 的记录只做字段级修复，不替换整条工作经历，避免牵连已正确字段。
            # EN: For records where "company/position are already correct, but the duties text was truncated by the old parser or mixed with labels",
            #     only repair at the field level, without replacing the whole work experience, so fields that are already correct are not affected.
            # JA: 「会社・職位はすでに正しいが、職務の本文が旧パーサーに切り詰められたりラベルが混入したりしている」レコードは、
            #     フィールド単位でだけ修正し、職歴全体は置き換えない。すでに正しいフィールドを巻き込まないため。
            for current_index, current_item in enumerate(current_works):
                if not isinstance(current_item, dict):
                    continue
                candidates = [
                    item for item in valid_web_works
                    if _web_work_items_match(current_item, item)
                ]
                if not candidates and current_index < len(valid_web_works):
                    indexed = valid_web_works[current_index]
                    if _compact_text(current_item.get("company_name")) and _compact_text(indexed.get("company_name")):
                        candidates = [indexed]
                if not candidates:
                    continue
                candidate = candidates[0]
                candidate_resp = _web_strip_work_label(candidate.get("position_responsibilities"))
                current_resp = _web_strip_work_label(current_item.get("position_responsibilities"))
                trimmed_current_resp = _web_trim_work_responsibilities(current_resp)
                if trimmed_current_resp != current_resp:
                    current_item["position_responsibilities"] = trimmed_current_resp
                    current_resp = trimmed_current_resp
                if candidate_resp and _compact_text(candidate_resp) in _compact_text(plain):
                    if not current_resp or _compact_text(current_resp) not in _compact_text(plain):
                        current_item["position_responsibilities"] = _web_trim_work_responsibilities(candidate_resp)
                current_position = str(current_item.get("position") or "").strip()
                candidate_position = str(candidate.get("position") or "").strip()
                if (
                    candidate_position
                    and _compact_text(candidate_position) in _compact_text(plain)
                    and current_position
                    and _compact_text(current_position) not in _compact_text(plain)
                ):
                    current_item["position"] = candidate_position

            current_work_bad = any(_web_bad_work(item) for item in current_works)
            current_work_dirty = any(_web_work_needs_evidence_repair(item) for item in current_works)
            current_work_score = _web_work_score(current_works)
            web_work_score = _web_work_score(valid_web_works)
            if valid_web_works and (
                len(valid_web_works) > len(current_works)
                or (len(valid_web_works) == len(current_works) and current_work_dirty)
                or (current_work_bad and web_work_score > current_work_score)
                or (current_work_bad and len(valid_web_works) < len(current_works))
                or (not current_works and valid_web_works)
                or (
                    web_work_score > current_work_score
                    and len(valid_web_works) >= len(current_works)
                    and all(str(item.get("company_name") or "").strip() and str(item.get("position") or "").strip() for item in valid_web_works)
                )
            ):
                r["work_experiences"] = valid_web_works
        except Exception:
            # 文本最终兜底失败时保留上一阶段已得到的结构化结果。
            # EN: If the final text fallback fails, keep the structured result obtained in the previous stage.
            # JA: テキストの最終手段が失敗した場合は、前の段階で得た構造化の結果を残す。
            pass

        # expected_list 规范化（每个 resume 保留数组；顶层 expected_info 是对象快照）
        # EN: Normalise expected_list (each resume keeps an array; the top-level expected_info is an object snapshot)
        # JA: expected_list の正規化（各 resume は配列を保持し、トップレベルの expected_info はオブジェクトのスナップショット）
        ei_in = r.get("expected_list") or []
        if isinstance(ei_in, list):
            ei_in = ei_in[0] if ei_in and isinstance(ei_in[0], dict) else {}
        if isinstance(ei_in, list) and ei_in and isinstance(ei_in[0], dict):
            ei_in = ei_in[0]
        _exp_dict = _normalize_expected_info(ei_in, plain)
        r["expected_list"] = [_exp_dict]

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
                cname = re.sub(r"[\[【]\s*\d+\s*年?\s*\d*\s*个?月?\s*[\]】]", "", cname)
                cname = cname.replace("\r", " ").replace("\n", " ").strip(" 　\t-—–*·")
                cname = re.sub(r"^\s*\d+\s*[:：]\s*", "", cname)
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
            # 少数多语言导出会把“职位 | 部门 | 公司 | 行业”整体写入 position，
            # 同时把真正的职位错放进 company_name。按源文本中可确认的公司段
            # 将字段移回 CONTEXT 对应位置，避免只清理斜杠而留下列错位。
            # EN: A few multilingual exports write "position | department | company | industry" as a whole into position,
            #     while putting the real position into company_name by mistake. Move the fields back to their CONTEXT positions according to the company section
            #     that can be confirmed in the source text, rather than only cleaning slashes and leaving the columns misplaced.
            # JA: 一部の多言語のエクスポートは「職位 | 部署 | 会社 | 業界」をまとめて position に書き込み、
            #     同時に本当の職位を company_name に誤って置いている。原文で確認できる会社の段落に従って
            #     フィールドを CONTEXT の対応する位置に戻し、スラッシュを整理するだけで列のずれを残すことがないようにする。
            raw_position = str(w.get("position") or "").strip()
            if raw_position and ("/" in raw_position or "／" in raw_position) and cname:
                position_parts = [
                    part.strip() for part in re.split(r"\s*[/／]\s*", raw_position) if part.strip()
                ]
                company_part_index = next(
                    (
                        part_index for part_index, part in enumerate(position_parts)
                        if any(token in part for token in ("公司", "有限公司", "有限会社", "株式会社", "集团", "集団"))
                    ),
                    -1,
                )
                company_like_old_name = any(
                    token in cname for token in ("公司", "有限公司", "有限会社", "株式会社", "集团", "集団")
                )
                old_name_in_source = bool(_compact_text(cname) and _compact_text(cname) in _compact_text(plain))
                if company_part_index >= 0 and not company_like_old_name and old_name_in_source:
                    source_company = position_parts[company_part_index]
                    w["company_name"] = source_company
                    w["position"] = cname
                    if company_part_index > 0 and not w.get("position_dept"):
                        w["position_dept"] = position_parts[0]
                    industry_parts = position_parts[company_part_index + 1:]
                    industry_parts = [
                        part for part in industry_parts
                        if part not in {"民营公司", "外资企业", "合资企业", "国有企业", "上市公司"}
                    ]
                    if industry_parts and not w.get("company_industry"):
                        w["company_industry"] = "/".join(industry_parts)
            w["position"] = _web_clean_work_position(w.get("position"))
            # 补齐 position_achievements（validate_batch.py 强约束）
            # EN: Fill position_achievements (a hard requirement of validate_batch.py)
            # JA: position_achievements を補う（validate_batch.py の必須条件）
            w.setdefault("position_achievements", "")
            responsibilities = _web_trim_work_responsibilities(w.get("position_responsibilities"))
            w["position_responsibilities"] = responsibilities
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

        # 训练段必须和项目/工作段分开。若旧解析把“药物名称/项目描述”或
        # “公司性质/工作职责”放进 training，优先使用 HTML 培训段的独立解析；
        # 没有可确认的培训段时，仅删除已确认的伪条目。
        # EN: Training sections must be kept separate from project/work sections. If the old parse put "药物名称/项目描述" (drug name / project description) or
        #     "公司性质/工作职责" (company type / job duties) into training, prefer the separate parse of the HTML training section;
        #     when there is no confirmable training section, only delete the confirmed pseudo entries.
        # JA: 研修の段落はプロジェクト・職歴の段落と分けなければならない。旧解析が「药物名称／项目描述」（薬剤名・プロジェクトの説明）や
        #     「公司性质／工作职责」（会社の性質・職務）を training に入れていた場合は、HTML の研修の段落の独立した解析を優先する。
        #     確認できる研修の段落がない場合は、確認済みの偽の項目だけを削除する。
        def _web_bad_training(item: Any) -> bool:
            if not isinstance(item, dict):
                return True
            org = str(item.get("organization_name") or "").strip()
            name = str(item.get("training_name") or "").strip()
            desc = str(item.get("description") or "").strip()
            if not name and not org:
                return True
            if any(token in org or token in name or token in desc for token in (
                "药物名称", "适应症", "项目经历", "项目描述", "项目经验", "项目职务",
                "项目概况", "项目职责", "项目业绩", "所在公司", "公司性质", "公司规模",
                "公司行业", "工作职责和业绩", "奖项描述", "活动描述", "曾获",
                "校园经历", "在校学习情况", "在校实践经历", "技能/语言", "专业技能",
            )):
                return True
            if desc.startswith(("公司描述", "公司性质", "企业性质", "工作职责和业绩", "药物名称", "适应症")):
                return True
            if name in {"培训时间", "培训内容", "时间", "项目经验", "项目经历", "项目概况"}:
                return True
            return False

        current_trains = r.get("training_list") or []
        web_trains = _parse_web_training_from_plain(plain)
        web_trains = _normalize_training_list_cleanup(web_trains)
        valid_web_trains = [item for item in web_trains if not _web_bad_training(item)]
        valid_current_trains = [item for item in current_trains if not _web_bad_training(item)]
        def _web_training_composite_noise(item: Any) -> bool:
            if not isinstance(item, dict):
                return False
            name = str(item.get("training_name") or "").strip()
            org = str(item.get("organization_name") or "").strip()
            desc = str(item.get("description") or "").strip()
            if not desc:
                return False
            if any(label in desc for label in ("培训机构", "培训地点", "所获证书", "培训描述", "培训内容")):
                return True
            # 旧版通用解析常把“课程名\n机构\n地点/证书”整体写进 description；
            # 课程名位于 description 首行时，即使机构字段已经丢失，也属于同类串位。
            # EN: The old generic parse often wrote "course name\nprovider\nplace/certificate" as a whole into description;
            #     when the course name is on the first line of description, it is the same kind of column misplacement even if the provider field has been lost.
            # JA: 旧来の汎用解析は「コース名\n機関\n場所／資格」をまとめて description に書き込むことが多かった。
            #     コース名が description の 1 行目にある場合は、機関のフィールドが失われていても同じ種類の列のずれである。
            if name and re.match(rf"^\s*{re.escape(name)}(?:\s|\n|$)", desc) and len(desc) > len(name):
                return True
            return bool(name and name in desc and org and org in desc)
        specialized_is_cleaner = (
            bool(valid_web_trains)
            and any(_web_training_composite_noise(item) for item in current_trains)
            and not any(_web_training_composite_noise(item) for item in valid_web_trains)
        )
        training_marker_found = any(
            line.strip() in {"培训经历", "培训经验"}
            or line.strip().startswith(("培训经历：", "培训经历:", "培训经验：", "培训经验:"))
            for line in plain.splitlines()
            if line.strip()
        )
        # 没有独立培训板块时，工作职责中的“培训”字样不能生成 training_list。
        # 先清空候选，再走统一的 current_trains 清理分支，避免把工作 bullet
        # 当作真实培训经历保留下来。
        # EN: Without a separate training section, the word "培训" (training) in job duties must not generate training_list.
        #     Clear the candidates first, then go through the unified current_trains cleanup branch, so work bullets
        #     are not kept as real training experiences.
        # JA: 独立した研修の欄がない場合、職務内容中の「培训」（研修）という語から training_list を生成してはならない。
        #     まず候補を空にしてから統一した current_trains の整理の分岐を通し、職務の箇条書きを
        #     本当の研修歴として残さないようにする。
        if not training_marker_found:
            valid_web_trains = []
            valid_current_trains = []

        def _web_training_needs_alignment(item: Any) -> bool:
            """判断当前培训条目是否明显来自其他板块或发生列串位。

            EN: Decide whether the current training entry obviously comes from another section or has a column misplacement.

            JA: 現在の研修の項目が明らかに他のセクション由来か、列のずれが起きているかを判定する。
            """
            if not isinstance(item, dict) or not training_marker_found:
                return False
            section_lines = [line.strip() for line in plain.splitlines() if line.strip()]
            marker_positions = [
                i for i, line in enumerate(section_lines)
                if line in {"培训经历", "培训经验"}
                or line.startswith(("培训经历：", "培训经历:", "培训经验：", "培训经验:"))
            ]
            if not marker_positions:
                return False
            section_start = marker_positions[-1]
            section_stops = {
                "教育经历", "教育背景", "项目经历", "项目经验", "工作经历", "工作经验",
                "专业技能", "技能/语言", "证书", "语言能力", "自我评价",
                "在校学习情况", "在校情况", "在校实践经历", "兴趣爱好", "附加信息", "其他信息",
            }
            section_end = next(
                (i for i in range(section_start + 1, len(section_lines)) if section_lines[i] in section_stops),
                len(section_lines),
            )
            section_compact = _compact_text("\n".join(section_lines[section_start:section_end]))
            org = str(item.get("organization_name") or "").strip()
            tname = str(item.get("training_name") or "").strip()
            desc = str(item.get("description") or "").strip()
            # 机构名/课程名都不在培训板块，通常是工作经历或项目经历串入。
            # EN: Neither the provider name nor the course name is in the training section; usually work or project history has leaked in.
            # JA: 機関名もコース名も研修の欄にない場合は、通常は職歴かプロジェクト経験が混入したものである。
            if org and _compact_text(org) not in section_compact:
                return True
            if tname and _compact_text(tname) not in section_compact:
                return True
            desc_lines = [line.strip() for line in desc.splitlines() if line.strip()]
            if desc_lines and re.match(r"^\s*\d{1,2}\s*[:：]", desc_lines[0]):
                return True
            # 课程名/机构名重复出现在 description 首段，是典型列串位。
            # EN: The course/provider name repeated in the first paragraph of description is a typical column misplacement.
            # JA: コース名・機関名が description の最初の段落に重複して現れるのは典型的な列のずれである。
            if tname and _compact_text(tname) in _compact_text(desc):
                return True
            if org and _compact_text(org) in _compact_text(desc):
                return True
            return False

        training_fields_swapped = any(
            isinstance(current_item, dict)
            and isinstance(web_item, dict)
            and _compact_text(current_item.get("organization_name"))
            and _compact_text(current_item.get("training_name"))
            and _compact_text(web_item.get("organization_name"))
            and _compact_text(web_item.get("training_name"))
            and _compact_text(current_item.get("organization_name")) == _compact_text(web_item.get("training_name"))
            and _compact_text(current_item.get("training_name")) == _compact_text(web_item.get("organization_name"))
            for current_item in current_trains
            for web_item in valid_web_trains
        )
        current_training_dirty = any(
            _web_training_composite_noise(item)
            or _web_training_needs_alignment(item)
            or any(
                token in str(item.get(key) or "")
                for key in ("organization_name", "training_name", "certificate_name", "description")
                for token in ("公司描述", "工作职责", "项目经历", "项目描述", "奖项描述", "活动描述", "在校学习情况")
            )
            for item in current_trains
            if isinstance(item, dict)
        )
        if valid_web_trains and (
            len(valid_web_trains) > len(valid_current_trains)
            or len(valid_current_trains) != len(current_trains)
            or not current_trains
            or specialized_is_cleaner
            or training_fields_swapped
            or (len(valid_web_trains) == len(valid_current_trains) and current_training_dirty)
        ):
            r["training_list"] = valid_web_trains
        elif len(valid_current_trains) != len(current_trains):
            r["training_list"] = valid_current_trains
        elif current_trains and not valid_web_trains and not training_marker_found:
            # 没有培训板块时，现有 training 多半是工作/项目/技能串位，
            # 不能因为旧 JSON 已有值就继续保留。
            # EN: Without a training section, the existing training is most likely misplaced work/project/skills content,
            #     and must not be kept just because the old JSON already has values.
            # JA: 研修の欄がない場合、既存の training は職歴・プロジェクト・スキルがずれて入ったものである可能性が高く、
            #     旧 JSON にすでに値があるというだけで残してはならない。
            r["training_list"] = []

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

        # CONTEXT 的正式字段名为 resume_languge；内部兼容旧解析器的 resume_language
        # 只在处理中使用，写出前统一为正式字段，避免两套字段并存。
        # EN: CONTEXT's formal field name is resume_languge; resume_language, kept internally for compatibility with the old parser,
        #     is used only during processing and is unified to the formal field before writing out, so the two field sets do not coexist.
        # JA: CONTEXT の正式なフィールド名は resume_languge である。旧パーサーとの互換のために内部で使う resume_language は
        #     処理中だけ使い、書き出す前に正式なフィールドに統一して、2 種類のフィールドが併存しないようにする。
        r["resume_languge"] = str(r.get("resume_language") or r.get("resume_languge") or "zh").lower()
        r.pop("resume_language", None)
        resumes_normalized.append(r)

    if not resumes_normalized:
        return False, "解析后无有效 resume 对象", None

    for resume in resumes_normalized:
        base_info = resume.get("base_info") if isinstance(resume, dict) else None
        if isinstance(base_info, dict) and not str(base_info.get("full_name") or "").strip():
            base_info["full_name"] = f"待确认姓名_{rec_id[:8]}"

    contact_phone, contact_email = _contact_values(resumes_normalized, plain)
    if not contact_phone and not contact_email:
        return True, "跳过：简历同时缺少手机号和邮箱", None
    primary_base_info = resumes_normalized[0].get("base_info") or {}
    if isinstance(primary_base_info, dict):
        if contact_phone and not str(primary_base_info.get("phone") or "").strip():
            primary_base_info["phone"] = contact_phone
        if contact_email and not str(primary_base_info.get("email") or "").strip():
            primary_base_info["email"] = contact_email

    zh_resume = resumes_normalized[0]

    # ============ 顶层 5 大对象（严格参考 JSON：无 6 lists，只有 base/expected/current/education + resumes）============
    # EN: ============ Top-level 5 main objects (strictly following the reference JSON: no 6 lists, only base/expected/current/education + resumes) ============
    # JA: ============ トップレベルの 5 つの主要オブジェクト（参照 JSON に厳密に従う：6 つのリストはなく、base/expected/current/education + resumes だけ）============
    sd_base_info = copy.deepcopy(zh_resume["base_info"])
    sd_expected_info = copy.deepcopy((zh_resume.get("expected_list") or [{}])[0])
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
    language_folder = _language_folder(resumes_normalized)
    json_path = json_dir / language_folder / json_name

    if json_path.exists() and not force:
        return True, "已存在跳过（可--force覆盖）", str(json_path)

    json_path.parent.mkdir(parents=True, exist_ok=True)

    # 顶层 raw_text 构建（从结构化数据）
    # EN: Build the top-level raw_text (from the structured data)
    # JA: トップレベルの raw_text を組み立てる（構造化データから）
    top_raw_text = _build_top_level_raw_text(structured_data)
    # 兜底：如果结构化数据没抽到文字，就用 plain 前 20000 字
    # EN: Fallback: if no text was extracted into the structured data, use the first 20000 characters of plain
    # JA: 最終手段：構造化データでテキストが取れなかった場合は、plain の先頭 20000 文字を使う
    if not top_raw_text:
        top_raw_text = plain[:20000]

    source_stat_path = source_file if source_file.exists() else html_path
    source_block = {
        "path": str(html_path.resolve()),
        "original_path": str(source_file),
        "filename": filename,
        "extension": source_suffix,
        "size": source_stat_path.stat().st_size,
        "html_filename": html_path.name,
        "note": "由 web_html_to_json.v2.py 从 Web 来源 HTML/MHT/EML 转换",
    }
    extraction_block = {
        "reader_group": "web_html_dom",
        "converter": "web_html_to_json.v2.py",
        "parser": "codex_gemini_html_schema_parser",
        "status": "success",
        "html_path": str(html_path.resolve()),
        "parser_version": "CodexGeminiHtmlSchemaParser + web_postprocess_v2.0",
        "record_id": rec_id,
        "plain_text_length": len(plain),
        "source_relative_path": metadata.get("relative_path", ""),
        "source_landing_time": metadata.get("source_landing_time", ""),
        "dom": {
            "heading_count": len(re.findall(r"<h[1-6][^>]*>", html_text, re.I)),
            "table_count": len(re.findall(r"<table[^>]*>", html_text, re.I)),
            "row_count":   len(re.findall(r"<tr[^>]*>",    html_text, re.I)),
            "paragraph_count": len(re.findall(r"<p[^>]*>",  html_text, re.I)),
            "headings": [],
        },
        "classifier_result": classification_data,
    }

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
        "classification": {
            "document_type": classification_data.get("document_type", "resume"),
            "reason": classification_data.get("reason", ""),
        },
        "structured_data": structured_data,
        "raw_text": top_raw_text,
        "quality": {
            "full_name": safe_name,
            "has_work": bool(zh_resume.get("work_experiences")),
            "work_count": len(zh_resume.get("work_experiences") or []),
            "has_education": bool(zh_resume.get("education_list")),
            "education_count": len(zh_resume.get("education_list") or []),
            "raw_text_length": len(top_raw_text),
            "status": "needs_review" if classification_data.get("document_type") == "ambiguous_resume" or fallback_failures else "passed",
            "contact": {"phone": contact_phone, "email": contact_email},
            "issues": fallback_failures,
        },
    }

    # ============== 最关键：强制顶层结构闸门 ==============
    # EN: ============== Most critical: the forced top-level structure gate ==============
    # JA: ============== 最も重要：トップレベル構造を強制するゲート ==============
    record = _force_top_level_schema(record)

    _atomic_write_json(json_path, record)
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
    map_payload, map_records = _load_web_map(args.map_path)

    if map_records:
        work_items: list[tuple[Path, dict[str, Any]]] = []
        for row in map_records:
            staged = Path(str(row.get("stage_path") or row.get("html_path") or ""))
            source = Path(str(row.get("source_path") or ""))
            candidate = staged if staged.exists() else source
            if candidate:
                work_items.append((candidate, row))
        total = len(work_items)
        print(f"[map 全量模式] Web sheet 记录 {total} 条；后缀范围: .html/.htm/.mht/.mhtml/.eml" f" / [map full mode] {total} Web sheet records; suffix range: .html/.htm/.mht/.mhtml/.eml / [map 全件モード] Web シートのレコード {total} 件、拡張子の範囲：.html/.htm/.mht/.mhtml/.eml")
    else:
        all_htmls = sorted([
            p for p in html_dir.rglob("*")
            if p.is_file() and p.suffix.lower() in (".html", ".htm", ".mht", ".mhtml", ".eml")
            and not p.name.startswith("_")
        ]) if html_dir.exists() else []
        work_items = [(path, {}) for path in all_htmls]
        total = len(work_items)
        print(f"[目录扫描模式] 目录共 {total} 个 HTML-like 文件（建议先生成 map）" f" / [directory scan mode] {total} HTML-like files in the directory (generating the map first is recommended) / [ディレクトリ走査モード] ディレクトリ内に HTML 風ファイルが {total} 個（先にマップを生成することを推奨）")

    if args.limit and args.limit > 0:
        if args.random_sample:
            import random as _rnd
            _rnd.seed(args.seed)
            sample_n = min(args.limit, total)
            work_items = _rnd.sample(work_items, sample_n)
            print(f"[随机抽样] seed={args.seed}, limit={args.limit}；范围共 {total} 个，本次随机抽 {len(work_items)} 个" f" / [random sampling] seed={args.seed}, limit={args.limit}; {total} in range, {len(work_items)} drawn at random this time / [ランダムサンプリング] seed={args.seed}, limit={args.limit}、範囲は {total} 個、今回ランダムに {len(work_items)} 個を抽出")
        else:
            work_items = work_items[: args.limit]
            print(f"[抽样模式] limit={args.limit}；范围共 {total} 个，本次抽样 {len(work_items)} 个" f" / [sampling mode] limit={args.limit}; {total} in range, {len(work_items)} sampled this time / [サンプリングモード] limit={args.limit}、範囲は {total} 個、今回 {len(work_items)} 個をサンプリング")
    else:
        print(f"[全量模式] 本次处理 {total} 个 Web 文件" f" / [full mode] {total} Web files to process this time / [全件モード] 今回は Web ファイル {total} 個を処理します")

    if args.indices:
        wanted = set(args.indices)
        work_items = [
            item for item in work_items
            if int(item[1].get("index", -1) or -1) in wanted
        ]
        print(f"[定点模式] 指定序号 {sorted(wanted)}；本次处理 {len(work_items)} 个" f" / [targeted mode] given indices {sorted(wanted)}; {len(work_items)} to process this time / [ピンポイントモード] 指定番号 {sorted(wanted)}、今回は {len(work_items)} 個を処理します")

    total_success = 0
    total_failed = 0
    total_skipped = 0
    items_report: list[dict[str, Any]] = []
    t0 = time.time()

    for i, (hp, metadata) in enumerate(work_items, 1):
        ok, msg, jpath = process_single_html(
            hp,
            json_dir,
            force=args.force,
            source_path=Path(str(metadata.get("source_path"))) if metadata.get("source_path") else None,
            metadata=metadata,
        )
        if ok and "跳过" in msg:
            total_skipped += 1
        elif ok:
            total_success += 1
        else:
            total_failed += 1
        if "非简历" in msg:
            item_status = "not_resume"
        elif "同时缺少手机号和邮箱" in msg:
            item_status = "skipped_no_contact"
        elif "已存在跳过" in msg:
            item_status = "passed_existing"
        elif ok:
            item_status = "passed"
        else:
            item_status = "failed"
        item = {
            "seq": i,
            "html": hp.name,
            "report_row": metadata.get("report_row", ""),
            "source_path": metadata.get("source_path", str(hp.resolve())),
            "stage_path": str(hp.resolve()),
            "status": item_status,
            "success": ok and "跳过" not in msg,
            "skipped": "跳过" in msg,
            "message": msg,
            "json_path": jpath or "",
        }
        items_report.append(item)
        if metadata and map_records:
            metadata["status"] = item_status
            metadata["message"] = msg
            metadata["json_path"] = jpath or metadata.get("json_path", "")
            metadata["json_paths"] = [jpath] if jpath else metadata.get("json_paths", [])
            metadata["error_reason"] = "" if ok else msg
            metadata["processed_at"] = datetime.now(tz=TZ_JST).isoformat(timespec="seconds")
            if jpath:
                metadata["language_folder"] = Path(jpath).parent.name
        if i % args.progress_interval == 0 or i == len(work_items):
            elapsed = time.time() - t0
            print(f"  [{i}/{len(work_items)}] {hp.name} → {msg}  (已用时 {elapsed:.1f}s)" f" / [{i}/{len(work_items)}] {hp.name} → {msg}  (elapsed {elapsed:.1f}s) / [{i}/{len(work_items)}] {hp.name} → {msg}  （経過 {elapsed:.1f} 秒）")
        if map_records and i % max(args.progress_interval, 25) == 0:
            _atomic_write_json(args.map_path, map_payload)

    elapsed = time.time() - t0
    report_data = {
        "generated_at": datetime.now(tz=TZ_JST).strftime("%Y-%m-%d %H:%M:%S"),
        "html_dir": str(html_dir),
        "json_dir": str(json_dir),
        "limit": args.limit,
        "force": args.force,
        "map_path": str(args.map_path),
        "counts": {
            "found": len(work_items),
            "success": total_success,
            "failed": total_failed,
            "skipped": total_skipped,
        },
        "elapsed_seconds": round(elapsed, 2),
        "items": items_report,
    }
    report_name = "_web_batch_report.targeted.v2.json" if args.indices else "_web_batch_report.v2.json"
    report_path = json_dir / report_name
    _atomic_write_json(report_path, report_data)
    if map_records:
        refreshed_counts: dict[str, int] = {}
        for row in map_records:
            row_status = str(row.get("status") or "pending")
            refreshed_counts[row_status] = refreshed_counts.get(row_status, 0) + 1
        map_payload["counts"] = refreshed_counts
        map_payload["last_batch_report"] = str(report_path.resolve())
        map_payload["last_batch_at"] = report_data["generated_at"]
        _atomic_write_json(args.map_path, map_payload)

    print("\n=== web 目录 HTML→JSON 批处理完成 ===" " / \n=== web directory HTML→JSON batch finished === / \n=== web ディレクトリの HTML→JSON 一括処理が完了しました ===")
    print(f"总计 发现:{len(work_items)} 成功:{total_success} 失败:{total_failed} 跳过:{total_skipped}" f" / Total found:{len(work_items)} success:{total_success} failed:{total_failed} skipped:{total_skipped} / 合計 検出:{len(work_items)} 成功:{total_success} 失敗:{total_failed} スキップ:{total_skipped}")
    print(f"总耗时: {elapsed:.2f} 秒；报告: {report_path}" f" / Total time: {elapsed:.2f} s; report: {report_path} / 所要時間：{elapsed:.2f} 秒、レポート：{report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
