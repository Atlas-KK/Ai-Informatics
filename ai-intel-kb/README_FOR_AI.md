# Codex 项目 Harness

本文件是面向 AI/自动化开发代理的项目记忆与操作契约，描述当前仓库可由证据支持的状态；它不替代 PRD，也不得把规划误写成已实现能力。

## 维护元数据

- 最近核验：2026-09-06（Asia/Shanghai）。
- 覆盖范围：`D:\AI_informatics\Ai情报搜集系统\ai-intel-kb` 及其两份上级权威文档。
- Git 快照（已确认，2026-09-06）：仓库根目录为 `D:\AI_informatics\Ai情报搜集系统`，分支 `main`，`HEAD=884ced3`，相对 `origin/main` ahead 1；PRD、Harness 和既有应用代码已受 Git 跟踪。UI 专项执行文档、UI-1/UI-2 新增源码与截图当前仍未跟踪，未经用户授权不得 `git add`、提交或推送。
- 结论标签：**已确认**表示本次读取或执行结果支持；**基于代码的推断**表示静态实现指向该行为但未完成对应运行验证；**待确认**表示仓库不能决定，必须由用户或产品负责人确认。

## 权威顺序

1. 当前用户明确指令。
2. `D:\AI_informatics\Ai情报搜集系统\AI情报知识库_PRD_工作稿.md`（v3.0）。
3. `D:\AI_informatics\Ai情报搜集系统\AI情报知识库_Codex开发执行文档_v1.1.md`（v1.1-AC）。
4. `D:\AI_informatics\Ai情报搜集系统\AI情报知识库_Codex_UI补全升级执行文档_v1.0.md`（v1.0-UI，仅约束 UI 补全升级阶段）。
5. Figma 文件 `PjXzkYaVIX4BxV26eW1Tk6` 的 `v2 · PRD 完整交互原型`，仅定义已确认的布局、信息层级和状态表达。
6. 当前代码与测试。

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
| UI 补全升级 UI-1：设计基础、应用壳与可测试拆分 | 已实现并经用户确认 | `web/src/app/`、`web/src/components/`、`web/src/styles/`、`web/src/App.tsx`、`docs/ui1-evidence/` |
| UI 补全升级 UI-2：首页、专题与历史检索 | 已实现，等待产品验收 | `phase7_repository.py`、`api/app.py`、`web/src/features/dashboard/`、`topics/`、`search/`、`web/src/services/`、`docs/ui2-evidence/` |
| UI 补全升级 UI-3：情报详情独立工作区 | 已实现并经回归修复 | `web/src/features/intel-detail/`、详情 DTO、`docs/ui3-evidence/` |
| UI 补全升级 UI-4：来源、专家、GitHub 规则与系统设置 | 已实现，等待产品验收 | `web/src/features/sources/`、`features/settings/`、迁移 `0010`、`docs/ui4-evidence/` |
| UI 补全升级 UI-5：质量反馈、校准版本、回退与重评分 | 已实现，等待产品验收 | `application/calibration.py`、`api/app.py`、`phase7_repository.py`、`web/src/features/quality/`、`docs/ui5-evidence/` |
| UI 补全升级 UI-6：运行详情、阶段重试与投递分段 | 已实现并完成回归问题修复，等待产品验收 | `phase7_repository.py`、`api/app.py`、`web/src/features/runs/`、`docs/ui6-evidence/` |
| UI 补全升级 UI-7：扩展搜索与选题建议 | 已实现并完成代码回归审查，等待产品验收 | `api/app.py`、`phase7_repository.py`、`web/src/features/intel-detail/expansion/`、`topic-ideas/`、`docs/ui7-evidence/` |
| UI 补全升级 UI-8：状态矩阵、无障碍、小屏与最终验收 | 已实现并通过本地最终验收 | `AsyncStateView.tsx`、`AppShell.tsx`、`RunsPage.tsx`、`web/e2e/phase7.cjs`、`docs/ui8-evidence/`、`docs/ui-upgrade/UI8_final_acceptance_report.md` |

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
| `src/ai_intel/api/` | FastAPI 本地 API；启动时迁移数据库并运行恢复器；提供 Phase 7 查询和用户操作接口；UI-2 的 archive/search 筛选、排序、分页由服务端执行，`/api/archive` 仅在显式 `paged=true` 时返回分页对象，默认数组响应保持兼容 |
| `web/` | React/Ant Design/ECharts 本地工作台；`src/app/` 管理应用壳、导航、主题和类型化视图状态，`src/components/` 管理共享展示/状态/确认组件；模拟 E2E 覆盖八类页面和十项写操作，真实栈 E2E 验证 FastAPI/SQLite 契约、刷新持久化与 1 万条页面性能 |
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
- 2026-09-05 的早期 Figma 原型评审“不通过”仍作为历史风险记录；后续 Figma v2（文件 `PjXzkYaVIX4BxV26eW1Tk6`）已补齐核心页面与状态。2026-09-06 用户确认：详情最终采用独立工作区；原型导览/状态验收不生产化；状态帧可收敛为共享组件；新库分层默认为 10/20/20、既有配置不自动覆盖。
- UI 补全升级 UI-1～UI-8 已完成。当前停止在 UI-8 产品验收门禁；不得自动进入真实适配器、小流量试运行或部署。
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
| 迁移后的实际表必须与 `schema.py` 一致 | 启动、恢复、所有 Phase 2～7 仓储 | 从空临时目录运行完整 pytest；确认 Alembic 到当前 head | `migrations/versions/`、`schema.py`、`tests/test_foundation.py`、`tests/phase2/` | 已确认；本次 head 为 `0010_ui4_source_settings` |
| 正式记录只能在 Raw/Archive/SQLite 一致并切换 READY 后可见 | `archive/commit.py`、`archive/recovery.py`、`db/repository.py` | `tests/phase2/test_recovery.py`、`test_archive_invariants.py` | 执行文档 7.2、Phase 2 测试 | 已确认 |
| Phase 4 稳定事件 ID 可为 UUID5，正式归档不得错误限定 UUID4 | `event_matching.py`、`domain/models.py`、`daily_selection.py` | Phase 5 `P5-TC-08` 正式化路径 | 当前代码与 `tests/phase5/test_phase5_acceptance.py` | 已确认；2026-09-04 回归后通过 |
| Phase 5 重评必须追加评分版本，正式化 provenance 必须随 staged 恢复 | `intelligence_repository.py`、`schema.py`、迁移 `0007` | Phase 5 校准/正式化与 Phase 2 恢复测试 | `0007_phase5_regression_fixes.py`、Phase 5 测试 | 已确认 |
| 真实内容不得触发工具调用或绕过 Fake 边界 | `ports/llm.py`、`adapters/llm/fake.py`、`intelligence_processing.py` | Phase 5 坏 JSON、超时、prompt injection 用例；secret scan | PRD 风控、`P5-TC-07`、`scripts/secret-scan.ps1` | 已确认（Fake 路径）；真实适配待确认/未授权 |
| 采集/模型/UI 不得直接写正式档案 | `adapters/`、`application/`、`infrastructure/archive/` | 搜索写入调用点并运行正式化/恢复用例 | 执行文档 5.3、当前依赖方向 | 已确认 |
| 本机监听限制不可被普通环境变量绕过 | `config.py`、`main.py`、Vite 配置 | `tests/test_config.py`，检查 Vite host | 当前代码/配置 | 已确认 |
| 质量门禁必须使用兼容 Node，且不得把未运行检查写成通过 | `scripts/quality.ps1`、`web/package.json` | 使用脚本选择的 bundled Node 运行 lint/test/build | 本次 Node 16 失败、Node 24.19.0 通过 | 已确认；正式最低 Node 版本待确认 |
| Figma 不得覆盖 PRD 分类与核心交互契约；121 个状态画面不得实现为 121 个路由 | 导航/统计/推送顺序、详情、校准、扩展搜索、运行重试 | 对照 v1.0-UI 的页面映射、UI-DEC-01～04 和 UI AC；检查生产导航与状态组件 | UI 执行文档、Figma v2、UI-0 用户确认 | 已确认；逐 Phase 执行 |
| 正式档案筛选、分层和排序必须由服务端权威执行，且 UI-2 不得破坏旧 archive/search 调用方 | `phase7_repository.py`、`api/app.py`、dashboard/topics/search features | Phase 7 组合筛选/分页/降级测试、前端 browse 契约测试、1 万条真实浏览器性能、旧 `/api/archive` 数组响应回归 | UI 执行文档 Phase UI-2、`tests/phase7/`、`web/src/services/browse.test.ts`、Phase 8 E2E | 已确认；`paged=true` 为显式分页契约 |
| 情报详情的系统字段必须只读，覆盖率必须来自服务端聚合，个人笔记和用户状态必须独立持久化 | `phase7_repository.py`、`features/intel-detail/`、`types.ts` | 详情 DTO 回归、观点规范化覆盖率映射、版本切换/笔记失败保留/XSS/乱序请求组件测试、浏览器四分区交互 | UI 执行文档 Phase UI-3、PRD AC-F05/F08-F11/F16/F22、AC-D06-D11、AC-I01-I08、AC-E14 | 已确认；待产品验收 |
| 来源逻辑删除与截断变更不得改写历史；GitHub 规则必须本地持久化；设置页不得回显密钥 | `source_repository.py`、`phase7_repository.py`、`api/app.py`、`features/sources/`、`features/settings/` | 来源 CRUD/状态/历史保留、迁移升级、GitHub 规则校验、缺失配置脱敏、来源与设置浏览器交互 | UI 执行文档 Phase UI-4、PRD AC-F01-F07/F13-F15、AC-D14、AC-I14、AC-E02/E13 | 已确认；真实采集仍为 fixture |
| 反馈不得自动修改评分配置；校准必须显式确认并生成版本；回退只能指向真实历史版本；重评分只追加且仅限反馈关联项 | `calibration.py`、`intelligence_repository.py`、`phase7_repository.py`、`api/app.py`、`features/quality/` | 样本不足、确认/拒绝、回退、非法重评范围原子拒绝、同配置追加重评、遥测与浏览器交互 | UI 执行文档 Phase UI-5、PRD AC-I06/I09-I13、AC-M01、Phase 5/7 与前端质量测试 | 已确认；UI-5 已完成 |
| 运行恢复阶段必须由服务端决定；业务重试只有实际成功才能完成工作项；投递重发必须在仓储层原子认领失败分段，成功分段保持幂等；全失败也必须保留本地日报 | `pipeline_repository.py`、`delivery.py`、`phase7_repository.py`、`api/app.py`、`features/runs/` | 失败结果保持待重试、成功后运行状态对账、失败分段原子认领与并发去重、无失败分段冲突、本地日报详情、浏览器双重试闭环、日志脱敏与全量门禁 | UI 执行文档 Phase UI-6、PRD AC-D12、AC-E01-E11、AC-M02-M04、Phase 6/7 测试 | 已确认；UI-6 已完成，真实飞书仍未授权 |
| 扩展结果未确认不得入库；确认后必须经过服务端加工与去重；收藏归档须对同一结果幂等并能从既有不可变中间产物恢复；外部 URL 仅允许 HTTP(S)；选题建议只含标题、大纲、爆点和可追溯支撑来源 | `search.py`、`extension_ingestion.py`、`topic_ideas.py`、`source_repository.py`、`event_repository.py`、`phase7_repository.py`、`api/app.py`、`features/intel-detail/expansion/`、`topic-ideas/` | 未收藏不入库、新建/关联已有事件两分支、同一结果成功重放、加工超时恢复、并发收藏单次归档、非 HTTP(S) 拒绝、未配置失败保持原情报、支撑证据映射与浏览器三分支 | UI 执行文档 Phase UI-7、PRD AC-F24/F26、AC-I15、AC-E12、Phase 5/7 与前端测试 | 已确认（Fake/未配置边界）；真实扩展搜索和真实 LLM 仍未授权 |
| UI 最终验收必须覆盖 loading/empty/partial/error、键盘与焦点、输入名称、小屏退化、六条核心浏览器流程及 10k 性能 | `AppShell.tsx`、`AsyncStateView.tsx`、`RunsPage.tsx`、`phase7.cjs` | 30 条前端测试、21 类浏览器写操作、1440×1000 与 390×844 截图、正式 Phase 8 审计 | UI 执行文档 Phase UI-8、AC-D03/D13、AC-I03-I05、AC-E13-E16、AC-M03-M05 | 已确认；本地 UI 范围完成，运行期延后项不冒充通过 |
| UI 专项文档、UI-1/UI-2 新增源码和证据尚未被 Git 跟踪，提交边界仍需用户授权 | UI 补全升级文件 | `git status --short --branch --untracked-files=all`；不得擅自 `git add` | 2026-09-06 Git 快照 | 已确认，高风险 |

