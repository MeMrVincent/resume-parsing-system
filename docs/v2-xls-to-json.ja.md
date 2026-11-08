# XLS → JSON 処理フローの説明

[English](v2-xls-to-json.md) | [简体中文](v2-xls-to-json.cn.md) | **日本語**

> このドキュメントは V2（word/xls/pdf/html → JSON）の流れを説明します。ディレクトリの既定値はルートの `config.example.json` を参照してください。本文中の `<プロジェクトルート>` は config の project_root のことです。統合した重複スクリプトは [`v2-name-mapping.ja.md`](v2-name-mapping.ja.md) の末尾にあります。

## 1. 目的と範囲

このフローは、Excel の履歴書ファイル（`.xls`、`.xlsx`）を意味付き DOM を持つ HTML に変換し、さらにその HTML から統一された履歴書 JSON に解析します。XLS は表のレイアウトの差が非常に大きいため、HTML は中間の表示用ファイルではなく、解析の事実の出所です。フィールドはまず HTML の DOM で正しく結び付けられていなければならず、JSON はそれらのノードを読み取って正規化するだけです。

このフローが重点的に扱うもの：

- 中国語、日本語、英語の履歴書と、中日・中英の二言語履歴書；
- 横向き、縦向き、混在した向きの Excel の表；
- 左右に並んだ 2 つの言語の履歴書；
- 氏名、連絡先、基本情報、求職希望、職歴、学歴、資格、言語、スキル、プロジェクト、自己評価；
- 元ファイルの取得時刻、元ファイルのパス、HTML のパス、JSON のパスの追跡できる記録；
- HTML、JSON、元の XLS の三者間のフィールドごとの検証。

元の XLS は常に残します。`passed`、`review` 内の変換コピーと中間結果は片付けてよいですが、元の収集ディレクトリにある XLS を削除してはいけません。

## 2. ディレクトリとファイル

### 2.1 入力とマップ

| 内容 | パス |
| --- | --- |
| Excel 棚卸しレポート | `<プロジェクトルート>\32718文件报告.xlsx` |
| 元の XLS/XLSX | `<プロジェクトルート>\需要采集的简历文件夹` とそのサブディレクトリ |
| XLS 変換マップ | `<プロジェクトルート>\complete-transfered-htmls\xls\xls_conversion_map.json` |
| HTML 変換の集計 | `<プロジェクトルート>\complete-transfered-htmls\xls\xls_conversion_summary.json` |

`xls_conversion_map.json` は元ファイル単位のメインインデックスです。各レコードには、少なくとも次が含まれます：

```json
{
  "source_path": "元の XLS の絶対パス",
  "filename": "棚卸しレポート上のファイル名",
  "download_date": "元ファイルの取得時刻",
  "html_path": "生成した HTML のパス",
  "phone": "元の表から確認した携帯番号",
  "email": "元の表から確認したメール",
  "status": "passed / needs_review / not_resume / failed",
  "language_folder": "中文 / 日文 / 中日文 / 中英文 ...",
  "languages": ["zh", "en"],
  "resume_count": 1,
  "validation": {}
}
```

（`language_folder` の値は実際のディレクトリ名です：`中文` 中国語、`日文` 日本語、`中日文` 中日、`中英文` 中英。）

### 2.2 HTML の作業ディレクトリ

```text
<プロジェクトルート>\complete-transfered-htmls\xls\passed
<プロジェクトルート>\complete-transfered-htmls\xls\review
```

連絡先として携帯番号かメールの少なくとも一方がある XLS は、通常 `passed` に入ります。確認できる連絡先がない、有効な履歴書にならない、または変換に失敗したファイルは `review`、`not_resume`、`failed` に入ります。

### 2.3 正式な JSON とレポート

```text
<プロジェクトルート>\complete-transfered-jsons\xls\中文
```

現在の中国語 XLS JSON のメインレポートと監査レポートは、このディレクトリにあります：

```text
_xls_html_to_json_v3_report.json
_xls_html_to_json_v3_post_audit.json
_xls_side_by_side_reprocess_report.json
_xls_incremental_reprocess_report.json
_xls_html_to_json_v3_bidirectional_review.json
```

