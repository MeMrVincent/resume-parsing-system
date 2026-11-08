# V3: Merge, Clean-up and Audit Pipeline

**English** | [简体中文](v3-pipeline.cn.md) | [日本語](v3-pipeline.ja.md)

> V3 merges the JSON produced by V2 (and the historical V1 JSON) into "one JSON per person" by phone number / e-mail address, and runs an independent audit. This document describes how the code fits together, the processing order, the repair directory and the `raw_text` rules. `<project root>` and `<repair_dir>` in the example paths are determined by `config.json`.

## 0. Iron rules (do not break)

1. **Never modify the originals**: the source résumé folder, `complete-transfered-jsons`, `complete-v1`, `codex-*`, `CONTEXT.md` (ask the user before changing CONTEXT.md). Every repair is an "overlay copy", placed in `<repair_dir>\<latest subdirectory>\` (JSON files with the same name under `v1\` and `v2\` replace the input).
2. Code files are named `claude_*.v3.py`. After changing code you must re-run the audit; never bypass it.
3. Verification order after every change: run the merge (in the cloud or locally) → audit → run again with a different `PYTHONHASHSEED` (e.g. 777) for comparison → only when both results are identical does it count.
4. If the user only wants to double-click once: `<project root>\scripts\merge.cmd` (not `claude_run_merge.v3.cmd`, which does not read the repair directory). It takes the **newest-named** directory under `output\source-repair-v3`, unpacks every `repair_json*.zip` in it (sorted by file name; later files overwrite same-named earlier ones), then merges, runs the comparison merge and audits.
5. Reply to the user in Chinese.

## 1. How the Python code fits together

Directory: `python\v3\` (the shared configuration module is `python\common\rc_config.py`). Shared module file names contain dots and cannot be imported normally; always load them by path with `importlib.util.spec_from_file_location`.

### 1.1 Main pipeline (dependency direction: upstream output → downstream reads)

```
Originals (source résumé folder) + complete-transfered-jsons + complete-v1  (read-only)
   │
   ├─ claude_pack_sources.v3.py   Pack: inputs/ (all v1, v2 JSON), originals/, html/, manifest.csv (JSON → original → key in the pack)
   ├─ claude_source_text.v3.py    Extract full text from the originals → texts/<key>.txt, extract_ledger.csv   [cloud only: needs LibreOffice/pdftotext]
   ├─ claude_source_audit.v3.py   Check each input JSON against its original and decide whether the parser was at fault → source_audit_ledger.csv, contact_recovery.csv
   ├─ claude_parse_*.v3.py        New per-template parsers (full source text → resume object)
   │     cn_platform (Zhaopin) / 51job / liepin / zh_report (recommendation report) / zh_table (recruiting-site xls) / zh_free (fallback) / jp / en
   ├─ claude_reparse.v3.py        Re-parse with the new per-template parser, score old vs new JSON against the source, replace only if not worse → written to the repair copy
   ├─ claude_source_repair.v3.py  Restore mobiles / e-mails / names that are in the original but missed by the JSON (repair copy; excludes consultant/HR/public contacts)
   ├─ claude_name_fix.v3.py       Name check against the source (last layer of the repair copy; uncertain cases go to name_review.csv)
   │        └─→ all of the above write to the "repair copy directory" (--repair-dir): same-named JSON under v1/, v2/
   │
   ├─ claude_merge.v3.py          ★ Main program: cross-checks and merges V2/V1, identifies the same person by mobile/e-mail, one JSON per person
   │     Loads: claude_merge_common.v3.py (field contract, contact/date/name normalization, language detection, snapshots, raw_text construction)
   │            claude_merge_normalize.v3.py (field placement and clean-up; rules map one-to-one to the checks)
   │            claude_merge_checks.v3.py (field problem checks high/medium/low; record only, never block)
   │            claude_merge_manual.v3.py (reads and applies manual_decisions.json / translations.json / alignments.json from the repair-dir)
   │     Input files (under repair-dir): manual_decisions.json, translations.json, alignments.json, source_texts.json, v1/, v2/
   │     Output: <out>\<run-id>\formal|needs_fix|pending_translation\*.json, ledgers\*, reports\summary.json
   ├─ claude_merge_audit.v3.py    ★ Independent acceptance (read-only, 30 checks, passes only when all are 0; loads common/checks, re-reads the decision files registered in summary itself and verifies their sha256)
   ├─ claude_review_book.v3.py    Turns needs_fix / review ledgers into a manual-review Excel (with source excerpts)
   └─ `scripts\merge.cmd`   Double-click entry: unpack zips → merge → witness merge → audit
