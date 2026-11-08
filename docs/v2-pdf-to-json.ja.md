# PDF → JSON v2 の説明

[English](v2-pdf-to-json.md) | [简体中文](v2-pdf-to-json.cn.md) | **日本語**

> このドキュメントは V2（word/xls/pdf/html → JSON）の流れを説明します。ディレクトリの既定値はルートの `config.example.json` を参照してください。本文中の `<プロジェクトルート>` は config の project_root のことです。統合した重複スクリプトは [`v2-name-mapping.ja.md`](v2-name-mapping.ja.md) の末尾にあります。

## 1. 目的と原則

このフローは PDF の履歴書を `complete-v1` の候補者 JSON に整理し、最終的に次へ公開します：

```text
<プロジェクトルート>\complete-transfered-jsons\pdf\new
```

現在の基準は **PDF v2** です。PDF のテキスト層から直接最終 JSON を作るのではなく、次の方式を採ります：

```text
元の PDF
  + iLovePDF で変換した Word
  + PDF文档.json にあるパスと分類の説明
  + GPT／旧 JSON を参考として使用
      ↓
Word → 意味付き HTML → 元ファイルごとの JSON → 候補者ごとの統合 JSON → 意味の修復 → 二重の監査 → new へ公開
```

過去には、PDF のテキスト層から直接抽出すると、複雑な表、2 段組、日本式の履歴書、多言語の履歴書で構造の品質が低くなっていました。iLovePDF が作る Word は通常、表と段落をよく保てるため、Word を主な解析入力とします。元の PDF は、本人情報、文字、ページ数、レイアウトを確認するための根拠として常に残します。

基本原則：

1. PDF の原本が最終的な証拠であり、変更も上書きもしない。
2. Word が主な解析入力だが、Word と PDF が食い違うときは PDF で見える内容を正とする。
3. GPT の JSON と旧 JSON は参考にとどめ、無条件に元ファイルを上書きしてはならない。
4. 物理的な PDF 1 つにつき、まず元ファイルごとの JSON を 1 つ生成し、その後、候補者の本人情報で統合する。
5. 氏名が同じことは自動統合の根拠にならず、携帯番号・メールなどの強い証拠を優先する。
6. 全件の監査に合格するまでは、`new` へ公開しない。

## 2. ディレクトリの役割

### 2.1 入力と説明

```text
<プロジェクトルート>\complete-transfered-htmls\pdf\
├── input\                  元の PDF
├── word\                   iLovePDF が生成した、または人手で再変換した DOCX
└── PDF文档.json            PDF のパス、分類、人手の説明
```

- `input`：元の PDF。履歴書と少数の履歴書でないファイルを含む。
- `word`：PDF → Word の変換結果。ファイル名は人手で変更されていることがあるため、ファイル名だけで対応付けてはならない。
- `PDF文档.json`：元のパス、履歴書かどうか、候補者の説明、連絡先、HTML 名など、権威ある人手の情報。

### 2.2 JSON の参考と正式な出力

```text
<プロジェクトルート>\complete-transfered-jsons\pdf\
├── old\                    前回の低品質な成果物。参考のみ
├── gpt\                    ChatGPT で変換した、または人手で統合した参考 JSON
└── new\                    現在の正式な納品 JSON
```

- `old`：そのまま正しいデータとみなしてはならない。
- `gpt`：品質の良いものもあれば、重複、多言語の構造の違い、誤った統合があるものもある。本人情報と元ファイルの数が一致する場合にだけ使う。
- `new`：候補者単位の監査にすべて合格して初めて、アトミックに置き換える。

### 2.3 中間成果物とレポート

```text
<プロジェクトルート>\complete-transfered-htmls\pdf\
├── rebuild-work\
│   ├── pdf_rebuild_map.v2.json       正本のマップ
│   ├── html\                         Word から変換した意味付き HTML
│   ├── json-by-source\                1 つの PDF につき 1 つの JSON を置く、元ファイル単位のステージング
│   └── json-by-candidate\             候補者単位で統合したステージング
└── rebuild-reports\                   抽出、監査、統合、確認、公開のレポート
```

## 3. 現在の v2 コード

PDF のメインフローは、次の 13 の入口だけを使います：

