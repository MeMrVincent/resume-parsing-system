# resume-parsing-system

[English](README.md) | **简体中文** | [日本語](README.ja.md)

把成千上万份格式各异的简历（Word / Excel / PDF / 网页 HTML，中文、日文、英文、德文混杂）整理成**一人一份、结构统一的 JSON**，并给出可审计的清洗、合并、多语言对齐结果。

> 本仓库只含**代码和文档**，不含任何真实简历或个人信息。`examples/` 里的人物、手机号、邮箱、公司全部是虚构的。

## 它做什么

```
原始简历文件 ──V2──▶ 每份文件一个 JSON ──V3──▶ 一人一份 JSON（可审计）
(doc/xls/pdf/html)   (complete-v2 / v1)        (formal / needs_fix / pending_translation)
```

- **基础与管理**（Google Antigravity 编写）：负责第一版基础代码编写，以及最后版本代码的整理重构与 Git 项目规范管理。
- **V2**（`python/v2/`，Codex 编写）：把 Word、XLS、PDF、网页 HTML 转成 HTML，再解析成统一 schema 的 JSON，并带多轮审计。说明见 `docs/v2-*.md`。
- **V3**（`python/v3/`，Claude 编写）：以手机号/邮箱认定同一个人，把 V2（主）和 V1（辅）的 JSON 合并成一人一份；多语言简历（中/日/英/德）各语言版本逐项对齐；独立审计（30 项检查）；`raw_text` 按固定规则生成。说明见 `docs/v3-pipeline.md`。
- **common**（`python/common/`）：统一配置读取 `rc_config.py` 和代码静态检查 `check_code.py`。

## AI 协同开发说明

本项目全链路代码、文档及工程化均由 AI 协同完成，具体分工如下：

- **Google Antigravity**：负责第一版的基础代码编写，以及最后版本代码的整理重构、三语国际化与 Git 项目的管理。
- **OpenAI Codex**：负责 V2 核心多源格式（Word / Excel / PDF / HTML）文件抽取、HTML 清洗与规则解析脚本迭代。
- **Anthropic Claude**：负责 V3 核心合并管道设计、手机/邮箱唯一主体归并、中日英多语言字段对齐算法与 30 项质量审计系统。

## 目录结构

```
resume-system/
├─ README.md  README.cn.md  README.ja.md  LICENSE  requirements.txt
├─ config.example.json        配置模板（复制为 config.json 后修改）
├─ python/
│  ├─ common/                 配置、静态检查
│  ├─ v2/                     Word/XLS/PDF/HTML → JSON（含 resume_importer 依赖库）
│  └─ v3/                     合并、解析、审计、多语言对齐
├─ scripts/                   Windows 双击入口（merge.cmd 等）
├─ docs/                      说明文档、代码索引
├─ examples/                  虚构示例数据和示例输出
└─ repair_data/               一次性修复脚本用的个人数据（不提交，只有格式示例）
```

## 快速开始

1. 安装 Python 3.13。V3 合并/审计只用标准库；V2 需要第三方库：`pip install -r requirements.txt`。
2. 复制 `config.example.json` 为 `config.json`，按需修改（见下）。
3. 先用示例数据体验一遍（不需要任何真实数据）：

```bash
python examples/make_examples.py
python python/v3/claude_merge.v3.py --v2-dir examples/v2 --v1-dir examples/v1 --out-root examples/out --run-id 20260101-demo
python python/v3/claude_merge_audit.v3.py --run-dir examples/out/20260101-demo --v2-dir examples/v2 --v1-dir examples/v1
```

   4 份示例会得到：2 份 `formal`（陈思明：V2 与 V1 合并；林雅婷：中英双语）、1 份 `pending_translation`（John Smith：只有英文版，缺中文主版本）、1 份因没有联系方式记入 `ledgers/no_contact_ledger`。结果样例见 `examples/output/`。

4. 跑自己的数据：把 V2/V1 的 JSON 放到配置里的 `v2_dir`、`v1_dir`，然后运行
   - Windows：双击 `scripts/merge.cmd`（合并 → 见证合并 → 审计）；
   - 其他系统：用上面的两条 `python` 命令（不带示例路径即读取配置）。
5. 审计通过（`reports/audit.json`、全部检查为 0）后，可用 `python python/v3/copy_to_v3.py` 把 `formal/` 复制到 `v3_dir`。

