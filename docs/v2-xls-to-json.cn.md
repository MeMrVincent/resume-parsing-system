# XLS 转 JSON 流程说明

[English](v2-xls-to-json.md) | **简体中文** | [日本語](v2-xls-to-json.ja.md)

> 本文档描述 V2（word/xls/pdf/html → JSON）流程。目录默认值见根目录 `config.example.json`；文中的 `<项目根>` 即 config 里的 project_root。已合并的重复脚本见 [`v2-name-mapping.cn.md`](v2-name-mapping.cn.md) 末尾。

## 1. 目标和范围

本流程用于把 Excel 简历文件（`.xls`、`.xlsx`）转换为带语义 DOM 的 HTML，再从 HTML 解析为统一的简历 JSON。XLS 的表格布局差异很大，因此 HTML 不是中间展示文件，而是解析的事实来源：字段必须先在 HTML DOM 中绑定正确，JSON 只负责读取和归一化这些节点。

本流程重点处理：

- 中文、日文、英文及中日/中英双语简历；
- 横向、纵向、混合方向的 Excel 表格；
- 左右并排的两份语言简历；
- 姓名、联系方式、基础信息、求职意向、工作、教育、证书、语言、技能、项目和自我评价；
- 源文件落地时间、源路径、HTML 路径和 JSON 路径的可追溯记录；
- HTML、JSON、源 XLS 三者之间的逐字段校验。

原始 XLS 永远保留。可以清理 `passed`、`review` 中的转换副本和中间结果，但不能删除原始采集目录中的 XLS。

## 2. 目录和文件

### 2.1 输入和映射

| 内容 | 路径 |
| --- | --- |
| Excel 盘点报告 | `<项目根>\32718文件报告.xlsx` |
| 原始 XLS/XLSX | `<项目根>\需要采集的简历文件夹` 及其子目录 |
| XLS 转换映射 | `<项目根>\complete-transfered-htmls\xls\xls_conversion_map.json` |
| HTML 转换汇总 | `<项目根>\complete-transfered-htmls\xls\xls_conversion_summary.json` |

`xls_conversion_map.json` 是源文件级主索引。每条记录至少包含：

```json
{
  "source_path": "原始 XLS 绝对路径",
  "filename": "盘点报告中的文件名",
  "download_date": "源文件落地时间",
  "html_path": "生成的 HTML 路径",
  "phone": "从源表格确认的手机",
  "email": "从源表格确认的邮箱",
  "status": "passed / needs_review / not_resume / failed",
  "language_folder": "中文 / 日文 / 中日文 / 中英文 ...",
  "languages": ["zh", "en"],
  "resume_count": 1,
  "validation": {}
}
```

### 2.2 HTML 工作目录

```text
<项目根>\complete-transfered-htmls\xls\passed
<项目根>\complete-transfered-htmls\xls\review
```

联系方式至少存在手机或邮箱之一的 XLS，通常进入 `passed`；没有可确认联系方式、无法形成有效简历或转换失败的文件进入 `review`、`not_resume` 或 `failed`。

### 2.3 正式 JSON 和报告

```text
<项目根>\complete-transfered-jsons\xls\中文
```

当前中文 XLS JSON 的主报告和审计报告位于该目录：

```text
_xls_html_to_json_v3_report.json
_xls_html_to_json_v3_post_audit.json
_xls_side_by_side_reprocess_report.json
_xls_incremental_reprocess_report.json
_xls_html_to_json_v3_bidirectional_review.json
```

JSON 文件名采用：

```text
姓名_手机.json
姓名_邮箱.json
姓名_无联系方式.json
```

同名冲突时追加源文件哈希或序号。手机号码在文件名和 JSON 中会去除横杠、空格等格式；明确的国际号码保留国家代码分隔，例如 `+86-13800000004`。

## 3. 总体链路

