# Word to JSON: Flow Description

**English** | [简体中文](v2-word-to-json.cn.md) | [日本語](v2-word-to-json.ja.md)

> This document describes the V2 (word/xls/pdf/html → JSON) flow. Default directories are in `config.example.json` in the repository root; `<project root>` in the text is `project_root` in config. The duplicate scripts that were merged are listed at the end of [`v2-name-mapping.md`](v2-name-mapping.md).

## 1. Goal and directories

This flow converts the Word résumés in the `docs` scope into HTML that can be parsed semantically, then into the unified JSON, and writes them to the formal directory after a source-file audit.

- Original Word files: `<project root>\需要采集的简历文件夹` (the source résumé folder)
- Conversion working directory: `<project root>\complete-transfered-htmls\docs`
- Overall conversion map: `<project root>\complete-transfered-htmls\docs\word_conversion_map.json`
- Formal JSON: `<project root>\complete-transfered-jsons\docs\<language>`
- Audit and intermediate reports: `<project root>\_resume_qa`
- JSON field description: `CONTEXT.md` (not published with the repository; for the field structure see the example JSON in `examples/`)
- Reference template: `<project root>\complete-v1\Zhang San_13800000003.json`

Formal JSON file names use:

```text
name_mobile.json
name_email.json
name_无联系方式.json        # "无联系方式" = no contact details
name_mobile_2.json        # incremented on a name clash
```

Several Word files of the same candidate can be merged into one JSON. All merged source paths are written to:

```text
source.source_files[].original_path
source.merged_original_paths[]
```

So the "number of formal JSON files" may be smaller than the "number of completed Word source files". Global progress must be counted by the number of source paths.

## 2. Overall flow

```text
Word
  ↓ c_resume_html_dom_common.v2.py
Semantic HTML + word_conversion_map.json
  ↓ classify by language and repair the DOM
Chinese / Japanese / Chinese-Japanese / Chinese-English ... HTML
  ↓ parser for the corresponding language
Staged JSON
  ↓ structure screening + field-by-field audit against the source
Qualified JSON
  ↓ promote / finalize
Formal JSON + updated map + completed HTML deleted
  ↓
Difficult files go to the OCR / unknown / failed manual batches
  ↓ c_resume_ocr_normalize.v2.py
  ↓ c_resume_ocr_finalize.v2.py
Formal JSON or the invalid_resume terminal state
```

Principle: a parser producing JSON does not mean it is done. An item counts as complete only after it passes the structure validation and the source-data audit, is written to the formal directory and its source path is registered.

## 3. Step 1: Word to semantic HTML

### `python/v2/c_resume_html_dom_common.v2.py`

The main conversion program. It:

- reads Word files such as `.doc` and `.docx`;
- extracts paragraphs, tables, headings and document metadata;
- generates HTML;
- writes recognizable fields as semantic DOM, e.g. `data-field`, `label`;
- generates independent child nodes for several fields in the same paragraph;
- records the source Word, HTML, language, conversion status and error information in `word_conversion_map.json`;
- does not keep résumé photos.

Example of the recommended semantic structure (the label values and field values are sample data and kept as in the source):

```html
<p data-field="full_name" label="姓名">张三</p>
<p label="基本信息">
  <i data-field="gender" label="性别">女</i>
  <i data-field="marital_status" label="婚姻">未婚</i>
  <i data-field="birth_date" label="生日">1988年03月16日</i>
</p>
```

Do not rely on a large set of regular expressions to infer fields back from the plain text of the whole page; name, contact details, certificates, education, work experience, etc. should become independent DOM nodes whenever possible.

### HTML repair and check programs

