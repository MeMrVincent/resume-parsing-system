from __future__ import annotations
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1] / "common"))
import rc_config as _rc  # noqa: E402  项目统一配置（python/common/rc_config.py）
# EN: noqa: E402  project-wide configuration (python/common/rc_config.py)
# JA: noqa: E402  プロジェクト共通設定（python/common/rc_config.py）

import argparse
import hashlib
import json
import re
import tempfile
import zipfile
from collections import defaultdict
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None


PROJECT_ROOT = _rc.project_root()
PDF_ROOT = PROJECT_ROOT / _rc.dirname("complete-transfered-htmls") / "pdf"
INPUT_DIR = PDF_ROOT / "input"
WORD_DIR = PDF_ROOT / "word"
MANIFEST_PATH = PDF_ROOT / "PDF文档.json"
GPT_DIR = PROJECT_ROOT / _rc.dirname("complete-transfered-jsons") / "pdf" / "gpt"
OLD_DIR = PROJECT_ROOT / _rc.dirname("complete-transfered-jsons") / "pdf" / "old"
WORK_DIR = PDF_ROOT / "rebuild-work"
REPORT_DIR = PDF_ROOT / "rebuild-reports"
MAP_PATH = WORK_DIR / "pdf_rebuild_map.v2.json"
ALIAS_PATH = REPORT_DIR / "pdf_word_aliases.v2.json"
PILOT_PATH = REPORT_DIR / "pdf_pilot_30.v2.json"
OVERRIDE_PATH = REPORT_DIR / "pdf_rebuild_overrides.v2.json"

VERSION = "pdf-rebuild-map-v2.0.1"
HASH_SUFFIX_RE = re.compile(r"__(?P<hash>[0-9a-f]{12})$", re.I)
PHONE_RE = re.compile(r"(?<!\d)(?:\+?86[-\s]?)?1[3-9]\d(?:[-\s]?\d){8}(?!\d)")
EMAIL_RE = re.compile(r"[A-Z0-9._%+*\-]+@[A-Z0-9.\-*]+\.[A-Z]{2,}", re.I)
NON_RESUME_HINT_RE = re.compile(
    r"案件更新|請求書|请求书|募集依頼|招聘委托|胜任力测评|员工守则|合同|开票|营业执照",
    re.I,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="建立 PDF v2 重构权威映射和试点清单" " / Build the authoritative map and pilot list for the PDF v2 rebuild / PDF v2 再構築の正本マップと試行用一覧を作成する")
    parser.add_argument("--input-dir", type=Path, default=INPUT_DIR)
    parser.add_argument("--word-dir", type=Path, default=WORD_DIR)
    parser.add_argument("--manifest", type=Path, default=MANIFEST_PATH)
    parser.add_argument("--gpt-dir", type=Path, default=GPT_DIR)
    parser.add_argument("--old-dir", type=Path, default=OLD_DIR)
    parser.add_argument("--map", type=Path, default=MAP_PATH)
    parser.add_argument("--alias-report", type=Path, default=ALIAS_PATH)
    parser.add_argument("--pilot-report", type=Path, default=PILOT_PATH)
    parser.add_argument("--overrides", type=Path, default=OVERRIDE_PATH)
    parser.add_argument("--pilot-size", type=int, default=30)
    return parser.parse_args()


def load_overrides(path: Path) -> dict[str, dict[str, Any]]:
    if not path.is_file():
        return {}
    payload = read_json(path)
    rows = payload.get("overrides", []) if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        raise ValueError("PDF 人工覆盖文件的 overrides 必须是数组")
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        filename = str(row.get("input_filename") or "").strip()
        if not filename:
            continue
        classification = str(row.get("classification") or "").strip()
        if classification not in {"resume", "non_resume", "needs_review"}:
            raise ValueError(f"无效的人工分类: {filename} -> {classification}")
        result[filename.casefold()] = row
    return result


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", suffix=".tmp", dir=path.parent, delete=False
    ) as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
        temp_path = Path(stream.name)
    temp_path.replace(path)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalized_stem(value: str | Path) -> str:
    stem = Path(value).stem.casefold()
    return re.sub(r"[\W_]+", "", stem, flags=re.UNICODE)


def compact_text(value: str) -> str:
    return re.sub(r"\s+", "", str(value or "")).casefold()


def text_ngrams(value: str, width: int = 3, limit: int = 30000) -> set[str]:
    text = compact_text(value)[:limit]
    if len(text) < width:
        return {text} if text else set()
    return {text[index : index + width] for index in range(len(text) - width + 1)}


def jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def extract_contacts(text: str) -> tuple[set[str], set[str]]:
    phones = {re.sub(r"\D", "", match.group(0))[-11:] for match in PHONE_RE.finditer(text)}
    emails = {match.group(0).casefold() for match in EMAIL_RE.finditer(text)}
    return {item for item in phones if len(item) == 11}, emails


def docx_text(path: Path) -> str:
    try:
        with zipfile.ZipFile(path) as archive:
            xml = archive.read("word/document.xml")
    except (OSError, KeyError, zipfile.BadZipFile):
        return ""
    root = ElementTree.fromstring(xml)
    chunks: list[str] = []
    for node in root.iter():
        local = node.tag.rsplit("}", 1)[-1]
        if local == "t" and node.text:
            chunks.append(node.text)
        elif local in {"p", "tr"}:
            chunks.append("\n")
        elif local in {"tab", "br"}:
            chunks.append(" ")
    return re.sub(r"\n{3,}", "\n\n", "".join(chunks)).strip()


def pdf_profile(path: Path) -> dict[str, Any]:
    profile: dict[str, Any] = {
        "page_count": 0,
        "text_chars": 0,
        "image_page_count": 0,
        "text_layer_status": "unavailable" if fitz is None else "unknown",
        "text": "",
        "error": "",
    }
    if fitz is None:
        return profile
    try:
        with fitz.open(path) as document:
            texts: list[str] = []
            image_pages = 0
            for page in document:
                text = page.get_text("text") or ""
                texts.append(text)
                if page.get_images(full=True):
                    image_pages += 1
            joined = "\n".join(texts).strip()
            profile.update(
                page_count=document.page_count,
                text_chars=len(compact_text(joined)),
                image_page_count=image_pages,
                text_layer_status=(
                    "low_text"
                    if len(compact_text(joined)) < max(80, document.page_count * 40)
                    else "readable"
                ),
                text=joined,
            )
    except Exception as exc:  # map creation must retain unreadable files
        profile.update(text_layer_status="unreadable", error=f"{type(exc).__name__}: {exc}")
    return profile


def load_gpt_index(gpt_dir: Path) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    by_source_name: dict[str, dict[str, Any]] = {}
    by_source_hash: dict[str, dict[str, Any]] = {}
    for path in sorted(gpt_dir.glob("*.json")):
        payload = read_json(path)
        if not payload.get("schema_version"):
            continue
        base = (payload.get("structured_data") or {}).get("base_info") or {}
        resumes = (payload.get("structured_data") or {}).get("resumes") or []
        languages = [
            str(item.get("resume_language") or item.get("resume_languge") or "").strip()
            for item in resumes
            if isinstance(item, dict)
        ]
        sources = (payload.get("source") or {}).get("source_files") or []
        group = {
            "json_path": str(path.resolve()),
            "json_filename": path.name,
            "candidate_name": str(base.get("full_name") or ""),
            "phone": str(base.get("phone") or ""),
            "email": str(base.get("email") or ""),
            "languages": [value for value in languages if value],
            "source_count": len(sources),
            "quality_status": str((payload.get("quality") or {}).get("quality_status") or ""),
            "warnings": list((payload.get("quality") or {}).get("warnings") or []),
        }
        for source in sources:
            name = str(source.get("filename") or source.get("pdf_filename") or "")
            digest = str(source.get("sha256") or "").casefold()
            if name:
                by_source_name[name.casefold()] = group
            if digest:
                by_source_hash[digest] = group
    return by_source_name, by_source_hash


def load_old_index(old_dir: Path) -> dict[str, list[str]]:
    by_source_name: dict[str, list[str]] = defaultdict(list)
    for path in sorted(old_dir.glob("*.json")):
        try:
            payload = read_json(path)
        except (OSError, json.JSONDecodeError):
            continue
        if not payload.get("schema_version"):
            continue
        source = payload.get("source") or {}
        source_path = str(source.get("original_path") or source.get("path") or "")
        if source_path:
            by_source_name[Path(source_path).name.casefold()].append(str(path.resolve()))
    return by_source_name


