# repair_data

**English** | [简体中文](README.cn.md) | [日本語](README.ja.md)

Two one-off repair scripts (`python/v2/word_nonchinese_known_name_repair.v2.py` and `word_nonchinese_semantics_repair.v2.py`) need personal data such as a "name / phone number" mapping.
This data is **not published with the repository**: write your real data in the format of the `*.example.json` files into files of the same name without `.example` (`known_names.json`, `semantics_repair.json`) and put them in this directory.
`repair_data/*.json` (other than the examples) is already excluded in `.gitignore`.
