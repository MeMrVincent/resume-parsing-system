# Word → JSON 処理フローの説明

[English](v2-word-to-json.md) | [简体中文](v2-word-to-json.cn.md) | **日本語**

> このドキュメントは V2（word/xls/pdf/html → JSON）の流れを説明します。ディレクトリの既定値はルートの `config.example.json` を参照してください。本文中の `<プロジェクトルート>` は config の project_root のことです。統合した重複スクリプトは [`v2-name-mapping.ja.md`](v2-name-mapping.ja.md) の末尾にあります。

## 1. 目的とディレクトリ

このフローは、`docs` の範囲にある Word 履歴書を意味解析できる HTML に変換し、さらに統一 JSON に変換して、元ファイルとの監査を経てから正式ディレクトリに書き込みます。

- 元の Word：`<プロジェクトルート>\需要采集的简历文件夹`（元の履歴書フォルダ）
- 変換の作業ディレクトリ：`<プロジェクトルート>\complete-transfered-htmls\docs`
- 変換の総合マップ：`<プロジェクトルート>\complete-transfered-htmls\docs\word_conversion_map.json`
- 正式な JSON：`<プロジェクトルート>\complete-transfered-jsons\docs\<言語>`
- 監査と中間レポート：`<プロジェクトルート>\_resume_qa`
- JSON フィールドの説明：`CONTEXT.md`（リポジトリには公開していません。フィールド構造は `examples/` のサンプル JSON を参照）
- 参考テンプレート：`<プロジェクトルート>\complete-v1\Zhang San_13800000003.json`

正式な JSON のファイル名は次の形式です：

```text
氏名_携帯番号.json
氏名_メール.json
氏名_无联系方式.json        # 「无联系方式」＝連絡先なし
氏名_携帯番号_2.json        # 同名が衝突したら連番を増やす
```

同じ候補者の複数の Word は 1 つの JSON に統合できます。統合後のすべての元ファイルのパスは次に書き込みます：

```text
source.source_files[].original_path
source.merged_original_paths[]
```

そのため、「正式な JSON のファイル数」は「完了した Word 元ファイル数」より少なくなることがあります。全体の進捗は元ファイルのパスの数で数えなければなりません。

## 2. 全体の流れ

```text
Word
  ↓ c_resume_html_dom_common.v2.py
意味付き HTML + word_conversion_map.json
  ↓ 言語ごとに分類し、DOM を修復
中国語／日本語／中日／中英などの HTML
  ↓ 対応する言語のパーサー
ステージング JSON
  ↓ 構造の絞り込み + 元ファイルとのフィールドごとの監査
合格した JSON
  ↓ promote / finalize
正式な JSON + マップの更新 + 完了した HTML の削除
  ↓
難しいファイルは OCR / unknown / failed の人手バッチへ
  ↓ c_resume_ocr_normalize.v2.py
  ↓ c_resume_ocr_finalize.v2.py
正式な JSON、または invalid_resume の終了状態
```

原則：パーサーが JSON を生成しただけでは完了ではありません。構造の検証と元データの監査に合格し、正式ディレクトリに書き込まれ、元ファイルのパスが登録されて初めて完了とみなします。

## 3. 第 1 段階：Word → 意味付き HTML

### `python/v2/c_resume_html_dom_common.v2.py`

メインの変換プログラム。次を担当します：

- `.doc`、`.docx` などの Word ファイルを読み込む；
- 段落、表、見出し、文書のメタデータを抽出する；
- HTML を生成する；
- 識別できるフィールドを `data-field`、`label` などの意味付き DOM として書き出す；
- 同じ段落内の複数のフィールドに、それぞれ独立した子ノードを作る；
- 元の Word、HTML、言語、変換の状態、エラー情報を `word_conversion_map.json` に記録する；
- 履歴書の写真は残さない。

推奨する意味構造の例（label の値とフィールドの値はサンプルデータで、原文のまま残しています）：

```html
<p data-field="full_name" label="姓名">张三</p>
<p label="基本信息">
  <i data-field="gender" label="性别">女</i>
  <i data-field="marital_status" label="婚姻">未婚</i>
  <i data-field="birth_date" label="生日">1988年03月16日</i>
</p>
```

