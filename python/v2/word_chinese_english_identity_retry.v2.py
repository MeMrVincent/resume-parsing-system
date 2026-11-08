"""隔离复制中英文待处理 HTML，并注入由源证据确认的姓名语义节点。

EN: Copy the pending Chinese-English HTML into isolation, and inject name semantic nodes confirmed by source evidence.

JA: 処理待ちの中英の HTML を分離してコピーし、ソースの証拠で確認した氏名の意味ノードを埋め込む。
"""

from __future__ import annotations

import argparse
import html
import json
import shutil
from pathlib import Path


def verified_name(source_path: str) -> str:
    rules = (
        ("陈 震", "陈震"),
        ("郑霄", "郑霄"),
        ("前端周士杰", "周士杰"),
        ("\\郁锋\\", "郁锋"),
        ("\\承朝\\", "承朝"),
        ("\\张卓\\", "张卓"),
        ("CAREER_2010", "陈骏"),
        ("\\张夏冰\\", "张夏冰"),
    )
    normalized = source_path.replace("/", "\\")
    for marker, name in rules:
        if marker.casefold() in normalized.casefold():
            return name
    return ""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    payload = json.loads(args.manifest.read_text(encoding="utf-8"))
    args.output_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for item in payload.get("items") or []:
        if str(item.get("language_folder") or "") != "中英文":
            continue
        source_path = str(item.get("source_path") or "")
        name = verified_name(source_path)
        source_html = Path(str(item.get("html_path") or ""))
        result = {"source_path": source_path, "source_html": str(source_html), "verified_name": name}
        if not name:
            result["status"] = "unmatched_identity_rule"
        elif not source_html.is_file():
            result["status"] = "missing_html"
        else:
            target = args.output_dir / source_html.name
            shutil.copy2(source_html, target)
            text = target.read_text(encoding="utf-8", errors="replace")
            node = (
                f'<p data-field="full_name" label="姓名" '
                f'data-repair-source="verified-source-identity">{html.escape(name)}</p>'
            )
            lower = text.casefold()
            body_at = lower.find("<body")
            body_end = text.find(">", body_at) if body_at >= 0 else -1
            if body_end >= 0:
                text = text[: body_end + 1] + "\n" + node + text[body_end + 1 :]
            else:
                text = node + "\n" + text
            target.write_text(text, encoding="utf-8")
            result.update(status="prepared", staged_html=str(target))
        results.append(result)

    report = {
        "prepared": sum(row.get("status") == "prepared" for row in results),
        "failed": sum(row.get("status") != "prepared" for row in results),
        "items": results,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key != "items"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
