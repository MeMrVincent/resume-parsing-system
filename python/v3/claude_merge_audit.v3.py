#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
claude_merge_audit.v3.py —— merge v3 输出的独立验收（只读）。

重新读取输入目录、正式目录和 source_map 台账，逐项检查，全部为 0 才算通过：
  1. 输入对账：每个输入 JSON 在 source_map 中恰好出现一次
  2. 正式 JSON 全部可解析
  3. 正式 JSON 至少有一个有效手机号或邮箱
  4. 同一手机号/邮箱只出现在一个输出 JSON 中（formal / needs_fix / pending_translation 三个目录合计）
  5. 同一输入来源只归属一个正式 JSON
  6. 同一 JSON 内同语种 resume 只有一个；formal / needs_fix 的 resumes[0] 必须是中文；pending_translation 不含中文
  6b. formal 目录中的 JSON 不允许有任何 high 级字段问题，姓名必须有效
  7. 顶层快照与 resumes[0] 一致
  8. raw_text_length、quality 计数正确
  9. 文件名与 merge_info.output_filename、主联系方式一致
 10. 列表字段均为数组、条目字段为标准字段集、同一列表无完全相同条目
 11. （可选）与另一轮输出逐文件 SHA256 比对（幂等）

用法：
  python python\\v3\\claude_merge_audit.v3.py --run-dir <merge_out_dir>\\20260926-v3.0
  幂等比对：加 --compare-dir <merge_out_dir>\\20260926-v3.0-witness

EN: claude_merge_audit.v3.py -- independent acceptance check of merge v3 output (read-only).

Re-reads the input directories, the formal directory and the source_map ledger, checks item by item; it passes only when everything is 0:
  1. Input reconciliation: each input JSON appears exactly once in source_map
  2. All formal JSON can be parsed
  3. Each formal JSON has at least one valid mobile number or e-mail
  4. The same mobile number/e-mail appears in only one output JSON (across the formal / needs_fix / pending_translation directories)
  5. The same input source belongs to only one formal JSON
  6. Within one JSON there is only one resume per language; resumes[0] of formal / needs_fix must be Chinese; pending_translation contains no Chinese
  6b. JSON in the formal directory may not have any high-severity field issue, and the name must be valid
  7. Top-level snapshots match resumes[0]
  8. raw_text_length and quality counts are correct
  9. The file name matches merge_info.output_filename and the primary contact
 10. List fields are all arrays, entry fields are the standard field sets, and no list has identical entries
 11. (Optional) per-file SHA256 comparison with another run's output (idempotence)

Usage:
  python python\\v3\\claude_merge_audit.v3.py --run-dir <merge_out_dir>\\20260926-v3.0
  Idempotence comparison: add --compare-dir <merge_out_dir>\\20260926-v3.0-witness

JA: claude_merge_audit.v3.py —— merge v3 の出力の独立した受け入れ検査（読み取り専用）。

入力ディレクトリ、正式ディレクトリ、source_map の台帳を読み直して 1 項目ずつチェックし、すべて 0 なら合格とする：
  1. 入力の突き合わせ：各入力 JSON が source_map にちょうど 1 回現れる
  2. 正式 JSON がすべて解析できる
  3. 正式 JSON には有効な携帯電話番号かメールが少なくとも 1 つある
  4. 同じ携帯電話番号・メールは 1 つの出力 JSON にしか現れない（formal / needs_fix / pending_translation の 3 ディレクトリ合計）
  5. 同じ入力ソースは 1 つの正式 JSON にしか属さない
  6. 1 つの JSON 内で同じ言語の resume は 1 つだけ。formal / needs_fix の resumes[0] は中国語でなければならず、pending_translation は中国語を含まない
  6b. formal ディレクトリの JSON には重大（high）なフィールドの問題が 1 つもあってはならず、氏名は有効でなければならない
  7. トップレベルのスナップショットが resumes[0] と一致する
  8. raw_text_length と quality の件数が正しい
  9. ファイル名が merge_info.output_filename および主な連絡先と一致する
 10. リストのフィールドはすべて配列で、項目のフィールドは標準のフィールドセット、同じリストに完全に同一の項目がない
 11. （任意）別の実行の出力とファイルごとの SHA256 を比較する（冪等性）

使い方：
  python python\\v3\\claude_merge_audit.v3.py --run-dir <merge_out_dir>\\20260926-v3.0
  冪等性の比較：--compare-dir <merge_out_dir>\\20260926-v3.0-witness を付ける
