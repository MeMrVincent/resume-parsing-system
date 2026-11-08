#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
claude_source_repair.v3.py —— 第一步回源修复：把原文件里有、解析器漏掉的手机号 / 邮箱 / 姓名补回 JSON。

原则：
  * 不改原 JSON：修复后的副本写到 <out>/v2/、<out>/v1/（文件名与原 JSON 相同），merge 用 --repair-dir 叠加读取。
  * 只补不删：已有的联系方式、姓名保持不动（姓名只在原值无效时替换）。
  * 每一处改动写 repair_ledger.csv：原值、新值、原文证据片段。
  * 排除不属于候选人的联系方式：
      - 同一号码/邮箱出现在 ≥3 个不同姓名的原文里（顾问、HR、中介等公共联系方式）
      - 号码前 20 字内有“顾问/推荐人/联系人/公司电话/单位电话/紧急联系/担当者/Consultant/HR”等字样
      - 平台打码（****）不补
      - 已被 merge 认定属于另一个姓名的联系方式不补

输入：--pack-dir（inputs/、manifest.csv）、--text-dir（texts/、extract_ledger.csv）、--audit-dir（source_audit_ledger.csv）、--merge-run

EN: claude_source_repair.v3.py -- step 1 of source repair: restore into the JSON the mobiles / e-mails / names that are in the original file but were missed by the parser.

Principles:
  * The original JSON is not changed: repaired copies are written to <out>/v2/, <out>/v1/ (same file names as the original JSON), and merge overlays them with --repair-dir.
  * Only add, never delete: existing contacts and names stay as they are (the name is replaced only when the original value is invalid).
  * Every change is written to repair_ledger.csv: old value, new value, evidence snippet from the source.
  * Exclude contacts that do not belong to the candidate:
      - the same number/e-mail appears in the sources of ≥3 different names (public contacts of consultants, HR, agencies, etc.)
      - within 20 characters before the number there are words like "顾问/推荐人/联系人/公司电话/单位电话/紧急联系/担当者/Consultant/HR" (consultant / referrer / contact person / company phone / work phone / emergency contact / person in charge)
      - platform-masked values (****) are not added
      - contacts already assigned by merge to another name are not added

Input: --pack-dir (inputs/, manifest.csv), --text-dir (texts/, extract_ledger.csv), --audit-dir (source_audit_ledger.csv), --merge-run

JA: claude_source_repair.v3.py —— 原文に基づく修復の第 1 段階：元のファイルにあるのにパーサーが漏らした携帯番号・メール・氏名を JSON に補い戻す。

原則：
  * 元の JSON は変更しない：修復したコピーを <out>/v2/、<out>/v1/（ファイル名は元の JSON と同じ）に書き、merge は --repair-dir で重ねて読む。
  * 補うだけで削除はしない：既存の連絡先・氏名はそのまま（氏名は元の値が無効な場合だけ置き換える）。
  * すべての変更を repair_ledger.csv に書く：元の値、新しい値、原文の証拠の抜粋。
  * 候補者本人のものではない連絡先を除外する：
      - 同じ番号・メールが 3 人以上の異なる氏名の原文に現れる（コンサルタント・人事・仲介などの共用の連絡先）
      - 番号の前 20 文字以内に「顾问／推荐人／联系人／公司电话／单位电话／紧急联系／担当者／Consultant／HR」（コンサルタント・推薦者・連絡担当・会社の電話・勤務先の電話・緊急連絡先・担当者）などの語がある
      - プラットフォームでマスクされたもの（****）は補わない
      - merge がすでに別の氏名のものと判定した連絡先は補わない

