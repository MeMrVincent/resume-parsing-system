# repair_data

[English](README.md) | [简体中文](README.cn.md) | **日本語**

一回限りの修復スクリプト 2 本（`python/v2/word_nonchinese_known_name_repair.v2.py`、`word_nonchinese_semantics_repair.v2.py`）は、「氏名／電話番号の対応表」などの個人データを必要とします。
このデータは**リポジトリに含めません**：実データを `*.example.json` の形式で、`.example` を付けない同名のファイル（`known_names.json`、`semantics_repair.json`）として、このディレクトリに置いてください。
`repair_data/*.json`（example 以外）は `.gitignore` で除外済みです。