def manifest_projection(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "index": row.get("序号"),
        "relative_path": str(row.get("相对路径") or ""),
        "filename": str(row.get("文件名") or ""),
        "original_path": str(row.get("source_path") or row.get("完整绝对路径") or ""),
        "download_date": str(row.get("download_date") or row.get("修改日期") or ""),
        "is_resume": row.get("is_resume"),
        "has_contact": row.get("has_contact"),
        "candidate_name": str(row.get("candidate_name") or ""),
        "phone": str(row.get("phone") or ""),
        "email": str(row.get("email") or ""),
        "status": str(row.get("status") or ""),
        "non_resume_reason": str(row.get("non_resume_reason") or ""),
        "html_filename": str(row.get("html_filename") or ""),
    }


def match_manifest(
    pdf: Path,
    digest: str,
    by_name: dict[str, list[dict[str, Any]]],
    by_html_stem: dict[str, list[dict[str, Any]]],
    by_path_hash: dict[str, list[dict[str, Any]]],
) -> tuple[list[dict[str, Any]], str, str]:
    exact = by_name.get(pdf.name.casefold(), [])
    candidates = exact
    method = "filename_unique" if len(exact) == 1 else "filename_duplicate" if exact else ""
    suffix_match = HASH_SUFFIX_RE.search(pdf.stem)
    if not candidates and suffix_match:
        candidates = by_html_stem.get(pdf.stem.casefold(), []) or by_path_hash.get(
            suffix_match.group("hash").casefold(), []
        )
        if not candidates:
            original_stem = pdf.stem[: suffix_match.start()]
            candidates = by_name.get(f"{original_stem}{pdf.suffix}".casefold(), [])
        method = "manifest_path_hash_suffix"
    if not candidates:
        return [], "unmatched", "needs_review"
    if len(candidates) == 1:
        return [manifest_projection(candidates[0])], method, "confirmed"

    content_matches: list[dict[str, Any]] = []
    for row in candidates:
        source = Path(str(row.get("source_path") or row.get("完整绝对路径") or ""))
        if not source.is_file():
            continue
        try:
            if source.stat().st_size == pdf.stat().st_size and sha256_file(source) == digest:
                content_matches.append(row)
        except OSError:
            continue
    if content_matches:
        # Multiple original paths with identical bytes are all retained as provenance.
        return [manifest_projection(row) for row in content_matches], "content_sha256", "confirmed"
    return [manifest_projection(row) for row in candidates], method, "needs_review"


def language_hints(value: str) -> set[str]:
    text = value.casefold()
    hints: set[str] = set()
    if re.search(r"日文|日本語|履歴|\.jp\b|jpn|japanese", text):
        hints.add("ja")
    if re.search(r"英文|english|\.en\b", text):
        hints.add("en")
    if re.search(r"德文|german|deutsch|\.de\b", text):
        hints.add("de")
    if re.search(r"中文|chinese|\.cn\b", text):
        hints.add("zh")
    return hints


def word_pair_score(
    pdf: Path,
    pdf_text: str,
    gpt: dict[str, Any] | None,
    docx: Path,
    word_text: str,
) -> tuple[float, dict[str, Any]]:
    stem_ratio = SequenceMatcher(None, normalized_stem(pdf), normalized_stem(docx)).ratio()
    pdf_grams = text_ngrams(pdf_text)
    word_grams = text_ngrams(word_text)
    text_score = jaccard(pdf_grams, word_grams)
    pdf_phones, pdf_emails = extract_contacts(pdf_text)
    word_phones, word_emails = extract_contacts(word_text)
    phone_match = bool(pdf_phones & word_phones)
    email_match = bool(pdf_emails & word_emails)
    candidate_match = False
    gpt_contact_match = False
    if gpt:
        candidate = compact_text(str(gpt.get("candidate_name") or ""))
        candidate_match = bool(candidate and candidate in compact_text(word_text + " " + docx.stem))
        gpt_phone = re.sub(r"\D", "", str(gpt.get("phone") or ""))[-11:]
        gpt_email = str(gpt.get("email") or "").casefold()
        gpt_contact_match = bool(
            (gpt_phone and gpt_phone in word_phones)
            or (gpt_email and gpt_email in word_emails)
        )
    language_match = bool(language_hints(pdf.name) & language_hints(docx.name))
    score = (
        text_score * 70
        + stem_ratio * 12
        + (24 if phone_match or email_match else 0)
        + (24 if gpt_contact_match else 0)
        + (12 if candidate_match else 0)
        + (5 if language_match else 0)
    )
    evidence = {
        "score": round(score, 4),
        "pdf_word_text_jaccard": round(text_score, 4),
        "stem_similarity": round(stem_ratio, 4),
        "phone_match": phone_match,
        "email_match": email_match,
        "gpt_contact_match": gpt_contact_match,
        "candidate_name_match": candidate_match,
        "language_hint_match": language_match,
    }
    return score, evidence