入力：--pack-dir（inputs/、manifest.csv）、--text-dir（texts/、extract_ledger.csv）、--audit-dir（source_audit_ledger.csv）、--merge-run
"""

import argparse
import collections
import copy
import csv
import json
import re
import sys
import unicodedata
from pathlib import Path, PureWindowsPath
import importlib.util

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("claude_merge_common_v3_sr", HERE / "claude_merge_common.v3.py")
C = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(C)
s = C.s

OTHER_PERSON_RE = re.compile(r"(顾问|顧問|推荐人|推薦人|推荐顾问|联系人|联络人|連絡担当|担当者|公司电话|公司電話|单位电话|办公电话|紧急|緊急|家属|家族|家庭电话|家庭電話|父|母|配偶|"
                             r"consultant|recruiter|\bHR\b|人事|紐培|纽培|蓝杰|Newpage|Fellowship|猎头|獵頭|reference|证明人)", re.I)
CONTACT_LABEL_RE = re.compile(r"(手机|手機|电话|電話|携帯|移动|联系|連絡|mobile|phone|tel|cell|e-?mail|邮箱|邮件|メール|mail)", re.I)
NAME_PREFIX_RE = re.compile(r"^([一-鿿]{2,4})\s*[（(_\s]")
GENERIC_NAME_RE = re.compile(r"^(编号|未知|简|简历|姓名|[一-鿿][先女][生士]|[一-鿿]{1,2}(先生|女士|小姐))$")
def standalone_in(mval: str, text: str) -> bool:
    """手机号在原文中是否以独立号码出现（允许 138-1865-7745 / 138 1865 7745 / +86 写法；前面不能紧挨字母或数字）。

    EN: Whether a mobile number appears in the source as a standalone number (allowing forms like 138-1865-7745 / 138 1865 7745 / +86; it must not be immediately preceded by a letter or digit).

    JA: 携帯番号が原文に独立した番号として現れるか（138-1865-7745 / 138 1865 7745 / +86 の書き方を許容し、直前に英字や数字が隣接していないこと）。
    """
    pat = r"(?<![A-Za-z0-9])(?:\+?86[\s\-]?)?" + mval[:3] + r"[\s\-]?" + mval[3:7] + r"[\s\-]?" + mval[7:] + r"(?![0-9])"
    return re.search(pat, text) is not None
HAN_NAME_BEFORE_RE = re.compile(r"([一-鿿]{2,3})\s*[:：]?\s*$")
BAD_NAME_WORD_RE = re.compile(r"(描述|经历|经验|项目|信息|简历|履歴|職歴|学歴|资料|评价|介绍|联系|电话|邮箱|地址|公司|学校|大学|学院|"
                              r"号|码|特長|特长|小区|编号|区|路|市|省|县|室|楼|村|镇|街|弄|手机|微信|其他|其它)")
NAME_LABEL_RE = re.compile(r"(?:姓\s*名|氏\s*名|名\s*前|Name)\s*[：:]\s*([一-鿿]{2,4}|[A-Za-z][A-Za-z .'\-]{1,30})")


def name_key(n: str) -> str:
    """同一个人的不同写法归成一个键：繁体/日文字形转简体；英文名不分大小写、不分姓名顺序。

    EN: Different spellings of the same person map to one key: traditional/Japanese glyphs converted to simplified; English names case-insensitive and independent of name order.

    JA: 同じ人の異なる表記を 1 つのキーにまとめる：繁体字・日本の字体は簡体字に変換し、英語名は大文字小文字と姓名の順序を区別しない。
    """
    n = C.s(n)
    if re.search(r"[一-鿿]", n):
        return C.name_key(C.to_simplified_name(n))
    return " ".join(sorted(re.findall(r"[a-z]+", n.lower())))


def same_script_match(nk: str, owners) -> bool:
    """merge 已认定的姓名里，与本 JSON 姓名同一书写系统的有没有它；同一书写系统里都没有同类姓名时不判冲突。

    EN: Whether, among the names already established by merge, there is one in the same writing system as this JSON's name; when the same writing system has no name of that kind, no conflict is declared.

    JA: merge がすでに確定した氏名の中に、この JSON の氏名と同じ表記体系のものがあるか。同じ表記体系に同種の氏名がまったくない場合は、衝突とは判定しない。
    """
    is_cn = bool(re.search(r"[一-鿿]", nk))
    same = {o for o in owners if bool(re.search(r"[一-鿿]", o)) == is_cn}
    return (nk in same) if same else True


def distinct_people(keys) -> int:
    """一个联系方式关联的不同姓名数：有中文名时只数中文名（英文拼写与中文名无法逐字对应，不单独计数）。

    EN: Number of different names linked to one contact: when there are Chinese names, count only Chinese names (English spellings cannot be matched character by character with Chinese names, so they are not counted separately).

    JA: 1 つの連絡先に結び付く異なる氏名の数：中国語名がある場合は中国語名だけを数える（英語の綴りは中国語名と 1 文字ずつ対応しないため、別に数えない）。
    """
    cn = {k for k in keys if re.search(r"[一-鿿]", k)}
    return len(cn) if cn else len(keys)


def contacts_with_pos(text: str):
    """[(kind, value, start, end)]；粘连的“手机号+邮箱”拆开。

    EN: [(kind, value, start, end)]; stuck-together "mobile + e-mail" are split.

    JA: [(kind, value, start, end)]。くっついた「携帯番号 + メール」は分ける。
    """
    t = unicodedata.normalize("NFKC", text)
    out = []
    for m in C.MOBILE_FIND.finditer(t):
        k, v = C.classify_phone(m.group(0))
        if k == "mobile":
            out.append(("m", v, m.start(), m.end()))
    for m in C.EMAIL_FIND.finditer(t):
        parts = C.split_glued(m.group(0))
        for part in parts:
            if "@" in part:
                k, v = C.classify_email(part)
                if k == "email":
                    out.append(("e", v, m.start(), m.end()))
            else:
                k, v = C.classify_phone(part)
                if k == "mobile":
                    out.append(("m", v, m.start(), m.end()))
    return t, out


def main():  # noqa: C901
    try:
        sys.stdout.reconfigure(errors="replace")
    except Exception:  # noqa: BLE001
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--pack-dir", type=Path, required=True)
    ap.add_argument("--text-dir", type=Path, required=True)
    ap.add_argument("--audit-dir", type=Path, required=True)
    ap.add_argument("--merge-run", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--shared-threshold", type=int, default=3)
    a = ap.parse_args()
    for v in ("v2", "v1"):
        (a.out / v).mkdir(parents=True, exist_ok=True)

    manifest = collections.defaultdict(list)
    orig_by_json = collections.defaultdict(list)
    for r in csv.DictReader(open(a.pack_dir / "manifest.csv", encoding="utf-8-sig")):
        if r["kind"] == "original":
            orig_by_json[r["input_json"]].append(r["path"])
        if r["kind"] == "original" and r["exists"] == "True":
            manifest[r["input_json"]].append(r["pack_key"])
    extract_ok = {r["pack_key"] for r in csv.DictReader(open(a.text_dir / "extract_ledger.csv", encoding="utf-8-sig")) if r["ok"] == "True"}
    audit = {r["input_json"]: r for r in csv.DictReader(open(a.audit_dir / "source_audit_ledger.csv", encoding="utf-8-sig"))}

    # merge 已认定的“联系方式 → 姓名”
    # EN: "contact → name" mappings already established by merge
    # JA: merge がすでに確定した「連絡先 → 氏名」
    owner = collections.defaultdict(set)
    for r in csv.DictReader(open(a.merge_run / "ledgers" / "source_map.csv", encoding="utf-8-sig")):
        if r["status"] in ("formal", "needs_fix", "pending_translation", "duplicate") and r["contacts"]:
            for c in r["contacts"].split(";"):
                if c:
                    owner[c.lower()].add(name_key(r["name"]))

    def load_text(key):
        p = a.text_dir / "texts" / (Path(key).stem + ".txt")
        return p.read_text(encoding="utf-8") if p.exists() else ""

    # 第一遍：统计每个联系方式在多少个不同姓名的原文里出现（识别顾问/HR 等公共联系方式）
    # EN: First pass: count in how many sources with different names each contact appears (to identify public contacts of consultants/HR, etc.)
    # JA: 1 回目：各連絡先が、異なる氏名の原文いくつに現れるかを数える（コンサルタント・人事などの共用の連絡先を識別するため）
    seen_names = collections.defaultdict(set)
    docs = {}
    for input_json, keys in manifest.items():
        au = audit.get(input_json)
        if not au:
            continue
        nm = name_key(au["name"]) if C.name_quality(au["name"])[0] == "valid" else ""
        for k in keys:
            if k not in extract_ok:
                continue
            _, cs = contacts_with_pos(load_text(k))
            for kind, v, _, _ in cs:
                if nm:
                    seen_names[v.lower()].add(nm)
    shared = {c for c, ns in seen_names.items() if distinct_people(ns) >= a.shared_threshold}
    print(f"原文中出现于 ≥{a.shared_threshold} 个不同姓名的公共联系方式：{len(shared)} 个" f" / Public contacts that appear in the source texts of ≥{a.shared_threshold} different names: {len(shared)} / 原文で {a.shared_threshold} 個以上の異なる氏名に現れる共用の連絡先：{len(shared)} 件", flush=True)

    ledger, skipped = [], []
    changed_files = 0
    for input_json, keys in manifest.items():
        au = audit.get(input_json)
        if not au:
            continue
        defects = au["defects"]
        name_bad = C.name_quality(au["name"])[0] != "valid"
        if "source_missing" in defects or "source_unreadable" in defects:
            continue
        ver = au["version"]
        src_json = a.pack_dir / "inputs" / ver / PureWindowsPath(input_json).name
        doc = json.loads(src_json.read_text(encoding="utf-8"))
        new = copy.deepcopy(doc)
        resumes = (new.get("structured_data") or {}).get("resumes") or []
        if not resumes:
            continue
        texts = [load_text(k) for k in keys if k in extract_ok]
        orig_paths = orig_by_json.get(input_json, [])
        all_m, all_e = set(), set()
        for t0 in texts:
            for kind, v, _, _ in contacts_with_pos(t0)[1]:
                (all_m if kind == "m" else all_e).add(v.lower())
        multi_person = len(all_m) > 3 or len(all_e) > 3
        json_m, json_e = set(), set()
        for r in resumes:
            for _f, kind, val, _raw in C.contacts_from_base(r.get("base_info") or {}):
                if kind in ("mobile", "intl_mobile"):
                    json_m.add(val)
                elif kind == "email":
                    json_e.add(val.lower())
        name = s((resumes[0].get("base_info") or {}).get("full_name"))
        nk = name_key(name)
        # JSON 里的手机号在原文中只出现在编号/日期里（如 R13800000015、19780511…），不是真实号码 → 移除
        # EN: A mobile number in the JSON that appears in the source only inside a number/date (e.g. R13800000015, 19780511…) is not a real number → remove
        # JA: JSON の携帯番号が原文では番号や日付の中にしか現れない（例：R13800000015、19780511…）場合は本当の番号ではない → 除去する
        joined = "\n".join(unicodedata.normalize("NFKC", x) for x in texts)
        bogus = []
        if texts:
            for mval in sorted(json_m):
                if not re.fullmatch(r"1\d{10}", mval):
                    continue
                if standalone_in(mval, joined):
                    continue
                names_digits = re.sub(r"\D", "", " ".join(PureWindowsPath(p).name for p in orig_paths))
                flat = re.sub(r"[\s\-]", "", joined)
                if mval in names_digits:
                    bogus.append((mval, "号码取自文件名里的时间戳/编号，原文中没有这个手机号"))
                elif mval in flat:
                    bogus.append((mval, "号码取自原文中的编号/身份证号/ID，不是独立手机号"))
                else:
                    bogus.append((mval, "原文中找不到该号码"))
        add_m, add_e = [], []
        # 姓名无效且修不好、或原文是多人名单（>3 个手机号/邮箱）时，不补联系方式
        # EN: When the name is invalid and cannot be fixed, or the source is a list of many people (>3 mobiles/e-mails), do not add contacts
        # JA: 氏名が無効で修正できない場合や、原文が複数人の名簿（携帯番号・メールが 3 つ超）の場合は、連絡先を補わない
        fixable_name = (not name_bad) or bool(NAME_PREFIX_RE.match(name)) or any(
            NAME_LABEL_RE.search(unicodedata.normalize("NFKC", x)) for x in texts)
        if multi_person or not fixable_name:
            skipped.append({"input_json": input_json, "value": "", "reason": "原文为多人名单" if multi_person else "姓名无效且原文无姓名栏，不补联系方式",
                            "evidence": f"原文手机号 {len(all_m)} 个、邮箱 {len(all_e)} 个"})
            texts_for_contacts = []
        else:
            texts_for_contacts = texts
        for t0 in texts_for_contacts:
            t, cs = contacts_with_pos(t0)
            for kind, v, st, en in cs:
                vl = v.lower()
                if (kind == "m" and v in json_m) or (kind == "e" and vl in json_e) or v in add_m or vl in add_e:
                    continue
                ctx_before = t[max(0, st - 20):st]
                snippet = t[max(0, st - 30):en + 10].replace("\n", " ").replace("\t", " ")
                reason = ""
                if vl in shared:
                    reason = f"公共联系方式（出现在 {distinct_people(seen_names[vl])} 个不同姓名的原文中）"
                elif OTHER_PERSON_RE.search(ctx_before):
                    reason = "前文为顾问/联系人/公司电话等，不属于候选人"
                elif (kind == "m" and HAN_NAME_BEFORE_RE.search(ctx_before) and not CONTACT_LABEL_RE.search(ctx_before)
                      and C.name_quality(HAN_NAME_BEFORE_RE.search(ctx_before).group(1))[0] == "valid"
                      and nk and name_key(HAN_NAME_BEFORE_RE.search(ctx_before).group(1)) != nk
                      and not BAD_NAME_WORD_RE.search(HAN_NAME_BEFORE_RE.search(ctx_before).group(1))):
                    reason = "号码前是另一个人名（" + HAN_NAME_BEFORE_RE.search(ctx_before).group(1) + "），不属于候选人"
                elif st > max(1500, len(t) * 0.4) and not CONTACT_LABEL_RE.search(ctx_before):
                    reason = "位于正文后部且无联系方式标签（多为证明人/同事），不补"
                elif owner.get(vl) and nk and not same_script_match(nk, owner[vl]):
                    reason = "merge 中已属于另一个姓名：" + ",".join(sorted(owner[vl]))[:40]
                if reason:
                    skipped.append({"input_json": input_json, "value": v, "reason": reason, "evidence": snippet[:120]})
                    continue
                (add_m if kind == "m" else add_e).append(v if kind == "m" else vl)
                ledger.append({"input_json": input_json, "version": ver, "name": name, "field": "phone" if kind == "m" else "email",
                               "old_value": s((resumes[0].get("base_info") or {}).get("phone" if kind == "m" else "email")),
                               "added_value": v if kind == "m" else vl, "evidence": snippet[:120],
                               "original_path": au["original_path"], "parser": au["parser"]})
        new_name = ""
        pm = NAME_PREFIX_RE.match(name) if name_bad else None
        if pm and C.name_quality(pm.group(1))[0] == "valid":
            new_name = pm.group(1)
            ledger.append({"input_json": input_json, "version": ver, "name": name, "field": "full_name", "old_value": name,
                           "added_value": new_name, "evidence": "原姓名去掉括号/后缀",
                           "original_path": au["original_path"], "parser": au["parser"]})
        elif name_bad:
            for t0 in texts:
                m = NAME_LABEL_RE.search(unicodedata.normalize("NFKC", t0))
                if m and C.name_quality(m.group(1).strip())[0] == "valid" and not BAD_NAME_WORD_RE.search(m.group(1)):
                    new_name = m.group(1).strip()
                    ledger.append({"input_json": input_json, "version": ver, "name": name, "field": "full_name", "old_value": name,
                                   "added_value": new_name, "evidence": m.group(0)[:120],
                                   "original_path": au["original_path"], "parser": au["parser"]})
                    break
        # 只有原文里确有真实手机号（或本次补上了）时才移除假号码，避免把 JSON 清空
        # EN: Remove fake numbers only when the source really has a real mobile (or one was added this time), to avoid emptying the JSON
        # JA: 原文に本当の携帯番号が実際にある（または今回補った）場合だけ偽の番号を除去し、JSON が空にならないようにする
        real_src_m = {v for v in all_m if standalone_in(v, joined)}
        # 来自文件名、编号的假号码一律移除；原文里找不到的号码，只在原文另有真实手机号时移除（可能来自图片等无法核对的内容）
        # EN: Fake numbers coming from file names or ID numbers are always removed; numbers not found in the source are removed only when the source has another real mobile (they may come from unverifiable content such as images)
        # JA: ファイル名や番号から来た偽の番号は常に除去する。原文に見つからない番号は、原文に別の本当の携帯番号がある場合だけ除去する（画像など照合できない内容から来ている可能性がある）
        kept = []
        for bv, why in bogus:
            if why.startswith("原文中找不到") and not (real_src_m or add_m):
                continue
            kept.append(bv)
            ledger.append({"input_json": input_json, "version": ver, "name": name, "field": "phone_removed",
                           "old_value": bv, "added_value": "", "evidence": why,
                           "original_path": au["original_path"], "parser": au["parser"]})
        bogus = kept
        if not (add_m or add_e or new_name or bogus):
            continue
        for r in resumes:
            b = r.setdefault("base_info", {})
            if bogus:
                parts = [x for x in C.split_contact_values(b.get("phone"))
                         if C.classify_phone(x)[1] not in bogus]
                b["phone"] = "; ".join(parts)
            if add_m:
                b["phone"] = "; ".join([x for x in [s(b.get("phone"))] if x] + add_m)
            if add_e:
                b["email"] = "; ".join([x for x in [s(b.get("email"))] if x] + add_e)
            if new_name and C.name_quality(s(b.get("full_name")))[0] != "valid":
                b["full_name"] = new_name
        sd = new.get("structured_data") or {}
        if isinstance(sd.get("base_info"), dict):
            sd["base_info"] = copy.deepcopy(resumes[0].get("base_info"))
        new.setdefault("source_repair", {})["claude_source_repair_v3"] = {
            "added_phones": add_m, "added_emails": add_e, "removed_phones": bogus, "full_name": new_name,
            "evidence_source": au["original_path"]}
        (a.out / ver / src_json.name).write_text(json.dumps(new, ensure_ascii=False, indent=2), encoding="utf-8")
        changed_files += 1

    def wcsv(name, rows):
        with open(a.out / name, "w", encoding="utf-8-sig", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()) if rows else ["empty"])
            w.writeheader()
            w.writerows(rows)

    wcsv("repair_ledger.csv", ledger)
    wcsv("repair_skipped.csv", skipped)
    summ = {"changed_files": changed_files, "changes": dict(collections.Counter(r["field"] for r in ledger)),
            "skipped": dict(collections.Counter(r["reason"].split("（")[0].split("：")[0] for r in skipped)),
            "shared_contacts": len(shared)}
    (a.out / "repair_summary.json").write_text(json.dumps(summ, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(summ, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
