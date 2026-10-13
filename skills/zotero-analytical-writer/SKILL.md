---
name: zotero-analytical-writer
description: "使用 Zotero metadata、批注和可访问的全文证据，按当前 Vault 模板创建或更新中文精读笔记，并确保 Zotero 链接、公式与原文引用真实可追溯。"
---

# Zotero Analytical Writer

## Critical Reading集成

执行本模块前读取[统一接口](../../references/workflow-integration.md)。保留本模块完整职责，并使用当前vault/fulltext/Notes/knowledge/templates目录；新精读结构与个人作者身份规则优先于旧示例。命令相对本包根目录运行。

## Canonical template

先读本Vault `templates/critical-reading-template.md`，缺失则用本包 `assets/analytical-note-template.md`；用户明确指定模板优先。本包 `templates/论文精读模板.md`是相同版本的兼容入口。遵守[新阅读规范](../../references/reading-workflow.md)，同路径更新而不制造重复页。

结构：研究方向/摘要/自动评分 → Gap与科学问题 → 创新点三项简述 → Results顺序图组解析及阶段判断 → 机制链 → 结论拆解 → 局限与后续研究 → 关联知识与个人页 → 参考文献/机制图。

创新点只有创新主张、与已有研究的差异、对应科学问题。既有边界和问题意义要具体。每个主图小面板1–3句，说明方法、分组、结果，不列样本量或重复数；几个面板完成一个发现/机制环节后立即总结，连接真实先前主图、补图和论文援引研究，判断证据力度与可增加实验，然后继续后续面板。补图不单独解析。不生成创新证据地图、独立方法/结果表、独立创新评估或统计章。

个人想法使用独立Notes页，AI页只保留入口和明确标注的AI建议；不在AI页留结构化“我的想法”待填栏，不替用户发言。[个人保护合同](../../references/linking-and-authorship.md)规定相同属性键、独立评分/分类和正文保护。首次完整精读后通过本包关联脚本创建空白个人页；已有页原文保留。

## 职责与语料顺序

Writer 只负责分析层：`metadata + annotations + MinerU Fulltext + 必要时 PDF → 中文 analytical note`。

- Fulltext 是原文证据，分析笔记是中文理解层；不得把二者混为一谈。
- 保留当前模板的研究方向、核心 Gap、创新简述、图组阶段证据判断、个人页入口、Zotero URI、MinerU 来源和 Dataview 评分逻辑；区分作者报告的发现与读者自己的判断。
- 不负责 PDF→MinerU；缺全文时交给 `zotero-fulltext-archiver`，不要自行伪造原文。
- 若已有正式 Fulltext，先复用并校验，不因 Note 模板修整而重新运行 MinerU。

## Knowledge handoff contract

The Analytical Note is the structural-library layer for later Knowledge synthesis; it is not a substitute for the Knowledge Page template. Preserve machine-readable fields and make the following handoff explicit whenever the Note will feed Knowledge:

- distinguish author-reported findings, methods, limitations, and the writer's interpretation;
- retain the exact `zotero_key`, `note_path`, `fulltext_path`, formulas, quotations, and PDF/Fulltext entry points;
- record which conclusions were checked against Fulltext and which remain Note-only;
- never mark a Knowledge claim as `fulltext_verified` merely because the Note contains a summary;
- if a field or conclusion cannot be located in the Note or Fulltext, write “未在当前材料中定位到可核验原文”，not a reconstructed quote or inferred page number.

When a later Knowledge task asks for “all papers”, the Knowledge Maintainer must read the Note's structured fields and the linked Fulltext independently; the Writer must not collapse the two layers into a single unsupported summary.

## Frontmatter 与稳定身份

