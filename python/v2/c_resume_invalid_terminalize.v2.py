"""终止已人工核对的 14 份 passed 中文非简历/身份不可恢复文件。

EN: Terminate the 14 manually verified "passed" Chinese files that are non-résumés or whose identity cannot be recovered.

JA: 人手で確認済みの passed 中国語ファイルのうち、非履歴書または本人を特定できない 14 件を終了扱いにする。
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


NON_RESUME = re.compile(r"大金中国-|工业园区公司内部结构|体检模板|药物添加剂模板|补充医疗保障福利服务手册")
IDENTITY_UNRECOVERABLE = {"2.docx", "7搜索不到.docx", "ID.docx", "企划  1 夏普.docx", "企划   3.docx"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--progress", type=Path, required=True)
    parser.add_argument("--map", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    progress = json.loads(args.progress.read_text(encoding="utf-8"))
    selected = {
        str(item.get("source_path") or ""): item
        for item in progress.get("unfinished") or []
        if item.get("status") == "passed" and item.get("language_folder") == "中文"
    }
    rows = json.loads(args.map.read_text(encoding="utf-8"))
    results = []
    for row in rows:
        source_path = str(row.get("source_path") or "")
        if source_path not in selected:
            continue
        filename = str(row.get("filename") or Path(source_path).name)
        if NON_RESUME.search(filename) or "职位介绍" in source_path:
            status, reason = "non_resume", "已逐份核对：职位/组织/体检/福利资料，不是候选人简历"
        elif filename in IDENTITY_UNRECOVERABLE:
            status, reason = "identity_unrecoverable", "已逐份核对：平台姓名及联系方式完全遮蔽，无法恢复候选人身份"
        else:
            raise RuntimeError(f"未覆盖的 passed 中文文件：{source_path}")
        html = Path(str(row.get("html_path") or ""))
        if html.is_file():
            html.unlink()
        row["status"] = status
        row["terminal_classification"] = status
        row["error_reason"] = reason
        results.append({"source_path": source_path, "status": status, "reason": reason})
    if len(results) != len(selected):
        raise RuntimeError(f"映射更新数 {len(results)} != 清单数 {len(selected)}")
    args.map.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report = {"total": len(results), "non_resume": sum(r["status"] == "non_resume" for r in results), "identity_unrecoverable": sum(r["status"] == "identity_unrecoverable" for r in results), "items": results}
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "items"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
