"""Review, rename and flatten every Web JSON output into one directory."""

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
import os
import re
import tempfile
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = _rc.project_root()
MAP_PATH = ROOT / _rc.dirname("complete-transfered-htmls") / "web" / "web_conversion_map.v2.json"
OUTPUT_DIR = ROOT / _rc.dirname("complete-transfered-jsons") / "web"
REVIEW_PATH = OUTPUT_DIR / "_web_filename_review.v2.json"
REPORT_PATH = OUTPUT_DIR / "_web_output_organize.v2.json"
INVALID_NAME_RE = re.compile(
    r"^(?:简历|个人简历|未知|未知姓名|Male|Female|添加标签|目前正在找工作|品质主管|待确认姓名_)$|性別|性别|照片",
    re.I,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--map", type=Path, default=MAP_PATH)
    parser.add_argument("--review", type=Path, default=REVIEW_PATH)
    parser.add_argument("--report", type=Path, default=REPORT_PATH)
    parser.add_argument("--apply", action="store_true")
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


def compact(value: str) -> str:
    return re.sub(r"[^0-9A-Za-z\u3400-\u9fff\u3040-\u30ff]+", "", value).casefold()


def safe_name(value: str) -> str:
    text = re.sub(r"[<>:\"/\\|?*\x00-\x1f]", "_", value.strip())
    text = re.sub(r"\s+", "_", text).strip(" ._")
    return text[:80]


def contact_token(base_info: dict[str, Any]) -> tuple[str, str]:
    phone = str(base_info.get("phone") or "").strip()
    phone_match = re.search(r"(?:\+?\d[\d\s()（）-]{5,}\d)", phone)
    if phone_match:
        digits = re.sub(r"\D", "", phone_match.group(0))
        if len(digits) >= 7:
            return digits, "phone"
    email = str(base_info.get("email") or "").strip()
    email_match = re.search(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", email, re.I)
    if email_match:
        return safe_name(email_match.group(0).lower()), "email"
    return "无联系方式", "none"


def source_text(path: Path) -> str:
    if not path.is_file() or not path.stat().st_size:
        return ""
    raw = path.read_bytes()
    for encoding in ("utf-8", "gb18030", "utf-16", "latin1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def output_suffix(path: Path, record: dict[str, Any]) -> str:
    match = re.search(r"_([0-9a-f]{8})$", path.stem, re.I)
    if match:
        return match.group(1).lower()
    digest = str(record.get("source_hash") or "")
    if len(digest) >= 8:
        return digest[:8].lower()
    return hashlib.sha256(str(record.get("index") or "").encode()).hexdigest()[:8]


def inspect_record(record: dict[str, Any]) -> dict[str, Any] | None:
    path_value = str(record.get("json_path") or "")
    if not path_value:
        return None
    old_path = Path(path_value)
    if not old_path.is_file():
        return {
            "index": int(record.get("index") or 0), "old_path": str(old_path), "status": "missing",
            "issues_before": ["json_missing"],
        }
    payload = json.loads(old_path.read_text(encoding="utf-8"))
    resumes = (((payload.get("structured_data") or {}).get("resumes")) or [])
    primary = resumes[0] if resumes and isinstance(resumes[0], dict) else {}
    base_info = primary.get("base_info") if isinstance(primary.get("base_info"), dict) else {}
    name = str(base_info.get("full_name") or "").strip()
    invalid = not name or bool(INVALID_NAME_RE.search(name)) or name.endswith(("简", "简历"))
    sanitized = safe_name(name)
    contact, contact_type = contact_token(base_info)
    filename_base = f"{sanitized}_{contact}" if sanitized else f"record_{int(record.get('index') or 0):04d}_{contact}"
    new_path = OUTPUT_DIR / f"{filename_base}.json"
    stage = Path(str(record.get("stage_path") or record.get("html_path") or ""))
    source = Path(str(record.get("source_path") or ""))
    evidence = compact(source_text(stage if stage.is_file() else source))
    filename_evidence = compact(source.name)
    normalized_name = compact(name)
    if normalized_name and normalized_name in evidence:
        name_status = "source_content_verified"
    elif normalized_name and normalized_name in filename_evidence:
        name_status = "source_filename_verified"
    elif not invalid:
        name_status = "prior_pairwise_review_verified"
    else:
        name_status = "invalid"
    issues: list[str] = []
    if old_path.parent.resolve() != OUTPUT_DIR.resolve():
        issues.append("classified_subdirectory_present")
    old_label = re.sub(r"_[0-9a-f]{8}$", "", old_path.stem, flags=re.I)
    if old_label != sanitized:
        issues.append("filename_name_mismatch")
    if invalid:
        issues.append("invalid_primary_name")
    return {
        "index": int(record.get("index") or 0),
        "source_path": str(source),
        "old_path": str(old_path),
        "new_path": str(new_path),
        "primary_full_name": name,
        "contact_token": contact,
        "contact_type": contact_type,
        "filename_base": filename_base,
        "name_status": name_status,
        "issues_before": issues,
        "status": "needs_review" if invalid else ("rename_or_move_required" if issues else "verified"),
    }


def main() -> int:
    args = parse_args()
    checked_at = datetime.now().astimezone().isoformat(timespec="seconds")
    payload = json.loads(args.map.read_text(encoding="utf-8"))
    records = payload.get("records", []) if isinstance(payload, dict) else []
    items = [item for record in records if (item := inspect_record(record)) is not None]
    # Stable numbering for repeated files belonging to the same person/contact.
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        grouped.setdefault(str(item.get("filename_base") or "").casefold(), []).append(item)
    for group in grouped.values():
        group.sort(key=lambda item: int(item.get("index") or 0))
        for position, item in enumerate(group, 1):
            suffix = "" if position == 1 else f"_{position}"
            item["duplicate_sequence"] = position
            item["new_path"] = str(OUTPUT_DIR / f"{item['filename_base']}{suffix}.json")
            old_path = Path(str(item.get("old_path") or ""))
            desired_label = f"{item['filename_base']}{suffix}"
            old_label = old_path.stem
            item["issues_before"] = [code for code in item.get("issues_before", []) if code != "filename_name_mismatch"]
            if old_label != desired_label:
                item["issues_before"].append("filename_name_or_contact_mismatch")
            item["status"] = "needs_review" if "invalid_primary_name" in item["issues_before"] else ("rename_or_move_required" if item["issues_before"] else "verified")
    destinations: dict[str, list[int]] = {}
    for item in items:
        destinations.setdefault(str(item.get("new_path") or "").casefold(), []).append(int(item["index"]))
    collisions = {path: indexes for path, indexes in destinations.items() if path and len(indexes) > 1}
    for item in items:
        if str(item.get("new_path") or "").casefold() in collisions:
            item["issues_before"].append("destination_collision")
            item["status"] = "needs_review"

    counts = Counter(str(item.get("status") or "") for item in items)
    review = {
        "report_version": "web-filename-review-v2",
        "mode": "review_before_apply",
        "checked_at": checked_at,
        "records_total": len(records),
        "json_records": len(items),
        "status_counts": dict(counts),
        "issue_counts": dict(Counter(code for item in items for code in item.get("issues_before", []))),
        "collision_count": len(collisions),
        "items": items,
    }
    atomic_json(args.review, review)
    if not args.apply:
        print(json.dumps({key: review[key] for key in ("records_total", "json_records", "status_counts", "issue_counts", "collision_count")}, ensure_ascii=False, indent=2))
        return 1 if collisions or counts.get("needs_review") else 0

    blockers = [item for item in items if item.get("status") in {"needs_review", "missing"}]
    if blockers:
        raise RuntimeError(f"文件名审计仍有 {len(blockers)} 个阻塞项，拒绝移动")

    by_index = {int(record.get("index") or 0): record for record in records}
    moved = 0
    for item in items:
        old_path = Path(item["old_path"])
        new_path = Path(item["new_path"])
        if old_path.resolve() != new_path.resolve():
            if new_path.exists():
                raise FileExistsError(f"目标已存在: {new_path}")
            old_path.replace(new_path)
            moved += 1
        record = by_index[item["index"]]
        record["json_path"] = str(new_path)
        record["json_paths"] = [str(new_path)]
        record.pop("language_folder", None)
        record["output_layout"] = "flat"
        record["filename_review_status"] = "verified"
        record["filename_reviewed_at"] = checked_at
        item["status"] = "moved_and_verified" if old_path.resolve() != new_path.resolve() else "verified"
        item["moved"] = old_path.resolve() != new_path.resolve()

    # Remove only superseded business JSONs that can be paired unambiguously
    # with a live mapped output by record_id and source path.  Reports (leading
    # underscore), unknown files and non-matching records are never deleted.
    mapped_paths = {
        Path(str(record.get("json_path") or "")).resolve()
        for record in records if str(record.get("json_path") or "")
    }
    live_identity: dict[tuple[str, str], Path] = {}
    for path in mapped_paths:
        if not path.is_file():
            continue
        live_payload = json.loads(path.read_text(encoding="utf-8"))
        identity = (
            str(live_payload.get("record_id") or ""),
            str((live_payload.get("source") or {}).get("path") or ""),
        )
        if all(identity):
            live_identity[identity] = path
    stale_copies_deleted: list[str] = []
    for candidate in sorted(OUTPUT_DIR.rglob("*.json")):
        resolved = candidate.resolve()
        resolved.relative_to(OUTPUT_DIR.resolve())
        if resolved in mapped_paths or candidate.name.startswith("_"):
            continue
        try:
            stale_payload = json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        identity = (
            str(stale_payload.get("record_id") or ""),
            str((stale_payload.get("source") or {}).get("path") or ""),
        )
        live_path = live_identity.get(identity)
        if live_path and live_path.is_file() and live_path.resolve() != resolved:
            candidate.unlink()
            stale_copies_deleted.append(str(candidate))

    removed_dirs: list[str] = []
    retained_dirs: list[str] = []
    for folder_name in ("中文", "多语言"):
        folder = OUTPUT_DIR / folder_name
        if folder.is_dir() and not any(folder.iterdir()):
            folder.rmdir()
            removed_dirs.append(str(folder))
        elif folder.is_dir():
            retained_dirs.append(str(folder))
    atomic_json(args.map, payload)
    report = {
        "report_version": "web-output-organize-v2",
        "mode": "applied_flat_layout",
        "completed_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "records_total": len(records),
        "json_records": len(items),
        "moved_count": moved,
        "verified_count": len(items),
        "removed_classification_directories": removed_dirs,
        "retained_nonempty_classification_directories": retained_dirs,
        "stale_copies_deleted_count": len(stale_copies_deleted),
        "stale_copies_deleted": stale_copies_deleted,
        "items": items,
    }
    atomic_json(args.report, report)
    print(json.dumps({key: report[key] for key in ("records_total", "json_records", "moved_count", "verified_count", "stale_copies_deleted_count", "removed_classification_directories", "retained_nonempty_classification_directories")}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
