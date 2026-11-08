# PDF 转 JSON v2 说明

[English](v2-pdf-to-json.md) | **简体中文** | [日本語](v2-pdf-to-json.ja.md)

> 本文档描述 V2（word/xls/pdf/html → JSON）流程。目录默认值见根目录 `config.example.json`；文中的 `<项目根>` 即 config 里的 project_root。已合并的重复脚本见 [`v2-name-mapping.cn.md`](v2-name-mapping.cn.md) 末尾。

## 1. 目标与原则

本流程把 PDF 简历整理为 `complete-v1` 候选人 JSON，最终发布到：

```text
<项目根>\complete-transfered-jsons\pdf\new
```

当前版本基线为 **PDF v2**。它不直接依赖 PDF 文本层生成最终 JSON，而是采用：

```text
原始 PDF
  + iLovePDF 转换后的 Word
  + PDF文档.json 的路径与分类说明
  + GPT/旧 JSON 参考
      ↓
Word → 语义 HTML → 逐源 JSON → 候选人合并 JSON → 语义修复 → 双重审计 → 发布 new
```

历史上直接从 PDF 文本层提取时，复杂表格、双栏、日式履历书和多语言简历的结构质量较差。iLovePDF 生成的 Word 通常能较好保留表格和段落，因此 Word 是主解析输入；原 PDF 始终保留为身份、文字、页数和版面复核依据。

核心原则：

1. PDF 原件是最终证据，不修改、不覆盖。
2. Word 是主解析输入，但 Word 与 PDF 冲突时以 PDF 可见内容为准。
3. GPT JSON、旧 JSON 仅作为参考，不能无条件覆盖源文件。
4. 一个物理 PDF 先生成一个逐源 JSON，再按候选人身份合并。
5. 姓名相同不是自动合并依据；手机号、邮箱等强证据优先。
6. 全量审计通过前，不发布到 `new`。

## 2. 目录职责

### 2.1 输入和说明

```text
<项目根>\complete-transfered-htmls\pdf\
├── input\                  原始 PDF
├── word\                   iLovePDF 生成或人工重新转换的 DOCX
└── PDF文档.json            PDF 路径、分类和人工说明
```

- `input`：原始 PDF，包含简历和少量非简历文件。
- `word`：PDF 转 Word 的结果；文件名可能被人工修改，不能只靠文件名匹配。
- `PDF文档.json`：原始路径、是否简历、候选人说明、联系方式、HTML 名称等权威人工信息。

### 2.2 JSON 参考和正式输出

```text
<项目根>\complete-transfered-jsons\pdf\
├── old\                    上一轮低质量产物，只作参考
├── gpt\                    ChatGPT 转换或人工合并的参考 JSON
└── new\                    当前正式交付 JSON
```

- `old`：不能直接视为正确数据。
- `gpt`：部分质量较好，部分存在重复、多语言结构差异或错误合并；只能在身份和来源数量匹配时使用。
- `new`：只有候选人级审计全部通过后才原子替换。

### 2.3 中间产物和报告

```text
<项目根>\complete-transfered-htmls\pdf\
├── rebuild-work\
│   ├── pdf_rebuild_map.v2.json       权威映射
│   ├── html\                         Word 转换后的语义 HTML
│   ├── json-by-source\                一 PDF 一 JSON 的逐源暂存
│   └── json-by-candidate\             候选人级合并暂存
└── rebuild-reports\                   提取、审计、合并、复核和发布报告
```

## 3. 当前 v2 代码

PDF 主流程只使用以下 13 个入口：

