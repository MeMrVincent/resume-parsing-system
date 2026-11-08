"""Choose the better value per field between rebuilt XLS JSON and complete-v1.

The source-derived JSON remains authoritative when both values are equally
supported.  A complete-v1 value can replace it only when it is more complete,
better evidenced by the source text, and not a template/profile placeholder.
"""
from __future__ import annotations
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1] / "common"))
import rc_config as _rc  # noqa: E402  项目统一配置（python/common/rc_config.py）
# EN: noqa: E402  project-wide configuration (python/common/rc_config.py)
# JA: noqa: E402  プロジェクト共通設定（python/common/rc_config.py）

import copy
import json
import re
import unicodedata
from collections import defaultdict
from pathlib import Path
from typing import Any

from process_xls_html_to_json import normalize_record_contacts, normalize_record_dates, sanitize_record, valid_rule_issues
from reuse_complete_v1_jsons import validate_json

ROOT = _rc.project_root()
OUT = ROOT / _rc.dirname("complete-transfered-jsons") / "xls" / "中文"
COMPLETE = ROOT / _rc.dirname("complete-v1")
MAP = ROOT / _rc.dirname("complete-transfered-htmls") / "xls" / "xls_conversion_map.json"
REPORT = OUT / "_xls_html_to_json_v3_bidirectional_review.json"

PLACEHOLDERS = {
    "education", "work experience", "work_experience", "履歴書", "姓名", "氏名", "名前", "お名前",
    "公司名称", "学校名称", "学校名", "年月日", "目前居住地", "标签名称", "身高 height", "工作经历",
    "工作经验", "education background", "work experience", "name", "full_name",
}
LIST_KEYS = {
    "work_experiences": "company_name", "education_list": "school_name", "certificate_list": "certificate_name",
    "language_list": "language_name", "skills_list": "skill_name", "training_list": "training_name",
    "project_list": "project_name", "expected_list": "expected_position",
}


def compact(value: Any) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", str(value or "")).casefold())


def canonical(value: Any) -> str:
    text = compact(value)
    # Dates are compared by their year/month/day digits; this aligns old
    # ``2012-07`` values with current ``2012年07月01日`` values.
    if re.search(r"(?:19|20)\d{2}", text):
        digits = re.sub(r"\D", "", text)
        if len(digits) >= 6:
            return digits[:8].lstrip("0") or "0"
    return text


def empty(value: Any) -> bool:
    return not str(value or "").strip()


def placeholder(value: Any) -> bool:
    text = compact(value)
    return text in {compact(x) for x in PLACEHOLDERS} or text in {"年", "月", "日", "男", "女"}


def evidenced(value: Any, raw: str) -> bool:
    text = compact(value)
    if not text or len(text) < 2 or placeholder(value):
        return False
    if text in compact(raw):
        return True
    digits = re.sub(r"\D", "", text)
    return bool(digits and len(digits) >= 4 and digits in re.sub(r"\D", "", unicodedata.normalize("NFKC", raw)))


def value_score(value: Any, raw: str, field: str) -> float:
    if empty(value) or placeholder(value):
        return -100.0
    score = 1.0
    if evidenced(value, raw):
        score += 8.0
    text = str(value)
    if len(text) > 20:
        score += min(3.0, len(text) / 500.0)
    if field.endswith("_time") or field.endswith("_start") or field.endswith("_resigned") or field.endswith("_ym"):
        if re.search(r"(?:19|20)\d{2}", text):
            score += 1.0
    return score


def item_key(item: dict[str, Any], identity: str) -> str:
    name = canonical(item.get(identity))
    if identity in {"company_name", "school_name"}:
        start = canonical(item.get("position_start") or item.get("school_start_ym"))
        return f"{name}|{start}" if name else ""
    return name


def merge_item(current: dict[str, Any], old: dict[str, Any], raw: str) -> tuple[dict[str, Any], int, float]:
    result = copy.deepcopy(current)
    changed = 0
    gain = 0.0
    for field in set(current) | set(old):
        cur = current.get(field)
        previous = result.get(field)
        candidate = old.get(field)
        cur_score = value_score(cur, raw, field)
        old_score = value_score(candidate, raw, field)
        # A source-derived value that is itself evidenced wins ties.  The old
        # record is allowed to repair only an empty/placeholder/un evidenced
        # current value; this prevents an old but plausible-looking field from
        # overwriting a newer DOM value merely because it is longer.
        choose_old = old_score > 0 and cur_score < 0
        if choose_old and not empty(candidate):
            result[field] = copy.deepcopy(candidate)
            if canonical(previous) != canonical(candidate):
                changed += 1
                gain += old_score - max(cur_score, 0)
        elif empty(previous) and not empty(candidate) and old_score > 0:
            result[field] = copy.deepcopy(candidate)
            changed += 1
            gain += old_score
    return result, changed, gain


