# resume-parsing-system

[English](README.md) | [简体中文](README.cn.md) | **日本語**

形式がばらばらな数千件の履歴書（Word / Excel / PDF / Web HTML。中国語・日本語・英語・ドイツ語が混在）を、**1 人 1 ファイル・統一構造の JSON** に整理し、監査可能なクレンジング・統合・多言語対応付けの結果を出力します。

> 本リポジトリには**コードとドキュメントのみ**が含まれ、実在の履歴書や個人情報は一切含みません。`examples/` に登場する人物・電話番号・メールアドレス・会社はすべて架空のものです。

## 概要

```
元の履歴書ファイル ──V2──▶ 1 ファイル 1 JSON ──V3──▶ 1 人 1 JSON（監査可能）
(doc/xls/pdf/html)          (complete-v2 / v1)        (formal / needs_fix / pending_translation)
```

- **基盤と管理**（Google Antigravity 作成）：第1版の基礎コードの作成、および最終バージョンのコード整理・リファクタリング、Git プロジェクトの管理を担当。
- **V2**（`python/v2/`、Codex 作成）：Word・XLS・PDF・Web HTML を HTML に変換し、統一スキーマの JSON に解析します。複数回の監査付き。詳細は `docs/v2-*.md`。
- **V3**（`python/v3/`、Claude 作成）：携帯電話番号／メールアドレスで同一人物を判定し、V2（主）と V1（副）の JSON を 1 人 1 ファイルに統合します。多言語履歴書（中・日・英・独）は言語版ごとに項目単位で対応付けし、独立監査（30 項目）を行い、`raw_text` を固定ルールで生成します。詳細は `docs/v3-pipeline.md`。
- **common**（`python/common/`）：共通設定読み込み `rc_config.py` と静的コードチェック `check_code.py`。

## AI 共同開発について

本リポジトリの全コード、ドキュメント、およびエンジニアリング作業は、複数の AI の協調作業によって作成されました：

- **Google Antigravity**：第1版の基礎コードの作成、最終版のコード整理・リファクタリング、日英中 3 言語の国際化対応、および Git プロジェクトの管理を担当。
- **OpenAI Codex**：V2 のマルチフォーマット（Word / Excel / PDF / HTML）抽出、HTML クリーニング、および解析ルールのイテレーションを担当。
- **Anthropic Claude**：V3 の統合パイプライン設計、電話番号・メールアドレスによる同一人物判定、多言語項目の対応付けアルゴリズム、30 項目の独立監査エンジンを担当。

## ディレクトリ構成

```
resume-system/
├─ README.md  README.cn.md  README.ja.md  LICENSE  requirements.txt
├─ config.example.json        設定テンプレート（config.json にコピーして編集）
├─ python/
│  ├─ common/                 設定、静的チェック
│  ├─ v2/                     Word/XLS/PDF/HTML → JSON（resume_importer ライブラリを含む）
│  └─ v3/                     統合、解析、監査、多言語対応付け
├─ scripts/                   Windows 用ダブルクリック起動スクリプト（merge.cmd など）
├─ docs/                      ドキュメント、コード索引
├─ examples/                  架空のサンプルデータとサンプル出力
└─ repair_data/               一回限りの修復スクリプト用の個人データ（コミットしない。形式サンプルのみ）
```

## クイックスタート

1. Python 3.13 をインストールします。V3 の統合・監査は標準ライブラリのみ使用します。V2 にはサードパーティ製ライブラリが必要です：`pip install -r requirements.txt`。
2. `config.example.json` を `config.json` にコピーし、必要に応じて編集します（後述）。
3. まずサンプルデータで試します（実データは不要）：

```bash
python examples/make_examples.py
python python/v3/claude_merge.v3.py --v2-dir examples/v2 --v1-dir examples/v1 --out-root examples/out --run-id 20260101-demo
python python/v3/claude_merge_audit.v3.py --run-dir examples/out/20260101-demo --v2-dir examples/v2 --v1-dir examples/v1
```

   4 件のサンプルから、`formal` 2 件（陈思明：V2 と V1 を統合／林雅婷：中英バイリンガル）、`pending_translation` 1 件（John Smith：英語版のみで中国語の主版がない）が生成され、連絡先のない 1 件は `ledgers/no_contact_ledger` に記録されます。結果の例は `examples/output/` にあります。

