# Word / XLS to JSON v2: File Naming Map

**English** | [简体中文](v2-name-mapping.cn.md) | [日本語](v2-name-mapping.ja.md)

> This document describes the V2 (word/xls/pdf/html → JSON) flow. Default directories are in `config.example.json` in the repository root; `<project root>` in the text is `project_root` in config. The duplicate scripts that were merged are listed at the end of `v2-name-mapping.md`.

All original scripts in this directory are kept. The `*.v2.py` files added in this batch are independent copies for easier cross-checking; they keep the original script logic and import relationships, and do not mean the production entry points have been switched.

## Word-specific code

| Original file | v2 file | Responsibility |
|---|---|---|
| `process_word_to_html.py` | `c_resume_html_dom_common.v2.py` | Main Word → semantic HTML conversion |
| `process_word_html_to_json.py` | `word_to_html_to_json.v2.py` | Main semantic HTML → JSON parsing |
| `codex_word_html_json_100.py` | `word_schema_extension.v2.py` | Word schema extension |
| `run_chinese_html_to_json.py` | `run_chinese_html_to_json.py` | Chinese HTML parsing entry |
| `run_chinese_english_html_to_json.py` | `run_chinese_english_html_to_json.py` | Chinese-English HTML parsing entry |
| `run_chinese_japanese_html_to_json.py` | `word_chinese_japanese_html_to_json.v2.py` | Chinese-Japanese HTML parsing entry |
| `run_japanese_html_to_json.py` | `word_japanese_html_to_json.v2.py` | Japanese HTML parsing entry |
| `repair_semantic_html_dom.py` | `word_semantic_html_repair.v2.py` | Word semantic DOM repair |
| `audit_semantic_html_batch.py` | `word_semantic_html_audit.v2.py` | Batch audit of Word semantic HTML |
| `audit_and_fix_htmls.py` | `word_html_audit_fix.v2.py` | Early audit and repair of Word HTML |
| `full_docs_deep_repair.py` | `word_full_docs_repair.v2.py` | Deep repair of the whole Word directory |
| `repair_nonchinese_remaining_semantics.py` | `word_nonchinese_semantics_repair.v2.py` | Semantic repair for non-Chinese résumés |
| `repair_nonchinese_known_names.py` | `word_nonchinese_known_name_repair.v2.py` | Repair of confirmed names in non-Chinese résumés |
| `inject_verified_html_identity.py` | `word_verified_identity_inject.v2.py` | Injection of verified identity fields |
| `word_japanese_identity_retry.v2.py` | `word_japanese_identity_retry.v2.py` | Preparation for Japanese identity retry |
| `prepare_japanese_name_retry.py` | `word_japanese_name_retry.v2.py` | Preparation for Japanese name retry |
| `prepare_chinese_english_identity_retry.py` | `word_chinese_english_identity_retry.v2.py` | Preparation for Chinese-English identity retry |
| `stage_detected_multilingual_parser_results.py` | `word_multilingual_parser_stage.v2.py` | Staging of multilingual results |
| `stage_complete_english_parser_results.py` | `word_english_parser_stage.v2.py` | Staging of English results |
| `stage_strong_chinese_resume_candidates.py` | `word_strong_candidate_stage.v2.py` | Screening of Chinese candidates |
| `build_staged_audit_input.py` | `word_staged_audit_input.v2.py` | Building of audit input |
| `repair_chinese_from_source_audit.py` | `word_chinese_source_repair.v2.py` | Repair from the Chinese source audit |
| `stage_unique_name_formal_reuse.py` | `word_unique_name_reuse_stage.v2.py` | Staging of historical reuse by unique name |
| `stage_multilingual_complete_v1_matches.py` | `word_multilingual_v1_match_stage.v2.py` | Staging of multilingual historical matches |
| `repair_nonchinese_complete_v1.py` | `word_nonchinese_v1_repair.v2.py` | Repair of non-Chinese historical candidates |
| `defer_difficult_review_items.py` | `word_difficult_review_defer.v2.py` | Deferral of difficult items to manual handling |
| `refresh_pending_ocr_folder.py` | `word_ocr_folder_refresh.v2.py` | OCR directory refresh |
| `report_batch_documents_without_json.py` | `word_batch_without_json_report.v2.py` | Reconciliation of batch documents missing JSON |
| `terminalize_invalid_unknown_jsons.py` | `word_invalid_unknown_terminalize.v2.py` | Terminal state for invalid unknown items |
| `finalize_failed1_batch.py` | `word_failed_batch_finalize.v2.py` | Wrap-up of the failed batch |

## XLS-specific code

