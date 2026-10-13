# Critical Reading

面向生物医学论文的 Codex Skill：在保留 Zotero Analytical Workflow 七个职责模块的基础上，按图组推进精读，并独立保存个人想法。

## 功能

- Zotero 元数据、附件、批注和已解析全文获取；SQLite 备用读取始终只读。
- 优先复用 MinerU Markdown；必要时使用已配置的 MinerU 归档全文与图片。
- 提炼 Gap、科学问题及创新点，按 Results 顺序逐个解析主图面板，在完成一个发现或机制环节后判断证据。
- 单篇入库、Collection 小批量调度、可重试状态与断点续跑。
- 保留跨论文 Knowledge 的主题、概念、方法、关系、争议、综合及来源追溯。
- 文献检索先定位 AI 精读，再按需核验原文/PDF；个人想法单独检索和标注。

这些是由 agent 编排的工作流与辅助脚本，不是一个自动生成科研结论的一体化命令。

## 来源分层

| Vault 目录 | 内容 |
|---|---|
| `fulltext/` | 作者原文 Markdown 与图片 |
| `vault/` | AI 单篇精读 |
| `Notes/` | 用户自由书写的个人想法 |
| `knowledge/` | 可追溯的跨论文派生知识 |
| `templates/` | 可在 Obsidian 中编辑的模板 |

AI 页与个人页属性键对应，并联动 Zotero、原文和彼此。已有个人正文、独立评分、分类和自定义属性保持原样；个人 idea 不计作论文实验或科学证据。

## 安装与配置

把本仓库安装为 Codex 的 `critical-reading` 技能目录。Windows PowerShell 示例（目标目录应不存在）：

```powershell
git clone https://github.com/Simu-Liu/critical-reading.git "$env:USERPROFILE\.codex\skills\critical-reading"
Set-Location "$env:USERPROFILE\.codex\skills\critical-reading"
```

macOS/Linux 可克隆到 `~/.codex/skills/critical-reading`。如果使用自定义 `CODEX_HOME`，安装到其 `skills/critical-reading`。已有安装时应先确认目录和本地修改，避免覆盖。

辅助工具需要 Python 3.11+ 和 PyYAML。可使用已有环境，或创建独立环境：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r scripts/requirements.txt
python tools/init_vault.py --vault-root "E:\ResearchVault"
python tools/check_environment.py
```

初始化只补缺失目录、模板及 `config.toml`，保留已有研究文件。按 `config.example.toml` 在本地配置 Vault、Zotero 数据目录及可选 MinerU 路径。`config.toml` 已被 Git 忽略，不随仓库上传。

Zotero 获取需要当前 agent 可访问的数据接口或本地数据。MinerU 仅在需要转换 PDF 时必需；已解析 Markdown 可直接复用。Obsidian Dataview 用于动态评分与索引。安装后在新的 Codex 会话中确认 `$critical-reading` 可选。

## 使用

```text
使用 $critical-reading 精读 Zotero 中的〈论文标题〉，复用已由 MinerU 解析的 Markdown。
我的 Obsidian Vault 是〈目录〉。生成 AI 精读，并关联独立个人笔记。
```

也可要求继续指定 Collection、维护跨论文 Knowledge，或检索“论文证据与我的个人想法”。精读规范见 [SKILL.md](SKILL.md) 和 [阅读规范](references/reading-workflow.md)。

方向分类仅使用 `research_directions`，允许多选；方向清单及派生标签见阅读规范。五维质量由 Dataview 计算。生成 Zotero URI 或标签不等于实际写回；写回只在用户请求且实际写接口可用时执行。

## 目录与验证

`skills/` 保留七个模块；`references/` 保存集成合同；`assets/`、`templates/` 保存模板；`scripts/`、`tools/` 提供关联、续跑、索引、获取和校验工具。

离线验证，不依赖实时 Zotero 或真实 PDF：

```powershell
python -m unittest discover -s tests -v
python -m unittest discover -s scripts -p test_reading_helpers.py -v
```

结构与指纹校验不替代原图、原句和科学判断的内容审核。缺少 PDF、图片或补充材料时保留真实暂缓状态，不宣称完整核验。

## 来源说明

七个工作流模块、部分工具、知识模板与原有测试复制并改编自 [cheneternity/Zotero-Analytical-Workflow-Skills](https://github.com/cheneternity/Zotero-Analytical-Workflow-Skills)。上游独立检索项目为 [Research-Vault-Literature-Retrieval](https://github.com/cheneternity/Research-Vault-Literature-Retrieval)。

本仓库在此基础上适配 `fulltext/vault/Notes` 目录、新的生物医学图组阅读标准、独立个人作者身份、续跑与索引工具。保留上游来源说明，不代表由上游作者维护本改编版本。
