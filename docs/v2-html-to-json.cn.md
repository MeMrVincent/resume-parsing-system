# HTML/Web 转 JSON 流程说明

[English](v2-html-to-json.md) | **简体中文** | [日本語](v2-html-to-json.ja.md)

> 本文档描述 V2（word/xls/pdf/html → JSON）流程。目录默认值见根目录 `config.example.json`；文中的 `<项目根>` 即 config 里的 project_root。已合并的重复脚本见 [`v2-name-mapping.cn.md`](v2-name-mapping.cn.md) 末尾。

## 1. 目标和范围

本流程用于把 Web 网页、邮件归档和 HTML-like 简历转换为统一的简历 JSON，并对源文件、暂存文件、JSON 字段和多语言版本进行逐文件审查与增量修复。

处理范围以 `32718文件报告.xlsx` 的 `Web网页与邮件 (.html, .eml)` 工作表为准，不按某个目录或某一批文件截取。当前支持的主要后缀为：

```text
.html  .htm  .mht  .mhtml  .eml
```

核心原则：

- 原始 Web 文件只读，不能改名、移动、覆盖或删除；
- 暂存文件必须与源文件字节一致，并用 SHA-256 校验；
- HTML/邮件正文是字段事实来源，不能只判断“字段有值”就认定合格；
- JSON 必须符合根目录 `CONTEXT.md` 的字段、快照和多语言约定；
- 每轮先记录问题，再做增量修复，最后重新全量审查；
- 业务 JSON 内不保存 `repair_history`、`rounds` 等膨胀型审计历史；
- 每条记录的状态、问题和修复动作统一保存在外部 `_*.v2.json` 报告中。

## 2. 目录和权威文件

| 内容 | 路径 |
| --- | --- |
| 文件盘点报告 | `<项目根>\32718文件报告.xlsx` |
| JSON 字段权威规范 | `CONTEXT.md（未随仓库公开；字段结构见 examples/ 中的示例 JSON）` |
| 原始 Web 文件 | `<项目根>\需要采集的简历文件夹` 及其子目录 |
| Web 安全暂存目录 | `<项目根>\complete-transfered-htmls\web\input` |
| Web 转换主映射 | `<项目根>\complete-transfered-htmls\web\web_conversion_map.v2.json` |
| 正式业务 JSON | `<项目根>\complete-transfered-jsons\web` |
| 全量独立审查报告 | `<项目根>\complete-transfered-jsons\web\_web_full_review.v2.json` |
| 全量增量修复报告 | `<项目根>\complete-transfered-jsons\web\_web_full_repair.v2.json` |
| 文件名和扁平化报告 | `<项目根>\complete-transfered-jsons\web\_web_output_organize.v2.json` |

`web_conversion_map.v2.json` 是源文件级主索引。工作簿行、源路径、暂存路径、源哈希、JSON 路径、状态和检查结果都以它为关联依据。不要通过文件名猜测源文件和 JSON 的对应关系。

正式目录中的业务 JSON 全部平铺。文件名格式为：

```text
姓名_手机号.json
姓名_邮箱.json
姓名_无联系方式.json
姓名_手机号_2.json       # 同一姓名和联系方式有多份文件时递增
```

文件名以手机号优先，手机号不存在时使用邮箱；两者都没有时使用 `无联系方式`。以 `_` 开头的 JSON 是报告，不是候选人业务 JSON。

## 3. 文件之间的关系