- `python/v2/word_semantic_html_repair.v2.py`: repairs the field nodes, tables and segment structure of HTML that is hard to parse (original file: `repair_semantic_html_dom.py`).
- `python/v2/word_semantic_html_audit.v2.py`: batch-checks whether the HTML has a parseable semantic structure (original file: `audit_semantic_html_batch.py`).
- `python/v2/word_html_audit_fix.v2.py`: early HTML audit and repair program (original file: `audit_and_fix_htmls.py`).
- `python/v2/word_full_docs_repair.v2.py`: early whole-directory deep repair program (original file: `full_docs_deep_repair.py`).
- `python/v2/word_nonchinese_semantics_repair.v2.py`: semantic repair of the remaining non-Chinese HTML (original file: `repair_nonchinese_remaining_semantics.py`).
- `python/v2/word_nonchinese_known_name_repair.v2.py`: uses confirmed names to fill in the identity nodes of non-Chinese HTML (original file: `repair_nonchinese_known_names.py`).
- `python/v2/word_verified_identity_inject.v2.py`: injects verified identity fields into HTML (original file: `inject_verified_html_identity.py`).

These repair programs are only for HTML that is genuinely hard to parse. Files that already have a clear semantic DOM should not be rewritten again.

## 4. Step 2: Parse HTML by language

### Chinese

#### `python/v2/run_chinese_html_to_json.py`

The main Chinese parser and the one used most in this run. It handles platform recognition, field normalization, résumé segmentation, date handling, quality validation and batch reports.

Example:

```powershell
python python\v2\run_chinese_html_to_json.py `
  --html-dir <Chinese HTML directory> `
  --json-dir <staged JSON directory> `
  --map <project root>\complete-transfered-htmls\docs\word_conversion_map.json `
  --report <project root>\_resume_qa\chinese_batch.json `
  --progress-interval 10 `
  --file-timeout 30
```

### Japanese

- `python/v2/word_japanese_html_to_json.v2.py`: parsing of Japanese 履歴書 and 職務経歴書 and Japanese semantic normalization.
- `python/v2/word_japanese_identity_retry.v2.py`: only when a trustworthy person name exists in the file name or directory, generates retry HTML with the identity filled in.
- `python/v2/word_japanese_name_retry.v2.py`: prepares Japanese name-retry items from audit problems.

Company names, job titles, recruiting content and invoice (請求書) names must not be taken as the candidate's name.

### Chinese-Japanese

- `python/v2/word_chinese_japanese_html_to_json.v2.py`: handles Chinese-Japanese bilingual résumés and keeps several `resumes` language versions.

### Chinese-English and other multilingual

- `python/v2/run_chinese_english_html_to_json.py`: handles Chinese-English bilingual résumés.
- `python/v2/word_chinese_english_identity_retry.v2.py`: prepares Chinese-English identity-retry items.
- `python/v2/word_multilingual_parser_stage.v2.py`: stages the automatically detected multilingual parse results.
- `python/v2/word_english_parser_stage.v2.py`: stages the results of the English parser.

Multilingual JSON must keep the corresponding language versions; an old JSON that lacks a language version must not be reused directly just because the names are the same.

## 5. JSON structure screening and source-file audit

### General structure validation

- `python/v2/reuse_complete_v1_jsons.py`
  - provides the unified `validate_json()`;
  - validates name, file name, contact details, dates, top-level snapshots, language versions, list fields and `raw_text`;
  - is the base validation module shared by several parsers and back-fill programs.
- `python/v2/word_strong_candidate_stage.v2.py`
  - screens the staged JSON for candidates with a valid name and a sufficient structure;
  - rejects job titles, company names, unknown names and empty-shell JSON.
- `python/v2/word_staged_audit_input.v2.py`
  - builds the audit input by pairing the staged JSON with the source Word/HTML in `word_conversion_map.json`.

### Chinese field-by-field audit

- `python/v2/audit_chinese_json_against_sources.py`
  - compares the JSON fields (name, contact details, expectations, work, education, certificates, training, projects, etc.) with the source Word/HTML;
  - non-business data, such as club posts, associations, social events, mentors, etc., may be dropped and need not be written to the formal JSON.
- `python/v2/word_chinese_source_repair.v2.py`
  - removes wrongly filled fields or repairs determinable problems according to the audit report;
  - the audit must be run again after the repair.
- `python/v2/c_resume_json_promote.v2.py`
  - writes only Chinese JSON without audit problems to the formal directory.
- `python/v2/c_resume_source_finalize.v2.py`
  - marks the successfully promoted source files as done;
  - updates `word_conversion_map.json`;
  - deletes the corresponding completed HTML.

