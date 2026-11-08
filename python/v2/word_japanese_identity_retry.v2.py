"""从日文候选文件名末段或直接父目录提取明确姓名，补语义节点重试。

EN: Extract an explicit name from the last segment of the Japanese candidate's file name or the direct parent directory, add a semantic node and retry.

JA: 日本語の候補者のファイル名の末尾の部分か直接の親ディレクトリから明確な氏名を抽出し、意味ノードを補って再試行する。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
from pathlib import Path

from bs4 import BeautifulSoup


BLOCK = re.compile(r"営業|担当|市場|総務|財務|人事|技術|開発|生産|計画|物流|品質|推广|助理|主任|課長|会社|公司|情報|履歴|職歴|職務|简历|日本語|日文|模板|個人経験|フォーマット|スタッフ|マネージャー|セールス|募集|请求|依頼|三菱|電機|职位|職位|介绍|紹介")


def key(value: object) -> str:
    return os.path.normcase(os.path.normpath(str(value or "")))


def clean_name(value: str) -> str:
    value = re.sub(r"(?:JP|J)$", "", value.strip(), flags=re.I)
    value = re.sub(r"[\s　]+", "", value)
    value = value.strip("-_‐―ー（）()[]【】")
    return value


def valid(value: str) -> bool:
    return bool(re.fullmatch(r"[\u3400-\u9fff々〆ヵヶ·]{2,6}", value)) and not BLOCK.search(value)


def infer(source: Path) -> str:
    stem = source.stem.strip()
    candidates = []
    # Newpage/推荐书通常把候选姓名放在最后一个连接符之后。
    # EN: Newpage / recommendation letters usually put the candidate's name after the last connector.
    # JA: Newpage・推薦書は通常、候補者の氏名を最後の接続記号の後に置く。
    for part in reversed(re.split(r"[-_‐―–—]+", stem)):
        name = clean_name(part)
        name = re.sub(r"^(?:NEWPAGE|Newpage|newpage|JNEWPAGE)", "", name)
        if valid(name):
            candidates.append(name)
            break
    # 履历书标题后直接跟姓名。
    # EN: The name follows directly after the rirekisho title.
    # JA: 履歴書のタイトルの直後に氏名が続く。
    title_cleaned = re.sub(r"履\s*歴\s*書|職務経歴書|職歴書|履歴書|简历日文|日文简历|和文|日本語|新版|新|！|!|\d+", " ", stem, flags=re.I)
    for match in re.findall(r"[\u3400-\u9fff々〆ヵヶ][\u3400-\u9fff々〆ヵヶ\s　]{1,10}", title_cleaned):
        name = clean_name(match)
        if valid(name):
            candidates.append(name)
    parent = clean_name(source.parent.name)
    if valid(parent):
        candidates.append(parent)
    return candidates[0] if candidates else ""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--progress", type=Path, required=True)
    parser.add_argument("--existing-json-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    progress = json.loads(args.progress.read_text(encoding="utf-8"))
    existing = set()
    for path in args.existing_json_dir.glob("*.json"):
        if path.name.startswith("_"):
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            existing.add(key((payload.get("source") or {}).get("original_path")))
        except Exception:
            pass
    args.output_dir.mkdir(parents=True, exist_ok=True)
    items = []
    for item in progress.get("unfinished") or []:
        if item.get("status") != "needs_review" or item.get("language_folder") != "日文":
            continue
        source = Path(str(item.get("source_path") or ""))
        html = Path(str(item.get("html_path") or ""))
        if key(source) in existing or not html.is_file():
            continue
        name = infer(source)
        if not name:
            continue
        target = args.output_dir / html.name
        shutil.copy2(html, target)
        soup = BeautifulSoup(target.read_text(encoding="utf-8", errors="replace"), "html.parser")
        node = soup.new_tag("p")
        node["data-field"] = "full_name"
        node["label"] = "氏名"
        node["data-repair-source"] = "source-path-identity-v2"
        node.string = name
        (soup.body or soup).insert(0, node)
        target.write_text(str(soup), encoding="utf-8")
        items.append({"source_path": str(source), "html": str(target), "full_name": name})
    report = {"prepared": len(items), "items": items}
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"prepared": len(items)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
