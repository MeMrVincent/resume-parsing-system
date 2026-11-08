"""按源路径明确姓名与正式库唯一姓名匹配，暂存复用候选供源文审计。

EN: Match the explicit name from the source path against unique names in the formal store, and stage reuse candidates for the source audit.

JA: ソースのパスにある明確な氏名を正式なデータ内の一意な氏名と照合し、再利用の候補を一時保存して原文監査に回す。
"""

from __future__ import annotations

import argparse
import copy
import json
import re
from collections import defaultdict
from pathlib import Path

from run_chinese_html_to_json import canonicalize_complete_schema


def compact(value: object) -> str:
    return re.sub(r"[\s_\-（）()\[\]·・]+", "", str(value or "")).casefold()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--progress", type=Path, required=True)
    parser.add_argument("--formal-root", type=Path, required=True)
    parser.add_argument("--language-folder", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    progress = json.loads(args.progress.read_text(encoding="utf-8"))
    index: dict[str, list[tuple[Path, dict, str]]] = defaultdict(list)
    for path in args.formal_root.rglob("*.json"):
        if path.name.startswith("_"):
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        name = str(((payload.get("structured_data") or {}).get("base_info") or {}).get("full_name") or "").strip()
        normalized = compact(name)
        if 2 <= len(normalized) <= 20:
            index[normalized].append((path, payload, name))

    args.output_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for item in progress.get("unfinished") or []:
        if item.get("status") != "needs_review" or item.get("language_folder") != args.language_folder:
            continue
        source_path = str(item.get("source_path") or "")
        evidence = compact(" ".join(Path(source_path).parts[-4:]))
        matches = []
        for name_key, candidates in index.items():
            if name_key in evidence and len(candidates) == 1:
                matches.append(candidates[0])
        # 长姓名可能包含短姓名，只保留最长的明确匹配。
        # EN: A long name may contain a short name; keep only the longest explicit match.
        # JA: 長い氏名が短い氏名を含むことがあるため、最も長い明確なマッチだけを残す。
        if matches:
            longest = max(len(compact(row[2])) for row in matches)
            matches = [row for row in matches if len(compact(row[2])) == longest]
        row = {"source_path": source_path, "html_path": item.get("html_path"), "status": "no_unique_name_match"}
        unique_paths = {str(match[0]).casefold(): match for match in matches}
        if len(unique_paths) != 1:
            results.append(row)
            continue
        candidate_path, candidate, name = next(iter(unique_paths.values()))
        staged = copy.deepcopy(candidate)
        staged["structured_data"] = canonicalize_complete_schema(staged.get("structured_data") or {})
        source = staged.setdefault("source", {})
        source["original_path"] = source_path
        source["path"] = source_path
        source["filename"] = Path(source_path).name
        source["converter"] = "formal-unique-name-reuse-candidate"
        source["note"] = (str(source.get("note") or "") + " 仅按源路径唯一姓名暂存，必须通过当前源文审计。 ").strip()
        target = args.output_dir / candidate_path.name
        sequence = 2
        while target.exists():
            target = args.output_dir / f"{candidate_path.stem}_{sequence}{candidate_path.suffix}"
            sequence += 1
        target.write_text(json.dumps(staged, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        row.update(status="staged", full_name=name, candidate_json=str(candidate_path), output_json=str(target))
        results.append(row)
    report = {"staged": sum(r["status"] == "staged" for r in results), "not_staged": sum(r["status"] != "staged" for r in results), "items": results}
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "items"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
