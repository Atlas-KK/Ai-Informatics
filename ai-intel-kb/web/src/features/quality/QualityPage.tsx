import {
  Alert,
  Button,
  Card,
  Descriptions,
  Drawer,
  Empty,
  Select,
  Space,
  Statistic,
  Table,
  Tabs,
  Tag,
  Typography,
  message,
} from 'antd'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { api } from '../../api'
import { AsyncStateView, ConfirmAction, PageHeader } from '../../components'
import type { CalibrationProposal, CalibrationWorkbench, FeedbackRecord } from '../../types'

const { Text } = Typography

const DIMENSION_LABELS: Record<string, string> = {
  source_authority: '来源权威性',
  timeliness: '时效性',
  reach: '传播影响力',
  information_density: '信息密度',
  innovation: '创新性',
}

interface QualityPageProps {
  feedback: FeedbackRecord[]
  refresh: () => Promise<void>
  notify: ReturnType<typeof message.useMessage>[0]
}

interface RescoreResult {
  appended: Array<{
    aggregate_version_id: string
    latest_score: number
    new_score: number
    new_score_id: string
    config_version: number
    score_count: number
  }>
}

function errorMessage(error: unknown, fallback: string) {
  return error instanceof Error ? error.message : fallback
}

export function QualityPage({ feedback, refresh, notify }: QualityPageProps) {
  const [workbench, setWorkbench] = useState<CalibrationWorkbench | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [assessment, setAssessment] = useState<CalibrationProposal | null>(null)
  const [selectedFeedback, setSelectedFeedback] = useState<FeedbackRecord | null>(null)
  const [rollbackVersion, setRollbackVersion] = useState<number | null>(null)
  const [selectedTargets, setSelectedTargets] = useState<React.Key[]>([])
  const [rescoreResult, setRescoreResult] = useState<RescoreResult | null>(null)
  const [pending, setPending] = useState(false)

  const loadWorkbench = useCallback(async () => {
    setLoading(true)
    try {
      setWorkbench(await api<CalibrationWorkbench>('/api/calibration/workbench'))
      setError('')
    } catch (loadError) {
      setError(errorMessage(loadError, '校准工作台加载失败'))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    const timer = window.setTimeout(() => void loadWorkbench(), 0)
    return () => window.clearTimeout(timer)
  }, [loadWorkbench])

  const run = async (operation: () => Promise<void>, fallback: string) => {
    setPending(true)
    try {
      await operation()
    } catch (operationError) {
      void notify.error(errorMessage(operationError, fallback))
    } finally {
      setPending(false)
    }
  }

  const calibrate = () => run(async () => {
    const next = await api<CalibrationProposal>('/api/calibration/proposals', { method: 'POST' })
    setAssessment(next)
    await loadWorkbench()
    if (!next.proposal) void notify.warning(`当前仅 ${next.sample_count} 条反馈，样本不足，未生成新配置`)
  }, '校准评估失败')

  const decide = (action: 'confirm' | 'reject') => run(async () => {
    if (!activeAssessment?.proposal) return
    await api(`/api/calibration/${activeAssessment.proposal.proposal_id}/${action}`, {
      method: 'POST',
      body: action === 'confirm' ? JSON.stringify({ confirmed: true }) : undefined,
    })
    setAssessment(null)
    await Promise.all([loadWorkbench(), refresh()])
    void notify.success(action === 'confirm' ? '新评分版本已启用' : '校准建议已拒绝')
  }, '校准决策失败')

  const rollback = () => run(async () => {
    if (rollbackVersion === null) return
    await api(`/api/calibration/config/${rollbackVersion}/rollback`, {
      method: 'POST', body: JSON.stringify({ confirmed: true }),
    })
    setRollbackVersion(null)
    await Promise.all([loadWorkbench(), refresh()])
    void notify.success(`已回退到评分配置 v${rollbackVersion}`)
  }, '版本回退失败')

  const rescore = () => run(async () => {
    const result = await api<RescoreResult>('/api/calibration/rescore', {
      method: 'POST',
      body: JSON.stringify({ aggregate_version_ids: selectedTargets, confirmed: true }),
    })
    setRescoreResult(result)
    setSelectedTargets([])
    await loadWorkbench()
    void notify.success(`已追加 ${result.appended.length} 条评分记录，历史评分保持不变`)
  }, '历史重评分失败')

  const rollbackOptions = useMemo(
    () => workbench?.configs
      .filter((item) => !item.is_active)
      .map((item) => ({ label: `score-v${item.version}`, value: item.version })) ?? [],
    [workbench],
  )
  const storedPendingProposal = workbench?.proposals.find((item) => item.decision === null)
  const activeAssessment: CalibrationProposal | null = assessment ?? (storedPendingProposal ? {
    sample_count: storedPendingProposal.sample_count,
    uncertainty: storedPendingProposal.uncertainty,
    proposal: storedPendingProposal,
  } : null)
  const proposalBaseConfig = workbench?.configs.find(
    (item) => item.version === activeAssessment?.proposal?.base_config_version,
  )
  const proposalIsStale = Boolean(
    activeAssessment?.proposal
    && activeAssessment.proposal.base_config_version !== workbench?.active_version,
  )

  if (loading && !workbench) return <AsyncStateView state="loading" description="正在加载质量校准工作台" />
  if (error && !workbench) {
    return <AsyncStateView state="error" errorTitle="质量校准工作台加载失败" description={error} onRetry={() => void loadWorkbench()} />
  }

  const feedbackTab = (
    <Card>
      {!feedback.length ? <Empty description="尚无质量反馈，可在情报详情页提交" /> : (
        <Table
          rowKey="feedback_id"
          dataSource={feedback}
          pagination={{ pageSize: 10 }}
          columns={[
            { title: '情报', dataIndex: 'canonical_title', ellipsis: true },
            { title: '处理结果', dataIndex: 'outcome', render: (value: string) => <Tag color={value === 'REMOVED' ? 'red' : 'green'}>{value === 'REMOVED' ? '已移除' : '已保留'}</Tag> },
            { title: '影响维度', dataIndex: 'affected_dimension', render: (value: string) => DIMENSION_LABELS[value] ?? value },
            { title: '原评分', dataIndex: 'original_score', width: 90 },
            { title: '时间', dataIndex: 'created_at', render: (value: string) => new Date(value).toLocaleString('zh-CN') },
            { title: '操作', key: 'action', width: 90, render: (_: unknown, record: FeedbackRecord) => <Button type="link" onClick={() => setSelectedFeedback(record)}>查看详情</Button> },
          ]}
        />
      )}
    </Card>
  )

  const calibrationTab = (
    <Space orientation="vertical" size="large" className="full-width">
      <Alert
        type="info"
        showIcon
        message="反馈只形成校准建议，不会自动修改评分规则"
        description="建议必须经你明确确认后才会生成新的评分配置；新配置仅影响后续评分，历史评分需手动重评。"
      />
      <Card
        title="评分校准建议"
        extra={<Button type="primary" disabled={Boolean(activeAssessment?.proposal)} loading={pending} onClick={() => void calibrate()}>基于当前反馈生成建议</Button>}
      >
        <Space size="large" wrap>
          <Statistic title="反馈样本" value={activeAssessment?.sample_count ?? feedback.length} suffix="条" />
          <Statistic title="当前配置" value={`score-v${workbench?.active_version ?? '-'}`} />
          <Statistic title="不确定性" value={activeAssessment?.uncertainty ?? '待评估'} />
        </Space>
      </Card>
      {activeAssessment && !activeAssessment.proposal && (
        <Alert type="warning" showIcon message="样本不足，未生成校准配置" description={`至少需要 5 条反馈；当前 ${activeAssessment.sample_count} 条，不确定性为 ${activeAssessment.uncertainty}。`} />
      )}
      {activeAssessment?.proposal && (
        <Card
          title={`待确认建议 · 基于 score-v${activeAssessment.proposal.base_config_version}`}
          extra={(
            <Space>
              <Button disabled={pending} onClick={() => void decide('reject')}>拒绝建议</Button>
              <ConfirmAction
                title="确认启用新的评分配置？"
                description="该操作会创建新版本，但不会覆盖历史评分。"
                disabled={proposalIsStale}
                onConfirm={() => decide('confirm')}
              >
                <Button type="primary" disabled={proposalIsStale} loading={pending}>审核并确认</Button>
              </ConfirmAction>
            </Space>
          )}
        >
          {proposalIsStale && (
            <Alert
              className="section-alert"
              type="warning"
              showIcon
              message="该提案基于非当前评分版本，不能再确认"
              description="你可以拒绝该提案，再基于当前配置生成新的校准建议。"
            />
          )}
          <div className="quality-weight-grid">
            {Object.entries(activeAssessment.proposal.suggested_weights).map(([dimension, weight]) => {
              const before = proposalBaseConfig?.weights[dimension]
              return (
                <div key={dimension}>
                  <Text type="secondary">{DIMENSION_LABELS[dimension] ?? dimension}</Text>
                  <strong>{before === undefined ? '—' : `${(before * 100).toFixed(1)}%`} → {(weight * 100).toFixed(1)}%</strong>
                </div>
              )
            })}
          </div>
          <Descriptions
            className="section-table"
            bordered
            column={1}
            items={[
              { key: 'scope', label: '预计影响', children: String(activeAssessment.proposal.estimated_impact.scope ?? '仅影响未来评分') },
              { key: 'dimension', label: '主要反馈维度', children: activeAssessment.proposal.affected_dimensions.map((item) => DIMENSION_LABELS[item] ?? item).join('、') },
              { key: 'history', label: '历史评分', children: '保留，不自动重算' },
            ]}
          />
        </Card>
      )}
    </Space>
  )

  const versionsTab = (
    <Space orientation="vertical" size="large" className="full-width">
      <Card title="评分配置版本">
        <Table
          rowKey="version"
          pagination={false}
          dataSource={workbench?.configs ?? []}
          columns={[
            { title: '版本', dataIndex: 'version', render: (value: number) => `score-v${value}` },
            { title: '状态', dataIndex: 'is_active', render: (active: boolean) => <Tag color={active ? 'green' : 'default'}>{active ? '当前启用' : '历史版本'}</Tag> },
            { title: '创建时间', dataIndex: 'created_at', render: (value: string) => new Date(value).toLocaleString('zh-CN') },
            { title: '权重合计', dataIndex: 'weights', render: (weights: Record<string, number>) => `${(Object.values(weights).reduce((sum, value) => sum + value, 0) * 100).toFixed(0)}%` },
          ]}
        />
      </Card>
      <Card title="回退到历史版本">
        <Space wrap>
          <Select
            aria-label="选择历史评分版本"
            placeholder="选择一个真实历史版本"
            value={rollbackVersion}
            options={rollbackOptions}
            onChange={setRollbackVersion}
            className="quality-version-select"
          />
          <ConfirmAction
            title={`确认回退到 score-v${rollbackVersion ?? ''}？`}
            description="回退会切换当前配置并记录审计，不删除后续版本。"
            disabled={rollbackVersion === null}
            onConfirm={rollback}
          >
            <Button danger disabled={rollbackVersion === null} loading={pending}>确认回退</Button>
          </ConfirmAction>
        </Space>
      </Card>
      <Card title="变更审计">
        <Table
          rowKey="audit_id"
          pagination={{ pageSize: 8 }}
          dataSource={workbench?.audits ?? []}
          columns={[
            { title: '动作', dataIndex: 'action', render: (value: string) => ({ INITIALIZE: '初始化', CONFIRM: '确认新版本', ROLLBACK: '回退' })[value] ?? value },
            { title: '原版本', dataIndex: 'old_config_version', render: (value: number | null) => value ? `score-v${value}` : '—' },
            { title: '目标版本', dataIndex: 'new_config_version', render: (value: number) => `score-v${value}` },
            { title: '时间', dataIndex: 'created_at', render: (value: string) => new Date(value).toLocaleString('zh-CN') },
          ]}
        />
      </Card>
      <Card title="校准提案记录">
        <Table
          rowKey="proposal_id"
          pagination={{ pageSize: 8 }}
          dataSource={workbench?.proposals ?? []}
          locale={{ emptyText: '暂无校准提案' }}
          columns={[
            { title: '基础版本', dataIndex: 'base_config_version', render: (value: number) => `score-v${value}` },
            { title: '样本量', dataIndex: 'sample_count' },
            { title: '不确定性', dataIndex: 'uncertainty' },
            { title: '决策', dataIndex: 'decision', render: (value: string | null) => value === 'CONFIRMED' ? <Tag color="green">已确认</Tag> : value === 'REJECTED' ? <Tag>已拒绝</Tag> : <Tag color="gold">待处理</Tag> },
            { title: '新版本', dataIndex: 'new_config_version', render: (value: number | null) => value ? `score-v${value}` : '—' },
            { title: '创建时间', dataIndex: 'created_at', render: (value: string) => new Date(value).toLocaleString('zh-CN') },
          ]}
        />
      </Card>
    </Space>
  )

  const rescoreTab = (
    <Space orientation="vertical" size="large" className="full-width">
      <Alert type="warning" showIcon message="历史重评分是手动追加操作" description="仅对勾选的反馈关联情报执行；原评分记录不会被修改或删除。" />
      <Card
        title="选择重评分范围"
        extra={(
          <ConfirmAction
            title={`确认重评 ${selectedTargets.length} 条情报？`}
            description={`将使用当前 score-v${workbench?.active_version ?? '-'} 追加评分记录。`}
            disabled={!selectedTargets.length}
            onConfirm={rescore}
          >
            <Button type="primary" disabled={!selectedTargets.length} loading={pending}>执行历史重评分</Button>
          </ConfirmAction>
        )}
      >
        <Table
          rowKey="aggregate_version_id"
          dataSource={workbench?.rescore_targets ?? []}
          rowSelection={{ selectedRowKeys: selectedTargets, onChange: setSelectedTargets }}
          pagination={{ pageSize: 10 }}
          locale={{ emptyText: '暂无可重评分的反馈关联情报' }}
          columns={[
            { title: '情报', dataIndex: 'canonical_title', ellipsis: true },
            { title: '最新评分', dataIndex: 'latest_score', width: 100 },
            { title: '评分版本', dataIndex: 'config_version', render: (value: number) => `score-v${value}` },
            { title: '历史记录数', dataIndex: 'score_count', width: 110 },
          ]}
        />
      </Card>
      {rescoreResult && (
        <Alert
          type="success"
          showIcon
          message={`已追加 ${rescoreResult.appended.length} 条评分记录`}
          description={rescoreResult.appended.map((item) => `${item.latest_score} → ${item.new_score}（共 ${item.score_count} 条历史）`).join('；')}
        />
      )}
    </Space>
  )

  return (
    <Space orientation="vertical" size="large" className="full-width">
      <PageHeader title="质量反馈与评分校准" description="审阅反馈、确认校准版本，并按需对历史情报追加重评分。" />
      <Tabs
        items={[
          { key: 'feedback', label: `反馈记录 (${feedback.length})`, children: feedbackTab },
          { key: 'calibration', label: '校准工作台', children: calibrationTab },
          { key: 'versions', label: '版本历史', children: versionsTab },
          { key: 'rescore', label: '历史重评分', children: rescoreTab },
        ]}
      />
      <Drawer title="质量反馈详情" open={selectedFeedback !== null} onClose={() => setSelectedFeedback(null)} size={520}>
        {selectedFeedback && (
          <Descriptions
            bordered
            column={1}
            items={[
              { key: 'title', label: '情报', children: selectedFeedback.canonical_title },
              { key: 'reason', label: '反馈原因', children: selectedFeedback.reason },
              { key: 'dimension', label: '影响维度', children: DIMENSION_LABELS[selectedFeedback.affected_dimension] ?? selectedFeedback.affected_dimension },
              { key: 'outcome', label: '处理结果', children: selectedFeedback.outcome === 'REMOVED' ? '已移除' : '已保留' },
              { key: 'score', label: '原评分', children: `${selectedFeedback.original_score} / score-v${selectedFeedback.score_version}` },
              { key: 'features', label: '内容特征', children: Object.keys(selectedFeedback.content_features).length ? JSON.stringify(selectedFeedback.content_features, null, 2) : '未记录' },
              { key: 'time', label: '提交时间', children: new Date(selectedFeedback.created_at).toLocaleString('zh-CN') },
            ]}
          />
        )}
      </Drawer>
    </Space>
  )
}
