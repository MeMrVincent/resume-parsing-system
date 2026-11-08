from __future__ import annotations
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1] / "common"))
import rc_config as _rc  # noqa: E402  项目统一配置（python/common/rc_config.py）
# EN: noqa: E402  project-wide configuration (python/common/rc_config.py)
# JA: noqa: E402  プロジェクト共通設定（python/common/rc_config.py）

import argparse
import csv
import json
import tempfile
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = _rc.project_root()
PDF_ROOT = PROJECT_ROOT / _rc.dirname("complete-transfered-htmls") / "pdf"
DEFAULT_MAP = PDF_ROOT / "rebuild-work" / "pdf_rebuild_map.v2.json"
DEFAULT_EXTRACT = PDF_ROOT / "rebuild-reports" / "pdf_full_extract.v2.json"
DEFAULT_AUDIT = PDF_ROOT / "rebuild-reports" / "pdf_full_audit.v2.json"
DEFAULT_JSON = PDF_ROOT / "rebuild-reports" / "pdf_word_problem_table.v2.json"
DEFAULT_CSV = PDF_ROOT / "rebuild-reports" / "pdf_word_problem_table.v2.csv"


def args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="生成 PDF/Word 全量问题协作表" " / Generate the full PDF/Word issue collaboration table / PDF/Word の問題を共同で確認するための全件の表を生成する")
    parser.add_argument("--map", type=Path, default=DEFAULT_MAP)
    parser.add_argument("--extract", type=Path, default=DEFAULT_EXTRACT)
    parser.add_argument("--audit", type=Path, default=DEFAULT_AUDIT)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    return parser.parse_args()


def read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".tmp", dir=path.parent, delete=False) as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
        temporary = Path(stream.name)
    temporary.replace(path)


def classify(
    status: str, reason: str, warnings: list[str], audit_codes: list[str], route: str,
    word_text_chars: int, pdf_word_text_ratio: float, metrics_available: bool,
) -> tuple[str, str, int]:
    joined = "|".join(warnings + audit_codes)
    if "没有可信的 iLovePDF Word" in reason or status == "failed":
        return "需要重新转Word", "请用 iLovePDF 从对应 PDF 重新生成 DOCX，文件名尽量与 PDF 一致。", 1
    if any(key in joined for key in ("resume_structure_incomplete", "invalid_full_name", "missing_full_name", "resume_name_unreliable", "invalid_full_name_semantics")):
        if metrics_available and "resume_structure_incomplete" in joined and (word_text_chars < 80 or (pdf_word_text_ratio and pdf_word_text_ratio < 0.55)):
            return "需要重新转Word", "Word 有效正文过少或相对 PDF 明显缺失；请用 iLovePDF 从对应 PDF 重新生成 DOCX。", 1
        if route == "japanese_table":
            return "日式表格Word较难识别", "请核对 Word 中表格、合并单元格、姓名栏和工作/学历年月列；必要时重新转 Word。", 2
        return "Word结构较难识别", "请核对 Word 是否漏页、文本框丢失、段落顺序错误；必要时重新转 Word。", 2
    if "foreign_translation_missing" in joined:
        return "Word可读，待外文翻译", "无需重新转 Word；后续补中文主版本并保留外文原文。", 3
    if "reference_identity_difference" in joined:
        return "身份字段待复核", "核对姓名、手机、邮箱；Word 有明确值时以 Word/PDF 为准。", 4
    return "其他字段待复核", "核对报告中的具体问题，不建议直接重转 Word。", 5


def main() -> int:
    cfg = args()
    mapping = read(cfg.map)
    extraction = read(cfg.extract)
    audit = read(cfg.audit)
    map_by_name = {row["input_filename"]: row for row in mapping.get("records") or []}
    audit_by_name = {row.get("input_filename", ""): row for row in audit.get("records") or []}
    rows: list[dict[str, Any]] = []
    for item in extraction.get("records") or []:
        if item.get("status") in {"success", "non_resume"}:
            continue
        filename = item["input_filename"]
        mapped = map_by_name.get(filename, {})
        audit_item = audit_by_name.get(filename, {})
        warnings = list(item.get("warnings") or [])
        audit_codes = [issue.get("code", "") for issue in audit_item.get("issues") or []]
        route = str((item.get("layout_profile") or {}).get("route") or (mapped.get("processing") or {}).get("layout_route") or "")
        layout = item.get("layout_profile") or {}
        category, recommendation, priority = classify(
            str(item.get("status") or ""), str(item.get("reason") or ""), warnings, audit_codes, route,
            int(layout.get("word_text_chars") or 0), float(layout.get("pdf_word_text_ratio") or 0),
            "word_text_chars" in layout,
        )
        gpt = mapped.get("gpt_reference") or {}
        rows.append({
            "优先级": priority,
            "问题分类": category,
            "PDF文件名": filename,
            "PDF路径": mapped.get("input_path", ""),
            "Word文件名": mapped.get("word_filename", ""),
            "Word路径": mapped.get("word_path", ""),
            "候选人参考": gpt.get("candidate_name", ""),
            "语言": ",".join(gpt.get("languages") or []),
            "版式路由": route,
            "Word结构类型": str(layout.get("structure_type") or ""),
            "Word有效字符数": int(layout.get("word_text_chars") or 0),
            "Word/PDF正文比": float(layout.get("pdf_word_text_ratio") or 0),
            "转换状态": item.get("status", ""),
            "解析问题": " | ".join(warnings + audit_codes) or str(item.get("reason") or ""),
            "建议动作": recommendation,
        })
    rows.sort(key=lambda row: (row["优先级"], row["PDF文件名"].casefold()))
    for index, row in enumerate(rows, 1):
        row["序号"] = index
    ordered = [{"序号": row.pop("序号"), **row} for row in rows]
    counts = Counter(row["问题分类"] for row in ordered)
    payload = {
        "version": "pdf-word-problem-table-v2.0.0",
        "generated_at": datetime.now().astimezone().isoformat(),
        "total": len(ordered),
        "category_counts": dict(counts),
        "records": ordered,
    }
    atomic_json(cfg.json, payload)
    cfg.csv.parent.mkdir(parents=True, exist_ok=True)
    with cfg.csv.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(ordered[0]) if ordered else ["序号"])
        writer.writeheader()
        writer.writerows(ordered)
    print(json.dumps({"total": len(ordered), "category_counts": dict(counts)}, ensure_ascii=False, indent=2))
    print(f"json={cfg.json.resolve()}")
    print(f"csv={cfg.csv.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
