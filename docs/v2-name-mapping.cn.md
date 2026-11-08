# Word / XLS 转 JSON v2 文件命名对照

[English](v2-name-mapping.md) | **简体中文** | [日本語](v2-name-mapping.ja.md)

> 本文档描述 V2（word/xls/pdf/html → JSON）流程。目录默认值见根目录 `config.example.json`；文中的 `<项目根>` 即 config 里的 project_root。已合并的重复脚本见本文末尾。

本目录中的原始脚本全部保留。本批新增的 `*.v2.py` 文件是便于后续核对的独立副本，当前保持原脚本逻辑和原导入关系，不代表已经切换生产入口。

## Word 专属代码

| 原文件 | v2 文件 | 职责 |
|---|---|---|
| `process_word_to_html.py` | `c_resume_html_dom_common.v2.py` | Word → 语义 HTML 主转换 |
| `process_word_html_to_json.py` | `word_to_html_to_json.v2.py` | 语义 HTML → JSON 主解析 |
| `codex_word_html_json_100.py` | `word_schema_extension.v2.py` | Word schema 扩展 |
| `run_chinese_html_to_json.py` | `run_chinese_html_to_json.py` | 中文 HTML 解析入口 |
| `run_chinese_english_html_to_json.py` | `run_chinese_english_html_to_json.py` | 中英文 HTML 解析入口 |
| `run_chinese_japanese_html_to_json.py` | `word_chinese_japanese_html_to_json.v2.py` | 中日文 HTML 解析入口 |
| `run_japanese_html_to_json.py` | `word_japanese_html_to_json.v2.py` | 日文 HTML 解析入口 |
| `repair_semantic_html_dom.py` | `word_semantic_html_repair.v2.py` | Word 语义 DOM 修复 |
| `audit_semantic_html_batch.py` | `word_semantic_html_audit.v2.py` | Word 语义 HTML 批量审计 |
| `audit_and_fix_htmls.py` | `word_html_audit_fix.v2.py` | Word HTML 早期审计与修复 |
| `full_docs_deep_repair.py` | `word_full_docs_repair.v2.py` | Word 全目录深度修复 |
| `repair_nonchinese_remaining_semantics.py` | `word_nonchinese_semantics_repair.v2.py` | 非中文语义修复 |
| `repair_nonchinese_known_names.py` | `word_nonchinese_known_name_repair.v2.py` | 非中文已确认姓名修复 |
| `inject_verified_html_identity.py` | `word_verified_identity_inject.v2.py` | 已核实身份字段注入 |
| `word_japanese_identity_retry.v2.py` | `word_japanese_identity_retry.v2.py` | 日文身份重试准备 |
| `prepare_japanese_name_retry.py` | `word_japanese_name_retry.v2.py` | 日文姓名重试准备 |
| `prepare_chinese_english_identity_retry.py` | `word_chinese_english_identity_retry.v2.py` | 中英文身份重试准备 |
| `stage_detected_multilingual_parser_results.py` | `word_multilingual_parser_stage.v2.py` | 多语言结果暂存 |
| `stage_complete_english_parser_results.py` | `word_english_parser_stage.v2.py` | 英文结果暂存 |
| `stage_strong_chinese_resume_candidates.py` | `word_strong_candidate_stage.v2.py` | 中文候选筛选 |
| `build_staged_audit_input.py` | `word_staged_audit_input.v2.py` | 审计输入构建 |
| `repair_chinese_from_source_audit.py` | `word_chinese_source_repair.v2.py` | 中文源审计修复 |
| `stage_unique_name_formal_reuse.py` | `word_unique_name_reuse_stage.v2.py` | 唯一姓名历史复用暂存 |
| `stage_multilingual_complete_v1_matches.py` | `word_multilingual_v1_match_stage.v2.py` | 多语言历史匹配暂存 |
| `repair_nonchinese_complete_v1.py` | `word_nonchinese_v1_repair.v2.py` | 非中文历史候选修复 |
| `defer_difficult_review_items.py` | `word_difficult_review_defer.v2.py` | 疑难项人工延期 |
| `refresh_pending_ocr_folder.py` | `word_ocr_folder_refresh.v2.py` | OCR 目录刷新 |
| `report_batch_documents_without_json.py` | `word_batch_without_json_report.v2.py` | 批次缺失 JSON 对账 |
| `terminalize_invalid_unknown_jsons.py` | `word_invalid_unknown_terminalize.v2.py` | unknown 无效项终态 |
| `finalize_failed1_batch.py` | `word_failed_batch_finalize.v2.py` | failed 批次收尾 |

## XLS 专属代码