| 文件 | 职责 |
|---|---|
| `python/v2/pdf_rebuild_map.v2.py` | 建立 PDF、Word、人工说明、GPT 和旧 JSON 的权威映射 |
| `python/v2/pdf_rebuild_extract.v2.py` | Word → 语义 HTML → 逐源 JSON |
| `python/v2/pdf_rebuild_audit.v2.py` | 审计逐源 JSON 与映射的覆盖、身份、结构和源哈希 |
| `python/v2/pdf_rebuild_merge.v2.py` | 按候选人保守合并，多语言版本独立保留 |
| `python/v2/pdf_rebuild_semantic_repair.v2.py` | 清除字段串位、模板占位、HTML 泄漏、重复与工作/学历错分，并加载 PDF 人工核验覆盖 |
| `python/v2/pdf_raw_text_v2.py` | 从 Word、PDF 和语义 HTML 重建独立原文证据，清理转码噪声并按物理来源去重 |
| `python/v2/pdf_rebuild_candidate_audit.v2.py` | 审计候选人级 JSON，确认每个源仅覆盖一次 |
| `python/v2/pdf_json_strict_audit.v2.py` | 兼容性结构审计，检查快照、日期和基础源证据 |
| `python/v2/pdf_json_field_strict_audit.v2.py` | 发布闸门：逐语言、逐列表、逐字段检查占位值、串字段、实体错分、日期、联系方式、重复、源证据及独立 `raw_text` 完整性 |
| `python/v2/pdf_rebuild_finalize.v2.py` | 审计通过后原子发布到 `new` |
| `python/v2/pdf_rebuild_issue_table.v2.py` | 生成人工重转 Word/难识别文件问题表 |
| `python/v2/pdf_gpt_review_compare.v2.py` | 对 GPT 结构差异执行 PDF、Word、GPT、当前 JSON 四方对比 |
| `python/v2/pdf_gpt_review_resolve.v2.py` | 把人工复核结论增量写入持久化覆盖文件 |

仍会复用以下公共代码，它们不属于已删除的旧 PDF 流水线：

- `c_resume_html_dom_common.v2.py`：Word HTML DOM 处理。
- `c_resume_html_to_json_common.v2.py`：通用简历字段解析和 schema 归一化。
- `xls_to_html_to_json.v2.py`：日式表格 Word 的 XLS 网格增强规则。

## 4. 完整运行步骤

所有命令都在 `<项目根>` 下执行。

### 4.1 建立映射

```powershell
python python/v2/pdf_rebuild_map.v2.py
```

映射阶段完成 PDF/Word 盘点、人工分类关联、同名和内容别名匹配、GPT/old 参考关联、PDF 页数和文本层分析以及非简历隔离。

重点文件：

```text
rebuild-work/pdf_rebuild_map.v2.json
rebuild-reports/pdf_word_aliases.v2.json
rebuild-reports/pdf_pilot_30.v2.json
```

### 4.2 全量提取

```powershell
python python/v2/pdf_rebuild_extract.v2.py `
  --scope all `
  --force `
  --report complete-transfered-htmls/pdf/rebuild-reports/pdf_full_extract.v2.json
```

处理顺序：

1. 读取匹配的 DOCX；
2. 转为标准 Word HTML；
3. 判断普通 Word、Word 表格或日式表格；
4. 普通 Word 使用标题、段落、日期和实体规则；
5. 日式表格优先复用 XLS 网格语义规则；
6. XLS 增强无法安全处理某种语言/日期格式时，回退到标准 Word HTML；
7. 输出逐源 JSON；
8. 根据 PDF 和人工说明补充源文件、日期、身份与分类信息。

提取状态包括：

- `success`：结构清楚；
- `needs_review`：逐源解析存在弱项，但后续可由同候选人其他版本或已复核 GPT 中文版本补足；
- `non_resume`：明确非简历；
- `failed`：读取或转换失败，禁止进入候选人合并。

### 4.3 逐源审计

```powershell
python python/v2/pdf_rebuild_audit.v2.py `
  --report complete-transfered-htmls/pdf/rebuild-reports/pdf_full_audit.v2.json
```

必须确认所有应处理简历都有逐源 JSON、没有多余 JSON、源 SHA-256 和路径一致、身份与结构满足最低要求，并且非简历没有进入候选人数据。

### 4.4 候选人级合并

```powershell
python python/v2/pdf_rebuild_merge.v2.py --replace
```

合并规则：

