"""规范用户 OCR JSON 到正式模板，并只暂存结构和内容均有效的简历。

EN: Normalise the user's OCR JSON to the formal template, and stage only résumés whose structure and content are both valid.

JA: ユーザーの OCR JSON を正式テンプレートに正規化し、構造と内容の両方が有効な履歴書だけを一時保存する。
"""

from __future__ import annotations

import argparse
import json
import os
import re
from collections import defaultdict
from pathlib import Path

from reuse_complete_v1_jsons import validate_json


BAD_NAME = re.compile(r"^(?:未知|无|姓名|待确认姓名|unknown|none|n/?a)$", re.I)
INVALID_FILENAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
OLD_LIST_FIELDS = {
    "certificate_info": "certificate_list",
    "language_info": "language_list",
    "skills_info": "skills_list",
    "training_experiences": "training_list",
    "project_experiences": "project_list",
    "communication_assessment": "communication_list",
}
LIST_FIELDS = (
    "work_experiences", "education_list", "certificate_list", "language_list",
    "skills_list", "training_list", "project_list", "communication_list",
)


def norm(value: object) -> str:
    return os.path.normcase(os.path.normpath(str(value or "")))


def safe_filename_part(value: object) -> str:
    return INVALID_FILENAME.sub("_", str(value or "").strip()).strip(" .")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json-dir", type=Path, required=True)
    parser.add_argument("--map", type=Path, required=True)
    parser.add_argument("--document-manifest", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    rows = json.loads(args.map.read_text(encoding="utf-8"))
    by_ocr_name: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        ocr_path = str(row.get("ocr_document_path") or "")
        if ocr_path:
            by_ocr_name[Path(ocr_path).name.casefold()].append(row)
    if args.document_manifest:
        manifest = json.loads(args.document_manifest.read_text(encoding="utf-8"))
        for manifest_item in manifest.get("items", []):
            copied_path = str(manifest_item.get("copied_path") or "")
            source_path = str(manifest_item.get("source_path") or "")
            matches = [row for row in rows if norm(row.get("source_path")) == norm(source_path)]
            if copied_path and len(matches) == 1:
                by_ocr_name[Path(copied_path).name.casefold()] = matches

    args.output_dir.mkdir(parents=True, exist_ok=True)
    results = []
    claimed: set[str] = set()
    for path in sorted(args.json_dir.glob("*.json")):
        errors: list[str] = []
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            results.append({"input_json": str(path), "status": "invalid", "errors": [f"invalid_json:{exc}"]})
            continue

        source = payload.setdefault("source", {})
        source_files = source.get("source_files") or []
        matched_rows = []
        enriched_files = []
        for value in source_files:
            item = dict(value) if isinstance(value, dict) else {"filename": str(value)}
            filename = str(item.get("filename") or "")
            matches = by_ocr_name.get(filename.casefold(), [])
            if len(matches) != 1:
                errors.append(f"ocr_source_match_count:{filename}:{len(matches)}")
                continue
            row = matches[0]
            matched_rows.append(row)
            item["original_path"] = str(row.get("source_path") or "")
            item["ocr_document_path"] = str(row.get("ocr_document_path") or "")
            enriched_files.append(item)
        if not matched_rows:
            errors.append("missing_mapped_source_files")
        originals = [str(row.get("source_path") or "") for row in matched_rows]
        if any(norm(value) in claimed for value in originals):
            errors.append("source_claimed_by_multiple_json")
        claimed.update(norm(value) for value in originals)
        if originals:
            source.update({
                "source_files": enriched_files,
                "original_path": originals[0],
                "path": originals[0],
                "filename": Path(originals[0]).name,
                "merged_original_paths": originals,
                "converter": "user-ocr-json",
            })

        structured = payload.get("structured_data")
        if not isinstance(structured, dict):
            errors.append("missing_structured_data")
            structured = {}
        expected = structured.get("expected_info")
        if isinstance(expected, list):
            expected = next((item for item in expected if isinstance(item, dict)), {})
            structured["expected_info"] = expected
        resumes = structured.get("resumes")
        if not isinstance(resumes, list) or not resumes:
            errors.append("missing_resumes")
            resumes = []
        for resume in resumes:
            if not isinstance(resume, dict):
                errors.append("resume_not_object")
                continue
            language = str(resume.get("resume_language") or resume.pop("resume_languge", "") or "").strip()
            resume["resume_language"] = language
            for old, new in OLD_LIST_FIELDS.items():
                if new not in resume and old in resume:
                    resume[new] = resume.pop(old)
                else:
                    resume.pop(old, None)
            for field in LIST_FIELDS:
                if not isinstance(resume.get(field), list):
                    resume[field] = []
            if not isinstance(resume.get("expected_list"), list):
                old_expected = resume.pop("expected_info", None)
                resume["expected_list"] = old_expected if isinstance(old_expected, list) else ([dict(expected)] if isinstance(expected, dict) else [])
            for work in resume["work_experiences"]:
                if isinstance(work, dict):
                    work.setdefault("position_achievements", "")

        base = structured.get("base_info") if isinstance(structured.get("base_info"), dict) else {}
        full_name = str(base.get("full_name") or "").strip()
        phone = re.sub(r"\D", "", str(base.get("phone") or ""))
        email = str(base.get("email") or "").strip()
        if not full_name or BAD_NAME.fullmatch(full_name):
            errors.append("invalid_full_name")
        if payload.get("classification", {}).get("document_type") != "resume":
            errors.append("not_classified_as_resume")
        if payload.get("extraction", {}).get("status") != "success":
            errors.append("extraction_not_success")
        raw_text = str(payload.get("raw_text") or "")
        if len(raw_text.strip()) < 100:
            errors.append("raw_text_too_short")
        structural_entries = sum(
            len(resume.get(field) or [])
            for resume in resumes if isinstance(resume, dict)
            for field in ("work_experiences", "education_list", "project_list", "training_list")
        )
        if structural_entries == 0:
            errors.append("insufficient_resume_structure")

        contact = phone or email or "无联系方式"
        output = args.output_dir / f"{safe_filename_part(full_name)}_{safe_filename_part(contact)}.json"
        if output.exists():
            sequence = 2
            while (args.output_dir / f"{safe_filename_part(full_name)}_{safe_filename_part(contact)}_{sequence}.json").exists():
                sequence += 1
            output = args.output_dir / f"{safe_filename_part(full_name)}_{safe_filename_part(contact)}_{sequence}.json"
        if originals:
            errors.extend(validate_json(output, payload, originals[0], "", "", "中文", strict=False))
        errors = sorted(set(errors))
        if errors:
            results.append({"input_json": str(path), "status": "invalid", "errors": errors, "original_paths": originals})
            continue
        output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        results.append({"input_json": str(path), "output_json": str(output), "status": "valid", "original_paths": originals})

    report = {
        "total": len(results),
        "valid": sum(item["status"] == "valid" for item in results),
        "invalid": sum(item["status"] == "invalid" for item in results),
        "source_documents": sum(len(item.get("original_paths") or []) for item in results if item["status"] == "valid"),
        "items": results,
    }
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("total", "valid", "invalid", "source_documents")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
