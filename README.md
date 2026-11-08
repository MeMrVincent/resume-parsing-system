# resume-parsing-system

**English** | [简体中文](README.cn.md) | [日本語](README.ja.md)

Turns thousands of résumés in mixed formats (Word / Excel / PDF / web HTML; Chinese, Japanese, English and German) into **one JSON file per person with a uniform structure**, together with auditable cleaning, merging and multilingual alignment results.

> This repository contains **code and documentation only**. It holds no real résumés or personal data. Every person, phone number, e-mail address and company in `examples/` is fictional.

## What it does

```
Original résumé files ──V2──▶ one JSON per file ──V3──▶ one JSON per person (auditable)
(doc/xls/pdf/html)             (complete-v2 / v1)        (formal / needs_fix / pending_translation)
```

- **V2** (`python/v2/`, written by Codex): converts Word, XLS, PDF and web HTML to HTML, then parses it into JSON with a unified schema, with several rounds of auditing. See `docs/v2-*.md`.
- **V3** (`python/v3/`, written by Claude): treats records sharing a phone number or e-mail address as the same person and merges the V2 (primary) and V1 (secondary) JSON into one file per person; aligns each language version of multilingual résumés (zh/ja/en/de) item by item; runs an independent audit (30 checks); builds `raw_text` by fixed rules. See `docs/v3-pipeline.md`.
- **common** (`python/common/`): shared configuration loader `rc_config.py` and static code checker `check_code.py`.

## Directory layout

```
resume-system/
├─ README.md  README.cn.md  README.ja.md  LICENSE  requirements.txt
├─ config.example.json        Configuration template (copy to config.json and edit)
├─ python/
│  ├─ common/                 Configuration, static checks
│  ├─ v2/                     Word/XLS/PDF/HTML → JSON (includes the resume_importer library)
│  └─ v3/                     Merging, parsing, auditing, multilingual alignment
├─ scripts/                   Windows double-click entry points (merge.cmd, etc.)
├─ docs/                      Documentation and code index
├─ examples/                  Fictional sample data and sample output
└─ repair_data/               Personal data for one-off repair scripts (not committed; format samples only)
```

## Quick start

1. Install Python 3.13. V3 merging and auditing use only the standard library; V2 needs third-party packages: `pip install -r requirements.txt`.
2. Copy `config.example.json` to `config.json` and edit it as needed (see below).
3. Try it on the sample data first (no real data required):

```bash
python examples/make_examples.py
python python/v3/claude_merge.v3.py --v2-dir examples/v2 --v1-dir examples/v1 --out-root examples/out --run-id 20260101-demo
python python/v3/claude_merge_audit.v3.py --run-dir examples/out/20260101-demo --v2-dir examples/v2 --v1-dir examples/v1
```

   The 4 samples produce: 2 `formal` files (Chen Siming: V2 merged with V1; Lin Yating: Chinese–English bilingual), 1 `pending_translation` file (John Smith: English only, no Chinese primary version), and 1 entry in `ledgers/no_contact_ledger` because it has no contact details. Sample results are in `examples/output/`.

4. To run on your own data, put the V2/V1 JSON in the configured `v2_dir` and `v1_dir`, then run
   - Windows: double-click `scripts/merge.cmd` (merge → witness merge → audit);
   - other systems: the two `python` commands above (without the sample paths, they read the configuration).
5. Once the audit passes (`reports/audit.json`, every check at 0), copy `formal/` to `v3_dir` with `python python/v3/copy_to_v3.py`.

## Configuration (config.json)

All paths come from a single `config.json`; **no drive letters are hard-coded**. Lookup order: environment variable `RESUME_CONFIG` → `<project root>/config.json` → `<project root>/python/config.json`; defaults apply if none is found. Command-line arguments override the configuration.

