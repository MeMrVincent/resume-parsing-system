from __future__ import annotations
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1] / "common"))
import rc_config as _rc  # noqa: E402  项目统一配置（python/common/rc_config.py）
# EN: noqa: E402  project-wide configuration (python/common/rc_config.py)
# JA: noqa: E402  プロジェクト共通設定（python/common/rc_config.py）

import argparse
import copy
import hashlib
import importlib.util
import json
import re
import sys
import tempfile
import unicodedata
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

PROJECT_ROOT = _rc.project_root()
PYTHON_ROOT = _rc.PYTHON_DIR / "v2"
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

PDF_ROOT = PROJECT_ROOT / _rc.dirname("complete-transfered-htmls") / "pdf"
DEFAULT_MAP = PDF_ROOT / "rebuild-work" / "pdf_rebuild_map.v2.json"
DEFAULT_PILOT = PDF_ROOT / "rebuild-reports" / "pdf_pilot_30.v2.json"
HTML_ROOT = PDF_ROOT / "rebuild-work" / "html"
JSON_ROOT = PDF_ROOT / "rebuild-work" / "json-by-source"
DEFAULT_REPORT = PDF_ROOT / "rebuild-reports" / "pdf_pilot_extract.v2.json"
VERSION = "pdf-rebuild-extract-v2.0.1"
NAME_NOISE_RE = re.compile(
    r"履歴書|職務経歴書|日本语|日本語|携帯|電話|邮箱|メール|基本情報|个人简历|求职意向|resume|curriculum|vitae",
    re.I,
)
EMAIL_RE = re.compile(r"[A-Z0-9._%+*\-]+@[A-Z0-9.\-*]+\.[A-Z]{2,}", re.I)
SOURCE_EMAIL_RE = re.compile(
    r"[A-Z0-9._%+\-]+@[A-Z0-9.\-]+?\.(?:com|cn|net|org|edu|gov|jp|co\.jp|de|uk|fr|info|biz|io)",
    re.I,
)
NUMBERED_KEY_RE = re.compile(r"^(?P<label>[A-Za-z][A-Za-z ]*?)\s+(?P<index>\d+)\s*:\s*(?P<value>.*)$")


def load_module(filename: str, name: str):
    spec = importlib.util.spec_from_file_location(name, PYTHON_ROOT / filename)
    if spec is None or spec.loader is None:
        raise ImportError(f"无法加载 {filename}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


DOM = load_module("c_resume_html_dom_common.v2.py", "_pdf_rebuild_dom_v2")
PARSER = load_module("c_resume_html_to_json_common.v2.py", "_pdf_rebuild_parser_v2")
XLS_RULES = None


def _semantic_resume_roots(soup):
    roots = list(soup.find_all("article", attrs={"data-role": "resume"}))
    if roots:
        return roots
    main = soup.find("main") or soup.find("body") or soup
    return [main]


def _dom_field_values(main) -> dict[str, list[str]]:
    values: dict[str, list[str]] = {}
    for node in main.find_all(attrs={"data-field": True}):
        field = str(node.get("data-field") or "").strip()
        value = node.get_text(" ", strip=True)
        if field and value and value not in values.setdefault(field, []):
            values[field].append(value)
    return values


def _filename_name_hint(path: Path) -> str:
    stem = path.stem
    stem = re.sub(r"^(?:\d+[_.\-\s]+)+", "", stem)
    stem = re.sub(r"简历|履历书|履歴書|職務経歴書|resume|curriculum vitae|cv", " ", stem, flags=re.I)
    candidates = re.findall(r"[\u3400-\u9fff]{2,4}", stem)
    return candidates[0] if candidates else ""


def _normalize_name(value: str) -> str:
    value = re.sub(r"^(?:姓名|氏名|Name)[:：\s]*", "", str(value or ""), flags=re.I)
    return re.sub(r"[\s_\-:：()（）]+$", "", value).strip()


# The shared v2 parser is used by wrapper entry points that historically
# injected these helpers.  The v2 adapter supplies them explicitly without
# modifying the existing Word implementation.
PARSER.semantic_resume_roots = _semantic_resume_roots
PARSER.dom_field_values = _dom_field_values
PARSER.filename_name_hint = _filename_name_hint
PARSER.normalize_name = _normalize_name


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="使用 iLovePDF Word 主输入生成 PDF v2 逐源暂存 JSON" " / Generate PDF v2 per-source staging JSON with iLovePDF Word as the main input / iLovePDF の Word を主な入力として、PDF v2 の元ファイルごとのステージング JSON を生成する")
    parser.add_argument("--map", type=Path, default=DEFAULT_MAP)
    parser.add_argument("--pilot", type=Path, default=DEFAULT_PILOT)
    parser.add_argument("--scope", choices=("pilot", "all"), default="pilot")
    parser.add_argument(
        "--filenames",
        nargs="+",
        default=[],
        help="只处理指定 PDF 文件名；设置后优先于 --scope" " / Process only the given PDF file names; takes precedence over --scope when set / 指定した PDF ファイル名だけを処理する（指定すると --scope より優先）",
    )
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--html-root", type=Path, default=HTML_ROOT)
    parser.add_argument("--json-root", type=Path, default=JSON_ROOT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument(
        "--merge-into-report",
        type=Path,
        default=None,
        help="将本次指定文件结果回写到既有全量报告，保持协作问题表同步" " / Write the results of the given files back to the existing full report, keeping the collaboration issue table in sync / 今回指定したファイルの結果を既存の全件レポートに書き戻し、共同確認用の問題表を同期した状態に保つ",
    )
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--disable-xls-grid", action="store_true")
    return parser.parse_args()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".tmp", dir=path.parent, delete=False) as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
        temporary = Path(stream.name)
    temporary.replace(path)


def safe_stem(value: str) -> str:
    result = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", Path(value).stem).strip(" ._")
    return result[:100] or "unnamed"


