#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
claude_merge_checks.v3.py —— 合并后 JSON 的结构与字段校验。

每条问题：{"field_path", "value", "issue_type", "severity", "note"}
severity:
  high   = 值放错字段 / 栏目标题或标签残留当作值 / 非学校当学校 / 乱码 / 明显不合理（出生日期晚于简历日期等）
  medium = 格式不规范 / 枚举不合法 / 可疑但可能正确
  low    = 提示性（需要人工看一眼）
规则来源：2026-09-26 对 merge-v3 首轮全量输出抽样 172 份人工核对发现的问题类型，以及 CONTEXT.md 字段契约。

EN: claude_merge_checks.v3.py -- structural and field validation of merged JSON.

Each issue: {"field_path", "value", "issue_type", "severity", "note"}
severity:
  high   = value in the wrong field / section title or label left over as a value / non-school used as school / garbled text / obviously unreasonable (birth date later than the résumé date, etc.)
  medium = non-standard format / invalid enum / suspicious but possibly correct
  low    = informational (needs a human glance)
Rule sources: issue types found on 2026-09-26 by manually checking a sample of 172 files from the first full merge-v3 output, plus the CONTEXT.md field contract.

JA: claude_merge_checks.v3.py —— 統合後の JSON の構造とフィールドの検証。

各問題：{"field_path", "value", "issue_type", "severity", "note"}
severity：
  high   = 値の置き間違い / 欄の見出しやラベルが値として残っている / 学校でないものが学校になっている / 文字化け / 明らかに不合理（生年月日が履歴書の日付より後など）
  medium = 形式が規範的でない / 列挙値が不正 / 疑わしいが正しい可能性もある
  low    = 注意喚起（人が一度見る必要がある）
