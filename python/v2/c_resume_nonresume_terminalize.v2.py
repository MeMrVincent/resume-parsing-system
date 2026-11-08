"""终止 review 中名称明确的非简历文件；保守规则，不处理含糊候选。

EN: Terminate files in review that are clearly named as non-résumés; conservative rule, ambiguous candidates are not touched.

JA: review 内で名前から明らかに非履歴書とわかるファイルを終了扱いにする。保守的なルールで、曖昧な候補には手を付けない。
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


PATTERN = re.compile(
    r"JD模板|职位\s*JD|职位简介|招聘职位|招聘信息|职位更新|求人[スシ]?[ペベ]ック|"
    r"会社紹介|公司介绍|集团公司一览|合同|协议书|协议$|开票信息|福利待遇|"
    r"入职体检|体检须知|入职所需资料|空白模[板版]|面试通知|面接対策|照片\.docx?|"
    r"刷单流程|网上可以买的家装材料|(?:^|[\\/])照片\.docx?$|"
    r"学历资格证书|证书材料|見積もり書|培训提纲|工作总结|契約書|笔试|筆試|"
    r"面接前送付情報|面接対策|人物像|职位信息|職位情報|工作内容$|"
    r"わたしのベスト|BEST\s*[３3]|宿題|入职资料|会社情報|人才测评ID|"
    r"付款申请书|岗位\s*JD|\bJD\s*\(|公司大体信息|雇员服务信息表|个人信息采集表|"
    r"推报告\s*-\s*模板|人才推荐书(?:EN|JP)\.doc|人材紹介依頼書|日文简历模板|"
    r"履歴書のフォーマット|注册招聘|登録招聘|招聘\s*\(|招聘\s*[（(]|晓丹职位情况|"
    r"旭化成投资-(?:IT|技术营业)|旭化成-法务|财务\s*200506|环安\s*[（(]004|"
    r"Newpage-[^-]+-\s*JP\.doc|"
    r"人材募集|募集中\s*JD|求人要件|(?:^|[\\/])JD[-_－—]|"
    r"(?:^|[\\/])[^\\/]*(?:职位内容|相關職位|相关职位|公司信息表|公司資料|"
    r"面试内容|面試內容|信息补充信息|情報共有|情报共有|测试题答案[^\\/]*|測試題答案[^\\/]*|"
    r"9个问题让你瞬间看穿候选人|负责区域情况|嵌入式，软硬件相关知识)\.docx?$|"
    r"(?:^|[\\/])MLCC[^\\/]*班长[^\\/]*\.docx?$|(?:^|[\\/])职位介绍[\\/]|"
    r"(?:^|[\\/])[^\\/]*课程\.docx?$|(?:^|[\\/])COVER\s+LETTER\.docx?$|"
    r"(?:^|[\\/])[^\\/]*职位\.docx?$",
    re.I,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--map", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--statuses", nargs="+", default=["needs_review"])
    args = parser.parse_args()
    rows = json.loads(args.map.read_text(encoding="utf-8"))
    items = []
    for row in rows:
        if row.get("status") not in args.statuses:
            continue
        evidence = str(row.get("source_path") or "") + "\n" + str(row.get("filename") or "")
        match = PATTERN.search(evidence)
        if not match:
            continue
        item = {"source_path": row.get("source_path"), "html_path": row.get("html_path"), "matched": match.group(0)}
        if args.apply:
            html = Path(str(row.get("html_path") or ""))
            if html.is_file():
                html.unlink()
                item["html_deleted"] = True
            row["status"] = "non_resume"
            row["terminal_classification"] = "non_resume"
            row["error_reason"] = f"明确非简历资料：{match.group(0)}"
        items.append(item)
    if args.apply:
        args.map.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report = {"mode": "apply" if args.apply else "dry-run", "selected": len(items), "items": items}
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"mode": report["mode"], "selected": len(items)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
