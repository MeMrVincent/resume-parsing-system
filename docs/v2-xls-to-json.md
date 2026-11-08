# XLS to JSON: Flow Description

**English** | [简体中文](v2-xls-to-json.cn.md) | [日本語](v2-xls-to-json.ja.md)

> This document describes the V2 (word/xls/pdf/html → JSON) flow. Default directories are in `config.example.json` in the repository root; `<project root>` in the text is `project_root` in config. The duplicate scripts that were merged are listed at the end of [`v2-name-mapping.md`](v2-name-mapping.md).

## 1. Goal and scope

This flow converts Excel résumé files (`.xls`, `.xlsx`) into HTML with a semantic DOM, and then parses the HTML into the unified résumé JSON. The table layouts of XLS files vary greatly, so the HTML is not an intermediate display file but the factual source for parsing: fields must first be bound correctly in the HTML DOM, and the JSON only reads and normalizes those nodes.

The flow focuses on:

- Chinese, Japanese and English résumés, and Chinese-Japanese / Chinese-English bilingual résumés;
- Excel tables in horizontal, vertical and mixed orientation;
- two language résumés placed side by side (left and right);
- name, contact details, basic information, job intention, work, education, certificates, languages, skills, projects and self-evaluation;
- traceable records of the source file's landing time, source path, HTML path and JSON path;
- field-by-field validation between the HTML, the JSON and the source XLS.

The original XLS files are always kept. The conversion copies and intermediate results in `passed` and `review` may be cleaned up, but the XLS files in the original collection directory must never be deleted.

## 2. Directories and files

### 2.1 Input and map

| Item | Path |
| --- | --- |
| Excel inventory report | `<project root>\32718文件报告.xlsx` |
| Original XLS/XLSX | `<project root>\需要采集的简历文件夹` and its subdirectories |
| XLS conversion map | `<project root>\complete-transfered-htmls\xls\xls_conversion_map.json` |
| HTML conversion summary | `<project root>\complete-transfered-htmls\xls\xls_conversion_summary.json` |

`xls_conversion_map.json` is the source-file-level master index. Each record contains at least:

```json
{
  "source_path": "absolute path of the original XLS",
  "filename": "file name in the inventory report",
  "download_date": "landing time of the source file",
  "html_path": "path of the generated HTML",
  "phone": "mobile confirmed from the source table",
  "email": "e-mail confirmed from the source table",
  "status": "passed / needs_review / not_resume / failed",
  "language_folder": "中文 / 日文 / 中日文 / 中英文 ...",
  "languages": ["zh", "en"],
  "resume_count": 1,
  "validation": {}
}
```

(`language_folder` values are the actual directory names: `中文` Chinese, `日文` Japanese, `中日文` Chinese-Japanese, `中英文` Chinese-English.)

### 2.2 HTML working directories

```text
<project root>\complete-transfered-htmls\xls\passed
<project root>\complete-transfered-htmls\xls\review
```

An XLS with at least one of mobile or e-mail normally goes to `passed`; files with no confirmable contact details, that cannot form a valid résumé, or whose conversion failed go to `review`, `not_resume` or `failed`.

### 2.3 Formal JSON and reports

```text
<project root>\complete-transfered-jsons\xls\中文
```

The main report and the audit reports of the current Chinese XLS JSON are in this directory:

```text
_xls_html_to_json_v3_report.json
_xls_html_to_json_v3_post_audit.json
_xls_side_by_side_reprocess_report.json
_xls_incremental_reprocess_report.json
_xls_html_to_json_v3_bidirectional_review.json
```

JSON file names use:

```text
name_mobile.json
name_email.json
name_无联系方式.json       # "无联系方式" = no contact details
```

On a name clash the source file hash or a serial number is appended. Mobile numbers are stripped of hyphens, spaces and similar formatting in file names and JSON; clear international numbers keep the country-code separator, e.g. `+86-13800000004`.

## 3. Overall chain

```text
32718文件报告.xlsx / original XLS
        │
        ├─ xls_conversion_map.v2.py
        │       ↓
        │   xls_conversion_map.json
        │
        ├─ process_xls_to_html.py
        │       ↓ reads the Excel grid, classifies the language, extracts contact details, generates semantic HTML
        │   passed/*.html or review/*.html
        │
        ├─ xls_to_html_to_json.v2.py
        │       ↓ rebuilds the DOM, binds fields, parses by language, normalizes, validates
        │   complete-transfered-jsons/xls/中文/*.json
        │
        ├─ xls_json_audit.v2.py
        │       ↓ audit of JSON / HTML / map / contact details / language versions
        │
        ├─ xls_bidirectional_review.v2.py (when needed)
        │       ↓ mutual review against the old complete-v1 JSON by source path
        │
        └─ xls_report_rebuild.v2.py
                ↓
            final overall report
```

