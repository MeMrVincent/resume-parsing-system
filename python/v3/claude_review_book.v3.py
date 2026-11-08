#!/usr/bin/env python3
"""第 7 批：人工复核表。

读取一次合并运行（--run-dir）的 needs_fix 输出、字段问题账、复核账，对照原文抽取片段，
生成一个 Excel：每行一个待人工确认的问题，附原文路径、JSON 路径、当前值、原文片段和建议。
只读，不改任何输入。

用法：python claude_review_book.v3.py --run-dir <merge 运行目录> --manifest <manifest.csv>
        --text-dir <原文文本目录> --name-review <name_review.csv> --out <xlsx>

EN: Batch 7: manual review workbook.

Reads one merge run's (--run-dir) needs_fix output, field-issue ledger and review ledger, extracts snippets from the source,
and produces an Excel file: one row per issue awaiting manual confirmation, with the source path, JSON path, current value, source snippet and suggestion.
Read-only; no input is changed.

Usage: python claude_review_book.v3.py --run-dir <merge run directory> --manifest <manifest.csv>
        --text-dir <source text directory> --name-review <name_review.csv> --out <xlsx>

JA: 第 7 バッチ：人手のレビュー用の表。

1 回の統合の実行（--run-dir）の needs_fix の出力・フィールドの問題の台帳・レビューの台帳を読み、原文から抜粋を取り出して、
Excel を作る：人手の確認を待つ問題ごとに 1 行で、原文のパス・JSON のパス・現在の値・原文の抜粋・提案を付ける。
読み取り専用で、入力は一切変更しない。

使い方：python claude_review_book.v3.py --run-dir <merge の実行ディレクトリ> --manifest <manifest.csv>
        --text-dir <原文のテキストのディレクトリ> --name-review <name_review.csv> --out <xlsx>
"""
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1] / "common"))
import rc_config as _rc  # noqa: E402  项目统一配置（python/common/rc_config.py）
# EN: noqa: E402  project-wide configuration (python/common/rc_config.py)
# JA: noqa: E402  プロジェクト共通設定（python/common/rc_config.py）
import argparse
import csv
import importlib.util
import json
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path, PureWindowsPath

from openpyxl import Workbook
from openpyxl.formatting.rule import FormulaRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
from openpyxl.worksheet.datavalidation import DataValidation

HERE = Path(__file__).resolve().parent


def _load(name, filename):
    sp = importlib.util.spec_from_file_location(name, HERE / filename)
    m = importlib.util.module_from_spec(sp)
    sys.modules[name] = m
    sp.loader.exec_module(m)
    return m


C = _load("claude_merge_common_v3_rb", "claude_merge_common.v3.py")
NF = _load("claude_name_fix_v3_rb", "claude_name_fix.v3.py")
N = _load("claude_merge_normalize_v3_rb", "claude_merge_normalize.v3.py")


def s(v):
    return "" if v is None else str(v)


FIELD_ZH = {
    "company_name": "公司", "position": "职位", "position_dept": "部门", "company_industry": "行业", "company_employees": "公司规模",
    "position_responsibilities": "职责", "position_start": "入职", "position_resigned": "离职", "position_salary": "薪资",
    "school_name": "学校", "school_major_name": "专业", "school_degree_type": "学历", "school_degree_rank": "学历级别",
    "school_start_ym": "入学", "school_end_ym": "毕业", "school_education_type": "学习形式",
    "full_name": "姓名", "birth_date": "出生日期", "address": "地址", "city": "城市", "household_registration": "户籍", "pr": "自我评价",
    "phone": "手机", "email": "邮箱", "certificate_name": "证书", "language_level": "语言等级",
}
LIST_ZH = {"work_experiences": "工作经历", "education_list": "学历", "certificate_list": "证书", "project_list": "项目",
           "training_list": "培训", "language_list": "语言", "skills_list": "技能", "expected_list": "求职意向", "base_info": "基本信息"}
LANG_ZH = {"zh": "中文", "jp": "日文", "en": "英文", "de": "德文", "fr": "法文", "ko": "韩文"}