| Key | Default | Meaning |
|---|---|---|
| `project_root` | empty (auto = parent of `python`) | Project/data root; can also be overridden with the `RESUME_ROOT` environment variable |
| `source_dir` | `需要采集的简历文件夹` | Folder of original résumés (read-only). **Replace it with your own folder name or an absolute path** |
| `html_dir` | `complete-transfered-htmls` | Intermediate V2 HTML |
| `v1_dir` / `v2_dir` | `complete-v1` / `complete-transfered-jsons` | Secondary / primary source JSON for merging |
| `v3_dir` | `complete-v3` | Final output |
| `output_dir` | `output` | Root of run output |
| `merge_out_dir` | `output/merge-v3` | Merge run output |
| `repair_dir` | `output/source-repair-v3` | Repair-copy directory (the subdirectory with the latest name is used) |
| `align_dir` | `claude-align` | Multilingual alignment working directory |
| `python_exe` | `python` | Interpreter used by the .cmd entry points |
| `path_map` | `{}` | Conversion table for the source paths recorded in the final JSON (`original_path` / `html_path`) once they are no longer valid: `{"old path prefix": "new location"}`; `{root}` in the new location means the project root. Example: `{"E:\\resume-system\\codex-transfered-htmls": "{root}/complete-transfered-htmls"}`. Used only to find files / check that they exist; the JSON is never rewritten |
| `dir_names` | `{}` | Extra directory rename map, e.g. `{"complete-transfered-jsons": "my-json"}` (every directory name hard-coded in the V2 scripts is resolved through it) |

Relative paths are relative to `project_root`; absolute paths are used as-is.

## Common commands

| Purpose | Command |
|---|---|
| Merge + audit (Windows double-click) | `scripts/merge.cmd` |
| Copy formal to v3_dir | `scripts/copy_to_v3.cmd` |
| Statically check all code (syntax, imports, file-name references) | `python python/common/check_code.py` or `scripts/check_code.cmd` |

## JSON field reference

This section describes the final per-person JSON produced by V3 (`formal/*.json`). The per-file JSON produced by V2 uses the same `structured_data` schema; the differences in the other top-level objects are listed at the end.

### Conventions

- **Dates inside résumés** use the format `YYYY年MM月DD日` (e.g. `2017年09月01日`). Incomplete dates are padded (`2010/4` → `2010年04月01日`). `resume_updated_date` and `resume_download_date` use `YYYY-MM-DD HH:MM:SS`; system timestamps use ISO 8601.
- **Field values stay in the language of the source.** Enumerations in the Chinese primary version use Chinese values (e.g. `全职` full-time, `在职` currently employed); the original values are kept as-is below.
- **List fields are never `null`**: they are `[]` when empty. Object snapshots (`expected_info`, `current_info`, `education_info`) always contain every key, with `""` for missing values.
- Only values supported by the source are filled in; nothing is invented.

### Top-level structure

```json
{
  "schema_version": "resume-merge-v3.0",
  "record_id": "merge-v3-<group_id>",
  "source": { ... },
  "dates": { ... },
  "extraction": { ... },
  "classification": { ... },
  "structured_data": {
    "base_info": { ... },
    "expected_info": { ... },
    "current_info": { ... },
    "education_info": { ... },
    "resumes": [
      {
        "resume_languge": "zh",
        "base_info": { ... },
        "expected_list": [ ... ],
        "work_experiences": [ ... ],
        "education_list": [ ... ],
        "certificate_list": [ ... ],
        "language_list": [ ... ],
        "skills_list": [ ... ],
        "training_list": [ ... ],
        "project_list": [ ... ],
        "communication_list": [ ... ]
      }
    ]
  },
  "raw_text": "<full text>",
  "quality": { ... },
  "merge_info": { ... }
}
```

| Field | Type | Description |
|---|---|---|
| `schema_version` | string | Schema version: `resume-merge-v3.0` for V3, `codex-resume-json-1.0` for V2 |
| `record_id` | string | Unique record ID (`merge-v3-<group_id>` in V3; a SHA-256 hash in V2) |
| `source` | object | Source file information |
| `dates` | object | Résumé dates and system timestamps |
| `extraction` | object | How the record was produced |
| `classification` | object | Document classification |
| `structured_data` | object | Structured résumé data (the core) |
| `raw_text` | string | Full plain text, for full-text search and keyword matching |
| `quality` | object | Quality summary |
| `merge_info` | object | Merge details (V3 only) |

### `source`