| ファイル | 役割 |
|---|---|
| `python/v2/pdf_rebuild_map.v2.py` | PDF、Word、人手の説明、GPT、旧 JSON の正本のマップを作成する |
| `python/v2/pdf_rebuild_extract.v2.py` | Word → 意味付き HTML → 元ファイルごとの JSON |
| `python/v2/pdf_rebuild_audit.v2.py` | 元ファイルごとの JSON を、マップに対する網羅性、本人情報、構造、元ファイルのハッシュについて監査する |
| `python/v2/pdf_rebuild_merge.v2.py` | 候補者ごとに保守的に統合し、多言語の版は独立して保持する |
| `python/v2/pdf_rebuild_semantic_repair.v2.py` | フィールドのずれ、テンプレートのプレースホルダー、HTML の漏れ、重複、職歴／学歴の取り違えを取り除き、PDF の人手確認済みの上書きを読み込む |
| `python/v2/pdf_raw_text_v2.py` | Word、PDF、意味付き HTML から独立した原文の証拠を再構築し、変換ノイズを取り除いて、物理ソースごとに重複排除する |
| `python/v2/pdf_rebuild_candidate_audit.v2.py` | 候補者単位の JSON を監査し、各元ファイルがちょうど 1 回だけカバーされていることを確認する |
| `python/v2/pdf_json_strict_audit.v2.py` | 互換用の構造監査。スナップショット、日付、基本的な元ファイルの証拠を検査する |
| `python/v2/pdf_json_field_strict_audit.v2.py` | 公開のゲート：言語ごと、リストごと、フィールドごとに、プレースホルダーの値、フィールドのずれ、エンティティの取り違え、日付、連絡先、重複、元ファイルの証拠、独立した `raw_text` の完全性を検査する |
| `python/v2/pdf_rebuild_finalize.v2.py` | 監査に合格した後、`new` へアトミックに公開する |
| `python/v2/pdf_rebuild_issue_table.v2.py` | 人手で Word を再変換すべきもの・識別が難しいファイルの問題表を生成する |
| `python/v2/pdf_gpt_review_compare.v2.py` | GPT の構造の違いについて、PDF、Word、GPT、現在の JSON の四者比較を行う |
| `python/v2/pdf_gpt_review_resolve.v2.py` | 人手による確認の結論を、永続的な上書きファイルへ差分で書き込む |

次の共通コードは引き続き再利用します。これらは削除済みの古い PDF パイプラインには属しません：

- `c_resume_html_dom_common.v2.py`：Word HTML の DOM 処理。
- `c_resume_html_to_json_common.v2.py`：共通の履歴書フィールドの解析とスキーマの正規化。
- `xls_to_html_to_json.v2.py`：日本式の表形式 Word 向けの、XLS グリッド強化ルール。

## 4. 完全な実行手順

すべてのコマンドは `<プロジェクトルート>` で実行します。

### 4.1 マップの作成

```powershell
python python/v2/pdf_rebuild_map.v2.py
```

マップの段階で、PDF/Word の棚卸し、人手の分類との関連付け、同名・内容による別名の照合、GPT/old の参考との関連付け、PDF のページ数とテキスト層の分析、履歴書でないものの隔離を行います。

主なファイル：

```text
rebuild-work/pdf_rebuild_map.v2.json
rebuild-reports/pdf_word_aliases.v2.json
rebuild-reports/pdf_pilot_30.v2.json
```

### 4.2 全件抽出

```powershell
python python/v2/pdf_rebuild_extract.v2.py `
  --scope all `
  --force `
  --report complete-transfered-htmls/pdf/rebuild-reports/pdf_full_extract.v2.json
```

処理の順序：

1. 対応する DOCX を読み込む；
2. 標準の Word HTML に変換する；
3. 通常の Word か、Word の表か、日本式の表かを判定する；
4. 通常の Word は、見出し・段落・日付・エンティティのルールを使う；
5. 日本式の表は、まず XLS グリッドの意味ルールを再利用する；
6. XLS の強化が、ある言語／日付形式を安全に処理できないときは、標準の Word HTML に戻す；
7. 元ファイルごとの JSON を出力する；
8. PDF と人手の説明に基づいて、元ファイル、日付、本人情報、分類の情報を補う。

抽出の状態には次のものがあります：

- `success`：構造が明確；
- `needs_review`：元ファイルごとの解析に弱い箇所はあるが、同じ候補者の別の版や確認済みの GPT の中国語版で後から補える；
- `non_resume`：明らかに履歴書ではない；
- `failed`：読み取りまたは変換に失敗。候補者の統合に進んではならない。

### 4.3 元ファイルごとの監査

```powershell
python python/v2/pdf_rebuild_audit.v2.py `
  --report complete-transfered-htmls/pdf/rebuild-reports/pdf_full_audit.v2.json
```

