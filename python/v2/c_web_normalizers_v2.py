"""Web/PDF 共用归一化 API（V2 过渡层）。

当前实现显式转发到历史 Web 规则，保证重构期间行为可核对；后续迁移函数体后，调用方接口保持不变。

EN: Normalisation API shared by Web/PDF (V2 transition layer).

The current implementation explicitly forwards to the historical Web rules so behaviour can be checked during the refactor; after the function bodies are migrated later, the caller interface stays the same.

JA: Web/PDF 共通の正規化 API（V2 移行レイヤー）。

現在の実装は過去の Web ルールへ明示的に転送しており、リファクタリング中も挙動を照合できる。今後関数本体を移しても、呼び出し側のインターフェースは変わらない。
"""

from run_web_html_to_json import (
    _normalize_certificate_list_cleanup,
    _normalize_communication_list,
    _normalize_education_list_and_fix_rank,
    _normalize_language_list,
    _normalize_project_list,
    _normalize_training_list_cleanup,
    _pick_highest_education,
    _pick_latest_work,
    _swap_end_start_when_reversed,
)

__all__ = [
    "_normalize_certificate_list_cleanup",
    "_normalize_communication_list",
    "_normalize_education_list_and_fix_rank",
    "_normalize_language_list",
    "_normalize_project_list",
    "_normalize_training_list_cleanup",
    "_pick_highest_education",
    "_pick_latest_work",
    "_swap_end_start_when_reversed",
]