## AI 工作协议

1. 开始前读取当前用户指令、两份上级权威文档、本 Harness 与 `README.md`，再刷新 Git 状态。
2. 明确目标 Phase、覆盖 FR/AC、拟修改/不修改文件、真实验证命令及冲突；不得提前实现下一 Phase。
3. 检查源代码、配置、测试、注释/TODO 和必要历史；跳过依赖、构建、缓存与生成物，除非用于验证具体事实。
4. 保留无关工作区改动。既有文件可用 Git diff 辅助核对；未跟踪的 UI 专项文档、新源码和证据仍需逐文件确认所有权。文件在审计期间发生变化时，重新读取后再决定是否编辑。
5. 只作有证据支持的最小修改。遇到依赖变更、迁移/数据语义、权限、真实集成、外部副作用、破坏性操作或业务规则冲突，必须停止并请求明确授权。
6. 完成前刷新 Git 状态，验证文档内路径、命令、链接和状态；报告实际运行与未运行检查、变更文件、风险和待确认事项。
7. 代码、权威文档、阶段授权、迁移 head、接口、数据边界或质量门禁变化时更新本 Harness；不要为制造 diff 而改写。

## 待确认事项

- UI 专项执行文档、UI-1/UI-2 新增源码和截图何时纳入 Git 跟踪；在确认前不得擅自 `git add`、提交或推送。
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

