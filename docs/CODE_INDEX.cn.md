# 代码索引

[English](CODE_INDEX.md) | **简体中文** | [日本語](CODE_INDEX.ja.md)

由 `python/` 下各文件的模块说明自动生成；说明为空表示该脚本没有写模块说明。

## common：公共模块与工具（2 个文件）

| 文件 | 说明 |
|---|---|
| `check_code.py` | check_code.py —— 静态检查 python/ 下全部代码（common、v2、v3）：只编译和分析，不运行任何脚本。 |
| `rc_config.py` | rc_config.py —— 项目统一配置读取（common）。 |

## v3：合并 / 解析 / 审计 / 对齐（Claude）（28 个文件）

| 文件 | 说明 |
|---|---|
| `claude_align_assemble.v3.py` |  |
| `claude_align_auto.v3.py` |  |
| `claude_align_check.v3.py` |  |
| `claude_align_mkbatches.v3.py` |  |
| `claude_align_mktasks.v3.py` |  |
| `claude_merge.v3.py` | claude_merge.v3.py —— V2 / V1 互校合并：以手机号或邮箱认定同一人，一人一份 JSON（单语或多语）。 |
| `claude_merge_audit.v3.py` | claude_merge_audit.v3.py —— merge v3 输出的独立验收（只读）。 |
| `claude_merge_checks.v3.py` | claude_merge_checks.v3.py —— 合并后 JSON 的结构与字段校验。 |
| `claude_merge_common.v3.py` | claude_merge_common.v3.py —— merge v3 公共模块：字段规范、联系方式/日期/名称规范化、语种判定、快照与 raw_text 重建。 |
| `claude_merge_manual.v3.py` | 按原文逐条复核后的人工决定（manual_decisions.json），在合并时应用到副本上。 |
| `claude_merge_normalize.v3.py` | claude_merge_normalize.v3.py —— 合并后、字段检查前的“字段归位与清理”。 |
| `claude_name_fix.v3.py` | claude_name_fix.v3.py —— 姓名回源核对（在所有模板重新解析之后运行，结果作为最后一层修复副本）。 |
| `claude_pack_sources.v3.py` | claude_pack_sources.v3.py —— 把“回源检查解析器”所需的全部材料打包（只读，不改动任何原文件）。 |
| `claude_parse_51job.v3.py` | claude_parse_51job.v3.py —— 前程无忧（51job）导出简历的新解析器（含猎聘同类版式的兜底识别）。 |
| `claude_parse_cn_platform.v3.py` | claude_parse_cn_platform.v3.py —— 中文招聘平台导出简历（智联招聘为主）的新解析器。 |
| `claude_parse_en.v3.py` | claude_parse_en.v3.py —— 英文简历（CV / Resume）解析器。 |
| `claude_parse_jp.v3.py` | claude_parse_jp.v3.py —— 日文简历（履歴書 / 職務経歴書 / 紐培等推荐表日文版 / 51job 日文版 / xls 日文表格）的新解析器。 |
| `claude_parse_liepin.v3.py` | claude_parse_liepin.v3.py —— 猎聘导出简历解析器。 |
| `claude_parse_zh_free.v3.py` | claude_parse_zh_free.v3.py —— 中文自由格式简历解析器（兜底）。 |
| `claude_parse_zh_report.v3.py` | claude_parse_zh_report.v3.py —— 中文推荐报告（猎头/人才公司的“推荐报告 / 候选人简历报告 / 人才推荐表”）解析器。 |
| `claude_parse_zh_table.v3.py` | claude_parse_zh_table.v3.py —— 招聘网站导出的 xls 简历表格解析器。 |
| `claude_reparse.v3.py` | claude_reparse.v3.py —— 第二步：按模板用新解析器从原文重新生成 resume，与旧 JSON 对照原文比较，择优替换。 |
| `claude_review_book.v3.py` | 第 7 批：人工复核表。 |
| `claude_source_audit.v3.py` | claude_source_audit.v3.py —— 每个输入 JSON 回到原始文件逐项核对，判定是否是解析器问题，生成台账。 |
| `claude_source_repair.v3.py` | claude_source_repair.v3.py —— 第一步回源修复：把原文件里有、解析器漏掉的手机号 / 邮箱 / 姓名补回 JSON。 |
| `claude_source_text.v3.py` | claude_source_text.v3.py —— 独立于原解析器，从原始简历文件抽取全文（用于回源核对）。 |
| `claude_split_pack.v3.py` | claude_split_pack.v3.py —— 把 claude_pack 的大分卷切成 30MB 小块，便于传输（只新增 .partNNN 文件，不改原分卷）。 |
| `copy_to_v3.py` | copy_to_v3.py —— 把某次合并运行中的 formal/*.json 复制到 v3_dir（默认 complete-v3），并逐份核对 sha256。 |

## v2：Word / XLS / PDF / HTML → JSON（Codex）（103 个文件）

| 文件 | 说明 |
|---|---|
| `audit_chinese_json_against_sources.py` | 按字段归属，将中文正式 JSON 与原始 Word 文本证据逐项比较。 |
| `batch_clean_resume_jsons.py` | 全量清洗 complete-transfered-jsons：非简历/应届无经验清理、多语言校验、关键词和 raw_text。 |
| `c_liepin_legacy_adapter.v2.py` | 命名对照入口；可导入版本见 c_liepin_legacy_adapter_v2.py。 |
| `c_liepin_legacy_adapter_v2.py` | 仍依赖 V1 猎聘解析器的最小兼容 API。 |
| `c_resume_global_progress.v2.py` | 按源文件路径严格核算 Word 转换清单与正式 JSON 的全局进度。 |
| `c_resume_html_dom_common.v2.py` |  |
| `c_resume_html_to_json_common.v2.py` |  |
| `c_resume_invalid_terminalize.v2.py` | 终止已人工核对的 14 份 passed 中文非简历/身份不可恢复文件。 |
| `c_resume_json_promote.v2.py` | 将双重校验通过的中文暂存 JSON 保守晋级到正式目录。 |
| `c_resume_nonchinese_promote.v2.py` | 只提升已通过源证据审计的多语言 JSON，并同步转换清单。 |
| `c_resume_nonchinese_source_audit.v2.py` | 以源 Word、语义 HTML 双重证据审计多语言暂存 JSON。 |
| `c_resume_nonresume_terminalize.v2.py` | 终止 review 中名称明确的非简历文件；保守规则，不处理含糊候选。 |
| `c_resume_ocr_finalize.v2.py` | 登记用户 OCR JSON，恢复原始源路径，移动到正式中文目录。 |
| `c_resume_ocr_normalize.v2.py` | 规范用户 OCR JSON 到正式模板，并只暂存结构和内容均有效的简历。 |
| `c_resume_ocr_stage.v2.py` | 把需要用户 OCR 的原始文档复制到指定目录，并在转换映射中标记等待 OCR。 |
| `c_resume_source_finalize.v2.py` | 同步已晋级 JSON 到转换映射，并删除其对应 HTML。 |
| `c_resume_terminal_status.v2.py` | 将已人工核验且不可继续解析的单个转换项标为终态。 |
| `c_resume_unknown_stage.v2.py` | 复制人工疑难和身份不可恢复的源文档到 unknown，并生成可追溯清单。 |
| `c_web_normalizers.v2.py` | 命名对照入口；可导入版本见 c_web_normalizers_v2.py。 |
| `c_web_normalizers_v2.py` | Web/PDF 共用归一化 API（V2 过渡层）。 |
| `c_web_text_rules.v2.py` | 命名对照入口；可导入版本见 c_web_text_rules_v2.py。 |
| `c_web_text_rules_v2.py` | Web 文本/日期公共 API（V2 过渡层）。 |
| `c_web_zhilian_rules.v2.py` | 命名对照入口；可导入版本见 c_web_zhilian_rules_v2.py。 |
| `c_web_zhilian_rules_v2.py` | 可复用的智联规则 API（V2 过渡层）。 |
| `classify_passed_html_by_language.py` |  |
| `codex_word_html_json_100.py` | 隔离的 Word -> HTML DOM -> JSON 试跑流程。 |
| `dedupe_pdf_semantic_overrides.v2.py` |  |
| `docs_to_html_and_complete.py` |  |
| `jsons_to_complete.py` | jsons_to_complete.py |
| `pdf_gpt_review_compare.v2.py` |  |
| `pdf_gpt_review_resolve.v2.py` |  |
| `pdf_json_field_strict_audit.v2.py` |  |
| `pdf_json_strict_audit.v2.py` |  |
| `pdf_raw_text_v2.py` |  |
| `pdf_rebuild_audit.v2.py` |  |
| `pdf_rebuild_candidate_audit.v2.py` |  |
| `pdf_rebuild_extract.v2.py` |  |
| `pdf_rebuild_finalize.v2.py` |  |
| `pdf_rebuild_issue_table.v2.py` |  |
| `pdf_rebuild_map.v2.py` |  |
| `pdf_rebuild_merge.v2.py` |  |
| `pdf_rebuild_semantic_repair.v2.py` |  |
| `pdf_source_completeness_repair.v2.py` |  |
| `process_word_html_to_json.py` |  |
| `process_word_to_html.py` |  |
| `process_xls_html_to_json.py` | 独立的 XLS 简历重建入口。 |
| `process_xls_to_html.py` |  |
| `reuse_complete_v1_jsons.py` |  |
| `run_chinese_english_html_to_json.py` | 中文主版 + 英文独立版 HTML -> JSON 语义解析器。 |
| `run_chinese_html_to_json.py` | complete-transfered-htmls\docs\中文 目录专属 HTML -> JSON 转换解析器。 |
| `run_liepin_html_to_json.py` | 猎聘网简历 HTML -> JSON 专用转换脚本。 |
| `run_web_html_to_json.py` | complete-transfered-htmls\web 目录 HTML -> JSON 专用转换脚本。 |
| `run_zhilian_html_to_json.py` | 智联招聘简历 HTML -> JSON 专用转换脚本。 |
| `web_batch_report.v2.py` | Rebuild a full Web batch report from the durable conversion map. |
| `web_conversion_map.v2.py` | Build the authoritative Web-source conversion map. |
| `web_full_repair.v2.py` | In-place, schema-strict repair for every Web conversion-map record. |
| `web_full_review.v2.py` | Independent, read-only review of the Web conversion code and outputs. |
| `web_html_json_reconcile.v2.py` | Compare every Web JSON output with its mapped HTML-like source. |
| `web_html_json_repair.v2.py` | Incrementally repair Web JSON files using the issues recorded by reconcile v2. |
| `web_html_to_json.v2.py` | complete-transfered-htmls\web 目录 HTML -> JSON 专用转换脚本。 |
| `web_internship_boundary_recovery.v2.py` | Record and verify recovery from the former `intern`/`International` boundary defect. |
| `web_json_audit.v2.py` | Audit Web HTML-like -> JSON v2 outputs against the conversion map. |
| `web_multilingual_repair.v2.py` | Offline, in-place multilingual repair for Web JSON outputs. |
| `web_output_organize.v2.py` | Review, rename and flatten every Web JSON output into one directory. |
| `word_batch_without_json_report.v2.py` | 列出 OCR/unknown 批次中未被任何结果 JSON 认领的源文档。 |
| `word_chinese_english_identity_retry.v2.py` | 隔离复制中英文待处理 HTML，并注入由源证据确认的姓名语义节点。 |
| `word_chinese_japanese_html_to_json.v2.py` | 中日混合目录 HTML -> complete-v1 JSON 专用解析器。 |
| `word_chinese_source_repair.v2.py` | 按中文源文审计证据保守修复暂存 JSON。 |
| `word_difficult_review_defer.v2.py` | 将剩余自动 review 疑难项转入人工处理队列，并保留 HTML。 |
| `word_english_parser_stage.v2.py` | 筛选英文解析结果：排除图片型猎聘，并阻止有工作/教育标题却解析为空的 JSON。 |
| `word_failed_batch_finalize.v2.py` | 终止 failed1 无输出源文件，并清理已判定无效的批次副本与结果 JSON。 |
| `word_full_docs_repair.v2.py` |  |
| `word_html_audit_fix.v2.py` |  |
| `word_invalid_unknown_terminalize.v2.py` | 将 unknown 校验失败 JSON 及其全部源文档登记为无效简历终态。 |
| `word_japanese_html_to_json.v2.py` | 日文语义 HTML -> complete-v1 JSON 解析器。 |
| `word_japanese_identity_retry.v2.py` | 从日文候选文件名末段或直接父目录提取明确姓名，补语义节点重试。 |
| `word_japanese_name_retry.v2.py` | 为日文解析姓名失败项补充可追溯的姓名语义节点，输出隔离重试 HTML。 |
| `word_multilingual_parser_stage.v2.py` | 按正文语言段证据筛选通用解析结果；缺少真实语言段的结果不进入审计。 |
| `word_multilingual_v1_match_stage.v2.py` | 按已解析身份与联系方式，暂存 complete-v1 中可严格审计的多语言候选。 |
| `word_nonchinese_known_name_repair.v2.py` | 修复已由源文件明确确认的多语言 JSON 姓名并按姓名+联系方式重命名。 |
| `word_nonchinese_semantics_repair.v2.py` | 修复多语言候选中已由源文确认的语义错位，不制造不存在的履历版本。 |
| `word_nonchinese_v1_repair.v2.py` | 增量修复 complete-v1 多语言 JSON，输出到暂存区，不覆盖正式结果。 |
| `word_ocr_folder_refresh.v2.py` | 让 OCR 工作目录只保留当前 pending_user_ocr 文档并刷新清单。 |
| `word_schema_extension.v2.py` | 隔离的 Word -> HTML DOM -> JSON 试跑流程。 |
| `word_semantic_html_audit.v2.py` |  |
| `word_semantic_html_repair.v2.py` |  |
| `word_staged_audit_input.v2.py` | 把隔离解析目录中的 JSON 组装成多语言源文审计输入。 |
| `word_strong_candidate_stage.v2.py` | 从中文解析暂存区筛出可保守晋级的强简历候选。 |
| `word_to_html_to_json.v2.py` |  |
| `word_unique_name_reuse_stage.v2.py` | 按源路径明确姓名与正式库唯一姓名匹配，暂存复用候选供源文审计。 |
| `word_verified_identity_inject.v2.py` | 向已人工核实的语义 HTML 注入权威姓名节点。 |
| `xls_bidirectional_review.v2.py` | Choose the better value per field between rebuilt XLS JSON and complete-v1. |
| `xls_conversion_map.v2.py` |  |
| `xls_dom_repair.v2.py` | Apply the current semantic DOM cleanup to already-generated XLS HTML. |
| `xls_field_audit.v2.py` | Strict field-by-field DOM -> JSON audit for the XLS batch. |
| `xls_html_json_audit.v2.py` | Audit the XLS source -> semantic HTML -> JSON chain for the 100-row batch. |
| `xls_incremental_reprocess.v2.py` | Rebuild only XLS sources whose current profile DOM/JSON is demonstrably bad. |
| `xls_json_audit.v2.py` | Strict post-run audit for every rebuilt XLS JSON against its source map. |
| `xls_json_normalize.v2.py` |  |
| `xls_report_rebuild.v2.py` | Reconstruct the full XLS report after targeted subset reruns. |
| `xls_side_by_side_reprocess.v2.py` | Incrementally rebuild XLS files that contain left/right language resumes. |
| `xls_source_html_json_audit.v2.py` | Conservative source -> HTML -> JSON coverage audit for the XLS batch. |
| `xls_to_html_to_json.v2.py` | 独立的 XLS 简历重建入口。 |

## v2/resume_importer（V1 遗留库）

V2 的 19 个脚本仍 `import resume_importer.*`（分类器、文本抽取、结构化解析器等），所以随 v2 一起放在 `python/v2/resume_importer/`。

