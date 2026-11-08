#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
claude_parse_liepin.v3.py —— 猎聘导出简历解析器。

覆盖猎聘几代导出格式（.doc / .htm / .docx / .mht）：
  A. 2014 年后台导出（“简历编号 / 个人信息 / 目前职业概况”，Tab 分栏）
  B. 2014 年网页版（“搜索同事2010.04 - 至今 公司 (4年8个月)”，公司下可有多段职位）
  C. 2017 年后导出（“目前求职状态 / 简历编号信息 / 公司性质：… | 公司规模：…”），
     含 .htm 版（每个词拆成一行，先拼回再解析）
只在原文里取值，不推测；“未填写 / 保密”一律视为空。

EN: claude_parse_liepin.v3.py -- parser for résumés exported from Liepin.

Covers several generations of Liepin export formats (.doc / .htm / .docx / .mht):
  A. 2014 back-office export ("简历编号 / 个人信息 / 目前职业概况" (résumé number / personal info / current career overview), tab columns)
  B. 2014 web version ("搜索同事2010.04 - 至今 company (4年8个月)"; a company may have several position periods)
  C. exports after 2017 ("目前求职状态 / 简历编号信息 / 公司性质：… | 公司规模：…" (current job-search status / résumé number info / company type / size)),
     including the .htm version (every word split onto its own line; joined back before parsing)
Values are taken only from the source, never guessed; "未填写 / 保密" (not filled in / confidential) are always treated as empty.

JA: claude_parse_liepin.v3.py —— Liepin からエクスポートした履歴書のパーサー。

Liepin の何世代ものエクスポート形式（.doc / .htm / .docx / .mht）に対応する：
  A. 2014 年の管理画面からのエクスポート（「简历编号 / 个人信息 / 目前职业概况」（履歴書番号・個人情報・現在の職業の概要）、タブ区切りの列）
  B. 2014 年の Web 版（「搜索同事2010.04 - 至今 会社 (4年8个月)」。1 つの会社の下に複数の職位の期間がある場合がある）
  C. 2017 年以降のエクスポート（「目前求职状态 / 简历编号信息 / 公司性质：… | 公司规模：…」（現在の求職状況・履歴書番号の情報・会社の性質・規模））、
     .htm 版を含む（語ごとに 1 行に分かれているので、つなぎ直してから解析する）