処理すべき履歴書のすべてに元ファイルごとの JSON があること、余分な JSON がないこと、元ファイルの SHA-256 とパスが一致すること、本人情報と構造が最低限の要件を満たすこと、履歴書でないものが候補者データに入っていないことを確認しなければなりません。

### 4.4 候補者単位の統合

```powershell
python python/v2/pdf_rebuild_merge.v2.py --replace
```

統合のルール：

1. 携帯番号が同じ、またはメールが同じことは、統合の強い証拠である。
2. 氏名の一致は補助にすぎず、連絡先が明確に衝突するときは統合してはならない。
3. 中国語、日本語、英語、ドイツ語などは `structured_data.resumes` に別々に保存する。
4. 同じ言語では、構造が完全で出所の信頼できる版を優先し、空でないリストを単純に連結しない。
5. 複数の出所は空のフィールドを補うだけで、劣る版が既存の信頼できるフィールドを上書きしない。
6. GPT の中国語は、GPT ファイル、元ファイルの数、候補者の本人情報が一致するときにだけ有効にする。
7. 四者確認済みの GPT の修復は、`pdf_gpt_review_overrides.v2.json` から永続的に読み込む。

### 4.5 意味の修復

```powershell
python python/v2/pdf_rebuild_semantic_repair.v2.py `
  --root complete-transfered-htmls/pdf/rebuild-work/json-by-candidate `
  --apply
```

この段階では、会社／学校／職種のずれ、テンプレートの見出し、HTML の断片、重複した経歴、逆転した日付、単一ソースの多言語の誤った分割を処理します。元の PDF を目視で確認して確定した個別の事例は `rebuild-reports/pdf_semantic_overrides.v2.json` に保存され、その後の全件再実行でも再利用されます。

### 4.6 候補者のカバレッジと全フィールドの厳密な監査

```powershell
python python/v2/pdf_rebuild_candidate_audit.v2.py `
  --json-root complete-transfered-htmls/pdf/rebuild-work/json-by-candidate

python python/v2/pdf_json_field_strict_audit.v2.py `
  --json-root complete-transfered-htmls/pdf/rebuild-work/json-by-candidate
```

公開の前に次を満たさなければなりません：

- `missing_source_hashes` が空；
- `duplicate_source_hashes` が空；
- 各履歴書の元ファイルが、ちょうど 1 つの候補者 JSON にカバーされている；
- `quality:ready` が候補者の総数と等しい；
- 翻訳待ちが 0；
- GPT の構造の確認待ちが 0；
- 品質の警告が 0。
- 厳密な監査の `strict_failure_file_count`、`review_file_count`、`total_issue_count` がすべて 0。

「厳密」とは、フィールドが空でないかを検査するだけのことではありません。監査器は、マップにある PDF、Word、HTML を独立した証拠として読み直し、フィールドごとに次を検査します：

- 氏名、電話、メール、会社、学校、職種、専攻などのエンティティを原文までたどれるか；
- 学校、会社、プロジェクト、資格、言語、自己評価が誤ったリストに入っていないか；
- エンティティのフィールドに、章の見出し、テンプレートの文言、長い職務内容の文、日付が混ざっていないか；
- 日付の形式、前後関係、在職の状態、学歴の段階、列挙値が妥当か；
- 同じリストの中に、完全に重複した、または意味が重複したレコードがないか；
- 多言語の版がそれぞれの構造を保ち、対応する言語の元ファイルと一致しているか；
- トップレベルのスナップショットが中国語の主版と一致しているか；
- `raw_text` が元ファイルから独立に再構築されたか、出所ブロック・ハッシュ・長さ・テキストの網羅が正しいか；
- `WordOOXMLTable*`、OpenXML の表のマーカー、HTML の断片、C0/C1 制御文字、よくある変換の文字化けが含まれていないか。

### 4.7 公開

```powershell
python python/v2/pdf_rebuild_finalize.v2.py --replace
```

公開プログラムは、まず一時ディレクトリにコピーしてファイルごとに SHA-256 を検証し、すべて合格して初めて、次をアトミックに置き換えます：

