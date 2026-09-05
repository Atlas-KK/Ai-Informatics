# AI 产品经理情报知识库

单用户、本地优先的 AI 情报知识库。当前已完成 Phase 2～7 本地基线，并完成 Phase 8 的本地/Fake 安全、恢复、性能和追踪审计工具。真实外部网络、真实 LLM/Embedding、系统调度、飞书、连续 7 个自然日试运行和人工质量抽检仍需分别取得授权或形成实际证据。

## 权威文件

- PRD：`D:\AI_informatics\Ai情报搜集系统\AI情报知识库_PRD_工作稿.md`，v3.0
- 开发执行文档：`D:\AI_informatics\Ai情报搜集系统\AI情报知识库_Codex开发执行文档_v1.1.md`，v1.1-AC
- UI 参考：Figma 文件 `N2TBiN3T1vELodjyM5e3FD`；2026-09-05 的新 UI 原型评审为不通过，故其仅可作视觉与信息架构初稿，不能替代 PRD v3.0 或作为实现基线。详见 [UI/PRD 评审报告](docs/figma-ui-prd-acceptance-report-2026-09-05.md)。

## 当前实现状态

| 能力 | 状态 | 说明 |
| --- | --- | --- |
| 本地运行骨架与 SQLite 初始化 | 已实现 | 启动时迁移数据库、创建数据目录并运行恢复器 |
| Phase 2 正式档案协议 | 已实现 | Raw/SQLite/Archive staged 提交、READY 可见性、恢复、回收站与 Vault 投影 |
| Phase 3 来源与采集 | 已实现（fixture） | Web、RSS、GitHub、视频只消费固定 fixture；Manual Inbox 为本地入口 |
| Phase 4 事件聚合 | 已实现 | 确定性规范化、匹配、版本、观点和候选 |
| Phase 5 加工与评分 | 已实现（Fake LLM） | 领域/应用/存储路径有验收测试，并由 Phase 7 本地 API/UI 消费 |
| Phase 6 日任务与日报 | 已实现（本地/Fake） | 唯一锁、超时、断点、日报、分段 outbox 与可观测事件 |
| Phase 7 HTTP API | 已实现 | 仪表盘、档案/详情、搜索、用户数据、运行、设置、反馈、校准与扩展搜索接口 |
| Phase 7 Web 页面 | 已实现 | 今日、主题、历史检索、来源、质量、运行、设置、回收站及详情抽屉 |
| Phase 8 本地验收 | 部分完成 | full gate、安全、恢复、真实浏览器 1 万条性能及 12 FR/76 AC/9 NFR/CTD 追踪报告已落地；真实时间与外部服务项不冒充通过 |
| 真实外部适配 | 未授权 | LLM、Embedding、扩展搜索、飞书与系统调度继续使用 Fake/显式降级边界 |

## 本地启动

Windows 一键启动：双击根目录的 `start.bat`。脚本会在缺少依赖时调用现有 bootstrap，分别打开后端与前端窗口，等待服务就绪后自动在默认浏览器打开系统界面；关闭这两个服务窗口即可停止系统。

手动启动方式：

1. 在 PowerShell 中执行 `powershell -File scripts/bootstrap.ps1`。
2. 复制 `.env.example` 为 `.env`；Phase 1 不需要填写外部服务凭证。
3. 后端：`.\.venv\Scripts\python.exe -m ai_intel.main`。
4. 前端：进入 `web` 后执行 `pnpm dev`。

后端默认仅监听 `127.0.0.1:8000`，前端默认使用 `127.0.0.1:5173`。

## 运行环境与配置

- Python：`>=3.12,<3.13`，依赖版本锁定在 `requirements.lock`。
- 前端包管理器：`pnpm@11.19.0`。`start.bat` 要求 Node 20.19+、22.12+ 或更高主版本；当前依赖在 Node 16.20.2 下无法运行 ESLint/Vitest，本次使用质量脚本优先选择的 bundled Node 24.19.0 验证通过。包清单暂未声明 `engines` 字段。
- 当前后端实际读取 `AI_INTEL_DATA_DIR`、`AI_INTEL_HOST` 和 `AI_INTEL_PORT`；host 只接受 `127.0.0.1` 或 `::1`。
- `.env.example` 中 LLM、Embedding、飞书字段是后续阶段占位。当前运行不需要真实外部服务凭证，不得把真实值提交到仓库。
- 若本机 PowerShell 执行策略阻止 `.ps1`，可在确认脚本来源后为单次命令增加 `-ExecutionPolicy Bypass`；不要修改系统级策略来绕过项目约束。

## 目录结构