1. 手机号相同或邮箱相同是强合并证据。
2. 姓名一致只能辅助，联系方式硬冲突时不得合并。
3. 中文、日文、英文、德文等分别保存在 `structured_data.resumes`。
4. 同一语言优先选结构完整、来源可靠的版本，不简单拼接非空列表。
5. 多份来源只补空字段，不让较差版本覆盖已有可靠字段。
6. GPT 中文仅在 GPT 文件、源文件数量和候选人身份一致时启用。
7. 已四方复核的 GPT 修复从 `pdf_gpt_review_overrides.v2.json` 持久化加载。

### 4.5 语义修复

```powershell
python python/v2/pdf_rebuild_semantic_repair.v2.py `
  --root complete-transfered-htmls/pdf/rebuild-work/json-by-candidate `
  --apply
```

该阶段会处理公司/学校/职位串位、模板表头、HTML 残片、重复经历、反向日期和单源多语言误拆。经原 PDF 视觉核验确认的个案保存在 `rebuild-reports/pdf_semantic_overrides.v2.json`，后续全量重跑仍会复用。

### 4.6 候选人覆盖与全字段严格审计

```powershell
python python/v2/pdf_rebuild_candidate_audit.v2.py `
  --json-root complete-transfered-htmls/pdf/rebuild-work/json-by-candidate

python python/v2/pdf_json_field_strict_audit.v2.py `
  --json-root complete-transfered-htmls/pdf/rebuild-work/json-by-candidate
```

发布前必须满足：

- `missing_source_hashes` 为空；
- `duplicate_source_hashes` 为空；
- 每个简历源恰好被一个候选人 JSON 覆盖；
- `quality:ready` 等于候选人总数；
- 待翻译为 0；
- GPT 结构待复核为 0；
- 质量警告为 0。
- 严格审计 `strict_failure_file_count`、`review_file_count` 和 `total_issue_count` 均为 0。

“严格”不是只检查字段是否非空。审计器会重新读取映射中的 PDF、Word 和 HTML 作为独立证据，逐字段检查：

- 姓名、电话、邮箱、公司、学校、职位、专业等实体能否追溯到原文；
- 学校、公司、项目、证书、语言和自我评价是否串入错误列表；
- 实体字段是否混入章节标题、模板文字、长段职责或日期；
- 日期格式、先后顺序、在职状态、学历层级和枚举值是否合理；
- 同一列表中是否存在完全重复或语义重复记录；
- 多语言版本是否保持各自结构，并与对应语言源文件一致；
- 顶层快照是否与中文主版本一致；
- `raw_text` 是否由源文件独立重建，来源块、哈希、长度和文本覆盖是否正确；
- 是否含 `WordOOXMLTable*`、OpenXML 表格标记、HTML 残片、C0/C1 控制字符或常见转码乱码。

### 4.7 发布

```powershell
python python/v2/pdf_rebuild_finalize.v2.py --replace
```

发布器先复制到临时目录并逐文件校验 SHA-256，全部通过后才原子替换：

```text
<项目根>\complete-transfered-jsons\pdf\new
```

发布完成后必须对正式目录再跑一次全字段审计，避免暂存目录与正式目录不一致：

```powershell
python python/v2/pdf_json_field_strict_audit.v2.py `
  --json-root complete-transfered-jsons/pdf/new `
  --report complete-transfered-htmls/pdf/rebuild-reports/pdf_json_field_strict_audit.formal.v2.json `
  --csv complete-transfered-htmls/pdf/rebuild-reports/pdf_json_field_strict_audit.formal.v2.csv
