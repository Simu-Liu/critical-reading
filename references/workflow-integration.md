# 七模块集成合同

统一内部七个Skill的接口。优先级：用户本轮要求 → 当前Vault有效模板及本合同 → 内部模块。保留原职责、状态和Knowledge冻结schema，不让旧示例覆盖用户选择。

## 路径与模板

新写入只用 `vault/`、`fulltext/`、`Notes/`、`knowledge/`、`templates/`。旧编号目录仅为同论文旧链接的读取输入。命令从本Skill根目录运行，加载本包模块而非全局旧版本。

AI模板：用户明确指定 → Vault `templates/critical-reading-template.md` → 本包 `assets/analytical-note-template.md`。本包 `templates/论文精读模板.md` 为同版兼容入口。个人模板：Vault `templates/personal-reading-template.md`或本包starter，正文只含导航和自由留白。知识模板：Vault `templates/知识库模板/`或本包同目录六模板，仍遵守Knowledge冻结schema。

## 字段交接

新AI结构不要求旧 `study_area/theme/methodology/core_variable/key_finding` 属性。消费者按真实字段/章节提取：

| 语义 | 当前来源 |
|---|---|
| 方向/主题 | research_directions、article_type、Gap与科学问题 |
| 方法/设计 | model_system、perturbation、各面板1–3句话 |
| 机制/变量 | mechanism_axis、机制链和图组 |
| 发现/证据强度 | 创新三项、阶段总结、结论拆解 |
| 限定/是否回源 | 局限、阶段判断、evidence_scope、conclusion_verification及实际Fulltext/PDF |
| 稳定身份 | zotero_key、pdf_key、真实库scope与URI |

旧字段可读，但不能要求用户恢复冗长章节。AI解释/建议与作者发现分开；个人Notes不进入Knowledge source_notes或实验支持计数。

## 单篇、集合与续跑

先读实际文件和技术日志决定最小动作。缺原文只补原文/链接，缺AI只写AI，模板不合只修同路径AI，缺个人页只补关联，缺知识决策只做决策。Collection成员须由实际connector/API或只读SQLite核实，不按磁盘标题猜。

技术记录默认 `knowledge/.meta/critical-reading/workflow.jsonl`，逐阶段追加库scope、key、时间、结果、原因和路径；失败保留可重试状态。身份冲突停止该论文写入，不把临时跳过永久标完成。

`scripts/workflow_state.py inspect`检查实际材料、链接及最近记录，以文件指纹确认是否仍完整。脚本给出下一阶段，不执行科学写作。`ALREADY_COMPLETE`必须上次完整记录与当前指纹一致、适用校验通过。

技术日志与人类日志分开：完整验证后追加 `knowledge/log.md` 的论文可读链接、全文/AI/个人状态、Knowledge动作和验证结果，不显示原始key。批次Knowledge整理另建覆盖账本，每篇真实来源进入匹配页面source_notes；报告总数、全文数、Note-only及未解决项。

## 完成门槛

保留原Collection PDF/正文/图片/AI/linked条件，并单独记录个人关联与Knowledge决策。缺PDF或全文可保留已有Note-only理解，不能标完整精读或fulltext_verified。个人前提不满足记录暂缓，不伪造三层完成。

Knowledge决策为 `KNOWLEDGE_UPDATED`、`NO_KNOWLEDGE_CHANGE`或暂缓；前两者才可完成完整流程。无需变更不要求创建知识页；单篇阅读或模板变化不强制建立综合页。

完整记录需要真实PDF访问确认、全文/图片、AI模板/引文内容审核、个人关联、Knowledge决策、适用Knowledge结构与覆盖审核。程序检结构与指纹，原句真实性、图像、机制和成熟度由agent审核并如实记录，不能声称脚本已替代科学审核。

## 检索适配

恢复严格项目文件模式、三种证据模式、Knowledge路由、全文召回例外、跨论文比较和综述覆盖规则。默认只读，不因问题自动入库。

Gateway协议仅在真实接口存在时使用。无Gateway时用项目文件搜索/rg建候选池，以scope+key、DOI、唯一规范题名去重；记录真实搜索范围、query、命中和新增论文数。不能编造has_more/next_page。小Vault可穷尽实际AI页后报告不足，不自动转外部检索。

个人想法显式检索Notes，标用户思考。判断idea有无依据时另从vault→fulltext核验；个人/Knowledge/全文命中不当作多篇论文。