## 配置（config.json）

所有路径都来自一个 `config.json`，**不再写死盘符**。查找顺序：环境变量 `RESUME_CONFIG` → `<项目根>/config.json` → `<项目根>/python/config.json`；找不到则用默认值。命令行参数优先于配置。

| 键 | 默认 | 含义 |
|---|---|---|
| `project_root` | 空（自动 = `python` 的上一级） | 项目/数据根目录；也可用环境变量 `RESUME_ROOT` 覆盖 |
| `source_dir` | `需要采集的简历文件夹` | 原始简历文件夹（只读）。**换成你自己的文件夹名或绝对路径即可** |
| `html_dir` | `complete-transfered-htmls` | V2 中间 HTML |
| `v1_dir` / `v2_dir` | `complete-v1` / `complete-transfered-jsons` | 合并的辅助 / 主来源 JSON |
| `v3_dir` | `complete-v3` | 最终成品 |
| `output_dir` | `output` | 运行输出根目录 |
| `merge_out_dir` | `output/merge-v3` | 合并运行输出 |
| `repair_dir` | `output/source-repair-v3` | 修复副本目录（取其中名字最新的子目录） |
| `align_dir` | `claude-align` | 多语言对齐工作目录 |
| `python_exe` | `python` | .cmd 入口使用的解释器 |
| `path_map` | `{}` | 成品 JSON 里记录的来源路径（`original_path`/`html_path`）失效时的换算表：`{"旧路径前缀": "新位置"}`，新位置里 `{root}` 代表项目根。例：`{"E:\\resume-system\\codex-transfered-htmls": "{root}/complete-transfered-htmls"}`。只用于找文件/检查是否存在，不改写 JSON |
| `dir_names` | `{}` | 额外的目录改名映射，例如 `{"complete-transfered-jsons": "my-json"}`（V2 脚本里写死的目录名都经过它换算） |

相对路径相对 `project_root`；绝对路径原样使用。

## 常用命令

| 目的 | 命令 |
|---|---|
| 合并 + 审计（Windows 双击） | `scripts/merge.cmd` |
| 复制 formal 到 v3_dir | `scripts/copy_to_v3.cmd` |
| 静态检查全部代码（语法、import、文件名引用） | `python python/common/check_code.py` 或 `scripts/check_code.cmd` |

## JSON 字段说明

本节说明 V3 输出的一人一份 JSON（`formal/*.json`）。V2 输出的每文件 JSON 使用相同的 `structured_data` 结构，其他顶层对象的差异列在本节末尾。

### 通用约定

- **简历内日期**统一为 `YYYY年MM月DD日`（如 `2017年09月01日`），不完整的日期自动补齐（`2010/4` → `2010年04月01日`）。`resume_updated_date`、`resume_download_date` 为 `YYYY-MM-DD HH:MM:SS`；系统时间为 ISO 8601。
- **字段值保持原文语言**。中文主版本的枚举值用中文（如 `全职`、`在职`）。
- **列表字段不得为 `null`**，无数据时为 `[]`。对象快照（`expected_info`、`current_info`、`education_info`）始终包含全部键，缺失值为 `""`。
- 只填写有原文依据的值，不得臆造。

