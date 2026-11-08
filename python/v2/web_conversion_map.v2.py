"""Build the authoritative Web-source conversion map.

The Web worksheet in ``32718文件报告.xlsx`` is the source of truth.  Every
row is retained, including HTML-like files which are not detected as HTML by
the report.  Source files are copied to a safe staging directory; originals
are never renamed, moved, or overwritten.
"""

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
import shutil
import tempfile
from datetime import date, datetime
from pathlib import Path
from typing import Any

try:
    import openpyxl
except ImportError as exc:  # pragma: no cover - environment error
    raise SystemExit("需要 openpyxl 才能读取 32718文件报告.xlsx") from exc


PROJECT_ROOT = _rc.project_root()
DEFAULT_REPORT = PROJECT_ROOT / "32718文件报告.xlsx"
DEFAULT_SHEET = "Web网页与邮件 (.html, .eml)"
DEFAULT_STAGE = PROJECT_ROOT / _rc.dirname("complete-transfered-htmls") / "web" / "input"
DEFAULT_MAP = PROJECT_ROOT / _rc.dirname("complete-transfered-htmls") / "web" / "web_conversion_map.v2.json"
WEB_SUFFIXES = {".html", ".htm", ".mht", ".mhtml", ".eml"}


def _json_default(value: Any) -> str:
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, default=_json_default)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    finally:
        Path(temp_name).unlink(missing_ok=True)


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def normalized_path(value: str) -> str:
    return os.path.normcase(os.path.normpath(os.path.abspath(value)))


def source_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_name(value: str) -> str:
    value = re.sub(r"[\\/:*?\"<>|]", "_", value).strip().strip(".")
    value = re.sub(r"\s+", " ", value)
    return value or "unnamed"


def normalize_datetime(value: Any) -> str:
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(value, date):
        return f"{value.isoformat()} 00:00:00"
    text = clean_text(value)
    if not text:
        return ""
    text = text.replace("年", "-").replace("月", "-").replace("日", "")
    text = text.replace("/", "-").replace(".", "-")
    text = re.sub(r"\s+", " ", text)
    parts = text.split(" ", 1)
    date_part = parts[0]
    time_part = parts[1] if len(parts) > 1 else "00:00:00"
    date_bits = date_part.split("-")
    if len(date_bits) >= 3:
        try:
            date_part = f"{int(date_bits[0]):04d}-{int(date_bits[1]):02d}-{int(date_bits[2]):02d}"
        except ValueError:
            pass
    time_bits = time_part.split(":")
    try:
        if len(time_bits) == 2:
            time_part = f"{int(time_bits[0]):02d}:{int(time_bits[1]):02d}:00"
        elif len(time_bits) >= 3:
            time_part = f"{int(time_bits[0]):02d}:{int(time_bits[1]):02d}:{int(time_bits[2]):02d}"
    except ValueError:
        time_part = "00:00:00"
    return f"{date_part} {time_part}"


def read_rows(report_path: Path, sheet_name: str) -> list[dict[str, Any]]:
    workbook = openpyxl.load_workbook(report_path, read_only=True, data_only=True)
    try:
        if sheet_name not in workbook.sheetnames:
            raise ValueError(f"报告中不存在工作表: {sheet_name}")
        sheet = workbook[sheet_name]
        rows = sheet.iter_rows(values_only=True)
        header_values = next(rows, None)
        if not header_values:
            return []
        headers = [clean_text(item) for item in header_values]
        result: list[dict[str, Any]] = []
        for row_number, values in enumerate(rows, start=2):
            record = {headers[i]: values[i] if i < len(values) else None for i in range(len(headers))}
            source_path = clean_text(record.get("完整绝对路径"))
            filename = clean_text(record.get("文件名"))
            extension = clean_text(record.get("后缀名")).lower()
            if not source_path and filename:
                continue
            result.append({
                "report_row": row_number,
                "index": int(record.get("序号") or len(result) + 1),
                "relative_path": clean_text(record.get("相对路径")),
                "filename": filename or Path(source_path).name,
                "extension": extension or Path(source_path).suffix.lower(),
                "detected_type": clean_text(record.get("探测真实类型")),
                "size_kb": record.get("大小(KB)"),
                "source_landing_time": normalize_datetime(record.get("修改日期")),
                "source_path": source_path,
            })
        return result
    finally:
        workbook.close()