| Field | Type | Description |
|---|---|---|
| `original_path` | string | Path of the original Word/PDF/XLS/HTML file |
| `html_path` | string | Path of the intermediate HTML (may be empty) |
| `source_count` | number | Number of input JSON files merged into this record |
| `source_files` | array | One entry per input JSON (see below) |

Each `source_files` entry:

| Field | Type | Description |
|---|---|---|
| `index` | number | Position of the input within the group |
| `version` | string | `v2` or `v1` |
| `json_path` | string | Path of the input JSON |
| `sha256` | string | SHA-256 of the input JSON bytes |
| `duplicate_paths` | array | Other inputs with identical content |
| `original_path` / `html_path` | string | Original file and intermediate HTML of this input |
| `resume_updated_date` | string | Résumé update date of this input |
| `languages` | array | Language codes found in this input (e.g. `["zh", "en"]`) |

### `dates`

| Field | Type | Description |
|---|---|---|
| `resume_updated_date` | string | Résumé update date, `YYYY-MM-DD HH:MM:SS`. Taken from an explicit "updated" date in the body first, otherwise the historical modification time of the HTML file. Never empty, and never the current processing time |
| `resume_download_date` | string | Résumé download/application date, same format and fallback rule |
| `resume_updated_date_source` | string | Where the update date came from (e.g. `文档正文更新时间` = body text, `HTML文件修改时间（历史资料替代）` = file modification time) |
| `resume_download_date_source` | string | Where the download date came from |
| `sys_created_date` | string | System creation time (ISO 8601, e.g. `2026-07-31T11:06:00+09:00`) |
| `sys_updated_date` | string | System update time (ISO 8601) |

### `extraction`

| Field | Type | Description |
|---|---|---|
| `merger` | string | V3: merge script (`claude_merge.v3.py`) |
| `rule_version` | string | V3: merge rule version (e.g. `merge-v3.0-contact-key`) |

V2 records use `reader_group`, `converter`, `parser`, `status` (`success` / `failed`), `html_path` and `dom` (DOM statistics such as `heading_count`, `table_count`) instead.

### `classification`

| Field | Type | Description |
|---|---|---|
| `document_type` | string | `resume` / `jd` / `contract` / `unknown` |
| `reason` | string | Reason for the classification |

### `structured_data`

Top-level snapshots are **always rebuilt from `resumes[0]`** (the Chinese primary version) and must never disagree with it:

| Snapshot | Source |
|---|---|
| `base_info` | `resumes[0].base_info` |
| `expected_info` | `resumes[0].expected_list[0]`; an object with all 8 keys empty when the list is empty |
| `current_info` | The most recent entry in `resumes[0].work_experiences`; an object with all 15 keys empty when there is none |
| `education_info` | The entry in `resumes[0].education_list` with the highest degree rank and latest dates; an object with all 7 keys empty when there is none |

#### `base_info` (20 fields)

| Field | Type | Description |
|---|---|---|
| `full_name` | string | Candidate name |
| `gender` | string | Gender (`男` male / `女` female) |
| `age` | string | Age |
| `birth_date` | string | Date of birth (`YYYY年MM月DD日`) |
| `birth_year` | string | Year of birth |
| `marital_status` | string | Marital status |
| `children_status` | string | Children |
| `political_status` | string | Political affiliation |
| `height_cm` | string | Height (cm) |
| `weight_kg` | string | Weight (kg) |
| `household_registration` | string | Place of household registration (hukou) |
| `address` | string | Current address |
| `postal_code` | string | Postal code |
| `platform_from` | string | Source platform (e.g. `前程无忧(51job)`) |
| `platform_resume_id` | string | Résumé ID on the platform (Liepin: 12 digits) |
| `phone` | string | Mobile phone number |
| `email` | string | E-mail address |
| `city` | string | City of residence |
| `nationality` | string | Nationality |
| `pr` | string | Self-assessment / personal strengths |

#### `expected_info` / `expected_list` items (8 fields)

