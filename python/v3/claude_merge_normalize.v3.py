#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
claude_merge_normalize.v3.py —— 合并后、字段检查前的“字段归位与清理”。

只做规则确定的处理，不推测、不改写内容：
  * 值放错了字段 → 移到正确字段（目标字段已有值时不覆盖，只从错误字段移除）
      行业写在职位/部门里、职位写在行业里、规模写在职位里、薪资粘在职位里、部门写在职位里 …
  * 残留的栏目名、标签、纯标点/数字 → 清掉
      “教育背景”“培训机构：”“：”“01”“月薪范围”“汉族”（写在国籍/政治面貌里）…
  * 可确定的规范化
      学历级别与学历名称不一致时按学历名称定级；英文城市/婚姻/性别在中文版里换成中文；括号补齐
  * 清理后整条为空的经历（没有公司/职位/职责、没有学校/专业等）删除
每一处都写入 cleaning_ledger（原值 → 新值、规则名），可逐条核对。
规则与 claude_merge_checks.v3.py 的检查一一对应：检查判为“值放错/残留”的，这里按同一判断归位或清理。

EN: claude_merge_normalize.v3.py -- "field placement and cleaning" after merging and before field checks.

Only rule-determined processing; no guessing and no rewriting of content:
  * value in the wrong field → move it to the correct field (if the target already has a value it is not overwritten; the value is only removed from the wrong field)
      industry written in position/department, position written in industry, size written in position, salary stuck to position, department written in position …
  * leftover section names, labels, pure punctuation/digits → removed
      "教育背景" "培训机构：" "：" "01" "月薪范围" "汉族" (written in nationality/political status) …
  * determinable normalisation
      when the degree rank disagrees with the degree name, the rank follows the degree name; English city/marital status/gender replaced with Chinese in the Chinese version; brackets completed
  * experiences that become entirely empty after cleaning (no company/position/duties, no school/major, etc.) are deleted
Every change is written to cleaning_ledger (old value → new value, rule name) and can be checked item by item.
The rules correspond one-to-one to the checks in claude_merge_checks.v3.py: what the checks judge "misplaced/leftover" is placed or cleaned here by the same judgement.

JA: claude_merge_normalize.v3.py —— 統合の後、フィールドのチェックの前に行う「フィールドの再配置とクレンジング」。

ルールで確定できる処理だけを行い、推測も内容の書き換えもしない：
  * 値の置き間違い → 正しいフィールドに移す（移動先にすでに値があれば上書きせず、誤ったフィールドから除くだけ）
      業界が職位・部署に、職位が業界に、規模が職位に、給与が職位にくっつき、部署が職位に書かれているなど …
  * 残った欄の名前・ラベル・句読点や数字だけのもの → 除去
      「教育背景」「培训机构：」「：」「01」「月薪范围」「汉族」（国籍・政治的身分に書かれたもの）…
  * 確定できる正規化
      学歴ランクと学歴名が一致しなければ学歴名に従ってランクを決める。中国語版にある英語の都市・婚姻状況・性別を中国語に置き換える。括弧を補う
  * クレンジングの後に丸ごと空になった経歴（会社・職位・職務も、学校・専攻などもない）は削除する