2026-09-06 Phase 8 本地审计实际验证：统一 `quality.ps1 -Scope full` 退出码 0，secret scan、Ruff、格式、mypy（71 个源文件）、pytest（113 passed，2 条第三方弃用警告）、前端 lint/Vitest/build、模拟交互 E2E 与真实 FastAPI+SQLite 浏览器 E2E 均通过；安全定向 6 条、恢复定向 11 条和 1 万条 repository/SQLite/真实浏览器性能对账通过。两条真实浏览器证据记录冷启动约 1.29～1.32 秒、筛选约 0.18～0.19 秒；原始计时、硬件信息和源码指纹保留在 `docs/phase8/evidence/`。实际 7 日试运行、人工质量抽检、真实适配和 30 日稳定性没有被报告为通过。

2026-09-06 UI-1 实际验证：`quality.ps1 -Scope frontend` 退出码 0；ESLint、6 条 Vitest 组件/应用壳测试、TypeScript 和 Vite build 通过。`web/e2e/phase7.cjs` 验证原有 9 个写操作通过，并生成 `docs/ui1-evidence/app-shell-1440x1000.png` 供视觉验收。该证据仅覆盖 UI-1，不代表 UI-2～UI-8 已实现。

2026-09-06 UI-2 实际验证：`quality.ps1 -Scope full` 退出码 0；secret scan、Ruff、格式、mypy（71 个源文件）、pytest（103 passed，2 条第三方弃用警告）、前端 ESLint、7 个 Vitest 文件/12 条测试、TypeScript/Vite build 均通过。模拟浏览器 E2E 验证原有 9 个写操作，真实 FastAPI+SQLite 浏览器 E2E 对 1 万条记录测得冷启动约 1.24 秒、服务端筛选约 0.20 秒。`docs/ui2-evidence/` 保存首页、专题档案和历史检索三张 1440×1000 截图。该证据不代表 UI-3～UI-8 已实现。

