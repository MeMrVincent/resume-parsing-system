# V3：合并、清洗、审计流水线

[English](v3-pipeline.md) | **简体中文** | [日本語](v3-pipeline.ja.md)

> V3 把 V2 产出的 JSON（及 V1 历史 JSON）按手机号/邮箱合并成“一人一份 JSON”，并做独立审计。本文说明代码关系、处理顺序、修复目录与 raw_text 规则。示例路径里的 `<项目根>`、`<repair_dir>` 均由 `config.json` 决定。

## 0. 铁律（不要破坏）

1. **不修改原件**：`需要采集的简历文件夹`、`complete-transfered-jsons`、`complete-v1`、`codex-*`、`CONTEXT.md`（改 CONTEXT.md 要先问使用者）。所有修复都是“覆盖副本”，放在 `<repair_dir>\<最新子目录>\`（`v1\`、`v2\` 下同名 JSON 替换输入）。
2. 代码文件命名 `claude_*.v3.py`；改完代码必须重新跑审计，不要绕过审计。
3. 每次改动后的验证顺序：云端/本机跑一遍合并 → 审计 → 换 `PYTHONHASHSEED`（如 777）再跑一遍做对照 → 两次结果完全一致才算数。
4. 使用者只想双击跑一次：`<项目根>\`scripts\merge.cmd`（不是 `claude_run_merge.v3.cmd`，那个不读修复目录）。它取 `output\source-repair-v3` 下名字**最新**的目录，解压其中所有 `repair_json*.zip`（按文件名排序，后面的覆盖前面的同名文件），然后合并、对照合并、审计。
5. 回复使用者用中文。

## 1. Python 代码之间的关系

目录：`python\v3\`（公共配置模块在 `python\common\rc_config.py`）。公共模块文件名带点，不能普通 import，一律用 `importlib.util.spec_from_file_location` 按路径加载。

### 1.1 主流水线（依赖方向：上游产物 → 下游读取）

```
原件(需要采集的简历文件夹) + complete-transfered-jsons + complete-v1  (只读)
   │
   ├─ claude_pack_sources.v3.py   打包：inputs/(v1,v2 全部 JSON)、originals/、html/、manifest.csv（JSON→原件→包内 key）
   ├─ claude_source_text.v3.py    从原件抽全文 → texts/<key>.txt、extract_ledger.csv   【只能在云端：要 LibreOffice/pdftotext】
   ├─ claude_source_audit.v3.py   每个输入 JSON 回原件核对，判是否解析器问题 → source_audit_ledger.csv、contact_recovery.csv
   ├─ claude_parse_*.v3.py        各模板新解析器（原文全文 → resume 对象）
   │     cn_platform(智联) / 51job / liepin / zh_report(推荐报告) / zh_table(招聘站 xls) / zh_free(兜底) / jp / en
   ├─ claude_reparse.v3.py        按模板用新解析器重解析，与旧 JSON 对照原文打分，不比旧的差才替换 → 写入修复副本
   ├─ claude_source_repair.v3.py  把原件里有而 JSON 漏掉的手机号/邮箱/姓名补回（修复副本；排除顾问/HR/公共联系方式）
   ├─ claude_name_fix.v3.py       姓名回源核对（最后一层修复副本；拿不准的写 name_review.csv）
   │        └─→ 以上全部输出到“修复副本目录”(--repair-dir)：v1/、v2/ 下同名 JSON
   │
   ├─ claude_merge.v3.py          ★主程序：V2/V1 互校合并，以手机号/邮箱认定同一人，一人一份 JSON
   │     加载：claude_merge_common.v3.py（字段契约、联系方式/日期/姓名规范化、语种判定、快照、raw_text 构造）
   │           claude_merge_normalize.v3.py（字段归位与清理，规则与 checks 一一对应）
   │           claude_merge_checks.v3.py（字段问题检查 high/medium/low，只记录不阻断）
   │           claude_merge_manual.v3.py（读 repair-dir 里的 manual_decisions.json / translations.json / alignments.json 并应用）
   │     输入文件（repair-dir 下）：manual_decisions.json、translations.json、alignments.json、source_texts.json、v1/、v2/
   │     输出：<out>\<run-id>\formal|needs_fix|pending_translation\*.json、ledgers\*、reports\summary.json
   ├─ claude_merge_audit.v3.py    ★独立验收（只读，30 项检查，全部为 0 才算通过；加载 common/checks，自己重读 summary 里登记的决定文件并核对 sha256）
   ├─ claude_review_book.v3.py    把 needs_fix/复核账生成人工复核 Excel（附原文片段）
   └─ `scripts\merge.cmd`   双击入口：解压 zip → merge → witness merge → audit