### Non-Chinese field-by-field audit

- `python/v2/c_resume_nonchinese_source_audit.v2.py`
  - checks whether name semantics, language versions, companies, schools and other fields can be found in the source file as evidence.
- `python/v2/c_resume_nonchinese_promote.v2.py`
  - promotes only non-Chinese JSON whose audit status is `passed`, and registers the source paths.

### Reuse of historical JSON

- `python/v2/word_unique_name_reuse_stage.v2.py`
  - from the unique name in the source file name, looks in the formal directory for historical JSON that may be the same person;
  - the result is only a candidate; a source-file audit is still required.
- `python/v2/word_multilingual_v1_match_stage.v2.py`
  - stages the multilingual JSON in `complete-v1` that may match.
- `python/v2/word_nonchinese_v1_repair.v2.py`
  - repairs the non-Chinese `complete-v1` candidates that can be confirmed.

Copying JSON on the basis of the same name alone is forbidden. Contact details, work experience, education, certificates and language versions must all be consistent.

## 6. Non-résumés and terminal states

- `python/v2/c_resume_nonresume_terminalize.v2.py`
  - recognizes job descriptions, recruiting notices, company materials, blank templates, interview questions, test questions, contracts, etc. whose names are clear;
  - writes the `non_resume` terminal state.
- `python/v2/c_resume_invalid_terminalize.v2.py`
  - cleans up the Chinese items in the old `passed` queue that cannot form a valid résumé.
- `python/v2/c_resume_terminal_status.v2.py`
  - writes a given terminal state for a single, manually confirmed source file.
- `python/v2/word_difficult_review_defer.v2.py`
  - turns the remaining items that failed automatic parsing or the strict audit into `deferred_manual_review`, and generates a CSV/JSON manual list.

Main statuses:

| Status | Meaning |
| --- | --- |
| `passed` | Formal JSON generated, source path registered |
| `needs_review` | Item in the automatic queue waiting for review |
| `deferred_manual_review` | Skipped by the automatic flow, waiting for manual handling |
| `pending_user_ocr` | Copied to the OCR directory, waiting for manual OCR / parsing |
| `non_resume` | Confirmed as a non-résumé or an invalid résumé |
| `identity_unrecoverable` | The candidate's identity cannot be recovered; may later fall back to invalid résumé |
| `superseded` | Replaced by a newer version |

An invalid résumé uses:

```text
status = non_resume
terminal_classification = invalid_resume
json_status = invalid_resume
```

## 7. Manual back-fill for OCR, unknown and failed

### Copying the source Word files that need manual handling

- `python/v2/c_resume_ocr_stage.v2.py`
  - copies the source Word files of the given types to `docs\ocr`;
  - the copy name contains the source-path hash to avoid overwriting same-named files;
  - updates the status to `pending_user_ocr`.
- `python/v2/word_ocr_folder_refresh.v2.py`
  - restores the copies missing from the OCR directory according to the map;
  - rewrites the OCR list.
- `python/v2/c_resume_unknown_stage.v2.py`
  - copies the source Word files with the given statuses to `unknown` or `failed`;
  - generates `unknown_manifest.json` or `failed_manifest.json`.

Example:

```powershell
python python\v2\c_resume_unknown_stage.v2.py `
  --progress <latest global progress JSON> `
  --output-dir <project root>\complete-transfered-htmls\docs\failed `
  --manifest <project root>\complete-transfered-htmls\docs\failed\failed_manifest.json `
  --statuses deferred_manual_review pending_user_ocr
```

### Validating manually produced JSON

- `python/v2/c_resume_ocr_normalize.v2.py`
  - restores the original source paths from the OCR list or the `unknown/failed` manifest;
  - corrects old fields, e.g. `resume_languge` → `resume_language`;
  - normalizes the top-level `expected_info` into an object;
  - fills in list fields and work-achievement fields;
  - renames by "name + mobile/e-mail/no contact";
  - rejects results such as "name to be confirmed", masked names, no body text, no résumé structure, non-résumés;
  - writes only valid JSON to the staging directory.

