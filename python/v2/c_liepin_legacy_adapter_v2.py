"""仍依赖 V1 猎聘解析器的最小兼容 API。

EN: Minimal compatible API that still depends on the V1 Liepin parser.

JA: いまだ V1 のLiepinパーサーに依存する最小限の互換 API。
"""

from run_liepin_html_to_json import (
    read_html_text,
    plain_text,
    build_record_from_html,
)

__all__ = ["read_html_text", "plain_text", "build_record_from_html"]
