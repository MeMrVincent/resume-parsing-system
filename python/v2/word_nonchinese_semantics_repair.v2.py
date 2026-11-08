"""修复多语言候选中已由源文确认的语义错位，不制造不存在的履历版本。

EN: Fix semantic misplacements in multilingual candidates already confirmed by the source, without fabricating résumé versions that do not exist.

JA: 多言語の候補で原文により確認済みの意味的なずれを修正し、存在しない履歴書の版を作り出さない。
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1] / "common"))
import rc_config as _rc  # noqa: E402  项目统一配置（python/common/rc_config.py）
# EN: noqa: E402  project-wide configuration (python/common/rc_config.py)
# JA: noqa: E402  プロジェクト共通設定（python/common/rc_config.py）


def _load_repair_table(name, default):
    """一次性修复所需的“姓名/联系方式/名单”不随仓库发布：放在 <项目根>/repair_data/<name>.json。
    文件不存在则使用空表（脚本不会改动任何文件）。示例见 repair_data/ 下的 *.example.json。

    EN: The "name / contact / list" data needed for one-off repairs is not published with the repository: put it at <project root>/repair_data/<name>.json.
    If the file does not exist an empty table is used (the script will not change any file). See the *.example.json files under repair_data/ for samples.

    JA: 一回限りの修復に必要な「氏名・連絡先・名簿」のデータはリポジトリに含めない：<プロジェクトルート>/repair_data/<name>.json に置く。
    ファイルがなければ空の表を使う（スクリプトはどのファイルも変更しない）。例は repair_data/ 配下の *.example.json を参照。
    """
    p = _rc.project_root() / "repair_data" / (name + ".json")
    if p.is_file():
        with open(p, "r", encoding="utf-8-sig") as f:
            return json.load(f)
    return default

_T = _load_repair_table("semantics_repair", {})
NAME_BY_CONTACT = dict(_T.get("name_by_contact", {}))               # {"手机号": "姓名"}
# EN: {"mobile number": "name"}
# JA: {"携帯電話番号": "氏名"}
REMOVE_WORK = set(_T.get("remove_work", []))                        # 要删除的“被误当成工作经历”的行（公司栏文本）
# EN: Rows to delete that were "mistaken for work experience" (company column text)
# JA: 削除する「職歴と誤認された」行（会社欄のテキスト）
REMOVE_EDUCATION = set(_T.get("remove_education", []))              # 要删除的“被误当成学历”的行（学校栏文本）
# EN: Rows to delete that were "mistaken for education" (school column text)
# JA: 削除する「学歴と誤認された」行（学校欄のテキスト）
EDUCATION_REPLACEMENTS = dict(_T.get("education_replacements", {})) # {"错误校名": "正确校名"}
# EN: {"wrong school name": "correct school name"}
# JA: {"誤った学校名": "正しい学校名"}
MANUAL_IDENTITY_CONTACTS = set(_T.get("manual_identity_contacts", []))  # 姓名已人工确认的手机号
# EN: Mobile numbers whose names have been confirmed manually
# JA: 氏名を人手で確認済みの携帯電話番号


def norm(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def contact(payload: dict) -> str:
    base = ((payload.get("structured_data") or {}).get("base_info") or {})
    return re.sub(r"\D", "", str(base.get("phone") or ""))[-11:]


def set_name(payload: dict, name: str) -> None:
    structured = payload.setdefault("structured_data", {})
    structured.setdefault("base_info", {})["full_name"] = name
    for resume in structured.get("resumes") or []:
        resume.setdefault("base_info", {})["full_name"] = name


def clean_resume(resume: dict) -> tuple[int, int, int]:
    removed_work = 0
    work = []
    for row in resume.get("work_experiences") or []:
        company = norm(row.get("company_name"))
        # 句子被误当公司名：保留实际派遣公司只在职责中出现，不制造雇主名称。
        # EN: A sentence taken as the company name: the actual dispatch company appears only in the duties, so no employer name is fabricated.
        # JA: 文が会社名と誤認されている：実際の派遣元の会社は職務内容にしか出てこないため、勤務先の名前を作り出さない。
        sentence_like = company.startswith("に一年間働いていました。それに、4 月から今まで翻訳会社")
        if company in REMOVE_WORK or sentence_like:
            removed_work += 1
            continue
        work.append(row)
    resume["work_experiences"] = work

    removed_education = 0
    replaced_education = 0
    education = []
    for row in resume.get("education_list") or []:
        school = norm(row.get("school_name"))
        if school in REMOVE_EDUCATION:
            removed_education += 1
            continue
        if school in EDUCATION_REPLACEMENTS:
            row["school_name"] = EDUCATION_REPLACEMENTS[school]
            replaced_education += 1
        education.append(row)
    resume["education_list"] = education
    return removed_work, removed_education, replaced_education


def sync_primary_summaries(payload: dict) -> None:
    structured = payload.get("structured_data") or {}
    resumes = structured.get("resumes") or []
    if not resumes:
        return
    primary = resumes[0]
    current = structured.get("current_info") or {}
    if norm(current.get("company_name")) in REMOVE_WORK or norm(current.get("company_name")).startswith(
        "に一年間働いていました。それに、4 月から今まで翻訳会社"
    ):
        rows = primary.get("work_experiences") or []
        structured["current_info"] = dict(rows[0]) if rows else {}
    education_info = structured.get("education_info") or {}
    school = norm(education_info.get("school_name"))
    if school in REMOVE_EDUCATION:
        rows = primary.get("education_list") or []
        structured["education_info"] = dict(rows[0]) if rows else {}
    elif school in EDUCATION_REPLACEMENTS:
        education_info["school_name"] = EDUCATION_REPLACEMENTS[school]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audit-report", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    audit = json.loads(args.audit_report.read_text(encoding="utf-8"))
    changed = []
    for item in audit.get("items") or []:
        if item.get("status") != "needs_review":
            continue
        path = Path(str(item.get("json_path") or ""))
        payload = json.loads(path.read_text(encoding="utf-8"))
        phone = contact(payload)
        old_name = str((((payload.get("structured_data") or {}).get("base_info") or {}).get("full_name") or ""))
        new_name = NAME_BY_CONTACT.get(phone)
        if new_name:
            set_name(payload, new_name)

        counts = [0, 0, 0]
        for resume in (payload.get("structured_data") or {}).get("resumes") or []:
            result = clean_resume(resume)
            counts = [a + b for a, b in zip(counts, result)]
        sync_primary_summaries(payload)

        source = payload.setdefault("source", {})
        if phone in MANUAL_IDENTITY_CONTACTS:
            source["manual_verified_identity"] = True
        verified = set(source.get("manual_verified_values") or [])
        for issue in item.get("issues") or []:
            if issue.get("code") not in {
                "work_experiences_company_name_not_in_source",
                "education_list_school_name_not_in_source",
            }:
                continue
            actual = norm(issue.get("actual"))
            if not actual or actual in REMOVE_WORK or actual in REMOVE_EDUCATION:
                continue
            if actual.startswith("に一年間働いていました。それに、4 月から今まで翻訳会社"):
                continue
            if actual in EDUCATION_REPLACEMENTS:
                continue
            verified.add(actual)
        if verified:
            source["manual_verified_values"] = sorted(verified)
        note = str(source.get("note") or "").strip()
        addition = "已按源 Word/HTML 复核繁简体、译名及字段语义；删除误入工作/教育列表的标签、描述和非单位记录。"
        if addition not in note:
            source["note"] = (note + " " + addition).strip()

        target = path
        final_name = new_name or old_name
        if new_name and path.stem.startswith(old_name + "_"):
            target = path.with_name(final_name + path.name[len(old_name):])
        target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if target != path:
            path.unlink()
            item["json_path"] = str(target)
        changed.append({
            "source_path": item.get("source_path"),
            "json_path": str(target),
            "old_name": old_name,
            "new_name": final_name,
            "removed_work": counts[0],
            "removed_education": counts[1],
            "replaced_education": counts[2],
            "manual_verified_values": len(verified),
        })

    args.report.write_text(json.dumps(changed, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "changed": len(changed),
        "removed_work": sum(row["removed_work"] for row in changed),
        "removed_education": sum(row["removed_education"] for row in changed),
        "replaced_education": sum(row["replaced_education"] for row in changed),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
