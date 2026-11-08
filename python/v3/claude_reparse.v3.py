#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
claude_reparse.v3.py —— 第二步：按模板用新解析器从原文重新生成 resume，与旧 JSON 对照原文比较，择优替换。

对每个输入 JSON（原文被识别为指定模板的）：
  1. 新解析器解析原文 → 新的中文 resume
  2. 对照原文分别给旧 JSON、新 JSON 打分：
       coverage        原文正文被收录的比例（逐行，≥60% 的 4 字片段命中算收录）
       missing_ranges  原文中日期区间的起始年月，在 JSON 条目里找不到的个数
       contacts_found  原文中候选人手机号/邮箱被收录的个数
       not_in_source   JSON 公司/学校/职位等值在原文中找不到的个数
       high_issues     claude_merge_checks 的 high 级字段问题个数
       name_ok         姓名有效且在原文中
  3. 新的不比旧的差（每项都不差）且至少一项更好 → 替换；否则保留旧的。每个文件的比较写入台账。
  4. 替换时：resumes 中的中文版换成新解析结果；旧 JSON 里的其他语种版本原样保留；source/dates 保留并记录 reparse 信息。

输出（--out，可与第一步的修复目录合并使用）：<out>/v2/*.json、<out>/v1/*.json、reparse_ledger.csv、reparse_summary.json
先读取 --base-overlay（第一步的修复副本）作为“旧 JSON”，保证第一步补回的联系方式参与比较。

EN: claude_reparse.v3.py -- step 2: regenerate resumes from the source with the new parsers by template, compare with the old JSON against the source, and replace with the better one.

For each input JSON (whose source is recognised as the given template):
  1. The new parser parses the source → a new Chinese resume
  2. Score the old JSON and the new JSON against the source:
       coverage        proportion of the source body included (line by line; a line counts as included when ≥60% of its 4-character fragments hit)
       missing_ranges  number of start year-months of date ranges in the source not found in JSON entries
       contacts_found  number of the candidate's mobiles/e-mails in the source that are included
       not_in_source   number of JSON values (company/school/position etc.) not found in the source
       high_issues     number of high-severity field issues from claude_merge_checks
       name_ok         the name is valid and in the source
  3. If the new one is no worse than the old (no worse on every item) and better on at least one → replace; otherwise keep the old. The comparison for each file is written to the ledger.
  4. On replacement: the Chinese version in resumes is replaced with the new parse; other language versions in the old JSON are kept as they are; source/dates are kept and reparse info is recorded.

Output (--out, can be used together with step 1's repair directory): <out>/v2/*.json, <out>/v1/*.json, reparse_ledger.csv, reparse_summary.json
First read --base-overlay (step 1's repair copies) as the "old JSON", so contacts restored in step 1 take part in the comparison.

JA: claude_reparse.v3.py —— 第 2 段階：テンプレートごとに新しいパーサーで原文から resume を作り直し、旧 JSON と原文に照らして比較し、よい方に置き換える。

各入力 JSON（原文が指定のテンプレートと認識されたもの）について：
  1. 新しいパーサーで原文を解析 → 新しい中国語の resume
  2. 原文に照らして旧 JSON と新 JSON をそれぞれ採点する：
       coverage        原文の本文が取り込まれた割合（行ごとに、4 文字の断片の 60% 以上がヒットすれば取り込み済みとする）
       missing_ranges  原文の期間の開始年月のうち、JSON の項目に見つからないものの数
       contacts_found  原文にある候補者の携帯番号・メールのうち、取り込まれたものの数
       not_in_source   JSON の会社・学校・職位などの値のうち、原文に見つからないものの数
       high_issues     claude_merge_checks の high のフィールドの問題の数
       name_ok         氏名が有効で、原文にある
  3. 新しい方が旧いものより悪くなく（すべての項目で悪くない）、少なくとも 1 項目でよければ → 置き換える。そうでなければ旧いものを残す。各ファイルの比較は台帳に書く。
  4. 置き換える際：resumes の中国語版を新しい解析結果に置き換え、旧 JSON の他の言語の版はそのまま残す。source/dates は残し、reparse の情報を記録する。

出力（--out。第 1 段階の修復ディレクトリと合わせて使える）：<out>/v2/*.json、<out>/v1/*.json、reparse_ledger.csv、reparse_summary.json
まず --base-overlay（第 1 段階の修復コピー）を「旧 JSON」として読み、第 1 段階で補った連絡先も比較に参加させる。
"""

import argparse
import collections
import copy
import csv
import importlib.util
import json
import re
import sys
import unicodedata
from pathlib import Path, PureWindowsPath

HERE = Path(__file__).resolve().parent


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, HERE / file)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


C = load("c_rp", "claude_merge_common.v3.py")
K = load("k_rp", "claude_merge_checks.v3.py")
A = load("a_rp", "claude_source_audit.v3.py")
NF = load("nf_rp", "claude_name_fix.v3.py")
PARSERS = {"zhilian": load("p_cn", "claude_parse_cn_platform.v3.py"), "51job": load("p_51", "claude_parse_51job.v3.py"),
           "jp": load("p_jp", "claude_parse_jp.v3.py"), "report": load("p_rp", "claude_parse_zh_report.v3.py"),
           "table": load("p_tb", "claude_parse_zh_table.v3.py"), "en": load("p_en", "claude_parse_en.v3.py"),
           "liepin": load("p_lp", "claude_parse_liepin.v3.py"), "free": load("p_fr", "claude_parse_zh_free.v3.py")}
TEMPLATE_LANG = {"jp": "jp", "en": "en"}  # 其余模板产出中文 resume
# EN: The other templates produce Chinese resumes
# JA: その他のテンプレートは中国語の resume を出力する
s = C.s
ID_LINE_RE = re.compile(r"(身份证|ID\s*[:：]|^\s*J[MRS]\d{9}R|简历编号)")
# 日期写法因人而异（2003年9月～2006年7月 / 2003.09-2006.07），日期由 missing_ranges 单独衡量，覆盖率只看文字内容
# EN: Date notation varies by person (2003年9月～2006年7月 / 2003.09-2006.07); dates are measured separately by missing_ranges, and coverage looks only at text content
# JA: 日付の書き方は人によって異なる（2003年9月～2006年7月 / 2003.09-2006.07）。日付は missing_ranges で別に測り、網羅率は文字の内容だけを見る
DATE_TOK_RE = re.compile(r"(?:(?:19|20)\d{2}|(?:平成|昭和|令和)\s*\d{1,2})\s*[年./\-]\s*\d{1,2}\s*(?:月|[./\-]\s*\d{1,2}\s*日?)?(?:\s*\d{1,2}:\d{2}:\d{2})?"
                         r"\s*(?:[-~～–—―至]+|から)?\s*(?:まで)?|至今|現在(?:に至る)?")
# 表格里的栏目名本身不是内容（“所属部門  営業部  職位  営業担当”里的“所属部門”“職位”）
# EN: Section names in tables are not content themselves ("所属部門" and "職位" in "所属部門  営業部  職位  営業担当")
# JA: 表の中の欄の名前自体は内容ではない（「所属部門  営業部  職位  営業担当」の「所属部門」「職位」）
FIELD_LABELS = set("""所属部門 部署 職位 役職 部下 入社年月 退社年月 入学年月 卒業年月 会社名 社名 規模 資本 場所 学校名 専攻 学歴 職歴 職務内容 業務内容 事業概要 事業内容
退職理由 転職理由 氏名 名前 ふりがな フリガナ 性別 生年月日 現住所 電話 携帯電話 固定電話 戸籍 民族 婚姻状況 希望職種 希望月収 勤務開始日 技能レベル 言語 資格証書
取得年 応用水準 パソコン ソフト名 水平 その他 身長 体重 出身地 国籍 資格 免許 趣味 特技 備考 年齢 入退社年月 社員数 公司性質 会社性質 職務概要 現在状況
姓名 性别 学历 专业 地点 毕业年月 入职年月 退职年月 规模 性质 职位 部门 工作内容 离职原因 联系电话 民族 籍贯 户口 婚姻状况 出生年月 拼音 外语 资格证书 取得年
应用水平 电脑 软件名 其他 希望职种 希望月薪 开始上班日 E-mail Email 学校 学部 学科""".split())
NATURE_RE = re.compile(r"(企业性质|规模|有海外工作|学习经验|如需联系方式|^未填写$|^保密$)")
ENT = {"work_experiences": ["company_name", "position"], "education_list": ["school_name", "school_major_name"],
       "certificate_list": ["certificate_name"], "project_list": ["project_name"], "training_list": ["organization_name", "training_name"]}


def pick_resume(resumes, lang):
    if lang == "zh":
        return next((r for r in resumes if C.resume_label(r) == "zh"), resumes[0] if resumes else {})
    return next((r for r in resumes if C.resume_label(r) == lang), None) or \
        next((r for r in resumes if C.detect_language(r)[0] == lang), resumes[0] if resumes else {})


FIELD_LABELS_N = {A.norm_src(x) for x in FIELD_LABELS}


def score(doc, src_text, src_m, src_e, lang="zh", ignore=()):
    sd = doc.get("structured_data") or {}
    resumes = sd.get("resumes") or []
    nsrc = A.norm_src(src_text)
    tstr = A.norm_src(json.dumps(sd, ensure_ascii=False))
    tgt = A.shingles(tstr)
    tot = lost = 0
    # 解析器认定不属于候选人本人的原文行（猎聘的公司简介、平台声明等）：新旧两份 JSON 评分时同样排除
    # EN: Source lines the parser judges not to belong to the candidate (Liepin company profiles, platform disclaimers, etc.): excluded likewise when scoring both the new and old JSON
    # JA: パーサーが候補者本人のものではないと判断した原文の行（Liepin の会社紹介・プラットフォームの声明など）：新旧 2 つの JSON の採点で同じく除外する
    ign_sh = A.shingles(A.norm_src(" ".join(ignore))) if ignore else set()
    for line in src_text.split("\n"):
        line = DATE_TOK_RE.sub("  ", line)
        nl = A.norm_src(line)
        if len(nl) < 15 or A.BOILER_RE.search(line) or ID_LINE_RE.search(line):
            continue
        sh = A.shingles(nl)
        if ign_sh and sh and len(sh & ign_sh) / len(sh) >= 0.8:
            continue
        tot += len(nl)
        if sh and len(sh & tgt) / len(sh) >= 0.6:
            continue
        # 一行里多个字段（“2015.09 - 2019.07  皖西学院  机械…  本科”）：逐段判断，去掉“标签：”
        # EN: Several fields on one line ("2015.09 - 2019.07  皖西学院  机械…  本科"): judge segment by segment and remove "label:"
        # JA: 1 行に複数のフィールド（「2015.09 - 2019.07  皖西学院  机械…  本科」）：部分ごとに判定し、「ラベル：」を除く
        toks = [A.norm_src(re.sub(r"^[^:：]{1,8}[:：]", "", x)) for x in re.split(r"\t+|\s{2,}|[|｜]", line)]
        toks = [x for x in toks if len(x) >= 2 and not NATURE_RE.search(x) and x not in FIELD_LABELS_N]
        if toks and all(x in tstr for x in toks):
            continue
        lost += len(nl)
    cov = 1 - lost / tot if tot else 1.0
    starts = set()
    for r in resumes:
        for lst, f in (("work_experiences", "position_start"), ("education_list", "school_start_ym"),
                       ("project_list", "start_ym"), ("training_list", "start_ym")):
            for it in r.get(lst) or []:
                k = C.ym_key(it.get(f))
                if k:
                    starts.add(k)
    miss = set()
    for m in A.RANGE_RE.finditer(unicodedata.normalize("NFKC", src_text)):
        if 1 <= int(m.group(2)) <= 12:
            k = f"{m.group(1)}{int(m.group(2)):02d}"
            if k not in starts:
                miss.add(k)
    jm, je = A.json_contacts(doc)
    found = len((jm & src_m) | (je & src_e))
    wrong_contacts = len(jm - src_m) + len(je - src_e)
    zh = pick_resume(resumes, lang)
    nis = 0
    for lst, fields in ENT.items():
        for it in zh.get(lst) or []:
            for f in fields:
                nv = A.norm_src(s(it.get(f)))
                if len(nv) >= 2 and nv not in nsrc:
                    nis += 1
    ry = s((doc.get("dates") or {}).get("resume_updated_date"))[:4]
    hi = [x for x in K.check_resume("r", zh, int(ry) if ry.isdigit() else None, lang) if x["severity"] == "high"]
    name = s((zh.get("base_info") or {}).get("full_name"))
    name_ok = C.name_quality(name)[0] == "valid" and A.norm_src(name) in nsrc
    return {"coverage": round(cov, 3), "missing_ranges": len(miss), "contacts_found": found, "wrong_contacts": wrong_contacts,
            "not_in_source": nis, "high_issues": len(hi), "name_ok": int(name_ok), "high_types": ";".join(sorted({x["issue_type"] for x in hi}))}


def better(new, old):
    """每项不差且至少一项更好。coverage 允许 0.01 的抖动。

    EN: No worse on every item and better on at least one. coverage allows a jitter of 0.01.

    JA: すべての項目で悪くなく、少なくとも 1 項目でよい。coverage は 0.01 の揺れを許容する。
    """
    not_worse = (new["coverage"] >= old["coverage"] - 0.01 and new["missing_ranges"] <= old["missing_ranges"]
                 and new["contacts_found"] >= old["contacts_found"] and new["wrong_contacts"] <= old["wrong_contacts"]
                 and new["not_in_source"] <= old["not_in_source"] and new["high_issues"] <= old["high_issues"]
                 and new["name_ok"] >= old["name_ok"])
    strictly = (new["coverage"] > old["coverage"] + 0.01 or new["missing_ranges"] < old["missing_ranges"]
                or new["contacts_found"] > old["contacts_found"] or new["wrong_contacts"] < old["wrong_contacts"]
                or new["not_in_source"] < old["not_in_source"] or new["high_issues"] < old["high_issues"]
                or new["name_ok"] > old["name_ok"])
    return not_worse and strictly, not_worse


def main():  # noqa: C901
    try:
        sys.stdout.reconfigure(errors="replace")
    except Exception:  # noqa: BLE001
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--template", required=True, choices=sorted(PARSERS))
    ap.add_argument("--pack-dir", type=Path, required=True)
    ap.add_argument("--text-dir", type=Path, required=True)
    ap.add_argument("--base-overlay", type=Path, help="第一步修复副本目录，作为旧 JSON 读取" " / Step-1 repair copy directory, read as the old JSON / 第 1 段階の修復コピーのディレクトリ（旧 JSON として読み込む）")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--exclude-dir", type=Path, action="append", default=[], help="这些目录里已有（被其他模板替换过）的 JSON 跳过" " / Skip the JSON already present in these directories (replaced by other templates) / これらのディレクトリにすでにある（ほかのテンプレートで置き換え済みの）JSON はスキップする")
    ap.add_argument("--dump-dir", type=Path, help="把每个新解析结果另存一份，便于人工核对" " / Save a separate copy of each new parse result for manual checking / 新しい解析結果ごとに別のコピーを保存し、人手での照合に使えるようにする")
    a = ap.parse_args()
    P = PARSERS[a.template]
    for v in ("v2", "v1"):
        (a.out / v).mkdir(parents=True, exist_ok=True)
    if a.dump_dir:
        a.dump_dir.mkdir(parents=True, exist_ok=True)
    manifest = collections.defaultdict(list)
    orig_path = {}
    for r in csv.DictReader(open(a.pack_dir / "manifest.csv", encoding="utf-8-sig")):
        if r["kind"] == "original" and r["exists"] == "True":
            manifest[r["input_json"]].append(r["pack_key"])
            orig_path[r["input_json"]] = r["path"]
    rows = []
    n = 0
    for input_json, keys in manifest.items():
        if len(keys) != 1:
            continue  # 多个原文合并成的 JSON 不在本步处理
            # EN: JSON merged from several sources are not handled in this step
            # JA: 複数の原文を統合した JSON はこの段階では処理しない
        tp = a.text_dir / "texts" / (Path(keys[0]).stem + ".txt")
        if not tp.exists():
            continue
        text = tp.read_text(encoding="utf-8")
        if not P.detect(text):
            continue
        n += 1
        if a.limit and n > a.limit:
            break
        ver = "v2" if "complete-v2" in input_json else "v1"
        name = PureWindowsPath(input_json).name
        if any((d / ver / name).is_file() for d in a.exclude_dir):
            continue
        base_p = (a.base_overlay / ver / name) if a.base_overlay else None
        src_p = base_p if base_p and base_p.is_file() else a.pack_dir / "inputs" / ver / name
        old = json.loads(src_p.read_text(encoding="utf-8"))
        parsed = P.parse(text)
        if parsed is None:
            continue
        new_res = parsed["resume"]
        new = copy.deepcopy(old)
        sd = new.setdefault("structured_data", {})
        lang = TEMPLATE_LANG.get(a.template, "zh")
        if lang != "zh" and parsed.get("content_lang") == "zh":
            # 日文模板但内容是中文（如 xls“日本語版”工作表里填的是中文）→ 按中文 resume 处理
            # EN: Japanese template with Chinese content (e.g. Chinese filled into an xls "日本語版" worksheet) → handled as a Chinese resume
            # JA: 日本語のテンプレートで内容が中国語（例：xls の「日本語版」のワークシートに中国語が記入されている）→ 中国語の resume として処理する
            lang = "zh"
        if lang == "zh":
            others = [r for r in (sd.get("resumes") or []) if C.resume_label(r) not in ("zh", "")]
            sd["resumes"] = [new_res] + others
        else:
            # 旧 JSON 里同语种（含被误标成 zh 的日文解析）一律由新结果替代；真正的中文版（如 xls 的中文工作表）保留在前
            # EN: Same-language versions in the old JSON (including Japanese parses mislabelled as zh) are all replaced by the new result; a real Chinese version (e.g. the Chinese worksheet of an xls) is kept in front
            # JA: 旧 JSON の同じ言語の版（zh と誤ってラベル付けされた日本語の解析を含む）はすべて新しい結果で置き換える。本当の中国語版（例：xls の中国語のワークシート）は前に残す
            keep_zh = [r for r in (sd.get("resumes") or []) if C.resume_label(r) in ("zh", "") and C.detect_language(r)[0] == "zh"
                       and (r.get("work_experiences") or r.get("education_list"))] if parsed.get("has_zh_part") else []
            others = [r for r in (sd.get("resumes") or []) if C.resume_label(r) not in ("zh", "", lang) and C.detect_language(r)[0] != lang]
            sd["resumes"] = keep_zh[:1] + [new_res] + others
        if parsed["updated"] and not s((new.get("dates") or {}).get("resume_updated_date")):
            new.setdefault("dates", {})["resume_updated_date"] = parsed["updated"] + " 00:00:00"
        sm, se = A.source_contacts(text)
        # 旧 JSON 里（第一步已按原文核实的）联系方式，新解析漏掉的补上——只补原文里确实有的
        # EN: Contacts in the old JSON (already verified against the source in step 1) that the new parse missed are added — only those really present in the source
        # JA: 旧 JSON にあり（第 1 段階で原文と照合済み）、新しい解析が漏らした連絡先を補う — 原文に実際にあるものだけ
        om, oe = A.json_contacts(old)
        nm, ne = A.json_contacts(new)
        b = new_res.setdefault("base_info", {})
        # 原文里标在“家庭电话/家属电话”后面的手机号，新解析已有本人手机号时不补（多为家人号码）
        # EN: Mobile numbers marked after "家庭电话/家属电话" (home / family phone) in the source are not added when the new parse already has the person's own mobile (usually a family member's number)
        # JA: 原文で「家庭电话／家属电话」（自宅・家族の電話）の後に書かれた携帯番号は、新しい解析にすでに本人の携帯番号があれば補わない（家族の番号であることが多い）
        fam = {C.classify_phone(x)[1] for x in re.findall(r"(?:家庭电话|家庭電話|家庭联系电话|家属电话|家人电话)\s*[:：]?\s*([+\d][\d\s\-]{9,16}\d)", text)}
        add_m = sorted((om & sm) - nm - (fam if nm else set()))
        add_e = sorted((oe & se) - ne)
        if add_m:
            b["phone"] = "; ".join([x for x in [s(b.get("phone"))] if x] + add_m)
        if add_e:
            b["email"] = "; ".join([x for x in [s(b.get("email"))] if x] + add_e)
        # 新解析的姓名按原文姓名栏 / 文件名核对一遍（与 claude_name_fix 同一规则），再与旧 JSON 比较
        # EN: The new parse's name is checked once against the source name field / file name (the same rules as claude_name_fix), then compared with the old JSON
        # JA: 新しい解析の氏名を原文の氏名欄・ファイル名と 1 回照合し（claude_name_fix と同じルール）、その後旧 JSON と比較する
        act, nn, _why, _ev, _best = NF.decide(s(b.get("full_name")), text, [orig_path[input_json]])
        if act == "fix":
            b["full_name"] = nn
        if C.name_quality(s(b.get("full_name")))[0] != "valid":
            # 新解析没取到有效姓名（原文只有“刘**”“王女士”），旧 JSON 里的有效姓名保留
            # EN: When the new parse got no valid name (the source has only "刘**", "王女士"), keep the valid name in the old JSON
            # JA: 新しい解析で有効な氏名が取れなかった場合（原文に「刘**」「王女士」しかない）は、旧 JSON の有効な氏名を残す
            on = s((pick_resume((old.get("structured_data") or {}).get("resumes") or [], lang).get("base_info") or {}).get("full_name"))
            # 只保留原文正文或文件名里确有的姓名（猎聘页面常把姓名显示成“林先生”，真名只在文件名里）
            # EN: Keep only names that really occur in the source body or the file name (Liepin pages often show the name as "林先生" (Mr Lin); the real name is only in the file name)
            # JA: 原文の本文かファイル名に実際にある氏名だけを残す（Liepin のページは氏名を「林先生」（林さん）と表示することが多く、本当の氏名はファイル名にしかない）
            if C.name_quality(on)[0] == "valid" and (NF.simp(on) in NF.simp(text) or NF.simp(on) in NF.simp(PureWindowsPath(orig_path[input_json]).stem)):
                b["full_name"] = on
        ign = parsed.get("ignored_lines") or ()
        so = score(old, text, sm, se, lang, ign)
        sn = score(new, text, sm, se, lang, ign)
        use, not_worse = better(sn, so)
        decision = "replace" if use else ("equal_keep_old" if not_worse else "keep_old")
        if use:
            # 顶层快照、raw_text 按新 resumes 重建，旧的（可能含别人联系方式的）不再留存
            # EN: Top-level snapshots and raw_text are rebuilt from the new resumes; the old ones (which may contain someone else's contacts) are not kept
            # JA: トップレベルのスナップショットと raw_text は新しい resumes から作り直し、古いもの（他人の連絡先を含む可能性がある）は残さない
            sd.update(C.build_snapshots(sd["resumes"]))
            new["raw_text"] = C.build_raw_text(sd["resumes"])
            new.setdefault("source_repair", {})["claude_reparse_v3"] = {"template": a.template, "parser": P.__name__,
                                                                        "unmapped_sections": parsed["unmapped"], "old_score": so, "new_score": sn}
            (a.out / ver / name).write_text(json.dumps(new, ensure_ascii=False, indent=2), encoding="utf-8")
        if a.dump_dir:
            (a.dump_dir / f"{ver}__{name}").write_text(json.dumps({"decision": decision, "old": so, "new": sn, "resume": new_res,
                                                                   "unmapped": parsed["unmapped"]}, ensure_ascii=False, indent=1), encoding="utf-8")
        rows.append({"input_json": input_json, "version": ver, "pack_key": keys[0], "decision": decision,
                     **{f"old_{k}": v for k, v in so.items()}, **{f"new_{k}": v for k, v in sn.items()},
                     "unmapped": ";".join(parsed["unmapped"])})
    with open(a.out / "reparse_ledger.csv", "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    dec = collections.Counter(r["decision"] for r in rows)
    agg = {}
    for k in ("coverage", "missing_ranges", "contacts_found", "wrong_contacts", "not_in_source", "high_issues", "name_ok"):
        agg[k] = {"old": round(sum(float(r[f"old_{k}"]) for r in rows) / max(len(rows), 1), 3),
                  "new": round(sum(float(r[f"new_{k}"]) for r in rows) / max(len(rows), 1), 3)}
    summ = {"template": a.template, "files": len(rows), "decisions": dict(dec), "avg": agg}
    (a.out / "reparse_summary.json").write_text(json.dumps(summ, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(summ, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
