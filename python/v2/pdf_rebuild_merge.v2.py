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
import importlib.util
import json
import re
import shutil
import sys
import tempfile
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = _rc.project_root()
PDF_ROOT = PROJECT_ROOT / _rc.dirname("complete-transfered-htmls") / "pdf"
DEFAULT_MAP = PDF_ROOT / "rebuild-work" / "pdf_rebuild_map.v2.json"
DEFAULT_SOURCE_ROOT = PDF_ROOT / "rebuild-work" / "json-by-source"
DEFAULT_OUTPUT_ROOT = PDF_ROOT / "rebuild-work" / "json-by-candidate"
DEFAULT_REPORT = PDF_ROOT / "rebuild-reports" / "pdf_candidate_merge.v2.json"
DEFAULT_TRANSLATION_JSON = PDF_ROOT / "rebuild-reports" / "pdf_translation_queue.v2.json"
DEFAULT_TRANSLATION_CSV = PDF_ROOT / "rebuild-reports" / "pdf_translation_queue.v2.csv"
DEFAULT_GPT_REVIEW_JSON = PDF_ROOT / "rebuild-reports" / "pdf_gpt_translation_review.v2.json"
DEFAULT_GPT_REVIEW_CSV = PDF_ROOT / "rebuild-reports" / "pdf_gpt_translation_review.v2.csv"
DEFAULT_GPT_REVIEW_OVERRIDES = PDF_ROOT / "rebuild-reports" / "pdf_gpt_review_overrides.v2.json"
VERSION = "pdf-rebuild-merge-v2.0.0"

EMAIL_RE = re.compile(r"[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}", re.I)
NAME_NOISE_RE = re.compile(
    r"履歴書|職務経歴書|日本语|日本語|基本情報|个人简历|求职|resume|curriculum|vitae|看图王|"
    r"^(?:address|job preferences?|personal details?|profile|contact|name|住所|ふりがな)$",
    re.I,
)
INVALID_FILENAME_RE = re.compile(r'[\\/:*?"<>|\r\n\t]+')


def load_parser_module():
    path = _rc.PYTHON_DIR / "v2" / "c_resume_html_to_json_common.v2.py"
    spec = importlib.util.spec_from_file_location("_pdf_merge_parser_v2", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"无法加载 {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


PARSER = load_parser_module()
GPT_REVIEW_OVERRIDES: dict[str, dict[str, Any]] = {}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="把 PDF v2 逐源 JSON 保守合并为候选人级 JSON" " / Conservatively merge PDF v2 per-source JSON into candidate-level JSON / PDF v2 の元ファイルごとの JSON を、保守的に候補者単位の JSON へ統合する")
    parser.add_argument("--map", type=Path, default=DEFAULT_MAP)
    parser.add_argument("--source-root", type=Path, default=DEFAULT_SOURCE_ROOT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--translation-json", type=Path, default=DEFAULT_TRANSLATION_JSON)
    parser.add_argument("--translation-csv", type=Path, default=DEFAULT_TRANSLATION_CSV)
    parser.add_argument("--gpt-review-json", type=Path, default=DEFAULT_GPT_REVIEW_JSON)
    parser.add_argument("--gpt-review-csv", type=Path, default=DEFAULT_GPT_REVIEW_CSV)
    parser.add_argument("--gpt-review-overrides", type=Path, default=DEFAULT_GPT_REVIEW_OVERRIDES)
    parser.add_argument("--replace", action="store_true", help="替换既有的本脚本候选人暂存目录" " / Replace this script's existing candidate staging directory / このスクリプトの既存の候補者ステージングディレクトリを置き換える")
    return parser.parse_args()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".tmp", dir=path.parent, delete=False) as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
        temporary = Path(stream.name)
    temporary.replace(path)


def text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def normalize_name(value: Any) -> str:
    value = unicodedata.normalize("NFKC", text(value)).casefold()
    value = re.sub(r"^(?:姓名|氏名|name)[:：\s]*", "", value, flags=re.I)
    return re.sub(r"[^0-9a-z\u3400-\u9fff\u3040-\u30ff]", "", value)


def valid_name(value: Any) -> bool:
    value = text(value)
    normalized = normalize_name(value)
    return bool(normalized) and len(normalized) <= 40 and not NAME_NOISE_RE.search(value)