Important principle: get the HTML right first, parse the JSON afterwards. Do not modify only the JSON extraction rules to cover up problems where the HTML DOM was not segmented or fields were bound wrongly.

## 4. Step 1: Build the XLS source-file list

### `python/v2/xls_conversion_map.v2.py`

This program reads the `Excel表格 (.xls, .xlsx)` worksheet (Excel tables) of `32718文件报告.xlsx` and builds the source-file-level map. It does not parse the résumé body and does not generate JSON.

Run:

```powershell
cd <project root>
python python\xls_conversion_map.v2.py
```

Run it only when the inventory report has changed and the source-file index has to be rebuilt. Day-to-day incremental processing should reuse the existing `xls_conversion_map.json`, to avoid losing the completed statuses, the source-file landing times and the HTML paths.

## 5. Step 2: XLS to semantic HTML

### `python/v2/process_xls_to_html.py`

This is the converter from the Excel grid to HTML. It reuses the generator, HTML schema and version information of the latest Word→HTML, so that XLS and Word do not end up with two inconsistent sets of DOM rules.

Main work:

1. read `.xls` with `xlrd` and `.xlsx` with `openpyxl`;
2. keep the cell row/column relations, merged cells, horizontal/vertical layout and the original text;
3. recognize name, mobile and e-mail, and use "at least one of mobile or e-mail" as the basic threshold for a valid résumé;
4. recognize Chinese, Japanese, English and multilingual evidence;
5. choose a language directory such as `中文`, `日文`, `中日文` or `中英文` according to the table content;
6. generate DOM nodes such as `resume-record`, `section`, `table`, `tr`, `td`;
7. write the source file path, HTML path, source landing time, language classification, conversion version and basic validation;
8. put the current-version HTML in `passed` or `review` and update `xls_conversion_map.json`.

Trial run of the first 100:

```powershell
python python\process_xls_to_html.py --limit 100
```

Full generation:

```powershell
python python\process_xls_to_html.py --limit 0
```

Force rebuilding existing HTML:

```powershell
python python\process_xls_to_html.py --limit 100 --force
```

By default HTML that is already of the current generator version is not overwritten; use `--force` only when the DOM really needs rebuilding.

## 6. HTML semantic DOM rules

### 6.1 Basic structure

```html
<article class="resume-record"
         data-role="resume"
         data-language-code="zh"
         data-language-variants="zh,en"
         data-language-count="2">
  <section data-section-type="base_info"
           data-language-code="zh">
    <span data-field="full_name" label="姓名">张三</span>
  </section>
  <section data-collection="work_experiences"
           data-section-type="work_experiences"
           data-language-code="zh">
    <tr data-record-type="work_experience">
      <span data-field="company_name">公司名称</span>
      <span data-field="position_start">2016年09月</span>
    </tr>
  </section>
</article>
```

The parser relies mainly on the following attributes:

| Attribute | Purpose |
| --- | --- |
| `data-role="resume"` | Marks the root node of one candidate résumé |
| `data-language-code` | Marks the language level, such as `zh`, `en`, `jp` |
| `data-language-count` | Marks whether the table may contain several language versions |
| `data-section-type` | Marks semantic sections such as `base_info`, `education_list`, `work_experiences` |
| `data-collection` | Marks a collection of list-type fields |
| `data-record-type` | Marks one work, education, certificate, etc. record |
| `data-field` | Marks a concrete field, e.g. `company_name`, `school_name` |
| `label` / `data-label-for` | Keeps the original header evidence of the field |

(The sample values in the HTML above, such as `姓名` "name", `公司名称` "company name" and `2016年09月`, are sample data and kept as in the source.)

### 6.2 Side-by-side bilingual tables

When there is one résumé on the left and one on the right, a whole row must not be bound to a single language. `split_side_by_side_bilingual_dom()` in `repair_html()` splits by column range: the left side keeps the Chinese nodes, the right side is copied into English/Japanese nodes, and `data-language-code` is set separately for each.

So a source table like the following forms two language layers:

```text
Left:  姓名 张三 / 工作经验 / 教育经历   (Name 张三 / Work experience / Education)
Right: Name Zhang San / Work Experience / Education Background
```