"""
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1] / "common"))
import rc_config as _rc  # noqa: E402  项目统一配置（python/common/rc_config.py）
# EN: noqa: E402  project-wide configuration (python/common/rc_config.py)
# JA: noqa: E402  プロジェクト共通設定（python/common/rc_config.py）

import argparse
import collections
import csv
import hashlib
import json
import os
import sys
from pathlib import Path
import importlib.util

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("claude_merge_common_v3_audit", HERE / "claude_merge_common.v3.py")
C = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(C)
_spec2 = importlib.util.spec_from_file_location("claude_merge_checks_v3_audit", HERE / "claude_merge_checks.v3.py")
K = importlib.util.module_from_spec(_spec2)
_spec2.loader.exec_module(K)
s = C.s
CATEGORIES = ("formal", "needs_fix", "pending_translation")


# 日期统一（unify_dates）可能改动日期字段，所以人工决定的行匹配不比较日期字段
# EN: unify_dates may change date fields, so row matching for manual decisions ignores date fields
# JA: unify_dates が日付フィールドを変更し得るため、人手決定の行照合では日付フィールドを比較しない
_DATE_FIELDS = {"work_experiences": ("position_start", "position_resigned"), "education_list": ("school_start_ym", "school_end_ym"),
                "certificate_list": ("certificate_time",), "language_list": ("language_certificate_time",),
                "training_list": ("start_ym", "end_ym"), "project_list": ("start_ym", "end_ym")}


class ManualCheck:
    """审计独立读取人工决定文件（路径与 sha256 取自本次 summary.json），只放行“人工按原文确认不是错误”的条目和人工定下的姓名。

    EN: The audit reads the manual-decision files independently (path and sha256 taken from this run's summary.json), and lets through only entries "manually confirmed against the source as not an error" and names decided manually.

    JA: 監査は人手の判断のファイルを独立して読み（パスと sha256 は今回の summary.json から取る）、「原文を見て人手で誤りではないと確認した」項目と人手で決めた氏名だけを通す。
    """
    def __init__(self, run_dir):
        self.accepts, self.names, self.info, self.excludes, self.exrecs = {}, {}, {}, {}, {}
        # 没有 manual_decisions / 对齐记录时（例如不带修复目录的演示运行）也要有默认值
        # EN: Defaults are needed even without manual_decisions / alignment records (e.g. a demo run without a repair directory)
        # JA: manual_decisions や対応付けの記録がない場合（例：修復ディレクトリなしのデモ実行）にも既定値が必要
        self.src_texts, self.st_info = None, {}
        self.align_lists, self.align_new, self.align_base, self.align_info = {}, {}, {}, {}
        try:
            summ = json.loads((Path(run_dir) / "reports" / "summary.json").read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return
        p = (summ.get("paths") or {}).get("manual_decisions")
        want = ((summ.get("inputs") or {}).get("manual_decisions") or {}).get("sha256")
        if not p or not Path(p).exists():
            return
        raw = Path(p).read_bytes()
        self.info = {"path": p, "sha256_ok": hashlib.sha256(raw).hexdigest() == want}
        if not self.info["sha256_ok"]:
            return
        self.src_texts, self.st_info = None, {}
        stp = (summ.get("paths") or {}).get("source_texts")
        if stp and Path(stp).exists():
            sraw = Path(stp).read_bytes()
            self.st_info = {"path": stp, "sha256_ok": hashlib.sha256(sraw).hexdigest() == ((summ.get("inputs") or {}).get("source_texts") or {}).get("sha256")}
            if self.st_info["sha256_ok"]:
                self.src_texts = json.loads(sraw.decode("utf-8"))
        self.align_lists = {}   # gid -> 对齐过的 list 名
        # EN: gid -> names of aligned lists
        # JA: gid -> 対応付け済みのリスト名
        self.align_new = {}   # gid -> [(lang, list, {字段: 译文})]
        # EN: gid -> [(lang, list, {field: translation})]
        # JA: gid -> [(lang, list, {フィールド: 訳文})]
        self.align_info = {}
        self.align_base = {}
        ap = (summ.get("paths") or {}).get("alignments")
        if ap and Path(ap).exists():
            araw = Path(ap).read_bytes()
            self.align_info = {"path": ap, "sha256_ok": hashlib.sha256(araw).hexdigest() == ((summ.get("inputs") or {}).get("alignments") or {}).get("sha256")}
            if self.align_info["sha256_ok"]:
                for x in json.loads(araw.decode("utf-8")).get("items", []):
                    self.align_lists[x["group_id"]] = list((x.get("lists") or {}).keys())
                    for lg, fv in (x.get("base") or {}).items():
                        self.align_base.setdefault(x["group_id"], []).append((lg, fv))
                    for lst, rows in (x.get("lists") or {}).items():
                        for row in rows:
                            if row.get("drop"):
                                continue
                            for lg, fv in (row.get("new") or {}).items():
                                self.align_new.setdefault(x["group_id"], []).append((lg, lst, fv))
        for d in json.loads(raw.decode("utf-8")).get("decisions", []):
            if d["kind"] == "name":
                self.names[d["group_id"]] = d["name"]
            elif d["kind"] == "exclude":
                self.excludes[d["group_id"]] = d
            elif d["kind"] == "exclude_record":
                self.exrecs[d["content_sha256"]] = d
            elif d["action"] == "accept":
                self.accepts.setdefault(d["group_id"], []).append(d)

    def allows(self, gid, resumes, iss):
        import re as _re
        t = iss["issue_type"]
        if t.startswith("name_") and gid in self.names:
            return True
        m = _re.match(r"resumes\[(\d+)\](?:\.(\w+))?(?:\[(\d+)\])?", iss["field_path"])
        if not m:
            return False
        ri, lst = int(m.group(1)), m.group(2) or ""
        res = resumes[ri] if ri < len(resumes) else {}
        if lst == "base_info":
            obj = res.get("base_info") or {}
        elif lst and m.group(3) is not None:
            items = res.get(lst) or []
            k = int(m.group(3))
            obj = items[k] if k < len(items) else None
        else:
            obj, lst = res, ""
        if lst == "base_info" and isinstance(obj, dict):
            fld = iss["field_path"].rsplit(".", 1)[-1]
            lg0 = s(res.get("resume_languge"))
            if any(l2 == lg0 and fld in fv and s(fv[fld]) == s(obj.get(fld)) for l2, fv in self.align_base.get(gid, [])):
                return True
        if lst and isinstance(obj, dict):
            lg = s(res.get("resume_languge"))
            for l2, lst2, fv in self.align_new.get(gid, []):
                if l2 == lg and lst2 == lst and all(s(obj.get(f)) == s(v) for f, v in fv.items() if f not in _DATE_FIELDS.get(lst, ())):
                    return True
        for d in self.accepts.get(gid, []):
            if d["resume_index"] == ri and d["list"] == lst and t in d.get("issue_types", []) and isinstance(obj, dict) \
                    and all(s(obj.get(f))[:600] == s(v) for f, v in d["match"].items() if f not in _DATE_FIELDS.get(lst, ())):
                return True
        return False

    def name_ok(self, gid, full_name):
        n = self.names.get(gid)
        return bool(n) and full_name in (n, C.to_simplified_name(n))


def valid_contacts(doc):
    out = set()
    for r in (doc.get("structured_data") or {}).get("resumes") or []:
        b = r.get("base_info") or {}
        for part in C.split_contact_values(b.get("phone")):
            k, v = C.classify_phone(part)
            if k in ("mobile", "intl_mobile"):
                out.add(("m", v))
        for part in C.split_contact_values(b.get("email")):
            k, v = C.classify_email(part)
            if k == "email":
                out.add(("e", v))
    return out


def main():
    try:
        sys.stdout.reconfigure(errors="replace")
    except Exception:  # noqa: BLE001
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", type=Path, required=True)
    ap.add_argument("--v2-dir", type=Path, default=_rc.path("v2_dir"))
    ap.add_argument("--v1-dir", type=Path, default=_rc.path("v1_dir"))
    ap.add_argument("--compare-dir", type=Path)
    a = ap.parse_args()
    global MANUAL
    MANUAL = ManualCheck(a.run_dir)
    fails = collections.defaultdict(list)
    stat_raw = collections.Counter()

    # 1. 输入对账
    # EN: 1. Input reconciliation
    # JA: 1. 入力の突き合わせ
    inputs = []
    for d in (a.v2_dir, a.v1_dir):
        with os.scandir(d) as it:
            inputs += [str(Path(e.path)) for e in it if e.is_file() and e.name.lower().endswith(".json") and not e.name.startswith("_")]
    smap = list(csv.DictReader(open(a.run_dir / "ledgers" / "source_map.csv", encoding="utf-8-sig")))
    cnt = collections.Counter(r["input_json"] for r in smap)
    for p in inputs:
        if cnt.get(p, 0) != 1:
            fails["input_reconciliation"].append(f"{p} 出现 {cnt.get(p, 0)} 次")
    for p in set(cnt) - set(inputs):
        fails["input_reconciliation"].append(f"source_map 中多余：{p}")
    sample_mode = any(r["status"] == "not_in_sample" for r in smap)

    # 2-10. 正式 JSON
    # EN: 2-10. Formal JSON
    # JA: 2-10. 正式 JSON
    files = [(c, f) for c in CATEGORIES for f in sorted((a.run_dir / c).glob("*.json"))]
    names_seen = collections.Counter(f.name.lower() for _, f in files)
    for n, k in names_seen.items():
        if k > 1:
            fails["same_filename_in_two_folders"].append(n)
    contact_owner = collections.defaultdict(list)
    source_owner = collections.defaultdict(list)
    for cat, f in files:
        try:
            doc = json.loads(f.read_text(encoding="utf-8"))
        except Exception as ex:  # noqa: BLE001
            fails["parse"].append(f"{f.name}: {ex}")
            continue
        sd = doc.get("structured_data") or {}
        resumes = sd.get("resumes") or []
        mi = doc.get("merge_info") or {}
        cs = valid_contacts(doc)
        if not cs:
            fails["no_valid_contact"].append(f.name)
        for c in cs:
            contact_owner[c].append(f"{cat}/{f.name}")
        for src in (doc.get("source") or {}).get("source_files") or []:
            source_owner[src.get("json_path")].append(f"{cat}/{f.name}")
        langs = [s(r.get("resume_languge")) for r in resumes]
        if len(langs) != len(set(langs)):
            fails["duplicate_language_resume"].append(f"{f.name}: {langs}")
        if cat in ("formal", "needs_fix") and (not langs or langs[0] != "zh"):
            fails["resumes0_not_zh"].append(f"{cat}/{f.name}: {langs}")
        if cat == "pending_translation" and "zh" in langs:
            fails["pending_translation_has_zh"].append(f.name)
        if mi.get("output_category") != cat:
            fails["category_mismatch"].append(f"{cat}/{f.name}: {mi.get('output_category')}")
        if cat == "formal":
            ry = s((doc.get("dates") or {}).get("resume_updated_date"))[:4]
            ry = int(ry) if ry.isdigit() else None
            hi = [x for i, r in enumerate(resumes) for x in K.check_resume(f"resumes[{i}]", r, ry, s(r.get("resume_languge"))) if x["severity"] == "high"]
            hi += [x for x in K.check_cross_language(resumes) if x["severity"] == "high"]
            gid = s(mi.get("group_id"))
            hi = [x for x in hi if not MANUAL.allows(gid, resumes, x)]
            if hi:
                fails["formal_has_high_issue"].append(f"{f.name}: {hi[0]['issue_type']} {hi[0]['field_path']}")
            if C.name_quality(s((resumes[0].get("base_info") or {}).get("full_name")))[0] != "valid" \
                    and not MANUAL.name_ok(gid, s((resumes[0].get("base_info") or {}).get("full_name"))):
                fails["formal_name_invalid"].append(f.name)
        if not resumes:
            fails["no_resume"].append(f.name)
            continue
        r0 = resumes[0]
        if sd.get("base_info") != {k: s((r0.get("base_info") or {}).get(k)) for k in C.BASE_FIELDS}:
            fails["snapshot_base_info"].append(f.name)
        exp = r0.get("expected_list") or []
        want = {k: s(exp[0].get(k)) for k in C.EXPECTED_FIELDS} if exp else {k: "" for k in C.EXPECTED_FIELDS}
        if sd.get("expected_info") != want:
            fails["snapshot_expected_info"].append(f.name)
        edu = r0.get("education_list") or []
        ei = sd.get("education_info") or {}
        if (edu and ei not in [{k: s(e.get(k)) for k in C.EDU_FIELDS} for e in edu]) or (not edu and any(ei.values())):
            fails["snapshot_education_info"].append(f.name)
        work = r0.get("work_experiences") or []
        ci = sd.get("current_info") or {}
        if work and ci not in [{k: s(w.get(k)) for k in C.CURRENT_FIELDS} for w in work]:
            fails["snapshot_current_info"].append(f.name)
        # raw_text 规则：单来源+单语言+未翻译 → 原文文本；其余（合并/翻译/多语言）→ 各字段一行拼装
        # EN: raw_text rule: single source + single language + not translated → original text; otherwise (merged/translated/multilingual) → assembled with one field per line
        # JA: raw_text のルール：単一ソース + 単一言語 + 翻訳なし → 原文のテキスト。それ以外（統合・翻訳・多言語）→ フィールドを 1 行ずつ組み立てる
        if True:
            translated = bool(mi.get("translated_from"))
            expect = None
            if len(resumes) == 1 and not translated and MANUAL.src_texts is not None:
                shas = [s(sf.get("sha256")) for sf in (doc.get("source") or {}).get("source_files") or []]
                ors = {MANUAL.src_texts["inputs"].get(x) for x in shas}
                if len(ors) == 1 and None not in ors and MANUAL.src_texts["originals"].get(next(iter(ors))):
                    o = next(iter(ors))
                    expect = C.clean_source_text(MANUAL.src_texts["originals"][o]["text"])
                    stat_raw["source"] += 1
                    opath = _rc.resolve_path(MANUAL.src_texts["originals"][o].get("original_path") or "")
                    if opath and os.path.isfile(opath):
                        stat_raw["original_checked"] += 1
                        if hashlib.sha256(Path(opath).read_bytes()).hexdigest() != o:
                            fails["raw_text_original_sha"].append(f"{f.name}: {opath}")
            if expect is None:
                expect = C.build_raw_text_assembled(resumes)
                stat_raw["assembled"] += 1
            if (doc.get("raw_text") or "") != expect:
                fails["raw_text_rule"].append(f.name)
            gl = MANUAL.align_lists.get(s(mi.get("group_id")))
            if gl and len(resumes) > 1:
                for lst in gl:
                    if len({len(r.get(lst) or []) for r in resumes}) > 1:
                        fails["align_list_counts"].append(f"{f.name}: {lst}")
                        break
        if len(doc.get("raw_text") or "") != (doc.get("quality") or {}).get("raw_text_length"):
            fails["raw_text_length"].append(f.name)
        if (doc.get("quality") or {}).get("work_count") != len(work):
            fails["quality_work_count"].append(f.name)
        if mi.get("output_filename") != f.name:
            fails["filename_mismatch"].append(f"{f.name} != {mi.get('output_filename')}")
        contact_part = C.safe_filename_part(mi.get("primary_phone") or mi.get("primary_email") or "")
        if contact_part not in f.stem:
            fails["filename_contact"].append(f.name)
        for i, r in enumerate(resumes):
            for lst, fields in C.LIST_FIELDS.items():
                items = r.get(lst)
                if not isinstance(items, list):
                    fails["list_not_array"].append(f"{f.name} resumes[{i}].{lst}")
                    continue
                seen = set()
                for j, it in enumerate(items):
                    if set(it) != set(fields):
                        fails["list_item_keys"].append(f"{f.name} resumes[{i}].{lst}[{j}]: {sorted(set(it) ^ set(fields))}")
                    key = json.dumps({k: v for k, v in it.items() if k != "sequence_no"}, ensure_ascii=False, sort_keys=True)
                    if key in seen:
                        fails["list_exact_duplicate"].append(f"{f.name} resumes[{i}].{lst}[{j}]")
                    seen.add(key)
    for c, owners in contact_owner.items():
        if len(owners) > 1:
            fails["contact_in_multiple_files"].append(f"{c[1]}: {owners}")
    for src, owners in source_owner.items():
        if len(owners) > 1:
            fails["source_in_multiple_files"].append(f"{src}: {owners}")
    out_rows = [r for r in smap if r["status"] in CATEGORIES]
    if len(out_rows) != len(source_owner):
        fails["source_map_vs_output"].append(f"source_map 输出来源={len(out_rows)}，输出 JSON 引用来源={len(source_owner)}")
    for r in out_rows:
        owners = source_owner.get(r["input_json"], [])
        if owners != [r["output_json"]]:
            fails["source_map_vs_output"].append(f"{r['input_json']}: source_map={r['output_json']} 实际={owners}")

    # 10b. 人工确认“不是简历”而不输出的：source_map 里的 excluded_non_resume 必须与（sha256 已核对的）人工决定完全一致，且不得出现在任何输出 JSON 里
    # EN: 10b. Inputs not output because they were manually confirmed as "not a résumé": excluded_non_resume in source_map must match the (sha256-verified) manual decisions exactly, and must not appear in any output JSON
    # JA: 10b. 人手で「履歴書ではない」と確認して出力しなかったもの：source_map の excluded_non_resume は（sha256 で照合済みの）人手の判断と完全に一致し、どの出力 JSON にも現れてはならない
    ex_rows = [r for r in smap if r["status"] == "excluded_non_resume"]
    ex_gids = {r["group_id"] for r in ex_rows if r["group_id"]}
    ex_shas = {r["sha256"] for r in ex_rows if not r["group_id"]}
    if ex_shas != set(MANUAL.exrecs):
        fails["excluded_vs_decision"].append(f"按输入文件排除的 sha256 与人工决定不一致：source_map={sorted(ex_shas)} 决定={sorted(MANUAL.exrecs)}")
    if MANUAL.info.get("sha256_ok") is False and ex_rows:
        fails["excluded_vs_decision"].append("人工决定文件 sha256 不符")
    for g in ex_gids - set(MANUAL.excludes):
        fails["excluded_vs_decision"].append(f"source_map 排除了 {g}，但人工决定里没有")
    for g in set(MANUAL.excludes) - ex_gids:
        fails["excluded_vs_decision"].append(f"人工决定要求排除 {g}，但 source_map 里没有")
    for r in ex_rows:
        if r["input_json"] in source_owner:
            fails["excluded_vs_decision"].append(f"{r['input_json']} 已排除但仍出现在输出 JSON 里")
    if not sample_mode:
        exl = list(csv.DictReader(open(a.run_dir / "ledgers" / "excluded_ledger.csv", encoding="utf-8-sig"))) if (a.run_dir / "ledgers" / "excluded_ledger.csv").exists() else []
        if {r["group_id"] for r in exl if r["group_id"]} != ex_gids or {r["content_sha256"] for r in exl if not r["group_id"]} != ex_shas:
            fails["excluded_vs_decision"].append("excluded_ledger 与 source_map 不一致")

    # 11. 幂等
    # EN: 11. Idempotence
    # JA: 11. 冪等性
    compare = None
    if a.compare_dir:
        def digest(d):
            return {f"{c}/{p.name}": hashlib.sha256(p.read_bytes()).hexdigest() for c in CATEGORIES for p in (d / c).glob("*.json")}
        x, y = digest(a.run_dir), digest(a.compare_dir)
        diff = sorted(n for n in set(x) | set(y) if x.get(n) != y.get(n))
        compare = {"files_a": len(x), "files_b": len(y), "diff": len(diff), "diff_sample": diff[:20]}
        if diff:
            fails["idempotency"].extend(diff[:200])

    checks = ["input_reconciliation", "parse", "same_filename_in_two_folders", "no_valid_contact", "contact_in_multiple_files",
              "source_in_multiple_files", "source_map_vs_output", "category_mismatch", "resumes0_not_zh", "pending_translation_has_zh",
              "formal_has_high_issue", "formal_name_invalid", "duplicate_language_resume", "no_resume", "snapshot_base_info",
              "snapshot_expected_info", "snapshot_education_info", "snapshot_current_info", "raw_text_length",
              "quality_work_count", "filename_mismatch", "filename_contact", "list_not_array", "list_item_keys",
              "list_exact_duplicate", "excluded_vs_decision", "raw_text_rule", "raw_text_original_sha", "align_list_counts"] + (["idempotency"] if a.compare_dir else [])
    result = {
        "manual_decisions": MANUAL.info,
        "run_dir": str(a.run_dir), "inputs": len(inputs), "sample_mode": sample_mode,
        "output_files": {c: sum(1 for x, _ in files if x == c) for c in CATEGORIES},
        "checks": {c: len(fails.get(c, [])) for c in checks},
        "passed": all(len(fails.get(c, [])) == 0 for c in checks),
        "compare": compare,
        "raw_text_stats": dict(stat_raw), "alignments": MANUAL.align_info, "source_texts": MANUAL.st_info,
        "examples": {c: v[:30] for c, v in fails.items()},
    }
    out = a.run_dir / "reports" / "audit.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    for c in checks:
        n = result["checks"][c]
        print(f"  {'OK ' if n == 0 else 'FAIL'} {c}: {n}")
    print(("审计通过" if result["passed"] else "审计未通过") + f"：{out}")
    sys.exit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()
