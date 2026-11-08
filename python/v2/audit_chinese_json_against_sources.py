"""按字段归属，将中文正式 JSON 与原始 Word 文本证据逐项比较。

EN: Compare the formal Chinese JSON with the original Word text evidence field by field, according to field ownership.

JA: フィールドの帰属に従い、中国語の正式 JSON と元の Word テキストの証拠を項目ごとに比較する。
"""

from __future__ import annotations
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1] / "common"))
import rc_config as _rc  # noqa: E402  项目统一配置（python/common/rc_config.py）
# EN: noqa: E402  project-wide configuration (python/common/rc_config.py)
# JA: noqa: E402  プロジェクト共通設定（python/common/rc_config.py）

import json
import argparse
import os
import re
import subprocess
import zipfile
from collections import Counter
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET


ROOT = _rc.project_root()
JSON_DIR = ROOT / _rc.dirname("complete-transfered-jsons") / "docs" / "中文"
REPORT = ROOT / _rc.dirname("complete-transfered-jsons") / "docs" / "chinese_field_source_comparison.json"
TZ_JST = timezone(timedelta(hours=9))
ANTIWORD = Path(r"C:\Program Files\Git\mingw64\bin\antiword.exe")
W_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

SECTION_ALIASES = {
    "expected": ("求职意向", "求职目标", "职业目标"),
    "work": ("工作经历", "工作经验", "工作履历", "职业经历"),
    "education": ("教育经历", "教育背景", "学历教育"),
    "certificate": ("证书", "资格证书", "所获证书"),
    "training": ("培训经历", "培训经验"),
    "project": ("项目经验", "项目经历"),
    "language": ("语言能力", "外语能力"),
    "skills": ("专业技能", "技能特长"),
    "other": ("在校情况", "校内荣誉", "在校活动", "社会实践", "校园经历", "校内职务", "获奖情况", "荣誉奖励", "自我评价", "个人评价"),
}
ALL_HEADINGS = {alias for aliases in SECTION_ALIASES.values() for alias in aliases}
DATE_RE = re.compile(r"(?:19|20)\d{2}\s*(?:年|[./-])\s*\d{1,2}")
MOBILE_RE = re.compile(r"(?<!\d)(1[3-9]\d{9})(?!\d)")
EMAIL_RE = re.compile(r"[A-Z0-9][A-Z0-9.!#$%&'*+/=?^_`{|}~-]*@[A-Z0-9.-]+\.[A-Z]{2,}", re.I)


class TextHTMLParser(HTMLParser):
    BLOCKS = {"p", "div", "td", "tr", "li", "h1", "h2", "h3", "h4", "br", "section", "table"}

    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.casefold() in self.BLOCKS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() in self.BLOCKS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


import unicodedata

def clean_lines(text: str) -> list[str]:
    text = unicodedata.normalize("NFKC", text or "")
    text = re.sub(r"(山东|交通|学院|大阪|产业|大学|目前|工作)(\1)", r"\1", text)
    return [re.sub(r"\s+", " ", line).strip() for line in text.replace("\r", "\n").split("\n") if re.sub(r"\s+", " ", line).strip()]


def read_docx_lines(path: Path) -> list[str]:
    with zipfile.ZipFile(path) as archive:
        root = ET.fromstring(archive.read("word/document.xml"))
    lines: list[str] = []
    for paragraph in root.iter(W_NS + "p"):
        text = "".join(node.text or "" for node in paragraph.iter(W_NS + "t"))
        if text.strip():
            lines.append(text)
    return clean_lines("\n".join(lines))


def decode_html_bytes(raw: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "gb18030", "utf-16"):
        try:
            text = raw.decode(encoding)
            if "\ufffd" not in text[:1000]:
                return text
        except UnicodeError:
            continue
    return raw.decode("latin1", errors="replace")


def read_doc_lines(path: Path) -> list[str]:
    raw = path.read_bytes()
    head = raw[:16384].lower()
    utf16_html = False
    if head.startswith((b"\xff\xfe", b"\xfe\xff")):
        try:
            decoded_head = raw[:32768].decode("utf-16", errors="ignore").casefold()
            utf16_html = "<html" in decoded_head or "<table" in decoded_head
        except Exception:
            utf16_html = False
    if b"<html" in head or b"<table" in head or utf16_html:
        parser = TextHTMLParser()
        parser.feed(decode_html_bytes(raw))
        return clean_lines("".join(parser.parts))
    if ANTIWORD.is_file():
        process = subprocess.run([str(ANTIWORD), "-m", "UTF-8.txt", str(path)], capture_output=True, timeout=30)
        if process.stdout:
            return clean_lines(process.stdout.decode("utf-8", errors="replace"))
    return []


