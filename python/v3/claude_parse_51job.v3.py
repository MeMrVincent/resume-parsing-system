#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
claude_parse_51job.v3.py —— 前程无忧（51job）导出简历的新解析器（含猎聘同类版式的兜底识别）。

直接从原文全文解析。入口：detect(text) -> bool，parse(text) -> dict | None（结构同 claude_parse_cn_platform.v3.py）。

覆盖的真实版式：
  A. 51job 旧版（2010-2016，.doc 实为 MIME / .mht）：标签与值分行，“2013/4--2015/9：公司(50-150人)”“[ 2 年5个月]”
     “所属行业：X”，其后两行为 部门 / 职位，再往后是工作描述（无“工作描述”标签）
  B. 51job 新版 mht（2017-2018）：每个词单独一行（碎片），“公司 (2个月 )”“行业 | 规模 | 性质”“部门”“职位”“工作描述：”
  C. 51job docx 导出（2018-2020）：整段压成少数长行，制表符分隔，“2019/3-至今\t公司 (9个月 )\t行业|规模|性质 部门\t职位 工作描述：…”
解析前先“回流”：把长行在日期区间、栏目名、描述标签前断开，把碎片行接回，统一成逐行结构后再按栏目解析。

EN: claude_parse_51job.v3.py -- new parser for résumés exported from 51job (Qiancheng Wuyou), including fallback recognition of the similar Liepin layout.

Parses directly from the full source text. Entry points: detect(text) -> bool, parse(text) -> dict | None (structure as in claude_parse_cn_platform.v3.py).

Real layouts covered:
  A. Old 51job (2010-2016, .doc that is really MIME / .mht): labels and values on separate lines, "2013/4--2015/9：company(50-150人)", "[ 2 年5个月]",
     "所属行业：X" (industry: X), followed by two lines department / position, then the job description (without a "工作描述" label)
  B. New 51job mht (2017-2018): every word on its own line (fragments), "company (2个月 )", "industry | size | type", "department", "position", "工作描述："
  C. 51job docx export (2018-2020): whole paragraphs compressed into a few long lines, tab-separated, "2019/3-至今	company (9个月 )	industry|size|type department	position 工作描述：…"
Before parsing, "reflow" first: break long lines before date ranges, section names and description labels, join fragment lines back, unify into a line-by-line structure, then parse by section.

JA: claude_parse_51job.v3.py —— 前程无忧（51job）からエクスポートした履歴書の新しいパーサー（同様のレイアウトの Liepin の最終手段の識別を含む）。

原文の全文から直接解析する。エントリ：detect(text) -> bool、parse(text) -> dict | None（構造は claude_parse_cn_platform.v3.py と同じ）。

対応する実際のレイアウト：
  A. 51job の旧版（2010〜2016、実態は MIME / .mht の .doc）：ラベルと値が別の行、「2013/4--2015/9：会社(50-150人)」「[ 2 年5个月]」、
     「所属行业：X」（所属業界：X）、その後の 2 行が 部署 / 職位、さらにその後が職務説明（「工作描述」のラベルなし）
  B. 51job の新版 mht（2017〜2018）：語ごとに 1 行（断片）、「会社 (2个月 )」「業界 | 規模 | 性質」「部署」「職位」「工作描述：」
  C. 51job の docx エクスポート（2018〜2020）：段落全体が少数の長い行に詰め込まれ、タブ区切り、「2019/3-至今	会社 (9个月 )	業界|規模|性質 部署	職位 工作描述：…」
