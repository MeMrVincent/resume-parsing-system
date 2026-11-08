# Code Index

**English** | [简体中文](CODE_INDEX.cn.md) | [日本語](CODE_INDEX.ja.md)

Generated automatically from the module description of each file under `python/`; an empty description means the script has no module description.

## common: shared modules and tools (2 files)

| File | Description |
|---|---|
| `check_code.py` | check_code.py -- static check of all code under python/ (common, v2, v3): only compiles and analyses, never runs any script. |
| `rc_config.py` | rc_config.py -- unified project configuration reader (common). |

## v3: merge / parse / audit / align (Claude) (28 files)

| File | Description |
|---|---|
| `claude_align_assemble.v3.py` |  |
| `claude_align_auto.v3.py` |  |
| `claude_align_check.v3.py` |  |
| `claude_align_mkbatches.v3.py` |  |
| `claude_align_mktasks.v3.py` |  |
| `claude_merge.v3.py` | claude_merge.v3.py -- cross-checks and merges V2 / V1: identifies the same person by mobile or e-mail, one JSON per person (single- or multi-language). |
| `claude_merge_audit.v3.py` | claude_merge_audit.v3.py -- independent acceptance of the merge v3 output (read-only). |
| `claude_merge_checks.v3.py` | claude_merge_checks.v3.py -- structure and field validation of the merged JSON. |
| `claude_merge_common.v3.py` | claude_merge_common.v3.py -- shared module of merge v3: field specification, contact/date/name normalization, language detection, snapshots and raw_text rebuilding. |
| `claude_merge_manual.v3.py` | Manual decisions made after item-by-item review against the source text (manual_decisions.json), applied to the copies during merge. |
| `claude_merge_normalize.v3.py` | claude_merge_normalize.v3.py -- "field placement and clean-up" after merge and before the field checks. |
| `claude_name_fix.v3.py` | claude_name_fix.v3.py -- name check against the source (runs after all templates are re-parsed; its result is the last layer of the repair copy). |
| `claude_pack_sources.v3.py` | claude_pack_sources.v3.py -- packs all the material the "check-against-source parsers" need (read-only, no original file is changed). |
| `claude_parse_51job.v3.py` | claude_parse_51job.v3.py -- new parser for résumés exported from 51job (also recognizes the similar Liepin layout as a fallback). |
| `claude_parse_cn_platform.v3.py` | claude_parse_cn_platform.v3.py -- new parser for résumés exported from Chinese recruiting platforms (mainly Zhaopin). |
| `claude_parse_en.v3.py` | claude_parse_en.v3.py -- parser for English résumés (CV / Resume). |
| `claude_parse_jp.v3.py` | claude_parse_jp.v3.py -- new parser for Japanese résumés (履歴書 / 職務経歴書 / the Japanese version of recommendation forms such as 紐培 / the 51job Japanese version / Japanese xls tables). |
| `claude_parse_liepin.v3.py` | claude_parse_liepin.v3.py -- parser for résumés exported from Liepin. |
| `claude_parse_zh_free.v3.py` | claude_parse_zh_free.v3.py -- parser for free-format Chinese résumés (fallback). |
| `claude_parse_zh_report.v3.py` | claude_parse_zh_report.v3.py -- parser for Chinese recommendation reports (headhunter / talent-agency "recommendation report / candidate résumé report / talent recommendation form"). |
| `claude_parse_zh_table.v3.py` | claude_parse_zh_table.v3.py -- parser for xls résumé tables exported from recruiting websites. |
| `claude_reparse.v3.py` | claude_reparse.v3.py -- step 2: re-generate the resume from the source text with the new per-template parser, compare with the old JSON against the source, and keep the better one. |
| `claude_review_book.v3.py` | Batch 7: manual review sheet. |
| `claude_source_audit.v3.py` | claude_source_audit.v3.py -- checks every input JSON item by item against its original file, decides whether the parser was at fault, and produces the ledgers. |
| `claude_source_repair.v3.py` | claude_source_repair.v3.py -- step 1 of source repair: restores into the JSON the mobiles / e-mails / names that are in the original file but were missed by the parser. |
| `claude_source_text.v3.py` | claude_source_text.v3.py -- extracts the full text from the original résumé files independently of the original parsers (for checking against the source). |
| `claude_split_pack.v3.py` | claude_split_pack.v3.py -- splits the large claude_pack volumes into 30MB chunks for easier transfer (only adds .partNNN files; the original volumes are not changed). |
| `copy_to_v3.py` | copy_to_v3.py -- copies formal/*.json from a merge run into v3_dir (default complete-v3) and verifies the sha256 of each file. |

## v2: Word / XLS / PDF / HTML → JSON (Codex) (103 files)

| File | Description |
|---|---|
| `audit_chinese_json_against_sources.py` | Compares the formal Chinese JSON with the evidence in the original Word text item by item, by field ownership. |
| `batch_clean_resume_jsons.py` | Full clean-up of complete-transfered-jsons: removes non-résumés / fresh graduates with no experience, multilingual checks, keywords and raw_text. |
| `c_liepin_legacy_adapter.v2.py` | Naming-map entry; the importable version is c_liepin_legacy_adapter_v2.py. |
| `c_liepin_legacy_adapter_v2.py` | Minimal compatibility API that still depends on the V1 Liepin parser. |
| `c_resume_global_progress.v2.py` | Strictly accounts, by source file path, for the global progress of the Word conversion list versus the formal JSON. |
| `c_resume_html_dom_common.v2.py` |  |
| `c_resume_html_to_json_common.v2.py` |  |
| `c_resume_invalid_terminalize.v2.py` | Terminates the 14 manually verified passed Chinese non-résumé / identity-unrecoverable files. |
| `c_resume_json_promote.v2.py` | Conservatively promotes the Chinese staged JSON that passed double verification to the formal directory. |
| `c_resume_nonchinese_promote.v2.py` | Promotes only the multilingual JSON that passed the source-evidence audit, and syncs the conversion list. |
| `c_resume_nonchinese_source_audit.v2.py` | Audits the multilingual staged JSON with double evidence: the source Word and the semantic HTML. |
| `c_resume_nonresume_terminalize.v2.py` | Terminates the non-résumé files in review whose names are clear; conservative rule, ambiguous candidates are not handled. |
| `c_resume_ocr_finalize.v2.py` | Registers the user's OCR JSON, restores the original source path and moves it to the formal Chinese directory. |
| `c_resume_ocr_normalize.v2.py` | Normalizes the user's OCR JSON to the formal template and stages only the résumés that are valid in both structure and content. |
| `c_resume_ocr_stage.v2.py` | Copies the original documents that need the user's OCR to a given directory and marks them as waiting for OCR in the conversion map. |
| `c_resume_source_finalize.v2.py` | Syncs the promoted JSON to the conversion map and deletes the corresponding HTML. |
| `c_resume_terminal_status.v2.py` | Marks a single conversion item, manually verified as impossible to parse further, as terminal. |
| `c_resume_unknown_stage.v2.py` | Copies the source documents that are manually difficult or whose identity is unrecoverable into unknown, and generates a traceable list. |
| `c_web_normalizers.v2.py` | Naming-map entry; the importable version is c_web_normalizers_v2.py. |
| `c_web_normalizers_v2.py` | Normalization API shared by Web/PDF (V2 transition layer). |
| `c_web_text_rules.v2.py` | Naming-map entry; the importable version is c_web_text_rules_v2.py. |
| `c_web_text_rules_v2.py` | Common API for Web text / dates (V2 transition layer). |
| `c_web_zhilian_rules.v2.py` | Naming-map entry; the importable version is c_web_zhilian_rules_v2.py. |
| `c_web_zhilian_rules_v2.py` | Reusable Zhaopin rules API (V2 transition layer). |
| `classify_passed_html_by_language.py` |  |
| `codex_word_html_json_100.py` | Isolated trial flow Word -> HTML DOM -> JSON. |
| `dedupe_pdf_semantic_overrides.v2.py` |  |
| `docs_to_html_and_complete.py` |  |
| `jsons_to_complete.py` | jsons_to_complete.py |
| `pdf_gpt_review_compare.v2.py` |  |
| `pdf_gpt_review_resolve.v2.py` |  |
| `pdf_json_field_strict_audit.v2.py` |  |
| `pdf_json_strict_audit.v2.py` |  |
| `pdf_raw_text_v2.py` |  |
| `pdf_rebuild_audit.v2.py` |  |
| `pdf_rebuild_candidate_audit.v2.py` |  |
| `pdf_rebuild_extract.v2.py` |  |
| `pdf_rebuild_finalize.v2.py` |  |
| `pdf_rebuild_issue_table.v2.py` |  |
| `pdf_rebuild_map.v2.py` |  |
| `pdf_rebuild_merge.v2.py` |  |
| `pdf_rebuild_semantic_repair.v2.py` |  |
| `pdf_source_completeness_repair.v2.py` |  |
| `process_word_html_to_json.py` |  |
| `process_word_to_html.py` |  |
| `process_xls_html_to_json.py` | Standalone entry for rebuilding XLS résumés. |
| `process_xls_to_html.py` |  |
| `reuse_complete_v1_jsons.py` |  |
| `run_chinese_english_html_to_json.py` | Semantic parser HTML -> JSON for a Chinese main version + an independent English version. |
| `run_chinese_html_to_json.py` | Conversion parser HTML -> JSON dedicated to the complete-transfered-htmls\docs\Chinese directory. |
| `run_liepin_html_to_json.py` | Dedicated conversion script Liepin résumé HTML -> JSON. |
| `run_web_html_to_json.py` | Dedicated conversion script HTML -> JSON for the complete-transfered-htmls\web directory. |
| `run_zhilian_html_to_json.py` | Dedicated conversion script Zhaopin résumé HTML -> JSON. |
| `web_batch_report.v2.py` | Rebuild a full Web batch report from the durable conversion map. |
| `web_conversion_map.v2.py` | Build the authoritative Web-source conversion map. |
| `web_full_repair.v2.py` | In-place, schema-strict repair for every Web conversion-map record. |
| `web_full_review.v2.py` | Independent, read-only review of the Web conversion code and outputs. |
| `web_html_json_reconcile.v2.py` | Compare every Web JSON output with its mapped HTML-like source. |
| `web_html_json_repair.v2.py` | Incrementally repair Web JSON files using the issues recorded by reconcile v2. |
| `web_html_to_json.v2.py` | Dedicated conversion script HTML -> JSON for the complete-transfered-htmls\web directory. |
| `web_internship_boundary_recovery.v2.py` | Record and verify recovery from the former `intern`/`International` boundary defect. |
| `web_json_audit.v2.py` | Audit Web HTML-like -> JSON v2 outputs against the conversion map. |
| `web_multilingual_repair.v2.py` | Offline, in-place multilingual repair for Web JSON outputs. |
| `web_output_organize.v2.py` | Review, rename and flatten every Web JSON output into one directory. |
| `word_batch_without_json_report.v2.py` | Lists the source documents in OCR/unknown batches that no result JSON has claimed. |
| `word_chinese_english_identity_retry.v2.py` | Copies the pending Chinese-English HTML in isolation and injects name semantic nodes confirmed by source evidence. |
| `word_chinese_japanese_html_to_json.v2.py` | Dedicated parser for mixed Chinese-Japanese directory HTML -> complete-v1 JSON. |
| `word_chinese_source_repair.v2.py` | Conservatively repairs the staged JSON according to the Chinese source audit evidence. |
| `word_difficult_review_defer.v2.py` | Moves the remaining difficult automatic-review items to the manual queue, keeping the HTML. |
| `word_english_parser_stage.v2.py` | Filters English parse results: excludes image-type Liepin and blocks JSON that has work/education headings but parsed as empty. |
| `word_failed_batch_finalize.v2.py` | Terminates the failed1 source files with no output and cleans up the batch copies and result JSON already judged invalid. |
| `word_full_docs_repair.v2.py` |  |
| `word_html_audit_fix.v2.py` |  |
| `word_invalid_unknown_terminalize.v2.py` | Registers the unknown JSON that failed validation, together with all their source documents, as the terminal state "invalid résumé". |
| `word_japanese_html_to_json.v2.py` | Parser for Japanese semantic HTML -> complete-v1 JSON. |
| `word_japanese_identity_retry.v2.py` | Extracts a clear name from the last segment of the Japanese candidate file name or its direct parent directory, adds a semantic node and retries. |
| `word_japanese_name_retry.v2.py` | Adds traceable name semantic nodes for Japanese items whose name parsing failed, and outputs isolated retry HTML. |
| `word_multilingual_parser_stage.v2.py` | Filters generic parse results by the evidence of body language segments; results lacking a real language segment do not enter the audit. |
| `word_multilingual_v1_match_stage.v2.py` | Stages the multilingual candidates in complete-v1 that can be strictly audited, by parsed identity and contact details. |
| `word_nonchinese_known_name_repair.v2.py` | Repairs the names of multilingual JSON clearly confirmed by the source file and renames the files by name + contact. |
| `word_nonchinese_semantics_repair.v2.py` | Repairs semantic misplacements in multilingual candidates that the source text has confirmed, without fabricating résumé versions that do not exist. |
| `word_nonchinese_v1_repair.v2.py` | Incrementally repairs the complete-v1 multilingual JSON, outputs to the staging area and does not overwrite the formal results. |
| `word_ocr_folder_refresh.v2.py` | Keeps only the current pending_user_ocr documents in the OCR working directory and refreshes the list. |
| `word_schema_extension.v2.py` | Isolated trial flow Word -> HTML DOM -> JSON. |
| `word_semantic_html_audit.v2.py` |  |
| `word_semantic_html_repair.v2.py` |  |
| `word_staged_audit_input.v2.py` | Assembles the JSON in the isolated parse directory into input for the multilingual source audit. |
| `word_strong_candidate_stage.v2.py` | Picks from the Chinese parse staging area the strong résumé candidates that can be conservatively promoted. |
| `word_to_html_to_json.v2.py` |  |
| `word_unique_name_reuse_stage.v2.py` | Stages reuse candidates for the source audit by matching the clear name in the source path with the unique name in the formal library. |
| `word_verified_identity_inject.v2.py` | Injects authoritative name nodes into the semantic HTML that has been manually verified. |
| `xls_bidirectional_review.v2.py` | Choose the better value per field between rebuilt XLS JSON and complete-v1. |
| `xls_conversion_map.v2.py` |  |
| `xls_dom_repair.v2.py` | Apply the current semantic DOM cleanup to already-generated XLS HTML. |
| `xls_field_audit.v2.py` | Strict field-by-field DOM -> JSON audit for the XLS batch. |
| `xls_html_json_audit.v2.py` | Audit the XLS source -> semantic HTML -> JSON chain for the 100-row batch. |
| `xls_incremental_reprocess.v2.py` | Rebuild only XLS sources whose current profile DOM/JSON is demonstrably bad. |
| `xls_json_audit.v2.py` | Strict post-run audit for every rebuilt XLS JSON against its source map. |
| `xls_json_normalize.v2.py` |  |
| `xls_report_rebuild.v2.py` | Reconstruct the full XLS report after targeted subset reruns. |
| `xls_side_by_side_reprocess.v2.py` | Incrementally rebuild XLS files that contain left/right language resumes. |
| `xls_source_html_json_audit.v2.py` | Conservative source -> HTML -> JSON coverage audit for the XLS batch. |
| `xls_to_html_to_json.v2.py` | Standalone entry for rebuilding XLS résumés. |

## v2/resume_importer (V1 legacy library)

19 scripts of V2 still `import resume_importer.*` (classifier, text extraction, structured parsers, etc.), so it is kept together with v2 in `python/v2/resume_importer/`.