2026-09-06 UI-3 实际验证：`quality.ps1 -Scope full` 退出码 0；secret scan、Ruff、格式、mypy（71 个源文件）、pytest（104 passed，2 条第三方弃用警告）、前端 ESLint、8 个 Vitest 文件/16 条测试、TypeScript/Vite build 均通过。模拟浏览器 E2E 验证原有 9 个写操作，真实 FastAPI+SQLite 浏览器 E2E 对 1 万条记录测得冷启动约 1.24 秒、服务端筛选约 0.19 秒。`docs/ui3-evidence/` 保存详情正文、来源与观点、历史版本和选题建议等 1440×1000 截图。该证据不代表 UI-4～UI-8 已实现。

2026-09-06 UI-4 实际验证：`quality.ps1 -Scope full` 退出码 0；secret scan、Ruff、格式、mypy（71 个源文件）、pytest（106 passed，2 条第三方弃用警告）、前端 ESLint、10 个 Vitest 文件/19 条测试、TypeScript/Vite build 均通过。模拟浏览器 E2E 验证 9 个写操作，真实 FastAPI+SQLite 浏览器 E2E 对 1 万条记录测得冷启动约 1.37 秒、服务端筛选约 0.21 秒。`docs/ui4-evidence/` 保存来源三页签与系统设置四页签的 1440×1000 截图。新增 `0010_ui4_source_settings` 迁移；新库分层默认 10/20/20，既有配置升级保持不变。该证据不代表 UI-5～UI-8 已实现。

