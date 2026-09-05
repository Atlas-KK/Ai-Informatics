# Phase 8 最终追踪报告

本报告区分本地/Fake 自动化证据与真实时间、人工评审和外部适配证据。

## 计数审计

| 对象 | 数量 | 结果 |
| --- | ---: | --- |
| FR | 12/12 | PASS |
| AC | 76/76 | PASS |
| NFR | 9/9 | PASS |
| CTD 执行别名 | 7/7（覆盖 CTD-01～08） | PASS |

## FR（本地/Fake 产品能力）

| ID | 状态 | 阶段/范围 | 证据或延期理由 |
| --- | --- | --- | --- |
| F1 | PASS | 3、7 | Source Management；docs/phase8/evidence/p8-tc-01-full-gate.json |
| F2 | PASS | 3、6 | Collection + Scheduler；docs/phase8/evidence/p8-tc-01-full-gate.json |
| F3 | PASS | 4 | Event Intelligence；docs/phase8/evidence/p8-tc-01-full-gate.json |
| F4 | PASS | 5 | AI Processing；docs/phase8/evidence/p8-tc-01-full-gate.json |
| F5 | PASS | 5、7 | Topic Engine；docs/phase8/evidence/p8-tc-01-full-gate.json |
| F6 | PASS | 5 | Scoring Engine；docs/phase8/evidence/p8-tc-01-full-gate.json |
| F7 | PASS | 5、7 | Calibration；docs/phase8/evidence/p8-tc-01-full-gate.json |
| F8 | PASS | 2、7 | Archive + User Data；docs/phase8/evidence/p8-tc-01-full-gate.json |
| F9 | PASS | 6 | Digest Delivery；docs/phase8/evidence/p8-tc-01-full-gate.json |
| F10 | PASS | 7 | Web UI；docs/phase8/evidence/p8-tc-01-full-gate.json |
| F11 | PASS | 7 | Search；docs/phase8/evidence/p8-tc-01-full-gate.json |
| F12 | PASS | 5、7 | Topic Ideas；docs/phase8/evidence/p8-tc-01-full-gate.json |

## AC