```

最终还要核对 `pdf_finalization.v2.json`：`published_count` 应为 419、`map_resume_records_updated` 应为 561，并按报告中每个文件记录的 SHA-256 比较暂存与正式目录，哈希差异必须为 0。

## 5. 日式表格简历

文件名或内容包含“日语、日文、履歴書、職務経歴書”等标记的文件，通常使用表格布局。常见风险包括：

- 年、月、学校/公司分散在不同单元格；
- “入学”和“毕业”被识别为两条学历；
- 教育、工作、资格在同一张大表中；
- 中文实体名与日文标题混排；
- 一份文件同时含履历书和职务经历书。

v2 的处理策略：

1. 从 DOCX OOXML 恢复真实单元格网格；
2. 把 Word 表格转换为 XLS 风格的二维单元格；
3. 复用 XLS 的横向字段、事件行和语言层规则；
4. 重新绑定姓名、联系方式、工作、教育和资格；
5. 若 XLS 增强结果不完整或规则异常，保留标准 Word HTML，不让增强器中断全量批次；
6. 最终仍以 PDF 可见表格复核条目数量、日期和归类。

## 6. GPT 差异复核

合并后如果 `pdf_gpt_translation_review.v2.json` 不为空，运行：

```powershell
python python/v2/pdf_gpt_review_compare.v2.py
```

四方材料为原始 PDF 全页、iLovePDF Word/语义 HTML、GPT JSON 和当前候选人 JSON。重点检查多语言重复、学校误作公司、项目/证书误作工作、日式入学毕业拆分和多份简历错误合并。

确认后把结论加入 `pdf_gpt_review_resolve.v2.py` 的 `FACTS`，再运行：

```powershell
python python/v2/pdf_gpt_review_resolve.v2.py
python python/v2/pdf_rebuild_merge.v2.py --replace
python python/v2/pdf_rebuild_candidate_audit.v2.py
```

复核脚本采用增量方式：已有复核记录会保留，新记录按 GPT 文件路径追加或替换，因此全量重跑不会恢复已修复的错误结构。

## 7. Word 需要重新转换时

以下情况进入问题表，由人工重新转 Word：

- Word 为空或只有图片；
- PDF 明显有内容，但 Word 缺页；
- 表格行列严重错位；
- 姓名、联系方式或主要经历在 Word 中丢失；
- PDF 是扫描件且 iLovePDF 未正确 OCR；
- Word 与 PDF 不是同一份内容。

生成问题表：

```powershell
python python/v2/pdf_rebuild_issue_table.v2.py
```

人工替换 Word 后，不修改 PDF。指定文件增量重提取示例：

```powershell
python python/v2/pdf_rebuild_map.v2.py
python python/v2/pdf_rebuild_extract.v2.py `
  --filenames "需要重跑的文件.pdf" `
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

## 8. JSON 结构要求

候选人 JSON 至少包含 `schema_version`、`record_id`、`source.source_files`、`dates`、`extraction`、`classification`、`structured_data.base_info`、`structured_data.resumes`、各经历列表、`raw_text` 和 `quality`。

规则：

1. `resumes[0]` 优先为中文主版本。
2. `expected_list`、`work_experiences`、`education_list`、`certificate_list`、`language_list`、`skills_list`、`training_list`、`project_list`、`communication_list` 只允许出现在各个 `structured_data.resumes[]` 内，主对象下不得再复制这些列表。
3. `structured_data` 顶层只保留 `base_info`、`expected_info`、`current_info`、`education_info` 四个查询快照和 `resumes`；快照与中文主版本保持一致。
4. 每份工作、教育、项目、培训必须一段一条，空实体记录必须删除。
5. 每个结构化值必须符合 context 中该字段的定义，不能仅因“有值”就视为合格；值必须语义合理且能追溯到对应源文档。
6. 不得把整段原文塞入公司名、学校名、职位、专业、项目名或证书名，也不得把学校当公司、公司当学校、校园经历当工作。
7. 不得保留 `公司名称`、`学校名`、`Post/Wages`、`WordOOXMLTable*` 等模板或转换占位值。
8. 高中、中专、初中和小学经历不进入 `education_list`；大学、专科、本科、硕士、博士等按 context 规范映射学位与教育类型。
9. 语言考试归入 `language_list`；考试名称或级别写入 `language_level`，`language_certificate` 只允许 `有`、`无` 或空字符串。
10. 月份精度的日期统一为 `YYYY年MM月01日`；全角数字、汉字年份和 `YYYY～YYYY` 等写法必须标准化，但不得虚构源文档没有给出的月份或具体日期。“至今”用空结束日期和 `status=在职` 表示。
11. 多语言简历合并后，每个物理源都必须出现在 `source.source_files` 和 `source.merge_trace`，至少记录文件名、路径、SHA-256、语言和文档类型，便于追溯。
12. `raw_text` 与最终结构化字段完全解耦。每个物理来源使用 `===== SOURCE: 文件名 =====` 分隔；同一人的多份、多语言简历按来源合并为一份 `raw_text`，按文件名、SHA-256 和正文去重，每个源只出现一次。
13. 单个来源块以 Word 文本为第一候选；Word 不可用时使用 PDF，再用语义 HTML 补充 Word/PDF 中缺失且不重复的行。清理仅限表格转换标记、HTML 元数据、控制字符、可逆转码乱码和确定的重复聚合行，不得为了美观删除难读但属于原件的内容。
14. 禁止从 `base_info`、工作、教育、项目、证书等结构化字段反向拼接或补写 `raw_text`。即使结构化姓名、电话或翻译实体未在文本层出现，也不得为使审计通过而写入 `raw_text`。
15. `extraction.raw_text_source` 固定为 `canonical_deduplicated_pdf_word_html_text`；严格审计会独立重读 PDF、Word 和 HTML，检查来源声明、来源块数量、长度、重复和文本覆盖。