def merge_list(current: list[Any], old: list[Any], identity: str, raw: str, allow_new: bool = False) -> tuple[list[Any], int, float]:
    result = [copy.deepcopy(item) for item in current if isinstance(item, dict)]
    indexes = {item_key(item, identity): index for index, item in enumerate(result) if item_key(item, identity)}
    changed = 0
    gain = 0.0
    for candidate in old:
        if not isinstance(candidate, dict):
            continue
        key = item_key(candidate, identity)
        item_score = sum(max(0.0, value_score(v, raw, f)) for f, v in candidate.items() if not empty(v))
        if item_score < 3.0:
            continue
        target_index = indexes.get(key) if key else None
        if target_index is None and identity in {"company_name", "school_name"}:
            old_start = canonical(candidate.get("position_start") or candidate.get("school_start_ym"))
            if old_start:
                matches = [idx for idx, item in enumerate(result) if canonical(item.get("position_start") or item.get("school_start_ym")) == old_start]
                if len(matches) == 1:
                    target_index = matches[0]
        if target_index is not None:
            merged, delta, added = merge_item(result[target_index], candidate, raw)
            result[target_index] = merged
            changed += delta
            gain += added
        elif not key:
            continue
        else:
            # Do not import a complete-v1 row unless its identity and at least
            # one meaningful value are evidenced in the current source text.
            if not evidenced(candidate.get(identity), raw):
                continue
            if not allow_new:
                continue
            result.append(copy.deepcopy(candidate))
            indexes[key] = len(result) - 1
            changed += 1
            gain += item_score
    return result, changed, gain


def choose_old(candidates: list[tuple[Path, dict[str, Any]]], source: str, row: dict[str, Any], raw: str) -> tuple[dict[str, Any] | None, bool]:
    best = None
    best_score = -1.0
    best_strict = False
    for path, candidate in candidates:
        errors = validate_json(path, candidate, source, str(row.get("phone") or ""), str(row.get("email") or ""), str(row.get("language_folder") or ""), True)
        strict = not errors
        sd = candidate.get("structured_data") or {}
        richness = 0.0
        for resume in sd.get("resumes") or []:
            richness += sum(1 for section in LIST_KEYS if resume.get(section))
            richness += sum(0.1 for v in (resume.get("base_info") or {}).values() if not empty(v))
        score = (100.0 if strict else 0.0) + richness + (5.0 if compact(candidate.get("raw_text")) else 0.0)
        if score > best_score:
            best, best_score, best_strict = candidate, score, strict
    return best, best_strict


def review_record(current: dict[str, Any], old: dict[str, Any], raw: str, strict: bool = False) -> tuple[int, float]:
    cur_sd = current.setdefault("structured_data", {})
    old_sd = old.get("structured_data") or {}
    cur_resumes = cur_sd.get("resumes") or []
    old_resumes = old_sd.get("resumes") or []
    old_by_code = {str(r.get("resume_languge") or r.get("resume_language") or "").casefold(): r for r in old_resumes}
    changed = 0
    gain = 0.0
    for resume in cur_resumes:
        code = str(resume.get("resume_languge") or resume.get("resume_language") or "").casefold()
        other = old_by_code.get(code)
        if not other:
            continue
        cur_base = resume.setdefault("base_info", {})
        old_base = other.get("base_info") or {}
        for field in set(cur_base) | set(old_base):
            if field in {"phone", "email"}:
                continue
            merged, delta, added = merge_item({field: cur_base.get(field)}, {field: old_base.get(field)}, raw)
            if delta:
                cur_base[field] = merged.get(field)
                changed += delta
                gain += added
        for section, identity in LIST_KEYS.items():
            merged, delta, added = merge_list(resume.get(section) or [], other.get(section) or [], identity, raw, allow_new=strict)
            if delta:
                resume[section] = merged
                changed += delta
                gain += added
    if cur_resumes:
        cur_sd["base_info"] = copy.deepcopy(cur_resumes[0].get("base_info") or {})
    return changed, gain


def main() -> int:
    rows = json.loads(MAP.read_text(encoding="utf-8"))
    row_by_source = {compact(row.get("source_path")): row for row in rows}
    old_by_source: dict[str, list[tuple[Path, dict[str, Any]]]] = defaultdict(list)
    for path in COMPLETE.glob("*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        source = compact((payload.get("source") or {}).get("original_path"))
        if source:
            old_by_source[source].append((path, payload))
    matched = reviewed = changed_records = changed_fields = 0
    report_items = []
    for path in sorted(OUT.glob("*.json")):
        if path.name.startswith("_"):
            continue
        try:
            current = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        source = compact((current.get("source") or {}).get("original_path"))
        if source not in old_by_source or source not in row_by_source:
            continue
        matched += 1
        # Evidence must come from the current source-derived DOM text.  Old
        # JSON raw_text can contain parser artefacts and must not legitimise a
        # contact or field that is absent from the current source extraction.
        raw = str(current.get("raw_text") or "")
        old, strict = choose_old(old_by_source[source], str((current.get("source") or {}).get("original_path") or ""), row_by_source[source], raw)
        if old is None:
            continue
        reviewed += 1
        delta, gain = review_record(current, old, raw, strict)
        if delta:
            sanitize_record(current)
            normalize_record_contacts(current)
            normalize_record_dates(current)
            current.setdefault("source", {})["complete_v1_bidirectional_review"] = {"strict_candidate": strict, "fields_changed": delta, "evidence_gain": round(gain, 3)}
            path.write_text(json.dumps(current, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            changed_records += 1
            changed_fields += delta
            report_items.append({"json": str(path.resolve()), "source_path": str((current.get("source") or {}).get("original_path") or ""), "fields_changed": delta, "evidence_gain": round(gain, 3), "strict_candidate": strict})
    result = {"current_json": sum(1 for p in OUT.glob("*.json") if not p.name.startswith("_")), "exact_path_matched": matched, "old_candidates_reviewed": reviewed, "changed_records": changed_records, "changed_fields": changed_fields, "items": report_items}
    REPORT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: result[k] for k in result if k != "items"}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
