"""Web 文本/日期公共 API（V2 过渡层）。

EN: Shared Web text/date API (V2 transition layer).

JA: Web のテキスト・日付共通 API（V2 移行レイヤー）。
"""

from run_chinese_english_html_to_json import (
    plain_text,
    dom_summary,
    parse_resume_dates,
)

__all__ = ["plain_text", "dom_summary", "parse_resume_dates"]