4. 自分のデータで実行する場合は、V2/V1 の JSON を設定の `v2_dir`・`v1_dir` に置いてから実行します。
   - Windows：`scripts/merge.cmd` をダブルクリック（統合 → 検証用統合 → 監査）。
   - その他の OS：上記 2 つの `python` コマンド（サンプルのパスを付けなければ設定を読み込みます）。
5. 監査に合格したら（`reports/audit.json` の全チェックが 0）、`python python/v3/copy_to_v3.py` で `formal/` を `v3_dir` にコピーできます。

## 設定（config.json）

すべてのパスは 1 つの `config.json` から取得し、**ドライブ名をハードコードしません**。検索順序：環境変数 `RESUME_CONFIG` → `<プロジェクトルート>/config.json` → `<プロジェクトルート>/python/config.json`。見つからない場合は既定値を使います。コマンドライン引数は設定より優先されます。

| キー | 既定値 | 意味 |
|---|---|---|
| `project_root` | 空（自動 = `python` の 1 つ上） | プロジェクト／データのルート。環境変数 `RESUME_ROOT` でも上書き可能 |
| `source_dir` | `需要采集的简历文件夹` | 元の履歴書フォルダ（読み取り専用）。**自分のフォルダ名か絶対パスに置き換えてください** |
| `html_dir` | `complete-transfered-htmls` | V2 の中間 HTML |
| `v1_dir` / `v2_dir` | `complete-v1` / `complete-transfered-jsons` | 統合の副／主となる入力 JSON |
| `v3_dir` | `complete-v3` | 最終成果物 |
| `output_dir` | `output` | 実行出力のルート |
| `merge_out_dir` | `output/merge-v3` | 統合実行の出力 |
| `repair_dir` | `output/source-repair-v3` | 修復コピーのディレクトリ（名前が最も新しいサブディレクトリを使用） |
| `align_dir` | `claude-align` | 多言語対応付けの作業ディレクトリ |
| `python_exe` | `python` | .cmd 起動スクリプトが使うインタープリター |
| `path_map` | `{}` | 成果物 JSON に記録されたソースパス（`original_path` / `html_path`）が無効になったときの変換表：`{"旧パスの接頭辞": "新しい場所"}`。新しい場所の `{root}` はプロジェクトルート。例：`{"E:\\resume-system\\codex-transfered-htmls": "{root}/complete-transfered-htmls"}`。ファイルを探す／存在確認にだけ使い、JSON は書き換えません |
| `dir_names` | `{}` | 追加のディレクトリ名マッピング。例：`{"complete-transfered-jsons": "my-json"}`（V2 スクリプト内のハードコードされたディレクトリ名はすべてこれを通して変換されます） |

相対パスは `project_root` 基準、絶対パスはそのまま使用します。

## よく使うコマンド

| 目的 | コマンド |
|---|---|
| 統合 + 監査（Windows ダブルクリック） | `scripts/merge.cmd` |
| formal を v3_dir にコピー | `scripts/copy_to_v3.cmd` |
| 全コードの静的チェック（構文、import、ファイル名参照） | `python python/common/check_code.py` または `scripts/check_code.cmd` |

## JSON フィールド仕様

この節では V3 が出力する 1 人 1 ファイルの JSON（`formal/*.json`）を説明します。V2 が出力するファイル単位の JSON も `structured_data` は同じ構造で、その他のトップレベルオブジェクトの違いは節末に記載しています。

### 共通ルール

- **履歴書内の日付**は `YYYY年MM月DD日`（例：`2017年09月01日`）に統一し、不完全な日付は補完します（`2010/4` → `2010年04月01日`）。`resume_updated_date`・`resume_download_date` は `YYYY-MM-DD HH:MM:SS`、システム時刻は ISO 8601 です。
- **フィールドの値は原文の言語のまま**です。中国語主版の列挙値は中国語です（例：`全职` 正社員、`在职` 在職中）。下表では元の値をそのまま記載しています。
- **リストフィールドは `null` にしません**。データがなければ `[]` です。オブジェクトのスナップショット（`expected_info`・`current_info`・`education_info`）は常に全キーを持ち、欠損値は `""` です。
- 原文に根拠のある値だけを記入し、推測で補いません。