| 原文件 | v2 文件 | 职责 |
|---|---|---|
| `build_xls_conversion_map.py` | `xls_conversion_map.v2.py` | XLS 源文件映射建立 |
| `process_xls_to_html.py` | `process_xls_to_html.py` | XLS → 语义 HTML 主转换 |
| `process_xls_html_to_json.py` | `xls_to_html_to_json.v2.py` | XLS 语义 HTML → JSON 主解析 |
| `audit_xls_all_fields.py` | `xls_field_audit.v2.py` | XLS 逐字段 DOM 审计 |
| `audit_xls_html_json.py` | `xls_html_json_audit.v2.py` | XLS HTML/JSON 审计 |
| `audit_xls_json_outputs.py` | `xls_json_audit.v2.py` | XLS JSON 输出审计 |
| `audit_xls_source_html_json.py` | `xls_source_html_json_audit.v2.py` | XLS 源文件/HTML/JSON 审计 |
| `bidirectional_review_xls_jsons.py` | `xls_bidirectional_review.v2.py` | XLS 与 complete-v1 双向复核 |
| `rebuild_xls_report.py` | `xls_report_rebuild.v2.py` | XLS 总报告重建 |
| `reprocess_side_by_side_xls.py` | `xls_side_by_side_reprocess.v2.py` | XLS 左右双语专项重跑 |
| `reprocess_xls_incremental.py` | `xls_incremental_reprocess.v2.py` | XLS 异常增量重跑 |
| `normalize_existing_xls_jsons.py` | `xls_json_normalize.v2.py` | XLS 历史 JSON 归一化 |
| `repair_existing_xls_dom_labels.py` | `xls_dom_repair.v2.py` | XLS DOM 标签修复 |

## Word/XLS 共用代码

| 原文件 | v2 文件 | 职责 |
|---|---|---|
| `process_word_to_html.py` | `c_resume_html_dom_common.v2.py` | 通用语义 HTML/DOM 基础能力快照 |
| `process_word_html_to_json.py` | `c_resume_html_to_json_common.v2.py` | 通用 HTML → complete-v1 基础解析快照 |
| `reuse_complete_v1_jsons.py` | `reuse_complete_v1_jsons.py` | complete-v1 结构校验与复用工具 |
| `classify_passed_html_by_language.py` | `classify_passed_html_by_language.py` | 语言检测与目录分类 |
| `audit_chinese_json_against_sources.py` | `audit_chinese_json_against_sources.py` | 源文件逐字段证据审计 |
| `audit_nonchinese_json_against_sources.py` | `c_resume_nonchinese_source_audit.v2.py` | 非中文源文件审计 |
| `promote_audited_chinese_json.py` | `c_resume_json_promote.v2.py` | 审计通过 JSON 晋升 |
| `promote_audited_nonchinese_json.py` | `c_resume_nonchinese_promote.v2.py` | 非中文 JSON 晋升 |
| `finalize_promoted_sources.py` | `c_resume_source_finalize.v2.py` | 源路径登记与 HTML 清理 |
| `build_global_docs_progress.py` | `c_resume_global_progress.v2.py` | 源路径级全局进度 |
| `stage_documents_for_user_ocr.py` | `c_resume_ocr_stage.v2.py` | 人工 OCR 文件暂存 |
| `normalize_and_validate_user_ocr_jsons.py` | `c_resume_ocr_normalize.v2.py` | 人工 OCR JSON 归一化与校验 |
| `finalize_user_ocr_jsons.py` | `c_resume_ocr_finalize.v2.py` | 人工 OCR JSON 正式登记 |
| `stage_unknown_documents.py` | `c_resume_unknown_stage.v2.py` | unknown/failed 文件暂存 |
| `mark_conversion_terminal.py` | `c_resume_terminal_status.v2.py` | 源文件终态登记 |
| `terminalize_obvious_nonresume_review.py` | `c_resume_nonresume_terminalize.v2.py` | 明确非简历终态处理 |
| `terminalize_unusable_passed_chinese.py` | `c_resume_invalid_terminalize.v2.py` | 无效简历终态处理 |

## 通用类快照

这些文件按类名命名，原位置 `python/resume_importer/` 下的实现仍然保留。

| 原文件 | v2 文件 | 主要类 |
|---|---|---|
| `resume_importer/classifier.py` | `document_classifier.v2.py` | `Classification`、`DocumentClassifier` |
| `resume_importer/codex_gemini_html_schema_parser.py` | `codex_gemini_html_schema_parser.v2.py` | `CodexGeminiHtmlSchemaParser` |
| `resume_importer/structured_parser.py` | `structured_resume_parser.v2.py` | `StructuredResumeParser` |
| `resume_importer/extractors.py` | `c_resume_text_extractor.v2.py` | `ExtractionError`、`ResumeTextExtractor` |
| `resume_importer/universal_schema_parser.py` | `universal_schema_parser.v2.py` | `UniversalSchemaParser` |
| `resume_importer/preread/reader_base.py` | `format_reader_base.v2.py` | `BaseFormatReader` |

## PDF 专属代码