def docx_layout_profile(path: Path, record: dict[str, Any]) -> dict[str, Any]:
    profile = {"route": "word_paragraph", "table_count": 0, "cell_count": 0, "table_text_ratio": 0.0}
    try:
        with zipfile.ZipFile(path) as archive:
            root = ElementTree.fromstring(archive.read("word/document.xml"))
    except Exception:
        return profile
    all_chars = 0
    table_chars = 0
    table_count = 0
    cell_count = 0
    text_parts: list[str] = []
    for node in root.iter():
        local = node.tag.rsplit("}", 1)[-1]
        if local == "tbl":
            table_count += 1
            for child in node.iter():
                child_local = child.tag.rsplit("}", 1)[-1]
                if child_local == "tc":
                    cell_count += 1
                elif child_local == "t" and child.text:
                    table_chars += len(re.sub(r"\s+", "", child.text))
        elif local == "t" and node.text:
            cleaned = re.sub(r"\s+", "", node.text)
            all_chars += len(cleaned)
            text_parts.append(node.text)
    ratio = table_chars / all_chars if all_chars else 0.0
    filename = record["input_filename"] + " " + path.name
    languages = set((record.get("gpt_reference") or {}).get("languages") or [])
    japanese_hint = bool(
        {"ja", "jp"} & languages
        or re.search(r"日文|日语|日本語|履歴書|職務経歴書|履历书", filename, re.I)
    )
    route = "japanese_table" if japanese_hint and table_count and (ratio >= 0.20 or cell_count >= 8) else "word_table" if table_count and ratio >= 0.55 else "word_paragraph"
    joined_text = " ".join(text_parts)
    structure_type = (
        "table_grid" if route in {"japanese_table", "word_table"}
        else "paragraph_numbered_key_value" if re.search(r"School\s+1\s*:", joined_text, re.I) and re.search(r"Company\s+1\s*:", joined_text, re.I)
        else "paragraph_heading_sections" if re.search(r"教育|学历|学歴|Education|Ausbildung|工作|職歴|Experience|Beruf", joined_text, re.I)
        else "paragraph_freeform"
    )
    pdf_chars = int((record.get("pdf_profile") or {}).get("text_chars") or 0)
    return {
        "route": route,
        "structure_type": structure_type,
        "table_count": table_count,
        "cell_count": cell_count,
        "table_text_ratio": round(ratio, 4),
        "word_text_chars": all_chars,
        "pdf_word_text_ratio": round(all_chars / pdf_chars, 4) if pdf_chars else 0.0,
        "japanese_hint": japanese_hint,
    }


def html_tables_as_xls_sheets(html_text: str) -> list[tuple[str, list[list[Any]]]]:
    soup = PARSER.BeautifulSoup(html_text, "html.parser")
    sheets: list[tuple[str, list[list[Any]]]] = []
    grid_cell = XLS_RULES.xls_html.GridCell
    for table_index, table in enumerate(soup.find_all("table"), 1):
        rows = [row for row in table.find_all("tr") if row.find_parent("table") is table]
        occupied: set[tuple[int, int]] = set()
        grid: list[list[Any]] = []
        width = 0
        for row_index, row in enumerate(rows):
            values: list[Any] = []
            column = 0
            cells = [cell for cell in row.find_all(["td", "th"], recursive=False)]
            for cell in cells:
                while (row_index, column) in occupied:
                    values.append(grid_cell(is_covered=True))
                    column += 1
                rowspan = max(1, int(cell.get("rowspan") or 1))
                colspan = max(1, int(cell.get("colspan") or 1))
                cell_copy = PARSER.BeautifulSoup(str(cell), "html.parser")
                for nested_table in cell_copy.find_all("table"):
                    nested_table.decompose()
                value = re.sub(r"\s+", " ", cell_copy.get_text(" ", strip=True)).strip()
                values.append(grid_cell(val=value, rs=rowspan, cs=colspan))
                for offset in range(1, colspan):
                    values.append(grid_cell(is_covered=True))
                for future_row in range(row_index, row_index + rowspan):
                    for future_col in range(column, column + colspan):
                        if future_row != row_index or future_col != column:
                            occupied.add((future_row, future_col))
                column += colspan
            while (row_index, column) in occupied:
                values.append(grid_cell(is_covered=True))
                column += 1
            width = max(width, len(values))
            grid.append(values)
        if not grid:
            continue
        for row in grid:
            row.extend(grid_cell() for _ in range(width - len(row)))
        sheets.append((f"WordTable{table_index}", grid))
    return sheets


def docx_tables_as_xls_sheets(word_path: Path) -> list[tuple[str, list[list[Any]]]]:
    word_ns = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    w = f"{{{word_ns}}}"
    with zipfile.ZipFile(word_path) as archive:
        root = ElementTree.fromstring(archive.read("word/document.xml"))
    parent = {child: node for node in root.iter() for child in node}
    grid_cell = XLS_RULES.xls_html.GridCell
    sheets: list[tuple[str, list[list[Any]]]] = []

    def nearest_table(node: ElementTree.Element) -> ElementTree.Element | None:
        current = parent.get(node)
        while current is not None:
            if current.tag == f"{w}tbl":
                return current
            current = parent.get(current)
        return None

    for table_index, table in enumerate(root.iter(f"{w}tbl"), 1):
        grid: list[list[Any]] = []
        width = 0
        for row in table.findall(f"{w}tr"):
            values: list[Any] = []
            for cell in row.findall(f"{w}tc"):
                text_parts: list[str] = []
                for node in cell.iter():
                    if node.tag == f"{w}t" and node.text and nearest_table(node) is table:
                        text_parts.append(node.text)
                    elif node.tag in {f"{w}tab", f"{w}br", f"{w}cr"} and nearest_table(node) is table:
                        text_parts.append(" ")
                value = re.sub(r"\s+", " ", "".join(text_parts)).strip()
                grid_span = cell.find(f"{w}tcPr/{w}gridSpan")
                colspan = max(1, int(grid_span.get(f"{w}val") or 1)) if grid_span is not None else 1
                values.append(grid_cell(val=value, cs=colspan))
                values.extend(grid_cell(is_covered=True) for _ in range(colspan - 1))
            width = max(width, len(values))
            if values:
                grid.append(values)
        if not grid:
            continue
        for row in grid:
            row.extend(grid_cell() for _ in range(width - len(row)))
        if any(cell.val for row in grid for cell in row if not cell.is_covered):
            sheets.append((f"WordOOXMLTable{table_index}", grid))
    return sheets


def xls_grid_candidate(html_text: str, word_path: Path, download_date: str) -> str:
    sheets = docx_tables_as_xls_sheets(word_path)
    if not sheets:
        raw_word_html = DOM.convert_docx_ooxml_to_html(word_path)
        sheets = html_tables_as_xls_sheets(raw_word_html or html_text)
    if not sheets:
        return ""
    xls_html = XLS_RULES.xls_html
    fragment = xls_html.build_excel_table_fragment(sheets)
    cleaned = xls_html.word_html.clean_html_styles(fragment)
    candidate = xls_html.word_html.build_semantic_html(
        cleaned, word_path, download_date, "", "", "word-table-xls-grid"
    )
    candidate = xls_html.enhance_excel_dom_annotations(candidate)
    candidate = xls_html.bind_excel_collection_records(candidate)
    candidate = xls_html.annotate_excel_language_layers(candidate)
    try:
        _folder, _codes, _evidence, candidate = xls_html.classify_excel_html_language(candidate)
    except KeyError:
        # The reusable XLS classifier currently maps only 中/日/英 folder
        # labels.  Its downstream repair pass also assumes English-style dates,
        # so an unsupported language must fall back to the standard Word HTML
        # instead of accepting a partially classified XLS-grid candidate.
        return ""
    return candidate


