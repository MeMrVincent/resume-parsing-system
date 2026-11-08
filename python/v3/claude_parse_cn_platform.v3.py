#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
claude_parse_cn_platform.v3.py —— 中文招聘平台导出简历（智联招聘为主）的新解析器。

直接从原始文件全文（claude_source_text.v3.py 的输出）解析，不依赖旧的 HTML 中间文件。
入口：parse(text) -> dict | None
  返回 {"resume": <resume 对象（resume_languge="zh"）>, "updated": "YYYY-MM-DD", "unmapped": [未映射栏目名], "notes": [...]}

支持的版式（均来自真实样本）：
  A. 智联 2012-2015：标签与值分行（“手机：”换行“1368…”），“简历名称/应聘职位 … 智联招聘”开头
  B. 智联 2016-2020：制表符分列，“应聘职位：\t… 智联招聘”、“ID：xxx 最近活跃时间”，求职意向为一行一条
  C. 智联 docx 导出：“王女士 王毳 女 | 1993年3月 | 26岁 | …”
栏目：求职意向、自我评价、工作经历/实习经历、项目经历、教育经历、培训经历、证书、语言能力、专业技能、
      在校实践经历/社会实践（→ project_list，keywords=在校实践）、其余栏目记入 unmapped。

EN: claude_parse_cn_platform.v3.py -- new parser for résumés exported from Chinese recruitment platforms (mainly Zhaopin).

Parses directly from the full text of the original file (the output of claude_source_text.v3.py), without relying on the old intermediate HTML.
Entry point: parse(text) -> dict | None
  returns {"resume": <resume object (resume_languge="zh")>, "updated": "YYYY-MM-DD", "unmapped": [unmapped section names], "notes": [...]}

Supported layouts (all from real samples):
  A. Zhaopin 2012-2015: labels and values on separate lines ("手机：" then a line "1368…"), starting with "简历名称/应聘职位 … 智联招聘" (résumé title / position applied for … Zhaopin)
  B. Zhaopin 2016-2020: tab-separated columns, "应聘职位：	… 智联招聘", "ID：xxx 最近活跃时间" (last active time), job preferences one per line
  C. Zhaopin docx export: "<surname>女士 <name> 女 | 1993年3月 | 26岁 | …"
Sections: job preferences, self-assessment, work/internship history, project history, education history, training history, certificates, language skills, professional skills,
      campus practice / social practice (→ project_list, keywords=在校实践); other sections are recorded in unmapped.

JA: claude_parse_cn_platform.v3.py —— 中国の求人プラットフォーム（主に Zhaopin）からエクスポートした履歴書の新しいパーサー。

元のファイルの全文（claude_source_text.v3.py の出力）から直接解析し、旧来の中間 HTML には依存しない。
エントリ：parse(text) -> dict | None
  戻り値 {"resume": <resume オブジェクト（resume_languge="zh"）>, "updated": "YYYY-MM-DD", "unmapped": [対応付けていない欄の名前], "notes": [...]}

対応するレイアウト（すべて実際のサンプルから）：
  A. Zhaopin 2012〜2015：ラベルと値が別の行（「手机：」の次の行に「1368…」）、「简历名称/应聘职位 … 智联招聘」（履歴書名・応募職位 … Zhaopin）で始まる
  B. Zhaopin 2016〜2020：タブ区切りの列、「应聘职位：	… 智联招聘」「ID：xxx 最近活跃时间」（最終アクティブ日時）、希望条件は 1 行に 1 件
  C. Zhaopin の docx エクスポート：「<姓>女士 <氏名> 女 | 1993年3月 | 26岁 | …」
欄：希望条件、自己評価、職歴・インターン経験、プロジェクト経験、学歴、研修歴、資格、語学力、専門スキル、
      在学中の実践・社会実践（→ project_list、keywords=在校实践）。その他の欄は unmapped に記録する。