2026-09-06 UI-5 实际验证：修复重复未决提案、活动版本空回退和过期详情响应测试时序后，`quality.ps1 -Scope full` 退出码 0；secret scan、Ruff、格式、mypy（71 个源文件）、pytest（107 passed，2 条第三方弃用警告）、前端 ESLint、11 个 Vitest 文件/23 条测试、TypeScript/Vite build 均通过。模拟浏览器验证 9 个写操作，真实 FastAPI+SQLite 浏览器 E2E 对 1 万条记录测得冷启动约 1.24 秒、服务端筛选约 0.19 秒。`docs/ui5-evidence/` 保存反馈记录与校准建议两张 1440×1000 截图。每个活动基础版本只保留一个未决提案；陈旧提案仅可拒绝；当前活动版本不能作为回退目标；历史重评分接口在写入前校验完整范围并只追加新评分记录。未新增迁移。该证据不代表 UI-6～UI-8 已实现。

2026-09-06 UI-6 修复后实际验证：`quality.ps1 -Scope full` 退出码 0；secret scan、Ruff、格式、mypy（71 个源文件）、pytest（107 passed，2 条第三方弃用警告）、前端 ESLint、12 个 Vitest 文件/25 条测试、TypeScript/Vite build 均通过。模拟浏览器验证 10 个写操作，真实 FastAPI+SQLite 浏览器 E2E 对 1 万条记录测得冷启动约 1.20 秒、服务端筛选约 0.18 秒。`docs/ui6-evidence/runs-detail-1440x1000.png` 已刷新并展示失败来源原因、重试次数和失败投递分段。业务重试失败结果保持 `WAITING_RETRY`，成功后对账运行状态；摘要级投递重发在仓储层原子认领 `FAILED` 分段，并发调用不会重复发送，无失败分段返回冲突。运行详情只返回脱敏事件摘要；未新增迁移且未接入真实飞书。UI-6 等待产品验收，该证据不代表 UI-7～UI-8 已实现。

2026-09-06 UI-7 修复后实际验证：`quality.ps1 -Scope full` 退出码 0；secret scan、Ruff、格式、mypy（71 个源文件）、pytest（113 passed，2 条第三方弃用警告）、前端 ESLint、13 个 Vitest 文件/29 条测试、TypeScript/Vite build 均通过。模拟浏览器验证 12 个写操作，并覆盖扩展搜索新建、重复关联和失败三条分支；真实 FastAPI+SQLite 浏览器 E2E 对 1 万条记录测得冷启动约 1.43 秒、服务端筛选约 0.19 秒。`docs/ui7-evidence/` 保存手动选题、扩展新建、重复关联和失败重试等 1440×1000 截图。扩展结果在确认前保持临时状态，服务端拒绝非 HTTP(S) URL；收藏归档对同一结果返回稳定结果，加工超时后从既有不可变快照/聚合版本恢复，并发提交只形成一条正式档案；手动选题失败可重试且不改变原情报，支撑来源由聚合证据显式映射。未新增迁移、依赖或真实外部适配；UI-7 等待产品验收，该证据不代表 UI-8 已实现。

2026-09-06 UI-8 实际验证：补齐 skip link、main landmark、导航展开语义、全局高对比焦点、异步状态 live region、运行行键盘选择及输入可访问名称；模拟浏览器扩展至六条核心流程和 21 类写操作，并验证 390×844 无 document 级横向溢出。正式 `phase8-audit.ps1` 退出码 0：113 条后端测试、30 条前端测试、真实 10k 浏览器冷启动约 1.341 秒、筛选约 0.187 秒；源码指纹 `6fb34e6f15928a93a984a0ee62f11c32386cba09ab563b889fa791c111158354`。UI-8 本地界面范围通过，真实适配器/7 日/30 日项仍按 `BLOCKED`/`NOT_RUN` 保留。

## 更新记录