人工确认的个案修复保存在：

```text
<项目根>\complete-transfered-htmls\pdf\rebuild-reports\pdf_semantic_overrides.v2.json
```

该文件在跨语言协调之后应用，是最终权威覆盖层。新增覆盖时必须同时记录源文件依据，避免下一次全量重跑恢复旧错误。

## 9. 当前验收基线

截至 2026-08-30：

- 原始 PDF：567 份；
- 简历：561 份；
- 非简历：6 份；
- 候选人 JSON：419 份；
- 合并候选人：107 份；
- 单来源候选人：312 份；
- PDF/Word/HTML/GPT/旧 JSON 对照后持久化覆盖记录：97 份候选人；
- 待翻译：0；
- GPT 结构待复核：0；
- 质量警告：0；
- 候选人审计：419/419 `ready`；
- 严格审计：419/419 `clean`，0 失败、0 待复核、0 问题；
- 561 个简历源全部且仅覆盖一次。
- 暂存目录与正式 `new`：419/419 文件 SHA-256 一致，0 哈希差异。
- `raw_text`：来源块数量与唯一源哈希数量一致，无重复源块、无缺失源块、无 Word/OpenXML 表格标记及 C0/C1 控制字符。

验收报告：

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

正式验收以 `pdf_json_field_strict_audit.formal.v2.json` 和 `pdf_finalization.v2.json` 为准；前者证明正式目录 419 份全字段审计为 0 问题，后者证明发布数量和文件哈希一致。

## 10. 已知源文件限制与后续重转

本轮结构化 JSON 已全部通过发布闸门，但以下两份 Word/PDF 文本层仍有内嵌字体映射造成的局部乱码，建议后续重新用 iLovePDF 转 Word：

| 候选人 JSON | 建议重转源文件 | 说明 |
|---|---|---|
| `张三_13800000001.json` | `张三中文简历.pdf` | 仅中文版本局部乱码；日文、英文版本可读。 |
| `李四_13800000002.json` | `李四 硕士 广岛大学 化学工学.pdf` | 正文持续字体映射乱码。 |

完整路径和当前 Word 路径见：

```text
<项目根>\complete-transfered-htmls\pdf\rebuild-reports\pdf_word_reconversion_needed.v2.md
```

这两项不阻塞本轮发布：结构化字段已结合 PDF、Word、其他语言版本和人工语义覆盖校正；`raw_text` 仍保留清除控制字符后的源证据，不伪造不可恢复文字。

## 11. 后续版本升级规则

当前 v2 是唯一有效 PDF 实现。后续开发 v3 时：

1. 复制当前 v2 脚本为 v3，不直接覆盖 v2；
2. 代码文件、`VERSION`、默认 MAP 和报告文件名必须同时升级；
3. v3 使用独立暂存或明确的版本化报告，避免污染 v2 验收基线；
4. 先做小批试点，再做全量；
5. 必须比较源覆盖、候选人数、质量状态和关键候选人结构；
6. v3 全量审计通过后才能替换正式 `new`；
7. 升级完成后再决定是否删除旧版本，禁止两套同名入口并存。
