# Phase 8 人工/外部证据格式

这些证据只接受实际运行或人工判定，不接受 Fake Clock、自动生成的正向答案或生产凭证。

## 7 日试运行

`scripts/phase8-soak.ps1` 以 SQLite 只读模式提取最近一次实际 `SCHEDULED` 运行，追加到 `docs/phase8/evidence/soak-observations.json`。采证会分别读取运行开始事件中的不可变启用来源快照、逐来源完成事件以及当前 `run_id` 的日报生成事件，不以来源尝试列表反推启用快照，也不关联同日其他任务的日报。脚本不会创建 Windows 计划任务，也不会主动运行管线。累计至少 7 个自然日后评估最近连续 7 日窗口；同一文件可继续累计滚动 30 日证据。

## 人工质量抽检

人工复核后创建 `docs/phase8/evidence/quality-review.json`。所有布尔字段必须使用 JSON `true`/`false`，字符串 `"true"`/`"false"` 会被拒绝：

```json
{
  "formal_count": 1,
  "expected_must_read_ids": ["event-id"],
  "formal_records_without_valid_source": 0,
  "reviews": [
    {
      "event_id": "event-id",
      "tier": "MUST_READ",
      "relevant": true,
      "worth_priority": true,
      "conclusion_count": 2,
      "traceable_conclusion_count": 2,
      "major_hallucination": false,
      "excluded_content": false,
      "valid_source_count": 1
    }
  ]
}
```

正式档案不足 30 条时必须全检，否则恰好抽 30 条；抽样必须包含周期内全部必读项。`worth_priority` 只对必读项必填。判定标准来自 PRD，不得为通过测试而修改阈值。

## 真实适配器小流量验证

只有在用户另行授权专用测试凭证和测试对象后，才可创建 `docs/phase8/evidence/real-adapters.json`。每条 `PASS` 检查必须引用项目目录内已存在的脱敏证据文件：

```json
{
  "authorization_reference": "用户授权记录编号，不含任何凭证值",
  "checks": [
    {
      "adapter": "provider-name",
      "status": "PASS",
      "evidence": "已脱敏证据路径"
    }
  ]
}
```

不得把 token、Cookie、账号密码、个人生产凭证或响应中的敏感正文写入该文件。

## 跳过自动命令

`scripts/phase8-audit.ps1 -SkipCommands` 只用于补充自然日、人工或真实适配证据后刷新报告。四份自动命令证据均包含当前源代码、测试、迁移、脚本和锁文件的 SHA-256 指纹；指纹、用例编号、退出码或状态不一致时命令会拒绝复用，必须重新执行完整审计。