```text
32718文件报告.xlsx / 原始 XLS
        │
        ├─ xls_conversion_map.v2.py
        │       ↓
        │   xls_conversion_map.json
        │
        ├─ process_xls_to_html.py
        │       ↓ 读取 Excel 网格、分类语言、提取联系方式、生成语义 HTML
        │   passed/*.html 或 review/*.html
        │
        ├─ xls_to_html_to_json.v2.py
        │       ↓ 重建 DOM、绑定字段、按语言解析、归一化、校验
        │   complete-transfered-jsons/xls/中文/*.json
        │
        ├─ xls_json_audit.v2.py
        │       ↓ JSON / HTML / 映射 / 联系方式 / 语言版本审计
        │
        ├─ xls_bidirectional_review.v2.py（需要时）
        │       ↓ 与 complete-v1 旧 JSON 按源路径互相 review
        │
        └─ xls_report_rebuild.v2.py
                ↓
            最终总报告
```

重要原则：HTML 先正确，JSON 后解析。不能只修改 JSON 提取规则来掩盖 HTML DOM 没有分段或字段绑定错误的问题。

## 4. 第一步：建立 XLS 源文件清单

### `python/v2/xls_conversion_map.v2.py`

该程序读取 `32718文件报告.xlsx` 的 `Excel表格 (.xls, .xlsx)` 工作表，建立源文件级映射。它不解析简历正文，也不生成 JSON。

运行：

```powershell
cd <项目根>
python python\xls_conversion_map.v2.py
```

只有在盘点报告发生变化、需要重新建立源文件索引时才运行。日常增量处理应复用已有 `xls_conversion_map.json`，避免丢失已完成状态、源文件落地时间和 HTML 路径。

## 5. 第二步：XLS 转语义 HTML

### `python/v2/process_xls_to_html.py`

这是 Excel 网格到 HTML 的转换器。它复用最新版 Word→HTML 的生成器、HTML schema 和版本信息，避免 XLS 与 Word 产生两套不一致的 DOM 规则。

主要工作：

1. 使用 `xlrd` 读取 `.xls`，使用 `openpyxl` 读取 `.xlsx`；
2. 保留单元格行列关系、合并单元格、横向/纵向布局和原始文本；
3. 识别姓名、手机、邮箱，并用“手机或邮箱至少一个”作为有效简历的基本门槛；
4. 识别中文、日文、英文及多语言证据；
5. 按表格内容选择 `中文`、`日文`、`中日文`、`中英文` 等语言目录；
6. 生成 `resume-record`、`section`、`table`、`tr`、`td` 等 DOM 节点；
7. 写入源文件路径、HTML 路径、源文件落地时间、语言分类、转换版本和基础校验；
8. 将当前版本 HTML 放到 `passed` 或 `review`，并更新 `xls_conversion_map.json`。

试跑前 100 条：

```powershell
python python\process_xls_to_html.py --limit 100
```

全量生成：

```powershell
python python\process_xls_to_html.py --limit 0
```

强制重建已有 HTML：

```powershell
python python\process_xls_to_html.py --limit 100 --force
```

默认不覆盖已经是当前生成器版本的 HTML；只有确认需要重建 DOM 时才使用 `--force`。

## 6. HTML 语义 DOM 规则

### 6.1 基本结构

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

解析器主要依赖以下属性：

| 属性 | 作用 |
| --- | --- |
| `data-role="resume"` | 标识一份候选人简历根节点 |
| `data-language-code` | 标识 `zh`、`en`、`jp` 等语言层级 |
| `data-language-count` | 标识表格是否可能包含多语言版本 |
| `data-section-type` | 标识 `base_info`、`education_list`、`work_experiences` 等语义区段 |
| `data-collection` | 标识列表型字段集合 |
| `data-record-type` | 标识一条工作、教育、证书等记录 |
| `data-field` | 标识具体字段，例如 `company_name`、`school_name` |
| `label` / `data-label-for` | 保存字段的原始表头证据 |

### 6.2 左右并排双语表格

左右各一份简历时，不能把整行同时绑定到一个语言。`repair_html()` 中的 `split_side_by_side_bilingual_dom()` 会根据列范围拆分：左侧保留中文节点，右侧复制为英文/日文节点，并分别设置 `data-language-code`。

因此类似下面的源表格会形成两个语言层：

```text
左侧：姓名 张三 / 工作经验 / 教育经历
右侧：Name Zhang San / Work Experience / Education Background
```