```text
<プロジェクトルート>\complete-transfered-jsons\pdf\new
```

公開後は、ステージングディレクトリと正式ディレクトリの不一致を避けるため、正式ディレクトリで全フィールドの監査をもう一度実行しなければなりません：

```powershell
python python/v2/pdf_json_field_strict_audit.v2.py `
  --json-root complete-transfered-jsons/pdf/new `
  --report complete-transfered-htmls/pdf/rebuild-reports/pdf_json_field_strict_audit.formal.v2.json `
  --csv complete-transfered-htmls/pdf/rebuild-reports/pdf_json_field_strict_audit.formal.v2.csv
```

最後に `pdf_finalization.v2.json` も確認します。`published_count` は 419、`map_resume_records_updated` は 561 であるべきで、レポートに記録された各ファイルの SHA-256 でステージングと正式ディレクトリを比較し、ハッシュの差異は 0 でなければなりません。

## 5. 日本式の表形式の履歴書

ファイル名や内容に「日语、日文、履歴書、職務経歴書」などの印を含むファイルは、通常、表のレイアウトを使います。よくあるリスクは次のとおりです：

- 年、月、学校／会社が別々のセルに分かれている；
- 「入学」と「卒業」が 2 件の学歴として識別される；
- 学歴、職歴、資格が同じ大きな表の中にある；
- 中国語のエンティティ名と日本語の見出しが混在している；
- 1 つのファイルに履歴書と職務経歴書の両方が含まれている。

v2 の対処方針：

1. DOCX の OOXML から実際のセルグリッドを復元する；
2. Word の表を XLS 風の二次元セルに変換する；
3. XLS の横方向のフィールド、イベント行、言語レイヤーのルールを再利用する；
4. 氏名、連絡先、職歴、学歴、資格を再度結び付ける；
5. XLS による強化結果が不完全だったりルールが異常だったりする場合は、標準の Word HTML を残し、強化処理が全件バッチを止めないようにする；
6. 最終的には、PDF で見える表と照らして、項目数、日付、分類を確認する。

## 6. GPT の差異の確認

統合の後で `pdf_gpt_translation_review.v2.json` が空でない場合は、次を実行します：

```powershell
python python/v2/pdf_gpt_review_compare.v2.py
```

四者の資料は、元の PDF の全ページ、iLovePDF の Word／意味付き HTML、GPT の JSON、現在の候補者 JSON です。多言語の重複、学校を会社と取り違えたもの、プロジェクトや資格を職歴と取り違えたもの、日本式の入学・卒業の分割、複数の履歴書の誤った統合を重点的に確認します。

確認後、その結論を `pdf_gpt_review_resolve.v2.py` の `FACTS` に追加し、次を実行します：

```powershell
python python/v2/pdf_gpt_review_resolve.v2.py
python python/v2/pdf_rebuild_merge.v2.py --replace
python python/v2/pdf_rebuild_candidate_audit.v2.py
```

確認用のスクリプトは差分方式です。既存の確認記録は保持され、新しい記録は GPT ファイルのパスごとに追加または置換されるため、全件再実行しても、すでに修正した誤った構造が元に戻ることはありません。

## 7. Word を再変換する必要がある場合

次の場合は問題表に入り、人手で Word を再変換します：

- Word が空、または画像だけ；
- PDF には明らかに内容があるのに、Word のページが欠けている；
- 表の行と列が大きくずれている；
- 氏名、連絡先、主な経歴が Word で失われている；
- PDF がスキャン画像で、iLovePDF が正しく OCR していない；
- Word と PDF が同じ内容ではない。

問題表の生成：

```powershell
python python/v2/pdf_rebuild_issue_table.v2.py
```

人手で Word を差し替えた後も、PDF は変更しません。指定したファイルを差分で再抽出する例：

```powershell
python python/v2/pdf_rebuild_map.v2.py
python python/v2/pdf_rebuild_extract.v2.py `
  --filenames "再実行するファイル.pdf" `
  --force `
  --report complete-transfered-htmls/pdf/rebuild-reports/pdf_reextract_batch.v2.json `
  --merge-into-report complete-transfered-htmls/pdf/rebuild-reports/pdf_full_extract.v2.json