### 顶层结构

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
  "raw_text": "<原始文本全文>",
  "quality": { ... },
  "merge_info": { ... }
}
```

| 字段 | 类型 | 说明 |
|---|---|---|
| `schema_version` | string | Schema 版本：V3 为 `resume-merge-v3.0`，V2 为 `codex-resume-json-1.0` |
| `record_id` | string | 记录唯一标识（V3 为 `merge-v3-<group_id>`；V2 为 SHA-256 哈希） |
| `source` | object | 源文件信息 |
| `dates` | object | 简历日期与系统时间 |
| `extraction` | object | 生成过程信息 |
| `classification` | object | 文档分类 |
| `structured_data` | object | 结构化数据（核心） |
| `raw_text` | string | 纯文本全文，用于全文搜索和关键词匹配 |
| `quality` | object | 质量概要 |
| `merge_info` | object | 合并信息（仅 V3） |

### `source` 源文件信息

| 字段 | 类型 | 说明 |
|---|---|---|
| `original_path` | string | 原始 Word/PDF/XLS/HTML 文件路径 |
| `html_path` | string | 中间 HTML 路径（可为空） |
| `source_count` | number | 合并进本记录的输入 JSON 数量 |
| `source_files` | array | 每个输入 JSON 一条（见下表） |

`source_files` 每条：

| 字段 | 类型 | 说明 |
|---|---|---|
| `index` | number | 该输入在组内的序号 |
| `version` | string | `v2` 或 `v1` |
| `json_path` | string | 输入 JSON 路径 |
| `sha256` | string | 输入 JSON 字节的 SHA-256 |
| `duplicate_paths` | array | 内容完全相同的其他输入 |
| `original_path` / `html_path` | string | 该输入的原件和中间 HTML |
| `resume_updated_date` | string | 该输入的简历更新日期 |
| `languages` | array | 该输入包含的语言代码（如 `["zh", "en"]`） |

### `dates` 日期信息

| 字段 | 类型 | 说明 |
|---|---|---|
| `resume_updated_date` | string | 简历更新日期，`YYYY-MM-DD HH:MM:SS`。优先取正文明确的更新时间，正文无值时取 HTML 文件历史修改时间；不得留空，也不得用本次处理时间冒充 |
| `resume_download_date` | string | 简历下载/投递日期，格式与取值规则同上 |
| `resume_updated_date_source` | string | 更新日期来源说明（`文档正文更新时间` 或 `HTML文件修改时间（历史资料替代）`） |
| `resume_download_date_source` | string | 下载日期来源说明 |
| `sys_created_date` | string | 系统创建时间（ISO 8601，如 `2026-07-31T11:06:00+09:00`） |
| `sys_updated_date` | string | 系统更新时间（ISO 8601） |

### `extraction` 生成过程信息

| 字段 | 类型 | 说明 |
|---|---|---|
| `merger` | string | V3：合并脚本（`claude_merge.v3.py`） |
| `rule_version` | string | V3：合并规则版本（如 `merge-v3.0-contact-key`） |

V2 记录改用 `reader_group`、`converter`、`parser`、`status`（`success` / `failed`）、`html_path`、`dom`（`heading_count`、`table_count` 等 DOM 统计）。

### `classification` 文档分类

| 字段 | 类型 | 说明 |
|---|---|---|
| `document_type` | string | `resume` / `jd` / `contract` / `unknown` |
| `reason` | string | 分类原因 |

### `structured_data` 结构化数据

顶层快照**一律由 `resumes[0]`（中文主版本）重构**，不允许与之不一致：

| 快照 | 来源 |
|---|---|
| `base_info` | `resumes[0].base_info` |
| `expected_info` | `resumes[0].expected_list[0]`；列表为空时补齐 8 个空字段 |
| `current_info` | `resumes[0].work_experiences` 中最近一段；没有时补齐 15 个空字段 |
| `education_info` | `resumes[0].education_list` 中学历等级最高、时间最新的一段；没有时补齐 7 个空字段 |

#### `base_info` 基本信息（20 字段）

| 字段 | 类型 | 说明 |
|---|---|---|
| `full_name` | string | 候选人姓名 |
| `gender` | string | 性别（`男` / `女`） |
| `age` | string | 年龄 |
| `birth_date` | string | 出生日期（`YYYY年MM月DD日`） |
| `birth_year` | string | 出生年份 |
| `marital_status` | string | 婚姻状况 |
| `children_status` | string | 子女状况 |
| `political_status` | string | 政治面貌 |
| `height_cm` | string | 身高（厘米） |
| `weight_kg` | string | 体重（公斤） |
| `household_registration` | string | 户籍所在地 |
| `address` | string | 现居住地址 |
| `postal_code` | string | 邮政编码 |
| `platform_from` | string | 来源平台（如 `前程无忧(51job)`） |
| `platform_resume_id` | string | 平台简历 ID（猎聘为 12 位） |
| `phone` | string | 手机号码 |
| `email` | string | 电子邮箱 |
| `city` | string | 所在城市 |
| `nationality` | string | 国籍 |
| `pr` | string | 自我评价/个人优势 |

#### `expected_info` / `expected_list` 求职意向（8 字段）

| 字段 | 类型 | 说明 |
|---|---|---|
| `expected_city` | string | 期望城市 |
| `expected_position` | string | 期望职位 |
| `expected_salary` | string | 期望月薪 |
| `expected_annual_salary_min` | string | 期望年薪下限 |
| `expected_annual_salary_max` | string | 期望年薪上限 |
| `expected_industry` | string | 期望行业 |
| `expected_employment_type` | string | 期望工作性质（`全职` / `兼职` / `实习` / `remote` / `混合办公`） |
| `expected_start_date` | string | 到岗时间 |

#### `current_info` 当前工作信息（15 字段）

与 `work_experiences` 条目的前 15 个字段（`company_name` 至 `position_resigned`）相同。

#### `education_info` / `education_list` 教育经历（7 字段）

| 字段 | 类型 | 说明 |
|---|---|---|
| `school_name` | string | 学校名称 |
| `school_major_name` | string | 专业名称 |
| `school_degree_type` | string | 学历类型（`博士后` / `博士` / `硕士` / `本科` / `大专` / `高中` / `中专` / `初中` / `小学`） |
| `school_degree_rank` | string | 学历等级 `1`-`7`（映射见下） |
| `school_education_type` | string | 培养方式（`全日制研究生` / `全日制大学` / `全日制大专` / `全日制高中` / `全日制中专` 等） |
| `school_start_ym` | string | 入学时间（`YYYY年MM月01日`） |
| `school_end_ym` | string | 毕业/结业时间 |

`school_degree_rank` 映射：`7` 博士后、`6` 博士、`5` 硕士、`4` 本科、`3` 大专、`2` 高中/中专、`1` 初中及以下。

### `resumes` 简历语言版本列表

- `resumes[0]` 固定为中文主版本（`resume_languge = "zh"`），必须是真实中文内容。
- 英文、日文、德文等原始外文版本从 `resumes[1]` 开始，标注真实语种。
- 纯外文简历：`resumes[0]` 为字段级中文翻译，`resumes[1]` 完整保留外文原版。
- 各语言版本结构完全一致、深度独立（不共享引用），列表条目尽量一一对应。
- 所有列表按“一段一条”构造，不得把整份原文塞进单条经历。

| 字段 | 类型 | 说明 |
|---|---|---|
| `resume_languge` | string | 语言代码（`zh` / `en` / `jp` / `de` 等）。输出沿用历史拼写；`resume_language` 只作兼容读取 |
| `base_info` | object | 基本信息（同顶层 `base_info`） |
| `expected_list` | array | 求职意向列表 |
| `work_experiences` | array | 工作经历列表 |
| `education_list` | array | 教育经历列表 |
| `certificate_list` | array | 证书列表 |
| `language_list` | array | 语言能力列表 |
| `skills_list` | array | 技能列表 |
| `training_list` | array | 培训经历列表 |
| `project_list` | array | 项目经历列表 |
| `communication_list` | array | 沟通记录列表 |

#### `work_experiences` 工作经历（18 字段/条）

| 字段 | 类型 | 说明 |
|---|---|---|
| `company_name` | string | 公司全称（剥离时间后缀与竖线） |
| `company_employees` | string | 公司规模（如 `100-499人`、`未填写`） |
| `company_industry` | string | 所属行业 |
| `position` | string | 职位名称（不得抓成 `公司性质：` 等属性标记） |
| `position_type` | string | 职位类别 |
| `position_salary` | string | 月薪 |
| `position_dept` | string | 所属部门 |
| `position_report_to` | string | 汇报对象 |
| `position_subordinate` | string | 下属人数 |
| `employment_type` | string | 雇佣类型（`全职` / `兼职` / `实习`） |
| `annual_salary_min` | string | 年薪下限 |
| `annual_salary_max` | string | 年薪上限 |
| `status` | string | 在离职状态（`在职` / `离职`） |
| `position_start` | string | 入职时间（`YYYY年MM月01日`） |
| `position_resigned` | string | 离职时间（在职为 `""`） |
| `resigned_reason` | string | 离职原因 |
| `position_responsibilities` | string | 纯工作职责与业绩（排除公司性质、规模、城市等杂质行） |
| `position_achievements` | string | 业绩/成就 |

#### `certificate_list` 证书（3 字段/条）

| 字段 | 类型 | 说明 |
|---|---|---|
| `certificate_name` | string | 证书名称（含等级/分数） |
| `certificate_type` | string | 证书类型（`证书` / `结业证` / `培训证` 等） |
| `certificate_time` | string | 取得时间（`YYYY年MM月01日`） |

CET、JLPT、TOEIC、TOEFL、BEC 等语言考试写入 `language_list`，不得同时写入 `certificate_list`；非语言类职业资格、专业认证、驾驶证等写入 `certificate_list`。

#### `language_list` 语言能力（4 字段/条）

| 字段 | 类型 | 说明 |
|---|---|---|
| `language_name` | string | 语言名称（`日语` / `英语` / `德语` / `普通话` / `粤语` 等） |
| `language_level` | string | 等级/水平（如 `熟练` / `一般` / `CET-6` / `N1`） |
| `language_certificate` | string | 是否有证书（`有` / `无` / `""`） |
| `language_certificate_time` | string | 证书取得时间（通常为空） |

#### `skills_list` 技能（2 字段/条）

| 字段 | 类型 | 说明 |
|---|---|---|
| `skill_name` | string | 技能名称 |
| `skill_level` | string | 熟练度（如 `熟练` / `精通` / `掌握`） |

#### `training_list` 培训经历（7 字段/条）

| 字段 | 类型 | 说明 |
|---|---|---|
| `sequence_no` | number | 序号（从 1 开始） |
| `organization_name` | string | 培训机构 |
| `training_name` | string | 培训课程/项目名称 |
| `start_ym` | string | 开始时间（`YYYY年MM月01日`） |
| `end_ym` | string | 结束时间 |
| `certificate_name` | string | 所获证书（无则 `""`） |
| `description` | string | 培训内容描述 |

#### `project_list` 项目经历（11 字段/条）

| 字段 | 类型 | 说明 |
|---|---|---|
| `sequence_no` | number | 序号（从 1 开始） |
| `fingerprint` | string | 项目指纹（去重用，通常为空） |
| `project_name` | string | 项目名称 |
| `company_or_client` | string | 所在公司/客户 |
| `role_name` | string | 担任角色 |
| `start_ym` | string | 开始时间（`YYYY年MM月01日`） |
| `end_ym` | string | 结束时间 |
| `description` | string | 项目描述（含软件环境、硬件环境等） |
| `responsibilities` | string | 项目职责 |
| `achievements` | string | 项目成果 |
| `keywords` | string | 关键词标签 |

#### `communication_list` 沟通记录（2 字段/条）

| 字段 | 类型 | 说明 |
|---|---|---|
| `communicate_time` | string | 沟通时间（`YYYY年MM月DD日 HH:mm:ss`） |
| `communicate_content` | string | 沟通内容 |

### `raw_text` 原始文本

- **单来源 + 单语言 + 无翻译**：用原文文本（去掉 `### 工作表` 标记行，每行去首尾空白，去空行，`\n` 连接）。
- **合并、翻译、多语言**：由各字段拼装，每个字段一行，`\n` 连接。各语言版本按 `resumes` 顺序（中文在前），每版依次为 `base_info`、`expected_list`、`work_experiences`、`education_list`、`certificate_list`、`language_list`、`skills_list`、`training_list`、`project_list`、`communication_list`；空值和占位符不写。多语言简历先对齐再生成 `raw_text`。
- `quality.raw_text_length` 必须等于最终 `raw_text` 的长度。

