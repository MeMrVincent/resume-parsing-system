#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
claude_parse_zh_free.v3.py —— 中文自由格式简历解析器（兜底）。

没有固定模板的中文简历（个人自制 Word/PDF、各类表格、导出页被改过的等），复用推荐报告/日文共用的解析引擎：
日期区间行、“标签：值”块、中文栏目名、履歴式“年 月 事项”行都能认。
识别条件：中文为主（假名很少）。在流水线里它最后运行，并跳过已被其他模板替换的文件，
所以它只处理“其他模板没认出来、或认出来但没能胜过旧 JSON”的原文；是否替换仍按原文逐项比较决定。
入口：detect(text) -> bool，parse(text) -> dict | None。

EN: claude_parse_zh_free.v3.py -- parser for free-format Chinese résumés (fallback).

Chinese résumés without a fixed template (self-made Word/PDF, assorted tables, edited export pages, etc.) reuse the parsing engine shared by recommendation reports/Japanese:
date-range lines, "label: value" blocks, Chinese section names and rirekisho-style "year month item" lines are all recognised.
Detection condition: mainly Chinese (very few kana). It runs last in the pipeline and skips files already replaced by other templates,
so it only handles sources that "no other template recognised, or that were recognised but could not beat the old JSON"; whether to replace is still decided by item-by-item comparison against the source.
Entry points: detect(text) -> bool, parse(text) -> dict | None.

JA: claude_parse_zh_free.v3.py —— 自由形式の中国語の履歴書のパーサー（最終手段）。

決まったテンプレートのない中国語の履歴書（自作の Word/PDF、各種の表、編集されたエクスポートページなど）は、推薦レポート・日本語と共用の解析エンジンを再利用する：
期間の行、「ラベル：値」のブロック、中国語の欄の名前、履歴書式の「年 月 事項」の行をすべて認識できる。
識別の条件：中国語が主（かなが非常に少ない）。パイプラインでは最後に実行し、他のテンプレートですでに置き換えたファイルはスキップする。
そのため「他のテンプレートが認識しなかった、または認識したが旧 JSON に勝てなかった」原文だけを処理する。置き換えるかどうかは引き続き原文との項目ごとの比較で決める。
エントリ：detect(text) -> bool、parse(text) -> dict | None。
"""

import importlib.util
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _load(name, file):
    spec = importlib.util.spec_from_file_location(name, HERE / file)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


J = _load("claude_parse_jp_v3_for_zh_free", "claude_parse_jp.v3.py")
J.jp_segment = lambda lines: lines


def detect(text: str) -> bool:
    kana = len(J.KANA_RE.findall(text))
    han = len(J.HAN_RE.findall(text))
    lat = len(re.findall(r"[A-Za-z]", text))
    return han >= 80 and kana / max(kana + han, 1) < 0.08 and lat / max(lat + han * 2, 1) < 0.8


def parse(text: str):
    if not detect(text):
        return None
    r = J.parse(text)
    if r is None:
        return None
    r["resume"]["resume_languge"] = "zh"
    r["content_lang"] = "zh"
    r["has_zh_part"] = False
    return r


if __name__ == "__main__":
    import json
    import sys
    print(json.dumps(parse(Path(sys.argv[1]).read_text(encoding="utf-8")), ensure_ascii=False, indent=1))
