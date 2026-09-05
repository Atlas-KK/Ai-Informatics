# Codex 项目 Harness

本文件是面向 AI/自动化开发代理的项目记忆与操作契约，描述当前仓库可由证据支持的状态；它不替代 PRD，也不得把规划误写成已实现能力。

## 维护元数据

- 最近核验：2026-09-05（Asia/Shanghai）。
- 覆盖范围：`D:\AI_informatics\Ai情报搜集系统\ai-intel-kb` 及其两份上级权威文档。
- Git 快照（已确认）：仓库根目录实际为 `D:\AI_informatics\Ai情报搜集系统`，分支 `main`，`HEAD=afa57cc`（Initial commit）；两份权威文档和整个 `ai-intel-kb/` 当前均为未跟踪文件。因此 Git 历史不能证明应用代码演进，也无法用普通 diff 区分这些文件内的既有改动。
- 结论标签：**已确认**表示本次读取或执行结果支持；**基于代码的推断**表示静态实现指向该行为但未完成对应运行验证；**待确认**表示仓库不能决定，必须由用户或产品负责人确认。

## 权威顺序

1. 当前用户明确指令。
2. `D:\AI_informatics\Ai情报搜集系统\AI情报知识库_PRD_工作稿.md`（v3.0）。
3. `D:\AI_informatics\Ai情报搜集系统\AI情报知识库_Codex开发执行文档_v1.1.md`（v1.1-AC）。
4. 当前代码与测试。

PRD 定义“做什么”，执行文档定义分阶段实施规则；不得修改 PRD 来迁就代码。代码、测试或旧文档与上级权威冲突时，记录冲突并停止相关实现。

## 项目范围、用户与当前发布边界

目标用户是单个本地 AI 产品经理。产品目标是在本机完成情报采集、事件聚合、加工评分、正式归档和后续阅读；MVP 强调可追溯、确定性门禁与本地数据边界。

| 范围 | 状态 | 当前证据 |
| --- | --- | --- |
| Phase 1：骨架、配置、质量入口 | 已实现 | `pyproject.toml`、`web/package.json`、`scripts/quality.ps1`、`src/ai_intel/main.py` |
| Phase 2：SQLite/Raw/Archive staged 提交、恢复、Vault 投影、用户元数据 | 已实现且本次回归通过 | `migrations/versions/0001_*`～`0002_*`、`infrastructure/archive/`、`tests/phase2/` |
| Phase 3：来源/专家配置、7 日窗口、采集、指标、Manual Inbox | 已实现；自动采集仅 fixture | `application/sources.py`、`adapters/collectors/fixture.py`、`tests/phase3/` |
| Phase 4：规范化、匹配、聚合、版本、候选 | 已实现且本次回归通过 | `domain/fingerprint.py`、`domain/event_matching.py`、`application/event_aggregation.py`、`tests/phase4/` |
| Phase 5：Fake LLM 加工、专题、评分、分层、反馈/校准、选题、正式化 | 已实现且本次回归通过 | `application/intelligence_processing.py`、`daily_selection.py`、`calibration.py`、`topic_ideas.py`、`tests/phase5/` |
| Phase 6：调度、日报、飞书、运行观测 | 已实现（本地/Fake）且本次回归通过 | `application/pipeline.py`、`scheduler/`、`delivery.py`、`telemetry/`、`tests/phase6/` |
| Phase 7：业务网页、搜索、可视化 | 已实现且本次回归/E2E 通过 | `api/app.py`、`phase7_repository.py`、`web/src/App.tsx`、`web/e2e/phase7.cjs`、`tests/phase7/` |
| Phase 8：安全加固、真实适配、试运行 | 部分完成 | 本地 full/security/recovery/performance 和追踪审计通过；7 日/人工/30 日未运行；真实适配未授权 |

Phase 8 的 `PARTIAL` 是严格状态：本地/Fake 能力通过不等于真实适配器或自然日试运行通过。

## 架构与模块职责

