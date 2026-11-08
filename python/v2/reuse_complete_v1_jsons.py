from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import tempfile
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any


LIST_FIELDS = (
    "expected_list", "work_experiences", "education_list", "certificate_list",
    "language_list", "skills_list", "training_list", "project_list",
    "communication_list",
)
BASE_FIELDS = {
    "full_name", "gender", "age", "birth_date", "birth_year", "marital_status",
    "children_status", "political_status", "height_cm", "weight_kg",
    "household_registration", "address", "postal_code", "platform_from",
    "platform_resume_id", "phone", "email", "city", "nationality", "pr",
}
EXPECTED_FIELDS = {
    "expected_city", "expected_position", "expected_salary",
    "expected_annual_salary_min", "expected_annual_salary_max",
    "expected_industry", "expected_employment_type", "expected_start_date",
}
CURRENT_FIELDS = {
    "company_name", "company_employees", "company_industry", "position",
    "position_type", "position_salary", "position_dept", "position_report_to",
    "position_subordinate", "employment_type", "annual_salary_min",
    "annual_salary_max", "status", "position_start", "position_resigned",
}
EDUCATION_FIELDS = {
    "school_name", "school_major_name", "school_degree_type", "school_degree_rank",
    "school_education_type", "school_start_ym", "school_end_ym",
}
ITEM_FIELDS = {
    "expected_list": EXPECTED_FIELDS,
    "work_experiences": CURRENT_FIELDS | {
        "resigned_reason", "position_responsibilities", "position_achievements",
    },
    "education_list": EDUCATION_FIELDS,
    "certificate_list": {"certificate_name", "certificate_type", "certificate_time"},
    "language_list": {"language_name", "language_level", "language_certificate", "language_certificate_time"},
    "skills_list": {"skill_name", "skill_level"},
    "training_list": {"sequence_no", "organization_name", "training_name", "start_ym", "end_ym", "certificate_name", "description"},
    "project_list": {"sequence_no", "fingerprint", "project_name", "company_or_client", "role_name", "start_ym", "end_ym", "description", "responsibilities", "achievements", "keywords"},
    "communication_list": {"communicate_time", "communicate_content"},
}
PRIMARY_ITEM_FIELDS = {
    "expected_list": EXPECTED_FIELDS,
    "work_experiences": {"company_name", "position"},
    "education_list": {"school_name"},
    "certificate_list": {"certificate_name"},
    "language_list": {"language_name"},
    "skills_list": {"skill_name"},
    "training_list": {"organization_name", "training_name", "description"},
    "project_list": {"project_name", "description"},
    "communication_list": {"communicate_content"},
}
DATE_ITEM_FIELDS = {
    "position_start", "position_resigned", "school_start_ym", "school_end_ym",
    "certificate_time", "language_certificate_time", "start_ym", "end_ym",
}
LANGUAGE_REQUIREMENTS = {
    "日文": {"zh", "jp"}, "英文": {"zh", "en"}, "中英文": {"zh", "en"},
    "中日文": {"zh", "jp"}, "中英日文": {"zh", "en", "jp"},
    "英日文": {"zh", "en", "jp"}, "德文": {"zh", "de"},
    "中英法文": {"zh", "en", "fr"}, "中法文": {"zh", "fr"},
}


def norm_path(value: str) -> str:
    return os.path.normcase(os.path.normpath(value.strip()))


def digits(value: str) -> str:
    return re.sub(r"\D", "", value or "")


def compact(value: str) -> str:
    return re.sub(r"[\s_\-（）()\[\]]+", "", value or "").casefold()


def valid_date(value: Any) -> bool:
    if not isinstance(value, str) or not value:
        return False
    return bool(
        re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", value)
        or re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:[+-]\d{2}:\d{2}|Z)?", value)
    )


def normalized_language(value: Any) -> str:
    language = str(value or "").strip().casefold()
    return {"ja": "jp", "jpn": "jp", "eng": "en", "deu": "de", "ger": "de", "fra": "fr", "fre": "fr", "cn": "zh", "chi": "zh"}.get(language, language)


def valid_structured_date(value: Any) -> bool:
    if value in (None, ""):
        return True
    if not isinstance(value, str):
        return False
    match = re.fullmatch(r"(\d{4})年(\d{2})月(\d{2})日", value)
    if not match:
        return False
    year, month, day = map(int, match.groups())
    return 1900 <= year <= 2100 and 1 <= month <= 12 and 1 <= day <= 31


def leaf_values(value: Any) -> list[str]:
    results: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            if key not in {"sequence_no", "fingerprint", "resume_language", "resume_languge", "keywords"}:
                results.extend(leaf_values(child))
    elif isinstance(value, list):
        for child in value:
            results.extend(leaf_values(child))
    elif isinstance(value, str) and value.strip():
        results.append(value.strip())
    return results


