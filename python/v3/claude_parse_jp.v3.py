#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
claude_parse_jp.v3.py —— 日文简历（履歴書 / 職務経歴書 / 紐培等推荐表日文版 / 51job 日文版 / xls 日文表格）的新解析器。

直接从原文全文解析，输出 resume_languge="jp" 的 resume。入口：detect(text) -> bool，parse(text) -> dict | None。

识别的行形态（均来自真实样本）：
  区间行   “2012.09-2015.06　中国地質大学　人事資源管理学　大卒”“2016.05-現在　白井電子商貿(上海)有限会社　営業担当”
  表格行   “2006年 9月\t2010年 6月\t上海海洋大学\t国際経済と貿易\t大卒\t上海”（xls 履歴書）
  履歴行   “2007\t9\t青岛飛洋学院商務日本語　入学”“平成12年9月　上海市理工大学附属高校 入学”（入学/卒業、入社/退社 成对）
学歴 / 職歴 / 免許・資格 由栏目标题和关键词区分；自己PR、志望動機等进 pr。

EN: claude_parse_jp.v3.py -- new parser for Japanese résumés (rirekisho / shokumu keirekisho / Japanese versions of recommendation forms / 51job Japanese version / Japanese xls tables).

Parses directly from the full source text and outputs a resume with resume_languge="jp". Entry points: detect(text) -> bool, parse(text) -> dict | None.

Recognised line shapes (all from real samples):
  range rows   "2012.09-2015.06　中国地質大学　人事資源管理学　大卒" "2016.05-現在　白井電子商貿(上海)有限会社　営業担当"
  table rows   "2006年 9月	2010年 6月	上海海洋大学	国際経済と貿易	大卒	上海" (xls rirekisho)
  history rows "2007	9	青岛飛洋学院商務日本語　入学" "平成12年9月　上海市理工大学附属高校 入学" (入学/卒業, 入社/退社 in pairs)
学歴 (education) / 職歴 (work history) / 免許・資格 (licences/qualifications) are distinguished by section headings and keywords; 自己PR, 志望動機 (motivation) etc. go into pr.

JA: claude_parse_jp.v3.py —— 日本語の履歴書（履歴書・職務経歴書・推薦表の日本語版・51job の日本語版・xls の日本語の表）の新しいパーサー。

原文の全文から直接解析し、resume_languge="jp" の resume を出力する。エントリ：detect(text) -> bool、parse(text) -> dict | None。

識別する行の形（すべて実際のサンプルから）：
  期間の行   「2012.09-2015.06　中国地質大学　人事資源管理学　大卒」「2016.05-現在　白井電子商貿(上海)有限会社　営業担当」
  表の行   「2006年 9月	2010年 6月	上海海洋大学	国際経済と貿易	大卒	上海」（xls の履歴書）
  経歴の行   「2007	9	青岛飛洋学院商務日本語　入学」「平成12年9月　上海市理工大学附属高校 入学」（入学／卒業、入社／退社 を組にする）
学歴・職歴・免許・資格は欄の見出しとキーワードで区別し、自己PR・志望動機などは pr に入れる。
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


CN = _load("claude_parse_cn_platform_v3_jp", "claude_parse_cn_platform.v3.py")
J5 = _load("claude_parse_51job_v3_jp", "claude_parse_51job.v3.py")
C = CN.C

KANA_RE = re.compile(r"[ぁ-ゖァ-ヺ]")
ERA = {"平成": 1988, "昭和": 1925, "令和": 2018, "H": 1988, "S": 1925, "R": 2018}
YEAR = r"((?:19|20)\d{2}|(?:平成|昭和|令和)\s*\d{1,2}|[HSR]\s*\d{1,2})"
RANGE_RE = re.compile(r"^(?:[※・*①-⑳]|\d{1,2}\s*[、.)]\s*(?=(?:19|20)\d{2}))?\s*" + YEAR + r"\s*[年./\-]\s*(\d{1,2})\s*月?\s*(?:から\s*[-~～–—―‐−〜]*|[-~～–—―‐−〜至]+)\s*"
                      r"((?:" + YEAR[1:-1] + r")\s*[年./\-]\s*\d{1,2}\s*月?|現在(?:に至る)?|現在|现在|目前|至今|今|在職中|在学中)\s*(?:まで)?\s*[：:]?\s*(.*)$")
GRID_RE = re.compile(r"^" + YEAR + r"\s*年\s*(\d{1,2})\s*月\s+" + YEAR + r"\s*年\s*(\d{1,2})\s*月\s*(.*)$")
EVENT_RE = re.compile(r"^" + YEAR + r"\s*[年./\-\t ]\s*(\d{1,2})\s*月?\s*[\t ]\s*(.+)$")
EDU_END = re.compile(r"(入学|入校|卒業|修了|中退|在学中|在学|編入|転入|退学|卒業見込み?)\s*$")
WORK_END = re.compile(r"(バイト終了|終了|開始|入社|入職|退社|退職|在職中|現在に至る|一身上の都合により退社|会社都合により退社|転籍|出向)\s*$")
SCHOOL_HINT = re.compile(r"(大学|学院|学校|高校|中学|小学|専門|短大|大専|高専|学部|研究科|University|College|School)", re.I)
ORG_HINT = re.compile(r"(会社|株式|有限|公司|集団|集团|工場|銀行|病院|事務所|センター|Co\.|Ltd|Inc|Corp|GmbH)", re.I)
DEG_MAP = [("博士", "6"), ("修士", "5"), ("大学院", "5"), ("MBA", "5"), ("研究生", "5"), ("硕士", "5"), ("大卒", "4"), ("学士", "4"), ("本科", "4"),
           ("四大", "4"), ("短大", "3"), ("大専", "3"), ("大专", "3"), ("専門", "3"), ("高専", "3"), ("高卒", "2"), ("高校", "2"), ("高中", "2"),
           ("中専", "2"), ("中专", "2")]
ZH_HEADS = (r"实践经验|海外经历|学生实践|社会经历|校园经历|实习经验|在校经历|技能特长|简历内容|在校学习情况|在校实践经验|在校情况|校内职务|校内荣誉|求职意向|个人基本信息|个人简历|学历背景|教育情况|学历|证书|项目业绩|基本信息|个人信息|个人资料|教育经历|教育背景|学历信息|教育信息|学习经历|工作经历|工作经验|工作履历|实习经历|项目经历|项目经验|培训经历|"
            r"资格证书|证书|所获证书|技能特长|专业技能|个人技能|语言能力|自我评价|个人评价|推荐理由|顾问评价|顾问意见|校内荣誉|获奖情况|求职意向|"
            r"薪资水平|社会实践|兴趣爱好|其他信息|附加信息|")
SECTION_RE = re.compile(r"^\s*[■◆●【\[]?\s*(" + ZH_HEADS + r"学\s*歴(?:\s*・\s*職\s*歴)?|[職职]\s*[歴暦]|賞\s*罰|職\s*務\s*(?:経\s*歴|履\s*歴|経\s*験)|職\s*歴\s*概\s*要|勤\s*務\s*経\s*歴|学\s*習\s*経\s*歴|職務経歴書|教育背景|基\s*本\s*情\s*報|個\s*人\s*情\s*報|履\s*歴\s*書|教\s*育|業\s*務\s*経\s*歴|プロフィール|家族構成|参加プロジェクト|プロジェクト(?:経歴|経験)?|トレーニング歴|研修歴|特長と趣味|語\s*学\s*力|教\s*育\s*経\s*歴|学\s*業\s*経\s*歴|"
                        r"免\s*許\s*[・、]?\s*資\s*格|資\s*格|スキル\s*[・、]?\s*資格|自\s*己\s*(?:PR|ＰＲ|紹介)|志\s*望\s*動\s*機|趣\s*味|特\s*技|"
                        r"本人希望|職務内容|セールスポイント|語学|語学力|ＰＣスキル|PCスキル)\s*[】\]]?\s*[:：]?\s*(?:[(（][^)）]{0,15}[)）])?\s*[:：]?\s*(?:[A-Za-z][A-Za-z \-/&]{2,40})?\s*$")


def year_of(y: str) -> int:
    y = re.sub(r"\s", "", y)
    m = re.match(r"(平成|昭和|令和|[HSR])(\d{1,2})", y)
    if m:
        return ERA[m.group(1)] + int(m.group(2))
    return int(y)


def ymd(y, m):
    try:
        yy, mm = year_of(y), int(m)
    except (TypeError, ValueError):
        return ""
    return f"{yy:04d}年{mm:02d}月01日" if 1 <= mm <= 12 and 1940 <= yy <= 2030 else ""


def end_of(s: str):
    if re.match(r"(現在|现在|目前|至今|今|在職中|在学中)", s):
        return "至今"
    m = re.match(YEAR + r"\s*[年./\-]\s*(\d{1,2})", s)
    return ymd(m.group(1), m.group(2)) if m else ""


def detect(text: str) -> bool:
    if CN.detect(text) or J5.detect(text):
        return False
    h = text[:3000]
    return bool(re.search(r"履\s*歴\s*書|職\s*務\s*経\s*歴|氏\s*名|ふりがな|フリガナ|生年月日|学\s*歴|職\s*歴", h)) and len(KANA_RE.findall(text)) >= 20


def pick_sheet(text: str) -> str:
    """xls：多个工作表时取日文最多的那张（履歴書），不含面试评价表。

    EN: xls: with several worksheets, take the one with the most Japanese (the rirekisho), excluding interview evaluation sheets.

    JA: xls：ワークシートが複数ある場合は日本語が最も多いもの（履歴書）を取り、面接評価表は含めない。
    """
    if not text.startswith("### sheet"):
        return text
    parts = re.split(r"(?m)^### sheet (.*)$", text)
    sheets = [(parts[i], parts[i + 1]) for i in range(1, len(parts) - 1, 2) if parts[i + 1].strip()]
    if not sheets:
        return text
    best = max(sheets, key=lambda x: (not re.search(r"(参考|記入例|サンプル|sample|例|評価|评定|评价|面试)", x[0], re.I),
                                      bool(re.search(r"(氏\s*名|履\s*歴)", x[1])), len(KANA_RE.findall(x[1]))))
    return best[1]


LABELS = ["时间", "公司", "学校", "公司名称", "工作时间", "在职时间", "勤務期間", "在籍期間", "従業人数", "配属部門", "現在収入", "社名", "期間", "業務", "会社業務", "会社名", "公司性質", "入退社年月", "社員数", "職務概要", "転職理由", "所属部門", "部署", "職位", "役職", "担当業務", "業務内容", "職務内容", "業種", "事業内容", "事業概要", "従業員数", "従業員",
          "退職理由", "会社性質", "勤務地", "専攻", "部下"]
LABEL_ROW = re.compile(r"^(" + "|".join(LABELS) + r")$")
LONG_SPLIT = re.compile(r"(?=[※]?(?:(?:19|20)\d{2}\s*[年./]\s*\d{1,2}\s*月?\s*(?:[-~～–—―‐−〜]|から)))|(?=(?:事業内容|勤務地|従業員|担当業務|職務内容|退職理由|実績)[:：])"
                        r"|(?=自己PR)|(?=セールスポイント)|(?=志望動機)")