```text
32718文件报告.xlsx
        │ 规定全量范围和原始绝对路径
        ▼
web_conversion_map.v2.py
        │ 建立/维护每条源文件记录
        ├──────────────► web_conversion_map.v2.json
        │                         │
        │ 只读复制并校验哈希      │ 提供 source/stage/json 对应关系
        ▼                         ▼
complete-transfered-htmls/web/input  web_html_to_json.v2.py
                                          │
                                          ▼
                           complete-transfered-jsons/web/*.json
                                          │
                         ┌────────────────┴────────────────┐
                         ▼                                 ▼
              web_full_review.v2.py              web_json_audit.v2.py
                 独立只读全量审查                    基础审计/回写状态
                         │
                         ▼
                 _web_full_review.v2.json
                         │ 问题清单是修复输入
                         ▼
                 web_full_repair.v2.py
                    逐字段增量修复
                         │
                         ├────────► _web_full_repair.v2.json
                         │          每条记录最终状态
                         ▼
                 web_full_review.v2.py
                    再次全量复核
                         │
                         ▼
                web_output_organize.v2.py
                 文件名校验、扁平化、旧副本清理
```

关系说明：

1. 工作簿决定“应该处理哪些物理文件”。
2. map 决定“某一行对应哪个源文件、暂存文件和 JSON”。
3. 暂存文件保留原始字节，转换器从暂存文件读取正文。
4. 业务 JSON 保存标准化数据，不保存每轮长篇审计历史。
5. review 报告记录修复前及修复后的问题；repair 报告记录每个 map 对象的状态和修复动作。
6. organize 报告记录最终文件名、移动结果和精确删除的旧副本。

## 4. 第一步：建立 Web 全量映射

### `python/v2/web_conversion_map.v2.py`

该程序读取工作簿的 Web 工作表，保留每一行，包括最终判断为非简历、无联系方式或源文件异常的记录。它把源文件复制到安全暂存目录，并计算内容哈希；不会改动原始文件。

运行：

```powershell
cd <项目根>
python python\web_conversion_map.v2.py
```

只有在工作簿范围或源文件发生变化时才需要使用 `--force`：

```powershell
python python\web_conversion_map.v2.py --force
```

注意：`--force` 会重新复制暂存文件并重算状态。已有修复批次中不要随意执行，避免把已经确认的 map 状态覆盖为初始状态。

## 5. 第二步：Web/HTML 转 JSON

### `python/v2/web_html_to_json.v2.py`

这是当前 Web HTML-like 文件到 JSON 的正式入口。它负责：

- 读取 `.html`、`.htm`、`.mht`、`.mhtml` 和 `.eml`；
- 解码 MHTML/EML 邮件正文；
- 解析 51job、智联、猎聘及普通 HTML 简历；
- 提取基础信息、求职意向、工作、教育、证书、语言、技能、培训和项目；
- 生成 `CONTEXT.md` 规定的 JSON 结构；
- 纯英文或纯日文源文件生成真实的字段级中文 `resumes[0]`，并把源语言版本保留在后续 resume；
- 原子写入 JSON，并回写 map。

全量转换：

```powershell
python python\web_html_to_json.v2.py --limit 0
```

只重跑指定工作簿序号：

```powershell
python python\web_html_to_json.v2.py --indices 300 650 1559 --force
```

随机可复现抽样：

```powershell
python python\web_html_to_json.v2.py --random --limit 50 --seed 20260804
```

`--force` 只应用于明确需要重建的记录。批量覆盖前必须先保存修复前报告，避免丢失问题证据。

## 6. JSON 结构要求

顶层固定为：

```text
schema_version
record_id
source
extraction
dates
classification
structured_data
raw_text
quality
```

`structured_data` 固定为：

```text
base_info
expected_info
current_info
education_info
resumes
```

其中：

- `base_info`、`expected_info`、`current_info`、`education_info` 是 `resumes[0]` 的顶层快照；
- 所有经历列表只能存在于 `structured_data.resumes[]`；
- `raw_text` 只允许存在于 JSON 顶层；
- 列表 item 不允许出现额外字段；
- 日期必须使用统一格式，例如 `2013年03月01日`；
- `school_degree_rank` 只能是字符串 `"1"` 至 `"7"` 或空字符串；
- `resume_languge` 沿用 `CONTEXT.md` 中的正式拼写。

不要在业务 JSON 中写入：

```text
repair_history
rounds
```

这两类历史会使 JSON 体积快速膨胀。每轮问题和修复状态应写入外部报告。

