---
name: critical-reading
description: "保留 Zotero Analytical Workflow 完整流程并扩展生物医学精读：Zotero获取、MinerU全文归档、图组证据分析、集合增量续跑、Knowledge维护和文献检索；独立保存自由书写的个人Notes，与AI精读及Zotero关联，区分论文证据与个人idea。"
---

# Critical Reading

统一入口，内部保留原工作流的七个职责模块。按任务读取并执行实际模块及其引用。已有正式材料优先复用，更新只补缺失或失效阶段。

## 任务路由

| 请求 | 本包执行模块 |
|---|---|
| 精读、添加、更新指定论文或检查入库状态 | [单篇编排](skills/research-vault-ingest-orchestrator/SKILL.md)，按阶段加载各模块 |
| Collection、小批量论文、继续上次任务 | [集合管理](skills/zotero-collection-manager/SKILL.md) |
| Zotero元数据、PDF、批注、缓存 | [材料获取](skills/zotero-data-fetcher/SKILL.md) |
| 复用MinerU Markdown、补全文、必要时转换PDF | [全文归档](skills/zotero-fulltext-archiver/SKILL.md) |
| 生成或修整AI精读 | [精读写作](skills/zotero-analytical-writer/SKILL.md)与[新阅读规范](references/reading-workflow.md) |
| 主题、概念、方法、关系、争议、综合和知识索引 | [Knowledge维护](skills/research-vault-knowledge-maintainer/SKILL.md) |
| 文献查找、比较、综述、原句和证据查询 | [文献检索](skills/research-vault-literature-retrieval/SKILL.md) |
| 个人页关联、记录或检索我的idea | [个人内容与联动](references/linking-and-authorship.md)；核验证据另走文献检索 |

内部模块是本包实际执行资源，不依赖全局同名旧Skill。相对命令从本Skill根目录执行。模块接口统一遵守[集成合同](references/workflow-integration.md)。

## 工作区与来源分层

从用户位置、当前Obsidian工作区或本地配置确认vault_root，不从Skill安装目录推断。

| 内容 | 当前目录 | 身份 |
|---|---|---|
| 作者原文与图片 | fulltext/<collection>/<zotero_key>.md | literature-fulltext |
| AI单篇精读 | vault/<collection>/<paper>.md | literature-note / note_origin: ai |
| 用户自由想法 | Notes/<paper> — 我的思考.md | personal-reading-note / note_origin: user |
| 跨论文知识、索引、人类日志 | knowledge/ | 六类冻结Knowledge type |
| claims/gaps、覆盖账本、技术续跑日志 | knowledge/.meta/ | 机器记录，不是知识页或论文 |
| 用户可编辑模板 | templates/ | 精读、个人页、知识库模板 |

稳定身份使用父条目zotero_key加真实库范围；pdf_key是附件身份。标题不能代替主键。01knowledge/02vault/03fulltext只作为同论文旧链接的读取输入，不重新建立这些目录或批量迁移无关论文。

## 新增阅读和个人规则

AI写作优先使用当前Vault的templates/critical-reading-template.md，缺失时使用[随附模板](assets/analytical-note-template.md)。Writer和Knowledge消费端都接受这套结构：

- Gap与科学问题 → 创新简述 → 按Results顺序的小图解析与阶段证据判断 → 机制链 → 结论拆解 → 局限与后续研究。
- 每个创新点只含创新主张、与已有研究的差异、对应科学问题；差异说明已有认识边界及解决问题的意义。
- 每个主图小面板1–3句话描述方法、分组、结果；不写样本量/重复数，不另建统计、全局方法、创新证据地图或独立创新评估章。
- 几个面板完成一个发现或机制环节，立即总结并判断证据，与之前主图、相关补图和本文援引研究连接，再继续。补图融入论证，不单列解析章。
- research_directions是唯一方向字段，可多选11个已确定方向；方向标签、五维评分和Dataview规则见[阅读规范](references/reading-workflow.md)。
- AI/个人属性键对应，个人正文自由留白。已有个人正文、评分、分类、自定义值保持原样，不替用户写想法或将其当作论文证据。

## 完整入库与增量维护

正常指定论文：现状检查 → Zotero身份 → 必要的全文阶段 → 必要的AI写作 → 个人关联 → 文献链接/索引 → Knowledge决策及必要更新 → 最终校验 → 追加日志。集合管理按同一流程逐篇执行并保留失败重试状态。

恢复原Knowledge决策：每篇完整论文明确更新、无需变更或暂缓。NO_KNOWLEDGE_CHANGE是合法成功，不强迫每篇创建知识页，也不把改模板当作科学贡献。主题/综合创建仍须通过原成熟门槛。

[workflow_state.py](scripts/workflow_state.py)提供现状检查、文件指纹续跑和追加日志；[refresh_literature_indexes.py](scripts/refresh_literature_indexes.py)维护四类索引。它们不生成科学内容，写作和科学判断由对应模块完成，不称为无人审核的一体化研究引擎。

无全文或附件保留原FULLTEXT_DEFERRED/部分状态。个人关联脚本需真实同论文全文与附件；前提不满足时记录暂缓，不伪造路径或原文，不宣称三层完成。

## 工具与校验

按[工具与运行方式](references/tools-and-validation.md)选择实际可用能力。保留配置、初始化、环境检查、只读SQLite备用读取、可选MinerU runner、文献链接与Knowledge验证器；本地API获取和个人保护脚本继续保留。PDF只读，优先复用合格MinerU结果；软件缺失时报告暂缓，不擅自安装。

完成前运行本次适用自动检查，并由agent核验图组覆盖、原句、模板、Knowledge覆盖和推断边界。结构检查不等于科学结论真实或原图已看过。普通阅读不运行扩展验收；修改本Skill时用隔离材料测试。

检索默认只读，先AI精读定位论文，再定向原文/PDF。Knowledge是派生导航，个人Notes是想法来源，均不能充当作者实验。普通文献索引仅计vault/内正式AI精读，同篇全文/个人页不重复计数。

Zotero URI、标签生成与实际写回分别记录。实际标签/反向链接同步只在用户请求且有可用写接口时执行，不直接写Zotero数据库，不将未执行同步标成功。

## 交付与来源

保存真实文件并提供AI页、个人页及本次Knowledge变更入口，报告部分状态、覆盖和真实验证结果。复制版按用户要求另提供。

七模块、工具、知识模板和原有测试复制并改编自[Zotero-Analytical-Workflow-Skills](https://github.com/cheneternity/Zotero-Analytical-Workflow-Skills)。本包统一适配当前目录、新精读标准与个人作者身份规则。