PR_START = re.compile(r"^(?:(自我评价|个人评价|自我介绍|推荐理由|顾问评价|志望の?動機|自己\s*PR|自分\s*PR|自己紹介|自己アピール|セールスポイント|アピールポイント|推薦理由|推薦コメント|自叙伝)[^\s:：]{0,10}\s*(?:[:：]|\s|$)|"
                      r"(コメント|本人希望|性\s*格|経\s*験|言語レベル|語学レベル|長\s*所|強\s*み)\s*(?:[:：]|\t|$))\s*(.*)$")
CERT_LINE = re.compile(r"(試験|検定|[1-6一二三四五六]級|資格|免許|証書|TOEIC|TOEFL|IELTS|CET|JLPT|N[1-5](?![0-9])|BJT)", re.I)
OTHER_START = re.compile(r"^(期望薪资|期望月薪|目前薪资|求职意向|在职状况|身高|特技|得意科目|最寄り駅|保護者|技能レベル|希望職種|希望月収|趣\s*味|健康状態|通勤時間|扶養家族|海外履歴|PCスキル|パソコン|給\s*与|希望給与|希望給料|現在給与)")
CERT_START = re.compile(r"^(资格证书|所获证书|技能資格|保有資格|資格他|資格・免許|免許・資格|資格|免許|取得資格)\s*(?:\t|[:：]|$)\s*(.*)$")
TABLE_HEAD = re.compile(r"^(入社年月|入学年月|入職年月|年\s*月\s*$)")
NATURE_TOK = re.compile(r"^[(（]?(日系|外資系?|民営|国営|独資|合資|個人経営|欧米系|台湾系|香港系|国有|中外合資|合弁)[)）]?$")


HDR_RE = re.compile(r"^(フリガナ|ふりがな|氏\s*名|生年月日|性\s*別|婚姻状況|現住所|戸\s*籍|出身地|身\s*長|体\s*重|民\s*族|固定電話|携帯電話|E-?MAIL|"
                    r"現職給与.*|賞与.*|現在年収.*|希望給与.*|年\s*齢|国\s*籍|最終学歴|日本語レベル|英語レベル|電話|メール)$", re.I)


SPACED_WORDS = sorted(set(LABELS + ["名前", "氏名", "姓名", "性別", "性别", "年齢", "民族", "戸籍", "住所", "現住所", "学歴", "職位", "部下", "特長", "趣味",
                                    "身長", "体重", "国籍", "専攻", "業種", "婚姻", "出身地", "配偶者", "生年月日", "学校名", "会社名", "役職", "職歴"]), key=len, reverse=True)
SPACED_RE = re.compile(r"(" + "|".join(r"[ \t]*".join(w) for w in SPACED_WORDS if len(w) >= 2) + r")(?=[ \t]*[:：\t]|[ ]{2,}|$)")


def explode(l: str):
    """xls 的“所属部門\t営業部\t職位\t営業担当”→ 每个标签一行“标签：值”。

    EN: xls "所属部門	営業部	職位	営業担当" → one "label: value" line per label.

    JA: xls の「所属部門	営業部	職位	営業担当」→ ラベルごとに 1 行の「ラベル：値」にする。
    """
    parts = [re.sub(r"(?<=[一-鿿ぁ-ヺ])\s+(?=[一-鿿ぁ-ヺ])", "", x.strip()) if len(x.strip()) <= 8 else x for x in l.split("\t")]
    first_lab = next((i for i, x in enumerate(parts) if LABEL_ROW.match(x.strip())), None)
    if first_lab and len(parts) >= 3 and not re.match(r"^(?:19|20)\d{2}", parts[0].strip()):
        pre = " ".join(x.strip() for x in parts[:first_lab] if x.strip())
        return ([pre] if pre else []) + explode("\t".join(parts[first_lab:]))
    if len(parts) >= 2 and LABEL_ROW.match(parts[0].strip()):
        out, i = [], 0
        while i < len(parts):
            p = parts[i].strip()
            if LABEL_ROW.match(p):
                v = []
                i += 1
                while i < len(parts) and not LABEL_ROW.match(parts[i].strip()):
                    v.append(parts[i].strip())
                    i += 1
                out.append(p + "：" + " ".join(x for x in v if x))
            else:
                if out:
                    out[-1] += " " + p
                else:
                    out.append(p)
                i += 1
        return out
    return [l]


HAN_RE = re.compile(r"[一-鿿]")
SIMP_RE = re.compile(r"[的了们这个为与经历职责务计业岗过说对时间还没种发现实际简执专资规划负练讯营销约请让认识该从进]")


def jp_segment(lines):
    """中日双语文档：去掉前面/后面的纯中文部分，只保留日文部分。

    EN: Chinese-Japanese bilingual documents: remove the pure Chinese parts before/after and keep only the Japanese part.

    JA: 中日のバイリンガル文書：前後の中国語だけの部分を除き、日本語の部分だけを残す。
    """
    kana = [len(KANA_RE.findall(x)) for x in lines]
    simp = [len(SIMP_RE.findall(x)) for x in lines]
    han = [len(HAN_RE.findall(x)) for x in lines]

    def ratio(a, b):
        k, h = sum(kana[a:b]), sum(han[a:b])
        return k / max(k + h, 1), h
    n = len(lines)
    lo, hi = 0, n
    for i in range(10, n - 10):
        r_pre, h_pre = ratio(0, i)
        r_post, _ = ratio(i, min(n, i + 25))
        if r_pre < 0.03 and h_pre >= 150 and r_post >= 0.1 and sum(simp[:i]) >= max(15, 0.05 * h_pre):
            lo = i
            break
    for i in range(n - 10, lo + 10, -1):
        r_suf, h_suf = ratio(i, n)
        r_before, _ = ratio(max(lo, i - 25), i)
        if r_suf < 0.03 and h_suf >= 150 and r_before >= 0.1 and sum(simp[i:]) >= max(15, 0.05 * h_suf):
            hi = i
            break
    return lines[lo:hi]