最终 JSON 必须在 `structured_data.resumes` 中保留两个版本；翻译后的姓名也要保留，例如中文 `张三`、英文 `Zhang San`，不能把第一个语言的姓名覆盖所有语言。

### 6.3 表头演示信息

Excel 顶部常见的演示表头或候选字段说明，例如：

```text
2014 男 1960 54 女 独身子なし 月収 年収 ネイティブ...
語学レベル 日本語 英語 中国語 上海語
```

这些是模板 demo，不是候选人数据。DOM 绑定阶段应清理或忽略，不应生成基础信息、语言记录、证书或工作记录。

## 7. 第三步：HTML 解析为 JSON

### `python/v2/xls_to_html_to_json.v2.py`

这是当前 XLS→JSON 的新入口。它没有修改旧的 Word 解析主流程，而是复用 Word 的 HTML schema、日期归一化、列表结构和通用校验，再加入 XLS 专用 DOM 修复。

典型全量命令：

```powershell
python python\xls_to_html_to_json.v2.py `
  --map <项目根>\complete-transfered-htmls\xls\xls_conversion_map.json `
  --output-dir <项目根>\complete-transfered-jsons\xls\中文 `
  --passed-dir <项目根>\complete-transfered-htmls\xls\passed `
  --review-dir <项目根>\complete-transfered-htmls\xls\review
```

试跑前 100 条：

```powershell
python python\xls_to_html_to_json.v2.py `
  --map <项目根>\complete-transfered-htmls\xls\xls_conversion_map.json `
  --output-dir <项目根>\complete-transfered-jsons\xls\中文 `
  --passed-dir <项目根>\complete-transfered-htmls\xls\passed `
  --review-dir <项目根>\complete-transfered-htmls\xls\review `
  --limit 100
