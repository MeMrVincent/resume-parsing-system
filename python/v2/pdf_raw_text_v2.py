from __future__ import annotations

import html
import re
import unicodedata
import zipfile
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

import fitz


W_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
HTML_META_RE = re.compile(
    r"^(?:源文件路径|简历落地时间|联系电话|电子邮箱)\s*[：:]?$|^[A-Z]:\\.*\.(?:docx?|pdf)$",
    re.I,
)


def text(value: Any) -> str:
    return str(value or "").strip()


def repair_utf8_mojibake(value: str) -> str:
    """Repair common UTF-8 bytes decoded as Latin-1 (for example ç®å)."""
    current = value or ""
    try:
        repaired = current.encode("latin1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return current
    current_noise = len(re.findall(r"[\x80-\x9f\u00c0-\u00ff]", current))
    repaired_noise = len(re.findall(r"[\x80-\x9f]", repaired))
    return repaired if current_noise and repaired_noise < current_noise else current


def normalize_line(value: str) -> str:
    value = repair_utf8_mojibake(value or "")
    value = unicodedata.normalize("NFKC", value).replace("\u00a0", " ")
    value = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]", "", value)
    return re.sub(r"[ \t]+", " ", value).strip()


def compact(value: str) -> str:
    return re.sub(r"[^0-9a-z\u3400-\u9fff\u3040-\u30ff]+", "", unicodedata.normalize("NFKC", value or "").casefold())


def read_pdf_text(path: Path) -> str:
    if not path.is_file():
        return ""
    try:
        with fitz.open(path) as document:
            return "\n".join(page.get_text("text") for page in document)
    except Exception:
        return ""


def read_docx_text(path: Path) -> str:
    if not path.is_file():
        return ""
    try:
        with zipfile.ZipFile(path) as archive:
            root = ET.fromstring(archive.read("word/document.xml"))
        paragraphs: list[str] = []
        for paragraph in root.iter(W_NS + "p"):
            value = "".join(node.text or "" for node in paragraph.iter(W_NS + "t"))
            value = normalize_line(value)
            if value:
                paragraphs.append(value)
        return "\n".join(paragraphs)
    except Exception:
        return ""


def read_html_text(path: Path) -> str:
    if not path.is_file():
        return ""
    raw = path.read_text(encoding="utf-8", errors="replace")
    raw = re.sub(r"<script\b[^>]*>.*?</script>|<style\b[^>]*>.*?</style>", " ", raw, flags=re.I | re.S)
    return html.unescape(re.sub(r"<[^>]+>", "\n", raw))


