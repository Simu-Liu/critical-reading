# Zotero 身份与既有 MinerU 原文获取

本资源用于 critical-reading 的获取阶段；不执行中文精读，也不写入 Zotero。身份与原文保全规则改编自 [cheneternity/Zotero-Analytical-Workflow-Skills](https://github.com/cheneternity/Zotero-Analytical-Workflow-Skills) 的 Data Fetcher、Fulltext Archiver。脚本为独立实现，不依赖源仓库配置文件或已安装的其他技能。

## 选择可用数据源

优先使用本次环境实际提供的 Zotero connector/API。取得父条目、PDF 子附件、库类型/id、集合、批注与可访问文件；按下述身份规则核对。没有 connector 时可使用配套标准库脚本，只向 `http://127.0.0.1:23119/api/` 发出 GET，请求不会转到外部网址。Zotero 必须已运行且本地 API 可用；不为这项阅读任务擅自更改 Zotero 设置。

```powershell
python "<skill目录>/scripts/fetch_zotero_readonly.py" --key <父条目键> --data-dir "<已核实的Zotero数据目录>"
python "<skill目录>/scripts/fetch_zotero_readonly.py" --title "<精确标题>" --pdf-key <已选择的PDF附件键> --data-dir "<已核实的Zotero数据目录>"
```

群组库加 `--group-id <真实群组id>`；个人库默认 API `users/0`。URI 从响应中的真实库类型/id 生成：个人库使用 `library/items/...`，群组库使用 `groups/<id>/items/...`。不要将父条目键当作 PDF 键，也不要把库 id 或群组 id 写死到工作流。

`--key` 只接受 `journalArticle`、`preprint`、`conferencePaper` 父条目；附件或 note 键会被拒绝。`--title` 要求标题逐字一致且唯一，查询中的近似结果不能作为身份。若存在多个 PDF，脚本列出候选并要求 `--pdf-key`，不选择第一份。所选 PDF 的 `parentItem` 和库身份必须对应父条目。

无法访问 connector/API 时保留准确的获取状态，使用用户提供的导出/原文继续可进行的工作。若错误来自网络沙箱或批准审核，按当前工具权限请求升级；被拒绝后不要借其他工具绕过。SQLite 锁定时用已启用的本地 API，避免触碰活跃数据库。该API脚本不访问数据库；本包另外保留tools/zotero_readonly_fetch.py的只读SQLite备用，使用mode=ro/query_only，不修改数据库。数据库锁定时保持暂缓并改用API/导出，不强制关闭Zotero。

## 本地附件路径必须由元数据确认

脚本不猜 `%USERPROFILE%/Zotero`，也不按标题全盘搜索。传显式 `--data-dir`，或传已确认对应当前 Zotero profile 的 `--prefs <prefs.js>`。后一方式只有在 `extensions.zotero.useDataDir=true` 且 `dataDir` 为有效路径时使用该目录；未确认自定义目录时改传显式目录。

仅对元数据确认的导入型 PDF，将 `filename` 解析到 `storage/<pdf_key>/`；检查解析后仍在该附件目录，文件真实存在且含 PDF 文件头。外部 linked-file 不在此脚本中解析，可用 connector 实际提供的文件引用。JSON 中 `pdf_found=false` 仅说明本次路径未核实或不可访问，不表示该 Zotero 条目没有原文。

## 复用 MinerU

在已核实数据目录的 `llm-for-zotero-mineru/*/_llm_source.json` 中，用 `parentItemKey` 与 `attachmentKey` 同时匹配身份。不要凭子目录编号、文件名或论文标题认领解析结果。存在多个匹配时分别报告，依据来源/完整性解决冲突，不自动取最新结果。

脚本报告对应 `full.md`、`manifest.json`、图片引用及实际路径，校验 JSON 可读取、正文非空、每个本地图片目标存在且位于来源目录内；外部图链不自动下载。`ready_for_archive` 只表示这些机械检查通过，**不能替代正文完整性检查**。随后应阅读正文开头、中间、末尾，检查标题、Results/Discussion、图注/参考文献等确实存在，无明显截断、乱码或身份冲突。不要因修改精读模板而重新运行 MinerU。

转换器页码/manifest 的 `totalPages` 只作为原始记录，不证明页码映射可靠；精确引用页码必须返回 PDF 核验。补充材料是否提供需独立检查，正文引用 Supplementary Fig./Table 不能证明补充材料已读取。

## 交给下游的最小记录

保留 `zotero_key`、`pdf_key`、`library`、标题/作者/日期/DOI/集合/原有标签、`zotero_uri`、`pdf_uri`、附件访问状态、批注与原文来源。路径只有核实存在后才能填写为可用。批注与 Zotero Notes 是原始输入，其内容不能替代论文证据。

输出 JSON 通过 stdout 给出，可存入当前工作区的可审查运行记录；原始批注可能包含个人内容，不向外部服务发送。归档到 `fulltext/` 时复制正文与必要图片，除 frontmatter 和安全图片路径修复外保留原文，不移动或覆盖 Zotero 源文件。
