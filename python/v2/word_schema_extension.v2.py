"""隔离的 Word -> HTML DOM -> JSON 试跑流程。

这个脚本不改动 Gemini 原文件、demo 样本或既有 jsons/complete-jsons。
默认只处理源目录中前 100 个真实 Word 文件，分两个明确阶段：

1. 每个 Word 单独转换为 HTML，写入 complete-transfered-htmls/；
2. 只读取这批 HTML，按 DOM 解析并写入 complete-transfered-jsons/。

输出目录使用独立前缀，便于人工核对后再合并到正式 MAP。

EN: Isolated Word -> HTML DOM -> JSON trial-run flow.

This script does not touch the original Gemini files, demo samples or existing jsons/complete-jsons.
By default it only processes the first 100 real Word files in the source directory, in two explicit stages:

1. Each Word file is converted to HTML separately and written to complete-transfered-htmls/;
2. Only this batch of HTML is read, parsed by DOM, and written to complete-transfered-jsons/.

The output directories use a separate prefix so they can be checked by hand before merging into the formal MAP.

JA: 分離された Word -> HTML DOM -> JSON の試行フロー。

このスクリプトは Gemini の元ファイル、demo サンプル、既存の jsons/complete-jsons を変更しない。
既定ではソースディレクトリ内の実際の Word ファイルのうち先頭 100 件だけを、2 つの明確な段階で処理する：

1. Word ファイルを 1 件ずつ HTML に変換し、complete-transfered-htmls/ に書き込む。
2. このバッチの HTML だけを読み、DOM で解析して complete-transfered-jsons/ に書き込む。

出力ディレクトリには別の接頭辞を付け、人手で確認してから正式な MAP に統合できるようにする。
"""
from __future__ import annotations
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1] / "common"))
import rc_config as _rc  # noqa: E402  项目统一配置（python/common/rc_config.py）
# EN: noqa: E402  project-wide configuration (python/common/rc_config.py)
# JA: noqa: E402  プロジェクト共通設定（python/common/rc_config.py）

import argparse
from email import policy
from email.parser import BytesParser
import hashlib
import io
import json
import os
import re
import html as html_module
import shutil
import subprocess
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
)
from resume_importer.classifier import DocumentClassifier
from resume_importer.structured_parser import StructuredResumeParser

try:
    from bs4 import BeautifulSoup, Comment
except ImportError:  # pragma: no cover - requirements install guard
    BeautifulSoup = None  # type: ignore[assignment]
    Comment = ()  # type: ignore[assignment]

try:
    import mammoth
except ImportError:  # pragma: no cover - environment guard
    mammoth = None  # type: ignore[assignment]

TZ_JST = timezone(timedelta(hours=9))
WORD_EXTENSIONS = frozenset({".doc", ".docm", ".docx", ".dotx", ".wps"})
AUX_PREFIXES = ("._", "~$")
FORMAT_OUTPUT_DIRS = ("docs", "pdf", "xls", "web", "text", "presentation", "image")
SUSPICIOUS_NAME_WORDS = {
    "未知", "目前", "未婚", "已婚", "副总经理", "基本资料", "个人简历",
    "销售和回款", "高速梯", "共青团员", "销售部经理", "工作经历",
}

# Windows 默认控制台常是 GBK；文件名可能含不在 GBK 中的字符（例如 NBSP），
# 批处理输出必须替换不可编码字符，不能因为打印进度导致整个跑批中断。
# EN: The default Windows console is often GBK, and file names may contain characters outside GBK (e.g. NBSP);
#     batch output must replace unencodable characters so printing progress cannot abort the whole batch run.
# JA: Windows の既定コンソールは GBK であることが多く、ファイル名に GBK にない文字（例：NBSP）が含まれることがある。
#     バッチ出力ではエンコードできない文字を置換し、進捗表示のせいでバッチ全体が止まらないようにする。
if os.name == "nt":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Codex Word -> HTML DOM -> JSON 100 条试跑" " / Codex Word -> HTML DOM -> JSON trial run of 100 / Codex Word -> HTML DOM -> JSON の 100 件の試行")
    p.add_argument("--source", type=Path, default=PROJECT_ROOT / _rc.dirname("需要采集的简历文件夹"))
    p.add_argument("--html-output", type=Path, default=PROJECT_ROOT / _rc.dirname("complete-transfered-htmls"))
    p.add_argument("--json-output", type=Path, default=PROJECT_ROOT / _rc.dirname("complete-transfered-jsons"))
    p.add_argument("--category", default="docs", choices=FORMAT_OUTPUT_DIRS,
                   help="当前格式批次的输出子目录；Word 类型使用 docs" " / Output subdirectory of the current format batch; Word types use docs / 現在の形式のバッチの出力サブディレクトリ（Word 形式は docs を使う）")
    p.add_argument("--limit", type=int, default=100)
    p.add_argument("--all", action="store_true", help="处理源目录下全部支持的 Word 文件，忽略 --limit" " / Process all supported Word files under the source directory, ignoring --limit / 元ディレクトリ配下の対応するすべての Word ファイルを処理し、--limit を無視する")
    p.add_argument("--force", action="store_true")
    p.add_argument("--legacy-timeout", type=int, default=60)
    p.add_argument("--progress-interval", type=int, default=10)
    return p.parse_args()


def is_real_word(path: Path) -> bool:
    return (
        path.is_file()
        and path.suffix.lower() in WORD_EXTENSIONS
        and not path.name.startswith(AUX_PREFIXES)
    )


def source_files(source: Path, limit: int) -> list[Path]:
    files = sorted((p for p in source.rglob("*") if is_real_word(p)), key=lambda p: str(p).casefold())
    return files if limit <= 0 else files[:limit]


def record_id(path: Path) -> str:
    stat = path.stat()
    value = f"{path.resolve()}|{stat.st_size}|{stat.st_mtime_ns}"
    return hashlib.sha256(value.encode("utf-8", "surrogatepass")).hexdigest()


def html_name(path: Path) -> str:
    stem = re.sub(r"[^\w\u4e00-\u9fff.-]+", "_", path.stem).strip("._") or "document"
    return f"{stem}__{record_id(path)[:12]}.html"


def name_quality_flags(name: str) -> list[str]:
    """只做批次复核提示，不自动改名；避免把职位/章节误当候选人姓名。

    EN: Only gives batch review hints and does not rename automatically, to avoid taking positions/section titles as candidate names.

    JA: バッチのレビュー用ヒントを出すだけで自動改名はしない。職位や章見出しを候補者名と誤認しないため。
    """
    value = re.sub(r"\s+", " ", str(name or "")).strip()
    flags: list[str] = []
    if not value or value in SUSPICIOUS_NAME_WORDS:
        flags.append("姓名缺失或疑似为职位/章节文字")
    if re.search(r"简历|资料|工作经历|教育经历|自我评价|求职意向|销售和回款|高速梯|共青团员", value, re.I):
        flags.append("姓名包含简历章节、职位或其他非姓名关键词")
    if len(re.sub(r"[^\u4e00-\u9fff]", "", value)) > 6:
        flags.append("中文姓名长度异常，需回看原文")
    return list(dict.fromkeys(flags))


def plain_text(html_text: str) -> str:
    if not html_text:
        return ""
    if BeautifulSoup is None:
        return re.sub(r"<[^>]+>", "\n", html_text)
    soup = BeautifulSoup(html_text, "html.parser")
    for tag in soup(["script", "style", "xml", "meta", "link"]):
        tag.decompose()
    return "\n".join(line.strip() for line in soup.get_text("\n").splitlines() if line.strip())


def normalize_html(html_text: str) -> str:
    """清理噪声但保留 DOM：表格、行列、标题、段落和列表均不压平。

    EN: Clean noise but keep the DOM: tables, rows/columns, headings, paragraphs and lists are not flattened.

    JA: ノイズを除去しつつ DOM は保持する：表・行列・見出し・段落・リストは平坦化しない。
    """
    if not html_text:
        return ""
    if BeautifulSoup is None:
        return html_text
    soup = BeautifulSoup(html_text, "html.parser")
    for node in soup.find_all(string=lambda value: isinstance(value, Comment)):
        node.extract()
    for tag in soup(["script", "style", "xml", "link"]):
        tag.decompose()
    # 只删除视觉属性，不删除表格结构和语义属性。
    # EN: Remove only visual attributes; do not remove table structure or semantic attributes.
    # JA: 見た目の属性だけを削除し、表の構造や意味的な属性は削除しない。
    keep = {"id", "lang", "rowspan", "colspan", "scope", "alt", "title"}
    for tag in soup.find_all(True):
        tag.attrs = {key: value for key, value in tag.attrs.items() if key in keep}
    body = soup.body
    if body:
        for nested_body in body.find_all("body"):
            nested_body.unwrap()
    body_content = "".join(str(child) for child in body.contents) if body else str(soup)
    return "<!doctype html><html><head><meta charset=\"utf-8\"></head><body>" + body_content + "</body></html>"


def convert_docx(path: Path) -> str:
    if mammoth is None:
        raise RuntimeError("缺少 mammoth，无法转换 docx/docm")
    with path.open("rb") as handle:
        result = mammoth.convert_to_html(handle)
    return f"<!doctype html><html><head><meta charset=\"utf-8\"></head><body>{result.value}</body></html>"


def looks_like_mhtml(data: bytes) -> bool:
    head = data[:8192].lower()
    return (
        b"mime-version:" in head
        and (b"multipart/related" in head or b"this is a multi-part message" in head)
    )


def decode_mhtml(data: bytes) -> str:
    """从扩展名伪装成 .doc 的 MHTML 中提取真正的 text/html 部分。

    EN: Extract the real text/html part from MHTML disguised with a .doc extension.

    JA: .doc の拡張子に偽装した MHTML から本当の text/html 部分を抽出する。
    """
    message = BytesParser(policy=policy.default).parsebytes(data)
    for part in message.walk():
        if part.get_content_type().lower() != "text/html":
            continue
        payload = part.get_payload(decode=True)
        if payload is None:
            raw = part.get_payload()
            if isinstance(raw, str):
                return raw
            continue
        charset = (part.get_content_charset() or "").lower().strip()
        if charset in ("unicode", "utf-16", "utf16"):
            charset = "utf-16"
        if payload.startswith((b"\xff\xfe", b"\xfe\xff")) or payload[:100].count(b"\x00") > 10:
            for u_enc in ("utf-16", "utf-16le", "utf-16be"):
                try:
                    return payload.decode(u_enc)
                except Exception:
                    pass
        for encoding in (charset, "utf-8", "gb18030", "gbk"):
            if not encoding: continue
            try:
                return payload.decode(encoding)
            except (LookupError, UnicodeDecodeError):
                continue
    raise RuntimeError("MHTML 中没有找到 text/html 部分")


def convert_legacy(path: Path, output: Path, timeout: int) -> str:
    """旧版 .doc/.wps 隔离交给现有只读 Word COM 转换器。

    EN: Isolation of old .doc/.wps is delegated to the existing read-only Word COM converter.

    JA: 旧 .doc/.wps の分離処理は既存の読み取り専用 Word COM 変換器に任せる。
    """
    helper = _rc.PYTHON_DIR / "v2" / "docs_to_html_and_complete.py"
    completed = subprocess.run(
        [sys.executable, str(helper), "--convert-single", str(path), str(output)],
        capture_output=True,
        timeout=timeout,
        cwd=str(PROJECT_ROOT),
    )
    if not output.exists() or output.stat().st_size < 100:
        detail = (completed.stderr or completed.stdout or b"").decode("utf-8", "replace")[-500:]
        raise RuntimeError(f"Word COM 转换失败：{detail}")
    for encoding in ("utf-8", "gb18030", "gbk", "gb2312"):
        try:
            return output.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    return output.read_text(encoding="utf-8", errors="replace")


def convert_antiword(path: Path) -> str:
    antiword = shutil.which("antiword") or r"C:\Program Files\Git\mingw64\bin\antiword.exe"
    if not Path(antiword).exists():
        raise RuntimeError("找不到 antiword 备用转换器")
    result = subprocess.run(
        [antiword, "-m", "UTF-8", str(path)],
        capture_output=True,
        timeout=30,
    )
    text = (result.stdout or b"").decode("utf-8", "replace")
    if not text.strip():
        raise RuntimeError("antiword 没有提取出正文")
    paragraphs = []
    for line in text.replace("\r\n", "\n").replace("\r", "\n").splitlines():
        value = line.strip()
        paragraphs.append(f"<p>{html_module.escape(value)}</p>" if value else "<p></p>")
    return "<!doctype html><html><head><meta charset=\"utf-8\"></head><body data-converter=\"antiword_fallback\">" + "\n".join(paragraphs) + "</body></html>"


def convert_binary_doc_fallback(path: Path) -> str:
    # 已有 HTML 的解析流程不需要旧 Word/OLE 读取依赖。延迟导入可避免
    # process_word_html_to_json.py 在仅解析 HTML 时被 olefile 等可选依赖阻塞。
    # EN: The parse flow for existing HTML does not need the old Word/OLE reader dependencies. Lazy import keeps
    #     process_word_html_to_json.py from being blocked by optional dependencies such as olefile when only parsing HTML.
    # JA: 既存の HTML を解析する流れでは、旧来の Word/OLE 読み取りの依存は不要。遅延インポートにより、
    #     HTML の解析だけを行うときに process_word_html_to_json.py が olefile などの任意依存でブロックされないようにする。
    from resume_importer.extractors import ResumeTextExtractor

    extractor = ResumeTextExtractor()
    text = extractor._extract_doc_without_word(path)
    if not text or len(re.sub(r"\s+", "", text)) < 8:
        raise RuntimeError("离线 OLE 解码没有提取出正文")
    paragraphs = []
    for line in text.replace("\r\n", "\n").replace("\r", "\n").splitlines():
        value = line.strip()
        paragraphs.append(f"<p>{html_module.escape(value)}</p>" if value else "<p></p>")
    return "<!doctype html><html><head><meta charset=\"utf-8\"></head><body>" + "\n".join(paragraphs) + "</body></html>"


