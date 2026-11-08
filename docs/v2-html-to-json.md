# HTML/Web to JSON: Flow Description

**English** | [简体中文](v2-html-to-json.cn.md) | [日本語](v2-html-to-json.ja.md)

> This document describes the V2 (word/xls/pdf/html → JSON) flow. Default directories are in `config.example.json` in the repository root; `<project root>` in the text is `project_root` in config. The duplicate scripts that were merged are listed at the end of [`v2-name-mapping.md`](v2-name-mapping.md).

## 1. Goal and scope

This flow converts web pages, e-mail archives and HTML-like résumés into the unified résumé JSON, and reviews source files, staged files, JSON fields and multilingual versions file by file, with incremental repair.

The scope is defined by the `Web网页与邮件 (.html, .eml)` worksheet (web pages and e-mails) of `32718文件报告.xlsx` (the 32,718-file inventory report), not by a directory or a batch of files. The main suffixes currently supported are:

```text
.html  .htm  .mht  .mhtml  .eml
```

Core principles:

- Original web files are read-only: they must not be renamed, moved, overwritten or deleted;
- Staged files must be byte-identical to the source files and verified with SHA-256;
- The HTML / e-mail body is the factual source of the fields; "the field has a value" is not enough to judge it qualified;
- The JSON must follow the field, snapshot and multilingual conventions of `CONTEXT.md` in the root directory;
- In each round, record the problems first, then repair incrementally, and finally re-review everything;
- Business JSON does not store bloated audit history such as `repair_history` or `rounds`;
- The status, problems and repair actions of each record are all kept in external `_*.v2.json` reports.

## 2. Directories and authoritative files

| Item | Path |
| --- | --- |
| File inventory report | `<project root>\32718文件报告.xlsx` |
| Authoritative JSON field specification | `CONTEXT.md` (not published with the repository; for the field structure see the example JSON in `examples/`) |
| Original web files | `<project root>\需要采集的简历文件夹` and its subdirectories |
| Safe web staging directory | `<project root>\complete-transfered-htmls\web\input` |
| Main web conversion map | `<project root>\complete-transfered-htmls\web\web_conversion_map.v2.json` |
| Formal business JSON | `<project root>\complete-transfered-jsons\web` |
| Full independent review report | `<project root>\complete-transfered-jsons\web\_web_full_review.v2.json` |
| Full incremental repair report | `<project root>\complete-transfered-jsons\web\_web_full_repair.v2.json` |
| File name and flattening report | `<project root>\complete-transfered-jsons\web\_web_output_organize.v2.json` |

`web_conversion_map.v2.json` is the source-file-level master index. The workbook row, source path, staging path, source hash, JSON path, status and check results are all linked through it. Do not guess the correspondence between a source file and a JSON from file names.

All business JSON in the formal directory is flat. The file name format is:

```text
name_mobile.json
name_email.json
name_无联系方式.json       # "无联系方式" = no contact details
name_mobile_2.json        # incremented when several files share the same name and contact
```

The file name uses the mobile number first; if there is none, the e-mail; if neither exists, `无联系方式`. JSON files starting with `_` are reports, not candidate business JSON.

## 3. How the files relate to each other

```text
32718文件报告.xlsx
        │ defines the full scope and the original absolute paths
        ▼
web_conversion_map.v2.py
        │ builds / maintains one record per source file
        ├──────────────► web_conversion_map.v2.json
        │                         │
        │ read-only copy with     │ provides the source/stage/json correspondence
        │ hash verification       │
        ▼                         ▼
complete-transfered-htmls/web/input  web_html_to_json.v2.py
                                          │
                                          ▼
                           complete-transfered-jsons/web/*.json
                                          │
                         ┌────────────────┴────────────────┐
                         ▼                                 ▼
              web_full_review.v2.py              web_json_audit.v2.py
         independent read-only full review      basic audit / status write-back
                         │
                         ▼
                 _web_full_review.v2.json
                         │ the problem list is the repair input
                         ▼
                 web_full_repair.v2.py
              field-by-field incremental repair
                         │
                         ├────────► _web_full_repair.v2.json
                         │          final status of each record
                         ▼
                 web_full_review.v2.py
                    full re-review
                         │
                         ▼
                web_output_organize.v2.py
     file-name check, flattening, clean-up of old copies
```

