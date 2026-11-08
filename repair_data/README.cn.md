# repair_data

[English](README.md) | **简体中文** | [日本語](README.ja.md)

两个一次性修复脚本（`python/v2/word_nonchinese_known_name_repair.v2.py`、`word_nonchinese_semantics_repair.v2.py`）需要“姓名/手机号对应表”等个人数据。
这些数据**不随仓库发布**：把真实数据按 `*.example.json` 的格式写成同名的 `known_names.json`、`semantics_repair.json`（不带 `.example`）放在这个目录即可。
`repair_data/*.json`（非 example）已在 `.gitignore` 中排除。