def read_source_lines(path: Path) -> list[str]:
    suffix = path.suffix.casefold()
    if suffix in {".html", ".htm"}:
        parser = TextHTMLParser()
        parser.feed(decode_html_bytes(path.read_bytes()))
        return clean_lines("".join(parser.parts))
    if suffix in {".docx", ".docm", ".dotx"}:
        return read_docx_lines(path)
    if suffix in {".doc", ".wps"}:
        return read_doc_lines(path)
    return []


def normalized(value: Any) -> str:
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", str(value or "").casefold())


def split_sections(lines: list[str]) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {key: [] for key in SECTION_ALIASES}
    current = ""
    for line in lines:
        compact_line = re.sub(r"\s+", "", line).strip("：:")
        matched = ""
        for key, aliases in SECTION_ALIASES.items():
            if any(compact_line == re.sub(r"\s+", "", alias) for alias in aliases):
                matched = key
                break
        if matched:
            current = matched
            continue
        if current:
            sections[current].append(line)
    return sections


def label_value(lines: list[str], labels: tuple[str, ...]) -> str:
    for index, line in enumerate(lines):
        compact_line = re.sub(r"\s+", "", line)
        for label in labels:
            compact_label = re.sub(r"\s+", "", label)
            match = re.match(r"^" + re.escape(compact_label) + r"\s*[：:]?\s*(.*)$", compact_line)
            if match and match.group(1).strip():
                return match.group(1).strip()
            if match:
                for following in lines[index + 1:index + 4]:
                    if following.strip("：:") not in ALL_HEADINGS and not re.search(r"^[^：:]{1,15}[：:]$", following):
                        return following.strip()
    return ""


def section_contains(section: list[str], value: Any) -> bool:
    needle = normalized(value)
    if not needle:
        return True
    haystack = normalized("\n".join(section))
    return needle in haystack or (len(needle) >= 8 and needle[:8] in haystack)


def substantive_section(section: list[str]) -> bool:
    text = "\n".join(section)
    return len(normalized(text)) >= 12 and (bool(DATE_RE.search(text)) or len(section) >= 2)


DATE_RANGE_PREFIX_RE = re.compile(
    r"^(?:(?:19|20)\d{2}\s*(?:年|[./-])\s*\d{1,2}(?:\s*(?:月|[./-])\s*\d{1,2}日?)?)\s*"
    r"(?:--|[-—–~～至到]{1,4})\s*(?:(?:19|20)\d{2}\s*(?:年|[./-])\s*\d{1,2}(?:\s*(?:月|[./-])\s*\d{1,2}日?)?|至今|现在|目前)\s*(.*)$",
    re.I,
)
SINGLE_DATE_PREFIX_RE = re.compile(r"^(?:19|20)\d{2}\s*(?:年|[./-])\s*\d{1,2}(?:\s*(?:月|[./-])\s*\d{1,2}日?)?\s*(.*)$")
NON_BUSINESS_TOKENS = ("学生会", "社团", "协会", "联谊", "导师", "指导老师", "课代表", "课程代表", "班委", "校内职务", "主席", "志愿者", "大学祭", "实习理事")
ATTRIBUTE_LINES = ("工作描述", "项目描述", "培训描述", "专业描述", "所属公司", "培训机构", "培训地点", "责任描述", "职务描述")
ORGANIZATION_MARKS = ("公司", "集团", "银行", "工厂", "株式会社", "事务所", "研究所", "研究院", "医院", "学校", "大学", "学院", "商社", "ホテル", "有限", "股份")
WORK_FIELD_LABELS = ("职位", "职务", "岗位", "部门", "行业", "公司性质", "公司规模", "工作描述", "职责")