すべての変更を cleaning_ledger（元の値 → 新しい値、ルール名）に書き込み、1 件ずつ確認できるようにする。
ルールは claude_merge_checks.v3.py のチェックと 1 対 1 で対応する：チェックで「置き間違い・残骸」と判定したものを、ここで同じ判断で再配置・除去する。
"""

import json
import re
from pathlib import Path
import importlib.util

HERE = Path(__file__).resolve().parent


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


C = _load("claude_merge_common_v3_norm", "claude_merge_common.v3.py")
K = _load("claude_merge_checks_v3_norm", "claude_merge_checks.v3.py")
s = C.s

ETHNIC_RE = re.compile(r"^[一-鿿]{1,4}族$|^(汉|漢)$")
CITY_EN = {"shanghai": "上海", "beijing": "北京", "suzhou": "苏州", "shenzhen": "深圳", "guangzhou": "广州", "hangzhou": "杭州",
           "nanjing": "南京", "wuxi": "无锡", "tianjin": "天津", "dalian": "大连", "chengdu": "成都", "wuhan": "武汉", "xian": "西安",
           "xi'an": "西安", "qingdao": "青岛", "xiamen": "厦门", "ningbo": "宁波", "kunshan": "昆山", "changzhou": "常州",
           "nantong": "南通", "hefei": "合肥", "chongqing": "重庆", "shenyang": "沈阳", "tokyo": "东京", "osaka": "大阪",
           "hong kong": "香港", "hongkong": "香港", "taipei": "台北", "singapore": "新加坡", "dongguan": "东莞", "foshan": "佛山",
           "zhuhai": "珠海", "jinan": "济南", "zhengzhou": "郑州", "changsha": "长沙", "fuzhou": "福州", "yangzhou": "扬州"}
# 拼音地名 → 中文（只在整值都能拆成已知地名时才换）：(中文, 级别 0省 1市 2区)
# EN: Pinyin place names → Chinese (replaced only when the whole value can be split into known place names): (Chinese, level 0 province 1 city 2 district)
# JA: ピンインの地名 → 中国語（値全体が既知の地名に分けられる場合だけ置き換える）：(中国語, レベル 0 省 1 市 2 区)
_PY = {
    "beijing": ("北京", 0), "shanghai": ("上海", 0), "tianjin": ("天津", 0), "chongqing": ("重庆", 0), "hebei": ("河北", 0), "shanxi": ("山西", 0),
    "liaoning": ("辽宁", 0), "jilin": ("吉林", 0), "heilongjiang": ("黑龙江", 0), "jiangsu": ("江苏", 0), "zhejiang": ("浙江", 0), "anhui": ("安徽", 0),
    "fujian": ("福建", 0), "jiangxi": ("江西", 0), "shandong": ("山东", 0), "henan": ("河南", 0), "hubei": ("湖北", 0), "hunan": ("湖南", 0),
    "guangdong": ("广东", 0), "hainan": ("海南", 0), "sichuan": ("四川", 0), "guizhou": ("贵州", 0), "yunnan": ("云南", 0), "shaanxi": ("陕西", 0),
    "gansu": ("甘肃", 0), "qinghai": ("青海", 0), "guangxi": ("广西", 0), "neimenggu": ("内蒙古", 0), "innermongolia": ("内蒙古", 0),
    "ningxia": ("宁夏", 0), "xinjiang": ("新疆", 0), "xizang": ("西藏", 0), "tibet": ("西藏", 0),
    "suzhou": ("苏州", 1), "shenzhen": ("深圳", 1), "guangzhou": ("广州", 1), "hangzhou": ("杭州", 1), "nanjing": ("南京", 1), "wuxi": ("无锡", 1),
    "dalian": ("大连", 1), "chengdu": ("成都", 1), "wuhan": ("武汉", 1), "xian": ("西安", 1), "qingdao": ("青岛", 1), "xiamen": ("厦门", 1),
    "ningbo": ("宁波", 1), "kunshan": ("昆山", 1), "changzhou": ("常州", 1), "nantong": ("南通", 1), "hefei": ("合肥", 1), "shenyang": ("沈阳", 1),
    "dongguan": ("东莞", 1), "foshan": ("佛山", 1), "zhuhai": ("珠海", 1), "jinan": ("济南", 1), "zhengzhou": ("郑州", 1), "changsha": ("长沙", 1),
    "fuzhou": ("福州", 1), "yangzhou": ("扬州", 1), "jingzhou": ("荆州", 1), "jingdezhen": ("景德镇", 1), "xinyang": ("信阳", 1),
    "harbin": ("哈尔滨", 1), "changchun": ("长春", 1), "shijiazhuang": ("石家庄", 1), "taiyuan": ("太原", 1), "nanchang": ("南昌", 1),
    "kunming": ("昆明", 1), "guiyang": ("贵阳", 1), "nanning": ("南宁", 1), "lanzhou": ("兰州", 1), "urumqi": ("乌鲁木齐", 1),
    "wenzhou": ("温州", 1), "shaoxing": ("绍兴", 1), "jiaxing": ("嘉兴", 1), "huzhou": ("湖州", 1), "taizhou": ("台州", 1), "jinhua": ("金华", 1),
    "xuzhou": ("徐州", 1), "yancheng": ("盐城", 1), "huaian": ("淮安", 1), "lianyungang": ("连云港", 1), "zhenjiang": ("镇江", 1),
    "yantai": ("烟台", 1), "weifang": ("潍坊", 1), "zibo": ("淄博", 1), "luoyang": ("洛阳", 1), "yichang": ("宜昌", 1), "anshan": ("鞍山", 1),
    "wuhu": ("芜湖", 1), "bengbu": ("蚌埠", 1), "anqing": ("安庆", 1), "mianyang": ("绵阳", 1), "baotou": ("包头", 1), "tangshan": ("唐山", 1),
    "baoding": ("保定", 1), "handan": ("邯郸", 1), "zhangjiagang": ("张家港", 1), "changshu": ("常熟", 1), "jiangyin": ("江阴", 1),
    "pudong": ("浦东新区", 2), "minhang": ("闵行区", 2), "songjiang": ("松江区", 2), "yangpu": ("杨浦区", 2), "xuhui": ("徐汇区", 2),
    "changning": ("长宁区", 2), "jingan": ("静安区", 2), "huangpu": ("黄浦区", 2), "hongkou": ("虹口区", 2), "putuo": ("普陀区", 2),
    "baoshan": ("宝山区", 2), "jiading": ("嘉定区", 2), "qingpu": ("青浦区", 2), "fengxian": ("奉贤区", 2), "jinshan": ("金山区", 2),
    "chongming": ("崇明区", 2), "zhabei": ("闸北区", 2), "luwan": ("卢湾区", 2),
}
_PY_FILLER = ("newdistrict", "district", "province", "city", "of", "pr", "china")


def pinyin_place(v):
    """“Shanghai-Pudong / Jingdezhen, JiangXi Province / HENAN XINYANG” → 上海浦东新区 / 江西景德镇 / 河南信阳；拆不开就返回空。

    EN: "Shanghai-Pudong / Jingdezhen, JiangXi Province / HENAN XINYANG" → 上海浦东新区 / 江西景德镇 / 河南信阳; returns empty if it cannot be split.

    JA: 「Shanghai-Pudong / Jingdezhen, JiangXi Province / HENAN XINYANG」→ 上海浦东新区 / 江西景德镇 / 河南信阳。分けられなければ空を返す。
    """
    x = re.sub(r"[^a-z]", "", v.lower().replace("xi'an", "xian"))
    if not x or not re.fullmatch(r"[A-Za-z][A-Za-z\s,\-.']*", v.strip()):
        return ""
    keys = sorted(list(_PY) + list(_PY_FILLER), key=len, reverse=True)
    best = {0: []}
    for i in range(len(x)):
        if i not in best:
            continue
        for k in keys:
            if x.startswith(k, i) and i + len(k) not in best:
                best[i + len(k)] = best[i] + [k]
    if len(x) not in best:
        return ""
    parts = [_PY[k] for k in best[len(x)] if k in _PY]
    if not parts:
        return ""
    seen, out = set(), []
    for nm, lv in sorted(parts, key=lambda p: p[1]):
        if nm not in seen:
            seen.add(nm)
            out.append(nm)
    return "".join(out)


MARITAL_EN = {"single": "未婚", "unmarried": "未婚", "married": "已婚", "divorced": "离异"}
GENDER_EN = {"male": "男", "female": "女", "m": "男", "f": "女"}
DEGREE_WORDS = ["博士后", "博士", "EMBA", "MBA", "硕士", "研究生", "本科", "学士", "大专", "专科", "高中", "中专", "中技", "职高", "初中"]
RANK = {"博士后": "7", "博士": "6", "硕士": "5", "研究生": "5", "MBA": "5", "EMBA": "5", "本科": "4", "学士": "4",
        "大专": "3", "专科": "3", "高中": "2", "中专": "2", "中技": "2", "职高": "2", "初中": "1"}
LEAK_HEAD_RE = re.compile(r"(^|\n)\s*(求职意向|教育经历|教育背景|工作经历|工作经验|项目经历|简历内容|職 ?歴|学 ?歴|資 ?格)\s*[:：]?\s*(\n|$)")
LEAK_LABEL_RE = re.compile(r"(期望月薪|期望从事职业|期望工作地区|目前状况|希望職種|希望給与)")


ORG_EXTRACT_RE = re.compile(r"([一-鿿A-Za-z0-9（）()&·\-]{2,40}?(?:股份有限公司|有限责任公司|有限公司|株式会社|有限会社|集团公司|集团|分公司|公司|银行|医院|研究所|研究院|事务所|代表处|办事处|Co\.,?\s*Ltd\.?|Limited|Inc\.?|Corporation))")
MAJOR_CUT_RE = re.compile(r"\s*(简历内容|附件简历|点击下载|求职信|所获奖项|获奖情况|姓名\s|\{\$).*$", re.S)
STUDY_WORDS_RE = re.compile(r"(本科|硕士|博士|大专|专科|学历|专业|専攻|专攻|学部|学科|留学|在读|毕业)")
DEGREE_IN_TEXT_RE = re.compile(r"(博士|硕士|本科|大专|专科|中专|高中)")

ASSUME_RE = re.compile(r"^(?:\d*年[，,]?\s*)?(?:在|于)\s*[“\"]?([^，。；;“”\"]{2,30}?)[”\"]?\s*(担任|任|从事|做)\s*([^，。；;]{1,20}?)(?:一职|工作)?[。．.]?$")
GENERIC_POS = {"学生实践", "学生实践(兼职)", "学生实践 (兼职)", "兼职", "实习", "担当", "役職", "描述", "职位", "职务"}
ORG_POS_RE = re.compile(r"^(.{2,30}(?:公司|集团|会社|厂|社|台|频道|支店|分店|店|银行|医院|事务所|[)）]))\s*(?:[-－]\s*)?([^()（）\s]{2,15})$")
# ---- 学历行整理用
# EN: ---- For tidying education rows
# JA: ---- 学歴の行の整理用
DATEY_RE = re.compile(r"^(?:[\d０-９]+|[年月日]|years?|months?|至今|now|ending\s*time|jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|[\s|｜.\-/~～—–:：()（）,，])+$", re.I)
DATE_PREFIX_RE = re.compile(r"^(?:(?:[\d０-９]{4}\s*(?:[年./\-]\s*)?)?[\d０-９]{1,2}\s*[月年](?:[\d０-９]{1,2}\s*日)?|[\d０-９]{4}\s*[./]\s*[\d０-９]{1,2}|年\s*[\d０-９]{1,2}\s*月(?:\s*[～~\-—]\s*(?:至今|[\d０-９]{4}\s*年\s*[\d０-９]{1,2}\s*月))?)\s+")
EDU_LABELS = {C.norm_text(x) for x in (
    "毕业情况", "人数", "附件简历", "仕事業務紹介", "会社名", "时期", "工作时间", "职历", "職務", "期间", "在職期間", "起止时间", "专业",
    "Hoping position", "Position", "Background", "Dept", "卒業", "毕业", "教育", "电脑能力", "Trainings", "Leadership Position", "Other",
    "Yes", "勤務経験", "Travel, Experience , Part-time work", "Project Experience", "学校名称", "日本工作对应", "单位", "公司性质",
    "证书", "证书说明", "証書", "资格证书", "資格")}
EDU_DEGREE_WORDS = {"硕士": "硕士", "研究生": "研究生", "大专": "大专", "本科": "本科", "学士": "学士", "文学学士": "学士", "博士": "博士",
                    "专升本": "本科", "修士号取得": "硕士", "undergraduate": "本科", "别科生": "", "在读": "", "交換留学修了": "", "理工科": ""}
SCHOOL_TOKEN_RE = re.compile(r"^(.*(?:大学院|大学|学院|専門学校|学校|大學|學院|語学院|语学院|高等学校|高校|中学|センター))", re.I)
SCHOOL_EN_RE = re.compile(r"((?:[A-Z][\w&.'\-]*\s+)*(?:University|College|Institute|School)(?:\s+of(?:\s+[A-Z][\w&.'\-]*)+)?)")
EDU_CERT_RE = re.compile(r"(大学英[语語]|证书|証書|证明书|証明書|能力测试|能力試験|能力考试|能力考核|等级考试|計算機|计算机考试|[\d０-９一二三四六][级級]\s*(合格)?|N[1-5]\b|驾照|機動車|机动车|TOEIC|TOEFL|托业|托福|雅思|IELTS)", re.I)
EDU_COMPANY_RE = re.compile(r"(有限公司|有限会社|株式会社|Co\.|\bLtd\b|Corporation|会社名称|^公司\s|Company Name|[（(]\s*\d+\s*年\s*\d*\s*个?月|\d+年\s*\d+个月|[（(]\d+\s*(years?|months?)|科技$|電子$|电子$|医療科技|人寿|本田|日野)", re.I)


class Normalizer:
    def __init__(self, log, source):
        self.log, self.source = log, source

    def note(self, path, rule, old, new):
        self.log.append({"source": self.source, "field_path": path,
                         "action": f"normalize:{rule}:{str(old)[:60]}->{str(new)[:60]}"})

    def setf(self, obj, f, new, path, rule):
        old = s(obj.get(f))
        if old != new:
            obj[f] = new
            self.note(f"{path}.{f}", rule, old, new)

    def move(self, obj, src, dst, path, rule, value=None):
        """把 src 的值（或给定 value）移到 dst；dst 已有值则只清空 src。

        EN: Move src's value (or the given value) to dst; if dst already has a value, just clear src.

        JA: src の値（または指定した value）を dst に移す。dst にすでに値があれば src を空にするだけ。
        """
        v = s(obj.get(src)) if value is None else value
        if v and not s(obj.get(dst)):
            obj[dst] = v
            self.note(f"{path}.{dst}", rule + "(移入)", "", v)
        self.setf(obj, src, "", path, rule)

    # ------------------------------------------------------------ 通用值
    # EN: ------------------------------------------------------------ General values
    # JA: ------------------------------------------------------------ 汎用的な値
    def clean_generic(self, obj, path, lang):
        for f in list(obj.keys()):
            v = s(obj.get(f))
            if not v or not (f in C.ENTITY_FIELDS or f in ("household_registration", "address", "marital_status", "company_industry",
                                                            "school_degree_type")):
                continue
            if K.PUNCT_ONLY_RE.match(v):
                self.setf(obj, f, "", path, "纯标点或数字")
                continue
            if K.is_section_word(v):
                self.setf(obj, f, "", path, "栏目名当成了值")
                continue
            m = K.LABEL_RE.search(v)
            if m:
                before, after = v[:m.start()].strip(" \t|,，;；※·•"), v[m.end():].strip(" \t|,，;；※·•")
                own = re.search(r"(职位名称|Position|Occupation)", m.group(1), re.I) and f in ("position", "project_name")
                if re.fullmatch(r"[A-Za-z]+", before or "") and re.match(r"[A-Za-z]", m.group(1)):
                    before = ""  # “Project Position: …”：前面的英文词是标签的一部分
                    # EN: "Project Position: …": the English words before it are part of the label
                    # JA: 「Project Position: …」：前にある英単語はラベルの一部
                    own = own and f == "position"
                if before and not K.LABEL_RE.search(before):
                    new = before
                elif own and after and not K.LABEL_RE.search(after):
                    new = after
                else:
                    new = ""
                self.setf(obj, f, new, path, "值里残留其他字段的标签")

    # ------------------------------------------------------------ 基本信息
    # EN: ------------------------------------------------------------ Basic info
    # JA: ------------------------------------------------------------ 基本情報
    def base(self, b, path, lang):
        self.clean_generic(b, path, lang)
        na = s(b.get("nationality"))
        if na and ("族" in na or na in ("汉", "漢")):
            self.setf(b, "nationality", "中国" if ETHNIC_RE.match(na) and lang == "zh" else "", path, "民族写进了国籍")
        ps = s(b.get("political_status"))
        if ps and ("族" in ps or ps in ("汉", "漢")):
            self.setf(b, "political_status", "", path, "民族写进了政治面貌")
        city = s(b.get("city"))
        if city:
            first = re.split(r"[\s\-,/]+", city.lower().strip())[0] if city.strip() else ""
            if lang == "zh" and city.lower().strip() in CITY_EN:
                self.setf(b, "city", CITY_EN[city.lower().strip()], path, "城市英文改中文")
            elif lang == "zh" and re.fullmatch(r"[A-Za-z][A-Za-z\s\-,/]*", city) and first in CITY_EN:
                self.setf(b, "city", CITY_EN[first], path, "城市英文改中文")
            elif city in K.PROVINCE_AS_CITY or K.COUNTRY_CITY_RE.match(city):
                self.setf(b, "city", city[:-1], path, "省/国名后误加“市”")
            elif re.fullmatch(r"[A-Za-z][A-Za-z\s\-,/]*", city) and first in CITY_EN:
                self.setf(b, "city", CITY_EN[first] if lang == "zh" else city.split("-")[0].split(",")[0].strip(), path, "城市只保留城市名")
            elif len(city) > 15 or K.CITY_BAD_RE.search(city):
                # 取原值里最先出现的地名（同位置取较长的）；按位置排序，保证每次运行结果一样
                # EN: Take the place name that appears first in the original value (the longer one at the same position); sort by position so every run gives the same result
                # JA: 元の値で最初に現れる地名を取る（同じ位置なら長い方）。位置で並べ替え、毎回同じ結果になるようにする
                hits = sorted(((city.find(c), -len(c), c) for c in set(CITY_EN.values()) | K.PLACE_NAMES if c in city))
                known = hits[0][2] if hits else ""
                self.setf(b, "city", known, path, "城市字段里是其他内容")
        if lang == "zh":
            for f in ("household_registration", "address", "city"):
                v = s(b.get(f))
                zh = pinyin_place(v) if v else ""
                if zh:
                    self.setf(b, f, zh, path, "拼音地名改中文")
            for f, mp, rule in (("marital_status", MARITAL_EN, "婚姻英文改中文"), ("gender", GENDER_EN, "性别英文改中文")):
                v = s(b.get(f))
                if v and v.lower() in mp:
                    self.setf(b, f, mp[v.lower()], path, rule)
    def pr_fix(self, res, path):
        b = res.get("base_info") or {}
        pr = s(b.get("pr"))
        if not pr:
            return
        new = pr.strip()
        # 开头重复的栏目名行（“自我评价⏎自我评价⏎…”）
        # EN: Repeated section-name lines at the start ("自我评价⏎自我评价⏎…")
        # JA: 先頭で繰り返される欄の名前の行（「自我评价⏎自我评价⏎…」）
        lines = new.split("\n")
        while lines and K.is_section_word(lines[0].strip()) and len(lines[0].strip()) <= 8:
            lines = lines[1:]
        new = "\n".join(lines).strip()
        # 混进来的“期望从事职业/期望月薪/目前状况 …”一段：从第一个标签处截断，值写回求职意向（原来为空时）
        # EN: A mixed-in passage "期望从事职业/期望月薪/目前状况 …" (desired occupation / monthly salary / current status …): truncate at the first label and write the values back into the job preferences (when they were empty)
        # JA: 混入した「期望从事职业／期望月薪／目前状况 …」（希望職種・希望月給・現在の状況…）の段落：最初のラベルで切り、値を希望条件に書き戻す（元が空の場合）
        m = LEAK_LABEL_RE.search(new)
        if m and len(new[:m.start()].strip()) >= 10:
            tail = new[m.start():]
            new = new[:m.start()].strip()
            got = {}
            for lab, f in (("期望从事职业", "expected_position"), ("希望職種", "expected_position"), ("期望月薪", "expected_salary"),
                           ("希望給与", "expected_salary"), ("期望工作地区", "expected_city")):
                mm = re.search(lab + r"\s*[:：]\s*(.+?)(?=(期望从事职业|期望月薪|期望工作地区|目前状况|希望職種|希望給与)\s*[:：]|$)", tail, re.S)
                if mm and re.sub(r"\s+", "", mm.group(1)):
                    got[f] = re.sub(r"\s*\n\s*", "", mm.group(1)).strip()
            if got:
                exp = res.setdefault("expected_list", [])
                if not exp:
                    exp.append({k: "" for k in C.LIST_FIELDS["expected_list"]})
                for f, v in got.items():
                    if not s(exp[0].get(f)):
                        exp[0][f] = v
                        self.note(f"{path.rsplit('.', 1)[0]}.expected_list[0].{f}", "自我评价里的求职意向移回(移入)", "", v)
        mh = LEAK_HEAD_RE.search(new)
        if mh and len(new[:mh.start()].strip()) >= 10:
            new = new[:mh.start()].strip()
        if new != pr.strip() and new:
            self.setf(b, "pr", new, path, "自我评价里混入其他栏目")

    # ------------------------------------------------------------ 工作
    # EN: ------------------------------------------------------------ Work
    # JA: ------------------------------------------------------------ 職歴
    def work(self, w, path, lang):
        self.clean_generic(w, path, lang)
        comp, pos = s(w.get("company_name")), s(w.get("position"))
        if comp and C.norm_text(comp) in {C.norm_text(x) for x in K.PLACEHOLDER_COMPANY}:
            self.setf(w, "company_name", "", path, "公司名是占位词")
        comp = s(w.get("company_name"))
        if comp and (K.too_long(comp) or K.SENT_PUNCT.search(comp) or K.COMPANY_SENT_WORDS.search(comp) or re.match(r"^(在|于|来|到|就职于|任职于|供职于)", comp)
                     or re.match(r"^[（(【\[:：]", comp) and not K.ORG_SUFFIX_RE.search(comp)):
            orgs = [m.group(1) for m in ORG_EXTRACT_RE.finditer(comp)]
            orgs = [re.sub(r"^(年\d*月?至今|至今|就职于|任职于|供职于|在|于|来|到|，|,|：|:|\|)+", "", o).strip(" |:：，,") for o in orgs]
            orgs = [o for o in orgs if len(o) >= 4 and not K.SENT_PUNCT.search(o)]
            if len(orgs) == 1:
                org = orgs[0]
                i = comp.find(org)
                before, after = comp[:i].strip(" |:：，,。"), comp[i + len(org):].strip(" |:：，,。")
                self.setf(w, "company_name", org, path, "公司栏是一句话，取出其中的单位名")
                if before and "|" in before and not s(w.get("position")) and len(before) <= 30:
                    w["position"] = before.split("|")[0].strip()
                    self.note(f"{path}.position", "公司栏里的职位(移入)", "", w["position"])
                    before = ""
                segs = [x for x in re.split(r"\s*[|｜]\s*", after) if x]
                if segs and K.INDUSTRY_SEG_RE.search(segs[0]) and not s(w.get("company_industry")):
                    w["company_industry"] = segs[0]
                    self.note(f"{path}.company_industry", "公司栏里的行业(移入)", "", segs[0])
                    after = ""
                rest = " ".join(x for x in (before, after) if x and not re.fullmatch(r"[\d\-人以上下|]+", x))
                if rest and len(rest) >= 6 and re.search(r"[一-鿿A-Za-z]{4,}", rest):
                    w["position_responsibilities"] = (rest + "\n" + s(w.get("position_responsibilities"))).strip()
                    self.note(f"{path}.position_responsibilities", "公司栏里的描述(移入)", "", rest)
            elif ASSUME_RE.match(comp) and len(ASSUME_RE.match(comp).group(1)) >= 4 and not K.SENT_PUNCT.search(ASSUME_RE.match(comp).group(1)) \
                    and len(ASSUME_RE.match(comp).group(3)) <= 12 and not K.SENT_PUNCT.search(ASSUME_RE.match(comp).group(3)):
                m_ = ASSUME_RE.match(comp)
                org, role = m_.group(1).strip("“”\"' "), m_.group(3).strip()
                self.setf(w, "company_name", org, path, "公司栏是“在X担任Y”，拆成单位和职位")
                if not pos or pos in GENERIC_POS:
                    self.setf(w, "position", role, path, "公司栏是“在X担任Y”，拆成单位和职位")
                elif C.norm_text(role) not in C.norm_text(pos + s(w.get("position_responsibilities"))):
                    w["position_responsibilities"] = (comp + "\n" + s(w.get("position_responsibilities"))).strip()
                    self.note(f"{path}.position_responsibilities", "公司栏原句(移入)", "", comp)
            elif re.match(r"^(在|于|就职于|任职于|供职于)[一-鿿A-Za-z]{2,20}$", comp) and K.ORG_SUFFIX_RE.search(comp) \
                    and not re.match(r"^(在|于)(职|校|读|学|册|编|岗|任|籍|日|中国|海外|国内|外)", comp) \
                    and len(re.sub(r"^(在|于|就职于|任职于|供职于)", "", comp)) >= 4:
                self.setf(w, "company_name", re.sub(r"^(在|于|就职于|任职于|供职于)", "", comp), path, "去掉公司名前的“在/就职于”")
        # 公司名末尾的在职时长“(1年 6个月 ) / ( 一个月内 )”
        # EN: Tenure at the end of company names "(1年 6个月 ) / ( 一个月内 )" (1 year 6 months / within a month)
        # JA: 会社名の末尾の在職期間「(1年 6个月 ) / ( 一个月内 )」（1 年 6 か月／1 か月以内）
        comp = s(w.get("company_name"))
        m_ = re.search(r"\s*[（(]\s*(\d+\s*年)?\s*(\d+\s*个?月)?\s*[)）]\s*$", comp) \
            or re.search(r"\s*[（(]\s*()([一二三四五六七八九十两半\d]+\s*(?:个月|年)(?:以内|内|以上)?)\s*[)）]\s*$", comp)
        if comp and m_ and (m_.group(1) or m_.group(2)) and len(comp[:m_.start()].strip()) >= 4:
            self.setf(w, "company_name", comp[:m_.start()].strip(), path, "公司名末尾粘了在职时长")
        # “丸红(上海)有限公司(实习) / 实习(上海灼日精细化工有限公司)”：实习/兼职写在公司名里
        # EN: "丸红(上海)有限公司(实习) / 实习(上海灼日精细化工有限公司)": internship/part-time written inside the company name
        # JA: 「丸红(上海)有限公司(实习) / 实习(上海灼日精细化工有限公司)」：インターン・パートが会社名の中に書かれている
        comp, pos = s(w.get("company_name")), s(w.get("position"))
        m_ = re.match(r"^(.{2,40}?)\s*[（(]\s*(实习|兼职|实习生|见习)\s*[)）]$", comp) \
            or re.match(r"^(实习|兼职|见习)\s*[（(]\s*(.{4,40})\s*[)）]$", comp)
        if m_:
            org, kind = (m_.group(1), m_.group(2)) if m_.group(2) in ("实习", "兼职", "实习生", "见习") else (m_.group(2), m_.group(1))
            org = org.strip()
            if len(org) >= 2 and not K.SENT_PUNCT.search(org):
                self.setf(w, "company_name", org, path, "公司名里的“实习/兼职”移到职位")
                if not pos or pos in GENERIC_POS:
                    self.setf(w, "position", kind, path, "公司名里的“实习/兼职”移到职位")
                elif kind not in pos:
                    self.setf(w, "position", f"{pos}（{kind}）", path, "公司名里的“实习/兼职”移到职位")
        # “上海标准件进出口有限公司(2006年6月归入…) / 英业达…有限公司（生产HP/Dell…）”：公司名后面括号里是说明
        # EN: "上海标准件进出口有限公司(2006年6月归入…) / 英业达…有限公司（生产HP/Dell…）": the brackets after the company name are notes
        # JA: 「上海标准件进出口有限公司(2006年6月归入…) / 英业达…有限公司（生产HP/Dell…）」：会社名の後の括弧は説明である
        comp = s(w.get("company_name"))
        m_ = re.match(r"^([^（(，,。；;]{4,40}?(?:有限公司|有限责任公司|股份公司|公司|会社|集团))\s*[（(]([^（()）]{8,})[)）]$", comp)
        if m_ and (K.SENT_PUNCT.search(m_.group(2)) or re.search(r"(\d{4}|年|归入|生产|主要|大型|连锁|零售|上市|总部|规模|[,，/])", m_.group(2))) \
                and not re.search(r"(有限公司|分公司|会社|集团)$", m_.group(2)):
            self.setf(w, "company_name", m_.group(1).strip(), path, "公司名后面括号里是说明，移到职责")
            w["position_responsibilities"] = ("（公司说明）" + m_.group(2).strip() + "\n" + s(w.get("position_responsibilities"))).strip()
            self.note(f"{path}.position_responsibilities", "公司名后面括号里是说明(移入)", "", m_.group(2).strip())
        # “58到家 客服 / 梅特勒-托利多(METTLER TOLEDO)内部销售实习生”：单位名后面粘着职位
        # EN: "58到家 客服 / 梅特勒-托利多(METTLER TOLEDO)内部销售实习生": the position is stuck after the organisation name
        # JA: 「58到家 客服 / 梅特勒-托利多(METTLER TOLEDO)内部销售实习生」：組織名の後に職位がくっついている
        comp, pos = s(w.get("company_name")), s(w.get("position"))
        if comp and pos and len(pos) >= 2 and comp.endswith(pos) and len(comp) - len(pos) >= 4 and not K.SENT_PUNCT.search(comp) \
                and re.search(r"(公司|集团|会社|厂|社|台|店|银行|医院|事务所|Co\.|Ltd)", comp[:-len(pos)], re.I) and K.POSITION_WORD_RE.search(pos):
            self.setf(w, "company_name", comp[:-len(pos)].strip(" -－"), path, "公司名后面粘了职位，拆开")
            comp = s(w.get("company_name"))
        if comp and (not pos or pos in GENERIC_POS) and not K.SENT_PUNCT.search(comp) and len(comp) <= 40:
            m_ = ORG_POS_RE.match(comp)
            if m_ and len(m_.group(1).strip()) >= 3 and len(m_.group(2).strip()) >= 2 and K.POSITION_WORD_RE.search(m_.group(2).strip()) \
                    and not re.fullmatch(r"(实习|兼职|家教|销售|采购|营业|翻译|会计|编辑|顾问|客服|前台)", m_.group(2).strip()):
                org, role = m_.group(1).strip(), m_.group(2).strip()
                self.setf(w, "company_name", org, path, "公司名后面粘了职位，拆开")
                if pos and pos != role:
                    self.note(f"{path}.position", "公司名后面粘了职位(原职位栏)", pos, role)
                self.setf(w, "position", role, path, "公司名后面粘了职位，拆开")
        # 各字段里的企业性质 / 规模 / 在职时长 / 薪资
        # EN: Enterprise type / size / tenure / salary in each field
        # JA: 各フィールドにある企業の性質・規模・在職期間・給与
        for f in ("company_name", "position", "position_dept", "company_industry"):
            v = s(w.get(f))
            if not v:
                continue
            if K.NATURE_RE.match(v):
                self.setf(w, f, "", path, "企业性质写进了" + f)
            elif K.EMPLOYEES_RE.match(v):
                self.move(w, f, "company_employees", path, "公司规模写进了" + f)
            elif K.SHORT_DURATION_RE.match(v):
                self.setf(w, f, "", path, "在职时长写进了" + f)
            elif f != "company_name" and K.SALARY_RE.search(v):
                m = re.search(r"[\d.,]+\s*[-~～至]\s*[\d.,]+\s*(?:元|RMB)?\s*(?:/\s*(?:月|Mo(?:nth)?))?|[\d.,]+\s*元\s*/\s*月|RMB\s*/\s*Mo(?:nth)?", v, re.I)
                sal = m.group(0).strip() if m else ""
                rest = (v[:m.start()] + v[m.end():]).strip(" |/，,") if m else v
                if sal and not s(w.get("position_salary")):
                    w["position_salary"] = sal
                    self.note(f"{path}.position_salary", "薪资粘在" + f + "(移入)", "", sal)
                self.setf(w, f, rest if not K.SALARY_RE.search(rest) else "", path, "薪资粘在" + f)
        pos = s(w.get("position"))
        if pos:
            core = K.INLINE_DURATION_RE.sub("", pos).strip()
            if core != pos:
                self.setf(w, "position", core, path, "职位里粘了在职时长")
                pos = core
        # 职位里是行业
        # EN: The position contains the industry
        # JA: 職位に業界が入っている
        if pos:
            segs = [x for x in re.split(r"[/／]", pos) if x]
            toks = pos.split()
            if segs and all(re.fullmatch("(" + K.INDUSTRY_TERMS + ")", x) for x in segs) and pos not in K.POSITION_OK_WORDS:
                self.move(w, "position", "company_industry", path, "职位里是行业")
            elif len(toks) > 1 and K.INDUSTRY_SEG_RE.search(toks[-1]):
                ind = toks[-1]
                if not s(w.get("company_industry")):
                    w["company_industry"] = ind
                    self.note(f"{path}.company_industry", "职位里粘了行业(移入)", "", ind)
                self.setf(w, "position", " ".join(toks[:-1]), path, "职位里粘了行业")
        # 职位里是部门
        # EN: The position contains the department
        # JA: 職位に部署が入っている
        pos = s(w.get("position"))
        if pos and re.search(r"(部|科|室|课|部门|本部|事业部|办公室)$", pos) and not re.search(r"(部长|科长|室长|课长|干部)$", pos) \
                and not re.search(r"(交易中心|研究中心|银行|医院|大学|学院|学校|工厂|酒店|商店)$", pos):
            parts = [x.strip() for x in re.split(r"\s*[-|｜/／]\s*|\s+", pos) if x.strip()]
            dpart = [x for x in parts if re.search(r"(部|科|室|课|部门|本部|事业部|办公室)$", x)]
            ppart = [x for x in parts if x not in dpart]
            if dpart and ppart and all(K.POSITION_WORD_RE.search(x) for x in ppart):
                # “医学事务专员-市场部”：职位与部门分开
                # EN: "医学事务专员-市场部" (medical affairs specialist - marketing dept): separate position and department
                # JA: 「医学事务专员-市场部」（メディカルアフェアーズ担当－マーケティング部）：職位と部署を分ける
                if not s(w.get("position_dept")):
                    w["position_dept"] = " ".join(dpart)
                    self.note(f"{path}.position_dept", "职位里粘了部门(移入)", "", w["position_dept"])
                np = pos
                for d in dpart:
                    np = np.replace(d, " ")
                np = re.sub(r"\s{2,}", " ", np).strip(" -|｜/／")
                self.setf(w, "position", np, path, "职位里粘了部门")
            else:
                self.move(w, "position", "position_dept", path, "职位位置是部门名")
        comp, pos = s(w.get("company_name")), s(w.get("position"))
        if comp and pos and C.norm_text(comp) == C.norm_text(pos):
            if K.POSITION_WORD_RE.search(comp) and not K.ORG_SUFFIX_RE.search(comp):
                self.setf(w, "company_name", "", path, "公司名与职位相同（是职位）")
            else:
                self.setf(w, "position", "", path, "职位与公司名相同")
        # 行业字段
        # EN: Industry field
        # JA: 業界のフィールド
        ind, pos = s(w.get("company_industry")), s(w.get("position"))
        if ind and pos and C.norm_text(ind) == C.norm_text(pos):
            self.setf(w, "company_industry", "", path, "行业与职位相同")
        elif ind and K.POSITION_WORD_RE.search(ind) and not K.INDUSTRY_SEG_RE.search(ind):
            if not pos:
                self.move(w, "company_industry", "position", path, "行业位置是职位")
            else:
                self.setf(w, "company_industry", "", path, "行业位置是职位")
        dept = s(w.get("position_dept"))
        if dept and (K.SENT_PUNCT.search(dept) or len(dept) > (60 if K.LATIN_ONLY_RE.match(dept) else 30)):
            w["position_responsibilities"] = (dept + "\n" + s(w.get("position_responsibilities"))).strip()
            self.note(f"{path}.position_responsibilities", "部门栏里的描述(移入)", "", dept)
            self.setf(w, "position_dept", "", path, "部门栏是一句话")
        # 部门字段
        # EN: Department field
        # JA: 部署のフィールド
        dept, pos, ind = s(w.get("position_dept")), s(w.get("position")), s(w.get("company_industry"))
        if dept:
            segs = [x for x in re.split(r"[/／]", dept) if x]
            if pos and C.norm_text(dept) == C.norm_text(pos):
                if re.search(r"(部|科|室|课|处|部门|本部|事业部|办公室|分公司|Dept\.?|Department|Division)\)?$", dept, re.I) \
                        and not re.search(r"(干部|部长|科长|室长|课长|处长)$", dept) and not K.POSITION_WORD_RE.search(dept):
                    self.setf(w, "position", "", path, "职位与部门相同（是部门）")
                else:
                    self.setf(w, "position_dept", "", path, "部门与职位相同")
            elif not K.DEPT_WORD_RE.search(dept) and segs and all(K.DEPT_POSITION_RE.search(x) for x in segs):
                if not pos:
                    self.move(w, "position_dept", "position", path, "部门位置是职位")
                else:
                    self.setf(w, "position_dept", "", path, "部门位置是职位")
            elif ind and C.norm_text(dept) == C.norm_text(ind) and K.DEPT_WORD_RE.search(dept):
                self.setf(w, "company_industry", "", path, "行业位置是部门名")
            elif (ind and C.norm_text(dept) == C.norm_text(ind) and len(dept) > 4) or \
                    (not K.DEPT_WORD_RE.search(dept) and (K.INDUSTRY_SEG_RE.search(dept) or ("/" in dept and C.HAN_RE.search(dept)))) \
                    and not K.SENT_PUNCT.search(dept) and len(dept) <= 30:
                toks = dept.split()
                keep = [x for x in toks if not (K.INDUSTRY_SEG_RE.search(x) or "/" in x)]
                indt = [x for x in toks if K.INDUSTRY_SEG_RE.search(x)]
                keep = [x for x in toks if x not in indt and re.search(r"[A-Za-z一-鿿ぁ-ヺ]", x)]
                if keep and indt:
                    if not s(w.get("company_industry")):
                        w["company_industry"] = " ".join(indt)
                        self.note(f"{path}.company_industry", "部门里粘了行业(移入)", "", w["company_industry"])
                    self.setf(w, "position_dept", " ".join(keep), path, "部门里粘了行业")
                else:
                    self.move(w, "position_dept", "company_industry", path, "部门位置是行业")

    def row_empty(self, lst, it):
        if lst == "work_experiences":
            return not any(s(it.get(f)) for f in ("company_name", "position", "position_responsibilities", "position_achievements"))
        if lst == "education_list":
            # 没有学校、也没有像样的专业：只剩旧工具默认填的“本科/全日制大学”，不是一段学历
            # EN: No school and no proper major: only the "本科/全日制大学" (bachelor / full-time university) defaults filled by old tools remain; this is not an education entry
            # JA: 学校もまともな専攻もなく、旧ツールが既定で入れた「本科／全日制大学」（学士・全日制大学）しか残っていない：これは学歴ではない
            return not s(it.get("school_name")) and not s(it.get("school_major_name"))
        if lst == "training_list":
            return not any(s(it.get(f)) for f in ("organization_name", "training_name", "description", "certificate_name"))
        if lst == "project_list":
            return not any(s(it.get(f)) for f in ("project_name", "description", "responsibilities", "achievements"))
        if lst == "certificate_list":
            return not s(it.get("certificate_name"))
        if lst == "language_list":
            return not s(it.get("language_name"))
        if lst == "skills_list":
            return not s(it.get("skill_name"))
        if lst == "expected_list":
            return not any(s(v) for v in it.values())
        return False

    # ------------------------------------------------------------ 教育
    # EN: ------------------------------------------------------------ Education
    # JA: ------------------------------------------------------------ 学歴
    def school_from(self, mj):
        """从专业栏里取出学校名：返回 (学校, 剩下的专业)。

        EN: Take the school name out of the major column: returns (school, remaining major).

        JA: 専攻欄から学校名を取り出す：(学校, 残りの専攻) を返す。
        """
        tok = mj.split()[0] if mj.split() else ""
        m = SCHOOL_TOKEN_RE.match(tok)
        if m and len(m.group(1)) >= 4:
            sch = m.group(1)
            rest = mj.replace(sch, "", 1)
        else:
            m = SCHOOL_EN_RE.search(mj)
            if not m:
                return "", mj
            sch = m.group(1).strip()
            rest = mj.replace(m.group(1), "", 1)
        rest = re.sub(r"(入学|卒業|毕业|修了)\s*([（(][^）)]*[）)])?\s*$", "", rest.strip()).strip(" ,，|;；")
        return sch, rest

    def edu(self, e, path, lang):
        self.clean_generic(e, path, lang)
        sc, mj = s(e.get("school_name")), s(e.get("school_major_name"))
        dt = s(e.get("school_degree_type"))
        # 三栏错位：学校在学历栏、学历在专业栏、专业在学校栏
        # EN: Three columns misplaced: the school in the degree column, the degree in the major column, the major in the school column
        # JA: 3 列のずれ：学校が学歴欄に、学歴が専攻欄に、専攻が学校欄に入っている
        d3 = next((x for x in DEGREE_WORDS if mj.startswith(x)), "")
        if sc and dt and not K.SCHOOL_RE.search(sc) and not K.TRAINING_ORG_RE.search(sc) and K.SCHOOL_RE.search(dt) \
                and (d3 or not mj) and len(dt) <= 30:
            self.setf(e, "school_name", dt, path, "学校/专业/学历三栏错位")
            self.setf(e, "school_major_name", sc, path, "学校/专业/学历三栏错位")
            self.setf(e, "school_degree_type", d3, path, "学校/专业/学历三栏错位")
            if d3:
                self.setf(e, "school_degree_rank", RANK.get(d3, ""), path, "学校/专业/学历三栏错位")
            sc, mj, dt = s(e.get("school_name")), s(e.get("school_major_name")), s(e.get("school_degree_type"))
        # 学校栏开头是年月（表格错位）：去掉年月
        # EN: The school column starts with a year-month (table misplacement): remove the year-month
        # JA: 学校欄が年月で始まる（表のずれ）：年月を除く
        if sc and not K.SCHOOL_RE.search(sc):
            if DATEY_RE.match(sc):
                new_sc = ""
            else:
                new_sc = DATE_PREFIX_RE.sub("", sc).strip()
            if new_sc != sc:
                if new_sc and not K.SCHOOL_RE.search(new_sc) and not K.TRAINING_ORG_RE.search(new_sc):
                    new_sc = ""
                self.setf(e, "school_name", new_sc, path, "学校栏是年月/开头粘了年月")
                sc = new_sc
        # 学校栏是栏目名/学历名
        # EN: The school column is a section name / degree name
        # JA: 学校欄が欄の名前・学歴名になっている
        nsc = C.norm_text(sc)
        if sc and not K.SCHOOL_RE.search(sc) and (nsc in EDU_LABELS or sc in EDU_DEGREE_WORDS or nsc in EDU_DEGREE_WORDS):
            d = EDU_DEGREE_WORDS.get(sc, EDU_DEGREE_WORDS.get(nsc, ""))
            if d and not dt:
                self.setf(e, "school_degree_type", d, path, "学校栏是学历名，移到学历栏")
                self.setf(e, "school_degree_rank", RANK.get(d, ""), path, "学校栏是学历名，移到学历栏")
            self.setf(e, "school_name", "", path, "学校栏是栏目名/学历名")
            sc = ""
        # 学校栏空、专业栏里是学校（“关东学院大学经济学部 经营管理学专业入学”）
        # EN: The school column is empty and the major column contains the school ("关东学院大学经济学部 经营管理学专业入学")
        # JA: 学校欄が空で、専攻欄に学校が入っている（「关东学院大学经济学部 经营管理学专业入学」）
        if not sc and mj and K.SCHOOL_RE.search(mj) and not re.search(r"(奖学金|奨学金|奖|賞|荣誉|称号)", mj):
            sch, rest = self.school_from(mj)
            if sch:
                self.setf(e, "school_name", sch, path, "专业栏里是学校，移到学校栏")
                self.setf(e, "school_major_name", rest, path, "专业栏里是学校，移到学校栏")
        sc, mj = s(e.get("school_name")), s(e.get("school_major_name"))
        if sc and C.norm_text(sc) in {C.norm_text(x) for x in K.PLACEHOLDER_SCHOOL}:
            self.setf(e, "school_name", "", path, "学校名是占位词")
            sc = ""
        if mj and sc and C.norm_text(mj) == C.norm_text(sc):
            self.setf(e, "school_major_name", "", path, "专业与学校名相同")
        elif mj and re.search(r"(大学|学院|学校|University|College)$", mj, re.I) and not sc:
            self.move(e, "school_major_name", "school_name", path, "专业位置是学校名")
        mj = s(e.get("school_major_name"))
        if mj and MAJOR_CUT_RE.search(mj):
            new = MAJOR_CUT_RE.sub("", mj).strip()
            self.setf(e, "school_major_name", new, path, "专业后面粘了其他栏目")
        mj = s(e.get("school_major_name"))
        if mj and re.search(r"(有限公司|有限会社|株式会社|Co\.,?\s*Ltd)", mj, re.I):
            self.setf(e, "school_major_name", "", path, "专业栏是公司名")
        sc, mj = s(e.get("school_name")), s(e.get("school_major_name"))
        if sc and (sc in K.PLACE_NAMES or sc in ("日本国", "中国大陆") or re.fullmatch(r"[一-鿿]{2,4}(市|省|区|县)", sc)
                   or re.fullmatch(r"[一-鿿]{2,3}-[一-鿿]{1,5}", sc)) and not K.SCHOOL_RE.search(sc):
            m_ = re.search(r"([一-鿿ぁ-ヺーA-Za-z]{2,30}(大学院|大学|学院|学校|語学院|语学院|高校|中学))", mj)
            if m_:
                self.setf(e, "school_name", m_.group(1), path, "学校栏是地名，专业栏里是学校")
                self.setf(e, "school_major_name", mj.replace(m_.group(1), "").strip(), path, "学校栏是地名，专业栏里是学校")
            else:
                self.setf(e, "school_name", "", path, "学校栏是地名")
        sc, mj = s(e.get("school_name")), s(e.get("school_major_name"))
        if not sc and mj and (K.SENT_PUNCT.search(mj) or re.search(r"\d", mj) or len(mj) > 20 or len(mj) < 2 or K.LABEL_RE.search(mj)):
            self.setf(e, "school_major_name", "", path, "无学校的学历行里专业是其他内容")
        dt = s(e.get("school_degree_type"))
        if dt and (re.search(r"\d{4}", dt) or (len(dt) > 12 and lang in ("zh", "jp"))):
            d = next((x for x in DEGREE_WORDS if re.search(r"(^|[\s　])" + x + r"(学位|学士|毕业|$|[\s　])", dt)), "") if len(dt) <= 30 else ""
            self.setf(e, "school_degree_type", d, path, "学历字段里有其他内容")
            dt = d
        rk = s(e.get("school_degree_rank"))
        for k, v in (("博士后", "7"), ("博士", "6"), ("硕士", "5"), ("研究生", "5"), ("MBA", "5"), ("EMBA", "5"), ("本科", "4"),
                     ("学士", "4"), ("大专", "3"), ("专科", "3"), ("高中", "2"), ("中专", "2")):
            if dt.startswith(k):
                if rk and rk != v:
                    self.setf(e, "school_degree_rank", v, path, "学历级别与学历名称不一致")
                break

    # ------------------------------------------------------------ 其他列表
    # EN: ------------------------------------------------------------ Other lists
    # JA: ------------------------------------------------------------ その他のリスト
    def other(self, lst, it, path, lang):
        self.clean_generic(it, path, lang)
        if lst == "language_list":
            lv = s(it.get("language_level"))
            if lv and re.search(r"(股份|公司|有限)", lv):
                new = re.sub(r"^.*?(股份有限公司|有限公司|股份|公司|有限)\s*", "", lv).strip()
                new = re.sub(r"^[（(]\s*(.*?)\s*[)）]", r"\1", new).strip()
                self.setf(it, "language_level", new if not re.search(r"(股份|公司|有限)", new) else "", path, "语言等级里粘了公司名")
            elif lv and lv.count("(") != lv.count(")"):
                new = lv + ")" * (lv.count("(") - lv.count(")")) if lv.count("(") > lv.count(")") else lv.replace(")", "", lv.count(")") - lv.count("("))
                self.setf(it, "language_level", new, path, "括号补齐")
        elif lst == "expected_list":
            for f in ("expected_city", "expected_position", "expected_industry", "expected_salary"):
                v = s(it.get(f))
                if v and K.EXPECT_LABEL_RE.search(v):
                    self.setf(it, f, "", path, "期望栏里是其他栏目标签")
            bad = {"expected_city": r"(大学|学院|院校|职能|职位|工程训练|勿推|月薪|设计|专业|艺术|管理)",
                   "expected_position": r"^(月薪范围|期望月薪|勿推.*)$", "expected_salary": r"(勿推|企业$|大学|学院)"}
            for f, pat in bad.items():
                v = s(it.get(f))
                if v and "不显示" not in v and re.search(pat, v):
                    self.setf(it, f, "", path, "期望栏的值放错了")
        elif lst == "training_list":
            org, tn = s(it.get("organization_name")), s(it.get("training_name"))
            if org and re.fullmatch(r"[\d\s.\-年月]+", org):
                self.setf(it, "organization_name", "", path, "培训机构是日期")
            if tn and re.fullmatch(r"[\d\s.\-年月]+", tn):
                self.setf(it, "training_name", "", path, "培训名称是日期")
        elif lst == "certificate_list":
            nm = s(it.get("certificate_name"))
            if nm and re.fullmatch(r"[（(]?[\d.]+[）)]?", nm):
                self.setf(it, "certificate_name", "", path, "证书名是数字")

    def work_to_edu(self, res, prefix, prov):
        """工作栏里其实是学历的条目（“苏州大学 工商管理 本科”，没有职位也没有职责）：学历里已有同一学校就删掉，否则移到学历栏。

        EN: Entries in the work column that are actually education ("苏州大学 工商管理 本科", with neither position nor duties): delete if education already has the same school, otherwise move to the education column.

        JA: 職歴欄に入っているが実は学歴である項目（「苏州大学 工商管理 本科」で職位も職務もない）：学歴に同じ学校がすでにあれば削除し、なければ学歴欄に移す。
        """
        works = res.get("work_experiences") or []
        edus = res.setdefault("education_list", [])
        keep = []
        for i, w in enumerate(works):
            comp, pos, resp = s(w.get("company_name")), s(w.get("position")), s(w.get("position_responsibilities"))
            has_job = len(pos) >= 2 and not K.is_section_word(pos) and not re.search(r"[:：]$", pos)
            if comp and K.SCHOOL_RE.search(comp) and not re.search(r"(公司|会社|集团|Co\.|Ltd|Inc|医院|Hospital)", comp, re.I) \
                    and not has_job and len(resp) < 15 and not K.too_long(comp) and not K.SENT_PUNCT.search(comp) \
                    and not re.search(r"(学生会|社团|协会|团委|实践|活动|志愿|奖学金|奨学金|奖|賞|队|隊|部活|サークル|クラブ|俱乐部|Club|Team|先生|老师|教师|讲师|担当|した|です|ます|留学生会|设立|運営|运营)", comp, re.I) \
                    and not re.search(r"^[\d年度]+", comp):
                toks = comp.split()
                if K.SCHOOL_RE.search(toks[0]):
                    school, rest = toks[0], " ".join(toks[1:])
                else:
                    m = re.match(r"^\s*(.+(?:大学院|大学|学院|学校|大學|學院|University|College|School))\s*(.*)$", comp, re.I)
                    school = m.group(1).strip() if m else comp
                    rest = m.group(2).strip() if m else ""
                same = [e for e in edus if C.norm_entity(e.get("school_name")) and (C.norm_entity(e.get("school_name")) in C.norm_entity(school)
                                                                                    or C.norm_entity(school) in C.norm_entity(e.get("school_name")))]
                if same:
                    self.note(f"{prefix}.work_experiences[{i}]", "工作栏里是学历，学历栏已有同一学校，删除", comp, "")
                    continue
                e = {k: "" for k in C.LIST_FIELDS["education_list"]}
                e["school_name"] = school
                dm = DEGREE_IN_TEXT_RE.search(rest)
                if dm:
                    e["school_degree_type"] = dm.group(1)
                    e["school_degree_rank"] = RANK.get(dm.group(1), "")
                    rest = rest.replace(dm.group(1), " ")
                e["school_major_name"] = re.sub(r"\s+", " ", rest).strip(" |")
                e["school_start_ym"], e["school_end_ym"] = s(w.get("position_start")), s(w.get("position_resigned")) if s(w.get("position_resigned")) != "至今" else ""
                edus.append(e)
                self.note(f"{prefix}.work_experiences[{i}]", "工作栏里是学历，移到学历栏", comp, school)
                if prov is not None and "education_list" in (prov.get("lists") or {}):
                    wl = (prov.get("lists") or {}).get("work_experiences") or []
                    prov["lists"]["education_list"].append(wl[i] if i < len(wl) else [0])
                continue
            keep.append((i, w))
        if len(keep) != len(works):
            if prov is not None and "work_experiences" in (prov.get("lists") or {}):
                wl = prov["lists"]["work_experiences"]
                prov["lists"]["work_experiences"] = [wl[i] for i, _ in keep if i < len(wl)]
            res["work_experiences"] = [w for _, w in keep]

    def birth_fix(self, res, path):
        """出生日期比本人的学历/工作日期还晚或只早几年（“2013年08月01日”这类，是别的日期填错了位置）：清掉。

        EN: A birth date later than, or only a few years earlier than, the person's education/work dates (like "2013年08月01日", another date put in the wrong place): clear it.

        JA: 生年月日が本人の学歴・職歴の日付より後か、数年しか前でない（「2013年08月01日」のように、別の日付が誤った場所に入ったもの）：空にする。
        """
        b = res.get("base_info") or {}
        bd = s(b.get("birth_date"))
        p = C.parse_ym(bd)
        by = p[0] if p else (int(s(b.get("birth_year"))) if s(b.get("birth_year")).isdigit() else None)
        if not by:
            return
        years = []
        for lst, fs in (("education_list", ("school_start_ym", "school_end_ym")), ("work_experiences", ("position_start", "position_resigned"))):
            for it in res.get(lst) or []:
                for f in fs:
                    q = C.parse_ym(s(it.get(f)))
                    if q and 1950 <= q[0] <= 2030 and not (p and q[0] == p[0] and q[1] == p[1]) and not (not p and q[0] == by):
                        years.append(q[0])
        if len(years) < 2:
            return
        if by > min(years) - 5 or max(years) - by < 15:
            self.setf(b, "birth_date", "", path, "出生日期与本人学历/工作日期矛盾（别的日期填错位置）")
            if s(b.get("birth_year")):
                self.setf(b, "birth_year", "", path, "出生日期与本人学历/工作日期矛盾（别的日期填错位置）")
            age = s(b.get("age"))
            if age.isdigit() and int(age) < 15:
                self.setf(b, "age", "", path, "出生日期与本人学历/工作日期矛盾（别的日期填错位置）")

    def edu_rows(self, res, prefix, prov):
        """学历栏里其实是证书 / 工作经历 / 别处已有的句子：证书移到证书栏，工作移到工作栏，别处已有的删掉。

        EN: The education column actually contains certificates / work history / sentences already present elsewhere: move certificates to the certificate column and work to the work column, and delete what exists elsewhere.

        JA: 学歴欄に実は資格・職歴・他の場所にすでにある文が入っている：資格は資格欄に、職歴は職歴欄に移し、他の場所にすでにあるものは削除する。
        """
        edus = res.get("education_list") or []
        if not edus:
            return
        hay_parts = []
        for k, v in res.items():
            if k == "education_list":
                continue
            if isinstance(v, dict):
                hay_parts += [s(x) for x in v.values() if isinstance(x, str)]
            elif isinstance(v, list):
                for it in v:
                    if isinstance(it, dict):
                        hay_parts += [s(x) for x in it.values() if isinstance(x, str)]
            elif isinstance(v, str):
                hay_parts.append(v)
        hay = C.norm_text("\n".join(hay_parts))

        def covered(v):
            toks = [x for x in re.split(r"[\s\t]+", v) if x]
            toks = [x for x in toks if not (K.is_section_word(x) or C.norm_text(x) in EDU_LABELS or DATEY_RE.match(x)
                                            or x in ("離社原因", "会社名称", "時間", "公司", "人物描写：", "自我介绍"))]
            toks = [C.norm_text(re.sub(r"^(人物描写|自我介绍|離社原因)[:：]?", "", x)) for x in toks]
            toks = [x for x in toks if len(x) >= 2]
            return bool(toks) and sum(len(x) for x in toks) >= 6 and all(x in hay for x in toks)

        certs = res.setdefault("certificate_list", [])
        works = res.setdefault("work_experiences", [])
        cert_names = [C.norm_text(c.get("certificate_name")) for c in certs]
        work_names = [C.norm_entity(w.get("company_name")) for w in works]
        pl = (prov.get("lists") or {}) if prov is not None else {}
        el = pl.get("education_list") or []
        keep = []
        for i, e in enumerate(edus):
            path = f"{prefix}.education_list[{i}]"
            sc, mj, dt = s(e.get("school_name")), s(e.get("school_major_name")), s(e.get("school_degree_type"))
            src = el[i] if i < len(el) else [0]
            sc0 = DATE_PREFIX_RE.sub("", sc).strip()
            if not sc or DATEY_RE.match(sc) or K.SCHOOL_RE.search(sc0) or K.RESEARCH_ORG_RE.search(sc0):
                keep.append((i, e))
                continue
            # 1) 证书
            # EN: 1) Certificates
            # JA: 1) 資格
            cand, when = [], ""
            for v in (sc0, mj):
                if C.norm_text(v) in EDU_LABELS:
                    continue
                vv = DATE_PREFIX_RE.sub("", v).strip()
                if vv != v.strip() and not when:
                    when = v.strip()[:len(v.strip()) - len(vv)].strip()
                if vv and EDU_CERT_RE.search(vv) and not re.search(r"(学习|培训|课程|辅导|学校|学院|大学(?!英))", vv) and len(vv) <= 40 \
                        and not K.SENT_PUNCT.search(vv):
                    cand.append(vv)
            others = [v for v in (sc0, mj) if v and DATE_PREFIX_RE.sub("", v).strip() not in cand and not DATEY_RE.match(v)
                      and C.norm_text(v) not in EDU_LABELS]
            mj_school = len(others) == 1 and others[0] == mj and K.SCHOOL_RE.search(mj) and not EDU_CERT_RE.search(mj) \
                and not K.SENT_PUNCT.search(mj) and len(mj) <= 30 and not DATE_PREFIX_RE.match(mj)
            if cand and (not others or mj_school):
                for c in cand:
                    nc = C.norm_text(c)
                    if any(nc and (nc in x or x in nc) for x in cert_names if x):
                        self.note(path, "学历栏里是证书，证书栏已有，删除", c, "")
                        continue
                    ci = {k: "" for k in C.LIST_FIELDS["certificate_list"]}
                    ci["certificate_name"] = c
                    ci["certificate_time"] = when or s(e.get("school_end_ym")) or s(e.get("school_start_ym"))
                    certs.append(ci)
                    cert_names.append(nc)
                    if "certificate_list" in pl:
                        pl["certificate_list"].append(src)
                    self.note(path, "学历栏里是证书，移到证书栏", c, c)
                if others:  # 证书 + 学校（“上海市计算机应用能力考核中级 | 上海太陽光科学開発学校”）
                # EN: Certificate + school ("上海市计算机应用能力考核中级 | 上海太陽光科学開発学校")
                # JA: 資格 + 学校（「上海市计算机应用能力考核中级 | 上海太陽光科学開発学校」）
                    self.setf(e, "school_name", mj, path, "学历栏里是证书，专业栏是学校")
                    self.setf(e, "school_major_name", "", path, "学历栏里是证书，专业栏是学校")
                    keep.append((i, e))
                continue
            # 2) 工作经历
            # EN: 2) Work history
            # JA: 2) 職歴
            if EDU_COMPANY_RE.search(sc) and not K.TRAINING_ORG_RE.search(sc0) and not re.search(r"(Master|硕士|博士|MBA)", dt, re.I):
                comp = re.sub(r"^(時間\s*)?会社名称\s*", "", sc0)
                comp = re.sub(r"^(公司|Company Name)\s*[:：]?\s*", "", comp, flags=re.I)
                comp = re.sub(r"\s+\d+\s*(以上|以下)?$", "", comp)
                comp = re.sub(r"[（(]\s*\d+\s*(年|years?)?\s*\d*\s*(个?月|months?)?\s*[)）]?$", "", comp, flags=re.I).strip()
                nce = C.norm_entity(comp)
                if nce and any(x and (nce in x or x in nce) for x in work_names):
                    self.note(path, "学历栏里是工作经历，工作栏已有，删除", sc, "")
                    continue
                pos = ""
                m = re.match(r"^(职位|Job Title)\s*[:：]\s*(.+)$", dt, re.I)
                if m:
                    pos = m.group(2).strip()
                resp = ""
                if mj and not DATEY_RE.match(mj):
                    if not pos and len(mj) <= 15 and not re.search(r"[\d，。；;]", mj):
                        pos = mj
                    else:
                        resp = mj
                w = {k: "" for k in C.LIST_FIELDS["work_experiences"]}
                w.update(company_name=comp, position=pos, position_responsibilities=resp,
                         position_start=s(e.get("school_start_ym")), position_resigned=s(e.get("school_end_ym")))
                works.append(w)
                work_names.append(nce)
                if "work_experiences" in pl:
                    pl["work_experiences"].append(src)
                self.note(path, "学历栏里是工作经历，移到工作栏", sc, comp)
                continue
            # 3) 别处已有的句子/栏目内容
            # EN: 3) Sentences/section content already present elsewhere
            # JA: 3) 他の場所にすでにある文や欄の内容
            if not K.SCHOOL_RE.search(mj) and covered(sc) and (not mj or covered(mj) or DATEY_RE.match(mj)) \
                    and not re.search(r"(硕士|博士|Master|Bachelor|Doctor|PhD|MBA)", dt + sc, re.I):
                self.note(path, "学历栏里是其他栏目的内容，别处已有，删除", sc, "")
                continue
            keep.append((i, e))
        if len(keep) != len(edus):
            if "education_list" in pl:
                pl["education_list"] = [el[i] for i, _ in keep if i < len(el)]
            res["education_list"] = [e for _, e in keep]

    def resume(self, res, prefix, prov=None):
        lang = s(res.get("resume_languge")) or "zh"
        self.work_to_edu(res, prefix, prov)
        self.edu_rows(res, prefix, prov)
        self.base(res.setdefault("base_info", {}), f"{prefix}.base_info", lang)
        self.birth_fix(res, f"{prefix}.base_info")
        self.pr_fix(res, f"{prefix}.base_info")
        for lst in C.LIST_ORDER:
            items = res.get(lst) or []
            keep = []
            for i, it in enumerate(items):
                p = f"{prefix}.{lst}[{i}]"
                if lst == "work_experiences":
                    self.work(it, p, lang)
                elif lst == "education_list":
                    self.edu(it, p, lang)
                else:
                    self.other(lst, it, p, lang)
                if self.row_empty(lst, it):
                    self.note(p, "清理后整条为空，删除", "", "")
                    continue
                key = json.dumps({k: v for k, v in it.items() if k != "sequence_no"}, ensure_ascii=False, sort_keys=True)
                if any(json.dumps({k: v for k, v in x.items() if k != "sequence_no"}, ensure_ascii=False, sort_keys=True) == key for x in keep):
                    self.note(p, "清理后与前一条完全相同，删除", "", "")
                    continue
                keep.append(it)
            if len(keep) != len(items):
                if prov is not None and lst in (prov.get("lists") or {}):
                    pl = prov["lists"][lst]
                    prov["lists"][lst] = [pl[k] for k, it in enumerate(items) if any(it is x for x in keep) and k < len(pl)]
                res[lst] = keep
                if lst in ("project_list", "training_list"):
                    for n, it in enumerate(keep, 1):
                        it["sequence_no"] = n


def normalize_resumes(resumes, log, source, provs=None):
    n = Normalizer(log, source)
    for i, res in enumerate(resumes):
        n.resume(res, f"resumes[{i}]", provs[i] if provs else None)
