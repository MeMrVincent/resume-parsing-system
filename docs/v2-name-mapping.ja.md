# Word / XLS → JSON v2 ファイル名対照表

[English](v2-name-mapping.md) | [简体中文](v2-name-mapping.cn.md) | **日本語**

> このドキュメントは V2（word/xls/pdf/html → JSON）の流れを説明します。ディレクトリの既定値はルートの `config.example.json` を参照してください。本文中の `<プロジェクトルート>` は config の project_root のことです。統合した重複スクリプトは `v2-name-mapping.ja.md` の末尾にあります。

このディレクトリの元のスクリプトはすべて残しています。今回のバッチで追加した `*.v2.py` ファイルは、後で照合しやすくするための独立したコピーで、元のスクリプトのロジックと import 関係をそのまま保っています。本番の入口が切り替わったという意味ではありません。

## Word 専用のコード

| 元のファイル | v2 ファイル | 役割 |
|---|---|---|
| `process_word_to_html.py` | `c_resume_html_dom_common.v2.py` | Word → 意味付き HTML の主変換 |
| `process_word_html_to_json.py` | `word_to_html_to_json.v2.py` | 意味付き HTML → JSON の主解析 |
| `codex_word_html_json_100.py` | `word_schema_extension.v2.py` | Word スキーマの拡張 |
| `run_chinese_html_to_json.py` | `run_chinese_html_to_json.py` | 中国語 HTML 解析の入口 |
| `run_chinese_english_html_to_json.py` | `run_chinese_english_html_to_json.py` | 中英 HTML 解析の入口 |
| `run_chinese_japanese_html_to_json.py` | `word_chinese_japanese_html_to_json.v2.py` | 中日 HTML 解析の入口 |
| `run_japanese_html_to_json.py` | `word_japanese_html_to_json.v2.py` | 日本語 HTML 解析の入口 |
| `repair_semantic_html_dom.py` | `word_semantic_html_repair.v2.py` | Word の意味付き DOM の修復 |
| `audit_semantic_html_batch.py` | `word_semantic_html_audit.v2.py` | Word の意味付き HTML の一括監査 |
| `audit_and_fix_htmls.py` | `word_html_audit_fix.v2.py` | Word HTML の初期の監査と修復 |
| `full_docs_deep_repair.py` | `word_full_docs_repair.v2.py` | Word ディレクトリ全体の詳細な修復 |
| `repair_nonchinese_remaining_semantics.py` | `word_nonchinese_semantics_repair.v2.py` | 中国語以外の意味の修復 |
| `repair_nonchinese_known_names.py` | `word_nonchinese_known_name_repair.v2.py` | 中国語以外の確認済み氏名の修復 |
| `inject_verified_html_identity.py` | `word_verified_identity_inject.v2.py` | 確認済みの本人情報フィールドの注入 |
| `word_japanese_identity_retry.v2.py` | `word_japanese_identity_retry.v2.py` | 日本語の本人情報の再試行の準備 |
| `prepare_japanese_name_retry.py` | `word_japanese_name_retry.v2.py` | 日本語の氏名の再試行の準備 |
| `prepare_chinese_english_identity_retry.py` | `word_chinese_english_identity_retry.v2.py` | 中英の本人情報の再試行の準備 |
| `stage_detected_multilingual_parser_results.py` | `word_multilingual_parser_stage.v2.py` | 多言語の結果のステージング |
| `stage_complete_english_parser_results.py` | `word_english_parser_stage.v2.py` | 英語の結果のステージング |
| `stage_strong_chinese_resume_candidates.py` | `word_strong_candidate_stage.v2.py` | 中国語の候補の絞り込み |
| `build_staged_audit_input.py` | `word_staged_audit_input.v2.py` | 監査入力の構築 |
| `repair_chinese_from_source_audit.py` | `word_chinese_source_repair.v2.py` | 中国語の原文監査に基づく修復 |
| `stage_unique_name_formal_reuse.py` | `word_unique_name_reuse_stage.v2.py` | 唯一の氏名による過去分の再利用のステージング |
| `stage_multilingual_complete_v1_matches.py` | `word_multilingual_v1_match_stage.v2.py` | 多言語の過去分との照合のステージング |
| `repair_nonchinese_complete_v1.py` | `word_nonchinese_v1_repair.v2.py` | 中国語以外の過去の候補の修復 |
| `defer_difficult_review_items.py` | `word_difficult_review_defer.v2.py` | 難しい項目の人手処理への持ち越し |
| `refresh_pending_ocr_folder.py` | `word_ocr_folder_refresh.v2.py` | OCR ディレクトリの更新 |
| `report_batch_documents_without_json.py` | `word_batch_without_json_report.v2.py` | JSON が欠けているバッチの突き合わせ |
| `terminalize_invalid_unknown_jsons.py` | `word_invalid_unknown_terminalize.v2.py` | unknown の無効な項目の終了状態 |
| `finalize_failed1_batch.py` | `word_failed_batch_finalize.v2.py` | failed バッチの締め |

