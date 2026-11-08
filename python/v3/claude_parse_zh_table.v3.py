#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
claude_parse_zh_table.v3.py —— 招聘网站导出的 xls 简历表格解析器。

两种模板（均来自真实样本）：
  智联导出  第 1 张表“下载简历列表”（一行汇总），第 2 张表“1.姓名”是这个人的完整简历（中文栏 + 英文栏）
  51job导出 第 1 张表“UserList”（一行汇总），第 2 张表“1.姓名”是完整简历（中文栏 + 英文栏并排）

只处理“恰好一个人”的文件（有多张明细表的是多人名单，不在这里拆）。
取明细表 → 去掉右侧英文栏 → 规范“2011-12至2012-08——公司:X”这类写法 → 交给日文/推荐报告共用的解析引擎，输出中文 resume。
入口：detect(text) -> bool，parse(text) -> dict | None。

EN: claude_parse_zh_table.v3.py -- parser for xls résumé tables exported from recruitment websites.

Two templates (both from real samples):
  Zhaopin export  sheet 1 "下载简历列表" (downloaded résumé list, a one-row summary); sheet 2 "1.name" is this person's complete résumé (Chinese columns + English columns)
  51job export    sheet 1 "UserList" (a one-row summary); sheet 2 "1.name" is the complete résumé (Chinese and English columns side by side)

Only files with "exactly one person" are handled (files with several detail sheets are lists of many people and are not split here).
Take the detail sheet → remove the English columns on the right → normalise forms like "2011-12至2012-08——公司:X" → hand over to the parsing engine shared with Japanese/recommendation reports, outputting a Chinese resume.
Entry points: detect(text) -> bool, parse(text) -> dict | None.

JA: claude_parse_zh_table.v3.py —— 求人サイトからエクスポートした xls の履歴書の表のパーサー。

2 つのテンプレート（どちらも実際のサンプルから）：
  Zhaopin のエクスポート  第 1 シート「下载简历列表」（ダウンロードした履歴書の一覧。1 行の概要）、第 2 シート「1.氏名」がこの人の完全な履歴書（中国語の欄 + 英語の欄）
  51job のエクスポート    第 1 シート「UserList」（1 行の概要）、第 2 シート「1.氏名」が完全な履歴書（中国語の欄と英語の欄が横に並ぶ）

「ちょうど 1 人」のファイルだけを処理する（明細のシートが複数あるものは複数人の名簿なので、ここでは分割しない）。
明細のシートを取る → 右側の英語の欄を除く →「2011-12至2012-08——公司:X」のような書き方を正規化する → 日本語・推薦レポートと共用の解析エンジンに渡し、中国語の resume を出力する。
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


J = _load("claude_parse_jp_v3_for_zh_table", "claude_parse_jp.v3.py")
J.jp_segment = lambda lines: lines
CJK = re.compile(r"[一-鿿]")
LIST_SHEETS = ("下载简历列表", "UserList")


def sheets_of(text):
    parts = re.split(r"(?m)^### sheet (.*)$", text)
    return [(parts[i].strip(), parts[i + 1]) for i in range(1, len(parts) - 1, 2)]


def detect(text: str) -> bool:
    sh = sheets_of(text)
    if not sh or sh[0][0] not in LIST_SHEETS:
        return False
    return len([s for s in sh[1:] if s[1].strip()]) == 1


def strip_en(text: str) -> str:
    """去掉右侧英文栏：某格之前是空格、这一格没有汉字而有英文 → 从这一格起都是英文栏；其后续行（无汉字）也属于英文栏。

    EN: Remove the English columns on the right: if the cell before is a space and this cell has no Han characters but has English → from this cell on is the English column; the following lines (without Han characters) also belong to the English column.

    JA: 右側の英語の欄を除く：前のセルが空白で、このセルに漢字がなく英語がある → このセル以降は英語の欄。その後の行（漢字なし）も英語の欄に属する。
    """
    out, en = [], False
    for l in text.split("\n"):
        cells = l.split("\t")
        if len(cells) > 1:
            cut = next((i for i in range(1, len(cells)) if cells[i].strip() and not cells[i - 1].strip() and (
                (not CJK.search(cells[i]) and re.search(r"[A-Za-z]{2}", cells[i]))
                or (i >= 3 and not cells[i - 2].strip() and any(c.strip() for c in cells[:i - 2])))), None)
            if cut is not None:
                out.append("\t".join(cells[:cut]).rstrip())
                en = True
                continue
            en = False
            out.append(l)
            continue
        if en and not CJK.search(l):
            continue
        en = False
        out.append(l)
    return "\n".join(out)


def normalize(text: str) -> str:
    t = strip_en(text)
    t = re.sub(r"(\d)\s*——\s*(?:公司\s*[:：])?\s*", r"\1\t", t)          # 2011-12至2012-08——公司:X → 日期\tX
    # EN: 2011-12至2012-08——公司:X → date\tX
    # JA: 2011-12至2012-08——公司:X → 日付\tX
    t = re.sub(r"(?m)^\*{5,}\s*$", "", t)
    out = []
    for l in t.split("\n"):
        cells = [c for c in l.split("\t")]
        head = [c for c in cells if c.strip()]
        # “教育经历\t2007-03至2010-07\t上海海事大学”：栏目名和内容在同一行 → 拆成两行
        # EN: "教育经历\t2007-03至2010-07\t上海海事大学": section name and content on the same line → split into two lines
        # JA: 「教育经历\t2007-03至2010-07\t上海海事大学」：欄の名前と内容が同じ行にある → 2 行に分ける
        if len(head) >= 2 and J.SECTION_RE.match(head[0].strip()) and not J.SECTION_RE.match(head[1].strip()):
            out.append(head[0].strip())
            out.append("\t".join(head[1:]))
            continue
        out.append(l)
    return "\n".join(out)


def parse(text: str):
    sh = [s for s in sheets_of(text)[1:] if s[1].strip()]
    if len(sh) != 1:
        return None
    body = normalize(sh[0][1])
    # 中文栏基本是空的（只填了英文栏）→ 这是英文简历，留给英文模板
    # EN: The Chinese columns are basically empty (only the English columns are filled in) → this is an English résumé; leave it to the English template
    # JA: 中国語の欄がほぼ空（英語の欄だけ記入されている）→ 英語の履歴書なので、英語のテンプレートに任せる
    vals = []
    for l in body.split("\n"):
        l = l.strip()
        if not l or J.SECTION_RE.match(l):
            continue
        if "\t" in l:
            vals.append(l.split("\t", 1)[1])
        elif not re.fullmatch(r"[^:：]{1,12}[:：]?", l):
            vals.append(l)
    values = "\n".join(vals)
    if len(CJK.findall(values)) < 150 and len(re.findall(r"[A-Za-z]", sh[0][1])) > 800:
        return None
    r = J.parse(body)
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