def lines_of(text: str):
    t = unicodedata.normalize("NFKC", re.sub(r"[①-⑳❶-❿➀-➉]", "※", pick_sheet(text))).replace("　", " ")
    t = re.sub(r"\[([^\]\n]{2,6})\]", r"\1：", t)
    t = re.sub(r"((?:19|20)\d{2})-(\d{2})-(\d{2}) 00:00:00", lambda m: f"{m.group(1)}年{m.group(2)}月" + ("" if m.group(3) == "01" else f"{m.group(3)}日"), t)  # xls 日期单元格
    # EN: xls date cells
    # JA: xls の日付のセル
    t = t.replace("〈実績〉", "実績：")
    t = re.sub(r"((?:19|20)\d{2}\s*年\s*\d{1,2}\s*月)([ \t]+)年[ \t]+月(?=[ \t])", r"\1-現在\2", t)  # 表格里退社年月空着 = 在职
    # EN: An empty leaving year-month in the table = still employed
    # JA: 表の退社年月が空 = 在職中
    # “学校名 2009年9月入学 2013年6月卒業” → 区间行
    # EN: "school name 2009年9月入学 2013年6月卒業" → a range line
    # JA: 「学校名 2009年9月入学 2013年6月卒業」→ 期間の行
    t = re.sub(r"(?m)^([^\n\d]{3,40}?)[ \t]+((?:19|20)\d{2}\s*年\s*\d{1,2}\s*月)\s*入学[ \t]+((?:19|20)\d{2}\s*年\s*\d{1,2}\s*月)\s*(?:卒業|修了)(?:見込み?)?",
               r"\2-\3\t\1", t)
    t = SPACED_RE.sub(lambda m: re.sub(r"[ \t]", "", m.group(1)), t)
    out = []
    raw = t.split("\n")
    paired = []
    i = 0
    while i < len(raw):
        cells = [c.strip() for c in raw[i].split("\t")]
        heads = [c for c in cells if c]
        if len(heads) >= 3 and all(HDR_RE.match(c) for c in heads) and i + 1 < len(raw):
            vals = [c.strip() for c in raw[i + 1].split("\t")]
            nv = [c for c in vals if c]
            if len(nv) >= 2 and not all(HDR_RE.match(c) for c in nv):
                for j, c in enumerate(cells):
                    if c and j < len(vals) and vals[j]:
                        paired.append(c + "：" + vals[j])
                i += 2
                continue
        paired.append(raw[i])
        i += 1
    for l in paired:
        l = re.sub(r"[ ]{2,}", "\t", l.strip())
        # “職　　位：”“部　　下：”→“職位：”
        # EN: "職　　位：" "部　　下：" → "職位："
        # JA: 「職　　位：」「部　　下：」→「職位：」
        l = re.sub(r"^((?:[一-鿿ぁ-ヺ]\s*){2,6})(?=[:：])", lambda m: re.sub(r"\s", "", m.group(1)), l)
        if not l.strip() or re.fullmatch(r"[※・*\s]+", l):
            continue
        # 学校/公司在前、年月在后的表格行：“日本筑波大学 経営政策・科学 修士\t2011-04\t2013-03\t卒業”
        # EN: Table rows with school/company first and year-months after: "日本筑波大学 経営政策・科学 修士\t2011-04\t2013-03\t卒業"
        # JA: 学校・会社が先で年月が後ろにある表の行：「日本筑波大学 経営政策・科学 修士\t2011-04\t2013-03\t卒業」
        msf = re.match(r"^([^\t]*[一-鿿A-Za-zぁ-ヺ][^\t]*)\t+((?:19|20)\d{2}\s*[年./\-]\s*\d{1,2}\s*月?)\t+((?:19|20)\d{2}\s*[年./\-]\s*\d{1,2}\s*月?|現在|至今|今|在学中|在職中)(.*)$", l)
        if msf and not re.search(r"(?:19|20)\d{2}", msf.group(1)):
            l = msf.group(2) + "-" + msf.group(3) + "\t" + msf.group(1) + msf.group(4)
        l = re.sub(r"^(?:搜索同事|查看同事)\s*", "", l)
        l = re.sub(r"^[(（]\s*((?:19|20)\d{2}\s*[年./\-]\s*\d{1,2}\s*月?\s*[-~～–—―至]+\s*(?:(?:19|20)\d{2}\s*[年./\-]\s*\d{1,2}\s*月?|至今|现在|現在|今))\s*[)）]$", r"\1", l)
        mnf = re.match(r"^([^\n]{2,80}?)\t+((?:19|20)\d{2}\s*[年./\-]\s*\d{1,2}\s*月?\s*[-~～–—―至]+\s*(?:(?:19|20)\d{2}\s*[年./\-]\s*\d{1,2}\s*月?|至今|现在|現在|今))\s*(?:[(（][^)）]{1,12}[)）])?\s*$", l)
        if mnf and not re.match(r"^(?:时间|期間|期间|入退社年月)", mnf.group(1)) and not re.search(r"(?:19|20)\d{2}\s*[年./\-]\s*\d", mnf.group(1)):
            l = mnf.group(2) + "\t" + mnf.group(1).strip()
        mpr = re.match(r"^([^\t(（\d]{2,40}?)\s*[(（]\s*((?:19|20)\d{2}\s*[年./\-]\s*\d{1,2}\s*月?\s*[-~～–—―至]+\s*(?:(?:19|20)\d{2}\s*[年./\-]\s*\d{1,2}\s*月?|至今|现在|現在|今))\s*[)）]\s*(.*)$", l)
        if mpr:
            l = mpr.group(2) + "\t" + mpr.group(1) + ("\t" + mpr.group(3) if mpr.group(3) else "")
        mcf = COMPANY_FIRST.match(l)
        if mcf and RANGE_RE.match(mcf.group(3)):
            mr = RANGE_RE.match(mcf.group(3))
            l = mcf.group(3)[:mr.start(4)] + "\t" + mcf.group(1) + "\t" + mr.group(4) + " " + mcf.group(2).strip()
        segs = [l]
        if len(l) > 80 or len(re.findall(r"(?:19|20)\d{2}\s*[年./]\s*\d{1,2}\s*月?\s*(?:[-~～–—―‐−〜]|から)", l)) >= 2:
            segs = [x.strip() for x in LONG_SPLIT.split(l) if x and x.strip()]
        for sg in segs:
            for x in explode(sg):
                if x.strip():
                    out.append(x.strip())
    # “期間：2011/11~今”后 1~2 行是“会社名：X” → 先调成“会社名”在前
    # EN: "期間：2011/11~今" followed 1-2 lines later by "会社名：X" → reorder so "会社名" comes first
    # JA: 「期間：2011/11~今」の 1〜2 行後に「会社名：X」がある → 「会社名」が先になるよう並べ替える
    for i in range(len(out) - 1):
        mp = re.match(r"^(?:入退社年月|在籍期間|勤務期間|期\s*間|时间|工作时间|在职时间)\s*[:：]\s*(.+)$", out[i])
        if mp and RANGE_RE.match(mp.group(1)):
            for j in (i + 1, i + 2):
                if j < len(out) and re.match(r"^(?:会社名|社名|公司名称|公司|学校名称|学校)\s*[:：]\s*\S", out[j]):
                    out[i], out[j] = out[j], out[i]
                    break
    # 单独一行的日期区间，下一行才是学校/公司 → 合并
    # EN: A date range on its own line, with the school/company on the next line → merge
    # JA: 単独の行の期間で、次の行が学校・会社 → 結合する
    merged = []
    i = 0
    while i < len(out):
        mr = RANGE_RE.match(out[i])
        if mr and not mr.group(4).strip() and i + 2 < len(out) and re.match(r"^公司描述\s*[:：]?\s*$", out[i + 1]) and len(out[i + 2]) <= 50:
            merged.append(out[i].rstrip() + "\t" + out[i + 2])  # 猎聘 PDF：“2013.01-2015.06 / 公司描述： / 公司名 / 描述…”
            # EN: Liepin PDF: "2013.01-2015.06 / 公司描述： (company description:) / company name / description…"
            # JA: Liepin の PDF：「2013.01-2015.06 / 公司描述：（会社の説明：）/ 会社名 / 説明…」
            i += 3
            continue
        if mr and not mr.group(4).strip():
            jn = next((j for j in range(i + 1, min(i + 4, len(out))) if re.match(r"^(?:会社名|社名|公司名称|学校名称|项目名称)\s*[:：]\s*\S", out[j])), None)
            if jn is not None and not any(RANGE_RE.match(out[k]) for k in range(i + 1, jn)):
                val = re.sub(r"^[^:：]+[:：]\s*", "", out[jn])
                merged.append(out[i].rstrip() + "\t" + val)
                merged += [out[k] for k in range(i + 1, jn)]
                i = jn + 1
                continue
        if mr and not mr.group(4).strip() and merged and (i + 1 >= len(out) or re.match(r"^[^:：]{1,10}[:：]", out[i + 1]) or SECTION_RE.match(out[i + 1])) \
                and len(merged[-1]) <= 60 and not RANGE_RE.match(merged[-1]) and not SECTION_RE.match(merged[-1]) \
                and not re.match(r"^[^:：]{1,10}[:：]", merged[-1]) and (SCHOOL_HINT.search(merged[-1]) or ORG_HINT.search(merged[-1])) \
                and not (i + 1 < len(out) and re.match(r"^公司描述\s*[:：]?\s*$", out[i + 1])):
            merged[-1] = out[i].rstrip() + "\t" + merged[-1]  # 猎聘：学校/公司一行，下一行才是“2003.09-2007.06”
            # EN: Liepin: school/company on one line, "2003.09-2007.06" on the next
            # JA: Liepin：学校・会社が 1 行にあり、次の行に「2003.09-2007.06」
            i += 1
            continue
        if mr and not mr.group(4).strip() and i + 1 < len(out) and not RANGE_RE.match(out[i + 1]) and not EVENT_RE.match(out[i + 1]) \
                and not SECTION_RE.match(out[i + 1]) and not re.match(r"^[^:：]{1,10}[:：]", out[i + 1]) and len(out[i + 1]) <= 80:
            merged.append(out[i].rstrip() + "\t" + out[i + 1])
            i += 2
            continue
        merged.append(out[i])
        i += 1
    out = merged
    # “会社名：X”后 1~3 行内有“入退社年月：2003年1月~2006年8月” → 合成区间行“2003年1月~2006年8月 X”
    # EN: "会社名：X" followed within 1-3 lines by "入退社年月：2003年1月~2006年8月" → synthesise the range line "2003年1月~2006年8月 X"
    # JA: 「会社名：X」の後 1〜3 行以内に「入退社年月：2003年1月~2006年8月」がある → 期間の行「2003年1月~2006年8月 X」を合成する
    res = []
    skip = set()
    for i, l in enumerate(out):
        if i in skip:
            continue
        mc = re.match(r"^(?:会社名|社名|公司名称|项目名称|学校名称|公司|学校)\s*[:：]\s*(.+)$", l)
        if mc:
            for j in range(i + 1, min(i + 7, len(out))):
                if re.match(r"^(?:会社名|社名|公司名称|项目名称|学校名称|公司|学校)\s*[:：]", out[j]):
                    break
                mp = re.match(r"^(?:入退社年月|在籍期間|勤務期間|期\s*間|工作时间|在职时间|任职时间|项目时期|项目时间|就读时间|时间段|时间)\s*[:：]\s*(.+)$", out[j])
                if mp and RANGE_RE.match(mp.group(1)):
                    res.append(mp.group(1) + "\t" + mc.group(1))
                    res += [out[k] for k in range(i + 1, j)]
                    skip.add(j)
                    break
            else:
                res.append(l)
            continue
        res.append(l)
    return res