def load_previous_map(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    rows = payload if isinstance(payload, list) else payload.get("records", [])
    if not isinstance(rows, list):
        return {}
    result = {}
    for row in rows:
        if isinstance(row, dict) and row.get("source_path"):
            result[normalized_path(str(row["source_path"]))] = row
    return result


def stage_one(record: dict[str, Any], stage_dir: Path, force: bool) -> tuple[str, str]:
    source = Path(record["source_path"])
    if not source.exists() or not source.is_file():
        return "", "source_missing"
    extension = source.suffix.lower() or record.get("extension") or ".html"
    if extension not in WEB_SUFFIXES:
        return "", "unsupported_web_extension"
    stem = safe_name(source.stem)
    staged_name = f"{int(record['index']):04d}_{stem}_{source_hash(source)[:10]}{extension}"
    destination = stage_dir / staged_name
    needs_copy = force or not destination.exists()
    if not needs_copy:
        try:
            needs_copy = source.stat().st_size != destination.stat().st_size or source_hash(source) != source_hash(destination)
        except OSError:
            needs_copy = True
    if needs_copy:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    return str(destination.resolve()), ""


def merge_processing_fields(current: dict[str, Any], previous: dict[str, Any], force: bool) -> dict[str, Any]:
    if not previous:
        return current
    # Workbook/source metadata is refreshed every run.  Processing results are
    # retained unless --force explicitly requests a clean conversion state.
    if not force:
        for key in (
            "status", "message", "json_path", "json_paths", "classification",
            "quality", "processed_at", "error_reason", "contact", "language_folder",
        ):
            if key in previous:
                current[key] = previous[key]
    return current


def build_map(report_path: Path, sheet_name: str, stage_dir: Path, map_path: Path, force: bool) -> dict[str, Any]:
    source_rows = read_rows(report_path, sheet_name)
    previous = load_previous_map(map_path)
    records: list[dict[str, Any]] = []
    for row in source_rows:
        source = Path(row["source_path"])
        source_exists = source.exists() and source.is_file()
        stage_path, stage_error = stage_one(row, stage_dir, force)
        record = {
            **row,
            "source_path": str(source.resolve()) if source_exists else row["source_path"],
            "source_exists": source_exists,
            "source_extension": source.suffix.lower() or row["extension"],
            "source_hash": source_hash(source) if source_exists else "",
            "stage_path": stage_path,
            "html_path": stage_path,
            "html_filename": Path(stage_path).name if stage_path else "",
            "status": "pending" if not stage_error else stage_error,
            "message": "",
            "error_reason": stage_error,
            "json_path": "",
            "json_paths": [],
            "classification": {},
            "quality": {},
            "contact": {},
            "language_folder": "",
            "processed_at": "",
        }
        records.append(merge_processing_fields(record, previous.get(normalized_path(str(source))), force))

    counts: dict[str, int] = {}
    for record in records:
        status = str(record.get("status") or "pending")
        counts[status] = counts.get(status, 0) + 1
    payload = {
        "schema_version": "web-conversion-map-v2",
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "report_path": str(report_path.resolve()),
        "sheet_name": sheet_name,
        "source_scope": "32718文件报告.xlsx / Web网页与邮件 (.html, .eml)",
        "total_rows": len(records),
        "web_extensions": sorted(WEB_SUFFIXES),
        "stage_dir": str(stage_dir.resolve()),
        "counts": counts,
        "records": records,
    }
    atomic_json(map_path, payload)
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="生成全量 Web 文件转换 map" " / Generate the full Web file conversion map / Web ファイル変換の全件マップを生成する")
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--sheet", default=DEFAULT_SHEET)
    parser.add_argument("--stage-dir", type=Path, default=DEFAULT_STAGE)
    parser.add_argument("--map", dest="map_path", type=Path, default=DEFAULT_MAP)
    parser.add_argument("--force", action="store_true", help="重新复制 staging 文件并清空处理状态" " / Re-copy the staging files and clear the processing status / ステージングファイルを再コピーし、処理状態をクリアする")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload = build_map(args.report, args.sheet, args.stage_dir, args.map_path, args.force)
    counts = payload["counts"]
    print(f"Web map 已生成: {args.map_path}" f" / Web map generated: {args.map_path} / Web マップを生成しました：{args.map_path}")
    print(f"范围: {payload['total_rows']} 条；后缀: {', '.join(payload['web_extensions'])}" f" / Scope: {payload['total_rows']} records; suffixes: {', '.join(payload['web_extensions'])} / 範囲：{payload['total_rows']} 件、拡張子：{', '.join(payload['web_extensions'])}")
    print(f"状态: {json.dumps(counts, ensure_ascii=False)}" f" / Status: {json.dumps(counts, ensure_ascii=False)} / 状態：{json.dumps(counts, ensure_ascii=False)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