def normalize_phone(value: Any) -> str:
    digits = re.sub(r"\D", "", text(value))
    if len(digits) < 8:
        return ""
    if digits.startswith("86") and len(digits) == 13:
        digits = digits[2:]
    return digits


def emails(value: Any) -> set[str]:
    return {match.group(0).casefold() for match in EMAIL_RE.finditer(text(value))}


def identity(payload: dict[str, Any]) -> dict[str, Any]:
    base = (payload.get("structured_data") or {}).get("base_info") or {}
    phone = normalize_phone(base.get("phone"))
    return {
        "name": text(base.get("full_name")),
        "name_key": normalize_name(base.get("full_name")),
        "phone": phone,
        "emails": sorted(emails(base.get("email"))),
    }


def language(resume: dict[str, Any]) -> str:
    value = text(resume.get("resume_language") or resume.get("resume_languge")).casefold()
    return {"jp": "ja", "jpn": "ja", "ch": "zh", "cn": "zh", "eng": "en"}.get(value, value or "zh")


def nonempty_count(value: Any) -> int:
    if isinstance(value, dict):
        return sum(nonempty_count(item) for item in value.values())
    if isinstance(value, list):
        return sum(nonempty_count(item) for item in value)
    return int(bool(text(value)))


def resume_score(resume: dict[str, Any]) -> tuple[int, int, int]:
    structural = (
        30 * len(resume.get("work_experiences") or [])
        + 25 * len(resume.get("education_list") or [])
        + 8 * len(resume.get("project_list") or [])
        + 5 * len(resume.get("language_list") or [])
        + 3 * len(resume.get("skills_list") or [])
    )
    return structural, nonempty_count(resume), len(json.dumps(resume, ensure_ascii=False))


def resume_quality_score(resume: dict[str, Any]) -> tuple[int, int, int, int]:
    """Rank semantic usability, not merely the number of parsed rows."""
    structural, populated, serialized = resume_score(resume)
    penalty = 0
    base = resume.get("base_info") or {}
    name = text(base.get("full_name"))
    if not name or re.search(
        r"^(?:married|male|female|ふりがな|フリガナ|氏名|姓名|name|resume|履歴書)$|@|\d{6,}",
        name, re.I,
    ):
        penalty += 300
    for row in resume.get("work_experiences") or []:
        if not isinstance(row, dict):
            penalty += 200
            continue
        company, position = text(row.get("company_name")), text(row.get("position"))
        if not company:
            penalty += 120
        if len(company) > 90 or re.search(
            r"^(?:company\s*[：:]|in corp$|which inc$|the prag$|负责|参与|协助)|"
            r"(?:工作描述|工作职责|project description|self-assessment)", company, re.I,
        ):
            penalty += 180
        if len(position) > 140 or re.search(r"^(?:负责|处理|通过|协助).{25,}", position):
            penalty += 100
    for row in resume.get("education_list") or []:
        if not isinstance(row, dict):
            penalty += 200
            continue
        school = text(row.get("school_name"))
        if not school:
            penalty += 120
        if len(school) > 100 or re.search(
            r"^(?:degree|\d{1,2}[.、])|(?:講師|教师|秘書|秘书|グループメンバー|项目组|工作经历|自我评价)",
            school, re.I,
        ):
            penalty += 180
        for field in ("school_start_ym", "school_end_ym"):
            if re.search(r"年\d{2}月20日$", text(row.get(field))):
                penalty += 60
    return structural - penalty, -penalty, populated, serialized


def substantive_chinese(payload: dict[str, Any], resume: dict[str, Any]) -> bool:
    if language(resume) != "zh":
        return False
    return bool(
        resume.get("work_experiences")
        or resume.get("education_list")
        or resume.get("project_list")
        or resume.get("expected_list")
        or len(text((resume.get("base_info") or {}).get("pr"))) >= 40
    )


def native_chinese_source(payload: dict[str, Any]) -> bool:
    resumes = [row for row in ((payload.get("structured_data") or {}).get("resumes") or []) if isinstance(row, dict)]
    langs = {language(row) for row in resumes}
    if langs == {"zh"}:
        return True
    source = payload.get("source") or {}
    filename = text(source.get("filename") or source.get("pdf_filename") or source.get("path"))
    return bool(re.search(r"中文|汉语|漢語|中日|chinese|(?<![a-z])cn(?![a-z])", filename, re.I))