| 原文件 | v2 文件 | 职责 |
|---|---|---|
| `process_pdf_to_html.py` | `pdf_to_html.v2.py` | PDF → 语义 HTML |
| `process_pdf_html_to_json.py` | `pdf_to_html_to_json.v2.py` | 语义 HTML → JSON |
| `validate_and_repair_pdf_json.py` | `pdf_json_validate.v2.py` | 基础 JSON 校验与修复 |
| `strict_validate_and_repair_pdf_json.py` | `pdf_json_strict_validate.v2.py` | 严格语义校验与修复 |
| `audit_pdf_json_against_sources.py` | `pdf_source_audit.v2.py` | PDF/HTML/JSON 源证据审计 |
| `parallel_pdf_to_html.py` | `pdf_parallel_to_html.v2.py` | PDF 并行转 HTML |
| `convert_pdf_report.py` | `pdf_conversion_map.v2.py` | PDF 源清单与映射建立 |
| `merge_pdf_conversion_reports.py` | `pdf_conversion_report_merge.v2.py` | PDF 转换报告合并 |
| `incremental_source_repair.py` | `pdf_source_repair.v2.py` | 源证据增量修复 |
| 新增 | `pdf_incremental_guard.v2.py` | 哈希快照、问题账本与合格候选安全晋升 |
| 新增 | `pdf_metadata_leak_repair.v2.py` | `section-profile/evidence` 及序列化分隔符字段污染专项增量修复 |
| `pdfs_to_complete.py` | `pdf_legacy_to_complete.v2.py` | 旧版 PDF 直接转 complete JSON |
| `resume_importer/preread/pdf_reader.py` | `pdf_format_reader.v2.py` | `PdfFormatReader` 类实现 |
| `jsons_to_complete.py` | `jsons_to_complete.py` | 旧版 complete JSON schema 兼容工具 |

## 后续约定

1. 原始文件不删除、不覆盖，仍作为历史基线。
2. PDF→HTML→JSON 主流程、校验、审计、修复和批处理代码一律使用 `pdf_*.v2.py`；不再新增 `pdf_*_v2.py` 或无版本号的 PDF 实现。
3. 本表左栏的无版本号文件仅是只读 V1 历史基线，不是当前入口，也不得被 V2 主流程引用。
4. 后续逻辑重构时，以 `word_to_html_to_json.v2.py`、`xls_to_html_to_json.v2.py`、`pdf_to_html.v2.py`、`pdf_to_html_to_json.v2.py` 和通用 v2 模块为新基线。
5. `.v2.py` 文件需要复用时，使用运行时按文件路径加载；禁止为了普通 `import` 再复制一份 `_v2.py` 同内容实现。

## 已拆出的公共 V2 API

| V2 API 文件 | 当前来源 | 复用接口 |
|---|---|---|
| `c_web_zhilian_rules.v2.py` / `c_web_zhilian_rules_v2.py` | `run_zhilian_html_to_json.py` | 求职意向、工作、教育、证书、语言、技能解析 |
| `c_web_normalizers.v2.py` / `c_web_normalizers_v2.py` | `run_web_html_to_json.py` | 教育、工作、证书、语言、培训、项目、沟通归一化 |
| `c_web_text_rules.v2.py` / `c_web_text_rules_v2.py` | `run_chinese_english_html_to_json.py` | 纯文本、DOM 摘要、日期解析 |
| `c_liepin_legacy_adapter.v2.py` / `c_liepin_legacy_adapter_v2.py` | `run_liepin_html_to_json.py` | 猎聘 HTML 读取、纯文本和记录构建 |

其中带点文件是人工核对入口，带下划线的 `_v2.py` 文件是 Python 可 import 的实现入口。当前这些 API 仍是 V1 函数的显式过渡转发，后续迁移函数体时保持接口不变。


## 整理发布时去掉的重复脚本

以下脚本与右侧保留的脚本内容完全相同，整理仓库时已删除（文档中的命令已同步改成保留的名字）：

| 已删除 | 保留 |
|---|---|
| `c_resume_source_audit.v2.py` | `audit_chinese_json_against_sources.py` |
| `word_to_html.v2.py` | `c_resume_html_dom_common.v2.py` |
| `c_resume_language_classifier.v2.py` | `classify_passed_html_by_language.py` |
| `c_resume_legacy_schema.v2.py` | `jsons_to_complete.py` |
| `c_resume_schema_validator.v2.py` | `reuse_complete_v1_jsons.py` |
| `prepare_japanese_identity_retry_v2.py` | `word_japanese_identity_retry.v2.py` |
| `xls_to_html.v2.py` | `process_xls_to_html.py` |
| `word_chinese_english_html_to_json.v2.py` | `run_chinese_english_html_to_json.py` |
| `word_chinese_html_to_json.v2.py` | `run_chinese_html_to_json.py` |

以下 6 个文件是 `resume_importer/` 包内模块的同内容副本（或其子包已不存在的残留），没有任何脚本引用，整理时已删除；对应关系：

| 已删除 | 等同于 |
|---|---|
| `c_resume_text_extractor.v2.py` | `resume_importer/extractors.py` |
| `codex_gemini_html_schema_parser.v2.py` | `resume_importer/codex_gemini_html_schema_parser.py` |
| `document_classifier.v2.py` | `resume_importer/classifier.py` |
| `structured_resume_parser.v2.py` | `resume_importer/structured_parser.py` |
| `universal_schema_parser.v2.py` | `resume_importer/universal_schema_parser.py` |
| `format_reader_base.v2.py` | （原 `resume_importer/parsers/` 子包的残留，不可独立运行） |
