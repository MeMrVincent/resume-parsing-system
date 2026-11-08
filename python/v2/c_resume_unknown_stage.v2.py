"""复制人工疑难和身份不可恢复的源文档到 unknown，并生成可追溯清单。

EN: Copy source documents that are manually difficult or whose identity cannot be recovered into unknown, and produce a traceable list.

JA: 人手でも難しいもの、本人を特定できないものの元文書を unknown にコピーし、追跡可能な一覧を作る。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path


DEFAULT_TARGET_STATUSES = {"deferred_manual_review", "identity_unrecoverable"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--progress", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--statuses", nargs="+", default=sorted(DEFAULT_TARGET_STATUSES))
    args = parser.parse_args()

    progress = json.loads(args.progress.read_text(encoding="utf-8"))
    target_statuses = set(args.statuses)
    selected = [item for item in progress.get("unfinished", []) if item.get("status") in target_statuses]
    args.output_dir.mkdir(parents=True, exist_ok=True)

    records = []
    copied = missing = 0
    for item in selected:
        source = Path(str(item.get("source_path") or ""))
        digest = hashlib.sha1(str(source).casefold().encode("utf-8")).hexdigest()[:12]
        target = args.output_dir / f"{source.stem}_{digest}{source.suffix}"
        record = {
            "status": item.get("status"),
            "language_folder": item.get("language_folder"),
            "source_path": str(source),
            "html_path": item.get("html_path"),
            "copied_path": str(target),
        }
        if source.is_file():
            shutil.copy2(source, target)
            record["copy_status"] = "copied"
            copied += 1
        else:
            record["copy_status"] = "source_missing"
            missing += 1
        records.append(record)

    report = {
        "selected": len(selected),
        "copied": copied,
        "missing": missing,
        "by_status": {
            status: sum(1 for item in selected if item.get("status") == status)
            for status in sorted(target_statuses)
        },
        "items": records,
    }
    args.manifest.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("selected", "copied", "missing", "by_status")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
