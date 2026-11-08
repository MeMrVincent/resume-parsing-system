from __future__ import annotations
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1] / "common"))
import rc_config as _rc  # noqa: E402  项目统一配置（python/common/rc_config.py）
# EN: noqa: E402  project-wide configuration (python/common/rc_config.py)
# JA: noqa: E402  プロジェクト共通設定（python/common/rc_config.py）

import argparse
import copy
import json
import re
import tempfile
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = _rc.project_root()
DEFAULT_JSON_ROOT = ROOT / _rc.dirname("complete-transfered-htmls") / "pdf" / "rebuild-work" / "json-by-candidate"
DEFAULT_AUDIT = ROOT / _rc.dirname("complete-transfered-htmls") / "pdf" / "rebuild-reports" / "pdf_bidirectional_source_audit.v2.json"
DEFAULT_REPORT = ROOT / _rc.dirname("complete-transfered-htmls") / "pdf" / "rebuild-reports" / "pdf_source_completeness_repair.v2.json"
VERSION = "pdf-source-completeness-repair-v2.0.0"

WORK_FIELDS = (
    "company_name", "company_employees", "company_industry", "position", "position_type",
    "position_salary", "position_dept", "position_report_to", "position_subordinate",
    "employment_type", "annual_salary_min", "annual_salary_max", "status", "position_start",
    "position_resigned", "resigned_reason", "position_responsibilities", "position_achievements",
)
EDU_FIELDS = (
    "school_name", "school_major_name", "school_degree_type", "school_degree_rank",
    "school_education_type", "school_start_ym", "school_end_ym",
)
PROJECT_FIELDS = (
    "sequence_no", "fingerprint", "project_name", "company_or_client", "role_name", "start_ym",
    "end_ym", "description", "responsibilities", "achievements", "keywords",
)
TRAINING_FIELDS = (
    "sequence_no", "organization_name", "training_name", "start_ym", "end_ym",
    "certificate_name", "description",
)
CERT_FIELDS = ("certificate_name", "certificate_type", "certificate_time")

RANGE_RE = re.compile(
    r"(?P<sy>(?:19|20)\d{2})\s*(?:年|[./-])\s*(?P<sm>1[0-2]|0?[1-9])"
    r"(?:\s*(?:月|[./-])\s*\d{1,2}\s*日?)?\s*"
    r"(?:[-—–～〜~]|至|到)+\s*"
    r"(?:(?P<ey>(?:19|20)\d{2})\s*(?:年|[./-])\s*(?P<em>1[0-2]|0?[1-9])|(?P<present>至今|现在|目前|現今|現在|Present|Now))",
    re.I,
)
SINGLE_RE = re.compile(r"(?P<y>(?:19|20)\d{2})\s*(?:年|[./-])\s*(?P<m>1[0-2]|0?[1-9])")
ORG_RE = re.compile(
    r"公司|集团|銀行|银行|工厂|株式会社|事务所|事務所|研究所|研究院|医院|学校|大学|学院|商社|ホテル|"
    r"\b(?:Company|Corp\.?|Corporation|Ltd\.?|Inc\.?|Bank|Institute|University|College|School|Laboratory)\b",
    re.I,
)
SCHOOL_RE = re.compile(r"大学|学院|学校|中学|小学|University|College|School|Institute|Academy", re.I)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="按源文档明确日期证据补齐 PDF JSON 缺失章节记录" " / Fill in missing section records of the PDF JSON from clear date evidence in the source documents / 元の文書にある明確な日付の証拠に基づいて、PDF JSON で欠けている区分のレコードを補う")
    parser.add_argument("--json-root", type=Path, default=DEFAULT_JSON_ROOT)
    parser.add_argument("--audit", type=Path, default=DEFAULT_AUDIT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--apply", action="store_true")
    return parser.parse_args()


def text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def compact(value: Any) -> str:
    current = unicodedata.normalize("NFKC", text(value)).casefold()
    return re.sub(r"[^0-9a-z\u3400-\u9fff\u3040-\u30ff]", "", current)


def blank(fields: tuple[str, ...]) -> dict[str, str]:
    return {field: "" for field in fields}


def atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".tmp", dir=path.parent, delete=False) as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
        temporary = Path(stream.name)
    temporary.replace(path)