Explanation of the relations:

1. The workbook decides "which physical files should be processed".
2. The map decides "which source file, staged file and JSON a given row corresponds to".
3. Staged files keep the original bytes, and the converter reads the body text from the staged file.
4. Business JSON stores normalized data, not long per-round audit history.
5. The review report records the problems before and after repair; the repair report records the status and repair actions of each map object.
6. The organize report records the final file names, the move results and the old copies that were deleted precisely.

## 4. Step 1: Build the full web map

### `python/v2/web_conversion_map.v2.py`

This program reads the web worksheet of the workbook and keeps every row, including records finally judged as non-résumés, without contact details, or with an abnormal source file. It copies the source files to the safe staging directory and computes content hashes; it does not touch the original files.

Run:

```powershell
cd <project root>
python python\web_conversion_map.v2.py
```

Use `--force` only when the workbook scope or the source files have changed:

```powershell
python python\web_conversion_map.v2.py --force
```

Note: `--force` re-copies the staged files and recomputes the status. Do not run it casually in a batch that has already been repaired, so that map statuses that were already confirmed are not overwritten with the initial state.

## 5. Step 2: Web/HTML to JSON

### `python/v2/web_html_to_json.v2.py`

This is the current formal entry from web HTML-like files to JSON. It:

- reads `.html`, `.htm`, `.mht`, `.mhtml` and `.eml`;
- decodes MHTML / EML mail bodies;
- parses 51job, Zhaopin, Liepin and ordinary HTML résumés;
- extracts basic information, job intention, work, education, certificates, languages, skills, training and projects;
- generates the JSON structure specified by `CONTEXT.md`;
- for source files in pure English or pure Japanese, generates a genuine field-level Chinese `resumes[0]` and keeps the source-language version in the following resume;
- writes the JSON atomically and writes back to the map.

Full conversion:

```powershell
python python\web_html_to_json.v2.py --limit 0
```

Re-run only given workbook indices:

```powershell
python python\web_html_to_json.v2.py --indices 300 650 1559 --force
```

Reproducible random sampling:

```powershell
python python\web_html_to_json.v2.py --random --limit 50 --seed 20260804
```

Apply `--force` only to records that clearly need rebuilding. Before a bulk overwrite, save the pre-repair report so the evidence of the problems is not lost.

## 6. JSON structure requirements

The top level is fixed as:

```text
schema_version
record_id
source
extraction
dates
classification
structured_data
raw_text
quality
```

`structured_data` is fixed as:

```text
base_info
expected_info
current_info
education_info
resumes
```

Where:

- `base_info`, `expected_info`, `current_info` and `education_info` are top-level snapshots of `resumes[0]`;
- all experience lists may exist only in `structured_data.resumes[]`;
- `raw_text` may exist only at the top level of the JSON;
- list items must not contain extra fields;
- dates must use the unified format, e.g. `2013年03月01日`;
- `school_degree_rank` may only be the string `"1"` to `"7"` or an empty string;
- `resume_languge` keeps the official spelling used in `CONTEXT.md`.

Do not write the following into business JSON:

```text
repair_history
rounds
```

These two kinds of history make the JSON grow quickly. The problems and repair status of each round belong in external reports.

## 7. Multilingual rules

The multilingual order must be uniform:

```text
resumes[0].resume_languge = "zh"
resumes[1].resume_languge = "en" or "jp"
```

Strict requirements:

- `resumes[0]` must be field-level Chinese content; it is not enough to change the language label of an English or Japanese object to `zh`;
- foreign-language company names, school names, positions, majors, duties, certificates, etc. all need to be translated into the Chinese primary version;
- the following foreign-language resume keeps the source-language content;
- the same experience must correspond across language versions in list length, order, dates and meaning;
- multilingual objects must be deep-copied, so that two resumes never reference the same object and overwrite each other;
- when the foreign-language original has only one version, first copy it as the source-language version, then generate the Chinese translated version.

Dedicated tool:

### `python/v2/web_multilingual_repair.v2.py`

Handles only the multilingual problems marked in the full review report, repairs the Chinese primary version with local offline translation support, and keeps the source-language version.

```powershell
python python\web_multilingual_repair.v2.py
```

After running it, `web_full_review.v2.py` must be run again; the translation program exiting successfully must not be taken as the data having passed.

## 8. Strict semantic rules

A field having a value does not mean the field is correct. Review and repair must check both "what the value is" and "whether the value belongs to this field".

### Work experience

The following are not formal work experience:

- internships, probation placements, intern, trainee;
- clubs, student unions, school associations and on-campus part-time jobs;
- stand-alone research assistant roles, research projects and graduation theses;
- section titles such as training, language ability and special skills;
- duty sentences, industry, salary or serial-number fragments sitting in the company-name position.

When the same company and dates were parsed into "an industry/salary line + a position line", merge them into one genuine work experience.

### Education

- `school_name` must be a school or educational institution, not a major, skill, place, training course or section title;
- when one education record was split into "one entry for the school + one entry for the degree", merge them;
- clubs, on-campus part-time jobs, short training and graduation research cannot be formal education records;
- identical start and end dates are not necessarily duplicates; they may be a double degree, so compare the school and other fields before judging.

### Certificates and certifications

A certificate name must point to a definite certificate, licence, qualification or exam level. The following must be deleted or reconstructed:

- places, e.g. "Shanghai", "Japan";
- names of schools, training institutions or certification companies;
- section titles or generic words such as "certificate", "training certificate";
- status sentences such as "currently an … auditor", which should be rebuilt from the source text into a definite qualification name;
- truncated text such as "份考试" (a fragment of "… exams");
- honours such as outstanding graduate, scholarship, competition awards and outstanding thesis;
- job duties, experiment arrangements and activity descriptions.

Example:

```text
Wrong:   目前为OHSMS审核员   ("currently an OHSMS auditor")
Correct: 职业健康安全管理体系（OHSMS）国家注册审核员   (nationally registered auditor of the occupational health and safety management system (OHSMS))

Wrong:   方圆标志认证集团有限公司   (Fangyuan Certification Group Co., Ltd.)
Action:  delete; it is a training/certification institution, not a certificate
```

### Skills, languages, training and projects

- `skills_list` must not be split by word or punctuation;
- English / Japanese and other languages go into `language_list`;
- CET, TEM, JLPT, IELTS and similar certificates go into language certificates or the certificate list;
- training institutions, course names and certificate names must not be mixed up with each other;
- internships, clubs and graduation theses must not be kept disguised as projects or training.

## 9. Step 3: Full independent review

### `python/v2/web_full_review.v2.py`

This program only reads the business JSON, the map, the staged files and the source files, and writes an independent report. It does not import the production conversion logic to prove that the production logic is correct, so it is the final quality gate.

```powershell
python python\web_full_review.v2.py
```

Default report:

```text
complete-transfered-jsons/web/_web_full_review.v2.json
```

It checks:

- whether the workbook and the map correspond one to one;
- whether source files, staged files and hashes are consistent;
- whether the JSON path, source path and file size are correct;
- whether the top level and all list fields strictly align with `CONTEXT.md`;
- whether the top-level snapshots agree with `resumes[0]`;
- whether field values can be found as evidence in the source text;
- whether the multilingual versions are complete and translations and lists are aligned;
- whether companies, schools, positions, certificates and skills are semantically misplaced;
- whether non-principal content such as internships, clubs, school associations and research remains;
- whether there are orphan JSON files, duplicate outputs and empty source files.