| 路径 | 职责与边界 |
| --- | --- |
| `src/ai_intel/domain/` | 纯领域规则：标识/时间校验、来源状态、指纹与匹配、版本决策、专题、评分和分层；不得调用网络、数据库或 UI |
| `src/ai_intel/application/` | 用例编排：采集、聚合、加工、每日选择、校准、选题、正式归档、日任务及 Phase 8 纯验收评估；外部能力经端口/仓储进入 |
| `src/ai_intel/ports/` | 采集器、LLM、仓储协议；真实适配器不得绕过这些边界 |
| `src/ai_intel/adapters/` | fixture 采集器、Fake LLM、Fake Feishu 与 Manual Inbox 本地导入 |
| `src/ai_intel/infrastructure/db/` | SQLite engine、表结构和 Phase 2～7 仓储；Alembic 迁移必须与 `schema.py` 同步 |
| `src/ai_intel/infrastructure/archive/` | staged 提交、正式 Markdown 渲染和启动恢复；只有 READY 才可见 |
| `src/ai_intel/infrastructure/vault_projection/` | 从权威档案生成可重建的只读阅读投影；不得反向导入 |
| `src/ai_intel/api/` | FastAPI 本地 API；启动时迁移数据库并运行恢复器；提供 Phase 7 查询和用户操作接口 |
| `web/` | React/Ant Design/ECharts 本地工作台；模拟 E2E 覆盖七类页面和九项写操作，真实栈 E2E 验证 FastAPI/SQLite 契约、刷新持久化与 1 万条页面性能 |
| `scripts/phase8_*`、`docs/phase8/` | Phase 8 一键审计、只读自然日采证、脱敏证据、追踪报告与风险清单 |
| `migrations/` | 从空库到当前 head 的 Alembic 链；破坏性 downgrade 受显式确认门禁约束 |
| `tests/` | foundation 及 Phase 2～8 的契约/验收证据；测试存在不等于本次已经执行 |

主数据流（已确认）：fixture/Manual Inbox → 不可变 Raw 快照 → 确定性事件聚合/版本 → Fake LLM 结构化加工 → 五维评分与每日分层 → Phase 2 staged 提交 → READY SQLite/Archive → 可重建 `vault-view/`。

## 运行、配置与集成边界

- Windows 本地入口 `start.bat` 只编排现有 bootstrap、后端和 Vite 开发服务，并在两者就绪后打开 `http://127.0.0.1:5173`；它不创建计划任务、系统服务或公网监听。
- Python：`>=3.12,<3.13`；后端入口为 `python -m ai_intel.main`，默认 `127.0.0.1:8000`。
- 前端：`pnpm@11.19.0`；Vite 仅监听 `127.0.0.1:5173`。`start.bat` 明确拒绝低于 Node 20.19 或 Node 22.12 的运行时（也接受更高主版本）；系统 Node 16.20.2 不兼容当前 ESLint/Vitest，质量脚本优先使用 bundled Node 24.19.0 可通过前端门禁。包清单尚未单独声明 `engines` 字段。
- 当前 `Settings` 只读取 `AI_INTEL_DATA_DIR`、`AI_INTEL_HOST`、`AI_INTEL_PORT`；host 类型限制为 `127.0.0.1` 或 `::1`。`.env.example` 中外部服务键仅为后续占位，当前不得填入或提交真实值。
- 启动会创建 `data/app.db` 及 `raw/`、`archive/`、`manual-inbox/`、`vault-view/`、`quarantine/`，运行迁移并执行恢复。
- 外部集成状态：Web/RSS/GitHub/视频为 fixture；LLM、扩展搜索和飞书仅有 Fake/可注入契约；Embedding 未配置时显式降级；系统调度与真实网络适配未实现/未授权。
- Obsidian、社区插件和 Web Clipper 不是运行前置。`vault-view/` 是非权威阅读投影。

## 当前阶段

- 当前已授权推进至 Phase 8；本地/Fake 安全、恢复、性能和逐项追踪审计已实现并通过。
- Phase 8 总体仍为 `PARTIAL`：P8-TC-04、05、08 尚无真实时间/人工证据，P8-TC-06 因无真实适配授权为 `BLOCKED`。
- 外部来源、扩展搜索、真实 LLM/Embedding 与飞书仍必须使用 Fake/fixture 或显式降级；接入真实能力需要新的单独授权。
- 2026-09-05 的 Figma UI/PRD 评审结论为**不通过**：该原型可作信息架构与视觉方向初稿，但不是下一轮实现基线。它的四个一级专题与 PRD v3.0 不一致，且详情追溯/版本、校准、扩展搜索和失败重试等关键闭环未完整呈现；不得据此改变分类、导航、统计或推送契约。
- 不得创建 Windows 计划任务、安装系统服务、开放公网端口、发送真实消息或写入真实凭证，除非用户另行明确授权。
- 每次补充自然日/人工/真实适配证据后运行 `phase8-audit.ps1 -SkipCommands` 刷新报告；历史自动证据必须与当前源码指纹一致，否则强制重跑；不得修改 PRD 阈值以制造通过。

