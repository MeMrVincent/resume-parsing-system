# コード索引

[English](CODE_INDEX.md) | [简体中文](CODE_INDEX.cn.md) | **日本語**

`python/` 配下の各ファイルのモジュール説明から自動生成しています。説明が空のものは、そのスクリプトにモジュール説明がないことを示します。

## common：共通モジュールとツール（2 ファイル）

| ファイル | 説明 |
|---|---|
| `check_code.py` | check_code.py —— python/ 配下のすべてのコード（common、v2、v3）を静的に検査する：コンパイルと解析だけを行い、スクリプトは一切実行しない。 |
| `rc_config.py` | rc_config.py —— プロジェクト共通の設定の読み込み（common）。 |

## v3：統合／解析／監査／対応付け（Claude）（28 ファイル）

| ファイル | 説明 |
|---|---|
| `claude_align_assemble.v3.py` |  |
| `claude_align_auto.v3.py` |  |
| `claude_align_check.v3.py` |  |
| `claude_align_mkbatches.v3.py` |  |
| `claude_align_mktasks.v3.py` |  |
| `claude_merge.v3.py` | claude_merge.v3.py —— V2 / V1 の相互照合と統合：携帯番号またはメールで同一人物を判定し、1 人 1 ファイルの JSON（単一言語または多言語）にする。 |
| `claude_merge_audit.v3.py` | claude_merge_audit.v3.py —— merge v3 の出力に対する独立した検収（読み取り専用）。 |
| `claude_merge_checks.v3.py` | claude_merge_checks.v3.py —— 統合後の JSON の構造とフィールドの検証。 |
| `claude_merge_common.v3.py` | claude_merge_common.v3.py —— merge v3 の共通モジュール：フィールド仕様、連絡先・日付・名称の正規化、言語判定、スナップショットと raw_text の再構築。 |
| `claude_merge_manual.v3.py` | 原文と 1 件ずつ照合して確認した後の人手の決定（manual_decisions.json）を、統合時にコピーへ適用する。 |
| `claude_merge_normalize.v3.py` | claude_merge_normalize.v3.py —— 統合の後、フィールド検査の前に行う「フィールドの振り分けと整理」。 |
| `claude_name_fix.v3.py` | claude_name_fix.v3.py —— 氏名を原文と照合する（すべてのテンプレートの再解析の後に実行し、結果は修復コピーの最後の層になる）。 |
| `claude_pack_sources.v3.py` | claude_pack_sources.v3.py —— 「原本照合パーサー」に必要なすべての資料をパックする（読み取り専用で、元のファイルは一切変更しない）。 |
| `claude_parse_51job.v3.py` | claude_parse_51job.v3.py —— 前程無憂（51job）からエクスポートした履歴書の新しいパーサー（猎聘の同種のレイアウトもフォールバックとして識別する）。 |
| `claude_parse_cn_platform.v3.py` | claude_parse_cn_platform.v3.py —— 中国の求人プラットフォーム（主に智聯招聘）からエクスポートした履歴書の新しいパーサー。 |
| `claude_parse_en.v3.py` | claude_parse_en.v3.py —— 英語の履歴書（CV / Resume）のパーサー。 |
| `claude_parse_jp.v3.py` | claude_parse_jp.v3.py —— 日本語の履歴書（履歴書／職務経歴書／紐培などの推薦票の日本語版／51job 日本語版／xls の日本語表）の新しいパーサー。 |
| `claude_parse_liepin.v3.py` | claude_parse_liepin.v3.py —— 猎聘からエクスポートした履歴書のパーサー。 |
| `claude_parse_zh_free.v3.py` | claude_parse_zh_free.v3.py —— 中国語の自由形式の履歴書のパーサー（フォールバック）。 |
| `claude_parse_zh_report.v3.py` | claude_parse_zh_report.v3.py —— 中国語の推薦レポート（ヘッドハンター／人材会社の「推薦レポート／候補者履歴書レポート／人材推薦票」）のパーサー。 |
| `claude_parse_zh_table.v3.py` | claude_parse_zh_table.v3.py —— 求人サイトからエクスポートした xls 履歴書表のパーサー。 |
| `claude_reparse.v3.py` | claude_reparse.v3.py —— 第 2 段階：テンプレートごとに新しいパーサーで原文から resume を作り直し、旧 JSON と原文に対して比較して、良い方に置き換える。 |
| `claude_review_book.v3.py` | 第 7 バッチ：人手による確認表。 |
| `claude_source_audit.v3.py` | claude_source_audit.v3.py —— 各入力 JSON を元のファイルに戻って項目ごとに照合し、パーサーの問題かどうかを判定して台帳を作る。 |
| `claude_source_repair.v3.py` | claude_source_repair.v3.py —— 原文に基づく修復の第 1 段階：元のファイルにあるのにパーサーが漏らした携帯番号・メール・氏名を JSON に補い戻す。 |
| `claude_source_text.v3.py` | claude_source_text.v3.py —— 元のパーサーとは独立に、元の履歴書ファイルから全文を抽出する（原文との照合用）。 |
| `claude_split_pack.v3.py` | claude_split_pack.v3.py —— 転送しやすいよう claude_pack の大きな分割ファイルを 30MB の小さな塊に分ける（.partNNN ファイルを追加するだけで、元の分割ファイルは変更しない）。 |
| `copy_to_v3.py` | copy_to_v3.py —— ある統合の実行の formal/*.json を v3_dir（既定は complete-v3）にコピーし、1 件ずつ sha256 を照合する。 |

## v2：Word / XLS / PDF / HTML → JSON（Codex）（103 ファイル）

| ファイル | 説明 |
|---|---|
| `audit_chinese_json_against_sources.py` | フィールドの帰属に従い、中国語の正式な JSON を元の Word テキストの証拠と項目ごとに比較する。 |
| `batch_clean_resume_jsons.py` | complete-transfered-jsons の全件クレンジング：履歴書でないもの・職務経験のない新卒の除去、多言語の検証、キーワードと raw_text。 |
| `c_liepin_legacy_adapter.v2.py` | 名称対照用の入口。import 可能な版は c_liepin_legacy_adapter_v2.py。 |
| `c_liepin_legacy_adapter_v2.py` | V1 の猎聘パーサーにまだ依存している最小限の互換 API。 |
| `c_resume_global_progress.v2.py` | 元ファイルのパスに基づいて、Word の変換リストと正式な JSON の全体の進捗を厳密に集計する。 |
| `c_resume_html_dom_common.v2.py` |  |
| `c_resume_html_to_json_common.v2.py` |  |
| `c_resume_invalid_terminalize.v2.py` | 人手で確認済みの passed のうち、中国語の履歴書でないもの・本人を特定できない 14 件を終了状態にする。 |
| `c_resume_json_promote.v2.py` | 二重の検証に合格した中国語のステージング JSON を、保守的に正式ディレクトリへ昇格させる。 |
| `c_resume_nonchinese_promote.v2.py` | 元ファイルの証拠による監査に合格した多言語 JSON だけを昇格させ、変換リストも同期する。 |
| `c_resume_nonchinese_source_audit.v2.py` | 元の Word と意味付き HTML の二重の証拠で、多言語のステージング JSON を監査する。 |
| `c_resume_nonresume_terminalize.v2.py` | review 内で名称が明確な、履歴書でないファイルを終了状態にする。保守的な規則で、曖昧な候補は扱わない。 |
| `c_resume_ocr_finalize.v2.py` | 利用者の OCR JSON を登録し、元のファイルのパスを復元して、正式な中国語ディレクトリへ移動する。 |
| `c_resume_ocr_normalize.v2.py` | 利用者の OCR JSON を正式なテンプレートに正規化し、構造も内容も有効な履歴書だけをステージングする。 |
| `c_resume_ocr_stage.v2.py` | 利用者の OCR が必要な元の文書を指定のディレクトリにコピーし、変換マップで OCR 待ちの印を付ける。 |
| `c_resume_source_finalize.v2.py` | 昇格した JSON を変換マップに同期し、対応する HTML を削除する。 |
| `c_resume_terminal_status.v2.py` | 人手で確認済みでそれ以上解析できない変換項目 1 件を終了状態にする。 |
| `c_resume_unknown_stage.v2.py` | 人手でも難しい、または本人を特定できない元の文書を unknown にコピーし、追跡できる一覧を生成する。 |
| `c_web_normalizers.v2.py` | 名称対照用の入口。import 可能な版は c_web_normalizers_v2.py。 |
| `c_web_normalizers_v2.py` | Web/PDF 共通の正規化 API（V2 の移行レイヤー）。 |
| `c_web_text_rules.v2.py` | 名称対照用の入口。import 可能な版は c_web_text_rules_v2.py。 |
| `c_web_text_rules_v2.py` | Web のテキスト・日付の共通 API（V2 の移行レイヤー）。 |
| `c_web_zhilian_rules.v2.py` | 名称対照用の入口。import 可能な版は c_web_zhilian_rules_v2.py。 |
| `c_web_zhilian_rules_v2.py` | 再利用できる智聯の規則 API（V2 の移行レイヤー）。 |
| `classify_passed_html_by_language.py` |  |
| `codex_word_html_json_100.py` | 分離した Word -> HTML DOM -> JSON の試行フロー。 |
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
| `process_xls_html_to_json.py` | XLS 履歴書を再構築するための独立した入口。 |
| `process_xls_to_html.py` |  |
| `reuse_complete_v1_jsons.py` |  |
| `run_chinese_english_html_to_json.py` | 中国語の主版 + 独立した英語版の HTML -> JSON 意味解析パーサー。 |
| `run_chinese_html_to_json.py` | complete-transfered-htmls\docs\中文 ディレクトリ専用の HTML -> JSON 変換パーサー。 |
| `run_liepin_html_to_json.py` | 猎聘の履歴書 HTML -> JSON 専用の変換スクリプト。 |
| `run_web_html_to_json.py` | complete-transfered-htmls\web ディレクトリ専用の HTML -> JSON 変換スクリプト。 |
| `run_zhilian_html_to_json.py` | 智聯招聘の履歴書 HTML -> JSON 専用の変換スクリプト。 |
| `web_batch_report.v2.py` | 永続的な変換マップから、Web バッチの完全なレポートを再構築する。 |
| `web_conversion_map.v2.py` | Web ソースの正本となる変換マップを作成する。 |
| `web_full_repair.v2.py` | Web 変換マップのすべてのレコードに対する、スキーマに厳密な、その場での修復。 |
| `web_full_review.v2.py` | Web 変換のコードと出力に対する、独立した読み取り専用のレビュー。 |
| `web_html_json_reconcile.v2.py` | Web の JSON 出力のすべてを、対応する HTML 風のソースと比較する。 |
| `web_html_json_repair.v2.py` | reconcile v2 が記録した問題を使って、Web の JSON ファイルを差分で修復する。 |
| `web_html_to_json.v2.py` | complete-transfered-htmls\web ディレクトリ専用の HTML -> JSON 変換スクリプト。 |
| `web_internship_boundary_recovery.v2.py` | 以前の `intern`/`International` の境界の不具合からの復旧を記録し、検証する。 |
| `web_json_audit.v2.py` | Web の HTML 風 -> JSON v2 の出力を、変換マップに照らして監査する。 |
| `web_multilingual_repair.v2.py` | Web の JSON 出力に対する、オフラインでその場の多言語修復。 |
| `web_output_organize.v2.py` | Web の JSON 出力のすべてをレビューし、名前を付け直して、1 つのディレクトリにまとめる。 |
| `word_batch_without_json_report.v2.py` | OCR/unknown のバッチのうち、どの結果 JSON にも対応付けられていない元の文書を列挙する。 |
| `word_chinese_english_identity_retry.v2.py` | 処理待ちの中英 HTML を分離してコピーし、元ファイルの証拠で確認された氏名の意味ノードを注入する。 |
| `word_chinese_japanese_html_to_json.v2.py` | 中日混在ディレクトリの HTML -> complete-v1 JSON 専用パーサー。 |
| `word_chinese_source_repair.v2.py` | 中国語の原文監査の証拠に基づいて、ステージング JSON を保守的に修復する。 |
| `word_difficult_review_defer.v2.py` | 自動 review に残った難しい項目を人手の処理キューに移し、HTML は残す。 |
| `word_english_parser_stage.v2.py` | 英語の解析結果を絞り込む：画像型の猎聘を除外し、職歴・学歴の見出しがあるのに空として解析された JSON を止める。 |
| `word_failed_batch_finalize.v2.py` | 出力のない failed1 の元ファイルを終了状態にし、無効と判定済みのバッチのコピーと結果 JSON を片付ける。 |
| `word_full_docs_repair.v2.py` |  |
| `word_html_audit_fix.v2.py` |  |
| `word_invalid_unknown_terminalize.v2.py` | 検証に失敗した unknown の JSON とそのすべての元の文書を、「無効な履歴書」の終了状態として登録する。 |
| `word_japanese_html_to_json.v2.py` | 日本語の意味付き HTML -> complete-v1 JSON のパーサー。 |
| `word_japanese_identity_retry.v2.py` | 日本語の候補ファイル名の末尾の区切り、または直接の親ディレクトリから明確な氏名を取り出し、意味ノードを補って再試行する。 |
| `word_japanese_name_retry.v2.py` | 氏名の解析に失敗した日本語の項目に、追跡できる氏名の意味ノードを補い、分離した再試行用 HTML を出力する。 |
| `word_multilingual_parser_stage.v2.py` | 本文の言語セグメントの証拠に基づいて汎用の解析結果を絞り込む。実際の言語セグメントがない結果は監査に進めない。 |
| `word_multilingual_v1_match_stage.v2.py` | 解析済みの本人情報と連絡先に基づいて、complete-v1 の中で厳密に監査できる多言語の候補をステージングする。 |
| `word_nonchinese_known_name_repair.v2.py` | 元ファイルで明確に確認された多言語 JSON の氏名を修復し、氏名 + 連絡先でファイル名を付け直す。 |
| `word_nonchinese_semantics_repair.v2.py` | 元の文章で確認された多言語候補の意味のずれを修復する。存在しない履歴書の版は作らない。 |
| `word_nonchinese_v1_repair.v2.py` | complete-v1 の多言語 JSON を差分で修復し、ステージング領域に出力して、正式な結果は上書きしない。 |
| `word_ocr_folder_refresh.v2.py` | OCR 作業ディレクトリに現在の pending_user_ocr の文書だけを残し、一覧を更新する。 |
| `word_schema_extension.v2.py` | 分離した Word -> HTML DOM -> JSON の試行フロー。 |
| `word_semantic_html_audit.v2.py` |  |
| `word_semantic_html_repair.v2.py` |  |
| `word_staged_audit_input.v2.py` | 分離した解析ディレクトリ内の JSON を、多言語の原文監査の入力にまとめる。 |
| `word_strong_candidate_stage.v2.py` | 中国語の解析ステージング領域から、保守的に昇格できる有力な履歴書の候補を選び出す。 |
| `word_to_html_to_json.v2.py` |  |
| `word_unique_name_reuse_stage.v2.py` | 元ファイルのパスにある明確な氏名と、正式ライブラリ内で唯一の氏名を突き合わせ、再利用の候補を原文監査用にステージングする。 |
| `word_verified_identity_inject.v2.py` | 人手で確認済みの意味付き HTML に、権威ある氏名ノードを注入する。 |
| `xls_bidirectional_review.v2.py` | 再構築した XLS の JSON と complete-v1 のうち、フィールドごとに良い方の値を選ぶ。 |
| `xls_conversion_map.v2.py` |  |
| `xls_dom_repair.v2.py` | 生成済みの XLS HTML に、現行の意味付き DOM のクリーンアップを適用する。 |
| `xls_field_audit.v2.py` | XLS バッチに対する、フィールドごとの厳密な DOM -> JSON 監査。 |
| `xls_html_json_audit.v2.py` | 100 行のバッチについて、XLS ソース -> 意味付き HTML -> JSON の連鎖を監査する。 |
| `xls_incremental_reprocess.v2.py` | 現在のプロファイルの DOM/JSON が明らかに不良な XLS ソースだけを再構築する。 |
| `xls_json_audit.v2.py` | 再構築したすべての XLS JSON を、ソースマップに照らして行う、実行後の厳密な監査。 |
| `xls_json_normalize.v2.py` |  |
| `xls_report_rebuild.v2.py` | 対象を絞った部分再実行の後で、XLS の完全なレポートを再構成する。 |
| `xls_side_by_side_reprocess.v2.py` | 左右に言語別の履歴書を含む XLS ファイルを、差分で再構築する。 |
| `xls_source_html_json_audit.v2.py` | XLS バッチに対する、保守的なソース -> HTML -> JSON のカバレッジ監査。 |
| `xls_to_html_to_json.v2.py` | XLS 履歴書を再構築するための独立した入口。 |

## v2/resume_importer（V1 の遺産ライブラリ）

V2 の 19 本のスクリプトは今も `import resume_importer.*`（分類器、テキスト抽出、構造化パーサーなど）しているため、v2 と一緒に `python/v2/resume_importer/` に置いています。