大量の正規表現でページ全体のプレーンテキストからフィールドを逆算することに頼らないでください。氏名、連絡先、資格、学歴、職歴などは、できるだけ独立した DOM ノードにします。

### HTML の修復・検査プログラム

- `python/v2/word_semantic_html_repair.v2.py`：解析しにくい HTML のフィールドノード、表、段落構造を修復する（元のファイル：`repair_semantic_html_dom.py`）。
- `python/v2/word_semantic_html_audit.v2.py`：HTML が解析可能な意味構造を備えているかを一括検査する（元のファイル：`audit_semantic_html_batch.py`）。
- `python/v2/word_html_audit_fix.v2.py`：初期の HTML 監査・修復プログラム（元のファイル：`audit_and_fix_htmls.py`）。
- `python/v2/word_full_docs_repair.v2.py`：初期のディレクトリ全体の詳細修復プログラム（元のファイル：`full_docs_deep_repair.py`）。
- `python/v2/word_nonchinese_semantics_repair.v2.py`：中国語以外の残りの HTML の意味の修復（元のファイル：`repair_nonchinese_remaining_semantics.py`）。
- `python/v2/word_nonchinese_known_name_repair.v2.py`：確認済みの氏名で、中国語以外の HTML の本人情報ノードを補う（元のファイル：`repair_nonchinese_known_names.py`）。
- `python/v2/word_verified_identity_inject.v2.py`：確認済みの本人情報フィールドを HTML に注入する（元のファイル：`inject_verified_html_identity.py`）。

これらの修復プログラムは、本当に解析しにくい HTML にだけ使います。すでに明確な意味付き DOM を持つファイルを重ねて書き換えてはいけません。

## 4. 第 2 段階：言語ごとの HTML の解析

### 中国語

#### `python/v2/run_chinese_html_to_json.py`

中国語のメインパーサーで、今回の処理でもっともよく使われた解析プログラムです。プラットフォームの識別、フィールドの正規化、履歴書の区切り、日付の処理、品質の検証、バッチレポートを担当します。

例：

```powershell
python python\v2\run_chinese_html_to_json.py `
  --html-dir <中国語 HTML ディレクトリ> `
  --json-dir <ステージング JSON ディレクトリ> `
  --map <プロジェクトルート>\complete-transfered-htmls\docs\word_conversion_map.json `
  --report <プロジェクトルート>\_resume_qa\chinese_batch.json `
  --progress-interval 10 `
  --file-timeout 30
```

### 日本語

- `python/v2/word_japanese_html_to_json.v2.py`：日本語の履歴書・職務経歴書の解析と、日本語の意味の正規化。
- `python/v2/word_japanese_identity_retry.v2.py`：ファイル名またはディレクトリに信頼できる人名がある場合に限り、本人情報を補った再試行用 HTML を生成する。
- `python/v2/word_japanese_name_retry.v2.py`：監査で出た問題に基づいて、日本語の氏名の再試行項目を準備する。

会社名、職種名、募集内容、請求書の名称を候補者の氏名として扱ってはいけません。

### 中日

- `python/v2/word_chinese_japanese_html_to_json.v2.py`：中日二言語の履歴書を処理し、複数の `resumes` の言語版を保持する。

### 中英およびその他の多言語

- `python/v2/run_chinese_english_html_to_json.py`：中英二言語の履歴書を処理する。
- `python/v2/word_chinese_english_identity_retry.v2.py`：中英の本人情報の再試行項目を準備する。
- `python/v2/word_multilingual_parser_stage.v2.py`：自動識別された多言語の解析結果をステージングする。
- `python/v2/word_english_parser_stage.v2.py`：英語パーサーの結果をステージングする。

多言語の JSON は対応する言語版を保持しなければなりません。氏名が同じというだけで、言語版が欠けた古い JSON をそのまま再利用してはいけません。

## 5. JSON の構造の絞り込みと元ファイルの監査

### 共通の構造検証

- `python/v2/reuse_complete_v1_jsons.py`
  - 統一された `validate_json()` を提供する；
  - 氏名、ファイル名、連絡先、日付、トップレベルのスナップショット、言語版、リストのフィールド、`raw_text` を検証する；
  - 複数のパーサーと補完プログラムが共用する基本の検証モジュール。