## 强制边界

- 只监听本机地址；不开放公网端口。
- 不把真实密钥写入代码、fixture、Markdown、SQLite、日志或前端。
- `raw/`、`archive/`、`vault-view/` 和用户数据必须保持执行文档规定的职责边界。
- `RawSnapshot`、`EventVersion`、`Evidence`、`Score` 只追加；用户数据只能写独立表。
- 正式记录必须经过 staged 协议并在 READY 切换后才可见；恢复器不得接受外部文件修改为新事实。
- Obsidian、社区插件和 Web Clipper 都不是核心运行前置。
- 外部来源、LLM、Embedding、扩展搜索和飞书在获得明确授权前只能使用 Fake。
- 不修改 PRD，不擅自改变专题、70 分阈值、50 条上限、三级分层或只读权限。
- 不提交、建分支、推送、部署、创建系统计划任务或永久删除数据，除非用户另行明确授权。

## 高风险约束索引

| 约束 | 影响区域 | 最小验证 | 证据来源 | 状态 |
| --- | --- | --- | --- | --- |
| 迁移后的实际表必须与 `schema.py` 一致 | 启动、恢复、所有 Phase 2～7 仓储 | 从空临时目录运行完整 pytest；确认 Alembic 到当前 head | `migrations/versions/`、`schema.py`、`tests/test_foundation.py`、`tests/phase2/` | 已确认；本次 head 为 `0009_phase7_local_web` |
| 正式记录只能在 Raw/Archive/SQLite 一致并切换 READY 后可见 | `archive/commit.py`、`archive/recovery.py`、`db/repository.py` | `tests/phase2/test_recovery.py`、`test_archive_invariants.py` | 执行文档 7.2、Phase 2 测试 | 已确认 |
| Phase 4 稳定事件 ID 可为 UUID5，正式归档不得错误限定 UUID4 | `event_matching.py`、`domain/models.py`、`daily_selection.py` | Phase 5 `P5-TC-08` 正式化路径 | 当前代码与 `tests/phase5/test_phase5_acceptance.py` | 已确认；2026-09-04 回归后通过 |
| Phase 5 重评必须追加评分版本，正式化 provenance 必须随 staged 恢复 | `intelligence_repository.py`、`schema.py`、迁移 `0007` | Phase 5 校准/正式化与 Phase 2 恢复测试 | `0007_phase5_regression_fixes.py`、Phase 5 测试 | 已确认 |
| 真实内容不得触发工具调用或绕过 Fake 边界 | `ports/llm.py`、`adapters/llm/fake.py`、`intelligence_processing.py` | Phase 5 坏 JSON、超时、prompt injection 用例；secret scan | PRD 风控、`P5-TC-07`、`scripts/secret-scan.ps1` | 已确认（Fake 路径）；真实适配待确认/未授权 |
| 采集/模型/UI 不得直接写正式档案 | `adapters/`、`application/`、`infrastructure/archive/` | 搜索写入调用点并运行正式化/恢复用例 | 执行文档 5.3、当前依赖方向 | 已确认 |
| 本机监听限制不可被普通环境变量绕过 | `config.py`、`main.py`、Vite 配置 | `tests/test_config.py`，检查 Vite host | 当前代码/配置 | 已确认 |
| 质量门禁必须使用兼容 Node，且不得把未运行检查写成通过 | `scripts/quality.ps1`、`web/package.json` | 使用脚本选择的 bundled Node 运行 lint/test/build | 本次 Node 16 失败、Node 24.19.0 通过 | 已确认；正式最低 Node 版本待确认 |
| 未经产品确认的 Figma 原型不得覆盖 PRD 分类与核心交互契约 | 主题导航/统计/推送顺序、详情、校准、扩展搜索、运行重试 | 将原型逐项映射到 PRD v3.0 的 F5、详情、F7、F11 和异常验收项；先修复 P0 再作为实现输入 | `docs/figma-ui-prd-acceptance-report-2026-09-05.md` | 已确认；原型评审不通过 |
| 当前项目全部未被 Git 跟踪，改动溯源和冲突识别能力有限 | 整个项目 | `git status --short --branch --untracked-files=all` | Git 快照 | 已确认，高风险 |

## AI 工作协议

