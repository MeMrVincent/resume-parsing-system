"""可复用的智联规则 API（V2 过渡层）。

这些函数当前仍由 V1 智联实现提供，先把实际公共接口固定下来；后续可在不影响调用方的情况下把函数体迁移到本模块。

EN: Reusable Zhaopin rule API (V2 transition layer).

These functions are still provided by the V1 Zhaopin implementation; the real public interface is fixed here first, and the function bodies can later be moved into this module without affecting callers.

JA: 再利用可能な Zhaopin（智联）ルール API（V2 移行レイヤー）。

これらの関数は現在も V1 の Zhaopin 実装が提供している。まず実際の公開インターフェースをここで固定し、後で呼び出し側に影響を与えずに関数本体を本モジュールへ移せるようにする。
"""

from run_zhilian_html_to_json import (
    _parse_zhilian_expected_info,
    _parse_zhilian_work_experiences,
    _parse_zhilian_education,
    _parse_zhilian_certificates,
    _parse_zhilian_languages,
    _parse_zhilian_skills,
)

__all__ = [
    "_parse_zhilian_expected_info",
    "_parse_zhilian_work_experiences",
    "_parse_zhilian_education",
    "_parse_zhilian_certificates",
    "_parse_zhilian_languages",
    "_parse_zhilian_skills",
]