```

辅助：`claude_archive.v3.py`（计划式归档，不删除）、`claude_verify_python.v3.py`（静态检查编译/依赖）、`claude_split_pack.v3.py`（大包切 30MB 块）、`CODE_INDEX.cn.md`（目录索引）。

### 1.2 merge 内部 build_group 的处理顺序（每个人一次）

1. 按联系方式把 V2/V1 输入分成“人”，同人合并（V2 优先，V1 补充；`group_id` 由成员**原始字节**的 sha256 算出，所以换成覆盖副本后 group_id 不变）。
2. `normalize_resumes`（字段归位/清理）→ `apply_translation`（没有中文版的人：外文版复制成 resumes[0] 并换成译文，`translations.json`，按 `source_sha256` 门控）→ 人工决定 `apply_items`（`manual_decisions.json`：set/delete/move/accept/add，按内容匹配，匹配不上就跳过并记账）→ `apply_name`（姓名）→ **`apply_alignment`（多语言对齐，`alignments.json`，按各语言版本内容 sha256 门控，对不上就跳过并记 `alignment:unmatched`）** → 快照 → raw_text。
3. 分类：没有 zh → `pending_translation`；有 high 问题或姓名无效 → `needs_fix`；其余 → `formal`。
4. 没有有效手机号/邮箱的输入不进输出 JSON，进 `ledgers\no_contact_ledger`。

### 1.3 修复目录（`<repair_dir>\<最新子目录>\`）里各文件的作用

| 文件 | 作用 |
|---|---|
| `repair_json_*.zip` | 覆盖副本 JSON（解压到 `v1\`、`v2\`），按文件名排序依次解压，后面的覆盖前面的 |
| `repair_json_zz_split.zip` | 第 11 批：共用联系方式拆分、两人合并拆开的覆盖副本 |
| `repair_json_zz_align.zip` | 第 12 批：解压出 `alignments.json` 和 `source_texts.json` |
| `manual_decisions.json` | 1,654 条人工决定（含 `exclude`、`exclude_record`、`name`） |
| `translations.json` | 166 份“外文译中文” |
| `alignments.json` | 多语言对齐记录（2,119 份，全量） |
| `source_texts.json` | 单来源简历的原文文本（10,112 个原件、14,732 个输入） |

> **注意**（已处理，仍需记住）：`repair_json_zz_align.zip` 每次运行都会把里面的 `alignments.json`、`source_texts.json` 解压覆盖目录里的同名文件。以后更新 `alignments.json` 时，**先删掉这个 zip**（或把新文件重新打进 zip），否则新文件会被旧的覆盖回去。`source_texts.json` 与对齐无关，不需要再改。

### 1.4 raw_text 规则（项目约定）

- 单来源 + 单语言 + 无翻译：用原文文本（去“### 工作表”标记行，每行去首尾空白，去空行，`\n` 连接）。“单来源”= 组内所有输入映射到同一个原件。
- 合并、翻译、多语言：各字段拼装，每个字段一行，`\n` 连接；顺序为各语言版本依次，每版先基本信息再各个列表；空值/占位符不写，不去重，不加空行（`claude_merge_common.v3.py: build_raw_text_assembled`）。
- 当前：6,894 份用原文，3,682 份用拼装。审计 `raw_text_rule` 逐份核对，`raw_text_original_sha` 在 PC 上核对原件 sha256。
- 多语言简历**先对齐再写 raw_text**（合并流程已经是这个顺序，不用手工写）。

### 1.5 对齐工具（本批新增，在 `<项目根>\python\` 下，数据在 `<项目根>\claude-align\`）

| 文件 | 作用 |
|---|---|
| `claude_align_auto.v3.py` | 程序自动对齐：同一语言内按名称+日期聚类去重；跨语言按日期（工作/教育/项目/培训）或名称（无日期列表）配对 |
| `claude_align_mktasks.v3.py` | 读 `export2\`（对齐前的各语言版本），只列“还缺某语言的行”，生成 `tasks2\<group_id>.json` |
| `claude_align_mkbatches.v3.py` | 把 tasks2 切成批 `batches\bNNN.jsonl`（每批 ≤90k 字符、≤40 份） |
| `PROMPT.md`（`claude-align\`） | 给大模型的完整任务说明（配对/补译/drop 残留行/输出格式） |
| `claude_align_check.v3.py` | 检查某批的结果文件：`python claude_align_check.v3.py b034`，输出 ok 才合格 |
| `claude_align_assemble.v3.py` | 把 `results\*.json` 汇总成 `alignments.json`：`python claude_align_assemble.v3.py <results目录> <输出文件>` |

环境变量 `CLAUDE_ALIGN_DIR` 可改数据目录（默认是 `python` 的上一级下的 `claude-align`）。这些脚本需要 `claude_merge_common.v3.py` 在同一目录。

**数据目录 `claude-align\`**（先双击 `python\v3\claude_unpack_align.v3.cmd` 解压 `claude_align_data.zip`）：
`export2\`(2,186 份对齐前导出) `tasks2\`(2,119 份任务) `batches\`(b000–b068) `results\`(b000–b068 全部 69 批) `PROMPT.md`。

## 5. 重要提醒（踩过的坑）

- 对齐记录按“各语言版本内容的 sha256”门控：前面的清洗、翻译、人工决定、覆盖副本有改动导致某份内容变了，这份的对齐会因 `unmatched` 被跳过，需要重新对齐那份。
- 云端模拟 PC 运行时，修复目录必须带齐所有 `repair_json*.zip` 的内容（`v1\`、`v2\` 全部覆盖副本），否则结果会大幅偏离。
- 运行 id 的前 8 位必须是日期（如 `20261012-…`），否则对照合并会因时间戳不同判“不幂等”。
- 子任务单次输出超过上限会报错，但文件可能已写成功，先检查结果文件再决定是否重做。
- 基线运行日志：`output\merge-v3\20261012-2125-v3.2-repair.log`。