- 2026-09-04：将既有约束清单扩展为证据化 Harness；补充范围、实现状态、模块职责、运行/集成边界、高风险矩阵、实际验证、Git 未跟踪风险与待确认政策；保留原有 Phase 5 授权和强制边界。
- 2026-09-04：推进 Phase 8；新增纯验收评估器、一键本地审计、只读 soak 采证、12 FR/76 AC/9 NFR/CTD 追踪报告及风险清单；总体保持 `PARTIAL`，未授权/未满自然日项保持 `BLOCKED` 或 `NOT_RUN`。
- 2026-09-04：刷新 Phase 8 证据指纹与运行快照；修正文档中的 Phase 5/目录状态和真实浏览器计时，使其与当前源码及最新脱敏证据一致。
- 2026-09-05：纳入 Figma UI/PRD 评审证据；将原型“不可作为实现基线”、四专题口径冲突和关键交互闭环缺口登记为高风险约束，并精确化 `start.bat` 的 Node 兼容门槛。
- 2026-09-06：记录 Figma v2 与 UI-DEC-01～04 的用户确认；完成 UI-1 应用壳、导航、token、类型化视图状态和共享组件基础，并保留逐 Phase 授权门禁。
- 2026-09-06：用户确认 UI-1 后完成 UI-2：首页四专题入口、空/部分态、专题筛选、历史组合检索与服务端分页；保留旧 archive 数组响应，新增显式分页契约和降级可观察状态，并通过全量质量门禁。
- 2026-09-06：用户确认 UI-2 后完成 UI-3：将详情从 Drawer 改为独立工作区，补齐只读正文、来源与观点、历史版本、选题建议四分区，并增加服务端评分依据、权威覆盖率、时间未知和来源状态 DTO；通过全量质量门禁，停止在 UI-3 产品验收点。
- 2026-09-06：修复 UI-3 回归评审问题：覆盖率改为按规范化观点关联，来源配置删除不再误报为网络不可访问，详情加载仅允许最后一次请求更新页面；新增正式化多来源映射和乱序响应测试，再次通过全量质量门禁。
- 2026-09-06：用户授权 UI-4 后完成来源/专家/GitHub 规则三页签、近期采集与失败状态、系统设置四页签、只读评分权重、专题顺序及脱敏服务状态；新增 GitHub 规则迁移并验证既有设置不被覆盖，完成阶段门禁后停止在 UI-4 产品验收点。
- 2026-09-06：用户继续授权后完成 UI-5：质量反馈详情、校准建议显式确认/拒绝、配置版本与审计、受控回退、反馈关联范围的手动追加重评分；补齐校准与配置变更遥测，通过全量质量门禁并停止在 UI-5 产品验收点。
- 2026-09-06：修复 UI-5 回归评审问题：串行化并复用同一基础版本的未决提案，拒绝活动版本空回退，陈旧提案禁止确认且按其基础版本展示权重；稳定详情乱序响应测试并补充领域、API、前端负向覆盖，再次通过全量质量门禁。
- 2026-09-06：用户继续授权后完成 UI-6：新增运行详情只读模型、超时/重复启动/失活锁状态提示、失败工作项及来源定位、服务端阶段重试、本地日报与投递分段状态、失败分段单独重发；通过全量质量门禁并停止在 UI-6 产品验收点。
- 2026-09-06：按用户要求调用 `code-review-skill` 回归审查 UI-6，结论为 Request Changes：需先修复业务重试失败被误标完成、失败分段重发边界与并发原子性，并补充负向/并发测试；保持停止在 UI-6。
- 2026-09-06：修复 UI-6 回归问题：重试执行器按真实业务结果决定是否完成工作项并对账运行状态；失败来源详情补全失败原因和重试次数；投递服务以单条原子 SQL 认领失败分段，避免并发重复发送；前后端补充失败、无失败分段和并发覆盖，全量质量门禁再次通过，继续停止在 UI-6 产品验收点。
- 2026-09-06：用户继续授权后完成 UI-7：新增手动选题 API 与可追溯支撑来源，完善扩展搜索加载/空/失败/确认状态及新建/重复关联结果反馈；代码回归审查后补充非 HTTP(S) URL 拒绝和旧响应保护，通过全量质量门禁并停止在 UI-7 产品验收点。
- 2026-09-06：修复 UI-7 回归问题：同一扩展结果重复收藏返回稳定成功响应；加工超时后复用不可变 Raw、聚合版本和既有评分继续归档；同进程并发收藏串行化且只生成一条正式档案；补充成功重放、超时恢复和并发回归测试，全量门禁通过。
- 2026-09-06：完成 UI-8 最终验收：补齐状态语义、键盘与焦点、小屏退化，扩展六条核心浏览器闭环至 21 类写操作，刷新 10k 性能与源码指纹证据；停止在 UI-8 产品验收点。
