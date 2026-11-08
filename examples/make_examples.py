#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
make_examples.py —— 生成虚构的示例简历 JSON（examples/v1、examples/v2），用来演示 V3 合并流程。
所有姓名、手机号、邮箱、公司都是虚构的（手机号 138 0000 xxxx，邮箱 @example.com）。

用法（项目根目录）：  python examples/make_examples.py
然后用示例目录跑合并：  python python/v3/claude_merge.v3.py --v2-dir examples/v2 --v1-dir examples/v1 --out-root examples/output --run-id 20260101-demo

EN: make_examples.py -- generates fictional sample résumé JSON (examples/v1, examples/v2) to demonstrate the V3 merge flow.
All names, phone numbers, e-mails and companies are fictional (phone numbers 138 0000 xxxx, e-mails @example.com).

Usage (from the project root):  python examples/make_examples.py
Then run the merge on the sample directories:  python python/v3/claude_merge.v3.py --v2-dir examples/v2 --v1-dir examples/v1 --out-root examples/output --run-id 20260101-demo

JA: make_examples.py —— V3 統合フローのデモ用に、架空のサンプル履歴書 JSON（examples/v1、examples/v2）を生成する。
氏名・電話番号・メール・会社はすべて架空（電話番号は 138 0000 xxxx、メールは @example.com）。