def assign_renamed_words(
    pdf_records: list[dict[str, Any]],
    word_files: list[Path],
) -> list[dict[str, Any]]:
    assigned_word_names = {
        Path(str(record.get("word_path") or "")).name.casefold()
        for record in pdf_records
        if record.get("word_path")
    }
    unmatched_records = [record for record in pdf_records if not record.get("word_path")]
    unmatched_words = [path for path in word_files if path.name.casefold() not in assigned_word_names]
    word_texts = {path: docx_text(path) for path in unmatched_words}
    ranked: list[tuple[float, str, str, dict[str, Any], dict[str, Any], Path]] = []
    per_pdf_scores: dict[str, list[float]] = defaultdict(list)
    for record in unmatched_records:
        pdf = Path(record["input_path"])
        for word in unmatched_words:
            score, evidence = word_pair_score(
                pdf,
                str((record.get("pdf_profile") or {}).get("text") or ""),
                record.get("gpt_reference"),
                word,
                word_texts[word],
            )
            ranked.append((score, pdf.name.casefold(), word.name.casefold(), evidence, record, word))
            per_pdf_scores[pdf.name.casefold()].append(score)
    ranked.sort(key=lambda item: (-item[0], item[1], item[2]))
    used_pdfs: set[str] = set()
    used_words: set[str] = set()
    aliases: list[dict[str, Any]] = []
    for score, pdf_key, word_key, evidence, record, word in ranked:
        if pdf_key in used_pdfs or word_key in used_words:
            continue
        strong_identity = bool(
            evidence["gpt_contact_match"]
            or evidence["phone_match"]
            or evidence["email_match"]
            or (evidence["candidate_name_match"] and evidence["pdf_word_text_jaccard"] >= 0.15)
        )
        if score < 15 and not strong_identity:
            continue
        used_pdfs.add(pdf_key)
        used_words.add(word_key)
        alternatives = sorted(per_pdf_scores[pdf_key], reverse=True)
        gap = score - alternatives[1] if len(alternatives) > 1 else score
        evidence["next_best_score_gap"] = round(gap, 4)
        confidence = (
            "confirmed"
            if score >= 35 and (gap >= 4 or evidence["gpt_contact_match"] or evidence["phone_match"] or evidence["email_match"])
            else "needs_review"
        )
        record.update(
            word_path=str(word.resolve()),
            word_filename=word.name,
            word_match_method="content_identity_alias",
            word_match_confidence=confidence,
            word_match_evidence=evidence,
        )
        aliases.append(
            {
                "pdf_filename": Path(record["input_path"]).name,
                "word_filename": word.name,
                "confidence": confidence,
                "evidence": evidence,
            }
        )
    for record in unmatched_records:
        pdf = Path(record["input_path"])
        if pdf.name.casefold() in used_pdfs:
            continue
        record.update(
            word_match_method="unmatched",
            word_match_confidence="needs_review",
            word_match_evidence={"reason": "没有达到身份或正文相似度门槛的 Word"},
        )
        aliases.append(
            {
                "pdf_filename": pdf.name,
                "word_filename": "",
                "confidence": "needs_review",
                "evidence": record["word_match_evidence"],
            }
        )
    for word in unmatched_words:
        if word.name.casefold() in used_words:
            continue
        aliases.append(
            {
                "pdf_filename": "",
                "word_filename": word.name,
                "confidence": "orphan_word",
                "evidence": {"reason": "没有达到身份或正文相似度门槛的 PDF"},
            }
        )
    return aliases