| Original file | v2 file | Responsibility |
|---|---|---|
| `build_xls_conversion_map.py` | `xls_conversion_map.v2.py` | Building the XLS source-file map |
| `process_xls_to_html.py` | `process_xls_to_html.py` | Main XLS → semantic HTML conversion |
| `process_xls_html_to_json.py` | `xls_to_html_to_json.v2.py` | Main XLS semantic HTML → JSON parsing |
| `audit_xls_all_fields.py` | `xls_field_audit.v2.py` | Field-by-field DOM audit of XLS |
| `audit_xls_html_json.py` | `xls_html_json_audit.v2.py` | XLS HTML/JSON audit |
| `audit_xls_json_outputs.py` | `xls_json_audit.v2.py` | Audit of XLS JSON output |
| `audit_xls_source_html_json.py` | `xls_source_html_json_audit.v2.py` | XLS source file / HTML / JSON audit |
| `bidirectional_review_xls_jsons.py` | `xls_bidirectional_review.v2.py` | Two-way review of XLS against complete-v1 |
| `rebuild_xls_report.py` | `xls_report_rebuild.v2.py` | Rebuilding the overall XLS report |
| `reprocess_side_by_side_xls.py` | `xls_side_by_side_reprocess.v2.py` | Dedicated rerun for XLS with left/right bilingual layout |
| `reprocess_xls_incremental.py` | `xls_incremental_reprocess.v2.py` | Incremental rerun of abnormal XLS items |
| `normalize_existing_xls_jsons.py` | `xls_json_normalize.v2.py` | Normalization of historical XLS JSON |
| `repair_existing_xls_dom_labels.py` | `xls_dom_repair.v2.py` | Repair of XLS DOM labels |

## Code shared by Word/XLS

| Original file | v2 file | Responsibility |
|---|---|---|
| `process_word_to_html.py` | `c_resume_html_dom_common.v2.py` | Snapshot of the common semantic HTML/DOM base capabilities |
| `process_word_html_to_json.py` | `c_resume_html_to_json_common.v2.py` | Snapshot of the common HTML → complete-v1 base parsing |
| `reuse_complete_v1_jsons.py` | `reuse_complete_v1_jsons.py` | complete-v1 structure validation and reuse tool |
| `classify_passed_html_by_language.py` | `classify_passed_html_by_language.py` | Language detection and directory classification |
| `audit_chinese_json_against_sources.py` | `audit_chinese_json_against_sources.py` | Field-by-field evidence audit against source files |
| `audit_nonchinese_json_against_sources.py` | `c_resume_nonchinese_source_audit.v2.py` | Audit of non-Chinese source files |
| `promote_audited_chinese_json.py` | `c_resume_json_promote.v2.py` | Promotion of audited JSON |
| `promote_audited_nonchinese_json.py` | `c_resume_nonchinese_promote.v2.py` | Promotion of non-Chinese JSON |
| `finalize_promoted_sources.py` | `c_resume_source_finalize.v2.py` | Source-path registration and HTML clean-up |
| `build_global_docs_progress.py` | `c_resume_global_progress.v2.py` | Global progress at source-path level |
| `stage_documents_for_user_ocr.py` | `c_resume_ocr_stage.v2.py` | Staging of files for manual OCR |
| `normalize_and_validate_user_ocr_jsons.py` | `c_resume_ocr_normalize.v2.py` | Normalization and validation of manual OCR JSON |
| `finalize_user_ocr_jsons.py` | `c_resume_ocr_finalize.v2.py` | Formal registration of manual OCR JSON |
| `stage_unknown_documents.py` | `c_resume_unknown_stage.v2.py` | Staging of unknown/failed files |
| `mark_conversion_terminal.py` | `c_resume_terminal_status.v2.py` | Registration of the terminal state of source files |
| `terminalize_obvious_nonresume_review.py` | `c_resume_nonresume_terminalize.v2.py` | Terminal handling of clear non-résumés |
| `terminalize_unusable_passed_chinese.py` | `c_resume_invalid_terminalize.v2.py` | Terminal handling of invalid résumés |

## Snapshots of common classes

These files are named after their classes; the implementations at the original location under `python/resume_importer/` are still kept.

| Original file | v2 file | Main classes |
|---|---|---|
| `resume_importer/classifier.py` | `document_classifier.v2.py` | `Classification`、`DocumentClassifier` |
| `resume_importer/codex_gemini_html_schema_parser.py` | `codex_gemini_html_schema_parser.v2.py` | `CodexGeminiHtmlSchemaParser` |
| `resume_importer/structured_parser.py` | `structured_resume_parser.v2.py` | `StructuredResumeParser` |
| `resume_importer/extractors.py` | `c_resume_text_extractor.v2.py` | `ExtractionError`、`ResumeTextExtractor` |
| `resume_importer/universal_schema_parser.py` | `universal_schema_parser.v2.py` | `UniversalSchemaParser` |
| `resume_importer/preread/reader_base.py` | `format_reader_base.v2.py` | `BaseFormatReader` |