JSON のファイル名は次の形式です：

```text
氏名_携帯番号.json
氏名_メール.json
氏名_无联系方式.json       # 「无联系方式」＝連絡先なし
```

同名が衝突したときは、元ファイルのハッシュまたは連番を付け足します。携帯番号は、ファイル名と JSON の中でハイフンや空白などの書式が取り除かれます。明確な国際番号は国番号の区切りを残します。例：`+86-13800000004`。

## 3. 全体の流れ

```text
32718文件报告.xlsx / 元の XLS
        │
        ├─ xls_conversion_map.v2.py
        │       ↓
        │   xls_conversion_map.json
        │
        ├─ process_xls_to_html.py
        │       ↓ Excel のグリッドを読み、言語を分類し、連絡先を抽出し、意味付き HTML を生成
        │   passed/*.html または review/*.html
        │
        ├─ xls_to_html_to_json.v2.py
        │       ↓ DOM の再構築、フィールドの結び付け、言語ごとの解析、正規化、検証
        │   complete-transfered-jsons/xls/中文/*.json
        │
        ├─ xls_json_audit.v2.py
        │       ↓ JSON／HTML／マップ／連絡先／言語版の監査
        │
        ├─ xls_bidirectional_review.v2.py（必要なとき）
        │       ↓ 元ファイルのパスで complete-v1 の旧 JSON と相互にレビュー
        │
        └─ xls_report_rebuild.v2.py
                ↓
            最終的な総合レポート
```

重要な原則：先に HTML を正しくし、その後で JSON を解析します。HTML の DOM が段落に分かれていない、またはフィールドの結び付けが誤っているという問題を、JSON の抽出ルールだけを変えて覆い隠してはいけません。

## 4. 第 1 段階：XLS 元ファイル一覧の作成

### `python/v2/xls_conversion_map.v2.py`

このプログラムは `32718文件报告.xlsx` の `Excel表格 (.xls, .xlsx)` ワークシート（Excel の表）を読み、元ファイル単位のマップを作成します。履歴書の本文は解析せず、JSON も生成しません。

実行：

```powershell
cd <プロジェクトルート>
python python\xls_conversion_map.v2.py
```

棚卸しレポートが変わり、元ファイルのインデックスを作り直す必要があるときだけ実行します。日常の差分処理では、完了状態、元ファイルの取得時刻、HTML のパスを失わないよう、既存の `xls_conversion_map.json` を再利用してください。

## 5. 第 2 段階：XLS → 意味付き HTML

### `python/v2/process_xls_to_html.py`

Excel のグリッドを HTML に変換する変換器です。最新版の Word→HTML の生成器、HTML スキーマ、バージョン情報を再利用し、XLS と Word で DOM のルールが 2 通りできて食い違うのを避けます。

主な処理：

1. `xlrd` で `.xls` を、`openpyxl` で `.xlsx` を読み込む；
2. セルの行列関係、結合セル、横向き／縦向きのレイアウト、元のテキストを保持する；
3. 氏名、携帯番号、メールを識別し、「携帯番号かメールの少なくとも一方」を有効な履歴書の最低条件とする；
4. 中国語、日本語、英語、多言語の証拠を識別する；
5. 表の内容に応じて、`中文`、`日文`、`中日文`、`中英文` などの言語ディレクトリを選ぶ；
6. `resume-record`、`section`、`table`、`tr`、`td` などの DOM ノードを生成する；
7. 元ファイルのパス、HTML のパス、元ファイルの取得時刻、言語の分類、変換バージョン、基本的な検証を書き込む；
8. 現行バージョンの HTML を `passed` または `review` に置き、`xls_conversion_map.json` を更新する。

先頭 100 件の試行：

```powershell
python python\process_xls_to_html.py --limit 100
```

全件生成：

```powershell
python python\process_xls_to_html.py --limit 0
```

既存の HTML を強制的に再構築：

```powershell
python python\process_xls_to_html.py --limit 100 --force
```

既定では、すでに現行の生成器バージョンである HTML は上書きしません。DOM の再構築が必要だと確認したときだけ `--force` を使います。

## 6. HTML の意味付き DOM のルール

