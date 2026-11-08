# V3：統合・クレンジング・監査パイプライン

[English](v3-pipeline.md) | [简体中文](v3-pipeline.cn.md) | **日本語**

> V3 は V2 が出力した JSON（および過去の V1 JSON）を携帯電話番号／メールアドレスで統合して「1 人 1 ファイルの JSON」にし、独立した監査を行います。このドキュメントでは、コード間の関係、処理順序、修復ディレクトリ、`raw_text` のルールを説明します。例のパスにある `<プロジェクトルート>`、`<repair_dir>` は `config.json` で決まります。

## 0. 鉄則（破らないこと）

1. **原本を変更しない**：元の履歴書フォルダ、`complete-transfered-jsons`、`complete-v1`、`codex-*`、`CONTEXT.md`（CONTEXT.md を変更する前に利用者へ確認する）。すべての修復は「上書き用コピー」で、`<repair_dir>\<最新のサブディレクトリ>\` に置く（`v1\`、`v2\` 配下の同名 JSON が入力を置き換える）。
2. コードファイル名は `claude_*.v3.py`。コードを変更したら必ず監査を再実行し、監査を迂回しない。
3. 変更のたびの検証順序：クラウド／ローカルで統合を 1 回実行 → 監査 → `PYTHONHASHSEED` を変えて（例：777）もう一度実行して比較 → 2 回の結果が完全に一致して初めて有効。
4. 利用者がダブルクリックで 1 回だけ実行したい場合：`<プロジェクトルート>\scripts\merge.cmd`（`claude_run_merge.v3.cmd` ではない。こちらは修復ディレクトリを読まない）。`output\source-repair-v3` 配下で名前が**最も新しい**ディレクトリを取り、その中のすべての `repair_json*.zip` を（ファイル名順に、後のものが同名の前のものを上書きして）展開し、続いて統合、比較用統合、監査を行う。
5. 利用者への返信は中国語で行う。

## 1. Python コード間の関係

ディレクトリ：`python\v3\`（共通の設定モジュールは `python\common\rc_config.py`）。共通モジュールのファイル名にはドットが含まれ、通常の import はできないため、必ず `importlib.util.spec_from_file_location` でパスを指定して読み込む。

### 1.1 メインパイプライン（依存の向き：上流の成果物 → 下流が読む）

```
原本（元の履歴書フォルダ）+ complete-transfered-jsons + complete-v1  （読み取り専用）
   │
   ├─ claude_pack_sources.v3.py   パック：inputs/（v1・v2 のすべての JSON）、originals/、html/、manifest.csv（JSON → 原本 → パック内のキー）
   ├─ claude_source_text.v3.py    原本から全文を抽出 → texts/<key>.txt、extract_ledger.csv   【クラウド専用：LibreOffice/pdftotext が必要】
   ├─ claude_source_audit.v3.py   各入力 JSON を原本と照合し、パーサーの問題かを判定 → source_audit_ledger.csv、contact_recovery.csv
   ├─ claude_parse_*.v3.py        各テンプレートの新しいパーサー（原文全文 → resume オブジェクト）
   │     cn_platform（智聯）/ 51job / liepin / zh_report（推薦レポート）/ zh_table（求人サイトの xls）/ zh_free（フォールバック）/ jp / en
   ├─ claude_reparse.v3.py        テンプレートごとに新しいパーサーで再解析し、旧 JSON と原文に対するスコアを比べ、劣らなければ置き換える → 修復コピーに書き出す
   ├─ claude_source_repair.v3.py  原本にあるのに JSON が漏らした携帯番号／メール／氏名を補う（修復コピー。コンサルタント・人事・共用の連絡先は除外）
   ├─ claude_name_fix.v3.py       氏名を原文と照合（修復コピーの最後の層。判断がつかないものは name_review.csv に書く）
   │        └─→ 以上はすべて「修復コピーのディレクトリ」(--repair-dir) に出力：v1/、v2/ 配下の同名 JSON
   │
   ├─ claude_merge.v3.py          ★メインプログラム：V2/V1 を相互照合して統合し、携帯番号／メールで同一人物を判定、1 人 1 ファイルの JSON にする
   │     読み込み：claude_merge_common.v3.py（フィールドの規約、連絡先・日付・氏名の正規化、言語判定、スナップショット、raw_text の構築）
   │               claude_merge_normalize.v3.py（フィールドの振り分けと整理。規則は checks と 1 対 1 に対応）
   │               claude_merge_checks.v3.py（フィールドの問題検査 high/medium/low。記録のみで処理は止めない）
   │               claude_merge_manual.v3.py（repair-dir の manual_decisions.json / translations.json / alignments.json を読んで適用）
   │     入力ファイル（repair-dir 配下）：manual_decisions.json、translations.json、alignments.json、source_texts.json、v1/、v2/
   │     出力：<out>\<run-id>\formal|needs_fix|pending_translation\*.json、ledgers\*、reports\summary.json
   ├─ claude_merge_audit.v3.py    ★独立した検収（読み取り専用、30 項目の検査、すべて 0 で合格。common/checks を読み込み、summary に登録された決定ファイルを自分で読み直して sha256 を照合）
   ├─ claude_review_book.v3.py    needs_fix／要確認の台帳から、人手で確認するための Excel を生成（原文の抜粋付き）
   └─ `scripts\merge.cmd`   ダブルクリックの入口：zip を展開 → merge → witness merge → audit
