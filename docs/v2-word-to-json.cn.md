# Word 转 JSON 流程说明

[English](v2-word-to-json.md) | **简体中文** | [日本語](v2-word-to-json.ja.md)

> 本文档描述 V2（word/xls/pdf/html → JSON）流程。目录默认值见根目录 `config.example.json`；文中的 `<项目根>` 即 config 里的 project_root。已合并的重复脚本见 [`v2-name-mapping.cn.md`](v2-name-mapping.cn.md) 末尾。


## 1. 目标与目录

本流程把 `docs` 范围内的 Word 简历转换为可语义化解析的 HTML，再转换为统一 JSON，并经过源文件审计后写入正式目录。

- 原始 Word：`<项目根>\需要采集的简历文件夹`
- 转换工作目录：`<项目根>\complete-transfered-htmls\docs`
- 转换总映射：`<项目根>\complete-transfered-htmls\docs\word_conversion_map.json`
- 正式 JSON：`<项目根>\complete-transfered-jsons\docs\<语言>`
- 审计及中间报告：`<项目根>\_resume_qa`
- JSON 字段说明：`CONTEXT.md（未随仓库公开；字段结构见 examples/ 中的示例 JSON）`
- 参考模板：`<项目根>\complete-v1\Zhang San_13800000003.json`

正式 JSON 文件名使用：

```text
姓名_手机号.json
姓名_邮箱.json
姓名_无联系方式.json
姓名_手机号_2.json        # 同名冲突时递增
```

同一候选人的多个 Word 可以合并为一个 JSON。合并后的所有源路径写入：

```text
source.source_files[].original_path
source.merged_original_paths[]
```

因此“正式 JSON 文件数”可能少于“已完成 Word 源文件数”。全局进度必须以源路径数量为准。

## 2. 总体流程

```text
Word
  ↓ c_resume_html_dom_common.v2.py
语义 HTML + word_conversion_map.json
  ↓ 按语言分类及 DOM 修复
中文/日文/中日文/中英文等 HTML
  ↓ 对应语言解析器
暂存 JSON
  ↓ 结构筛选 + 源文件逐字段审计
合格 JSON
  ↓ promote / finalize
正式 JSON + 更新映射 + 删除已完成 HTML
  ↓
疑难文件进入 OCR / unknown / failed 人工批次
  ↓ c_resume_ocr_normalize.v2.py
  ↓ c_resume_ocr_finalize.v2.py
正式 JSON 或 invalid_resume 终态
```

原则：解析器生成 JSON 不等于完成。只有通过结构校验和源数据审计、写入正式目录并登记源路径后，才算完成。

## 3. 第一步：Word 转语义 HTML

### `python/v2/c_resume_html_dom_common.v2.py`

主转换程序。负责：

- 读取 `.doc`、`.docx` 等 Word 文件；
- 提取段落、表格、标题及文档元数据；
- 生成 HTML；
- 将可识别字段写成语义 DOM，例如 `data-field`、`label`；
- 为同一段落中的多个字段生成独立子节点；
- 记录源 Word、HTML、语言、转换状态和错误信息到 `word_conversion_map.json`；
- 不保留简历照片。

推荐语义结构示例：

```html
<p data-field="full_name" label="姓名">张三</p>
<p label="基本信息">
  <i data-field="gender" label="性别">女</i>
  <i data-field="marital_status" label="婚姻">未婚</i>
  <i data-field="birth_date" label="生日">1988年03月16日</i>
</p>
```

不要依赖一大组正则从整页纯文本反推字段；姓名、联系方式、证书、教育、工作经历等应尽量成为独立 DOM 节点。

### HTML 修复和检查程序

- `python/v2/word_semantic_html_repair.v2.py`：修复难解析 HTML 的字段节点、表格和分段结构（原文件：`repair_semantic_html_dom.py`）。
- `python/v2/word_semantic_html_audit.v2.py`：批量检查 HTML 是否具备可解析的语义结构（原文件：`audit_semantic_html_batch.py`）。
- `python/v2/word_html_audit_fix.v2.py`：早期 HTML 审计及修复程序（原文件：`audit_and_fix_htmls.py`）。
- `python/v2/word_full_docs_repair.v2.py`：早期全目录深度修复程序（原文件：`full_docs_deep_repair.py`）。
- `python/v2/word_nonchinese_semantics_repair.v2.py`：非中文剩余 HTML 的语义修复（原文件：`repair_nonchinese_remaining_semantics.py`）。
- `python/v2/word_nonchinese_known_name_repair.v2.py`：使用已确认姓名补充非中文 HTML 身份节点（原文件：`repair_nonchinese_known_names.py`）。
- `python/v2/word_verified_identity_inject.v2.py`：向 HTML 注入经过核实的身份字段（原文件：`inject_verified_html_identity.py`）。

