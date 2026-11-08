"""按已解析身份与联系方式，暂存 complete-v1 中可严格审计的多语言候选。

EN: Based on the parsed identity and contact details, stage the multilingual candidates in complete-v1 that can be strictly audited.

JA: 解析済みの本人情報と連絡先に基づいて、complete-v1 の中で厳格に監査できる多言語の候補を一時保存する。
"""

from __future__ import annotations

import argparse
import copy
import json
import re
from collections import defaultdict
from pathlib import Path


def compact(value: object) -> str:
    return re.sub(r"\s+", "", str(value or "")).casefold()


def identity(payload: dict) -> tuple[str, str, str]:
    base = (payload.get("structured_data") or {}).get("base_info") or {}
    name = compact(base.get("full_name") or base.get("name"))
    phone = re.sub(r"\D", "", str(base.get("phone") or ""))
    email_match = re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", str(base.get("email") or ""))
    return name, phone[-11:] if len(phone) >= 11 else phone, email_match.group(0).casefold() if email_match else ""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--identity-json-dir", type=Path, required=True)
    parser.add_argument("--complete-v1", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--allow-unique-name", action="store_true")
    parser.add_argument("--required-languages", nargs="+", default=["zh", "jp", "en"])
    args = parser.parse_args()

    index: dict[tuple[str, str], list[tuple[Path, dict]]] = defaultdict(list)
    name_index: dict[str, list[tuple[Path, dict]]] = defaultdict(list)
    for path in args.complete_v1.glob("*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        name, phone, email = identity(payload)
        if name:
            name_index[name].append((path, payload))
        if name and phone:
            index[(name, phone)].append((path, payload))
        if name and email:
            index[(name, email)].append((path, payload))

    args.output_dir.mkdir(parents=True, exist_ok=True)
    results = []
    seen_sources: set[str] = set()
    for parsed_path in args.identity_json_dir.glob("*.json"):
        if parsed_path.name.startswith("_"):
            continue
        parsed = json.loads(parsed_path.read_text(encoding="utf-8"))
        source_path = str((parsed.get("source") or {}).get("original_path") or "")
        if not source_path or source_path.casefold() in seen_sources:
            continue
        seen_sources.add(source_path.casefold())
        name, phone, email = identity(parsed)
        matches: dict[str, tuple[Path, dict]] = {}
        for contact in (phone, email):
            if not contact:
                continue
            for candidate_path, candidate in index.get((name, contact), []):
                matches[str(candidate_path).casefold()] = (candidate_path, candidate)
        match_basis = "name_and_contact"
        if not matches and args.allow_unique_name:
            eligible = []
            for candidate_path, candidate in name_index.get(name, []):
                languages = {
                    str(resume.get("resume_language") or resume.get("resume_languge") or "").casefold()
                    for resume in ((candidate.get("structured_data") or {}).get("resumes") or [])
                }
                if set(args.required_languages).issubset(languages):
                    eligible.append((candidate_path, candidate))
            if len(eligible) == 1:
                candidate_path, candidate = eligible[0]
                matches[str(candidate_path).casefold()] = (candidate_path, candidate)
                match_basis = "unique_name_with_three_languages"
        item = {"source_path": source_path, "parsed_json": str(parsed_path), "name": name, "phone": phone, "email": email}
        if len(matches) != 1:
            item.update(status="no_unique_strong_match", matches=[str(row[0]) for row in matches.values()])
            results.append(item)
            continue
        candidate_path, candidate = next(iter(matches.values()))
        languages = {
            str(resume.get("resume_language") or resume.get("resume_languge") or "").casefold()
            for resume in ((candidate.get("structured_data") or {}).get("resumes") or [])
        }
        if not set(args.required_languages).issubset(languages):
            item.update(status="candidate_missing_languages", candidate_json=str(candidate_path), languages=sorted(languages))
            results.append(item)
            continue
        staged = copy.deepcopy(candidate)
        source = staged.setdefault("source", {})
        source["original_path"] = source_path
        source["converter"] = "complete-v1-identity-contact-reuse"
        source["actual_resume_languages"] = list(args.required_languages)
        source["note"] = (str(source.get("note") or "") + " 同姓名及联系方式的重复源文件；候选需再通过当前源文审计。").strip()
        target = args.output_dir / candidate_path.name
        suffix = 2
        while target.exists():
            target = args.output_dir / f"{candidate_path.stem}_{suffix}.json"
            suffix += 1
        target.write_text(json.dumps(staged, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        item.update(status="staged", candidate_json=str(candidate_path), output_json=str(target), match_basis=match_basis)
        results.append(item)

    report = {
        "staged": sum(row.get("status") == "staged" for row in results),
        "not_staged": sum(row.get("status") != "staged" for row in results),
        "items": results,
    }
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key != "items"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