| Field | Type | Description |
|---|---|---|
| `expected_city` | string | Desired city |
| `expected_position` | string | Desired position |
| `expected_salary` | string | Desired monthly salary |
| `expected_annual_salary_min` | string | Desired annual salary, lower bound |
| `expected_annual_salary_max` | string | Desired annual salary, upper bound |
| `expected_industry` | string | Desired industry |
| `expected_employment_type` | string | Desired employment type (`全职` full-time / `兼职` part-time / `实习` internship / `remote` / `混合办公` hybrid) |
| `expected_start_date` | string | Available start date |

#### `current_info` (15 fields)

The same as the first 15 fields of a `work_experiences` item (from `company_name` to `position_resigned`).

#### `education_info` / `education_list` items (7 fields)

| Field | Type | Description |
|---|---|---|
| `school_name` | string | School name |
| `school_major_name` | string | Major |
| `school_degree_type` | string | Degree (`博士后` postdoc / `博士` doctorate / `硕士` master / `本科` bachelor / `大专` junior college / `高中` high school / `中专` vocational secondary / `初中` junior high / `小学` primary) |
| `school_degree_rank` | string | Degree rank `1`–`7` (see the mapping below) |
| `school_education_type` | string | Mode of study (`全日制研究生` full-time postgraduate / `全日制大学` full-time university / `全日制大专` / `全日制高中` / `全日制中专`, etc.) |
| `school_start_ym` | string | Start date (`YYYY年MM月01日`) |
| `school_end_ym` | string | Graduation / end date |

`school_degree_rank` mapping: `7` postdoc, `6` doctorate, `5` master, `4` bachelor, `3` junior college, `2` high school / vocational secondary, `1` junior high or below.

### `resumes` (one item per language version)

- `resumes[0]` is always the Chinese primary version (`resume_languge = "zh"`) and must contain real Chinese content.
- Original foreign-language versions (English, Japanese, German, …) follow from `resumes[1]`, each labelled with its real language.
- A résumé that exists only in a foreign language gets a field-by-field Chinese translation as `resumes[0]` and keeps the untouched original as `resumes[1]`.
- All language versions have exactly the same structure, are deep copies (no shared references), and their lists correspond item by item.
- Every list holds one item per entry (one job, one school, …); a whole résumé is never stuffed into a single item.

| Field | Type | Description |
|---|---|---|
| `resume_languge` | string | Language code (`zh` / `en` / `jp` / `de`, …). The historical spelling is kept for output; `resume_language` is accepted only when reading |
| `base_info` | object | Basic information (same fields as the top-level `base_info`) |
| `expected_list` | array | Job preferences |
| `work_experiences` | array | Work history |
| `education_list` | array | Education history |
| `certificate_list` | array | Professional certificates |
| `language_list` | array | Language skills |
| `skills_list` | array | Skills |
| `training_list` | array | Training history |
| `project_list` | array | Project history |
| `communication_list` | array | Communication records |

#### `work_experiences` items (18 fields)

| Field | Type | Description |
|---|---|---|
| `company_name` | string | Full company name (date suffixes and pipes stripped) |
| `company_employees` | string | Company size (e.g. `100-499人`, `未填写` = not filled in) |
| `company_industry` | string | Industry |
| `position` | string | Job title (never a company attribute such as `公司性质：`) |
| `position_type` | string | Job function category |
| `position_salary` | string | Monthly salary |
| `position_dept` | string | Department |
| `position_report_to` | string | Reports to |
| `position_subordinate` | string | Number of direct reports |
| `employment_type` | string | `全职` full-time / `兼职` part-time / `实习` internship |
| `annual_salary_min` | string | Annual salary, lower bound |
| `annual_salary_max` | string | Annual salary, upper bound |
| `status` | string | `在职` currently employed / `离职` left |
| `position_start` | string | Start date (`YYYY年MM月01日`) |
| `position_resigned` | string | End date (`""` while still employed) |
| `resigned_reason` | string | Reason for leaving |
| `position_responsibilities` | string | Duties and results only (company type, size, city and similar lines are removed) |
| `position_achievements` | string | Achievements |

#### `certificate_list` items (3 fields)