这些修复程序只用于确实难解析的 HTML。已经具备清晰语义 DOM 的文件不应重复改写。

## 4. 第二步：按语言解析 HTML

### 中文

#### `python/v2/run_chinese_html_to_json.py`

中文主解析器，也是本次处理使用最多的解析程序。负责平台识别、字段归一、简历分段、日期处理、质量校验及批处理报告。

示例：

```powershell
python python\v2\run_chinese_html_to_json.py `
  --html-dir <中文HTML目录> `
  --json-dir <暂存JSON目录> `
  --map <项目根>\complete-transfered-htmls\docs\word_conversion_map.json `
  --report <项目根>\_resume_qa\chinese_batch.json `
  --progress-interval 10 `
  --file-timeout 30
```

### 日文

- `python/v2/word_japanese_html_to_json.v2.py`：日文履歴書、職務経歴書解析和日文语义规范化。
- `python/v2/word_japanese_identity_retry.v2.py`：仅在文件名或目录中存在可信人名时，生成身份补全后的重试 HTML。
- `python/v2/word_japanese_name_retry.v2.py`：根据审计问题准备日文姓名重试项。

不能把公司名、职位名、募集内容、请求书名称当作候选人姓名。

### 中日文

- `python/v2/word_chinese_japanese_html_to_json.v2.py`：处理中日双语简历，保留多个 `resumes` 语言版本。

### 中英文及其他多语言

- `python/v2/run_chinese_english_html_to_json.py`：处理中英双语简历。
- `python/v2/word_chinese_english_identity_retry.v2.py`：准备中英文身份重试项。
- `python/v2/word_multilingual_parser_stage.v2.py`：暂存自动识别出的多语言解析结果。
- `python/v2/word_english_parser_stage.v2.py`：暂存英文解析器结果。

多语言 JSON 必须保留对应语言版本，不可只因姓名相同就直接复用缺少语言版本的旧 JSON。

## 5. JSON 结构筛选与源文件审计

### 通用结构校验

- `python/v2/reuse_complete_v1_jsons.py`
  - 提供统一的 `validate_json()`；
  - 校验姓名、文件名、联系方式、日期、顶层快照、语言版本、列表字段及 `raw_text`；
  - 是多个解析器和回填程序共用的基础校验模块。
- `python/v2/word_strong_candidate_stage.v2.py`
  - 从暂存 JSON 中筛选姓名有效、结构足够的候选；
  - 会拒绝职位名、公司名、未知姓名及空壳 JSON。
- `python/v2/word_staged_audit_input.v2.py`
  - 将暂存 JSON 与 `word_conversion_map.json` 中的源 Word/HTML 建立审计输入。

### 中文逐字段审计

- `python/v2/audit_chinese_json_against_sources.py`
  - 将 JSON 的姓名、联系方式、期望信息、工作、教育、证书、培训、项目等字段与源 Word/HTML 对比；
  - 非业务数据，如社团职位、协会、联谊、导师等，可以舍弃，不要求写入正式 JSON。
- `python/v2/word_chinese_source_repair.v2.py`
  - 根据审计报告删除误填字段或修复可确定的问题；
  - 修复后必须再次运行审计。
- `python/v2/c_resume_json_promote.v2.py`
  - 只将无审计问题的中文 JSON 写入正式目录。
- `python/v2/c_resume_source_finalize.v2.py`
  - 将成功晋升的源文件标记完成；
  - 更新 `word_conversion_map.json`；
  - 删除对应已完成 HTML。

### 非中文逐字段审计

- `python/v2/c_resume_nonchinese_source_audit.v2.py`
  - 检查姓名语义、语言版本、公司、学校等字段是否能在源文件中找到证据。
- `python/v2/c_resume_nonchinese_promote.v2.py`
  - 只晋升审计状态为 `passed` 的非中文 JSON，并登记源路径。

### 历史 JSON 复用

- `python/v2/word_unique_name_reuse_stage.v2.py`
  - 根据源文件名中的唯一姓名，从正式目录中寻找可能相同的历史 JSON；
  - 只能作为候选，仍须做源文件审计。
- `python/v2/word_multilingual_v1_match_stage.v2.py`
  - 暂存 `complete-v1` 中可能匹配的多语言 JSON。