| ID | 状态 | 阶段/范围 | 证据或延期理由 |
| --- | --- | --- | --- |
| AC-F01 | PASS | 3 | 来源新增契约测试；数据库行与下一任务候选；docs/phase8/evidence/p8-tc-01-full-gate.json |
| AC-F02 | PASS | 3 | 专家白名单启停集成测试；历史引用不变；docs/phase8/evidence/p8-tc-01-full-gate.json |
| AC-F03 | PASS | 3 | GitHub 日榜/周榜/白名单 fixture；总 Star 日快照与近七日差值契约测试；docs/phase8/evidence/p8-tc-01-full-gate.json |
| AC-F04 | PASS | 3 | Fake Clock 验证 window_start/end 精确为 7×24 小时；docs/phase8/evidence/p8-tc-01-full-gate.json |
| AC-F05 | PASS | 3 | 缺日期 fixture 使用 first_seen_at 并展示状态；docs/phase8/evidence/p8-tc-01-full-gate.json |
| AC-F06 | PASS | 3 | 四类 Collector contract 测试及字段快照；docs/phase8/evidence/p8-tc-01-full-gate.json |
| AC-F07 | PASS | 3 | 无字幕 fixture 验证无音频/ASR 调用；docs/phase8/evidence/p8-tc-01-full-gate.json |
| AC-F08 | PASS | 5 | Fake LLM schema 测试及五项输出字段；docs/phase8/evidence/p8-tc-01-full-gate.json |
| AC-F09 | PASS | 4 | 多来源同事件 fixture 只生成一个 event_id；docs/phase8/evidence/p8-tc-01-full-gate.json |
| AC-F10 | PASS | 4、7 | 观点来源与覆盖比例计算单元测试、详情页断言；docs/phase8/evidence/p8-tc-01-full-gate.json |
| AC-F11 | PASS | 4 | 新事实/观点/来源/正文变化四类版本测试；docs/phase8/evidence/p8-tc-01-full-gate.json |
| AC-F12 | PASS | 4 | 仅时间变化测试，版本数和推送候选数不变；docs/phase8/evidence/p8-tc-01-full-gate.json |
| AC-F13 | PASS | 3 | 1万/2万/5万及默认2万截断测试，原始快照不变；docs/phase8/evidence/p8-tc-01-full-gate.json |
| AC-F14 | PASS | 5 | 每条结果恰有一个主专题、允许多标签的 schema 测试；docs/phase8/evidence/p8-tc-01-full-gate.json |
| AC-F15 | PASS | 5 | 六类工程安全 fixture 分类测试；docs/phase8/evidence/p8-tc-01-full-gate.json |
| AC-F16 | PASS | 5 | 五维得分、总分边界和配置版本单元测试；docs/phase8/evidence/p8-tc-01-full-gate.json |
| AC-F17 | PASS | 5 | 69.99/70 分边界测试及正式档案查询断言；docs/phase8/evidence/p8-tc-01-full-gate.json |
| AC-F18 | PASS | 5 | 51+候选排序测试，正式入选数等于50；docs/phase8/evidence/p8-tc-01-full-gate.json |
| AC-F19 | PASS | 5 | 少量达标候选不补低分内容测试；docs/phase8/evidence/p8-tc-01-full-gate.json |
| AC-F20 | PASS | 5 | 0/5/10/11/30/31/50 条分层参数化测试；docs/phase8/evidence/p8-tc-01-full-gate.json |
| AC-F21 | PASS | 6 | 零达标候选生成空日报集成测试；docs/phase8/evidence/p8-tc-01-full-gate.json |
| AC-F22 | PASS | 2、6 | SQLite 与 archive/ 正式 Markdown 的 event/version/source/hash 对账；vault-view/ 明确排除在正式对账对象外；docs/phase8/evidence/p8-tc-01-full-gate.json |
| AC-F23 | PASS | 6 | Fake Feishu 验证层级、专题顺序和全部入选 ID；docs/phase8/evidence/p8-tc-01-full-gate.json |
| AC-F24 | PASS | 5、7 | 必读自动生成及其他条目手动生成契约测试；docs/phase8/evidence/p8-tc-01-full-gate.json |
| AC-F25 | PASS | 7 | 标题/摘要/正文/来源/标签/笔记全文与语义查询测试；docs/phase8/evidence/p8-tc-01-full-gate.json |
| AC-F26 | PASS | 4、7 | 未收藏无写入；收藏后去重归档 E2E；docs/phase8/evidence/p8-tc-01-full-gate.json |
| AC-D01 | PASS | 7 | 首页组件/E2E：状态、总数、三级数量、四专题；docs/phase8/evidence/p8-tc-01-full-gate.json |
| AC-D02 | PASS | 7 | 图表数据 contract 与浏览器快照；docs/phase8/evidence/p8-tc-01-full-gate.json |
| AC-D03 | PASS | 7 | 空数据、部分失败数据的可视状态测试；docs/phase8/evidence/p8-tc-01-full-gate.json |
| AC-D04 | PASS | 7 | 三级徽标和排序 E2E；docs/phase8/evidence/p8-tc-01-full-gate.json |
| AC-D05 | PASS | 7 | 四专题路由、数量、标签和列表 E2E；docs/phase8/evidence/p8-tc-01-full-gate.json |
| AC-D06 | PASS | 7 | 详情页字段完整性 E2E；docs/phase8/evidence/p8-tc-01-full-gate.json |
| AC-D07 | PASS | 7 | 英文/译文/中文摘要分区组件测试；docs/phase8/evidence/p8-tc-01-full-gate.json |
| AC-D08 | PASS | 7 | 多来源、观点和覆盖比例组件测试；docs/phase8/evidence/p8-tc-01-full-gate.json |
| AC-D09 | PASS | 7 | 首版/最新版切换与时间线 E2E；docs/phase8/evidence/p8-tc-01-full-gate.json |
| AC-D10 | PASS | 7 | 失效来源状态 fixture 浏览器测试；docs/phase8/evidence/p8-tc-01-full-gate.json |
| AC-D11 | PASS | 2、7 | 无系统字段编辑控件；笔记区独立 E2E；docs/phase8/evidence/p8-tc-01-full-gate.json |
| AC-D12 | PASS | 6、7 | 失败任务详情、次数和操作入口 E2E；docs/phase8/evidence/p8-tc-01-full-gate.json |
| AC-D13 | PASS | 7、8 | 1 万条 fixture 性能报告：冷启动≤5秒、交互≤2秒；docs/phase8/evidence/p8-tc-03-performance.json |
| AC-D14 | PASS | 6、7 | 顺序持久化并影响网页和下一日报契约测试；docs/phase8/evidence/p8-tc-01-full-gate.json |
| AC-I01 | PASS | 2、7 | Repository/API 均拒绝系统字段更新；docs/phase8/evidence/p8-tc-01-full-gate.json |
| AC-I02 | PASS | 2、7 | 笔记保存、刷新和事件升级后关联不变；docs/phase8/evidence/p8-tc-01-full-gate.json |
| AC-I03 | PASS | 2、6、7 | 后台运行 fixture 下已完成记录仍可操作用户数据；docs/phase8/evidence/p8-tc-01-full-gate.json |
| AC-I04 | PASS | 2、7 | PROCESSING 记录不在正式查询和详情路由中；docs/phase8/evidence/p8-tc-01-full-gate.json |
| AC-I05 | PASS | 2、7 | 收藏/置顶/已读持久化 E2E；docs/phase8/evidence/p8-tc-01-full-gate.json |
| AC-I06 | PASS | 2、7 | 剔除原因必填与回收站状态 E2E；docs/phase8/evidence/p8-tc-01-full-gate.json |
| AC-I07 | PASS | 2、7 | 恢复后专题、版本、笔记和元数据对账；docs/phase8/evidence/p8-tc-01-full-gate.json |
| AC-I08 | PASS | 2、7 | 永久删除二次确认的确认/取消双分支测试；docs/phase8/evidence/p8-tc-01-full-gate.json |
| AC-I09 | PASS | 5 | 只有反馈无校准时 active_config 不变；docs/phase8/evidence/p8-tc-01-full-gate.json |
| AC-I10 | PASS | 5、7 | 建议页面包含样本量、维度、变化和影响范围；docs/phase8/evidence/p8-tc-01-full-gate.json |
| AC-I11 | PASS | 5、7 | 确认创建新版本；拒绝保持当前版本；docs/phase8/evidence/p8-tc-01-full-gate.json |
| AC-I12 | PASS | 5、7 | 回退后新评分使用目标版本并产生审计事件；docs/phase8/evidence/p8-tc-01-full-gate.json |
| AC-I13 | PASS | 5 | 历史重评分追加记录、不覆盖旧记录；docs/phase8/evidence/p8-tc-01-full-gate.json |
| AC-I14 | PASS | 3 | 新截断配置仅对下一采集生效；docs/phase8/evidence/p8-tc-01-full-gate.json |
| AC-I15 | PASS | 4、7 | 收藏重复扩展结果时关联已有事件；docs/phase8/evidence/p8-tc-01-full-gate.json |
| AC-E01 | PASS | 3、6 | 单源抛错后其他来源仍完成的集成测试；docs/phase8/evidence/p8-tc-01-full-gate.json |
| AC-E02 | PASS | 3 | 排名失败时白名单继续、失败事件存在；docs/phase8/evidence/p8-tc-01-full-gate.json |
| AC-E03 | PASS | 3 | 提取失败只有元数据和失败记录，无 READY 记录；docs/phase8/evidence/p8-tc-01-full-gate.json |
| AC-E04 | PASS | 5、6 | 四类加工失败均无半成品/推送；docs/phase8/evidence/p8-tc-01-full-gate.json |
| AC-E05 | PASS | 6 | 阶段化重试验证前置成功产物未重复执行；docs/phase8/evidence/p8-tc-01-full-gate.json |
| AC-E06 | PASS | 6 | 部分分段失败后仅补发失败幂等键；docs/phase8/evidence/p8-tc-01-full-gate.json |
| AC-E07 | PASS | 6 | 全失败时日报完整且提供重试命令/入口；docs/phase8/evidence/p8-tc-01-full-gate.json |
| AC-E08 | PASS | 6 | Fake Clock 模拟错过计划后只补最近一次；docs/phase8/evidence/p8-tc-01-full-gate.json |
| AC-E09 | PASS | 6 | 并发启动测试只有一个 run owner；docs/phase8/evidence/p8-tc-01-full-gate.json |
| AC-E10 | PASS | 6 | deadline 到达后不再领任务，已完成提交，余项待补；docs/phase8/evidence/p8-tc-01-full-gate.json |
| AC-E11 | PASS | 2、6 | 进程不存在时释放遗留锁并转待重试；docs/phase8/evidence/p8-tc-01-full-gate.json |
| AC-E12 | PASS | 7 | 扩展搜索异常时原事件快照不变；docs/phase8/evidence/p8-tc-01-full-gate.json |
| AC-E13 | PASS | 1、6、7 | 缺环境变量阻止对应功能且只显示变量名；docs/phase8/evidence/p8-tc-01-full-gate.json |
| AC-E14 | PASS | 7 | XSS payload 不执行、危险属性被清洗；docs/phase8/evidence/p8-tc-02-security.json |
| AC-E15 | PASS | 5、8 | 提示注入 fixture 不改变系统 schema/调用权限；docs/phase8/evidence/p8-tc-02-security.json |
| AC-E16 | PASS | 1、6、8 | 日志与观测秘密扫描无明文凭证；docs/phase8/evidence/p8-tc-02-security.json |
| AC-M01 | PASS | 6 | 12 类事件的必需字段参数化测试；docs/phase8/evidence/p8-tc-01-full-gate.json |
| AC-M02 | PASS | 6 | 单个 run_id 可重建完整阶段序列；docs/phase8/evidence/p8-tc-01-full-gate.json |
| AC-M03 | PASS | 6、7 | 首页/运行页与事件查询结果对账；docs/phase8/evidence/p8-tc-01-full-gate.json |
| AC-M04 | PASS | 1、6、8 | 日志和事件 payload 秘密扫描；docs/phase8/evidence/p8-tc-02-security.json |
| AC-M05 | PASS | 2、6 | 永久删除后正文不存在、审计壳保留；docs/phase8/evidence/p8-tc-01-full-gate.json |