### トップレベル構造

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
  "raw_text": "<全文テキスト>",
  "quality": { ... },
  "merge_info": { ... }
}
```

| フィールド | 型 | 説明 |
|---|---|---|
| `schema_version` | string | スキーマのバージョン：V3 は `resume-merge-v3.0`、V2 は `codex-resume-json-1.0` |
| `record_id` | string | レコードの一意 ID（V3 は `merge-v3-<group_id>`、V2 は SHA-256 ハッシュ） |
| `source` | object | 元ファイル情報 |
| `dates` | object | 履歴書の日付とシステム時刻 |
| `extraction` | object | 生成処理の情報 |
| `classification` | object | 文書分類 |
| `structured_data` | object | 構造化データ（中核） |
| `raw_text` | string | プレーンテキスト全文。全文検索・キーワード照合用 |
| `quality` | object | 品質の概要 |
| `merge_info` | object | 統合情報（V3 のみ） |

### `source` 元ファイル情報

| フィールド | 型 | 説明 |
|---|---|---|
| `original_path` | string | 元の Word/PDF/XLS/HTML ファイルのパス |
| `html_path` | string | 中間 HTML のパス（空の場合あり） |
| `source_count` | number | このレコードに統合された入力 JSON の数 |
| `source_files` | array | 入力 JSON ごとに 1 件（下表） |

`source_files` の各要素：

| フィールド | 型 | 説明 |
|---|---|---|
| `index` | number | グループ内での入力の番号 |
| `version` | string | `v2` または `v1` |
| `json_path` | string | 入力 JSON のパス |
| `sha256` | string | 入力 JSON のバイト列の SHA-256 |
| `duplicate_paths` | array | 内容が完全に同じ他の入力 |
| `original_path` / `html_path` | string | この入力の元ファイルと中間 HTML |
| `resume_updated_date` | string | この入力の履歴書更新日 |
| `languages` | array | この入力に含まれる言語コード（例：`["zh", "en"]`） |

### `dates` 日付情報

| フィールド | 型 | 説明 |
|---|---|---|
| `resume_updated_date` | string | 履歴書の更新日（`YYYY-MM-DD HH:MM:SS`）。本文に明記された更新日を優先し、なければ HTML ファイルの過去の更新日時を使います。空欄不可、今回の処理時刻での代用も不可 |
| `resume_download_date` | string | 履歴書のダウンロード／応募日。形式と取得ルールは同上 |
| `resume_updated_date_source` | string | 更新日の取得元（`文档正文更新时间` = 本文、`HTML文件修改时间（历史资料替代）` = ファイル更新日時） |
| `resume_download_date_source` | string | ダウンロード日の取得元 |
| `sys_created_date` | string | システム作成日時（ISO 8601、例：`2026-07-31T11:06:00+09:00`） |
| `sys_updated_date` | string | システム更新日時（ISO 8601） |

### `extraction` 生成処理の情報

| フィールド | 型 | 説明 |
|---|---|---|
| `merger` | string | V3：統合スクリプト（`claude_merge.v3.py`） |
| `rule_version` | string | V3：統合ルールのバージョン（例：`merge-v3.0-contact-key`） |

V2 のレコードでは代わりに `reader_group`・`converter`・`parser`・`status`（`success` / `failed`）・`html_path`・`dom`（`heading_count`・`table_count` などの DOM 統計）を使います。

### `classification` 文書分類

| フィールド | 型 | 説明 |
|---|---|---|
| `document_type` | string | `resume` / `jd` / `contract` / `unknown` |
| `reason` | string | 分類理由 |

### `structured_data` 構造化データ

トップレベルのスナップショットは**常に `resumes[0]`（中国語主版）から再構築**し、食い違いは許されません。

| スナップショット | 取得元 |
|---|---|
| `base_info` | `resumes[0].base_info` |
| `expected_info` | `resumes[0].expected_list[0]`。リストが空なら 8 キーすべて空のオブジェクト |
| `current_info` | `resumes[0].work_experiences` のうち最新の 1 件。なければ 15 キーすべて空のオブジェクト |
| `education_info` | `resumes[0].education_list` のうち学歴ランクが最も高く日付が最も新しい 1 件。なければ 7 キーすべて空のオブジェクト |

#### `base_info` 基本情報（20 フィールド）

| フィールド | 型 | 説明 |
|---|---|---|
| `full_name` | string | 氏名 |
| `gender` | string | 性別（`男` 男性 / `女` 女性） |
| `age` | string | 年齢 |
| `birth_date` | string | 生年月日（`YYYY年MM月DD日`） |
| `birth_year` | string | 生年 |
| `marital_status` | string | 婚姻状況 |
| `children_status` | string | 子どもの有無 |
| `political_status` | string | 政治的身分 |
| `height_cm` | string | 身長（cm） |
| `weight_kg` | string | 体重（kg） |
| `household_registration` | string | 戸籍所在地 |
| `address` | string | 現住所 |
| `postal_code` | string | 郵便番号 |
| `platform_from` | string | 取得元プラットフォーム（例：`前程无忧(51job)`） |
| `platform_resume_id` | string | プラットフォーム上の履歴書 ID（猟聘は 12 桁） |
| `phone` | string | 携帯電話番号 |
| `email` | string | メールアドレス |
| `city` | string | 居住都市 |
| `nationality` | string | 国籍 |
| `pr` | string | 自己 PR・強み |

#### `expected_info` / `expected_list` 希望条件（8 フィールド）

| フィールド | 型 | 説明 |
|---|---|---|
| `expected_city` | string | 希望勤務地 |
| `expected_position` | string | 希望職種 |
| `expected_salary` | string | 希望月給 |
| `expected_annual_salary_min` | string | 希望年収の下限 |
| `expected_annual_salary_max` | string | 希望年収の上限 |
| `expected_industry` | string | 希望業界 |
| `expected_employment_type` | string | 希望雇用形態（`全职` 正社員 / `兼职` パート / `实习` インターン / `remote` / `混合办公` ハイブリッド） |
| `expected_start_date` | string | 入社可能時期 |

#### `current_info` 現職情報（15 フィールド）

`work_experiences` の要素の先頭 15 フィールド（`company_name` から `position_resigned` まで）と同じです。

#### `education_info` / `education_list` 学歴（7 フィールド）

| フィールド | 型 | 説明 |
|---|---|---|
| `school_name` | string | 学校名 |
| `school_major_name` | string | 専攻 |
| `school_degree_type` | string | 学歴区分（`博士后` ポスドク / `博士` 博士 / `硕士` 修士 / `本科` 学士 / `大专` 短大・専門 / `高中` 高校 / `中专` 中等専門学校 / `初中` 中学 / `小学` 小学校） |
| `school_degree_rank` | string | 学歴ランク `1`〜`7`（対応は下記） |
| `school_education_type` | string | 就学形態（`全日制研究生` 全日制大学院 / `全日制大学` / `全日制大专` / `全日制高中` / `全日制中专` など） |
| `school_start_ym` | string | 入学年月（`YYYY年MM月01日`） |
| `school_end_ym` | string | 卒業・修了年月 |

`school_degree_rank` の対応：`7` ポスドク、`6` 博士、`5` 修士、`4` 学士、`3` 短大・専門、`2` 高校・中等専門、`1` 中学以下。

### `resumes` 言語版の一覧

- `resumes[0]` は常に中国語主版（`resume_languge = "zh"`）で、実際の中国語の内容でなければなりません。
- 英語・日本語・ドイツ語などの原文版は `resumes[1]` 以降に置き、実際の言語を記録します。
- 外国語のみの履歴書は、`resumes[0]` にフィールド単位の中国語訳を、`resumes[1]` に原文をそのまま保持します。
- 各言語版の構造は完全に同一で、互いに独立したディープコピー（参照の共有なし）です。リストの要素はできるだけ 1 対 1 で対応させます。
- どのリストも「1 件 1 要素」で構成し、履歴書全文を 1 つの要素に詰め込みません。

| フィールド | 型 | 説明 |
|---|---|---|
| `resume_languge` | string | 言語コード（`zh` / `en` / `jp` / `de` など）。出力は従来の綴りを維持し、`resume_language` は読み込み時の互換用のみ |
| `base_info` | object | 基本情報（トップレベルの `base_info` と同じ） |
| `expected_list` | array | 希望条件 |
| `work_experiences` | array | 職歴 |
| `education_list` | array | 学歴 |
| `certificate_list` | array | 資格 |
| `language_list` | array | 語学力 |
| `skills_list` | array | スキル |
| `training_list` | array | 研修歴 |
| `project_list` | array | プロジェクト経験 |
| `communication_list` | array | コミュニケーション記録 |

#### `work_experiences` 職歴（1 件 18 フィールド）

| フィールド | 型 | 説明 |
|---|---|---|
| `company_name` | string | 会社の正式名称（日付の接尾辞や縦線を除去） |
| `company_employees` | string | 会社規模（例：`100-499人`、`未填写` = 未記入） |
| `company_industry` | string | 業界 |
| `position` | string | 職位（`公司性质：` などの会社属性を誤って入れない） |
| `position_type` | string | 職種区分 |
| `position_salary` | string | 月給 |
| `position_dept` | string | 部署 |
| `position_report_to` | string | 報告先（上長） |
| `position_subordinate` | string | 部下の人数 |
| `employment_type` | string | 雇用形態（`全职` 正社員 / `兼职` パート / `实习` インターン） |
| `annual_salary_min` | string | 年収の下限 |
| `annual_salary_max` | string | 年収の上限 |
| `status` | string | 在職状況（`在职` 在職中 / `离职` 退職） |
| `position_start` | string | 入社年月（`YYYY年MM月01日`） |
| `position_resigned` | string | 退社年月（在職中は `""`） |
| `resigned_reason` | string | 退職理由 |
| `position_responsibilities` | string | 職務内容と実績のみ（会社の性質・規模・都市などの行は除外） |
| `position_achievements` | string | 実績・成果 |

#### `certificate_list` 資格（1 件 3 フィールド）

| フィールド | 型 | 説明 |
|---|---|---|
| `certificate_name` | string | 資格名（級・スコアを含む） |
| `certificate_type` | string | 資格の種類（`证书` 資格証 / `结业证` 修了証 / `培训证` 研修証 など） |
| `certificate_time` | string | 取得年月（`YYYY年MM月01日`） |

CET・JLPT・TOEIC・TOEFL・BEC などの語学試験は `language_list` に入れ、`certificate_list` に重複して入れません。語学以外の職業資格・専門認定・運転免許などは `certificate_list` に入れます。

#### `language_list` 語学力（1 件 4 フィールド）

| フィールド | 型 | 説明 |
|---|---|---|
| `language_name` | string | 言語名（`日语` 日本語 / `英语` 英語 / `德语` ドイツ語 / `普通话` 標準中国語 / `粤语` 広東語 など） |
| `language_level` | string | レベル（例：`熟练` 堪能 / `一般` 普通 / `CET-6` / `N1`） |
| `language_certificate` | string | 資格の有無（`有` あり / `无` なし / `""`） |
| `language_certificate_time` | string | 資格取得年月（通常は空） |

#### `skills_list` スキル（1 件 2 フィールド）

| フィールド | 型 | 説明 |
|---|---|---|
| `skill_name` | string | スキル名 |
| `skill_level` | string | 習熟度（例：`熟练` / `精通` / `掌握`） |

#### `training_list` 研修歴（1 件 7 フィールド）

| フィールド | 型 | 説明 |
|---|---|---|
| `sequence_no` | number | 通し番号（1 から） |
| `organization_name` | string | 研修機関 |
| `training_name` | string | 研修コース／プログラム名 |
| `start_ym` | string | 開始年月（`YYYY年MM月01日`） |
| `end_ym` | string | 終了年月 |
| `certificate_name` | string | 取得した資格（なければ `""`） |
| `description` | string | 研修内容 |

#### `project_list` プロジェクト経験（1 件 11 フィールド）

| フィールド | 型 | 説明 |
|---|---|---|
| `sequence_no` | number | 通し番号（1 から） |
| `fingerprint` | string | 重複排除用のプロジェクト指紋（通常は空） |
| `project_name` | string | プロジェクト名 |
| `company_or_client` | string | 所属会社／クライアント |
| `role_name` | string | 担当した役割 |
| `start_ym` | string | 開始年月（`YYYY年MM月01日`） |
| `end_ym` | string | 終了年月 |
| `description` | string | プロジェクト概要（ソフトウェア・ハードウェア環境などを含む） |
| `responsibilities` | string | 担当業務 |
| `achievements` | string | 成果 |
| `keywords` | string | キーワードタグ |

#### `communication_list` コミュニケーション記録（1 件 2 フィールド）

| フィールド | 型 | 説明 |
|---|---|---|
| `communicate_time` | string | 日時（`YYYY年MM月DD日 HH:mm:ss`） |
| `communicate_content` | string | 内容 |

### `raw_text` 全文テキスト

- **単一ソース・単一言語・翻訳なし**：原文テキストを使用します（`### 工作表` などのシート見出し行を除去し、各行の前後の空白を削除、空行を除き、`\n` で連結）。
- **統合・翻訳・多言語**：各フィールドを 1 行ずつ組み立てて `\n` で連結します。言語版は `resumes` の順（中国語が先頭）、各版の中は `base_info`、`expected_list`、`work_experiences`、`education_list`、`certificate_list`、`language_list`、`skills_list`、`training_list`、`project_list`、`communication_list` の順です。空値やプレースホルダーは書き込みません。多言語履歴書は対応付けを済ませてから `raw_text` を生成します。
- `quality.raw_text_length` は常に最終的な `raw_text` の長さと一致します。

