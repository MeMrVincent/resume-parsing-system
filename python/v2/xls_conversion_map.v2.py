from __future__ import annotations
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1] / "common"))
import rc_config as _rc  # noqa: E402  项目统一配置（python/common/rc_config.py）
# EN: noqa: E402  project-wide configuration (python/common/rc_config.py)
# JA: noqa: E402  プロジェクト共通設定（python/common/rc_config.py）

import json
import os
import sys
from pathlib import Path
import openpyxl

sys.stdout.reconfigure(encoding="utf-8")

PROJECT_ROOT = _rc.project_root()
REPORT_XLSX = PROJECT_ROOT / "32718文件报告.xlsx"
OUTPUT_DIR = PROJECT_ROOT / _rc.dirname("complete-transfered-htmls") / "xls"
MAP_JSON_PATH = OUTPUT_DIR / "xls_conversion_map.json"

GENERATOR_VERSION = "2.4.2"
SCHEMA_VERSION = "resume-dom-v1"


def build_xls_conversion_map() -> list[dict]:
    if not REPORT_XLSX.exists():
        raise FileNotFoundError(f"找不到盘点报告文件: {REPORT_XLSX}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"读取 Excel 盘点报告: {REPORT_XLSX} ..." f" / Reading the Excel inventory report: {REPORT_XLSX} ... / Excel 棚卸しレポートを読み込み中：{REPORT_XLSX} ...")
    wb = openpyxl.load_workbook(str(REPORT_XLSX), read_only=True, data_only=True)
    sheet_name = "Excel表格 (.xls, .xlsx)"
    if sheet_name not in wb.sheetnames:
        raise ValueError(f"工作表中未找到 '{sheet_name}'")

    sheet = wb[sheet_name]
    rows = list(sheet.iter_rows(values_only=True))[1:]  # 跳过表头
    # EN: Skip the table header
    # JA: 表見出しをスキップする
    wb.close()

    print(f"共提取到 {len(rows)} 条 Excel 简历记录" f" / Extracted {len(rows)} Excel résumé records / Excel 履歴書のレコードを {len(rows)} 件抽出しました")

    records: list[dict] = []
    for sequence, row in enumerate(rows, 1):
        idx = int(row[0]) if row[0] is not None else sequence
        filename = str(row[2] or "").strip()
        download_date = str(row[6] or "").strip()
        source_path = str(row[7] or "").strip()

        record = {
            "index": idx,
            "filename": filename,
            "source_path": source_path,
            "download_date": download_date,
            "html_path": "",
            "phone": "",
            "email": "",
            "status": "pending",
            "error_reason": "",
            "converter": "",
            "generator_version": GENERATOR_VERSION,
            "schema_version": SCHEMA_VERSION,
            "resume_count": 0,
            "candidate_keys": [],
            "validation": {},
        }
        records.append(record)

    MAP_JSON_PATH.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✅ 成功生成 Excel 文件路径清单: {MAP_JSON_PATH} (共 {len(records)} 条)" f" / ✅ Excel file path list generated: {MAP_JSON_PATH} ({len(records)} records) / ✅ Excel ファイルのパス一覧を生成しました：{MAP_JSON_PATH}（全 {len(records)} 件）")
    return records


if __name__ == "__main__":
    build_xls_conversion_map()