python python/v2/pdf_rebuild_audit.v2.py `
  --report complete-transfered-htmls/pdf/rebuild-reports/pdf_full_audit.v2.json
python python/v2/pdf_rebuild_merge.v2.py --replace
python python/v2/pdf_rebuild_semantic_repair.v2.py --apply
python python/v2/pdf_rebuild_candidate_audit.v2.py
python python/v2/pdf_json_field_strict_audit.v2.py
python python/v2/pdf_rebuild_finalize.v2.py --replace
```

## 8. JSON 構造の要件

候補者 JSON には、少なくとも `schema_version`、`record_id`、`source.source_files`、`dates`、`extraction`、`classification`、`structured_data.base_info`、`structured_data.resumes`、各経歴リスト、`raw_text`、`quality` が含まれます。

ルール：

1. `resumes[0]` は、できるだけ中国語の主版にする。
2. `expected_list`、`work_experiences`、`education_list`、`certificate_list`、`language_list`、`skills_list`、`training_list`、`project_list`、`communication_list` は、各 `structured_data.resumes[]` の内側にだけ置くことができ、メインのオブジェクトの下にこれらのリストを複製してはならない。
3. `structured_data` のトップレベルには、`base_info`、`expected_info`、`current_info`、`education_info` の 4 つの検索用スナップショットと `resumes` だけを残す。スナップショットは中国語の主版と一致させる。
4. 職歴、学歴、プロジェクト、研修は、1 区間につき 1 件とし、中身のないエンティティのレコードは削除しなければならない。
5. 構造化された値はすべて、context でのそのフィールドの定義に合っていなければならず、「値がある」というだけで合格とみなしてはならない。値は意味として妥当で、対応する元の文書までたどれなければならない。
6. 会社名、学校名、職種、専攻、プロジェクト名、資格名に原文の段落をまるごと入れてはならず、学校を会社に、会社を学校に、学内の活動を職歴にしてもならない。
7. `公司名称`（会社名）、`学校名`、`Post/Wages`、`WordOOXMLTable*` などのテンプレートや変換のプレースホルダーの値を残してはならない。
8. 高校、中等専門学校、中学校、小学校の経歴は `education_list` に入れない。大学、短大・専科、学部、修士、博士などは、context の規定に従って学位と教育の種類を対応付ける。
9. 語学試験は `language_list` に入れる。試験名またはレベルは `language_level` に書き、`language_certificate` は `有`（あり）、`无`（なし）、または空文字列だけを許す。
10. 月の精度の日付は `YYYY年MM月01日` に統一する。全角数字、漢数字の年、`YYYY～YYYY` などの書き方は標準化しなければならないが、元の文書にない月や具体的な日を作り出してはならない。「現在まで」は、終了日を空にして `status=在职`（在職）で表す。
11. 多言語の履歴書を統合した後は、すべての物理ソースが `source.source_files` と `source.merge_trace` に現れなければならず、追跡できるよう、少なくともファイル名、パス、SHA-256、言語、文書の種類を記録する。
12. `raw_text` は最終的な構造化フィールドと完全に切り離す。物理ソースごとに `===== SOURCE: ファイル名 =====` で区切り、同じ人の複数の履歴書・多言語の履歴書は、ソースごとに 1 つの `raw_text` にまとめ、ファイル名、SHA-256、本文で重複排除して、各ソースが 1 回だけ現れるようにする。
13. 1 つのソースブロックでは、Word のテキストを第一候補とする。Word が使えない場合は PDF を使い、さらに Word/PDF に欠けていて重複しない行を意味付き HTML で補う。整理してよいのは、表変換のマーカー、HTML のメタデータ、制御文字、元に戻せる変換の文字化け、確実に重複している集約行に限り、読みにくくても原本に属する内容を見た目のために削除してはならない。
14. `base_info`、職歴、学歴、プロジェクト、資格などの構造化フィールドから、`raw_text` を逆に組み立てたり補ったりしてはならない。構造化された氏名、電話番号、翻訳したエンティティがテキスト層に現れなくても、監査に通すために `raw_text` へ書き込んではならない。
15. `extraction.raw_text_source` は `canonical_deduplicated_pdf_word_html_text` に固定する。厳密な監査は PDF、Word、HTML を独立して読み直し、出所の宣言、出所ブロックの数、長さ、重複、テキストの網羅を検査する。

人手で確認した個別の修復は、次に保存します：

```text
<プロジェクトルート>\complete-transfered-htmls\pdf\rebuild-reports\pdf_semantic_overrides.v2.json
```