def apply_layout_route(
    html_path: Path, profile: dict[str, Any], word_path: Path, download_date: str,
    disable_xls_grid: bool = False,
) -> dict[str, Any]:
    global XLS_RULES
    if profile["route"] not in {"japanese_table", "word_table"}:
        return profile
    if XLS_RULES is None:
        XLS_RULES = load_module("xls_to_html_to_json.v2.py", "_pdf_rebuild_xls_rules_v2")
    original = html_path.read_text(encoding="utf-8", errors="replace")
    repaired = XLS_RULES.repair_html(original)
    repaired = XLS_RULES.repair_bound_identity_dom(repaired)
    grid_rebuild_used = False
    if (
        not disable_xls_grid
        and profile["route"] in {"japanese_table", "word_table"}
        and profile.get("table_text_ratio", 0) >= 0.45
    ):
        candidate = xls_grid_candidate(original, word_path, download_date)
        if candidate:
            try:
                candidate = XLS_RULES.repair_bound_identity_dom(XLS_RULES.repair_html(candidate))
            except (AttributeError, KeyError, TypeError, ValueError):
                # XLS enhancement is optional.  A language/date pattern outside
                # the reusable XLS rules must not abort extraction when the
                # standard Word HTML is already available.
                candidate = ""
        if candidate:
            standard_validation = DOM.validate_semantic_html(repaired)
            candidate_validation = DOM.validate_semantic_html(candidate)
            original_length = len(re.sub(r"\s+", "", DOM.strip_tags(original)))
            candidate_length = len(re.sub(r"\s+", "", DOM.strip_tags(candidate)))
            standard_score = (
                int(standard_validation.get("annotated_field_count") or 0),
                int(standard_validation.get("section_count") or 0),
            )
            candidate_score = (
                int(candidate_validation.get("annotated_field_count") or 0),
                int(candidate_validation.get("section_count") or 0),
            )
            if (
                candidate_validation.get("valid")
                and candidate_length >= int(original_length * 0.45)
                and candidate_score > standard_score
            ):
                repaired = candidate
                grid_rebuild_used = True
    validation = DOM.validate_semantic_html(repaired)
    profile = dict(profile)
    profile["xls_dom_repair_applied"] = True
    profile["xls_grid_rebuild_applied"] = grid_rebuild_used
    profile["semantic_validation"] = validation
    if validation.get("valid"):
        DOM.atomic_write_text(html_path, repaired)
    else:
        profile["route_warning"] = "XLS DOM 修复结果未通过语义HTML验证，保留原Word HTML"
    return profile


