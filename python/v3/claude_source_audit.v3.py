#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
claude_source_audit.v3.py —— 每个输入 JSON 回到原始文件逐项核对，判定是否是解析器问题，生成台账。

输入：
  --pack-dir    claude_pack 解压目录（inputs/、manifest.csv）
  --text-dir    claude_source_text.v3.py 输出目录（texts/、extract_ledger.csv）
  --merge-run   merge-v3 某次运行目录（ledgers/source_map.csv、ledgers/field_issue_ledger.csv）
输出（--out）：
  source_audit_ledger.csv      每个输入 JSON 一行：原文件、后缀、真实格式、解析器、联系方式/姓名/字段回源结果、结论
  contact_recovery.csv         原文件里有手机号/邮箱而 JSON 没有（重点：无联系方式批次）
  field_not_in_source.csv      JSON 字段值在原文件中找不到（疑似解析错位、编造或翻译）
  parser_summary.csv           按解析器 × 问题类型汇总
  source_audit_summary.json

判定（defects 列，可多项）：
  source_missing          原文件缺失 / 未打包
  source_unreadable       原文件无法抽取文本（图片、损坏、超时）
  contact_missed          原文件有联系方式，JSON 一个都没有
  contact_partial         原文件的手机号/邮箱只收了一部分
  contact_not_in_source   JSON 的联系方式在原文件中找不到
  name_not_in_source      JSON 姓名在原文件中找不到
  entity_not_in_source    与原文同语种的 resume 中，公司/学校/职位等有值在原文中找不到
  entries_missing         原文日期区间数量明显多于 JSON 工作+教育+项目+培训条目
  content_lost            原文正文大量内容未进入 JSON raw_text
  field_issue_high        merge 字段校验有 high 问题（字段放错位置等）

EN: claude_source_audit.v3.py -- checks each input JSON item by item against the original file, decides whether it is a parser problem, and produces ledgers.

Input:
  --pack-dir    the extracted claude_pack directory (inputs/, manifest.csv)
  --text-dir    the output directory of claude_source_text.v3.py (texts/, extract_ledger.csv)
  --merge-run   a merge-v3 run directory (ledgers/source_map.csv, ledgers/field_issue_ledger.csv)
Output (--out):
  source_audit_ledger.csv      one row per input JSON: original file, suffix, real format, parser, results of contact/name/field verification, conclusion
  contact_recovery.csv         the original file has a mobile/e-mail but the JSON does not (focus: the no-contact batch)
  field_not_in_source.csv      JSON field values not found in the original file (suspected parse misplacement, fabrication or translation)
  parser_summary.csv           summary by parser × issue type
  source_audit_summary.json

Decisions (defects column, may have several):
  source_missing          original file missing / not packed
  source_unreadable       text cannot be extracted from the original file (image, damaged, timeout)
  contact_missed          the original file has contacts, the JSON has none
  contact_partial         only some of the original file's mobiles/e-mails were taken
  contact_not_in_source   the JSON's contacts are not found in the original file
  name_not_in_source      the JSON name is not found in the original file
  entity_not_in_source    in a resume of the same language as the source, values such as company/school/position are not found in the source
  entries_missing         the number of date ranges in the source is clearly greater than the JSON's work + education + project + training entries
  content_lost            a large part of the source body did not get into the JSON raw_text
  field_issue_high        the merge field validation has high-severity issues (fields in the wrong place, etc.)

JA: claude_source_audit.v3.py —— 各入力 JSON を元のファイルに戻って 1 項目ずつ照合し、パーサーの問題かどうかを判定して台帳を作る。

入力：
  --pack-dir    claude_pack を展開したディレクトリ（inputs/、manifest.csv）
  --text-dir    claude_source_text.v3.py の出力ディレクトリ（texts/、extract_ledger.csv）
  --merge-run   merge-v3 のある実行ディレクトリ（ledgers/source_map.csv、ledgers/field_issue_ledger.csv）
出力（--out）：
  source_audit_ledger.csv      入力 JSON ごとに 1 行：元のファイル、拡張子、実際の形式、パーサー、連絡先・氏名・フィールドの照合結果、結論
  contact_recovery.csv         元のファイルに携帯番号・メールがあるのに JSON にない（重点：連絡先なしのバッチ）
  field_not_in_source.csv      JSON のフィールドの値が元のファイルに見つからない（解析のずれ・捏造・翻訳の疑い）
  parser_summary.csv           パーサー × 問題の種類ごとの集計
  source_audit_summary.json

