# 属性对应、个人内容保护与三层联动

## 两种笔记共用schema

AI页与个人页有一一对应的顶层属性键，字段相同不代表判断值必须相同。type与note_origin明确标身份，title保持论文题名；个人页文件名/H1可使用“论文名 — 我的思考”。

| 字段组 | 规则 |
|---|---|
| title / authors / year / journal / doi / pmid / collection / zotero_key / pdf_key / source_format / zotero_uri / pdf_uri | 论文事实与身份一致；不猜缺失数据；既有非空值冲突先解决 |
| research_relevance / research_directions / article_type / model_system / perturbation / mechanism_axis | 新个人页可以继承初始分类；之后用户修改独立保留，不持续强制覆盖 |
| tags | 从research_directions派生相同的Obsidian/Zotero层级标签`研究方向/<方向>`，方向内部`/`改为`-`；AI可有literature-note，个人须用personal-reading-note，不能复制会触发文献索引的身份标签 |
| quality_dimensions / article_quality | 同五个评分子键；AI暂定分数，个人初始五项0；均使用Dataview自动计算，保留既有个人评分 |
| status / date_created / date_read | 页面各自的记录状态/日期；新个人页初始未记录、创建日为本轮日期、date_read留空；已有个人页缺失状态或历史创建日时留空，不猜测或借用AI阅读完成状态 |
| evidence_scope / conclusion_verification | AI记录实际核验范围；个人初始留空，不能因为链接原文就标个人idea为已核验发现 |
| zotero_tag_sync | 未真实写回就用待同步；不能复制一个不适用的人页同步完成声明 |
| type / note_origin | AI=literature-note/ai；个人=personal-reading-note/user |
| note_path | 各页面自己的真实相对路径 |
| analytical_note_path / personal_note_path / fulltext_path | 两份笔记指向同一组三层文件，均可验证存在 |

用户的额外属性不丢弃。两页顶层键采用并集，额外属性只在原页保留原值，另一页补null；不能把用户自定义观点作为AI内容。若用户已有个人笔记没有身份属性，只在关联身份得到确认后补入。

全文不是个人/AI模板：type=literature-fulltext，`note_path`和`analytical_note_path`指AI页、`personal_note_path`指个人页，`fulltext_path`指自己。只修改关联frontmatter，原文正文不改。

## 个人正文

从 [起始模板](../assets/personal-note-starter.md) 生成导航区，分隔线后空白。不复制结构化“我的想法”“科学问题”“假说/实验”等栏目，不自动向用户提问来强制填写。

已有个人正文保持原样，包括未成句、问号、相互矛盾想法、Markdown格式和图片。更新AI页不能润色、归纳、重排或附加观点到个人正文。用户明确要求将其想法记录/整理时才处理对应内容，AI建议另行标识，不伪造用户语气。

旧AI页可能包含用户填写的个人栏目。需要迁移时先确认实际用户内容，保留文字；不可因删除旧栏目误删已写想法。用户只是创建Skill时不改真实既有笔记。

## 辅助脚本

Python 3.11+；[requirements.txt](../scripts/requirements.txt) 声明PyYAML依赖。使用现有可用解释器/依赖，不擅自安装全局环境。

```text
python scripts/link_personal_note.py --vault "E:/ResearchVault" --note "vault/CAR-T/论文.md" --date 2026-10-13 --dry-run --json
python scripts/link_personal_note.py --vault "E:/ResearchVault" --note "vault/CAR-T/论文.md" --date 2026-10-13 --json
python scripts/validate_reading_links.py --vault "E:/ResearchVault" --note "vault/CAR-T/论文.md" --json
```

这只是参数示例，不代表论文.md已经存在。实际note路径从目标论文解析。`--personal`可指定已有的`Notes/`目标；默认文件名从真实论文题名生成。`--date`使用用户所在时区本轮日期；没有日期覆盖时脚本默认系统日期，应检查其是否一致。

先dry-run看目标与变更，不向用户重复索取已授权的可逆本地操作。身份/已有路径冲突不自动覆盖；路径不能逃出Vault或落入其他层。脚本只完成metadata/导航关联，不替代AI正文创作或观点判断。

## 检索与索引

论文事实/引句/证据：`vault`中的AI页 → 对应`fulltext` → 必要时原PDF。AI阶段总结中解释性部分仍是AI判断；正式原句要回源。

“我之前想到什么”“我的假说/idea”：在`Notes`按zotero_key/方向/内容检索，注明个人想法及是否有相邻原文依据。判断该idea是否被支持时另查论文来源，不能把自己的笔记当作独立实验支持。

普通文献索引只识别 `vault` 且 `type = "literature-note"`。个人页即使含title/doi/研究方向也不进入论文计数。个人索引可以单独筛 `type = "personal-reading-note"`。

## Zotero联动

两页都提供条目选择URI及PDF打开URI，真实对应父条目与附件；个人库/群组库URI用实际库信息，不机械套个人库形式。没有实际pdf_key时不生成虚假PDF链接。

Obsidian内部双链与ZoteroURI存在，只证明本地导航可构造，不证明Zotero已保存笔记或标签。Zotero→Obsidian反向链接需要用户请求写回后，使用当前可调用且有写权限的接口；生成正确编码的 `obsidian://open?vault=...&file=...`，必要时写入一个有明确用途的Zotero子Note。未写回时不记录为已同步，直接SQLite写入禁止。