- `python/v2/word_strong_candidate_stage.v2.py`
  - ステージング JSON から、氏名が有効で構造が十分な候補を絞り込む；
  - 職種名、会社名、不明な氏名、中身のない JSON は拒否する。
- `python/v2/word_staged_audit_input.v2.py`
  - ステージング JSON と `word_conversion_map.json` 内の元の Word/HTML を対応付けて、監査の入力を作る。

### 中国語のフィールドごとの監査

- `python/v2/audit_chinese_json_against_sources.py`
  - JSON の氏名、連絡先、希望条件、職歴、学歴、資格、研修、プロジェクトなどのフィールドを元の Word/HTML と比較する；
  - サークルの役職、協会、懇親会、メンターなどの業務に関係しないデータは捨ててよく、正式な JSON に書き込む必要はない。
- `python/v2/word_chinese_source_repair.v2.py`
  - 監査レポートに基づいて、誤って入力されたフィールドを削除したり、確定できる問題を修復したりする；
  - 修復後は必ず監査を再実行する。
- `python/v2/c_resume_json_promote.v2.py`
  - 監査で問題のない中国語 JSON だけを正式ディレクトリに書き込む。
- `python/v2/c_resume_source_finalize.v2.py`
  - 昇格に成功した元ファイルを完了としてマークする；
  - `word_conversion_map.json` を更新する；
  - 対応する完了済みの HTML を削除する。

### 中国語以外のフィールドごとの監査

- `python/v2/c_resume_nonchinese_source_audit.v2.py`
  - 氏名の意味、言語版、会社、学校などのフィールドに、元ファイルで証拠が見つかるかを検査する。
- `python/v2/c_resume_nonchinese_promote.v2.py`
  - 監査状態が `passed` の中国語以外の JSON だけを昇格させ、元ファイルのパスを登録する。

### 過去の JSON の再利用

- `python/v2/word_unique_name_reuse_stage.v2.py`
  - 元のファイル名にある唯一の氏名から、正式ディレクトリの中で同一人物の可能性がある過去の JSON を探す；
  - 候補にすぎず、元ファイルの監査は引き続き必要。
- `python/v2/word_multilingual_v1_match_stage.v2.py`
  - `complete-v1` の中で一致する可能性のある多言語 JSON をステージングする。
- `python/v2/word_nonchinese_v1_repair.v2.py`
  - 確認できる中国語以外の `complete-v1` の候補を修復する。

氏名が同じというだけで JSON をコピーすることは禁止です。連絡先、職歴、学歴、資格、言語版がすべて一致していなければなりません。

## 6. 履歴書でないものと終了状態

- `python/v2/c_resume_nonresume_terminalize.v2.py`
  - 名称が明確な求人票、募集要項、会社資料、空白のテンプレート、面接の問題、テストの問題、契約書などを識別する；
  - `non_resume` の終了状態を書き込む。
- `python/v2/c_resume_invalid_terminalize.v2.py`
  - 古い `passed` キューの中で、正当な履歴書にならない中国語の項目を片付ける。
- `python/v2/c_resume_terminal_status.v2.py`
  - 人手で確認済みの 1 つの元ファイルに、指定の終了状態を書き込む。
- `python/v2/word_difficult_review_defer.v2.py`
  - 自動解析に失敗した、または厳密な監査に通らなかった残りの項目を `deferred_manual_review` にして、CSV/JSON の人手用一覧を生成する。

主な状態：

| 状態 | 意味 |
| --- | --- |
| `passed` | 正式な JSON を生成済みで、元ファイルのパスも登録済み |
| `needs_review` | 自動処理キュー内の確認待ちの項目 |
| `deferred_manual_review` | 自動フローがスキップし、人手の処理を待つ |
| `pending_user_ocr` | OCR ディレクトリにコピー済みで、人手の OCR／解析を待つ |
| `non_resume` | 履歴書でない、または無効な履歴書と確認済み |
| `identity_unrecoverable` | 候補者の本人情報を復元できない。後で無効な履歴書へ戻すことがある |
| `superseded` | より新しい版に置き換えられた |

無効な履歴書では次を使います：

```text
status = non_resume
terminal_classification = invalid_resume
json_status = invalid_resume
```

## 7. OCR、unknown、failed の人手による補完

### 人手処理が必要な元の Word のコピー