### `quality` 质量概要

| 字段 | 类型 | 说明 |
|---|---|---|
| `full_name` | string | 候选人姓名（快速核对用） |
| `has_work` | boolean | 是否有工作经历 |
| `work_count` | number | 工作经历段数 |
| `has_education` | boolean | 是否有教育经历 |
| `education_count` | number | 教育经历段数 |
| `languages` | array | `resumes` 中的语言代码 |
| `raw_text_length` | number | `raw_text` 字符长度 |

V2 记录视转换器不同，可能只包含其中部分字段。

### `merge_info` 合并信息（仅 V3）

| 字段 | 类型 | 说明 |
|---|---|---|
| `group_id` | string | 组 ID（由成员原始字节的 SHA-256 计算，换用修复副本后不变） |
| `rule_version` | string | 合并规则版本 |
| `output_filename` | string | 输出文件名：`姓名_联系方式.json`，优先规范化手机号，其次邮箱 |
| `name_status` | string | `valid` 或 `unreliable` |
| `canonical_name` | string | 采用的姓名 |
| `english_name` | string | 英文/罗马字姓名（如有） |
| `primary_phone` / `primary_email` | string | 作为身份主键的联系方式 |
| `other_phones` / `other_emails` / `landlines` | array | 找到的其他联系方式 |
| `shared_contacts_ignored` | array | 与他人共用、因此不作主键的联系方式 |
| `needs_translation` | boolean | 没有中文版时为 `true` |
| `v2_count` / `v1_count` | number | V2 / V1 输入数量 |
| `language_sources` | object | 每种语言来自哪些 `source_files` 序号 |
| `translated_from` | string | 中文译文的源语言（如有） |
| `name_note` | string | 姓名判定备注 |
| `conflict_count` | number | 记录的字段冲突数 |
| `field_issue_count` / `high_issue_count` | number | 字段问题数 / 高等级问题数 |
| `name_linked_sources` | array | 依据姓名证据关联的输入 |
| `output_category` | string | `formal` / `needs_fix` / `pending_translation` |

