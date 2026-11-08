"""将双重校验通过的中文暂存 JSON 保守晋级到正式目录。

EN: Conservatively promote staged Chinese JSON that passed double validation into the formal directory.

JA: 二重検証に合格した中国語の一時 JSON を、保守的に正式ディレクトリへ昇格させる。
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

from audit_chinese_json_against_sources import read_source_lines


TZ_JST = timezone(timedelta(hours=9))
NON_BUSINESS_IDENTITY_TOKENS = (
    "学生会", "学生社联", "学生组织", "学联", "社团", "同乡会", "联谊会", "联谊",
    "青年志愿者协会", "志愿者协会", "校友会", "校内职务", "在校任职", "社团任职",
    "课代表", "课程代表", "指导老师", "指导教师", "导师：", "导师:",
)


def source_key(value: str) -> str:
    return os.path.normcase(os.path.normpath(value or ""))


def structured_has_non_business_identity(structured: dict) -> bool:
    """只检查经历身份字段；正文工作描述中的普通词语不作误杀。

    EN: Only check the identity fields of experiences; ordinary words in the job description body are not false positives.

    JA: 経歴の識別フィールドだけをチェックする。職務説明本文中の一般的な語句で誤って弾かない。
    """
    for resume in structured.get("resumes") or []:
        for list_name, fields in (
            ("work_experiences", ("company_name", "position", "position_dept")),
            # 协会可以是合法的项目客户或培训机构；只过滤“协会职务/社团任职”本身。
            # EN: An association can legitimately be a project client or training provider; only filter "association post / society membership" itself.
            # JA: 協会は正当なプロジェクトの顧客や研修機関になり得る。除外するのは「協会での役職／団体での任職」そのものだけ。
            ("project_list", ("project_name", "role_name")),
            ("training_list", ("training_name",)),
        ):
            for row in resume.get(list_name) or []:
                identity = "|".join(str((row or {}).get(field) or "") for field in fields)
                if any(token in identity for token in NON_BUSINESS_IDENTITY_TOKENS):
                    return True
    return False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--staging-dir", type=Path, required=True)
    parser.add_argument("--formal-dir", type=Path, required=True)
    parser.add_argument("--audit-report", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, help="只处理增量清单中已有 staging_json 的源文件" " / Process only the source files that already have staging_json in the incremental list / 増分一覧で staging_json が既にある元ファイルだけを処理する")
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    audit = json.loads(args.audit_report.read_text(encoding="utf-8"))
    affected = {
        source_key(str(record.get("json") or ""))
        for record in audit.get("records") or []
        if record.get("issues")
    }
    allowed_sources: set[str] | None = None
    if args.manifest:
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
        allowed_sources = {
            source_key(str(item.get("source_path") or ""))
            for item in manifest.get("items") or []
            if item.get("staging_json") or item.get("output_json")
        }
    audit_covers_manifest = bool(
        allowed_sources is not None
        and int(audit.get("total_json") or 0) == len(allowed_sources)
        and int(audit.get("unreadable_sources") or 0) == 0
    )

    formal_by_source: dict[str, Path] = {}
    for path in args.formal_dir.glob("*.json"):
        if path.name.startswith("_"):
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        original = str((payload.get("source") or {}).get("original_path") or "")
        if original:
            formal_by_source[source_key(original)] = path

    promoted: list[dict] = []
    rejected_counts = {
        "already_completed": 0,
        "audit_issue": 0,
        "source_unreadable": 0,
        "non_business_identity": 0,
        "invalid_json": 0,
    }
    for staging_path in sorted(args.staging_dir.glob("*.json")):
        if staging_path.name.startswith("_") or staging_path.name in {args.audit_report.name, args.report.name}:
            continue
        if source_key(str(staging_path)) in affected:
            rejected_counts["audit_issue"] += 1
            continue
        try:
            payload = json.loads(staging_path.read_text(encoding="utf-8"))
        except Exception:
            rejected_counts["invalid_json"] += 1
            continue
        original = str((payload.get("source") or {}).get("original_path") or "")
        key = source_key(original)
        if allowed_sources is not None and key not in allowed_sources:
            continue
        # 正式目录中已有同一源文件即视为完成：纯增量流程绝不覆盖或复检。
        # EN: If the formal directory already has the same source file, treat it as done: the purely incremental flow never overwrites or re-checks.
        # JA: 正式ディレクトリに同じソースファイルがあれば完了とみなす。純粋な増分フローは決して上書きも再チェックもしない。
        if key in formal_by_source:
            rejected_counts["already_completed"] += 1
            continue
        try:
            readable = bool(original and Path(original).is_file() and read_source_lines(Path(original)))
        except Exception:
            readable = False
        # 老式 .doc 可能无法被底层读取器直接打开，但字段审计会使用对应 HTML 证据回退。
        # 只有当审计完整覆盖本次 manifest 且 unreadable_sources=0 时才接受该回退。
        # EN: Old-style .doc files may not open directly in the underlying reader, but the field audit falls back to the matching HTML evidence.
        #     This fallback is accepted only when the audit fully covers this manifest and unreadable_sources=0.
        # JA: 旧形式の .doc は基盤のリーダーで直接開けないことがあるが、フィールド監査は対応する HTML の証拠にフォールバックする。
        #     このフォールバックは、監査が今回の manifest を完全に網羅し、かつ unreadable_sources=0 のときだけ受け入れる。
        if not readable and not audit_covers_manifest:
            rejected_counts["source_unreadable"] += 1
            continue
        structured = payload.get("structured_data") or {}
        if structured_has_non_business_identity(structured):
            rejected_counts["non_business_identity"] += 1
            continue

        destination = args.formal_dir / staging_path.name
        stem, suffix = destination.stem, destination.suffix
        sequence = 2
        while destination.exists():
            destination = args.formal_dir / f"{stem}_{sequence}{suffix}"
            sequence += 1
        formal_by_source[key] = destination
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(destination.suffix + ".tmp")
        shutil.copyfile(staging_path, temporary)
        os.replace(temporary, destination)
        promoted.append({"source": original, "staging": str(staging_path), "formal": str(destination)})

    report = {
        "completed_at": datetime.now(TZ_JST).isoformat(),
        "staging_total": len(allowed_sources) if allowed_sources is not None else len([p for p in args.staging_dir.glob("*.json") if not p.name.startswith("_") and p.name != args.audit_report.name]),
        "promoted": len(promoted),
        "rejected_counts": rejected_counts,
        "items": promoted,
    }
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("staging_total", "promoted", "rejected_counts")}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