def base_info(lines, joined, contact_lines=None):
    b = {k: "" for k in C.BASE_FIELDS}
    b["platform_from"] = "个人简历"
    name = ""
    m = re.search(r"姓\s*[（(]?漢字[)）]?\s*[:：]\s*(\S+)\s+名\s*[（(]?漢字[)）]?\s*[:：]\s*(\S+)", joined)
    if m:
        name = m.group(1) + m.group(2)
    fulljoined = "\n".join(contact_lines) if contact_lines else joined
    for src in (joined, fulljoined):
        if name:
            break
        for m in re.finditer(r"(?:氏\s*名|名\s*前|姓\s*名)(?:\s*/\s*(?:氏名|姓名))?(?:\s*(?:カタカナ|ふりがな|フリガナ))?\s*[:：]?\s*(?:[(（]漢字[)）]\s*)?(?:[ァ-ヺー・ ]+[\t ]*(?=[一-鿿(（])|[ァ-ヺー・ ]+\t)?[(（]?"
                             r"([一-鿿々]{1,4}(?:[ \t]{1,3}[一-鿿々]{1,3}){0,3}|[A-Za-z][A-Za-z .]{2,30}?)(?=\s|$|\(|（|\)|）|性|生年)", src):
            v = m.group(1)
            if re.search(r"[一-鿿]", v):
                parts = re.split(r"[ \t]+", v)
                keep = []
                for x in parts:
                    if keep and (re.match(r"^(年齢|性別|性别|生年|民族|戸籍|户籍|户口|籍贯|現?住所|学歴|学历|学位|专业|婚姻|国籍|身長|身高|出身|出生|本籍|政治|电话|手机|年龄)", x)
                                 or x in ("年", "性", "男", "女", "学", "民", "籍", "出", "电", "手")
                                 or len("".join(keep)) >= 4 or (len("".join(keep)) >= 2 and len(x) >= 2)):
                        break
                    keep.append(x)
                v = "".join(keep)
            else:
                v = v.strip()
            if C.name_quality(v)[0] == "valid" and not re.search(r"(性別|生年|月日|戸籍|ふりがな|フリガナ|氏名|名前|姓名|学歴|現住所|写真|本籍)", v):
                name = v
                break
    if not name:
        mnm = re.search(r"(?:^|\n)\s*Name\s*[:：]\s*([A-Za-z][A-Za-z .\-]{2,40}?)\s*(?:\t|\n|$)", fulljoined)
        if mnm and C.name_quality(mnm.group(1).strip())[0] == "valid":
            name = mnm.group(1).strip()
    if not name:
        # “张三 手机：13800000017 男 37岁”“李四流程状态”——姓名紧跟“手机/电话”或“男/女 xx岁”
        # EN: "张三 手机：13800000017 男 37岁" / "李四流程状态" — the name is immediately followed by "手机/电话" (mobile/phone) or "男/女 xx岁" (gender, age)
        # JA: 「张三 手机：13800000017 男 37岁」「李四流程状态」— 氏名のすぐ後に「手机／电话」（携帯・電話）か「男／女 xx岁」（性別・年齢）が続く
        fj = "\n".join(contact_lines or lines)
        for mnp in re.finditer(r"(?<![一-鿿])([一-鿿]{2,4})\s*(?:(?:手\s*机|电\s*话|联系电话|移动电话)\s*[:：]|[\t ]+(?:男|女)[\t ]*[\d（(|｜])", fj[:3000]):
            cand = mnp.group(1)
            if C.name_quality(cand)[0] == "valid" and not re.search(r"(先生|女士|小姐|简历|姓名|联系|个人|信息|基本|方式)", cand):
                name = cand
                break
    if not name:
        # 智联式：姓名单独一行，下一行“女 23岁(1994年3月)…”；或“刘川江 手机：…”
        # EN: Zhaopin style: the name on its own line, with "女 23岁(1994年3月)…" on the next; or "<name> 手机：…"
        # JA: Zhaopin 式：氏名が単独の行にあり、次の行が「女 23岁(1994年3月)…」。または「<氏名> 手机：…」
        cl = contact_lines or lines
        for i, l in enumerate(cl[:60]):
            t = re.sub(r"[\s:：]+$", "", l.strip())
            nxt = cl[i + 1].strip() if i + 1 < len(cl) else ""
            m1 = re.fullmatch(r"([一-鿿]{2,4})", t)
            m2 = re.match(r"^([一-鿿]{2,4})\s+(?:手机|电话|Tel|TEL)\s*[:：]", t)
            cand = (m1.group(1) if m1 and re.match(r"^(男|女)\s", nxt) else "") or (m2.group(1) if m2 else "")
            if cand and C.name_quality(cand)[0] == "valid" and not re.search(r"(先生|女士|小姐)$", cand):
                name = cand
                break
    if not name:
        # 首行即姓名（“楽艶 （らくえん） 女 | 中国/上海”“劉暁慧 生年月日：…”）
        # EN: The first line is the name ("<name> （<reading>） 女 | 中国/上海", "<name> 生年月日：…")
        # JA: 1 行目が氏名（「<氏名> （<読み>） 女 | 中国/上海」「<氏名> 生年月日：…」）
        for l in (contact_lines or lines)[:4]:
            l = re.sub(r"(?:的)?(?:个人简历|简历|履历|個人履歴書|履歴書)\s*$", "", l.lstrip("\ufeff").strip())
            msp = re.match(r"^([一-鿿]{1,2})[ \t]{1,3}([一-鿿]{1,2})(?=\s|$|[(（|｜]|[A-Za-z])", l.strip())
            tok = (msp.group(1) + msp.group(2)) if msp else re.split(r"[\s\t(（|｜,，]", l.strip())[0]
            if re.fullmatch(r"[一-鿿]{2,4}", tok) and C.name_quality(tok)[0] == "valid" and not SCHOOL_HINT.search(tok) \
                    and not re.search(r"(履歴|簡歴|简历|個人|个人|職務|経歴|情報)", tok):
                name = tok
                break
    if re.fullmatch(r"[一-鿿]{2,3}[男女]", name or "") and re.search(re.escape(name[:-1]) + r"\s*[\t ]", fulljoined):
        name = name[:-1]
    if name and (C.name_quality(name)[0] != "valid" or re.search(r"(氏名|名前|姓名|性別|学歴|住所|写真|戸籍|生年)", name)):
        name = ""
    b["full_name"] = name
    mg = re.search(r"性\s*[別别]\s*[:：]?\s*\t?\s*(男|女)(?!\s*・)", fulljoined) or \
        re.search(r"(?<![一-鿿])(男|女)\s*[·|｜\t ,，]\s*\d{2}\s*岁", fulljoined) or re.search(r"(?<![一-鿿])(男|女)性(?![一-鿿])", joined) or \
        re.search(r"^[一-鿿]{2,4}\s*(?:[(（][^)）]{1,12}[)）])?\s*(男|女)\s*[|｜\t]", fulljoined[:300], re.M)
    if mg:
        b["gender"] = mg.group(1)
    mb = next((x for x in re.finditer(YEAR + r"\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日", joined[:1500])
               if 1940 <= year_of(x.group(1)) <= 2010), None) or re.search(r"(?:生年月日|出生年月日?|出生日期|誕生日|生\s*日)\s*[:：]?\s*\t?\s*((?:19|20)\d{2})\s*[./\-年]\s*(\d{1,2})(?:\s*[./\-月]\s*(\d{1,2}))?", joined)
    if not mb:
        mb = re.search(r"(?:生年月日|出生年月|出生日期|誕生日|生\s*日)[^\n]{0,12}?((?:19|20)\d{2})\s*[./\-年]\s*(\d{1,2})()", joined)
    if mb:
        yy = year_of(mb.group(1))
        if 1940 <= yy <= 2010:
            b["birth_year"] = str(yy)
            b["birth_date"] = f"{yy:04d}年{int(mb.group(2)):02d}月{int(mb.group(3) or 1):02d}日"
    ma = re.search(r"満\s*(\d{2})\s*歳|(\d{2})\s*歳", joined)
    if ma:
        b["age"] = ma.group(1) or ma.group(2)
    mad = re.search(r"(?:現\s*住\s*所|现\s*居\s*住?\s*地|现\s*住\s*址|居\s*住\s*地)\s*[:：]?\s*\t?\s*(?:〒\s*[\d\-]*\s*\t?\s*)?([^\t\n〒]{2,60}?)(?=\t|\n|電話|TEL|$)", joined)
    if mad and not re.search(r"(市外局番|電話|TEL|携帯|〒|郵便)", mad.group(1)):
        b["address"] = mad.group(1).strip()
        mc = re.match(r"^(北京|上海|天津|重慶|重庆|[一-鿿]{2,3}?[市省])", b["address"])
        b["city"] = (mc.group(1) + ("" if mc.group(1).endswith(("市", "省")) else "市")) if mc else ""
    mh = re.search(r"(?:戸\s*籍|本\s*籍|出\s*身\s*地|户\s*籍|户\s*口|籍\s*贯)\s*[:：]?\s*\t?\s*([一-鿿]{2,10})", joined)
    b["household_registration"] = mh.group(1) if mh else ""
    mm = re.search(r"(?:婚\s*姻(?:状[況况])?|配偶者)\s*[:：]?\s*\t?\s*(既婚|已婚|未婚|有り|有|無し|無|离异|離婚)", joined)
    if mm:
        b["marital_status"] = {"既婚": "已婚", "已婚": "已婚", "有": "已婚", "有り": "已婚", "未婚": "未婚", "無": "未婚", "無し": "未婚",
                               "離婚": "离异", "离异": "离异"}[mm.group(1)]
    mn = re.search(r"国\s*籍\s*[:：]?\s*\t?\s*([一-鿿]{2,6})", joined)
    b["nationality"] = mn.group(1) if mn else ""
    ms, es = [], []
    for l in (contact_lines or lines):
        if re.search(r"(TEL|FAX|www\.|紐培|纽培|ヒューマン|コンサル|担当者|会社住所)", l, re.I):
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
    b["phone"], b["email"] = "; ".join(ms), "; ".join(es)
    mex = re.search(r"(?:期望薪资|期望月薪|期望薪水|期望年薪|希望月収|希望給与|希望給料)\s*[:：]?\s*\t?\s*([^\t\n]{2,40})", joined)
    b["_expected_salary"] = mex.group(1).strip() if mex else ""
    return b


def deg_of(s: str):
    for k, r in DEG_MAP:
        if k in s:
            return k, r
    return "", ""


def edu_item(start, end, text):
    e = CN.empty("education_list")
    e["school_start_ym"], e["school_end_ym"] = start, end
    text = re.sub(r"[。.]\s*$", "", text.strip())
    text = re.sub(r"\s*[にを]$", "", EDU_END.sub("", text).strip()).strip()
    msent = re.match(r"^[:：\s]*([^\s:：、。]{3,30}?(?:大学院|大学|学院|学校|高校|中学|専門学院|短大))(?:で|にて|に)(?:.*)$", text)
    if msent:
        text = msent.group(1)
    if re.search(r"(。|ため|旅行|です|ます|ました)", text) or re.match(r"^[^\t ]*(勉強|留学)", text):
        return None
    text = re.sub(r"(?:で|を)勉強(?:する|した)?\s*$", "", text).strip()
    toks = [x for x in re.split(r"\t+|\s+", text) if x]
    deg, rank = "", ""
    rest = []
    for t in toks:
        d, r = deg_of(t)
        if d and not SCHOOL_HINT.search(t.replace(d, "")) and len(t) <= 8 and not deg and not re.search(r"(です|。|、)", t):
            deg, rank = t, r
        elif re.fullmatch(r"(上海|北京|天津|大連|大连|日本|東京|大阪|[一-鿿]{2}市)", t) and rest:
            continue  # 场所列
            # EN: Place column
            # JA: 場所の列
        else:
            rest.append(t)
    if not rest:
        return None
    # 学校名：第一个含学校字样的词；其后为专业
    # EN: School name: the first word containing school characters; what follows is the major
    # JA: 学校名：学校を示す字を含む最初の語。その後が専攻
    si = next((i for i, t in enumerate(rest) if SCHOOL_HINT.search(t)), 0)
    school = rest[si]
    # 学校后面单独的“大学”“大学院”“専門学校”是学历栏
    # EN: A standalone "大学" "大学院" "専門学校" after the school is the degree column
    # JA: 学校の後にある単独の「大学」「大学院」「専門学校」は学歴の欄
    generic = {"大学": ("大学", "4"), "大学院": ("大学院", "5"), "短大": ("短大", "3"), "専門学校": ("専門学校", "3"), "高校": ("高校", "2"),
               "短期大学": ("短期大学", "3"), "高等学校": ("高等学校", "2"), "大学本科": ("大学本科", "4")}
    tail = [t for t in rest[si + 1:]]
    if tail and tail[-1] in generic and len(tail) >= 1:
        if not deg:
            deg, rank = generic[tail[-1]]
        rest = rest[:si + 1] + tail[:-1]
    m = re.match(r"^(.*?(?:大学院|高等学校|中学校|小学校|専門学校|大学|学院|学校|高校|中学|短大))(.+)$", school)
    major = " ".join(rest[si + 1:])
    if m and not major and not m.group(2).startswith("校"):
        school, major = m.group(1), m.group(2)
    if re.fullmatch(r"[^\s]{2,14}(学院|学部|研究科)", major.strip()) and re.search(r"大学", school):
        school, major = school + major.strip(), ""
    mpar = re.match(r"^([(（][^)）]{1,8}[)）])\s*(.*)$", major.strip())
    if mpar and mpar.group(2):
        school, major = school + mpar.group(1), mpar.group(2)
    if re.fullmatch(r"[(（][^)）]{1,10}[)）]", major.strip()):
        school, major = school + major.strip(), ""
    if re.fullmatch(r"(School|University|College|大学|学校|学校名|高校|大学院|学院)", school, re.I):
        return None
    e["school_name"] = school
    e["school_major_name"] = re.sub(r"^(専攻|专业)\s*[:：]?", "", major).strip()
    if not deg:
        d, r = deg_of(school + " " + major)
        if d:
            deg, rank = d, r
        elif "大学" in school:
            rank = "4"
    e["school_degree_type"] = deg
    e["school_degree_rank"] = rank
    return e


DUR_TOK = re.compile(r"^[(（]?\s*[一二三四五六七八九十\d]+\s*(?:ヶ月|か月|カ月|个月|年間?|years?|months?)\s*[;；]?\s*[)）]?$|^[(（]?\s*(?:\d+\s*年)?\s*(?:\d+\s*(?:个|ヶ|か|カ|ケ)?月)?\s*[)）]?$|^[(（]\s*\d+\s*年\s*[)）]$")


POS_ONLY = re.compile(r"(担当|主管|部長|課長|係長|主任|助理|マネージャー|エンジニア|スタッフ|アシスタント|通訳|翻訳|秘書|リーダー|責任者|社員|店員|職員|"
                      r"经理|专员|工程师|研究员|技术员|实习生|科长|课长|部长|处长|厂长|代表|顾问|总监|督导|采购|客服|文员|会计|出纳|销售|设计师|翻译|组长|主管|员|"
                      r"\bSE|\bPM|\bPL|Engineer|Manager|Assistant|Specialist|Leader|[^司]管理)(\s*[(（][^)）]*[)）])?$")
SCHOOL_OK = re.compile(r"(カレッジ|学園|専門学校|附中|大学|学院|学校|分校|大専|短大|大学院|高校|高等学校|中学|小学|中专|专科|研究科|学部|University|College|Institute|School|Academy)", re.I)
TRAIN_HINT = re.compile(r"(培训|认证|研修|講習|课程|セミナー)")


EVENT_RANGE_RE = re.compile(r"^" + YEAR + r"\s*[年./\t ]\s*(\d{1,2})\s*[-~～]\s*(\d{1,2})\s*月?\s*[\t ]\s*(.+)$")


MARK_MID = re.compile(r"^(.+?)\s*(入学|入校|卒業|修了|中退|入社|入職|退社|退職|開始|バイト終了|終了)\s*(?:[(（]([^)）]{1,30})[)）])?\s*(.*)$")