## 7. 多语言规则

多语言顺序必须统一：

```text
resumes[0].resume_languge = "zh"
resumes[1].resume_languge = "en" 或 "jp"
```

严格要求：

- `resumes[0]` 必须是字段级中文内容，不能只把英文或日文对象的语言标签改成 `zh`；
- 外文公司名、学校名、职位、专业、职责和证书等都需要翻译到中文主版本；
- 后续外文 resume 保留源语言内容；
- 同一经历在各语言版本中的列表数量、顺序、日期和语义必须对应；
- 多语言对象必须深拷贝，不能让两个 resume 引用同一个对象后互相覆盖；
- 外文原文只有一个版本时，先复制为源语言版本，再生成中文翻译版本。

专项工具：

### `python/v2/web_multilingual_repair.v2.py`

只处理全量审查报告中标记的多语言问题，使用本地离线翻译支持修复中文主版本，并保留源语言版本。

```powershell
python python\web_multilingual_repair.v2.py
```

运行后必须再次执行 `web_full_review.v2.py`，不能把翻译程序自身的成功退出当作数据通过。

## 8. 严格语义规则

字段有值不代表字段正确。审查和修复必须同时检查“值是什么”和“值是否属于该字段”。

### 工作经历

以下内容不作为正式工作经历：

- 实习、见习、intern、trainee；
- 社团、学生会、学校协会和校内兼职；
- 单独的研究助理、课题研究、毕业论文；
- 培训、语言能力、特殊技能等章节标题；
- 公司名位置中的职责句子、行业、薪资或序号碎片。

同一公司和日期被解析成“行业/薪资一行 + 职位一行”时，应合并为一条真实工作经历。

### 教育经历

- `school_name` 必须是学校或教育机构，不得是专业、技能、地点、培训课程或章节标题；
- 同一教育记录被拆成“学校一条 + 学历一条”时应合并；
- 社团、在校兼职、短期培训和毕业研究不能作为正式教育记录；
- 起止时间相同不一定是重复，也可能是双学位，必须比较学校和其他字段后判断。

### 证书和认证

证书名称必须指向明确证书、执照、资格或考试等级。以下内容必须删除或重新构造：

- 地点，例如“上海”“日本”；
- 学校、培训机构或认证公司名称；
- “证书”“培训证书”等章节或泛化词；
- “目前为……审核员”等状态句，应根据源文重建为明确资格名称；
- “份考试”等截断文本；
- 优秀毕业生、奖学金、比赛奖项和优秀论文等荣誉；
- 工作职责、实验安排和活动描述。

例：

```text
错误：目前为OHSMS审核员
正确：职业健康安全管理体系（OHSMS）国家注册审核员

错误：方圆标志认证集团有限公司
处理：删除；它是培训/认证机构，不是证书
```

### 技能、语言、培训和项目

- `skills_list` 不能按单词或标点拆分；
- English/日语等语言进入 `language_list`；
- CET、TEM、JLPT、IELTS 等证书进入语言证书或证书列表；
- 培训机构、课程名称和证书名称不能互相错位；
- 实习、社团和毕业论文不能伪装成项目或培训继续保留。

## 9. 第三步：全量独立审查

### `python/v2/web_full_review.v2.py`

该程序只读业务 JSON、map、暂存文件和源文件，写出独立报告。它不导入生产转换逻辑来证明生产逻辑正确，因此是最终质量闸门。

```powershell
python python\web_full_review.v2.py
```

默认报告：

```text
complete-transfered-jsons/web/_web_full_review.v2.json
```

它检查：

- 工作簿与 map 是否一一对应；
- 源文件、暂存文件及哈希是否一致；
- JSON 路径、源路径和文件大小是否正确；
- 顶层和所有列表字段是否严格对齐 `CONTEXT.md`；
- 顶层快照是否与 `resumes[0]` 一致；
- 字段值是否能在源文找到证据；
- 多语言版本是否齐全、翻译和列表是否对齐；
- 公司、学校、职位、证书、技能是否存在语义错位；
- 实习、社团、学校协会、研究等非主要内容是否残留；
- 是否存在孤儿 JSON、重复输出和空源文件。