ルールの出所：2026-09-26 に merge-v3 の最初の全件出力から 172 件を抽出して人手で確認した問題の種類、および CONTEXT.md のフィールドの約束。
"""

import re
from pathlib import Path
import importlib.util

_spec = importlib.util.spec_from_file_location("claude_merge_common_v3_checks", Path(__file__).resolve().parent / "claude_merge_common.v3.py")
C = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(C)
s = C.s

# ---------------------------------------------------------------- 词表与模式
# EN: ---------------------------------------------------------------- Vocabularies and patterns
# JA: ---------------------------------------------------------------- 語彙とパターン
GARBLED_RE = re.compile(r"�|锟斤拷|烫烫烫|屯屯屯|Ã.|â€|\?{4,}")
HTML_RE = re.compile(r"</?[a-zA-Z][^>]{0,40}>|&(nbsp|amp|lt|gt|quot|#\d+);")
PUNCT_ONLY_RE = re.compile(r"^[\s\W_\d.]+$")
SENT_PUNCT = re.compile(r"[，。；！？;]")


def too_long(v: str) -> bool:
    """名称过长像句子：中日文 40 字；英文名称天然更长（University of … / … Co., Ltd.），按 80 字。

    EN: Names so long they look like sentences: 40 characters for Chinese/Japanese; English names are naturally longer (University of … / … Co., Ltd.), so 80 characters.

    JA: 文のように長すぎる名前：中国語・日本語は 40 文字、英語の名前はもともと長い（University of … / … Co., Ltd.）ため 80 文字。
    """
    latin = len(re.findall(r"[A-Za-z]", v))
    cjk = len(re.findall(r"[一-鿿ぁ-ヺ]", v))
    return len(v) > (80 if latin > cjk * 2 else 40)
DATE_OK_RE = re.compile(r"^\d{4}年\d{2}月\d{2}日$")

# 栏目标题（中/日/英），去空格后整值等于这些词，或以这些词开头并跟冒号
# EN: Section headings (Chinese/Japanese/English): after removing spaces, the whole value equals one of these words, or starts with one of them followed by a colon
# JA: 欄の見出し（中国語・日本語・英語）：空白を除いた値全体がこれらの語と等しいか、これらの語で始まりコロンが続くもの
SECTION_WORDS = [
    "職歴", "学歴", "資格", "免許", "賞罰", "自己紹介", "自己PR", "志望動機", "職務経歴", "職務内容", "学歴職歴", "趣味", "特技",
    "工作经历", "工作经验", "教育经历", "教育背景", "项目经历", "项目经验", "培训经历", "证书", "所获证书", "语言能力", "技能特长",
    "专业技能", "自我评价", "个人评价", "求职意向", "期望工作", "基本信息", "个人信息", "个人资料", "联系方式", "在校经历", "实践经历",
    "实践描述", "培训描述", "活动描述", "项目描述", "工作描述", "在校学习情况", "社会实践", "获奖情况", "奖励情况", "海外经历",
    "在校实践经历", "培训地点", "所获奖项", "所获奖励", "奖项", "获奖经历", "技能证书", "证书名称", "IT技能", "语言技能", "所在", "个人技能", "求职信", "发表论文", "简历内容", "特殊技能", "description", "responsibilities",
    "workexperience", "education", "educationbackground", "skills", "summary", "profile", "objective", "personalinformation",
]
SECTION_SET = {C.norm_text(w) for w in SECTION_WORDS}
# 标签残留：“xxx：”形式的字段名混入值中
# EN: Leftover labels: field names of the form "xxx：" mixed into values
# JA: ラベルの残骸：「xxx：」の形式のフィールド名が値に混入したもの
LABEL_RE = re.compile(
    r"(企业性质|公司性质|公司规模|公司行业|所属行业|所在地区|工作地点|下属人数|汇报对象|汇报人|职位名称|担当職位|企業性質|所在地|"
    r"会社概要|職位|手机|电话|電話|e-?mail|邮箱|邮编|性别|性別|年龄|出生|籍贯|户口|民族|婚姻|身高|体重|学历|专业|学校|"
    r"培训地点|培训机构|培训描述|实践描述|活动描述|项目描述|Period|Company|Occupation|Position)\s*[:：]", re.I)
SALARY_RE = re.compile(r"\d{3,}\s*[-~～至]\s*\d{3,}\s*(元|RMB|/月|/Mo)|\d{3,}\s*元\s*/\s*月|RMB\s*/\s*Mo|/\s*Mo\b", re.I)
DURATION_RE = re.compile(r"^\(?\s*\d+\s*年\s*\d*\s*个?月?\s*\)?$|^（\s*\d+\s*年|\d+年間|\d+ヶ月")
ORG_SUFFIX_RE = re.compile(r"(公司|集团|会社|株式会社|有限|工厂|厂$|研究院|研究所|研究中心|银行|医院|事务所|办事处|代表处|中心|政府|协会|"
                           r"学会|大学|学院|学校|店$|商店|酒店|宾馆|局$|处$|委员会|部$|站$|院$|所$|社$|馆$|"
                           r"Co\.?|Ltd|Inc|Corp|Company|Group|GmbH|LLC|Bank|Hospital|University|Center|Centre)", re.I)
SCHOOL_RE = re.compile(r"(カレッジ|学園|専門学校|附中|附属中学|一中|二中|三中|大学|学院|学校|分校|大専|短大|短期大学|大学院|高校|高等学校|中学|小学|高专|高職|职高|技校|中专|专科|党校|夜大|函授|电大|電大|广播电视大学|"
                       r"高中|卫校|職校|职校|师范|師範|师大|理工$|工大$|农大$|医大$|财大$|学堂|技工|完小|[一二三四五六七八九十]+中$|中学校|語学|语言学校|日本語学校|日语学校|外语学校|日本語科|"
                       r"大學|學院|學校|學園|美校|美院|师专|師専|商专|医专|医科$|职院|技师$|院校|女校|初中|研究生院|"
                       r"Senior High|High School|[EÉ]cole|Institut\b|Colleage|Schule|"
                       r"University|College|Institute|School|Academy|Universität|Hochschule|Polytechnic|Univ\.?\b|Uni\b)", re.I)
# 培训/语言学校/进修机构（不是学历教育，但确实是教育机构）
# EN: Training / language schools / continuing-education institutions (not degree education, but definitely educational institutions)
# JA: 研修・語学学校・進修機関（学歴の教育ではないが、確かに教育機関である）
TRAINING_ORG_RE = re.compile(r"(教育|培训|進修|进修|日语|日本語|日本语|英语|英語|韩语|外国语|外國語|语言|語学|语学|文化馆|文化館|学园|学馆|网校|網校|学城|"
                             r"考研|会计在线|会計オンライン|青鸟|华尔街|Wall Stree|Well Street|韦博|ゼミナール|スクール|アカデミ|センター|中心$|协会|協会|"
                             r"Academy|学塾|塾$)", re.I)
RESEARCH_ORG_RE = re.compile(r"(研究院|研究所|研究总院|研究中心|重点实验室|社科院|科学院)")
ABBR_BAD_RE = re.compile(r"(公司|会社|集团|科技|电子|電子|贸易|商贸|工贸|物流|实业|医療|人寿|银行|酒店|饭店|超市|Co\b|Ltd|Inc)", re.I)
LOW_SCHOOL_RE = re.compile(r"(小学|初中|中学|高中|高校|高等学校|职高|中专|技校)")
MAJOR_HINT = re.compile(r"(专业|系$|工程$|管理$|文学$|技术$|经济$|会计$|学$)")
TRAINING_HINT = re.compile(r"(培训|认证|咨询有限公司|内审员|研修|講習|课程)")
CITY_BAD_RE = re.compile(r"(専攻|专业|大学|学院|公司|职能|职位|院校|工程训练|手机|电话|邮箱|[:：])")
PROVINCE_AS_CITY = {"广东市", "江苏市", "浙江市", "山东市", "河南市", "河北市", "湖南市", "湖北市", "四川市", "安徽市", "福建市", "江西市",
                    "辽宁市", "黑龙江市", "山西市", "陕西市", "云南市", "贵州市", "广西市", "甘肃市", "海南市"}
PLACE_NAMES = {"北京", "上海", "天津", "重庆", "广州", "深圳", "杭州", "南京", "苏州", "成都", "武汉", "西安", "大连", "青岛", "厦门", "宁波",
               "无锡", "沈阳", "长沙", "郑州", "济南", "合肥", "福州", "昆山", "东莞", "佛山", "珠海", "日本", "中国", "香港", "台湾", "东京", "大阪"}
HONOR_RE = re.compile(r"(奖学金|三好|优秀|奖$|等奖|一等|二等|三等|学生会|主席|部长|辅导员|演讲比赛|比赛|竞赛|荣誉|称号|活动描述|志愿者|团干部|干部)")
LANG_CERT_RE = re.compile(r"(CET|TEM|JLPT|\bN[1-5]\b|TOEIC|TOEFL|IELTS|BEC|托业|托福|雅思|日语|日本語|英语|英語|大学英语|能力试验|能力試験|能力考试|PETS)", re.I)
EXPECT_BAD_RE = re.compile(r"(大学|学院|院校|职能|职位[:：]|月薪范围|勿推|企业$|工程训练)")
ZH_MARITAL = {"已婚", "未婚", "离异", "离婚", "丧偶", "已婚已育", "已婚未育", "未婚未育", "保密"}
POSITION_WORD_RE = re.compile(r"(专员|助理|经理|主管|总监|工程师|代表|担当|文员|秘书|实习|实习生|老师|教师|翻译|采购员|销售员|会计|出纳|"
                              r"设计师|技术员|操作员|店员|营业员|客服|前台|编辑|顾问|司机|厨师|负责人|主任|课长|部长|家教|兼职)$|^(实习|兼职|家教|销售|采购|营业)$")
FRAGMENT_RE = re.compile(r"^(对|为|在|于|相当|负责|主要|通过|担任|以及)|^(和|与)(?=.*[，。、；,;])|等$|。$")
INDUSTRY_TERMS = ("教育|培训|院校|旅游|度假|贸易|进出口|制造|互联网|电子商务|医疗|医疗设备|器械|房地产|金融|广告|会展|公关|市场推广|物流|"
                  "餐饮|酒店|计算机软件|计算机硬件|计算机服务|IT服务|通信|电信|电子技术|半导体|集成电路|快速消费品|耐用消费品|服装|纺织|"
                  "皮革|家具|家电|机械|机械制造|设备|重工|汽车|摩托车|零配件|制药|生物工程|化工|能源|矿产|环保|建筑|建材|工程|咨询|"
                  "法律|会计|审计|人力资源|银行|保险|证券|投资|基金|信托|租赁|拍卖|典当|检测|认证|印刷|包装|造纸|媒体|出版|影视|"
                  "文化|传播|娱乐|体育|休闲|批发|零售|百货|超市|交通|运输|仓储|航空|航天|农业|林业|牧业|渔业|政府|公共事业|非盈利机构|"
                  "农|林|牧|渔|农/林/牧/渔|学术|科研|外包服务|专业服务|中介服务|其他|多元化业务集团公司|新能源|大型设备|机电设备|仪器仪表|工业自动化|"
                  "网络游戏|电子商务|原材料|汽车制造|服装|服装服饰|电气|电力|水利|石油|石化|加工|美容|保健|家居|室内设计|装潢|物业管理|商业中心|酒店/旅游|贸易/进出口")
INDUSTRY_WORD_RE = re.compile(r"^(" + INDUSTRY_TERMS + r")(/|$)")
INDUSTRY_SEG_RE = re.compile(r"(^|/)(" + INDUSTRY_TERMS + r")(/|$)")
DEPT_WORD_RE = re.compile(r"(部|科|室|课|处|组|中心|团队|事业|本部|部门|车间|分部|分公司|办公室|Dept|Department|Division|Team)", re.I)
INLINE_DURATION_RE = re.compile(r"[（(]\s*\d+\s*(个月|个?年|年\s*\d+\s*个?月|ヶ月|か月|months?|years?)\s*[）)]", re.I)
COMPANY_SENT_WORDS = re.compile(r"(包括|负责|主要|我们|本人|以及|评价|考核|获得|完成|参与|协助|期间|担任|工作内容|任职)")
POSITION_OK_WORDS = {"会计", "审计", "法律", "咨询", "人力资源", "检测", "认证", "设计", "翻译", "销售", "采购"}
DEPT_POSITION_RE = re.compile(r"(专员|助理|经理|主管|总监|工程师|代表|担当|文员|秘书|实习生|老师|教师|采购员|销售员|设计师|技术员|操作员|"
                              r"店员|营业员|司机|厨师|负责人|主任|课长|部长)$")
LATIN_ONLY_RE = re.compile(r"^[A-Za-z][A-Za-z\s\-.,]*$")
PLACEHOLDER_SCHOOL = {"学校", "大学", "学院", "school", "university", "college", "学校名称", "学校名", "培训机构", "实践描述",
                      "Name of school", "The University", "School name", "high school", "Middle School"}
PLACEHOLDER_COMPANY = {"公司", "公司名称", "company", "单位", "工作单位", "个人", "无", "应聘公司", "搜索同事", "所在", "所在公司", "目前公司", "当前公司"}
NATURE_RE = re.compile(r"^(外资|合资|国企|民营|私营|外企|国有企业|上市公司|事业单位|股份制企业|外商独资|中外合资)[（(]?[^)）]{0,8}[)）]?$")
EMPLOYEES_RE = re.compile(r"^\d+\s*[-~～至]\s*\d+\s*人$|^\d+\s*人(以上|以下)$|^少于\s*\d+\s*人$")
SHORT_DURATION_RE = re.compile(r"^[（(]?\s*\d+\s*(个月|个?年|年\s*\d+\s*个?月|ヶ月|か月)\s*[）)]?$")
EXPECT_LABEL_RE = re.compile(r"(期望从事行业|期望从事职业|期望工作地区|期望月薪|目前状况|工作性质)")
COUNTRY_CITY_RE = re.compile(r"^(日本|中国|美国|韩国|英国|德国|法国|加拿大|澳大利亚|新加坡|泰国|越南|印度|巴西|俄罗斯)市$")


def _issue(path, value, itype, severity, note=""):
    return {"field_path": path, "value": value if isinstance(value, str) else str(value), "issue_type": itype,
            "severity": severity, "note": note}


def is_section_word(v: str) -> bool:
    n = C.norm_text(v)
    if not n:
        return False
    if n in SECTION_SET:
        return True
    # “資 格 大学”这类标题粘连
    # EN: Headings stuck together like "資 格 大学"
    # JA: 「資 格 大学」のような見出しのくっつき
    return any(n.startswith(w) and len(n) - len(w) <= 3 for w in SECTION_SET if len(w) >= 2)


# ---------------------------------------------------------------- 通用
# EN: ---------------------------------------------------------------- General
# JA: ---------------------------------------------------------------- 汎用
def check_generic_value(path, field, v, out, lang):
    if not isinstance(v, str) or not v:
        return
    if GARBLED_RE.search(v):
        out.append(_issue(path, v, "garbled_text", "high"))
    if C.RADICAL_RE.search(v):
        out.append(_issue(path, v, "pdf_garbled_chars", "medium", "含康熙部首/兼容汉字，疑似 PDF 转换乱码"))
    if HTML_RE.search(v):
        out.append(_issue(path, v, "html_residue", "medium"))
    if field in C.ENTITY_FIELDS or field in ("household_registration", "address", "marital_status", "company_industry", "school_degree_type"):
        if PUNCT_ONLY_RE.match(v):
            out.append(_issue(path, v, "punctuation_or_number_only", "high"))
        if is_section_word(v):
            out.append(_issue(path, v, "section_heading_as_value", "high"))
        if LABEL_RE.search(v):
            out.append(_issue(path, v, "label_residue", "high", "值中含有其他字段的标签"))


# ---------------------------------------------------------------- 基本信息
# EN: ---------------------------------------------------------------- Basic info
# JA: ---------------------------------------------------------------- 基本情報
def check_base(prefix, base, ref_year, lang, out):
    for f, v in (base or {}).items():
        check_generic_value(f"{prefix}.base_info.{f}", f, s(v), out, lang)
    name = s(base.get("full_name"))
    q, kind = C.name_quality(name)
    if q != "valid":
        out.append(_issue(f"{prefix}.base_info.full_name", name, "name_" + q, "high" if q == "invalid" else "medium"))
    elif name in PLACE_NAMES:
        out.append(_issue(f"{prefix}.base_info.full_name", name, "name_is_place", "high"))
    elif re.search(r"(性别|性別|年龄|出生|男$|女$)", name) and len(name) >= 3:
        out.append(_issue(f"{prefix}.base_info.full_name", name, "name_label_glued", "high"))
    g = s(base.get("gender"))
    if g and lang == "zh" and g not in ("男", "女"):
        out.append(_issue(f"{prefix}.base_info.gender", g, "gender_enum", "medium", "中文主版本应为 男/女"))
    bd = s(base.get("birth_date"))
    if bd and not DATE_OK_RE.match(bd):
        out.append(_issue(f"{prefix}.base_info.birth_date", bd, "date_format", "medium"))
    p = C.parse_ym(bd)
    by = p[0] if p else (int(s(base.get("birth_year"))) if s(base.get("birth_year")).isdigit() else None)
    if by and ref_year and (ref_year - by < 15 or ref_year - by > 75):
        out.append(_issue(f"{prefix}.base_info.birth_date", bd or str(by), "birth_date_implausible", "high",
                          f"出生年 {by} 与简历日期年 {ref_year} 相差 {ref_year - by} 年"))
    age = s(base.get("age"))
    if age:
        m = re.fullmatch(r"\d{1,3}", age)
        if not m:
            out.append(_issue(f"{prefix}.base_info.age", age, "age_format", "medium", "应为纯数字"))
        mm = re.search(r"\d{1,3}", age)
        if by and mm and ref_year and abs(int(mm.group(0)) - (ref_year - by)) > 1:
            out.append(_issue(f"{prefix}.base_info.age", age, "age_birth_conflict", "medium",
                              f"出生年 {by}，简历日期年 {ref_year}，推算约 {ref_year - by} 岁"))
    ps = s(base.get("political_status"))
    if ps and ("族" in ps or ps in ("汉", "漢")):
        out.append(_issue(f"{prefix}.base_info.political_status", ps, "ethnicity_in_political_status", "high", "民族写进了政治面貌"))
    na = s(base.get("nationality"))
    if na and ("族" in na or na in ("汉", "漢")):
        out.append(_issue(f"{prefix}.base_info.nationality", na, "ethnicity_in_nationality", "high", "民族写进了国籍"))
    pr = s(base.get("pr"))
    if pr:
        leak = [w for w in ("期望月薪", "期望从事职业", "期望工作地区", "目前状况", "希望職種", "希望給与") if w in pr]
        leak += [m.group(2) for m in re.finditer(r"(^|\n)\s*(求职意向|教育经历|教育背景|工作经历|工作经验|项目经历|简历内容|職 ?歴|学 ?歴|資 ?格)\s*[:：]?\s*(\n|$)", pr)]
        first = pr.strip().split("\n", 1)[0].strip()
        if leak or (is_section_word(first) and len(first) <= 8):
            out.append(_issue(f"{prefix}.base_info.pr", pr[:200], "section_leak_in_text", "high",
                              "自我评价中混入其他栏目：" + ",".join(leak or [first])))
    city = s(base.get("city"))
    if city and (len(city) > 15 or CITY_BAD_RE.search(city) or city in PROVINCE_AS_CITY or COUNTRY_CITY_RE.match(city)):
        out.append(_issue(f"{prefix}.base_info.city", city, "city_invalid", "high"))
    elif city and re.search(r"(路|街|号|弄|室|栋|楼|巷)", city):
        out.append(_issue(f"{prefix}.base_info.city", city, "address_in_city", "medium"))
    for f in ("address", "household_registration"):
        v = s(base.get(f))
        if v and re.fullmatch(r"[〒\s\-\d]*", v):
            out.append(_issue(f"{prefix}.base_info.{f}", v, "placeholder_value", "medium"))
        if v and re.search(r"(民族|漢民族|汉族)", v) and f == "address":
            out.append(_issue(f"{prefix}.base_info.{f}", v, "other_field_in_address", "high"))
    if lang == "zh":
        for f in ("city", "address", "household_registration", "gender", "marital_status", "nationality"):
            v = s(base.get(f))
            if v and LATIN_ONLY_RE.match(v) and len(v) > 1:
                if f in ("address", "city") and re.search(r"(Road|Rd\.?|Str(asse|aße|\.)?|Street|St\.|Avenue|Ave\.?|Lane|district|No\.)\b|str$", v, re.I):
                    out.append(_issue(f"{prefix}.base_info.{f}", v, "latin_address", "medium", "地址为英文原文（街道名）"))
                else:
                    out.append(_issue(f"{prefix}.base_info.{f}", v, "latin_in_zh_field", "high", "中文主版本字段为英文，需翻译"))
    ms = s(base.get("marital_status"))
    if ms and lang == "zh" and ms not in ZH_MARITAL:
        out.append(_issue(f"{prefix}.base_info.marital_status", ms, "marital_enum", "medium"))
    for f in ("phone", "email"):
        for part in C.split_contact_values(base.get(f)):
            kind2, _ = C.classify_email(part) if "@" in part else C.classify_phone(part)
            if kind2 in ("invalid", "masked"):
                out.append(_issue(f"{prefix}.base_info.{f}", part, f"{f}_{kind2}", "medium"))
            if "@" in part and re.match(r"^1[3-9]\d{9}.{3,}@", part):
                out.append(_issue(f"{prefix}.base_info.{f}", part, "contact_glued", "high", "手机号与邮箱粘连"))


# ---------------------------------------------------------------- 列表
# EN: ---------------------------------------------------------------- Lists
# JA: ---------------------------------------------------------------- リスト
def _date_pair(p, it, a, b, out, itype="date_reversed"):
    x, y = C.ym_key(it.get(a)), C.ym_key(it.get(b))
    if len(x) == 6 and len(y) == 6 and y < x:
        out.append(_issue(f"{p}.{b}", s(it.get(b)), itype, "high", f"开始 {s(it.get(a))} 晚于结束"))


def check_work(p, it, lang, out):
    comp, pos = s(it.get("company_name")), s(it.get("position"))
    resp = s(it.get("position_responsibilities"))
    if not comp and (pos or resp):
        out.append(_issue(f"{p}.company_name", comp, "work_company_missing", "high"))
    if comp:
        if too_long(comp) or SENT_PUNCT.search(comp) or (re.match(r"^[（(【\[]", comp) and not ORG_SUFFIX_RE.search(comp)
                                                          and not re.match(r"^[（(]\s*[株有財社]\s*[)）]", comp)) or COMPANY_SENT_WORDS.search(comp):
            out.append(_issue(f"{p}.company_name", comp, "work_company_sentence", "high"))
        if C.norm_text(comp) in {C.norm_text(x) for x in PLACEHOLDER_COMPANY}:
            out.append(_issue(f"{p}.company_name", comp, "work_company_placeholder", "high"))
        has_org = ORG_SUFFIX_RE.search(comp)
        if SCHOOL_RE.search(comp) and not re.search(r"(公司|会社|集团|Co\.|Ltd|Inc|医院|Hospital)", comp, re.I):
            # 在学校/研究所/实验室任职是正常经历；只有像学历（带学历/专业字样，或既无职位也无职责）时才算放错
            # EN: Holding a post at a school/research institute/laboratory is a normal experience; it counts as misplaced only when it looks like education (containing degree/major words, or having neither position nor duties)
            # JA: 学校・研究所・研究室での在職は正常な経歴である。学歴のように見える場合（学歴・専攻の語を含む、または職位も職務もない）だけ置き間違いとみなす
            has_job = len(pos) >= 2 and not is_section_word(pos) and not re.search(r"[:：]$", pos)
            studyish = re.search(r"(本科|硕士|博士|大专|专科|学历|专业|専攻|专攻|学部|学科|留学|在读|毕业)", comp) or (not has_job and len(resp) < 15)
            if studyish:
                out.append(_issue(f"{p}.company_name", comp, "school_in_work", "high", "学校写进了工作经历"))
            else:
                out.append(_issue(f"{p}.company_name", comp, "school_employer", "low", "在学校/研究机构任职"))
        elif HONOR_RE.search(comp) and not has_org:
            out.append(_issue(f"{p}.company_name", comp, "honor_in_work", "high", "奖项/荣誉写进了工作经历"))
        elif not has_org and re.fullmatch(r"(家教|兼职|兼职教师\s*家教|兼职教师|暑期实习|专业实习|业余兼职|自由职业|打工|实习|社会实践|学生实践|アルバイト)", comp):
            out.append(_issue(f"{p}.company_name", comp, "informal_job", "low", "家教/兼职/实习等，无具体单位"))
        elif not has_org and re.search(r"(家教|家庭教师|家庭日语教师|兼职|实习|打工|学生实践|アルバイト|バイト)", comp) and len(comp) <= 20 \
                and not SENT_PUNCT.search(comp):
            out.append(_issue(f"{p}.company_name", comp, "informal_job", "low", "家教/兼职/实习等，无具体单位"))
        elif not has_org and POSITION_WORD_RE.search(comp):
            out.append(_issue(f"{p}.company_name", comp, "position_as_company", "high", "公司名位置是职位"))
        elif FRAGMENT_RE.search(comp) and not re.search(r"(公司|会社|集团|Co\.|Ltd|Inc)", comp, re.I):
            out.append(_issue(f"{p}.company_name", comp, "work_company_sentence", "high", "公司名位置是句子片段"))
        elif not has_org and lang in ("zh", "jp") and C.HAN_RE.search(comp) and len(comp) <= 8:
            out.append(_issue(f"{p}.company_name", comp, "company_no_org_suffix", "medium", "像职位/描述而不是单位名"))
    if pos:
        if comp and C.norm_text(comp) == C.norm_text(pos):
            out.append(_issue(f"{p}.position", pos, "work_company_equals_position", "high"))
        if re.search(r"(有限公司|株式会社|有限会社|Co\.,?\s*Ltd)", pos, re.I) or re.search(r"(公司|集团|杂志社|报社|事务所|研究院)$", pos):
            out.append(_issue(f"{p}.position", pos, "company_in_position", "high"))
        tokens = pos.split()
        pos_segs = [x for x in re.split(r"[/／]", pos) if x]
        all_industry = bool(pos_segs) and all(re.fullmatch("(" + INDUSTRY_TERMS + ")", x) for x in pos_segs)
        if (all_industry and pos not in POSITION_OK_WORDS) or (len(tokens) > 1 and INDUSTRY_SEG_RE.search(tokens[-1])):
            out.append(_issue(f"{p}.position", pos, "industry_in_position", "high", "职位里粘了行业"))
        if INLINE_DURATION_RE.search(pos):
            out.append(_issue(f"{p}.position", pos, "duration_in_wrong_field", "high", "职位里粘了在职时长"))
        pos_core = INLINE_DURATION_RE.sub("", pos).strip()
        if re.search(r"(交易中心|研究中心|银行|医院|大学|学院|学校|工厂|酒店|商店)$", pos_core):
            out.append(_issue(f"{p}.position", pos, "company_in_position", "high", "职位位置是单位名"))
        elif re.search(r"(部|科|室|课|部门|本部|事业部|办公室)$", pos_core) and not re.search(r"(部长|科长|室长|课长)$", pos_core):
            out.append(_issue(f"{p}.position", pos, "dept_in_position", "high", "职位位置是部门名"))
    elif comp and lang == "zh":
        out.append(_issue(f"{p}.position", "", "work_position_missing", "medium"))
    if comp and re.search(r"[（(]\s*(兼职|实习)\s*[)）]|^(兼职|实习)", comp):
        out.append(_issue(f"{p}.company_name", comp, "position_in_company", "high", "公司名里带了职位/兼职字样"))
    if comp and not ORG_SUFFIX_RE.search(comp) and all(INDUSTRY_SEG_RE.search(x) or INDUSTRY_WORD_RE.search(x) for x in re.split(r"[/／]", comp) if x) and "/" in comp:
        out.append(_issue(f"{p}.company_name", comp, "industry_in_company", "high", "公司名位置是行业"))
    for f in ("company_name", "position", "position_dept", "company_industry"):
        v = s(it.get(f))
        if v and NATURE_RE.match(v):
            out.append(_issue(f"{p}.{f}", v, "company_nature_in_wrong_field", "high", "企业性质写进了该字段"))
        if v and EMPLOYEES_RE.match(v):
            out.append(_issue(f"{p}.{f}", v, "employees_in_wrong_field", "high", "公司规模写进了该字段"))
        if v and SHORT_DURATION_RE.match(v):
            out.append(_issue(f"{p}.{f}", v, "duration_in_wrong_field", "high", "在职时长写进了该字段"))
    if pos and re.search(r"(厂|画报|杂志|报社|电视台)$", pos) and not POSITION_WORD_RE.search(pos):
        out.append(_issue(f"{p}.position", pos, "company_in_position", "high", "职位位置是单位名"))
    dept0 = s(it.get("position_dept"))
    if dept0 and (SENT_PUNCT.search(dept0) or len(dept0) > (60 if LATIN_ONLY_RE.match(dept0) else 30)):
        out.append(_issue(f"{p}.position_dept", dept0, "dept_sentence", "high"))
    for f in ("position", "position_dept", "company_industry", "company_name"):
        v = s(it.get(f))
        if v and SALARY_RE.search(v):
            out.append(_issue(f"{p}.{f}", v, "salary_in_wrong_field", "high"))
        if v and f != "company_name" and DURATION_RE.search(v):
            out.append(_issue(f"{p}.{f}", v, "duration_in_wrong_field", "medium"))
    ind = s(it.get("company_industry"))
    if ind and pos and C.norm_text(ind) == C.norm_text(pos):
        out.append(_issue(f"{p}.company_industry", ind, "position_in_industry", "high"))
    elif ind and POSITION_WORD_RE.search(ind) and not INDUSTRY_SEG_RE.search(ind):
        out.append(_issue(f"{p}.company_industry", ind, "position_in_industry", "high", "行业位置是职位"))
    dept = s(it.get("position_dept"))
    if dept:
        segs = [x for x in re.split(r"[/／]", dept) if x]
        if pos and C.norm_text(dept) == C.norm_text(pos):
            out.append(_issue(f"{p}.position_dept", dept, "dept_equals_position", "high", "部门与职位相同，部门字段被职位占用"))
        elif not DEPT_WORD_RE.search(dept) and segs and all(DEPT_POSITION_RE.search(x) for x in segs):
            out.append(_issue(f"{p}.position_dept", dept, "position_in_dept", "high", "部门位置是职位"))
        elif ind and C.norm_text(dept) == C.norm_text(ind) and DEPT_WORD_RE.search(dept):
            out.append(_issue(f"{p}.company_industry", ind, "dept_in_industry", "high", "行业位置是部门名"))
        elif SALARY_RE.search(dept):
            pass  # 已记 salary_in_wrong_field
            # EN: Already recorded as salary_in_wrong_field
            # JA: すでに salary_in_wrong_field として記録済み
        elif (ind and C.norm_text(dept) == C.norm_text(ind) and len(dept) > 4) or \
                (not DEPT_WORD_RE.search(dept) and (INDUSTRY_SEG_RE.search(dept) or ("/" in dept and C.HAN_RE.search(dept)))):
            out.append(_issue(f"{p}.position_dept", dept, "industry_in_dept", "high", "部门位置是行业"))
        elif lang == "zh" and LATIN_ONLY_RE.match(dept) and len(dept) > 3:
            out.append(_issue(f"{p}.position_dept", dept, "latin_dept", "medium", "部门名为英文原文"))
    if ind and re.search(r"(外资|合资|国企|民营|私营|上市公司|事业单位|外企代表处)", ind) and ("|" in ind or "｜" in ind):
        out.append(_issue(f"{p}.company_industry", ind, "company_nature_in_industry", "medium", "行业里粘了企业性质"))
    if not any(s(it.get(f)) for f in ("company_name", "position", "position_responsibilities")):
        out.append(_issue(p, "", "work_placeholder_row", "high"))
    st, rs = s(it.get("status")), s(it.get("position_resigned"))
    if st == "在职" and rs:
        out.append(_issue(f"{p}.status", st, "work_status_conflict", "medium", f"在职但离职日期={rs}"))
    if st and lang == "zh" and st not in ("在职", "离职"):
        out.append(_issue(f"{p}.status", st, "work_status_enum", "medium"))
    _date_pair(p, it, "position_start", "position_resigned", out)
    if resp:
        heads = [w for w in ("自己紹介", "自我评价", "教育经历", "教育背景", "資 格", "资格证书", "学歴", "個人情報", "求职意向") if w in resp]
        if heads:
            out.append(_issue(f"{p}.position_responsibilities", resp[:200], "section_leak_in_text", "medium", f"含其他栏目：{','.join(heads)}"))


def _training_org(sc):
    m = TRAINING_ORG_RE.search(sc)
    if not m or too_long(sc) or SENT_PUNCT.search(sc) or LABEL_RE.search(sc) or re.match(r"^[\d０-９]", sc):
        return False
    if re.search(r"(证书|能力测试|能力考试|等级|[一二]级|N[1-5]|学习$)", sc):
        return False
    return len(C.norm_text(sc.replace(m.group(1), ""))) >= 2


def _school_abbr(sc, mj, dt):
    """“上海交大 / 江西机电 / JAIST”这类简称：专业、学历都齐全，本身不像公司。

    EN: Abbreviations like "上海交大 / 江西机电 / JAIST": with both major and degree present, they do not look like companies themselves.

    JA: 「上海交大／江西机电／JAIST」のような略称：専攻と学歴がそろっており、それ自体は会社らしくない。
    """
    if not mj or not dt or ABBR_BAD_RE.search(sc) or SENT_PUNCT.search(sc) or LABEL_RE.search(sc) or is_section_word(sc):
        return False
    if re.search(r"(助理|经理|主管|专员|工程师|销售|文员|[\d０-９])", mj) or len(mj) > 20:
        return False
    if not re.search(r"(本科|学士|大专|专科|硕士|博士|中专|高中|Bachelor|Master|Doctor|PhD)", dt, re.I):
        return False
    return bool(re.fullmatch(r"[一-鿿]{3,8}", sc) or re.fullmatch(r"[A-Z]{3,6}", sc) or re.fullmatch(r"[一-鿿]{2,6}[(（][一-鿿]{2,4}[)）]", sc))


def check_education(p, it, lang, out):  # noqa: C901
    sc, mj = s(it.get("school_name")), s(it.get("school_major_name"))
    dt, rk = s(it.get("school_degree_type")), s(it.get("school_degree_rank"))
    if not sc:
        out.append(_issue(f"{p}.school_name", sc, "school_missing", "high"))
    else:
        if C.norm_text(sc) in {C.norm_text(x) for x in PLACEHOLDER_SCHOOL}:
            out.append(_issue(f"{p}.school_name", sc, "school_placeholder", "high"))
        elif TRAINING_HINT.search(sc):
            out.append(_issue(f"{p}.school_name", sc, "training_in_education", "medium", "培训/进修机构列在学历里"))
        elif not SCHOOL_RE.search(sc) and _training_org(sc):
            out.append(_issue(f"{p}.school_name", sc, "training_in_education", "medium", "培训/语言学校/进修机构列在学历里"))
        elif not SCHOOL_RE.search(sc) and RESEARCH_ORG_RE.search(sc) and re.search(r"(硕士|博士|研究生|Master|Doctor|PhD)", dt, re.I):
            pass  # 研究院/研究所培养的研究生
            # EN: Graduate students trained by research institutes
            # JA: 研究院・研究所で育成された大学院生
        elif not SCHOOL_RE.search(sc) and _school_abbr(sc, mj, dt):
            out.append(_issue(f"{p}.school_name", sc, "school_abbrev", "medium", "学校名是简称，需补全"))
        elif not SCHOOL_RE.search(sc) and mj and TRAINING_HINT.search(mj) and len(sc) <= 12 and not SENT_PUNCT.search(sc):
            out.append(_issue(f"{p}.school_name", sc, "training_in_education", "medium", f"专业栏是培训：{mj}"))
        elif not SCHOOL_RE.search(sc):
            if MAJOR_HINT.search(sc):
                out.append(_issue(f"{p}.school_name", sc, "school_major_swapped", "high", f"专业={mj}"))
            else:
                out.append(_issue(f"{p}.school_name", sc, "school_not_school", "high", "不像学校名"))
        if too_long(sc) or SENT_PUNCT.search(sc) or LABEL_RE.search(sc):
            out.append(_issue(f"{p}.school_name", sc, "school_sentence", "high"))
        if LOW_SCHOOL_RE.search(sc) and rank_of(rk) >= 3:
            out.append(_issue(f"{p}.school_degree_rank", f"{sc}|{dt}|{rk}", "degree_school_mismatch", "high", "中小学被标成大专及以上"))
    if sc and lang == "zh" and LATIN_ONLY_RE.match(sc) and len(sc) > 3:
        if SCHOOL_RE.search(sc) and not C.norm_text(sc) in {C.norm_text(x) for x in PLACEHOLDER_SCHOOL}:
            out.append(_issue(f"{p}.school_name", sc, "latin_school_name", "medium", "学校名为英文原文"))
        else:
            out.append(_issue(f"{p}.school_name", sc, "latin_in_zh_field", "high", "中文主版本学校名为英文，需翻译或与中文行合并"))
    if mj:
        if sc and C.norm_text(mj) == C.norm_text(sc):
            out.append(_issue(f"{p}.school_major_name", mj, "major_equals_school", "high"))
        if re.search(r"(有限会社|有限公司|株式会社|従業員|实践|学习情况|海外经历|保研|论文|求职信|简历|奖项|获奖)", mj):
            out.append(_issue(f"{p}.school_major_name", mj, "major_not_major", "high"))
        elif re.search(r"(学院|College)$", mj, re.I) and sc and not re.search(r"(大学|University)", mj, re.I) and \
                re.search(r"(大学|University)", sc, re.I):
            out.append(_issue(f"{p}.school_major_name", mj, "school_residue_in_major", "medium", "专业位置是院系名"))
        elif re.search(r"(大学|学院|学校|University|College)$", mj, re.I):
            out.append(_issue(f"{p}.school_major_name", mj, "school_in_major", "high", "专业位置是学校名"))
        elif re.search(r"(学院|学部|大学)\s", mj):
            out.append(_issue(f"{p}.school_major_name", mj, "school_residue_in_major", "medium", "专业里带了院系名"))
    if dt and (re.search(r"\d{4}", dt) or (len(dt) > 12 and lang in ("zh", "jp"))):
        out.append(_issue(f"{p}.school_degree_type", dt, "degree_type_residue", "high"))
    expect_rank = {"博士后": 7, "博士": 6, "硕士": 5, "研究生": 5, "MBA": 5, "EMBA": 5, "本科": 4, "学士": 4, "大专": 3, "专科": 3, "高中": 2, "中专": 2}
    for k, v in expect_rank.items():
        if dt.startswith(k) and rk and rank_of(rk) != v:
            out.append(_issue(f"{p}.school_degree_rank", f"{dt}|{rk}", "degree_rank_mismatch", "high", f"{dt} 应为 {v}"))
            break
    if rk and rk not in {"1", "2", "3", "4", "5", "6", "7"}:
        out.append(_issue(f"{p}.school_degree_rank", rk, "degree_rank_enum", "medium"))
    _date_pair(p, it, "school_start_ym", "school_end_ym", out)


def rank_of(rk):
    try:
        return int(rk)
    except (TypeError, ValueError):
        return 0


def check_lists(prefix, res, lang, out):
    lang_names = {}
    for lst in C.LIST_ORDER:
        for i, it in enumerate(res.get(lst) or []):
            p = f"{prefix}.{lst}[{i}]"
            for f, v in it.items():
                check_generic_value(f"{p}.{f}", f, s(v), out, lang)
            for f in C.DATE_FIELDS.get(lst, []):
                v = s(it.get(f))
                if v and not DATE_OK_RE.match(v):
                    out.append(_issue(f"{p}.{f}", v, "date_format", "medium"))
            if lst == "work_experiences":
                check_work(p, it, lang, out)
            elif lst == "education_list":
                check_education(p, it, lang, out)
            elif lst == "certificate_list":
                nm = s(it.get("certificate_name"))
                if nm and (PUNCT_ONLY_RE.match(nm) or re.fullmatch(r"[（(]?[\d.]+[）)]?", nm)):
                    out.append(_issue(f"{p}.certificate_name", nm, "certificate_not_certificate", "high"))
                elif nm and HONOR_RE.search(nm):
                    out.append(_issue(f"{p}.certificate_name", nm, "honor_as_certificate", "medium"))
                if nm and (len(nm) > 30 or re.search(r"[，、,;；]", nm)):
                    out.append(_issue(f"{p}.certificate_name", nm, "certificate_not_split", "medium"))
                if nm and re.match(r"^[※·•\-\*]", nm):
                    out.append(_issue(f"{p}.certificate_name", nm, "bullet_residue", "medium"))
                if nm and LANG_CERT_RE.search(nm):
                    out.append(_issue(f"{p}.certificate_name", nm, "language_cert_in_certificate_list", "low"))
            elif lst == "language_list":
                ln = s(it.get("language_name"))
                key = {"日本語": "日语", "英語": "英语", "japanese": "日语", "english": "英语", "中文": "普通话", "chinese": "普通话"}.get(ln.lower() if ln.isascii() else ln, ln)
                if key in lang_names:
                    out.append(_issue(f"{p}.language_name", ln, "language_duplicate", "medium", f"与 {lang_names[key]} 重复"))
                lang_names.setdefault(key, ln)
                lc = s(it.get("language_certificate"))
                if lc and lc not in ("有", "无"):
                    out.append(_issue(f"{p}.language_certificate", lc, "language_certificate_enum", "low"))
                lv = s(it.get("language_level"))
                if lv and (re.search(r"(股份|公司|有限)", lv) or lv.count("(") != lv.count(")")):
                    out.append(_issue(f"{p}.language_level", lv, "language_level_residue", "high"))
                if lv and re.fullmatch(r"[●○◎■□\s]+", lv):
                    out.append(_issue(f"{p}.language_level", lv, "language_level_symbol", "medium"))
            elif lst == "expected_list":
                for f in ("expected_city", "expected_position", "expected_industry", "expected_salary"):
                    v = s(it.get(f))
                    if v and EXPECT_LABEL_RE.search(v):
                        out.append(_issue(f"{p}.{f}", v, "label_residue", "high", "值中粘了其他栏目标签"))
                bad = {"expected_city": r"(大学|学院|院校|职能|职位|工程训练|勿推|月薪|设计|专业|艺术|管理)",
                       "expected_position": r"^(月薪范围|期望月薪|勿推.*)$",
                       "expected_salary": r"(勿推|企业$|大学|学院)"}
                for f, pat in bad.items():
                    v = s(it.get(f))
                    if v and "不显示" not in v and re.search(pat, v):
                        out.append(_issue(f"{p}.{f}", v, "expected_value_misplaced", "high"))
            elif lst == "training_list":
                org, tn = s(it.get("organization_name")), s(it.get("training_name"))
                if org and tn and C.norm_text(org) == C.norm_text(tn):
                    out.append(_issue(f"{p}.training_name", tn, "training_org_equals_name", "medium"))
                if org and (re.fullmatch(r"[\d\s.\-年月]+", org) or LABEL_RE.search(org)):
                    out.append(_issue(f"{p}.organization_name", org, "training_org_invalid", "high"))
                if tn and re.fullmatch(r"[\d\s.\-年月]+", tn):
                    out.append(_issue(f"{p}.training_name", tn, "training_name_invalid", "high"))
                if (org and too_long(org)) or (tn and too_long(tn)):
                    out.append(_issue(p, org or tn, "training_sentence", "medium"))
            elif lst == "project_list":
                nm = s(it.get("project_name"))
                if nm and (len(nm) > 50 or LABEL_RE.search(nm)):
                    out.append(_issue(f"{p}.project_name", nm, "project_name_sentence", "medium"))
    seen_school = {}
    for i, e in enumerate(res.get("education_list") or []):
        k = C.norm_entity(e.get("school_name")) + "|" + C.norm_text(e.get("school_major_name"))
        if C.norm_entity(e.get("school_name")) and k in seen_school:
            out.append(_issue(f"{prefix}.education_list[{i}]", s(e.get("school_name")), "education_duplicate", "medium", f"与 education_list[{seen_school[k]}] 重复"))
        seen_school.setdefault(k, i)
    edus = res.get("education_list") or []
    for i, a in enumerate(edus):
        for j in range(i + 1, len(edus)):
            b = edus[j]
            sa, sb = C.norm_text(a.get("school_name")), C.norm_text(b.get("school_name"))
            same_time = C.ym_key(a.get("school_end_ym")) == C.ym_key(b.get("school_end_ym")) and C.ym_key(a.get("school_start_ym")) == C.ym_key(b.get("school_start_ym"))
            if sa and sb and sa != sb and same_time and (sa.startswith(sb) or sb.startswith(sa)):
                out.append(_issue(f"{prefix}.education_list[{j}]", s(b.get("school_name")), "education_duplicate", "high",
                                  f"与 education_list[{i}] {s(a.get('school_name'))} 是同一段学历"))
    if lang == "zh":
        text = C.resume_business_text(res)
        kana = len(C.KANA_RE.findall(text))
        if kana >= 5:
            out.append(_issue(prefix, "", "foreign_text_in_zh", "medium", f"中文主版本中含 {kana} 个日文假名"))


def check_resume(prefix, res, ref_year, lang):
    out = []
    check_base(prefix, res.get("base_info") or {}, ref_year, lang, out)
    check_lists(prefix, res, lang, out)
    if lang == "zh" and not (res.get("work_experiences") or res.get("education_list")):
        out.append(_issue(prefix, "", "no_work_no_education", "high"))
    return out


def check_cross_language(resumes):
    """同一人不同语言版本之间的一致性：性别、出生日期。

    EN: Consistency between language versions of the same person: gender, date of birth.

    JA: 同一人物の言語版の間の一貫性：性別、生年月日。
    """
    out = []
    base0 = resumes[0].get("base_info") or {} if resumes else {}
    g0, b0 = s(base0.get("gender")), C.parse_ym(base0.get("birth_date"))
    gmap = {"男": "m", "女": "f", "male": "m", "female": "f", "男性": "m", "女性": "f", "m": "m", "f": "f"}
    for i, r in enumerate(resumes[1:], 1):
        b = r.get("base_info") or {}
        g = s(b.get("gender"))
        if g0 and g and gmap.get(g0.lower()) and gmap.get(g.lower()) and gmap[g0.lower()] != gmap[g.lower()]:
            out.append(_issue(f"resumes[{i}].base_info.gender", g, "cross_language_conflict", "high", f"与 resumes[0] 的 {g0} 不一致"))
        bd = C.parse_ym(b.get("birth_date"))
        if b0 and bd and (b0[0], b0[1]) != (bd[0], bd[1]):
            out.append(_issue(f"resumes[{i}].base_info.birth_date", s(b.get("birth_date")), "cross_language_conflict", "high",
                              f"与 resumes[0] 的 {s(base0.get('birth_date'))} 不一致"))
    return out