def choose_pilot(records: list[dict[str, Any]], size: int) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    selected_ids: set[str] = set()

    def take(category: str, candidates: list[dict[str, Any]], limit: int) -> None:
        for record in sorted(candidates, key=lambda item: item["input_filename"].casefold()):
            if len(selected) >= size or limit <= 0:
                return
            record_id = record["source_sha256"]
            if record_id in selected_ids:
                continue
            selected_ids.add(record_id)
            selected.append(
                {
                    "sequence": len(selected) + 1,
                    "category": category,
                    "input_filename": record["input_filename"],
                    "input_path": record["input_path"],
                    "word_path": record.get("word_path", ""),
                    "candidate_name": (record.get("gpt_reference") or {}).get("candidate_name", ""),
                    "languages": (record.get("gpt_reference") or {}).get("languages", []),
                    "gpt_source_count": (record.get("gpt_reference") or {}).get("source_count", 0),
                    "text_layer_status": (record.get("pdf_profile") or {}).get("text_layer_status", ""),
                    "word_match_method": record.get("word_match_method", ""),
                }
            )
            limit -= 1

    take("non_resume_control", [r for r in records if r["classification"] == "non_resume"], 5)
    take("renamed_word", [r for r in records if r.get("word_match_method") != "exact_stem"], 5)
    take("low_text_or_scanned", [r for r in records if r["pdf_profile"]["text_layer_status"] != "readable"], 4)
    take("german", [r for r in records if "de" in (r.get("gpt_reference") or {}).get("languages", [])], 2)
    take("japanese", [r for r in records if "ja" in (r.get("gpt_reference") or {}).get("languages", [])], 4)
    take("english", [r for r in records if "en" in (r.get("gpt_reference") or {}).get("languages", [])], 3)
    take("multi_source_merge", [r for r in records if (r.get("gpt_reference") or {}).get("source_count", 0) > 1], 5)
    take("general_resume", [r for r in records if r["classification"] == "resume"], size)
    return selected[:size]