## PDF-specific code

| Original file | v2 file | Responsibility |
|---|---|---|
| `process_pdf_to_html.py` | `pdf_to_html.v2.py` | PDF → semantic HTML |
| `process_pdf_html_to_json.py` | `pdf_to_html_to_json.v2.py` | Semantic HTML → JSON |
| `validate_and_repair_pdf_json.py` | `pdf_json_validate.v2.py` | Basic JSON validation and repair |
| `strict_validate_and_repair_pdf_json.py` | `pdf_json_strict_validate.v2.py` | Strict semantic validation and repair |
| `audit_pdf_json_against_sources.py` | `pdf_source_audit.v2.py` | PDF/HTML/JSON source-evidence audit |
| `parallel_pdf_to_html.py` | `pdf_parallel_to_html.v2.py` | Parallel PDF → HTML conversion |
| `convert_pdf_report.py` | `pdf_conversion_map.v2.py` | Building the PDF source list and map |
| `merge_pdf_conversion_reports.py` | `pdf_conversion_report_merge.v2.py` | Merging PDF conversion reports |
| `incremental_source_repair.py` | `pdf_source_repair.v2.py` | Incremental repair from source evidence |
| New | `pdf_incremental_guard.v2.py` | Hash snapshots, issue ledger and safe promotion of qualified candidates |
| New | `pdf_metadata_leak_repair.v2.py` | Dedicated incremental repair of fields polluted by `section-profile/evidence` and serialization separators |
| `pdfs_to_complete.py` | `pdf_legacy_to_complete.v2.py` | Legacy direct PDF → complete JSON conversion |
| `resume_importer/preread/pdf_reader.py` | `pdf_format_reader.v2.py` | Implementation of the `PdfFormatReader` class |
| `jsons_to_complete.py` | `jsons_to_complete.py` | Legacy complete JSON schema compatibility tool |

## Conventions going forward

1. Original files are neither deleted nor overwritten; they remain the historical baseline.
2. The main PDF→HTML→JSON flow and its validation, audit, repair and batch code all use `pdf_*.v2.py`; no new `pdf_*_v2.py` or unversioned PDF implementations are added.
3. The unversioned files in the left column of these tables are only a read-only V1 historical baseline; they are not current entry points and must not be referenced by the V2 main flow.
4. In later logic refactoring, `word_to_html_to_json.v2.py`, `xls_to_html_to_json.v2.py`, `pdf_to_html.v2.py`, `pdf_to_html_to_json.v2.py` and the common v2 modules are the new baseline.
5. When a `.v2.py` file needs to be reused, load it at run time by file path; do not copy an identical `_v2.py` implementation just to allow a plain `import`.

## Public V2 APIs split out

| V2 API file | Current source | Reusable interface |
|---|---|---|
| `c_web_zhilian_rules.v2.py` / `c_web_zhilian_rules_v2.py` | `run_zhilian_html_to_json.py` | Parsing of job intention, work, education, certificates, languages and skills |
| `c_web_normalizers.v2.py` / `c_web_normalizers_v2.py` | `run_web_html_to_json.py` | Normalization of education, work, certificates, languages, training, projects and communication |
| `c_web_text_rules.v2.py` / `c_web_text_rules_v2.py` | `run_chinese_english_html_to_json.py` | Plain text, DOM summary and date parsing |
| `c_liepin_legacy_adapter.v2.py` / `c_liepin_legacy_adapter_v2.py` | `run_liepin_html_to_json.py` | Liepin HTML reading, plain text and record building |

Of these, the dotted files are entry points for manual cross-checking, and the underscored `_v2.py` files are the entry points that Python can import. These APIs are currently still explicit transitional forwards to V1 functions; the interface stays unchanged when the function bodies are migrated later.


## Duplicate scripts removed when the repository was tidied for release

The following scripts have exactly the same content as the script kept on the right and were deleted when the repository was tidied (the commands in the documents have been changed to the kept names accordingly):

| Deleted | Kept |
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

The following 6 files are same-content copies of modules inside the `resume_importer/` package (or leftovers of a sub-package that no longer exists); no script references them and they were deleted during the tidy-up; the correspondence:

| Deleted | Equivalent to |
|---|---|
| `c_resume_text_extractor.v2.py` | `resume_importer/extractors.py` |
| `codex_gemini_html_schema_parser.v2.py` | `resume_importer/codex_gemini_html_schema_parser.py` |
| `document_classifier.v2.py` | `resume_importer/classifier.py` |
| `structured_resume_parser.v2.py` | `resume_importer/structured_parser.py` |
| `universal_schema_parser.v2.py` | `resume_importer/universal_schema_parser.py` |
| `format_reader_base.v2.py` | (a leftover of the former `resume_importer/parsers/` sub-package; cannot run on its own) |