When saving the report from before a round of repair, use a separate file name; do not overwrite:

```powershell
python python\web_full_review.v2.py `
  --report complete-transfered-jsons\web\_web_review_round_before.v2.json
```

## 10. Step 4: Incremental repair

### `python/v2/web_full_repair.v2.py`

This program reads the review report, re-checks every record in the map, changes only the problem fields that have reliable source evidence, and writes the final status of each object to an external repair report.

```powershell
python python\web_full_repair.v2.py
```

Specify the pre-repair report of a round and a separate repair report:

```powershell
python python\web_full_repair.v2.py `
  --review complete-transfered-jsons\web\_web_review_round_before.v2.json `
  --report complete-transfered-jsons\web\_web_repair_round.v2.json
```

Status meanings:

| Status | Meaning |
| --- | --- |
| `clean` | No problems in this round's check and nothing modified |
| `repaired` | Incremental changes were made this round; no problems remain after re-review |
| `needs_review` | Problems remain after automatic repair |
| `no_json_expected` | Non-résumé, no contact details, etc.; no JSON is expected |
| `failed` | Source file missing, empty or unreadable; JSON cannot be generated reliably |

After repair, a full review must be run again. The recommended loop:

```text
review (save the pre-repair report)
  → repair (save this round's repair report)
  → review (update the final report)
  → if problems remain, go to the next round
```

Do not clear a field in bulk just to get the report down to zero. Content that can be recovered from the source text should be rebuilt; delete only when it is certain to be pollution, misplacement or non-principal content.

## 11. Other auxiliary programs

| File | Purpose | Relation to the main flow |
| --- | --- | --- |
| `python/v2/web_json_audit.v2.py` | Basic HTML/JSON/map audit; `--apply` writes the audit status back | Auxiliary check; does not replace the full review |
| `python/v2/web_html_json_reconcile.v2.py` | Early JSON-by-JSON reconciliation program | Compatibility tool; the main flow now prefers the full review |
| `python/v2/web_html_json_repair.v2.py` | Early repair based on the reconcile results | Compatibility tool; must not write embedded long history again |
| `python/v2/web_batch_report.v2.py` | Rebuilds the batch statistics report from the map | Summary only; does not repair business data |
| `python/v2/web_internship_boundary_recovery.v2.py` | Records recovery from the former intern/International boundary defect | Dedicated historical verification tool |
| `python/v2/web_output_organize.v2.py` | Reviews file names, flattens the output, updates the map, cleans up verified old copies | Run after all content problems are cleared |

These auxiliary programs must not change the principle that "the full review is the final independent quality gate".

## 12. File name check and flattening

### `python/v2/web_output_organize.v2.py`

Review only first:

```powershell
python python\web_output_organize.v2.py
```

Apply only after `collision_count = 0` and `needs_review = 0`:

```powershell
python python\web_output_organize.v2.py --apply
```

When applying, the program:

- generates the final file name from the name and the real contact details;
- appends `_2`, `_3` to several files with the same name/contact;
- moves JSON in classification subdirectories to the root of `complete-transfered-jsons/web`;
- updates `json_path` in the map;
- deletes an old copy only if both `record_id + source.path` of the old file and the currently mapped file agree;
- does not delete unknown files, report files or JSON that cannot be paired uniquely.

Do not move JSON by hand in bulk and then edit the map, otherwise the source files, JSON and reports lose their links.

## 13. Recommended full re-run order

```powershell
cd <project root>

# 1. Rebuild the map only when the workbook or the source scope changes
python python\web_conversion_map.v2.py

# 2. Generate or selectively rebuild the JSON
python python\web_html_to_json.v2.py --limit 0

# 3. Save the full list of problems before repair
python python\web_full_review.v2.py `
  --report complete-transfered-jsons\web\_web_review_round_before.v2.json

# 4. Incremental repair
python python\web_full_repair.v2.py `
  --review complete-transfered-jsons\web\_web_review_round_before.v2.json `
  --report complete-transfered-jsons\web\_web_repair_round.v2.json

# 5. Final full re-review
python python\web_full_review.v2.py

# 6. File-name review; add --apply once nothing blocks
python python\web_output_organize.v2.py
```

If step 5 still shows business JSON problems, go back to step 3 for the next round and do not proceed to file organization.

## 14. Common problems and how to handle them

### A JSON field has a value but it is clearly wrong semantically

The source text and the field semantics prevail. A company cannot be a duty sentence, a school cannot be "special skills", a certificate cannot be a place or an institution. First record the exact path and value in the review report, then repair incrementally.

### In an English résumé `resumes[0]` is also English

That is wrong. `resumes[0]` should be the complete Chinese translation, and only `resumes[1]` keeps the `en` source text; the same applies to Japanese.

### One work experience was parsed into two entries

Compare company, start time, end time and position. If one entry is an industry/salary fragment and the other is the real position, merge them; do not simply keep two non-empty records.

### The certificate list contains outstanding graduate, thesis or a training institution

These are not certificates. Honours are deleted according to the current business rules; a training institution stays in the institution field of the training record; if someone clearly passed an auditor exam and obtained the qualification, rebuild it from the source text as the full qualification name.

### The source file exists but is 0 bytes

It is judged an unqualified source file and the status is recorded as `failed / source_file_empty`. No empty-shell JSON may be generated and the content must not be guessed from the file name. It can be restored only after a non-empty original file is obtained again.

### The review report is zero but a human still finds problems

First check whether the review rules really traverse all `resumes` and lists, paying special attention to coverage gaps such as indentation, early `return`, swallowed exceptions or checking only empty lists. After adding a rule, the review must be re-run on all 1,739 business JSON files, not just the files the user gave as examples.

### JSON files keep growing

Check whether `repair_history` or `rounds` was written into the business JSON by mistake. Audit history must be kept in external reports. After deleting them, scan everything to confirm that neither key exists in nested objects either.

## 15. Status of the current batch (2026-08-27)

| Item | Count / status |
| --- | --- |
| Total map records | 1,754 |
| Valid business JSON | 1,739 |
| Expected to produce no JSON | 14 |
| Source file failures | 1 (index 664; both the source file and the staged file are 0 bytes) |
| Orphan JSON | 0 |
| Classification subdirectories | 0; all business JSON is flat |
| Leftover `repair_history` / `rounds` | 0 |
| Business problems in the current full review | Only the empty-source-file problem of index 664 |

The certificate-specific review of this round also keeps:

```text
complete-transfered-jsons/web/_web_certificate_review_round_before.v2.json
complete-transfered-jsons/web/_web_certificate_repair_round.v2.json
```

The former records the 22 résumés and 38 wrong certificate items before repair; the latter records the per-object repair status of this round. The final result is still determined by `_web_full_review.v2.json`.

## 16. v2 naming and maintenance conventions

- The implementation and command-line entries of the current web main flow all use `*.v2.py`;
- `web_html_to_json.v2.py` loads the dotted v2 dependencies at run time;
- Unversioned or `_v2.py` historical files serve only as a compatibility base and should not be used as new web batch entries;
- When adding review, repair or dedicated scripts, keep using `web_<purpose>.v2.py`;
- A new rule must enter the independent review first and then the repair; it must not be silently corrected only in the generator;
- Before changing the field structure, update `CONTEXT.md` first, then synchronize the converter, reviewer, repairer and documentation;
- Every program that writes business JSON must keep writes atomic and verify that the JSON can be parsed afterwards.
