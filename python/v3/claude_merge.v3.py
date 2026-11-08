#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
claude_merge.v3.py —— V2 / V1 互校合并：以手机号或邮箱认定同一人，一人一份 JSON（单语或多语）。

输入（只读，不修改）：
  --v2-dir  <v2_dir>   主来源
  --v1-dir  <v1_dir>        辅助来源（字段优先级低于 V2）
输出（新建目录，不覆盖）：
  <out-root>\\<run-id>\\formal\\*.json            正式 JSON，一人一份，文件名 姓名_联系方式.json
  <out-root>\\<run-id>\\ledgers\\                 台账（jsonl + csv）
      source_map                每个输入文件的去向（正式 / 无联系方式 / 复核 / 重复副本 / 解析失败）
      no_contact_ledger         无有效手机号和邮箱的输入：JSON 路径、原始文件路径、HTML 路径、是否存在、原因
      field_issue_ledger        字段问题（只记录，不阻断）：字段路径、值、问题类型、来源 JSON、原始文件、HTML
      review_ledger             需人工判断：公共联系方式、姓名不可靠、纯外文待翻译
      conflict_ledger           同一人不同来源的字段冲突及最终取值
      cleaning_ledger           已执行的确定性清洗（去空白/控制字符/占位值/日期格式）
  <out-root>\\<run-id>\\reports\\summary.json

规则（详见 merge.v3.plan.md 第三节）：
  1. 身份键 = 规范化手机号（含国际手机）或有效邮箱，来自每个 JSON 全部语言版本的 base_info；不看文件名；固话不作身份键。
  2. 任一身份键相同即同一人，可传递；姓名/生日等冲突只记录不拆分。
  3. 同一号码/邮箱关联 >= --shared-threshold 个不同有效姓名时视为公共联系方式，不参与合并，相关记录进复核台账。
  4. 字节完全相同的输入只取一份（V2 优先）。
  5. 来源优先级：V2 > V1，其次简历更新日期新者，其次信息完整者。字段逐项取第一个有效非空值；冲突记账。
  6. 同一人所有简历按真实语种分组，同语种合并为一个 resume；有中文时 resumes[0] 为中文。
  7. 顶层快照、raw_text、quality 由最终 resumes 重建。

用法：
  python python\\v3\\claude_merge.v3.py --run-id 20260926-v3.0
  试跑：加 --sample-groups 200

EN: claude_merge.v3.py -- V2 / V1 cross-checked merge: records sharing a mobile number or e-mail are the same person; one JSON per person (single- or multilingual).

Input (read-only, never modified):
  --v2-dir  <v2_dir>   primary source
  --v1-dir  <v1_dir>        secondary source (field priority lower than V2)
Output (new directory, never overwritten):
  <out-root>\\<run-id>\\formal\\*.json            formal JSON, one per person, file name name_contact.json
  <out-root>\\<run-id>\\ledgers\\                 ledgers (jsonl + csv)
      source_map                where each input file went (formal / no contact / review / duplicate copy / parse failure)
      no_contact_ledger         inputs without a valid mobile number or e-mail: JSON path, original file path, HTML path, whether it exists, reason
      field_issue_ledger        field issues (recorded only, not blocking): field path, value, issue type, source JSON, original file, HTML
      review_ledger             needs manual judgement: public contacts, unreliable names, foreign-only awaiting translation
      conflict_ledger           field conflicts between different sources of the same person, and the final value
      cleaning_ledger           deterministic cleaning performed (whitespace / control characters / placeholders / date format)
  <out-root>\\<run-id>\\reports\\summary.json

Rules (see section 3 of merge.v3.plan.md for details):
  1. Identity key = normalised mobile number (including international mobiles) or valid e-mail, from base_info of all language versions of each JSON; file names are ignored; landlines are not identity keys.
  2. Any shared identity key means the same person, transitively; conflicts in name/birthday etc. are only recorded, not split.
  3. A number/e-mail linked to >= --shared-threshold different valid names is treated as a public contact, does not take part in merging, and the related records go to the review ledger.
  4. Byte-identical inputs are taken only once (V2 first).
  5. Source priority: V2 > V1, then the newer résumé update date, then the more complete record. Each field takes the first valid non-empty value; conflicts are logged.
  6. All résumés of the same person are grouped by real language, and each language is merged into one resume; when there is Chinese, resumes[0] is Chinese.
  7. Top-level snapshots, raw_text and quality are rebuilt from the final resumes.

Usage:
  python python\\v3\\claude_merge.v3.py --run-id 20260926-v3.0
  Trial run: add --sample-groups 200

JA: claude_merge.v3.py —— V2 / V1 の相互照合による統合：携帯電話番号かメールで同一人物と判定し、1 人 1 ファイルの JSON（単一言語または多言語）にする。

入力（読み取り専用。変更しない）：
  --v2-dir  <v2_dir>   主ソース
  --v1-dir  <v1_dir>        副ソース（フィールドの優先度は V2 より低い）
出力（新しいディレクトリ。上書きしない）：
  <out-root>\\<run-id>\\formal\\*.json            正式 JSON。1 人 1 ファイルで、ファイル名は 氏名_連絡先.json
  <out-root>\\<run-id>\\ledgers\\                 台帳（jsonl + csv）
      source_map                各入力ファイルの行き先（正式／連絡先なし／レビュー／重複コピー／解析失敗）
      no_contact_ledger         有効な携帯電話番号もメールもない入力：JSON のパス、元ファイルのパス、HTML のパス、存在するか、理由
      field_issue_ledger        フィールドの問題（記録するだけでブロックしない）：フィールドのパス、値、問題の種類、ソースの JSON、元ファイル、HTML
      review_ledger             人手の判断が必要なもの：共用の連絡先、信頼できない氏名、翻訳待ちの外国語のみのもの
      conflict_ledger           同一人物の異なるソース間のフィールドの競合と最終的な値
      cleaning_ledger           実行した確定的なクレンジング（空白・制御文字・プレースホルダー・日付の形式）
  <out-root>\\<run-id>\\reports\\summary.json

ルール（詳細は merge.v3.plan.md の第 3 節）：
  1. 本人の識別キー = 正規化した携帯電話番号（国際携帯を含む）か有効なメール。各 JSON の全言語版の base_info から取り、ファイル名は見ない。固定電話は識別キーにしない。
  2. どれかの識別キーが同じなら同一人物で、推移的に適用する。氏名・生年月日などの食い違いは記録するだけで分割しない。
  3. 同じ番号・メールが --shared-threshold 個以上の異なる有効な氏名に結び付く場合は共用の連絡先とみなし、統合には使わず、関連するレコードはレビューの台帳に入れる。
  4. バイト列が完全に同じ入力は 1 つだけ取る（V2 を優先）。
  5. ソースの優先順位：V2 > V1、次に履歴書の更新日が新しいもの、次に情報がより完全なもの。各フィールドは最初の有効で空でない値を取り、競合は台帳に記録する。
  6. 同一人物のすべての履歴書を実際の言語でグループ化し、同じ言語は 1 つの resume に統合する。中国語があれば resumes[0] を中国語にする。
  7. トップレベルのスナップショット・raw_text・quality は最終的な resumes から作り直す。

使い方：
  python python\\v3\\claude_merge.v3.py --run-id 20260926-v3.0
  試行：--sample-groups 200 を付ける