- `python/v2/c_resume_ocr_stage.v2.py`
  - 指定した種類の元の Word を `docs\ocr` にコピーする；
  - コピー名に元ファイルのパスのハッシュを含め、同名の上書きを避ける；
  - 状態を `pending_user_ocr` に更新する。
- `python/v2/word_ocr_folder_refresh.v2.py`
  - マップに基づいて、OCR ディレクトリで欠けているコピーを復元する；
  - OCR の一覧を書き直す。
- `python/v2/c_resume_unknown_stage.v2.py`
  - 指定した状態の元の Word を `unknown` または `failed` にコピーする；
  - `unknown_manifest.json` または `failed_manifest.json` を生成する。

例：

```powershell
python python\v2\c_resume_unknown_stage.v2.py `
  --progress <最新の全体進捗 JSON> `
  --output-dir <プロジェクトルート>\complete-transfered-htmls\docs\failed `
  --manifest <プロジェクトルート>\complete-transfered-htmls\docs\failed\failed_manifest.json `
  --statuses deferred_manual_review pending_user_ocr
```

### 人手で作成した JSON の検証

- `python/v2/c_resume_ocr_normalize.v2.py`
  - OCR の一覧または `unknown/failed` の manifest から、元ファイルのパスを復元する；
  - 古いフィールドを修正する。例：`resume_languge` → `resume_language`；
  - トップレベルの `expected_info` をオブジェクトに正規化する；
  - リストのフィールドと、職歴の成果フィールドを補う；
  - 「氏名 + 携帯番号／メール／連絡先なし」で名前を付け直す；
  - 「氏名要確認」、マスクされた氏名、本文なし、履歴の構造なし、履歴書でないものなどの結果を拒否する；
  - 有効な JSON だけをステージングディレクトリに書き込む。

### 人手の JSON の正式な登録

- `python/v2/c_resume_ocr_finalize.v2.py`
  - ステージング JSON を正式な中国語ディレクトリに書き込む；
  - 1 つの JSON に複数の元の Word が対応する場合に対応；
  - すべての元ファイルのパスを `passed_user_ocr` に更新する；
  - 対応する HTML を削除する。

例：

```powershell
python python\v2\c_resume_ocr_finalize.v2.py `
  --json-dir <検証に合格したステージングディレクトリ> `
  --map <プロジェクトルート>\complete-transfered-htmls\docs\word_conversion_map.json `
  --document-manifest <ocr/unknown/failed の一覧> `
  --formal-dir <プロジェクトルート>\complete-transfered-jsons\docs\中文 `
  --report <プロジェクトルート>\_resume_qa\user_json_finalize_apply.json `
  --apply
```

### 人手バッチの突き合わせと無効な項目の片付け

- `python/v2/word_batch_without_json_report.v2.py`
  - バッチの manifest と出力 JSON の `source_files` を比較する；
  - どの JSON にも対応付けられていない元の Word を列挙する。
- `python/v2/word_invalid_unknown_terminalize.v2.py`
  - 厳密な検証に失敗した JSON と対応する元ファイルを `invalid_resume` として登録する；
  - 対応する HTML を削除する。
- `python/v2/word_failed_batch_finalize.v2.py`
  - failed バッチのうち JSON が出力されなかった項目を処理する；
  - 無効な元ファイルをマークする；
  - 無効な作業コピー、中間 JSON、残った HTML を削除する。

注意：片付けるのは `docs\ocr`、`docs\unknown`、`docs\failed` にある作業コピーと中間結果だけです。元の履歴書フォルダ（`需要采集的简历文件夹`）にある元の Word を削除してはいけません。

## 8. 全体の統計

### `python/v2/c_resume_global_progress.v2.py`

`word_conversion_map.json` の元ファイルのパスを基準にして、次を集計します：

- 元ファイルの総数；
- 正式な JSON のファイル数；
- 正式な JSON がカバーしている元ファイルのパス数；
- 未完了の元ファイルのパス数；
- 各状態と各言語ディレクトリの件数；
- 正式ディレクトリ内の無効な JSON。

例：

```powershell
python python\v2\c_resume_global_progress.v2.py `
  --map <プロジェクトルート>\complete-transfered-htmls\docs\word_conversion_map.json `
  --formal-root <プロジェクトルート>\complete-transfered-jsons\docs `
  --output <プロジェクトルート>\_resume_qa\global_docs_progress.json