class UnionFind:
    def __init__(self, size: int):
        self.parent = list(range(size))

    def find(self, item: int) -> int:
        while self.parent[item] != item:
            self.parent[item] = self.parent[self.parent[item]]
            item = self.parent[item]
        return item

    def union(self, left: int, right: int) -> None:
        left_root, right_root = self.find(left), self.find(right)
        if left_root != right_root:
            self.parent[right_root] = left_root


def contacts_overlap(left: dict[str, Any], right: dict[str, Any]) -> list[str]:
    evidence: list[str] = []
    if left["phone"] and left["phone"] == right["phone"]:
        evidence.append("same_phone")
    if set(left["emails"]) & set(right["emails"]):
        evidence.append("same_email")
    return evidence


def contacts_conflict(left: dict[str, Any], right: dict[str, Any]) -> bool:
    phone_conflict = bool(left["phone"] and right["phone"] and left["phone"] != right["phone"])
    email_conflict = bool(left["emails"] and right["emails"] and not (set(left["emails"]) & set(right["emails"])))
    return phone_conflict and email_conflict


def safe_filename(value: str, fallback: str) -> str:
    value = INVALID_FILENAME_RE.sub("_", text(value)).strip(" .") or fallback
    return value[:120].rstrip(" .")


def dedupe_source_files(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for record in records:
        source = record["payload"].get("source") or {}
        rows = source.get("source_files") or [{
            "input_path": source.get("path"),
            "filename": source.get("filename"),
            "sha256": record["map"].get("source_sha256"),
            "size": source.get("size"),
            "word_path": source.get("word_path"),
        }]
        for row in rows:
            if not isinstance(row, dict):
                continue
            key = (text(row.get("sha256")).casefold(), text(row.get("input_path")).casefold())
            if key in seen:
                continue
            seen.add(key)
            output.append(copy.deepcopy(row))
    return output


def choose_resume(records: list[dict[str, Any]], lang: str) -> tuple[dict[str, Any] | None, str]:
    candidates: list[tuple[tuple[int, int, int], dict[str, Any], dict[str, Any]]] = []
    for record in records:
        for resume in ((record["payload"].get("structured_data") or {}).get("resumes") or []):
            if not isinstance(resume, dict) or language(resume) != lang:
                continue
            if lang == "zh" and not native_chinese_source(record["payload"]):
                continue
            score = resume_score(resume)
            if lang == "zh" and substantive_chinese(record["payload"], resume):
                score = (score[0] + 1000, score[1], score[2])
            candidates.append((score, record, resume))
    if not candidates:
        return None, ""
    candidates.sort(key=lambda row: row[0], reverse=True)
    selected_record, selected = candidates[0][1], copy.deepcopy(candidates[0][2])
    selected.pop("resume_languge", None)
    selected["resume_language"] = lang
    # Identity blanks and entirely absent sections may be completed from another
    # source of the same language. Nonempty lists are never concatenated here.
    for _, _, fallback in candidates[1:]:
        base = selected.setdefault("base_info", {})
        for field, value in (fallback.get("base_info") or {}).items():
            if not text(base.get(field)) and text(value):
                base[field] = copy.deepcopy(value)
        for collection in PARSER.RESUME_LISTS:
            if not selected.get(collection) and fallback.get(collection):
                selected[collection] = copy.deepcopy(fallback[collection])
    return selected, str(selected_record["path"])


def normalize_external_resume(resume: dict[str, Any], lang: str) -> dict[str, Any]:
    base = PARSER.normalize_row(resume.get("base_info") or {}, PARSER.BASE_FIELDS)
    legacy_expected = resume.get("expected_info")
    expected = resume.get("expected_list")
    if not isinstance(expected, list):
        expected = legacy_expected if isinstance(legacy_expected, list) else ([legacy_expected] if isinstance(legacy_expected, dict) else [])
    normalized = {
        "resume_language": lang,
        "base_info": base,
        "expected_list": [PARSER.normalize_row(row, PARSER.EXPECTED_FIELDS) for row in expected if isinstance(row, dict)],
    }
    for collection in PARSER.RESUME_LISTS:
        if collection == "expected_list":
            continue
        normalized[collection] = [
            PARSER.normalize_row(
                row,
                tuple(field for field in PARSER.COLLECTION_FIELDS[collection] if field != "company_nature"),
            )
            for row in (resume.get(collection) or [])
            if isinstance(row, dict)
        ]
    return normalized


def gpt_chinese_fallback(records: list[dict[str, Any]], identity_value: dict[str, Any]) -> tuple[dict[str, Any] | None, str, bool]:
    references = [row["map"].get("gpt_reference") or {} for row in records]
    paths = {text(reference.get("json_path")) for reference in references if text(reference.get("json_path"))}
    expected_counts = {int(reference.get("source_count") or 0) for reference in references}
    if len(paths) != 1 or expected_counts != {len(records)}:
        return None, "", False
    if any(reference.get("quality_status") not in {"", "passed"} or reference.get("warnings") for reference in references):
        return None, "", False
    path = Path(next(iter(paths)))
    if not path.is_file():
        return None, "", False
    payload = read_json(path)
    gpt_identity = identity(payload)
    single_source_hash_bound = len(records) == 1 and expected_counts == {1}
    if not single_source_hash_bound and not contacts_overlap(identity_value, gpt_identity) and not (
        identity_value["name_key"] and identity_value["name_key"] == gpt_identity["name_key"]
    ):
        return None, "", False
    override = GPT_REVIEW_OVERRIDES.get(str(path.resolve()).casefold())
    if override and isinstance(override.get("corrected_resume"), dict):
        corrected = normalize_external_resume(override["corrected_resume"], "zh")
        if substantive_chinese({"structured_data": {"resumes": [corrected]}}, corrected):
            return corrected, f"gpt_reference:{path}", False
    candidates = []
    for resume in ((payload.get("structured_data") or {}).get("resumes") or []):
        if isinstance(resume, dict) and language(resume) == "zh":
            normalized = normalize_external_resume(resume, "zh")
            if substantive_chinese({"structured_data": {"resumes": [normalized]}}, normalized):
                candidates.append(normalized)
    if not candidates:
        return None, "", False
    selected = max(candidates, key=resume_score)
    gpt_foreign_rows = [
        normalize_external_resume(resume, language(resume))
        for resume in ((payload.get("structured_data") or {}).get("resumes") or [])
        if isinstance(resume, dict) and language(resume) not in {"", "zh"}
    ]
    structure_mismatch = False
    if gpt_foreign_rows:
        richest = max(gpt_foreign_rows, key=resume_score)
        if abs(len(selected.get("work_experiences") or []) - len(richest.get("work_experiences") or [])) > 2:
            structure_mismatch = True
        if abs(len(selected.get("education_list") or []) - len(richest.get("education_list") or [])) > 3:
            structure_mismatch = True
    return selected, f"gpt_reference:{path}", structure_mismatch


def empty_chinese(identity_value: dict[str, Any]) -> dict[str, Any]:
    base = PARSER.empty_object(PARSER.BASE_FIELDS)
    base["full_name"] = identity_value["name"]
    base["phone"] = identity_value["phone"]
    base["email"] = identity_value["emails"][0] if identity_value["emails"] else ""
    return {"resume_language": "zh", "base_info": base, **{name: [] for name in PARSER.RESUME_LISTS}}


def parse_date(value: Any) -> datetime:
    value = text(value)
    if not value:
        return datetime.min
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        pass
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return datetime.min


def build_candidate(records: list[dict[str, Any]], evidence: list[str]) -> tuple[dict[str, Any], dict[str, Any]]:
    records = sorted(
        records,
        key=lambda row: (parse_date((row["payload"].get("dates") or {}).get("resume_updated_date")), row["path"].name),
        reverse=True,
    )
    identities = [row["identity"] for row in records]
    names = [row for row in identities if valid_name(row["name"])]
    if not names:
        for record in records:
            reference_name = text((record["map"].get("gpt_reference") or {}).get("candidate_name"))
            if valid_name(reference_name):
                names.append({"name": reference_name, "name_key": normalize_name(reference_name), "phone": "", "emails": []})
    names = names or identities
    name_identity = max(
        names,
        key=lambda row: (
            bool(re.fullmatch(r"[\u3400-\u9fff]{2,4}", row["name_key"])),
            bool(re.search(r"[\u3400-\u9fff]", row["name_key"])),
            bool(row["phone"] or row["emails"]),
            -len(row["name_key"]),
        ),
    )
    phone_counts = Counter(row["phone"] for row in identities if row["phone"])
    email_counts = Counter(email for row in identities for email in row["emails"])
    identity_value = {
        "name": name_identity["name"],
        "name_key": name_identity["name_key"],
        "phone": phone_counts.most_common(1)[0][0] if phone_counts else "",
        "emails": [email_counts.most_common(1)[0][0]] if email_counts else [],
    }
    chosen: list[dict[str, Any]] = []
    selected_sources: dict[str, str] = {}
    zh, zh_source = choose_resume(records, "zh")
    foreign_languages = sorted({language(resume) for row in records for resume in ((row["payload"].get("structured_data") or {}).get("resumes") or []) if isinstance(resume, dict)} - {"zh", ""})
    gpt_translation_structure_mismatch = False
    gpt_zh, gpt_source, gpt_mismatch = gpt_chinese_fallback(records, identity_value)
    if gpt_zh is not None and (zh is None or resume_quality_score(gpt_zh) > resume_quality_score(zh)):
        zh, zh_source = gpt_zh, gpt_source
        gpt_translation_structure_mismatch = gpt_mismatch
    gpt_translation_used = bool(zh_source.startswith("gpt_reference:"))
    translation_needed = bool(foreign_languages and zh is None)
    if zh is None:
        zh = empty_chinese(identity_value)
    chosen.append(zh)
    if zh_source:
        selected_sources["zh"] = zh_source
    for lang in foreign_languages:
        selected, selected_source = choose_resume(records, lang)
        if selected is not None:
            chosen.append(selected)
            selected_sources[lang] = selected_source

    # Source-backed candidate identity is copied to language variants only where
    # a parser left the value blank. Existing source-language spellings survive.
    for resume in chosen:
        base = resume.setdefault("base_info", PARSER.empty_object(PARSER.BASE_FIELDS))
        for field in PARSER.BASE_FIELDS:
            base.setdefault(field, "")
        if not text(base.get("full_name")):
            base["full_name"] = identity_value["name"]
        if not text(base.get("phone")):
            base["phone"] = identity_value["phone"]
        if not text(base.get("email")) and identity_value["emails"]:
            base["email"] = identity_value["emails"][0]

    primary = chosen[0]
    source_files = dedupe_source_files(records)
    seed = copy.deepcopy(records[0]["payload"])
    source = copy.deepcopy(seed.get("source") or {})
    source["source_files"] = source_files
    source["merge_note"] = "候选人级保守合并：联系方式为强证据；GPT 分组仅在姓名一致且无联系方式冲突时辅助。"
    source["merged_source_count"] = len(source_files)
    dates = [row["payload"].get("dates") or {} for row in records]
    updated_values = [text(row.get("resume_updated_date")) for row in dates if text(row.get("resume_updated_date"))]
    download_values = [text(row.get("resume_download_date")) for row in dates if text(row.get("resume_download_date"))]
    created_values = [text(row.get("sys_created_date")) for row in dates if text(row.get("sys_created_date"))]
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    expected = copy.deepcopy((primary.get("expected_list") or [{}])[0] if primary.get("expected_list") else PARSER.empty_object(PARSER.EXPECTED_FIELDS))
    structured = {
        "base_info": copy.deepcopy(primary.get("base_info") or {}),
        "expected_info": expected,
        "current_info": PARSER.latest_work(primary.get("work_experiences") or []),
        "education_info": PARSER.highest_education(primary.get("education_list") or []),
        "resumes": chosen,
    }
    warnings = sorted({
        warning
        for row in records
        for warning in ((row["payload"].get("quality") or {}).get("warnings") or [])
        if warning != "foreign_translation_missing" and not str(warning).startswith("reference_identity_difference:")
    })
    if primary.get("work_experiences") or primary.get("education_list"):
        warnings = [warning for warning in warnings if warning != "resume_structure_incomplete"]
    if translation_needed:
        warnings.append("foreign_translation_missing")
    if gpt_translation_structure_mismatch:
        warnings.append("gpt_translation_structure_mismatch")
    # Preserve complete independent source text from every physical PDF/Word
    # conversion. Do not regenerate raw_text from selected JSON fields.
    raw_blocks = []
    for row in records:
        value = str(row["payload"].get("raw_text") or "").strip()
        if value:
            raw_blocks.append(f"===== SOURCE: {row['map']['input_filename']} =====\n{value}")
    raw_text = "\n\n".join(dict.fromkeys(raw_blocks)).strip()
    source_hashes = sorted(text(row.get("sha256")) for row in source_files if text(row.get("sha256")))
    record_id = hashlib.sha256("|".join(source_hashes).encode("utf-8")).hexdigest()
    payload = {
        "schema_version": seed.get("schema_version") or "complete-v1",
        "record_id": record_id,
        "source": source,
        "dates": {
            "resume_updated_date": max(updated_values, key=parse_date) if updated_values else now,
            "resume_download_date": max(download_values, key=parse_date) if download_values else (max(updated_values, key=parse_date) if updated_values else now),
            "resume_updated_date_source": "合并来源中的最新简历日期",
            "resume_download_date_source": "合并来源中的最新历史落地日期",
            "sys_created_date": min(created_values, key=parse_date) if created_values else now,
            "sys_updated_date": now,
        },
        "extraction": {
            **copy.deepcopy(seed.get("extraction") or {}),
            "status": "needs_review" if warnings else "success",
            "merge_version": VERSION,
            "candidate_group_evidence": sorted(set(evidence)),
            "selected_language_sources": selected_sources,
            "raw_text_source": "merged_independent_source_text",
        },
        "classification": copy.deepcopy(seed.get("classification") or {}),
        "structured_data": structured,
        "raw_text": raw_text,
        "quality": {
            "full_name": text((primary.get("base_info") or {}).get("full_name")),
            "has_work": bool(primary.get("work_experiences")),
            "work_count": len(primary.get("work_experiences") or []),
            "has_education": bool(primary.get("education_list")),
            "education_count": len(primary.get("education_list") or []),
            "raw_text_length": len(raw_text),
            "quality_status": "needs_review" if warnings else "candidate_passed",
            "warnings": warnings,
        },
    }
    detail = {
        "record_id": record_id,
        "candidate_name": payload["quality"]["full_name"],
        "phone": text((primary.get("base_info") or {}).get("phone")),
        "email": text((primary.get("base_info") or {}).get("email")),
        "source_count": len(records),
        "languages": [language(row) for row in chosen],
        "translation_needed": translation_needed,
        "gpt_translation_used": gpt_translation_used,
        "gpt_translation_structure_mismatch": gpt_translation_structure_mismatch,
        "warnings": warnings,
        "evidence": sorted(set(evidence)),
        "selected_language_sources": selected_sources,
        "input_files": [row["map"]["input_filename"] for row in records],
    }
    return payload, detail


def write_translation_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    import csv

    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8-sig", newline="", suffix=".tmp", dir=path.parent, delete=False) as stream:
        writer = csv.DictWriter(stream, fieldnames=["序号", "候选人", "联系方式", "待翻译语言", "来源数量", "来源PDF", "候选JSON"])
        writer.writeheader()
        writer.writerows(rows)
        temporary = Path(stream.name)
    temporary.replace(path)


def main() -> int:
    global GPT_REVIEW_OVERRIDES
    cfg = parse_args()
    GPT_REVIEW_OVERRIDES = {}
    if cfg.gpt_review_overrides.is_file():
        override_payload = read_json(cfg.gpt_review_overrides)
        GPT_REVIEW_OVERRIDES = {
            str(Path(row["gpt_json"]).resolve()).casefold(): row
            for row in (override_payload.get("records") or [])
            if isinstance(row, dict) and text(row.get("gpt_json")) and isinstance(row.get("corrected_resume"), dict)
        }
    mapping = read_json(cfg.map)
    records: list[dict[str, Any]] = []
    missing: list[dict[str, str]] = []
    fallback_index: dict[str, Path] = {}
    for candidate_path in cfg.source_root.glob("*.json"):
        try:
            candidate_payload = read_json(candidate_path)
        except Exception:
            continue
        candidate_source = text((candidate_payload.get("source") or {}).get("path")).casefold()
        if candidate_source:
            fallback_index[candidate_source] = candidate_path
    map_output_fallbacks: list[dict[str, str]] = []
    for map_record in mapping.get("records") or []:
        if map_record.get("classification") != "resume":
            continue
        staging = ((map_record.get("processing") or {}).get("staging_outputs") or [])
        path = Path(staging[0]) if staging else Path()
        if not staging or not path.is_file():
            path = fallback_index.get(text(map_record.get("input_path")).casefold(), Path())
            if path.is_file():
                map_output_fallbacks.append({
                    "input_filename": map_record.get("input_filename", ""),
                    "resolved_staging_output": str(path),
                })
            else:
                missing.append({"input_filename": map_record.get("input_filename", ""), "reason": "staging_not_found"})
                continue
        payload = read_json(path)
        records.append({"path": path, "payload": payload, "map": map_record, "identity": identity(payload)})
    if missing:
        raise SystemExit(f"逐源 JSON 不完整，拒绝合并: {len(missing)}")

    uf = UnionFind(len(records))
    evidence_by_pair: dict[tuple[int, int], list[str]] = {}
    contact_index: dict[tuple[str, str], int] = {}
    for index, record in enumerate(records):
        ident = record["identity"]
        keys = []
        if ident["phone"]:
            keys.append(("phone", ident["phone"]))
        keys.extend(("email", email) for email in ident["emails"])
        for key in keys:
            if key in contact_index:
                other = contact_index[key]
                uf.union(index, other)
                evidence_by_pair[(min(index, other), max(index, other))] = [f"same_{key[0]}"]
            else:
                contact_index[key] = index

    gpt_groups: dict[str, list[int]] = defaultdict(list)
    for index, record in enumerate(records):
        gpt_path = text((record["map"].get("gpt_reference") or {}).get("json_path")).casefold()
        if gpt_path:
            gpt_groups[gpt_path].append(index)
    rejected_gpt_pairs: list[dict[str, Any]] = []
    for gpt_path, indexes in gpt_groups.items():
        for offset, left_index in enumerate(indexes):
            for right_index in indexes[offset + 1:]:
                left, right = records[left_index]["identity"], records[right_index]["identity"]
                overlap = contacts_overlap(left, right)
                same_name = bool(left["name_key"] and left["name_key"] == right["name_key"] and valid_name(left["name"]) and valid_name(right["name"]))
                if overlap or (same_name and not contacts_conflict(left, right)):
                    uf.union(left_index, right_index)
                    pair_evidence = overlap + (["same_name", "same_gpt_group"] if same_name else ["same_gpt_group"])
                    evidence_by_pair[(min(left_index, right_index), max(left_index, right_index))] = pair_evidence
                else:
                    rejected_gpt_pairs.append({
                        "gpt_json": gpt_path,
                        "left": records[left_index]["map"]["input_filename"],
                        "right": records[right_index]["map"]["input_filename"],
                        "left_identity": left,
                        "right_identity": right,
                        "reason": "identity_not_verified_or_contact_conflict",
                    })

    grouped: dict[int, list[int]] = defaultdict(list)
    for index in range(len(records)):
        grouped[uf.find(index)].append(index)

    target = cfg.output_root.resolve()
    if target.exists() and any(target.iterdir()):
        if not cfg.replace:
            raise SystemExit(f"输出目录非空，拒绝覆盖: {target}")
        # Exact, project-scoped generated target; replacement is opt-in.
        shutil.rmtree(target)
    target.mkdir(parents=True, exist_ok=True)

    allocated: set[str] = set()
    details: list[dict[str, Any]] = []
    translations: list[dict[str, Any]] = []
    gpt_reviews: list[dict[str, Any]] = []
    for group_indexes in sorted(grouped.values(), key=lambda rows: min(rows)):
        group_records = [records[index] for index in group_indexes]
        group_evidence = [evidence for pair, evidences in evidence_by_pair.items() if pair[0] in group_indexes and pair[1] in group_indexes for evidence in evidences]
        if len(group_indexes) == 1:
            group_evidence = ["single_source"]
        payload, detail = build_candidate(group_records, group_evidence)
        base = (payload.get("structured_data") or {}).get("base_info") or {}
        contact = normalize_phone(base.get("phone")) or (next(iter(emails(base.get("email"))), "")) or "无联系方式"
        filename = f"{safe_filename(text(base.get('full_name')), '未知')}_{safe_filename(contact, '无联系方式')}.json"
        suffix = 2
        while filename.casefold() in allocated:
            filename = f"{safe_filename(text(base.get('full_name')), '未知')}_{safe_filename(contact, '无联系方式')}_{suffix}.json"
            suffix += 1
        allocated.add(filename.casefold())
        output_path = target / filename
        atomic_json(output_path, payload)
        detail["output_json"] = str(output_path)
        details.append(detail)
        if detail["translation_needed"]:
            translations.append({
                "record_id": detail["record_id"],
                "candidate_name": detail["candidate_name"],
                "contact": detail["phone"] or detail["email"],
                "languages": [lang for lang in detail["languages"] if lang != "zh"],
                "source_count": detail["source_count"],
                "input_files": detail["input_files"],
                "candidate_json": str(output_path),
            })
        if detail["gpt_translation_structure_mismatch"]:
            gpt_reviews.append({
                "record_id": detail["record_id"],
                "candidate_name": detail["candidate_name"],
                "contact": detail["phone"] or detail["email"],
                "languages": [lang for lang in detail["languages"] if lang != "zh"],
                "source_count": detail["source_count"],
                "input_files": detail["input_files"],
                "candidate_json": str(output_path),
                "gpt_json": detail["selected_language_sources"].get("zh", ""),
            })

    report = {
        "version": VERSION,
        "generated_at": datetime.now().astimezone().isoformat(),
        "source_json_count": len(records),
        "candidate_count": len(details),
        "merged_candidate_count": sum(row["source_count"] > 1 for row in details),
        "single_source_candidate_count": sum(row["source_count"] == 1 for row in details),
        "translation_candidate_count": len(translations),
        "gpt_translation_used_count": sum(row.get("gpt_translation_used") for row in details),
        "gpt_translation_review_count": len(gpt_reviews),
        "warning_counts": dict(Counter(warning for row in details for warning in row["warnings"])),
        "map_output_fallback_count": len(map_output_fallbacks),
        "map_output_fallbacks": map_output_fallbacks,
        "rejected_gpt_pair_count": len(rejected_gpt_pairs),
        "rejected_gpt_pairs": rejected_gpt_pairs,
        "records": details,
    }
    translation_report = {
        "version": VERSION,
        "generated_at": report["generated_at"],
        "total": len(translations),
        "records": translations,
    }
    atomic_json(cfg.report, report)
    atomic_json(cfg.translation_json, translation_report)
    atomic_json(cfg.gpt_review_json, {
        "version": VERSION,
        "generated_at": report["generated_at"],
        "total": len(gpt_reviews),
        "reason": "GPT 中文与其外文版本的工作或学历条目数量差异超过阈值",
        "records": gpt_reviews,
    })
    csv_rows = [{
        "序号": index,
        "候选人": row["candidate_name"],
        "联系方式": row["contact"],
        "待翻译语言": ",".join(row["languages"]),
        "来源数量": row["source_count"],
        "来源PDF": " | ".join(row["input_files"]),
        "候选JSON": row["candidate_json"],
    } for index, row in enumerate(translations, 1)]
    write_translation_csv(cfg.translation_csv, csv_rows)
    review_rows = [{
        "序号": index,
        "候选人": row["candidate_name"],
        "联系方式": row["contact"],
        "待翻译语言": ",".join(row["languages"]),
        "来源数量": row["source_count"],
        "来源PDF": " | ".join(row["input_files"]),
        "候选JSON": row["candidate_json"],
    } for index, row in enumerate(gpt_reviews, 1)]
    write_translation_csv(cfg.gpt_review_csv, review_rows)
    print(json.dumps({key: value for key, value in report.items() if key not in {"records", "rejected_gpt_pairs"}}, ensure_ascii=False, indent=2))
    print(f"output={target}")
    print(f"report={cfg.report.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