```text
ai-intel-kb/
├─ start.bat           # Windows 一键启动并打开本地系统界面
├─ src/ai_intel/
│  ├─ domain/          # 纯领域规则与不可变量
│  ├─ application/     # 采集、聚合、加工、选择、校准、选题和归档编排
│  ├─ ports/           # 采集器、LLM、仓储协议
│  ├─ adapters/        # fixture、Fake LLM/Feishu 与 Manual Inbox 适配器
│  ├─ infrastructure/  # SQLite、正式档案、恢复和 Vault 投影
│  └─ api/             # 本地 FastAPI 查询与用户操作接口
├─ migrations/         # Alembic 迁移，当前 head 为 0009_phase7_local_web
├─ tests/              # foundation 与 Phase 2～8 契约/验收测试
├─ web/                # React/Ant Design/ECharts 本地工作台
├─ scripts/            # bootstrap、质量门禁、secret scan 和 Phase 8 验收/采证
├─ docs/phase8/        # 脱敏命令证据、追踪报告、风险清单和证据格式
└─ data/               # 运行时数据；不进入版本控制
```

## 已知限制与开发快照

- 自动来源、模型、语义检索和扩展检索仍为 fixture/Fake 或显式降级；没有隐式真实网络调用。
- 运行失败项重试提供可注入接口；生产执行器未配置时返回明确的 503，不伪装成功。
- 前端 production build 已把图表拆为懒加载 chunk；当前主包 gzip 约 368 KB、图表 chunk gzip 约 165 KB。
- 当前生产权限、数据保留期限、备份/恢复目标、允许的外部副作用、日志保留及敏感数据分类仍待产品/用户确认。
- 新 UI 原型存在专题分类与 PRD v3.0 不一致，以及详情版本/来源、校准、扩展搜索和运行重试闭环缺口；在产品确认并通过再验收前，不应将其用于驱动实现变更。
- Git 仓库根目录是上一级 `D:\AI_informatics\Ai情报搜集系统`；截至 2026-09-04，两个权威文档和整个 `ai-intel-kb/` 均未被跟踪，`HEAD=afa57cc` 只有初始提交。不要擅自 `git add`、提交或假设 Git 历史能区分现有改动。

## 质量门禁

```powershell
powershell -File scripts/quality.ps1 -Scope foundation
powershell -File scripts/quality.ps1 -Scope backend
powershell -File scripts/quality.ps1 -Scope frontend
powershell -File scripts/quality.ps1 -Scope full
powershell -ExecutionPolicy Bypass -File scripts/phase8-audit.ps1
```

只有脚本真实运行且退出码为 0，才能报告门禁通过。

Phase 2 定向测试：

```powershell
.\.venv\Scripts\python.exe -B -m pytest tests\phase2 -q
```

Phase 3 定向测试：

```powershell
.\.venv\Scripts\python.exe -B -m pytest tests\phase3 -q
```

Phase 4 定向测试：

```powershell
.\.venv\Scripts\python.exe -B -m pytest tests\phase4 -q
```

Phase 5 定向测试：

```powershell
.\.venv\Scripts\python.exe -B -m pytest tests\phase5 -q
```

2026-09-04 的 Phase 8 本地审计：`quality.ps1 -Scope full` 以退出码 0 完成；secret scan、Ruff、格式、mypy、`102 passed`、前端 lint/Vitest/build、模拟交互 E2E 和真实 FastAPI+SQLite 浏览器 E2E 全部通过。安全定向用例 5 条、恢复定向用例 11 条以及 1 万条 repository/SQLite/真实浏览器性能对账均通过；本次两条真实浏览器证据记录冷启动约 1.51～1.63 秒、筛选约 0.24 秒。命令证据绑定当前源码指纹，原始计时和硬件信息保留在脱敏证据中。Phase 8 当前总体为 `PARTIAL`：实际 7 日试运行、人工质量抽检与 30 日观测尚未执行，真实适配器因未授权为 `BLOCKED`。详见 [Phase 8 验收报告](docs/phase8/phase8-acceptance-report.md) 和 [追踪报告](docs/phase8/traceability-report.md)。

