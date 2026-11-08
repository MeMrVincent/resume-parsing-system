from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path

from bs4 import BeautifulSoup


PRIMARY_FIELDS = {
    "work_experience": {"company_name", "position", "position_start", "position_responsibilities"},
    "education": {"school_name", "school_start_ym"},
    "certificate": {"certificate_name"},
    "language": {"language_name"},
    "skill": {"skill_name"},
    "expected": {"expected_position", "expected_city", "expected_salary"},
}


def audit(root: Path) -> dict[str, object]:
    files = sorted(root.glob("*.html"))
    record_counts: Counter[str] = Counter()
    repair_modes: Counter[str] = Counter()
    errors: list[dict[str, object]] = []
    article_count = 0
    empty_fields = 0

    for path in files:
        soup = BeautifulSoup(path.read_text(encoding="utf-8"), "lxml")
        main = soup.find("main", attrs={"data-role": "document-content"})
        document = soup.find("article", attrs={"data-schema-version": "resume-dom-v1"})
        file_errors: list[str] = []
        if main is None or document is None:
            file_errors.append("missing_semantic_root")
        else:
            articles = list(main.find_all("article", attrs={"data-role": "resume"}, recursive=False))
            article_count += len(articles)
            if not articles:
                file_errors.append("missing_resume_article")
            expected = list(range(1, len(articles) + 1))
            actual = [int(node.get("data-resume-index") or 0) for node in articles]
            if actual != expected:
                file_errors.append("bad_resume_indices")
        if soup.find("img") or "[pic]" in soup.get_text(" ", strip=True).casefold():
            file_errors.append("image_or_placeholder")
        if document is not None:
            repair_modes[str(document.get("data-dom-repair-mode") or "specialized-or-generator")] += 1

        for node in soup.find_all(attrs={"data-field": True}):
            value = node.get_text(" ", strip=True)
            if not value:
                empty_fields += 1
                file_errors.append("empty_data_field")
            field = str(node.get("data-field") or "")
            if field.endswith(("_ym", "_date", "_time")):
                for month in re.findall(r"(?:19|20)\d{2}[-/.年](\d{1,2})", value):
                    if not 1 <= int(month) <= 12:
                        file_errors.append("illegal_month")

        containers = soup.find_all(attrs={"data-record-type": True})
        for container in containers:
            record_type = str(container.get("data-record-type") or "")
            record_counts[record_type] += 1
            fields = {
                str(node.get("data-field") or "")
                for node in container.find_all(attrs={"data-field": True})
            }
            primary = PRIMARY_FIELDS.get(record_type)
            if primary is None or not fields.intersection(primary):
                file_errors.append(f"record_without_primary:{record_type}")

        for parent in soup.find_all(attrs={"data-collection": True}):
            by_type: dict[str, list[int]] = {}
            for container in parent.find_all(attrs={"data-record-type": True}):
                # 嵌套 collection 各自维护索引，不能把子 collection 的记录
                # 合并到父 collection 后再判断连续性。
                # EN: Nested collections each maintain their own index; records of a child collection must not
                #     be merged into the parent collection before checking continuity.
                # JA: 入れ子の collection はそれぞれ独自の番号を持つ。子の collection のレコードを
                #     親の collection に統合してから連続性を判定してはならない。
                if container.find_parent(attrs={"data-collection": True}) is not parent:
                    continue
                kind = str(container.get("data-record-type") or "")
                try:
                    index = int(container.get("data-record-index") or 0)
                except ValueError:
                    index = 0
                by_type.setdefault(kind, []).append(index)
            for indices in by_type.values():
                if indices != list(range(1, len(indices) + 1)):
                    file_errors.append("bad_record_indices")

        if file_errors:
            errors.append({"html_path": str(path), "issues": sorted(set(file_errors))})

    return {
        "root": str(root),
        "html_files": len(files),
        "resume_articles": article_count,
        "record_counts": dict(sorted(record_counts.items())),
        "repair_modes": dict(sorted(repair_modes.items())),
        "empty_fields": empty_fields,
        "error_files": len(errors),
        "errors": errors,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    result = audit(args.root)
    if args.report:
        args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key != "errors"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