def chunk_coverage(candidate: str, corpus: str, *, size: int = 28) -> float:
    current = compact(candidate)
    target = compact(corpus)
    if not current:
        return 1.0
    if current in target:
        return 1.0
    if len(current) < size:
        return 0.0
    starts = list(range(0, len(current), size))
    chunks = [current[start:start + size] for start in starts if len(current[start:start + size]) >= max(10, size // 2)]
    if not chunks:
        return 0.0
    return sum(chunk in target for chunk in chunks) / len(chunks)


def clean_lines(value: str, *, html_source: bool = False) -> list[str]:
    lines = [normalize_line(line) for line in (value or "").replace("\r", "\n").split("\n")]
    # iLovePDF/Word conversion bookkeeping is not resume text.  It must not
    # leak into raw_text or become evidence for a structured field.
    lines = [line for line in lines if line and not re.fullmatch(r"WordOOXMLTable\d+", line, re.I)]
    if html_source:
        filtered: list[str] = []
        skip_value_after_label = False
        for line in lines:
            if skip_value_after_label:
                skip_value_after_label = False
                continue
            if HTML_META_RE.search(line):
                if re.fullmatch(r"(?:源文件路径|简历落地时间|联系电话|电子邮箱)\s*[：:]?", line, re.I):
                    skip_value_after_label = True
                continue
            filtered.append(line)
        lines = filtered

    # Word table conversion can emit one very long concatenated row followed by
    # the same cells as readable short lines. Keep the readable representation.
    joined_short = "\n".join(line for line in lines if len(compact(line)) <= 160)
    without_aggregates: list[str] = []
    for line in lines:
        if len(compact(line)) > 160 and chunk_coverage(line, joined_short) >= 0.72:
            continue
        without_aggregates.append(line)

    output: list[str] = []
    seen: set[str] = set()
    for line in without_aggregates:
        key = compact(line)
        if not key or key in seen:
            continue
        seen.add(key)
        output.append(line)
    return output


def merge_texts(word_text: str, pdf_text: str, html_text: str) -> str:
    sources = [
        clean_lines(word_text),
        clean_lines(pdf_text),
        clean_lines(html_text, html_source=True),
    ]
    primary_index = next((index for index, lines in enumerate(sources) if lines), None)
    if primary_index is None:
        return ""
    output = list(sources[primary_index])
    corpus = "\n".join(output)
    for index, lines in enumerate(sources):
        if index == primary_index:
            continue
        for line in lines:
            key = compact(line)
            if not key:
                continue
            if key in compact(corpus):
                continue
            if len(key) >= 28 and chunk_coverage(line, corpus) >= 0.72:
                continue
            output.append(line)
            corpus += "\n" + line
    return "\n".join(output).strip()


def build_source_text_index(mapping: dict[str, Any]) -> dict[str, str]:
    output: dict[str, str] = {}
    for row in mapping.get("records") or []:
        filename = text(row.get("input_filename"))
        if not filename:
            continue
        input_path = Path(text(row.get("input_path")))
        processing = row.get("processing") or {}
        word_path = Path(text(row.get("word_path") or processing.get("word_path")))
        html_path = Path(text(processing.get("html_path")))
        output[filename.casefold()] = merge_texts(
            read_docx_text(word_path),
            read_pdf_text(input_path),
            read_html_text(html_path),
        )
    return output


def payload_raw_text(payload: dict[str, Any], source_index: dict[str, str]) -> str:
    blocks: list[str] = []
    seen_files: set[str] = set()
    seen_bodies: set[str] = set()
    seen_hashes: set[str] = set()
    for row in ((payload.get("source") or {}).get("source_files") or []):
        if not isinstance(row, dict):
            continue
        filename = text(row.get("filename") or Path(text(row.get("input_path"))).name)
        key = filename.casefold()
        source_hash = text(row.get("sha256")).casefold()
        body = source_index.get(key, "").strip()
        body_key = compact(body)
        if not body or key in seen_files or body_key in seen_bodies or (source_hash and source_hash in seen_hashes):
            continue
        seen_files.add(key)
        seen_bodies.add(body_key)
        if source_hash:
            seen_hashes.add(source_hash)
        blocks.append(f"===== SOURCE: {repair_utf8_mojibake(filename)} =====\n{body}")
    return "\n\n".join(blocks).strip()


def detect_resume_languages(filename: str, body: str) -> list[str]:
    name = unicodedata.normalize("NFKC", filename or "")
    if re.search(r"日语|日文|日本語|履歴書|職務経歴", name, re.I):
        return ["ja"]
    if re.search(r"英文|英語|English", name, re.I):
        return ["en"]
    if re.search(r"中文|中国語", name, re.I):
        return ["zh"]
    kana = len(re.findall(r"[\u3040-\u30ff]", body or ""))
    han = len(re.findall(r"[\u3400-\u9fff]", body or ""))
    latin = len(re.findall(r"[A-Za-z]", body or ""))
    if kana >= 12:
        return ["ja"]
    if latin >= 120 and latin > han * 2:
        return ["en"]
    return ["zh"]


def detect_document_type(filename: str, body: str) -> str:
    value = unicodedata.normalize("NFKC", (filename or "") + "\n" + (body or "")[:1000])
    if re.search(r"職務経歴書|工作经历|WORK EXPERIENCE", value, re.I):
        return "work_history"
    if re.search(r"履歴書|个人简历|個人簡歴|简历|resume|curriculum vitae", value, re.I):
        return "resume"
    return "resume"