The final JSON must keep both versions in `structured_data.resumes`; the translated name must also be kept, e.g. Chinese `张三` and English `Zhang San`; the name of the first language must not overwrite those of all languages.

### 6.3 Header demo information

Excel files often have demo headers or candidate-field notes at the top, for example:

```text
2014 男 1960 54 女 独身子なし 月収 年収 ネイティブ...
語学レベル 日本語 英語 中国語 上海語
```

(roughly: year, male/female, single/no children, monthly/annual income, native speaker; language level: Japanese, English, Chinese, Shanghainese)

These are template demos, not candidate data. The DOM binding stage should clear or ignore them, and must not generate basic information, language records, certificates or work records from them.

## 7. Step 3: Parse HTML into JSON

### `python/v2/xls_to_html_to_json.v2.py`

This is the new XLS→JSON entry. It does not modify the old Word parsing main flow; it reuses Word's HTML schema, date normalization, list structure and general validation, and adds XLS-specific DOM repair.

Typical full command:

```powershell
python python\xls_to_html_to_json.v2.py `
  --map <project root>\complete-transfered-htmls\xls\xls_conversion_map.json `
  --output-dir <project root>\complete-transfered-jsons\xls\中文 `
  --passed-dir <project root>\complete-transfered-htmls\xls\passed `
  --review-dir <project root>\complete-transfered-htmls\xls\review
```

Trial run of the first 100:

```powershell
python python\xls_to_html_to_json.v2.py `
  --map <project root>\complete-transfered-htmls\xls\xls_conversion_map.json `
  --output-dir <project root>\complete-transfered-jsons\xls\中文 `
  --passed-dir <project root>\complete-transfered-htmls\xls\passed `
  --review-dir <project root>\complete-transfered-htmls\xls\review `
  --limit 100