## 核心成功指标

| ID | 状态 | 阶段/范围 | 证据或延期理由 |
| --- | --- | --- | --- |
| NFR-S01 | NOT_RUN | 8 | 连续7日、7次任务均生成日报且≤2小时；P8-TC-04：尚未形成连续 7 个自然日的实际计划运行证据 |
| NFR-S02 | NOT_RUN | 8/运营期 | 建立滚动报表；未满30日不得宣称通过；P8-TC-08：未满 30 个自然日，不得提前宣称稳定性指标通过 |
| NFR-S03 | NOT_RUN | 6、8 | 每次 attempted_sources 等于启用来源数；P8-TC-04：尚未形成连续 7 个自然日的实际计划运行证据 |
| NFR-S04 | NOT_RUN | 8 | 按 PRD 方法抽检，相关率≥90%；P8-TC-05：尚未提交基于 7 日正式档案的人工质量抽检结果 |
| NFR-S05 | NOT_RUN | 8 | 用户二值评价，值得优先阅读比例≥90%；P8-TC-05：尚未提交基于 7 日正式档案的人工质量抽检结果 |
| NFR-S06 | NOT_RUN | 8 | 抽检关键结论，可追溯率≥95%，重大编造为0；P8-TC-05：尚未提交基于 7 日正式档案的人工质量抽检结果 |
| NFR-S07 | NOT_RUN | 8 | 抽检中明确排除内容为0；P8-TC-05：尚未提交基于 7 日正式档案的人工质量抽检结果 |
| NFR-S08 | NOT_RUN | 4、5、8 | 正式档案均至少关联一个有效来源；P8-TC-05：尚未提交基于 7 日正式档案的人工质量抽检结果 |
| NFR-S09 | PASS | 7、8 | 页面统计与 SQLite 查询完全一致；docs/phase8/evidence/p8-tc-03-performance.json |

