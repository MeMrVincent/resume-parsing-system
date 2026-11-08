# Requirements / 依赖 / 依存ライブラリ

Python 3.13. V3 merging and auditing use only the standard library; the packages below are for the V2 conversion flow (Word / XLS / PDF / HTML → JSON).
Python 3.13。V3 合并/审计只用标准库；下表是 V2 转换流程（Word / XLS / PDF / HTML → JSON）需要的第三方库。
Python 3.13。V3 の統合・監査は標準ライブラリのみ使用します。下表は V2 の変換フロー（Word / XLS / PDF / HTML → JSON）で必要なサードパーティ製ライブラリです。

Install / 安装 / インストール: `pip install -r requirements.txt`

| Package | Required | English | 简体中文 | 日本語 |
|---|---|---|---|---|
| `beautifulsoup4` | Yes | HTML parsing and semantic-DOM handling (used by most V2 scripts) | HTML 解析与语义 DOM 处理（大多数 V2 脚本使用） | HTML の解析と意味付き DOM の処理（ほとんどの V2 スクリプトが使用） |
| `lxml` | Yes | Fast XML/HTML parser backend | 快速的 XML/HTML 解析后端 | 高速な XML/HTML パーサーのバックエンド |
| `openpyxl` | Yes | Read `.xlsx` files (XLS flow, inventory report) | 读取 `.xlsx` 文件（XLS 流程、盘点报告） | `.xlsx` ファイルの読み込み（XLS フロー、棚卸しレポート） |
| `xlrd` | Yes | Read legacy `.xls` files | 读取旧版 `.xls` 文件 | 旧形式の `.xls` ファイルの読み込み |
| `pyxlsb` | Yes | Read binary `.xlsb` files | 读取二进制 `.xlsb` 文件 | バイナリ形式の `.xlsb` ファイルの読み込み |
| `mammoth` | Yes | Convert `.docx` to HTML (Word → HTML step) | 将 `.docx` 转为 HTML（Word → HTML 步骤） | `.docx` を HTML に変換（Word → HTML の段階） |
| `olefile` | Yes | Read OLE containers of old `.doc`/`.xls` files | 读取旧版 `.doc`/`.xls` 的 OLE 容器 | 旧形式の `.doc`/`.xls` の OLE コンテナの読み込み |
| `python-docx` | Yes | Read Word documents (paragraphs, tables) | 读取 Word 文档（段落、表格） | Word 文書（段落・表）の読み込み |
| `python-pptx` | Yes | Extract text from PowerPoint files | 提取 PowerPoint 文件中的文本 | PowerPoint ファイルからのテキスト抽出 |
| `defusedxml` | Yes | Safe XML parsing of untrusted documents | 安全地解析不可信文档中的 XML | 信頼できない文書の XML を安全に解析 |
| `pypdf` | Yes | Read PDF text and page information | 读取 PDF 文本与页面信息 | PDF のテキストとページ情報の読み込み |
| `PyMuPDF` | Yes | PDF text layer / page analysis (imported as `fitz`) | PDF 文本层与页面分析（以 `fitz` 导入） | PDF のテキスト層・ページの解析（`fitz` として import） |
| `Pillow` | Yes | Image handling for OCR | 为 OCR 处理图片 | OCR 用の画像処理 |
| `pytesseract` | Yes | OCR wrapper (requires the Tesseract program installed separately) | OCR 封装（需另行安装 Tesseract 程序） | OCR のラッパー（Tesseract 本体は別途インストールが必要） |
| `pywin32` | Optional (Windows only) | Word/Excel conversion through Microsoft Office (`sys_platform == "win32"`) | 通过 Microsoft Office 进行 Word/Excel 转换（仅 Windows） | Microsoft Office 経由の Word/Excel 変換（Windows のみ） |
| `torch` | Optional (commented out) | Only for the optional local translation feature | 仅用于可选的本地翻译功能 | 任意のローカル翻訳機能にのみ使用 |
| `transformers` | Optional (commented out) | Only for the optional local translation feature | 仅用于可选的本地翻译功能 | 任意のローカル翻訳機能にのみ使用 |