- `python/v2/word_nonchinese_v1_repair.v2.py`
  - 修复可确认的非中文 `complete-v1` 候选。

禁止仅凭姓名相同直接复制 JSON。联系方式、工作经历、教育、证书和语言版本必须一致。

## 6. 非简历和终态处理

- `python/v2/c_resume_nonresume_terminalize.v2.py`
  - 识别名称明确的岗位 JD、募集书、公司资料、空白模板、面试题、测试题、合同等；
  - 写入 `non_resume` 终态。
- `python/v2/c_resume_invalid_terminalize.v2.py`
  - 清理旧 `passed` 队列中不能形成合法简历的中文项。
- `python/v2/c_resume_terminal_status.v2.py`
  - 对单个已人工确认的源文件写入指定终态。
- `python/v2/word_difficult_review_defer.v2.py`
  - 将自动解析失败或严格审计不通过的剩余项转为 `deferred_manual_review`，并生成 CSV/JSON 人工清单。

主要状态：

| 状态 | 含义 |
| --- | --- |
| `passed` | 已生成正式 JSON，源路径已登记 |
| `needs_review` | 自动处理队列中的待审项 |
| `deferred_manual_review` | 自动流程跳过，等待人工处理 |
| `pending_user_ocr` | 已复制到 OCR 目录，等待人工 OCR/解析 |
| `non_resume` | 已确认非简历或无效简历 |
| `identity_unrecoverable` | 无法恢复候选人身份；后续可回退为无效简历 |
| `superseded` | 已被更新版本替代 |

无效简历使用：

```text
status = non_resume
terminal_classification = invalid_resume
json_status = invalid_resume
```

## 7. OCR、unknown 和 failed 人工回填

### 复制待人工处理的源 Word

- `python/v2/c_resume_ocr_stage.v2.py`
  - 将指定类型的源 Word 复制到 `docs\ocr`；
  - 复制名包含源路径哈希，避免同名覆盖；
  - 更新状态为 `pending_user_ocr`。
- `python/v2/word_ocr_folder_refresh.v2.py`
  - 根据映射恢复 OCR 目录中缺少的副本；
  - 重写 OCR 清单。
- `python/v2/c_resume_unknown_stage.v2.py`
  - 按指定状态将源 Word 复制到 `unknown` 或 `failed`；
  - 生成 `unknown_manifest.json` 或 `failed_manifest.json`。

示例：

```powershell
python python\v2\c_resume_unknown_stage.v2.py `
  --progress <最新全局进度JSON> `
  --output-dir <项目根>\complete-transfered-htmls\docs\failed `
  --manifest <项目根>\complete-transfered-htmls\docs\failed\failed_manifest.json `
  --statuses deferred_manual_review pending_user_ocr
```

### 校验人工生成的 JSON

- `python/v2/c_resume_ocr_normalize.v2.py`
  - 根据 OCR 清单或 `unknown/failed` manifest 恢复原始源路径；
  - 修正旧字段，例如 `resume_languge` → `resume_language`；
  - 将顶层 `expected_info` 规范为对象；
  - 补齐列表字段及工作成就字段；
  - 按“姓名 + 手机/邮箱/无联系方式”重新命名；
  - 拒绝“待确认姓名”、脱敏姓名、无正文、无履历结构、非简历等结果；
  - 仅将有效 JSON 写入暂存目录。

### 正式登记人工 JSON

- `python/v2/c_resume_ocr_finalize.v2.py`
  - 将暂存 JSON 写入正式中文目录；
  - 支持一个 JSON 对应多个原始 Word；
  - 更新全部源路径为 `passed_user_ocr`；
  - 删除对应 HTML。

示例：

```powershell
python python\v2\c_resume_ocr_finalize.v2.py `
  --json-dir <校验合格暂存目录> `
  --map <项目根>\complete-transfered-htmls\docs\word_conversion_map.json `
  --document-manifest <ocr/unknown/failed清单> `
  --formal-dir <项目根>\complete-transfered-jsons\docs\中文 `
  --report <项目根>\_resume_qa\user_json_finalize_apply.json `
  --apply
```

### 人工批次对账和无效项清理

- `python/v2/word_batch_without_json_report.v2.py`
  - 比较批次 manifest 与输出 JSON 的 `source_files`；
  - 列出未被任何 JSON 认领的源 Word。
- `python/v2/word_invalid_unknown_terminalize.v2.py`
  - 将严格校验失败的 JSON 和对应源文件登记为 `invalid_resume`；
  - 删除对应 HTML。