def validate_json(path: Path, payload: Any, source_path: str, map_phone: str, map_email: str, language_folder: str, strict: bool = False) -> list[str]:
    errors: list[str] = []
    if not isinstance(payload, dict):
        return ["root_not_object"]
    source = payload.get("source")
    if not isinstance(source, dict) or norm_path(str(source.get("original_path") or "")) != norm_path(source_path):
        errors.append("source_path_mismatch")
    dates = payload.get("dates")
    if not isinstance(dates, dict):
        errors.append("missing_dates")
    else:
        for key in ("resume_updated_date", "resume_download_date"):
            if not valid_date(dates.get(key)):
                errors.append(f"invalid_{key}")
    structured = payload.get("structured_data")
    if not isinstance(structured, dict):
        return errors + ["missing_structured_data"]
    base = structured.get("base_info")
    if not isinstance(base, dict):
        errors.append("missing_base_info")
        base = {}
    elif not BASE_FIELDS.issubset(base):
        errors.append("incomplete_base_info")
    full_name = str(base.get("full_name") or "").strip()
    phone = digits(str(base.get("phone") or ""))
    email = str(base.get("email") or "").strip().casefold()
    if not full_name:
        errors.append("missing_full_name")
    stem = compact(path.stem)
    if full_name and compact(full_name) not in stem:
        errors.append("filename_name_mismatch")
    filename_has_contact = bool(
        (phone and phone in digits(path.stem))
        or (email and compact(email) in compact(path.stem))
        or (not phone and not email and "无联系方式" in path.stem)
    )
    if not filename_has_contact:
        errors.append("filename_contact_mismatch")
    expected = structured.get("expected_info")
    current = structured.get("current_info")
    education = structured.get("education_info")
    if not isinstance(expected, dict) or not EXPECTED_FIELDS.issubset(expected):
        errors.append("incomplete_expected_info")
    if not isinstance(current, dict) or not CURRENT_FIELDS.issubset(current):
        errors.append("incomplete_current_info")
    if not isinstance(education, dict) or not EDUCATION_FIELDS.issubset(education):
        errors.append("incomplete_education_info")
    resumes = structured.get("resumes")
    if not isinstance(resumes, list) or not resumes:
        errors.append("missing_resumes")
    else:
        languages: list[str] = []
        for index, resume in enumerate(resumes):
            if not isinstance(resume, dict):
                errors.append(f"resume_{index}_not_object")
                continue
            if not isinstance(resume.get("base_info"), dict):
                errors.append(f"resume_{index}_missing_base")
            language = normalized_language(resume.get("resume_language") or resume.get("resume_languge"))
            languages.append(language)
            for field in LIST_FIELDS:
                if not isinstance(resume.get(field), list):
                    errors.append(f"resume_{index}_{field}_not_list")
                    continue
                if strict:
                    seen_items: set[str] = set()
                    for item_index, item in enumerate(resume[field]):
                        prefix = f"resume_{index}_{field}_{item_index}"
                        if not isinstance(item, dict):
                            errors.append(f"{prefix}_not_object")
                            continue
                        required = ITEM_FIELDS[field]
                        if not required.issubset(item):
                            errors.append(f"{prefix}_incomplete_fields")
                        for key in required:
                            if key in item and key != "sequence_no" and not isinstance(item[key], str):
                                errors.append(f"{prefix}_{key}_not_string")
                        if not any(str(item.get(key) or "").strip() for key in PRIMARY_ITEM_FIELDS[field]):
                            errors.append(f"{prefix}_missing_primary")
                        for key in DATE_ITEM_FIELDS.intersection(item):
                            if not valid_structured_date(item.get(key)):
                                errors.append(f"{prefix}_{key}_invalid_date")
                        fingerprint = json.dumps(item, ensure_ascii=False, sort_keys=True)
                        if fingerprint in seen_items:
                            errors.append(f"resume_{index}_{field}_duplicate_item")
                        seen_items.add(fingerprint)
            if not language:
                errors.append(f"resume_{index}_missing_language")
        first = resumes[0] if isinstance(resumes[0], dict) else {}
        if first.get("base_info") != base:
            errors.append("top_base_not_synced")
        if normalized_language(first.get("resume_language") or first.get("resume_languge")) != "zh":
            errors.append("first_resume_not_zh")
        if strict:
            if len(languages) != len(set(languages)):
                errors.append("duplicate_resume_language")
            required_languages = LANGUAGE_REQUIREMENTS.get(language_folder, {"zh"})
            if not required_languages.issubset(set(languages)):
                errors.append("missing_required_language_variants")
        first_expected = first.get("expected_list") if isinstance(first.get("expected_list"), list) else []
        expected_snapshot = first_expected[0] if first_expected else {key: "" for key in EXPECTED_FIELDS}
        if expected != expected_snapshot:
            errors.append("top_expected_not_synced")
        first_work = first.get("work_experiences") if isinstance(first.get("work_experiences"), list) else []
        if any(str(current.get(key) or "") for key in {"company_name", "position", "position_start"}) and not any(
            isinstance(item, dict)
            and str(item.get("company_name") or "") == str(current.get("company_name") or "")
            and str(item.get("position") or "") == str(current.get("position") or "")
            for item in first_work
        ):
            errors.append("top_current_not_in_resume")
        first_education = first.get("education_list") if isinstance(first.get("education_list"), list) else []
        if any(str(education.get(key) or "") for key in EDUCATION_FIELDS) and not any(
            isinstance(item, dict)
            and str(item.get("school_name") or "") == str(education.get("school_name") or "")
            and str(item.get("school_degree_type") or "") == str(education.get("school_degree_type") or "")
            for item in first_education
        ):
            errors.append("top_education_not_in_resume")
    raw_text = payload.get("raw_text")
    if not isinstance(raw_text, str) or len(raw_text.strip()) < 20:
        errors.append("raw_text_missing_or_short")
    raw_compact = compact(raw_text if isinstance(raw_text, str) else "")
    if full_name and compact(full_name) not in raw_compact:
        errors.append("name_missing_from_raw_text")
    map_phone_digits = digits(map_phone)
    map_email_clean = (map_email or "").strip().casefold()
    if map_phone_digits and phone and map_phone_digits != phone:
        errors.append("map_phone_conflict")
    if map_email_clean and email and map_email_clean != email:
        errors.append("map_email_conflict")
    if phone and phone not in digits(raw_text if isinstance(raw_text, str) else ""):
        errors.append("phone_missing_from_raw_text")
    if email and compact(email) not in raw_compact:
        errors.append("email_missing_from_raw_text")
    if strict and isinstance(resumes, list):
        missing_leaf_values = 0
        for value in leaf_values(resumes):
            normalized = compact(value)
            if len(normalized) >= 3 and normalized not in raw_compact:
                missing_leaf_values += 1
                if missing_leaf_values >= 3:
                    break
        if missing_leaf_values:
            errors.append("raw_text_missing_structured_values")
    if strict and isinstance(resumes, list):
        # 严格拦截废弃字段、校内奖励与错位文本
        # EN: Strictly intercept deprecated fields, campus awards and misplaced text
        # JA: 廃止フィールド・学内の表彰・ずれたテキストを厳格に遮断する
        school_award_kws = {"奖学金", "三好学生", "优秀学生", "优秀干部", "优秀共青团员", "优秀干事"}
        invalid_school_name_kws = {"负责", "组织", "管理", "运营", "推文", "项目", "实习", "工作", "审核"}
        invalid_company_name_kws = {"排名", "本科", "硕士", "学士", "博士", "1/", "2/", "3/"}
        
        for index, resume in enumerate(resumes):
            if isinstance(resume, dict):
                # 1. 检查社团经历是否被提取 (禁止提取社团经历)
                # EN: 1. Check whether club/society experience was extracted (extracting club experience is forbidden)
                # JA: 1. サークル・団体活動の経験が抽出されていないかチェックする（抽出は禁止）
                social_exp = resume.get("social_experiences")
                if isinstance(social_exp, list) and len(social_exp) > 0:
                    errors.append(f"resume_{index}_forbidden_social_experiences_extracted")
                
                # 2. 检查证书列表中是否包含了校内奖励
                # EN: 2. Check whether the certificate list contains campus awards
                # JA: 2. 資格の一覧に学内の表彰が含まれていないかチェックする
                cert_list = resume.get("certificate_list") or []
                for cert in cert_list:
                    c_name = str(cert.get("certificate_name") or "")
                    if any(award in c_name for award in school_award_kws):
                        errors.append(f"resume_{index}_certificate_contains_school_award")
                        break
                        
                # 3. 检查教育经历 school_name 是否包含错位长动词
                # EN: 3. Check whether school_name in education history contains misplaced long verbs
                # JA: 3. 学歴の school_name にずれた長い動詞句が含まれていないかチェックする
                edu_list = resume.get("education_list") or []
                for edu in edu_list:
                    s_name = str(edu.get("school_name") or "")
                    if len(s_name) > 25 or any(kw in s_name for kw in invalid_school_name_kws):
                        errors.append(f"resume_{index}_invalid_school_name")
                        break
                        
                # 4. 检查工作经历 company_name 是否包含教育/排名特征
                # EN: 4. Check whether company_name in work history contains education/ranking features
                # JA: 4. 職歴の company_name に学歴・ランキングの特徴が含まれていないかチェックする
                work_list = resume.get("work_experiences") or []
                for work in work_list:
                    c_name = str(work.get("company_name") or "")
                    if any(kw in c_name for kw in invalid_company_name_kws):
                        errors.append(f"resume_{index}_invalid_company_name")
                        break

    if strict:
        for key, value in base.items():
            if key in BASE_FIELDS and not isinstance(value, str):
                errors.append(f"base_{key}_not_string")
        for snapshot_name, snapshot in (("expected", expected), ("current", current), ("education", education)):
            if isinstance(snapshot, dict) and any(not isinstance(value, str) for value in snapshot.values()):
                errors.append(f"top_{snapshot_name}_non_string_value")
    return sorted(set(errors))


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--map", type=Path, required=True)
    parser.add_argument("--source-json-dir", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--languages", nargs="+", required=True)
    parser.add_argument("--statuses", nargs="+", default=["passed"])
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--extra-html-root", type=Path)
    parser.add_argument("--only-existing-html", action="store_true")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    data = json.loads(args.map.read_text(encoding="utf-8"))
    records = data if isinstance(data, list) else data.get("records", [])
    selected = [
        row for row in records
        if (not args.statuses or row.get("status") in args.statuses or "status" not in row)
        and (not args.languages or row.get("language_folder") in args.languages or "language_folder" not in row)
        and (not args.only_existing_html or Path(str(row.get("html_path") or "")).is_file())
    ]
    source_index: dict[str, list[tuple[Path, Any]]] = defaultdict(list)
    invalid_json_files: list[dict[str, str]] = []
    for path in sorted(args.source_json_dir.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            original = str((payload.get("source") or {}).get("original_path") or "")
            if original:
                source_index[norm_path(original)].append((path, payload))
        except Exception as exc:
            invalid_json_files.append({"json_path": str(path), "error": str(exc)})

    summary = Counter()
    items: list[dict[str, Any]] = []
    now = datetime.now().astimezone().isoformat()
    for row in selected:
        matches = source_index.get(norm_path(str(row.get("source_path") or "")), [])
        item: dict[str, Any] = {
            "source_path": row.get("source_path"),
            "language_folder": row.get("language_folder"),
            "html_path": row.get("html_path"),
        }
        if not matches:
            item["status"] = "json_not_found"
            summary["json_not_found"] += 1
            items.append(item)
            continue
        if len(matches) > 1:
            item["status"] = "multiple_json_matches"
            item["matches"] = [str(path) for path, _payload in matches]
            summary["multiple_json_matches"] += 1
            items.append(item)
            continue
        json_path, payload = matches[0]
        errors = validate_json(
            json_path, payload, str(row.get("source_path") or ""),
            str(row.get("phone") or ""), str(row.get("email") or ""),
            str(row.get("language_folder") or ""), args.strict,
        )
        item["candidate_json"] = str(json_path)
        if errors:
            item["status"] = "json_invalid"
            item["issues"] = errors
            summary["json_invalid"] += 1
            items.append(item)
            continue
        destination = args.output_root / str(row.get("language_folder")) / json_path.name
        item["status"] = "reused"
        item["output_json"] = str(destination)
        deleted: list[str] = []
        if args.apply:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(json_path, destination)
            html_path = Path(str(row.get("html_path") or ""))
            if html_path.is_file():
                html_path.unlink()
                deleted.append(str(html_path))
            if args.extra_html_root:
                staged = args.extra_html_root / html_path.name
                if staged.is_file() and staged != html_path:
                    staged.unlink()
                    deleted.append(str(staged))
            row["json_status"] = "passed_reused_complete_v1"
            row["json_path"] = str(destination)
            row["json_source"] = "complete-v1"
            row["json_validated_at"] = now
            row["json_validation_profile"] = "complete-v1-strict-v2" if args.strict else "complete-v1-standard-v1"
            row["html_status"] = "deleted_after_valid_json_reuse"
            row["parsed_completed"] = True
        item["deleted_html"] = deleted
        summary["reused"] += 1
        items.append(item)

    if args.apply:
        atomic_json(args.map, records)
    report = {
        "mode": "apply" if args.apply else "dry-run",
        "validation_profile": "complete-v1-strict-v2" if args.strict else "complete-v1-standard-v1",
        "languages": args.languages,
        "selected": len(selected),
        "summary": dict(summary),
        "invalid_source_json_files": invalid_json_files,
        "items": items,
    }
    atomic_json(args.report, report)
    print(json.dumps({key: value for key, value in report.items() if key != "items"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
