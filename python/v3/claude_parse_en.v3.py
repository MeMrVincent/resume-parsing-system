#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
claude_parse_en.v3.py —— 英文简历（CV / Resume）解析器。

从原文全文解析，输出 resume_languge="en" 的 resume（日期统一写成 YYYY年MM月01日，与其他语种一致）。
入口：detect(text) -> bool，parse(text) -> dict | None。

识别的写法（来自真实样本）：
  日期区间  2012.09-2014.06 / Sep.,2017~So far / Feb 2011 to present / 09/2015 - 03/2018 / 2016 - 2019
            “From October, 2007” 与下一行 “To October,2009” 成对
  区间位置  行首（后接公司/学校）、行尾（“Senior Consultant, XX Company, Shanghai   Feb 2011 to present”）、单独一行（下一行是公司/学校）
  标签      Name / Gender / Date of Birth / Nationality / Mobile / E-mail / Position / Title / Company / Department / Responsibilities …
  栏目      Education / Work Experience / Professional Experience / Career Path / Projects / Skills / Languages / Certificates / Summary …

EN: claude_parse_en.v3.py -- parser for English résumés (CV / Resume).

Parses from the full source text and outputs a resume with resume_languge="en" (dates uniformly written as YYYY年MM月01日, consistent with other languages).
Entry points: detect(text) -> bool, parse(text) -> dict | None.

Recognised writings (from real samples):
  date ranges  2012.09-2014.06 / Sep.,2017~So far / Feb 2011 to present / 09/2015 - 03/2018 / 2016 - 2019
            "From October, 2007" paired with "To October,2009" on the next line
  range position  start of line (followed by company/school), end of line ("Senior Consultant, XX Company, Shanghai   Feb 2011 to present"), on its own line (company/school on the next line)
  labels      Name / Gender / Date of Birth / Nationality / Mobile / E-mail / Position / Title / Company / Department / Responsibilities …
  sections      Education / Work Experience / Professional Experience / Career Path / Projects / Skills / Languages / Certificates / Summary …

JA: claude_parse_en.v3.py —— 英語の履歴書（CV / Resume）のパーサー。

原文の全文から解析し、resume_languge="en" の resume を出力する（日付は他の言語と同じく YYYY年MM月01日 に統一）。
エントリ：detect(text) -> bool、parse(text) -> dict | None。

識別する書き方（実際のサンプルから）：
  期間  2012.09-2014.06 / Sep.,2017~So far / Feb 2011 to present / 09/2015 - 03/2018 / 2016 - 2019
            「From October, 2007」と次の行の「To October,2009」の組
  期間の位置  行頭（後ろに会社・学校）、行末（「Senior Consultant, XX Company, Shanghai   Feb 2011 to present」）、単独の行（次の行が会社・学校）
  ラベル      Name / Gender / Date of Birth / Nationality / Mobile / E-mail / Position / Title / Company / Department / Responsibilities …
  欄      Education / Work Experience / Professional Experience / Career Path / Projects / Skills / Languages / Certificates / Summary …