### 身份与输出规则

- 规范化手机号或有效邮箱任一一致即为同一人；姓名、生日、公司等冲突只记录，不拆分。
- 不同人共用的联系方式只归一个人：简历创建时间最新的那位。
- 正式 JSON 必须至少有一个有效手机号或邮箱；没有的输入记入 `ledgers/no_contact_ledger`，不生成文件。
- 输出分类：没有中文版 → `pending_translation`；有高等级问题或姓名无效 → `needs_fix`；其余 → `formal`。

### 多语言日期规则

同一份简历里，各语言版本的日期必须一致，以中文版（`resumes[0]`）为准。对齐之后由 `claude_merge.v3.py` 的 `unify_dates` 处理，只处理已配对（各语言列表长度相等）的行，只处理日期字段（`position_start`、`position_resigned`、`school_start_ym`、`school_end_ym`、项目和培训的 `start_ym` / `end_ym`、`certificate_time`、`language_certificate_time`）：

1. 先把所有日期规范为 `YYYY年MM月DD日`。时分秒去掉；缺月份的不臆造（只有年份、年份区间原样保留）。
2. 中文为空、其他语言有值 → 用其他语言的日期补中文。
3. 其他语言为空或不同 → 用中文日期覆盖。
4. 相差超过 24 个月，或有一边无法比较 → 仍以中文为准，但在 `ledgers/cleaning_ledger` 记为 `date_unify_override_far`。这类行多半是两种语言配对到了不同的经历（不同时期或不同公司），是需要对照源文件抽查的对象。
5. 如果改完会使开始日期晚于结束日期 → 整行不改，记为 `date_unify_skip`。
6. `birth_date` 适用同一规则，另有两点：英文长写法（`November 2, 1965`）先规范；年月一致而其中一个的日是 `01`（只写了年月而补的 01）时，各语言都取有具体日的那个。出生年份不同则不动，记为 `date_unify_skip`。