値は原文からだけ取り、推測はしない。「未填写／保密」（未記入・非公開）は常に空とみなす。
"""

import re
import unicodedata
from pathlib import Path
import importlib.util

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("claude_merge_common_v3_lp", HERE / "claude_merge_common.v3.py")
C = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(C)
s = C.s

DEGREES = ["博士后", "博士", "EMBA", "MBA", "硕士", "研究生", "本科", "大专", "专科", "中专", "中技", "高中", "职高", "初中"]
EMPTY_VALUES = {"未填写", "保密", "无", "暂无", "-", "--", "面议"}

SECTIONS = {
    "个人信息": "head", "目前职业概况": "head", "职业发展意向": "head", "求职意向": "head", "职业期望": "head",
    "工作经历": "work", "工作经验": "work", "项目经历": "proj", "项目经验": "proj",
    "教育经历": "edu", "教育背景": "edu", "语言能力": "lang", "自我评价": "pr",
    "附加信息": "extra", "附加消息": "extra", "证书": "cert", "资格证书": "cert", "培训经历": "train",
    "专业技能": "skill", "技能专长": "skill", "在校情况": "extra", "社会实践": "extra", "所获奖项": "extra",
}
LABELS = [
    # 头部
    # EN: Header
    # JA: ヘッダー
    "目前求职状态", "主动应聘职位", "关联职位", "简历编号信息", "简历编号", "简历更新时间", "最新登录", "姓名", "性别", "手机号码",
    "联系电话", "年龄", "电子邮件", "教育程度", "学历", "工作年限", "婚姻状况", "职业状态", "所在地", "国籍", "微信号", "户口所在地",
    "所在行业", "公司名称", "所任职位", "目前年薪", "目前薪资", "期望行业", "期望职位", "期望地点", "期望年薪", "期望月薪",
    "勿推企业", "勿推荐企业", "手机", "邮箱", "期望薪资", "目前行业", "更新时间", "操作时间", "声明",
    # 工作
    # EN: Work
    # JA: 職歴
    "公司性质", "公司规模", "公司行业", "所属行业", "公司描述", "所在地区", "所在部门", "汇报对象", "下属人数", "薪酬状况",
    "工作职责和业绩", "工作职责", "工作业绩", "职责业绩", "离职原因", "工作内容", "所用技术", "工作地点", "月薪",
    # 项目 / 教育 / 培训
    # EN: Projects / education / training
    # JA: プロジェクト・学歴・研修
    "项目职务", "所在公司", "项目简介", "项目描述", "项目职责", "项目业绩", "专业", "是否统招",
    "培训机构", "培训课程", "所获证书", "培训描述",
]
LABEL_RE = re.compile(r"(?<![一-鿿])(" + "|".join(sorted(map(re.escape, LABELS), key=len, reverse=True)) + r")\s*[:：]")
YM = r"((?:19|20)\d{2})\s*[./年\-]\s*(\d{1,2})\s*月?"
YM_NC = r"(?:19|20)\d{2}\s*[./年\-]\s*\d{1,2}\s*月?"
RANGE_RE = re.compile(YM + r"\s*[-–—~～至]+\s*(至今|现在|今|" + YM_NC + r")")
START_RE = re.compile(r"^(?:搜索同事)?\s*" + RANGE_RE.pattern)
DUR_RE = re.compile(r"[（(]\s*(?:\d+\s*年)?\s*(?:\d+\s*个?月)?\s*[)）]\s*$")
SALARY_RE = re.compile(r"(\d[\d.,]*\s*(?:万|千)?\s*元\s*/\s*月(?:\s*\*\s*\d+\s*个月)?|\d[\d.]*\s*万\s*(?:元)?\s*/?\s*年?)")
# 2021 版：“威海灿荣进出口有限公司（2020.06-至今，1年6个月）”
# EN: 2021 version: "威海灿荣进出口有限公司（2020.06-至今，1年6个月）" (company (2020.06 - present, 1 year 6 months))
# JA: 2021 年版：「威海灿荣进出口有限公司（2020.06-至今，1年6个月）」（会社（2020.06〜現在、1 年 6 か月））
START2_RE = re.compile(r"^(.+?)\s*[（(]\s*" + RANGE_RE.pattern + r"\s*(?:[，,][^)）]*)?[)）]\s*$")
IGN = []   # 解析器认定不属于候选人本人信息的原文行（公司简介、平台声明、求职状态），评分时新旧一视同仁地排除
# EN: Source lines the parser judges not to be the candidate's own information (company profiles, platform disclaimers, job-search status) are excluded equally for old and new when scoring
# JA: パーサーが候補者本人の情報ではないと判断した原文の行（会社紹介・プラットフォームの声明・求職状況）は、採点の際に新旧どちらからも同じく除外する
EMP_RE = re.compile(r"^\d+\s*[-~]\s*\d+\s*人$|^\d+\s*人(?:以上|以下)$|^少于\s*\d+\s*人$")


def ym(y, m):
    try:
        mi = int(m)
    except (TypeError, ValueError):
        return ""
    return f"{int(y):04d}年{mi:02d}月01日" if 1 <= mi <= 12 else ""


def range_of(m):
    start = ym(m.group(1), m.group(2))
    end_raw = m.group(3)
    if re.match(r"(至今|现在|今)", end_raw):
        return start, "至今"
    mm = re.match(YM, end_raw)
    return start, (ym(mm.group(1), mm.group(2)) if mm else "")


def val(x):
    x = re.sub(r"\s+", " ", s(x)).strip(" |｜\t")
    return "" if x in EMPTY_VALUES else x


# ------------------------------------------------------------------ 预处理
# EN: ------------------------------------------------------------------ Pre-processing
# JA: ------------------------------------------------------------------ 前処理
def norm_lines(text: str):
    t = unicodedata.normalize("NFKC", text).replace("﻿", "")
    t = re.sub(r"月\s+薪\s*[:：]", "月薪：", t)
    raw = [l.strip() for l in t.split("\n")]
    lines = [l for l in raw if l]
    # .htm 导出把一个词拆成多行：把孤立的“/ ( ) |”、数字后的“元”、“年以上”、以“-”结尾的日期拼回去
    # EN: .htm exports split one word over several lines: join back isolated "/ ( ) |", "元" after digits, "年以上" (years or more), and dates ending with "-"
    # JA: .htm のエクスポートは 1 つの語を複数行に分けてしまう：孤立した「/ ( ) |」、数字の後の「元」、「年以上」、「-」で終わる日付をつなぎ直す
    out = []
    for l in lines:
        if out:
            p = out[-1]
            if (l in ("/", "(", ")", "（", "）", "|", "｜", "·") or re.match(r"^[/)）·]", l) or re.search(r"[(（/·\-–]$", p)
                    or (re.fullmatch(r"\d[\d.\-~]*", p) and re.match(r"^(元|万|千|年以上|年|个月|人)", l))
                    or (p in ("元", "元/") and l in ("/", "月"))
                    or (re.search(r"元\s*/$", p))
                    or re.fullmatch(r"(转|至今)\s*\d*", l) and re.search(r"\d$", p)):
                sep = "" if not re.search(r"[A-Za-z0-9]$", p) or not re.match(r"^[A-Za-z0-9]", l) else " "
                out[-1] = p + sep + l
                continue
            if re.search(r"[)）]$", p) and "(" in p.replace("（", "(") and not LABEL_RE.search(l) and \
                    re.match(r"^[一-鿿A-Za-z]{0,14}(公司|集团|中心|研究所|研究院|大学|学院|医院|银行|事务所|工厂|分公司)$", l):
                out[-1] = p + l  # “辉瑞(中国)” + “研究开发有限公司”
                # EN: "辉瑞(中国)" + "研究开发有限公司" (Pfizer (China) + R&D Co., Ltd.)
                # JA: 「辉瑞(中国)」+「研究开发有限公司」（ファイザー（中国）+ 研究開発有限会社）
                continue
        out.append(l)
    return out


def fragmented(lines) -> bool:
    """.htm 版每个词一行：短行占比高。

    EN: The .htm version has one word per line: a high proportion of short lines.

    JA: .htm 版は語ごとに 1 行で、短い行の割合が高い。
    """
    return len(lines) > 30 and sum(1 for l in lines if len(l) <= 4) / len(lines) >= 0.25


FRAG = {"on": False}


def join_cont(a: str, b: str) -> str:
    if not a:
        return b
    if FRAG["on"] and not re.match(r"^\d{1,2}\s*[.、)）]", b):
        sep = " " if re.search(r"[A-Za-z0-9]$", a) and re.match(r"^[A-Za-z0-9]", b) else ""
        return a + sep + b
    return a + "\n" + b


def tokens(line: str):
    """一行 → [(label, value)]；行首无标签的文字记为 (None, text)。

    EN: One line → [(label, value)]; text at the start of a line without a label is recorded as (None, text).

    JA: 1 行 → [(label, value)]。行頭にラベルのないテキストは (None, text) として記録する。
    """
    res = []
    ms = list(LABEL_RE.finditer(line))
    if not ms:
        return [(None, line.strip())]
    if ms[0].start() > 0 and line[:ms[0].start()].strip(" |\t"):
        res.append((None, line[:ms[0].start()].strip(" |\t")))
    for i, m in enumerate(ms):
        end = ms[i + 1].start() if i + 1 < len(ms) else len(line)
        res.append((m.group(1), line[m.end():end].strip(" |｜\t")))
    return res


def empty(lst):
    return {k: "" for k in C.LIST_FIELDS[lst]}


# ------------------------------------------------------------------ 头部
# EN: ------------------------------------------------------------------ Header
# JA: ------------------------------------------------------------------ ヘッダー
def parse_head(lines):
    kv = {}
    pend = None
    for l in lines:
        for lab, v in tokens(l):
            if lab is None:
                if pend and not kv.get(pend):
                    kv[pend] = v
                    pend = None
                continue
            if lab not in kv or not kv[lab]:
                kv[lab] = v
            pend = lab if not v else None
    b = {f: "" for f in C.BASE_FIELDS}
    b["full_name"] = re.sub(r"\s+", "", val(kv.get("姓名", "")))
    b["gender"] = val(kv.get("性别", ""))[:1] if val(kv.get("性别", ""))[:1] in ("男", "女") else ""
    ma = re.match(r"(\d{2})", val(kv.get("年龄", "")))
    b["age"] = ma.group(1) if ma else ""
    b["marital_status"] = val(kv.get("婚姻状况", ""))
    b["city"] = val(kv.get("所在地", ""))
    b["nationality"] = val(kv.get("国籍", "")) or "中国"
    b["household_registration"] = val(kv.get("户口所在地", ""))
    b["platform_from"] = "猎聘"
    mid = re.search(r"[0-9A-Za-z]{6,}", kv.get("简历编号信息", "") or kv.get("简历编号", ""))
    b["platform_resume_id"] = mid.group(0) if mid else ""
    ms, es = [], []
    for field in ("手机号码", "联系电话", "电子邮件", "手机", "邮箱"):
        v = kv.get(field, "")
        for x in C.MOBILE_FIND.findall(v):
            k, n = C.classify_phone(x)
            if k == "mobile" and n not in ms:
                ms.append(n)
        for x in C.EMAIL_FIND.findall(v):
            for part in C.split_glued(x):
                k, n = (C.classify_email(part) if "@" in part else C.classify_phone(part))
                if k == "email" and n not in es:
                    es.append(n)
                elif k == "mobile" and n not in ms:
                    ms.append(n)
    if not ms:
        for field in ("手机号码", "联系电话", "手机"):
            raw = re.sub(r"\s+", " ", kv.get(field, "")).strip()
            if len(re.sub(r"\D", "", raw)) >= 7:
                ms.append(raw)  # 固话（含分机），merge 按固话处理
                # EN: Landlines (including extensions); merge treats them as landlines
                # JA: 固定電話（内線を含む）。merge は固定電話として扱う
                break
    b["phone"] = "; ".join(ms)
    b["email"] = "; ".join(es)
    if not b["full_name"]:
        # 2021 版头部：“宋女士 在职，看看新机会 女 | 28岁 | 威海 | 本科 | 工作2年”
        # EN: 2021 version header: "<surname>女士 在职，看看新机会 女 | 28岁 | 威海 | 本科 | 工作2年" (Ms X, employed, open to new opportunities, female | 28 | Weihai | bachelor | 2 years of work)
        # JA: 2021 年版のヘッダー：「<姓>女士 在职，看看新机会 女 | 28岁 | 威海 | 本科 | 工作2年」（〇〇さん、在職中・新しい機会を検討、女性｜28 歳｜威海｜学士｜勤続 2 年）
        for l in lines[:6]:
            mh = re.match(r"^([一-鿿·]{2,6})\s+(?:(?:在职|离职|应届|目前)\S*\s+)?(男|女)\s*[|｜]\s*(\d{2})岁\s*[|｜]\s*([^|｜]+?)\s*[|｜]", l)
            if mh:
                b["full_name"], b["gender"], b["age"], b["city"] = mh.group(1), mh.group(2), mh.group(3), mh.group(4).strip()
                break
    for k in ("目前求职状态",):
        if kv.get(k):
            IGN.append(k + "：" + kv[k])
    exp = empty("expected_list")
    exp["expected_city"] = val(kv.get("期望地点", ""))
    exp["expected_position"] = val(kv.get("期望职位", ""))
    exp["expected_industry"] = val(kv.get("期望行业", ""))
    sal = val(kv.get("期望年薪", "")) or val(kv.get("期望月薪", "")) or val(kv.get("期望薪资", ""))
    if not sal and re.match(r"^(面议|保密)", kv.get("勿推企业", "") or kv.get("勿推荐企业", "")):
        sal = ""
    exp["expected_salary"] = sal
    cur = {"company": val(kv.get("公司名称", "")), "position": val(kv.get("所任职位", "")),
           "industry": val(kv.get("所在行业", "")), "salary": val(kv.get("目前年薪", "")) or val(kv.get("目前薪资", ""))}
    upd = ""
    mu = re.search(r"((?:19|20)\d{2})-(\d{1,2})-(\d{1,2})", kv.get("简历更新时间", "") or kv.get("最新登录", "") or kv.get("更新时间", ""))
    if mu:
        upd = f"{mu.group(1)}-{int(mu.group(2)):02d}-{int(mu.group(3)):02d}"
    return b, ([exp] if any(exp.values()) else []), cur, upd


# ------------------------------------------------------------------ 工作经历
# EN: ------------------------------------------------------------------ Work history
# JA: ------------------------------------------------------------------ 職歴
LONG = {"工作职责和业绩": "position_responsibilities", "工作职责": "position_responsibilities",
        "工作业绩": "position_achievements", "职责业绩": "position_responsibilities", "离职原因": "resigned_reason",
        "工作内容": "position_responsibilities", "所用技术": "position_responsibilities"}
ROLE_LAB = {"所在部门": "position_dept", "汇报对象": "position_report_to", "下属人数": "position_subordinate",
            "薪酬状况": "position_salary", "月薪": "position_salary"}


def parse_work(lines):
    blocks = []          # 每个公司块：{company, start, end, industry, employees, btype, roles:[...]}
    # EN: Each company block: {company, start, end, industry, employees, btype, roles:[...]}
    # JA: 各会社のブロック：{company, start, end, industry, employees, btype, roles:[...]}
    blk = role = None
    long_field = pend = None

    def new_role(pos, start="", end=""):
        r = empty("work_experiences")
        ms_ = SALARY_RE.search(pos)
        if ms_:
            r["position_salary"] = ms_.group(0).replace(" ", "")
            pos = val(pos[:ms_.start()] + pos[ms_.end():])
        r["position"] = pos
        r["position_start"], r["position_resigned"] = start, end
        blk["roles"].append(r)
        return r

    def role_from_pending():
        """公司描述之后、职位标签之前的无标签行：最后一个非薪资行是职位（.htm 版公司描述会拆成多行）。

        EN: Unlabelled lines after the company description and before the position label: the last non-salary line is the position (in the .htm version the company description is split over several lines).

        JA: 会社の説明の後、職位のラベルの前にあるラベルのない行：給与でない最後の行が職位（.htm 版では会社の説明が複数行に分かれる）。
        """
        pf = blk.get("pend_free") or []
        sal, pos = "", ""
        for x in reversed(pf):
            xs = x.replace(" ", "")
            if not sal and SALARY_RE.fullmatch(xs):
                sal = xs
            elif not pos and not SALARY_RE.fullmatch(xs):
                pos = x
                break
        IGN.extend(x for x in pf if x != pos and not SALARY_RE.fullmatch(x.replace(" ", "")))
        blk["pend_free"] = []
        ms_ = SALARY_RE.search(pos)
        if ms_:
            sal = sal or ms_.group(0).replace(" ", "")
            pos = pos[:ms_.start()] + pos[ms_.end():]
        r = new_role(val(pos))
        r["position_salary"] = sal or r["position_salary"]
        return r

    for l in lines:
        m = START_RE.match(l)
        m2 = None if m else START2_RE.match(l)
        if m2 and not LABEL_RE.search(l):
            sub = RANGE_RE.search(l)
            start, end = range_of(sub)
            blk = {"company": m2.group(1).strip(), "start": start, "end": end, "industry": "", "employees": "",
                   "btype": False, "roles": [], "desc": False, "pend_free": []}
            blocks.append(blk)
            role, long_field = None, None
            continue
        if m and long_field and role is not None and re.search(r"[，,。；;、:：]|^(期间|就职|进入|作为|负责|担任|主要|从事)", l[m.end():].strip()):
            # 职责正文里以日期开头的句子（“2012.03—2013.01 从事天猫商城…”），不是新的公司
            # EN: Sentences in the duties text starting with a date ("2012.03—2013.01 从事天猫商城…" (worked on the Tmall store …)) are not a new company
            # JA: 職務の本文で日付から始まる文（「2012.03—2013.01 从事天猫商城…」（天猫モールの〜に従事））は新しい会社ではない
            role[long_field] = join_cont(role[long_field], l).strip()
            continue
        if m:
            start, end = range_of(m)
            rest = l[m.end():].strip(" \t|")
            btype = l.startswith("搜索同事") or bool(DUR_RE.search(rest))
            if blk and role is None and blk.get("pend_free") and not rest and not btype:
                # “销售担当”下一行单独的“2008.02 - 至今”：是这个职位的时间，不是新公司
                # EN: A standalone "2008.02 - 至今" on the line after "销售担当" (sales person in charge): it is this position's period, not a new company
                # JA: 「销售担当」（営業担当）の次の行にある単独の「2008.02 - 至今」：この職位の期間であり、新しい会社ではない
                role = role_from_pending()
                role["position_start"], role["position_resigned"] = start, end
                long_field = None
                continue
            if blk and blk["btype"] and not btype:
                # 网页版：公司块下的职位行“2010.04 - 至今品牌经理”
                # EN: Web version: position lines under a company block "2010.04 - 至今品牌经理" (brand manager)
                # JA: Web 版：会社のブロックの下の職位の行「2010.04 - 至今品牌经理」（ブランドマネージャー）
                role = new_role(rest, start, end)
                long_field = None
                continue
            blk = {"company": DUR_RE.sub("", rest).strip(), "start": start, "end": end, "industry": "", "employees": "",
                   "btype": btype, "roles": [], "desc": False, "pend_free": []}
            blocks.append(blk)
            role, long_field = None, None
            continue
        if blk is None:
            continue
        toks = tokens(l)
        if toks[0][0] is None and long_field and role is not None:
            # 多行职责/业绩的续行（其中可能夹着“工作业绩：”）
            # EN: Continuation lines of multi-line duties/achievements (which may include "工作业绩：" (work achievements:))
            # JA: 複数行の職務・実績の続きの行（途中に「工作业绩：」（業務実績：）が挟まることがある）
            role[long_field] = join_cont(role[long_field], toks[0][1]).strip()
            toks = toks[1:]
            if not toks:
                continue
        if toks[0][0] is None and pend:
            # 上一行是“公司规模：”这类空值标签，本行是它的值
            # EN: The previous line is an empty-valued label like "公司规模：" (company size:); this line is its value
            # JA: 前の行が「公司规模：」（会社規模：）のような値の空のラベルで、この行がその値
            toks = [(pend, toks[0][1])] + toks[1:]
        pend = None
        for lab, v in toks:
            if lab is not None and not v and lab not in LONG and lab != "公司描述":
                pend = lab
            if lab is None:
                if not blk["company"]:
                    blk["company"] = v
                    continue
                if blk["btype"] and role is None:
                    # 网页版公司块头：“国内上市公司 | IT服务/系统集成 | 1000-2000人”或单独的行业行，之后是公司简介
                    # EN: Web-version company block header: "国内上市公司 | IT服务/系统集成 | 1000-2000人" (domestic listed company | IT services/system integration | 1000-2000 people) or a standalone industry line, followed by the company profile
                    # JA: Web 版の会社のブロックの見出し：「国内上市公司 | IT服务/系统集成 | 1000-2000人」（国内上場企業｜IT サービス・システムインテグレーション｜1000〜2000 人）または単独の業界の行で、その後に会社紹介が続く
                    if not blk["industry"] and not blk["desc"]:
                        parts = [x.strip() for x in re.split(r"\s*[|｜]\s*", v) if x.strip()]
                        for p in parts:
                            if EMP_RE.match(p):
                                blk["employees"] = p
                        inds = [p for p in parts if not EMP_RE.match(p)]
                        blk["industry"] = inds[-1] if inds else ""
                        blk["desc"] = True
                    else:
                        IGN.append(v)
                    continue
                if role is None and blk["desc"] and not RANGE_RE.search(v):
                    blk.setdefault("pend_free", []).append(v)
                    continue
                if role is None or (role["position"] and (START_RE.search(v) or RANGE_RE.search(v))):
                    # 职位行：“高级注册专员 12000元/月”或“人力资源主管  2012/07-至今”
                    # EN: Position lines: "高级注册专员 12000元/月" (senior registration specialist, 12000 yuan/month) or "人力资源主管  2012/07-至今" (HR supervisor)
                    # JA: 職位の行：「高级注册专员 12000元/月」（シニア登録担当、月 12000 元）または「人力资源主管  2012/07-至今」（人事主任）
                    mr = RANGE_RE.search(v)
                    pos = v[:mr.start()] if mr else v
                    st, en = range_of(mr) if mr else ("", "")
                    msal = SALARY_RE.search(pos)
                    sal = ""
                    if msal:
                        sal = msal.group(0).replace(" ", "")
                        pos = pos[:msal.start()] + pos[msal.end():]
                    role = new_role(val(pos), st, en)
                    role["position_salary"] = sal or role["position_salary"]
                    long_field = None
                    continue
                if role is not None and not role["position_salary"] and SALARY_RE.fullmatch(v.replace(" ", "")):
                    role["position_salary"] = v.replace(" ", "")
                continue
            if lab == "公司性质":
                continue
            if lab == "公司规模":
                blk["employees"] = val(v)
            elif lab in ("公司行业", "所属行业"):
                blk["industry"] = val(v)
            elif lab == "公司描述":
                blk["desc"] = True
                IGN.append(v)
            elif lab == "所在地区":
                if role is None and blk.get("pend_free"):
                    role = role_from_pending()
            elif lab in ROLE_LAB:
                if role is None:
                    role = role_from_pending()
                role[ROLE_LAB[lab]] = val(v)
            elif lab in LONG:
                if role is None:
                    role = role_from_pending()
                long_field = LONG[lab]
                v2 = re.sub(r"^(工作职责|工作描述)\s*[:：]\s*", "", v)
                if lab == "所用技术" and v2:
                    v2 = "所用技术：" + v2
                role[long_field] = join_cont(role[long_field], v2).strip()
            elif lab in ("公司名称", "所任职位"):
                pass
    out = []
    for b in blocks:
        roles = b["roles"] or [None]
        for r in roles:
            w = r if r is not None else empty("work_experiences")
            w["company_name"] = re.sub(r"\s+(?=[（(])", "", b["company"]).strip()
            w["company_industry"] = w["company_industry"] or b["industry"]
            w["company_employees"] = w["company_employees"] or b["employees"]
            if not w["position_start"]:
                w["position_start"], w["position_resigned"] = b["start"], b["end"]
            for f in ("position_responsibilities", "position_achievements"):
                t = w[f]
                # “工作职责：… 工作业绩：…”写在同一段里
                # EN: "工作职责：… 工作业绩：…" (duties: … achievements: …) written in the same paragraph
                # JA: 「工作职责：… 工作业绩：…」（職務：… 実績：…）が同じ段落に書かれている
                mm = re.search(r"\n?\s*工作业绩\s*[:：]", t)
                if f == "position_responsibilities" and mm:
                    w["position_achievements"] = (t[mm.end():].strip() + ("\n" + w["position_achievements"] if w["position_achievements"] else "")).strip()
                    w[f] = t[:mm.start()].strip()
                w[f] = re.sub(r"^(工作职责|工作业绩)\s*[:：]\s*", "", w[f]).strip()
            for f in ("position", "position_dept", "position_report_to", "position_subordinate", "position_salary"):
                w[f] = val(w[f])
            w["status"] = "在职" if w["position_resigned"] == "至今" else ("离职" if w["position_resigned"] else "")
            w["employment_type"] = "全职"
            if w["company_name"] or w["position"]:
                out.append(w)
    return out


# ------------------------------------------------------------------ 项目 / 培训
# EN: ------------------------------------------------------------------ Projects / training
# JA: ------------------------------------------------------------------ プロジェクト・研修
def parse_ranged(lines, lst, name_field, labmap, long_labs):
    out, cur, long_field, pend = [], None, None, None
    for l in lines:
        m = START_RE.match(l)
        if m:
            cur = empty(lst)
            cur["start_ym"], cur["end_ym"] = range_of(m)
            cur[name_field] = l[m.end():].strip(" \t|")
            out.append(cur)
            long_field = None
            continue
        if cur is None:
            continue
        toks = tokens(l)
        if toks[0][0] is None and pend:
            toks = [(pend, toks[0][1])] + toks[1:]
        pend = None
        for lab, v in toks:
            if lab is None:
                if not cur[name_field]:
                    cur[name_field] = v
                elif long_field:
                    cur[long_field] = join_cont(cur[long_field], v).strip()
                continue
            if not v and lab not in long_labs:
                pend = lab
                continue
            f = labmap.get(lab)
            if not f:
                continue
            v = re.sub(r"^(项目描述|项目职责|项目业绩|培训描述)\s*[:：]\s*", "", v)
            cur[f] = join_cont(cur[f], v).strip() if cur[f] else val(v)
            long_field = f if lab in long_labs else None
    for i, it in enumerate(out, 1):
        it["sequence_no"] = str(i)
    return out


# ------------------------------------------------------------------ 教育 / 语言 / 附加
# EN: ------------------------------------------------------------------ Education / languages / additional
# JA: ------------------------------------------------------------------ 学歴・語学・付加情報
def degree_of(x):
    return next((d for d in DEGREES if d in x), "")


def parse_edu(lines):
    out, cur, pend = [], None, None
    # “华东理工大学”+“( 2009.09-2012.03 )”分两行 → 拼成一行
    # EN: "华东理工大学" + "( 2009.09-2012.03 )" on two lines → joined into one line
    # JA: 「华东理工大学」+「( 2009.09-2012.03 )」が 2 行に分かれている → 1 行につなげる
    merged = []
    for l in lines:
        mr = RANGE_RE.search(l)
        if merged and mr and not l[:mr.start()].strip(" \t(（") and not LABEL_RE.search(merged[-1]) and not RANGE_RE.search(merged[-1]):
            merged[-1] = merged[-1] + "  " + l.strip(" \t(（)）")
        else:
            merged.append(l)
    for l in merged:
        mr = RANGE_RE.search(l)
        if mr and not LABEL_RE.match(l):
            cur = empty("education_list")
            cur["school_start_ym"], cur["school_end_ym"] = range_of(mr)
            if cur["school_end_ym"] == "至今":
                cur["school_end_ym"] = ""
            before = l[:mr.start()].strip(" \t（(")
            after = l[mr.end():].strip(" \t）)")
            cur["school_name"] = re.sub(r"\s+", "", before) if re.search(r"[一-鿿]", before) else before
            parts = [x for x in re.split(r"\t+|\s{2,}", after) if x.strip()]
            if not parts and re.search(r"\s{2,}", before):
                # 2021 版：“和歌山大學  信息工程·本科·统招 2014.03-2019.03”
                # EN: 2021 version: "和歌山大學  信息工程·本科·统招 2014.03-2019.03"
                # JA: 2021 年版：「和歌山大學  信息工程·本科·统招 2014.03-2019.03」
                b0, b1 = re.split(r"\s{2,}", before, maxsplit=1)
                cur["school_name"] = b0.strip()
                parts = [x for x in re.split(r"[·•]", b1) if x.strip()]
                before = b0
            for p in parts:
                d = degree_of(p)
                if p.strip() in ("统招", "非统招"):
                    cur["school_education_type"] = p.strip()
                elif d and len(p) <= 6:
                    cur["school_degree_type"] = d
                elif not cur["school_major_name"]:
                    cur["school_major_name"] = p.strip()
            out.append(cur)
            continue
        if cur is None:
            continue
        toks = tokens(l)
        if toks[0][0] is None and pend:
            toks = [(pend, toks[0][1])] + toks[1:]
        pend = None
        for lab, v in toks:
            if lab is not None and not v:
                pend = lab
            if lab is None:
                # 无标签的“土木工程”“本科”两行
                # EN: Two unlabelled lines "土木工程" (civil engineering), "本科" (bachelor)
                # JA: ラベルのない「土木工程」（土木工学）と「本科」（学士）の 2 行
                d = degree_of(v)
                if d and len(v) <= 6 and not cur["school_degree_type"]:
                    cur["school_degree_type"] = d
                elif not cur["school_major_name"] and len(v) <= 30 and not d:
                    cur["school_major_name"] = v
            if lab == "专业":
                cur["school_major_name"] = val(v)
            elif lab in ("学历", "教育程度"):
                cur["school_degree_type"] = degree_of(v) or val(v)
            elif lab == "是否统招":
                cur["school_education_type"] = "统招" if v.startswith("是") else ("非统招" if v.startswith("否") else "")
    return out


def parse_lang(lines):
    out = []
    for l in lines:
        for x in re.split(r"[、,，;；/]\s*|\s{2,}|\t", l):
            x = x.strip()
            if 1 < len(x) <= 12 and not LABEL_RE.search(x) and re.search(r"[一-鿿A-Za-z]", x):
                it = empty("language_list")
                it["language_name"] = x
                out.append(it)
    return out


CERT_LINE = re.compile(r"^((?:19|20)\d{2})\s*/\s*(\d{1,2})\s+(.+)$")


def parse_extra(lines):
    """附加信息：“2011 /7 全国普通高等大学毕业证书”这类行拆成证书，其余作为文字。

    EN: Additional info: lines like "2011 /7 全国普通高等大学毕业证书" (national general higher education graduation certificate) are split into certificates; the rest is kept as text.

    JA: 付加情報：「2011 /7 全国普通高等大学毕业证书」（全国普通高等教育卒業証書）のような行は資格に分け、残りはテキストとする。
    """
    certs, text = [], []
    for l in lines:
        segs = [x.strip() for x in re.split(r"\t+", l) if x.strip()]
        joined = " ".join(segs)
        items = re.split(r"\s+(?=(?:19|20)\d{2}\s*/\s*\d{1,2}\s)", joined)
        hit = False
        for it in items:
            m = CERT_LINE.match(it.strip())
            if m and re.search(r"(证|证书|资格|等级|四级|六级|考试|合格|N[1-5]|级)", m.group(3)):
                c = empty("certificate_list")
                c["certificate_time"] = ym(m.group(1), m.group(2))
                c["certificate_name"] = m.group(3).strip()
                certs.append(c)
                hit = True
        if not hit:
            text.append(l)
    return certs, "\n".join(text).strip()


# ------------------------------------------------------------------ 入口
# EN: ------------------------------------------------------------------ Entry point
# JA: ------------------------------------------------------------------ エントリ
def detect(text: str) -> bool:
    h = unicodedata.normalize("NFKC", text[:3000])
    if re.search(r"X-51JOB|51job\.com|前程无忧", h) or re.search(r"智联招聘|zhaopin\.com", h[:300]):
        return False
    if re.search(r"(推荐理由|顾问评价|候选人推荐报告|推荐报告)", h[:1500]):
        return False
    return bool("目前职业概况" in h or ("简历编号" in h[:1500] and "期望职位" in text))


def parse(text: str):
    if not detect(text):
        return None
    lines = norm_lines(text)
    FRAG["on"] = fragmented(lines)
    IGN.clear()
    tail = []
    kept = []
    for l in lines:
        # 平台声明、操作记录、底部“简历编号 | 更新时间”：不是简历内容
        # EN: Platform disclaimers, operation logs, the bottom "简历编号 | 更新时间" (résumé number | update time): not résumé content
        # JA: プラットフォームの声明・操作記録・末尾の「简历编号 | 更新时间」（履歴書番号｜更新日時）：履歴書の内容ではない
        if re.match(r"^(声明\s*[:：]|操作时间\s*[:：]|简历编号\s*[:：].*更新时间)", l):
            IGN.append(l)
            if l.startswith("简历编号"):
                tail.append(l)
            continue
        kept.append(l)
    lines = kept
    secs, cur = [["head", []]], None
    for l in lines:
        key = re.sub(r"[\s:：]+$", "", re.sub(r"^[|｜]\s*", "", l))
        if key in SECTIONS:
            cur = [SECTIONS[key], []]
            secs.append(cur)
            continue
        (cur or secs[0])[1].append(l)
    head = [l for k, body in secs if k == "head" for l in body] + [x for t_ in tail for x in re.split(r"\s*[|｜]\s*", t_)]
    base, expected, curjob, updated = parse_head(head)
    res = {"resume_languge": "zh", "base_info": base}
    for lst in C.LIST_FIELDS:
        res[lst] = []
    res["expected_list"] = expected
    prs, unmapped = [], []
    for kind, body in secs[1:]:
        if kind == "head":
            continue
        if kind == "work":
            res["work_experiences"] += parse_work(body)
        elif kind == "proj":
            res["project_list"] += parse_ranged(body, "project_list", "project_name",
                                                {"项目职务": "role_name", "所在公司": "company_or_client", "项目简介": "description",
                                                 "项目描述": "description", "项目职责": "responsibilities", "项目业绩": "achievements"},
                                                {"项目简介", "项目描述", "项目职责", "项目业绩"})
        elif kind == "train":
            res["training_list"] += parse_ranged(body, "training_list", "training_name",
                                                 {"培训机构": "organization_name", "培训课程": "training_name",
                                                  "所获证书": "certificate_name", "培训描述": "description"}, {"培训描述"})
        elif kind == "edu":
            res["education_list"] += parse_edu(body)
        elif kind == "lang":
            res["language_list"] += parse_lang(body)
        elif kind == "pr":
            prs.append("\n".join(body).strip())
        elif kind in ("extra", "cert"):
            certs, txt = parse_extra(body)
            res["certificate_list"] += certs
            if txt:
                prs.append(txt)
        elif kind == "skill":
            for l in body:
                for x in re.split(r"[、,，;；]\s*|\t+", l):
                    if x.strip():
                        it = empty("skills_list")
                        it["skill_name"] = x.strip()
                        res["skills_list"].append(it)
        else:
            unmapped.append(kind)
    base["pr"] = "\n".join(p for p in prs if p)
    if not res["work_experiences"] and (curjob["company"] or curjob["position"]):
        w = empty("work_experiences")
        w["company_name"], w["position"], w["company_industry"] = curjob["company"], curjob["position"], curjob["industry"]
        w["status"] = "在职"
        w["employment_type"] = "全职"
        res["work_experiences"].append(w)
    return {"resume": res, "updated": updated, "unmapped": unmapped, "notes": [], "content_lang": "zh", "has_zh_part": False,
            "ignored_lines": [x for x in IGN if len(x) >= 6]}


if __name__ == "__main__":
    import json
    import sys
    print(json.dumps(parse(Path(sys.argv[1]).read_text(encoding="utf-8")), ensure_ascii=False, indent=1))