### `quality` 品質の概要

| フィールド | 型 | 説明 |
|---|---|---|
| `full_name` | string | 氏名（簡易確認用） |
| `has_work` | boolean | 職歴の有無 |
| `work_count` | number | 職歴の件数 |
| `has_education` | boolean | 学歴の有無 |
| `education_count` | number | 学歴の件数 |
| `languages` | array | `resumes` に含まれる言語コード |
| `raw_text_length` | number | `raw_text` の文字数 |

V2 のレコードは変換スクリプトによって、このうち一部のフィールドしか持たない場合があります。

### `merge_info` 統合情報（V3 のみ）

| フィールド | 型 | 説明 |
|---|---|---|
| `group_id` | string | グループ ID（メンバーの元バイト列の SHA-256 から算出。修復コピーを使っても変わらない） |
| `rule_version` | string | 統合ルールのバージョン |
| `output_filename` | string | 出力ファイル名：`氏名_連絡先.json`。正規化した携帯番号を優先し、次にメールアドレス |
| `name_status` | string | `valid` または `unreliable` |
| `canonical_name` | string | 採用した氏名 |
| `english_name` | string | 英語／ローマ字表記の氏名（あれば） |
| `primary_phone` / `primary_email` | string | 本人識別キーとして使う連絡先 |
| `other_phones` / `other_emails` / `landlines` | array | 見つかったその他の連絡先 |
| `shared_contacts_ignored` | array | 他人と共有しているためキーに使わない連絡先 |
| `needs_translation` | boolean | 中国語版がない場合は `true` |
| `v2_count` / `v1_count` | number | V2 / V1 の入力数 |
| `language_sources` | object | 各言語がどの `source_files` 番号から来たか |
| `translated_from` | string | 中国語訳の原文言語（あれば） |
| `name_note` | string | 氏名判定に関するメモ |
| `conflict_count` | number | 記録したフィールド競合の数 |
| `field_issue_count` / `high_issue_count` | number | フィールドの問題数 / 重大な問題の数 |
| `name_linked_sources` | array | 氏名の証拠で関連付けた入力 |
| `output_category` | string | `formal` / `needs_fix` / `pending_translation` |