def convert_one(path: Path, html_path: Path, timeout: int) -> dict[str, Any]:
    started = time.monotonic()
    try:
        if html_path.exists() and html_path.stat().st_size > 100:
            html = html_path.read_text(encoding="utf-8", errors="replace")
            return {"status": "existing", "seconds": round(time.monotonic() - started, 2)}
        raw_bytes = path.read_bytes()
        # 许多 51job/无忧精英导出的文件扩展名是 .doc，实际是 MIME/MHTML。
        # 必须先解码 MIME，不能交给 Word 或把 base64 当成 HTML。
        # EN: Many files exported by 51job / Wuyou Elite have a .doc extension but are actually MIME/MHTML.
        #     They must be MIME-decoded first, not handed to Word, and base64 must not be treated as HTML.
        # JA: 51job／無憂精英からエクスポートされた多くのファイルは拡張子が .doc だが、実際は MIME/MHTML である。
        #     先に MIME をデコードする必要があり、Word に渡したり base64 を HTML として扱ったりしてはならない。
        method = ""
        fallback_note = ""
        if looks_like_mhtml(raw_bytes):
            html = decode_mhtml(raw_bytes)
            method = "mhtml_decode"
        elif path.suffix.lower() in {".docx", ".docm", ".dotx"}:
            html = convert_docx(path)
            method = "mammoth_docx"
        else:
            try:
                html = convert_legacy(path, html_path, timeout)
                method = "word_com"
            except Exception as legacy_error:
                # 当前环境的 Word COM 可能没有交互登录会话；旧 .doc 仍尝试文本备用解析。
                # EN: Word COM in the current environment may lack an interactive logon session; old .doc files still try the text fallback parser.
                # JA: 現在の環境の Word COM には対話型ログオンセッションがないことがある。旧 .doc でもテキストによる代替解析を試みる。
                try:
                    html = convert_binary_doc_fallback(path)
                    method = "binary_doc_fallback"
                    fallback_note = f"Word COM失败，已使用离线 OLE 解码：{legacy_error}"
                except Exception as binary_error:
                    html = convert_antiword(path)
                    method = "antiword_fallback"
                    fallback_note = f"Word COM/OLE均失败，已使用 antiword：{legacy_error}; {binary_error}"
        html = normalize_html(html)
        if len(plain_text(html)) < 2:
            raise RuntimeError("转换后没有可读文本")
        html_path.write_text(html, encoding="utf-8")
        result = {"status": "success", "converter": method, "seconds": round(time.monotonic() - started, 2)}
        if fallback_note:
            result["fallback_note"] = fallback_note
        return result
    except Exception as exc:
        return {"status": "failed", "error": str(exc), "seconds": round(time.monotonic() - started, 2)}


def date_from_mtime(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime, tz=TZ_JST).strftime("%Y-%m-%d %H:%M:%S")


def local_file_time(path: Path, attribute: str) -> str:
    value = getattr(path.stat(), attribute)
    return datetime.fromtimestamp(value, tz=TZ_JST).isoformat(timespec="seconds")


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