ISSUE = {  # 类型: (中文说明, 建议做法)
# EN: Type: (Chinese description, suggested action)
# JA: 種類：(中国語の説明, 推奨する対応)
    "work_company_sentence": ("公司栏是一句话/句子片段", "对照原文找出这段经历的真实公司名填入“修正值”；句子本身是职责内容。原文也没有公司名就选“保持原样”。"),
    "work_company_missing": ("工作经历缺公司名", "在原文里找这段经历的公司名填入；原文确实没写公司就选“保持原样”。"),
    "school_missing": ("学历行没有学校名", "对照原文补学校名；这一行其实不是学历（证书、培训、其他内容）就选“删除此条”。"),
    "school_not_school": ("学校栏不像学校名", "改成原文里的学校名；这一行其实不是学历就选“删除此条”；确实是学校（如简称、海外学校）就选“保持原样”。"),
    "school_in_major": ("专业栏写的是学校名", "按建议把学校名移到学校栏；若学校栏已对、专业栏是重复就把专业清空。"),
    "school_sentence": ("学校栏是句子或带了标签", "改成原文里的学校名；整行不是学历就选“删除此条”。"),
    "position_as_company": ("公司栏写的是职位", "把这个值移到职位栏，公司名从原文补；原文没写公司（如家教、自由职业）就选“保持原样”。"),
    "degree_school_mismatch": ("中小学被标成大专及以上", "学历按学校改成 高中/中专/初中；若学校名其实是大学（名字被截断），在修正值里写对的学校名。"),
    "position_in_company": ("公司名里带了职位/兼职字样", "把职位部分移到职位栏，公司栏只留单位名。"),
    "date_reversed": ("开始日期晚于结束日期", "对照原文改日期，常见是两者写反。"),
    "name_invalid": ("姓名无效", "填写原文里的真实姓名。"),
    "school_in_work": ("学校写进了工作经历", "如果是上学经历，选“删除此条”（或移到学历）；如果是在学校工作，选“保持原样”。"),
    "cross_language_conflict": ("中文版与其他语言版本的值不一致", "对照原文确认哪个版本对，在修正值里写正确的值。"),
    "company_in_position": ("职位栏写的是公司名", "把公司名移到公司栏，职位从原文补。"),
    "no_work_no_education": ("整份简历既没有工作也没有学历", "打开原文看：原文就只有基本信息则“保持原样”；原文有内容则这份解析失败，请在备注说明。"),
    "honor_in_work": ("奖项/荣誉写进了工作经历", "建议“删除此条”（奖项不属于工作经历）。"),
    "section_leak_in_text": ("自我评价/职责里混入了其他栏目", "删掉混入的部分；看不出来就“保持原样”。"),
    "major_not_major": ("专业栏不是专业", "改成原文里的专业，没有就清空。"),
    "latin_in_zh_field": ("中文版里是英文值", "填中文写法；原文只有英文就“保持原样”。"),
    "dept_in_position": ("职位栏是部门名", "把部门名移到部门栏，职位从原文补。"),
    "garbled_text": ("乱码", "对照原文改正；原文也是乱码就“删除此条”或清空。"),
    "education_duplicate": ("学历重复", "确认是同一段学历就“删除此条”。"),
    "city_invalid": ("城市栏不是城市", "改成原文里的城市，没有就清空。"),
    "industry_in_company": ("公司栏写的是行业", "把公司名从原文补上。"),
    "birth_date_implausible": ("出生日期不合理", "按原文改；原文没有出生日期就清空。"),
    "punctuation_or_number_only": ("值只有标点或数字", "按原文改或清空。"),
    "salary_in_wrong_field": ("薪资写错了栏", "移到薪资栏。"),
    "school_major_swapped": ("学校与专业写反", "对调学校和专业。"),
    "position_in_dept": ("部门栏是职位", "把职位移到职位栏。"),
    "degree_rank_mismatch": ("学历级别与学历名称不一致", "按学历名称改级别。"),
    "industry_in_position": ("职位里粘了行业", "去掉行业部分。"),
    "dept_equals_position": ("部门与职位相同", "按原文区分部门和职位。"),
    "contact_glued": ("手机号与邮箱粘在一起", "拆开：手机号放手机，邮箱放邮箱。"),
    "section_heading_as_value": ("值是栏目名", "清空，或按原文改成真正的值。"),
    "other_field_in_address": ("地址栏里是其他信息", "改成原文里的地址，没有就清空。"),
}

EXTRA_SIMP = str.maketrans({"訳": "译", "瑤": "瑶", "寕": "宁", "寜": "宁"})
DECISIONS = ["按建议改", "改为修正值", "保持原样（不是错误）", "删除此条", "跳过"]
NAME_DECISIONS = ["采用建议姓名", "改为修正值", "保持原样", "跳过"]
CONFLICT_DECISIONS = ["是同一人", "不是同一人（需拆开）", "跳过"]


class Texts:
    def __init__(self, manifest, text_dir):
        self.by_path = {}
        for r in csv.DictReader(open(manifest, encoding="utf-8-sig")):
            if r["kind"] == "original" and r["pack_key"]:
                self.by_path.setdefault(r["path"], r["pack_key"])
        self.text_dir = Path(text_dir)
        self.cache = {}

    def get(self, orig_path):
        if orig_path in self.cache:
            return self.cache[orig_path]
        key = self.by_path.get(orig_path, "")
        t = ""
        if key:
            p = self.text_dir / (os.path.basename(key).split(".")[0] + ".txt")
            if p.exists():
                t = p.read_text(encoding="utf-8", errors="ignore")
        self.cache[orig_path] = t
        return t