### 本人識別と出力のルール

- 正規化した携帯電話番号か有効なメールアドレスのいずれかが一致すれば同一人物とみなします。氏名・生年月日・会社などの食い違いは記録するだけで、グループは分割しません。
- 別人同士で共有されている連絡先は 1 人だけに割り当てます：履歴書の作成日時が最も新しい人です。
- 正式な JSON には有効な電話番号かメールアドレスが少なくとも 1 つ必要です。どちらもない入力は `ledgers/no_contact_ledger` に記録し、ファイルは生成しません。
- 出力区分：中国語版がない → `pending_translation`、重大な問題があるか氏名が無効 → `needs_fix`、それ以外 → `formal`。

### 多言語の日付ルール

1 つの履歴書内では、すべての言語版の日付が一致していなければならず、中国語版（`resumes[0]`）を基準とします。整列の後、`claude_merge.v3.py` の `unify_dates` が処理します。対象は、すでに対応付け済みの行（言語間でリスト長が等しいもの）の日付フィールド（`position_start`、`position_resigned`、`school_start_ym`、`school_end_ym`、プロジェクト・研修の `start_ym` / `end_ym`、`certificate_time`、`language_certificate_time`）のみです。

1. まず全日付を `YYYY年MM月DD日` に正規化します。時刻は除去し、月がない値は補いません（年のみ・年の範囲はそのまま）。
2. 中国語が空で他言語に値がある → 他言語の日付で中国語を補います。
3. 他言語が空または異なる → 中国語の日付で上書きします。
4. 差が 24 か月を超える、または比較できない → やはり中国語を優先しますが、`ledgers/cleaning_ledger` に `date_unify_override_far` として記録します。こうした行は言語間で別の経歴（別の時期・別の会社）に対応付けられていることが多く、元ファイルで抽出確認すべき対象です。
5. 変更すると開始日が終了日より後になる場合 → 行全体を変更せず、`date_unify_skip` として記録します。
6. `birth_date` にも同じルールを適用します。ただし、英語の長い書式（`November 2, 1965`）は先に正規化し、年月が一致して一方の日が `01`（年月のみの値を補った 01）の場合は、全言語で具体的な日がある方を採用します。出生年が異なる場合は変更せず `date_unify_skip` として記録します。