def extract_named_records(section: list[str], kind: str) -> list[str]:
    """从日期行及紧随行提取该字段在原文中的明确名称值。

    EN: Extract the explicit name value of this field in the source from the date line and the line right after it.

    JA: 日付行とその直後の行から、原文におけるこのフィールドの明示的な名称値を抽出する。
    """
    results: list[str] = []
    for index, line in enumerate(section):
        match = (SINGLE_DATE_PREFIX_RE if kind == "certificate" else DATE_RANGE_PREFIX_RE).match(line)
        if not match:
            continue
        candidate = match.group(1).strip(" :：|｜-，,")
        if kind == "work" and candidate and not any(mark in candidate for mark in ORGANIZATION_MARKS):
            candidate = ""
        if kind == "work" and candidate:
            candidate = candidate.strip()
            if (
                len(candidate) > 80
                or candidate in {"民营公司", "外资公司", "合资公司", "银行", "公司"}
                or candidate.startswith(("负责", "参与", "协助", "组织", "管理", "整理", "汇报对象", "搜索同事", "在该公司", "该公司为", "主要负责", "【负责品牌】"))
                or not re.search(r"(?:有限责任公司|股份有限公司|有限公司|集团|银行|工厂|制造厂|株式会社|事务所|研究所|研究院|医院|学校|大学|学院|商社|公司)$", candidate)
            ):
                candidate = ""
        if kind in {"work", "project"} and candidate and re.search(r"大学|学院|学校", candidate):
            # 无清晰区段边界的推荐报告常把教育日期行串入工作/项目区；
            # 学校不能仅凭日期行被要求补成公司或项目。
            # EN: Recommendation reports without clear section boundaries often let education date lines leak into the work/project sections;
            #     a school must not be turned into a company or project just because of a date line.
            # JA: 区切りがはっきりしない推薦レポートでは、学歴の日付行が職歴・プロジェクト欄に紛れ込みやすい。
            #     日付行があるというだけで学校を会社やプロジェクトとして補ってはならない。
            candidate = ""
        if not candidate:
            fallback = ""
            for following in section[index + 1:index + 7]:
                following = following.strip()
                if not following or DATE_RANGE_PREFIX_RE.match(following) or SINGLE_DATE_PREFIX_RE.match(following):
                    continue
                if any(following.startswith(prefix) for prefix in ATTRIBUTE_LINES):
                    continue
                if kind == "work":
                    labelled = re.match(r"^(?:公司|单位|任职单位|工作单位)\s*[：:]\s*(.+)$", following)
                    if labelled:
                        candidate = labelled.group(1).strip(); break
                    if any(following.startswith(label) for label in WORK_FIELD_LABELS):
                        continue
                    if any(mark in following for mark in ORGANIZATION_MARKS):
                        candidate = following; break
                    if not fallback and len(following) <= 50:
                        fallback = following
                    continue
                candidate = following
                break
            # 没有公司/机构标志时，fallback 常常只是部门或职位，不能冒充公司名。
            # EN: Without a company/organisation marker, the fallback is often just a department or job title and must not pose as the company name.
            # JA: 会社・機関を示す目印がない場合、fallback は部署名や職位にすぎないことが多く、会社名として扱ってはならない。
            if not candidate and kind == "work":
                candidate = ""
        candidate = re.sub(r"\s*[（(]\s*\d+\s*(?:年|个?月).*?[）)]\s*$", "", candidate).strip()
        if kind == "work" and "|" in candidate:
            candidate = candidate.split("|", 1)[0].strip()
        if kind == "work" and candidate and not any(mark in candidate for mark in ORGANIZATION_MARKS):
            candidate = ""
        if kind == "work" and candidate:
            candidate = candidate.strip(" ：:，,。；;")
            if (
                len(candidate) > 60
                or candidate in {"民营公司", "外资公司", "合资公司", "银行", "公司"}
                or any(token in candidate for token in ("项目描述", "项目职责", "项目业绩", "工作描述", "负责", "参与", "协助", "汇报对象"))
                or candidate.startswith(("搜索同事", "【任职公司】", "销售以", "该公司", "在该公司"))
                or "为主的" in candidate
                or not re.search(r"(?:有限责任公司|股份有限公司|有限公司|集团|银行|工厂|制造厂|株式会社|事务所|研究所|研究院|医院|学校|大学|学院|商社|公司)$", candidate)
            ):
                candidate = ""
        if kind in {"work", "project"} and candidate and re.search(r"大学|学院|学校", candidate):
            candidate = ""
        if kind == "project" and candidate and len(candidate) < 2:
            candidate = ""
        if kind == "education" and candidate and not any(mark in candidate for mark in ("学校", "大学", "学院", "中学", "小学")):
            candidate = ""
        if kind == "certificate" and candidate:
            certificate_marks = (
                "证书", "资格", "执照", "雅思", "托福", "托业", "口译", "笔译",
                "英语", "日语", "法语", "德语", "韩语", "普通话", "计算机",
                "CET", "TEM", "TOEIC", "TOEFL", "IELTS", "JLPT", "N1", "N2",
            )
            if (
                len(candidate) > 50
                or bool(re.match(r"^\d{1,2}[./-]\d{1,2}\s+", candidate))
                or any(token in candidate for token in ("比赛", "竞赛", "奖学金", "组织者", "演唱者", "获院", "曾获"))
                or not any(mark.casefold() in candidate.casefold() for mark in certificate_marks)
            ):
                candidate = ""
        if kind == "training" and candidate:
            if (
                any(token in candidate for token in ("证书", "CCNA", "CIPS", "BJT", "能力考试", "语言", "奖学金", "公司", "有限公司"))
                or candidate in {"英语", "日语", "商务英语"}
            ):
                candidate = ""
        if candidate and not any(token in candidate for token in NON_BUSINESS_TOKENS):
            results.append(candidate)
    return list(dict.fromkeys(results))