保存某一轮修复前报告时，使用独立文件名，不能覆盖：

```powershell
python python\web_full_review.v2.py `
  --report complete-transfered-jsons\web\_web_review_round_before.v2.json
```

## 10. 第四步：增量修复

### `python/v2/web_full_repair.v2.py`

该程序读取 review 报告，对 map 中每一条记录重新检查，只修改有可靠源证据的问题字段，并把每个对象的最终状态写入外部 repair 报告。

```powershell
python python\web_full_repair.v2.py
```

指定一轮修复前报告和独立修复报告：

```powershell
python python\web_full_repair.v2.py `
  --review complete-transfered-jsons\web\_web_review_round_before.v2.json `
  --report complete-transfered-jsons\web\_web_repair_round.v2.json
```

状态含义：

| 状态 | 含义 |
| --- | --- |
| `clean` | 本轮检查无问题且未修改 |
| `repaired` | 本轮发生增量修改，复核后无剩余问题 |
| `needs_review` | 自动修复后仍有问题 |
| `no_json_expected` | 非简历、无联系方式等预期不生成 JSON |
| `failed` | 源文件缺失、空文件或无法读取，不能可靠生成 JSON |

修复完成后必须再次执行全量审查。推荐循环：

```text
review（保存修复前报告）
  → repair（保存本轮修复报告）
  → review（更新最终报告）
  → 仍有问题则进入下一轮
```

不要直接批量清空一个字段来追求报告为零。能从源文恢复的内容应重建；只有确定是污染、错位或非主要内容时才删除。

## 11. 其他辅助程序

| 文件 | 作用 | 与主流程关系 |
| --- | --- | --- |
| `python/v2/web_json_audit.v2.py` | 基础 HTML/JSON/map 审计，可用 `--apply` 回写 audit 状态 | 辅助检查，不代替 full review |
| `python/v2/web_html_json_reconcile.v2.py` | 早期逐 JSON 对账程序 | 兼容工具；当前主流程优先使用 full review |
| `python/v2/web_html_json_repair.v2.py` | 早期按 reconcile 结果修复 | 兼容工具；不得重新写入嵌入式长历史 |
| `python/v2/web_batch_report.v2.py` | 从 map 重建批次统计报告 | 只汇总，不修复业务数据 |
| `python/v2/web_internship_boundary_recovery.v2.py` | 记录曾经的 intern/International 边界缺陷恢复 | 专项历史验证工具 |
| `python/v2/web_output_organize.v2.py` | 审查文件名、平铺输出、更新 map、清理已验证旧副本 | 所有内容问题清零后执行 |

这些辅助程序不能改变“full review 是最终独立质量闸门”的原则。

## 12. 文件名校验和扁平化

### `python/v2/web_output_organize.v2.py`

先只审查：

```powershell
python python\web_output_organize.v2.py
```

只有在 `collision_count = 0`、`needs_review = 0` 后才能应用：

```powershell
python python\web_output_organize.v2.py --apply
```

应用时程序会：

- 按姓名和真实联系方式生成最终文件名；
- 同一姓名/联系方式的多份文件追加 `_2`、`_3`；
- 把分类子目录中的 JSON 移到 `complete-transfered-jsons/web` 根目录；
- 更新 map 中的 `json_path`；
- 只有在旧文件与当前映射文件的 `record_id + source.path` 同时一致时，才删除旧副本；
- 不删除未知文件、报告文件或无法唯一配对的 JSON。

不要手工批量移动 JSON 后再改 map，否则源文件、JSON 和报告会失去关联。

## 13. 推荐全量复跑顺序

```powershell
cd <项目根>

# 1. 工作簿或源范围变化时才重建 map
python python\web_conversion_map.v2.py

# 2. 生成或定点重建 JSON
python python\web_html_to_json.v2.py --limit 0