## XLS 専用のコード

| 元のファイル | v2 ファイル | 役割 |
|---|---|---|
| `build_xls_conversion_map.py` | `xls_conversion_map.v2.py` | XLS 元ファイルのマップ作成 |
| `process_xls_to_html.py` | `process_xls_to_html.py` | XLS → 意味付き HTML の主変換 |
| `process_xls_html_to_json.py` | `xls_to_html_to_json.v2.py` | XLS 意味付き HTML → JSON の主解析 |
| `audit_xls_all_fields.py` | `xls_field_audit.v2.py` | XLS のフィールドごとの DOM 監査 |
| `audit_xls_html_json.py` | `xls_html_json_audit.v2.py` | XLS の HTML/JSON 監査 |
| `audit_xls_json_outputs.py` | `xls_json_audit.v2.py` | XLS の JSON 出力の監査 |
| `audit_xls_source_html_json.py` | `xls_source_html_json_audit.v2.py` | XLS の元ファイル／HTML／JSON の監査 |
| `bidirectional_review_xls_jsons.py` | `xls_bidirectional_review.v2.py` | XLS と complete-v1 の双方向の確認 |
| `rebuild_xls_report.py` | `xls_report_rebuild.v2.py` | XLS の総合レポートの再構築 |
| `reprocess_side_by_side_xls.py` | `xls_side_by_side_reprocess.v2.py` | XLS の左右二言語レイアウト専用の再実行 |
| `reprocess_xls_incremental.py` | `xls_incremental_reprocess.v2.py` | XLS の異常項目の差分再実行 |
| `normalize_existing_xls_jsons.py` | `xls_json_normalize.v2.py` | 過去の XLS JSON の正規化 |
| `repair_existing_xls_dom_labels.py` | `xls_dom_repair.v2.py` | XLS の DOM ラベルの修復 |

## Word/XLS 共通のコード