Keep the selected template's frontmatter and replace its placeholders with verified values. For the current mechanism template, preserve `research_relevance`, the multi-value `research_directions`, `article_type`, `model_system`, `perturbation`, `mechanism_axis`, the five `quality_dimensions`, `tags`, and the Zotero/PDF/source fields. Do not reintroduce the repository's former `theme`/`study_area`/`methodology` schema when it conflicts with the selected template. Add the following identity and navigation fields after the template fields when the values are known:
```yaml
type: literature-note
zotero_key: "Q22PFLNV"
pdf_key: "4RMSR7ZR"
doi: "..."
collection: "创新经济地理"
note_path: "vault/创新经济地理/论文标题.md"
fulltext_path: "fulltext/创新经济地理/Q22PFLNV.md"
```

New Analytical Notes are written only to `vault/<collection>/<paper>.md`; new Fulltext records are written only to `fulltext/<collection>/<zotero_key>.md`. Historical `note/` and `论文库/` files may be read during migration, but are never destinations for new files. Historical `03fulltext/` links may be resolved as a read fallback; normalize a path only when updating that same Note.

## 原文引用规则

- “主要发现 + 原文引用”中的原文必须真实出现在 MinerU Fulltext 或 Original PDF。
- 严禁根据中文摘要反向生成英文 quote；定位不到时写“未在当前全文中定位到可核验原句”。
- 引用要保留必要上下文，检查否定、条件、稳健性限定、假设和局限。
- PDF 页码只有在可靠映射或实际 PDF 验证后才写入 `zotero://open-pdf/...?...page=` 或写入“PDF 第 n 页”；否则保留 Fulltext 链接并写“PDF 页码未验证”。不能因为 Fulltext 的 `page_mapping: unknown` 就猜页码，也不能因为页码未知而阻止通过原 PDF 直接核验引文。
- 结论区每一条“主要发现”都要紧邻至少一条真实原文引用；先在 MinerU Fulltext 定位，再在 Original PDF 核对上下文、否定、条件、稳健性和页码。找不到原句时明确写“未在当前全文中定位到可核验原句”，不得反向生成 quote。

## 内容与格式约束

- 核心 Gap、科学问题、创新点、实验设计、证据位置和个人判断必须来自真实材料，不复制大段摘要；无法定位的信息明确标记为 NR。
- 过滤作者地址、单位、邮编、邮箱、基金号和排版垃圾；数据与方法缺失时如实说明。
- 公式仅在原文可靠时保留；乱码或残片不强行解释，也不为占位符生成符号拆解。
- 写入前检查 YAML、美元符号配对、`zotero://select/...` 和 PDF/Fulltext 入口。
- 写入前检查标题层级、模板占位符是否清除、结论是否成对、公式是否闭合，以及 `fulltext_path` 与 Note↔Fulltext 双向入口是否存在。
- `关联精读笔记` 只保留与研究问题、方法或结论存在直接关系的真实 Note；没有可确认的关联时，保留章节说明但移除示例链接。

## 写入与索引

1. 先判定是新建还是更新指定 Note；两种情况都先读取当前 Vault 模板或仓库随附模板。更新时允许重排正文以匹配模板，但不得改变稳定身份或制造重复 Note。
2. 在基本信息区的链接行加入 `全文 Markdown：[[fulltext/<collection>/<zotero_key>]]`（路径存在时），并保留可验证的 Zotero 入口。
3. 新建论文笔记时才刷新四个根 Dataview 索引；更新既有 Note 不触发全库批量重写，但若标题、路径或索引字段变化，定向刷新受影响索引。




## 个人关联、Knowledge和索引交接

用本包scripts/link_personal_note.py先dry-run再正式关联；前提缺失记录暂缓，不伪造Fulltext。Knowledge消费者读取research_directions/article_type/model_system/perturbation/mechanism_axis及图组/结论章节，不要求旧theme/study_area/methodology字段。保留evidence_scope和conclusion_verification；只有逐条回源才能标全文已核验。每次正常入库都交单篇编排做Knowledge决策，不能因个人页已创建就跳过。

四类索引位于vault/_index/：文献索引、研究主题索引、研究方法索引、字段补全检查。用scripts/refresh_literature_indexes.py先dry-run；只在新建或相关字段/路径变化时维护。只计type=literature-note且note_origin不是user的AI页，Notes/全文/Knowledge不计论文数。