def snippet(text, needles, width=70):
    """在原文里找第一个能找到的值，返回前后各 width 字的片段（换行显示为 ⏎）。

    EN: Find the first value that can be found in the source and return a snippet of width characters before and after (line breaks shown as ⏎).

    JA: 原文で見つかる最初の値を探し、前後それぞれ width 文字の抜粋を返す（改行は ⏎ で表示）。
    """
    if not text:
        return "（原文文本不可用）"
    flat = re.sub(r"[ \t\u3000]+", " ", text)
    for nd in needles:
        nd = s(nd).strip()
        if len(nd) < 2:
            continue
        for probe in (nd, nd[:20], nd[:10], nd[:6]):
            if len(probe) < 2:
                continue
            i = flat.find(probe)
            if i < 0:
                i = flat.find(re.sub(r"\s+", " ", probe))
            if i >= 0:
                a, b = max(0, i - width), min(len(flat), i + len(probe) + width)
                frag = ("…" if a > 0 else "") + flat[a:b] + ("…" if b < len(flat) else "")
                return re.sub(r"\n+", "⏎", frag).strip()
    return "（原文里找不到这个值）"


NAME_LABEL_RE = re.compile(r"(?:姓\s*名|氏\s*名|名\s*前|Name)\s*[：:]\s*([一-鿿](?:[ \u3000]?[一-鿿]){1,4}|[A-Za-z][A-Za-z .]{1,30}[A-Za-z])")


def label_names(text):
    out = []
    for m in NAME_LABEL_RE.finditer(NF.unicodedata_nfkc(text)):
        n = re.sub(r"[ \u3000]", "", m.group(1)) if re.match(r"[一-鿿]", m.group(1)) else m.group(1).strip()
        n = re.sub(r"(性别|性別|年龄|年齢|出生|生年月日|性|男|女)$", "", n)
        if n and n not in out:
            out.append(n)
    return out


def masked_full_names(cur, text):
    """“赵女士”→ 在原文里找以“赵”开头、像姓名的词（“赵女士 赵艺”）。

    EN: "赵女士" (Ms Zhao) → look in the source for a name-like word starting with "赵" ("赵女士 <name>").

    JA: 「赵女士」（趙さん）→ 原文から「赵」で始まる氏名らしい語を探す（「赵女士 <氏名>」）。
    """
    m = re.match(r"^([一-鿿]{1,2})(先生|女士|小姐)$", s(cur))
    if not m or not text:
        return []
    sur = m.group(1)
    cnt = Counter(x for x in re.findall(r"(?<![一-鿿])(" + sur + r"[一-鿿]{1,2})(?![一-鿿])", NF.unicodedata_nfkc(text))
                  if NF.person_like(x) and not re.search(r"[等的和在是为了与及]$", x))
    return [n for n, _ in cnt.most_common(3)]


def names_next_to_contact(text, contacts):
    """原文里紧挨在本人手机号/邮箱前面的姓名（“张三 13800000018”）。返回 [(姓名, 联系方式)]。

    EN: The name immediately before the person's mobile/e-mail in the source ("张三 13800000018"). Returns [(name, contact)].

    JA: 原文で本人の携帯番号・メールの直前にある氏名（「张三 13800000018」）。[(氏名, 連絡先)] を返す。
    """
    t = NF.unicodedata_nfkc(text)
    out = []
    for c in contacts:
        for m in re.finditer(re.escape(c), t):
            pre = t[max(0, m.start() - 25):m.start()]
            mm = re.search(r"(?:^|[\s|:：])([一-鿿]{2,4})[\s|,，]*(?:(?:手机|电话|Tel|TEL|mobile|Mobile)[:：\s]*)?$", pre)
            if mm and NF.person_like(mm.group(1)) and not re.search(r"(省|市|县|区|厅|局)$", mm.group(1)) and (mm.group(1), c) not in out \
                    and not re.search(re.escape(mm.group(1)) + r"(市|盟|省|县|区|州)", t):
                out.append((mm.group(1), c))
    return out


def pc_json(p):
    name = os.path.basename(p)
    return str(_rc.path("v1_dir" if "/v1/" in p else "v2_dir") / name)


def item_at(res, fp):
    m = re.match(r"resumes\[(\d+)\]\.(\w+)(?:\[(\d+)\])?(?:\.(\w+))?", fp)
    if not m:
        return None, None, None, None
    ri, lst, idx, fld = int(m.group(1)), m.group(2), m.group(3), m.group(4)
    r = res[ri] if ri < len(res) else None
    if r is None:
        return None, None, None, None
    if lst == "base_info":
        return r, lst, r.get("base_info") or {}, fld
    items = r.get(lst) or []
    it = items[int(idx)] if idx is not None and int(idx) < len(items) else None
    return r, lst, it, fld