```

### 7.1 `process_row()` 的实际调用顺序

对每个源 XLS，`process_row()` 大致按以下顺序执行：

1. 调用 `process_xls_to_html.py` 中的 `convert_single_excel_detailed()` 重新生成或取得当前 HTML；
2. 执行 `repair_html()`，补充语义区段和字段节点；
3. 清理错误姓名、错误联系方式和日期/公司绑定；
4. 调用 `parse_html_record()`，按语言层解析基础信息和列表；
5. 合并 DOM 中明确绑定的工作、教育、语言、PR、证书节点；
6. 对左右并排语言分别修复姓名，避免中文姓名覆盖英文/日文姓名；
7. 去掉表头 demo、地址/户口/政治面貌串入值、日期串入公司名等非法值；
8. 过滤实习、兼职、学生实践、社团、球队、活动等非正式证书条目；
9. 按日期将教育和工作经历整理为最新到最早；
10. 规范手机、邮箱、日期和文件名；
11. 将修复后的完整 HTML 写入 `raw_text`；
12. 将 `source.html_path`、`source.html_filename`、`source.source_landing_time` 写入 JSON；
13. 运行 `valid_rule_issues()`，成功项写入正式中文 JSON 目录，问题项标记 `needs_review`。

### 7.2 目前复用的核心模块

- `process_xls_to_html.py`：Excel 网格读取和 HTML 生成；
- `c_resume_html_to_json_common.v2.py`：HTML 基础解析、日期、姓名、顶层快照和列表 schema；
- `reuse_complete_v1_jsons.py`：通用 `validate_json()`；
- `c_resume_html_dom_common.v2.py`：HTML 版本、清理和文本工具；
- `classify_passed_html_by_language.py`：语言证据和目录分类。

## 8. JSON 结构和字段规则

正式 JSON 的核心结构如下：

```json
{
  "source": {
    "original_path": "源 XLS 绝对路径",
    "html_path": "最终 HTML 绝对路径",
    "html_filename": "HTML 文件名",
    "source_landing_time": "源文件落地时间",
    "resume_index": 1,
    "resume_count": 1
  },
  "dates": {
    "resume_download_date": "源文件落地时间",
    "resume_updated_date": "简历更新时间",
    "sys_created_date": "系统创建时间",
    "sys_updated_date": "系统更新时间"
  },
  "structured_data": {
    "base_info": {},
    "expected_info": {},
    "current_info": {},
    "education_info": {},
    "resumes": []
  },
  "raw_text": "修复后 HTML 的文本快照"
}
```

`resumes` 中每个语言版本包含：

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

字段判断不是“有值就通过”，而是“有值且有源 HTML 证据、字段类型合法、没有表头/demo 串入”才通过。

### 联系方式

- 手机或邮箱至少有一个才作为有效简历候选；
- 顶部平台联系方式只有在源 HTML 中能与候选人记录对应时才使用；
- 手机去除中间横杠、空格和括号；
- 国际号码保留国家代码，例如 `+81-8012345678`；
- 联系方式不能被地址、政治面貌、模板表头覆盖。

### 教育和工作

教育按“时间、学校、专业、学历”绑定；工作按“时间、公司、公司行业/性质、部门、职位、工作内容、离职理由”等绑定。教育和工作默认按结束时间或开始时间从最新到最早排序。

实习经历、学生会/社团活动、兼职、校内实践等与正式职业履历无关的内容不进入正式工作或证书列表，除非源文件明确把它作为正式工作经历且满足业务规则。

### 证书、语言和技能

证书必须有证书语义和源文本证据。语言 demo、技能标签、软件名称、校园活动名称不能误认成证书。语言版本和语言能力等级分开存储，语言表格的横向/纵向布局必须以 DOM 单元格位置为依据。

### `raw_text`

`raw_text` 来源是修复后的 HTML 文本，不是 JSON 序列化结果。这样可以在后续审计时回到 HTML 现场，判断字段是否真的来自源 DOM。

## 9. 增量重跑和专项修复

### 左右并排双语批次

```powershell
python python\xls_side_by_side_reprocess.v2.py
```

该脚本扫描现有 XLS JSON 和 HTML，识别 `data-language-count="2"`、`data-language-variants` 或左右五列中英文表格，按源路径去重后重新执行 `process_row()`。报告写入：

```text
complete-transfered-jsons\xls\中文\_xls_side_by_side_reprocess_report.json
```

重点指标：`selected_sources`、`success`、`needs_review`、`failed`、`valid_language_variants`。

### 泛化异常增量

```powershell
python python\xls_incremental_reprocess.v2.py
```

该脚本针对以下异常重建：

- 基础信息出现模板表头；
- 工作经历为空但 HTML 有工作语义节点；
- 双语 HTML 缺少英文/日文语言节点；
- 教育经历仍是标题长文本；
- 自我评价标题重复正文；
- 姓名或联系方式明显异常。

报告写入：

```text
complete-transfered-jsons\xls\中文\_xls_incremental_reprocess_report.json
```

### 与 `complete-v1` 互相 review

```powershell
python python\xls_bidirectional_review.v2.py
```

该步骤按 `source.original_path` 精确匹配 `<项目根>\complete-v1` 中的历史 JSON。历史 JSON 只能作为候选参考：某个字段只有在旧 JSON 更完整、源 HTML 有证据且没有占位符时，才允许合并。不能只凭姓名相同覆盖当前源文件解析结果。

报告写入：

```text
complete-transfered-jsons\xls\中文\_xls_html_to_json_v3_bidirectional_review.json
```

## 10. 校验和报告

### 基础 JSON 审计

```powershell
python python\xls_json_audit.v2.py
```

该审计逐个检查：

- JSON 是否可读取；
- 源 XLS 是否能在映射中找到；
- HTML 是否存在；
- 姓名、联系方式是否有证据；
- 语言版本是否合理；
- 工作、教育、证书、语言等列表是否为合法结构；
- 日期和公司名是否被错位；
- JSON 与 HTML 的主要字段是否一致。

输出：

```text
complete-transfered-jsons\xls\中文\_xls_html_to_json_v3_post_audit.json
```

### 严格字段审计

需要更细的 DOM→JSON 对照时使用：

```powershell
python python\xls_field_audit.v2.py
```

该程序逐语言收集 HTML `data-field`，再与 JSON 的基础字段和列表字段逐项比较。日期允许不同展示格式，但不允许年份、月份、公司、学校错位。

### 重建总报告

```powershell
python python\xls_report_rebuild.v2.py
```

它根据最新审计结果重建：

```text
_xls_html_to_json_v3_report.json
```

总报告中的 `total` 是映射记录数量，不等于 JSON 数量。`not_resume` 包括没有联系方式、模板、岗位说明、公司资料等不应进入简历 JSON 的记录。

## 11. 推荐操作顺序

1. 确认原始 XLS 仍在采集目录，备份 `xls_conversion_map.json`。
2. 盘点报告有变化时运行 `xls_conversion_map.v2.py`。
3. 先小批量运行 `process_xls_to_html.py --limit 100`，检查 HTML DOM。
4. 确认 DOM 中的语言、section、record、data-field 正确后，再运行 XLS→JSON。
5. 先输出 100 条 JSON，检查源 XLS、HTML、JSON 三者是否一致。
6. 运行 `xls_json_audit.v2.py`，修复审计发现的问题。
7. 对左右并排双语模板运行 `xls_side_by_side_reprocess.v2.py`。
8. 对其余异常运行 `xls_incremental_reprocess.v2.py`。
9. 必要时与 `complete-v1` 做源路径级双向 review。
10. 再次运行全量审计和 `xls_report_rebuild.v2.py`。
11. 确认审计通过后，才把结果交给下游系统使用。

## 12. 常见问题和处理方式

### JSON 有值，但值明显不合法

先看 HTML 是否把表头、日期、公司和内容绑定到了错误的 `data-field`。如果 DOM 错误，应修复 `repair_html()` 或生成阶段的绑定，不要只在 JSON 阶段拼接字符串。

### 中文和英文混在同一份 `resume`

检查 `data-language-code`、`data-language-count`、`data-language-variants`，以及左右表格的列范围。使用 `xls_side_by_side_reprocess.v2.py` 重新生成 DOM，确保每个语言拥有独立 section。

### 工作经历为空

检查 HTML 的 `work_experiences` section 是否有 `company_name`、日期和 `position_responsibilities` 节点。若源表把正式经历放到项目标题中，`bind_project_as_work_when_work_empty()` 会在确认公司、时间和内容后补充正式工作节点。

### 证书出现实习或社团活动

这是模板 demo 或校园活动被误绑定。检查 `certificate_list` 和对应 HTML 节点，使用当前 `sanitize_record()` 规则清除实习、兼职、社团、球队、活动等非证书内容。

### 审计通过但仍然担心字段错位

不要只看 `valid`。打开对应源 XLS、HTML 和 JSON，对姓名、联系方式、教育、工作、证书、语言和 PR 逐字段核对；必要时运行 `xls_field_audit.v2.py` 和 `xls_bidirectional_review.v2.py`。

## 13. 版本和维护约定

- XLS HTML 生成器版本由 `process_xls_to_html.py` 复用 Word 生成器版本；
- 当前 XLS 规则版本记录为 `xls-word-dom-3-language`；
- JSON 解析入口固定为 `python/v2/xls_to_html_to_json.v2.py`；
- 新增字段时先修改 DOM 绑定和字段别名，再修改 JSON 归一化；
- 修改 DOM 规则后必须至少重跑一个中文、一个日文、一个中英/中日并排样本；
- 批量重跑后必须执行全量审计，并保留专项报告；
- 原始 XLS、源文件落地时间、源路径和 HTML 路径是后期核对的最小追溯信息，不能删除或覆盖。

## 14. v2 文件命名与共用模块

原始 XLS 脚本全部保留。新增 XLS 类别统一使用 `xls_` 前缀：

| 原脚本 | v2 对照文件 |
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

Word/XLS 共用能力统一使用 `c_` 前缀，例如：

```text
reuse_complete_v1_jsons.py
classify_passed_html_by_language.py
audit_chinese_json_against_sources.py
c_resume_html_dom_common.v2.py
c_resume_html_to_json_common.v2.py
```

完整文件映射见 [`v2-name-mapping.cn.md`](v2-name-mapping.cn.md)。带点的 `.v2.py` 文件用于命名核对和命令行入口；需要被 Python `import` 时，使用对应的 `_v2.py` 合法模块名。

XLS 主流程暂不直接替换旧入口。v2 文件先作为行为一致的对照副本，避免仅改名造成流程变化；后续完成公共函数迁移和回归验证后，再切换生产调用。