使い方（プロジェクトルートで）：  python examples/make_examples.py
その後サンプルディレクトリで統合を実行：  python python/v3/claude_merge.v3.py --v2-dir examples/v2 --v1-dir examples/v1 --out-root examples/output --run-id 20260101-demo
"""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent

BASE_KEYS = ["full_name", "gender", "age", "birth_date", "birth_year", "marital_status", "children_status", "political_status",
             "height_cm", "weight_kg", "household_registration", "address", "postal_code", "platform_from", "platform_resume_id",
             "phone", "email", "city", "nationality", "pr"]
WORK = ["company_name", "company_employees", "company_industry", "position", "position_type", "position_salary", "position_dept",
        "position_report_to", "position_subordinate", "employment_type", "annual_salary_min", "annual_salary_max", "status",
        "position_start", "position_resigned", "resigned_reason", "position_responsibilities", "position_achievements"]
EDU = ["school_name", "school_major_name", "school_degree_type", "school_degree_rank", "school_education_type", "school_start_ym", "school_end_ym"]
CERT = ["certificate_name", "certificate_type", "certificate_time"]
LANG = ["language_name", "language_level", "language_certificate", "language_certificate_time"]
SKILL = ["skill_name", "skill_level"]
EXPECT = ["expected_city", "expected_position", "expected_salary", "expected_annual_salary_min", "expected_annual_salary_max",
          "expected_industry", "expected_employment_type", "expected_start_date"]


def row(keys, **kw):
    r = {k: "" for k in keys}
    r.update(kw)
    return r


def resume(lang, base, work=(), edu=(), cert=(), langs=(), skills=(), expect=()):
    b = row(BASE_KEYS, **base)
    return {
        "base_info": b,
        "work_experiences": [row(WORK, **w) for w in work],
        "education_list": [row(EDU, **e) for e in edu],
        "certificate_list": [row(CERT, **c) for c in cert],
        "language_list": [row(LANG, **l) for l in langs],
        "skills_list": [row(SKILL, **s) for s in skills],
        "training_list": [], "project_list": [],
        "communication_list": [], "resume_language": lang, "keywords": "",
        "expected_list": [row(EXPECT, **e) for e in expect],
    }


def record(src_name, resumes, raw_text, updated="2024-05-01 10:00:00"):
    first = resumes[0]
    return {
        "source": {"original_path": f"<项目根>/需要采集的简历文件夹/示例/{src_name}"},
        "dates": {"resume_updated_date": updated, "resume_download_date": "2024-05-02 09:00:00",
                  "sys_created_date": "2026-01-01T09:00:00+09:00", "sys_updated_date": "2026-01-01T09:00:00+09:00"},
        "structured_data": {
            "base_info": dict(first["base_info"]),
            "expected_info": dict(first["expected_list"][0]) if first["expected_list"] else row(EXPECT),
            "current_info": {k: first["work_experiences"][0][k] for k in WORK[:-2] if k in first["work_experiences"][0]} if first["work_experiences"] else {},
            "education_info": dict(first["education_list"][0]) if first["education_list"] else row(EDU),
            "resumes": resumes,
        },
        "raw_text": raw_text,
    }


def write(sub, name, rec):
    d = HERE / sub
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_text(json.dumps(rec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


# ---- 陈思明：只有中文版（V2 和 V1 各一份，V1 更旧，合并时 V2 优先、V1 补充）
# EN: ---- Chen Siming: Chinese version only (one V2 and one V1; V1 is older, so V2 takes priority when merging and V1 fills gaps)
# JA: ---- 陈思明：中国語版のみ（V2 と V1 が各 1 件。V1 の方が古いため、統合時は V2 を優先し V1 で補完）
zs_zh = resume("zh",
    dict(full_name="陈思明", gender="男", birth_date="1990年05月01日", birth_year="1990", phone="13800000001", email="chensiming@example.com", city="上海", platform_from="示例平台"),
    work=[dict(company_name="示例科技有限公司", position="软件工程师", position_start="2016年07月01日", position_resigned="", status="在职",
               position_responsibilities="负责后端接口开发与维护。\n参与数据平台建设。"),
          dict(company_name="虚构信息咨询有限公司", position="助理工程师", position_start="2013年07月01日", position_resigned="2016年06月01日",
               position_responsibilities="协助完成系统测试。")],
    edu=[dict(school_name="示例大学", school_major_name="计算机科学", school_degree_type="本科", school_degree_rank="4", school_start_ym="2009年09月01日", school_end_ym="2013年06月01日")],
    cert=[dict(certificate_name="软件设计师", certificate_type="证书", certificate_time="2014年05月01日")],
    langs=[dict(language_name="英语", language_level="良好")], skills=[dict(skill_name="Python", skill_level="熟练")],
    expect=[dict(expected_city="上海", expected_position="软件工程师", expected_salary="20001-30000元/月", expected_employment_type="全职")])
write("v2", "陈思明_13800000001.json", record("陈思明简历.docx", [zs_zh], "陈思明\n男 1990年05月01日\n示例科技有限公司 软件工程师\n示例大学 计算机科学 本科"))
zs_v1 = json.loads(json.dumps(zs_zh, ensure_ascii=False))
zs_v1["base_info"]["address"] = "上海市示例区示例路1号"
write("v1", "陈思明_13800000001.json", record("陈思明简历.docx", [zs_v1], "陈思明 旧版本", updated="2023-01-01 10:00:00"))

# ---- 林雅婷：中文 + 英文两个语言版本
# EN: ---- Lin Yating: two language versions, Chinese + English
# JA: ---- 林雅婷：中国語 + 英語の 2 言語版
ls_zh = resume("zh", dict(full_name="林雅婷", gender="女", birth_year="1992", phone="13800000002", email="linyating@example.com", city="北京", platform_from="示例平台"),
    work=[dict(company_name="示例贸易有限公司", position="销售经理", position_start="2018年03月01日", position_resigned="", status="在职",
               position_responsibilities="负责华东区客户开发。")],
    edu=[dict(school_name="示例外国语大学", school_major_name="英语", school_degree_type="本科", school_degree_rank="4", school_start_ym="2010年09月01日", school_end_ym="2014年06月01日")],
    langs=[dict(language_name="英语", language_level="流利")])
ls_en = resume("en", dict(full_name="Lin Yating", gender="Female", birth_year="1992", phone="13800000002", email="linyating@example.com", city="Beijing", platform_from="Example Platform"),
    work=[dict(company_name="Example Trading Co., Ltd.", position="Sales Manager", position_start="2018年03月01日", position_resigned="", status="Current",
               position_responsibilities="Responsible for customer development in East China.")],
    edu=[dict(school_name="Example University of Foreign Studies", school_major_name="English", school_degree_type="Bachelor", school_degree_rank="4", school_start_ym="2010年09月01日", school_end_ym="2014年06月01日")],
    langs=[dict(language_name="English", language_level="Fluent")])
write("v2", "林雅婷_13800000002.json", record("林雅婷简历中英文.docx", [ls_zh, ls_en], "林雅婷\nLin Yating\n示例贸易有限公司 销售经理"))

# ---- John Smith：只有英文版 -> 没有中文主版本，进入 pending_translation
# EN: ---- John Smith: English version only -> no Chinese primary version, goes to pending_translation
# JA: ---- John Smith：英語版のみ -> 中国語の主版がないため pending_translation へ
js_en = resume("en", dict(full_name="John Smith", gender="Male", birth_year="1988", phone="13800000003", email="john.smith@example.com", city="Shanghai", platform_from="Example Platform"),
    work=[dict(company_name="Sample Industries Ltd.", position="Project Manager", position_start="2015年01月01日", position_resigned="", status="Current",
               position_responsibilities="Lead cross-functional project teams.")],
    edu=[dict(school_name="Sample State University", school_major_name="Business Administration", school_degree_type="Bachelor", school_degree_rank="4", school_start_ym="2006年09月01日", school_end_ym="2010年06月01日")])
write("v2", "John Smith_13800000003.json", record("john_smith_resume.pdf", [js_en], "John Smith\nProject Manager\nSample Industries Ltd."))

# ---- 赵建国：没有手机号和邮箱 -> 不进输出，记入 no_contact_ledger
# EN: ---- Zhao Jianguo: no phone number or e-mail -> not output, recorded in no_contact_ledger
# JA: ---- 赵建国：電話番号もメールもない -> 出力せず no_contact_ledger に記録
ww = resume("zh", dict(full_name="赵建国", gender="男", city="广州"), work=[dict(company_name="虚构制造有限公司", position="技术员", position_start="2019年01月01日")])
write("v2", "赵建国_无联系方式.json", record("赵建国简历.doc", [ww], "赵建国 虚构制造有限公司 技术员"))
print("examples written")
