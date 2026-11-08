from __future__ import annotations
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
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = _rc.project_root()
PDF_ROOT = PROJECT_ROOT / _rc.dirname("complete-transfered-htmls") / "pdf"
DEFAULT_COMPARISON = PDF_ROOT / "rebuild-reports" / "pdf_gpt_four_way_comparison.v2.json"
DEFAULT_OUTPUT = PDF_ROOT / "rebuild-reports" / "pdf_gpt_review_overrides.v2.json"
DEFAULT_CSV = PDF_ROOT / "rebuild-reports" / "pdf_gpt_review_resolution.v2.csv"
VERSION = "pdf-gpt-four-way-resolution-v2.0.0"


def load_merge_module():
    path = _rc.PYTHON_DIR / "v2" / "pdf_rebuild_merge.v2.py"
    spec = importlib.util.spec_from_file_location("_pdf_rebuild_merge_v2", path)
    if spec is None or spec.loader is None:
        raise ImportError(path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MERGE = load_merge_module()


def work(company: str, start: str = "", end: str = "", position: str = "", employment: str = "全职", responsibilities: str = "") -> dict[str, Any]:
    return {
        "company_name": company,
        "position_start": start,
        "position_resigned": end,
        "position": position,
        "employment_type": employment,
        "status": "在职" if not end else "离职",
        "position_responsibilities": responsibilities,
    }


def education(school: str, start: str = "", end: str = "", major: str = "", degree: str = "") -> dict[str, Any]:
    return {
        "school_name": school,
        "school_start_ym": start,
        "school_end_ym": end,
        "school_major_name": major,
        "school_degree_type": degree,
    }


def project(name: str, start: str = "", end: str = "", role: str = "", description: str = "") -> dict[str, Any]:
    return {"project_name": name, "start_ym": start, "end_ym": end, "role_name": role, "description": description}


FACTS: dict[str, dict[str, Any]] = {
    "宗磊": {
        "work": [
            work("三井物产（上海）贸易有限公司", "2016年04月01日", "", "高级经理", responsibilities="砂糖、烘焙及巧克力原料销售；关联公司支持及市场调查。"),
            work("三菱瓦斯化学商贸（上海）有限公司", "2010年05月01日", "2015年10月01日", "营业部经理", responsibilities="化学品市场开发、销售、许可申请及原料采购。"),
            work("三菱瓦斯化学株式会社总部", "2008年03月01日", "2010年05月01日", "管理部成员", responsibilities="关联公司财务、预算决算、董事会及损益分析。"),
            work("菱天（南京）精细化工有限公司／三菱瓦斯化学南京工厂", "2005年08月01日", "2008年03月01日", "总经理助理", responsibilities="建厂审批、政府协调、原料采购及口笔译。"),
        ],
        "education": [
            education("南京农业大学", "2001年09月01日", "2005年07月01日", "外国语学院日语系", "本科"),
            education("无锡市东林中学", "1998年09月01日", "2001年07月01日", "", "高中"),
        ],
        "note": "删除中日双语重复项及被误识别为工作的学历。",
    },
    "卫伟": {
        "work": [
            work("佐竹机械", "2012年06月01日", "", "社长助理／综合企划室", responsibilities="制度流程、经营进度、总部月报及行政部门管理支持。"),
            work("名古屋江苏国际株式会社", "2007年04月01日", "2012年02月01日", "", responsibilities="报关、库存、出货、应收款及资料翻译。"),
            work("苏州爱普生有限公司", "2003年08月01日", "2004年09月01日", "日语翻译", responsibilities="现场技术指导翻译、生产计划及文件翻译。"),
        ],
        "education": [
            education("中京大学大学院", "2010年04月01日", "2012年03月01日", "计量经济学", "硕士"),
            education("中京大学", "2006年04月01日", "2010年03月01日", "经济学", "本科"),
            education("爱知国际学院", "2004年10月01日", "2006年03月01日", "日语", "语言学校"),
            education("苏州中山进修学院", "1999年09月01日", "2002年07月01日", "计算机", "大专"),
            education("苏州财政经济学校", "1996年09月01日", "1999年07月01日", "财务会计", "中专"),
        ],
        "note": "按源表补回中京大学本科，修复公司名和学历结束日期。",
    },
    "叶盛成": {
        "work": [
            work("MUSASINO科技设备（苏州）有限公司上海分公司", "2008年08月01日", "2011年11月01日", "售后服务担当／联络窗口", responsibilities="对日联络、客户报修、零件与工程师协调。"),
            work("微软上海紫竹研发中心", "2013年08月01日", "2014年04月01日", "项目经理实习生", "实习", "参与 Microsoft Dynamics AX 日本本地化功能调研、录入及测试。"),
        ],
        "education": [
            education("上海外国语大学", "2012年09月01日", "2015年03月01日", "日语语言文学", "硕士"),
            education("山东经济学院", "2004年09月01日", "2008年06月01日", "会计学", "本科"),
        ],
        "note": "合并中英日重复经历，移除证书和学历误入工作的问题。",
    },
    "施跻骎": {
        "work": [
            work("Minebea Trading Corporation", "2017年09月01日", "2018年01月01日", "销售助理", responsibilities="销售数据、库存分析及销售报表。"),
            work("BMB International Corporation", "2011年08月01日", "2017年07月01日", "海外主管兼销售助理", responsibilities="进出口、货运单据、销售及客户支持。"),
            work("Rapid Rack Industries Inc.", "2009年02月01日", "2011年07月01日", "办公室主管"),
            work("Britan Logistics Company Shanghai Branch", "2007年09月01日", "2008年10月01日", "运营助理"),
        ],
        "education": [
            education("上海海事大学", "2007年10月01日", "2011年01月01日", "国际商务与贸易", "本科"),
            education("上海工会管理职业学院", "2004年09月01日", "2007年07月01日", "商务英语", "大专"),
        ],
        "note": "补回漏失的物流公司，删除学生会、奖励等伪学历。",
    },
    "崔广宇": {
        "work": [
            work("北京大基康明医疗设备有限公司", "2017年08月01日", "2017年10月01日", "设备部实习生", "实习", "PET 设备安装、调试、维护及拆卸。"),
            work("上海尚普和风日本留学有限公司", "2017年11月01日", "2018年01月01日", "文书翻译／新媒体实习生", "实习", "留学材料日语翻译及社交媒体账号维护。"),
        ],
        "education": [
            education("谢菲尔德大学", "2018年07月01日", "2019年09月01日", "电子与电气工程", "硕士"),
            education("河北工业大学", "2013年09月01日", "2017年06月01日", "生物医学工程", "本科"),
            education("哈尔滨市阿城区第一高级中学", "2010年09月01日", "2013年06月01日", "", "高中"),
        ],
        "projects": [
            project("光子晶体器件结构变化研究", "2019年01月01日", "2019年09月01日", "研究生研究项目"),
            project("全国大学生创新创业训练计划", "2016年04月01日", "2017年04月01日", "团队成员", "脑电信号控制 VR 视频播放以提升儿童注意力。"),
            project("MMC 柔性两端直流输电系统仿真", "2016年07月01日", "2016年08月01日"),
            project("河北工业大学生物医学工程创新设计竞赛", "2016年07月01日", "2016年08月01日", "团队成员", "脑电波监测与共享系统，获二等奖。"),
        ],
        "note": "将创新项目从学历移至项目，合并重复实习。",
    },
    "聂腾飞": {
        "work": [
            work("上海森松制药设备工程有限公司", "2012年07月01日", "2018年03月01日", "项目经理"),
            work("无锡维尔肯工业系统工程有限公司", "2018年03月01日", "", "项目经理兼工艺设计"),
        ],
        "education": [education("郑州大学", "2008年09月01日", "2012年06月01日", "化学工程与工艺", "本科")],
        "note": "把已实施项目从工作经历中剥离，工作仅保留两家雇主。",
    },
    "瓮宝琴": {
        "work": [
            work("广汽丰田汽车有限公司", "2019年05月01日", "2020年04月01日", "日语翻译兼助理", "派遣", "总经办及互联出行部口笔译和事务支持。"),
            work("独角兽互联网工作室", "2017年07月01日", "2018年12月01日", "日语翻译", responsibilities="字幕、动画及资料翻译编辑。"),
        ],
        "education": [
            education("北京第二外国语学院", "2015年09月01日", "2017年06月01日", "日语笔译", "硕士"),
            education("东北大学", "2011年09月01日", "2015年06月01日", "日语", "本科"),
            education("韩国庆星大学", "2013年01月01日", "2013年07月01日", "日语、韩语", "交换留学"),
        ],
        "note": "合并中日学历重复项并补回第二段正式工作。",
    },
    "仇俊军": {
        "work": [
            work("上海相申调味品有限公司", "2002年10月01日", "", "总经理助理"),
            work("阪和贸易（上海）有限公司", "2001年06月01日", "2002年09月01日", "营业担当"),
        ],
        "education": [
            education("上海外国语大学日本文化经济学院", "1997年09月01日", "2001年07月01日", "日语", "本科"),
            education("上海市北中学", "1994年09月01日", "1997年07月01日", "", "高中"),
        ],
        "training": [{"organization_name": "日本海外技术者研修协会（AOTS）", "training_name": "企业经营与生产管理研修", "start_ym": "2003年01月01日", "end_ym": "2004年01月01日"}],
        "note": "删除中日重复项，将 AOTS 经历归入培训。",
    },
    "卫燕": {
        "work": [
            work("のとや株式会社", "2008年12月01日", "2012年08月01日", "服装销售", responsibilities="接客、补货及收银。"),
            work("曦晨幼儿园", "2013年01月01日", "", "教师", responsibilities="幼儿课程设计、教学及幼小衔接。"),
        ],
        "education": [
            education("拓殖大学", "2009年04月01日", "2010年03月01日", "留学生别科", "大学预科"),
            education("复旦大学网络学院", "2006年09月01日", "2008年07月01日", "国际经济与贸易", "本科"),
            education("上海建桥学院", "2003年09月01日", "2006年07月01日", "工商管理", "大专"),
            education("上海市钱桥中学", "2000年09月01日", "2003年07月01日", "", "高中"),
        ],
        "note": "按中日英三栏源表恢复两份工作，移除模板占位字段。",
    },
    "呉灵杰": {
        "work": [
            work("爱普香料集团股份有限公司", "2021年09月01日", "", "销售经理"),
            work("上海心美信息科技有限公司", "2021年04月01日", "2021年06月01日", "实验员"),
            work("上海华伊美化妆品有限公司", "2016年07月01日", "2016年08月01日", "质量检测员", "实习"),
        ],
        "education": [
            education("京都大学", "2020年04月01日", "2021年03月01日", "研究生", "研究生"),
            education("JCL外国语学院", "2018年10月01日", "2020年03月01日", "日语", "语言学校"),
            education("上海应用技术大学", "2014年09月01日", "2018年06月01日", "轻化工程", "本科"),
            education("湖南省常德市第七中学", "2011年09月01日", "2014年06月01日", "", "高中"),
        ],
        "note": "将三段学历从工作列表移回学历，修复高中模板行。",
    },
    "吴雯婷": {
        "work": [
            work("名古屋大学大学院医学系研究科", "2010年10月01日", "2015年03月01日", "博士研究生／研究人员", "研究", "纳米材料安全性评价研究、实验、数据分析和论文撰写。"),
            work("上海市黄浦区疾病预防控制中心", "2010年02月01日", "2010年04月01日", "实习科员", "实习"),
            work("复旦大学医院管理教研室", "2009年07月01日", "2009年07月01日", "调研访谈员", "项目"),
            work("上海市第五人民医院", "2008年08月01日", "2009年02月01日", "实习医师", "实习"),
            work("上海市爱国卫生运动委员会办公室", "2006年11月01日", "2006年11月01日", "问卷调查员", "项目"),
        ],
        "education": [
            education("名古屋大学大学院", "2010年10月01日", "2015年03月01日", "医学系研究科职业与环境卫生学", "医学博士"),
            education("复旦大学", "2005年09月01日", "2010年07月01日", "预防医学", "医学学士"),
        ],
        "note": "删除论文题名和多语言学历误入工作，保留源文件明确列出的研究及社会实践。",
    },
    "陆欣染": {
        "work": [],
        "education": [
            education("东云小学", "2001年04月01日", "2007年03月01日", "", "小学"),
            education("深川第五中学校", "2007年04月01日", "2010年03月01日", "", "初中"),
            education("品川Etoile女子高等学校", "2010年04月01日", "2013年03月01日", "一般类型选拔班", "高中"),
            education("二松学舍大学", "2013年04月01日", "2017年03月01日", "国际政治经济学", "本科"),
            education("北京大学", "2014年07月01日", "2014年07月01日", "短期语言留学", "短期留学"),
        ],
        "note": "源 PDF 无正式职历；补齐日式入学/毕业日期。",
    },
    "杨林": {
        "work": [
            work("软银通信科技（上海）有限公司", "2006年06月01日", "", "SE课技术管理"),
            work("日本新思软件株式会社（株式会社Thrust）", "2003年08月01日", "2006年04月01日", ""),
            work("湖南科创信息技术股份有限公司", "1996年08月01日", "2003年07月01日", "技术经理"),
        ],
        "education": [
            education("中南大学", "2000年09月01日", "2003年05月01日", "计算机应用技术", "硕士"),
            education("中南大学（铁道学院）", "1992年09月01日", "1996年07月01日", "计算机软件", "本科"),
        ],
        "note": "删除出生日期和项目名称伪学历，保留三段雇佣关系。",
    },
    "张陆伟": {
        "work": [],
        "education": [
            education("东京设计师学院", "2016年04月01日", "2018年03月01日", "", "专门学校"),
            education("宁波大学科学技术学院", "2010年07月01日", "2014年09月01日", "", "本科"),
        ],
        "note": "合并日式入学/毕业事件，删除自我介绍误入学历。",
    },
    "崔滢婷": {
        "work": [
            work("Kanebo", "2013年05月01日", "2015年08月01日", "销售翻译", "兼职"),
            work("Saizeriya", "2011年07月01日", "2013年05月01日", "大厅服务", "兼职"),
            work("Lawson", "2010年09月01日", "2011年12月01日", "收银", "兼职"),
        ],
        "education": [
            education("明治大学", "2011年04月01日", "2015年03月01日", "商学部商学科", "本科"),
            education("富士国际语学院", "2009年08月01日", "2011年03月01日", "日语", "语言学校"),
        ],
        "note": "合并入学/毕业行；正式职历为空，但保留源文件明确列出的三段兼职。",
    },
    "王珮": {
        "work": [
            work("上海修曼人才有限公司", "2013年09月01日", "2014年01月01日", "销售／人才匹配"),
            work("中国太平金融服务共享中心", "2014年03月01日", "2014年09月01日", "客服专员／讲师"),
            work("上海汉熙文化传播有限公司", "2014年09月01日", "2015年01月01日", "销售／讲师"),
            work("上海朗译商务咨询有限公司", "2014年09月01日", "", "销售／讲师"),
        ],
        "education": [
            education("华东师范大学（函授）", "2013年09月01日", "2015年09月01日", "行政管理", "本科"),
            education("东京语文学院", "2009年10月01日", "2010年10月01日", "日语", "语言学校"),
            education("兴化市第一中学（上海市光明中学）", "2006年09月01日", "2009年06月01日", "", "高中"),
            education("上海市格致初级中学", "2002年09月01日", "2006年06月01日", "", "初中"),
        ],
        "note": "从职责段恢复四家雇主并移除模板学校行。",
    },
    "魏铭君": {
        "work": [work("吉林省档案馆", "2018年03月01日", "2018年06月01日", "实习生", "实习")],
        "education": [
            education("富山大学", "2019年04月01日", "", "人文科学研究科国际关系论", "硕士"),
            education("辽宁大学", "2014年09月01日", "2018年07月01日", "外国语学院日语", "本科"),
            education("大阪经济法科大学", "2015年09月01日", "2016年08月01日", "交换留学", "交换留学"),
        ],
        "note": "把 TOEIC、J.TEST、驾照和兴趣从工作中移除，保留明确实习。",
    },
    "屈国超": {
        "work": [
            work("仁宝电脑", "2016年10月01日", "2017年05月01日", "项目工程师"),
            work("英业达（上海）有限公司", "2013年03月01日", "2016年06月01日", "QA工程师"),
            work("昌硕科技（上海）有限公司", "2012年03月01日", "2013年03月01日", "AOI工程师"),
        ],
        "education": [education("齐齐哈尔医学院", "2006年09月01日", "2011年07月01日", "医学检验", "本科")],
        "note": "将齐齐哈尔医学院从工作移回学历，删除 School Honors 占位项。",
    },
    "何夢茜": {
        "work": [
            work("上海布朗商行有限公司", "2020年04月01日", "", "销售助理", responsibilities="化学品订单、库存、进出口单证及物流管理。"),
            work("上海三景贸易有限公司", "2017年11月01日", "2020年03月01日", "销售助理", responsibilities="服装订单、交期、客户与供应商沟通及进出口。"),
        ],
        "education": [
            education("中央大学", "2015年01月01日", "2017年01月01日", "综合政策研究科", "肄业"),
            education("富士国际语学院", "2013年01月01日", "2015年01月01日", "日语", "语言学校"),
            education("东华大学", "2010年01月01日", "2013年01月01日", "日语", "本科课程"),
            education("上海工程技术大学", "2009年01月01日", "2013年01月01日", "服装设计与工程", "本科"),
        ],
        "note": "删除公司/学校模板占位行并恢复第二家雇主。",
    },
    "朱素娟": {
        "work": [
            work("国际商业机器全球服务（大连）有限公司上海分公司（IBM）", "2019年04月01日", "", "技术顾问", responsibilities="开发、测试及项目助理（PMO）。"),
            work("许昌市第一中学", "2013年08月01日", "2016年06月01日", "英语教师／副班主任"),
        ],
        "education": [
            education("横滨国立大学", "2017年04月01日", "2019年03月01日", "经营学", "硕士"),
            education("MANABI外语学院东京校", "2016年07月01日", "2017年03月01日", "日语", "语言学校"),
            education("安阳学院", "2009年09月01日", "2013年06月01日", "日语", "本科"),
            education("许昌市第二高级中学", "2006年09月01日", "2009年06月01日", "", "高中"),
        ],
        "note": "将项目条目从工作列表剥离，补回教师经历并修复高中日期。",
    },
    "王貝寧": {
        "work": [],
        "education": [
            education("神户大学大学院", "2018年04月01日", "2020年03月01日", "国际文化学研究科全球文化", "硕士"),
            education("北陆大学", "2016年04月01日", "2017年08月01日", "国际教养学部留学生别科", "留学生别科"),
            education("天津外国语大学滨海外事学院", "2013年09月01日", "2017年06月01日", "日语", "本科"),
        ],
        "note": "源表把三段学历置于“职历”栏；按内容纠正为学历并删除研究/自我介绍伪条目。",
    },
    "江一陶": {
        "work": [
            work("上海市质子重离子医院有限公司", "2016年07月01日", "", "放射物理师", responsibilities="放疗计划、设备与患者计划 QA、剂量验证及数据分析。"),
            work("和冠科技上海分公司", "2013年07月01日", "2013年10月01日", "全球供应链项目助理／行政助理", "实习"),
        ],
        "education": [
            education("复旦大学", "2014年09月01日", "2016年06月01日", "生物医学工程", "工程硕士"),
            education("复旦大学", "2010年09月01日", "2014年06月01日", "核科学与技术", "本科"),
        ],
        "note": "合并中英日重复履历，补回供应链实习。",
    },
    "张震": {
        "work": [work("Don Quijote株式会社", "", "", "销售兼职", "兼职")],
        "education": [
            education("大阪府立大学", "2016年03月01日", "2018年03月01日", "经济金融", "硕士"),
            education("南阳理工学院", "2011年09月01日", "2014年09月01日", "日语", "本科"),
            education("新蔡县高级中学", "2008年09月01日", "2011年06月01日", "文科", "高中"),
        ],
        "note": "将两段学历从工作移回学历，保留源文件明确列出的无日期兼职。",
    },
    "霍炀": {
        "work": [
            work("Japan Forum of Business and Society", "2016年09月01日", "2017年09月01日", "秘书", "兼职"),
            work("早稻田大学大学院商学部", "2016年09月01日", "2017年07月01日", "教学助理", "兼职"),
            work("Harbin Meixintong Construction & Decoration Engineering Company", "2015年01月01日", "2015年06月01日", "经理助理", "实习"),
        ],
        "education": [
            education("早稻田大学大学院", "2016年04月01日", "2018年04月01日", "商学研究科", "硕士"),
            education("富士国际日本语学校", "2015年07月01日", "2016年03月01日", "日语", "语言学校"),
            education("东北大学", "2011年09月01日", "2015年07月01日", "日语", "本科"),
        ],
        "note": "将三段学历、奖学金和模板行从工作中移除，恢复实习与兼职。",
    },
    "孫儀珊": {
        "work": [
            work("日商创周有限公司台湾分公司", "2015年05月01日", "2016年11月01日", "业务", responsibilities="客户开发、商品企划、成本报价、生产质量管理及进口报关。"),
            work("琼安开发股份有限公司", "2014年04月01日", "2015年03月01日", "服装设计助理", responsibilities="成本估算、设计资料建档、样衣确认及设计支持。"),
            work("彦庭国际有限公司", "2011年08月01日", "2012年11月01日", "日语专员", responsibilities="日本品牌联络、市场调查、会议口译及网店运营。"),
        ],
        "education": [
            education("文化服装学院", "2013年01月01日", "2014年01月01日", "服饰研究科", "专门学校"),
            education("明治学院大学", "2009年01月01日", "2010年01月01日", "交换留学", "交换留学"),
            education("东吴大学", "2008年01月01日", "2011年01月01日", "日文系", "本科"),
            education("台北商业技术学院", "2002年01月01日", "2007年01月01日", "企业管理", "五年制专科"),
        ],
        "note": "删除毕业状态、离职原因和模板字段误入工作的问题，按中日源表恢复三段工作与四段学历。",
    },
}


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".tmp", dir=path.parent, delete=False) as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
        temporary = Path(stream.name)
    temporary.replace(path)


