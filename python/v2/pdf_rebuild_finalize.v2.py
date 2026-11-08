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
import shutil
import tempfile
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = _rc.project_root()
PDF_ROOT = PROJECT_ROOT / _rc.dirname("complete-transfered-htmls") / "pdf"
DEFAULT_SOURCE = PDF_ROOT / "rebuild-work" / "json-by-candidate"
DEFAULT_TARGET = PROJECT_ROOT / _rc.dirname("complete-transfered-jsons") / "pdf" / "new"
DEFAULT_MAP = PDF_ROOT / "rebuild-work" / "pdf_rebuild_map.v2.json"
DEFAULT_MERGE_REPORT = PDF_ROOT / "rebuild-reports" / "pdf_candidate_merge.v2.json"
DEFAULT_AUDIT_REPORT = PDF_ROOT / "rebuild-reports" / "pdf_candidate_audit.v2.json"
DEFAULT_REPORT = PDF_ROOT / "rebuild-reports" / "pdf_finalization.v2.json"
VERSION = "pdf-rebuild-finalize-v2.0.0"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="审计通过后把 PDF v2 候选人 JSON 发布到 new" " / After the audit passes, publish the PDF v2 candidate JSON to new / 監査に合格した後、PDF v2 の候補者 JSON を new に公開する")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--target", type=Path, default=DEFAULT_TARGET)
    parser.add_argument("--map", type=Path, default=DEFAULT_MAP)
    parser.add_argument("--merge-report", type=Path, default=DEFAULT_MERGE_REPORT)
    parser.add_argument("--audit-report", type=Path, default=DEFAULT_AUDIT_REPORT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--replace", action="store_true", help="审计通过后原子替换现有 new 目录" " / After the audit passes, atomically replace the existing new directory / 監査に合格した後、既存の new ディレクトリをアトミックに置き換える")
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


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    cfg = parse_args()
    audit = read_json(cfg.audit_report)
    counts = audit.get("counts") or {}
    candidate_total = int(audit.get("candidate_total") or 0)
    if counts.get("passed") != candidate_total or audit.get("missing_source_hashes") or audit.get("duplicate_source_hashes"):
        raise SystemExit("候选人审计未全量通过，拒绝发布")
    sources = sorted(cfg.source.glob("*.json"))
    if len(sources) != candidate_total:
        raise SystemExit(f"候选文件数量与审计不一致: files={len(sources)} audit={candidate_total}")
    target = cfg.target.resolve()
    target.mkdir(parents=True, exist_ok=True)
    target_has_files = any(target.iterdir())
    if target_has_files and not cfg.replace:
        raise SystemExit(f"new 目录非空，拒绝覆盖: {target}")

    copies: list[dict[str, str]] = []
    stage = target.parent / f".{target.name}-stage-{uuid.uuid4().hex}"
    stage.mkdir(parents=False, exist_ok=False)
    for source in sources:
        destination = stage / source.name
        shutil.copy2(source, destination)
        source_hash, destination_hash = sha256(source), sha256(destination)
        if source_hash != destination_hash:
            raise SystemExit(f"发布后哈希不一致: {source.name}")
        copies.append({"source": str(source.resolve()), "output": str(target / source.name), "sha256": destination_hash})

    if target_has_files:
        backup = target.parent / f".{target.name}-backup-{uuid.uuid4().hex}"
        target.rename(backup)
        try:
            stage.rename(target)
        except Exception:
            backup.rename(target)
            raise
        shutil.rmtree(backup)
    else:
        target.rmdir()
        stage.rename(target)

    merge_report = read_json(cfg.merge_report)
    output_by_input: dict[str, str] = {}
    warning_by_input: dict[str, list[str]] = {}
    for row in merge_report.get("records") or []:
        output = str(target / Path(row["output_json"]).name)
        for filename in row.get("input_files") or []:
            output_by_input[filename] = output
            warning_by_input[filename] = list(row.get("warnings") or [])
    # Candidate filenames may be corrected after semantic review (for example,
    # replacing a temporary "待确认姓名" prefix). Resolve mappings from each
    # final payload's own source manifest so output_path always exists.
    for source in sources:
        payload = read_json(source)
        for row in ((payload.get("source") or {}).get("source_files") or []):
            if not isinstance(row, dict):
                continue
            filename = row.get("filename") or Path(str(row.get("input_path") or "")).name
            if filename:
                output_by_input[filename] = str(target / source.name)
    mapping = read_json(cfg.map)
    updated = 0
    for row in mapping.get("records") or []:
        filename = row.get("input_filename")
        if filename not in output_by_input:
            continue
        processing = row.setdefault("processing", {})
        processing["merge_status"] = "needs_review" if warning_by_input[filename] else "merged"
        processing["output_path"] = output_by_input[filename]
        updated += 1
    atomic_json(cfg.map, mapping)

    report = {
        "version": VERSION,
        "generated_at": datetime.now().astimezone().isoformat(),
        "published_count": len(copies),
        "map_resume_records_updated": updated,
        "target": str(target),
        "quality_counts": {key.removeprefix("quality:"): value for key, value in counts.items() if key.startswith("quality:")},
        "candidate_audit_report": str(cfg.audit_report.resolve()),
        "candidate_merge_report": str(cfg.merge_report.resolve()),
        "files": copies,
    }
    atomic_json(cfg.report, report)
    print(json.dumps({key: value for key, value in report.items() if key != "files"}, ensure_ascii=False, indent=2))
    print(f"report={cfg.report.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
