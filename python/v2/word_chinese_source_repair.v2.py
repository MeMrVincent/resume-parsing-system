"""按中文源文审计证据保守修复暂存 JSON。

EN: Conservatively repair staged JSON according to the audit evidence from the Chinese source text.

JA: 中国語の原文の監査証拠に基づいて、一時保存した JSON を保守的に修復する。
"""

from __future__ import annotations

import argparse
import copy
import json
import re
import shutil
from pathlib import Path

from run_chinese_html_to_json import canonicalize_complete_schema


SCHOOL = re.compile(r"大学|学院|学校")
COMPANY = re.compile(r"公司|集团|银行|医院|事务所|研究院|研究所|中心|工厂|厂$|政府|委员会")


def values(issue: dict) -> list[str]:
    raw = issue.get("expected_from_source") or []
    if isinstance(raw, str):
        raw = [raw]
    return [str(v).strip() for v in raw if str(v).strip()]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    audit = json.loads(args.audit.read_text(encoding="utf-8"))
    args.output_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for record in audit.get("records") or []:
        issues = record.get("issues") or []
        if not issues:
            continue
        source_json = Path(str(record.get("json") or ""))
        payload = json.loads(source_json.read_text(encoding="utf-8"))
        structured = canonicalize_complete_schema(copy.deepcopy(payload.get("structured_data") or {}))
        resume = structured["resumes"][0]
        changed = []

        bad_indices: dict[str, list[int]] = {name: [] for name in (
            "certificate_list", "education_list", "project_list", "training_list", "work_experiences"
        )}
        for issue in issues:
            code = str(issue.get("code") or "")
            expected = values(issue)
            if code == "certificate_list.certificate_name":
                match = re.search(r"certificate_list\[(\d+)\]", str(issue.get("path") or ""))
                if match:
                    bad_indices["certificate_list"].append(int(match.group(1)))
                continue
            bad_field_match = re.fullmatch(
                r"(education_list|project_list|training_list|work_experiences)\.(?:school_name|project_name|training_name|company_name)",
                code,
            )
            if bad_field_match:
                list_name = bad_field_match.group(1)
                match = re.search(re.escape(list_name) + r"\[(\d+)\]", str(issue.get("path") or ""))
                if match:
                    bad_indices[list_name].append(int(match.group(1)))
                continue
            if code == "certificate_list.missing":
                existing = {str(row.get("certificate_name") or "") for row in resume["certificate_list"]}
                for value in expected:
                    if value not in existing:
                        resume["certificate_list"].append({"certificate_name": value})
                        existing.add(value)
                        changed.append(f"certificate:{value}")
            elif code == "training_list.missing":
                existing = {str(row.get("training_name") or "") for row in resume["training_list"]}
                for value in expected:
                    if value not in existing and len(value) <= 120:
                        resume["training_list"].append({"training_name": value})
                        existing.add(value)
                        changed.append(f"training:{value}")
            elif code == "project_list.missing":
                existing = {str(row.get("project_name") or "") for row in resume["project_list"]}
                for value in expected:
                    if SCHOOL.search(value) or "已关联" in value or len(value) > 120:
                        continue
                    if value not in existing:
                        resume["project_list"].append({"project_name": value})
                        existing.add(value)
                        changed.append(f"project:{value}")
            elif code == "education_list.missing":
                existing = {str(row.get("school_name") or "") for row in resume["education_list"]}
                for value in expected:
                    if SCHOOL.search(value) and value not in existing:
                        resume["education_list"].append({"school_name": value})
                        existing.add(value)
                        changed.append(f"education:{value}")
            elif code == "work_experiences.missing":
                existing = {str(row.get("company_name") or "") for row in resume["work_experiences"]}
                for value in expected:
                    if COMPANY.search(value) and not SCHOOL.search(value) and value not in existing:
                        resume["work_experiences"].append({"company_name": value})
                        existing.add(value)
                        changed.append(f"work:{value}")
            elif code.startswith("expected_info.") and len(expected) == 1:
                field = code.split(".", 1)[1]
                value = expected[0]
                if field == "expected_salary" and not re.search(r"\d|面谈|面议", value):
                    resume.setdefault("expected_list", [{}])[0][field] = ""
                    changed.append(f"clear_expected:{field}")
                    continue
                if field == "expected_industry" and (len(value) > 50 or "企业性质" in value or "工作" in value):
                    resume.setdefault("expected_list", [{}])[0][field] = ""
                    changed.append(f"clear_expected:{field}")
                    continue
                expected_rows = resume.get("expected_list") or [{}]
                if not resume.get("expected_list"):
                    resume["expected_list"] = expected_rows
                expected_rows[0][field] = value
                changed.append(f"expected:{field}={value}")

        for list_name, indices in bad_indices.items():
            for index in sorted(set(indices), reverse=True):
                if 0 <= index < len(resume[list_name]):
                    removed = resume[list_name].pop(index)
                    changed.append(f"remove_{list_name}:{json.dumps(removed, ensure_ascii=False)}")

        payload["structured_data"] = canonicalize_complete_schema(structured)
        target = args.output_dir / source_json.name
        target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        results.append({"source_path": record.get("source"), "input_json": str(source_json), "output_json": str(target), "changes": changed})
    report = {"repaired": len(results), "with_changes": sum(bool(r["changes"]) for r in results), "items": results}
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "items"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