def canonical_name(kind: str, value: Any) -> str:
    current = text(value).strip("-—–~～|｜:：,，;；")
    if not current or len(current) > 100:
        return ""
    if re.search(r"^(?:项目职务|项目描述|责任描述|工作描述|培训机构|培训地点|职位|职务|出生日期|联系电话)\s*[：:]", current):
        return ""
    if kind == "work":
        return current if ORG_RE.search(current) else ""
    if kind == "education":
        match = re.match(r"^(.{2,70}?(?:大学|学院|学校|中学|小学|University|College|School|Institute|Academy))(?=\s|$|[（(])", current, re.I)
        return text(match.group(1)) if match else (current if SCHOOL_RE.search(current) and len(current) <= 70 else "")
    if kind == "project" and re.search(r"语言证书|专业技能|自我评价|产品目录$", current):
        return ""
    if kind == "certificate" and not re.search(r"证书|资格|执照|CET|TEM|TOEIC|TOEFL|IELTS|JLPT|N[1-5]|普通话|计算机|口译|笔译", current, re.I):
        return ""
    return current


def source_lines(raw_text: str) -> list[str]:
    return [text(line) for line in unicodedata.normalize("NFKC", raw_text or "").splitlines() if text(line)]


def clipped(value: str, limit: int = 500) -> str:
    current = text(value)
    return current if len(current) <= limit else current[: limit - 1].rstrip() + "…"


def date_only_line(value: str) -> bool:
    current = text(value)
    if len(current) > 80 or not RANGE_RE.search(current):
        return False
    remainder = RANGE_RE.sub("", current)
    remainder = re.sub(r"[\s|｜:：,，;；()（）\[\]【】]+", "", remainder)
    return len(remainder) <= 12


def nearby_range(line: str, name: str) -> re.Match[str] | None:
    """Return a range only when it is textually bound to the entity name."""
    normalized_name = text(name)
    name_pos = line.casefold().find(normalized_name.casefold())
    if name_pos < 0:
        compact_name = compact(name)
        compact_line = compact(line)
        name_pos = compact_line.find(compact_name)
        if name_pos < 0:
            return None
        # Compact positions cannot be mapped back exactly; reject very long collapsed lines.
        if len(line) > 500:
            return None
    matches = list(RANGE_RE.finditer(line))
    if not matches:
        return None
    name_end = name_pos + len(normalized_name)
    match = min(matches, key=lambda item: min(abs(item.start() - name_end), abs(name_pos - item.end())))
    distance = min(abs(match.start() - name_end), abs(name_pos - match.end()))
    return match if distance <= 160 else None


def find_evidence(lines: list[str], name: str) -> tuple[str, str, str]:
    needle = compact(name)
    indexes = [index for index, line in enumerate(lines) if needle and (needle in compact(line) or compact(line) in needle)]
    for index in indexes:
        match = nearby_range(lines[index], name)
        if not match and index > 0 and date_only_line(lines[index - 1]):
            match = RANGE_RE.search(lines[index - 1])
        if not match and index + 1 < len(lines) and date_only_line(lines[index + 1]):
            match = RANGE_RE.search(lines[index + 1])
        if match:
            start = f"{int(match.group('sy')):04d}年{int(match.group('sm')):02d}月01日"
            end = "" if match.group("present") else f"{int(match.group('ey')):04d}年{int(match.group('em')):02d}月01日"
            window = lines[max(0, index - 1):min(len(lines), index + 2)]
            return start, end, clipped(" | ".join(window))
    return "", "", ""


def find_certificate_date(lines: list[str], name: str) -> tuple[str, str]:
    needle = compact(name)
    for index, line in enumerate(lines):
        if needle and (needle in compact(line) or compact(line) in needle):
            candidates = [line]
            if index > 0 and len(lines[index - 1]) <= 80:
                candidates.append(lines[index - 1])
            if index + 1 < len(lines) and len(lines[index + 1]) <= 80:
                candidates.append(lines[index + 1])
            for candidate in candidates:
                match = SINGLE_RE.search(candidate)
                if match:
                    return f"{int(match.group('y')):04d}年{int(match.group('m')):02d}月01日", clipped(" | ".join(lines[max(0, index - 1):index + 2]))
    return "", ""