def norm_event(rest: str):
    """“南昌大学 材料科学工程入学(中国江西省)”“X 入社 担当：…”→ 标记移到末尾，后面的说明另存。

    EN: "南昌大学 材料科学工程入学(中国江西省)", "X 入社 担当：…" → move the marker to the end and store the notes after it separately.

    JA: 「南昌大学 材料科学工程入学(中国江西省)」「X 入社 担当：…」→ 印を末尾に移し、その後の説明は別に保存する。
    """
    m = MARK_MID.match(rest)
    if not m or (not m.group(3) and not m.group(4)):
        return rest, ""
    head, mark, par, tail = m.group(1).strip(), m.group(2), m.group(3), m.group(4).strip()
    if par and mark in ("入社", "入職"):
        head = head + " (" + par + ")"
    elif par and mark not in ("入学", "入校", "卒業", "修了", "中退"):
        head = head + " " + par
    if tail and len(tail) <= 15 and not re.search(r"[:：]", tail) and mark in ("入学", "入校", "卒業", "修了"):
        head, tail = head + " " + tail, ""
    return head + " " + mark, tail


def work_item(start, end, text):
    w = CN.empty("work_experiences")
    w["position_start"], w["position_resigned"] = start, end
    w["status"] = "在职" if end == "至今" else ("离职" if end else "")
    text = WORK_END.sub("", text).strip()
    text = re.sub(r"\s*(?:に|を|として)$", "", text)
    msal = re.search(r"\s*(\d+(?:\.\d+)?\s*(?:[kK千万])?\s*元\s*/\s*月)\s*$", text)
    if msal:
        w["position_salary"], text = msal.group(1), text[:msal.start()]
    text = re.sub(r"^[,，、;；|｜:：\s]+", "", text)
    toks = [x for x in re.split(r"\t+|\s{2,}|\s*[|｜]\s*", text) if x and not DUR_TOK.match(x)]
    comp = toks[0] if toks else ""
    # 会社名后粘了职位（“豊島国際有限会社 営業担当”）
    # EN: A position stuck after the company name ("豊島国際有限会社 営業担当")
    # JA: 会社名の後ろに職位がくっついている（「豊島国際有限会社 営業担当」）
    mc = re.match(r"^(.*?(?:有限会社|株式会社|有限公司|公司|会社|集団|集团|Co\.,?\s*Ltd\.?|Ltd\.?|Inc\.?))\s+(.+)$", comp)
    if mc:
        comp, toks = mc.group(1), [mc.group(1), mc.group(2)] + toks[1:]
    comp = re.sub(r"^(?:迄|まで|至)\s*[:：]\s*", "", comp.strip())
    comp = re.sub(r"\s*[(（]\s*(?:\d+\s*年)?\s*(?:\d+\s*(?:个|ヶ|か|カ)?月)?\s*[)）]\s*$", "", comp)
    comp = re.sub(r"\s*[(（]\s*部下\s*[:：]?\s*[^)）]{1,8}[)）]", "", comp)
    mem = re.search(r"\s*[(（]\s*(?:(?:社員数|従業員数?|全社員|人数)\s*[:：]?\s*([^)）]{1,15})|(\d+\s*[-~～]\s*\d+\s*人|\d+\s*人以[上下]|少于\s*\d+\s*人))[)）]\s*$", comp)
    if mem:
        w["company_employees"], comp = (mem.group(1) or mem.group(2)).strip(), comp[:mem.start()]
    comp = re.sub(r"\s*[(（](日系|外資系?|民営|国営|独資|合資|個人経営|欧米系|台湾系|香港系|国有|中外合資|合弁)[)）]\s*$", "", comp.strip())
    w["company_name"] = comp.strip()
    rest = [t for t in toks[1:] if not NATURE_TOK.match(t) and not DUR_TOK.match(t.strip())]
    # 第一个是职位、后面才是公司（“営業担当 XX有限公司”）
    # EN: The first is the position and the company comes after ("営業担当 XX有限公司")
    # JA: 最初が職位で、後ろが会社（「営業担当 XX有限公司」）
    if rest and not ORG_HINT.search(comp) and ORG_HINT.search(rest[0]) and len(comp) <= 20:
        comp, rest = rest[0], [comp] + rest[1:]
        w["company_name"] = comp.strip()
    if re.search(r"(。|です|ます|ました|ため|として|をやり|を担当|都合|により|退社|退職|希望)", w["company_name"]) or len(w["company_name"]) > 50 \
            or not re.search(r"[一-鿿A-Za-zァ-ヺ]", w["company_name"]) or SCHOOL_HINT.search(w["company_name"]) and not ORG_HINT.search(w["company_name"]):
        w["company_name"] = ""
    for t in rest:
        if re.search(r"(\d+\s*人|人ぐらい|従業員)", t):
            w["company_employees"] = t
        elif re.fullmatch(r"(日系|外資系?|民営|国営|独資|合資|個人経営|欧米系|台湾系|香港系|国有)", t):
            continue
        elif re.fullmatch(r"(上海|北京|大連|大连|蘇州|苏州|[一-鿿]{2}市|日本)", t):
            continue
        elif re.fullmatch(r"[一-鿿（）()]{2,12}(?:/[一-鿿（）()]{2,12})+", t) and not POS_ONLY.search(t):
            w["company_industry"] = w["company_industry"] or t  # “电子技术/半导体/集成电路”
            # EN: "电子技术/半导体/集成电路" (electronics / semiconductors / integrated circuits)
            # JA: 「电子技术/半导体/集成电路」（電子技術・半導体・集積回路）
        elif not w["position"] and re.search(r"[一-鿿A-Za-zぁ-ヺ]", t):
            w["position"] = t
    if re.search(r"(事業部|部|課|室|センター|本部)$", w["position"]) and not re.search(r"(長|担当|員|者|師)", w["position"]):
        w["position_dept"], w["position"] = w["position"], ""
    w["employment_type"] = "全职"
    return w


WK_LABELS = {
    "dept": ["所在部门", "配属部門", "所属部門", "所属部署", "部署", "部門", "部门"],
    "report": ["汇报对象", "直属上司(職位)", "直属上司", "上司"],
    "pos": ["担当职务", "职位名称", "职务", "岗位", "職位・報酬", "所属部署/職位", "所属/職位", "部署/役職", "部门/职位", "部署/職位", "部門/職位", "本人職位", "職位", "役職", "職種", "ポジション", "职位"],
    "sal": ["薪酬状况", "月薪", "薪资"],
    "resp": ["职责业绩", "工作职责和业绩", "职位内容", "职责内容", "工作描述", "工作职责", "业务内容", "主要职责", "职责描述", "職務概要", "職務内容", "業務", "業務内容", "仕事内容", "工作内容", "担当業務", "担当", "主な業務", "内容"],
    "ach": ["工作业绩", "主要业绩", "业绩", "実績", "業績", "成果"],
    "ind": ["行业/事业内容", "所在行业", "所属行业", "公司行业", "行业", "会社業務", "業種", "事業内容", "事業概要", "会社概要", "業界"],
    "emp": ["公司规模", "従業人数", "従業員数", "従業員", "社員数", "規模"],
    "reason": ["换职原因", "转职理由", "离职理由", "転職理由", "退職理由", "離職原因", "離職理由", "离职理由", "退社理由", "离职原因"],
    "sub": ["下属人数", "部下"],
    "skip": ["专业", "学历", "学位", "性质", "公司性质", "工作地点", "所在地区", "公司性質", "企業性質", "会社性質", "会社住所", "所在地", "勤務地", "働く場所", "会社製品", "公司产品", "主要お客様", "主要な客先", "主要客户",
             "資本", "資本金", "場所", "売上", "売上高", "設立", "専攻", "専門"],
}
ALL_WK = [x for v in WK_LABELS.values() for x in v]
ALL_WK.sort(key=len, reverse=True)
LABELS = sorted(set(LABELS + ALL_WK + ["会社規模", "勤務開始日", "職種", "住所"]) - {"内容", "担当", "業務", "場所", "規模", "資本"}, key=len, reverse=True)
LABELS += ["業務"]
LABEL_ROW = re.compile(r"^(" + "|".join(re.escape(x) for x in LABELS) + r")$")


INLINE_LAB = re.compile(r"(?:^|\s+)(?=(?:" + "|".join(re.escape(x) for x in ALL_WK) + r")\s*[:：])")
COMPANY_FIRST = re.compile(r"^(?:会社|社名|会社名|公司|公司名称|勤務先)[^:：\t]{0,12}[:：]\s*(\S+)(.*?)(?:期[间間]|在籍期間|勤務期間)\s*[:：]\s*(.+)$")