```

補助：`claude_archive.v3.py`（計画式アーカイブ、削除はしない）、`claude_verify_python.v3.py`（コンパイル／依存関係の静的チェック）、`claude_split_pack.v3.py`（大きなパックを 30MB の塊に分割）、`CODE_INDEX.ja.md`（ディレクトリ索引）。

### 1.2 merge 内部の build_group の処理順序（1 人ごとに 1 回）

1. 連絡先で V2/V1 の入力を「人」に分け、同一人物のものを統合する（V2 を優先し V1 で補う。`group_id` はメンバーの**元のバイト列**の sha256 から計算するため、上書きコピーに切り替えても `group_id` は変わらない）。
2. `normalize_resumes`（フィールドの振り分け／整理）→ `apply_translation`（中国語版がない人：外国語版を resumes[0] としてコピーし訳文に置き換える。`translations.json`、`source_sha256` でゲート）→ 人手の決定 `apply_items`（`manual_decisions.json`：set/delete/move/accept/add、内容で照合し、一致しなければスキップして記録）→ `apply_name`（氏名）→ **`apply_alignment`（多言語の対応付け、`alignments.json`、各言語版の内容の sha256 でゲート。一致しなければスキップし `alignment:unmatched` を記録）** → スナップショット → raw_text。
3. 分類：zh がない → `pending_translation`；high の問題がある、または氏名が無効 → `needs_fix`；それ以外 → `formal`。
4. 有効な携帯番号／メールがない入力は出力 JSON に入れず、`ledgers\no_contact_ledger` に入れる。

### 1.3 修復ディレクトリ（`<repair_dir>\<最新のサブディレクトリ>\`）内の各ファイルの役割

| ファイル | 役割 |
|---|---|
| `repair_json_*.zip` | 上書き用コピーの JSON（`v1\`、`v2\` に展開）。ファイル名順に順次展開し、後のものが前のものを上書きする |
| `repair_json_zz_split.zip` | 第 11 バッチ：共用の連絡先の分割、2 人が統合されたものを分けるための上書きコピー |
| `repair_json_zz_align.zip` | 第 12 バッチ：`alignments.json` と `source_texts.json` に展開される |
| `manual_decisions.json` | 1,654 件の人手の決定（`exclude`、`exclude_record`、`name` を含む） |
| `translations.json` | 166 件の「外国語 → 中国語」訳 |
| `alignments.json` | 多言語の対応付け記録（2,119 件、全件） |
| `source_texts.json` | 単一ソースの履歴書の原文テキスト（原本 10,112 件、入力 14,732 件） |

> **注意**（対応済みだが覚えておくこと）：`repair_json_zz_align.zip` は実行のたびに、中の `alignments.json` と `source_texts.json` をディレクトリ内の同名ファイルに上書き展開します。今後 `alignments.json` を更新するときは、**先にこの zip を削除する**（または新しいファイルを zip に詰め直す）こと。さもないと新しいファイルが古いもので上書きされます。`source_texts.json` は対応付けとは無関係で、これ以上変更する必要はありません。

### 1.4 raw_text のルール（プロジェクトの取り決め）

- 単一ソース + 単一言語 + 翻訳なし：原文テキストを使う（「### ワークシート」の見出し行を除き、各行の前後の空白を除去し、空行を除き、`\n` で連結する）。「単一ソース」＝グループ内のすべての入力が同じ原本に対応すること。
- 統合・翻訳・多言語：各フィールドを組み立て、1 フィールド 1 行で `\n` で連結する。順序は言語版ごとに順に、各版の中は基本情報を先に、続いて各リスト。空の値・プレースホルダーは書かず、重複排除はせず、空行は入れない（`claude_merge_common.v3.py: build_raw_text_assembled`）。
- 現状：6,894 件が原文を使用、3,682 件が組み立てを使用。監査の `raw_text_rule` が 1 件ずつ照合し、`raw_text_original_sha` は PC 上で原本の sha256 を照合する。
- 多言語の履歴書は**先に対応付けしてから raw_text を書く**（統合の流れはすでにこの順序になっており、手作業は不要）。

### 1.5 対応付けツール（今回のバッチで追加。`<プロジェクトルート>\python\` 配下、データは `<プロジェクトルート>\claude-align\`）

| ファイル | 役割 |
|---|---|
| `claude_align_auto.v3.py` | プログラムによる自動対応付け：同一言語内は名称 + 日付でクラスタリングして重複排除、言語間は日付（職歴／学歴／プロジェクト／研修）または名称（日付のないリスト）でペアにする |
| `claude_align_mktasks.v3.py` | `export2\`（対応付け前の各言語版）を読み、「まだ言語が足りない行」だけを列挙して `tasks2\<group_id>.json` を生成する |
| `claude_align_mkbatches.v3.py` | tasks2 をバッチ `batches\bNNN.jsonl` に切る（1 バッチ 9 万文字以下、40 件以下） |
| `PROMPT.md`（`claude-align\`） | 大規模言語モデルへの完全なタスク説明（ペアリング／訳の補完／残った行の drop／出力形式） |
| `claude_align_check.v3.py` | あるバッチの結果ファイルを検査：`python claude_align_check.v3.py b034`、ok と出れば合格 |
| `claude_align_assemble.v3.py` | `results\*.json` を `alignments.json` にまとめる：`python claude_align_assemble.v3.py <results ディレクトリ> <出力ファイル>` |

環境変数 `CLAUDE_ALIGN_DIR` でデータディレクトリを変更できます（既定は `python` の 1 つ上にある `claude-align`）。これらのスクリプトは `claude_merge_common.v3.py` が同じディレクトリにある必要があります。

**データディレクトリ `claude-align\`**（先に `python\v3\claude_unpack_align.v3.cmd` をダブルクリックして `claude_align_data.zip` を展開）：
`export2\`（対応付け前の書き出し 2,186 件）、`tasks2\`（タスク 2,119 件）、`batches\`（b000–b068）、`results\`（b000–b068 の全 69 バッチ）、`PROMPT.md`。

## 5. 重要な注意点（これまでにはまった落とし穴）

- 対応付け記録は「各言語版の内容の sha256」でゲートされます。前段のクレンジング・翻訳・人手の決定・上書きコピーの変更で内容が変わった場合、その件の対応付けは `unmatched` としてスキップされるため、その件を再度対応付けする必要があります。
- クラウドで PC 実行を模擬するときは、修復ディレクトリにすべての `repair_json*.zip` の中身（`v1\`、`v2\` のすべての上書きコピー）が揃っていなければなりません。さもないと結果が大きくずれます。
- 実行 id の先頭 8 文字は日付（例：`20261012-…`）でなければなりません。さもないと比較用統合でタイムスタンプが異なり、「冪等でない」と判定されます。
- サブタスクの 1 回の出力が上限を超えるとエラーになりますが、ファイルはすでに書き込まれている場合があります。やり直す前に結果ファイルを確認してください。
- 基準となる実行ログ：`output\merge-v3\20261012-2125-v3.2-repair.log`。