### 6.1 基本構造

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

パーサーは主に次の属性に依存します：

| 属性 | 役割 |
| --- | --- |
| `data-role="resume"` | 候補者の履歴書 1 件のルートノードを示す |
| `data-language-code` | `zh`、`en`、`jp` などの言語の階層を示す |
| `data-language-count` | 表に複数の言語版が含まれる可能性があるかを示す |
| `data-section-type` | `base_info`、`education_list`、`work_experiences` などの意味の区分を示す |
| `data-collection` | リスト型フィールドの集合を示す |
| `data-record-type` | 職歴、学歴、資格などの 1 件のレコードを示す |
| `data-field` | `company_name`、`school_name` など、具体的なフィールドを示す |
| `label` / `data-label-for` | フィールドの元の見出しの証拠を保持する |

（上の HTML のサンプル値、`姓名`「氏名」、`公司名称`「会社名」、`2016年09月` などは、サンプルデータとして原文のまま残しています。）

### 6.2 左右に並んだ二言語の表

左右に履歴書が 1 つずつあるときは、行全体を 1 つの言語にまとめて結び付けてはいけません。`repair_html()` の中の `split_side_by_side_bilingual_dom()` が列の範囲で分割します：左側は中国語のノードを残し、右側は英語／日本語のノードとして複製し、それぞれに `data-language-code` を設定します。

そのため、次のような元の表は 2 つの言語の階層になります：

```text
左：姓名 张三 / 工作经验 / 教育经历   （氏名 張三／職歴／学歴）
右：Name Zhang San / Work Experience / Education Background
```

最終的な JSON は、`structured_data.resumes` に 2 つの版を保持しなければなりません。翻訳後の氏名も保持する必要があります。例：中国語 `张三`、英語 `Zhang San`。最初の言語の氏名ですべての言語を上書きしてはいけません。

### 6.3 見出しのデモ情報

Excel の上部によくある、デモ用の見出しや候補者フィールドの説明、例えば次のようなもの：

```text
2014 男 1960 54 女 独身子なし 月収 年収 ネイティブ...
語学レベル 日本語 英語 中国語 上海語
```

これらはテンプレートのデモで、候補者のデータではありません。DOM の結び付けの段階で取り除くか無視し、基本情報、言語のレコード、資格、職歴を生成してはいけません。

## 7. 第 3 段階：HTML → JSON の解析

### `python/v2/xls_to_html_to_json.v2.py`

現在の XLS→JSON の新しい入口です。古い Word の解析メインフローには手を加えず、Word の HTML スキーマ、日付の正規化、リスト構造、共通の検証を再利用して、XLS 専用の DOM 修復を加えています。

典型的な全件コマンド：

```powershell
python python\xls_to_html_to_json.v2.py `
  --map <プロジェクトルート>\complete-transfered-htmls\xls\xls_conversion_map.json `
  --output-dir <プロジェクトルート>\complete-transfered-jsons\xls\中文 `
  --passed-dir <プロジェクトルート>\complete-transfered-htmls\xls\passed `
  --review-dir <プロジェクトルート>\complete-transfered-htmls\xls\review
```

先頭 100 件の試行：

```powershell
python python\xls_to_html_to_json.v2.py `
  --map <プロジェクトルート>\complete-transfered-htmls\xls\xls_conversion_map.json `
  --output-dir <プロジェクトルート>\complete-transfered-jsons\xls\中文 `
  --passed-dir <プロジェクトルート>\complete-transfered-htmls\xls\passed `
  --review-dir <プロジェクトルート>\complete-transfered-htmls\xls\review `
  --limit 100