| Field | Type | Description |
|---|---|---|
| `certificate_name` | string | Certificate name (including level / score) |
| `certificate_type` | string | Certificate type (`证书` certificate / `结业证` completion / `培训证` training, …) |
| `certificate_time` | string | Date obtained (`YYYY年MM月01日`) |

Language tests (CET, JLPT, TOEIC, TOEFL, BEC, …) go into `language_list`, never into `certificate_list` as well. Non-language qualifications, professional certifications, driving licences, etc. go into `certificate_list`.

#### `language_list` items (4 fields)

| Field | Type | Description |
|---|---|---|
| `language_name` | string | Language (`日语` Japanese / `英语` English / `德语` German / `普通话` Mandarin / `粤语` Cantonese, …) |
| `language_level` | string | Level (e.g. `熟练` proficient / `一般` basic / `CET-6` / `N1`) |
| `language_certificate` | string | Has a certificate (`有` yes / `无` no / `""`) |
| `language_certificate_time` | string | Date the certificate was obtained (usually empty) |

#### `skills_list` items (2 fields)

| Field | Type | Description |
|---|---|---|
| `skill_name` | string | Skill |
| `skill_level` | string | Proficiency (e.g. `熟练` / `精通` / `掌握`) |

#### `training_list` items (7 fields)

| Field | Type | Description |
|---|---|---|
| `sequence_no` | number | Sequence number (from 1) |
| `organization_name` | string | Training provider |
| `training_name` | string | Course / programme name |
| `start_ym` | string | Start date (`YYYY年MM月01日`) |
| `end_ym` | string | End date |
| `certificate_name` | string | Certificate obtained (`""` if none) |
| `description` | string | Course description |

#### `project_list` items (11 fields)

| Field | Type | Description |
|---|---|---|
| `sequence_no` | number | Sequence number (from 1) |
| `fingerprint` | string | Project fingerprint for de-duplication (usually empty) |
| `project_name` | string | Project name |
| `company_or_client` | string | Company or client |
| `role_name` | string | Role in the project |
| `start_ym` | string | Start date (`YYYY年MM月01日`) |
| `end_ym` | string | End date |
| `description` | string | Project description (software/hardware environment, etc.) |
| `responsibilities` | string | Responsibilities |
| `achievements` | string | Results |
| `keywords` | string | Keyword tags |

#### `communication_list` items (2 fields)

| Field | Type | Description |
|---|---|---|
| `communicate_time` | string | Time (`YYYY年MM月DD日 HH:mm:ss`) |
| `communicate_content` | string | Content |

### `raw_text`

- **Single source, single language, no translation**: the original document text (sheet-marker lines such as `### 工作表` removed, each line trimmed, blank lines dropped, joined with `\n`).
- **Merged, translated or multilingual**: assembled from the fields, one field per line joined with `\n`. Language versions follow the order of `resumes` (Chinese first); within each version: `base_info`, `expected_list`, `work_experiences`, `education_list`, `certificate_list`, `language_list`, `skills_list`, `training_list`, `project_list`, `communication_list`. Empty values and placeholders are never written. Multilingual résumés are aligned before `raw_text` is built.
- `quality.raw_text_length` always equals the length of the final `raw_text`.

### `quality`

| Field | Type | Description |
|---|---|---|
| `full_name` | string | Candidate name (for quick checks) |
| `has_work` | boolean | Has work history |
| `work_count` | number | Number of work entries |
| `has_education` | boolean | Has education history |
| `education_count` | number | Number of education entries |
| `languages` | array | Language codes present in `resumes` |
| `raw_text_length` | number | Character length of `raw_text` |

V2 records may contain only some of these fields, depending on the converter.

### `merge_info` (V3 only)

