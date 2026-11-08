"""从中文解析暂存区筛出可保守晋级的强简历候选。

EN: Select strong résumé candidates that can be conservatively promoted from the Chinese parse staging area.

JA: 中国語の解析の一時保存領域から、保守的に昇格できる確度の高い履歴書の候補を選ぶ。
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
from collections import Counter
from pathlib import Path


BAD_NAME = {"未知", "项目", "要采集", "sxd", "简历", "姓名", "应聘者", "候选人"}
BAD_NAME_PATTERN = re.compile(r"市場|交流|面接|情報|参考|担当|営業|職務|経歴|履歴|人事|総務|財務|财务|技術|技术|募集|会社|公司|推荐|推薦")
NON_RESUME_PATH = re.compile(
    r"职位\s*JD|JD模板|职位简介|招聘职位|招聘信息|公司介绍|合同|协议|通知|体检|"
    r"福利待遇|入职所需|空白模[板版]|培训提纲|测试题|工作总结|开票资料|集团公司一览",
    re.I,
)


def meaningful(rows: object, keys: tuple[str, ...]) -> int:
    if not isinstance(rows, list):
        return 0
    return sum(
        isinstance(row, dict) and any(str(row.get(key) or "").strip() for key in keys)
        for row in rows
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--staging-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    counts: Counter[str] = Counter()
    items = []
    for path in sorted(args.staging_dir.glob("*.json")):
        if path.name.startswith("_"):
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            counts["invalid_json"] += 1
            items.append({"json": str(path), "status": "invalid_json", "reason": str(exc)})
            continue
        structured = payload.get("structured_data") or {}
        base = structured.get("base_info") or {}
        name = str(base.get("full_name") or "").strip()
        source = str((payload.get("source") or {}).get("original_path") or "")
        raw = str(payload.get("raw_text") or "")
        resumes = structured.get("resumes") or []
        resume = resumes[0] if resumes and isinstance(resumes[0], dict) else {}
        work = meaningful(resume.get("work_experiences"), ("company_name", "position"))
        education = meaningful(resume.get("education_list"), ("school_name", "school_major_name"))
        project = meaningful(resume.get("project_list"), ("project_name", "description"))
        name_valid = bool(re.fullmatch(r"[\u3400-\u9fff·]{2,6}", name)) and name not in BAD_NAME and not BAD_NAME_PATTERN.search(name)
        name_evidence = name and (name in raw or name in Path(source).stem)
        experience_evidence = work > 0 or education > 0 or (project > 0 and education > 0)
        path_is_non_resume = bool(NON_RESUME_PATH.search(source))
        status = "staged"
        if not name_valid:
            status = "invalid_name"
        elif not name_evidence:
            status = "name_not_in_source"
        elif not experience_evidence:
            status = "insufficient_resume_structure"
        elif path_is_non_resume and work == 0 and education == 0:
            status = "likely_non_resume"
        item = {"json": str(path), "source_path": source, "name": name, "work": work, "education": education, "project": project, "status": status}
        if status == "staged":
            target = args.output_dir / path.name
            sequence = 2
            while target.exists():
                target = args.output_dir / f"{path.stem}_{sequence}{path.suffix}"
                sequence += 1
            shutil.copy2(path, target)
            item["output_json"] = str(target)
        counts[status] += 1
        items.append(item)
    report = {"summary": dict(counts), "items": items}
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