def dom_summary(html: str) -> dict[str, Any]:
    if BeautifulSoup is None:
        return {"heading_count": 0, "table_count": 0, "row_count": 0, "headings": []}
    soup = BeautifulSoup(html, "html.parser")
    headings = [node.get_text(" ", strip=True) for node in soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"]) if node.get_text(strip=True)]
    return {
        "heading_count": len(headings),
        "table_count": len(soup.find_all("table")),
        "row_count": len(soup.find_all("tr")),
        "paragraph_count": len(soup.find_all("p")),
        "headings": headings[:80],
    }


def extend_schema(parsed: dict[str, Any], clean_text: str, filename: str, source_path: str) -> dict[str, Any]:
    """在 Gemini 样本结构上补充三个集合，不改原 Gemini 解析器。

    EN: Add three collections on top of the Gemini sample structure without changing the original Gemini parser.

    JA: 元の Gemini パーサーは変えずに、Gemini サンプルの構造に 3 つのコレクションを追加する。
    """
    data = dict(parsed or {})
    resumes = list(data.get("resumes") or [])
    helper = StructuredResumeParser()
    fallback = helper.parse(clean_text, filename, source_path)

    # 表单里的“职位申请表”是文档标题，不是候选人的求职职位；优先读取
    # Applied Position / 申请职位后的真实职位名称。
    # EN: "职位申请表" (job application form) in a form is the document title, not the candidate's desired position; prefer
    #     the real position name after Applied Position / 申请职位.
    # JA: フォーム内の「职位申请表」（職位応募票）は文書のタイトルであり、候補者の希望職位ではない。
    #     Applied Position／申请职位 の後にある実際の職位名を優先して読む。
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

    company_suffix = r"(?:有限公司|有限责任公司|股份有限公司|集团(?:公司)?|研究所|研究中心|研究院|中心|公司|株式会社|会社|Corporation|Company|Consulting|Institute|Center|银行|監査法人)"

    def extract_company_name(value: str) -> str:
        """从公司行中保留完整机构名，尤其不能截掉“日立电梯(上海)”等括号。

        EN: Keep the full institution name from the company line; in particular, brackets like "日立电梯(上海)" must not be cut off.

        JA: 会社行から機関名を完全な形で残す。特に「日立电梯(上海)」などの括弧を切り落としてはならない。
        """
        value = re.sub(r"\s+", " ", str(value or "")).strip(" ：:|│")
        # 只去除行末表示任职时长/合作方式的括号，不去除公司名内部括号。
        # EN: Only remove trailing brackets that indicate tenure/cooperation type; do not remove brackets inside the company name.
        # JA: 行末にある在職期間・協力形態を示す括弧だけを除去し、会社名内部の括弧は除去しない。
        value = re.sub(r"\s*[\[【［(（][^\]】］)）]*(?:\d+\s*(?:年|个月|月)|合作|外包|兼职|代接)[^\]】］)）]*[\]】］)）]\s*$", "", value, flags=re.I).strip()
        match = re.search(rf"(?P<company>.{{2,140}}?{company_suffix})", value, re.I)
        return (match.group("company") if match else value).strip(" ：:|│")

    def infer_work_context(row: dict[str, Any]) -> tuple[str, str]:
        """从日期对应的原文工作段校正公司和职位，避免字段错位。

        EN: Correct the company and position from the original work section matching the dates, to avoid misplaced fields.

        JA: 日付に対応する原文の職歴段落から会社と職位を補正し、フィールドのずれを防ぐ。
        """
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
        # 工作段中，公司通常是单独一行；先排除“公司性质/公司规模”等字段。
        # EN: In a work section the company is usually on its own line; first exclude fields such as "company type / company size".
        # JA: 職歴の段落では会社が単独の行にあることが多い。まず「会社の性質／会社規模」などのフィールドを除外する。
        company_match = re.search(
            rf"(?m)^\s*(?!公司(?:性质|规模|行业|描述)|所在|汇报|下属|职位类别|工作职责|工作内容|工作描述)"
            rf"(?P<company>.{{2,120}}?{company_suffix})\s*$",
            window,
            re.I,
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
        # 去掉简历模板附加的任职时长/合作说明，不污染公司主字段。
        # EN: Remove the tenure/cooperation notes added by résumé templates so they do not pollute the main company field.
        # JA: 履歴書テンプレートが付け加える在職期間・協力形態の説明を除去し、会社の主フィールドを汚染しないようにする。
        company = re.sub(r"\s*[\[【［(（][^\]】］)）]*(?:年|个月|month|year|代接|合作|外包|兼职)[^\]】］)）]*[\]】］)）]\s*$", "", company, flags=re.I).strip()
        company = re.sub(r"^\s*(?:\d+年\d*个月?|\d+个月?|\d+月)\s*(?:[一至到\-—~～]+\s*(?:至今|现在)?)?\s*", "", company)
        company = re.sub(r"^.*?(?:至今|现在|至現在|現在)\s+", "", company).strip()
        # 日文银行/审计行把部门和职责紧接在机构名后，独立出真正机构名。
        # EN: Japanese bank/audit lines put the department and duties right after the institution name; separate out the real institution name.
        # JA: 日本の銀行・監査の行では機関名の直後に部署と職務が続くため、本来の機関名を切り出す。
        bank_name = re.match(r"^(.+?(?:銀行|银行))", company, re.I)
        if bank_name:
            company = bank_name.group(1).strip()
        if "KPMG監査法人" in company:
            company = "KPMG監査法人"
        company = re.sub(r"\s*\.\s*(?:VP|Vice President|Director|Manager|内部审计|internal audit).*$", "", company, flags=re.I).strip()
        # “2018年9月 一 至今 公司”常见于纯文本模板，补齐起始月。
        # EN: "2018年9月 一 至今 公司" is common in plain-text templates; fill in the start month.
        # JA: 「2018年9月 一 至今 会社」はプレーンテキストのテンプレートによくある形で、開始月を補う。
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
        # 某些模板把“公司名 职位”整体写入了公司或职位字段。
        # EN: Some templates write "company name + position" as a whole into the company or position field.
        # JA: テンプレートによっては「会社名 職位」をまとめて会社または職位フィールドに書き込んでいる。
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
        # 若通用解析把公司行首字截掉（例如“日立电梯”变成“立电梯”），
        # 以同一日期窗口中的完整公司名为准。只要当前值不是原文中的完整
        # 连续片段，就允许上下文校正。
        # EN: If the generic parser cuts off the first character of a company line (e.g. "日立电梯" becomes "立电梯"),
        #     use the full company name within the same date window. As long as the current value is not a complete
        #     contiguous fragment of the source text, contextual correction is allowed.
        # JA: 汎用パーサーが会社行の先頭文字を切り落とした場合（例：「日立电梯」が「立电梯」になる）、
        #     同じ日付範囲内の完全な会社名を正とする。現在の値が原文中の完全な連続部分でない限り、文脈による補正を許可する。
        if inferred_company and (
            not re.search(re.escape(company), clean_text, re.I)
            or (len(inferred_company) > len(company) and inferred_company.endswith(company.rstrip("（(")))
        ):
            company = inferred_company
        # 日文银行/监査法人履历的职位通常与公司写在同一行，通用 DOM 解析容易把下一行职责当职位。
        # EN: In Japanese bank / audit firm histories the position is usually on the same line as the company; generic DOM parsing tends to treat the next line's duties as the position.
        # JA: 日本の銀行・監査法人の経歴では職位が会社と同じ行に書かれることが多く、汎用 DOM 解析は次の行の職務を職位と誤認しやすい。
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
        # 中文“日期 公司 职位”行优先于下一行的“主要工作内容/工作描述”标题。
        # EN: A Chinese "date company position" line takes priority over the "main duties / job description" heading on the next line.
        # JA: 中国語の「日付 会社 職位」の行は、次の行の「主な業務内容／職務説明」の見出しより優先する。
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
        # 从职责原文首部补回被错位的职位/公司，并清除模板元数据前缀。
        # EN: Recover the misplaced position/company from the start of the duties text and remove template metadata prefixes.
        # JA: 職務原文の先頭からずれた職位・会社を補い戻し、テンプレートのメタデータ接頭辞を除去する。
        responsibility = str(row.get("position_responsibilities") or "").replace("\r", "").strip()
        if responsibility:
            first_lines = [line.strip(" \t|│") for line in responsibility.splitlines() if line.strip()]
            if first_lines:
                first = first_lines[0]
                first = re.sub(r"\s*[\[【［(（][^\]】］)）]*(?:年|个月|month|year)[^\]】］)）]*[\]】］)）]\s*$", "", first, flags=re.I).strip()
                if not re.search(r"公司性质|公司规模|公司行业|工作描述|工作职责", first):
                    company_match = re.search(rf"(?P<company>.{{2,100}}?{company_suffix})(?=\s*[，,：:|｜ ]|$)", first, re.I)
                    # 已由结构化日期/公司边界识别出的公司优先；只有当前字段缺失或
                    # 明显污染时，才允许从职责首行回填，避免把“2020年10月进入…”
                    # 的日期前缀重新吞进公司名称。
                    # EN: Companies already identified from structured date/company boundaries take priority; only when the current field is missing or
                    #     obviously polluted may it be back-filled from the first line of duties, so the date prefix in "joined ... in October 2020"
                    #     is not swallowed into the company name again.
                    # JA: 構造化された日付・会社の境界から特定済みの会社を優先する。現在のフィールドが欠けているか明らかに汚染されている場合に限り、
                    #     職務の 1 行目から補完を許可し、「2020年10月に…に入社」の日付接頭辞が再び会社名に取り込まれないようにする。
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
                # 工作内容字段不应重复公司名、时长和行业元信息。
                # EN: The duties field should not repeat the company name, tenure or industry metadata.
                # JA: 業務内容フィールドに会社名・在職期間・業界のメタ情報を重複させない。
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
        # 不能把“日立电梯”中的首字“日”当成日期单位删除；这里只清理
        # 真正的数字/分隔符前缀。
        # EN: The first character "日" of "日立电梯" must not be removed as a date unit; only clean up
        #     real digit/separator prefixes here.
        # JA: 「日立电梯」の先頭の「日」を日付の単位として削除してはならない。ここでは本当の数字・区切り文字の接頭辞だけを除去する。
        company = re.sub(r"^[\s\d./-]+", "", company).strip(" ：:|｜")
        row["company_name"] = company
        if position.strip() == company or re.search(company_suffix, position, re.I):
            position = ""
        if not position:
            for line in raw.splitlines():
                line = line.strip(" \t|│")
                if (2 <= len(line) <= 40 and line != company and re.search(r"工程师|经理|主管|专员|代表|分析师|开发|测试|架构师|产品|办事员|销售|职位", line) and not re.search(r"公司|有限公司|工作描述|职责|行业", line)):
                    position = line
                    break
        # 日文岗位常用“内部監査/財務経理/担当業務”等词，不应因日文逗号被清空或退化为下一行职责。
        # EN: Japanese positions often use words like "内部監査/財務経理/担当業務"; they should not be cleared because of Japanese commas or degraded into the next line's duties.
        # JA: 日本語の職位には「内部監査／財務経理／担当業務」などの語がよく使われ、読点のせいで空にされたり次の行の職務に退化したりしてはならない。
        if position and re.search(r"監査|財務|経理|法務|Consultant|担当|部長|課長|主任|係長", position, re.I):
            position = re.split(r"[、，,。；;：:]", position, maxsplit=1)[0].strip()
        if len(position) > 60 or (re.search(r"[，。；;]", position) and not re.search(r"经理|工程师|主管|专员|代表|分析师|开发|测试|架构师|产品|销售|设计|部长|担当|課長", position)):
            position = ""
        if not position:
            # 叙述式经历常写成“进入某公司，任销售经理，负责……”，
            # 该职位不一定单独占一行，直接从原始段落补回。
            # EN: Narrative histories are often written as "joined company X, served as sales manager, responsible for ...";
            #     that position is not necessarily on its own line, so recover it directly from the original paragraph.
            # JA: 叙述式の経歴は「某社に入社し、営業マネージャーを務め、〜を担当」と書かれることが多い。
            #     その職位は必ずしも独立した行にないため、元の段落から直接補い戻す。
            role_from_raw = re.search(r"(?:任职|担任|任)\s*(?P<role>[^，,。；;\n]{2,40})", raw, re.I)
            if role_from_raw:
                candidate_role = role_from_raw.group("role").strip(" ：:，,")
                if candidate_role and len(candidate_role) <= 40:
                    position = candidate_role
        # 表单式工作块的元数据通常在 raw_text 中以“标签行\n值行”出现。
        # 这里统一回填独立字段，避免只保留在职责长文本里。
        # EN: Metadata of form-style work blocks usually appears in raw_text as "label line\nvalue line".
        #     Back-fill them uniformly into separate fields here, instead of leaving them only in the long duties text.
        # JA: フォーム形式の職歴ブロックのメタデータは、raw_text では通常「ラベル行\n値行」の形で現れる。
        #     ここで一括して個別フィールドに補完し、長い職務テキストの中にだけ残らないようにする。
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
        # “下属人数：6 人”应保留真实值，不能被通用默认值 0 人覆盖。
        # EN: "下属人数：6 人" (6 subordinates) should keep the real value and not be overwritten by the generic default of 0.
        # JA: 「下属人数：6 人」（部下 6 名）は実際の値を残し、汎用の既定値 0 人で上書きしてはならない。
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
        # 文件路径、教育字段和文档标题被误识别为公司时，必须丢弃该行。
        # EN: When file paths, education fields or document titles are misidentified as companies, the line must be discarded.
        # JA: ファイルパス・学歴フィールド・文書タイトルが会社と誤認された場合、その行は破棄しなければならない。
        if re.search(r"(?:[A-Za-z]:[\\/]|源文件路径|简历下载|专业\s*[:：]|学历\s*[:：]|教育经历|工作经历)", company):
            return False
        if re.search(r"公司性质|公司规模|公司行业|工作职责|工作内容|企业本质|物联网行业|大学|学院|学校|专业\s*[:：]|学历\s*[:：]|项目经验|项目描述|推行|负责|客户|成立于|项目简介|下属：|所在职务：", company):
            return False
        if re.search(r"^(?:公司名称|名称|所在公司|所属公司)\s*[:：]", company) or re.search(r"担任职务|项目经验|项目描述", str(item.get("position") or "")):
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
        # 兼容“学位 | 日期 | 学校”格式，不能把学位/GPA当成学校名。
        # EN: Support the "degree | date | school" format; the degree/GPA must not be taken as the school name.
        # JA: 「学位 | 日付 | 学校」の形式に対応し、学位や GPA を学校名として扱わない。
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
        # 旧式 Word 行常把“学校+学院/专业”整体放在 school_name。
        # EN: Old-style Word lines often put "school + faculty/major" as a whole into school_name.
        # JA: 旧式の Word の行では「学校 + 学部／専攻」がまとめて school_name に入っていることが多い。
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
    def strip_project_leading_date(value: Any) -> str:
        """项目日期已在 start_ym/end_ym 中独立保存，正文不重复保留日期行。

        EN: Project dates are already stored separately in start_ym/end_ym, so the body does not repeat the date line.

        JA: プロジェクトの日付は start_ym/end_ym に個別に保存済みなので、本文に日付行を重複して残さない。
        """
        text = str(value or "").replace("\r\n", "\n").replace("\r", "\n").strip()
        if not text:
            return ""
        # 支持“2017年至今”、2018/04-2018/06、2018.04-至今等写法。
        # EN: Support forms such as "2017年至今", 2018/04-2018/06 and 2018.04-至今.
        # JA: 「2017年至今」、2018/04-2018/06、2018.04-至今 などの書き方に対応する。
        date_prefix = r"(?:19|20)\d{2}\s*(?:(?:[./-]\s*\d{1,2})|年\s*(?:\d{1,2}\s*月)?)?"
        date_range = rf"{date_prefix}\s*(?:(?:至今|现在|目前)|[-—–~～至到]\s*{date_prefix})?"
        return re.sub(
            rf"^\s*[（(]?{date_range}\s*[）)]?\s*(?:[,，、:：]|\s+|\n+)+",
            "",
            text,
            count=1,
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
        """从连续纯文本模板补出工作段；HTML DOM 没有标题层级时仍按日期切段。

        EN: Recover work sections from continuous plain-text templates; when the HTML DOM has no heading hierarchy, still split by date.

        JA: 連続したプレーンテキストのテンプレートから職歴段落を補う。HTML DOM に見出し階層がない場合でも日付で区切る。
        """
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
                "company_name": company,
                "company_employees": "",
                "company_industry": "",
                "position": role,
                "position_type": "",
                "position_salary": "",
                "position_dept": "",
                "position_report_to": "",
                "position_subordinate": "",
                "employment_type": "全职",
                "annual_salary_min": "",
                "annual_salary_max": "",
                "status": "在职" if not end else "离职",
                "position_start": start,
                "position_resigned": end,
                "resigned_reason": "",
                "position_responsibilities": body,
                "position_achievements": "",
                "raw_text": body,
            })
        return rows
    text_works = text_work_items()
    def text_work_items_v2() -> list[dict[str, Any]]:
        """兼容招聘网站模板：公司名与任职日期分行、日期括号包裹、日/月日期成对出现。

        EN: Support job-site templates: company name and employment dates on separate lines, dates wrapped in brackets, day/month dates appearing in pairs.

        JA: 求人サイトのテンプレートに対応：会社名と在職期間が別の行、日付が括弧で囲まれる、日／月の日付が対で現れる。
        """
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
            # 日期前一行是公司名（51job模板、猎聘模板）。
            # EN: The line before the date is the company name (51job template, Liepin template).
            # JA: 日付の前の行が会社名（51job テンプレート、Liepin テンプレート）。
            prev = lines[idx - 1] if idx else ""
            if (not rest or not company_pat.search(rest)) and company_pat.search(prev) and len(prev) < 120:
                rest = prev
                header_idx = idx - 1
            # 日期单独一行，下一行是公司名。
            # EN: The date is on its own line and the next line is the company name.
            # JA: 日付が単独の行にあり、次の行が会社名。
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
            # 重新按下一个工作日期截断，避免吞入后续公司。
            # EN: Truncate again at the next work date so the following company is not swallowed.
            # JA: 次の職歴の日付で改めて切り詰め、後続の会社を取り込まないようにする。
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
        """候选人报告/表单的标签式工作经历：时间、公司、职位、职位描述严格按标签切段。

        EN: Labelled work history in candidate reports/forms: split strictly by the labels time, company, position, job description.

        JA: 候補者レポート・フォームのラベル付き職歴：期間・会社・職位・職務説明のラベルで厳密に区切る。
        """
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
        """猎聘/候选人报告式工作块：日期→公司→公司元数据→职位→部门→职责。

        EN: Liepin / candidate-report style work blocks: date → company → company metadata → position → department → duties.

        JA: Liepin・候補者レポート形式の職歴ブロック：日付 → 会社 → 会社のメタデータ → 職位 → 部署 → 職務。
        """
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
            # 日期后的首个非元数据行是公司名；职位在“职位类别”之前的末个标题行。
            # 这类模板的日期下一行就是公司名；“公司性质/规模”后面的“未填写”不能当公司名。
            # EN: The first non-metadata line after the date is the company name; the position is the last heading line before "职位类别" (job category).
            #     In this kind of template the line right after the date is the company name; "未填写" (not filled in) after "company type/size" must not be taken as the company name.
            # JA: 日付の後の最初の非メタデータ行が会社名で、職位は「职位类别」（職種）の前にある最後の見出し行。
            #     この種のテンプレートでは日付の次の行が会社名であり、「会社の性質／規模」の後の「未填写」（未記入）を会社名にしてはならない。
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
            # 无“职位类别”字段的重复块，从公司元数据之后找明确的职位行。
            # EN: For repeated blocks without a "职位类别" (job category) field, look for an explicit position line after the company metadata.
            # JA: 「职位类别」（職種）フィールドのない繰り返しブロックでは、会社のメタデータの後から明確な職位行を探す。
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
        # 同一经历常在 HTML 中重复一次，保留职责更完整的一条。
        # EN: The same experience is often repeated once in the HTML; keep the one with the more complete duties.
        # JA: 同じ経歴が HTML 内で 1 回重複していることが多く、職務がより完全な方を残す。
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
        """单行经历模板：日期 职位 公司：项目/职责。

        EN: Single-line experience template: date position company: project/duties.

        JA: 1 行形式の経歴テンプレート：日付 職位 会社：プロジェクト／職務。
        """
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
        """中文表单式经历：日期行后接公司，块内用工作部门/工作职位/汇报对象标注。

        EN: Chinese form-style experience: the date line is followed by the company, and the block is labelled with department/position/reports-to.

        JA: 中国語のフォーム形式の経歴：日付行の後に会社が続き、ブロック内は部署／職位／報告先でラベル付けされる。
        """
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
        """按文档视觉顺序解析“日期→职位→公司”及“日期→公司”模板。

        EN: Parse "date → position → company" and "date → company" templates in the document's visual order.

        JA: 文書の見た目の順序に従って「日付 → 職位 → 会社」と「日付 → 会社」のテンプレートを解析する。
        """
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
        rows = []
        def norm_date(value: str, current: bool = False) -> str:
            value = re.sub(r"\s+", "", value or "")
            if value in {"至今", "现在", "目前", "現在", "現在まで"}: return ""
            value = value.replace(".", "年").replace("/", "年").replace("-", "年")
            return re.sub(r"^(\d{4})年(\d{1,2})月?$", r"\1年\2月01日", value)
        def is_company(value: str) -> bool:
            """识别公司/机构名；日文履历常用“○○銀行/監査法人”而没有株式会社后缀。

            EN: Recognise company/institution names; Japanese histories often use "○○銀行/監査法人" without the 株式会社 suffix.

            JA: 会社・機関名を識別する。日本の経歴では「○○銀行／監査法人」のように株式会社の接尾辞がないことが多い。
            """
            value = re.sub(r"\s+", " ", str(value or "")).strip(" ：:|-—–~～")
            if not value or len(value) > 140:
                return False
            first = value.split(" ", 1)[0]
            return bool(re.search(company_suffix, value, re.I) or re.search(r"(?:銀行|銀行本店|監査法人|Consulting|Corporation|Company)", value, re.I))
        # “职位 | 公司 | 起止年月”是中文化的日文履历书常见格式。
        # EN: "Position | company | start-end date" is a common format of Japanese rirekisho translated into Chinese.
        # JA: 「職位 | 会社 | 期間」は、中国語化された日本の履歴書でよく見られる形式。
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
                # 日文简历常写成“○○銀行内部監査部 内部監査”，首个空格前是机构名，后面是职位/部门。
                # EN: Japanese résumés often write "○○銀行内部監査部 内部監査": the part before the first space is the institution, the rest is position/department.
                # JA: 日本の履歴書は「○○銀行内部監査部 内部監査」のように書くことが多く、最初の空白の前が機関名、後ろが職位・部署。
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
                # 同一行公司后的职位或下一行的职位
                # EN: Position after the company on the same line, or position on the next line
                # JA: 同じ行の会社の後ろにある職位、または次の行の職位
                tail = rest[len(company):].strip(" ：:|-—–~～")
                if tail and not role and not re.search(r"公司性质|公司规模|公司行业|国有企业|人\s*[|｜]|芜湖|贵阳", tail): role = tail
                elif following and len(following[0]) <= 50 and not re.search(r"^(?:工作|职责|项目|事業|売上|従業員|所在|薪酬|汇报|下属|所属|公司)", following[0], re.I) and not is_company(following[0]):
                    role, consumed = following[0].strip(" ：:"), 1
            elif rest and not re.search(r"^(?:工作|职责|项目|事業|売上|従業員|所在|薪酬|汇报|下属|所属|公司)", rest, re.I):
                role = rest
                if following and is_company(following[0]):
                    company, consumed = extract_company_name(following[0]), 1
            else:
                # 另一种常见视觉顺序是“公司名\n日期\n职位”。
                # EN: Another common visual order is "company name\ndate\nposition".
                # JA: もう 1 つよくある見た目の順序は「会社名\n日付\n職位」。
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
            # 同一行日期后常把职责正文紧跟在职位后；职位只保留第一段，避免把整段职责塞进 position。
            # EN: On a line with a date, the duties text often follows the position directly; keep only the first segment as the position so the whole duties text is not stuffed into position.
            # JA: 日付のある行では職務本文が職位の直後に続くことが多い。職位は最初の部分だけを残し、職務全体を position に詰め込まない。
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
            # 日文职务经历常在同一家公司下继续列出多个“起止年月→部门/职责”子段。
            # EN: Japanese work histories often list several "start-end → department/duties" sub-sections under the same company.
            # JA: 日本の職務経歴では、同じ会社の下に「期間 → 部署／職務」の小区分が複数続くことが多い。
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
        # 视觉模板通常会重复渲染同一段；不同职位不能被误合并。
        # EN: Visual templates often render the same section twice; different positions must not be merged by mistake.
        # JA: 見た目重視のテンプレートは同じ段落を重複して描画することが多いが、異なる職位を誤って統合してはならない。
        unique, seen = [], set()
        for row in rows:
            key = (row["company_name"], row.get("position", ""), row["position_start"], row["position_resigned"])
            if key not in seen: seen.add(key); unique.append(row)
        return unique
    text_works_explicit_v3_rows = text_work_items_explicit_v3()
    def text_work_items_dom_v4() -> list[dict[str, Any]]:
        """解析招聘网站 DOM 常见的“日期→职位→公司→工作描述”顺序。

        Mammoth/Word COM 会把日期后的“至今”拆成下一行，通用规则因此只
        留下最后一段工作。本规则先恢复日期行，再以公司行作为字段边界。

        EN: Parse the common job-site DOM order "date → position → company → job description".

        Mammoth/Word COM splits "至今" (present) after the date onto the next line, so the generic rule
        keeps only the last work section. This rule first restores the date line, then uses the company line as the field boundary.

        JA: 求人サイトの DOM によくある「日付 → 職位 → 会社 → 職務説明」の順序を解析する。

        Mammoth/Word COM は日付の後の「至今」（現在）を次の行に分けてしまうため、汎用ルールでは
        最後の職歴しか残らない。このルールはまず日付行を復元し、会社行をフィールドの境界として使う。
        """
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
            # 公司行可能带“150-500人|外资”等元数据，只保留机构名称。
            # EN: The company line may carry metadata like "150-500人|外资" (150-500 people | foreign-owned); keep only the institution name.
            # JA: 会社の行には「150-500人|外资」（150〜500 人｜外資）などのメタデータが付くことがあり、機関名だけを残す。
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
    def text_work_items_narrative_v5() -> list[dict[str, Any]]:
        """解析企业申请表中“工作/实习经历”叙述式段落。

        EN: Parse narrative "work/internship experience" paragraphs in company application forms.

        JA: 企業の応募フォームにある叙述式の「職歴／インターン経験」段落を解析する。
        """
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
            # “YYYY年M月进入公司……，YYYY年M月正式签订劳动合同”没有范围符号，
            # 将后一日期视为该实习/试用段的结束日期。
            # EN: "Joined the company in month M of year YYYY ..., formally signed the labour contract in month M of year YYYY" has no range symbol;
            #     treat the later date as the end date of that internship/probation period.
            # JA: 「YYYY年M月に入社……、YYYY年M月に正式に労働契約を締結」には範囲記号がないため、
            #     後の日付をそのインターン・試用期間の終了日とみなす。
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
    if len(text_works_narrative_v5_rows) >= len(text_works_labelled):
        text_works_labelled = text_works_narrative_v5_rows
    if len(text_works_explicit_v3_rows) >= 1:
        text_works_labelled = text_works_explicit_v3_rows
    if len(text_works_narrative_v5_rows) > len(text_works_labelled):
        text_works_labelled = text_works_narrative_v5_rows
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
    # 明确的“日期→公司/职位”解析已经按工作区块边界截断，优先级高于
    # 通用 v2 扫描；后者容易把教育、语言和自我评价尾部误识别成工作。
    # EN: Explicit "date → company/position" parsing is already truncated at work-block boundaries and takes priority over
    #     the generic v2 scan; the latter tends to misidentify the tail of education, language and self-assessment as work.
    # JA: 明示的な「日付 → 会社／職位」の解析はすでに職歴ブロックの境界で切り詰められており、汎用の v2 スキャンより優先する。
    #     後者は学歴・語学・自己評価の末尾を職歴と誤認しやすい。
    if text_works_explicit_v3_rows:
        text_works_labelled = text_works_explicit_v3_rows
    # 与 HTML DOM 主解析器保持同一套“日期→公司→职位/部门→职责”规则。
    # 旧的 extend_schema 备用扫描在 51job 模板中可能把职责首句当作公司名；
    # 只要 DOM 主规则得到可信公司和职位，就优先使用它，避免最终 JSON
    # 又被旧 fallback 覆盖。
    # EN: Keep the same "date → company → position/department → duties" rules as the main HTML DOM parser.
    #     The old extend_schema fallback scan may take the first sentence of duties as the company name in 51job templates;
    #     whenever the main DOM rules yield a credible company and position, use them first so the final JSON
    #     is not overwritten by the old fallback again.
    # JA: HTML DOM のメインパーサーと同じ「日付 → 会社 → 職位／部署 → 職務」ルールを保つ。
    #     旧来の extend_schema の代替スキャンは 51job テンプレートで職務の最初の文を会社名と誤認することがある。
    #     DOM のメインルールで信頼できる会社と職位が得られたらそれを優先し、最終 JSON が旧 fallback に再び上書きされないようにする。
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
    # DOM 版可能只有一段工作，但比叙述扫描产生的“，公司/担任…”伪行更可靠；
    # 当当前候选行全部校验失败时，保留至少一条有效 DOM 工作经历。
    # EN: The DOM version may have only one work entry, but it is more reliable than the ", company / served as ..." pseudo-lines from the narrative scan;
    #     when all current candidate lines fail validation, keep at least one valid DOM work experience.
    # JA: DOM 版には職歴が 1 件しかないこともあるが、叙述スキャンが生む「，会社／〜を担当」といった疑似行より信頼できる。
    #     現在の候補行がすべて検証に失敗した場合は、有効な DOM の職歴を少なくとも 1 件残す。
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
    # 标签式候选人报告的公司/职位边界比通用日期扫描更可靠，即使数量相同也优先采用。
    # EN: Company/position boundaries in labelled candidate reports are more reliable than the generic date scan, so prefer them even when the counts are equal.
    # JA: ラベル形式の候補者レポートの会社・職位境界は汎用の日付スキャンより信頼できるため、件数が同じでも優先して採用する。
    if len(text_works_labelled) >= 2:
        fallback_works = text_works_labelled
    def text_education_items() -> list[dict[str, Any]]:
        """教育对象专用规则：日期行、表单标签、日文最终学历分别识别。

        EN: Rules specific to education objects: date lines, form labels and Japanese "最終学歴" are recognised separately.

        JA: 学歴オブジェクト専用のルール：日付行、フォームのラベル、日本の「最終学歴」をそれぞれ識別する。
        """
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
                # “西安理工  工业工程  本科”这类学校名没有“大学/学院”后缀。
                # EN: School names like "西安理工  工业工程  本科" have no "大学/学院" (university/college) suffix.
                # JA: 「西安理工  工业工程  本科」のような学校名には「大学／学院」の接尾辞がない。
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
                    "school_name": school,
                    "school_major_name": rest,
                    "school_degree_type": degree,
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
            # 中文人才库简历常把教育行写成“学历：学校/专业：本科”。
            # EN: Chinese talent-pool résumés often write education lines as "学历：school/major：本科".
            # JA: 中国の人材データベースの履歴書では学歴行が「学历：学校／専攻：本科」と書かれることが多い。
            m = re.search(r"(?:学历|教育程度|毕业院校)\s*[:：]?\s*(.+)", line, re.I)
            if m and (re.search(school_re, m.group(1), re.I) or re.search(degree_re, m.group(1), re.I)):
                append_row(line, "", "", m.group(1))

        # 旧 Word 表格转换后，学校、日期、专业、学位各自成为一行。
        # EN: After converting old Word tables, school, date, major and degree each become a separate line.
        # JA: 旧 Word の表を変換すると、学校・日付・専攻・学位がそれぞれ別の行になる。
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

        # 日文履历书的“最終学歴”通常没有日期范围，下一行才是学校和专业。
        # EN: The "最終学歴" (highest education) of Japanese rirekisho usually has no date range; the school and major are on the next line.
        # JA: 日本の履歴書の「最終学歴」には通常日付範囲がなく、次の行に学校と専攻がある。
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
        # 去除重复行，避免“教育背景”和“最終学歴”同时出现时重复入库。
        # EN: Remove duplicate lines so entries are not stored twice when both "教育背景" and "最終学歴" appear.
        # JA: 重複行を除去し、「教育背景」と「最終学歴」が両方ある場合に二重登録しないようにする。
        unique, seen = [], set()
        for row in rows:
            key = (row.get("school_name", ""), row.get("school_start_ym", ""), row.get("school_end_ym", ""), row.get("school_major_name", ""))
            if key not in seen:
                seen.add(key)
                unique.append(row)
        return [r for r in unique if r.get("school_name")]

    def text_certificate_items() -> list[dict[str, Any]]:
        """证书/资格对象专用规则，保留证书名称、类型和取得时间。

        EN: Rules specific to certificate/qualification objects, keeping the certificate name, type and date obtained.

        JA: 資格オブジェクト専用のルール。資格名・種類・取得日を保持する。
        """
        rows = []
        normalized = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", clean_text.replace("\r", ""))
        for line in normalized.splitlines():
            value = re.sub(r"^\s*[■□•·➢➤➣\-*\d.)]+\s*", "", line).strip(" |│")
            if not value or re.search(r"证书|资格|資格|CET|TOEIC|ACCA|驾照|驾驶证|運転免許|执业药师|簿记|語学能力|能力考试", value, re.I) is None:
                continue
            if re.search(r"^(证书|资格证书|資格|Certificates?)\s*[:：]?\s*$", value, re.I):
                continue
            # “证书（包括IT技能、语言能力、证书、成绩、培训经历）”是栏目说明，不是证书。
            # EN: "证书（包括IT技能、语言能力、证书、成绩、培训经历）" is a section description, not a certificate.
            # JA: 「证书（包括IT技能、语言能力、证书、成绩、培训经历）」は欄の説明であり、資格ではない。
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
        """语言对象专用规则，只抽取语言名称和等级，不吞入工作描述。

        EN: Rules specific to language objects: extract only the language name and level, without swallowing job descriptions.

        JA: 語学オブジェクト専用のルール。言語名とレベルだけを抽出し、職務説明を取り込まない。
        """
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

    def text_project_items() -> list[dict[str, Any]]:
        """项目对象专用规则：项目日期独立存储，正文不重复日期。

        EN: Rules specific to project objects: project dates are stored separately and not repeated in the body.

        JA: プロジェクトオブジェクト専用のルール：プロジェクトの日付は個別に保存し、本文で重複させない。
        """
        normalized = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", clean_text.replace("\r", ""))
        lines = [x.strip(" |│") for x in normalized.splitlines() if x.strip()]
        start_idx = next((i for i, x in enumerate(lines) if re.search(r"项目经历|项目经验|项目案例|Project Experience|プロジェクト", x, re.I)), None)
        if start_idx is None:
            return []
        stop_re = re.compile(r"教育经历|教育背景|教育程度|学历|工作经历|工作经验|语言能力|外语水平|技能|证书|资格|培训|自我评价|自己PR|附加信息", re.I)
        date_re = re.compile(r"(?P<start>(?:19|20)\d{2}[./-]\s*\d{1,2})\s*[-—–~～至到]+\s*(?P<end>(?:19|20)\d{2}[./-]\s*\d{1,2}|至今|现在|目前)")
        events = []
        for idx in range(start_idx + 1, len(lines)):
            if stop_re.search(lines[idx]) and not date_re.search(lines[idx]):
                break
            m = date_re.search(lines[idx])
            if m:
                title = lines[idx][m.end():].strip(" ：:|-—–~～")
                if not title and idx + 1 < len(lines):
                    title = lines[idx + 1].strip()
                events.append((idx, m, title))
        rows = []
        for n, (idx, m, title) in enumerate(events):
            end_idx = events[n + 1][0] if n + 1 < len(events) else len(lines)
            block = lines[idx + 1:end_idx]
            if title and block and block[0] == title:
                block = block[1:]
            role = next((re.sub(r"^项目职务\s*[:：]?\s*", "", x).strip() for x in block if re.search(r"项目职务|项目角色|role", x, re.I)), "")
            company = next((re.sub(r"^(?:所在公司|所属公司|客户)\s*[:：]?\s*", "", x).strip() for x in block if re.search(r"所在公司|所属公司|客户", x, re.I)), "")
            body = "\n".join(x for x in block if not re.search(r"项目职务|项目角色|所在公司|所属公司|客户", x, re.I)).strip()
            rows.append({"sequence_no": n + 1, "project_name": title[:160], "company_or_client": company, "role_name": role, "start_ym": re.sub(r"\s+", "", m.group("start")), "end_ym": "" if m.group("end") in {"至今", "现在", "目前"} else re.sub(r"\s+", "", m.group("end")), "description": strip_project_leading_date(body), "raw_text": body})
        return [r for r in rows if r.get("project_name")]

    def text_training_items() -> list[dict[str, Any]]:
        """按“培训经历”栏目逐行解析培训记录。

        旧的通用解析器会把整段表格压成一条记录，并把第一行日期误当作
        2010-01/2011-01。培训记录本身通常是“日期 + 培训名称 + 机构”三列，
        因此这里只在培训栏目内按行切分，日期、名称、机构分别保存。

        EN: Parse training records line by line within the "培训经历" (training history) section.

        The old generic parser compressed the whole table into one record and mistook the date on the first line for
        2010-01/2011-01. A training record is usually three columns, "date + training name + provider",
        so here we split by line only inside the training section and store date, name and provider separately.

        JA: 「培训经历」（研修歴）欄の中で研修記録を 1 行ずつ解析する。

        旧来の汎用パーサーは表全体を 1 件のレコードに押し込み、1 行目の日付を
        2010-01/2011-01 と誤認していた。研修記録は通常「日付 + 研修名 + 機関」の 3 列なので、
        ここでは研修欄の中だけ行単位で分け、日付・名称・機関を個別に保存する。
        """
        normalized = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", clean_text.replace("\r", ""))
        lines = [re.sub(r"\s+", " ", x).strip() for x in normalized.splitlines()]
        lines = [x for x in lines if x]
        heading = re.compile(r"^(?:培训经历|培训经验|培训背景|培训及证书|培训经历及证书|Training(?:\s+Experience)?)$", re.I)
        start_idx = next((i for i, line in enumerate(lines) if heading.search(line)), None)
        if start_idx is None:
            return []
        stop_heading = re.compile(r"^(?:证书|资格证书|语言能力|外语水平|语言|技能|项目经历|项目经验|工作经历|教育经历|教育背景|自我评价|个人优势|附加信息)", re.I)
        section = []
        for line in lines[start_idx + 1:]:
            if stop_heading.search(line):
                break
            section.append(line)
        # 允许日期后带“至今/—YYYY-MM”，同时避免把 2010-2011 拆成月份 20。
        # EN: Allow "至今/—YYYY-MM" after a date, while avoiding splitting 2010-2011 into month 20.
        # JA: 日付の後に「至今／—YYYY-MM」が続くことを許容しつつ、2010-2011 を月 20 と誤って分割しないようにする。
        date_token = r"(?:19|20)\d{2}(?:[./-]\d{1,2}(?!\d))?"
        date_re = re.compile(
            rf"^[➢➤•·\-*]?\s*(?P<start>{date_token})\s*"
            rf"(?:(?:[-—–~～至到一]+)\s*(?P<end>{date_token}|至今|现在|目前|現在))?\s+(?P<rest>.+)$",
            re.I,
        )
        org_re = re.compile(
            r"(?P<title>.+?)\s+(?P<org>(?:deep\s*thinking机构|宝武人才开发院|西安政治学院|南京政治学院|海军\s*\d+部队|[^\s]+(?:人才开发院|政治学院|学院|大学院|大学|机构|部队)))\s*$",
            re.I,
        )
        rows: list[dict[str, Any]] = []
        seen: set[tuple[str, str, str, str]] = set()

        def normal_date(value: str) -> str:
            value = re.sub(r"\s+", "", value or "")
            m = re.match(r"^((?:19|20)\d{2})[./-](\d{1,2})$", value)
            return f"{m.group(1)}-{int(m.group(2)):02d}" if m else value

        for line in section:
            match = date_re.match(line)
            if not match:
                continue
            start = normal_date(match.group("start"))
            end_value = match.group("end") or ""
            end = "" if end_value in {"至今", "现在", "目前", "現在"} else normal_date(end_value)
            rest = match.group("rest").strip(" ：:|│")
            org_match = org_re.search(rest)
            if org_match:
                training_name = org_match.group("title").strip(" ：:|│")
                organization = org_match.group("org").strip(" ：:|│")
            else:
                # 未知机构时用多空格列间距切开；无法确定机构就保留名称，
                # 绝不把日期和整段后续正文写进 organization_name。
                # EN: When the institution is unknown, split on multi-space column gaps; if the institution cannot be determined, keep the name,
                #     and never write dates and whole following paragraphs into organization_name.
                # JA: 機関が不明な場合は複数の空白による列の間隔で分割する。機関が確定できなければ名称をそのまま残し、
                #     日付や後続の本文全体を organization_name に書き込むことは決してしない。
                columns = [x.strip() for x in re.split(r"\s{2,}", rest) if x.strip()]
                training_name = columns[0] if columns else rest
                organization = columns[-1] if len(columns) > 1 else ""
            if not training_name or len(training_name) > 180:
                continue
            key = (training_name, organization, start, end)
            if key in seen:
                continue
            seen.add(key)
            rows.append({
                "sequence_no": len(rows) + 1,
                "organization_name": organization,
                "training_name": training_name,
                "start_ym": start,
                "end_ym": end,
                "certificate_name": "",
                "description": "",
                "raw_text": line,
            })
        return rows

    def text_education_table_rows() -> list[dict[str, Any]]:
        """表格/HTML 顺序化教育行：学校、专业/学位、起止日期分别或同一行。

        EN: Table/HTML sequential education lines: school, major/degree and start/end dates on separate lines or on the same line.

        JA: 表／HTML で順に並ぶ学歴行：学校・専攻／学位・期間が別々の行、または同じ行にある。
        """
        lines = [re.sub(r"\s+", " ", x).strip(" |│") for x in clean_text.replace("\r", "").splitlines() if x.strip(" |│")]
        degree_re = r"本科|大专|专科|学士|硕士|博士|修士|研究生|MBA|EMBA"
        school_re = r"大学院|大学|学院|高等学校|中学|高中|学校|Institute|University|College"
        date_re = re.compile(r"(?P<start>(?:19|20)\d{2})[./-](?P<sm>\d{1,2})\s*[-—–~～至到]+\s*(?P<end>(?:19|20)\d{2})[./-](?P<em>\d{1,2})")
        rows = []

        # 猎聘等模板把一条教育经历拆成“学校 / 日期 / 专业 / 学历 / 是否统招”五行。
        # 不能只用日期行的前两行拼接：第二条记录前面常有上一条的“是否统招”，
        # 会导致学校名被拼掉，从而漏掉中间学历。先在明确的教育区块内逐块读取。
        # “教育程度：本科”是个人信息字段，不是教育经历区块标题；优先匹配真正的经历标题。
        # EN: Templates such as Liepin split one education entry into five lines: "school / date / major / degree / unified enrolment or not".
        #     Joining only the two lines before the date line is not enough: the second record is often preceded by the previous record's "unified enrolment or not",
        #     which drops the school name and so misses the middle degree. Read block by block inside the explicit education section first.
        #     "教育程度：本科" is a personal-info field, not an education-history section heading; match the real history heading first.
        # JA: Liepin などのテンプレートは 1 件の学歴を「学校 / 日付 / 専攻 / 学歴 / 統一入試か否か」の 5 行に分ける。
        #     日付行の前 2 行をつなげるだけでは不十分で、2 件目のレコードの前には前のレコードの「統一入試か否か」があることが多く、
        #     学校名が失われて途中の学歴を取りこぼす。まず明確な学歴ブロック内でブロックごとに読む。
        #     「教育程度：本科」は個人情報のフィールドであり学歴欄の見出しではないため、本当の経歴見出しを優先してマッチさせる。
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
                    "school_major_name": major,
                    "school_degree_type": degree,
                    "school_education_type": etype,
                    "school_start_ym": start,
                    "school_end_ym": end,
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
            # 同一行的“学校 专业/硕士”不能把整段塞进 school_name。
            # EN: "School major/master's" on the same line must not be stuffed entirely into school_name.
            # JA: 同じ行の「学校 専攻／修士」を丸ごと school_name に詰め込んではならない。
            if school and (degree or rest):
                rows.append(education_item({"school_name": school, "school_major_name": rest, "school_degree_type": degree, "school_start_ym": start, "school_end_ym": end, "raw_text": raw}))
        for i, line in enumerate(lines):
            m = date_re.search(line)
            if not m: continue
            start, end = f"{m.group('start')}.{int(m.group('sm')):02d}", f"{m.group('end')}.{int(m.group('em')):02d}"
            body = (line[:m.start()] + line[m.end():]).strip()
            if body and re.search(school_re, body, re.I):
                make(body, start, end, line); continue
            # 三行表格：学校 / 专业与学位 / 日期。
            # EN: Three-line table: school / major and degree / date.
            # JA: 3 行の表：学校 / 専攻と学位 / 日付。
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
    fallback_edus = [education_item(item) for item in (fallback.get("education_experiences") or [])]
    fallback_edus = [item for item in fallback_edus if item.get("school_name") and re.search(r"大学|学院|学校|大学院|中学|高中|高等学校|University|College|Institute", item.get("school_name", ""), re.I)]
    text_edus = text_education_items()
    text_edus_table = text_education_table_rows()
    if len(text_edus_table) >= 1:
        text_edus = text_edus_table
    if len(text_edus_table) >= 1:
        fallback_edus = text_edus_table
    elif len(text_edus) > len(fallback_edus):
        fallback_edus = text_edus
    text_projects = text_project_items()
    if text_projects and len(data.get("project_experiences") or []) == 0:
        data["project_experiences"] = text_projects
    text_trainings = text_training_items()
    if text_trainings:
        trainings = text_trainings
        data["training_experiences"] = text_trainings
    text_certs = text_certificate_items()
    text_langs = text_language_items()
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
            key = (name, str(row.get("certificate_time") or ""))
            if key not in seen:
                seen.add(key); cleaned.append(row)
        return cleaned

    def split_grouped_certificate_text(value: str) -> list[str]:
        """把同一行的技能/证书清单按顶层标点拆开，忽略括号内的逗号。

        EN: Split same-line skill/certificate lists on top-level punctuation, ignoring commas inside brackets.

        JA: 同じ行のスキル・資格の一覧をトップレベルの句読点で分割し、括弧内のカンマは無視する。
        """
        text = re.sub(r"\s+", " ", str(value or "")).strip()
        if not text:
            return []
        parts, buf, depth = [], [], 0
        for ch in text:
            if ch in "（(【[":
                depth += 1
            elif ch in "）)】]" and depth:
                depth -= 1
            if ch in "，,、；;" and depth == 0:
                part = "".join(buf).strip(" ：:，,、；;|│")
                if part:
                    parts.append(part)
                buf = []
            else:
                buf.append(ch)
        part = "".join(buf).strip(" ：:，,、；;|│")
        if part:
            parts.append(part)
        return parts

    def split_certificate_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """拆分“技能/证书”混合行，并过滤栏目说明、占位标题。

        EN: Split mixed "skills/certificates" lines and filter out section descriptions and placeholder headings.

        JA: 「スキル／資格」が混在する行を分割し、欄の説明やプレースホルダーの見出しを除外する。
        """
        expanded = []
        generic = re.compile(r"^(?:证书|资格证书|资格|技能|技能特长|Certificates?|Professional|Skills|证书技能)(?:\s*[（(].*[）)])?$", re.I)
        skill_re = re.compile(r"熟练|精通|软件|Office|驾照|驾驶证|能力|沟通|团队|数据库|编程|语言|计算机", re.I)
        for item in rows or []:
            row = dict(item)
            name = re.sub(r"\s+", " ", str(row.get("certificate_name") or "")).strip(" ：:，,|│")
            if not name or generic.match(name) or re.search(r"包括.*(?:证书|培训|技能)", name, re.I):
                continue
            chunks = split_grouped_certificate_text(name)
            # 无顶层分隔符的单项仍保留。
            # EN: Single items without a top-level separator are still kept.
            # JA: トップレベルの区切りがない単一項目も残す。
            for chunk in chunks or [name]:
                if generic.match(chunk) or len(chunk) < 2:
                    continue
                new_row = dict(row)
                new_row["certificate_name"] = chunk
                if not new_row.get("certificate_type") or str(new_row.get("certificate_type")) in {"证书", "资格"}:
                    new_row["certificate_type"] = "技能" if skill_re.search(chunk) and not re.search(r"证书|驾照|驾驶证|CET|TOEIC|簿记|资格", chunk, re.I) else "证书"
                new_row["raw_text"] = row.get("raw_text") or name
                expanded.append(new_row)
        return clean_certificate_rows(expanded)

    def normalize_degree_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """补齐可推断的学历等级，并把“专业·硕士/本科”拆干净。

        EN: Fill in inferable degree ranks and split "major·master's/bachelor's" cleanly.

        JA: 推定できる学歴ランクを補い、「専攻・修士／学士」をきれいに分割する。
        """
        degree_rank = {"高中": "3", "中专": "3", "大专": "3", "专科": "3", "本科": "4", "学士": "4", "硕士": "5", "修士": "5", "研究生": "5", "MBA": "5", "EMBA": "5", "博士": "6", "博士后": "6"}
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
    data["certificate_info"] = split_certificate_rows(data.get("certificate_info") or [])
    if text_certs:
        data["certificate_info"] = split_certificate_rows((data.get("certificate_info") or []) + text_certs)
    if not data.get("language_info") and text_langs:
        data["language_info"] = text_langs
    for resume in resumes:
        if resume.get("work_experiences"):
            normalized_works = [
                cleaned for cleaned in (clean_work_item(item) for item in resume.get("work_experiences", []))
                if valid_work_item(cleaned)
            ]
            # 同一公司+起止时间可能被模板重复输出，合并为一段工作。
            # EN: The same company + start/end dates may be output twice by the template; merge them into one work entry.
            # JA: 同じ会社 + 期間がテンプレートにより重複出力されることがあり、1 件の職歴に統合する。
            merged_works = []
            seen_work = {}
            for item in normalized_works:
                key = (item.get("company_name", ""), item.get("position", ""), item.get("position_start", ""), item.get("position_resigned", ""))
                if key in seen_work:
                    old = seen_work[key]
                    if len(str(item.get("position_responsibilities") or "")) > len(str(old.get("position_responsibilities") or "")):
                        old["position_responsibilities"] = item.get("position_responsibilities") or old.get("position_responsibilities")
                    if (not old.get("position") or old.get("position") in {">>", "担当"}) and item.get("position"):
                        old["position"] = item.get("position")
                else:
                    seen_work[key] = item
                    merged_works.append(item)
            resume["work_experiences"] = merged_works
        # 明确标签式工作块（时间/公司/职位）优先于通用 DOM 推断。
        # 两者数量相同也必须替换，否则通用解析可能把“公司：”和前一段职责带入公司字段。
        # EN: Explicitly labelled work blocks (time/company/position) take priority over generic DOM inference.
        #     They must replace it even when the counts are equal, otherwise generic parsing may carry "公司：" and the previous duties into the company field.
        # JA: 明示的なラベル付きの職歴ブロック（期間／会社／職位）は汎用的な DOM 推定より優先する。
        #     件数が同じでも置き換える必要があり、さもないと汎用解析が「公司：」や前の職務を会社フィールドに持ち込むことがある。
        preferred_works = text_works_labelled if len(text_works_labelled) >= 1 else fallback_works
        if preferred_works and (len(text_works_labelled) >= 1 or not resume.get("work_experiences") or len(resume.get("work_experiences") or []) < len(preferred_works)):
            resume["work_experiences"] = [clean_work_item(item) for item in preferred_works if valid_work_item(clean_work_item(item))]
        education_bad = any(
            (not str(item.get("school_name") or "").strip())
            or re.search(r"GPA|荣誉奖项|相关课程|生活委员|校内职务|学生会", str(item.get("school_name") or ""), re.I)
            or len(str(item.get("school_major_name") or "")) > 40
            or re.search(r"毕业日期|语言能力|外语水平|工作经历", str(item.get("school_major_name") or ""), re.I)
            for item in (resume.get("education_list") or [])
        )
        normalized_edus = [education_item(item) for item in (resume.get("education_list") or [])]
        normalized_edus = [item for item in normalized_edus if item.get("school_name") and re.search(r"大学|学院|学校|大学院|中学|高中|高等学校|University|College|Institute", item.get("school_name", ""), re.I) and not re.search(r"生活委员|团支部|教务处|学生会|GPA", item.get("school_name", ""), re.I)]
        def normalize_education_annotation(item: dict[str, Any]) -> dict[str, Any]:
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
        normalized_edus = [normalize_education_annotation(item) for item in normalized_edus]
        fallback_edus = [normalize_education_annotation(item) for item in fallback_edus]
        # 表格简历把“学历/所修专业”拆到基本信息区，回填到唯一教育对象。
        # EN: Table résumés put "degree / major studied" in the basic-info area; back-fill them into the single education object.
        # JA: 表形式の履歴書は「学歴／専攻」を基本情報欄に置いているため、唯一の学歴オブジェクトに補完する。
        if len(normalized_edus) == 1:
            degree_match = re.search(r"学\s*历\s*[:：|│]?\s*(本科|大专|专科|学士|硕士|博士|MBA|EMBA)", clean_text, re.I)
            major_match = re.search(r"(?:所修专业|专\s*业)\s*[:：|│]?\s*([^\n|│]{2,40})", clean_text, re.I)
            if degree_match and not normalized_edus[0].get("school_degree_type"):
                normalized_edus[0]["school_degree_type"] = degree_match.group(1)
            if major_match and not normalized_edus[0].get("school_major_name"):
                value = major_match.group(1).strip()
                if not re.search(r"毕业日期|语言能力|工作经历|项目经历", value, re.I):
                    normalized_edus[0]["school_major_name"] = value
        if fallback_edus and (not normalized_edus or education_bad or len(fallback_edus) > len(normalized_edus)):
            resume["education_list"] = fallback_edus
        else:
            resume["education_list"] = normalized_edus
        resume["education_list"] = normalize_degree_rows(resume.get("education_list") or [])
        resume["certificate_info"] = split_certificate_rows((resume.get("certificate_info") or []) + text_certs)
        if not resume.get("language_info") and text_langs:
            resume["language_info"] = text_langs
        if not resume.get("project_experiences") and data.get("project_experiences"):
            resume["project_experiences"] = list(data.get("project_experiences") or [])
        # 训练经历同项目经历一样只属于 resume 明细；旧解析器若把它放在
        # structured_data 顶层，这里迁移到中文（或唯一）履历块。
        # EN: Like project history, training history belongs only to the resume details; if an old parser put it at the
        #     top level of structured_data, migrate it here into the Chinese (or only) résumé block.
        # JA: 研修歴はプロジェクト経験と同様に resume の明細にのみ属する。旧パーサーが
        #     structured_data のトップレベルに置いていた場合は、ここで中国語（または唯一）の履歴書ブロックに移す。
        if not resume.get("training_experiences") and data.get("training_experiences"):
            resume["training_experiences"] = list(data.get("training_experiences") or [])
        if not resume.get("training_experiences") and trainings:
            resume["training_experiences"] = list(trainings)
        resume.setdefault("project_experiences", [])
        resume.setdefault("training_experiences", [])
        resume.setdefault("communication_assessment", [])
    data["resumes"] = resumes
    # 只在候选人 resume 对象中保存项目/培训明细，顶层仅保留摘要字段。
    # EN: Project/training details are stored only in the candidate's resume objects; the top level keeps only summary fields.
    # JA: プロジェクト・研修の明細は候補者の resume オブジェクトにのみ保存し、トップレベルには概要フィールドだけを残す。
    data.pop("project_experiences", None)
    data.pop("training_experiences", None)
    # 多语言文档按约定优先中文块；中文块为空时，使用有姓名/联系方式的日文或英文块作为基础摘要。
    # EN: By convention multilingual documents prefer the Chinese block; when it is empty, use a Japanese or English block that has a name/contact as the base summary.
    # JA: 多言語文書は規約により中国語ブロックを優先する。中国語ブロックが空なら、氏名・連絡先のある日本語または英語ブロックを基本の概要として使う。
    primary_resume = next((r for r in resumes if r.get("resume_languge") == "zh" and (r.get("base_info") or {}).get("full_name")), None)
    primary_resume = primary_resume or next((r for r in resumes if (r.get("base_info") or {}).get("full_name") or (r.get("base_info") or {}).get("phone") or (r.get("base_info") or {}).get("email")), None)
    if primary_resume:
        data["base_info"] = dict(primary_resume.get("base_info") or {})
    if not (data.get("base_info") or {}).get("full_name"):
        html_name = Path(str(source_path)).stem
        html_name = re.sub(r"__[^_]+$", "", html_name)
        candidate_name = re.split(r"[-_（( ]", html_name, maxsplit=1)[0].strip()
        if candidate_name and len(candidate_name) <= 20:
            data.setdefault("base_info", {})["full_name"] = candidate_name
    # 日文履历书常用英文文件名，保留完整的英文姓名（例如 Jianfeng Wu）。
    # EN: Japanese rirekisho often use English file names; keep the full English name (e.g. Jianfeng Wu).
    # JA: 日本の履歴書は英語のファイル名を使うことが多く、英語の氏名全体（例：Jianfeng Wu）を残す。
    filename_stem = Path(str(source_path)).stem
    filename_stem = re.sub(r"[\s_\-]*履歴書.*$", "", filename_stem, flags=re.I).strip(" _-")
    if re.search(r"[A-Za-z].+\s+[A-Za-z]", filename_stem):
        current_name = str((data.get("base_info") or {}).get("full_name") or "").strip()
        if not current_name or current_name.lower() in {"jianfeng", "wu"} or filename_stem.lower().startswith(current_name.lower()):
            data.setdefault("base_info", {})["full_name"] = filename_stem.replace("_", " ").strip()
    base = data.setdefault("base_info", {})
    # 地址字段优先于普通文本中的“项目/小区”词，修正 Word 换行造成的前缀残字。
    # EN: The address field takes priority over "project/estate" words in ordinary text, and fixes leftover prefix characters caused by Word line breaks.
    # JA: 住所フィールドを一般テキスト中の「プロジェクト／団地」という語より優先し、Word の改行で生じた接頭辞の残り文字を修正する。
    address_match = re.search(r"(?:地址|居\s*住\s*(?:地|地址)?|所在\s*地|现\s*居\s*(?:地|地址)?|住所|Address)\s*[:：]?\s*([\u4e00-\u9fffA-Za-z0-9市省区县镇乡路街号室栋\- ,]{2,100})", clean_text, re.I)
    if address_match:
        address_value = address_match.group(1).strip(" ：:，,。")
        address_value = re.sub(r"^上(?=(?:江苏|浙江|山东|安徽|广东|河北|河南|湖北|湖南|江西|福建|四川|陕西|山西|辽宁|吉林|黑龙江|云南|贵州|甘肃|青海|内蒙古|广西|新疆|西藏))", "", address_value)
        if address_value:
            base["address"] = address_value
            base["city"] = address_value
    # 英文简历常用 Mobile/Phone/Email 标签；正文提取器可能只识别了邮箱。
    # EN: English résumés often use Mobile/Phone/Email labels; the body extractor may have recognised only the e-mail.
    # JA: 英語の履歴書は Mobile/Phone/Email のラベルをよく使うが、本文抽出器はメールしか認識していないことがある。
    if not base.get("phone"):
        phone_match = re.search(r"(?:手机|电话|联系电话|Mobile|Phone|Tel(?:ephone)?)\s*[:：]?\s*(\+?\d[\d\s()\-]{6,24})", clean_text, re.I)
        if phone_match:
            base["phone"] = re.sub(r"\D", "", phone_match.group(1))
    if not base.get("email"):
        email_match = re.search(r"[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}", clean_text, re.I)
        if email_match:
            base["email"] = email_match.group(0).strip()
    # 标签式简历的户口/国籍、政治面貌经常位于独立表格单元，不能依赖通用正文解析。
    # EN: In labelled résumés, hukou/nationality and political status are often in separate table cells and cannot rely on generic body parsing.
    # JA: ラベル形式の履歴書では戸籍・国籍や政治的身分が独立した表のセルにあることが多く、汎用の本文解析には頼れない。
    if not base.get("household_registration"):
        household_match = re.search(r"(?:户口(?:/国籍)?|户籍|籍贯|国籍|戸籍|出身地)\s*[:：]?\s*([^\n|｜]{1,40})", clean_text, re.I)
        if household_match:
            value = household_match.group(1).strip(" ：:，,。")
            if value and not re.search(r"政治|婚姻|工作|学历|职位", value):
                base["household_registration"] = value
    if not base.get("political_status"):
        political_match = re.search(r"(?:政治面貌|政治面目|政党|政治立场)\s*[:：]?\s*([^\n|｜]{1,40})", clean_text, re.I)
        if political_match:
            base["political_status"] = political_match.group(1).strip(" ：:，,。")
    # 日文模板有时把“研修等”误识别为城市；优先从居住地/户籍标签回填。
    # EN: Japanese templates sometimes misidentify "研修等" (training etc.) as the city; back-fill from the residence/registration labels first.
    # JA: 日本語テンプレートでは「研修等」が都市と誤認されることがあるため、現住所・本籍のラベルからの補完を優先する。
    city = str(base.get("city") or "").strip()
    if city and re.search(r"研修|课程|等市|工作|职位|大学|会社|統括|会社市|经理|城市|公司名称", city):
        city = ""
    if not city:
        city_match = re.search(r"(?:居\s*住\s*(?:地|地址)?|所在\s*地|现\s*居\s*(?:地|地址)?|住所|戸\s*籍|戶\s*籍)\s*[:：]?\s*([^\n|｜]{2,30})", clean_text, re.I)
        if city_match:
            candidate_city = city_match.group(1).strip(" \t:：，,。")
            if candidate_city and not re.search(r"研修|课程|等市|工作|职位|大学|会社|統括|会社市|经理|城市|公司名称", candidate_city):
                city = candidate_city
    if city:
        base["city"] = city
    # “36岁(1981-4) | 山东 | 汉族”这类页眉日期优先于解析器的默认年龄日期。
    # EN: Header dates like "36岁(1981-4) | 山东 | 汉族" take priority over the parser's default age date.
    # JA: 「36岁(1981-4) | 山东 | 汉族」のようなヘッダーの日付は、パーサーの既定の年齢日付より優先する。
    header_birth = re.search(r"\d{1,3}\s*岁\s*[（(]\s*((?:19|20)\d{2})\s*[-./]\s*(\d{1,2})(?:\s*[-./]\s*(\d{1,2}))?", clean_text[:500])
    if header_birth:
        day = int(header_birth.group(3) or 1)
        base["birth_date"] = f"{header_birth.group(1)}年{int(header_birth.group(2)):02d}月{day:02d}日"
        base["birth_year"] = header_birth.group(1)
    header_region = re.search(r"\|\s*([\u4e00-\u9fff]{2,12})\s*\|\s*(?:汉族|少数民族)", clean_text[:500])
    if header_region and not base.get("address"):
        base["address"] = header_region.group(1)
        base["city"] = header_region.group(1)
    # 求职意向是独立对象，不能留在“期望职位为空”的默认值中。
    # EN: Job preferences are a separate object and must not be left at the default of "desired position empty".
    # JA: 希望条件は独立したオブジェクトであり、「希望職位が空」という既定値のままにしてはならない。
    expected_rows = data.get("expected_info") or [{}]
    expected = dict(expected_rows[0] if expected_rows else {})
    label_patterns = {
        "expected_city": r"(?:期望地点|目标地点|期望城市|希望工作地|希望勤務地)\s*[:：]?\s*([^\n|｜]{1,60})",
        "expected_position": r"(?:期望职位|意向职位|希望职位|希望職種)\s*[:：]?\s*([^\n|｜]{1,100})",
        "expected_salary": r"(?:期望薪资|期望薪酬|期望待遇|薪资|希望年収)\s*[:：]?\s*([^\n|｜]{1,60})",
        "expected_industry": r"(?:期望行业|希望行业|希望業界)\s*[:：]?\s*([^\n|｜]{1,80})",
    }
    for key, pattern in label_patterns.items():
        m = re.search(pattern, clean_text, re.I)
        if m:
            value = re.sub(r"\s+", " ", m.group(1)).strip(" ：:，,。")
            if value and not re.search(r"^(?:未填写|暂无|无)$", value, re.I):
                expected[key] = value
    if expected.get("expected_salary"):
        salary = expected["expected_salary"]
        nums = re.findall(r"\d+(?:\.\d+)?", salary)
        if nums:
            expected["expected_annual_salary_min"] = nums[0]
            expected["expected_annual_salary_max"] = nums[-1]
    data["expected_info"] = [expected]
    # 中文/日文模板的姓名标签通常不在第一行；优先读取明确的“姓名/氏名”字段。
    # EN: The name label of Chinese/Japanese templates is usually not on the first line; read the explicit "姓名/氏名" (name) field first.
    # JA: 中国語・日本語テンプレートの氏名ラベルは通常 1 行目にない。明示的な「姓名／氏名」フィールドを優先して読む。
    explicit_name = re.search(r"(?:姓名|姓\s*名|氏名|お名前)[ \t\u3000]*[:：]?[ \t\u3000|│]*([\u4e00-\u9fffA-Za-z·]{1,20}(?:[ \t\u3000]+[\u4e00-\u9fffA-Za-z·]{1,10})?)", clean_text, re.I)
    if explicit_name:
        name_value = re.sub(r"\s+", "", explicit_name.group(1)).strip()
        name_value = re.split(r"(?:性别|年龄|手机|电话|电子邮件|教育程度|婚姻状况)", name_value, maxsplit=1, flags=re.I)[0].strip()
        if name_value and not re.search(r"电子邮件|教育|经历|履历|職務|工作|简历", name_value, re.I):
            current_name = str(base.get("full_name") or "").strip()
            if not current_name or re.search(r"职务经历|職務経歴|履历|履歴書|简历|个人简历", current_name, re.I) or len(name_value) <= 8:
                base["full_name"] = name_value
    # 猎聘导出的页眉通常没有“姓名：”标签，而是“姓名 离职，正在找工作”。
    # 该规则只看文档前部，避免把自我评价中的普通句子误当姓名。
    # EN: Liepin export headers usually have no "姓名：" label but read "name 离职，正在找工作" (left job, currently looking for work).
    #     This rule looks only at the beginning of the document so ordinary sentences in the self-assessment are not taken as the name.
    # JA: Liepin のエクスポートのヘッダーには通常「姓名：」ラベルがなく、「氏名 离职，正在找工作」（退職済み、求職中）となっている。
    #     このルールは文書の前半だけを見るため、自己評価中の普通の文を氏名と誤認しない。
    header_name = re.search(
        r"(?m)^\s*(?P<name>[\u4e00-\u9fff·]{2,8})\s*(?:在职|离职|正在找工作|待业|求职)",
        clean_text[:1200],
        re.I,
    )
    if header_name:
        base["full_name"] = header_name.group("name").strip()
    # 文件名是“简历-日期”时不能把“简历”当姓名；优先读取正文首行姓名。
    # EN: When the file name is "简历-date" (résumé-date), "简历" must not be taken as the name; prefer the name on the first line of the body.
    # JA: ファイル名が「简历-日付」（履歴書-日付）の場合、「简历」を氏名にしてはならない。本文 1 行目の氏名を優先して読む。
    generic_name = str(base.get("full_name") or "").strip() in {"简历", "个人简历", "resume", "cv", "CV"}
    if generic_name or not str(base.get("full_name") or "").strip():
        for first_line in clean_text.splitlines()[:8]:
            line = re.sub(r"[^\u4e00-\u9fffA-Za-z·\s]", " ", first_line).strip()
            candidates = re.findall(r"[\u4e00-\u9fff]{2,4}", line)
            if candidates:
                candidate = candidates[0]
                if len(candidate) == 4 and candidate[0] == candidate[1]:
                    candidate = candidate[1:]
                if candidate not in {"电子邮件", "目前薪资", "期望薪资", "婚姻状况", "教育背景"}:
                    base["full_name"] = candidate
                    break
    # 顶层当前工作摘要必须与清洗后的第一段工作经历一致，不能保留旧的错位值。
    # EN: The top-level current-job summary must match the first cleaned work experience and must not keep old misplaced values.
    # JA: トップレベルの現職の概要は、クレンジング後の最初の職歴と一致しなければならず、古いずれた値を残してはならない。
    all_works = [item for resume in resumes for item in (resume.get("work_experiences") or [])]
    first_work = None
    if all_works:
        # 当前工作优先；否则取起始时间最新的一段作为摘要。
        # EN: The current job takes priority; otherwise use the entry with the latest start date as the summary.
        # JA: 現職を優先し、なければ開始日が最も新しい職歴を概要とする。
        first_work = sorted(
            all_works,
            key=lambda item: (
                1 if str(item.get("status") or "") == "在职" or not item.get("position_resigned") else 0,
                str(item.get("position_start") or "")
            ),
            reverse=True,
        )[0]
    if first_work:
        current = dict(data.get("current_info") or {})
        mapping = {
            "company_name": "company_name", "company_employees": "company_employees", "company_industry": "company_industry",
            "position": "position", "position_dept": "position_dept", "position_report_to": "position_report_to",
            "position_subordinate": "position_subordinate", "employment_type": "employment_type", "position_salary": "position_salary",
            "annual_salary_min": "annual_salary_min", "annual_salary_max": "annual_salary_max", "status": "status",
            "position_start": "position_start", "position_resigned": "position_resigned",
        }
        for target, source in mapping.items():
            if source in first_work:
                current[target] = first_work.get(source) or ""
        data["current_info"] = current
    # 教育摘要也遵循同一规则：有中文履历时必须从中文 resume 取，不能被日文/英文块覆盖。
    # EN: The education summary follows the same rule: when there is a Chinese résumé it must come from the Chinese resume and cannot be overwritten by Japanese/English blocks.
    # JA: 学歴の概要も同じルールに従う。中国語の履歴書がある場合は中国語の resume から取り、日本語・英語ブロックで上書きしてはならない。
    first_resume = primary_resume if primary_resume and primary_resume.get("education_list") else next((r for r in resumes if r.get("education_list")), None)
    if first_resume:
        education_rows = first_resume.get("education_list") or []
        highest = sorted(education_rows, key=lambda x: (int(str(x.get("school_degree_rank") or "1")) if str(x.get("school_degree_rank") or "1").isdigit() else 1, str(x.get("school_end_ym") or "")), reverse=True)[0]
        data["education_info"] = {
            "school_name": highest.get("school_name") or "",
            "school_major_name": highest.get("school_major_name") or "",
            "school_degree_type": highest.get("school_degree_type") or "",
            "school_degree_rank": str(highest.get("school_degree_rank") or ""),
            "school_education_type": highest.get("school_education_type") or "",
            "school_start_ym": highest.get("school_start_ym") or "",
            "school_end_ym": highest.get("school_end_ym") or "",
        }
    # 语言等级只保留可检索的语言/证书等级，避免把后续说明文字串进来。
    # EN: Language levels keep only searchable language/certificate levels, so subsequent explanatory text is not pulled in.
    # JA: 語学レベルは検索可能な言語・資格レベルだけを残し、後続の説明文が混入しないようにする。
    def clean_language_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        cleaned = []
        for item in rows or []:
            row = dict(item)
            level = re.sub(r"[\s√✓✔☑（）()]+", " ", str(row.get("language_level") or "")).strip(" /|，,；;")
            exams = []
            for label, code in (("六级", "CET-6"), ("四级", "CET-4"), ("CET[- ]?6", "CET-6"), ("CET[- ]?4", "CET-4"), ("日语一?级", "N1")):
                for m in re.finditer(label + r"\s*[-:]?\s*(\d{3})?", level, re.I):
                    exams.append(code + (f" {m.group(1)}" if m.group(1) else ""))
            if exams:
                level = " / ".join(dict.fromkeys(exams))
            elif re.search(r"流程|内控|工作|项目|负责|有效性|跟踪|课题|竞赛|演讲|荣誉|获奖|厂房|民用|食堂|宿舍|地址|公司", level):
                level = ""
            else:
                level = re.split(r"[，,；;。|]", level, maxsplit=1)[0].strip()[:40]
            row["language_level"] = level
            if row.get("language_name") and (level or row.get("language_certificate")):
                cleaned.append(row)
        return cleaned
    data["language_info"] = clean_language_rows(data.get("language_info") or [])
    for resume in resumes:
        resume["language_info"] = clean_language_rows(resume.get("language_info") or [])
    # 多语言简历：中文 resume 是基础信息唯一来源。地址/城市等经过全局清洗后，必须同步回中文子对象，避免顶层与 resume[0] 不一致。
    # EN: Multilingual résumés: the Chinese resume is the only source of basic information. After global cleaning of address/city etc., sync back into the Chinese sub-object so the top level and resume[0] do not disagree.
    # JA: 多言語の履歴書：基本情報の唯一のソースは中国語の resume。住所・都市などを全体クレンジングした後は中国語のサブオブジェクトにも同期し、トップレベルと resume[0] が食い違わないようにする。
    if primary_resume:
        primary_resume["base_info"] = dict(data.get("base_info") or {})
        for resume in resumes:
            if resume.get("resume_languge") == "zh" and resume is not primary_resume:
                # 仅在该中文块缺失或明显污染时同步，保留同一中文块的完整字段。
                # EN: Sync only when the Chinese block is missing or obviously polluted, keeping the full fields of the same Chinese block.
                # JA: 中国語ブロックが欠けているか明らかに汚染されている場合だけ同期し、同じ中国語ブロックの全フィールドを保持する。
                nested = dict(resume.get("base_info") or {})
                for key, value in (data.get("base_info") or {}).items():
                    if value or not nested.get(key):
                        nested[key] = value
                resume["base_info"] = nested
        # 顶层摘要必须与中文 resume 的明细一致，不再从其他语言或旧 DOM 错位字段取值。
        # EN: The top-level summary must match the details of the Chinese resume; values are no longer taken from other languages or old misplaced DOM fields.
        # JA: トップレベルの概要は中国語 resume の明細と一致しなければならず、他言語や古いずれた DOM フィールドから値を取らない。
        zh_works = primary_resume.get("work_experiences") or []
        if zh_works:
            current_work = sorted(zh_works, key=lambda x: (0 if x.get("position_resigned") else 1, str(x.get("position_start") or "")), reverse=True)[0]
            current = dict(data.get("current_info") or {})
            for key in ("company_name", "company_employees", "company_industry", "position", "position_dept", "position_report_to", "position_subordinate", "employment_type", "position_salary", "annual_salary_min", "annual_salary_max", "status", "position_start", "position_resigned"):
                current[key] = current_work.get(key) or ""
            data["current_info"] = current
        zh_edus = primary_resume.get("education_list") or []
        if zh_edus:
            highest = sorted(zh_edus, key=lambda x: (int(str(x.get("school_degree_rank") or "1")) if str(x.get("school_degree_rank") or "1").isdigit() else 1, str(x.get("school_end_ym") or "")), reverse=True)[0]
            data["education_info"] = {key: highest.get(key) or "" for key in ("school_name", "school_major_name", "school_degree_type", "school_degree_rank", "school_education_type", "school_start_ym", "school_end_ym")}
    # 文件级 structured_data 只保留一个汇总 raw_text；列表子对象的 raw_text
    # 和 fingerprint 会造成重复占用空间。这里直接使用 HTML 清洗后的全文，
    # 保留基础信息、求职意向、工作/教育/语言、自我评价和文末文字，避免
    # 从结构化列表反向拼接时遗漏原简历中的未结构化内容。
    # EN: File-level structured_data keeps only one aggregate raw_text; raw_text and fingerprint in list sub-objects
    #     waste space through duplication. Here the full text after HTML cleaning is used directly,
    #     keeping basic info, job preferences, work/education/language, self-assessment and trailing text, so that
    #     unstructured content of the original résumé is not lost when reassembling from the structured lists.
    # JA: ファイル単位の structured_data には集約した raw_text を 1 つだけ残す。リストのサブオブジェクトにある raw_text と
    #     fingerprint は重複して容量を消費する。ここでは HTML をクレンジングした全文をそのまま使い、
    #     基本情報・希望条件・職歴／学歴／語学・自己評価・末尾の文章を残して、構造化リストから逆に組み立てる際に
    #     元の履歴書の非構造化部分が漏れないようにする。
    resume_raw_text = clean_text.strip()

    def strip_internal(value: Any) -> Any:
        if isinstance(value, dict):
            return {
                key: strip_internal(child)
                for key, child in value.items()
                if key not in {"raw_text", "fingerprint"}
            }
        if isinstance(value, list):
            return [strip_internal(child) for child in value]
        return value

    data = strip_internal(data)
    data["raw_text"] = resume_raw_text
    data.pop("communication_assessment", None)
    return data


def parse_one(path: Path, html_path: Path, parser: CodexGeminiHtmlSchemaParser) -> dict[str, Any]:
    html = html_path.read_text(encoding="utf-8", errors="replace")
    text = plain_text(html)
    parsed = parser.parse(html, filename=path.name, source_path=str(path))
    # extend_schema 会在原对象上补字段；先保留主解析器输出，供最终工作经历同步。
    # EN: extend_schema adds fields onto the original object; keep the main parser's output first for the final work-experience sync.
    # JA: extend_schema は元のオブジェクトにフィールドを追加するため、最終的な職歴の同期用にメインパーサーの出力を先に保持しておく。
    parsed_work_snapshot = [
        [dict(item) for item in (resume.get("work_experiences") or [])]
        for resume in (parsed.get("resumes") or [])
    ]
    parsed_base_snapshot = [
        dict(resume.get("base_info") or {})
        for resume in (parsed.get("resumes") or [])
    ]
    structured = extend_schema(parsed, text, path.name, str(path))
    # extend_schema 还保留一组旧版 fallback 规则。对工作经历，DOM 主解析器
    # 的“日期→公司→职位/部门→职责”边界更可靠；这里在最终出口再次同步，
    # 防止备用规则把“作为开发进入公司”“(9年”等片段覆盖回最终 JSON。
    # EN: extend_schema also keeps a set of old fallback rules. For work experience, the main DOM parser's
    #     "date → company → position/department → duties" boundaries are more reliable; sync once more at the final exit
    #     so the fallback rules cannot write fragments like "joined the company as a developer" or "(9 years" back into the final JSON.
    # JA: extend_schema には旧来の fallback ルールも残っている。職歴については DOM メインパーサーの
    #     「日付 → 会社 → 職位／部署 → 職務」の境界の方が信頼できるため、最終出口で改めて同期し、
    #     代替ルールが「開発者として入社」「(9年」などの断片を最終 JSON に書き戻すのを防ぐ。
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
        if parsed_work:
            structured_resumes[index]["work_experiences"] = [
                {key: value for key, value in item.items() if key not in {"raw_text", "fingerprint"}}
                for item in parsed_work
            ]
    if structured_resumes and structured_resumes[0].get("work_experiences"):
        first_work = sorted(
            structured_resumes[0]["work_experiences"],
            key=lambda item: (1 if not item.get("position_resigned") else 0, str(item.get("position_start") or "")),
            reverse=True,
        )[0]
        current = dict(structured.get("current_info") or {})
        for key in ("company_name", "company_employees", "company_industry", "position", "position_dept",
                    "position_report_to", "position_subordinate", "employment_type", "position_salary",
                    "annual_salary_min", "annual_salary_max", "status", "position_start", "position_resigned"):
            current[key] = first_work.get(key) or ""
        structured["current_info"] = current
    structured["resumes"] = structured_resumes
    if structured_resumes and structured_resumes[0].get("base_info"):
        structured["base_info"] = dict(structured_resumes[0]["base_info"])
    fallback_date = date_from_mtime(path)
    now = datetime.now(TZ_JST).isoformat(timespec="seconds")
    resume_date = updated_date(text, fallback_date)
    return {
        "schema_version": "codex-resume-json-1.0",
        "record_id": record_id(path),
        "source": {
            "path": str(path.resolve()),
            "original_path": str(path.resolve()),
            "filename": path.name,
            "extension": path.suffix.lower(),
            "size": path.stat().st_size,
        },
        "dates": {
            "resume_updated_date": resume_date,
            "resume_download_date": fallback_date,
            "resume_updated_date_source": "文档内更新日期" if resume_date != fallback_date else "本地文件修改时间",
            "resume_download_date_source": "本地文件修改时间（历史资料时间）",
            "sys_created_date": now,
            "sys_updated_date": now,
        },
        "extraction": {
            "reader_group": "word_html_dom",
            "converter": "codex_word_html_json_100",
            "parser": "codex_gemini_html_schema_parser",
            "status": "success",
            "html_path": str(html_path.resolve()),
            "dom": dom_summary(html),
        },
        "structured_data": structured,
        "quality": {
            "full_name": (structured.get("base_info") or {}).get("full_name", ""),
            "has_work": bool((structured.get("resumes") or [{}])[0].get("work_experiences")),
            "has_education": bool((structured.get("resumes") or [{}])[0].get("education_list")),
            "raw_text_length": len(text),
        },
    }


def main() -> int:
    args = parse_args()
    if os.name == "nt":
        os.system("title Codex Word - HTML DOM - JSON 100 Test")
    source = args.source.resolve()
    html_root = args.html_output.resolve()
    json_root = args.json_output.resolve()
    # 先建立全部格式目录，便于后续按 docs/pdf/xls/web/text/presentation/image
    # 分批运行；本轮 Word 文件实际写入 docs。
    # EN: Create all format directories first so later runs can be batched by docs/pdf/xls/web/text/presentation/image;
    #     this round's Word files are actually written to docs.
    # JA: 後で docs/pdf/xls/web/text/presentation/image ごとに分けて実行できるよう、先にすべての形式のディレクトリを作る。
    #     今回の Word ファイルは実際には docs に書き込む。
    for category in FORMAT_OUTPUT_DIRS:
        (html_root / category).mkdir(parents=True, exist_ok=True)
        (json_root / category).mkdir(parents=True, exist_ok=True)
    html_output = html_root / args.category
    json_output = json_root / args.category
    html_output.mkdir(parents=True, exist_ok=True)
    json_output.mkdir(parents=True, exist_ok=True)
    files = source_files(source, 0 if args.all else args.limit)
    print(f"Codex Word→HTML→JSON 试跑：选中 {len(files)} 个真实 Word 文件" f" / Codex Word→HTML→JSON trial run: {len(files)} real Word files selected / Codex Word→HTML→JSON の試行：実際の Word ファイル {len(files)} 個を選択", flush=True)
    print(f"源目录：{source}" f" / Source directory: {source} / 元ディレクトリ：{source}", flush=True)
    print(f"HTML目录：{html_output}" f" / HTML directory: {html_output} / HTML ディレクトリ：{html_output}", flush=True)
    print(f"JSON目录：{json_output}" f" / JSON directory: {json_output} / JSON ディレクトリ：{json_output}", flush=True)
    manifest: list[dict[str, Any]] = []
    last_heartbeat = time.monotonic()
    print("\n=== 阶段 1/2：逐文件生成 HTML DOM ===" " / \n=== Stage 1/2: generate the HTML DOM file by file === / \n=== 段階 1/2：ファイルごとに HTML DOM を生成 ===", flush=True)
    for index, path in enumerate(files, 1):
        html_path = html_output / html_name(path)
        result = convert_one(path, html_path, args.legacy_timeout)
        row = {"index": index, "source": str(path), "html": str(html_path), "conversion": result}
        manifest.append(row)
        print(f"[HTML {index:03d}/{len(files):03d}] {result['status']:>8} {path.name} ({result.get('seconds', 0)}s)", flush=True)
        if time.monotonic() - last_heartbeat >= args.progress_interval:
            print(f"[心跳] HTML阶段 {index}/{len(files)}，成功 {sum(r['conversion']['status'] in ('success','existing') for r in manifest)}，失败 {sum(r['conversion']['status']=='failed' for r in manifest)}" f" / [heartbeat] HTML stage {index}/{len(files)}, succeeded {sum(r['conversion']['status'] in ('success','existing') for r in manifest)}, failed {sum(r['conversion']['status']=='failed' for r in manifest)} / [ハートビート] HTML 段階 {index}/{len(files)}、成功 {sum(r['conversion']['status'] in ('success','existing') for r in manifest)}、失敗 {sum(r['conversion']['status']=='failed' for r in manifest)}", flush=True)
            last_heartbeat = time.monotonic()

    parser = CodexGeminiHtmlSchemaParser()
    classifier = DocumentClassifier()
    parsed_count = 0
    parse_failed = 0
    non_resume_count = 0
    print("\n=== 阶段 2/2：只解析本批 HTML DOM 并生成 JSON ===" " / \n=== Stage 2/2: parse only this batch's HTML DOM and generate JSON === / \n=== 段階 2/2：このバッチの HTML DOM だけを解析して JSON を生成 ===", flush=True)
    for row in manifest:
        if row["conversion"]["status"] == "failed" or not Path(row["html"]).exists():
            row["parsing"] = {"status": "not_run", "error": "HTML生成失败"}
            continue
        path = Path(row["source"])
        html_path = Path(row["html"])
        try:
            html_text = html_path.read_text(encoding="utf-8", errors="replace")
            classification = classifier.classify(plain_text(html_text), filename=path.name)
            row["classification"] = classification.__dict__
            # 只有简历及“疑难简历”进入 JSON；JD、合同、客户资料、培训等
            # 非简历资料不生成候选人 JSON，但保留 HTML 证据供本轮复核。
            # EN: Only résumés and "difficult résumés" go into JSON; JDs, contracts, client materials, training and other
            #     non-résumé materials do not produce candidate JSON, but their HTML evidence is kept for this round's review.
            # JA: JSON にするのは履歴書と「難しい履歴書」だけ。JD・契約書・顧客資料・研修などの
            #     非履歴書資料からは候補者 JSON を生成しないが、今回のレビュー用に HTML の証拠は残す。
            if classification.document_type not in {"resume", "ambiguous_resume"}:
                row["parsing"] = {
                    "status": "skipped_non_resume",
                    "document_type": classification.document_type,
                    "reason": classification.reason,
                }
                non_resume_count += 1
                print(f"[跳过非简历 {non_resume_count:03d}] {path.name} → {classification.document_type}" f" / [skipped non-résumé {non_resume_count:03d}] {path.name} → {classification.document_type} / [履歴書でないためスキップ {non_resume_count:03d}] {path.name} → {classification.document_type}", flush=True)
                continue
            record = parse_one(path, html_path, parser)
            name = ((record.get("structured_data") or {}).get("base_info") or {}).get("full_name") or "未知"
            target = json_output / f"({re.sub(r'[\\/:*?\"<>|]', '', name)})__{record['record_id'][:12]}.json"
            target.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
            row["parsing"] = {
                "status": "success",
                "json": str(target),
                "full_name": name,
            }
            row["quality_flags"] = name_quality_flags(name)
            parsed_count += 1
            print(f"[JSON {parsed_count:03d}] success {path.name} → {name}", flush=True)
        except Exception as exc:
            row["parsing"] = {"status": "failed", "error": str(exc)}
            parse_failed += 1
            print(f"[JSON] failed {path.name}: {exc}", flush=True)

    report = {
        "workflow": "codex_word_html_dom_json_batch",
        "category": args.category,
        "source": str(source),
        "selected": len(files),
        "html_success": sum(r["conversion"]["status"] in ("success", "existing") for r in manifest),
        "html_failed": sum(r["conversion"]["status"] == "failed" for r in manifest),
        "json_success": parsed_count,
        "json_failed": parse_failed,
        "non_resume_skipped": non_resume_count,
        "items": manifest,
    }
    report_path = json_output / "_doc_batch_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    context = {
        "context_version": "codex-doc-batch-1.0",
        "purpose": "Word 类型第一轮转换、分类和解析复核上下文",
        "category": args.category,
        "output_html_dir": str(html_output),
        "output_json_dir": str(json_output),
        "supported_extensions": sorted(WORD_EXTENSIONS),
        "selected": len(files),
        "html_success": report["html_success"],
        "html_failed": report["html_failed"],
        "json_success": parsed_count,
        "json_failed": parse_failed,
        "non_resume_skipped": non_resume_count,
        "items_requiring_attention": [
            item for item in manifest
            if item.get("conversion", {}).get("status") == "failed"
            or item.get("parsing", {}).get("status") == "failed"
            or item.get("classification", {}).get("document_type") == "ambiguous_resume"
            or item.get("quality_flags")
        ],
        "notes": [
            "Word 类型包含 .doc、.docx、.docm、.dotx、.wps。",
            "非简历文件不生成 JSON；对应 HTML 保留在 docs，便于核对分类依据。",
            "转换失败或疑难简历会记录在本 context 的 items_requiring_attention 中。",
        ],
    }
    context_path = html_output / "_doc_batch_context.json"
    context_path.write_text(json.dumps(context, ensure_ascii=False, indent=2), encoding="utf-8")
    md_lines = [
        "# Word 类型第一轮处理 Context",
        "",
        f"- 源文件数：{len(files)}",
        f"- HTML 成功/失败：{report['html_success']} / {report['html_failed']}",
        f"- 简历 JSON：{parsed_count}",
        f"- 非简历跳过：{non_resume_count}",
        f"- 需要复核：{len(context['items_requiring_attention'])}",
        "",
        "详细问题见同目录 `_doc_batch_context.json`。",
    ]
    (html_output / "_doc_batch_context.md").write_text("\n".join(md_lines), encoding="utf-8")
    print("\n=== Codex 100 条试跑完成 ===" " / \n=== Codex trial run of 100 finished === / \n=== Codex の 100 件の試行が完了しました ===", flush=True)
    print(f"HTML成功：{report['html_success']}；HTML失败：{report['html_failed']}" f" / HTML succeeded: {report['html_success']}; HTML failed: {report['html_failed']} / HTML 成功：{report['html_success']}、HTML 失敗：{report['html_failed']}", flush=True)
    print(f"JSON成功：{report['json_success']}；JSON失败：{report['json_failed']}" f" / JSON succeeded: {report['json_success']}; JSON failed: {report['json_failed']} / JSON 成功：{report['json_success']}、JSON 失敗：{report['json_failed']}", flush=True)
    print(f"非简历跳过：{report['non_resume_skipped']}" f" / Non-résumés skipped: {report['non_resume_skipped']} / 履歴書でないためスキップ：{report['non_resume_skipped']}", flush=True)
    print(f"报告：{report_path}" f" / Report: {report_path} / レポート：{report_path}", flush=True)
    print(f"问题 Context：{context_path}" f" / Problem Context: {context_path} / 問題の Context：{context_path}", flush=True)
    return 0 if parse_failed == 0 and report["html_failed"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