## CTD 执行别名

| ID | 状态 | 阶段/范围 | 证据或延期理由 |
| --- | --- | --- | --- |
| TA-OBS-01 | PASS | 1、2、8 | 未安装 Obsidian 时后端、网页、采集、搜索和 Fake 推送全量门禁通过；docs/phase8/evidence/p8-tc-01-full-gate.json |
| TA-OBS-02 | PASS | 2 | 修改或删除 vault-view/ 文件后，SQLite/Raw/Archive 哈希不变，投影可重建；docs/phase8/evidence/p8-tc-01-full-gate.json |
| TA-OBS-03 | PASS | 1、2、8 | 包清单、启动脚本和测试不包含 Obsidian/社区插件前置；.obsidian/ 不参与权威数据对账；docs/phase8/evidence/p8-tc-01-full-gate.json |
| TA-MAN-01 | PASS | 3、4、5 | Manual Inbox 条目经过采集、去重、评分和归档全链路；未达标不入正式档案，且不计入自动来源完整性；docs/phase8/evidence/p8-tc-01-full-gate.json |
| TA-GH-01 | PASS | 3 | 当前与七日前快照计算正确；基线不足返回 insufficient_history，不产生伪造增长值；docs/phase8/evidence/p8-tc-01-full-gate.json |
| TA-SEARCH-01 | PASS | 7 | FTS5 与 Embedding 融合结果可复现；Embedding 不可用时 FTS5 仍返回结果并展示降级状态；docs/phase8/evidence/p8-tc-01-full-gate.json |
| TA-PROV-01 | PASS | 2、4、5 | Raw、Archive、派生输出均可由稳定 ID 和哈希追溯；派生内容不得覆盖上游记录；docs/phase8/evidence/p8-tc-01-full-gate.json |