def record_summary(lst, it):
    if not isinstance(it, dict):
        return ""
    if lst == "work_experiences":
        keys = ("company_name", "position", "position_dept", "position_start", "position_resigned")
    elif lst == "education_list":
        keys = ("school_name", "school_major_name", "school_degree_type", "school_start_ym", "school_end_ym")
    elif lst == "base_info":
        keys = ("full_name", "birth_date", "city")
    else:
        keys = list(it.keys())[:4]
    parts = [f"{FIELD_ZH.get(k, k)}：{s(it.get(k))[:40]}" for k in keys if s(it.get(k))]
    if lst == "work_experiences" and s(it.get("position_responsibilities")):
        parts.append("职责：" + re.sub(r"\s+", " ", s(it.get("position_responsibilities")))[:60])
    return "；".join(parts)


def propose(itype, lst, it, fld, value):
    """能从现有值直接推出的建议值；推不出返回空。

    EN: A suggested value that can be derived directly from the existing value; returns empty if it cannot be derived.

    JA: 既存の値から直接導ける提案の値。導けなければ空を返す。
    """
    if not isinstance(it, dict):
        return ""
    if itype == "school_in_major":
        mj, sc = s(it.get("school_major_name")), s(it.get("school_name"))
        if sc and re.search(r"(大学|学院|学校|高校|中学|University|College)$", sc, re.I):
            return "专业＝（清空）"
        return f"学校＝{mj}；专业＝（清空）" if mj else ""
    if itype == "date_reversed":
        a, b = ("position_start", "position_resigned") if lst == "work_experiences" else ("school_start_ym", "school_end_ym")
        if s(it.get(a)) and s(it.get(b)):
            return f"开始＝{s(it.get(b))}；结束＝{s(it.get(a))}"
    if itype == "position_as_company":
        return f"职位＝{s(it.get('company_name'))}；公司＝（待补）"
    if itype == "company_in_position":
        return f"公司＝{s(it.get('position'))}；职位＝（待补）"
    if itype == "school_major_swapped":
        return f"学校＝{s(it.get('school_major_name'))}；专业＝{s(it.get('school_name'))}"
    if itype == "degree_school_mismatch":
        sc = s(it.get("school_name"))
        d = "初中" if re.search(r"(初中|初级中学)", sc) else "中专" if re.search(r"(中专|职校|技校|職校|卫校)", sc) else "高中"
        return f"学历＝{d}"
    if itype == "work_company_sentence":
        comp = s(it.get("company_name"))
        m = re.match(r"^([^（(，,。；;]{4,40}?(?:有限公司|有限责任公司|公司|会社|集团|代表处|事务所|Co\.,?\s*Ltd\.?|Limited))\s*[（(]", comp, re.I)
        if m:
            return f"公司＝{m.group(1).strip()}；括号里的说明移到职责"
        orgs = [m.group(1) for m in N.ORG_EXTRACT_RE.finditer(comp)]
        orgs = [o for o in orgs if len(o) >= 5 and not re.match(r"^(\d|[1-9]\)|担任|协助|负责|我|本|以及|和|与|在|于)", o)
                and "本公司" not in o and not re.search(r"(以及|的|和)公司$", o)]
        if len(orgs) == 1:
            return f"公司＝{orgs[0]}；原句移到职责"
    if itype in ("honor_in_work", "education_duplicate"):
        return "删除此条"
    if itype == "position_in_company":
        comp = re.sub(r"\s*[（(]\s*[^（()）]*(个月|年|months?|years?)[^（()）]*[)）]\s*$", "", s(it.get("company_name")))
        m = re.match(r"^(实习|兼职|暑期实习|毕业实习|见习|打工)\s*[（(](.+)[)）]$", comp)
        if m:
            return f"公司＝{m.group(2).strip()}；职位＝{m.group(1)}"
        m = re.match(r"^(.+?)\s*[（(](实习|兼职|实习生)[)）]$", comp)
        if m:
            return f"公司＝{m.group(1).strip()}；职位＝{m.group(2)}"
        m = re.match(r"^(.*?(?:公司|会社|集团|厂|店|银行|医院|事务所|Co\.,?\s*Ltd\.?|Ltd\.?|Inc\.?))\s*(.+)$", comp, re.I)
        if m:
            return f"公司＝{m.group(1).strip()}；职位＝{m.group(2).strip()}"
    return ""