每处改动在清洗台账里记为 `date_unify_format`、`date_unify_fill_zh`、`date_unify_fill_other` 或 `date_unify_override`。快照（`current_info`、`education_info`）和 `raw_text` 在这一步之后才计算。独立审计在匹配人工决定的行时忽略日期字段。

### V2 每文件 JSON 的差异

- `schema_version` 为 `codex-resume-json-1.0`；`record_id` 为 SHA-256 哈希；没有 `merge_info`。
- `source` 含 `path`、`original_path`、`filename`、`extension`、`size`（字节）、`html_filename`、`note`。
- `extraction` 使用上文列出的 V2 字段。
- 文件名：`<姓名>_<源路径 SHA-256 前 12 位>.json`；多语言合并时可串联多个哈希（`<姓名>_<中文哈希>_<英文哈希>.json`）；缺姓名时为 `待确认姓名_<哈希>.json`。

## 注意

- 简历属于个人敏感信息。`.gitignore` 已排除数据目录、`config.json`、`CONTEXT.md`、运行输出和各类决定/对齐文件，**请不要把真实简历或由它们生成的 JSON 提交到任何仓库**。
- V2 里两个一次性修复脚本需要“姓名/手机号对应表”，数据不随仓库发布：见 `repair_data/README.md`。
- V2 的脚本是历史上分批迭代出来的（按 Word / XLS / PDF / Web 分别处理），仅做了路径配置化，没有重写；整理时只删除了内容完全相同的重复文件（对照见 `docs/v2-name-mapping.md`）。

## License

MIT，见 `LICENSE`。