このファイルは言語間の調整の後で適用され、最終的な正本の上書き層です。上書きを追加するときは、次回の全件再実行で古い誤りが戻らないよう、元ファイルの根拠も同時に記録しなければなりません。

## 9. 現在の検収基準

2026-08-30 時点：

- 元の PDF：567 件；
- 履歴書：561 件；
- 履歴書でないもの：6 件；
- 候補者 JSON：419 件；
- 統合した候補者：107 件；
- 単一ソースの候補者：312 件；
- PDF/Word/HTML/GPT/旧 JSON と照合した後の永続的な上書き記録：97 件の候補者；
- 翻訳待ち：0；
- GPT の構造の確認待ち：0；
- 品質の警告：0；
- 候補者の監査：419/419 `ready`；
- 厳密な監査：419/419 `clean`、失敗 0、確認待ち 0、問題 0；
- 561 件の履歴書の元ファイルが、すべて、かつ 1 回だけカバーされている。
- ステージングディレクトリと正式な `new`：419/419 ファイルで SHA-256 が一致、ハッシュの差異 0。
- `raw_text`：出所ブロックの数と一意な元ファイルのハッシュの数が一致し、重複した出所ブロック・欠けた出所ブロック・Word/OpenXML の表のマーカー・C0/C1 制御文字がない。

検収レポート：

```text
rebuild-reports/pdf_full_extract.v2.json
rebuild-reports/pdf_full_audit.v2.json
rebuild-reports/pdf_candidate_merge.v2.json
rebuild-reports/pdf_candidate_audit.v2.json
rebuild-reports/pdf_semantic_repair.v2.json
rebuild-reports/pdf_json_strict_audit.v2.json
rebuild-reports/pdf_json_field_strict_audit.v2.json
rebuild-reports/pdf_json_field_strict_audit.v2.csv
rebuild-reports/pdf_json_field_strict_audit.formal.v2.json
rebuild-reports/pdf_json_field_strict_audit.formal.v2.csv
rebuild-reports/pdf_gpt_review_resolution.v2.csv
rebuild-reports/pdf_finalization.v2.json
```

正式な検収は `pdf_json_field_strict_audit.formal.v2.json` と `pdf_finalization.v2.json` を基準とします。前者は正式ディレクトリの 419 件の全フィールド監査で問題が 0 であることを、後者は公開した件数とファイルのハッシュが一致していることを示します。

## 10. 既知の元ファイルの制約と今後の再変換

今回の構造化 JSON はすべて公開のゲートに合格していますが、次の 2 件は Word/PDF のテキスト層に、埋め込みフォントの対応に起因する部分的な文字化けが残っているため、今後 iLovePDF で Word に変換し直すことをお勧めします：

| 候補者 JSON | 再変換を推奨する元ファイル | 説明 |
|---|---|---|
| `张三_13800000001.json` | `张三中文简历.pdf` | 中国語版だけに部分的な文字化けがある。日本語版・英語版は読める。 |
| `李四_13800000002.json` | `李四 硕士 广岛大学 化学工学.pdf` | 本文全体がフォントの対応のため文字化けしている。 |

完全なパスと現在の Word のパスは、次を参照してください：

```text
<プロジェクトルート>\complete-transfered-htmls\pdf\rebuild-reports\pdf_word_reconversion_needed.v2.md
```

この 2 件は今回の公開を妨げません。構造化フィールドは PDF、Word、ほかの言語版、人手の意味の上書きを組み合わせて修正済みで、`raw_text` は制御文字を取り除いた後の元ファイルの証拠をそのまま保持し、復元できない文字を捏造することはしません。

## 11. 今後のバージョンアップのルール

現在の v2 が、唯一有効な PDF の実装です。今後 v3 を開発するときは：

1. 現在の v2 のスクリプトを v3 としてコピーし、v2 を直接上書きしない；
2. コードファイル、`VERSION`、既定の MAP、レポートのファイル名を同時にバージョンアップする；
3. v3 は独立したステージング、または明確にバージョン付けしたレポートを使い、v2 の検収基準を汚さない；
4. まず小さなバッチで試行し、その後で全件を実行する；
5. 元ファイルのカバレッジ、候補者数、品質の状態、主要な候補者の構造を比較する；
6. v3 の全件の監査に合格して初めて、正式な `new` を置き換える；
7. バージョンアップの完了後に、旧バージョンを削除するかを決める。同名の入口を 2 セット並存させてはならない。