変更はすべてクレンジング台帳に `date_unify_format`、`date_unify_fill_zh`、`date_unify_fill_other`、`date_unify_override` として記録されます。スナップショット（`current_info`、`education_info`）と `raw_text` はこの処理の後に計算されます。独立監査は、人手決定との行照合で日付フィールドを比較しません。

### V2 のファイル単位 JSON との違い

- `schema_version` は `codex-resume-json-1.0`、`record_id` は SHA-256 ハッシュで、`merge_info` はありません。
- `source` は `path`・`original_path`・`filename`・`extension`・`size`（バイト）・`html_filename`・`note` を持ちます。
- `extraction` は前述の V2 用フィールドを使います。
- ファイル名：`<氏名>_<元パスの SHA-256 先頭 12 文字>.json`。多言語を統合した場合は複数のハッシュを連結できます（`<氏名>_<中国語ハッシュ>_<英語ハッシュ>.json`）。氏名がない場合は `待确认姓名_<ハッシュ>.json`（氏名要確認）です。

## 注意事項

- 履歴書は機微な個人情報です。`.gitignore` でデータディレクトリ、`config.json`、`CONTEXT.md`、実行出力、各種の判定／対応付けファイルを除外済みです。**実在の履歴書やそこから生成した JSON をどのリポジトリにもコミットしないでください。**
- V2 の一回限りの修復スクリプト 2 本は「氏名／電話番号の対応表」を必要としますが、そのデータはリポジトリに含めていません。`repair_data/README.md` を参照してください。
- V2 のスクリプトは過去に（Word / XLS / PDF / Web ごとに）段階的に作られたもので、パスを設定化しただけで書き直してはいません。整理の際に削除したのは内容が完全に同一の重複ファイルだけです（対照表は `docs/v2-name-mapping.md`）。

## ライセンス

MIT。`LICENSE` を参照してください。