# 3. 保存修复前全量问题
python python\web_full_review.v2.py `
  --report complete-transfered-jsons\web\_web_review_round_before.v2.json

# 4. 增量修复
python python\web_full_repair.v2.py `
  --review complete-transfered-jsons\web\_web_review_round_before.v2.json `
  --report complete-transfered-jsons\web\_web_repair_round.v2.json

# 5. 最终全量复核
python python\web_full_review.v2.py

# 6. 文件名审查；确认无阻塞后再加 --apply
python python\web_output_organize.v2.py
```

如果第 5 步仍然有业务 JSON 问题，回到第 3 步开始下一轮，不进入文件整理。

## 14. 常见问题和处理方式

### JSON 字段有值，但语义明显错误

以源文和字段语义为准。公司不能是职责句子，学校不能是“特殊技能”，证书不能是地点或机构。先在 review 报告中记录精确路径和值，再增量修复。

### 英文简历的 `resumes[0]` 也是英文

这是错误。`resumes[0]` 应是完整中文翻译，`resumes[1]` 才保留 `en` 源文；日文同理。

### 同一工作经历被解析成两条

比较公司、开始时间、结束时间和职位。如果一条是行业/薪资碎片，另一条是真实职位，应合并，不是简单保留两条非空记录。

### 证书列表出现优秀毕业生、论文、培训机构

这些不是证书。荣誉按当前业务规则删除；培训机构留在培训记录的机构字段；明确通过审核员考试并取得资格的，按源文重建为完整资格名称。

### 源文件存在但为 0 字节

判定为不合格源文件，状态记为 `failed / source_file_empty`。不得生成空壳 JSON，也不得根据文件名猜测内容。只有重新获得非空原始文件后才能恢复。

### review 报告为零，但人工仍发现问题

先检查审查规则是否真的遍历了所有 `resumes` 和列表，尤其注意缩进、提前 `return`、异常被吞掉或仅检查空列表等覆盖漏洞。增加规则后必须重新对全部 1,739 份业务 JSON 执行审查，不能只检查用户举例的文件。

### JSON 文件越来越大

检查业务 JSON 内是否误写 `repair_history` 或 `rounds`。审计历史必须保存在外部报告中。删除后需要全量扫描确认嵌套对象中也不存在这两个键。

## 15. 当前批次状态（2026-08-27）

| 项目 | 数量/状态 |
| --- | --- |
| map 总记录 | 1,754 |
| 有效业务 JSON | 1,739 |
| 预期不生成 JSON | 14 |
| 源文件失败 | 1（索引 664，源文件与暂存文件均为 0 字节） |
| 孤儿 JSON | 0 |
| 分类子目录 | 0，业务 JSON 已全部平铺 |
| `repair_history` / `rounds` 遗留 | 0 |
| 当前 full review 业务问题 | 仅索引 664 的空源文件问题 |

本轮证书专项审查另保留：

```text
complete-transfered-jsons/web/_web_certificate_review_round_before.v2.json
complete-transfered-jsons/web/_web_certificate_repair_round.v2.json
```

前者记录修复前 22 份简历、38 条错误证书项；后者记录本轮逐对象修复状态。最终结果仍以 `_web_full_review.v2.json` 为准。

## 16. v2 命名和维护约定

- 当前 Web 主流程的实现和命令行入口统一使用 `*.v2.py`；
- `web_html_to_json.v2.py` 通过运行时方式加载带点的 v2 依赖；
- 无版本号或 `_v2.py` 历史文件只作为兼容底座，不应作为新的 Web 批处理入口；
- 新增审查、修复或专项脚本时继续使用 `web_<用途>.v2.py`；
- 新规则必须先进入独立 review，再进入 repair，不能只在生成器中静默修正；
- 修改字段结构前先更新 `CONTEXT.md`，再同步转换器、审查器、修复器和说明文档；
- 所有写入业务 JSON 的程序都必须保持原子写入，并在完成后验证 JSON 可解析。