### Formally registering manual JSON

- `python/v2/c_resume_ocr_finalize.v2.py`
  - writes the staged JSON to the formal Chinese directory;
  - supports one JSON for several original Word files;
  - updates all source paths to `passed_user_ocr`;
  - deletes the corresponding HTML.

Example:

```powershell
python python\v2\c_resume_ocr_finalize.v2.py `
  --json-dir <validated staging directory> `
  --map <project root>\complete-transfered-htmls\docs\word_conversion_map.json `
  --document-manifest <ocr/unknown/failed list> `
  --formal-dir <project root>\complete-transfered-jsons\docs\中文 `
  --report <project root>\_resume_qa\user_json_finalize_apply.json `
  --apply
```

### Reconciling manual batches and cleaning up invalid items

- `python/v2/word_batch_without_json_report.v2.py`
  - compares the batch manifest with the `source_files` of the output JSON;
  - lists the source Word files not claimed by any JSON.
- `python/v2/word_invalid_unknown_terminalize.v2.py`
  - registers JSON that failed strict validation, and the corresponding source files, as `invalid_resume`;
  - deletes the corresponding HTML.
- `python/v2/word_failed_batch_finalize.v2.py`
  - handles the items of the failed batch that have no JSON output;
  - marks invalid source files;
  - deletes invalid working copies, intermediate JSON and leftover HTML.

Note: only the working copies and intermediate results in `docs\ocr`, `docs\unknown` and `docs\failed` are cleaned up. The original Word files in the source résumé folder (`需要采集的简历文件夹`) must never be deleted.

## 8. Global statistics

### `python/v2/c_resume_global_progress.v2.py`

Taking the original source paths in `word_conversion_map.json` as the baseline, it counts:

- the total number of source files;
- the number of formal JSON files;
- the number of source paths covered by the formal JSON;
- the number of unfinished source paths;
- the numbers per status and per language directory;
- the invalid JSON in the formal directory.

Example:

```powershell
python python\v2\c_resume_global_progress.v2.py `
  --map <project root>\complete-transfered-htmls\docs\word_conversion_map.json `
  --formal-root <project root>\complete-transfered-jsons\docs `
  --output <project root>\_resume_qa\global_docs_progress.json
```

The statistics must satisfy the relation:

```text
total source files = source files covered by generated formal JSON
                   + non-résumés / invalid résumés
                   + manual / OCR waiting items
                   + identity_unrecoverable
                   + superseded