"""

import re
import unicodedata
from pathlib import Path
import importlib.util

_kspec = importlib.util.spec_from_file_location("claude_merge_checks_v3_pcp", Path(__file__).resolve().parent / "claude_merge_checks.v3.py")
K = importlib.util.module_from_spec(_kspec)
_kspec.loader.exec_module(K)
_spec = importlib.util.spec_from_file_location("claude_merge_common_v3_pcp", Path(__file__).resolve().parent / "claude_merge_common.v3.py")
C = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(C)

SECTIONS = {
    "求职意向": "expected", "期望工作": "expected",
    "自我评价": "pr", "个人评价": "pr", "自我介绍": "pr",
    "工作经历": "work", "工作经验": "work", "实习经历": "work", "实习经验": "work",
    "项目经历": "project", "项目经验": "project",
    "教育经历": "edu", "教育背景": "edu",
    "培训经历": "training",
    "证书": "cert", "专业资格证书": "cert", "所获证书": "cert",
    "语言能力": "lang",
    "专业技能": "skill", "其它技能": "skill", "其他技能": "skill", "特殊技能": "skill", "IT技能": "skill",
    "在校实践经历": "practice", "在校实践经验": "practice", "社会实践": "practice", "社会活动": "practice",
    "在校学习情况": "other", "兴趣爱好": "other", "个人爱好": "other", "获得荣誉": "other", "受到奖励": "other",
    "著作/论文": "other", "其他信息": "other", "附件": "other", "特长爱好": "other",
}
RANGE = r"((?:19|20)\d{2})\s*[./年\-]\s*(\d{1,2})\s*月?\s*[-–—~～至到]+\s*(至今|现在|今|(?:19|20)\d{2}\s*[./年\-]\s*\d{1,2}\s*月?)"
ENTRY_RE = re.compile(r"^" + RANGE + r"\s*(.*)$")
DURATION_TAIL_RE = re.compile(r"[（(]\s*(?:\d+\s*年)?\s*(?:\d+\s*个?月)?\s*[）)]\s*$")
SALARY_RE = re.compile(r"(\d+\s*[-~]\s*\d+\s*元|元/月|万元|/月|年薪|月薪|\d{3,}\s*以[上下]|保密|面议)")
DEGREES = ["博士后", "博士", "MBA", "EMBA", "硕士", "研究生", "本科", "大专", "专科", "中专", "中技", "高中", "职高", "初中"]
DEGREE_RANK = {"博士后": "7", "博士": "6", "MBA": "5", "EMBA": "5", "硕士": "5", "研究生": "5", "本科": "4", "大专": "3", "专科": "3",
               "中专": "2", "中技": "2", "高中": "2", "职高": "2", "初中": "1"}
EDU_TYPE = {"7": "全日制研究生", "6": "全日制研究生", "5": "全日制研究生", "4": "全日制大学", "3": "全日制大专", "2": "全日制高中", "1": "全日制初中及以下"}
LABEL_ONLY_RE = re.compile(r"^[^\s：:]{1,12}\s*[：:]$|^ID$|^[：:]$")


def norm_lines(text: str):
    t = unicodedata.normalize("NFKC", text).replace("　", " ")
    raw = [re.sub(r"[ \t]+$", "", x) for x in t.split("\n")]
    out = []
    i = 0
    while i < len(raw):
        line = raw[i].strip()
        if not line:
            i += 1
            continue
        # “手机：” / “E-mail：” / “ID” “：” 这种标签独占一行时与下一行合并
        # EN: When labels like "手机：" (mobile:) / "E-mail：" / "ID" "：" occupy a line on their own, merge them with the next line
        # JA: 「手机：」（携帯：）／「E-mail：」／「ID」「：」のようなラベルが単独で 1 行を占める場合は、次の行と結合する
        while LABEL_ONLY_RE.match(line) and i + 1 < len(raw):
            j = i + 1
            while j < len(raw) and not raw[j].strip():
                j += 1
            if j >= len(raw):
                break
            nxt = raw[j].strip()
            if nxt in SECTIONS and SECTIONS[nxt] != "other":
                break
            line = (line + nxt) if line.endswith(("：", ":")) or nxt.startswith(("：", ":")) else (line + " " + nxt)
            i = j
        out.append(line)
        i += 1
    return glue_fragments(out)


FRAG_END_RE = re.compile(r"(?:[-–—~/|｜(（:：]|\d{4}\s*[./]\s*\d{1,2}\s*-)\s*$")
FRAG_START_RE = re.compile(r"^(?:[/|｜)）]|年|月|岁|元|个月|至今|现在)")


def glue_fragments(lines):
    """HTML 导出时每个词单独一行（“2017.11 -”“至今”“(1”“年”“ 5”“个月”“)”），把碎片接回原句。

    EN: In HTML exports every word is on its own line ("2017.11 -" "至今" "(1" "年" " 5" "个月" ")"); join the fragments back into the original sentence.

    JA: HTML のエクスポートでは語ごとに 1 行になっている（「2017.11 -」「至今」「(1」「年」「 5」「个月」「)」）。断片をつなぎ直して元の文に戻す。
    """
    out = []
    for l in lines:
        if out and out[-1] not in SECTIONS and l not in SECTIONS and (
                FRAG_END_RE.search(out[-1]) or FRAG_START_RE.match(l)
                or (re.fullmatch(r"[(（]?\s*\d{1,4}", out[-1]) and re.match(r"^(年|月|岁|个月|日)", l))):
            out[-1] = out[-1] + ("" if re.search(r"[:：/]$", out[-1]) or FRAG_START_RE.match(l) else " ") + l
        else:
            out.append(l)
    return out


def ym(y, m):
    try:
        mi = int(m)
    except (TypeError, ValueError):
        return ""
    return f"{int(y):04d}年{mi:02d}月01日" if 1 <= mi <= 12 else ""


def parse_range(m):
    start = ym(m.group(1), m.group(2))
    end_raw = m.group(3)
    if re.match(r"(至今|现在|今)", end_raw):
        end = "至今"
    else:
        mm = re.match(r"((?:19|20)\d{2})\s*[./年\-]\s*(\d{1,2})", end_raw)
        end = ym(mm.group(1), mm.group(2)) if mm else ""
    return start, end


def split_cols(s: str):
    return [x.strip() for x in re.split(r"\t+|\s{2,}", s) if x.strip()]


def empty(lst):
    return {k: "" for k in C.LIST_FIELDS[lst]}


def degree_of(s: str):
    for d in DEGREES:
        if d in s:
            return d
    return ""


# ------------------------------------------------------------------ 头部
# EN: ------------------------------------------------------------------ Header
# JA: ------------------------------------------------------------------ ヘッダー
def parse_header(lines, notes):
    head = "\n".join(lines)
    b = {k: "" for k in C.BASE_FIELDS}
    b["platform_from"] = "智联招聘"
    m = re.search(r"(?:^|\n)\s*(?:姓\s*名)\s*[:：]\s*([一-鿿]{2,4}|[A-Za-z][A-Za-z .]{1,30})", head)
    name = m.group(1).strip() if m else ""
    joined = re.sub(r"\s+", " ", " ".join(lines))
    gm = re.search(r"(?<![一-鿿])(男|女)\W{0,8}(\d{2})\s*岁", joined) or re.search(r"(?<![一-鿿])(男|女)(?![一-鿿])", joined)
    gpos = gm.start() if gm else len(joined)
    if not name:
        # 2019-2020 版：“金女士 女 27岁 … 金秋鸣 女 | 1993年10月 | 27岁”——真实姓名在“性别 | 出生年月”之前
        # EN: 2019-2020 version: "<surname>女士 女 27岁 … <name> 女 | 1993年10月 | 27岁" — the real name comes before "gender | birth date"
        # JA: 2019〜2020 年版：「<姓>女士 女 27岁 … <氏名> 女 | 1993年10月 | 27岁」— 本当の氏名は「性別 | 生年月」の前にある
        mfull = re.search(r"(?:^|\s)([一-鿿]\s?[一-鿿]{1,3}|[A-Za-z][A-Za-z .]{1,30}?)\s+(男|女)\s*[|｜]\s*(?:19|20)\d{2}\s*年", joined)
        if mfull:
            cand = mfull.group(1).replace(" ", "") if re.search(r"[一-鿿]", mfull.group(1)) else mfull.group(1).strip()
            if C.name_quality(cand)[0] == "valid" and cand not in NAME_STOP:
                name = cand
    if not name:
        mg2 = re.search(r"[一-鿿](?:女士|先生|小姐)\s*([一-鿿]{2,4})(?=\s*(?:男|女|手机|\d{11}|$|\s))", joined[:gpos + 20])
        if mg2 and C.name_quality(mg2.group(1))[0] == "valid" and mg2.group(1) not in NAME_STOP:
            name = mg2.group(1)
    if not name:
        # 姓名：取 ID 行之后、性别之前第一个像人名的词（跳过“丁女士”“付先生”这种称呼）
        # EN: Name: take the first person-name-like word after the ID line and before the gender (skipping forms of address like "丁女士" (Ms Ding), "付先生" (Mr Fu))
        # JA: 氏名：ID の行の後、性別の前にある最初の人名らしい語を取る（「丁女士」（丁さん）「付先生」（付さん）のような呼称はスキップする）
        start = 0
        mid = re.search(r"ID\s*[:：]\s*\S+", joined)
        if mid and mid.end() < gpos:
            start = mid.end()
        window = joined[start:gpos + 40]
        window = re.sub(r"(?<![一-鿿])([一-鿿]) ([一-鿿]{1,2})(?![一-鿿])", r"\1\2", window)  # “程 劼”“贾 敏君”
        # EN: Names with a space inside, like "<surname> <given name>"
        # JA: 「<姓> <名>」のように途中に空白のある氏名
        for tok in re.split(r"[\s|｜:：]+", window):
            tok = re.sub(r"^(姓名|应聘者)", "", tok).strip("()（）[]")
            if not tok or tok in NAME_STOP or re.match(r"[一-鿿](先生|女士|小姐)$", tok):
                continue
            if re.fullmatch(r"[一-鿿]{2,4}", tok) and C.name_quality(tok)[0] == "valid" and not degree_of(tok) \
                    and not re.search(r"(区|市|省|县|职业|经验|工作|简历)$", tok):
                name = tok
                break
    if not name:
        mt = re.search(r"([一-鿿](?:先生|女士|小姐))", joined[:gpos + 20])
        honorific = mt.group(1) if mt else ""
        # 2018 版：“包女士 女 30岁 … 户口：上海 包渭芳 电话：…”——真实姓名在电话前，姓与称呼一致
        # EN: 2018 version: "<surname>女士 女 30岁 … 户口：上海 <name> 电话：…" — the real name is before the phone, and the surname matches the form of address
        # JA: 2018 年版：「<姓>女士 女 30岁 … 户口：上海 <氏名> 电话：…」— 本当の氏名は電話の前にあり、姓は呼称と一致する
        if honorific:
            for mr in re.finditer(r"(?<![一-鿿])(" + re.escape(honorific[0]) + r"[一-鿿]{1,3})(?![一-鿿])\s*(?=性\s*别|电\s*话|手\s*机|E-?mail|男|女|(?:\+?86[\s\-]?)?1[3-9]\d{9}|$)", joined[:gpos + 600]):
                cand = mr.group(1)
                if C.name_quality(cand)[0] == "valid" and cand not in NAME_STOP and not re.search(r"(先生|女士|小姐)$", cand):
                    name, honorific = cand, ""
                    break
    else:
        honorific = ""
    if not name:
        # 英文名：ID 编号之后、“手机/性别”之前的一段
        # EN: English name: the segment after the ID number and before "手机/性别" (mobile / gender)
        # JA: 英語名：ID 番号の後、「手机／性别」（携帯・性別）の前の部分
        mid = re.search(r"ID\s*[:：]\s*\S+\s+(.{2,40}?)\s+(?:手机|Mobile|男|女)", joined)
        if mid:
            cand = mid.group(1).replace("_", " ").strip()
            if C.name_quality(cand)[0] == "valid" and cand not in NAME_STOP and not re.search(r"(招聘|简历)", cand):
                name = cand
    if not name:
        # “… 户口:上海| 群众 zhuzhu 13800000019 邮箱”：手机号前的姓名（含英文名）
        # EN: "… 户口:上海| 群众 zhuzhu 13800000019 邮箱" (hukou: Shanghai | masses ...): the name before the mobile number (including English names)
        # JA: 「… 户口:上海| 群众 zhuzhu 13800000019 邮箱」（戸籍：上海｜一般大衆 …）：携帯番号の前の氏名（英語名を含む）
        mph = re.search(r"(?:户口|现居住地)[^|｜]{0,20}[|｜][^0-9]{0,40}?(?<![A-Za-z一-鿿])([一-鿿]{2,4}|[A-Za-z][A-Za-z .]{1,24}?)\s+(?:\+?86[\s\-]?)?1[3-9]\d{9}", joined[:gpos + 600])
        if mph:
            cand = mph.group(1).strip()
            if C.name_quality(cand)[0] == "valid" and cand not in NAME_STOP and not re.search(r"(群众|团员|党员|先生|女士)", cand):
                name, honorific = cand, ""
    b["full_name"] = name or honorific  # 只有“X先生/女士”时保留称呼（merge 会标为姓名不可靠）
    # EN: When there is only "X先生/女士" (Mr/Ms X), keep the form of address (merge will flag the name as unreliable)
    # JA: 「X先生／女士」（X さん）しかない場合は呼称を残す（merge が氏名を信頼できないと印を付ける）
    info = joined[gpos:gpos + 160] if gm else ""
    b["gender"] = gm.group(1) if gm else ""
    ma = re.search(r"(\d{2})\s*岁", info)
    b["age"] = ma.group(1) if ma else ""
    mb = re.search(r"((?:19|20)\d{2})\s*年\s*(\d{1,2})\s*月(?:\s*(\d{1,2})\s*日)?", info) or \
        re.search(r"((?:19|20)\d{2})\s*年\s*(\d{1,2})\s*月(?:\s*(\d{1,2})\s*日)?\s*生", joined)
    if mb:
        b["birth_year"] = mb.group(1)
        b["birth_date"] = f"{int(mb.group(1)):04d}年{int(mb.group(2)):02d}月{int(mb.group(3) or 1):02d}日"
    mm = re.search(r"(已婚|未婚|离异|保密)", info) or re.search(r"(?:婚姻状况|婚姻)\s*[:：]\s*(已婚|未婚|离异|保密)", joined)
    b["marital_status"] = mm.group(1) if mm else ""
    mh = re.search(r"身高\s*[:：]?\s*(\d{3})\s*cm", head, re.I)
    b["height_cm"] = mh.group(1) if mh else ""
    for l in lines:
        if "现居住地" in l or "户口" in l:
            mr = re.search(r"现居住地?\s*[:：]?\s*(.+?)(?=\s*[|｜]|户口|手机|$)", l)
            if mr:
                b["address"] = mr.group(1).strip()
                b["city"] = city_of(b["address"])
            mhk = re.search(r"户口(?:/国籍)?\s*[:：]?\s*(.+?)(?=\s*[|｜]|手机|电话|E-?mail|邮箱|中共|共青团员|团员|群众|民主党派|无党派|\d{11}|$)", l)
            if mhk:
                b["household_registration"] = mhk.group(1).strip()
            mp = re.search(r"(中共党员|中共预备党员|共青团员|团员|群众|民主党派|无党派人士|无党派)", l)
            if mp:
                b["political_status"] = mp.group(1)
            break
    for l in lines:
        ma2 = re.match(r"^地址\s*[:：]\s*([^|｜]+)(?:[|｜]\s*邮编\s*[:：]\s*(\d{6}))?", l)
        if ma2:
            if not b["address"] or len(ma2.group(1).strip()) > len(b["address"]):
                b["address"] = ma2.group(1).strip()
            b["postal_code"] = ma2.group(2) or ""
            break
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
        if re.search(r"(公司电话|紧急联系|联系人)", l):
            continue
        for x in C.MOBILE_FIND.findall(l):
            k, v = C.classify_phone(x)
            if k == "mobile" and v not in ms and not re.search(r"[A-Za-z]" + v, l.replace(" ", "")):
                ms.append(v)
        for x in C.EMAIL_FIND.findall(l):
            for part in C.split_glued(x):
                if "@" in part:
                    k, v = C.classify_email(part)
                    if k == "email" and v not in es:
                        es.append(v)
                else:
                    k, v = C.classify_phone(part)
                    if k == "mobile" and v not in ms:
                        ms.append(v)
    if not ms:
        ms = list(dict.fromkeys(home))
    b["phone"] = "; ".join(ms)
    b["email"] = "; ".join(es)
    b["nationality"] = "中国" if not re.search(r"[一-鿿]+籍", head[:600]) else re.search(r"([一-鿿]+)籍", head[:600]).group(1)
    return b


NAME_STOP = {"待沟通", "保密", "智联招聘", "智联简历", "招聘网", "其他", "简历", "我的简历", "个人简历", "中文简历", "求职简历", "未命名简历", "求职意向",
             "应届毕业生", "目前正在找工作", "下载简历", "未婚", "已婚", "离异", "保密", "团员", "群众", "党员", "手机", "邮箱", "现居住地",
             "户口", "最近活跃时间", "更新时间", "简历名称", "期望从事职业", "简历更新时间", "应聘职位", "应聘机构", "工作地点"}
CITY_RE = re.compile(r"^(北京|上海|天津|重庆)|^([一-鿿]{2,4}?)(?:市|-|\s|$)")


def city_of(v: str) -> str:
    v = v.strip()
    m = re.match(r"^(北京|上海|天津|重庆)", v)
    if m:
        return m.group(1) + "市"
    m = re.match(r"^([一-鿿]{2,3}省)?\s*[-\s]?([一-鿿]{2,4}?)(市|-|\s|$)", v)
    if m and m.group(2):
        return m.group(2) + "市"
    return ""


# ------------------------------------------------------------------ 栏目
# EN: ------------------------------------------------------------------ Sections
# JA: ------------------------------------------------------------------ 欄
def parse_expected(lines):
    out = []
    labeled = {}
    for l in lines:
        m = re.match(r"^(期望工作地区|期望工作地点|期望月薪|期望薪资|目前状况|期望工作性质|工作类型|期望从事职业|期望职位|期望从事行业|期望行业|到岗时间)\s*[:：]\s*(.*)$", l)
        if m:
            labeled[m.group(1)] = m.group(2).strip()
    if labeled:
        e = empty("expected_list")
        e["expected_city"] = labeled.get("期望工作地区") or labeled.get("期望工作地点", "")
        e["expected_salary"] = labeled.get("期望月薪") or labeled.get("期望薪资", "")
        e["expected_start_date"] = labeled.get("目前状况") or labeled.get("到岗时间", "")
        e["expected_employment_type"] = labeled.get("期望工作性质") or labeled.get("工作类型", "")
        e["expected_position"] = labeled.get("期望从事职业") or labeled.get("期望职位", "")
        e["expected_industry"] = labeled.get("期望从事行业") or labeled.get("期望行业", "")
        out.append(e)
        return out
    # B 版式：“化学分析  上海-闵行区  6001-8000元/月 | 电子商务、学术/科研 | 实习、兼职”
    # EN: Layout B: "化学分析  上海-闵行区  6001-8000元/月 | 电子商务、学术/科研 | 实习、兼职" (chemical analysis, Shanghai-Minhang, 6001-8000 yuan/month | e-commerce, academic/research | internship, part-time)
    # JA: レイアウト B：「化学分析  上海-闵行区  6001-8000元/月 | 电子商务、学术/科研 | 实习、兼职」（化学分析・上海閔行区・月 6001〜8000 元｜EC・学術研究｜インターン・パート）
    for l in lines:
        if "|" not in l:
            continue
        parts = [x.strip() for x in l.split("|")]
        cols = split_cols(parts[0])
        e = empty("expected_list")
        if cols:
            e["expected_position"] = cols[0]
        if len(cols) >= 2:
            e["expected_city"] = cols[1]
        if len(cols) >= 3:
            e["expected_salary"] = cols[2]
        if len(parts) >= 2:
            e["expected_industry"] = parts[1]
        if len(parts) >= 3:
            e["expected_employment_type"] = parts[2]
        out.append(e)
    return out


ORG_HINT_RE = re.compile(r"(公司|集团|会社|株式|有限|厂|银行|医院|大学|学院|学校|中学|研究|中心|事务所|协会|政府|局|店|院|所|"
                         r"Co\.|Ltd|Inc|Corp|Group|GmbH|LLC|University|College|School)", re.I)
DUR_RE = re.compile(r"[（(]\s*(?:\d+\s*年)?\s*(?:\d+\s*个?\s*月)?\s*[）)]|[（(]\s*\d+\s*$")


def split_entries(lines, desc_labels=("工作描述", "项目描述", "责任描述", "培训描述", "实践描述")):
    """按“日期区间开头的行”切分条目。描述文字中以日期开头的句子（如“2014.4-2015.7 负责……”）不算新条目。

    EN: Split entries by "lines starting with a date range". Sentences in descriptions starting with a date (e.g. "2014.4-2015.7 负责……" (responsible for ...)) do not count as new entries.

    JA: 「期間で始まる行」で項目を分ける。説明文中の日付で始まる文（例：「2014.4-2015.7 负责……」（〜を担当））は新しい項目とみなさない。
    """
    entries, cur, in_desc = [], None, False
    desc_re = re.compile(r"^(" + "|".join(desc_labels) + r")\s*[:：]")
    for i, l in enumerate(lines):
        m = ENTRY_RE.match(l)
        if m:
            rest = m.group(4).strip()
            nxt = " ".join(lines[i + 1:i + 3])
            looks_header = (not rest) or DUR_RE.search(rest) or ORG_HINT_RE.search(rest) or re.search(r"[|｜]|元\s*/\s*月", nxt) \
                or DUR_RE.search(nxt[:30]) or len(rest) <= 30
            if not in_desc or (looks_header and not re.search(r"(负责|完成|参与|协助|获得|主要|。|；|;)", rest)):
                cur = {"m": m, "rest": rest, "body": []}
                entries.append(cur)
                in_desc = False
                continue
        if cur is not None:
            cur["body"].append(l)
            if desc_re.match(l):
                in_desc = True
    return entries


def glue(s: str) -> str:
    """把被拆成碎片的“4001-6000 元 / 月”“(8 个月 )”“互联网 / 电子商务”粘回去。

    EN: Glue back fragments of "4001-6000 元 / 月", "(8 个月 )", "互联网 / 电子商务" (internet / e-commerce).

    JA: 細切れになった「4001-6000 元 / 月」「(8 个月 )」「互联网 / 电子商务」（インターネット／EC）をつなぎ直す。
    """
    s = re.sub(r"\s*/\s*", "/", s)
    s = re.sub(r"(\d)\s+元", r"\1元", s)
    s = re.sub(r"[（(]\s*(\d+)\s*(年|个月|月)", r"(\1\2", s)
    s = re.sub(r"(\d+)\s*(个月|年)\s*[）)]", r"\1\2)", s)
    s = re.sub(r"(\d+年)\s+(\d+个月)", r"\1 \2", s)
    return re.sub(r"\s+", " ", s).strip()


DEPT_SUFFIX_RE = re.compile(r"(部|科|室|课|处|中心|事业部|本部|部门|组|团队|办公室|车间)$")


def take_label_blocks(body, labels):
    """把“标签：值”及其后续行归到对应标签下。返回 (dict, 前置行)。

    EN: Assign "label: value" and the following lines to the corresponding label. Returns (dict, leading lines).

    JA: 「ラベル：値」とその後の行を対応するラベルの下にまとめる。戻り値：(dict, 前置きの行)。
    """
    got, pre, cur = {}, [], None
    lab_re = re.compile(r"^(" + "|".join(labels) + r")\s*[:：]\s*(.*)$")
    for l in body:
        m = lab_re.match(l)
        if m:
            cur = m.group(1)
            got.setdefault(cur, [])
            if m.group(2).strip():
                got[cur].append(m.group(2).strip())
        elif cur:
            got[cur].append(l)
        else:
            pre.append(l)
    return {k: "\n".join(v).strip() for k, v in got.items()}, pre


def parse_work(lines):
    out = []
    for en in split_entries(lines):
        w = empty("work_experiences")
        w["position_start"], w["position_resigned"] = parse_range(en["m"])
        if w["position_resigned"] == "至今":
            w["status"] = "在职"
        elif w["position_resigned"]:
            w["status"] = "离职"
        lab, pre = take_label_blocks(en["body"], ["工作描述", "工作职责", "主要业绩", "工作业绩", "离职原因", "汇报对象", "下属人数",
                                                  "所在部门", "职位名称", "公司性质", "公司规模", "公司行业", "所属行业", "软件环境",
                                                  "硬件环境", "开发工具"])
        # 条目头：日期行剩余部分 + 描述之前的各行，拼成一串再解析
        # EN: Entry header: the rest of the date line + the lines before the description, joined into one string and then parsed
        # JA: 項目の見出し：日付行の残り + 説明の前の各行を 1 つの文字列につなげてから解析する
        hdr = glue(" ".join([en["rest"]] + pre))
        comp, rest = hdr, ""
        md = DUR_RE.search(hdr)
        if md:
            comp, rest = hdr[:md.start()].strip(), hdr[md.end():].strip()
        elif en["rest"]:
            comp = glue(en["rest"])
            rest = glue(" ".join(pre))
        elif pre:
            comp = glue(pre[0])
            rest = glue(" ".join(pre[1:]))
        w["company_name"] = re.sub(r"^([一-鿿])\s+(?=[一-鿿])", r"\1", comp.strip(" |"))  # HTML 碎片：“迪 爱生投资”
        # EN: HTML fragments: "迪 爱生投资"
        # JA: HTML の断片：「迪 爱生投资」
        ms = SALARY_RE.search(rest)
        before, after = (rest[:ms.start()], rest[ms.end():]) if ms else (rest, "")
        if ms:
            # 取完整薪资片段（如“6001-8000元/月”“年薪 8-10万”）
            # EN: Take the complete salary fragment (e.g. "6001-8000元/月", "年薪 8-10万" (annual salary 80-100k))
            # JA: 完全な給与の断片を取る（例：「6001-8000元/月」「年薪 8-10万」（年収 8〜10 万元））
            mfull = re.search(r"[\d\-~万千元/月年薪以上下 ]*" + re.escape(ms.group(0)) + r"[\d\-~万千元/月年薪以上下]*", rest)
            w["position_salary"] = (mfull.group(0) if mfull else ms.group(0)).strip(" |")
            before = rest[:mfull.start()] if mfull else before
            after = rest[mfull.end():] if mfull else after
        else:
            # 无薪资：第一段“|”之前为职位，其余为行业/性质/规模
            # EN: No salary: the first segment before "|" is the position, the rest are industry/type/size
            # JA: 給与なし：最初の「|」の前の部分が職位、残りが業界・性質・規模
            parts0 = [x.strip() for x in re.split(r"\s*[|｜]\s*", rest) if x.strip()]
            before = " | ".join(parts0[:2]) if len(parts0) >= 2 and not re.match(r"(企业性质|规模|公司性质)", parts0[1]) else (parts0[0] if parts0 else "")
            after = " | ".join(parts0[2:] if before.count("|") else parts0[1:])
        bparts = [x.strip() for x in re.split(r"\s*[|｜]\s*", before) if x.strip()]
        if bparts and not after.strip():
            toks = bparts[-1].split(" ")
            if len(toks) >= 2 and K.INDUSTRY_SEG_RE.search(toks[-1]):
                bparts[-1] = " ".join(toks[:-1])
                after = toks[-1]
        if len(bparts) >= 2:
            w["position_dept"], w["position"] = bparts[-2], bparts[-1]
        elif len(bparts) == 1:
            if DEPT_SUFFIX_RE.search(bparts[0]) and not re.search(r"(部长|科长|主任|经理|主管|总监)$", bparts[0]):
                w["position_dept"] = bparts[0]
            else:
                w["position"] = bparts[0]
        ind_parts = []
        for p in [x.strip() for x in re.split(r"\s*[|｜]\s*", after) if x.strip()]:
            mm = re.match(r"^(规模|公司规模)\s*[:：]\s*(.*)$", p)
            if mm:
                w["company_employees"] = mm.group(2).strip()
            elif re.match(r"^(企业性质|公司性质)", p):
                continue
            else:
                ind_parts.append(p)
        ind_parts = [re.sub(r"^(以下|以上)\s*", "", x) for x in ind_parts]
        ind_parts = [x for x in ind_parts if x]
        if ind_parts and not w["company_industry"]:
            w["company_industry"] = "|".join(ind_parts)
        w["position_dept"] = w["position_dept"] or lab.get("所在部门", "")
        w["position"] = w["position"] or lab.get("职位名称", "")
        w["company_industry"] = w["company_industry"] or lab.get("公司行业", "") or lab.get("所属行业", "")
        w["company_employees"] = w["company_employees"] or lab.get("公司规模", "")
        w["position_report_to"] = lab.get("汇报对象", "")
        w["position_subordinate"] = lab.get("下属人数", "")
        w["resigned_reason"] = lab.get("离职原因", "")
        w["position_responsibilities"] = lab.get("工作描述") or lab.get("工作职责", "")
        w["position_achievements"] = lab.get("主要业绩") or lab.get("工作业绩", "")
        w["employment_type"] = "全职"
        if w["company_name"] in ("***", ":", "：") or re.fullmatch(r"[\W_]*", w["company_name"]):
            w["company_name"] = ""
        out.append(w)
    return out


def parse_edu(lines):
    out = []
    for en in split_entries(lines):
        e = empty("education_list")
        e["school_start_ym"], e["school_end_ym"] = parse_range(en["m"])
        cols = split_cols(en["rest"])
        if len(cols) == 1 and " " in cols[0]:
            cols = cols[0].split()
        extra = [x for x in en["body"] if len(x) <= 40 and not re.search(r"[:：]", x)][:3]
        if cols and extra and all(x in cols[0] for x in extra):
            extra = []  # 学校行已含专业/学历（单空格分隔），后续行是重复
            # EN: The school line already contains major/degree (separated by single spaces); the following lines are duplicates
            # JA: 学校の行にすでに専攻・学歴がある（1 つの空白で区切る）ので、後続の行は重複
        cols += extra
        if len(cols) > 1 and " " in cols[0] and all(x in cols[0] for x in cols[1:]):
            cols = [cols[0]]
        if len(cols) == 1 and " " in cols[0]:
            cols = cols[0].split()
        deg = ""
        if cols and ((degree_of(cols[-1]) and len(cols[-1]) <= 8) or cols[-1] in ("其他", "其它")):
            deg = cols.pop()
        e["school_name"] = cols[0] if cols else ""
        e["school_major_name"] = " ".join(cols[1:]) if len(cols) > 1 else ""
        if e["school_major_name"] in ("无", "-", "—", "暂无"):
            e["school_major_name"] = ""
        d = degree_of(deg)
        e["school_degree_type"] = deg
        e["school_degree_rank"] = DEGREE_RANK.get(d, "")
        e["school_education_type"] = "统招" if "统招" in deg else ""
        if not e["school_name"] and any(x["school_start_ym"] == e["school_start_ym"] and x["school_end_ym"] == e["school_end_ym"] for x in out):
            continue  # 平台导出时同一段学历重复一行、且没有学校名
            # EN: On platform export the same education entry is repeated on one line without the school name
            # JA: プラットフォームのエクスポートでは同じ学歴が学校名なしでもう 1 行繰り返される
        out.append(e)
    return out


def parse_project(lines, practice=False):
    out = []
    for en in split_entries(lines):
        p = empty("project_list")
        s, e = parse_range(en["m"])
        p["start_ym"], p["end_ym"] = s, e
        lab, pre = take_label_blocks(en["body"], ["项目描述", "责任描述", "项目职务", "担任职务", "所在公司", "项目业绩", "开发工具", "软件环境",
                                                  "硬件环境", "实践描述", "活动描述"])
        p["project_name"] = en["rest"] or (pre.pop(0) if pre else "")
        p["role_name"] = lab.get("项目职务") or lab.get("担任职务", "")
        p["company_or_client"] = lab.get("所在公司", "")
        p["description"] = lab.get("项目描述") or lab.get("实践描述") or lab.get("活动描述") or "\n".join(pre)
        p["responsibilities"] = lab.get("责任描述", "")
        p["achievements"] = lab.get("项目业绩", "")
        p["keywords"] = "在校实践" if practice else ""
        out.append(p)
    return out


def parse_training(lines):
    out = []
    for en in split_entries(lines):
        t = empty("training_list")
        t["start_ym"], t["end_ym"] = parse_range(en["m"])
        lab, pre = take_label_blocks(en["body"], ["培训机构", "培训地点", "所获证书", "培训描述", "培训课程"])
        cols = split_cols(en["rest"])
        t["training_name"] = lab.get("培训课程") or (cols[0] if cols else (pre.pop(0) if pre else ""))
        t["organization_name"] = lab.get("培训机构", "") or (cols[1] if len(cols) > 1 else "")
        t["certificate_name"] = lab.get("所获证书", "")
        t["description"] = lab.get("培训描述", "") or "\n".join(pre)
        out.append(t)
    return out


def parse_cert(lines):
    out = []
    fixed = []
    for l in lines:
        if fixed and re.fullmatch(r"(?:19|20)\d{2}\s*[./年\-]\s*\d{1,2}\s*月?", fixed[-1]):
            fixed[-1] = fixed[-1] + " " + l
        else:
            fixed.append(l)
    lines = [l for l in fixed if not re.fullmatch(r"(?:19|20)\d{2}\s*[./年\-]\s*\d{1,2}\s*月?", l)]
    for l in lines:
        m = re.match(r"^((?:19|20)\d{2})\s*[./年\-]\s*(\d{1,2})\s*月?\s+(.+)$", l)
        c = empty("certificate_list")
        if m:
            c["certificate_time"] = ym(m.group(1), m.group(2))
            name = m.group(3)
        else:
            name = l
        name = re.sub(r"\s*[|｜].*$", "", name).strip()
        if re.match(r"^(证书说明|说明|备注)\s*[:：]", name):
            continue
        if name and not re.fullmatch(r"[\d\s.\-]+", name):
            c["certificate_name"] = name
            out.append(c)
    return out


def parse_lang(lines):
    out = []
    joined = []
    for l in lines:
        if joined and (joined[-1].endswith(("：", ":")) or l.startswith("|") or joined[-1].endswith("|")):
            joined[-1] = joined[-1] + " " + l
        else:
            joined.append(l)
    for l in joined:
        m = re.match(r"^([一-鿿A-Za-z]{1,8}?)\s*[:：]\s*(.+)$", l)
        if not m:
            continue
        g = empty("language_list")
        g["language_name"] = m.group(1)
        g["language_level"] = m.group(2).strip()
        out.append(g)
    return out


def parse_skill(lines):
    out = []
    for l in lines:
        m = re.match(r"^(.{1,40}?)\s*[:：]\s*(.{0,20})$", l) or re.match(r"^(.{1,40}?)\s*[|｜]\s*.*?[|｜]?\s*(精通|熟练|良好|一般|了解)\s*$", l)
        k = empty("skills_list")
        if m:
            k["skill_name"], k["skill_level"] = m.group(1).strip(), m.group(2).strip()
        elif len(l) <= 40:
            k["skill_name"] = l
        else:
            continue
        out.append(k)
    return out


# ------------------------------------------------------------------ 入口
# EN: ------------------------------------------------------------------ Entry point
# JA: ------------------------------------------------------------------ エントリ
def detect(text: str) -> bool:
    h = unicodedata.normalize("NFKC", text[:3000])
    if re.search(r"X-51JOB|51job|前程无忧", h):
        return False
    if re.search(r"智联招聘|zhaopin|ID[:：]\s*J[MRS]\d|J[MRS]\d{9}R", h):
        return True
    # 2018 版智联导出：“期望从事职业 / 简历更新时间 / ID：随机串”
    # EN: 2018 Zhaopin export: "期望从事职业 / 简历更新时间 / ID：random string" (desired occupation / résumé update time / ID)
    # JA: 2018 年の Zhaopin のエクスポート：「期望从事职业 / 简历更新时间 / ID：ランダムな文字列」（希望職種・履歴書の更新日時・ID）
    return bool(re.search(r"简历更新时间", h) and re.search(r"(?m)^\s*ID\s*$|ID\s*[:：]", h) and re.search(r"期望从事职业|求职意向", h))


def parse(text: str):
    lines = norm_lines(text)
    head_txt = " ".join(lines[:40])
    if re.search(r"\b(Male|Female)\b", head_txt) and not re.search(r"(?<![一-鿿])(男|女)(?![一-鿿])", head_txt):
        return None  # 智联英文版简历，交给英文解析器
        # EN: Zhaopin English résumés are handed to the English parser
        # JA: Zhaopin の英語版の履歴書は英語のパーサーに任せる
    # 切栏目
    # EN: Split into sections
    # JA: 欄に分ける
    first_sec = next((i for i, l in enumerate(lines) if l in SECTIONS), len(lines))
    head, secs = lines[:first_sec], []
    cur = None
    for l in lines[first_sec:]:
        if l in SECTIONS:
            cur = [l, []]
            secs.append(cur)
        elif cur:
            cur[1].append(l)
    notes, unmapped = [], []
    base = parse_header(head, notes)
    res = {"resume_languge": "zh", "base_info": base}
    for lst in C.LIST_FIELDS:
        res[lst] = []
    for title, body in secs:
        kind = SECTIONS[title]
        if kind == "expected":
            res["expected_list"] += parse_expected(body)
        elif kind == "pr":
            base["pr"] = "\n".join(body).strip()
        elif kind == "work":
            res["work_experiences"] += parse_work(body)
        elif kind == "edu":
            res["education_list"] += parse_edu(body)
        elif kind == "project":
            res["project_list"] += parse_project(body)
        elif kind == "practice":
            res["project_list"] += parse_project(body, practice=True)
        elif kind == "training":
            res["training_list"] += parse_training(body)
        elif kind == "cert":
            res["certificate_list"] += parse_cert(body)
        elif kind == "lang":
            res["language_list"] += parse_lang(body)
        elif kind == "skill":
            res["skills_list"] += parse_skill(body)
        else:
            unmapped.append(title)
    for i, p in enumerate(res["project_list"], 1):
        p["sequence_no"] = str(i)
    for i, t in enumerate(res["training_list"], 1):
        t["sequence_no"] = str(i)
    mu = re.search(r"(?:简历更新时间|更新时间)\s*[:：]?\s*((?:19|20)\d{2})[./\-](\d{1,2})[./\-](\d{1,2})", "\n".join(head))
    updated = f"{mu.group(1)}-{int(mu.group(2)):02d}-{int(mu.group(3)):02d}" if mu else ""
    return {"resume": res, "updated": updated, "unmapped": unmapped, "notes": notes}


if __name__ == "__main__":
    import json
    import sys
    t = Path(sys.argv[1]).read_text(encoding="utf-8")
    print(json.dumps(parse(t), ensure_ascii=False, indent=1))