```

### 7.1 Actual call order of `process_row()`

For each source XLS, `process_row()` roughly executes in this order:

1. call `convert_single_excel_detailed()` in `process_xls_to_html.py` to regenerate or obtain the current HTML;
2. run `repair_html()` to add semantic sections and field nodes;
3. clean wrong names, wrong contact details and date/company bindings;
4. call `parse_html_record()` to parse basic information and lists by language layer;
5. merge the work, education, language, PR and certificate nodes that are clearly bound in the DOM;
6. repair the names of the side-by-side languages separately, so that the Chinese name does not overwrite the English/Japanese name;
7. remove illegal values such as header demos, address / household registration / political affiliation leaking into values, and dates leaking into company names;
8. filter non-formal certificate entries such as internships, part-time jobs, student practice, clubs, teams and activities;
9. order education and work experience from latest to earliest by date;
10. normalize mobile, e-mail, dates and file names;
11. write the complete repaired HTML into `raw_text`;
12. write `source.html_path`, `source.html_filename` and `source.source_landing_time` into the JSON;
13. run `valid_rule_issues()`; successful items are written to the formal Chinese JSON directory and problem items are marked `needs_review`.

### 7.2 Core modules currently reused

- `process_xls_to_html.py`: Excel grid reading and HTML generation;
- `c_resume_html_to_json_common.v2.py`: basic HTML parsing, dates, names, top-level snapshots and list schema;
- `reuse_complete_v1_jsons.py`: the general `validate_json()`;
- `c_resume_html_dom_common.v2.py`: HTML version, clean-up and text tools;
- `classify_passed_html_by_language.py`: language evidence and directory classification.

## 8. JSON structure and field rules

The core structure of the formal JSON is as follows:

```json
{
  "source": {
    "original_path": "absolute path of the source XLS",
    "html_path": "absolute path of the final HTML",
    "html_filename": "HTML file name",
    "source_landing_time": "landing time of the source file",
    "resume_index": 1,
    "resume_count": 1
  },
  "dates": {
    "resume_download_date": "landing time of the source file",
    "resume_updated_date": "résumé update time",
    "sys_created_date": "system creation time",
    "sys_updated_date": "system update time"
  },
  "structured_data": {
    "base_info": {},
    "expected_info": {},
    "current_info": {},
    "education_info": {},
    "resumes": []
  },
  "raw_text": "text snapshot of the repaired HTML"
}
```

Each language version in `resumes` contains:

```text
base_info
expected_list
work_experiences
education_list
certificate_list
language_list
skills_list
training_list
project_list
communication_list
```

A field passes not simply because it has a value, but only if it has a value, has evidence in the source HTML, has a legal field type, and has no header/demo leaking into it.

### Contact details

- At least one of mobile or e-mail is required for a valid résumé candidate;
- the platform contact details at the top are used only when they can be matched to the candidate record in the source HTML;
- mobile numbers are stripped of hyphens, spaces and brackets;
- international numbers keep the country code, e.g. `+81-8012345678`;
- contact details must not be overwritten by addresses, political affiliation or template headers.

### Education and work

Education is bound as "time, school, major, degree"; work is bound as "time, company, company industry/nature, department, position, job content, reason for leaving", etc. Education and work are by default sorted from latest to earliest by end time or start time.

Internships, student union / club activities, part-time jobs, on-campus practice and other content unrelated to the formal career do not enter the formal work or certificate lists, unless the source file clearly treats it as formal work experience and the business rules are met.

### Certificates, languages and skills

A certificate must have certificate semantics and evidence in the source text. Language demos, skill tags, software names and campus activity names must not be mistaken for certificates. Language versions and language proficiency levels are stored separately, and the horizontal/vertical layout of a language table must be based on the DOM cell positions.

### `raw_text`

`raw_text` comes from the repaired HTML text, not from the serialized JSON. This lets a later audit go back to the HTML on the spot and judge whether a field really came from the source DOM.

## 9. Incremental re-runs and dedicated repairs

### Side-by-side bilingual batch

```powershell
python python\xls_side_by_side_reprocess.v2.py
```

This script scans the existing XLS JSON and HTML, recognizes `data-language-count="2"`, `data-language-variants` or left/right five-column Chinese-English tables, de-duplicates by source path, and re-runs `process_row()`. The report is written to:

```text
complete-transfered-jsons\xls\中文\_xls_side_by_side_reprocess_report.json
```

Key indicators: `selected_sources`, `success`, `needs_review`, `failed`, `valid_language_variants`.

### Generalized incremental handling of anomalies

```powershell
python python\xls_incremental_reprocess.v2.py
```

This script rebuilds for the following anomalies:

- template headers appear in the basic information;
- work experience is empty but the HTML has work semantic nodes;
- bilingual HTML lacks English/Japanese language nodes;
- education is still a long heading text;
- the self-evaluation heading repeats the body;
- name or contact details are clearly abnormal.

The report is written to:

```text
complete-transfered-jsons\xls\中文\_xls_incremental_reprocess_report.json
```

### Mutual review with `complete-v1`

```powershell
python python\xls_bidirectional_review.v2.py
```

This step matches the historical JSON in `<project root>\complete-v1` exactly by `source.original_path`. Historical JSON can only serve as a candidate reference: a field may be merged only if the old JSON is more complete, the source HTML has evidence and there are no placeholders. The current parse result of the source file must not be overwritten on the basis of the same name alone.

The report is written to:

```text
complete-transfered-jsons\xls\中文\_xls_html_to_json_v3_bidirectional_review.json
```

## 10. Validation and reports

### Basic JSON audit

```powershell
python python\xls_json_audit.v2.py
```

This audit checks one by one:

- whether the JSON is readable;
- whether the source XLS can be found in the map;
- whether the HTML exists;
- whether name and contact details have evidence;
- whether the language versions are reasonable;
- whether lists such as work, education, certificates and languages have a legal structure;
- whether dates and company names have been misplaced;
- whether the main fields of the JSON and the HTML agree.

Output:

```text
complete-transfered-jsons\xls\中文\_xls_html_to_json_v3_post_audit.json
```

### Strict field audit

Use it when a finer DOM→JSON comparison is needed:

```powershell
python python\xls_field_audit.v2.py
```

This program collects the HTML `data-field` per language and compares them item by item with the JSON's basic and list fields. Different display formats are allowed for dates, but misplacement of year, month, company or school is not.

### Rebuilding the overall report

```powershell
python python\xls_report_rebuild.v2.py
```

It rebuilds, from the latest audit results:

```text
_xls_html_to_json_v3_report.json
```

`total` in the overall report is the number of map records and does not equal the number of JSON files. `not_resume` includes records that should not enter the résumé JSON, such as those without contact details, templates, job descriptions and company materials.

## 11. Recommended order of operations

1. Confirm the original XLS files are still in the collection directory and back up `xls_conversion_map.json`.
2. Run `xls_conversion_map.v2.py` when the inventory report has changed.
3. First run `process_xls_to_html.py --limit 100` as a small batch and check the HTML DOM.
4. Once the language, section, record and data-field in the DOM are correct, run XLS→JSON.
5. Output 100 JSON first and check that the source XLS, the HTML and the JSON agree.
6. Run `xls_json_audit.v2.py` and fix the problems the audit finds.
7. Run `xls_side_by_side_reprocess.v2.py` for the side-by-side bilingual templates.
8. Run `xls_incremental_reprocess.v2.py` for the remaining anomalies.
9. If necessary, do a source-path-level mutual review with `complete-v1`.
10. Run the full audit and `xls_report_rebuild.v2.py` again.
11. Hand the results to downstream systems only after the audit passes.

## 12. Common problems and how to handle them

### The JSON has a value but it is clearly illegal

First check whether the HTML bound the header, date, company and content to the wrong `data-field`. If the DOM is wrong, fix the binding in `repair_html()` or in the generation stage; do not just stitch strings together at the JSON stage.

### Chinese and English are mixed in the same `resume`

Check `data-language-code`, `data-language-count`, `data-language-variants` and the column range of the left/right tables. Use `xls_side_by_side_reprocess.v2.py` to regenerate the DOM and make sure every language has its own section.

### Work experience is empty

Check whether the `work_experiences` section of the HTML has `company_name`, date and `position_responsibilities` nodes. If the source table puts the formal experience in a project title, `bind_project_as_work_when_work_empty()` adds formal work nodes once the company, time and content are confirmed.

### Internships or club activities appear among the certificates

This is a template demo or campus activity bound by mistake. Check `certificate_list` and the corresponding HTML nodes, and use the current `sanitize_record()` rules to remove non-certificate content such as internships, part-time jobs, clubs, teams and activities.

### The audit passes but misplaced fields are still a concern

Do not look only at `valid`. Open the corresponding source XLS, HTML and JSON and check name, contact details, education, work, certificates, languages and PR field by field; if necessary run `xls_field_audit.v2.py` and `xls_bidirectional_review.v2.py`.

## 13. Version and maintenance conventions

- The XLS HTML generator version is the Word generator version reused by `process_xls_to_html.py`;
- the current XLS rule version is recorded as `xls-word-dom-3-language`;
- the JSON parsing entry is fixed as `python/v2/xls_to_html_to_json.v2.py`;
- when adding a field, first change the DOM binding and field aliases, then the JSON normalization;
- after changing DOM rules, re-run at least one Chinese, one Japanese and one Chinese-English / Chinese-Japanese side-by-side sample;
- after a bulk re-run, the full audit must be run and the dedicated reports kept;
- the original XLS, the source-file landing time, the source path and the HTML path are the minimum traceability information for later checks and must not be deleted or overwritten.

## 14. v2 file naming and shared modules

All original XLS scripts are kept. The new XLS category uniformly uses the `xls_` prefix:

| Original script | v2 counterpart |
|---|---|
| `build_xls_conversion_map.py` | `python/v2/xls_conversion_map.v2.py` |
| `process_xls_to_html.py` | `python/v2/process_xls_to_html.py` |
| `process_xls_html_to_json.py` | `python/v2/xls_to_html_to_json.v2.py` |
| `audit_xls_all_fields.py` | `python/v2/xls_field_audit.v2.py` |
| `audit_xls_json_outputs.py` | `python/v2/xls_json_audit.v2.py` |
| `audit_xls_source_html_json.py` | `python/v2/xls_source_html_json_audit.v2.py` |
| `bidirectional_review_xls_jsons.py` | `python/v2/xls_bidirectional_review.v2.py` |
| `rebuild_xls_report.py` | `python/v2/xls_report_rebuild.v2.py` |
| `reprocess_side_by_side_xls.py` | `python/v2/xls_side_by_side_reprocess.v2.py` |
| `reprocess_xls_incremental.py` | `python/v2/xls_incremental_reprocess.v2.py` |

Capabilities shared by Word/XLS uniformly use the `c_` prefix, for example:

```text
reuse_complete_v1_jsons.py
classify_passed_html_by_language.py
audit_chinese_json_against_sources.py
c_resume_html_dom_common.v2.py
c_resume_html_to_json_common.v2.py
```

For the complete file mapping see [`v2-name-mapping.md`](v2-name-mapping.md). The dotted `.v2.py` files are for naming cross-checks and command-line entry; when they need to be imported by Python, use the corresponding legal module name `_v2.py`.

The XLS main flow does not directly replace the old entries for now. The v2 files serve first as behaviour-identical counterparts, so that a mere rename does not change the flow; the production calls will be switched after the shared functions have been migrated and regression-tested.