def main() -> int:
    cfg = parse_args()
    audit = json.loads(cfg.audit.read_text(encoding="utf-8-sig"))
    requested: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    for record in audit.get("records") or []:
        filename = Path(text(record.get("json"))).name
        for issue in record.get("issues") or []:
            code = text(issue.get("code"))
            if not code.endswith(".missing") or "resumes[0]" not in text(issue.get("path")):
                continue
            collection = code.split(".", 1)[0]
            for value in issue.get("expected_from_source") or []:
                requested[filename][collection].add(text(value))

    counters: Counter[str] = Counter()
    changes: list[dict[str, Any]] = []
    for filename, collections in sorted(requested.items()):
        path = cfg.json_root / filename
        if not path.is_file():
            continue
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
        resumes = ((payload.get("structured_data") or {}).get("resumes") or [])
        if not resumes or not isinstance(resumes[0], dict):
            continue
        primary = resumes[0]
        lines = source_lines(str(payload.get("raw_text") or ""))
        file_changes = []
        specs = {
            "work_experiences": ("work", WORK_FIELDS, "company_name", "position_start", "position_resigned"),
            "education_list": ("education", EDU_FIELDS, "school_name", "school_start_ym", "school_end_ym"),
            "project_list": ("project", PROJECT_FIELDS, "project_name", "start_ym", "end_ym"),
            "training_list": ("training", TRAINING_FIELDS, "training_name", "start_ym", "end_ym"),
        }
        for collection, names in collections.items():
            if collection == "certificate_list":
                existing = {compact(row.get("certificate_name")) for row in primary.get(collection) or [] if isinstance(row, dict)}
                for raw_name in sorted(names):
                    name = canonical_name("certificate", raw_name)
                    if not name or any(compact(name) in value or value in compact(name) for value in existing if value):
                        continue
                    date, evidence = find_certificate_date(lines, name)
                    row = blank(CERT_FIELDS)
                    row.update(certificate_name=name, certificate_time=date)
                    primary.setdefault(collection, []).append(row)
                    existing.add(compact(name))
                    counters["add_certificate"] += 1
                    file_changes.append({"collection": collection, "name": name, "start": date, "end": "", "evidence": evidence})
                continue
            if collection not in specs:
                continue
            kind, fields, key_field, start_field, end_field = specs[collection]
            existing = {compact(row.get(key_field)) for row in primary.get(collection) or [] if isinstance(row, dict)}
            for raw_name in sorted(names):
                name = canonical_name(kind, raw_name)
                if not name or any(compact(name) in value or value in compact(name) for value in existing if value):
                    continue
                start, end, evidence = find_evidence(lines, name)
                if not start:
                    counters[f"skip_{kind}_without_date"] += 1
                    continue
                row = blank(fields)
                row[key_field], row[start_field], row[end_field] = name, start, end
                if collection == "work_experiences":
                    row["status"] = "离职" if end else "在职"
                if collection == "project_list":
                    row["sequence_no"] = str(len(primary.get(collection) or []) + 1)
                if collection == "training_list" and not row.get("organization_name") and ORG_RE.search(name):
                    row["organization_name"] = name
                primary.setdefault(collection, []).append(row)
                existing.add(compact(name))
                counters[f"add_{kind}"] += 1
                file_changes.append({"collection": collection, "name": name, "start": start, "end": end, "evidence": evidence})
        if file_changes:
            changes.append({"filename": filename, "changes": file_changes})
            if cfg.apply:
                atomic_json(path, payload)

    report = {
        "version": VERSION,
        "generated_at": datetime.now().astimezone().isoformat(),
        "mode": "apply" if cfg.apply else "dry_run",
        "json_root": str(cfg.json_root.resolve()),
        "changed_file_count": len(changes),
        "repair_counts": dict(counters.most_common()),
        "records": changes,
    }
    atomic_json(cfg.report, report)
    print(json.dumps({key: value for key, value in report.items() if key != "records"}, ensure_ascii=False, indent=2))
    print(f"report={cfg.report.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