解析の前にまず「行の組み直し」を行う：長い行を期間・欄の名前・説明のラベルの前で区切り、断片の行をつなぎ直して、1 行ずつの構造に統一してから欄ごとに解析する。
"""

import re
import unicodedata
from pathlib import Path
import importlib.util

HERE = Path(__file__).resolve().parent


def _load(name, file):
    spec = importlib.util.spec_from_file_location(name, HERE / file)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


CN = _load("claude_parse_cn_platform_v3_51", "claude_parse_cn_platform.v3.py")
C = CN.C
K = CN.K

SECTIONS = {
    "最近工作": "skip", "学历": "skip", "个人信息": "skip", "基本信息": "skip",
    "求职意向": "expected", "自我评价": "pr", "工作经验": "work", "工作经历": "work", "实习经验": "work", "实习经历": "work",
    "项目经验": "project", "项目经历": "project", "教育经历": "edu", "教育背景": "edu",
    "培训经历": "training", "证书": "cert", "语言能力": "lang", "技能/语言": "langskill", "IT技能": "skill", "技能特长": "langskill",
    "专业技能": "skill", "在校情况": "practice", "校内荣誉": "other", "校内职务": "practice", "社会经验": "practice",
    "学生实践经验": "practice", "社会实践": "practice", "实践经验": "practice",
    "附加信息": "other", "其他信息": "other", "其他": "other", "所获奖项": "other", "获奖经历": "other",
}
RANGE_SLASH = r"(?:19|20)\d{2}\s*/\s*\d{1,2}\s*-+\s*(?:至今|现在|(?:19|20)\d{2}\s*/\s*\d{1,2})"
SPLIT_BEFORE = re.compile(
    r"(?<=\S)\s+(?=(?:" + RANGE_SLASH + r"))"
    r"|(?<=\S)\s+(?=(?:最近工作|个人信息|求职意向|自我评价[:：]|工作经验|工作经历|项目经验|教育经历|在校情况|校内荣誉|校内职务|技能特长|"
    r"技能/语言|证书|培训经历|附加信息|语言能力|IT\s*技能|学生实践经验|校内职务)(?:\s|[:：]|$))"
    r"|(?<=\S)\s+(?=(?:工作描述|项目描述|责任描述|专业描述|职务描述|培训机构|培训地点|培训描述|所属行业|关键字|期望薪资|地点|职能/职位|"
    r"行业|到岗时间|工作类型|户口/国籍|婚姻状况|目前年收入|政治面貌|家庭地址)\s*[:：])")
SIZE_RE = re.compile(r"(少于\s*\d+\s*人|\d+\s*-\s*\d+\s*人|\d+\s*人以上|\d+\s*人以下)")
NATURE_RE = re.compile(r"^(外资\s*[（(]\s*非?欧美\s*[)）]|外企代表处|民营公司|私营企业|国有企业|股份制企业|上市公司|事业单位|政府机关|非营利组织|"
                       r"创业公司|国家机关|外资|合资|国企|民营|私营)")
DUR_ANY = re.compile(r"[\[［(（]\s*(?:\d+\s*年)?\s*(?:\d+\s*个?\s*月)?\s*[\]］)）]")


def detect(text: str) -> bool:
    h = unicodedata.normalize("NFKC", text[:2500])
    if CN.detect(text):
        return False
    return bool(re.search(r"51job|前程无忧|\(ID:\d{6,}\)|ID:\d{6,}|最近工作\s*[\[（(]|职\s*位\s*[:：].*\n?.*公\s*司\s*[:：]", h))


EN_START_RE = re.compile(r"(Process Status|Career Objective|Recent Work|Basic Info\.|Personal Information|Work Experience|"
                         r"I'm looking for jobs|Only good opportunities)")


def reflow(text: str):
    t = unicodedata.normalize("NFKC", text).replace("\u3000", " ")
    # 中英文双版本导出：中文部分之后出现英文版本时截断（英文版本另行处理）
    # EN: Chinese-English dual-version exports: truncate when an English version appears after the Chinese part (the English version is handled separately)
    # JA: 中英 2 版のエクスポート：中国語部分の後に英語版が現れたらそこで切る（英語版は別に処理する）
    mcn = re.search(r"(工作经验|教育经历)", t)
    if mcn:
        men = EN_START_RE.search(t, mcn.end())
        if men:
            cut = t.rfind("\n", 0, men.start())
            t = t[:cut if cut > mcn.end() else men.start()]
    t = re.sub(r"\*{4,}\S*", " ", t)  # 打码的联系方式
    # EN: Masked contact details
    # JA: マスクされた連絡先
    lines = []
    for raw in t.split("\n"):
        raw = raw.rstrip()
        lines += SPLIT_BEFORE.split(raw)
    out = CN.norm_lines("\n".join(x for x in lines if x is not None))
    g = []
    for l in out:
        if g and g[-1] not in SECTIONS and l not in SECTIONS and (
                re.match(r"^[（(|｜]", l) or g[-1].endswith(("|", "｜")) or g[-1].count("(") + g[-1].count("（") > g[-1].count(")") + g[-1].count("）")):
            g[-1] = g[-1] + ("" if re.match(r"^[)）]", l) else " ") + l
        else:
            g.append(l)
    out = g
    # 标题被拆成两行（“证”“书”）或带多余空白（“IT    技能”）
    # EN: Headings split over two lines ("证" "书") or with extra whitespace ("IT    技能")
    # JA: 2 行に分かれた見出し（「证」「书」）や余分な空白のある見出し（「IT    技能」）
    fixed = []
    for l in out:
        l2 = re.sub(r"\s+", "", l) if len(l) <= 12 else l
        if fixed and fixed[-1] + l2 in SECTIONS:
            fixed[-1] = fixed[-1] + l2
            continue
        if l2 in SECTIONS:
            fixed.append(l2)
            continue
        m = re.match(r"^(自我评价|附加信息)\s*[:：]\s*(.*)$", l)
        if m:
            fixed.append(m.group(1))
            if m.group(2).strip():
                fixed.append(m.group(2).strip())
            continue
        fixed.append(l)
    return fixed


# ------------------------------------------------------------------ 头部
# EN: ------------------------------------------------------------------ Header
# JA: ------------------------------------------------------------------ ヘッダー
NAME_STOP = CN.NAME_STOP | {"部门", "行业", "职位", "公司", "学校", "专业", "地点", "职能", "个人信息", "标签", "匹配度", "流程状态", "下载简历", "目前正在找工作", "观望有好机会会考虑", "我目前在职", "剩余下载数"}


def parse_header(lines):
    b = {k: "" for k in C.BASE_FIELDS}
    b["platform_from"] = "前程无忧(51job)"
    joined = re.sub(r"\s+", " ", " ".join(lines))
    # 预处理：把粘连的“姓名+手机号/ID/标签”拆开，把“翁 佛全”这种带空格的姓名接上
    # EN: Pre-processing: split stuck "name + mobile/ID/label", and join names with spaces like "<surname> <given name>"
    # JA: 前処理：くっついた「氏名 + 携帯番号・ID・ラベル」を分け、「<姓> <名>」のように空白の入った氏名をつなげる
    hj = re.sub(r"([一-鿿])(?=\d|ID|[A-Za-z]{2,}@)", r"\1 ", joined[:900])
    hj = re.sub(r"(\d)(?=[A-Z][A-Za-z]+ [A-Z])", r"\1 ", hj)
    hj = re.sub(r"(?<![A-Za-z])[A-Z](?=[一-鿿]{2,3} )", "", hj)  # “I崇逢”这类残留的 ID 首字母
    # EN: Leftover ID initials like "I<name>"
    # JA: 「I<氏名>」のような ID の頭文字の残骸
    hj = re.sub(r"([一-鿿])(?=(?:流程状态|标签|匹配度|下载简历|目前正在找工作|观望有好机会会考虑|我目前))", r"\1 ", hj)
    hj = re.sub(r"(?<![一-鿿])([一-鿿]) ([一-鿿]{1,2})(?= (?:ID|标签|1[3-9]\d{9}|\S+@|流程状态|匹配度|下载简历|目前|观望))", r"\1\2", hj)
    name = ""
    for pat in (r"(?:姓\s*名)\s*[:：]\s*([一-鿿]{2,4})",
                r"([一-鿿]{2,4}) (?:匹配度|流程状态|标签)",
                r"ID\s*[:：]\s*\d{5,}\s*(?:ID\s*[:：]\s*\d{5,}\s*)?(?:下载简历\s*)?(?:目前正在找工作|观望有好机会会考虑)?\s*([一-鿿]{2,4}) ",
                r"([一-鿿]{2,4}) (?:ID\s*[:：]|1[3-9]\d{9}|\S+@)",
                r"([一-鿿]{2,4})\s+(?:[\d\-]+\s*年(?:以上)?|[一二三四五六七八九十]+年以上|\d+个月|无)工作经验\s*[|｜]",
                r"(?:^|\s)([一-鿿]{2,4})\s*[|｜]\s*(?:男|女)\s*[|｜]",
                r"([一-鿿]{2,4}) (?:手\s*机|电\s*话)\s*[:：]",
                r"(?:^|\s)([A-Z][A-Za-z]+(?: [A-Z][A-Za-z]+){1,2}) ID\s*[:：]",
                r"ID\s*[:：]\s*\d{5,}\s*(?:ID\s*[:：]\s*\d{5,}\s*)?([A-Za-z][A-Za-z .]{1,30}?)\s*(?:男|女|标签|1[3-9]\d{9}|\S+@|下载简历)"):
        for m in re.finditer(pat, hj):
            cand = m.group(1).strip()
            if C.name_quality(cand)[0] == "valid" and cand not in NAME_STOP and not CN.degree_of(cand) \
                    and not re.search(r"(区|市|省|县|工作|经验|简历|状态|职位|公司)$", cand):
                name = cand
                break
        if name:
            break
    if not name:
        # 只剩姓（“王”）或称呼：保留，merge 会标为姓名不可靠
        # EN: Only a surname ("王") or a form of address remains: keep it; merge will flag the name as unreliable
        # JA: 姓（「王」）か呼称しか残っていない：残す。merge が氏名を信頼できないと印を付ける
        m = re.search(r"(?:更新时间\s*[:：]\s*\d{4}-\d{2}-\d{2})\s+([一-鿿]{1,4})\s", hj)
        name = m.group(1) if m and m.group(1) not in NAME_STOP else ""
    b["full_name"] = name
    gm = re.search(r"(?<![一-鿿])(男|女)\s*[|｜]?\s*(\d{2})\s*岁", joined) or re.search(r"[|｜]\s*(男|女)\s*[|｜]", joined)
    if gm:
        b["gender"] = gm.group(1)
    ma = re.search(r"(\d{2})\s*岁", joined)
    b["age"] = ma.group(1) if ma else ""
    mb = re.search(r"岁\s*[（(]\s*((?:19|20)\d{2})\s*[年\-/]\s*(\d{1,2})(?:\s*[月\-/]\s*(\d{1,2}))?", joined)
    if mb:
        b["birth_year"] = mb.group(1)
        b["birth_date"] = f"{int(mb.group(1)):04d}年{int(mb.group(2)):02d}月{int(mb.group(3) or 1):02d}日"
    mm = re.search(r"(已婚|未婚|离异)", joined)
    b["marital_status"] = mm.group(1) if mm else ""
    mh = re.search(r"(\d{3})\s*cm", joined, re.I)
    b["height_cm"] = mh.group(1) if mh else ""
    mp = re.search(r"(中共党员|中共预备党员|共青团员|团员|群众|民主党派|无党派人士|无党派)", joined)
    b["political_status"] = mp.group(1) if mp else ""
    mr = re.search(r"(?:居住地|现居住地?|现居住)\s*[:：]?\s*([一-鿿A-Za-z\-]{2,20}(?:\s*[-\s]\s*[一-鿿]{2,10})?)", joined)
    if mr:
        b["address"] = mr.group(1).strip()
        b["city"] = CN.city_of(b["address"].replace("-", " "))
    mk = re.search(r"户口(?:/国籍)?\s*[:：]\s*([一-鿿]{2,10})", joined)
    b["household_registration"] = mk.group(1) if mk else ""
    ma2 = re.search(r"地\s*址\s*[:：]\s*([^|｜（(]{2,60}?)\s*(?:[（(]\s*邮编\s*[:：]\s*(\d{6})\s*[)）])?(?=\s|$)", joined)
    if ma2:
        b["address"] = ma2.group(1).strip() if len(ma2.group(1).strip()) > len(b["address"]) else b["address"]
        b["postal_code"] = ma2.group(2) or ""
    ms, es = [], []
    home = []  # “家庭电话”栏的手机号：本人另有手机号时多为家人号码，不收
    # EN: Mobile numbers in the "家庭电话" (home phone) field: when the person has another mobile of their own, it is usually a family member's number, so it is not taken
    # JA: 「家庭电话」（自宅電話）欄の携帯番号：本人に別の携帯番号がある場合は家族の番号であることが多いため、取らない
    segs = []
    for l in lines:
        for seg in re.split(r"[|｜]", l):
            if re.search(r"(家庭电话|家庭電話|家庭联系电话|家属电话|家人电话)", seg):
                home += [C.classify_phone(x)[1] for x in C.MOBILE_FIND.findall(seg) if C.classify_phone(x)[0] == "mobile"]
                continue
            segs.append(seg)
    for l in segs:
        if re.search(r"(公司电话|紧急联系|联系人|推荐人)", l):
            continue
        for x in C.MOBILE_FIND.findall(l):
            k, v = C.classify_phone(x)
            if k == "mobile" and v not in ms:
                ms.append(v)
        for x in C.EMAIL_FIND.findall(l):
            for part in C.split_glued(x):
                k, v = (C.classify_email(part) if "@" in part else C.classify_phone(part))
                if k == "email" and v not in es:
                    es.append(v)
                elif k == "mobile" and v not in ms:
                    ms.append(v)
    if not ms:
        ms = list(dict.fromkeys(home))
    b["phone"] = "; ".join(ms)
    b["email"] = "; ".join(es)
    mid = re.search(r"ID\s*[:：]\s*(\d{6,})", joined)
    b["platform_resume_id"] = mid.group(1) if mid else ""
    b["nationality"] = "中国"
    return b


# ------------------------------------------------------------------ 栏目
# EN: ------------------------------------------------------------------ Sections
# JA: ------------------------------------------------------------------ 欄
def parse_expected(lines):
    lab = {}
    txt = " ".join(lines)
    for key, pat in (("pos", r"(?:目标职能|职能/职位|期望职位)\s*[:：]\s*(.+?)(?=\s+\S{2,6}[:：]|$)"),
                     ("city", r"(?:目标地点|地点|期望工作地区)\s*[:：]\s*(.+?)(?=\s+\S{2,6}[:：]|$)"),
                     ("sal", r"期望薪资\s*[:：]\s*(.+?)(?=\s+\S{2,6}[:：]|$)"),
                     ("ind", r"(?:希望行业|行业)\s*[:：]\s*(.+?)(?=\s+\S{2,6}[:：]|$)"),
                     ("type", r"(?:工作性质|工作类型)\s*[:：]\s*(.+?)(?=\s+\S{2,6}[:：]|$)"),
                     ("start", r"(?:到岗时间|求职状态)\s*[:：]\s*(.+?)(?=\s+\S{2,6}[:：]|$)")):
        m = re.search(pat, txt)
        if m:
            lab[key] = re.sub(r"\s+", " ", m.group(1)).strip()
    if not lab:
        return []
    e = CN.empty("expected_list")
    e["expected_position"], e["expected_city"], e["expected_salary"] = lab.get("pos", ""), lab.get("city", ""), lab.get("sal", "")
    e["expected_industry"], e["expected_employment_type"], e["expected_start_date"] = lab.get("ind", ""), lab.get("type", ""), lab.get("start", "")
    return [e]


def _is_header_like(l):
    return len(l) <= 30 and not re.match(r"^\d+\s*[.、．)）]", l) and not re.search(r"[。；;]", l) and not re.search(r"[:：]", l)


def parse_work(lines):
    out = []
    for en in CN.split_entries(lines, desc_labels=("工作描述", "项目描述", "责任描述")):
        w = CN.empty("work_experiences")
        w["position_start"], w["position_resigned"] = CN.parse_range(en["m"])
        w["status"] = "在职" if w["position_resigned"] == "至今" else ("离职" if w["position_resigned"] else "")
        lab, pre = CN.take_label_blocks(en["body"], ["工作描述", "所属行业", "汇报对象", "下属人数", "离职原因", "工作业绩"])
        items = [x.strip() for x in re.split(r"\t+", en["rest"].lstrip("：: ")) if x.strip()]
        body_items = []
        for l in pre:
            body_items += [x.strip() for x in re.split(r"\t+", l) if x.strip()]
        allitems = [x for x in items + body_items if not re.fullmatch(r"[\[\]［］()（）|｜\s]+", x)]
        # 2019-2020 版：“职位|部门 公司 (时长) 行业|规模|性质”
        # EN: 2019-2020 version: "position|department company (tenure) industry|size|type"
        # JA: 2019〜2020 年版：「職位|部署 会社 (在職期間) 業界|規模|性質」
        if allitems:
            mv = re.match(r"^([^|｜()（）\[\]]{1,40})[|｜]([^()（）\[\]]+?)\s*[（(\[［]\s*(?:\d+\s*年)?\s*(?:\d+\s*个?月)?\s*[)）\]］]\s*(.*)$", allitems[0])
            if mv and not SIZE_RE.search(mv.group(1)):
                w["position"] = mv.group(1).strip()
                parts = mv.group(2).split()
                if len(parts) >= 2:
                    w["position_dept"], comp_v = parts[0], " ".join(parts[1:])
                else:
                    comp_v = mv.group(2).strip()
                allitems = [comp_v] + ([mv.group(3)] if mv.group(3).strip() else []) + allitems[1:]
            elif re.match(r"^(.+?)((?:\s*[（(]\s*(?:兼职|实习)\s*[)）])+)\s+(\S.+)$", allitems[0]):
                mj = re.match(r"^(.+?)((?:\s*[（(]\s*(?:兼职|实习)\s*[)）])+)\s+(\S.+)$", allitems[0])
                w["position"] = mj.group(1).strip() + ("(实习)" if "实习" in mj.group(2) else "")
                w["employment_type"] = "兼职" if "兼职" in mj.group(2) else w["employment_type"]
                allitems = [mj.group(3).strip()] + allitems[1:]
            elif "|" not in allitems[0] and re.match(r"^(\S{2,15}?(?:专员|助理|经理|主管|总监|工程师|代表|担当|文员|秘书|实习生|老师|教师|翻译|销售员|"
                                                      r"设计师|技术员|店员|营业员|客服|顾问|家教|兼职))\s+(\S.{1,60})$", DUR_ANY.sub("", allitems[0]).strip()):
                mp = re.match(r"^(\S{2,15}?(?:专员|助理|经理|主管|总监|工程师|代表|担当|文员|秘书|实习生|老师|教师|翻译|销售员|"
                              r"设计师|技术员|店员|营业员|客服|顾问|家教|兼职))\s+(\S.{1,60})$", DUR_ANY.sub("", allitems[0]).strip())
                w["position"] = mp.group(1)
                allitems = [mp.group(2)] + allitems[1:]
            else:
                mv2 = re.match(r"^([^|｜()（）\[\]]{1,30})\s*[|｜]\s*([^|｜]{1,30})$", allitems[0])
                if mv2 and len(allitems) > 1 and "|" not in allitems[1] and not SIZE_RE.search(allitems[0]):
                    w["position"], w["position_dept"] = mv2.group(1).strip(), mv2.group(2).strip()
                    allitems = allitems[1:]
        # 公司：第一项，去掉 (规模) (时长) [时长]
        # EN: Company: the first item, with (size) (tenure) [tenure] removed
        # JA: 会社：最初の項目から (規模) (在職期間) [在職期間] を除いたもの
        comp = allitems.pop(0) if allitems else ""
        ms = SIZE_RE.search(comp)
        if ms:
            w["company_employees"] = re.sub(r"\s", "", ms.group(1))
        comp = re.sub(r"[（(]\s*" + SIZE_RE.pattern + r"\s*[)）]", "", comp)
        comp = DUR_ANY.sub("", comp).strip()
        w["company_name"] = re.sub(r"\s*\(\s*\)|\s*（\s*）", "", comp).strip()
        ind_lines = lab.get("所属行业", "").split("\n")
        first = ind_lines[0].strip()
        # 压平的旧版：“所属行业： 建筑/建材/工程 商业设计部 建筑设计师 项目职责：…”
        # EN: Flattened old version: "所属行业： 建筑/建材/工程 商业设计部 建筑设计师 项目职责：…" (industry: construction/materials/engineering, commercial design dept, architect, project duties: …)
        # JA: 平坦化された旧版：「所属行业： 建筑/建材/工程 商业设计部 建筑设计师 项目职责：…」（所属業界：建築・建材・工事、商業デザイン部、建築デザイナー、プロジェクトの担当：…）
        mflat = re.match(r"^(\S+)\s+(\S{1,20})\s+(\S{1,20})(?:\s+(.*))?$", first)
        if mflat and ("/" in mflat.group(1) or K.INDUSTRY_SEG_RE.search(mflat.group(1))) and not re.search(r"[。，；,;]", mflat.group(2) + mflat.group(3)):
            w["company_industry"] = mflat.group(1)
            ind_lines = [first] + [mflat.group(2), mflat.group(3)] + ([mflat.group(4)] if mflat.group(4) else []) + ind_lines[1:]
        else:
            w["company_industry"] = first
        allitems += [x for x in ind_lines[1:] if x.strip()]
        rest_items = []
        for it in allitems:
            it = DUR_ANY.sub("", it).strip()
            if not it:
                continue
            if "|" in it or "｜" in it:
                segs = [x.strip() for x in re.split(r"[|｜]", it)]
                tail = ""
                for s in segs:
                    s2 = s
                    msz = SIZE_RE.match(s2)
                    if msz:
                        w["company_employees"] = w["company_employees"] or re.sub(r"\s", "", msz.group(1))
                        continue
                    mn = NATURE_RE.match(s2)
                    if mn:
                        tail = re.sub(r"^\s*[（(]\s*非?欧美\s*[)）]\s*", "", s2[len(mn.group(0)):]).strip()
                        continue
                    if not w["company_industry"]:
                        w["company_industry"] = s2
                if tail:
                    rest_items.append(tail)
                continue
            rest_items.append(it)
        # 描述：有“工作描述”标签用标签；否则（旧版）部门/职位之后的行
        # EN: Description: use the "工作描述" (job description) label if present; otherwise (old version) the lines after department/position
        # JA: 説明：「工作描述」（職務説明）のラベルがあればそれを使い、なければ（旧版）部署・職位の後の行を使う
        heads, desc = [], []
        for it in rest_items:
            if len(heads) < 2 and not desc and _is_header_like(it):
                heads.append(it)
            else:
                desc.append(it)
        heads = [re.sub(r"(海外经历|\(兼职\)|（兼职）)$", "", h).strip() for h in heads]
        if w["position"]:
            heads = []
        if len(heads) == 2:
            w["position_dept"], w["position"] = heads
        elif len(heads) == 1:
            w["position"] = heads[0]
        w["position_responsibilities"] = lab.get("工作描述") or "\n".join(desc)
        w["position_report_to"] = lab.get("汇报对象", "")
        w["position_subordinate"] = lab.get("下属人数", "")
        w["resigned_reason"] = lab.get("离职原因", "")
        w["position_achievements"] = lab.get("工作业绩", "")
        w["employment_type"] = w["employment_type"] or ("兼职" if "兼职" in " ".join(heads) else "全职")
        out.append(w)
    return out


EDU_RE = re.compile(r"^(.*?)\s+(博士后|博士|MBA|EMBA|硕士|本科|大专|中专|中技|高中|职高|初中|其他)\s*[|｜]\s*(.*)$")


def parse_edu(lines):
    out = []
    for en in CN.split_entries(lines, desc_labels=("专业描述",)):
        e = CN.empty("education_list")
        e["school_start_ym"], e["school_end_ym"] = CN.parse_range(en["m"])
        lab, pre = CN.take_label_blocks(en["body"], ["专业描述"])
        rest = en["rest"].lstrip("：: ").strip()
        m = EDU_RE.match(re.sub(r"\t+", " ", rest))
        if m:
            e["school_name"], deg, e["school_major_name"] = re.sub(r"海外经历$", "", m.group(1).strip()), m.group(2), m.group(3).strip()
        else:
            cols = [x for x in re.split(r"\t+|\s{2,}", rest) if x.strip()]
            cols += [x for x in pre[:3] if len(x) <= 30 and not re.search(r"[。；;:：]", x)]
            deg = ""
            for i, c in enumerate(cols):
                mds = re.match(r"^(博士后|博士|MBA|EMBA|硕士|本科|大专|中专|中技|高中|职高|初中)\s+(\S.*)$", c)
                if mds and i > 0:
                    deg = mds.group(1)
                    cols = cols[:i]
                    break
                mdm = re.match(r"^(博士后|博士|MBA|EMBA|硕士|本科|大专|中专|中技|高中|职高|初中|其他)\s*[|｜]\s*(.*)$", c)
                if mdm:
                    deg = mdm.group(1)
                    cols[i] = mdm.group(2).strip()
                    break
                if (CN.degree_of(c) and len(c) <= 8) or c in ("其他", "其它"):
                    deg = cols.pop(i)
                    break
            e["school_name"] = cols[0] if cols else ""
            e["school_major_name"] = cols[1] if len(cols) > 1 else ""
        e["school_degree_type"] = deg
        e["school_degree_rank"] = CN.DEGREE_RANK.get(CN.degree_of(deg), "")
        out.append(e)
    return out


def parse_training(lines):
    out = []
    for en in CN.split_entries(lines, desc_labels=("培训描述",)):
        t = CN.empty("training_list")
        t["start_ym"], t["end_ym"] = CN.parse_range(en["m"])
        lab, pre = CN.take_label_blocks(en["body"], ["培训机构", "培训地点", "培训描述", "所获证书", "培训课程"])
        rest = [x for x in re.split(r"\t+|\s{2,}", en["rest"].lstrip("：: ")) if x.strip()]
        items = rest + pre
        if lab.get("培训机构"):
            t["organization_name"] = lab["培训机构"].split("\n")[0].strip()
            t["training_name"] = items[0] if items else ""
            t["description"] = lab.get("培训描述", "") or "\n".join(items[1:])
        else:
            # 旧版：机构 / 课程 / [证书] / 描述
            # EN: Old version: provider / course / [certificate] / description
            # JA: 旧版：機関 / コース / [資格] / 説明
            t["organization_name"] = items[0] if items else ""
            t["training_name"] = items[1] if len(items) > 1 else ""
            rest2 = items[2:]
            if rest2 and len(rest2[0]) <= 20 and re.search(r"(证|证书|结业)", rest2[0]):
                t["certificate_name"] = rest2.pop(0)
            t["description"] = "\n".join(rest2)
        out.append(t)
    return out


def parse_cert(lines):
    out = []
    i = 0
    while i < len(lines):
        l = lines[i]
        m = re.match(r"^((?:19|20)\d{2})\s*[/.\-]\s*(\d{1,2})\s*(.*)$", l)
        if m:
            name = re.sub(r"^-+\s*(?:(?:19|20)\d{2}\s*/\s*\d{1,2}|至今)\s*", "", m.group(3).strip())
            if not name and i + 1 < len(lines):
                i += 1
                name = lines[i].strip()
            c = CN.empty("certificate_list")
            c["certificate_time"] = CN.ym(m.group(1), m.group(2))
            c["certificate_name"] = re.sub(r"^\t+|\t.*$", "", name).strip()
            if c["certificate_name"]:
                out.append(c)
        i += 1
    return out


def parse_langskill(lines):
    langs, skills = [], []
    it_mode = False
    buf = []
    for l in lines:
        if re.fullmatch(r"技能名称\s*熟练程度\s*使用时间", l.replace("\t", " ")) or l in ("技能名称", "熟练程度", "使用时间"):
            it_mode = True
            continue
        if re.match(r"^[（(]包括", l):
            continue
        if it_mode:
            buf.append(l)
            if len(buf) == 3:
                k = CN.empty("skills_list")
                k["skill_name"], k["skill_level"] = buf[0], buf[1]
                skills.append(k)
                buf = []
            continue
        m = re.match(r"^([一-鿿A-Za-z]{1,6}?)(?:等级)?\s*(?:[（(]([^)）]{1,6})[)）])?\s*[:：\t ]\s*(.+)$", l)
        if m and re.search(r"(语|English|Japanese)", m.group(1)):
            g = CN.empty("language_list")
            g["language_name"] = m.group(1)
            g["language_level"] = "；".join(x for x in (m.group(2), m.group(3).strip()) if x)
            langs.append(g)
        elif m:
            k = CN.empty("skills_list")
            k["skill_name"], k["skill_level"] = m.group(1), m.group(3).strip()[:20]
            skills.append(k)
    return langs, skills


def parse(text: str):
    lines = reflow(text)
    first = next((i for i, l in enumerate(lines) if l in SECTIONS and SECTIONS[l] not in ("skip",)), len(lines))
    head = lines[:first]
    secs, cur = [], None
    for l in lines[first:]:
        if l in SECTIONS:
            cur = [l, []]
            secs.append(cur)
        elif cur:
            cur[1].append(l)
    base = parse_header(head + [l for t, b in secs if SECTIONS[t] == "skip" for l in b])
    res = {"resume_languge": "zh", "base_info": base}
    for lst in C.LIST_FIELDS:
        res[lst] = []
    unmapped = []
    for title, body in secs:
        kind = SECTIONS[title]
        if kind == "expected":
            res["expected_list"] += parse_expected(body)
        elif kind == "pr":
            base["pr"] = "\n".join(x for x in body if not re.match(r"^关键词\s*[:：]", x)).strip()
        elif kind == "work":
            res["work_experiences"] += parse_work(body)
        elif kind == "edu":
            res["education_list"] += parse_edu(body)
        elif kind == "project":
            res["project_list"] += CN.parse_project(body)
        elif kind == "practice":
            res["project_list"] += CN.parse_project(body, practice=True)
        elif kind == "training":
            res["training_list"] += parse_training(body)
        elif kind == "cert":
            res["certificate_list"] += parse_cert(body)
        elif kind in ("lang", "langskill", "skill"):
            lg, sk = parse_langskill(body)
            res["language_list"] += lg
            res["skills_list"] += sk
            # 技能特长里夹带的“证书”“培训经历”子块已在回流时断成独立栏目
            # EN: "证书" (certificates) and "培训经历" (training) sub-blocks embedded in skills were already broken into separate sections during reflow
            # JA: スキル欄に含まれていた「证书」（資格）「培训经历」（研修歴）の小ブロックは、行の組み直しの際にすでに独立した欄に分けてある
        elif kind == "skip":
            continue
        else:
            unmapped.append(title)
    for i, p in enumerate(res["project_list"], 1):
        p["sequence_no"] = str(i)
        p["project_name"] = p["project_name"].lstrip("：: ").strip()
    for i, t in enumerate(res["training_list"], 1):
        t["sequence_no"] = str(i)
    mu = re.search(r"更新时间\s*[:：]?\s*((?:19|20)\d{2})[./\-](\d{1,2})[./\-](\d{1,2})", " ".join(head))
    updated = f"{mu.group(1)}-{int(mu.group(2)):02d}-{int(mu.group(3)):02d}" if mu else ""
    if not (res["work_experiences"] or res["education_list"]):
        return None
    return {"resume": res, "updated": updated, "unmapped": unmapped, "notes": []}


if __name__ == "__main__":
    import json
    import sys
    print(json.dumps(parse(Path(sys.argv[1]).read_text(encoding="utf-8")), ensure_ascii=False, indent=1))