| Field | Type | Description |
|---|---|---|
| `group_id` | string | Group ID (derived from the SHA-256 of the members' original bytes, so it is stable when repair copies are used) |
| `rule_version` | string | Merge rule version |
| `output_filename` | string | Output file name: `<name>_<contact>.json` — normalised mobile number first, then e-mail |
| `name_status` | string | `valid` or `unreliable` |
| `canonical_name` | string | Name used for the record |
| `english_name` | string | English / romanised name, if any |
| `primary_phone` / `primary_email` | string | Contact details used as the identity key |
| `other_phones` / `other_emails` / `landlines` | array | Other contact details found |
| `shared_contacts_ignored` | array | Contacts shared with other people and therefore not used as a key |
| `needs_translation` | boolean | `true` when there is no Chinese version |
| `v2_count` / `v1_count` | number | Number of V2 / V1 inputs |
| `language_sources` | object | For each language, the indexes of the `source_files` it came from |
| `translated_from` | string | Source language of the Chinese translation, if any |
| `name_note` | string | Note about the name decision |
| `conflict_count` | number | Number of field conflicts recorded |
| `field_issue_count` / `high_issue_count` | number | Number of field issues / high-severity issues |
| `name_linked_sources` | array | Inputs linked by name evidence |
| `output_category` | string | `formal` / `needs_fix` / `pending_translation` |

### Identity and output rules

- Records sharing a normalised mobile number or a valid e-mail address are the same person. Conflicts in name, birthday, company, etc. are logged but do not split the group.
- A contact shared by different people belongs to only one of them: the person whose résumé was created most recently.
- Every formal JSON must have at least one valid phone number or e-mail; inputs without one go to `ledgers/no_contact_ledger` and get no output file.
- Output categories: no Chinese version → `pending_translation`; high-severity issues or an invalid name → `needs_fix`; otherwise → `formal`.

### Multi-language date rule

Within one résumé, the dates of all language versions must agree, and the Chinese version (`resumes[0]`) is the reference. After alignment, `unify_dates` (in `claude_merge.v3.py`) does this, only for rows already paired (lists of equal length across languages) and only for date fields (`position_start`, `position_resigned`, `school_start_ym`, `school_end_ym`, project and training `start_ym` / `end_ym`, `certificate_time`, `language_certificate_time`):

1. Every date is first normalised to `YYYY年MM月DD日`. Time-of-day is dropped; a missing month is never invented (year-only values and ranges stay as they are).
2. Chinese blank, other language filled → the Chinese date is filled from the other language.
3. Other language blank or different → it is overwritten by the Chinese date.
4. The difference is more than 24 months, or a value cannot be compared → Chinese still wins, but it is logged as `date_unify_override_far` in `ledgers/cleaning_ledger`. Such rows are often mis-paired (different stints or employers), so they are the ones to spot-check against the source files.
5. If the change would make a start date later than its end date, the whole row is left unchanged and logged as `date_unify_skip`.
6. `birth_date` follows the same rule, with two exceptions: English long forms (`November 2, 1965`) are normalised first, and when year and month agree but one day is `01` (padding for a year-month-only value) the value with the real day is used for all languages. A different birth year is left alone and logged as `date_unify_skip`.

Every change is logged in the cleaning ledger as `date_unify_format`, `date_unify_fill_zh`, `date_unify_fill_other` or `date_unify_override`. The snapshots (`current_info`, `education_info`) and `raw_text` are computed after this step. The independent audit ignores date fields when it matches rows against manual decisions.

### V2 per-file JSON differences

- `schema_version` is `codex-resume-json-1.0`; `record_id` is a SHA-256 hash; there is no `merge_info`.
- `source` has `path`, `original_path`, `filename`, `extension`, `size` (bytes), `html_filename` and `note`.
- `extraction` uses the V2 fields listed above.
- File name: `<name>_<first 12 chars of the SHA-256 of the source path>.json`; multilingual merges may chain several hashes (`<name>_<zh hash>_<en hash>.json`); a missing name gives `待确认姓名_<hash>.json` (name to be confirmed).

## Notes

- Résumés are sensitive personal data. `.gitignore` already excludes the data directories, `config.json`, `CONTEXT.md`, run output and the various decision/alignment files. **Do not commit real résumés, or JSON generated from them, to any repository.**
- Two one-off repair scripts in V2 need a "name / phone number" mapping whose data is not published with the repository: see `repair_data/README.md`.
- The V2 scripts grew in historical batches (Word / XLS / PDF / Web handled separately). They were only made path-configurable, not rewritten; the clean-up removed only files with identical content (mapping in `docs/v2-name-mapping.md`).

## License

MIT, see `LICENSE`.