```

統計は次の関係を満たさなければなりません：

```text
元ファイルの総数 = 生成済みの正式な JSON がカバーする元ファイル
                 + 履歴書でないもの／無効な履歴書
                 + 人手／OCR の待ち項目
                 + identity_unrecoverable
                 + superseded
```

今回の最終状態：

```text
元ファイルの総数：14,019
正式な JSON がカバーする元ファイル：13,573
無効／履歴書でないもの：445
新しいファイルに置き換えられたもの：1
自動 review／OCR／人手の難件キュー：0
```

つまり：

```text
13,573 + 445 + 1 = 14,019
```

正式な JSON のファイル数は 13,539 で、完了した元ファイルのパス 13,573 より少ないのは、一部の候補者の重複した Word や多言語の Word が同じ JSON に統合されているためです。

## 9. 推奨する再実行の順序

1. `word_conversion_map.json` をバックアップする。
2. `c_resume_html_dom_common.v2.py` を実行して、HTML とマップを生成する。
3. 言語ディレクトリごとに HTML を確認し、必要なら意味付き DOM の修復プログラムを実行する。
4. 対応する言語のパーサーを使って、独立したステージングディレクトリに書き込む。正式ディレクトリへ直接書き込むのは禁止。
5. 構造の絞り込みプログラムを実行する。
6. 中国語または中国語以外の元ファイルの監査を実行する。
7. 確定できる問題を修復し、再度監査する。
8. 対応する `promote` プログラムで正式ディレクトリに書き込む。
9. `c_resume_source_finalize.v2.py` でマップを更新し、完了した HTML を削除する。
10. 残った難しい項目を OCR/unknown/failed にコピーして人手で処理する。
11. 人手の JSON は、まず `c_resume_ocr_normalize.v2.py` を実行する。
12. 有効な項目には `c_resume_ocr_finalize.v2.py` を実行し、無効な項目は `invalid_resume` の終了状態に書き込む。
13. 最後に `c_resume_global_progress.v2.py` を実行し、すべての元ファイルのパスの行き先が明確になっていることを確認する。

## 10. 重要な注意事項

- パーサーの「正常な出力」をそのまま有効な履歴書として扱わない。
- 会社名、職種、ディレクトリ名、募集内容、「氏名要確認」を氏名として扱わない。
- 氏名だけで過去の JSON を再利用しない。連絡先と主な経歴のフィールドを監査しなければならない。
- 多言語の履歴書は `structured_data.resumes` に各言語版を保持する。
- `expected_info`、`current_info`、`education_info` はトップレベルのスナップショットで、最初の主言語の履歴書と同期させる。
- 職歴、学歴、プロジェクト、研修、資格などは構造化されたリストでなければならない。
- `raw_text` は必ず存在し、JSON 内の主な構造化された値を網羅していること。
- 画像の履歴書は OCR に回し、Word→HTML の段階では写真を残さない。
- 完了した項目は差分で処理し、正式な JSON を繰り返し上書きしない。
- HTML や作業コピーを削除する前に、正式な JSON が書き込まれ、元ファイルのパスが登録されていることを必ず確認する。
- 元の Word は常に残す。削除してよいのは変換ディレクトリ内のコピーと中間ファイルだけ。

## 11. v2 のファイル命名と V1 との互換関係

元のスクリプトはすべて残しています。照合しやすいよう、統一したカテゴリ接頭辞を付けた v2 の対照ファイルを追加しました：

| 元のスクリプト | v2 対照ファイル | カテゴリ |
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
| `process_word_to_html.py` | `python/v2/c_resume_html_dom_common.v2.py` | 共通 |
| `process_word_html_to_json.py` | `python/v2/c_resume_html_to_json_common.v2.py` | 共通 |
| `reuse_complete_v1_jsons.py` | `python/v2/reuse_complete_v1_jsons.py` | 共通 |
| `audit_chinese_json_against_sources.py` | `python/v2/audit_chinese_json_against_sources.py` | 共通 |

共通カテゴリには一貫して `c_` 接頭辞を使います。完全な対応表は [`v2-name-mapping.ja.md`](v2-name-mapping.ja.md) を参照してください。