def attach_details(item, lines, kind):
    """条目后的“所属部門/職位/業種/業務内容/職務内容/退職理由”等行。

    EN: Lines after an entry such as "所属部門/職位/業種/業務内容/職務内容/退職理由".

    JA: 項目の後にある「所属部門／職位／業種／業務内容／職務内容／退職理由」などの行。
    """
    lines = [x for x in lines if not (re.fullmatch(r"[^:：]{1,8}[:：]\s*", x) and re.sub(r"[:：\s]", "", x) not in ALL_WK)]
    lab, pre = CN.take_label_blocks(lines, [re.escape(x) for x in ALL_WK])
    first = lambda v: re.sub(r"^[:：\s]+", "", re.split(r"\t|\n", v or "")[0]).strip()  # noqa: E731

    # 单值标签（職位/部署/規模等）后面跟着的多行，是职责描述
    # EN: The lines following a single-value label (職位/部署/規模 etc.) are the duty description
    # JA: 単一の値のラベル（職位・部署・規模など）の後に続く複数の行は職務の説明
    spill = []
    for g in ("pos", "dept", "emp", "sub", "ind", "skip", "report", "sal"):
        for k in WK_LABELS[g]:
            v = lab.get(k)
            if v and "\n" in v:
                head, more = v.split("\n", 1)
                lab[k] = head
                spill.append(more.strip())

    def get(group, one=False):
        for k in WK_LABELS[group]:
            if lab.get(k):
                return first(lab[k]) if one else lab[k].strip()
        return ""
    if kind == "work":
        item["position_dept"] = item["position_dept"] or get("dept", True)
        pos = get("pos", True)
        tanto = get("resp")
        t2 = (lab.get("担当業務") or lab.get("担当") or "").strip()
        if not pos and not item["position"] and t2 and t2 == tanto and "\n" not in tanto and len(tanto) <= 25:
            pos, tanto = tanto, ""
        item["position"] = pos or item["position"]
        if re.search(r"(事業部|部|課|科|室|センター|本部)$", item["position"]) and not re.search(r"(長|担当|員|者|師)", item["position"]) \
                and not item["position_dept"]:
            item["position_dept"], item["position"] = item["position"], ""
        item["position_report_to"] = get("report", True)
        sub = get("sub", True)
        item["position_subordinate"] = sub if re.search(r"\d", sub) else ""
        item["company_industry"] = get("ind", True)
        item["company_employees"] = item["company_employees"] or get("emp", True)
        extra = [x for x in pre if not re.match(r"^[\d\s年月]+$", x)]
        item["position_salary"] = item["position_salary"] or get("sal", True)
        # 猎聘：公司行下一行单独是职位（“硬件工程师”“FAE 现场应用工程师”）
        # EN: Liepin: the line after the company line is the position on its own ("硬件工程师" (hardware engineer), "FAE 现场应用工程师" (field application engineer))
        # JA: Liepin：会社の行の次の行が単独の職位（「硬件工程师」（ハードウェアエンジニア）「FAE 现场应用工程师」（フィールドアプリケーションエンジニア））
        if extra and not item["position"] and len(extra[0]) <= 25 and not re.search(r"[。，,;；:：|｜]", extra[0]) and POS_ONLY.search(extra[0]):
            item["position"], extra = extra[0].strip(), extra[1:]
        # 智联导出：条目下第一行“客户经理 | 6001-8000元/月”，第二行“银行”（行业）
        # EN: Zhaopin export: the first line under an entry "客户经理 | 6001-8000元/月" (account manager | salary), the second line "银行" (bank, the industry)
        # JA: Zhaopin のエクスポート：項目の下の 1 行目「客户经理 | 6001-8000元/月」（顧客担当マネージャー｜給与）、2 行目「银行」（銀行、業界）
        if extra and not item["position"]:
            parts = [x.strip() for x in re.split(r"\s*[|｜]\s*", extra[0])]
            NAT = r"(独资|民营|私营|国企|国有|合资|外资|外企|上市|事业单位|政府|企业性质|公司性质|\d+\s*[-~]\s*\d+\s*人|\d+人以[上下]|少于\d+人)"
            if len(parts) >= 2 and any(re.search(NAT, x) for x in parts):
                # 猎聘“外商独资·外企办事处 | 制药/生物工程 | 1000-2000人”：公司信息行，不是职位
                # EN: Liepin "外商独资·外企办事处 | 制药/生物工程 | 1000-2000人" (wholly foreign-owned · foreign representative office | pharma/biotech | 1000-2000 people): a company-info line, not a position
                # JA: Liepin の「外商独资·外企办事处 | 制药/生物工程 | 1000-2000人」（外資独資・外資の事務所｜製薬・バイオ｜1000〜2000 人）：会社情報の行であり職位ではない
                ind = [x for x in parts if x and not re.search(NAT, x)]
                if ind and not item["company_industry"]:
                    item["company_industry"] = ind[0]
                emp = [x for x in parts if re.search(r"\d+\s*[-~]\s*\d+\s*人|\d+人以[上下]|少于\d+人", x)]
                if emp and not item["company_employees"]:
                    item["company_employees"] = emp[0]
                extra = extra[1:]
                parts = [x.strip() for x in re.split(r"\s*[|｜]\s*", extra[0])] if extra else []
            if len(parts) >= 2 and all(0 < len(x) <= 30 for x in parts) and not any(re.search(NAT, x) for x in parts):
                sal = [x for x in parts if re.search(r"\d.*(元|万|k|K)", x)]
                rest_p = [x for x in parts if x not in sal]
                if len(rest_p) >= 2 and re.search(r"(部|部门|课|科|室|中心)$", rest_p[0]):  # “技术部 | 软件工程师 | 2001-4000元/月”
                # EN: "技术部 | 软件工程师 | 2001-4000元/月" (technical dept | software engineer | salary)
                # JA: 「技术部 | 软件工程师 | 2001-4000元/月」（技術部｜ソフトウェアエンジニア｜給与）
                    item["position_dept"] = item["position_dept"] or rest_p[0]
                    rest_p = rest_p[1:]
                item["position"] = rest_p[0] if rest_p else ""
                if sal:
                    item["position_salary"] = sal[0]
                extra = extra[1:]
                if extra and not item["company_industry"] and len(extra[0]) <= 60:
                    ind = re.split(r"\s*[|｜]\s*", extra[0])[0].strip()
                    if ind and len(ind) <= 30 and not re.search(r"[。，,;；:：]", ind):
                        item["company_industry"], extra = ind, extra[1:]
        item["position_responsibilities"] = (tanto + ("\n" + "\n".join(extra) if extra and not tanto else "")
                                             + ("\n" + "\n".join(spill) if spill else "")).strip()
        item["position_achievements"] = get("ach")
        item["resigned_reason"] = get("reason")
    else:
        if lab.get("専攻") and not item["school_major_name"]:
            item["school_major_name"] = first(lab["専攻"])
        if lab.get("专业") and not item["school_major_name"]:
            item["school_major_name"] = first(lab["专业"])
        for k in ("学历", "学位"):
            if lab.get(k) and not item["school_degree_type"]:
                d, r = deg_of(first(lab[k]))
                item["school_degree_type"], item["school_degree_rank"] = (first(lab[k]), r) if d else (item["school_degree_type"], item["school_degree_rank"])
        # 51job 导出：学校下一行“行政管理 本科”
        # EN: 51job export: the line after the school is "行政管理 本科" (public administration, bachelor)
        # JA: 51job のエクスポート：学校の次の行が「行政管理 本科」（行政管理・学士）
        if pre and not item["school_major_name"] and len(pre[0]) <= 40 and not re.search(r"[。，,;；:：|｜]|描述|简历|经历|经验|部长|实践", pre[0]):
            toks = pre[0].split()
            if toks and deg_of(toks[-1])[0] and len(toks[-1]) <= 8:
                if not item["school_degree_type"]:
                    item["school_degree_type"], item["school_degree_rank"] = toks[-1], deg_of(toks[-1])[1]
                toks = toks[:-1]
            item["school_major_name"] = " ".join(toks)


def _mon(v):
    m = re.match(r"(\d{4})年(\d{2})月", v or "")
    return int(m.group(1)) * 12 + int(m.group(2)) if m else None


def dedupe(items, name_f, start_f):
    """同一经历在“職歴表”和“履歴行”里各出现一次：名称前 4 字相同且起始相差 ≤2 个月 → 保留信息多的那条。

    EN: The same experience appears once in the "職歴表" (work-history table) and once in the "履歴行" (history rows): if the first 4 characters of the name match and the starts differ by ≤2 months → keep the one with more information.

    JA: 同じ経歴が「職歴表」と「履歴行」にそれぞれ 1 回ずつ現れる：名前の先頭 4 文字が同じで開始が 2 か月以内の差なら → 情報の多い方を残す。
    """
    out = []
    for it in items:
        k = re.sub(r"\s", "", it[name_f])[:4]
        dup = None
        for o in out:
            a, b = _mon(o[start_f]), _mon(it[start_f])
            if re.sub(r"\s", "", o[name_f])[:4] == k and (a is None or b is None or abs(a - b) <= 2):
                dup = o
                break
        if dup is None:
            out.append(it)
            continue
        filled = lambda x: sum(1 for v in x.values() if v)  # noqa: E731
        if filled(it) > filled(dup):
            out[out.index(dup)] = it
    return out


HEADING_WORDS = re.compile(r"^(資格|免許|資格免許|資格と免許|資格・免許|免許・資格|資格·免許|資格・奨等|資格能力|資格他|資格認定|取得資格|保有資格|趣味|特技|賞罰|"
                           r"Education|Work Experience|Experience|Skills?|Certificates?|Qualifications?|Profile|所在地|戸籍|住所|学歴|職歴)$", re.I)
PUNCT_ONLY = re.compile(r"^[\s\-‐–—―:：|｜()（）\[\]【】,，.。、;；*・▪■●%0-9]*$")


def cleanup(res):
    """最后一道：去掉标签残留、纯标点、栏目标题，句子当公司名的条目丢弃，学校/专业错位修正。

    EN: The last pass: remove leftover labels, pure punctuation and section headings, discard entries with a sentence as the company name, and fix school/major misplacement.

    JA: 最後の処理：ラベルの残骸・句読点だけのもの・欄の見出しを除き、文が会社名になっている項目を捨て、学校と専攻のずれを修正する。
    """
    def strip_lab(v):
        v = re.sub(r"^[▪■●◆・\s]+", "", v or "")
        v = re.sub(r"\s*[^\s:：]{2,8}[:：]\s*$", "", v)
        return "" if PUNCT_ONLY.match(v) else v.strip()
    b = res["base_info"]
    for f in ("address", "household_registration", "city", "nationality"):
        v = re.split(r"\s*[|｜]\s*|\s+(?:户口|户籍|戸籍)\s*[:：]", b.get(f, "") or "")[0]
        v = strip_lab(v)
        if HEADING_WORDS.match(v) or re.fullmatch(r"[\d\s\-‐+()]+", v) or re.search(r"\d{3,4}-\d{7,8}", v):
            v = ""
        b[f] = v
    works = []
    for w in res["work_experiences"]:
        for f in ("company_name", "position", "position_dept", "company_industry", "company_employees"):
            w[f] = strip_lab(w.get(f, ""))
        c = w["company_name"]
        if not c or c.startswith(("【", "[")) or (("、" in c or "," in c and not re.search(r"(Co|Ltd|Inc)", c)) and not ORG_HINT.search(c)) \
                or (len(c) > 40 and not ORG_HINT.search(c[:40])) or re.search(r"(を受け|に参加|を獲得|を担当)", c):
            continue
        works.append(w)
    res["work_experiences"] = works
    for e in res["education_list"]:
        e["school_major_name"] = strip_lab(e["school_major_name"])
        e["school_degree_type"] = strip_lab(e["school_degree_type"])
        toks = e["school_major_name"].split()
        if toks and SCHOOL_OK.search(toks[-1]):
            last = toks[-1]
            if len(last) <= 6 and not re.search(r"(大学|学院)$", e["school_name"]) or last.startswith("附属"):
                e["school_name"] = e["school_name"] + last
            elif not SCHOOL_OK.search(e["school_name"]):
                e["school_name"], toks = last, [e["school_name"]] + toks
            else:
                continue
            e["school_major_name"] = " ".join(toks[:-1]).strip()
    for ex in res.get("expected_list") or []:
        ex["expected_salary"] = strip_lab(ex.get("expected_salary", ""))
    for pj in res.get("project_list") or []:
        pj["project_name"] = strip_lab(pj.get("project_name", ""))
        pj["role_name"] = strip_lab(pj.get("role_name", ""))
    for lst, f in (("certificate_list", "certificate_name"), ("training_list", "organization_name"), ("training_list", "training_name")):
        keep = []
        for c in res[lst]:
            v = re.sub(r"^[■【\[・\s]+|[】\]:：\s]+$", "", c.get(f) or "")
            if not v and lst == "training_list":
                keep.append(c)
                continue
            if HEADING_WORDS.match(v) or PUNCT_ONLY.match(v) or re.match(r"^[^:：\t]{1,10}[:：]", v) and lst == "certificate_list" and not CERT_LINE.search(v.split(":")[0].split("：")[0]):
                continue
            c[f] = v
            keep.append(c)
        res[lst] = keep