判定（defects 列。複数あり得る）：
  source_missing          元のファイルがない・まとめられていない
  source_unreadable       元のファイルからテキストを抽出できない（画像・破損・タイムアウト）
  contact_missed          元のファイルに連絡先があるのに、JSON には 1 つもない
  contact_partial         元のファイルの携帯番号・メールの一部しか取り込まれていない
  contact_not_in_source   JSON の連絡先が元のファイルに見つからない
  name_not_in_source      JSON の氏名が元のファイルに見つからない
  entity_not_in_source    原文と同じ言語の resume で、会社・学校・職位などの値が原文に見つからない
  entries_missing         原文の期間の数が、JSON の職歴 + 学歴 + プロジェクト + 研修の項目より明らかに多い
  content_lost            原文の本文の大部分が JSON の raw_text に入っていない
  field_issue_high        merge のフィールドの検証で high の問題がある（フィールドの置き間違いなど）
"""

import argparse
import collections
import csv
import importlib.util
import json
import os
import re
import sys
import unicodedata
from pathlib import Path, PureWindowsPath

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("claude_merge_common_v3_sa", HERE / "claude_merge_common.v3.py")
C = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(C)
s = C.s

ENTITY_FIELDS = {
    "work_experiences": ["company_name", "position"],
    "education_list": ["school_name", "school_major_name"],
    "certificate_list": ["certificate_name"],
    "project_list": ["project_name"],
    "training_list": ["organization_name", "training_name"],
}
RANGE_RE = re.compile(r"((?:19|20)\d{2})\s*[年./\-／]\s*(\d{1,2})\s*月?\s*(?:[~～\-－—–至到]+|\s+to\s+)\s*"
                      r"(?:((?:19|20)\d{2})\s*[年./\-／]\s*(\d{1,2})|至今|现在|今|present|now|現在)", re.I)
# 招聘平台页面上的操作按钮、页眉页脚等非简历内容，不计入覆盖率
# EN: Operation buttons, headers/footers etc. on recruitment platform pages are not résumé content and do not count toward coverage
# JA: 求人プラットフォームのページにある操作ボタン・ヘッダー・フッターなどは履歴書の内容ではないため、網羅率に数えない
BOILER_RE = re.compile(r"(下载简历|打印简历|转发简历|简历来自|来自51job|前程无忧|智联招聘网|猎聘网|Content-Type|Content-Transfer|boundary|"
                       r"MIME-Version|X-51JOB|推荐理由|顾问评价|紐培|推薦理由|版权所有|Copyright|www\.|http)", re.I)
EXT_PARSER = {
    ".doc": "word(推断)", ".docx": "word(推断)", ".docm": "word(推断)", ".dotx": "word(推断)", ".wps": "word(推断)",
    ".xls": "xls(推断)", ".xlsx": "xls(推断)",
    ".htm": "web(推断)", ".html": "web(推断)", ".mht": "web(推断)",
    ".pdf": "pdf(推断)",
}


DATE_CANON_RE = re.compile(r"((?:19|20)\d{2})\s*[年./\-／]\s*(\d{1,2})(?:\s*[月./\-／]\s*(\d{1,2})\s*日?|\s*月)?")
DURATION_RE = re.compile(r"[（(]\s*\d+\s*年?\s*\d*\s*个?月?\s*[）)]")


def canon(t: str) -> str:
    """比较用：日期统一为 YYYYMM（去掉日），去掉“（1年3个月）”这类时长。

    EN: For comparison: unify dates to YYYYMM (dropping the day) and remove durations like "（1年3个月）" (1 year 3 months).

    JA: 比較用：日付を YYYYMM に統一し（日は除く）、「（1年3个月）」（1 年 3 か月）のような期間を除く。
    """
    t = unicodedata.normalize("NFKC", t or "")
    t = DURATION_RE.sub("", t)
    return DATE_CANON_RE.sub(lambda m: f"{m.group(1)}{int(m.group(2)):02d}", t)


def norm_src(t: str) -> str:
    t = canon(t).lower()
    return re.sub(r"[\s\W_]+", "", t)


def shingles(t: str, n=4):
    return {t[i:i + n] for i in range(0, max(len(t) - n + 1, 0))}


def parser_label(doc: dict, ver: str, ext: str) -> str:
    ex = doc.get("extraction") or {}
    conv = s(ex.get("converter")) or s(ex.get("parser_version"))
    grp = s(ex.get("reader_group"))
    note = s((doc.get("source") or {}).get("note"))
    if conv or grp:
        return f"{ver}:{conv or '-'}|{grp or '-'}"
    m = re.search(r"由\s*([\w.]+\.py)", note)
    if m:
        return f"{ver}:{m.group(1)}"
    return f"{ver}:{EXT_PARSER.get(ext, 'other(推断)')}"


def source_contacts(text: str):
    """原文中的手机号/邮箱；“13800000020happy@163.com”这类粘连拆成手机号 + 邮箱。

    EN: Mobiles/e-mails in the source; stuck-together values like "13800000020happy@163.com" are split into mobile + e-mail.

    JA: 原文の携帯番号・メール。「13800000020happy@163.com」のようにくっついたものは携帯番号 + メールに分ける。
    """
    ms, es = set(), set()
    t = unicodedata.normalize("NFKC", text)
    for m in C.MOBILE_FIND.findall(t):
        k, v = C.classify_phone(m)
        if k == "mobile":
            ms.add(v)
    for e in C.EMAIL_FIND.findall(t):
        for part in C.split_glued(e):
            if "@" in part:
                k, v = C.classify_email(part)
                if k == "email":
                    es.add(v)
            else:
                k, v = C.classify_phone(part)
                if k == "mobile":
                    ms.add(v)
    return ms, es


def json_contacts(doc):
    ms, es = set(), set()
    for r in (doc.get("structured_data") or {}).get("resumes") or []:
        for _f, kind, val, _raw in C.contacts_from_base(r.get("base_info") or {}):
            if kind in ("mobile", "intl_mobile"):
                ms.add(val)
            elif kind == "email":
                es.add(val)
    return ms, es


def main():  # noqa: C901
    try:
        sys.stdout.reconfigure(errors="replace")
    except Exception:  # noqa: BLE001
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--pack-dir", type=Path, required=True)
    ap.add_argument("--text-dir", type=Path, required=True)
    ap.add_argument("--merge-run", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)

    manifest = collections.defaultdict(list)
    for r in csv.DictReader(open(a.pack_dir / "manifest.csv", encoding="utf-8-sig")):
        manifest[r["input_json"]].append(r)
    extract = {r["pack_key"]: r for r in csv.DictReader(open(a.text_dir / "extract_ledger.csv", encoding="utf-8-sig"))}
    smap = {r["input_json"]: r for r in csv.DictReader(open(a.merge_run / "ledgers" / "source_map.csv", encoding="utf-8-sig"))}
    issues = collections.defaultdict(list)
    for r in csv.DictReader(open(a.merge_run / "ledgers" / "field_issue_ledger.csv", encoding="utf-8-sig")):
        if r["severity"] == "high":
            for sj in (r.get("source_json") or "").split(";"):
                if sj:
                    issues[sj.strip()].append(r["issue_type"])

    text_cache = {}

    def src_text(key):
        if key not in text_cache:
            p = a.text_dir / "texts" / (Path(key).stem + ".txt")
            text_cache[key] = p.read_text(encoding="utf-8") if p.exists() else None
            if len(text_cache) > 3000:
                text_cache.pop(next(iter(text_cache)))
        return text_cache[key]

    rows, recov, notin, lost_rows = [], [], [], []
    par_sum = collections.defaultdict(collections.Counter)
    for input_json, mrows in manifest.items():
        ver = mrows[0]["version"]
        rel = f"inputs/{ver}/{PureWindowsPath(input_json).name}"
        try:
            doc = json.loads((a.pack_dir / rel).read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        origs = [r for r in mrows if r["kind"] == "original"]
        sm = smap.get(input_json, {})
        orig_path = origs[0]["path"] if origs else ""
        ext = PureWindowsPath(orig_path).suffix.lower()
        parser = parser_label(doc, ver, ext)
        defects = []
        texts, methods = [], []
        for r in origs:
            if r["exists"] != "True":
                continue
            ex = extract.get(r["pack_key"], {})
            methods.append(ex.get("method", ""))
            t = src_text(r["pack_key"]) if ex.get("ok") == "True" else None
            if t:
                texts.append(t)
        if not any(r["exists"] == "True" for r in origs):
            defects.append("source_missing")
        elif not texts:
            defects.append("source_unreadable")
        full = "\n".join(texts)
        nsrc = norm_src(full)
        sd = doc.get("structured_data") or {}
        resumes = sd.get("resumes") or []
        jm, je = json_contacts(doc)
        sm_m, sm_e = source_contacts(full) if full else (set(), set())
        contact_status = ""
        if full:
            if (sm_m or sm_e) and not (jm or je):
                contact_status = "contact_missed"
            elif (sm_m - jm) or (sm_e - je):
                contact_status = "contact_partial"
            if (jm - sm_m) or (je - sm_e):
                # 手机号在原文中可能带空格/横线，已在 contacts_in_text 中归一；邮箱大小写已归一
                # EN: Mobile numbers in the source may carry spaces/dashes, already normalised in contacts_in_text; e-mail case is already normalised
                # JA: 原文の携帯番号には空白やハイフンが入っていることがあるが、contacts_in_text で正規化済み。メールの大文字小文字も正規化済み
                contact_status = (contact_status + ";" if contact_status else "") + "contact_not_in_source"
            defects += [x for x in contact_status.split(";") if x]
            if contact_status.startswith("contact_missed") or "contact_partial" in contact_status:
                recov.append({"input_json": input_json, "merge_status": sm.get("status", ""), "output_json": sm.get("output_json", ""),
                              "name": s((resumes[0].get("base_info") or {}).get("full_name")) if resumes else "",
                              "original_path": orig_path, "parser": parser,
                              "source_mobiles": ";".join(sorted(sm_m)), "source_emails": ";".join(sorted(sm_e)),
                              "json_mobiles": ";".join(sorted(jm)), "json_emails": ";".join(sorted(je)),
                              "status": contact_status})
        name = s((resumes[0].get("base_info") or {}).get("full_name")) if resumes else ""
        name_in = ""
        if full and name:
            nn = norm_src(name)
            if nn in nsrc:
                name_in = "exact"
            elif nn and all(ch in nsrc for ch in nn):
                name_in = "split_or_spaced"  # 姓、名分在不同单元格，或中间有标签
                # EN: Surname and given name in different cells, or with a label in between
                # JA: 姓と名が別のセルにある、または間にラベルがある
            elif re.search(r"[*＊]{2,}|[先女]\s*[生士]", full[:600]):
                name_in = "masked_in_source"  # 原文姓名被平台隐去，姓名来自文件名/其他来源
                # EN: The source name was hidden by the platform; the name comes from the file name / other sources
                # JA: 原文の氏名がプラットフォームで隠されており、氏名はファイル名や他の出所から取っている
            else:
                name_in = "not_found"
                defects.append("name_not_in_source")
        # 字段回源：只对“与原文同语种”的 resume 严格要求（其余可能是翻译版本）
        # EN: Field verification against the source: strictly required only for resumes "in the same language as the source" (the others may be translations)
        # JA: フィールドの原文照合：「原文と同じ言語」の resume だけに厳格に求める（他は翻訳版の可能性がある）
        ent_total = ent_found = 0
        per_res = []
        for i, r in enumerate(resumes):
            lang = s(r.get("resume_languge") or r.get("resume_language"))
            tot = fnd = 0
            miss = []
            for lst, fields in ENTITY_FIELDS.items():
                for j, it in enumerate(r.get(lst) or []):
                    for f in fields:
                        v = s(it.get(f))
                        nv = norm_src(v)
                        if len(nv) < 2:
                            continue
                        tot += 1
                        if nv in nsrc:
                            fnd += 1
                        else:
                            miss.append((f"resumes[{i}].{lst}[{j}].{f}", v))
            ratio = fnd / tot if tot else None
            per_res.append(f"{lang}:{fnd}/{tot}")
            # 与原文同语种（命中率 ≥ 0.5 视为原文语种；< 0.5 视为翻译/生成版本，单独标注）
            # EN: Same language as the source (a hit rate ≥ 0.5 is considered the source language; < 0.5 is considered a translated/generated version, flagged separately)
            # JA: 原文と同じ言語（ヒット率 0.5 以上なら原文の言語、0.5 未満なら翻訳・生成した版とみなして別に印を付ける）
            if full and tot:
                if ratio is not None and ratio >= 0.5:
                    ent_total += tot
                    ent_found += fnd
                    for fp, v in miss:
                        notin.append({"input_json": input_json, "original_path": orig_path, "parser": parser, "field_path": fp,
                                      "value": v[:120], "resume_language": lang, "resume_hit_ratio": f"{ratio:.2f}"})
                else:
                    defects.append(f"resume_{lang or 'x'}_not_from_source")
        if ent_total and ent_found < ent_total:
            defects.append("entity_not_in_source")
        # 条目：原文中每个日期区间的起始年月，JSON 的工作/教育/项目/培训中是否有同一起始年月
        # EN: Entries: for each date range's start year-month in the source, whether the JSON's work/education/projects/training has the same start year-month
        # JA: 項目：原文の各期間の開始年月について、JSON の職歴・学歴・プロジェクト・研修に同じ開始年月があるか
        src_ranges = 0
        missing_ranges = []
        if full:
            starts = set()
            for r in resumes:
                for lst, f in (("work_experiences", "position_start"), ("education_list", "school_start_ym"),
                               ("project_list", "start_ym"), ("training_list", "start_ym")):
                    for it in r.get(lst) or []:
                        k = C.ym_key(it.get(f))
                        if k:
                            starts.add(k)
            seen = set()
            for m in RANGE_RE.finditer(unicodedata.normalize("NFKC", full)):
                k = f"{m.group(1)}{int(m.group(2)):02d}"
                if k in seen or not (1 <= int(m.group(2)) <= 12):
                    continue
                seen.add(k)
                src_ranges += 1
                if k not in starts:
                    missing_ranges.append(k)
        json_items = max((sum(len(r.get(k) or []) for k in ("work_experiences", "education_list", "project_list", "training_list"))
                          for r in resumes), default=0)
        if len(missing_ranges) >= 2:
            defects.append("entries_missing")
        # 正文覆盖：逐行比对，行内 ≥60% 的 4 字片段出现在 JSON（raw_text + 结构化字段）中即视为已收录
        # EN: Body coverage: compare line by line; a line counts as included when ≥60% of its 4-character fragments appear in the JSON (raw_text + structured fields)
        # JA: 本文の網羅：行ごとに比較し、行内の 4 文字の断片の 60% 以上が JSON（raw_text + 構造化フィールド）に現れれば取り込み済みとする
        cov = ""
        lost_lines = []
        if full:
            tgt = shingles(norm_src(doc.get("raw_text") or "") + norm_src(json.dumps(sd, ensure_ascii=False)))
            tot_c = lost_c = 0
            for line in full.split("\n"):
                nl = norm_src(line)
                if len(nl) < 15 or BOILER_RE.search(line):
                    continue
                sh = shingles(nl)
                hit = len(sh & tgt) / len(sh) if sh else 1
                tot_c += len(nl)
                if hit < 0.6:
                    lost_c += len(nl)
                    lost_lines.append(line.strip()[:150])
            if tot_c:
                cov = f"{1 - lost_c / tot_c:.2f}"
                if lost_c / tot_c > 0.35 and lost_c > 200:
                    defects.append("content_lost")
                if lost_lines:
                    lost_rows.append({"input_json": input_json, "parser": parser, "original_path": orig_path,
                                      "coverage": cov, "lost_chars": lost_c, "lost_lines": " ‖ ".join(lost_lines[:12])})
        hi = issues.get(input_json, [])
        if hi:
            defects.append("field_issue_high")
        for d in set(defects) or {"ok"}:
            par_sum[parser][d] += 1
        par_sum[parser]["_files"] += 1
        rows.append({
            "input_json": input_json, "version": ver, "merge_status": sm.get("status", ""), "output_json": sm.get("output_json", ""),
            "original_path": orig_path, "original_count": len(origs), "ext": ext, "extract_method": ";".join(methods),
            "parser": parser, "source_chars": len(full), "source_mobiles": ";".join(sorted(sm_m)), "source_emails": ";".join(sorted(sm_e)),
            "json_mobiles": ";".join(sorted(jm)), "json_emails": ";".join(sorted(je)), "name": name, "name_in_source": name_in,
            "resumes_hit": " ".join(per_res), "source_date_ranges": src_ranges, "json_items": json_items, "missing_range_starts": " ".join(missing_ranges[:12]), "raw_coverage": cov,
            "high_issue_count": len(hi), "high_issue_types": ";".join(f"{k}×{v}" for k, v in collections.Counter(hi).most_common(6)),
            "defects": ";".join(sorted(set(defects))) or "ok",
        })

    def wcsv(name, data, fields=None):
        with open(a.out / name, "w", encoding="utf-8-sig", newline="") as fh:
            fields = fields or (list(data[0].keys()) if data else ["empty"])
            w = csv.DictWriter(fh, fieldnames=fields)
            w.writeheader()
            w.writerows(data)

    wcsv("source_audit_ledger.csv", rows)
    wcsv("contact_recovery.csv", recov)
    wcsv("field_not_in_source.csv", notin)
    wcsv("content_lost_lines.csv", lost_rows)
    keys = sorted({k for c in par_sum.values() for k in c})
    ps = [{"parser": p, **{k: c.get(k, 0) for k in keys}} for p, c in sorted(par_sum.items(), key=lambda x: -x[1]["_files"])]
    wcsv("parser_summary.csv", ps, ["parser"] + keys)
    summ = {"inputs": len(rows), "defects": dict(collections.Counter(d for r in rows for d in r["defects"].split(";")).most_common()),
            "contact_recovery": len(recov),
            "no_contact_with_source_contact": sum(1 for r in recov if r["merge_status"] == "no_contact")}
    (a.out / "source_audit_summary.json").write_text(json.dumps(summ, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(summ, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