```

### 7.1 `process_row()` の実際の呼び出し順序

元の XLS 1 件ごとに、`process_row()` は大まかに次の順序で実行します：

1. `process_xls_to_html.py` の `convert_single_excel_detailed()` を呼び出して、現行の HTML を再生成または取得する；
2. `repair_html()` を実行し、意味の区分とフィールドのノードを補う；
3. 誤った氏名、誤った連絡先、日付と会社の結び付けを整理する；
4. `parse_html_record()` を呼び出し、言語の階層ごとに基本情報とリストを解析する；
5. DOM で明確に結び付けられている職歴、学歴、言語、PR、資格のノードを統合する；
6. 左右に並んだ言語ごとに氏名を修復し、中国語の氏名が英語／日本語の氏名を上書きしないようにする；
7. 見出しのデモ、住所・戸籍・政治的な所属の値への混入、日付の会社名への混入などの不正な値を取り除く；
8. インターン、アルバイト、学生の実践、サークル、チーム、活動などの、正式でない資格の項目を除外する；
9. 日付に基づき、学歴と職歴を新しい順から古い順に整える；
10. 携帯番号、メール、日付、ファイル名を正規化する；
11. 修復後の完全な HTML を `raw_text` に書き込む；
12. `source.html_path`、`source.html_filename`、`source.source_landing_time` を JSON に書き込む；
13. `valid_rule_issues()` を実行し、成功した項目は正式な中国語 JSON ディレクトリに書き込み、問題のある項目は `needs_review` とマークする。

### 7.2 現在再利用している中核モジュール

- `process_xls_to_html.py`：Excel グリッドの読み込みと HTML 生成；
- `c_resume_html_to_json_common.v2.py`：HTML の基本解析、日付、氏名、トップレベルのスナップショット、リストのスキーマ；
- `reuse_complete_v1_jsons.py`：共通の `validate_json()`；
- `c_resume_html_dom_common.v2.py`：HTML のバージョン、整理、テキストのツール；
- `classify_passed_html_by_language.py`：言語の証拠とディレクトリの分類。

## 8. JSON の構造とフィールドのルール

正式な JSON の中核となる構造は次のとおりです：

```json
{
  "source": {
    "original_path": "元の XLS の絶対パス",
    "html_path": "最終的な HTML の絶対パス",
    "html_filename": "HTML のファイル名",
    "source_landing_time": "元ファイルの取得時刻",
    "resume_index": 1,
    "resume_count": 1
  },
  "dates": {
    "resume_download_date": "元ファイルの取得時刻",
    "resume_updated_date": "履歴書の更新時刻",
    "sys_created_date": "システムでの作成時刻",
    "sys_updated_date": "システムでの更新時刻"
  },
  "structured_data": {
    "base_info": {},
    "expected_info": {},
    "current_info": {},
    "education_info": {},
    "resumes": []
  },
  "raw_text": "修復後の HTML のテキストのスナップショット"
}
```

`resumes` の各言語版には次が含まれます：

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

フィールドの判断は「値があれば合格」ではなく、「値があり、元の HTML に証拠があり、フィールドの型が正当で、見出しやデモが混入していない」ものだけが合格です。

### 連絡先

- 携帯番号かメールの少なくとも一方があって初めて、有効な履歴書の候補になる；
- 上部のプラットフォームの連絡先は、元の HTML で候補者のレコードと対応付けられる場合にだけ使う；
- 携帯番号は、途中のハイフン、空白、括弧を取り除く；
- 国際番号は国番号を残す。例：`+81-8012345678`；
- 連絡先を、住所、政治的な所属、テンプレートの見出しで上書きしてはならない。

### 学歴と職歴

学歴は「時期、学校、専攻、学位」で、職歴は「時期、会社、会社の業界・性質、部署、職種、仕事内容、退職理由」などで結び付けます。学歴と職歴は既定で、終了時期または開始時期に基づき新しい順から古い順に並べます。

インターン、学生会・サークルの活動、アルバイト、学内の実践など、正式な職歴と関係のない内容は、元ファイルがそれを正式な職歴として明確に扱い、かつ業務ルールを満たす場合を除き、正式な職歴や資格のリストに入れません。

### 資格、言語、スキル

資格には、資格としての意味と元の文章の証拠が必要です。言語のデモ、スキルのタグ、ソフトウェア名、学内の活動名を資格と取り違えてはいけません。言語の版と言語能力のレベルは別々に保存し、言語の表の横向き／縦向きのレイアウトは DOM のセルの位置に基づかなければなりません。

### `raw_text`

`raw_text` の出所は修復後の HTML のテキストであり、JSON をシリアライズしたものではありません。こうすることで、後の監査で HTML の現場に戻り、フィールドが本当に元の DOM から来たものかを判断できます。

## 9. 差分の再実行と専用の修復

### 左右に並んだ二言語のバッチ

```powershell
python python\xls_side_by_side_reprocess.v2.py
```

このスクリプトは、既存の XLS JSON と HTML を走査し、`data-language-count="2"`、`data-language-variants`、または左右 5 列の中英表を識別し、元ファイルのパスで重複排除したうえで `process_row()` を再実行します。レポートの書き込み先：

```text
complete-transfered-jsons\xls\中文\_xls_side_by_side_reprocess_report.json
```

主な指標：`selected_sources`、`success`、`needs_review`、`failed`、`valid_language_variants`。

### 汎用的な異常の差分処理

```powershell
python python\xls_incremental_reprocess.v2.py
```

このスクリプトは、次の異常に対して再構築します：

- 基本情報にテンプレートの見出しが現れている；
- 職歴が空なのに、HTML には職歴の意味ノードがある；
- 二言語の HTML に、英語／日本語の言語ノードが欠けている；
- 学歴が、見出しの長いテキストのままになっている；
- 自己評価の見出しが本文を繰り返している；
- 氏名や連絡先が明らかにおかしい。

レポートの書き込み先：

```text
complete-transfered-jsons\xls\中文\_xls_incremental_reprocess_report.json
```

### `complete-v1` との相互レビュー

```powershell
python python\xls_bidirectional_review.v2.py
```

この段階では、`source.original_path` で `<プロジェクトルート>\complete-v1` 内の過去の JSON と厳密に照合します。過去の JSON は候補の参考にしかなりません。あるフィールドは、旧 JSON のほうが完全で、元の HTML に証拠があり、プレースホルダーがない場合にだけ統合できます。氏名が同じというだけで、現在の元ファイルの解析結果を上書きしてはいけません。

レポートの書き込み先：

```text
complete-transfered-jsons\xls\中文\_xls_html_to_json_v3_bidirectional_review.json
```

## 10. 検証とレポート

### 基本的な JSON 監査

```powershell
python python\xls_json_audit.v2.py
```

この監査は 1 件ずつ次を検査します：

- JSON が読み込めるか；
- 元の XLS がマップで見つかるか；
- HTML が存在するか；
- 氏名と連絡先に証拠があるか；
- 言語版が妥当か；
- 職歴、学歴、資格、言語などのリストが正当な構造か；
- 日付と会社名がずれていないか；
- JSON と HTML の主なフィールドが一致するか。

出力：

```text
complete-transfered-jsons\xls\中文\_xls_html_to_json_v3_post_audit.json
```

### 厳密なフィールド監査

より細かい DOM→JSON の突き合わせが必要なときに使います：

```powershell
python python\xls_field_audit.v2.py
```

このプログラムは、言語ごとに HTML の `data-field` を集め、JSON の基本フィールドとリストのフィールドと 1 項目ずつ比較します。日付は表示形式の違いを許容しますが、年・月・会社・学校のずれは許容しません。

### 総合レポートの再構築

```powershell
python python\xls_report_rebuild.v2.py
```

最新の監査結果に基づいて、次を再構築します：

```text
_xls_html_to_json_v3_report.json
```

総合レポートの `total` はマップのレコード数であり、JSON の件数とは等しくありません。`not_resume` には、連絡先がないもの、テンプレート、求人の説明、会社の資料など、履歴書 JSON に入れるべきでないレコードが含まれます。

## 11. 推奨する操作の順序

1. 元の XLS が収集ディレクトリにまだあることを確認し、`xls_conversion_map.json` をバックアップする。
2. 棚卸しレポートが変わったときは `xls_conversion_map.v2.py` を実行する。
3. まず小さなバッチで `process_xls_to_html.py --limit 100` を実行し、HTML の DOM を確認する。
4. DOM の言語、section、record、data-field が正しいことを確認してから、XLS→JSON を実行する。
5. まず 100 件の JSON を出力し、元の XLS、HTML、JSON の三者が一致しているかを確認する。
6. `xls_json_audit.v2.py` を実行し、監査で見つかった問題を修復する。
7. 左右に並んだ二言語のテンプレートには `xls_side_by_side_reprocess.v2.py` を実行する。
8. 残りの異常には `xls_incremental_reprocess.v2.py` を実行する。
9. 必要なら、`complete-v1` と元ファイルのパス単位で双方向にレビューする。
10. 再度、全件の監査と `xls_report_rebuild.v2.py` を実行する。
11. 監査に合格したことを確認してから、結果を下流のシステムに渡す。

## 12. よくある問題と対処

### JSON に値はあるが、値が明らかに不正

まず、HTML が見出し・日付・会社・内容を誤った `data-field` に結び付けていないかを確認します。DOM が誤っているなら、`repair_html()` や生成段階の結び付けを修正し、JSON の段階で文字列を継ぎ合わせるだけで済ませてはいけません。

### 中国語と英語が同じ `resume` に混在している

`data-language-code`、`data-language-count`、`data-language-variants`、そして左右の表の列の範囲を確認します。`xls_side_by_side_reprocess.v2.py` で DOM を再生成し、各言語が独立した section を持つようにします。

### 職歴が空

HTML の `work_experiences` section に、`company_name`、日付、`position_responsibilities` のノードがあるかを確認します。元の表が正式な経歴をプロジェクトの見出しの中に置いている場合、`bind_project_as_work_when_work_empty()` が、会社・時期・内容を確認したうえで正式な職歴のノードを補います。

### 資格にインターンやサークル活動が現れる

テンプレートのデモや学内の活動が誤って結び付けられたものです。`certificate_list` と対応する HTML のノードを確認し、現行の `sanitize_record()` のルールで、インターン、アルバイト、サークル、チーム、活動など資格でない内容を取り除きます。

### 監査には合格したが、フィールドのずれがまだ心配

`valid` だけを見てはいけません。対応する元の XLS、HTML、JSON を開き、氏名、連絡先、学歴、職歴、資格、言語、PR をフィールドごとに突き合わせます。必要なら `xls_field_audit.v2.py` と `xls_bidirectional_review.v2.py` を実行してください。

## 13. バージョンと保守の取り決め

- XLS の HTML 生成器のバージョンは、`process_xls_to_html.py` が再利用する Word 生成器のバージョンである；
- 現在の XLS ルールのバージョンは `xls-word-dom-3-language` と記録されている；
- JSON 解析の入口は `python/v2/xls_to_html_to_json.v2.py` に固定する；
- フィールドを追加するときは、まず DOM の結び付けとフィールドの別名を修正し、その後で JSON の正規化を修正する；
- DOM のルールを変更したら、少なくとも中国語 1 件、日本語 1 件、中英／中日の左右並びのサンプル 1 件を再実行する；
- 一括で再実行した後は、必ず全件の監査を実行し、専用レポートを残す；
- 元の XLS、元ファイルの取得時刻、元ファイルのパス、HTML のパスは、後で照合するための最小限の追跡情報であり、削除も上書きもしてはならない。

## 14. v2 のファイル命名と共通モジュール

元の XLS スクリプトはすべて残しています。新たに追加した XLS カテゴリには、一貫して `xls_` 接頭辞を使います：

| 元のスクリプト | v2 対照ファイル |
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

Word/XLS 共通の機能には、一貫して `c_` 接頭辞を使います。例：

```text
reuse_complete_v1_jsons.py
classify_passed_html_by_language.py
audit_chinese_json_against_sources.py
c_resume_html_dom_common.v2.py
c_resume_html_to_json_common.v2.py
```

完全なファイルの対応表は [`v2-name-mapping.ja.md`](v2-name-mapping.ja.md) を参照してください。ドット付きの `.v2.py` ファイルは、名称の照合とコマンドラインの入口に使うものです。Python から `import` する必要があるときは、対応する正当なモジュール名の `_v2.py` を使います。

XLS のメインフローは、当面は古い入口を直接置き換えません。v2 のファイルは、まず動作が同じ対照用のコピーとして置き、名前を変えるだけでフローが変わってしまうのを避けます。共通関数の移行と回帰検証が終わった後で、本番の呼び出しを切り替えます。
