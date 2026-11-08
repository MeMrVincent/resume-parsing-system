"""Offline, in-place multilingual repair for Web JSON outputs.

Only records flagged by the independent Web review are processed.  The first
resume remains the Chinese primary and only its translatable semantic fields
are translated.  Following resumes retain their original field content; only
an incorrect language label may be corrected.  Every attempted JSON receives
an incremental quality/reconciliation entry and the run writes a full report.
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
import importlib.util
import json
import os
import re
import tempfile
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable


ROOT = _rc.project_root()
MAP_PATH = ROOT / _rc.dirname("complete-transfered-htmls") / "web" / "web_conversion_map.v2.json"
REVIEW_PATH = ROOT / _rc.dirname("complete-transfered-jsons") / "web" / "_web_full_review.v2.json"
REPORT_PATH = ROOT / _rc.dirname("complete-transfered-jsons") / "web" / "_web_multilingual_repair.v2.json"
ISSUE_CODES = {
    "primary_zh_contains_untranslated_foreign_content",
    "primary_zh_fields_equal_untranslated_foreign_source",
    "multilingual_list_count_mismatch",
}
ADDITIONAL_TRANSLATABLE_KEYS = {"certificate_name", "skill_name", "language_certificate"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--map", type=Path, default=MAP_PATH)
    parser.add_argument("--review", type=Path, default=REVIEW_PATH)
    parser.add_argument("--report", type=Path, default=REPORT_PATH)
    parser.add_argument("--limit", type=int, default=0)
    return parser.parse_args()


def atomic_json(path: Path, payload: Any) -> None:
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


def load_translation_support() -> Any:
    """Reuse the repository's local NLLB wrapper without calling a service."""
    path = _rc.PYTHON_DIR / "v2" / "batch_clean_resume_jsons.py"
    spec = importlib.util.spec_from_file_location("local_translation_support", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载离线翻译模块: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def strings(value: Any, path: tuple[str, ...] = ()) -> Iterable[tuple[tuple[str, ...], str]]:
    if isinstance(value, dict):
        for key, child in value.items():
            yield from strings(child, path + (str(key),))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from strings(child, path + (str(index),))
    elif isinstance(value, str) and value.strip():
        yield path, value.strip()


def language_counts(value: Any) -> tuple[int, int, int]:
    text = "\n".join(text for path, text in strings(value) if not path or path[-1] != "resume_languge")
    return (
        len(re.findall(r"[\u3400-\u9fff]", text)),
        len(re.findall(r"[\u3040-\u30ff]", text)),
        len(re.findall(r"[A-Za-z]", text)),
    )


def detected_language(resume: dict[str, Any]) -> str:
    han, kana, latin = language_counts(resume)
    if kana >= 10:
        return "jp"
    if latin >= 80 and latin >= max(80, han * 2):
        return "en"
    return "zh"


def source_language(text: str, target: str, key: str, support: Any) -> str | None:
    detected = support.source_language(text, target, key)
    if detected or target != "zh" or key not in ADDITIONAL_TRANSLATABLE_KEYS:
        return detected
    if re.search(r"https?://|www\.|@", text, re.I):
        return None
    han, kana, latin = support.char_counts(text)
    if kana >= 2:
        return "ja"
    if latin >= 4 and latin >= max(3, han * 2):
        return "en"
    return None


def transform_primary(
    value: Any,
    support: Any,
    translator: Any,
    path: tuple[str, ...] = (),
    changes: list[dict[str, str]] | None = None,
) -> Any:
    if isinstance(value, dict):
        return {key: transform_primary(child, support, translator, path + (str(key),), changes) for key, child in value.items()}
    if isinstance(value, list):
        return [transform_primary(child, support, translator, path + (str(index),), changes) for index, child in enumerate(value)]
    if not isinstance(value, str):
        return value
    key = path[-1] if path else ""
    source = source_language(value, "zh", key, support)
    if not source:
        return value
    translated = translator.translate(value, source, "zh")
    if translated.strip() and translated != value:
        if changes is not None:
            changes.append({
                "path": ".".join(path),
                "source_language": source,
                "before": value[:160],
                "after": translated[:160],
            })
        return translated
    return value


def transform_to_language(value: Any, target: str, support: Any, translator: Any, path: tuple[str, ...] = (), changes: list[dict[str, str]] | None = None) -> Any:
    if isinstance(value, dict):
        return {key: transform_to_language(child, target, support, translator, path + (str(key),), changes) for key, child in value.items()}
    if isinstance(value, list):
        return [transform_to_language(child, target, support, translator, path + (str(index),), changes) for index, child in enumerate(value)]
    if not isinstance(value, str):
        return value
    key = path[-1] if path else ""
    source = source_language(value, target, key, support)
    if not source:
        return value
    translated = translator.translate(value, source, target)
    if translated.strip() and translated != value:
        if changes is not None:
            changes.append({"path": ".".join(path), "source_language": source, "target_language": target, "before": value[:160], "after": translated[:160]})
        return translated
    return value


def main() -> int:
    args = parse_args()
    started_at = datetime.now().astimezone().isoformat(timespec="seconds")
    support = load_translation_support()
    review = json.loads(args.review.read_text(encoding="utf-8"))
    flagged = [
        int(item.get("index") or 0)
        for item in review.get("items", [])
        if any(issue.get("code") in ISSUE_CODES for issue in item.get("issues", []))
    ]
    if args.limit:
        flagged = flagged[:args.limit]
    flagged_set = set(flagged)
    map_payload = json.loads(args.map.read_text(encoding="utf-8"))
    records = map_payload.get("records", []) if isinstance(map_payload, dict) else []
    selected = [record for record in records if int(record.get("index") or 0) in flagged_set]

    loaded: dict[int, tuple[Path, dict[str, Any]]] = {}
    alignments_by_index: dict[int, list[dict[str, Any]]] = {}
    requests: set[tuple[str, str, str]] = set()
    preflight: list[dict[str, Any]] = []
    for record in selected:
        index = int(record.get("index") or 0)
        path = Path(str(record.get("json_path") or ""))
        if not path.is_file():
            preflight.append({"index": index, "json_path": str(path), "status": "missing_json"})
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        resumes = ((payload.get("structured_data") or {}).get("resumes") or [])
        if not resumes or not isinstance(resumes[0], dict):
            preflight.append({"index": index, "json_path": str(path), "status": "missing_primary_resume"})
            continue
        loaded[index] = (path, payload)
        alignments: list[dict[str, Any]] = []
        primary = resumes[0]
        for resume_index, foreign in enumerate(resumes[1:], 1):
            target = str(foreign.get("resume_languge") or "")
            if target not in {"en", "jp"}:
                continue
            for list_name in ("expected_list", "work_experiences", "education_list", "certificate_list", "language_list", "skills_list", "training_list", "project_list"):
                primary_count = len(primary.get(list_name) or [])
                foreign_count = len(foreign.get(list_name) or [])
                if foreign_count >= primary_count:
                    continue
                foreign[list_name] = copy.deepcopy(primary[list_name])
                alignments.append({"resume_index": resume_index, "target_language": target, "list_name": list_name, "before": foreign_count, "after": primary_count})
        alignments_by_index[index] = alignments
        pair_counts: Counter[str] = Counter()
        for field_path, text in strings(resumes[0]):
            key = field_path[-1] if field_path else ""
            source = source_language(text, "zh", key, support)
            if source:
                requests.add((source, "zh", text))
                pair_counts[f"{source}>zh"] += 1
        for alignment in alignments:
            resume_index = int(alignment["resume_index"])
            list_name = str(alignment["list_name"])
            target = str(alignment["target_language"])
            for field_path, text in strings(resumes[resume_index][list_name]):
                key = field_path[-1] if field_path else ""
                source = source_language(text, target, key, support)
                if source:
                    requests.add((source, target, text))
                    pair_counts[f"{source}>{target}"] += 1
        preflight.append({
            "index": index,
            "json_path": str(path),
            "status": "ready",
            "translation_requests": sum(pair_counts.values()),
            "language_pairs": dict(pair_counts),
            "list_alignments": alignments,
        })

    print(json.dumps({
        "flagged_records": len(flagged),
        "loaded_records": len(loaded),
        "unique_translation_requests": len(requests),
    }, ensure_ascii=False), flush=True)
    translator = support.OfflineTranslator(enabled=True)
    failures_before = len(translator.failures)
    translator.precompute(requests)

    items: list[dict[str, Any]] = []
    totals: Counter[str] = Counter()
    for record in selected:
        index = int(record.get("index") or 0)
        if index not in loaded:
            item = next((entry for entry in preflight if entry["index"] == index), {"index": index, "status": "not_loaded"})
            items.append(item)
            totals[item["status"]] += 1
            continue
        path, payload = loaded[index]
        resumes = payload["structured_data"]["resumes"]
        original_following = copy.deepcopy(resumes[1:])
        changes: list[dict[str, str]] = []
        resumes[0] = transform_primary(resumes[0], support, translator, ("structured_data", "resumes", "0"), changes)
        resumes[0]["resume_languge"] = "zh"
        alignment_changes: list[dict[str, str]] = []
        for alignment in alignments_by_index.get(index, []):
            resume_index = int(alignment["resume_index"])
            list_name = str(alignment["list_name"])
            target = str(alignment["target_language"])
            resumes[resume_index][list_name] = transform_to_language(
                resumes[resume_index][list_name], target, support, translator,
                ("structured_data", "resumes", str(resume_index), list_name), alignment_changes,
            )
        label_changes: list[dict[str, Any]] = []
        for resume_index in range(1, len(resumes)):
            old_label = str(resumes[resume_index].get("resume_languge") or "")
            new_label = detected_language(resumes[resume_index])
            if new_label != old_label:
                resumes[resume_index]["resume_languge"] = new_label
                label_changes.append({"resume_index": resume_index, "before": old_label, "after": new_label})
        content_preserved = all(
            {key: value for key, value in current.items() if key != "resume_languge"}
            == {key: value for key, value in original.items() if key != "resume_languge"}
            for current, original in zip(resumes[1:], original_following)
        ) and len(resumes[1:]) == len(original_following)
        if not content_preserved and not alignments_by_index.get(index):
            raise RuntimeError(f"原始外文版本发生了非标签变化: index={index}")

        checked_at = datetime.now().astimezone().isoformat(timespec="seconds")
        quality = payload.get("quality") if isinstance(payload.get("quality"), dict) else {}
        payload["quality"] = quality
        quality["multilingual_repair"] = {
            "status": "translated" if changes else "checked_no_change",
            "checked_at": checked_at,
            "translated_field_count": len(changes),
            "aligned_foreign_field_translation_count": len(alignment_changes),
            "list_alignments": alignments_by_index.get(index, []),
            "language_label_changes": label_changes,
            "original_following_content_preserved": content_preserved,
            "translation_engine": "local_nllb_200_distilled_600m",
            "external_service_used": False,
        }
        reconciliation = quality.get("reconciliation") if isinstance(quality.get("reconciliation"), dict) else {}
        quality["reconciliation"] = reconciliation
        reconciliation.pop("rounds", None)
        reconciliation.pop("repair_history", None)
        atomic_json(path, payload)
        status = "translated" if changes else "checked_no_change"
        items.append({
            "index": index,
            "json_path": str(path),
            "status": status,
            "translated_field_count": len(changes),
            "language_label_changes": label_changes,
            "original_following_content_preserved": content_preserved,
            "changes": changes,
            "repair_round": {
                "applied_at": checked_at,
                "issue_codes_before": sorted(ISSUE_CODES),
                "fixes_applied": {"translated_fields": len(changes), "language_labels_corrected": len(label_changes)},
            },
        })
        totals[status] += 1
        totals["translated_fields"] += len(changes)
        totals["aligned_foreign_fields_translated"] += len(alignment_changes)
        totals["foreign_lists_aligned"] += len(alignments_by_index.get(index, []))
        totals["language_labels_corrected"] += len(label_changes)

    translator.save()
    report = {
        "schema_version": "web-multilingual-repair-v2",
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "started_at": started_at,
        "scope": {
            "review_flagged_records": len(flagged),
            "selected_map_records": len(selected),
            "loaded_json_records": len(loaded),
            "unique_translation_requests": len(requests),
        },
        "summary": dict(totals),
        "translation_failures": translator.failures[failures_before:],
        "preflight": preflight,
        "items": items,
    }
    atomic_json(args.report, report)
    print(json.dumps(report["summary"], ensure_ascii=False), flush=True)
    print(f"多语言增量修复报告: {args.report}" f" / Multilingual incremental repair report: {args.report} / 多言語の差分修復レポート：{args.report}", flush=True)
    return 0 if not report["translation_failures"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