Phase 8 的实际计划运行只读采证命令如下；它不会创建或触发 Windows 计划任务：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/phase8-soak.ps1
```

## Phase 5 加工与评分边界

- LLM 端口只接收固定系统指令、JSON Schema 和“不可信正文”；当前只提供无工具权限的 Fake LLM，坏 JSON、缺字段和超时均只写失败记录。
- 英文保留原文并生成中文译文、摘要、结论和产品价值；中文不重复翻译；每条结论必须引用当前聚合版本的有效证据 ID。
- 主专题限定为 PRD 四类，可带多个二级标签；幻觉、注入、越权、投毒、数据污染和泄露由纯规则强制路由至“AI 工程安全与可靠性”。
- 评分固定为来源权威性 30%、及时性 25%、传播范围 15%、信息密度 15%、创新性 15%；缺互动数据使用中性回退值，来源权威参数可独立覆盖。
- 只有总分不低于 70 的候选参与排序，同分依次比及时性和来源权威性，最多 50 条；1～10 为必读、11～30 为重要、31～50 为扩展，不为凑数降低阈值。
- 反馈本身不修改配置；校准必须用户发起，展示样本数、不确定性、影响维度和范围，确认后追加新配置并留审计；拒绝、回退和历史重评均不覆盖旧记录。
- 必读项由每日分层流程自动生成标题、大纲、爆点和支撑来源；其他层级只允许手动生成，没有完整文章或自动发布字段。
- 入选项仍必须通过 Phase 2 staged 协议才能变为 `READY`；候选事件、加工结果、评分、入选、正式版本和上游 Evidence 之间保留追溯链。

## Phase 4 聚合边界

- URL、标题、正文、作者和实体均以确定性纯函数规范化；同一批输入不受顺序影响。
- 规范化 URL、正文指纹及标题+实体特征用于事件匹配；歧义匹配显式失败，不由 UI 状态参与决策。
- 每个观点保存支持来源集合、支持来源数、有效来源数和来源覆盖率；覆盖率不表示事实置信度。
- 新事实、新观点、新来源或同源正文变化会追加聚合版本并进入当日待评分候选；旧版本、证据和匹配键由 SQLite 触发器保护为只追加。
- 仅时间变化和语义等价正文返回 `NO_CHANGE`，不新增版本或候选；扩展搜索未选结果返回 `IGNORED`。
- 扩展搜索选中结果与 Manual Inbox 使用同一历史事件匹配流程；同一事件同一天最多保留一条待评分候选。
- 聚合证据通过外键指向 Phase 3 原始快照；Phase 4 不写 Phase 2 正式 READY 档案，须等待后续评分阶段。

## Phase 3 采集边界

- 来源配置支持 Web、RSS、GitHub 与视频四类自动来源，以及暂停、恢复和逻辑删除；专家白名单与来源建立独立关联。
- 每次运行在开始时固化 `window_end=started_at`、`window_start=started_at-7×24h` 和启用来源快照；恢复来源不会补采七日前内容。
- Web、RSS、GitHub README 与视频官方英文字幕适配器仅消费固定 fixture。无官方字幕时只保留公开元数据，媒体下载与 ASR 端口调用次数必须为零。
- GitHub 日榜、周榜、AI 相关性和白名单独立执行；Star 增长仅用本地追加式快照计算，历史不足返回 `insufficient_history`。
- 正文只在模型输入边界按来源配置截断为 10,000、20,000 或 50,000 字符，Raw 原文及哈希保持不变。
- 单一来源抓取或提取失败会记录阶段、原因、时间和重试次数，不阻断其他来源；Phase 3 采集项只进入后续处理队列，不会直接生成 READY 档案。
- `manual-inbox/` 接受带严格 front matter 的本地 Markdown，保存原文件哈希、识别重复并记录损坏文件重试；不计入自动来源尝试数。

## Phase 2 存储协议

- Alembic 从空库升级到 Phase 2 当前 head；对含档案数据库的破坏性回退默认拒绝。
- `RawSnapshot`、`EventVersion`、`Evidence`、`Score` 和评分配置由数据库触发器禁止更新；新事实只能追加新版本。
- Raw、Archive 和 SQLite 通过 `.staging/` 协议提交；只有 `staged_commits.state=READY` 的当前版本对正式查询可见。
- 启动恢复器处理遗留 staged commit、失效记录锁、缺失文件、孤立文件和哈希漂移；异常内容进入 `quarantine/` 并写本地恢复审计。
- 个人笔记及收藏、置顶、已读、回收站状态独立保存，不写入不可变档案。
- 永久删除必须先进入回收站并再次确认；正文、Raw、Archive 和用户数据删除后，只保留不含正文的审计壳。
- `vault-view/` 支持全量和增量重建；外部编辑被隔离或覆盖，不存在向 SQLite、Raw 或 Archive 的反向导入。

## 数据目录边界

运行时在 `data/` 下创建：

- `app.db`：SQLite 权威结构化状态、索引和审计。
- `raw/`：不可变来源快照。
- `archive/`：与事件版本一一对应的不可变正式 Markdown。
- `manual-inbox/`：Phase 3 可选人工投递区；导入结果进入与自动采集相同的后续处理队列。
- `vault-view/`：可重建、非权威的 Obsidian 阅读投影。
- `quarantine/`：恢复器隔离的孤立、缺失关联或哈希漂移文件。

`data/`、`.env`、日志、临时文件、`.obsidian/` 和前端构建产物均不得进入版本控制。