def parse(text: str):
    full = lines_of(text)
    lines = jp_segment(full)
    joined = "\n".join(lines)
    base = base_info(lines, joined, full)
    exp_salary = base.pop("_expected_salary", "")
    res = {"resume_languge": "jp", "base_info": base}
    for lst in C.LIST_FIELDS:
        res[lst] = []
    section = ""
    events = []  # (kind, date, text)
    pr_parts, certs = [], []
    cur, cur_kind, cur_body = None, "", []
    last_company = ""
    agency_parts = []
    last_year = 0

    def flush():
        nonlocal cur, cur_body
        if cur is not None and cur_kind == "proj":
            lab, pre = CN.take_label_blocks(cur_body, ["项目内容", "项目描述", "项目职责", "责任描述", "项目业绩", "所属公司", "担任角色", "项目角色", "概要", "担当", "役割", "成果"])
            cur["description"] = (lab.get("项目描述") or lab.get("项目内容") or lab.get("概要") or "\n".join(pre)).strip()
            cur["responsibilities"] = (lab.get("项目职责") or lab.get("责任描述") or lab.get("担当") or "").strip()
            cur["achievements"] = (lab.get("项目业绩") or lab.get("成果") or "").strip()
            cur["company_or_client"] = (lab.get("所属公司") or "").split("\n")[0].strip()
            cur["role_name"] = cur["role_name"] or (lab.get("担任角色") or lab.get("项目角色") or lab.get("役割") or "").split("\n")[0].strip()
            res["project_list"].append(cur)
        elif cur is not None:
            attach_details(cur, cur_body, cur_kind)
            (res["work_experiences"] if cur_kind == "work" else res["education_list"]).append(cur)
        cur, cur_body = None, []

    for l in lines:
        if section in ("skip", "agency"):
            if re.search(r"履\s*歴\s*書|氏\s*名|職務経歴書|個人情報|基本情報|名\s*前|性\s*別|生年月日", l) or RANGE_RE.match(l) or GRID_RE.match(l):
                section = ""
            elif not SECTION_RE.match(re.sub(r"^(?:\d{1,2}\s*[、.．)]\s*)", "", l)):
                if section == "agency" and not re.search(r"(TEL|FAX|希望給|上海ヒューマン|紐培|纽培)", l):
                    agency_parts.append(l)
                continue
        if re.match(r"^(記入上の注意|\d\.\s*鉛筆以外|写真をはる)", l) or re.search(r"(鉛筆以外の黒又は青|該当するものを○で囲む|数字はアラビア数字)", l):
            continue
        if l.startswith("ヒューマンコメント"):
            section = "agency"
            continue
        if re.match(r"^\d/\d$", l):
            section = "skip"
            continue
        if TABLE_HEAD.match(l):
            flush()
            continue
        mp = PR_START.match(l)
        if mp:
            flush()
            section = "pr"
            if mp.group(3).strip():
                pr_parts.append(mp.group(3).strip())
            continue
        mcs = CERT_START.match(l)
        if mcs:
            flush()
            section = "cert"
            if mcs.group(2).strip() and not re.search(r"[:：]\s*$", l):
                c = CN.empty("certificate_list")
                c["certificate_name"] = mcs.group(2).strip()
                certs.append(c)
            continue
        if re.match(r"^(履歴補充|職歴補充|その他の職歴)\s*$", l):
            flush()
            section = "work"
            continue
        if OTHER_START.match(l):
            flush()
            section = "other"
            continue
        if cur is not None and cur_kind == "work" and re.sub(r"[\s:：]", "", l) in ALL_WK:
            cur_body.append(re.sub(r"[\s:：]", "", l) + "：")  # 条目内的“職務内容”小标题
            # EN: "職務内容" sub-headings within entries
            # JA: 項目内の「職務内容」の小見出し
            continue
        ms = SECTION_RE.match(re.sub(r"^(?:(?:西暦\s*[・･]?\s*)?年\s*[(（]?(?:西暦)?[)）]?\s*月\s*|\d{1,2}\s*[、.．)]\s*|[一二三四五六七八九十]\s*[、.．]\s*)", "", l))
        if ms:
            flush()
            h = re.sub(r"\s", "", ms.group(1))
            zh_sec = ("edu" if re.match(r"(教育|学历|学习经历)", h) else "work" if re.match(r"(工作|实习|社会实践)", h)
                      else "proj" if re.match(r"(项目|在校实践)", h) else "train" if re.match(r"培训", h) else "cert" if re.search(r"(证书|荣誉|获奖)", h)
                      else "pr" if re.search(r"(评价|推荐理由|顾问意见)", h) else "skill" if re.search(r"(技能|语言)", h)
                      else "" if re.match(r"(基本信息|个人信息|个人资料)", h) else "other" if re.search(r"[一-鿿]", h) and not KANA_RE.search(h) and
                      re.match(r"(" + ZH_HEADS[:-1] + r")", h) else None)
            section = zh_sec if zh_sec is not None else ("proj" if re.search(r"プロジェクト", h) else "edu" if h in ("学歴", "教育背景", "学習経歴", "教育経歴", "学業経歴", "教育")
                       else "work" if h == "業務経歴"
                       else "skip" if h in ("家族構成",)
                       else "" if h in ("プロフィール", "基本情報", "個人情報", "履歴書") else "work" if re.match(r"[職职][歴暦]|職務|職務経歴書|職務内容|勤務経歴", h)
                       else "cert" if re.search(r"資格|免許|賞罰", h) else "pr" if re.search(r"PR|ＰＲ|紹介|志望|セールス|本人希望", h)
                       else "skill" if re.search(r"語学|スキル|PC", h) else "other")
            if h.startswith("学歴・職歴") or h == "学歴職歴":
                section = "edu"
            continue
        mr = RANGE_RE.match(l)
        mg = GRID_RE.match(l)
        if mr or mg:
            if mg:
                start, end, rest = ymd(mg.group(1), mg.group(2)), ymd(mg.group(3), mg.group(4)), mg.group(5).strip()
                cells = [x for x in rest.split("\t") if x.strip()]
                if len(cells) >= 3 and re.fullmatch(r"[一-鿿]{2,4}", cells[-1]) and not re.search(r"(大学|学院|学校|会社|公司|人|卒|科)$", cells[-1]):
                    rest = "\t".join(cells[:-1])  # 表格最后一栏“場所”
                    # EN: The last column of the table, "場所" (place)
                    # JA: 表の最後の列「場所」
            else:
                start, end, rest = ymd(mr.group(1), mr.group(2)), end_of(mr.group(3)), mr.group(4).strip()
            if not start:
                continue
            if section == "train":
                flush()
                t = CN.empty("training_list")
                t["start_ym"], t["end_ym"] = start, end
                parts = [x for x in re.split(r"\t+|\s{2,}|\s*[|｜]\s*", rest) if x.strip()]
                t["training_name"] = parts[0].strip() if parts else ""
                t["organization_name"] = parts[1].strip() if len(parts) > 1 else ""
                if t["training_name"]:
                    res["training_list"].append(t)
                continue
            if section == "proj":
                flush()
                pj = CN.empty("project_list")
                pj["start_ym"], pj["end_ym"] = start, end
                parts = [x for x in re.split(r"\t+|\s{2,}|\s*[|｜]\s*", rest) if x.strip()]
                pj["project_name"] = parts[0].strip() if parts else ""
                pj["role_name"] = parts[1].strip() if len(parts) > 1 and len(parts[1]) <= 20 else ""
                if pj["project_name"]:
                    cur, cur_kind = pj, "proj"
                continue
            if section in ("pr", "other", "skip", "skill"):
                if ORG_HINT.search(rest) and not SCHOOL_HINT.search(rest):
                    section = "work"
                elif SCHOOL_HINT.search(rest) and not ORG_HINT.search(rest) and section != "pr":
                    section = "edu"
                else:
                    if section == "pr":
                        pr_parts.append(l)
                    continue
            if section == "cert" or (re.search(r"(級|CET|TOEIC|TOEFL|JLPT|IELTS|試験|検定|(?<![A-Za-z])N[1-5](?![0-9]))", rest)
                                     and not re.search(r"(入学|卒業|有限|会社|公司)", rest) and len(rest) <= 40):
                c = CN.empty("certificate_list")
                c["certificate_time"], c["certificate_name"] = start, rest
                if rest:
                    certs.append(c)
                continue
            if section == "work" and not re.search(r"(入学|卒業|修了)\s*$", rest) and not (
                    SCHOOL_HINT.search(rest) and not ORG_HINT.search(rest) and re.search(r"(本科|硕士|博士|大专|中专|高中|学士|修士|大卒|MBA)", rest)):
                kind = "work"
            elif section == "edu" and not (ORG_HINT.search(rest) and not SCHOOL_HINT.search(rest)):
                kind = "edu"
            else:
                kind = "edu" if (SCHOOL_HINT.search(rest) and not ORG_HINT.search(rest)) else "work" if (ORG_HINT.search(rest) or section == "work") \
                    else ("edu" if section == "edu" else "work")
            tail = []
            if kind == "work":
                parts = INLINE_LAB.split(rest)
                rest, tail = parts[0].strip(), [x.strip() for x in parts[1:] if x.strip()]
                if not rest and cur is not None and cur_kind == "work" and cur.get("company_name"):
                    rest = cur["company_name"]  # 同一公司内的职位变迁“2010/01 – 2011/10 役職:… 仕事内容:…”
                    # EN: Position changes within the same company "2010/01 – 2011/10 役職:… 仕事内容:…"
                    # JA: 同じ会社での職位の変遷「2010/01 – 2011/10 役職:… 仕事内容:…」
            if kind == "work":
                rest = re.sub(r"^(?:会社名|公司名前|公司名称|公司名|社名|勤務先|会社)\s*[:：]?\s*(?:\t|\s)", "", rest).strip()
            item = edu_item(start, end, rest) if kind == "edu" else work_item(start, end, rest)
            if kind == "work" and item is not None and last_company and POS_ONLY.search(item["company_name"]) \
                    and not ORG_HINT.search(item["company_name"]) and not item["position"]:
                item["position"], item["company_name"] = item["company_name"], last_company  # 同一公司内的岗位段
                # EN: Post periods within the same company
                # JA: 同じ会社でのポストの期間
            mrole = re.match(r"^(?:担任|任|作为|として)\s*(.{2,20}?)\s*[。，,.]?$", rest)
            if kind == "work" and mrole and last_company:
                flush()
                item = work_item(start, end, last_company)
                item["position"] = mrole.group(1)
                cur, cur_kind, cur_body = item, "work", []
                continue
            if kind == "work" and (item is None or not item["company_name"]) and cur is not None and cur_kind == "work":
                cur_body.append(l)  # 公司内的时间段说明（“2014.1月－2018.1月 財務総監秘書…”）
                # EN: Time-period notes within a company ("2014.1月－2018.1月 財務総監秘書…")
                # JA: 会社内の期間の説明（「2014.1月－2018.1月 財務総監秘書…」）
                continue
            flush()
            if item is not None and (item.get("school_name") or item.get("company_name")):
                cur, cur_kind = item, kind
                cur_body = tail
                if kind == "work":
                    last_company = item["company_name"]
            continue
        me = EVENT_RE.match(l)
        mmo = re.match(r"^(\d{1,2})\s*月?\t+([^\t].*)$", l) if (last_year and cur is None and section in ("edu", "work", "")) else None
        if mmo and 1 <= int(mmo.group(1)) <= 12 and re.search(r"[一-鿿ぁ-ヺA-Za-z]", mmo.group(2)):
            events.append([ymd(str(last_year), mmo.group(1)), mmo.group(2).strip(), [], section, ""])  # 年栏为空（同上一年）的履歴行
            # EN: History rows with an empty year column (same as the previous year)
            # JA: 年の欄が空（前の行と同じ年）の経歴の行
            continue
        mrg = EVENT_RANGE_RE.match(l) if section in ("edu", "work", "") else None
        if mrg and ymd(mrg.group(1), mrg.group(2)):
            y = mrg.group(1)
            events.append([ymd(y, mrg.group(2)), mrg.group(4).strip(), [], section, ymd(y, mrg.group(3))])  # “2009\t1-3\t…”
            continue
        if me and section in ("edu", "work", "", "cert") and not re.match(r"^\d{4}\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日", l):
            d = ymd(me.group(1), me.group(2))
            rest = me.group(3).strip()
            if d and section != "cert":
                last_year = int(d[:4])
            if d and rest:
                if section == "cert":
                    c = CN.empty("certificate_list")
                    c["certificate_time"], c["certificate_name"] = d, rest
                    certs.append(c)
                else:
                    flush()
                    events.append([d, rest, [], section, ""])
                continue
        if section == "pr":
            pr_parts.append(l)
        elif section == "cert" and (re.fullmatch(r"[・■【\[\s]*[^\s:：]{0,8}(資格|免許|スキル|奨|認定|賞罰)[^\s:：]{0,6}\s*[】\]]?\s*[:：]?\s*", l)
                                    or re.fullmatch(r"(賞罰|趣味|特技|工作经历|职业技能|教育经历)", l) or re.match(r"^[^:：]{1,12}[:：]", l) and not CERT_LINE.search(l.split(":")[0].split("：")[0])):
            continue
        elif section == "cert" and not re.search(r"(年|月)\s*$", l) and len(l) <= 40 and re.search(r"[一-鿿A-Za-zぁ-ヺ]", l) \
                and not re.search(r"\d{3,4}-\d{4}", l) \
                and not re.search(r"(紐培|纽培|www|有限公司|TEL|ヒューマン|以上|自己PR|職務経歴|アピール)", l, re.I):
            c = CN.empty("certificate_list")
            c["certificate_name"] = l
            certs.append(c)
        elif section in ("edu", "") and cur is None and len(l) <= 40 and CERT_LINE.search(l) and not SCHOOL_HINT.search(l):
            c = CN.empty("certificate_list")
            c["certificate_name"] = l
            certs.append(c)
        elif section == "edu" and cur is not None and cur_kind == "edu" and len(l) <= 40 and CERT_LINE.search(l):
            flush()
            c = CN.empty("certificate_list")
            c["certificate_name"] = l
            certs.append(c)
        elif cur is not None:
            cur_body.append(l)
        elif events and section in ("work", "") and not re.match(r"^[^:：]{1,10}[:：]", l) and not SECTION_RE.match(l) \
                and not re.match(r"^(?:19|20)\d{2}", l) and not OTHER_START.match(l) \
                and (WORK_END.search(events[-1][1]) or ORG_HINT.search(events[-1][1]) or events[-1][3] == "work"):
            events[-1][2].append(l)  # 履歴行下面的工作说明
            # EN: Job notes under a history row
            # JA: 経歴の行の下にある業務の説明
    flush()
    # 履歴行：入学/卒業、入社/退社 成对；无标记的行单独成条；行下的说明文字作为职责
    # EN: History rows: 入学/卒業 (enrolment/graduation) and 入社/退社 (joining/leaving) in pairs; unmarked rows form entries on their own; the explanatory text under a row is used as duties
    # JA: 経歴の行：入学／卒業、入社／退社 を組にする。印のない行は単独で 1 項目にする。行の下の説明文は職務とする
    def add_work(st_d, en_d, text, desc):
        item = work_item(st_d, en_d, text)
        if desc and not item["position"]:
            mpos = re.match(r"^\s*(?:担当|職位|役職|職種)\s*[:：]\s*([^\s:：]{1,20})", desc[0])
            if mpos:
                item["position"] = mpos.group(1)
        if item["company_name"]:
            if desc:
                item["position_responsibilities"] = "\n".join(desc)
            res["work_experiences"].append(item)

    open_edu, open_work = {}, []
    for ev in events:
        ev[1], extra = norm_event(ev[1])
        if extra:
            ev[2].insert(0, extra)
        if any(re.fullmatch(r"(現在に至る|現在|在職中|至今)", x.strip()) for x in ev[2]):
            ev[2] = [x for x in ev[2] if not re.fullmatch(r"(現在に至る|現在|在職中|至今)", x.strip())]
            if not ev[4] and WORK_END.search(ev[1]) and WORK_END.search(ev[1]).group(1) in ("入社", "入職", "開始"):
                ev[4] = "至今"
    for d, rest, desc, sec, end_d in events:
        if re.search(r"(級|CET|TOEIC|TOEFL|JLPT|IELTS|試験|検定|(?<![A-Za-z])N[1-5](?![0-9]))", rest) and not re.search(r"(入学|卒業|有限|会社|公司|入社)", rest) \
                and len(rest) <= 40:
            c = CN.empty("certificate_list")
            c["certificate_time"], c["certificate_name"] = d, rest
            certs.append(c)
            continue
        core = EDU_END.sub("", WORK_END.sub("", rest)).strip()
        key = (re.split(r"[\t ]+", core) or [""])[0]
        if EDU_END.search(rest) and not ORG_HINT.search(rest):
            st = EDU_END.search(rest).group(1)
            if st.startswith("在学") and key not in open_edu:
                item = edu_item(d, "至今", rest)
                if item:
                    res["education_list"].append(item)
                continue
            if st in ("入学", "編入", "転入"):
                open_edu[key] = (d, rest)
            else:
                prev = open_edu.pop(key, None) or (open_edu.pop(next(iter(open_edu)), None) if open_edu and key in ("同", "同校", "同大学") else None)
                item = edu_item(prev[0] if prev else "", "至今" if st.startswith("在学") else d, prev[1] if prev else rest)
                if item:
                    res["education_list"].append(item)
        elif WORK_END.search(rest) or ORG_HINT.search(rest) or sec == "work":
            st = WORK_END.search(rest).group(1) if WORK_END.search(rest) else ""
            if end_d:
                add_work(d, end_d, rest, desc)
            elif st in ("入社", "入職", "転籍", "出向", "開始"):
                open_work.append([key, d, rest, list(desc)])
            elif st in ("在職中", "現在に至る"):
                if open_work and (key in ("同社", "同", "") or key == open_work[-1][0]):
                    k, d0, r0, ds0 = open_work.pop()
                    add_work(d0, "至今", r0, ds0 + desc)
                else:
                    add_work(d, "至今", rest, desc)
            elif st:  # 退社・退職
            # EN: 退社・退職 (leaving / resignation)
            # JA: 退社・退職
                idx = next((i for i in range(len(open_work) - 1, -1, -1) if open_work[i][0] == key), None)
                if idx is None and open_work and (key in ("同社", "同", "") or not ORG_HINT.search(core)):
                    idx = len(open_work) - 1
                if idx is not None:
                    k, d0, r0, ds0 = open_work.pop(idx)
                    add_work(d0, d, r0, ds0 + desc)
                else:
                    add_work("", d, rest, desc)
            else:
                add_work(d, "", rest, desc)  # 无入社/退社标记：只有起始年月
                # EN: No 入社/退社 marker: only the start year-month
                # JA: 入社・退社の印がない：開始年月だけ
        elif sec == "edu":
            item = edu_item(d, "", rest)
            if item:
                res["education_list"].append(item)
    for key, (d, rest) in open_edu.items():
        item = edu_item(d, "", rest)
        if item:
            res["education_list"].append(item)
    latest = max((o[1] for o in open_work), default="")
    for k, d, rest, desc in open_work:
        add_work(d, "至今" if d == latest else "", rest, desc)
    # 学歴里不是学校的（語学研修・ボランティア等）→ 培训；句子 → 丢弃
    # EN: Items in 学歴 that are not schools (語学研修 language training, ボランティア volunteering, etc.) → training; sentences → discarded
    # JA: 学歴のうち学校でないもの（語学研修・ボランティアなど）→ 研修。文 → 捨てる
    keep_edu = []
    for e in res["education_list"]:
        sc = e["school_name"]
        if SCHOOL_OK.search(sc) and not TRAIN_HINT.search(sc):
            keep_edu.append(e)
        elif len(sc) <= 30 and not re.search(r"(。|、|をやり|として|ため|です|ます)", sc):
            t = CN.empty("training_list")
            t["organization_name"], t["training_name"] = sc, e["school_major_name"]
            t["start_ym"], t["end_ym"] = e["school_start_ym"], e["school_end_ym"]
            res["training_list"].append(t)
    res["education_list"] = keep_edu
    moved = [w for w in res["work_experiences"] if SCHOOL_OK.search(w["company_name"]) and not ORG_HINT.search(w["company_name"])
             and (not w["position"] or re.search(r"(入学|卒業|留学|学生|専攻|专业|学部|学科)", w["position"]))]
    for w in moved:
        e = edu_item(w["position_start"], "" if w["position_resigned"] == "至今" else w["position_resigned"], w["company_name"] + " " + w["position"])
        if e:
            res["education_list"].append(e)
    res["work_experiences"] = [w for w in res["work_experiences"] if w not in moved]
    res["work_experiences"] = dedupe(res["work_experiences"], "company_name", "position_start")
    res["education_list"] = dedupe(res["education_list"], "school_name", "school_start_ym")
    res["certificate_list"] = certs
    base["pr"] = "\n".join(pr_parts + agency_parts).strip()
    res["work_experiences"].sort(key=lambda w: w["position_start"], reverse=True)
    res["education_list"].sort(key=lambda e: e["school_start_ym"], reverse=True)
    if not (res["work_experiences"] or res["education_list"]):
        return None
    if exp_salary:
        ex = CN.empty("expected_list")
        ex["expected_salary"] = exp_salary
        res["expected_list"] = [ex]
    cleanup(res)
    if not (res["work_experiences"] or res["education_list"]):
        return None
    k, hn, sm = len(KANA_RE.findall(joined)), len(HAN_RE.findall(joined)), len(SIMP_RE.findall(joined))
    content_lang = "zh" if (sm / max(hn, 1) >= 0.06 and k / max(k + hn, 1) < 0.15) else "jp"
    if content_lang == "zh":
        res["resume_languge"] = "zh"  # 日文模板、中文内容（xls“日本語版”里填中文等）
        # EN: Japanese template with Chinese content (Chinese filled into an xls "日本語版" (Japanese version), etc.)
        # JA: 日本語のテンプレートに中国語の内容（xls の「日本語版」に中国語を記入したものなど）
    # 原文里另有中文部分（双语文档被切掉的中文段 / xls 的中文工作表）→ 旧 JSON 的中文版可保留
    # EN: The source has a separate Chinese part (the Chinese section cut off from a bilingual document / the Chinese worksheet of an xls) → the Chinese version in the old JSON may be kept
    # JA: 原文に別の中国語部分がある（バイリンガル文書から切り離された中国語の段落・xls の中国語のワークシート）→ 旧 JSON の中国語版を残してよい
    has_zh_part = len(lines) < len(full) or bool(re.search(r"(?m)^### sheet .*(中国語|中文|中国语|简历|履历)", text))
    return {"resume": res, "updated": "", "unmapped": [], "notes": [], "content_lang": content_lang, "has_zh_part": has_zh_part}


if __name__ == "__main__":
    import json
    import sys
    print(json.dumps(parse(Path(sys.argv[1]).read_text(encoding="utf-8")), ensure_ascii=False, indent=1))