def evidence_excerpt(section: list[str], limit: int = 8) -> str:
    return "\n".join(section[:limit])[:1200]


def add(issues: list[dict[str, Any]], code: str, path: str, actual: Any, expected: Any, evidence: str) -> None:
    issues.append({"code": code, "path": path, "actual_json": actual, "expected_from_source": expected, "source_evidence": evidence})


def audit(payload: dict[str, Any], lines: list[str]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    sections = split_sections(lines)
    structured = payload.get("structured_data") or {}
    base = structured.get("base_info") or {}
    whole = "\n".join(lines)

    phones = list(dict.fromkeys(MOBILE_RE.findall(whole)))
    emails: list[str] = []
    for raw_email in EMAIL_RE.findall(whole):
        if "|" in raw_email:
            raw_email = raw_email.split("|", 1)[1]
        raw_email = raw_email.strip()
        if "@" not in raw_email: continue
        local, domain = raw_email.split("@", 1)
        # 只有当手机号后面粘连了真正的字母前缀时才剥离 (例如 13800000000zhangsan@163.com)
        # EN: Strip only when a real letter prefix is stuck to the end of the phone number (e.g. 13800000000zhangsan@163.com)
        # JA: 電話番号の後ろに本物の英字プレフィックスがくっついている場合のみ除去する（例：13800000000zhangsan@163.com）
        glued = re.match(r"^1[3-9]\d{9}([a-zA-Z._\-]+.*)$", local)
        cleaned = (glued.group(1) if glued else local) + "@" + domain
        if "*" not in cleaned and cleaned.casefold() not in {value.casefold() for value in emails}:
            emails.append(cleaned)
    actual_phone = re.sub(r"\D", "", str(base.get("phone") or ""))
    actual_email = str(base.get("email") or "").strip()
    # 修复“手机号+邮箱”粘连证据：138... + user1@example.com。
    # EN: Repair evidence where "phone + e-mail" are stuck together: 138... + user1@example.com.
    # JA: 「電話番号 + メール」がくっついた証拠を修復する：138... + user1@example.com。
    if actual_email and "@" in actual_email:
        local, domain = actual_email.split("@", 1)
        glued = re.match(r"^(1[3-9]\d{9})(.{4,})$", local)
        if glued and (not actual_phone or actual_phone == glued.group(1)):
            add(issues, "base_info.email", "structured_data.base_info.email", actual_email, glued.group(2) + "@" + domain, actual_email)
            if not actual_phone:
                add(issues, "base_info.phone", "structured_data.base_info.phone", actual_phone, glued.group(1), actual_email)
    if actual_phone and phones and actual_phone not in phones:
        add(issues, "base_info.phone", "structured_data.base_info.phone", actual_phone, phones[0], " / ".join(phones[:5]))
    if actual_email and emails and actual_email.casefold() not in {email.casefold() for email in emails}:
        add(issues, "base_info.email", "structured_data.base_info.email", actual_email, emails[0], " / ".join(emails[:5]))

    expected_contracts = {
        "expected_city": ("期望工作地区", "期望地区", "地点"),
        "expected_position": ("期望从事职业", "职能/职位", "期望职位"),
        "expected_salary": ("期望月薪", "期望薪资", "期望工资"),
        "expected_industry": ("期望从事行业", "行业"),
        "expected_employment_type": ("期望工作性质", "工作类型"),
        "expected_start_date": ("到岗时间",),
    }
    expected = structured.get("expected_info") or {}
    for field, labels in expected_contracts.items():
        source_value = label_value(sections["expected"] or lines, labels)
        actual_value = str(expected.get(field) or "").strip()
        start_equivalent = False
        if field == "expected_start_date" and source_value:
            start_equivalent = normalized(actual_value).removesuffix("到岗") == normalized(source_value).removesuffix("到岗")
        if source_value and not start_equivalent and not section_contains([source_value], actual_value):
            add(issues, f"expected_info.{field}", f"structured_data.expected_info.{field}", actual_value, source_value, source_value)

    resumes = structured.get("resumes") or []
    for resume_index, resume in enumerate(resumes):
        list_contracts = {
            "work_experiences": ("work", "company_name", "work"),
            "education_list": ("education", "school_name", "education"),
            "certificate_list": ("certificate", "certificate_name", "certificate"),
            "training_list": ("training", "training_name", "training"),
            "project_list": ("project", "project_name", "project"),
        }
        for list_name, (section_name, key_field, kind) in list_contracts.items():
            section = sections[section_name]
            items = resume.get(list_name) or []
            expected_names = extract_named_records(section, kind)
            actual_names = [str((item or {}).get(key_field) or "").strip() for item in items if str((item or {}).get(key_field) or "").strip()]
            if list_name == "certificate_list":
                actual_names.extend(
                    str((item or {}).get("language_level") or "").strip()
                    for item in resume.get("language_list") or []
                    if str((item or {}).get("language_level") or "").strip()
                )
            actual_normalized = {normalized(name) for name in actual_names}
            missing_names = [name for name in expected_names if normalized(name) not in actual_normalized and not any(normalized(name) in normalized(actual) or normalized(actual) in normalized(name) for actual in actual_names if normalized(actual))]
            if missing_names:
                add(issues, f"{list_name}.missing", f"structured_data.resumes[{resume_index}].{list_name}", actual_names, missing_names, evidence_excerpt(section))
            for item_index, item in enumerate(items):
                actual_value = str((item or {}).get(key_field) or "").strip()
                if actual_value and section and not section_contains(section, actual_value):
                    add(issues, f"{list_name}.{key_field}", f"structured_data.resumes[{resume_index}].{list_name}[{item_index}].{key_field}", actual_value, expected_names, evidence_excerpt(section))

    unique: dict[tuple[str, str, str], dict[str, Any]] = {}
    for issue in issues:
        unique[(issue["code"], issue["path"], str(issue["actual_json"]))] = issue
    return list(unique.values())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json-dir", type=Path, default=JSON_DIR)
    parser.add_argument("--report", type=Path, default=REPORT)
    parser.add_argument("--manifest", type=Path, help="只审计增量清单中已有 staging_json 的源文件" " / Audit only the source files that already have staging_json in the incremental list / 増分一覧で staging_json が既にある元ファイルだけを監査する")
    args = parser.parse_args()
    cache: dict[str, list[str]] = {}
    records: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    unreadable = 0
    allowed_sources: set[str] | None = None
    if args.manifest:
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
        allowed_sources = {
            os.path.normcase(os.path.normpath(str(item.get("source_path") or "")))
            for item in manifest.get("items") or []
            if item.get("staging_json")
        }
    files = []
    for path in args.json_dir.glob("*.json"):
        if path.name.startswith("_"):
            continue
        if allowed_sources is None:
            files.append(path)
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        source = str((payload.get("source") or {}).get("original_path") or "")
        if os.path.normcase(os.path.normpath(source)) in allowed_sources:
            files.append(path)
    for sequence, json_path in enumerate(sorted(files), 1):
        try:
            payload = json.loads(json_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        source = str((payload.get("source") or {}).get("original_path") or "")
        if source not in cache:
            source_path = Path(source)
            try:
                cache[source] = read_source_lines(source_path) if source_path.is_file() else []
            except Exception:
                cache[source] = []
            if not cache[source]:
                html_path = Path(str((payload.get("extraction") or {}).get("html_path") or ""))
                try:
                    cache[source] = read_source_lines(html_path) if html_path.is_file() else []
                except Exception:
                    cache[source] = []
        lines = cache[source]
        if not lines:
            unreadable += 1
            continue
        issues = audit(payload, lines)
        if issues:
            for issue in issues:
                counts[issue["code"]] += 1
            records.append({"json": str(json_path), "source": source, "issues": issues})
        if sequence % 500 == 0:
            print(f"{sequence}/{len(files)} affected={len(records)} unreadable={unreadable}", flush=True)
    report = {
        "audited_at": datetime.now(TZ_JST).isoformat(), "total_json": len(files),
        "sources_read": len(cache) - unreadable, "unreadable_sources": unreadable,
        "affected_files": len(records), "issue_counts": dict(sorted(counts.items())), "records": records,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("total_json", "sources_read", "unreadable_sources", "affected_files", "issue_counts")}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
