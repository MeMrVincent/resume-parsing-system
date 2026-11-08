"""为日文解析姓名失败项补充可追溯的姓名语义节点，输出隔离重试 HTML。

EN: Add traceable name semantic nodes for items whose Japanese name parsing failed, and output isolated retry HTML.

JA: 日本語の氏名の解析に失敗した項目に追跡可能な氏名の意味ノードを補い、分離した再試行用の HTML を出力する。
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
from pathlib import Path

from bs4 import BeautifulSoup


def infer_name(source_path: Path) -> str:
    stem = re.sub(r"(?:履歴書|履歴|日本語|日文|日语|简历|個人|写真|新版|最终版|CV)", " ", source_path.stem, flags=re.I)
    excluded = {"通勤時間", "営業", "营业", "总务", "總務", "財務", "财务", "担当", "技術", "技术"}
    candidates = [value for value in re.findall(r"[\u3400-\u9fff]{2,4}", stem) if value not in excluded]
    if candidates:
        return candidates[0]
    parent = source_path.parent.name
    candidates = [value for value in re.findall(r"[\u3400-\u9fff]{2,4}", parent) if value not in excluded]
    return candidates[0] if candidates else ""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--map", type=Path, required=True)
    parser.add_argument("--batch-report", type=Path, required=True)
    parser.add_argument("--audit-report", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    rows = json.loads(args.map.read_text(encoding="utf-8"))
    by_html_name = {Path(str(row.get("html_path") or "")).name.casefold(): row for row in rows}
    batch = json.loads(args.batch_report.read_text(encoding="utf-8"))
    audit = json.loads(args.audit_report.read_text(encoding="utf-8"))
    html_names = {
        Path(str(item.get("html") or "")).name
        for item in batch.get("items") or []
        if str(item.get("status") or "") not in {"success", "skipped", "non_resume"}
    }
    for item in audit.get("items") or []:
        if any(issue.get("code") == "invalid_full_name_semantics" for issue in item.get("issues") or []):
            source = str(item.get("source_path") or "")
            row = next((row for row in rows if str(row.get("source_path") or "") == source), None)
            if row:
                html_names.add(Path(str(row.get("html_path") or "")).name)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for html_name in sorted(html_names):
        row = by_html_name.get(html_name.casefold())
        if not row:
            continue
        source_path = Path(str(row.get("source_path") or ""))
        source_html = Path(str(row.get("html_path") or ""))
        # 正式提升可能已删除原 HTML；样本隔离目录保留了同名副本。
        # EN: Formal promotion may have deleted the original HTML; the sample isolation directory keeps a copy with the same name.
        # JA: 正式な昇格で元の HTML が削除されていることがある。サンプルの分離ディレクトリには同じ名前のコピーが残っている。
        if not source_html.is_file():
            candidates = list(args.batch_report.parent.rglob(html_name))
            if not candidates:
                candidates = list(args.batch_report.parent.parent.rglob(html_name))
            source_html = candidates[0] if candidates else source_html
        if not source_html.is_file():
            continue
        name = infer_name(source_path)
        if not name:
            continue
        target = args.output_dir / html_name
        shutil.copy2(source_html, target)
        soup = BeautifulSoup(target.read_text(encoding="utf-8", errors="replace"), "html.parser")
        node = soup.new_tag("p")
        node["data-field"] = "full_name"
        node["label"] = "氏名"
        node["data-repair-source"] = "source-path-identity"
        node.string = name
        container = soup.body or soup
        container.insert(0, node)
        target.write_text(str(soup), encoding="utf-8")
        results.append({"source_path": str(source_path), "html": str(target), "full_name": name})
    args.report.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"prepared": len(results), "items": results}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
