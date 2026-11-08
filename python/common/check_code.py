#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
check_code.py —— 静态检查 python/ 下全部代码（common、v2、v3）：只编译和分析，不运行任何脚本。

检查：
  1. 语法：每个 .py 能被解析；
  2. import：指向本项目模块（同目录、common、v2/resume_importer 包）的，目标文件必须存在；
  3. 文件名引用：代码里以字符串引用的 *.py 文件名（按路径加载、subprocess 调用等），必须存在于同目录或 common。
用法（项目根目录）：  python python/common/check_code.py
退出码：0 = 全部通过；1 = 有缺失或语法错误。

EN: check_code.py -- statically checks all code under python/ (common, v2, v3): only compiles and analyses, never runs any script.

Checks:
  1. Syntax: every .py can be parsed;
  2. import: for imports pointing at this project's modules (same directory, common, the v2/resume_importer package), the target file must exist;
  3. File-name references: *.py file names referenced as strings in code (loaded by path, subprocess calls, etc.) must exist in the same directory or in common.
Usage (from the project root):  python python/common/check_code.py
Exit code: 0 = all passed; 1 = missing files or syntax errors.

JA: check_code.py —— python/ 配下の全コード（common、v2、v3）を静的チェックする。コンパイルと解析のみで、スクリプトは一切実行しない。

チェック内容：
  1. 構文：すべての .py がパースできること。
  2. import：本プロジェクトのモジュール（同じディレクトリ、common、v2/resume_importer パッケージ）を指すものは、対象ファイルが存在すること。
  3. ファイル名参照：コード中で文字列として参照される *.py ファイル名（パス指定の読み込み、subprocess 呼び出しなど）が、同じディレクトリか common に存在すること。
使い方（プロジェクトルートで）：  python python/common/check_code.py
終了コード：0 = すべて合格、1 = 欠落ファイルまたは構文エラーあり。
"""
import ast
import re
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parents[1]
FILE_REF = re.compile(r"^[A-Za-z0-9_.\-]+\.py$")
# 仅作为“来源标签”写进输出 JSON 的历史脚本名，不是要加载的文件
# EN: Historical script name written into the output JSON only as a "source label"; not a file to load
# JA: 出力 JSON に「出所ラベル」として書き込むだけの過去のスクリプト名で、読み込むファイルではない
THIRD_PARTY = {"bs4", "lxml", "openpyxl", "xlrd", "pyxlsb", "mammoth", "olefile", "docx", "pptx", "defusedxml", "pypdf", "fitz", "PIL", "pytesseract", "pythoncom", "win32com", "torch", "transformers"}  # 对应 requirements.txt
# EN: Corresponds to requirements.txt
# JA: requirements.txt に対応
PROVENANCE_LABELS = {"__init__.py", "run_chinese_japanese_html_to_json.py", "run_english_html_to_json.py", "run_japanese_html_to_json.py", "run_chinese_english_japanese_html_to_json.py"}


def main() -> int:
    std = set(sys.stdlib_module_names)
    problems = []
    n = 0
    for sub in ("common", "v2", "v3"):
        d = PYDIR / sub
        local = {p.stem for p in d.glob("*.py")} | {p.stem for p in (PYDIR / "common").glob("*.py")}
        local |= {p.name for p in d.iterdir() if p.is_dir() and (p / "__init__.py").exists()}
        for p in sorted(d.rglob("*.py")):
            n += 1
            try:
                tree = ast.parse(p.read_text(encoding="utf-8"), filename=str(p))
            except SyntaxError as e:
                problems.append(f"语法错误 {p.relative_to(PYDIR)}: {e}")
                continue
            for node in ast.walk(tree):
                mods = []
                if isinstance(node, ast.Import):
                    mods = [a.name for a in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                    mods = [node.module]
                for m in mods:
                    top = m.split(".")[0]
                    if top in std or top in local:
                        continue
                    if top not in THIRD_PARTY:
                        problems.append(f"import 找不到 {p.relative_to(PYDIR)}: {m}")
                if isinstance(node, ast.Constant) and isinstance(node.value, str) and FILE_REF.match(node.value) and len(node.value) > 5:
                    name = node.value
                    if name in PROVENANCE_LABELS:
                        continue
                    if not ((p.parent / name).exists() or (PYDIR / "common" / name).exists() or (PYDIR / "v2" / name).exists() or (PYDIR / "v3" / name).exists()):
                        problems.append(f"文件名引用找不到 {p.relative_to(PYDIR)}: {name}")
    print(f"检查 {n} 个 .py 文件，问题 {len(problems)} 个" f" / Checked {n} .py files, {len(problems)} problems / {n} 個の .py ファイルを検査、問題 {len(problems)} 件")
    for x in problems:
        print("  -", x)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