```

Final state of this run:

```text
Total source files: 14,019
Source files covered by formal JSON: 13,573
Invalid / non-résumés: 445
Replaced by a newer file: 1
Automatic review / OCR / manual difficult queue: 0
```

That is:

```text
13,573 + 445 + 1 = 14,019
```

The number of formal JSON files is 13,539, fewer than the 13,573 completed source paths, because the duplicate or multilingual Word files of some candidates were merged into the same JSON.

## 9. Recommended re-run order

1. Back up `word_conversion_map.json`.
2. Run `c_resume_html_dom_common.v2.py` to generate HTML and the map.
3. Check the HTML by language directory and, if necessary, run the semantic DOM repair programs.
4. Use the parser for the corresponding language and write to a separate staging directory; never write directly to the formal directory.
5. Run the structure screening program.
6. Run the Chinese or non-Chinese source-file audit.
7. Repair the determinable problems and audit again.
8. Write to the formal directory with the corresponding `promote` program.
9. Use `c_resume_source_finalize.v2.py` to update the map and delete the completed HTML.
10. Copy the remaining difficult items to OCR/unknown/failed for manual handling.
11. Run `c_resume_ocr_normalize.v2.py` first on the manual JSON.
12. Run `c_resume_ocr_finalize.v2.py` on valid items; write invalid items to the `invalid_resume` terminal state.
13. Finally run `c_resume_global_progress.v2.py` to make sure every source path has a clear destination.

## 10. Important notes

- Do not treat a parser's "successful output" directly as a valid résumé.
- Do not take a company name, job title, directory name, recruiting content or "name to be confirmed" as a name.
- Do not reuse historical JSON on the basis of the name alone; the contact details and main career fields must be audited.
- Multilingual résumés should keep every language version in `structured_data.resumes`.
- `expected_info`, `current_info` and `education_info` are top-level snapshots and should be synchronized with the first, main-language résumé.
- Work, education, projects, training, certificates, etc. must be structured lists.
- `raw_text` must exist and should cover the main structured values in the JSON.
- Image-based résumés go to OCR; photos are not kept in the Word→HTML stage.
- Completed items are processed incrementally; formal JSON is not overwritten repeatedly.
- Before deleting any HTML or working copy, confirm that the formal JSON has been written and the source path registered.
- The original Word files are always kept; only copies and intermediate files in the conversion directories may be deleted.

## 11. v2 file naming and V1 compatibility

All original scripts are kept. For easier cross-checking, v2 counterpart files with a unified category prefix have been added:

| Original script | v2 counterpart | Category |
|---|---|---|
| `process_word_to_html.py` | `python/v2/c_resume_html_dom_common.v2.py` | Word |
| `process_word_html_to_json.py` | `python/v2/word_to_html_to_json.v2.py` | Word |
| `run_chinese_html_to_json.py` | `python/v2/run_chinese_html_to_json.py` | Word |
| `run_chinese_english_html_to_json.py` | `python/v2/run_chinese_english_html_to_json.py` | Word |
| `run_chinese_japanese_html_to_json.py` | `python/v2/word_chinese_japanese_html_to_json.v2.py` | Word |
| `run_japanese_html_to_json.py` | `python/v2/word_japanese_html_to_json.v2.py` | Word |
| `word_japanese_identity_retry.v2.py` | `python/v2/word_japanese_identity_retry.v2.py` | Word |
| `prepare_japanese_name_retry.py` | `python/v2/word_japanese_name_retry.v2.py` | Word |
| `prepare_chinese_english_identity_retry.py` | `python/v2/word_chinese_english_identity_retry.v2.py` | Word |
| `stage_detected_multilingual_parser_results.py` | `python/v2/word_multilingual_parser_stage.v2.py` | Word |
| `stage_complete_english_parser_results.py` | `python/v2/word_english_parser_stage.v2.py` | Word |
| `stage_strong_chinese_resume_candidates.py` | `python/v2/word_strong_candidate_stage.v2.py` | Word |
| `build_staged_audit_input.py` | `python/v2/word_staged_audit_input.v2.py` | Word |
| `repair_chinese_from_source_audit.py` | `python/v2/word_chinese_source_repair.v2.py` | Word |
| `stage_unique_name_formal_reuse.py` | `python/v2/word_unique_name_reuse_stage.v2.py` | Word |
| `stage_multilingual_complete_v1_matches.py` | `python/v2/word_multilingual_v1_match_stage.v2.py` | Word |
| `repair_nonchinese_complete_v1.py` | `python/v2/word_nonchinese_v1_repair.v2.py` | Word |
| `defer_difficult_review_items.py` | `python/v2/word_difficult_review_defer.v2.py` | Word |
| `refresh_pending_ocr_folder.py` | `python/v2/word_ocr_folder_refresh.v2.py` | Word |
| `report_batch_documents_without_json.py` | `python/v2/word_batch_without_json_report.v2.py` | Word |
| `terminalize_invalid_unknown_jsons.py` | `python/v2/word_invalid_unknown_terminalize.v2.py` | Word |
| `finalize_failed1_batch.py` | `python/v2/word_failed_batch_finalize.v2.py` | Word |
| `process_word_to_html.py` | `python/v2/c_resume_html_dom_common.v2.py` | Common |
| `process_word_html_to_json.py` | `python/v2/c_resume_html_to_json_common.v2.py` | Common |
| `reuse_complete_v1_jsons.py` | `python/v2/reuse_complete_v1_jsons.py` | Common |
| `audit_chinese_json_against_sources.py` | `python/v2/audit_chinese_json_against_sources.py` | Common |

The common category uniformly uses the `c_` prefix. For the complete mapping see [`v2-name-mapping.md`](v2-name-mapping.md).