1. 开始前读取当前用户指令、两份上级权威文档、本 Harness 与 `README.md`，再刷新 Git 状态。
2. 明确目标 Phase、覆盖 FR/AC、拟修改/不修改文件、真实验证命令及冲突；不得提前实现下一 Phase。
3. 检查源代码、配置、测试、注释/TODO 和必要历史；跳过依赖、构建、缓存与生成物，除非用于验证具体事实。
4. 保留无关工作区改动。当前文件均未跟踪，不能依赖 Git 自动区分所有权；文件在审计期间发生变化时，重新读取后再决定是否编辑。
5. 只作有证据支持的最小修改。遇到依赖变更、迁移/数据语义、权限、真实集成、外部副作用、破坏性操作或业务规则冲突，必须停止并请求明确授权。
6. 完成前刷新 Git 状态，验证文档内路径、命令、链接和状态；报告实际运行与未运行检查、变更文件、风险和待确认事项。
7. 代码、权威文档、阶段授权、迁移 head、接口、数据边界或质量门禁变化时更新本 Harness；不要为制造 diff 而改写。

## 待确认事项

- 项目何时纳入 Git 跟踪，以及当前未跟踪文件的责任人/基线；在确认前不得擅自 `git add` 或提交。
- 前端包清单是否应补充 `engines` 字段；当前启动脚本的兼容门槛为 Node 20.19+、22.12+ 或更高主版本，Node 16.20.2 不兼容、bundled Node 24.19.0 可通过。
- Phase 8 真实适配与系统调度是否授权；真实 LLM/Embedding/搜索/飞书供应商与身份均未决定。
- 生产权限模型、数据保留期限、备份/恢复目标、允许的外部副作用、日志保留和敏感数据分类。仓库当前只给出本地单用户和禁止泄密边界，不能据此臆测正式政策。
- 用户可见 API/UI 的发布门槛及公网/多用户范围；当前仅支持本机单用户运行。

## 当前质量命令

```powershell
powershell -File scripts/quality.ps1 -Scope foundation
powershell -File scripts/quality.ps1 -Scope full
.\.venv\Scripts\python.exe -B -m pytest tests\phase2 -q
.\.venv\Scripts\python.exe -B -m pytest tests\phase3 -q
.\.venv\Scripts\python.exe -B -m pytest tests\phase4 -q
.\.venv\Scripts\python.exe -B -m pytest tests\phase5 -q
.\.venv\Scripts\python.exe -B -m pytest tests\phase6 -q
.\.venv\Scripts\python.exe -B -m pytest tests\phase7 -q
.\.venv\Scripts\python.exe -B -m pytest tests\phase8 -q
powershell -ExecutionPolicy Bypass -File scripts\phase8-audit.ps1
```

不得声称未运行的检查已通过。

2026-09-04 Phase 8 本地审计实际验证：统一 `quality.ps1 -Scope full` 退出码 0，secret scan、Ruff、格式、mypy（71 个源文件）、pytest（102 passed，2 条第三方弃用警告）、前端 lint/Vitest/build、模拟交互 E2E 与真实 FastAPI+SQLite 浏览器 E2E 均通过；安全定向 5 条、恢复定向 11 条和 1 万条 repository/SQLite/真实浏览器性能对账通过。本次两条真实浏览器证据记录冷启动约 1.51～1.63 秒、筛选约 0.24 秒；原始计时、硬件信息和源码指纹保留在 `docs/phase8/evidence/`。实际 7 日试运行、人工质量抽检、真实适配和 30 日稳定性没有被报告为通过。

## 更新记录

- 2026-09-04：将既有约束清单扩展为证据化 Harness；补充范围、实现状态、模块职责、运行/集成边界、高风险矩阵、实际验证、Git 未跟踪风险与待确认政策；保留原有 Phase 5 授权和强制边界。
- 2026-09-04：推进 Phase 8；新增纯验收评估器、一键本地审计、只读 soak 采证、12 FR/76 AC/9 NFR/CTD 追踪报告及风险清单；总体保持 `PARTIAL`，未授权/未满自然日项保持 `BLOCKED` 或 `NOT_RUN`。
- 2026-09-04：刷新 Phase 8 证据指纹与运行快照；修正文档中的 Phase 5/目录状态和真实浏览器计时，使其与当前源码及最新脱敏证据一致。
- 2026-09-05：纳入 Figma UI/PRD 评审证据；将原型“不可作为实现基线”、四专题口径冲突和关键交互闭环缺口登记为高风险约束，并精确化 `start.bat` 的 Node 兼容门槛。