"""

import importlib.util
import re
import unicodedata
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _load(name, file):
    spec = importlib.util.spec_from_file_location(name, HERE / file)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


CN = _load("claude_parse_cn_platform_v3_en", "claude_parse_cn_platform.v3.py")
J5 = _load("claude_parse_51job_v3_en", "claude_parse_51job.v3.py")
JP = _load("claude_parse_jp_v3_en", "claude_parse_jp.v3.py")
C = CN.C

CJK = re.compile(r"[一-鿿ぁ-ヺ]")
MON = {m: i + 1 for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}
MON_RE = r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?"
D1 = r"(?:" + MON_RE + r"\s*[,.]?\s*(?:19|20)\d{2}|(?:19|20)\d{2}\s*[./\-年]\s*\d{1,2}\s*月?|\d{1,2}\s*/\s*(?:19|20)\d{2}|(?:19|20)\d{2})"
PRESENT = r"(?:present|now|current(?:ly)?|so\s*far|till\s*now|to\s*date|today|至今|今)"
SEP = r"\s*(?:-{1,2}|–|—|~|～|to|till|until|至)\s*"
RANGE_RE = re.compile(r"(?<![\w/.])(" + D1 + r")" + SEP + r"(" + D1 + r"|" + PRESENT + r")(?![\w/])", re.I)
FROM_RE = re.compile(r"^\s*from\s*[:：]?\s*(" + D1 + r")\s*(.*)$", re.I)
TO_RE = re.compile(r"^\s*to\s*[:：]?\s*(" + D1 + r"|" + PRESENT + r")\s*(.*)$", re.I)

SECTIONS = [
    ("edu", r"education(?:al)?(?:\s+background|\s+history|\s+experience)?|academic\s+(?:background|qualifications?)|qualifications?"),
    ("work", r"(?:work(?:ing)?|professional|employment|career|job)\s*(?:experiences?|history|path|record|summary)?|experiences?|internships?|key\s+experience"),
    ("proj", r"projects?(?:\s+experiences?)?|project\s+history"),
    ("cert", r"certificat(?:es?|ions?)|licen[cs]es?|honou?rs?(?:\s*(?:&|and)\s*awards?)?|awards?(?:\s*(?:&|and)\s*honou?rs?)?|achievements"),
    ("lang", r"languages?(?:\s+skills?|\s+abilit(?:y|ies)|\s+proficiency)?"),
    ("skill", r"(?:computer\s+|it\s+|technical\s+|professional\s+|key\s+)?skills?(?:\s*(?:&|and)\s*(?:abilities|qualifications|competencies))?|competencies|strengths?|key\s+strengths"),
    ("pr", r"(?:professional\s+|personal\s+|career\s+)?(?:summary|profile|objective|about\s+me|self[-\s]?(?:evaluation|assessment|introduction)|introduction|comments?|overview|highlights)"),
    ("train", r"trainings?|courses?|professional\s+development"),
    ("base", r"personal\s+(?:information|details|data|profile)|basic\s+information|contact(?:\s+information)?"),
    ("other", r"hobbies|interests|references?|activities|extracurricular(?:\s+activities)?|others?|additional\s+information|volunteer(?:\s+experience)?"),
]
SECTION_RE = re.compile(r"^\s*[■◆●▪►•\-\*]?\s*(" + "|".join(p for _, p in SECTIONS) + r")\s*[:：]?\s*$", re.I)
STRONG_ORG = re.compile(r"(co\.?,?\s*ltd|company|corporation|corp\.?\b|inc\.?\b|limited|ltd\.?\b|group|gmbh|llc|plc|bank|会社|公司|株式|集团)", re.I)
ORG_RE = re.compile(r"(co\.?,?\s*ltd|company|corporation|corp\.?|inc\.?\b|limited|ltd\.?\b|group|gmbh|llc|plc|bank|technolog(?:y|ies)|trading|"
                    r"industr|electronics?|manufactur|holdings?|partners|services?|solutions?|systems?|会社|公司|株式|集团|agency|firm|studio|hotel|hospital)", re.I)
SCHOOL_RE = re.compile(r"(universit|college|institute|school|academy|polytechnic|大学|学院|学校)", re.I)
DEGREE = [("ph.?d|doctor", "博士", "6"), ("mba|master|m\\.?s\\.?c?\\b|m\\.?a\\.?\\b|m\\.?eng|postgraduate", "硕士", "5"),
          ("bachelor|b\\.?s\\.?c?\\b|b\\.?a\\.?\\b|b\\.?eng|undergraduate", "本科", "4"),
          ("associate|diploma|junior\\s+college|vocational", "大专", "3"), ("high\\s+school", "高中", "2")]
POS_RE = re.compile(r"(manager|engineer|director|assistant|specialist|consultant|analyst|officer|supervisor|coordinator|representative|executive|"
                    r"intern|accountant|designer|developer|lead(?:er)?|head|president|vp\b|translator|interpreter|teacher|sales|admin|clerk|"
                    r"administrator|secretary|advisor|architect|programmer|tester|buyer|planner|associate|staff|member|chief|ceo|cfo|cto|coo)", re.I)
LABELS = {
    "company": r"company(?:\s+name)?|employer|organi[sz]ation|firm",
    "position": r"position|title|job\s+title|role|designation|post|project\s+(?:position|role)",
    "dept": r"department|dept\.?|division",
    "resp": r"responsibilit(?:y|ies)(?:\s*(?:&|and)\s*duties)?|duties|job\s+description|description|work\s+content|main\s+(?:tasks|duties)|role\s+and\s+responsibilities|tasks",
    "ach": r"achievements?|results?|accomplishments?|key\s+achievements?",
    "reason": r"reason(?:s)?\s+for\s+(?:leaving|resignation|change)|leaving\s+reason",
    "ind": r"industry|business|nature|type\s+of\s+company|company\s+type",
    "report": r"report(?:s|ing)?\s+to",
    "loc": r"location|city|place",
    "school": r"school|university|college|institution",
    "major": r"major|specialty|speciali[sz]ation|field(?:\s+of\s+study)?|course",
    "degree": r"degree|diploma",
}
LABEL_LINE = re.compile(r"^\s*(" + "|".join(LABELS.values()) + r")\s*(?:[:：]|\t)\s*(.*)$", re.I)
LABEL_CELL = re.compile(r"^(" + "|".join(LABELS.values()) + r"|gender|sex|nationality|mobile|e-?mail|age|name)$", re.I)


def label_kind(lab):
    for k, p in LABELS.items():
        if re.fullmatch(p, lab.strip(), re.I):
            return k
    return ""


def ym(s: str):
    s = s.strip().lower()
    m = re.match(r"(" + MON_RE + r")\s*[,.]?\s*((?:19|20)\d{2})", s, re.I)
    if m:
        return f"{int(m.group(2)):04d}年{MON[m.group(1)[:3]]:02d}月01日"
    m = re.match(r"((?:19|20)\d{2})\s*[./\-年]\s*(\d{1,2})", s)
    if m and 1 <= int(m.group(2)) <= 12:
        return f"{int(m.group(1)):04d}年{int(m.group(2)):02d}月01日"
    m = re.match(r"(\d{1,2})\s*/\s*((?:19|20)\d{2})", s)
    if m and 1 <= int(m.group(1)) <= 12:
        return f"{int(m.group(2)):04d}年{int(m.group(1)):02d}月01日"
    m = re.match(r"((?:19|20)\d{2})$", s)
    if m:
        return f"{int(m.group(1)):04d}年01月01日"
    return ""


def end_ym(s: str):
    return "至今" if re.fullmatch(PRESENT, s.strip(), re.I) else ym(s)


def detect(text: str) -> bool:
    if CN.detect(text) or J5.detect(text) or JP.detect(text):
        return False
    lat = len(re.findall(r"[A-Za-z]", text))
    cjk = len(CJK.findall(text))
    return lat >= 400 and lat / max(lat + cjk * 2, 1) >= 0.8


FLAT_HEADS = (r"Self Assessment|Self-Assessment|Career Objective|Job Objective|Work Experience|Working Experience|Project Experience|Education(?: Background)?|"
              r"Training(?: Experience)?|Certificates?|Languages?(?: Skills| Ability)?|Professional Skills|IT Skills|Skills|Awards|Honors|In-school Practices?|"
              r"Scholarships?|Other Information|Additional Information")


def split_labels(l: str):
    """xls 行“公司\tNature\tSolely\tDepartment\tIP\tTitle\tPatent Engineer”→ 公司 + 每个标签一行；纯表头行（全是栏目名）丢弃。

    EN: xls row "company	Nature	Solely	Department	IP	Title	Patent Engineer" → company + one line per label; pure header rows (all section names) are discarded.

    JA: xls の行「会社	Nature	Solely	Department	IP	Title	Patent Engineer」→ 会社 + ラベルごとに 1 行。見出しだけの行（すべて欄の名前）は捨てる。
    """
    cells = [c.strip() for c in l.split("\t") if c.strip()]
    labs = [k for k, c in enumerate(cells) if LABEL_CELL.match(c) or re.fullmatch(r"period|from|to", c, re.I)]
    if cells and len(labs) == len(cells) and len(cells) >= 2:
        return []
    labs = [k for k in labs if LABEL_CELL.match(cells[k])]
    if not (len(labs) >= 2 or (labs and labs[0] > 0)):
        return [l]
    out = []
    head = cells[:labs[0]]
    if head:
        out.append("\t".join(head))
    for n, k in enumerate(labs):
        nxt = labs[n + 1] if n + 1 < len(labs) else len(cells)
        out.append(cells[k] + ": " + " ".join(cells[k + 1:nxt]))
    return out


def lines_of(text: str):
    t = unicodedata.normalize("NFKC", text)
    t = re.sub(r"[\ue000-\uf8ff]", " ", t)  # Word 符号字体的项目符号
    # EN: Bullets in the Word Symbol font
    # JA: Word の Symbol フォントの箇条書き記号
    t = re.sub(r"(?m)^### sheet .*$", "", t)
    # 智联/51job 英文版导出成一整行：在日期区间、栏目名、“标签:\t”前断行
    # EN: Zhaopin/51job English exports come out as one whole line: break before date ranges, section names and "label:\t"
    # JA: Zhaopin／51job の英語版のエクスポートは 1 行全体になっている：期間・欄の名前・「ラベル:\t」の前で改行する
    fixed = []
    for l in t.split("\n"):
        if len(l) > 300:
            l = RANGE_RE.sub(lambda m: "\n" + m.group(0), l)
            l = re.sub(r"\s(" + FLAT_HEADS + r")\s", lambda m: "\n" + m.group(1) + "\n", l)
            l = re.sub(r"[ \t]+([A-Z][A-Za-z.]*(?: [A-Za-z.()]+){0,3} ?:)\t", lambda m: "\n" + m.group(1) + "\t", l)
        fixed.append(l)
    t = "\n".join(fixed)
    out = []
    raw = [re.sub(r"[ \u00a0]{2,}", "\t", l.strip()) for l in t.split("\n")]
    raw = [re.sub(r"^[•●▪►◆■\-\*➢✓·]\s*", "", l).strip() for l in raw]
    raw = [l for l in raw if l and len(re.findall(r"[\x00-\x08\x0b-\x1f\x7f-\x9f\u0100-\u024f]", l)) < max(3, len(l) // 10)]
    i = 0
    while i < len(raw):
        l = raw[i]
        mf = FROM_RE.match(l)
        if mf and i + 1 < len(raw) and TO_RE.match(raw[i + 1]):
            mt = TO_RE.match(raw[i + 1])
            rest = "\t".join(x for x in (mf.group(2), mt.group(2)) if x.strip())
            out += split_labels(f"{mf.group(1)} - {mt.group(1)}\t{rest}".strip())
            i += 2
            continue
        out += split_labels(l)
        i += 1
    return out


def split_range(l: str):
    """返回 (start, end, rest, pos)；pos=start/end/alone。没有区间返回 None。

    EN: Returns (start, end, rest, pos); pos=start/end/alone. Returns None if there is no range.

    JA: 戻り値：(start, end, rest, pos)。pos=start/end/alone。期間がなければ None を返す。
    """
    m = RANGE_RE.search(l)
    if not m:
        return None
    st, en = ym(m.group(1)), end_ym(m.group(2))
    if not st:
        return None
    before, after = l[:m.start()].strip(" \t,|:-–—()（）"), l[m.end():].strip(" \t,|:-–—()（）")
    if not before and not after:
        return st, en, "", "alone"
    if not before:
        return st, en, after, "start"
    if not after or len(after) <= 3:
        return st, en, before, "end"
    return st, en, before + "\t" + after, "mid"


def degree_of(s: str):
    for p, d, r in DEGREE:
        if re.search(r"\b(?:" + p + r")", s, re.I):
            return d, r
    return "", ""


PLACEHOLDER_RE = re.compile(r"(?i)(company(?:\s+name)?|university|college|school|position|title|period|date|time|name|major|degree|"
                            r"employer|organi[sz]ation|department|duration|from|to|location|city)")
LAB_PREFIX_RE = re.compile(r"(?i)^(?:position|title|job\s+title|company(?:\s+name)?|type\s+of\s+company|project\s+(?:position|role)|"
                           r"related\s+company|role|department|school|university|major|degree)\s*[:：]\s*")
SENT_START_RE = re.compile(r"^(?:responsible|assist(?:ed)?|promoted|put|independently|he|she|i|we|worked\s+on|participat(?:ed|e)|led|managed|"
                           r"developed|designed|helped|handled|conducted|organi[sz]ed|translated?|prepared|provided|supported|made|did|was)\b", re.I)


def is_sentence(t: str) -> bool:
    """像描述句子而不是公司/学校名：太长、小写或括号开头、以动词开头。

    EN: Looks like a descriptive sentence rather than a company/school name: too long, starts with lowercase or a bracket, or starts with a verb.

    JA: 会社名・学校名ではなく説明文のように見える：長すぎる、小文字か括弧で始まる、動詞で始まる。
    """
    t = t.strip()
    if not t:
        return False
    if SENT_START_RE.match(t) or re.match(r"^[a-z(（]", t):
        return True
    if "\t" in t:
        return False  # 表格式“公司\t职位\t地点”
        # EN: Tabular "company\tposition\tplace"
        # JA: 表形式の「会社\t職位\t場所」
    words = len(re.findall(r"\b(?:the|and|was|were|for|with|to|in|of|a|an|my|our)\b", t, re.I))
    return (len(t) > 90 and words >= 3) or (len(t.split()) >= 12 and words >= 3 and not STRONG_ORG.search(t))


def clean_tok(x: str) -> str:
    x = LAB_PREFIX_RE.sub("", x.strip())
    return x


def toks_of(s):
    raw = _toks_of(s)
    out = []
    for x in raw:
        x = clean_tok(x)
        if not x or PLACEHOLDER_RE.fullmatch(x.strip(" :：")) or not re.search(r"[A-Za-z一-鿿ぁ-ヺ]", x) or SECTION_RE.match(x):
            continue
        out.append(x)
    return out


def _toks_of(s):
    return [x.strip(" ,;|") for x in re.split(r"\t+|\s*[|｜]\s*|\s{2,}|,\s+(?=[A-Z])(?!(?:LTD|Ltd|Inc|INC|Limited|LIMITED|Co\b|CO\b|LLC|L\.L\.C))", s) if x.strip(" ,;|")]


def make_work(st, en, head):
    w = CN.empty("work_experiences")
    w["position_start"], w["position_resigned"] = st, en
    w["status"] = "在职" if en == "至今" else ("离职" if en else "")
    w["employment_type"] = "全职"
    toks = toks_of(head)
    comp = next((t for t in toks if STRONG_ORG.search(t)), "") or next((t for t in toks if ORG_RE.search(t) and not POS_RE.search(t)), "") \
        or next((t for t in toks if ORG_RE.search(t)), "")
    pos = next((t for t in toks if t != comp and POS_RE.search(t) and len(t) <= 60), "")
    if not comp and toks:
        comp = next((t for t in toks if t != pos), "")
    if not pos:
        pos = next((t for t in toks if t not in (comp,) and len(t) <= 60 and not re.fullmatch(r"[A-Z][a-z]+(?:,\s*[A-Z][a-z]+)?", t)), "")
    comp = re.sub(r"\s*\((?:more than |less than |about )?[\d,\-~ ]+\s*(?:people|employees|staff)\)", "", comp, flags=re.I).strip()
    msp = re.match(r"^(.*?(?:co\.?,?\s*ltd\.?|limited|inc\.?|corporation|corp\.?|company|group|gmbh|llc))[\s.,]+([A-Za-z].{2,50})$", comp, re.I)
    if msp and POS_RE.search(msp.group(2)) and not ORG_RE.search(msp.group(2)):
        comp, pos = msp.group(1), pos or msp.group(2)
    IW = r"^(?:work(?:ed|ing)?|intern(?:ship)?|intership|internship\s+program)\s+(?:in|at|for)\s+(.+)$"
    if not comp and re.match(IW, pos, re.I):
        comp, pos = pos, ""
    mw = re.match(IW, comp, re.I)
    if mw:
        if re.match(r"^inter", comp, re.I) and not pos:
            pos = "Intern"
        comp = mw.group(1)
    mp = re.match(r"^work(?:ed|ing)?\s+as\s+(?:an?\s+)?(.+)$", pos, re.I)
    if mp:
        pos = mp.group(1)
    mb = re.fullmatch(r"\[([^\]]{2,60})\]", comp.strip())
    if mb and POS_RE.search(mb.group(1)):  # “[Equipment service manager]”
        comp, pos = "", pos or mb.group(1)
    desc = []
    if is_sentence(comp):
        desc.append(comp)
        comp = ""
    if is_sentence(pos):
        desc.append(pos)
        pos = ""
    if re.search(r"\b(department|dept\.?|division)\b", pos, re.I) and not re.search(r"(manager|director|head|chief|supervisor)", pos, re.I):
        w["position_dept"], pos = pos.strip(), ""  # “公司 | FINANCE DEPARTMENT”，职位在下一行
        # EN: "company | FINANCE DEPARTMENT", with the position on the next line
        # JA: 「会社 | FINANCE DEPARTMENT」で、職位は次の行
    w["company_name"], w["position"] = comp.strip(" ‘’“”'\""), pos.strip(" ‘’“”'\"")
    w["position_responsibilities"] = "\n".join(desc)
    return w


def make_edu(st, en, head):
    e = CN.empty("education_list")
    e["school_start_ym"], e["school_end_ym"] = st, en
    toks = toks_of(head)
    toks = [re.sub(r"^(?:school|university|major|specialty|degree)\s*[:：]\s*", "", t, flags=re.I) for t in toks]
    school = next((t for t in toks if SCHOOL_RE.search(t)), "")
    mpar = re.search(r"\(([^()]*(?:universit|college|institute|school)[^()]*)\)", school, re.I)
    if mpar:
        rest_t = school[:mpar.start()].strip()
        school = mpar.group(1).strip()
        toks = toks + [rest_t]
    msd = re.match(r"^((?:bachelor|master|doctor|ph\.?d|mba|diploma|associate)[^;,]*?)[;,]\s*(.+)$", school, re.I)
    if msd and SCHOOL_RE.search(msd.group(2)):
        toks, school = toks + [msd.group(1)], msd.group(2).strip()
    if school and (len(school) > 60 or is_sentence(school) or re.search(r"\d|[:;：；]", school)):
        # “April1st2012~March31th ,2015: Kyoto University; Marketing” → 取出校名短语
        # EN: "April1st2012~March31th ,2015: Kyoto University; Marketing" → take out the school-name phrase
        # JA: 「April1st2012~March31th ,2015: Kyoto University; Marketing」→ 学校名の語句を取り出す
        mph = re.search(r"((?:[A-Z][A-Za-z.'&\-]*\s+){0,5}(?:University|College|Institute|School|Academy|Polytechnic)(?:\s+(?:of|for|and|&)\s+(?:[A-Z][A-Za-z.'\-]*\s*){1,5})?)", school)
        if mph and len(mph.group(1).strip()) >= 8:
            rest_t = (school[:mph.start()] + " " + school[mph.end():]).strip(" ;,:")
            school = mph.group(1).strip()
            if rest_t and not is_sentence(rest_t):
                toks = toks + [rest_t]
    if not school:
        school = next((t for t in toks if not degree_of(t)[0] and not re.search(r"@|\d{5,}", t)), "")
    d, r = "", ""
    major = []
    for t in toks:
        if t == school:
            continue
        dd, rr = degree_of(t)
        if dd and not d:
            d, r = dd, rr
            m = re.search(r"\bmajor(?:ing)?\s+in\s+(.+)$", t, re.I) or re.search(r"\b(?:in|of)\s+(.+)$", t)
            if m and not re.search(r"(degree|diploma)$", m.group(1), re.I):
                major.append(m.group(1))
            continue
        if re.fullmatch(r"[A-Z][a-z]+(?:,\s*[A-Z][a-z]+)?", t) and not re.search(r"(engineering|science|management|design)", t, re.I) and major:
            continue  # 城市
            # EN: City
            # JA: 都市
        major.append(t)
    if not d:
        d, r = degree_of(school)
    e["school_name"] = school
    e["school_major_name"] = " ".join(major)[:80]
    e["school_degree_type"], e["school_degree_rank"] = d, r
    return e


def base_info(lines, text):
    b = {k: "" for k in C.BASE_FIELDS}
    b["platform_from"] = "个人简历"
    j = "\n".join(lines)
    name = ""
    m = re.search(r"(?im)(?:^|\s)(?:\d+\.\s*)?(?:full\s+|chinese\s+)?name\s*[:：]?\s*\t?\s*[:：]?\s*([一-鿿]{2,4}(?=[\s(（]|$)|[A-Za-z][A-Za-z .,'()\-]{1,40}?)\s*(?:\t|$|\s{2,}|gender|sex|date|geschlecht|age\b|[一-鿿])", j)
    if m:
        name = re.sub(r"\s*\([^)]*\)\s*", " ", m.group(1)).strip(" ,")
        name = re.sub(r"\s{2,}", " ", name)
        # “Name： Jiang  Xinnan”：名和姓之间是两个空格
        # EN: "Name： <given name>  <surname>": two spaces between given name and surname
        # JA: 「Name： <名>  <姓>」：名と姓の間に空白が 2 つ
        mx = re.match(r"(?:[ \u3000]{2,3}|\t)([A-Z][a-z]+)(?![A-Za-z])", j[m.end(1):])
        if re.fullmatch(r"[A-Za-z]+", name) and mx and not re.match(r"(?i)(gender|sex|date|age|male|female|birth|tel|mobile|email)", mx.group(1)):
            name = name + " " + mx.group(1)
        if C.name_quality(name)[0] != "valid":
            name = ""
    if not name:
        mr = re.search(r"(?im)^\s*(?:resume|cv)\t+([A-Za-z][A-Za-z'\- ]{2,30}?)\s*$", j)
        if mr and C.name_quality(mr.group(1).strip())[0] == "valid":
            name = mr.group(1).strip()
    if not name:
        for l in lines[:6]:
            t = l.lstrip("\ufeff").strip()
            if re.fullmatch(r"(?i)(resume|curriculum\s*vitae|cv|lebenslauf|personal\s+(information|details|profile)|basi\s*c\s+information|profile)", t) or SECTION_RE.match(t):
                continue
            mc = re.search(r"[(（]([一-鿿]{2,4})[)）]", t) or re.match(r"^([一-鿿]{2,4})\s*[(（][A-Za-z][A-Za-z .\-]{1,30}[)）]\s*$", t)
            if mc:
                name = mc.group(1)
                break
            t = re.sub(r"(?<=[A-Za-z])\s*[(（][A-Za-z]{2,15}[)）]\s*", " ", t).strip()  # “Na(Lina) Li”：去掉括号里的英文昵称
            # EN: "Na(Lina) Li": remove the English nickname in brackets
            # JA: 「Na(Lina) Li」：括弧内の英語のニックネームを除く
            head = re.split(r"\t|\s{2,}|\s*[(（·|]\s*|,\s*(?:MPH|MBA|PhD|CPA|MSc|MA|BA)\b|\s+(?:male|female)\b", t, flags=re.I)[0].strip(" ,")
            head = re.sub(r"\s*,\s*", " ", head) if re.fullmatch(r"[A-Za-z]+\s*,\s*[A-Za-z]+", head) else head
            if re.fullmatch(r"[A-Za-z][A-Za-z'\-]+(?:\s+[A-Za-z][A-Za-z'\-]+){0,3}", head) and not re.search(
                    r"(resume|curriculum|vitae|mobile|phone|email|address|shanghai|china|beijing|objective|summary|birth|status|nationality|residen|"
                    r"gender|name|date|position|education|experience|information|details)", head, re.I):
                name = " ".join(head.split())
                break
            if re.fullmatch(r"[一-鿿]{2,4}", t):
                name = t
                break
            break
    q = C.name_quality(name)[0] if name else "invalid"
    b["full_name"] = name if q == "valid" else ""
    mg = re.search(r"(?im)\b(?:gender|sex)\s*[:：]?\s*\t?\s*(male|female|男|女)", j)
    if mg:
        b["gender"] = {"male": "男", "female": "女"}.get(mg.group(1).lower(), mg.group(1))
    mb = re.search(r"(?im)\b(?:date\s+of\s+birth|birth\s*date|d\.?o\.?b\.?|born(?:\s+on)?|birthday)\s*[:：]?\s*\t?\s*([^\t\n]{4,30})", j)
    if mb:
        v = mb.group(1)
        md = re.search(r"((?:19|20)\d{2})\s*[./\-]\s*(\d{1,2})(?:\s*[./\-]\s*(\d{1,2}))?", v) or None
        mdmy = re.search(r"(\d{1,2})\s*/\s*(\d{1,2})\s*/\s*((?:19|20)\d{2})", v)
        mm_ = re.search(r"(" + MON_RE + r")\s*\.?\s*(\d{1,2})?(?:st|nd|rd|th)?\s*,?\s*((?:19|20)\d{2})", v, re.I)
        mdm = re.search(r"(\d{1,2})(?:st|nd|rd|th)?\s+(" + MON_RE + r")\s*,?\s*((?:19|20)\d{2})", v, re.I)
        y = mo = d = None
        if md:
            y, mo, d = md.group(1), md.group(2), md.group(3) or "1"
        elif mdmy:
            y, mo, d = mdmy.group(3), mdmy.group(2), mdmy.group(1)
        elif mm_:
            y, mo, d = mm_.group(3), MON[mm_.group(1)[:3].lower()], mm_.group(2) or "1"
        elif mdm:
            y, mo, d = mdm.group(3), MON[mdm.group(2)[:3].lower()], mdm.group(1)
        if y and 1 <= int(mo) <= 12 and 1 <= int(d) <= 31 and 1940 <= int(y) <= 2010:
            b["birth_date"], b["birth_year"] = f"{int(y):04d}年{int(mo):02d}月{int(d):02d}日", str(int(y))
    mn = re.search(r"(?im)\bnationality\s*[:：]?\s*\t?\s*([A-Za-z]{3,20})", j)
    b["nationality"] = mn.group(1) if mn else ""
    mm = re.search(r"(?im)\bmarital\s+status\s*[:：]?\s*\t?\s*(single|married|unmarried|divorced)", j)
    if mm:
        b["marital_status"] = {"single": "未婚", "unmarried": "未婚", "married": "已婚", "divorced": "离异"}[mm.group(1).lower()]
    ma = re.search(r"(?im)\b(?:address|residence|current\s+address|location|living\s+in)\s*[:：]?\s*\t?\s*([^\t\n]{3,80})", j)
    if ma and not re.search(r"(@|\d{7,}|;$)", ma.group(1).strip()):
        b["address"] = ma.group(1).strip()
    ms, es = [], []
    for l in lines:
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
    b["phone"], b["email"] = "; ".join(ms), "; ".join(es)
    return b


def sec_of(l):
    l = re.sub(r"^[一-鿿ぁ-ヺ]+\s*", "", l) if re.match(r"^[一-鿿]{2,8}\s*[A-Za-z]", l) else l
    m = SECTION_RE.match(l)
    if not m:
        t = l.strip(" :：■◆●")
        if len(t) <= 50 and not re.search(r"\d|[:：@]", t) and (t.isupper() or len(t.split()) <= 4):
            for k, kw in (("work", r"\b(work|employment|professional\s+experience|career|experience)\b"), ("edu", r"\b(education|learning\s+experience|academic\s+background|study\s+experience|qualifications?)"),
                          ("proj", r"\bprojects?\b"), ("cert", r"\b(certificat|award|honou?r)"), ("skill", r"\bskills?\b"),
                          ("lang", r"\blanguages?\b"), ("pr", r"\b(summary|profile|objective|about me)\b")):
                if re.search(kw, t, re.I) and (t.isupper() or t.istitle() or re.match(kw, t, re.I)):
                    return k
        return None
    h = m.group(1)
    for k, p in SECTIONS:
        if re.fullmatch(p, h, re.I):
            return k
    return "other"


def parse(text: str):
    lines = lines_of(text)
    if not lines:
        return None
    base = base_info(lines, text)
    res = {"resume_languge": "en", "base_info": base}
    for lst in C.LIST_FIELDS:
        res[lst] = []
    section = ""
    cur, cur_kind, body = None, "", []
    pending = None  # 单独一行的区间，等下一行
    # EN: A range on its own line; wait for the next line
    # JA: 単独の行にある期間。次の行を待つ
    pr, certs, langs, skills = [], [], [], []

    def flush():
        nonlocal cur, body
        if cur is None:
            body = []
            return
        lab, pre = {}, []
        k = None
        for l in body:
            ml = LABEL_LINE.match(l)
            if ml:
                k = label_kind(ml.group(1))
                lab.setdefault(k, [])
                if ml.group(2).strip():
                    lab[k].append(ml.group(2).strip())
            elif k:
                lab[k].append(l)
            else:
                pre.append(l)
        g = lambda x: "\n".join(lab.get(x, [])).strip()  # noqa: E731
        g1 = lambda x: (lab.get(x) or [""])[0].strip()  # noqa: E731
        if cur_kind == "work":
            if g1("company"):
                cur["company_name"] = g1("company")
            if g1("position"):
                cur["position"] = g1("position")
            cur["position_dept"] = g1("dept") or cur["position_dept"]
            cur["position_report_to"] = g1("report")
            parts_i = [x.strip() for x in g1("ind").split("\t") if x.strip()]
            cur["company_industry"] = parts_i[0] if parts_i else ""
            if len(parts_i) >= 2:
                pi = next((k for k in range(1, len(parts_i)) if POS_RE.search(parts_i[k]) and len(parts_i[k]) <= 50), None)
                if pi is not None and not cur["position"]:
                    cur["position"] = parts_i[pi]
                    if pi >= 2 and not cur["position_dept"]:
                        cur["position_dept"] = parts_i[1]
                    extra_desc = [x for x in parts_i[pi + 1:] if len(x) > 20]
                    if extra_desc:
                        lab.setdefault("resp", [])
                        lab["resp"] = extra_desc + lab["resp"]
            # 条目头后面紧跟的一两行短文本：公司/职位
            # EN: One or two short lines right after the entry header: company/position
            # JA: 項目の見出しの直後に続く 1〜2 行の短いテキスト：会社・職位
            while pre and len(pre[0]) <= 80 and not re.search(r"[.;。]$", pre[0]) and (not cur["company_name"] or not cur["position"]):
                t = pre[0]
                if not toks_of(t):
                    pre = pre[1:]
                    continue
                if not cur["company_name"] and ORG_RE.search(t):
                    cur["company_name"] = toks_of(t)[0]
                elif not cur["position"] and (POS_RE.search(t) or len(t) <= 40):
                    cur["position"] = toks_of(t)[0].strip(" ‘’“”'\"")
                else:
                    break
                pre = pre[1:]
            cur["position_responsibilities"] = "\n".join(x for x in (cur["position_responsibilities"], g("resp"), "\n".join(pre)) if x).strip()
            cur["position_achievements"] = g("ach")
            cur["resigned_reason"] = g("reason")
            bad = SECTION_RE.match(cur["company_name"]) or re.fullmatch(r"[^:：]{1,30}[:：]", cur["company_name"]) or \
                re.search(r"(scholarship|prize|award|secretary of student|student union)", cur["company_name"], re.I)
            if not cur["company_name"] and not cur["position"] and cur["position_responsibilities"] and res["work_experiences"]:
                # 只有一段描述（日期开头的句子）：并入上一段经历
                # EN: Only a description (a sentence starting with a date): merge into the previous experience
                # JA: 説明（日付で始まる文）だけの場合：直前の経歴に統合する
                prev = res["work_experiences"][-1]
                prev["position_responsibilities"] = (prev["position_responsibilities"] + "\n" + cur["position_responsibilities"]).strip()
            if (cur["company_name"] or cur["position"]) and not bad:
                if not cur["company_name"]:
                    cur["company_name"] = cur["position"]
                    cur["position"] = ""
                res["work_experiences"].append(cur)
        elif cur_kind == "edu":
            if g1("school"):
                cur["school_name"] = g1("school")
            if g1("major"):
                cur["school_major_name"] = g1("major")
            if g1("degree") and not cur["school_degree_type"]:
                cur["school_degree_type"], cur["school_degree_rank"] = degree_of(g1("degree"))[0] or g1("degree"), degree_of(g1("degree"))[1]
            while pre and len(pre[0]) <= 80 and not re.search(r"[.;。]$", pre[0]):
                t = pre[0]
                d, r = degree_of(t)
                if d and not cur["school_degree_type"]:
                    cur["school_degree_type"], cur["school_degree_rank"] = d, r
                    m = re.search(r"\bmajor(?:ing)?\s+in\s+(.+)$", t, re.I) or re.search(r"\b(?:in|of)\s+(.+)$", t)
                    if m and not cur["school_major_name"]:
                        cur["school_major_name"] = m.group(1)
                elif SCHOOL_RE.search(t) and not SCHOOL_RE.search(cur["school_name"]):
                    cur["school_name"] = t
                elif not cur["school_major_name"] and len(t) <= 60 and not re.search(r"(honou?rs?|awards?|gpa|scholarship)", t, re.I):
                    cur["school_major_name"] = t
                else:
                    break
                pre = pre[1:]
            if SECTION_RE.match(cur["school_major_name"] or "x") or PLACEHOLDER_RE.fullmatch(cur["school_major_name"].strip(" :：")):
                cur["school_major_name"] = ""
            if cur["school_name"] and not SCHOOL_RE.search(cur["school_name"]) and (is_sentence(cur["school_name"]) or len(cur["school_name"]) > 45
                                                                                  or not (cur["school_degree_type"] or cur["school_major_name"])):
                # 教育栏里的活动、交换项目、实习（“Social Survey on …”“Two week internship …”）：记为项目经历，不当学校
                # EN: Activities, exchange programmes and internships in the education section ("Social Survey on …", "Two week internship …"): recorded as project experience, not as a school
                # JA: 学歴欄にある活動・交換プログラム・インターン（「Social Survey on …」「Two week internship …」）：プロジェクト経験として記録し、学校にはしない
                p = CN.empty("project_list")
                p["start_ym"], p["end_ym"] = cur["school_start_ym"], cur["school_end_ym"]
                p["project_name"] = cur["school_name"][:120]
                p["description"] = "\n".join(x for x in ([cur["school_name"][120:]] if len(cur["school_name"]) > 120 else []) + pre + [g("resp")] if x).strip()
                res["project_list"].append(p)
            elif cur["school_name"]:
                res["education_list"].append(cur)
        elif cur_kind == "proj":
            cur["description"] = (g("resp") or "\n".join(pre)).strip()
            cur["role_name"] = cur["role_name"] or g1("position")
            if cur["project_name"]:
                res["project_list"].append(cur)
        cur, body = None, []

    def start_item(st, en, head):
        nonlocal cur, cur_kind
        flush()
        kind = section if section in ("edu", "work", "proj") else ("edu" if SCHOOL_RE.search(head) and not ORG_RE.search(head) else "work")
        if kind == "work" and SCHOOL_RE.search(head) and not STRONG_ORG.search(head) and not POS_RE.search(head):
            kind = "edu"  # 工作栏里的学校行（教育栏标题没认出来）
            # EN: School lines in the work section (the education section heading was not recognised)
            # JA: 職歴欄にある学校の行（学歴欄の見出しが認識されなかったもの）
        if kind == "edu":
            cur, cur_kind = make_edu(st, en, head), "edu"
        elif kind == "proj":
            p = CN.empty("project_list")
            p["start_ym"], p["end_ym"] = st, en
            tk = toks_of(head)
            p["project_name"] = tk[0] if tk else ""
            p["role_name"] = tk[1] if len(tk) > 1 and len(tk[1]) <= 40 else ""
            cur, cur_kind = p, "proj"
        else:
            cur, cur_kind = make_work(st, en, head), "work"

    for l in lines:
        s = sec_of(l)
        if s is not None:
            flush()
            if pending:
                pending = None
            section = s
            continue
        r = split_range(l) if section not in ("pr", "skill", "lang") and not LABEL_LINE.match(l) else None
        if r and section == "cert":
            c = CN.empty("certificate_list")
            c["certificate_time"], c["certificate_name"] = r[0], r[2]
            if r[2]:
                certs.append(c)
            continue
        rc = re.sub(r"\s+", " ", r[2]) if r else ""
        if r and cur is not None and is_sentence(r[2].split("\t")[0]) and section != "edu":
            body.append(l)  # 描述里以日期开头的句子
            # EN: Sentences in descriptions that start with a date
            # JA: 説明の中の日付で始まる文
            continue
        if r and cur is not None and not (SCHOOL_RE.search(rc) or STRONG_ORG.search(rc)) and (
                len(rc) > 90 or re.search(r"\b(the|and|was|were|for|with|to)\b.*\b(the|and|a|of)\b", rc) and r[3] != "start"):
            body.append(l)  # 描述句子里的日期
            # EN: Dates inside description sentences
            # JA: 説明の文の中の日付
            continue
        if r:
            st, en, rest, pos = r
            if pos == "alone":
                flush()
                pending = (st, en)
                continue
            if pos == "end" and cur is not None and cur_kind == "work" and section == "work" and not body and not ORG_RE.search(rest):
                # “职位行 + 行尾日期”跟在公司行后面：同一公司的另一段
                # EN: "position line + trailing date" following a company line: another period at the same company
                # JA: 会社の行の後に続く「職位の行 + 行末の日付」：同じ会社での別の期間
                pass
            start_item(st, en, rest)
            continue
        if pending:
            start_item(pending[0], pending[1], l)
            pending = None
            continue
        if section == "edu" and SCHOOL_RE.search(l) and len(l) <= 150 and not re.search(r"(honou?r|award|outstanding|scholarship|prize|“|\"|gpa)", l, re.I) and (cur is None or body or SCHOOL_RE.search(cur.get("school_name", "")) or cur_kind != "edu"):
            # 没有起止年月的学历行：“Bachelor of Commerce   Zhejiang Gongshang University, 2006”
            # EN: Education lines without start/end year-months: "Bachelor of Commerce   Zhejiang Gongshang University, 2006"
            # JA: 開始・終了の年月がない学歴の行：「Bachelor of Commerce   Zhejiang Gongshang University, 2006」
            my = re.search(r"((?:19|20)\d{2})(?!.*(?:19|20)\d{2})", l)
            start_item("", ym(my.group(1)) if my else "", re.sub(r",?\s*(?:19|20)\d{2}\s*$", "", l))
            continue
        if section == "pr":
            pr.append(l)
        elif section == "cert":
            if len(l) <= 120 and len(re.findall(r"[A-Za-z一-鿿]", l)) >= 3 and not re.fullmatch(r"[^:：]{1,30}[:：]", l.strip()) \
                    and not LABEL_CELL.match(l.strip(" :：")):
                c = CN.empty("certificate_list")
                c["certificate_name"] = l
                certs.append(c)
        elif section == "lang":
            for ch in re.split(r"[、;；，]|,\s*(?=[A-Z一-鿿])|\s{2,}|\t(?=[A-Z一-鿿][a-z]*\s*[(（:：])", l):
                ch = ch.strip(" .")
                m = re.match(r"^([A-Z][a-z]{2,14}|[一-鿿]{2,4}语)\s*(?:[:：\-–(（]\s*(.*?))?\s*[)）]?\s*[:：]?$", ch)
                if m and len(ch) <= 80:
                    lg = CN.empty("language_list")
                    lv = (m.group(2) or "").strip(" :：")
                    lv = lv + ")" if lv.count("(") > lv.count(")") else lv.rstrip(")") if lv.count(")") > lv.count("(") else lv
                    lg["language_name"], lg["language_level"] = m.group(1), lv.strip()
                    langs.append(lg)
        elif section == "skill":
            if len(l) <= 150 and len(re.findall(r"[A-Za-z一-鿿]", l)) >= 3:
                sk = CN.empty("skills_list")
                sk["skill_name"] = l
                skills.append(sk)
        elif cur is not None:
            body.append(l)
    flush()
    res["certificate_list"] = certs
    res["language_list"] = langs
    res["skills_list"] = skills
    base["pr"] = "\n".join(pr).strip()
    res["work_experiences"].sort(key=lambda w: w["position_start"], reverse=True)
    res["education_list"].sort(key=lambda e: e["school_start_ym"], reverse=True)
    if not (res["work_experiences"] or res["education_list"]):
        return None
    has_zh = len(CJK.findall(text)) >= 300
    return {"resume": res, "updated": "", "unmapped": [], "notes": [], "content_lang": "en", "has_zh_part": has_zh}


if __name__ == "__main__":
    import json
    import sys
    print(json.dumps(parse(Path(sys.argv[1]).read_text(encoding="utf-8")), ensure_ascii=False, indent=1))