def apply_xls_record_repairs(
    parsed: dict[str, Any], parser_quality: dict[str, Any], html_path: Path, profile: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Reuse the proven XLS semantic-table repair chain for Japanese Word tables."""
    if profile.get("route") != "japanese_table" or not profile.get("xls_dom_repair_applied"):
        return parsed, parser_quality
    html_text = html_path.read_text(encoding="utf-8", errors="replace")
    quality = dict(parser_quality)
    XLS_RULES.repair_bound_identity(parsed, html_text)
    XLS_RULES.repair_variant_names(parsed, html_text)
    XLS_RULES.merge_bound_self_evaluation(parsed, html_text)
    XLS_RULES.clear_verified_name_warning(parsed, html_text, quality)
    XLS_RULES.prune_language_without_sections(parsed, html_text)
    XLS_RULES.clear_collections_without_dom(parsed, html_text)
    XLS_RULES.prune_profile_without_core_dom(parsed, html_text)
    XLS_RULES.merge_bound_work_fields(parsed, html_text)
    XLS_RULES.rebuild_bound_work_records(parsed, html_text)
    XLS_RULES.merge_mixed_work_records(parsed, html_text)
    XLS_RULES.merge_training_work_fields(parsed, html_text)
    XLS_RULES.remove_mixed_work_from_education(parsed, html_text)
    XLS_RULES.rebuild_bound_education(parsed, html_text)
    XLS_RULES.rebuild_japanese_education(parsed, html_text)
    XLS_RULES.merge_training_into_education(parsed, html_text)
    XLS_RULES.filter_education_to_explicit_dom(parsed, html_text)
    XLS_RULES.restore_work_to_explicit_dom(parsed, html_text)
    XLS_RULES.merge_bound_language_records(parsed, html_text)
    XLS_RULES.rebuild_certificate_rows(parsed, html_text)
    XLS_RULES.restore_work_to_explicit_dom(parsed, html_text)
    XLS_RULES.sanitize_record(parsed)
    XLS_RULES.normalize_record_dates(parsed)
    XLS_RULES.sanitize_record(parsed)
    structured = parsed.get("structured_data") or {}
    resumes = structured.get("resumes") or []
    issues = list(quality.get("issues") or [])
    if any(resume.get("work_experiences") or resume.get("education_list") for resume in resumes):
        issues = [issue for issue in issues if issue != "resume_structure_incomplete"]
    quality["issues"] = list(dict.fromkeys(issues))
    quality["xls_record_repair_pipeline"] = True
    return parsed, quality


def source_date(record: dict[str, Any]) -> tuple[str, str]:
    for row in record.get("manifest_records") or []:
        value = str(row.get("download_date") or "").strip()
        if value:
            return value, "PDF文档.json 历史修改/落地时间"
    path = Path(record["input_path"])
    return datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S"), "input PDF 文件修改时间"


def canonicalize_resumes(structured: dict[str, Any]) -> None:
    resumes = structured.get("resumes") or []
    for resume in resumes:
        language = str(resume.pop("resume_languge", "") or resume.get("resume_language") or "").strip()
        resume["resume_language"] = "ja" if language == "jp" else language
        base = resume.get("base_info") or {}
        email_candidates = SOURCE_EMAIL_RE.findall(str(base.get("email") or ""))
        if email_candidates:
            base["email"] = email_candidates[0]
            resume["base_info"] = base
        # The current project schema removed this historical parser-only field.
        for row in resume.get("work_experiences") or []:
            if isinstance(row, dict):
                row.pop("company_nature", None)
    chinese = next((resume for resume in resumes if resume.get("resume_language") == "zh"), None)
    if chinese is None and resumes:
        source_base = resumes[0].get("base_info") or {}
        chinese_base = PARSER.empty_object(PARSER.BASE_FIELDS)
        for field in ("full_name", "phone", "email", "platform_from", "platform_resume_id"):
            chinese_base[field] = source_base.get(field, "")
        chinese = {
            "resume_language": "zh",
            "base_info": chinese_base,
            **{name: [] for name in PARSER.RESUME_LISTS},
        }
        resumes.insert(0, chinese)
    elif chinese is not None and resumes[0] is not chinese:
        resumes[:] = [chinese, *[resume for resume in resumes if resume is not chinese]]
    if resumes:
        structured["base_info"] = copy.deepcopy(resumes[0].get("base_info") or {})


def split_period(value: str) -> tuple[str, str]:
    parts = re.split(r"\s*(?:--|—|–|―|～|〜|~|至|到)\s*", str(value or ""), maxsplit=1)
    start = PARSER.normalized_month(parts[0]) if parts and parts[0].strip() else ""
    end = PARSER.normalized_month(parts[1]) if len(parts) > 1 and parts[1].strip() else ""
    return start, end


def paragraph_key_value_override(
    parsed: dict[str, Any], parser_quality: dict[str, Any], html_path: Path
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Parse iLovePDF paragraph resumes whose sections use numbered English keys."""
    html_text = html_path.read_text(encoding="utf-8", errors="replace")
    soup = PARSER.BeautifulSoup(html_text, "html.parser")
    paragraphs = soup.find_all("p")
    lines = [re.sub(r"\s+", " ", node.get_text(" ", strip=True)).strip() for node in paragraphs]
    if not any(re.match(r"^School\s+1\s*:", line, re.I) for line in lines):
        return parsed, parser_quality
    if not any(re.match(r"^Company\s+1\s*:", line, re.I) for line in lines):
        return parsed, parser_quality

    base = PARSER.empty_object(PARSER.BASE_FIELDS)
    for field in ("full_name", "age", "phone", "email"):
        node = soup.find(attrs={"data-field": field})
        if node:
            base[field] = node.get_text(" ", strip=True)
    location = next((re.sub(r"^Location\s*:\s*", "", line, flags=re.I) for line in lines if re.match(r"^Location\s*:", line, re.I)), "")
    base["address"] = location
    base["platform_from"] = "PDF/Word简历"
    base["age"] = re.sub(r"\D", "", str(base.get("age") or ""))

    groups: dict[str, dict[int, dict[str, str]]] = {"education": {}, "work": {}, "language": {}}
    for node, line in zip(paragraphs, lines):
        match = NUMBERED_KEY_RE.match(line)
        if not match:
            continue
        label = match.group("label").strip().casefold()
        index = int(match.group("index"))
        value = match.group("value").strip()
        collection = (
            "education" if label in {"school", "major", "degree"}
            else "work" if label in {"company", "description"}
            else "language" if label in {"language", "details"}
            else ""
        )
        if collection:
            groups[collection].setdefault(index, {})[label] = value
        elif label == "time":
            section = node.find_parent("section")
            section_type = str(section.get("data-section-type") or "") if section else ""
            target = "education" if section_type == "education_list" else "work" if section_type == "work_experiences" else ""
            if target:
                groups[target].setdefault(index, {})["time"] = value

    education: list[dict[str, Any]] = []
    for index in sorted(groups["education"]):
        item = groups["education"][index]
        start, end = split_period(item.get("time", ""))
        degree = item.get("degree", "")
        row = PARSER.empty_object(PARSER.EDUCATION_FIELDS)
        row.update(
            school_name=item.get("school", ""),
            school_major_name=item.get("major", ""),
            school_degree_type=degree,
            school_degree_rank=str(PARSER.degree_rank("", degree, item.get("school", ""))),
            school_start_ym=start,
            school_end_ym=end,
        )
        education.append(row)

    work: list[dict[str, Any]] = []
    for index in sorted(groups["work"]):
        item = groups["work"][index]
        start, end = split_period(item.get("time", ""))
        row = PARSER.empty_object(PARSER.WORK_FIELDS)
        row.update(
            company_name=item.get("company", ""),
            position_start=start,
            position_resigned=end,
            status="离职" if end else "",
            position_responsibilities=item.get("description", ""),
        )
        work.append(row)

    languages: list[dict[str, Any]] = []
    for index in sorted(groups["language"]):
        item = groups["language"][index]
        details = item.get("details", "")
        languages.append(
            PARSER.normalize_row(
                {
                    "language_name": item.get("language", ""),
                    "language_level": details,
                    "language_certificate": "有" if PARSER.LANGUAGE_CERTIFICATE_RE.search(details) else "",
                },
                PARSER.COLLECTION_FIELDS["language_list"],
            )
        )

    expected = PARSER.empty_object(PARSER.EXPECTED_FIELDS)
    simple_fields = {
        "Arrival Time": "expected_start_date",
        "Job Type": "expected_employment_type",
        "Target Location": "expected_city",
        "Target Industry": "expected_industry",
    }
    for line in lines:
        for label, field in simple_fields.items():
            if line.casefold().startswith(label.casefold()):
                expected[field] = line.split(":", 1)[-1].strip()
    if expected["expected_start_date"]:
        expected["expected_start_date"] = PARSER.normalized_month(expected["expected_start_date"])
    if expected["expected_employment_type"] == "フルタイム":
        expected["expected_employment_type"] = "全职"

    self_section = soup.find("section", attrs={"data-section-type": "self_evaluation"})
    if self_section:
        base["pr"] = "\n".join(
            re.sub(r"^Point\s+\d+\s*:\s*", "", p.get_text(" ", strip=True), flags=re.I)
            for p in self_section.find_all("p")
            if p.get_text(" ", strip=True)
        )

    foreign = {
        "resume_languge": "jp",
        "base_info": base,
        "expected_list": [expected] if any(str(value).strip() for value in expected.values()) else [],
        "work_experiences": work,
        "education_list": education,
        "certificate_list": [],
        "language_list": languages,
        "skills_list": [],
        "training_list": [],
        "project_list": [],
        "communication_list": [],
    }
    chinese_base = PARSER.empty_object(PARSER.BASE_FIELDS)
    for field in ("full_name", "age", "phone", "email", "platform_from"):
        chinese_base[field] = base.get(field, "")
    chinese = {
        "resume_languge": "zh",
        "base_info": chinese_base,
        **{name: [] for name in PARSER.RESUME_LISTS},
    }
    structured = {
        "base_info": copy.deepcopy(chinese_base),
        "expected_info": PARSER.empty_object(PARSER.EXPECTED_FIELDS),
        "current_info": PARSER.latest_work([]),
        "education_info": PARSER.highest_education([]),
        "resumes": [chinese, foreign],
    }
    parsed = dict(parsed)
    parsed["structured_data"] = structured
    parser_quality = dict(parser_quality)
    issues = [issue for issue in parser_quality.get("issues", []) if issue != "resume_name_unreliable"]
    issues.append("foreign_translation_missing")
    parser_quality["issues"] = list(dict.fromkeys(issues))
    parser_quality["paragraph_key_value_override"] = True
    return parsed, parser_quality


MONTH_NAME = r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
FLEX_DATE_TOKEN = rf"(?:\d{{1,2}}[./]\d{{4}}|(?:19|20)\d{{2}}\s*(?:年|[./-])\s*\d{{1,2}}\s*月?|{MONTH_NAME}\s+(?:19|20)\d{{2}}|(?:19|20)\d{{2}})"
FLEX_RANGE_RE = re.compile(
    rf"(?P<start>{FLEX_DATE_TOKEN})\s*(?:--|—|–|―|[-~～@]|から|bis)\s*(?P<end>{FLEX_DATE_TOKEN}|Present|Current|Now|Heute|今|今迄|現在)?",
    re.I,
)


def flexible_period(value: str) -> tuple[str, str, tuple[int, int] | None]:
    normalized = unicodedata.normalize("NFKC", str(value or ""))
    match = FLEX_RANGE_RE.search(normalized)
    if not match:
        return "", "", None
    start = PARSER.normalized_month(match.group("start"))
    end_raw = str(match.group("end") or "")
    end = "" if re.fullmatch(r"Present|Current|Now|Heute|今|今迄|現在", end_raw, re.I) else PARSER.normalized_month(end_raw)
    return start, end, match.span()


def section_paragraphs(section: Any) -> list[str]:
    values: list[str] = []
    for node in section.find_all(["p", "tr"]):
        value = re.sub(r"\s+", " ", node.get_text(" ", strip=True)).strip()
        if value and (not values or values[-1] != value):
            values.append(value)
    return values


def parse_labeled_work(lines: list[str]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if any(re.match(r"^Period\s*:", line, re.I) for line in lines):
        groups: list[list[str]] = []
        current: list[str] = []
        for line in lines:
            if re.match(r"^Period\s*:", line, re.I) and current:
                groups.append(current)
                current = []
            if current or re.match(r"^Period\s*:", line, re.I):
                current.append(line)
        if current:
            groups.append(current)
        for group in groups:
            row = PARSER.empty_object(PARSER.WORK_FIELDS)
            start, end, _ = flexible_period(group[0].split(":", 1)[-1])
            row["position_start"], row["position_resigned"] = start, end
            descriptions: list[str] = []
            for line in group[1:]:
                if re.match(r"^Company\s*:", line, re.I):
                    row["company_name"] = line.split(":", 1)[-1].strip()
                elif re.match(r"^(?:Title|Position)\s*:", line, re.I):
                    row["position"] = line.split(":", 1)[-1].strip()
                elif not re.match(r"^Description\s*:\s*$", line, re.I):
                    descriptions.append(line)
            row["position_responsibilities"] = "\n".join(descriptions)
            row["status"] = "离职" if end else "在职"
            if row["company_name"]:
                records.append(row)
        return records

    starts: list[int] = []
    ranges: dict[int, tuple[str, str, tuple[int, int]]] = {}
    for index, line in enumerate(lines):
        start, end, span = flexible_period(line)
        if span:
            starts.append(index)
            ranges[index] = (start, end, span)
    for offset, index in enumerate(starts):
        end_index = starts[offset + 1] if offset + 1 < len(starts) else len(lines)
        line = lines[index]
        start, end, span = ranges[index]
        before = line[: span[0]].strip(" \t:：,-")
        after = line[span[1] :].strip(" \t:：,-")
        descriptor = after or before
        if re.search(r"期間\s*[:：]?\s*$", before):
            descriptor = before.rsplit("期間", 1)[0].strip()
        if not descriptor and index > 0 and index - 1 not in starts:
            descriptor = lines[index - 1]
        row = PARSER.empty_object(PARSER.WORK_FIELDS)
        row["position_start"], row["position_resigned"] = start, end
        if " - " in descriptor:
            row["position"], row["company_name"] = [part.strip() for part in descriptor.split(" - ", 1)]
        elif "," in descriptor and not re.search(r"株式会社|有限公司|会社", descriptor):
            parts = [part.strip() for part in descriptor.split(",") if part.strip()]
            row["position"] = parts[0] if parts else ""
            row["company_name"] = ", ".join(parts[1:]) if len(parts) > 1 else ""
        else:
            row["company_name"] = descriptor
        details = [value for value in lines[index + 1 : end_index] if value != descriptor]
        row["position_responsibilities"] = "\n".join(details)
        row["status"] = "离职" if end else "在职"
        if row["company_name"] or row["position"]:
            records.append(row)
    if records:
        return records

    # Traditional Japanese rirekisho tables often contain one event per row
    # rather than a date range: ``2016 3 Company 入社`` / ``2016 7 Company 退社``.
    active: dict[str, Any] | None = None
    for source_line in lines:
        line = unicodedata.normalize("NFKC", source_line)
        match = re.match(r"^\s*((?:19|20)\d{2})\s*[年./\-]?\s*(\d{1,2})?\s*[月./\-]?\s+(.+?)\s*$", line)
        if not match:
            if active is not None and not re.fullmatch(r"職歴|以上", line.strip()):
                detail = line.strip()
                if detail and detail not in active["position_responsibilities"]:
                    active["position_responsibilities"] = "\n".join(filter(None, [active["position_responsibilities"], detail]))
            continue
        year, month, description = match.group(1), match.group(2) or "1", match.group(3).strip()
        date_value = PARSER.normalized_month(f"{year}-{month}")
        if re.search(r"退社|退職|離職|卒業", description):
            if active is not None:
                active["position_resigned"] = date_value
                active["status"] = "离职"
            continue
        if re.search(r"入社|勤務|配属|実習|インターン", description) or re.search(r"株式会社|有限公司|会社|病院|センター|大学", description):
            row = PARSER.empty_object(PARSER.WORK_FIELDS)
            company = re.sub(r"\s*(?:入社|勤務開始|配属).*$", "", description).strip()
            row["company_name"] = company
            row["position_start"] = date_value
            row["status"] = "在职"
            records.append(row)
            active = row
    return records


def parse_labeled_education(lines: list[str]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if any(re.match(r"^Period\s*:", line, re.I) for line in lines):
        row = PARSER.empty_object(PARSER.EDUCATION_FIELDS)
        for line in lines:
            if re.match(r"^Period\s*:", line, re.I):
                row["school_start_ym"], row["school_end_ym"], _ = flexible_period(line.split(":", 1)[-1])
            elif re.match(r"^School\s*:", line, re.I):
                row["school_name"] = line.split(":", 1)[-1].strip()
            elif re.match(r"^(?:Degree/)?Major\s*:", line, re.I):
                row["school_major_name"] = line.split(":", 1)[-1].strip()
        if row["school_name"]:
            records.append(row)
        return records

    starts: list[int] = []
    ranges: dict[int, tuple[str, str, tuple[int, int]]] = {}
    for index, line in enumerate(lines):
        start, end, span = flexible_period(line)
        if span:
            starts.append(index)
            ranges[index] = (start, end, span)
        elif re.fullmatch(r"(?:19|20)\d{2}", line):
            starts.append(index)
            ranges[index] = (PARSER.normalized_month(line), "", (0, len(line)))
    for offset, index in enumerate(starts):
        end_index = starts[offset + 1] if offset + 1 < len(starts) else len(lines)
        line = lines[index]
        start, end, span = ranges[index]
        before = line[: span[0]].strip(" \t:：,-")
        after = line[span[1] :].strip(" \t:：,-")
        descriptor = after or before
        following = lines[index + 1 : end_index]
        row = PARSER.empty_object(PARSER.EDUCATION_FIELDS)
        row["school_start_ym"], row["school_end_ym"] = start, end
        if re.search(r"University|Universität|大学|学院|Institut", descriptor, re.I):
            row["school_name"] = descriptor
        elif following:
            school = next((item for item in following if re.search(r"University|Universität|大学|学院|Institut", item, re.I)), "")
            row["school_name"] = school or descriptor
            row["school_major_name"] = descriptor if school and descriptor != school else ""
        else:
            row["school_name"] = descriptor
        degree_text = " ".join([descriptor, *following[:2]])
        degree = next((value for value in ("博士", "修士", "学士", "Master", "Bachelor") if re.search(value, degree_text, re.I)), "")
        row["school_degree_type"] = degree
        row["school_degree_rank"] = str(PARSER.degree_rank("", degree, row["school_name"])) if degree else ""
        if row["school_name"]:
            records.append(row)
    return records


def parse_global_structures(page_text: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Last-resort structure recovery for a whole table flattened to one text node."""
    normalized = unicodedata.normalize("NFKC", re.sub(r"\s+", " ", page_text))
    works: list[dict[str, Any]] = []
    education: list[dict[str, Any]] = []
    matches = list(FLEX_RANGE_RE.finditer(normalized))
    for index, match in enumerate(matches):
        tail_end = matches[index + 1].start() if index + 1 < len(matches) else min(len(normalized), match.end() + 500)
        tail = normalized[match.end() : tail_end].strip(" :：,-~～")
        descriptor = re.split(r"(?:会社紹介|仕事内容|職責|業務内容|専攻|学歴|職歴|教育|技能|資格)", tail, maxsplit=1)[0].strip()
        descriptor = descriptor[:180].strip()
        if not descriptor:
            continue
        start = PARSER.normalized_month(match.group("start"))
        end_raw = str(match.group("end") or "")
        end = "" if re.fullmatch(r"Present|Current|Now|Heute|今|今迄|現在", end_raw, re.I) else PARSER.normalized_month(end_raw)
        nearby = normalized[max(0, match.start() - 80) : match.start()]
        if re.search(r"大学|学院|学校|University|Universität|教育|学歴", descriptor + nearby, re.I):
            row = PARSER.empty_object(PARSER.EDUCATION_FIELDS)
            row["school_name"] = descriptor
            row["school_start_ym"], row["school_end_ym"] = start, end
            education.append(row)
        else:
            row = PARSER.empty_object(PARSER.WORK_FIELDS)
            row["company_name"] = descriptor
            row["position_start"], row["position_resigned"] = start, end
            row["status"] = "离职" if end else "在职"
            works.append(row)

    event_re = re.compile(
        r"((?:19|20)\d{2})\s*年?\s*(\d{1,2})\s*月?\s+(.{2,160}?)(?=(?:19|20)\d{2}\s*年?\s*\d{1,2}\s*月?|年\s*月|$)"
    )
    active_work: dict[str, Any] | None = None
    for match in event_re.finditer(normalized):
        year, month, description = match.group(1), match.group(2), match.group(3).strip()
        date_value = PARSER.normalized_month(f"{year}-{month}")
        if re.search(r"退社|退職|離職", description):
            if active_work is not None:
                active_work["position_resigned"] = date_value
                active_work["status"] = "离职"
            continue
        if re.search(r"入学|卒業|修了", description) and re.search(r"大学|学院|学校", description):
            row = PARSER.empty_object(PARSER.EDUCATION_FIELDS)
            row["school_name"] = re.sub(r"\s*(?:入学|卒業|修了).*$", "", description).strip()
            row["school_start_ym"] = date_value
            education.append(row)
        elif re.search(r"入社|勤務|実習|インターン", description):
            row = PARSER.empty_object(PARSER.WORK_FIELDS)
            row["company_name"] = re.sub(r"\s*(?:入社|勤務開始|配属).*$", "", description).strip()
            row["position_start"] = date_value
            row["status"] = "在职"
            works.append(row)
            active_work = row
    return works, education


def heading_paragraph_fallback(
    parsed: dict[str, Any], parser_quality: dict[str, Any], html_path: Path
) -> tuple[dict[str, Any], dict[str, Any]]:
    structured = parsed.get("structured_data") or {}
    resumes = structured.get("resumes") or []
    if any(resume.get("work_experiences") or resume.get("education_list") for resume in resumes):
        return parsed, parser_quality
    soup = PARSER.BeautifulSoup(html_path.read_text(encoding="utf-8", errors="replace"), "html.parser")
    page_text = soup.get_text(" ", strip=True)
    language = "de" if re.search(r"Bildungsweg|Praxiserfahrung|Lebenslauf|Persönlich", page_text, re.I) else "ja" if re.search(r"職務経歴|学歴|履歴書", page_text) else "en"
    source_resume = next((resume for resume in resumes if resume.get("resume_languge") in {language, "jp" if language == "ja" else language}), None)
    if source_resume is None:
        source_resume = {
            "resume_languge": "jp" if language == "ja" else language,
            "base_info": PARSER.empty_object(PARSER.BASE_FIELDS),
            **{name: [] for name in PARSER.RESUME_LISTS},
        }
        resumes.append(source_resume)

    work_lines: list[str] = []
    education_lines: list[str] = []
    for section in soup.find_all("section"):
        kind = str(section.get("data-section-type") or "")
        if kind == "work_experiences":
            work_lines.extend(section_paragraphs(section))
        elif kind == "education_list":
            education_lines.extend(section_paragraphs(section))
    all_lines: list[str] = []
    for node in soup.find_all(["p", "tr"]):
        value = re.sub(r"\s+", " ", node.get_text(" ", strip=True)).strip()
        if value and (not all_lines or all_lines[-1] != value):
            all_lines.append(value)
    heading_map = {
        "education": re.compile(r"^[»>◆●・\s]*(?:Bildungsweg|Bildung|Education|E\s*D\s*U\s*C\s*A\s*T\s*I\s*O\s*N|学歴|教育の背景|教育背景|教育履歴)[：:\s]*$", re.I),
        "work": re.compile(r"^[»>◆●・\s]*(?:Praxiserfahrung|Work Experience|Experience|E\s*X\s*P\s*E\s*R\s*I\s*E\s*N\s*C\s*E|職務経歴|職歴|社歴|業務履歴|実習の経験|科研工作|社会工作|学校工作)[：:\s]*$", re.I),
        "stop": re.compile(r"^[»>◆●・\s]*(?:Weitere Kenntnisse|Kenntnisse|Skills|Languages|免許|資格|プロジェクト|Project|言語能力|技能|証書|自己評価|論文|所獲奖励|総合技能)", re.I),
    }
    active = ""
    for line in all_lines:
        if heading_map["education"].match(line):
            active = "education"
            continue
        if heading_map["work"].match(line):
            active = "work"
            continue
        if heading_map["stop"].match(line):
            active = ""
            continue
        if active == "education" and line not in education_lines:
            education_lines.append(line)
        elif active == "work" and line not in work_lines:
            work_lines.append(line)

    works = parse_labeled_work(work_lines)
    education = parse_labeled_education(education_lines)
    if not works and not education:
        works, education = parse_global_structures(page_text)
    if not works and not education:
        return parsed, parser_quality
    source_resume["work_experiences"] = works
    source_resume["education_list"] = education
    structured["resumes"] = resumes
    quality = dict(parser_quality)
    issues = [issue for issue in quality.get("issues", []) if issue != "resume_structure_incomplete"]
    quality["issues"] = list(dict.fromkeys(issues))
    quality["heading_paragraph_fallback"] = True
    return parsed, quality


def repair_identity_with_evidence(
    structured: dict[str, Any], record: dict[str, Any], html_text: str
) -> list[dict[str, str]]:
    reference = record.get("gpt_reference") or {}
    if not reference:
        return []
    evidence_text = DOM.strip_tags(html_text) + "\n" + record["input_filename"]
    compact_evidence = re.sub(r"\s+", "", evidence_text).casefold()
    digit_evidence = re.sub(r"\D", "", evidence_text)
    manifest = record.get("manifest_records") or []
    manifest_names = {str(row.get("candidate_name") or "").strip() for row in manifest}
    manifest_phones = {re.sub(r"\D", "", str(row.get("phone") or "")) for row in manifest}
    manifest_emails = {str(row.get("email") or "").strip().casefold() for row in manifest}
    candidates = {
        "full_name": str(reference.get("candidate_name") or "").strip(),
        "phone": str(reference.get("phone") or "").strip(),
        "email": str(reference.get("email") or "").strip(),
    }
    verified: dict[str, str] = {}
    phone_digits = re.sub(r"\D", "", candidates["phone"])
    if phone_digits and (phone_digits in digit_evidence or phone_digits in manifest_phones):
        verified["phone"] = candidates["phone"]
    email = candidates["email"].casefold()
    if email and (email in evidence_text.casefold() or email in manifest_emails):
        verified["email"] = candidates["email"]
    name = candidates["full_name"]
    contact_verified = bool(verified.get("phone") or verified.get("email"))
    if name and (
        re.sub(r"\s+", "", name).casefold() in compact_evidence
        or name in manifest_names
        or contact_verified
    ):
        verified["full_name"] = name

    actions: list[dict[str, str]] = []
    resumes = structured.get("resumes") or []
    primary = resumes[0] if resumes else None
    if primary:
        base = primary.get("base_info") or {}
        for field, value in verified.items():
            current = str(base.get(field) or "")
            if current != value:
                base[field] = value
                actions.append({"field": field, "before": current, "after": value})
        primary["base_info"] = base
        for resume in resumes[1:]:
            other = resume.get("base_info") or {}
            for field, value in verified.items():
                if field != "full_name" or not str(other.get(field) or "").strip() or NAME_NOISE_RE.search(str(other.get(field) or "")):
                    other[field] = value
            resume["base_info"] = other
        structured["base_info"] = copy.deepcopy(base)
    return actions


def build_source(record: dict[str, Any], resume_index: int) -> dict[str, Any]:
    originals = [str(row.get("original_path") or "") for row in record.get("manifest_records") or []]
    originals = list(dict.fromkeys(value for value in originals if value))
    download_date, _ = source_date(record)
    return {
        "path": record["input_path"],
        "original_path": originals[0] if originals else record["input_path"],
        "filename": record["input_filename"],
        "extension": ".pdf",
        "size": record["size"],
        "pdf_filename": record["input_filename"],
        "word_path": record.get("word_path") or "",
        "resume_index": resume_index,
        "source_files": [
            {
                "input_path": record["input_path"],
                "original_paths": originals,
                "filename": record["input_filename"],
                "sha256": record["source_sha256"],
                "size": record["size"],
                "word_path": record.get("word_path") or "",
                "download_date": download_date,
                "manifest_indices": [row.get("index") for row in record.get("manifest_records") or []],
            }
        ],
        "note": "iLovePDF Word 为主要结构提取输入；原 PDF 为来源、哈希和视觉核验事实依据。",
    }


def compare_gpt(payload: dict[str, Any], reference: dict[str, Any]) -> dict[str, Any]:
    base = (payload.get("structured_data") or {}).get("base_info") or {}
    differences: list[str] = []
    for field in ("full_name", "phone", "email"):
        left = re.sub(r"\s+", "", str(base.get(field) or "")).casefold()
        right = re.sub(r"\s+", "", str(reference.get(field if field != "full_name" else "candidate_name") or "")).casefold()
        if left and right and left != right:
            differences.append(field)
    return {
        "reference_json": str(reference.get("json_path") or ""),
        "reference_candidate": str(reference.get("candidate_name") or ""),
        "reference_source_count": int(reference.get("source_count") or 0),
        "identity_difference_fields": differences,
    }


def complete_payload(
    record: dict[str, Any], parsed: dict[str, Any], quality: dict[str, Any], html_path: Path,
    resume_index: int, layout_profile: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    structured = copy.deepcopy(parsed.get("structured_data") or {})
    canonicalize_resumes(structured)
    resumes = structured.get("resumes") or []
    html_text = html_path.read_text(encoding="utf-8", errors="replace")
    identity_repairs = repair_identity_with_evidence(structured, record, html_text)
    # raw_text is an independent source-evidence layer. Never rebuild or pad it
    # from structured JSON fields; otherwise a wrong field can validate itself.
    raw_text = DOM.strip_tags(html_text).strip()
    identity = structured.get("base_info") or {}
    download_date, download_source = source_date(record)
    parsed_dates = parsed.get("dates") or {}
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    warnings = list(dict.fromkeys(quality.get("issues") or []))
    base = structured.get("base_info") or {}
    resolved_name = str(base.get("full_name") or "").strip()
    if resolved_name and not NAME_NOISE_RE.search(resolved_name):
        warnings = [
            warning for warning in warnings
            if warning not in {"missing_full_name", "resume_name_unreliable", "invalid_full_name_semantics"}
        ]
    if not resolved_name:
        warnings.append("missing_full_name")
    elif NAME_NOISE_RE.search(resolved_name):
        warnings.append("invalid_full_name_semantics")
    if not any((resume.get("work_experiences") or resume.get("education_list")) for resume in resumes):
        warnings.append("resume_structure_incomplete")
    payload = {
        "schema_version": "codex-resume-json-1.0",
        "record_id": hashlib.sha256(f"{record['source_sha256']}:{resume_index}".encode()).hexdigest(),
        "source": build_source(record, resume_index),
        "dates": {
            "resume_updated_date": str(parsed_dates.get("resume_updated_date") or download_date),
            "resume_download_date": download_date,
            "resume_updated_date_source": "Word正文日期或PDF历史落地时间",
            "resume_download_date_source": download_source,
            "sys_created_date": now,
            "sys_updated_date": now,
        },
        "extraction": {
            "reader_group": "ilovepdf_word_semantic_dom",
            "converter": str(quality.get("html_generator_version") or "c_resume_html_dom_common.v2.py"),
            "parser": "c_resume_html_to_json_common.v2.py + pdf_rebuild_extract.v2.py",
            "status": "success",
            "html_path": str(html_path.resolve()),
            "word_path": record.get("word_path") or "",
            "pdf_used_as": "source_identity_and_visual_audit",
            "layout_route": layout_profile,
            "raw_text_source": "semantic_html_full_text",
        },
        "classification": {
            "document_type": "resume",
            "reason": record.get("classification_reason") or "映射确认为简历",
        },
        "structured_data": structured,
        "raw_text": raw_text,
        "quality": {
            "full_name": str(base.get("full_name") or ""),
            "has_work": bool(resumes and resumes[0].get("work_experiences")),
            "work_count": len(resumes[0].get("work_experiences") or []) if resumes else 0,
            "has_education": bool(resumes and resumes[0].get("education_list")),
            "education_count": len(resumes[0].get("education_list") or []) if resumes else 0,
            "raw_text_length": len(raw_text),
            "quality_status": "needs_review" if warnings else "candidate_passed",
            "warnings": warnings,
        },
    }
    comparison = compare_gpt(payload, record.get("gpt_reference") or {})
    comparison["verified_identity_repairs"] = identity_repairs
    source_authoritative: list[str] = []
    unresolved_differences: list[str] = []
    html_compact = re.sub(r"\s+", "", DOM.strip_tags(html_text)).casefold()
    html_digits = re.sub(r"\D", "", DOM.strip_tags(html_text))
    for field in comparison["identity_difference_fields"]:
        value = str(base.get(field) or "").strip()
        if field == "email":
            backed = bool(EMAIL_RE.fullmatch(value) and value.casefold() in html_compact)
        elif field == "phone":
            digits = re.sub(r"\D", "", value)
            backed = bool(len(digits) >= 7 and digits in html_digits)
        else:
            backed = bool(value and not NAME_NOISE_RE.search(value) and re.sub(r"\s+", "", value).casefold() in html_compact)
        (source_authoritative if backed else unresolved_differences).append(field)
    comparison["source_authoritative_fields"] = source_authoritative
    comparison["unresolved_identity_difference_fields"] = unresolved_differences
    if unresolved_differences:
        payload["quality"]["warnings"].append(
            "reference_identity_difference:" + ",".join(unresolved_differences)
        )
        payload["quality"]["warnings"] = list(dict.fromkeys(payload["quality"]["warnings"]))
        payload["quality"]["quality_status"] = "needs_review"
    return payload, comparison


def main() -> int:
    args = parse_args()
    map_payload = read_json(args.map)
    records = map_payload.get("records") or []
    selected_names: set[str] | None = None
    if args.filenames:
        selected_names = {str(name).casefold() for name in args.filenames}
        records = [row for row in records if row["input_filename"].casefold() in selected_names]
    elif args.scope == "pilot":
        selected_names = {row["input_filename"] for row in (read_json(args.pilot).get("records") or [])}
        records = [row for row in records if row["input_filename"] in selected_names]
    if args.limit > 0:
        records = records[: args.limit]

    passed_dir = args.html_root / "passed"
    review_dir = args.html_root / "review"
    rows: list[dict[str, Any]] = []
    counts = {"success": 0, "needs_review": 0, "non_resume": 0, "failed": 0, "skipped_existing": 0}
    by_sha = {row["source_sha256"]: row for row in map_payload.get("records") or []}
    for record in records:
        row: dict[str, Any] = {"input_filename": record["input_filename"], "source_sha256": record["source_sha256"]}
        if record.get("classification") != "resume":
            row.update(status="non_resume", reason=record.get("classification_reason") or "")
            counts["non_resume"] += 1
            rows.append(row)
            continue
        word_path = Path(str(record.get("word_path") or ""))
        if not word_path.is_file():
            row.update(status="needs_review", reason="没有可信的 iLovePDF Word 对应文件")
            counts["needs_review"] += 1
            rows.append(row)
            continue
        download_date, _ = source_date(record)
        conversion = DOM.convert_single_word_detailed(
            str(word_path), passed_dir, review_dir, record["input_filename"], download_date
        )
        if not conversion.get("ok"):
            row.update(status="failed", reason=conversion.get("error_reason") or "Word转语义HTML失败")
            counts["failed"] += 1
            rows.append(row)
            continue
        html_path = Path(conversion["html_path"])
        layout_profile = apply_layout_route(
            html_path, docx_layout_profile(word_path, record), word_path, download_date,
            disable_xls_grid=args.disable_xls_grid,
        )
        resume_count = int(conversion.get("resume_count") or 1)
        outputs: list[str] = []
        comparisons: list[dict[str, Any]] = []
        record_warnings: list[str] = []
        for resume_index in range(1, resume_count + 1):
            parsed, parser_quality = PARSER.parse_html_record(
                Path(record["input_path"]), html_path, download_date, resume_index=resume_index
            )
            parsed, parser_quality = apply_xls_record_repairs(parsed, parser_quality, html_path, layout_profile)
            parsed, parser_quality = paragraph_key_value_override(parsed, parser_quality, html_path)
            parsed, parser_quality = heading_paragraph_fallback(parsed, parser_quality, html_path)
            payload, comparison = complete_payload(
                record, parsed, parser_quality, html_path, resume_index, layout_profile
            )
            output = args.json_root / f"{safe_stem(record['input_filename'])}__{record['source_sha256'][:12]}__r{resume_index}.json"
            if output.exists() and not args.force:
                counts["skipped_existing"] += 1
            else:
                atomic_json(output, payload)
            outputs.append(str(output.resolve()))
            comparisons.append(comparison)
            record_warnings.extend(payload["quality"]["warnings"])
        status = "needs_review" if record_warnings else "success"
        counts[status] += 1
        row.update(
            status=status,
            html_path=str(html_path.resolve()),
            outputs=outputs,
            resume_count=resume_count,
            converter=conversion.get("converter") or "",
            layout_profile=layout_profile,
            warnings=list(dict.fromkeys(record_warnings)),
            gpt_comparisons=comparisons,
        )
        map_record = by_sha[record["source_sha256"]]
        map_record["processing"].update(
            extract_status=status,
            html_path=str(html_path.resolve()),
            staging_outputs=outputs,
            layout_route=layout_profile.get("route", ""),
        )
        rows.append(row)

    report = {
        "version": VERSION,
        "generated_at": datetime.now().astimezone().isoformat(),
        "scope": "filenames" if args.filenames else args.scope,
        "requested_filenames": list(args.filenames),
        "selected_count": len(records),
        "counts": counts,
        "records": rows,
    }
    atomic_json(args.report, report)
    if args.merge_into_report:
        merged = read_json(args.merge_into_report) if args.merge_into_report.is_file() else {
            "version": VERSION,
            "scope": "all",
            "records": [],
        }
        replacements = {row["input_filename"]: row for row in rows}
        merged_rows = [
            replacements.pop(row.get("input_filename"), row)
            for row in (merged.get("records") or [])
        ]
        merged_rows.extend(replacements.values())
        merged_counts = {"success": 0, "needs_review": 0, "non_resume": 0, "failed": 0, "skipped_existing": 0}
        for row in merged_rows:
            status = str(row.get("status") or "")
            if status in merged_counts:
                merged_counts[status] += 1
        merged.update(
            version=VERSION,
            generated_at=datetime.now().astimezone().isoformat(),
            selected_count=len(merged_rows),
            counts=merged_counts,
            records=merged_rows,
        )
        atomic_json(args.merge_into_report, merged)
    atomic_json(args.map, map_payload)
    print(json.dumps(report["counts"], ensure_ascii=False, indent=2))
    print(f"report={args.report.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