"""
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1] / "common"))
import rc_config as _rc  # noqa: E402  项目统一配置（python/common/rc_config.py）
# EN: noqa: E402  project-wide configuration (python/common/rc_config.py)
# JA: noqa: E402  プロジェクト共通設定（python/common/rc_config.py）

import argparse
import collections
import copy
import csv
import json
import os
import re
import sys
from datetime import date, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _load(name, filename):
    import importlib.util
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


C = _load("claude_merge_common_v3", "claude_merge_common.v3.py")
K = _load("claude_merge_checks_v3", "claude_merge_checks.v3.py")
NM = _load("claude_merge_normalize_v3", "claude_merge_normalize.v3.py")
MAN = _load("claude_merge_manual_v3", "claude_merge_manual.v3.py")
s = C.s

LANG_ORDER = ["zh", "jp", "en", "de", "kr", "fr", "es"]


# ======================================================================= 扫描
# EN: ======================================================================= Scanning
# JA: ======================================================================= スキャン
def scan_dir(d: Path, version: str):
    files = []
    subdirs = 0
    if not d.is_dir():
        raise SystemExit(f"输入目录不存在：{d}")
    with os.scandir(d) as it:
        for e in it:
            if e.is_dir():
                subdirs += 1
            elif e.name.lower().endswith(".json") and not e.name.startswith("_"):
                files.append(Path(e.path))
    if not files:
        # 输入目录里没有 .json：结果会缺人，直接中止
        # EN: no .json in the input directory: the result would be missing people, abort
        # JA: 入力ディレクトリに .json がない：結果が欠けるため中止する
        raise SystemExit(f"输入目录里没有 .json 文件（{version}）：{d}。输入不完整，已中止。")
    files.sort(key=lambda p: p.name)
    return [(version, p) for p in files], subdirs


def html_path_of(data: dict) -> str:
    src = data.get("source") or {}
    ext = data.get("extraction") or {}
    p = s(src.get("path"))
    if p.lower().endswith((".html", ".htm", ".mht", ".mhtml")):
        return p
    return s(src.get("html_path")) or s(ext.get("html_path")) or ""


# ======================================================================= 清洗与结构规范
# EN: ======================================================================= Cleaning and structural normalisation
# JA: ======================================================================= クレンジングと構造の正規化
def normalize_resume(res: dict, rec_ref: str, cleaning: list):
    """返回规范后的 resume 深拷贝：标准字段、清洗、日期格式。动作写入 cleaning。

    EN: Return a normalised deep copy of the resume: standard fields, cleaning, date format. Actions are written into cleaning.

    JA: 正規化した resume のディープコピーを返す：標準のフィールド、クレンジング、日付の形式。処理内容は cleaning に書き込む。
    """
    out = {"resume_languge": C.resume_label(res) or ""}
    base_in = res.get("base_info") or {}
    base = {}
    for f in C.BASE_FIELDS:
        v, acts = C.clean_value(base_in.get(f, ""))
        v = s(v)
        if f == "age" and v:
            nv = C.normalize_age(v)
            if nv != v:
                acts.append(f"age_normalize:{v}->{nv}")
                v = nv
        if f == "pr" and v:
            nv = C.strip_pr_heading(v)
            if nv != v:
                acts.append("pr_strip_heading")
                v = nv
        if f == "full_name" and v:
            nv = C.strip_name_label(v)
            if nv != v:
                acts.append(f"name_strip_label:{v}->{nv}")
                v = nv
        if f == "birth_date" and v:
            nv = C.format_cn_date(v)
            if nv and nv != v:
                acts.append(f"date_format:{v}->{nv}")
                v = nv
        for a in acts:
            cleaning.append({"source": rec_ref, "field_path": f"base_info.{f}", "action": a})
        base[f] = v
    for extra in sorted(set(base_in) - set(C.BASE_FIELDS)):
        if s(base_in.get(extra)):
            cleaning.append({"source": rec_ref, "field_path": f"base_info.{extra}", "action": f"drop_nonstandard_key:{s(base_in.get(extra))[:200]}"})
    out["base_info"] = base

    for lst in C.LIST_ORDER:
        items_in = res.get(lst) or []
        if lst == "expected_list" and not items_in and isinstance(res.get("expected_info"), dict):
            items_in = [res["expected_info"]]
            cleaning.append({"source": rec_ref, "field_path": "expected_info", "action": "legacy_expected_info_to_expected_list"})
        items = []
        for j, it in enumerate(items_in if isinstance(items_in, list) else []):
            if not isinstance(it, dict):
                v = s(it)
                if v:
                    cleaning.append({"source": rec_ref, "field_path": f"{lst}[{j}]", "action": f"drop_non_object_item:{v[:200]}"})
                continue
            alias = C.ALIASES.get(lst, {})
            src_item = {alias.get(k, k): v for k, v in it.items()}
            new = {}
            for f in C.LIST_FIELDS[lst]:
                raw = src_item.get(f, "")
                if f == "sequence_no":
                    new[f] = raw if isinstance(raw, int) else 0
                    continue
                v, acts = C.clean_value(raw if isinstance(raw, str) else ("" if raw is None else str(raw)))
                v = s(v)
                if f in C.DATE_FIELDS.get(lst, []) and v:
                    if f in ("position_resigned", "school_end_ym", "end_ym") and C.is_present_word(v):
                        acts.append(f"present_to_empty:{v}")
                        v = ""
                        if lst == "work_experiences" and not s(src_item.get("status")):
                            src_item["status"] = "在职"
                    else:
                        nv = C.format_cn_date(v)
                        if nv and nv != v:
                            acts.append(f"date_format:{v}->{nv}")
                            v = nv
                for a in acts:
                    cleaning.append({"source": rec_ref, "field_path": f"{lst}[{j}].{f}", "action": a})
                new[f] = v
            if lst == "work_experiences" and not new["status"] and s(src_item.get("status")):
                new["status"] = s(src_item.get("status"))
            for extra in sorted(set(src_item) - set(C.LIST_FIELDS[lst])):
                if s(src_item.get(extra)) and extra != "raw_text":
                    cleaning.append({"source": rec_ref, "field_path": f"{lst}[{j}].{extra}", "action": f"drop_nonstandard_key:{s(src_item.get(extra))[:200]}"})
            if any(s(v) for k, v in new.items() if k not in ("sequence_no", "fingerprint", "employment_type", "status", "expected_employment_type")):
                items.append(new)
            else:
                cleaning.append({"source": rec_ref, "field_path": f"{lst}[{j}]", "action": "drop_empty_item"})
        out[lst] = items
    for legacy in ("keywords",):
        if res.get(legacy):
            cleaning.append({"source": rec_ref, "field_path": legacy, "action": f"drop_legacy_key:{json.dumps(res.get(legacy), ensure_ascii=False)[:300]}"})
    return out


# ======================================================================= 记录
# EN: ======================================================================= Records
# JA: ======================================================================= レコード
class Record:
    __slots__ = ("idx", "version", "path", "sha", "dup_of", "dups", "data", "error", "resumes", "langs", "mobiles",
                 "emails", "landlines", "bad_contacts", "names", "updated", "downloaded", "original_path", "html_path",
                 "completeness", "status", "group", "cleaning", "dates", "rt_mobiles", "rt_emails", "loaded")

    def __init__(self, idx, version, path):
        self.idx, self.version, self.path = idx, version, path
        self.sha = ""
        self.dup_of = None
        self.dups = []
        self.data = None
        self.error = ""
        self.resumes = []
        self.langs = []
        self.mobiles, self.emails, self.landlines, self.bad_contacts = set(), set(), set(), []
        self.names = []
        self.updated = self.downloaded = ""
        self.original_path = self.html_path = ""
        self.completeness = 0
        self.status = ""
        self.group = None
        self.cleaning = []
        self.dates = {}
        self.rt_mobiles, self.rt_emails = [], []
        self.loaded = False

    @property
    def ref(self):
        return f"{self.version}:{self.path.name}"

    def priority(self):
        garbled = 1 if sum(C.resume_garble_score(r) for r in self.resumes) >= 3 else 0
        return (0 if self.version == "v2" else 1, garbled, _neg(self.updated), -self.completeness, str(self.path).lower())


def _neg(datestr):
    # 日期新的排前面：转成可比较的负序字符串
    # EN: Newer dates first: convert to comparable negative-order strings
    # JA: 新しい日付を先にする：比較可能な逆順の文字列に変換する
    return "".join(chr(0x10FFFF - ord(ch)) for ch in (datestr or "0000"))


SOURCE_TEXTS = None  # <repair-dir>/source_texts.json：{"originals": {原件sha256: {original_path, method, text}}, "inputs": {输入JSON字节sha256: 原件sha256}}
# EN: <repair-dir>/source_texts.json: {"originals": {original sha256: {original_path, method, text}}, "inputs": {input JSON byte sha256: original sha256}}
# JA: <repair-dir>/source_texts.json：{"originals": {元ファイルの sha256: {original_path, method, text}}, "inputs": {入力 JSON のバイト列の sha256: 元ファイルの sha256}}
REPAIR_DIR = None  # --repair-dir：回源修复后的 JSON 副本（<dir>/v2/、<dir>/v1/，文件名同原 JSON）
# EN: --repair-dir: JSON copies repaired against the sources (<dir>/v2/, <dir>/v1/, file names identical to the original JSON)
# JA: --repair-dir：原文に基づいて修復した JSON のコピー（<dir>/v2/、<dir>/v1/。ファイル名は元の JSON と同じ）


def load_record(rec: Record):
    raw = rec.path.read_bytes()
    rec.sha = C.sha256_bytes(raw)  # 字节去重仍按原文件
    # EN: Byte-level dedup is still done on the original files
    # JA: バイト単位の重複排除は引き続き元のファイルで行う
    if REPAIR_DIR is not None:
        rp = REPAIR_DIR / rec.version / rec.path.name
        if rp.is_file():
            raw = rp.read_bytes()
            rec.cleaning.append({"source": rec.ref, "field_path": "*", "action": f"source_repair_overlay:{rp}"})
    try:
        data = json.loads(raw.decode("utf-8-sig"))
    except Exception as ex:  # noqa: BLE001
        rec.error = f"{type(ex).__name__}: {ex}"
        return
    if not isinstance(data, dict) or not isinstance((data.get("structured_data") or {}).get("resumes"), list):
        rec.error = "schema: 缺少 structured_data.resumes"
        return
    rec.data = data
    rec.loaded = True


def analyze_record(rec: Record):
    d = rec.data
    src = d.get("source") or {}
    rec.original_path = s(src.get("original_path"))
    rec.html_path = html_path_of(d)
    dates = d.get("dates") or {}
    rec.updated = C.norm_datetime(dates.get("resume_updated_date"))
    rec.downloaded = C.norm_datetime(dates.get("resume_download_date"))
    resumes_in = [r for r in d["structured_data"]["resumes"] if isinstance(r, dict)]
    rec.resumes = [normalize_resume(r, rec.ref, rec.cleaning) for r in resumes_in]
    rec.langs = [C.detect_language(r)[0] for r in rec.resumes]
    # 模板解析器（claude_reparse）按中文平台版式解析出的中文 resume：以版式为准，工作描述里夹日文不改变语种
    # EN: Chinese resumes parsed by the template parser (claude_reparse) by Chinese platform layout: the layout is authoritative, and Japanese mixed into job descriptions does not change the language
    # JA: テンプレートのパーサー（claude_reparse）が中国のプラットフォームのレイアウトで解析した中国語の resume：レイアウトを正とし、職務説明に日本語が混じっていても言語は変えない
    if (d.get("source_repair") or {}).get("claude_reparse_v3"):
        rec.langs = ["zh" if C.resume_label(r) == "zh" else lg for r, lg in zip(rec.resumes, rec.langs)]
    bases = [r["base_info"] for r in rec.resumes] + [d["structured_data"].get("base_info") or {}]
    for b in bases:
        for field, kind, val, raw in C.contacts_from_base(b):
            if kind in ("mobile", "intl_mobile"):
                rec.mobiles.add(val)
            elif kind == "email":
                rec.emails.add(val)
            elif kind == "landline":
                rec.landlines.add(val)
            elif kind in ("invalid", "masked"):
                rec.bad_contacts.append(f"{field}:{kind}:{raw}")
    for r, lang in zip(rec.resumes, rec.langs):
        n = s(r["base_info"].get("full_name"))
        if n:
            q, kind = C.name_quality(n)
            rec.names.append((n, q, kind, lang))
    rec.completeness = sum(1 for r in rec.resumes for v in r["base_info"].values() if v) + \
        sum(len(r[lst]) * 3 for r in rec.resumes for lst in C.LIST_ORDER)
    rec.dates = dict(d.get("dates") or {})
    if not rec.mobiles and not rec.emails:
        rec.rt_mobiles, rec.rt_emails = C.contacts_in_text(d.get("raw_text", ""))
    rec.data = None  # 释放原始 JSON，只保留规范化后的 resumes，控制内存
    # EN: Release the original JSON and keep only the normalised resumes, to control memory
    # JA: 元の JSON を解放し、正規化した resumes だけを残してメモリを抑える


# ======================================================================= 身份
# EN: ======================================================================= Identity
# JA: ======================================================================= 本人の識別
class UnionFind:
    def __init__(self):
        self.p = {}

    def find(self, x):
        self.p.setdefault(x, x)
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            if ra > rb:
                ra, rb = rb, ra
            self.p[rb] = ra


VARIANTS = set()


def build_variants(records):
    """从数据本身学繁简/日文新字体的对应字：同一记录里不同语种的同长度姓名，逐字不同的字对；出现 ≥2 次才采信。

    EN: Learn traditional/simplified/Japanese shinjitai character correspondences from the data itself: in the same record, same-length names in different languages give character pairs that differ position by position; trust them only if they occur ≥2 times.

    JA: 繁体字・簡体字・日本の新字体の対応する字をデータ自体から学ぶ：同じレコード内で異なる言語の同じ長さの氏名について、1 文字ずつ異なる字の組を取り、2 回以上現れたものだけを採用する。
    """
    cnt = collections.Counter()
    for r in records:
        ns = sorted({n for n, q, kind, _ in r.names if q == "valid" and kind == "cn"})
        for i, x in enumerate(ns):
            for y in ns[i + 1:]:
                if len(x) == len(y):
                    for a_, b_ in zip(x, y):
                        if a_ != b_:
                            cnt[frozenset((a_, b_))] += 1
    VARIANTS.clear()
    VARIANTS.update(k for k, v in cnt.items() if v >= 2)


def variant_names(x, y):
    return len(x) == len(y) and all(a_ == b_ or frozenset((a_, b_)) in VARIANTS for a_, b_ in zip(x, y))


def collapse_variants(names):
    """繁简/日文字形不同的同一姓名只算一个。

    EN: The same name in different traditional/simplified/Japanese glyph forms counts as one.

    JA: 繁体字・簡体字・日本の字体で字形が異なる同じ氏名は 1 つとして数える。
    """
    out = []
    for n in sorted(names):
        if not any(n == m or variant_names(n, m) for m in out):
            out.append(n)
    return out


NAME_LINKED = {}  # record idx → 按姓名+公司/学校并入的依据
# EN: record idx → grounds for joining by name + company/school
# JA: record idx → 氏名 + 会社・学校で統合した根拠


def person_key(n: str) -> str:
    """姓名比较键：中文转简体；英文不分大小写和姓名顺序。

    EN: Name comparison key: Chinese converted to simplified; English case-insensitive and independent of name order.

    JA: 氏名の比較キー：中国語は簡体字に変換し、英語は大文字小文字と姓名の順序を区別しない。
    """
    n = s(n)
    if re.search(r"[一-鿿]", n):
        return C.name_key(C.to_simplified_name(n))
    return " ".join(sorted(re.findall(r"[a-z]+", n.lower())))


def record_entities(r):
    comps, schools = set(), set()
    for res in r.resumes:
        for w in res.get("work_experiences") or []:
            e = C.norm_entity(w.get("company_name"))
            if len(e) >= 4:
                comps.add(e)
        for ed in res.get("education_list") or []:
            e = C.norm_entity(ed.get("school_name"))
            if len(e) >= 4:
                schools.add(e)
    return comps, schools


def record_birth_year(r):
    for res in r.resumes:
        b = res.get("base_info") or {}
        m = re.match(r"((?:19|20)\d{2})", s(b.get("birth_year")) or s(b.get("birth_date")))
        if m:
            return m.group(1)
    return ""


def sanitize_linked(r):
    """按姓名并入的记录只带入干净的内容：字段检查判为高级别问题的条目整条不带入，基本信息里的问题字段清空。

    EN: Records joined by name bring in only clean content: entries judged by the field checks to have high-severity issues are not brought in at all, and problematic fields in basic info are cleared.

    JA: 氏名で統合したレコードはきれいな内容だけを持ち込む：フィールドのチェックで重大な問題と判定された項目はまるごと持ち込まず、基本情報の問題のあるフィールドは空にする。
    """
    for i, res in enumerate(r.resumes):
        ry = int(r.updated[:4]) if r.updated[:4].isdigit() else None
        bad_items, bad_base = set(), set()
        for iss in K.check_resume("r", res, ry, r.langs[i] if i < len(r.langs) else "zh"):
            if iss["severity"] != "high":
                continue
            m = re.match(r"r\.(\w+)\[(\d+)\]", iss["field_path"])
            if m:
                bad_items.add((m.group(1), int(m.group(2))))
            else:
                mb = re.match(r"r\.base_info\.(\w+)$", iss["field_path"])
                if mb:
                    bad_base.add(mb.group(1))
        for lst, k in sorted(bad_items, key=lambda x: (x[0], -x[1])):
            if lst in res and k < len(res[lst]):
                del res[lst][k]
                r.cleaning.append({"source": r.ref, "field_path": f"resumes[{i}].{lst}[{k}]", "action": "name_linked_drop_high_issue_item"})
        for f in bad_base:
            if f in (res.get("base_info") or {}) and f != "full_name":
                res["base_info"][f] = ""
                r.cleaning.append({"source": r.ref, "field_path": f"resumes[{i}].base_info.{f}", "action": "name_linked_drop_high_issue_field"})


def link_no_contact(groups, no_contact):
    """没有有效联系方式的记录：姓名相同、且至少有一个相同的公司或学校、并且只对得上一个候选人时，并入该候选人。
    只按学校对上的，要求姓名 ≥3 个汉字（或英文名 ≥2 个词）或有 2 所以上相同学校，避免“张伟 + 同济大学”这类重名。
    出生年份或性别矛盾的不并。对得上多个候选人的不并，写入复核台账。返回 (剩下的无联系方式记录, 复核行)。

    EN: Records without valid contact details: join a candidate when the name is the same, at least one company or school is the same, and only one candidate matches.
    For matches by school only, require a name of ≥3 Chinese characters (or an English name of ≥2 words) or 2+ schools in common, to avoid homonyms like "张伟 + 同济大学".
    Do not join on a contradiction in birth year or gender. Do not join when several candidates match; write to the review ledger. Returns (remaining no-contact records, review rows).

    JA: 有効な連絡先のないレコード：氏名が同じで、少なくとも 1 つの会社か学校が同じで、かつ候補者が 1 人だけに対応する場合は、その候補者に統合する。
    学校だけで一致した場合は、氏名が漢字 3 文字以上（または英語名が 2 語以上）か、同じ学校が 2 校以上あることを求め、「张伟 + 同济大学」のような同姓同名を避ける。
    生年や性別が矛盾する場合は統合しない。複数の候補者に対応する場合も統合せず、レビューの台帳に書く。戻り値：(残った連絡先なしのレコード, レビューの行)。
    """
    index = collections.defaultdict(set)
    ginfo = {}
    for root, members in groups.items():
        keys, comps, schools, years, genders = set(), set(), set(), set(), set()
        for m in members:
            for n, q, kind, _ in m.names:
                if q == "valid":
                    keys.add(person_key(n))
            c_, s_ = record_entities(m)
            comps |= c_
            schools |= s_
            y = record_birth_year(m)
            if y:
                years.add(y)
            for res in m.resumes:
                g = s((res.get("base_info") or {}).get("gender"))
                if g in ("男", "女"):
                    genders.add(g)
        ginfo[root] = (comps, schools, years, genders)
        for k in keys:
            if k:
                index[k].add(root)
    rest, review = [], []
    for r in no_contact:
        keys = {person_key(n) for n, q, kind, _ in r.names if q == "valid"} - {""}
        comps, schools = record_entities(r)
        y = record_birth_year(r)
        genders = {s((res.get("base_info") or {}).get("gender")) for res in r.resumes} & {"男", "女"}
        hits = []
        for root in sorted({g for k in keys for g in index.get(k, ())}, key=str):
            gc, gs, gy, gg = ginfo[root]
            co, sc = comps & gc, schools & gs
            long_name = any((len(k) >= 3 and re.search(r"[一-鿿]", k)) or len(k.split()) >= 2 for k in keys)
            if not (co or (sc and (long_name or len(sc) >= 2))):
                continue
            if y and gy and y not in gy:
                continue
            if genders and gg and not (genders & gg):
                continue
            hits.append((root, sorted(co), sorted(sc)))
        if len(hits) == 1:
            root, co, sc = hits[0]
            sanitize_linked(r)
            groups[root].append(r)
            NAME_LINKED[r.idx] = "姓名 " + "/".join(sorted({n for n, q, *_ in r.names if q == "valid"})) + \
                (" + 公司 " + "、".join(co[:2]) if co else "") + (" + 学校 " + "、".join(sc[:2]) if sc else "")
        else:
            if len(hits) > 1:
                review.append({"reason": "name_link_ambiguous", "input_json": str(r.path), "original_path": r.original_path,
                               "detail": f"姓名与公司/学校对得上 {len(hits)} 个候选人，未并入"})
            rest.append(r)
    return rest, review


def shared_keys(records, threshold):
    names_by_key = collections.defaultdict(lambda: {"cn": set(), "en": set()})
    for r in records:
        keys = [("m", x) for x in r.mobiles] + [("e", x) for x in r.emails]
        for n, q, kind, _ in r.names:
            if q != "valid":
                continue
            for k in keys:
                names_by_key[k]["cn" if kind == "cn" else "en"].add(C.name_key(n))
    shared = {}
    for k, v in names_by_key.items():
        cnt = len(collapse_variants(v["cn"])) if v["cn"] else len(v["en"])
        if cnt >= threshold:
            shared[k] = sorted(v["cn"] or v["en"])
    return shared


# ======================================================================= 合并
# EN: ======================================================================= Merging
# JA: ======================================================================= 統合
def fingerprint(lst, it):
    """同一条目的匹配键。工作/教育以开始年月为主键（同一人同月开始两段经历极少见），缺日期时退回实体名。

    EN: Matching key for the same entry. Work/education use the start year-month as the main key (one person rarely starts two experiences in the same month); without a date, fall back to the entity name.

    JA: 同じ項目の照合キー。職歴・学歴は開始年月を主なキーとする（同じ人が同じ月に 2 つの経歴を始めることはまれ）。日付がなければ主体名に戻す。
    """
    n = C.norm_entity
    if lst == "work_experiences":
        st = C.ym_key(it.get("position_start"))
        if len(st) == 6:
            return "t:" + st
        a = n(it.get("company_name")) or n(it.get("position"))
        return ("c:" + a + "|" + st) if a else ""
    if lst == "education_list":
        st = C.ym_key(it.get("school_start_ym"))
        if len(st) == 6:
            return "t:" + st
        en = C.ym_key(it.get("school_end_ym"))
        a = n(it.get("school_name"))
        return ("s:" + a + "|" + st + "|" + en) if a else ("e:" + en if len(en) == 6 else "")
    if lst == "project_list":
        a = n(it.get("project_name"))
        return a + "|" + C.ym_key(it.get("start_ym")) if a else ""
    if lst == "training_list":
        a = n(it.get("training_name")) or n(it.get("organization_name"))
        return a + "|" + C.ym_key(it.get("start_ym")) if a else ""
    if lst == "certificate_list":
        return n(it.get("certificate_name"))
    if lst == "language_list":
        return n(it.get("language_name"))
    if lst == "skills_list":
        return n(it.get("skill_name"))
    if lst == "expected_list":
        a = n(it.get("expected_position")) + "|" + n(it.get("expected_city"))
        return a if a != "|" else ""
    if lst == "communication_list":
        return C.norm_text(it.get("communicate_time")) + "|" + C.norm_text(it.get("communicate_content"))[:60]
    return ""


def content_key(lst, it):
    return lst + "#" + "|".join(C.norm_text(it.get(f)) for f in C.LIST_FIELDS[lst] if f not in ("sequence_no", "fingerprint"))


LONG_TEXT = {"position_responsibilities", "position_achievements", "description", "responsibilities", "communicate_content", "pr", "resigned_reason"}


def pick_value(cands, field):
    """cands: [(order, si, value)]。按 (质量惩罚, 来源顺序) 选；长文本字段优先来源顺序，其次更长者。

    EN: cands: [(order, si, value)]. Choose by (quality penalty, source order); long-text fields prefer the source order, then the longer one.

    JA: cands: [(order, si, value)]。(品質の減点, ソースの順序) で選ぶ。長文のフィールドはソースの順序を優先し、次に長い方。
    """
    cands = [c for c in cands if s(c[2])]
    if not cands:
        return None, []
    if field in LONG_TEXT:
        ranked = sorted(cands, key=lambda c: (C.value_penalty(c[2], field) >= 8, c[0]))
    else:
        ranked = sorted(cands, key=lambda c: (C.value_penalty(c[2], field), c[0]))
    best = ranked[0]
    others = [c for c in ranked[1:] if C.norm_text(c[2]) != C.norm_text(best[2])]
    return best, others


def merge_bucket(entries, lang, conflicts, gid):
    """entries: [(src_index, resume)]，已按来源优先级排序。字段逐项择优，返回 (resume, prov)。

    EN: entries: [(src_index, resume)], already sorted by source priority. Choose the best value field by field and return (resume, prov).

    JA: entries: [(src_index, resume)]。ソースの優先順位で並べ替え済み。フィールドごとに最良の値を選び、(resume, prov) を返す。
    """
    base, prov_base = {}, {}
    for f in C.BASE_FIELDS:
        if f in ("phone", "email"):
            base[f] = ""
            prov_base[f] = None
            continue
        best, others = pick_value([(o, si, s(r["base_info"].get(f))) for o, (si, r) in enumerate(entries)], f)
        base[f] = s(best[2]) if best else ""
        prov_base[f] = best[1] if best else None
        if best and f not in LONG_TEXT:
            for o in others:
                conflicts.append({"group_id": gid, "lang": lang, "field_path": f"base_info.{f}", "chosen": best[2],
                                  "chosen_source": best[1], "other": o[2], "other_source": o[1]})
    out = {"resume_languge": lang, "base_info": base}
    prov_lists = {}
    for lst in C.LIST_ORDER:
        clusters, index, seen_ck = [], {}, set()
        for o, (si, r) in enumerate(entries):
            for it in r[lst]:
                ck = content_key(lst, it)
                if ck in seen_ck:
                    continue
                seen_ck.add(ck)
                fp = fingerprint(lst, it)
                if fp and fp in index:
                    clusters[index[fp]].append((o, si, it))
                else:
                    clusters.append([(o, si, it)])
                    if fp:
                        index[fp] = len(clusters) - 1
        if lst in ("work_experiences", "education_list"):
            ent = "company_name" if lst == "work_experiences" else "school_name"
            dated = {}
            for k, cl in enumerate(clusters):
                if fingerprint(lst, cl[0][2]).startswith("t:"):
                    for _, _, it in cl:
                        e = C.norm_entity(it.get(ent))
                        if e:
                            dated.setdefault(e, []).append(k)
            for k, cl in enumerate(clusters):
                if not cl or fingerprint(lst, cl[0][2]).startswith("t:"):
                    continue
                e = C.norm_entity(cl[0][2].get(ent))
                targets = sorted(set(dated.get(e, [])))
                if len(targets) == 1:  # 只有唯一匹配时才并入，避免把两段同公司经历混在一起
                # EN: Join only on a unique match, so two experiences at the same company are not mixed together
                # JA: 一意にマッチした場合だけ統合し、同じ会社での 2 つの経歴を混ぜないようにする
                    clusters[targets[0]].extend(cl)
                    clusters[k] = []
            clusters = [cl for cl in clusters if cl]
        merged, prov = [], []
        for k, cl in enumerate(clusters):
            item, srcs = {}, []
            for f in C.LIST_FIELDS[lst]:
                if f in ("sequence_no", "fingerprint"):
                    item[f] = cl[0][2].get(f, 0 if f == "sequence_no" else "")
                    continue
                best, others = pick_value([(o, si, s(it.get(f))) for o, si, it in cl], f)
                item[f] = s(best[2]) if best else ""
                if best and best[1] not in srcs:
                    srcs.append(best[1])
                if best and f not in LONG_TEXT:
                    for ot in others:
                        conflicts.append({"group_id": gid, "lang": lang, "field_path": f"{lst}[#{k}].{f}", "chosen": best[2],
                                          "chosen_source": best[1], "other": ot[2], "other_source": ot[1]})
            if lst == "work_experiences" and item.get("position_resigned") and item.get("status") == "在职":
                item["status"] = "离职"
            merged.append(item)
            prov.append(srcs or [cl[0][1]])
        date_field = {"work_experiences": "position_start", "education_list": "school_start_ym",
                      "project_list": "start_ym", "training_list": "start_ym"}.get(lst)
        if date_field:
            order = sorted(range(len(merged)), key=lambda i: (0 if C.ym_key(merged[i].get(date_field)) else 1,
                                                                _neg(C.ym_key(merged[i].get(date_field))), i))
            merged = [merged[i] for i in order]
            prov = [prov[i] for i in order]
        if lst in ("project_list", "training_list"):
            for i, it in enumerate(merged, 1):
                it["sequence_no"] = i
        out[lst] = merged
        prov_lists[lst] = prov
    return out, {"base": prov_base, "lists": prov_lists}


def choose_name(members):
    """返回 (中文规范名, 英文名, 来源说明)。

    EN: Returns (canonical Chinese name, English name, source note).

    JA: 戻り値：(中国語の正規の氏名, 英語名, 出所の説明)。
    """
    score_cn, score_en, first_seen = collections.Counter(), collections.Counter(), {}
    for rank, m in enumerate(members):
        w = 3 if m.version == "v2" else 1
        for n, q, kind, lang in m.names:
            if q != "valid":
                continue
            key = (kind, n)
            first_seen.setdefault(key, rank)
            (score_cn if kind == "cn" else score_en)[n] += w
    def best(counter, kind):
        if not counter:
            return ""
        return sorted(counter, key=lambda n: (-counter[n], first_seen[(kind, n)], n))[0]
    # 中文名按简体形计票（張志 / 张志 算同一个名字），再取该名字里票数最高的原写法
    # EN: Chinese names are voted on by their simplified form (張志 / 张志 count as the same name), then the original spelling with the most votes within that name is taken
    # JA: 中国語名は簡体字の形で票を数え（張志／张志 は同じ名前とみなす）、その名前の中で票数の最も多い元の表記を採用する
    by_simp = collections.Counter()
    for n, v in score_cn.items():
        by_simp[C.to_simplified_name(n)] += v
    cn = ""
    if by_simp:
        first_simp = {}
        for (kind, n), rank in first_seen.items():
            if kind == "cn":
                k = C.to_simplified_name(n)
                first_simp[k] = min(first_simp.get(k, rank), rank)
        key = sorted(by_simp, key=lambda k: (-by_simp[k], first_simp[k], k))[0]
        cn = best(collections.Counter({n: v for n, v in score_cn.items() if C.to_simplified_name(n) == key}), "cn")
    return cn, best(score_en, "en")


def choose_contact(members, attr, shared):
    cnt, first = collections.Counter(), {}
    kind = "m" if attr == "mobiles" else "e"
    for rank, m in enumerate(members):
        for v in getattr(m, attr):
            if (kind, v) in shared:
                continue
            cnt[v] += 3 if m.version == "v2" else 1
            first.setdefault(v, rank)
    if not cnt:
        return ""
    return sorted(cnt, key=lambda v: (-cnt[v], first[v], v))[0]


def build_group(gid, members, stamp, shared, ctx):
    members = sorted(members, key=lambda m: m.priority())
    conflicts = ctx["conflicts"]
    buckets = collections.OrderedDict()
    for si, m in enumerate(members):
        for r, lang in zip(m.resumes, m.langs):
            if r["resume_languge"] and r["resume_languge"] != lang:
                ctx["issues"].append(_issue_row(None, m, f"resumes[{m.resumes.index(r)}].resume_languge",
                                                r["resume_languge"], "language_label_mismatch", "low", f"内容判定为 {lang}"))
            buckets.setdefault(lang, []).append((si, r))
    langs = sorted(buckets, key=lambda l: (LANG_ORDER.index(l) if l in LANG_ORDER else 99, l))
    cn_name, en_name = choose_name(members)
    if "zh" in langs and cn_name:  # 有中文简历的人，规范名用简体；只有外文简历的保持原写法，留给翻译
    # EN: For people with a Chinese résumé the canonical name is in simplified characters; people with only foreign résumés keep the original spelling, left for translation
    # JA: 中国語の履歴書がある人は正規の氏名を簡体字にし、外国語の履歴書しかない人は元の表記のままにして翻訳に任せる
        simp = C.to_simplified_name(cn_name)
        if simp != cn_name:
            ctx["cleaning"].append({"source": f"group:{gid}", "field_path": "merge_info.canonical_name",
                                    "action": f"simplified_name:{cn_name}->{simp}"})
            cn_name = simp
    canonical = cn_name or en_name
    name_status = "valid" if canonical else "unreliable"
    phone = choose_contact(members, "mobiles", shared)
    email = choose_contact(members, "emails", shared)
    resumes, provs = [], []
    for lang in langs:
        res, prov = merge_bucket(buckets[lang], lang, conflicts, gid)
        b = res["base_info"]
        want = ""
        if lang == "zh":
            want = cn_name or (b["full_name"] if C.name_quality(b["full_name"])[0] == "valid" else "") or en_name
        elif C.name_quality(b["full_name"])[0] != "valid":
            want = (en_name or cn_name) if lang in ("en", "de", "fr", "es") else (cn_name or en_name)
        if want and want != b["full_name"]:
            ctx["cleaning"].append({"source": f"group:{gid}", "field_path": f"resumes[{lang}].base_info.full_name",
                                    "action": f"canonical_name:{b['full_name']}->{want}"})
            b["full_name"] = want
        # 联系方式：桶内有效值优先，没有则用本组主联系方式
        # EN: Contact details: valid values within the bucket first; if none, use the group's primary contact
        # JA: 連絡先：バケット内の有効な値を優先し、なければこのグループの主な連絡先を使う
        bm = [C.classify_phone(p)[1] for si, r in buckets[lang] for p in C.split_contact_values(r["base_info"].get("phone"))
              if C.classify_phone(p)[0] in ("mobile", "intl_mobile") and ("m", C.classify_phone(p)[1]) not in shared]
        be = [C.classify_email(e)[1] for si, r in buckets[lang] for e in C.split_contact_values(r["base_info"].get("email"))
              if C.classify_email(e)[0] == "email" and ("e", C.classify_email(e)[1]) not in shared]
        b["phone"] = phone if (lang == "zh" or not bm) else bm[0]
        b["email"] = email if (lang == "zh" or not be) else be[0]
        if not phone and bm:
            b["phone"] = bm[0]
        if not email and be:
            b["email"] = be[0]
        resumes.append(res)
        provs.append(prov)
    # 字段检查
    # EN: Field checks
    # JA: フィールドのチェック
    upd = max((m.updated for m in members), default="")
    ref_year = int(upd[:4]) if upd[:4].isdigit() else None
    # 字段归位与清理（放错字段的值移回、标签/栏目名/纯标点清掉），逐条记入 cleaning_ledger
    # EN: Field placement and cleaning (values in the wrong field are moved back; labels / section names / pure punctuation are cleared), each recorded in cleaning_ledger
    # JA: フィールドの再配置とクレンジング（誤ったフィールドの値を戻し、ラベル・欄の名前・句読点だけのものを除く）。1 件ずつ cleaning_ledger に記録する
    NM.normalize_resumes(resumes, ctx["cleaning"], f"group:{gid}", provs)
    man = ctx.get("manual")
    manual_name = ""
    # 没有中文版的人：外文版复制到 resumes[0] 并换成中文译文（translations.json），先于人工决定应用
    # EN: People without a Chinese version: copy the foreign version into resumes[0] and replace it with the Chinese translation (translations.json), applied before manual decisions
    # JA: 中国語版がない人：外国語版を resumes[0] にコピーして中国語訳（translations.json）に置き換える。人手の判断より先に適用する
    translated_from = man.apply_translation(gid, resumes, provs, ctx["cleaning"]) if man is not None else ""
    if translated_from:
        langs.insert(0, "zh")
        if cn_name:
            cn_name = C.to_simplified_name(cn_name)
        b0 = resumes[0]["base_info"]
        want = cn_name or en_name
        if want and b0.get("full_name") != want:
            ctx["cleaning"].append({"source": f"group:{gid}", "field_path": "resumes[0].base_info.full_name",
                                    "action": f"canonical_name:{b0.get('full_name')}->{want}"})
            b0["full_name"] = want
    # 按原文逐条复核后的人工决定（manual_decisions.json），逐条记入 cleaning_ledger
    # EN: Manual decisions made after item-by-item review against the source (manual_decisions.json), each recorded in cleaning_ledger
    # JA: 原文と 1 件ずつ照合した後の人手の判断（manual_decisions.json）。1 件ずつ cleaning_ledger に記録する
    if man is not None:
        man.apply_items(gid, resumes, provs, ctx["cleaning"])
        manual_name = man.apply_name(gid, resumes, ctx["cleaning"])
    if manual_name:
        ctx["cleaning"].append({"source": f"group:{gid}", "field_path": "merge_info.canonical_name",
                                "action": f"manual:canonical_name:{cn_name or en_name or '待确认姓名'}->{manual_name}"})
        if re.search(r"[一-鿿]", manual_name):
            cn_name = manual_name
        else:
            cn_name, en_name = "", manual_name
        name_status = "valid"
    # 多语言对齐（alignments.json）；ALIGN_EXPORT 环境变量指向目录时，把对齐前的各语言版本导出，供逐份对齐使用
    # EN: Multilingual alignment (alignments.json); when the ALIGN_EXPORT environment variable points to a directory, export the pre-alignment language versions for one-by-one alignment
    # JA: 多言語の対応付け（alignments.json）。環境変数 ALIGN_EXPORT がディレクトリを指す場合は、対応付け前の各言語版を出力し、1 件ずつの対応付けに使う
    if man is not None and len(resumes) > 1:
        exp = os.environ.get("ALIGN_EXPORT")
        if exp:
            tg, _nb = man.base_gaps(resumes)
            Path(exp).mkdir(parents=True, exist_ok=True)
            (Path(exp) / f"{gid}.json").write_text(json.dumps({
                "group_id": gid, "output_json": f"{C.safe_filename_part(cn_name or en_name or '待确认姓名')}_{C.safe_filename_part(phone or email)}.json",
                "src_sha256": {s(r.get('resume_languge')): man.resume_sha(r) for r in resumes},
                "resumes": resumes, "base_text_gaps": tg}, ensure_ascii=False), encoding="utf-8")
        man.apply_alignment(gid, resumes, provs, ctx["cleaning"])
    if man is not None:
        man.apply_date_fixes(gid, resumes, ctx["cleaning"])
    # EN: manual date corrections from re-reading the source (after alignment)
    # JA: 元ファイルを読み直した人手の日付修正（整列の後）
    unify_dates(resumes, ctx["cleaning"], gid)
    # EN: unify dates across languages, Chinese wins (see unify_dates)
    # JA: 言語間で日付を統一する。中国語を優先（unify_dates 参照）
    snaps = C.build_snapshots(resumes)
    raw_text, raw_mode = None, "assembled"
    if SOURCE_TEXTS is not None and len(resumes) == 1 and not translated_from:
        ors = {SOURCE_TEXTS["inputs"].get(m.sha) for m in members}
        if len(ors) == 1 and None not in ors and SOURCE_TEXTS["originals"].get(next(iter(ors))):
            raw_text, raw_mode = C.clean_source_text(SOURCE_TEXTS["originals"][next(iter(ors))]["text"]), "source"
    if raw_text is None:
        raw_text = C.build_raw_text_assembled(resumes)
        if len(resumes) == 1 and not translated_from:
            ctx["cleaning"].append({"source": f"group:{gid}", "field_path": "raw_text", "action": "raw_text:单来源但没有原文文本，改用字段拼装"})
    display_name = cn_name or en_name or "待确认姓名"
    contact = phone or email
    fname = f"{C.safe_filename_part(display_name)}_{C.safe_filename_part(contact)}.json"
    sources = []
    for si, m in enumerate(members):
        sources.append({
            "index": si, "version": m.version, "json_path": str(m.path), "sha256": m.sha,
            "duplicate_paths": [str(d.path) for d in m.dups], "original_path": m.original_path, "html_path": m.html_path,
            "resume_updated_date": m.updated, "languages": m.langs,
        })
    latest = sorted(members, key=lambda m: m.updated or "", reverse=True)[0]
    ld = latest.dates
    created = sorted(s(m.dates.get("sys_created_date")) for m in members if s(m.dates.get("sys_created_date")))
    other_phones = sorted(x for x in set().union(*[m.mobiles for m in members]) - {phone} if ("m", x) not in shared)
    other_emails = sorted(x for x in set().union(*[m.emails for m in members]) - {email} if ("e", x) not in shared)
    doc = {
        "schema_version": "resume-merge-v3.0",
        "record_id": f"merge-v3-{gid}",
        "source": {
            "original_path": members[0].original_path,
            "html_path": members[0].html_path,
            "source_count": len(members),
            "source_files": sources,
        },
        "dates": {
            "resume_updated_date": latest.updated,
            "resume_download_date": latest.downloaded,
            "resume_updated_date_source": s(ld.get("resume_updated_date_source")),
            "resume_download_date_source": s(ld.get("resume_download_date_source")),
            "sys_created_date": created[0] if created else stamp,
            "sys_updated_date": stamp,
        },
        "extraction": {"merger": "claude_merge.v3.py", "rule_version": C.RULE_VERSION},
        "classification": {"document_type": "resume", "reason": "按手机号/邮箱合并的候选人"},
        "structured_data": {**snaps, "resumes": resumes},
        "raw_text": raw_text,
        "quality": {
            "full_name": display_name,
            "has_work": bool(resumes[0]["work_experiences"]) if resumes else False,
            "work_count": len(resumes[0]["work_experiences"]) if resumes else 0,
            "has_education": bool(resumes[0]["education_list"]) if resumes else False,
            "education_count": len(resumes[0]["education_list"]) if resumes else 0,
            "languages": langs,
            "raw_text_length": len(raw_text),
        },
        "merge_info": {
            "group_id": gid,
            "rule_version": C.RULE_VERSION,
            "output_filename": fname,
            "name_status": name_status,
            "canonical_name": display_name,
            "english_name": en_name,
            "primary_phone": phone,
            "primary_email": email,
            "other_phones": other_phones,
            "other_emails": other_emails,
            "landlines": sorted(set().union(*[m.landlines for m in members])),
            "shared_contacts_ignored": sorted({f"{k[0]}:{k[1]}" for m in members for k in
                                              ([("m", x) for x in m.mobiles] + [("e", x) for x in m.emails]) if k in shared}),
            "needs_translation": "zh" not in langs,
            "v2_count": sum(1 for m in members if m.version == "v2"),
            "v1_count": sum(1 for m in members if m.version == "v1"),
            "language_sources": {lang: sorted({si for si, _ in buckets[lang if lang in buckets else translated_from]}) for lang in langs},
            "translated_from": translated_from,
            "name_note": (("招聘平台隐去了全名，原文只有“" + manual_name + "”，按原文沿用") if manual_name and man is not None
                          and (man.names.get(gid) or {}).get("masked") else ""),
            "conflict_count": 0,
            "field_issue_count": 0,
            "name_linked_sources": [{"json_path": str(m.path), "evidence": NAME_LINKED[m.idx]} for m in members if m.idx in NAME_LINKED],
        },
    }
    # 字段问题（带来源追溯）
    # EN: Field issues (with source traceability)
    # JA: フィールドの問題（出所を追跡できる形で）
    issues = []
    for i, (res, prov) in enumerate(zip(resumes, provs)):
        for iss in K.check_resume(f"resumes[{i}]", res, ref_year, res["resume_languge"]):
            if man is not None:
                man.adjust_issue(gid, lambda fp: _obj_at(resumes, fp), iss)
            si = _prov_for(iss["field_path"], prov)
            m = members[si] if si is not None else members[0]
            issues.append(_issue_row(fname, m, iss["field_path"], iss["value"], iss["issue_type"], iss["severity"], iss.get("note", ""), gid))
    for iss in K.check_cross_language(resumes):
        if man is not None:
            man.adjust_issue(gid, lambda fp: _obj_at(resumes, fp), iss)
        issues.append(_issue_row(fname, members[0], iss["field_path"], iss["value"], iss["issue_type"], iss["severity"], iss.get("note", ""), gid))
    high = sum(1 for x in issues if x["severity"] == "high")
    if "zh" not in langs:
        category = "pending_translation"
    elif high or name_status != "valid":
        category = "needs_fix"
    else:
        category = "formal"
    doc["merge_info"]["output_category"] = category
    doc["merge_info"]["high_issue_count"] = high
    return doc, issues


def _obj_at(resumes, path):
    """字段路径 → 所在的条目对象（整份简历 / base_info / 列表条目）。

    EN: Field path → the entry object that contains it (whole résumé / base_info / list entry).

    JA: フィールドのパス → それを含む項目のオブジェクト（履歴書全体／base_info／リストの項目）。
    """
    m = re.match(r"resumes\[(\d+)\](?:\.(\w+))?(?:\[(\d+)\])?", path)
    if not m or int(m.group(1)) >= len(resumes):
        return None
    res = resumes[int(m.group(1))]
    if not m.group(2):
        return res
    if m.group(2) == "base_info":
        return res.get("base_info")
    if m.group(3) is None:
        return res
    items = res.get(m.group(2)) or []
    k = int(m.group(3))
    return items[k] if k < len(items) else None


def _prov_for(path, prov):
    import re as _re
    m = _re.match(r"resumes\[\d+\]\.base_info\.(\w+)", path)
    if m:
        return prov["base"].get(m.group(1))
    m = _re.match(r"resumes\[\d+\]\.(\w+)\[(\d+)\]", path)
    if m and m.group(1) in prov["lists"]:
        lst = prov["lists"][m.group(1)]
        k = int(m.group(2))
        return lst[k][0] if k < len(lst) else None
    return None


def _issue_row(output_json, rec, path, value, itype, severity, note="", gid=""):
    return {
        "output_json": output_json or "", "group_id": gid, "field_path": path, "value": value, "issue_type": itype,
        "severity": severity, "note": note, "source_json": str(rec.path), "source_version": rec.version,
        "original_path": rec.original_path, "html_path": rec.html_path,
    }


# ======================================================================= 输出
# EN: ======================================================================= Output
# JA: ======================================================================= 出力
def write_json_atomic(path: Path, obj):
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    json.loads(tmp.read_text(encoding="utf-8"))
    os.replace(tmp, path)


def write_ledger(ledger_dir: Path, name: str, rows, columns):
    with open(ledger_dir / f"{name}.jsonl", "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    with open(ledger_dir / f"{name}.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(columns)
        for r in rows:
            w.writerow([r.get(c, "") if not isinstance(r.get(c), (list, dict)) else json.dumps(r.get(c), ensure_ascii=False) for c in columns])


_STD_DATE = re.compile(r"^(\d{4})年(\d{2})月(\d{2})日$")
_YEAR_ONLY = re.compile(r"^(\d{4})年?$")
_TIME_TAIL = re.compile(r"^(.*?\d{1,2}日?)\s+\d{1,2}:\d{2}(?::\d{2})?$")
DATE_UNIFY_MAX_MONTHS = 24  # 中文与其他语言相差超过该月数则视为可能错配，跳过并记录
# EN: DATE_UNIFY_MAX_MONTHS = 24  more than this many months apart between Chinese and another language is treated as a likely mis-pairing: skip and record
# JA: DATE_UNIFY_MAX_MONTHS = 24  中国語と他言語でこの月数を超えて差があれば誤対応の疑いとしてスキップし記録する

_EN_MONTHS = {m: i for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july", "august",
                                         "september", "october", "november", "december"], 1)}
_EN_LONG_DATE = re.compile(r"^\s*([A-Za-z]+)\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+((?:19|20)\d{2})\s*$")


def _unify_birth(resumes, cleaning, gid):
    """出生日期：英文长写法（November 2, 1965）先规范；各语言之间以中文为准。
    同年同月时，日为 01 多半是只写了年月而补的 01，此时取有具体日的那个（不丢信息）；
    年份不同则不动、记 date_unify_skip。出生年份字段随之保持一致。

    EN: Birth date: normalise English long forms (November 2, 1965) first; across languages Chinese wins.
    In the same year and month, a day of 01 is usually padding for a year-month-only value, so the one with a real day is used
    (no information lost); a different year is left alone and logged as date_unify_skip. The birth-year field follows.
    JA: 生年月日：英語の長い書式（November 2, 1965）をまず正規化し、言語間では中国語を優先する。
    同じ年月で日が 01 の場合は年月のみの値を補った可能性が高いため、具体的な日がある方を採用する（情報を失わない）。
    年が異なる場合は変更せず date_unify_skip として記録する。出生年フィールドも揃える。
    """
    ref = f"group:{gid}"
    for ri, r in enumerate(resumes):
        b = r.get("base_info") or {}
        v = s(b.get("birth_date"))
        m = _EN_LONG_DATE.match(v) if v else None
        if m and m.group(1).lower() in _EN_MONTHS:
            nv = f"{int(m.group(3)):04d}年{_EN_MONTHS[m.group(1).lower()]:02d}月{int(m.group(2)):02d}日"
            cleaning.append({"source": ref, "field_path": f"resumes[{ri}].base_info.birth_date", "action": f"date_unify_format:{v}->{nv}"})
            b["birth_date"] = nv
    if len(resumes) < 2:
        return
    zb = resumes[0].get("base_info") or {}
    for ri, o in enumerate(resumes[1:], 1):
        ob = o.get("base_info") or {}
        u, v = s(zb.get("birth_date")), s(ob.get("birth_date"))
        if u == v:
            continue
        mu, mv = _STD_DATE.match(u), _STD_DATE.match(v)
        if not u and v:
            zb["birth_date"] = v
            cleaning.append({"source": ref, "field_path": "resumes[0].base_info.birth_date", "action": f"date_unify_fill_zh:->{v}"})
        elif u and not v:
            ob["birth_date"] = u
            cleaning.append({"source": ref, "field_path": f"resumes[{ri}].base_info.birth_date", "action": f"date_unify_fill_other:->{u}"})
        elif mu and mv and mu.group(1) != mv.group(1):
            cleaning.append({"source": ref, "field_path": f"resumes[{ri}].base_info.birth_date", "action": f"date_unify_skip:zh={u}|other={v}"})
            continue
        elif mu and mv and mu.group(2) == mv.group(2) and mu.group(3) == "01" and mv.group(3) != "01":
            zb["birth_date"] = v
            cleaning.append({"source": ref, "field_path": "resumes[0].base_info.birth_date", "action": f"date_unify_fill_zh:{u}->{v}"})
        else:
            ob["birth_date"] = u
            cleaning.append({"source": ref, "field_path": f"resumes[{ri}].base_info.birth_date", "action": f"date_unify_override:{v}->{u}"})
        by = s(zb.get("birth_date"))[:4]
        for rr in resumes:
            bb = rr.get("base_info") or {}
            if by.isdigit() and "birth_year" in bb and s(bb.get("birth_year")) not in ("", by) and s(bb.get("birth_date")) == s(zb.get("birth_date")):
                bb["birth_year"] = by


def unify_dates(resumes, cleaning, gid):
    """日期统一：先把各语言日期规范为 YYYY年MM月DD日（去掉时分秒，不臆造月份）；
    再对列表长度相等的已对齐行，以中文（resumes[0]）为准：中文空则取其他语言、
    其他语言空或不同则取中文；相差超过 DATE_UNIFY_MAX_MONTHS 个月或无法比较时也以中文为准，记为 date_unify_override_far，供抽查错配的行。

    EN: Date unification. First normalise every language's dates to YYYY年MM月DD日 (strip time-of-day, never invent a month).
    Then, for aligned rows whose lists have equal length, Chinese (resumes[0]) wins: a blank Chinese date is filled from the
    other language; a blank or different date in the other language is overwritten by the Chinese one. Differences above
    DATE_UNIFY_MAX_MONTHS months, or values that cannot be compared, are also overwritten by the Chinese date and logged as
    date_unify_override_far so mis-paired rows can be spot-checked.
    JA: 日付の統一。まず各言語の日付を YYYY年MM月DD日 に正規化する（時刻は除去、月は捏造しない）。
    次に、リスト長が等しい整列済みの行について中国語（resumes[0]）を優先する。中国語が空なら他言語から補い、
    他言語が空または異なる場合は中国語で上書きする。DATE_UNIFY_MAX_MONTHS か月を超える差、または比較できない値も中国語で
    上書きし、誤対応の行を抽出できるよう date_unify_override_far として記録する。
    """
    for ri, r in enumerate(resumes):
        for lst, fs in C.DATE_FIELDS.items():
            for i, it in enumerate(r.get(lst) or []):
                for f in fs:
                    v = s(it.get(f))
                    if not v or C.is_present_word(v):
                        continue
                    m = _TIME_TAIL.match(v)
                    nv = C.format_cn_date(m.group(1) if m else v)
                    if nv and nv != v:
                        cleaning.append({"source": f"group:{gid}", "field_path": f"resumes[{ri}].{lst}[{i}].{f}",
                                         "action": f"date_unify_format:{v}->{nv}"})
                        it[f] = nv
    if len(resumes) < 2:
        return
    zh = resumes[0]
    _unify_birth(resumes, cleaning, gid)
    _unify_birth(resumes, cleaning, gid)  # 第二遍：中文被其他语言补全后，前面已比较过的语言要再对齐一次
    # EN: second pass: after Chinese is filled from another language, languages compared earlier must be aligned again
    # JA: 2 回目：中国語が他言語から補われた後、先に比較した言語をもう一度揃える必要がある

    def months(v):
        m = _STD_DATE.match(v or "")
        return int(m.group(1)) * 12 + int(m.group(2)) if m else None

    skipped = set()  # 已因“开始晚于结束”整行恢复的行，第二遍不再重试
    # EN: rows already restored because "start later than end" are not retried in the second pass
    # JA: 「開始が終了より後」で行全体を戻した行は、2 周目では再試行しない
    # 跑两遍：中文版的空值可能在处理第二种外语时才补上，第一种外语需要再对齐一次
    # EN: run two passes: a blank zh value may only be filled while handling the second foreign language, so the first one must be re-aligned
    # JA: 2 周する：中国語版の空欄が 2 番目の外国語を処理する時に初めて埋まることがあり、1 番目の外国語を再度揃える必要がある
    for _pass in range(2):
      for ri, o in enumerate(resumes[1:], 1):
        for lst, fs in C.DATE_FIELDS.items():
            a, b = zh.get(lst) or [], o.get(lst) or []
            if not a or len(a) != len(b):
                continue
            for i, (x, y) in enumerate(zip(a, b)):
                if (ri, lst, i) in skipped:
                    continue
                x0, y0 = dict(x), dict(y)
                log = []
                for f in fs:
                    u, v = s(x.get(f)), s(y.get(f))
                    if u == v:
                        continue
                    ref = f"group:{gid}"
                    if not u:
                        x[f] = v
                        log.append({"source": ref, "field_path": f"resumes[0].{lst}[{i}].{f}", "action": f"date_unify_fill_zh:->{v}"})
                    elif not v:
                        y[f] = u
                        log.append({"source": ref, "field_path": f"resumes[{ri}].{lst}[{i}].{f}", "action": f"date_unify_fill_other:->{u}"})
                    else:
                        mu, mv = months(u), months(v)
                        yu, yv = _YEAR_ONLY.match(u), _YEAR_ONLY.match(v)
                        if re.sub(r"学年$", "", u) == v:
                            # “2014-2015学年”与“2014-2015”：只是写法不同
                            # EN: "2014-2015学年" vs "2014-2015": only the wording differs
                            # JA: 「2014-2015学年」と「2014-2015」は表記の違いだけ
                            y[f] = u
                            log.append({"source": ref, "field_path": f"resumes[{ri}].{lst}[{i}].{f}", "action": f"date_unify_override:{v}->{u}"})
                        elif yv and mu is not None and yv.group(1) == u[:4]:
                            # 其他语言只有年份、中文是同一年的完整日期：取中文
                            # EN: the other language has only a year and Chinese has a full date in that year: take the Chinese one
                            # JA: 他言語が年のみで中国語が同じ年の完全な日付なら中国語を採用する
                            y[f] = u
                            log.append({"source": ref, "field_path": f"resumes[{ri}].{lst}[{i}].{f}", "action": f"date_unify_override:{v}->{u}"})
                        elif yu and mv is not None and yu.group(1) == v[:4]:
                            # 中文只有年份、其他语言是同一年的完整日期：取更完整的那个
                            # EN: Chinese has only a year and the other language a full date in that year: take the more complete one
                            # JA: 中国語が年のみで他言語が同じ年の完全な日付なら、より完全な方を採用する
                            x[f] = v
                            log.append({"source": ref, "field_path": f"resumes[0].{lst}[{i}].{f}", "action": f"date_unify_fill_zh:{u}->{v}"})
                        else:
                            # 相差超过 DATE_UNIFY_MAX_MONTHS 个月（或无法比较）也以中文为准，但记为 override_far，便于抽查错配的行
                            # EN: more than DATE_UNIFY_MAX_MONTHS apart (or not comparable): Chinese still wins, logged as override_far so mis-paired rows can be spot-checked
                            # JA: DATE_UNIFY_MAX_MONTHS か月を超える差（または比較不能）でも中国語を優先するが、誤対応の行を抽出できるよう override_far として記録する
                            far = mu is None or mv is None or abs(mu - mv) > DATE_UNIFY_MAX_MONTHS
                            y[f] = u
                            log.append({"source": ref, "field_path": f"resumes[{ri}].{lst}[{i}].{f}",
                                        "action": f"date_unify_override{'_far' if far else ''}:{v}->{u}"})
                if len(fs) == 2:
                    def rev(it0, it1):
                        ma, mb = months(s(it1.get(fs[0]))), months(s(it1.get(fs[1])))
                        ra = months(s(it0.get(fs[0]))), months(s(it0.get(fs[1])))
                        return (ma is not None and mb is not None and ma > mb
                                and not (ra[0] is not None and ra[1] is not None and ra[0] > ra[1]))
                    if rev(x0, x) or rev(y0, y):
                        # 统一后出现开始晚于结束：说明补填来源不可信，整行恢复，交人工看
                        # EN: start later than end after unification: the filled-in source is untrustworthy, restore the whole row for manual review
                        # JA: 統一後に開始が終了より後になった場合は補填元が信頼できないため、行全体を元に戻して人手確認に回す
                        x.update(x0)
                        y.update(y0)
                        skipped.add((ri, lst, i))
                        log = [{"source": f"group:{gid}", "field_path": f"resumes[{ri}].{lst}[{i}]",
                                "action": "date_unify_skip:统一后开始晚于结束，整行不改"}]
                cleaning.extend(log)

def main():
    try:
        sys.stdout.reconfigure(errors="replace")
    except Exception:  # noqa: BLE001
        pass
    ap = argparse.ArgumentParser(description="merge v3：按手机号/邮箱合并 V2/V1 简历 JSON")
    ap.add_argument("--v2-dir", type=Path, default=_rc.path("v2_dir"))
    ap.add_argument("--v1-dir", type=Path, default=_rc.path("v1_dir"))
    ap.add_argument("--out-root", type=Path, default=_rc.path("merge_out_dir"))
    ap.add_argument("--run-id", default=f"{date.today():%Y%m%d}-v3.0")
    ap.add_argument("--stamp", default="", help="sys_updated_date，默认取 run-id 日期 00:00:00+09:00，保证重跑幂等")
    ap.add_argument("--shared-threshold", type=int, default=3)
    ap.add_argument("--sample-groups", type=int, default=0, help="试跑：只输出均匀抽取的 N 个候选人")
    ap.add_argument("--overwrite", action="store_true")
    ap.add_argument("--repair-dir", type=Path, default=None, help="回源修复副本目录（claude_source_repair.v3.py 输出）")
    a = ap.parse_args()
    global REPAIR_DIR
    REPAIR_DIR = a.repair_dir
    global SOURCE_TEXTS
    _stp = Path(a.repair_dir) / "source_texts.json" if a.repair_dir else None
    SOURCE_TEXTS = json.loads(_stp.read_text(encoding="utf-8")) if _stp and _stp.exists() else None

    run_dir = a.out_root / a.run_id
    formal_dir, ledger_dir, report_dir = run_dir / "formal", run_dir / "ledgers", run_dir / "reports"
    cat_dirs = {c: run_dir / c for c in ("formal", "needs_fix", "pending_translation")}
    if run_dir.exists() and any(run_dir.iterdir()) and not a.overwrite:
        raise SystemExit(f"输出目录已存在且非空：{run_dir}（换一个 --run-id，或加 --overwrite）")
    for d in (ledger_dir, report_dir, *cat_dirs.values()):
        d.mkdir(parents=True, exist_ok=True)
    if a.overwrite:
        for d in cat_dirs.values():
            for p in d.glob("*.json"):
                p.unlink()
    stamp = a.stamp or (f"{a.run_id[:4]}-{a.run_id[4:6]}-{a.run_id[6:8]}T00:00:00+09:00" if a.run_id[:8].isdigit() else datetime.now().astimezone().isoformat(timespec="seconds"))
    t0 = datetime.now()

    # ---- 扫描与读取
    # EN: ---- Scanning and reading
    # JA: ---- スキャンと読み込み
    v2_files, v2_sub = scan_dir(a.v2_dir, "v2")
    v1_files, v1_sub = scan_dir(a.v1_dir, "v1")
    records = [Record(i, v, p) for i, (v, p) in enumerate(v2_files + v1_files)]
    print(f"扫描：V2 {len(v2_files)} 个，V1 {len(v1_files)} 个（子目录 V2 {v2_sub} / V1 {v1_sub} 个，不递归）")
    by_sha = {}
    for n, r in enumerate(records, 1):
        load_record(r)
        if r.sha in by_sha:
            r.dup_of = by_sha[r.sha]
            by_sha[r.sha].dups.append(r)
            r.data = None
        elif r.loaded:
            by_sha[r.sha] = r
            analyze_record(r)
        else:
            by_sha[r.sha] = r
        if n % 3000 == 0:
            print(f"  读取并分析 {n}/{len(records)}")
    canon = [r for r in records if r.loaded and r.dup_of is None]
    # 人工按原文确认某个输入文件“不是简历”（如招聘启事、访谈记录）：从身份识别之前就拿掉，登记到 excluded_ledger
    # EN: An input file confirmed manually against the source as "not a résumé" (e.g. a job posting, an interview record): removed before identity matching and registered in excluded_ledger
    # JA: 原文を見て人手で「履歴書ではない」と確認した入力ファイル（求人広告・面談記録など）：本人の識別の前に取り除き、excluded_ledger に登録する
    MANUAL = MAN.Manual(a.repair_dir, C)
    excluded_rec_rows, excluded_rec_map = [], []
    if MANUAL.excluded_records:
        keep = []
        for r in canon:
            xd = MANUAL.excluded_records.get(r.sha)
            if not xd:
                keep.append(r)
                continue
            names_x = sorted({n2 for n2, *_ in r.names})
            for rec in [r] + r.dups:
                excluded_rec_map.append({"input_json": str(rec.path), "version": rec.version, "sha256": r.sha,
                                   "status": "excluded_non_resume" if rec is r else "duplicate", "duplicate_of": "" if rec is r else str(r.path),
                                   "output_json": "", "group_id": "", "name": "、".join(names_x),
                                   "contacts": ";".join(sorted(r.mobiles | r.emails)), "languages": ",".join(r.langs),
                                   "original_path": rec.original_path or r.original_path, "note": xd["reason"]})
            excluded_rec_rows.append({"group_id": "", "would_be_output": "", "reason": xd["reason"], "evidence": xd.get("evidence", ""),
                                      "review_id": xd["review_id"], "input_json": str(r.path), "version": r.version,
                                      "duplicate_paths": ";".join(str(d.path) for d in r.dups),
                                      "contacts": ";".join(sorted(r.mobiles | r.emails)), "original_path": r.original_path or "",
                                      "html_path": r.html_path or "", "content_sha256": r.sha})
        canon = keep

    # ---- 身份
    # EN: ---- Identity
    # JA: ---- 本人の識別
    build_variants(canon)
    shared = shared_keys(canon, a.shared_threshold)
    uf = UnionFind()
    keyed, no_contact, shared_only = [], [], []
    for r in canon:
        keys = [("m", x) for x in sorted(r.mobiles)] + [("e", x) for x in sorted(r.emails)]
        good = [k for k in keys if k not in shared]
        if good:
            keyed.append(r)
            for k in good:
                uf.union(("r", r.idx), k)
        elif keys:
            shared_only.append(r)
        else:
            no_contact.append(r)
    groups = collections.defaultdict(list)
    for r in keyed:
        groups[uf.find(("r", r.idx))].append(r)
    n_nc = len(no_contact)
    no_contact, link_review = link_no_contact(groups, no_contact)
    print(f"无联系方式记录按姓名+公司/学校并入候选人：{n_nc - len(no_contact)} 个")
    gid_groups = {}
    for members in groups.values():
        gid = C.sha256_text("|".join(sorted(m.sha for m in members)))[:16]
        gid_groups[gid] = members
    gids = sorted(gid_groups)
    if a.sample_groups:
        step = max(1, len(gids) // a.sample_groups)
        # 保证多来源、多语言样本入选：先取来源最多的 20 组，再均匀抽样
        # EN: Make sure multi-source, multilingual samples are selected: first take the 20 groups with the most sources, then sample evenly
        # JA: 複数の出所・多言語のサンプルが選ばれるようにする：まず出所の最も多い 20 グループを取り、その後均等に抽出する
        big = sorted(gids, key=lambda g: (-len(gid_groups[g]), g))[:20]
        gids = sorted(set(big) | set(gids[::step][: a.sample_groups]))
    print(f"身份：可合并记录 {len(keyed)}，候选人 {len(gid_groups)}，无联系方式 {len(no_contact)}，仅公共联系方式 {len(shared_only)}，公共联系方式 {len(shared)} 个")

    # ---- 构建与写出
    # EN: ---- Building and writing
    # JA: ---- 組み立てと書き出し
    ctx = {"conflicts": [], "issues": [], "cleaning": [], "manual": MANUAL}
    if ctx["manual"].loaded:
        print(f"人工决定：{ctx['manual'].loaded} 条（{a.repair_dir}\\manual_decisions.json）")
    source_map, review = list(excluded_rec_map), list(link_review)
    written = {}
    excluded_rows = []
    for n, gid in enumerate(gids, 1):
        members = gid_groups[gid]
        xd = ctx["manual"].excluded.get(gid)
        if xd:
            # 人工按原文确认“不是简历”（招聘启事、通讯录、班车表等）：不输出候选人 JSON，登记到 excluded_ledger
            # EN: Confirmed manually against the source as "not a résumé" (job postings, address books, shuttle-bus timetables, etc.): no candidate JSON is output; registered in excluded_ledger
            # JA: 原文を見て人手で「履歴書ではない」と確認したもの（求人広告・連絡先一覧・送迎バスの時刻表など）：候補者 JSON は出力せず、excluded_ledger に登録する
            names_x = sorted({n2 for m in members for n2, *_ in m.names})
            for m in members:
                for rec in [m] + m.dups:
                    source_map.append({"input_json": str(rec.path), "version": rec.version, "sha256": m.sha,
                                       "status": "excluded_non_resume" if rec is m else "duplicate", "duplicate_of": "" if rec is m else str(m.path),
                                       "output_json": "", "group_id": gid, "name": "、".join(names_x),
                                       "contacts": ";".join(sorted(m.mobiles | m.emails)), "languages": ",".join(m.langs),
                                       "original_path": rec.original_path or m.original_path, "note": xd["reason"]})
                excluded_rows.append({"group_id": gid, "would_be_output": xd["output_json"], "reason": xd["reason"], "evidence": xd.get("evidence", ""),
                                      "review_id": xd["review_id"], "input_json": str(m.path), "version": m.version,
                                      "duplicate_paths": ";".join(str(d.path) for d in m.dups),
                                      "contacts": ";".join(sorted(m.mobiles | m.emails)), "original_path": m.original_path or "",
                                      "html_path": m.html_path or "", "content_sha256": m.sha})
            continue
        before_c = len(ctx["conflicts"])
        doc, issues = build_group(gid, members, stamp, shared, ctx)
        fname = doc["merge_info"]["output_filename"]
        if fname.lower() in written:
            other_gid = written[fname.lower()]
            fname = fname[:-5] + f"_冲突_{gid}.json"
            doc["merge_info"]["output_filename"] = fname
            review.append({"group_id": gid, "output_json": fname, "reason": "filename_collision", "detail": f"与 group {other_gid} 同名同联系方式"})
        opath = f'{doc["merge_info"]["output_category"]}/{fname}'
        for c in ctx["conflicts"][before_c:]:
            c["output_json"] = opath
            c["chosen_source"] = str(members_sorted_path(members, c["chosen_source"]))
            c["other_source"] = str(members_sorted_path(members, c["other_source"]))
        for i in issues:
            i["output_json"] = opath
        doc["merge_info"]["conflict_count"] = len(ctx["conflicts"]) - before_c
        doc["merge_info"]["field_issue_count"] = len(issues)
        ctx["issues"].extend(issues)
        mi = doc["merge_info"]
        category = mi["output_category"]
        write_json_atomic(cat_dirs[category] / fname, doc)
        written[fname.lower()] = gid
        if mi["name_status"] != "valid":
            review.append({"group_id": gid, "output_json": f"{category}/{fname}", "reason": "name_unreliable",
                           "detail": "; ".join(sorted({n for m in members for n, *_ in m.names}))})
        cn_names = sorted({n for m in members for n, q, kind, _ in m.names if q == "valid" and kind == "cn" and len(n) >= 2})
        clash = [(x, y) for i, x in enumerate(cn_names) for y in cn_names[i + 1:] if not (set(x) & set(y)) and not variant_names(x, y)
                 and C.to_simplified_name(x) != C.to_simplified_name(y)]
        if clash:
            # 同一联系方式连起来的记录，中文姓名一个字都不重合（繁简体写法至少有一个字相同）→ 可能是别人的联系方式，人工核对
            # EN: Records linked by the same contact whose Chinese names share not a single character (with at least one character in common across traditional/simplified spellings) → possibly someone else's contact; check manually
            # JA: 同じ連絡先でつながったレコードの中国語名に共通の文字が 1 つもない（繁体字・簡体字の表記で少なくとも 1 文字は共通するはず）→ 他人の連絡先の可能性があるため人手で確認する
            review.append({"group_id": gid, "output_json": f"{category}/{fname}", "reason": "name_conflict",
                           "detail": "; ".join(cn_names) + " | 连接用的联系方式: " + ";".join(sorted(
                               k for k, v in collections.Counter(x for m in members for x in (m.mobiles | m.emails)).items() if v >= 2)[:5])})
        if mi["needs_translation"]:
            review.append({"group_id": gid, "output_json": f"{category}/{fname}", "reason": "needs_translation",
                           "detail": ",".join(doc["quality"]["languages"])})
        for m in members:
            for rec in [m] + m.dups:
                source_map.append({"input_json": str(rec.path), "version": rec.version, "sha256": m.sha,
                                   "status": category if rec is m else "duplicate", "duplicate_of": "" if rec is m else str(m.path),
                                   "output_json": f"{category}/{fname}", "group_id": gid, "name": mi["canonical_name"],
                                   "contacts": ";".join(sorted(m.mobiles | m.emails)), "languages": ",".join(m.langs),
                                   "original_path": rec.original_path or m.original_path})
        if n % 1000 == 0:
            print(f"  写出 {n}/{len(gids)}")
    sampled = set(gids)

    # ---- 未输出记录
    # EN: ---- Records not output
    # JA: ---- 出力しなかったレコード
    if a.sample_groups:
        for gid, members in gid_groups.items():
            if gid in sampled:
                continue
            for m in members:
                for rec in [m] + m.dups:
                    source_map.append({"input_json": str(rec.path), "version": rec.version, "sha256": m.sha,
                                       "status": "not_in_sample", "group_id": gid})
    nc_rows = []
    for r in no_contact:
        for i, res in enumerate(r.resumes):
            for iss in K.check_resume(f"resumes[{i}]", res, int(r.updated[:4]) if r.updated[:4].isdigit() else None, r.langs[i]):
                ctx["issues"].append(_issue_row(str(r.path), r, iss["field_path"], iss["value"], iss["issue_type"], iss["severity"], iss.get("note", "")))
        rt_m, rt_e = r.rt_mobiles, r.rt_emails
        reason = "masked" if any(":masked:" in b for b in r.bad_contacts) else \
            "invalid_format" if r.bad_contacts else "landline_only" if r.landlines else "empty"
        names = [n for n, *_ in r.names]
        nc_rows.append({
            "json_path": str(r.path), "version": r.version, "content_sha256": r.sha,
            "duplicate_paths": [str(d.path) for d in r.dups],
            "original_path": r.original_path, "original_exists": bool(r.original_path) and os.path.exists(_rc.resolve_path(r.original_path)),
            "html_path": r.html_path, "html_exists": bool(r.html_path) and os.path.exists(_rc.resolve_path(r.html_path)),
            "source_format": Path(r.original_path).suffix.lower() if r.original_path else "",
            "full_name": names[0] if names else "", "birth_date": s(r.resumes[0]["base_info"].get("birth_date")) if r.resumes else "",
            "gender": s(r.resumes[0]["base_info"].get("gender")) if r.resumes else "", "languages": ",".join(r.langs),
            "raw_contact_values": r.bad_contacts + [f"landline:{x}" for x in sorted(r.landlines)],
            "raw_text_mobiles": rt_m, "raw_text_emails": rt_e, "reason": reason,
            "resume_updated_date": r.updated,
        })
        for rec in [r] + r.dups:
            source_map.append({"input_json": str(rec.path), "version": rec.version, "sha256": r.sha,
                               "status": "no_contact" if rec is r else "duplicate", "duplicate_of": "" if rec is r else str(r.path),
                               "name": names[0] if names else "", "languages": ",".join(r.langs), "original_path": rec.original_path or r.original_path})
    for r in shared_only:
        keys = sorted([f"m:{x}" for x in r.mobiles] + [f"e:{x}" for x in r.emails])
        review.append({"group_id": "", "output_json": "", "reason": "shared_contact_only", "input_json": str(r.path),
                       "detail": "; ".join(f"{k} 关联姓名: {','.join(shared[(k[0], k[2:])])}" for k in keys),
                       "original_path": r.original_path, "html_path": r.html_path})
        for rec in [r] + r.dups:
            source_map.append({"input_json": str(rec.path), "version": rec.version, "sha256": r.sha,
                               "status": "review_shared_contact" if rec is r else "duplicate", "duplicate_of": "" if rec is r else str(r.path),
                               "contacts": ";".join(keys), "original_path": r.original_path})
    for r in records:
        if not r.loaded:
            source_map.append({"input_json": str(r.path), "version": r.version, "sha256": r.sha, "status": "parse_error", "note": r.error})
    cleaning = ctx["cleaning"] + [c for r in canon for c in r.cleaning]

    # ---- 台账
    # EN: ---- Ledgers
    # JA: ---- 台帳
    write_ledger(ledger_dir, "source_map", sorted(source_map, key=lambda x: (x["version"], x["input_json"])),
                 ["input_json", "version", "status", "output_json", "group_id", "name", "contacts", "languages", "duplicate_of", "original_path", "sha256", "note"])
    write_ledger(ledger_dir, "excluded_ledger", excluded_rows + excluded_rec_rows,
                 ["group_id", "review_id", "reason", "evidence", "would_be_output", "input_json", "version", "contacts", "original_path", "html_path",
                  "duplicate_paths", "content_sha256"])
    write_ledger(ledger_dir, "no_contact_ledger", nc_rows,
                 ["json_path", "version", "reason", "full_name", "birth_date", "gender", "languages", "original_path", "original_exists",
                  "html_path", "html_exists", "source_format", "raw_contact_values", "raw_text_mobiles", "raw_text_emails",
                  "resume_updated_date", "duplicate_paths", "content_sha256"])
    write_ledger(ledger_dir, "field_issue_ledger", ctx["issues"],
                 ["output_json", "field_path", "issue_type", "severity", "value", "note", "source_json", "source_version", "original_path", "html_path", "group_id"])
    write_ledger(ledger_dir, "review_ledger", review, ["reason", "output_json", "input_json", "detail", "group_id", "original_path", "html_path"])
    write_ledger(ledger_dir, "conflict_ledger", ctx["conflicts"], ["output_json", "lang", "field_path", "chosen", "other", "chosen_source", "other_source", "note", "group_id"])
    write_ledger(ledger_dir, "cleaning_ledger", cleaning, ["source", "field_path", "action"])
    by_type = collections.Counter((i["issue_type"], i["severity"]) for i in ctx["issues"])
    by_file = collections.defaultdict(lambda: collections.Counter())
    for i in ctx["issues"]:
        if i["output_json"]:
            by_file[i["output_json"]][i["severity"]] += 1
    with open(ledger_dir / "field_issue_by_file.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["output_json", "high", "medium", "low"])
        for fn, c in sorted(by_file.items(), key=lambda x: (-x[1]["high"], x[0])):
            w.writerow([fn, c["high"], c["medium"], c["low"]])
    with open(ledger_dir / "field_issue_summary.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["issue_type", "severity", "count"])
        for (t, sv), c in sorted(by_type.items(), key=lambda x: -x[1]):
            w.writerow([t, sv, c])

    status_counts = collections.Counter(x["status"] for x in source_map)
    status_counts_cat = {c: len(list(d.glob("*.json"))) for c, d in cat_dirs.items()}
    summary = {
        "run_id": a.run_id, "rule_version": C.RULE_VERSION, "stamp": stamp,
        "started_at": t0.isoformat(timespec="seconds"), "finished_at": datetime.now().isoformat(timespec="seconds"),
        "inputs": {"v2": len(v2_files), "v1": len(v1_files), "total": len(records),
                   "parse_error": sum(1 for r in records if not r.loaded),
                   "byte_duplicates": sum(1 for r in records if r.dup_of is not None), "canonical": len(canon)},
        "identity": {"keyed_records": len(keyed), "candidates": len(gid_groups), "no_contact_records": len(no_contact),
                     "shared_contact_only_records": len(shared_only), "shared_contacts": {f"{k[0]}:{k[1]}": v for k, v in sorted(shared.items())}},
        "output": {"candidates_written": len(gids) - len({r["group_id"] for r in excluded_rows}), "excluded_non_resume": len({r["group_id"] for r in excluded_rows}), "excluded_records": len(excluded_rec_rows), "sample_mode": bool(a.sample_groups),
                   "formal": status_counts_cat.get("formal", 0), "needs_fix": status_counts_cat.get("needs_fix", 0),
                   "pending_translation": status_counts_cat.get("pending_translation", 0),
                   "multi_source": sum(1 for g in gids if len(gid_groups[g]) > 1),
                   "needs_translation": sum(1 for x in review if x["reason"] == "needs_translation"),
                   "name_unreliable": sum(1 for x in review if x["reason"] == "name_unreliable"),
                   "name_conflict": sum(1 for x in review if x["reason"] == "name_conflict")},
        "source_map_status": dict(status_counts),
        "ledgers": {"field_issues": len(ctx["issues"]), "conflicts": len(ctx["conflicts"]), "cleaning": len(cleaning),
                    "review": len(review), "no_contact": len(nc_rows), "excluded": len(excluded_rows) + len(excluded_rec_rows)},
        "reconciliation_ok": sum(status_counts.values()) == len(records),
        "paths": {c: str(d) for c, d in cat_dirs.items()} | {"ledgers": str(ledger_dir)},
    }
    mdp = Path(a.repair_dir) / "manual_decisions.json" if a.repair_dir else None
    if mdp and mdp.exists():
        summary["inputs"]["manual_decisions"] = {"count": ctx["manual"].loaded, "sha256": C.sha256_bytes(mdp.read_bytes()) if hasattr(C, "sha256_bytes")
                                                 else __import__("hashlib").sha256(mdp.read_bytes()).hexdigest(),
                                                 "unmatched": sum(1 for x in cleaning if str(x.get("action", "")).startswith("manual:unmatched"))}
        summary["paths"]["manual_decisions"] = str(mdp)
    stp = Path(a.repair_dir) / "source_texts.json" if a.repair_dir else None
    if stp and stp.exists():
        summary["inputs"]["source_texts"] = {"originals": len(SOURCE_TEXTS["originals"]), "inputs": len(SOURCE_TEXTS["inputs"]),
                                             "sha256": __import__("hashlib").sha256(stp.read_bytes()).hexdigest()}
        summary["paths"]["source_texts"] = str(stp)
    alp = Path(a.repair_dir) / "alignments.json" if a.repair_dir else None
    if alp and alp.exists():
        summary["inputs"]["alignments"] = {"count": len(ctx["manual"].alignments), "applied": len(ctx["manual"].aligned),
                                           "sha256": __import__("hashlib").sha256(alp.read_bytes()).hexdigest(),
                                           "unmatched": sum(1 for x in cleaning if str(x.get("action", "")).startswith("alignment:unmatched"))}
        summary["paths"]["alignments"] = str(alp)
    write_json_atomic(report_dir / "summary.json", summary)
    print(json.dumps({k: summary[k] for k in ("inputs", "output", "source_map_status", "ledgers", "reconciliation_ok")}, ensure_ascii=False, indent=1))
    print(f"完成：{run_dir}")


def members_sorted_path(members, si):
    ms = sorted(members, key=lambda m: m.priority())
    return ms[si].path if isinstance(si, int) and si < len(ms) else ""


if __name__ == "__main__":
    main()