| 元のファイル | v2 ファイル | 役割 |
|---|---|---|
| `process_word_to_html.py` | `c_resume_html_dom_common.v2.py` | 共通の意味付き HTML/DOM の基本機能のスナップショット |
| `process_word_html_to_json.py` | `c_resume_html_to_json_common.v2.py` | 共通の HTML → complete-v1 の基本解析のスナップショット |
| `reuse_complete_v1_jsons.py` | `reuse_complete_v1_jsons.py` | complete-v1 の構造検証と再利用ツール |
| `classify_passed_html_by_language.py` | `classify_passed_html_by_language.py` | 言語検出とディレクトリ分類 |
| `audit_chinese_json_against_sources.py` | `audit_chinese_json_against_sources.py` | 元ファイルに対するフィールドごとの証拠監査 |
| `audit_nonchinese_json_against_sources.py` | `c_resume_nonchinese_source_audit.v2.py` | 中国語以外の元ファイルの監査 |
| `promote_audited_chinese_json.py` | `c_resume_json_promote.v2.py` | 監査に合格した JSON の昇格 |
| `promote_audited_nonchinese_json.py` | `c_resume_nonchinese_promote.v2.py` | 中国語以外の JSON の昇格 |
| `finalize_promoted_sources.py` | `c_resume_source_finalize.v2.py` | 元ファイルのパスの登録と HTML の整理 |
| `build_global_docs_progress.py` | `c_resume_global_progress.v2.py` | 元ファイルのパス単位の全体進捗 |
| `stage_documents_for_user_ocr.py` | `c_resume_ocr_stage.v2.py` | 人手 OCR 用ファイルのステージング |
| `normalize_and_validate_user_ocr_jsons.py` | `c_resume_ocr_normalize.v2.py` | 人手 OCR JSON の正規化と検証 |
| `finalize_user_ocr_jsons.py` | `c_resume_ocr_finalize.v2.py` | 人手 OCR JSON の正式な登録 |
| `stage_unknown_documents.py` | `c_resume_unknown_stage.v2.py` | unknown/failed ファイルのステージング |
| `mark_conversion_terminal.py` | `c_resume_terminal_status.v2.py` | 元ファイルの終了状態の登録 |
| `terminalize_obvious_nonresume_review.py` | `c_resume_nonresume_terminalize.v2.py` | 明確な履歴書でないものの終了処理 |
| `terminalize_unusable_passed_chinese.py` | `c_resume_invalid_terminalize.v2.py` | 無効な履歴書の終了処理 |

## 共通クラスのスナップショット

これらのファイルはクラス名で命名しています。元の場所 `python/resume_importer/` 配下の実装もそのまま残しています。

| 元のファイル | v2 ファイル | 主なクラス |
|---|---|---|
| `resume_importer/classifier.py` | `document_classifier.v2.py` | `Classification`、`DocumentClassifier` |
| `resume_importer/codex_gemini_html_schema_parser.py` | `codex_gemini_html_schema_parser.v2.py` | `CodexGeminiHtmlSchemaParser` |
| `resume_importer/structured_parser.py` | `structured_resume_parser.v2.py` | `StructuredResumeParser` |
| `resume_importer/extractors.py` | `c_resume_text_extractor.v2.py` | `ExtractionError`、`ResumeTextExtractor` |
| `resume_importer/universal_schema_parser.py` | `universal_schema_parser.v2.py` | `UniversalSchemaParser` |
| `resume_importer/preread/reader_base.py` | `format_reader_base.v2.py` | `BaseFormatReader` |

## PDF 専用のコード

| 元のファイル | v2 ファイル | 役割 |
|---|---|---|
| `process_pdf_to_html.py` | `pdf_to_html.v2.py` | PDF → 意味付き HTML |
| `process_pdf_html_to_json.py` | `pdf_to_html_to_json.v2.py` | 意味付き HTML → JSON |
| `validate_and_repair_pdf_json.py` | `pdf_json_validate.v2.py` | 基本的な JSON の検証と修復 |
| `strict_validate_and_repair_pdf_json.py` | `pdf_json_strict_validate.v2.py` | 厳密な意味の検証と修復 |
| `audit_pdf_json_against_sources.py` | `pdf_source_audit.v2.py` | PDF/HTML/JSON の元ファイルの証拠監査 |
| `parallel_pdf_to_html.py` | `pdf_parallel_to_html.v2.py` | PDF → HTML の並列変換 |
| `convert_pdf_report.py` | `pdf_conversion_map.v2.py` | PDF 元ファイル一覧とマップの作成 |
| `merge_pdf_conversion_reports.py` | `pdf_conversion_report_merge.v2.py` | PDF 変換レポートの統合 |
| `incremental_source_repair.py` | `pdf_source_repair.v2.py` | 元ファイルの証拠に基づく差分修復 |
| 新規 | `pdf_incremental_guard.v2.py` | ハッシュのスナップショット、問題台帳、合格した候補の安全な昇格 |
| 新規 | `pdf_metadata_leak_repair.v2.py` | `section-profile/evidence` やシリアライズの区切り文字によるフィールド汚染の専用差分修復 |
| `pdfs_to_complete.py` | `pdf_legacy_to_complete.v2.py` | 旧版の PDF から complete JSON への直接変換 |
| `resume_importer/preread/pdf_reader.py` | `pdf_format_reader.v2.py` | `PdfFormatReader` クラスの実装 |
| `jsons_to_complete.py` | `jsons_to_complete.py` | 旧版 complete JSON スキーマの互換ツール |