def normalize_rows(rows: list[dict[str, Any]], collection: str) -> list[dict[str, Any]]:
    return [MERGE.PARSER.normalize_row(row, MERGE.PARSER.COLLECTION_FIELDS[collection]) for row in rows]


def select_zh(payload: dict[str, Any]) -> dict[str, Any]:
    rows = [
        MERGE.normalize_external_resume(row, "zh")
        for row in ((payload.get("structured_data") or {}).get("resumes") or [])
        if isinstance(row, dict) and MERGE.language(row) == "zh"
    ]
    if not rows:
        raise ValueError("GPT JSON 中没有中文 resume")
    return max(rows, key=MERGE.resume_score)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="生成 PDF GPT 四方复核后的持久化修复覆盖" " / Generate the persistent repair overrides after the four-way PDF/GPT review / PDF の GPT 四者確認後の、永続的な修復上書きを生成する")
    parser.add_argument("--comparison", type=Path, default=DEFAULT_COMPARISON)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    return parser.parse_args()


def main() -> int:
    cfg = parse_args()
    comparison = read_json(cfg.comparison)
    existing_records = []
    if cfg.output.is_file():
        existing_records = [row for row in (read_json(cfg.output).get("records") or []) if isinstance(row, dict)]
    records_by_gpt = {str(row.get("gpt_json") or "").casefold(): row for row in existing_records if row.get("gpt_json")}
    seen: set[str] = set()
    for source in comparison.get("records") or []:
        name = source["candidate_name"]
        facts = FACTS.get(name)
        if facts is None:
            raise KeyError(f"缺少人工复核结论: {name}")
        gpt_path = Path(source["gpt_json"])
        resume = select_zh(read_json(gpt_path))
        before = {"work": len(resume.get("work_experiences") or []), "education": len(resume.get("education_list") or [])}
        resume["work_experiences"] = normalize_rows(facts["work"], "work_experiences")
        resume["education_list"] = normalize_rows(facts["education"], "education_list")
        if "projects" in facts:
            resume["project_list"] = normalize_rows(facts["projects"], "project_list")
        if "training" in facts:
            resume["training_list"] = normalize_rows(facts["training"], "training_list")
        after = {"work": len(resume["work_experiences"]), "education": len(resume["education_list"])}
        reviewed_sources = {
            "pdf": [row["pdf"] for row in source.get("sources") or []],
            "word": [row["word"] for row in source.get("sources") or []],
            "html": [row["html"] for row in source.get("sources") or []],
            "gpt_json": str(gpt_path),
            "candidate_json": source["candidate_json"],
        }
        record = {
            "candidate_name": name,
            "status": "corrected_and_closed",
            "gpt_json": str(gpt_path.resolve()),
            "reviewed_sources": reviewed_sources,
            "before_counts": before,
            "after_counts": after,
            "resolution": facts["note"],
            "corrected_resume": resume,
        }
        records_by_gpt[str(gpt_path.resolve()).casefold()] = record
        seen.add(name)
    records = list(records_by_gpt.values())
    csv_rows = []
    for index, record in enumerate(records, 1):
        before = record.get("before_counts") or {}
        after = record.get("after_counts") or {}
        reviewed = record.get("reviewed_sources") or {}
        csv_rows.append({
            "序号": index,
            "候选人": record.get("candidate_name", ""),
            "复核状态": "已四方复核并修复",
            "修复前工作": before.get("work", ""),
            "修复后工作": after.get("work", ""),
            "修复前学历": before.get("education", ""),
            "修复后学历": after.get("education", ""),
            "处理结论": record.get("resolution", ""),
            "来源PDF": " | ".join(Path(value).name for value in (reviewed.get("pdf") or [])),
        })
    report = {
        "version": VERSION,
        "generated_at": datetime.now().astimezone().isoformat(),
        "total": len(records),
        "status_counts": {"corrected_and_closed": len(records)},
        "review_basis": ["source_pdf_all_pages", "converted_word_html", "gpt_json", "current_candidate_json"],
        "records": records,
    }
    atomic_json(cfg.output, report)
    cfg.csv.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8-sig", newline="", suffix=".tmp", dir=cfg.csv.parent, delete=False) as stream:
        writer = csv.DictWriter(stream, fieldnames=list(csv_rows[0]))
        writer.writeheader()
        writer.writerows(csv_rows)
        temporary = Path(stream.name)
    temporary.replace(cfg.csv)
    print(json.dumps({key: value for key, value in report.items() if key != "records"}, ensure_ascii=False, indent=2))
    print(f"output={cfg.output.resolve()}")
    print(f"csv={cfg.csv.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
