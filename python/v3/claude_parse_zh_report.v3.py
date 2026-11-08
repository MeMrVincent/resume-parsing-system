#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
claude_parse_zh_report.v3.py —— 中文推荐报告（猎头/人才公司的“推荐报告 / 候选人简历报告 / 人才推荐表”）解析器。

这类文档的结构和日文履歴書解析器处理的是同一套写法：日期区间行、“标签：值”块、栏目标题。
所以直接复用 claude_parse_jp.v3.py 的解析引擎（已含中文栏目名和中文标签），区别只有：
  - 不做“去掉中文部分”的双语切分（这里要的正是中文）；
  - 输出 resume_languge = "zh"；
  - 识别条件是推荐报告特有的字样，且不属于智联 / 51job / 日文模板。
入口：detect(text) -> bool，parse(text) -> dict | None。

EN: claude_parse_zh_report.v3.py -- parser for Chinese recommendation reports (headhunter/talent firms' "推荐报告 / 候选人简历报告 / 人才推荐表" (recommendation report / candidate résumé report / talent recommendation form)).

The structure of these documents uses the same writing conventions as those handled by the Japanese rirekisho parser: date-range lines, "label: value" blocks, section headings.
So it directly reuses the parsing engine of claude_parse_jp.v3.py (which already includes Chinese section names and labels); the only differences are:
  - no bilingual split that "removes the Chinese part" (here the Chinese is exactly what we want);
  - output resume_languge = "zh";
  - the detection condition is wording specific to recommendation reports, and it does not belong to the Zhaopin / 51job / Japanese templates.
Entry points: detect(text) -> bool, parse(text) -> dict | None.

JA: claude_parse_zh_report.v3.py —— 中国語の推薦レポート（ヘッドハンター・人材会社の「推荐报告／候选人简历报告／人才推荐表」（推薦レポート・候補者履歴書レポート・人材推薦表））のパーサー。

この種の文書の構造は、日本語の履歴書パーサーが扱うものと同じ書き方である：期間の行、「ラベル：値」のブロック、欄の見出し。
そのため claude_parse_jp.v3.py の解析エンジン（中国語の欄の名前とラベルを含む）をそのまま再利用し、違いは次の点だけ：
  - 「中国語部分を除く」バイリンガルの分割はしない（ここで必要なのはまさに中国語）。
  - 出力は resume_languge = "zh"。
  - 識別の条件は推薦レポート特有の語句であり、かつ Zhaopin／51job／日本語のテンプレートに属さないこと。
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


J = _load("claude_parse_jp_v3_for_zh_report", "claude_parse_jp.v3.py")
J.jp_segment = lambda lines: lines  # 中文文档不切分
# EN: Chinese documents are not split
# JA: 中国語の文書は分割しない

REPORT_RE = re.compile(r"(推荐理由|顾问评价|顾问意见|推荐报告|候选人推荐|推荐公司|推荐职位|推荐岗位|候选人简历报告|人才推荐|推荐人选|推荐企业)")


def detect(text: str) -> bool:
    if J.CN.detect(text) or J.J5.detect(text) or J.detect(text):
        return False
    return bool(REPORT_RE.search(text[:1500]))


def parse(text: str):
    kana = len(J.KANA_RE.findall(text))
    han = len(J.HAN_RE.findall(text))
    if kana / max(kana + han, 1) >= 0.1:
        return None  # 日文为主的留给日文模板
        # EN: Mainly-Japanese documents are left to the Japanese template
        # JA: 日本語が主のものは日本語のテンプレートに任せる
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
