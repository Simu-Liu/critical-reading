# 工具与实际校验范围

相对命令从本Skill根目录执行，Python 3.11+。个人保护、索引和状态脚本另需[PyYAML](../scripts/requirements.txt)，使用已有环境，不自动全局安装。

本机安装可在本地config.toml的paths中记录python_executable与python_dependencies。若已配置，使用该解释器并将依赖目录设为本次命令的PYTHONPATH，再运行环境检查。它们是本地运行路径，不随可移植模板传播；换机器时重新确认，不修改系统全局Python。

| 工具 | 用途 |
|---|---|
| tools/config.py、config.example.toml | TOML/环境变量/CLI配置 |
| tools/init_vault.py --vault-root <vault> | 只补缺失目录、模板、配置 |
| tools/check_environment.py --config <toml> | 只读环境/工具/依赖检查 |
| scripts/fetch_zotero_readonly.py --key <key> --data-dir <dir> | 本地API GET及既有MinerU发现 |
| tools/zotero_readonly_fetch.py --key <key> --data-dir <dir> | 只读SQLite备用，元数据/PDF/批注/缓存 |
| tools/zotero_readonly_fetch.py --collection-title <name> --data-dir <dir> | 唯一Collection直接成员列表；子集合须明确范围 |
| tools/run_mineru_production.py --input <pdf> --output <new-dir> | 必要时现有MinerU转换；副本/hash/超时/诊断，不直接发布全文 |
| scripts/link_personal_note.py --vault <vault> --note <vault/...md> --dry-run --json | 预览/建立三层关联，保留个人与原文正文 |
| scripts/refresh_literature_indexes.py --vault <vault> --dry-run | 四类文献索引，保护未知既有内容 |
| scripts/workflow_state.py inspect --vault <vault> --key <key> --scope library | 现状及最小阶段检查 |
| scripts/workflow_state.py record --vault <vault> --event-file <json> | 阶段技术记录；完整完成时重校验与可读日志 |
| tools/validate_research_vault_literature_links.py --vault <vault> | 原Note/Fulltext配对检查的目录适配 |
| scripts/validate_reading_links.py --vault <vault> --note <vault/...md> --json | 新三层schema、身份/图片/路径校验 |
| skills/research-vault-knowledge-maintainer/scripts/validate_research_vault_knowledge.py --vault <vault> --json | 六类知识字段/枚举、真实AI来源、覆盖数、claim/gap结构检查 |

connector/API优先；SQLite始终mode=ro/query_only。多PDF选择附件；缓存与批注不替代原文。优先复用合格MinerU，不因模板修改重跑。实际图像缺失时报告文字阅读范围，不能宣称原图核验或完整完成。

状态event JSON含zotero_key、scope、stage、status、title、reason。COMPLETE还需pdf_access为local/remote，knowledge_decision为KNOWLEDGE_UPDATED/NO_KNOWLEDGE_CHANGE，reviews内template/quotes/figures/knowledge_coverage均为passed，以及knowledge_pages实际路径列表（无变更可空，已更新必须非空）。程序重跑结构检查并记录指纹；reviews必须来自本次真实内容审核。inspect只检查现有文件和记录，不自行证明PDF可访问；最近最终暂缓记录会返回fulltext阶段，实际恢复后再记录成功阶段。

自动检查不能代替科学审查：章节/覆盖、证据role、条件争议、推断、图像与原句仍按模块合同审核。claim statement_hash以normalized_statement去首尾空白后按UTF-8计算SHA-256；hash一致只证明文本一致，不证明实验真实。

缺失/未执行的验证如实报告；无知识页的结构检查不能称为已核验知识内容。普通阅读只做适用标准校验；扩展验收仅用户请求或Skill开发时执行。

测试用隔离Vault、合成SQLite与假的MinerU进程，不连接实时Zotero或改真实论文。运行 `python -m unittest discover -s tests -v` 和 `python -m unittest discover -s scripts -p test_reading_helpers.py -v`；独立试用另检查实际决策与文件。
