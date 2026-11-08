"""向已人工核实的语义 HTML 注入权威姓名节点。

EN: Inject authoritative name nodes into semantic HTML that has been verified manually.

JA: 人手で確認済みのセマンティック HTML に、正とする氏名ノードを埋め込む。
"""

from __future__ import annotations

import argparse
import html
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--html", type=Path, required=True)
    parser.add_argument("--name", required=True)
    args = parser.parse_args()
    text = args.html.read_text(encoding="utf-8", errors="replace")
    node = f'<p data-field="full_name" label="姓名" data-repair-source="verified-source-identity">{html.escape(args.name)}</p>'
    body = text.casefold().find("<body")
    end = text.find(">", body) if body >= 0 else -1
    text = text[: end + 1] + "\n" + node + text[end + 1 :] if end >= 0 else node + "\n" + text
    args.html.write_text(text, encoding="utf-8")
    print(str(args.html))


if __name__ == "__main__":
    main()