```

Auxiliary: `claude_archive.v3.py` (plan-based archiving, never deletes), `claude_verify_python.v3.py` (static check of compilation/dependencies), `claude_split_pack.v3.py` (splits large packs into 30MB chunks), `CODE_INDEX.md` (directory index).

### 1.2 Processing order of build_group inside merge (once per person)

1. Split the V2/V1 inputs into "people" by contact details and merge those of the same person (V2 first, V1 supplements; `group_id` is computed from the sha256 of the members' **original bytes**, so it stays unchanged after switching to overlay copies).
2. `normalize_resumes` (field placement / clean-up) → `apply_translation` (for people without a Chinese version: copy the foreign-language version as resumes[0] and replace it with the translation, `translations.json`, gated by `source_sha256`) → manual decisions `apply_items` (`manual_decisions.json`: set/delete/move/accept/add, matched by content; if no match, skip and record) → `apply_name` (name) → **`apply_alignment` (multilingual alignment, `alignments.json`, gated by the content sha256 of each language version; on mismatch it is skipped and recorded as `alignment:unmatched`)** → snapshot → raw_text.
3. Classification: no zh → `pending_translation`; has a high-severity problem or an invalid name → `needs_fix`; everything else → `formal`.
4. Inputs without a valid mobile/e-mail do not go into the output JSON; they go to `ledgers\no_contact_ledger`.

### 1.3 What each file in the repair directory (`<repair_dir>\<latest subdirectory>\`) does

| File | Purpose |
|---|---|
| `repair_json_*.zip` | Overlay-copy JSON (unpacked into `v1\`, `v2\`), unpacked in file-name order, later ones overwrite earlier ones |
| `repair_json_zz_split.zip` | Batch 11: overlay copies for splitting shared contacts and separating two merged people |
| `repair_json_zz_align.zip` | Batch 12: unpacks to `alignments.json` and `source_texts.json` |
| `manual_decisions.json` | 1,654 manual decisions (including `exclude`, `exclude_record`, `name`) |
| `translations.json` | 166 "foreign language → Chinese" translations |
| `alignments.json` | Multilingual alignment records (2,119 entries, full set) |
| `source_texts.json` | Source text of single-source résumés (10,112 originals, 14,732 inputs) |

> **Note** (already handled, but remember it): on every run `repair_json_zz_align.zip` unpacks its `alignments.json` and `source_texts.json` over the same-named files in the directory. When you update `alignments.json` later, **delete this zip first** (or repack the new files into it), otherwise the new files are overwritten by the old ones. `source_texts.json` is unrelated to alignment and needs no further change.

### 1.4 raw_text rules (project convention)

- Single source + single language + no translation: use the source text (drop the "### worksheet" marker lines, strip each line, drop empty lines, join with `\n`). "Single source" = all inputs in the group map to the same original.
- Merged, translated or multilingual: assemble from the fields, one field per line, joined with `\n`; the order is each language version in turn, and within each version the basic information first and then each list; empty values / placeholders are not written, no de-duplication, no blank lines (`claude_merge_common.v3.py: build_raw_text_assembled`).
- Currently: 6,894 use the source text, 3,682 use assembly. The audit's `raw_text_rule` checks every one; `raw_text_original_sha` verifies the original's sha256 on the PC.
- For multilingual résumés, **align first, then write raw_text** (the merge flow already works in this order; nothing to do by hand).

### 1.5 Alignment tools (added in this batch; under `<project root>\python\`, data in `<project root>\claude-align\`)

| File | Purpose |
|---|---|
| `claude_align_auto.v3.py` | Automatic alignment by program: within one language, cluster and de-duplicate by name + date; across languages, pair by date (work / education / project / training) or by name (lists without dates) |
| `claude_align_mktasks.v3.py` | Reads `export2\` (language versions before alignment), lists only "rows still missing a language", and generates `tasks2\<group_id>.json` |
| `claude_align_mkbatches.v3.py` | Cuts tasks2 into batches `batches\bNNN.jsonl` (each batch ≤90k characters, ≤40 entries) |
| `PROMPT.md` (in `claude-align\`) | Full task description for the LLM (pairing / back-filling translations / dropping leftover rows / output format) |
| `claude_align_check.v3.py` | Checks the result file of one batch: `python claude_align_check.v3.py b034`; only "ok" is acceptable |
| `claude_align_assemble.v3.py` | Collects `results\*.json` into `alignments.json`: `python claude_align_assemble.v3.py <results directory> <output file>` |

The environment variable `CLAUDE_ALIGN_DIR` can change the data directory (default: `claude-align` one level above `python`). These scripts need `claude_merge_common.v3.py` in the same directory.

**Data directory `claude-align\`** (first double-click `python\v3\claude_unpack_align.v3.cmd` to unpack `claude_align_data.zip`):
`export2\` (2,186 exports before alignment), `tasks2\` (2,119 tasks), `batches\` (b000–b068), `results\` (all 69 batches b000–b068), `PROMPT.md`.

## 5. Important reminders (pitfalls already hit)

- Alignment records are gated by "the sha256 of each language version's content": if earlier clean-up, translation, manual decisions or overlay copies change the content of an entry, its alignment is skipped as `unmatched` and that entry must be re-aligned.
- When simulating a PC run in the cloud, the repair directory must contain everything from all `repair_json*.zip` (all overlay copies in `v1\` and `v2\`), otherwise the results deviate widely.
- The first 8 characters of a run id must be a date (e.g. `20261012-…`); otherwise the comparison merge judges "not idempotent" because the timestamps differ.
- If a sub-task's single output exceeds the limit it reports an error, but the file may already have been written; check the result file before deciding whether to redo it.
- Baseline run log: `output\merge-v3\20261012-2125-v3.2-repair.log`.