def main():  # noqa: C901
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--text-dir", required=True)
    ap.add_argument("--name-review", default="")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    run = Path(a.run_dir)
    T = Texts(a.manifest, a.text_dir)
    led = run / "ledgers"
    issues = [r for r in csv.DictReader(open(led / "field_issue_ledger.csv", encoding="utf-8-sig"))
              if r["severity"] == "high" and r["output_json"].startswith("needs_fix/")]
    review = list(csv.DictReader(open(led / "review_ledger.csv", encoding="utf-8-sig")))
    smap = list(csv.DictReader(open(led / "source_map.csv", encoding="utf-8-sig")))
    by_out = defaultdict(list)
    for r in smap:
        if r["output_json"]:
            by_out[r["output_json"]].append(r)
    in2out = {r["input_json"]: r["output_json"] for r in smap}
    docs = {}

    def doc(oj):
        if oj not in docs:
            docs[oj] = json.load(open(run / oj, encoding="utf-8"))
        return docs[oj]

    def src_text(oj):
        return "\n".join(T.get(r["original_path"]) for r in by_out.get(oj, []) if r["original_path"])

    def originals(oj):
        seen = []
        for r in by_out.get(oj, []):
            if r["original_path"] and r["original_path"] not in seen:
                seen.append(r["original_path"])
        return seen

    # ---------------------------------------------------------------- 1 姓名
    # EN: ---------------------------------------------------------------- 1 Names
    # JA: ---------------------------------------------------------------- 1 氏名
    name_rows = []
    unreliable = [r for r in review if r["reason"] == "name_unreliable"]
    done = set()
    for r in unreliable:
        oj = r["output_json"]
        d = doc(oj)
        mi = d["merge_info"]
        origs = originals(oj)
        text = src_text(oj)
        cands = []
        for p in origs:
            for n, strength, where in NF.filename_candidates(p):
                cands.append(f"{n}（{where}{'' if strength == 'strong' else '，弱'}）")
        lab = label_names(text)[:3]
        full = masked_full_names(r["detail"], text)
        cur = s(r["detail"])
        if re.search(r"(先生|女士|小姐)$", cur):
            situ = f"原文里只有“{cur}”，招聘平台隐去了名字"
            situ += f"；原文别处出现了“{'、'.join(full)}”" if full else "；原文别处也没有全名"
        elif cur:
            situ = f"当前取到的“{cur}”不像姓名（地名/栏目名/过长等）"
            if cur in label_names(text):
                situ = f"原文“姓名”栏写的就是“{cur}”，但它同时是地名/常用词，系统没有自动采用"
        else:
            situ = "原文里没有取到姓名"
        contacts = [x for x in [mi.get("primary_phone"), mi.get("primary_email")] + list(mi.get("other_phones") or [])
                    + list(mi.get("other_emails") or []) if x]
        adj = names_next_to_contact(text, contacts)
        msur = re.match(r"^([一-鿿]{1,2})(先生|女士|小姐)$", cur or next((x for x in lab if re.search(r"(先生|女士|小姐)$", x)), ""))
        strong = [n for p in origs for n, st, w in NF.filename_candidates(p) if st == "strong"]
        if msur:  # 平台隐名：只采用同姓的候选
        # EN: Platform-hidden names: only accept candidates with the same surname
        # JA: プラットフォームで隠された氏名：同じ姓の候補だけを採用する
            strong = [n for n in strong if n.startswith(msur.group(1))]
        glued = re.match(r"^([一-鿿]{1,2})(先生|女士|小姐)([一-鿿]{1,3})$", cur)  # “山女士山丹”
        # EN: "<surname>女士<name>" (Ms X followed by the full name)
        # JA: 「<姓>女士<氏名>」（〇〇さんの後に氏名が続く）
        if glued and glued.group(3).startswith(glued.group(1)) and len(glued.group(3)) >= 2:
            full = [glued.group(3)] + full
            situ = f"原文里是“{cur}”：平台显示的“{glued.group(1)}{glued.group(2)}”后面紧跟着全名“{glued.group(3)}”"
        sur = msur.group(1) if msur else (glued.group(1) if glued else "")
        if sur:
            adj = [x for x in adj if x[0].startswith(sur)]
        if adj:
            situ += f"。原文里“{adj[0][0]}”紧挨着本人的联系方式 {adj[0][1]} 出现，可信度高"
        sugg = (adj[0][0] if adj else "") or (full[0] if full else "") or next((x for x in lab if NF.person_like(x)), "") \
            or (strong[0] if strong else "")
        if not sugg:
            sugg = next((x for x in lab if not re.search(r"(先生|女士|小姐)$", x)), "")
        if not cur:
            mk = next((x for x in lab if re.search(r"(先生|女士|小姐)$", x)), "")
            if mk:
                situ = f"原文里只有“{mk}”，招聘平台隐去了名字" + (f"；原文别处出现了“{'、'.join(full)}”" if full else "；原文别处也没有全名")
        head = re.sub(r"\s+", " ", text)[:160] if text else "（原文文本不可用）"
        name_rows.append(["待确认姓名", oj.replace("/", "\\"), situ, mi.get("primary_phone") or "", mi.get("primary_email") or "",
                          "；".join(dict.fromkeys(cands)) or "（文件名里没有像姓名的词）", "；".join(lab) or "（原文里没有“姓名”栏）",
                          sugg, head, "\n".join(origs)])
        done.add(oj)
    for r in issues:
        if r["issue_type"] != "name_invalid" or r["output_json"] in done:
            continue
        oj = r["output_json"]
        d = doc(oj)
        mi = d["merge_info"]
        origs = originals(oj)
        text = src_text(oj)
        cands = [f"{n}（{w}）" for p in origs for n, st, w in NF.filename_candidates(p)]
        name_rows.append(["某一版本姓名无效", oj.replace("/", "\\"), f"{r['field_path']}：{r['value']}（合并后姓名：{mi.get('canonical_name')}）",
                          mi.get("primary_phone") or "", mi.get("primary_email") or "", "；".join(dict.fromkeys(cands)) or "",
                          "", mi.get("canonical_name") or "", re.sub(r"\s+", " ", text)[:160], "\n".join(origs)])
    for r in review:
        if r["reason"] != "name_conflict":
            continue
        oj = r["output_json"]
        name_rows.append(["同一联系方式下有两个不同姓名", oj.replace("/", "\\"), r["detail"], "", "", "", "", "",
                          "请确认这些姓名是不是同一个人（例如本名/英文名/曾用名）。", "\n".join(originals(oj))])
    if a.name_review and os.path.exists(a.name_review):
        seen_nr = set()
        for r in csv.DictReader(open(a.name_review, encoding="utf-8-sig")):
            ij = r["input_json"]
            key = ("/home/claude/pack/inputs/v1/" if "complete-v1" in ij else "/home/claude/pack/inputs/v2/") + PureWindowsPath(ij).name
            oj = in2out.get(key, "")
            if not oj:
                continue
            cur = doc(oj)["merge_info"].get("canonical_name")
            cand = s(r["candidate"])
            simp = lambda x: re.sub(r"[男女\s]+$", "", C.to_simplified_name(s(x)).translate(EXTRA_SIMP))  # noqa: E731
            if simp(cand) == simp(cur) or (oj, cand) in seen_nr:
                continue  # 合并后已经是这个名字，或只是繁简/日文字形不同
                # EN: Already this name after merging, or differing only in traditional/simplified/Japanese glyphs
                # JA: 統合後にすでにこの名前になっているか、繁体字・簡体字・日本の字体が異なるだけ
            seen_nr.add((oj, cand))
            name_rows.append(["姓名整理时拿不准", oj.replace("/", "\\"), f"源 JSON 姓名：{r['current_name']}；合并后姓名：{cur}",
                              "", "", r["candidate"], r["evidence"], r["candidate"], "", "\n".join(originals(oj))])

    # ---------------------------------------------------------------- 2 字段问题
    # EN: ---------------------------------------------------------------- 2 Field issues
    # JA: ---------------------------------------------------------------- 2 フィールドの問題
    field_rows = []
    per_file = Counter()
    for r in sorted((x for x in issues if x["issue_type"] != "name_invalid"), key=lambda x: (x["output_json"], x["field_path"])):
        oj = r["output_json"]
        d = doc(oj)
        res = d["structured_data"]["resumes"]
        rr, lst, it, fld = item_at(res, r["field_path"])
        lang = s(rr.get("resume_languge")) if rr else ""
        zh, how = ISSUE.get(r["issue_type"], (r["issue_type"], "对照原文修正。"))
        where = LIST_ZH.get(lst or "", lst or "")
        m = re.search(r"\[(\d+)\]", r["field_path"][r["field_path"].find(".") + 1:] if "." in r["field_path"] else "")
        if m:
            where += f" 第{int(m.group(1)) + 1}条"
        if fld:
            where += " · " + FIELD_ZH.get(fld, fld)
        needles = [r["value"]]
        if isinstance(it, dict):
            needles += [re.sub(r"\s+", " ", s(it.get(k))).strip()[:20] for k in ("position_responsibilities", "company_name", "school_name", "school_major_name", "position")
                        if len(s(it.get(k)).strip()) >= 4]
        text = T.get(r["original_path"]) if r["original_path"] else ""
        per_file[oj] += 1
        field_rows.append([oj.replace("/", "\\"), LANG_ZH.get(lang, lang) + ("（主版本）" if r["field_path"].startswith("resumes[0]") else ""),
                           where, zh, s(r["value"])[:300], record_summary(lst, it), propose(r["issue_type"], lst, it, fld, r["value"]),
                           how, snippet(text, needles), r["original_path"], pc_json(r["source_json"]), r["field_path"], r["issue_type"]])

    # ---------------------------------------------------------------- 3 归并
    # EN: ---------------------------------------------------------------- 3 Grouping
    # JA: ---------------------------------------------------------------- 3 グループ化
    link_rows = []
    for r in review:
        if r["reason"] in ("name_link_ambiguous", "shared_contact_only"):
            link_rows.append(["姓名+公司/学校对上多个人，未并入" if r["reason"] == "name_link_ambiguous" else "只有共用联系方式，未输出",
                              pc_json(r["input_json"]) if r["input_json"] else "", r["detail"], r["original_path"]])

    # ---------------------------------------------------------------- 写 Excel
    # EN: ---------------------------------------------------------------- Write Excel
    # JA: ---------------------------------------------------------------- Excel を書き出す
    FONT = "Microsoft YaHei"
    f_body = Font(name=FONT, size=10)
    f_head = Font(name=FONT, size=10, bold=True, color="FFFFFF")
    fill_head = PatternFill("solid", fgColor="44546A")
    fill_in = PatternFill("solid", fgColor="FFF2CC")
    thin = Side(style="thin", color="D9D9D9")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    wrap = Alignment(wrap_text=True, vertical="top")

    wb = Workbook()
    ws0 = wb.active
    ws0.title = "说明"

    def sheet(title, headers, widths, rows, choices, input_cols):
        ws = wb.create_sheet(title)
        ws.append(headers)
        for c in range(1, len(headers) + 1):
            cell = ws.cell(row=1, column=c)
            cell.font, cell.fill, cell.alignment, cell.border = f_head, fill_head, Alignment(wrap_text=True, vertical="center"), border
            ws.column_dimensions[get_column_letter(c)].width = widths[c - 1]
        for row in rows:
            row = [ILLEGAL_CHARACTERS_RE.sub("", x) if isinstance(x, str) else x for x in row]
            ws.append(row + [""] * (len(headers) - len(row)))
        n = len(rows) + 1
        for r_ in ws.iter_rows(min_row=2, max_row=n):
            for cell in r_:
                cell.font, cell.alignment, cell.border = f_body, wrap, border
        for col in input_cols:
            L = get_column_letter(col)
            for i in range(2, n + 1):
                ws[f"{L}{i}"].fill = fill_in
        dv = DataValidation(type="list", formula1='"' + ",".join(choices) + '"', allow_blank=True, showDropDown=False)
        dv.error, dv.errorTitle = "请从下拉列表里选择", "决定"
        ws.add_data_validation(dv)
        dv.add(f"{get_column_letter(input_cols[0])}2:{get_column_letter(input_cols[0])}{max(n, 2)}")
        ws.freeze_panes = "B2"
        ws.auto_filter.ref = f"A1:{get_column_letter(len(headers))}{max(n, 2)}"
        # 已作决定的行变浅绿
        # EN: Rows already decided turn light green
        # JA: 判断済みの行は薄い緑にする
        L = get_column_letter(input_cols[0])
        ws.conditional_formatting.add(f"A2:{get_column_letter(len(headers))}{max(n, 2)}",
                                      FormulaRule(formula=[f'LEN(${L}2)>0'], fill=PatternFill("solid", fgColor="E2EFDA")))
        return ws

    name_headers = ["类型", "输出 JSON（output\\merge-v3\\<运行>\\ 下）", "当前情况", "手机", "邮箱", "文件名/文件夹里的候选姓名",
                    "原文“姓名”栏", "建议姓名", "原文开头", "原文路径", "你的决定", "修正值", "备注"]
    ws1 = sheet("1 姓名", name_headers, [16, 34, 28, 13, 22, 26, 22, 12, 50, 50, 16, 14, 18], name_rows, NAME_DECISIONS + CONFLICT_DECISIONS[:2], [11, 12, 13])
    field_headers = ["输出 JSON（output\\merge-v3\\<运行>\\ 下）", "版本", "位置", "问题", "当前值", "同一条记录", "建议值",
                     "怎么处理", "原文片段", "原文路径", "来源 JSON（原版）", "字段路径", "问题代码", "你的决定", "修正值", "备注"]
    ws2 = sheet("2 字段问题", field_headers, [30, 11, 18, 20, 30, 40, 28, 34, 55, 45, 40, 30, 18, 16, 20, 18], field_rows, DECISIONS, [14, 15, 16])
    link_headers = ["类型", "源 JSON", "说明", "原文路径", "你的决定", "要并入的输出 JSON", "备注"]
    ws3 = sheet("3 未归并记录", link_headers, [30, 45, 60, 60, 16, 30, 18], link_rows, ["并入（在右栏写输出JSON）", "不并入", "跳过"], [5, 6, 7])

    # 统计
    # EN: Statistics
    # JA: 統計
    ws4 = wb.create_sheet("4 统计")
    ws4.append(["问题", "条数", "已作决定", "剩余"])
    types = Counter(r[3] for r in field_rows)
    for i, (k, v) in enumerate(types.most_common(), start=2):
        ws4.append([k, f"=COUNTIF('2 字段问题'!D:D,A{i})", f"=COUNTIFS('2 字段问题'!D:D,A{i},'2 字段问题'!N:N,\"?*\")", f"=B{i}-C{i}"])
    last = ws4.max_row
    ws4.append(["字段问题合计", f"=SUM(B2:B{last})", f"=SUM(C2:C{last})", f"=SUM(D2:D{last})"])
    ws4.append(["姓名", f"=COUNTA('1 姓名'!A:A)-1", f"=COUNTA('1 姓名'!K:K)-1", f"=B{last + 2}-C{last + 2}"])
    ws4.append(["未归并记录", f"=COUNTA('3 未归并记录'!A:A)-1", f"=COUNTA('3 未归并记录'!E:E)-1", f"=B{last + 3}-C{last + 3}"])
    for r_ in ws4.iter_rows(min_row=1, max_row=ws4.max_row):
        for cell in r_:
            cell.font, cell.border = f_body, border
    for c in range(1, 5):
        ws4.cell(row=1, column=c).font, ws4.cell(row=1, column=c).fill = f_head, fill_head
    for rr_ in range(last + 1, last + 4):
        ws4.cell(row=rr_, column=1).font = Font(name=FONT, size=10, bold=True)
    ws4.column_dimensions["A"].width = 34
    for L in "BCD":
        ws4.column_dimensions[L].width = 11

    # 说明
    # EN: Notes
    # JA: 説明
    n_files = len({r[0] for r in field_rows} | {r[1] for r in name_rows})
    n_nf = len({r[0] for r in field_rows} | {r[1] for r in name_rows if r[1].startswith("needs_fix")})
    lines = [
        ("人工复核表", True),
        (f"来源：合并运行 {run.name}。涉及 {n_files} 个输出 JSON：needs_fix 里的 {n_nf} 个（逐条列出全部高级别问题），"
         f"以及 formal 里姓名还需要确认的 {n_files - n_nf} 个。", False),
        ("所有内容只读生成，原始 JSON、原文件都没有改。", False),
        ("", False),
        ("怎么填", True),
        ("只填黄色的三栏：“你的决定”（下拉选择）、“修正值”、“备注”。其他栏不要改。", False),
        ("选了决定的行会变成浅绿，方便看进度；“4 统计”里有每类问题的剩余条数。", False),
        ("“按建议改”＝采用“建议值”栏；“改为修正值”＝采用你在“修正值”栏写的内容；“保持原样”＝不是错误，下次检查不再算高级别；“删除此条”＝整条经历/学历删掉。", False),
        ("修正值的写法：一个字段直接写值；多个字段用“字段＝值；字段＝值”，例如：公司＝上海某某有限公司；职位＝销售经理。字段名用表里的中文：公司、职位、部门、学校、专业、学历、入职、离职、入学、毕业。", False),
        ("拿不准、原文也看不清的，选“跳过”或留空，不影响其他行。", False),
        ("", False),
        ("示例（2 字段问题）", True),
        ("问题：公司栏是一句话 ｜ 当前值：在湖南省某电视台担任播音员。 ｜ 你的决定：改为修正值 ｜ 修正值：公司＝湖南省某电视台；职位＝播音员", False),
        ("", False),
        ("各页", True),
        (f"1 姓名：{len(name_rows)} 条。原文里找不到可靠姓名的、某个版本姓名无效的、同一联系方式下出现两个姓名的。“原文开头”是原文件前 160 字，姓名通常在这里。", False),
        (f"2 字段问题：{len(field_rows)} 条，按输出文件排序，同一个人的问题挨在一起。“原文片段”是在原文里找到该值（或同一条记录里其他值）的前后文；“原文里找不到这个值”通常说明解析时把别处的内容放进了这一栏。", False),
        (f"3 未归并记录：{len(link_rows)} 条。没有联系方式、姓名和公司/学校又对上多个候选人的记录；只有顾问共用联系方式的记录。", False),
        ("4 统计：按问题类型汇总，公式自动计算。", False),
        ("", False),
        ("填完以后", True),
        ("把这个文件原样保存（不要改名、不要改表头），告诉我。我会写一个脚本读取你的决定，做成新的修复副本（和之前一样只做副本），再跑一次合并和审计。", False),
    ]
    for i, (t, b) in enumerate(lines, start=1):
        c = ws0.cell(row=i, column=1, value=t)
        c.font = Font(name=FONT, size=12 if i == 1 else 10, bold=b)
        c.alignment = Alignment(wrap_text=True, vertical="top")
    ws0.column_dimensions["A"].width = 120
    wb.save(a.out)
    print(json.dumps({"name_rows": len(name_rows), "field_rows": len(field_rows), "link_rows": len(link_rows), "files": n_files,
                      "field_types": types.most_common()}, ensure_ascii=False))


if __name__ == "__main__":
    main()