- `python/v2/word_failed_batch_finalize.v2.py`
  - 处理 failed 批次无 JSON 输出项；
  - 标记无效源文件；
  - 删除无效工作副本、中间 JSON 和残留 HTML。

注意：清理的只是 `docs\ocr`、`docs\unknown`、`docs\failed` 中的工作副本及中间结果。不得删除 `需要采集的简历文件夹` 中的原始 Word。

## 8. 全局统计

### `python/v2/c_resume_global_progress.v2.py`

以 `word_conversion_map.json` 的原始源路径为基准，统计：

- 源文件总数；
- 正式 JSON 文件数；
- 正式 JSON 已覆盖的源路径数；
- 未完成源路径数；
- 各状态和语言目录数量；
- 正式目录中的无效 JSON。

示例：

```powershell
python python\v2\c_resume_global_progress.v2.py `
  --map <项目根>\complete-transfered-htmls\docs\word_conversion_map.json `
  --formal-root <项目根>\complete-transfered-jsons\docs `
  --output <项目根>\_resume_qa\global_docs_progress.json
```

统计关系必须满足：

```text
源文件总数 = 已生成正式 JSON 覆盖的源文件
            + 非简历/无效简历
            + 人工/OCR等待项
            + identity_unrecoverable
            + superseded
```

本次最终状态：

```text
源文件总数：14,019
正式 JSON 覆盖源文件：13,573
无效/非简历：445
被更新文件替代：1
自动 review / OCR / 人工疑难队列：0
```

即：

```text
13,573 + 445 + 1 = 14,019
```

正式 JSON 文件数为 13,539，少于 13,573 个完成源路径，是因为部分候选人的重复或多语言 Word 已合并到同一个 JSON。

## 9. 推荐复跑顺序

1. 备份 `word_conversion_map.json`。
2. 运行 `c_resume_html_dom_common.v2.py` 生成 HTML 和映射。
3. 按语言目录检查 HTML，必要时运行语义 DOM 修复程序。
4. 使用对应语言解析器写入独立暂存目录，禁止直接写正式目录。
5. 运行结构筛选程序。
6. 运行中文或非中文源文件审计。
7. 修复可确定的问题并再次审计。
8. 使用对应 `promote` 程序写入正式目录。
9. 使用 `c_resume_source_finalize.v2.py` 更新映射并删除已完成 HTML。
10. 将剩余疑难项复制到 OCR/unknown/failed，人工处理。
11. 人工 JSON 先运行 `c_resume_ocr_normalize.v2.py`。
12. 有效项运行 `c_resume_ocr_finalize.v2.py`；无效项写入 `invalid_resume` 终态。
13. 最后运行 `c_resume_global_progress.v2.py`，确保全部源路径均有明确归属。

## 10. 重要注意事项

- 不要把解析器“成功输出”直接当作有效简历。
- 不要把公司名、职位、目录名、募集内容或“待确认姓名”当作姓名。
- 不要仅凭姓名复用历史 JSON；必须审计联系方式和主要履历字段。
- 多语言简历应在 `structured_data.resumes` 中保留各语言版本。
- `expected_info`、`current_info`、`education_info` 是顶层快照，应与第一份主语言简历同步。
- 工作、教育、项目、培训、证书等必须是结构化列表。
- `raw_text` 必须存在，且应覆盖 JSON 中的主要结构化值。
- 图片简历交给 OCR，不在 Word→HTML 阶段保留照片。
- 已完成项做增量处理，不重复覆盖正式 JSON。
- 删除任何 HTML 或工作副本前，必须先确认正式 JSON 已写入且源路径已登记。
- 原始 Word 永远保留；只能删除转换目录中的副本和中间文件。

## 11. v2 文件命名与 V1 兼容关系

原始脚本全部保留。为便于核对，新增带统一类别前缀的 v2 对照文件：

| 原脚本 | v2 对照文件 | 类别 |
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
| `process_word_to_html.py` | `python/v2/c_resume_html_dom_common.v2.py` | 通用 |
| `process_word_html_to_json.py` | `python/v2/c_resume_html_to_json_common.v2.py` | 通用 |
| `reuse_complete_v1_jsons.py` | `python/v2/reuse_complete_v1_jsons.py` | 通用 |
| `audit_chinese_json_against_sources.py` | `python/v2/audit_chinese_json_against_sources.py` | 通用 |

通用类别统一使用 `c_` 前缀。完整映射见 [`v2-name-mapping.cn.md`](v2-name-mapping.cn.md)。