def main() -> int:
    args = parse_args()
    input_files = sorted(args.input_dir.glob("*.pdf"), key=lambda path: path.name.casefold())
    word_files = sorted(args.word_dir.glob("*.docx"), key=lambda path: path.name.casefold())
    manifest = read_json(args.manifest)
    if not isinstance(manifest, list):
        raise ValueError("PDF文档.json 顶层必须是数组")

    overrides = load_overrides(args.overrides)
    previous_records: dict[str, dict[str, Any]] = {}
    if args.map.is_file():
        previous_payload = read_json(args.map)
        for previous in previous_payload.get("records", []):
            if isinstance(previous, dict) and previous.get("input_path"):
                previous_records[str(previous["input_path"]).casefold()] = previous

    manifest_by_name: dict[str, list[dict[str, Any]]] = defaultdict(list)
    manifest_by_html_stem: dict[str, list[dict[str, Any]]] = defaultdict(list)
    manifest_by_path_hash: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in manifest:
        manifest_by_name[str(row.get("文件名") or "").casefold()].append(row)
        html_filename = str(row.get("html_filename") or "")
        if html_filename:
            manifest_by_html_stem[Path(html_filename).stem.casefold()].append(row)
            hash_match = HASH_SUFFIX_RE.search(Path(html_filename).stem)
            if hash_match:
                manifest_by_path_hash[hash_match.group("hash").casefold()].append(row)

    gpt_by_name, gpt_by_hash = load_gpt_index(args.gpt_dir)
    old_by_name = load_old_index(args.old_dir)
    word_by_stem = {path.stem.casefold(): path for path in word_files}

    records: list[dict[str, Any]] = []
    for sequence, pdf in enumerate(input_files, 1):
        digest = sha256_file(pdf)
        profile = pdf_profile(pdf)
        manifest_rows, manifest_method, manifest_confidence = match_manifest(
            pdf, digest, manifest_by_name, manifest_by_html_stem, manifest_by_path_hash
        )
        gpt = gpt_by_hash.get(digest) or gpt_by_name.get(pdf.name.casefold())
        manifest_resume_values = {row.get("is_resume") for row in manifest_rows}
        override = overrides.get(pdf.name.casefold())
        if override:
            classification = str(override["classification"])
            classification_reason = str(override.get("reason") or "用户人工确认")
            classification_source = "user_override"
        elif gpt:
            classification = "resume"
            classification_reason = "GPT source_files SHA-256 与当前 input 完全一致"
            classification_source = "gpt_source_sha256"
        elif manifest_resume_values == {False} or NON_RESUME_HINT_RE.search(pdf.name):
            classification = "non_resume"
            classification_reason = next(
                (row.get("non_resume_reason") for row in manifest_rows if row.get("non_resume_reason")),
                "文件名和历史清单均为非简历证据",
            )
            classification_source = "manifest_or_filename"
        else:
            classification = "needs_review"
            classification_reason = "缺少可确认的简历/非简历证据"
            classification_source = "automatic_needs_review"

        direct_word = word_by_stem.get(pdf.stem.casefold())
        source_names = {pdf.name.casefold()}
        source_names.update(str(row.get("filename") or "").casefold() for row in manifest_rows)
        old_references = sorted(
            {reference for name in source_names for reference in old_by_name.get(name, [])}
        )
        previous = previous_records.get(str(pdf.resolve()).casefold()) or {}
        processing = dict(previous.get("processing") or {})
        if not processing:
            processing = {
                "extract_status": "pending",
                "audit_status": "pending",
                "merge_status": "pending" if classification == "resume" else "not_applicable",
                "output_path": "",
            }
        if classification != "resume":
            processing.update(
                extract_status="non_resume",
                merge_status="not_applicable",
                output_path="",
            )
        record = {
            "sequence": sequence,
            "source_sha256": digest,
            "input_path": str(pdf.resolve()),
            "input_filename": pdf.name,
            "size": pdf.stat().st_size,
            "pdf_profile": {key: value for key, value in profile.items() if key != "text"},
            "_pdf_text": profile.get("text", ""),
            "manifest_match_method": manifest_method,
            "manifest_match_confidence": manifest_confidence,
            "manifest_records": manifest_rows,
            "word_path": str(direct_word.resolve()) if direct_word else "",
            "word_filename": direct_word.name if direct_word else "",
            "word_match_method": "exact_stem" if direct_word else "pending_alias_match",
            "word_match_confidence": "confirmed" if direct_word else "pending",
            "word_match_evidence": {},
            "gpt_reference": gpt or {},
            "old_references": old_references,
            "classification": classification,
            "classification_reason": classification_reason,
            "classification_source": classification_source,
            "classification_override": override or {},
            "processing": processing,
        }
        # Keep extracted PDF text in-memory for alias matching only.
        record["pdf_profile"]["text"] = record.pop("_pdf_text")
        records.append(record)

    aliases = assign_renamed_words(records, word_files)
    for record in records:
        record["pdf_profile"].pop("text", None)

    pilot = choose_pilot(records, max(1, args.pilot_size))
    summary = {
        "input_pdf_count": len(input_files),
        "word_docx_count": len(word_files),
        "manifest_record_count": len(manifest),
        "classification_counts": dict(
            sorted((key, sum(1 for row in records if row["classification"] == key)) for key in {r["classification"] for r in records})
        ),
        "manifest_match_counts": dict(
            sorted((key, sum(1 for row in records if row["manifest_match_confidence"] == key)) for key in {r["manifest_match_confidence"] for r in records})
        ),
        "word_match_method_counts": dict(
            sorted((key, sum(1 for row in records if row["word_match_method"] == key)) for key in {r["word_match_method"] for r in records})
        ),
        "word_match_confidence_counts": dict(
            sorted((key, sum(1 for row in records if row["word_match_confidence"] == key)) for key in {r["word_match_confidence"] for r in records})
        ),
        "gpt_referenced_input_count": sum(1 for row in records if row["gpt_reference"]),
        "user_override_count": sum(1 for row in records if row["classification_source"] == "user_override"),
        "old_referenced_input_count": sum(1 for row in records if row["old_references"]),
        "text_layer_counts": dict(
            sorted((key, sum(1 for row in records if row["pdf_profile"]["text_layer_status"] == key)) for key in {r["pdf_profile"]["text_layer_status"] for r in records})
        ),
        "pilot_count": len(pilot),
    }
    generated_at = datetime.now().astimezone().isoformat()
    map_payload = {
        "version": VERSION,
        "generated_at": generated_at,
        "scope": {
            "input_dir": str(args.input_dir.resolve()),
            "word_dir": str(args.word_dir.resolve()),
            "manifest_path": str(args.manifest.resolve()),
            "gpt_dir": str(args.gpt_dir.resolve()),
            "old_dir": str(args.old_dir.resolve()),
            "override_path": str(args.overrides.resolve()),
        },
        "summary": summary,
        "records": records,
    }
    alias_payload = {
        "version": VERSION,
        "generated_at": generated_at,
        "summary": {
            "alias_count": len(aliases),
            "confirmed": sum(1 for row in aliases if row["confidence"] == "confirmed"),
            "needs_review": sum(1 for row in aliases if row["confidence"] == "needs_review"),
        },
        "aliases": aliases,
    }
    pilot_payload = {
        "version": VERSION,
        "generated_at": generated_at,
        "selection_rule": "覆盖非简历、改名Word、低文字层、德/日/英、多源合并和一般中文简历",
        "count": len(pilot),
        "records": pilot,
    }
    atomic_json(args.map, map_payload)
    atomic_json(args.alias_report, alias_payload)
    atomic_json(args.pilot_report, pilot_payload)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"map={args.map.resolve()}")
    print(f"aliases={args.alias_report.resolve()}")
    print(f"pilot={args.pilot_report.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