## 今後の取り決め

1. 元のファイルは削除も上書きもせず、過去の基準として残す。
2. PDF→HTML→JSON の主な流れと、その検証・監査・修復・バッチ処理のコードは、すべて `pdf_*.v2.py` を使う。`pdf_*_v2.py` やバージョン番号のない PDF 実装は新たに追加しない。
3. これらの表の左の列にあるバージョン番号のないファイルは、読み取り専用の V1 の過去の基準にすぎず、現行の入口ではなく、V2 の主な流れから参照してはならない。
4. 今後ロジックをリファクタリングするときは、`word_to_html_to_json.v2.py`、`xls_to_html_to_json.v2.py`、`pdf_to_html.v2.py`、`pdf_to_html_to_json.v2.py` と共通の v2 モジュールを新しい基準とする。
5. `.v2.py` ファイルを再利用する必要があるときは、実行時にファイルパスで読み込む。通常の `import` のためだけに同じ内容の `_v2.py` をもう 1 つコピーしてはならない。

## 切り出した共通の V2 API

| V2 API ファイル | 現在の出所 | 再利用できるインターフェース |
|---|---|---|
| `c_web_zhilian_rules.v2.py` / `c_web_zhilian_rules_v2.py` | `run_zhilian_html_to_json.py` | 求職希望、職歴、学歴、資格、言語、スキルの解析 |
| `c_web_normalizers.v2.py` / `c_web_normalizers_v2.py` | `run_web_html_to_json.py` | 学歴、職歴、資格、言語、研修、プロジェクト、コミュニケーションの正規化 |
| `c_web_text_rules.v2.py` / `c_web_text_rules_v2.py` | `run_chinese_english_html_to_json.py` | プレーンテキスト、DOM の要約、日付の解析 |
| `c_liepin_legacy_adapter.v2.py` / `c_liepin_legacy_adapter_v2.py` | `run_liepin_html_to_json.py` | 猎聘 HTML の読み取り、プレーンテキスト、レコードの構築 |

このうち、ドット付きのファイルは人手で照合するための入口で、アンダースコア付きの `_v2.py` ファイルは Python から import できる実装の入口です。これらの API は現時点ではまだ V1 の関数への明示的な移行用の転送で、今後関数本体を移したときもインターフェースは変えません。


## 公開に向けた整理で取り除いた重複スクリプト

次のスクリプトは、右側に残したスクリプトと内容が完全に同一で、リポジトリの整理時に削除しました（ドキュメント中のコマンドも残した名前に合わせて修正済みです）：

| 削除したもの | 残したもの |
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

次の 6 ファイルは `resume_importer/` パッケージ内のモジュールと同一内容のコピー（またはすでに存在しないサブパッケージの残骸）で、どのスクリプトからも参照されておらず、整理時に削除しました。対応関係：

| 削除したもの | 同等のもの |
|---|---|
| `c_resume_text_extractor.v2.py` | `resume_importer/extractors.py` |
| `codex_gemini_html_schema_parser.v2.py` | `resume_importer/codex_gemini_html_schema_parser.py` |
| `document_classifier.v2.py` | `resume_importer/classifier.py` |
| `structured_resume_parser.v2.py` | `resume_importer/structured_parser.py` |
| `universal_schema_parser.v2.py` | `resume_importer/universal_schema_parser.py` |
| `format_reader_base.v2.py` | （旧 `resume_importer/parsers/` サブパッケージの残骸。単独では実行できない） |
