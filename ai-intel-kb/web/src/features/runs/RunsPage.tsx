import { ReloadOutlined } from '@ant-design/icons'
import { Alert, Button, Card, Col, Empty, List, Row, Space, Statistic, Table, Typography } from 'antd'
import type { KeyboardEvent } from 'react'
import { useEffect, useMemo, useState } from 'react'
import { api } from '../../api'
import { AsyncStateView, StatusBadge } from '../../components'
import type { PipelineRun, PipelineRunDetail } from '../../types'

const { Paragraph, Text, Title } = Typography

const triggerLabels: Record<string, string> = {
  SCHEDULED: '定时任务', CATCH_UP: '补偿运行', MANUAL: '手动运行',
}

interface RunRetryResponse {
  retried: Array<{ aggregate_version_id: string; stage: string }>
  failed: Array<{ aggregate_version_id: string; stage: string; error_code: string }>
}

interface DeliveryRetryResponse {
  status: string
  retried_segment_ids: string[]
  failed_segments: number
}

function elapsed(run: PipelineRun) {
  if (!run.finished_at) return '运行中'
  const seconds = Math.max(0, Math.round((Date.parse(run.finished_at) - Date.parse(run.started_at)) / 1000))
  return `${String(Math.floor(seconds / 60)).padStart(2, '0')}:${String(seconds % 60).padStart(2, '0')}`
}

function formatTime(value: string) {
  return new Intl.DateTimeFormat('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }).format(new Date(value))
}

export function RunsPage({
  runs, refresh, notify,
}: {
  runs: PipelineRun[]
  refresh: () => Promise<void>
  notify: { success: (value: string) => unknown; error: (value: string) => unknown }
}) {
  const [selectedId, setSelectedId] = useState<string | null>(runs[0]?.run_id ?? null)
  const [detail, setDetail] = useState<PipelineRunDetail | null>(null)
  const [loading, setLoading] = useState(false)
  const [actioning, setActioning] = useState(false)
  const effectiveSelectedId = selectedId && runs.some((run) => run.run_id === selectedId)
    ? selectedId
    : runs[0]?.run_id ?? null

  useEffect(() => {
    if (!effectiveSelectedId) return
    let active = true
    void Promise.resolve().then(async () => {
      if (active) setLoading(true)
      try {
        const value = await api<PipelineRunDetail>(`/api/runs/${effectiveSelectedId}`)
        if (active) setDetail(value)
      } catch (error) {
        if (active) void notify.error(error instanceof Error ? error.message : '运行详情加载失败')
      } finally {
        if (active) setLoading(false)
      }
    })
    return () => { active = false }
  }, [effectiveSelectedId, notify])

  const metrics = useMemo(() => {
    const today = new Date().toISOString().slice(0, 10)
    const completed = runs.filter((run) => run.status === 'SUCCEEDED')
    const durations = completed.filter((run) => run.finished_at).map((run) => Date.parse(run.finished_at as string) - Date.parse(run.started_at))
    return {
      today: runs.filter((run) => run.report_date === today).length,
      success: runs.length ? Math.round((completed.length / runs.length) * 1000) / 10 : 0,
      average: durations.length ? Math.round(durations.reduce((sum, value) => sum + value, 0) / durations.length / 1000) : 0,
      warnings: runs.filter((run) => run.retry_count > 0 || ['FAILED', 'TIMED_OUT', 'WAITING_RETRY'].includes(run.status)).length,
    }
  }, [runs])

  const reloadDetail = async () => {
    if (!effectiveSelectedId) return
    setDetail(await api<PipelineRunDetail>(`/api/runs/${effectiveSelectedId}`))
  }
  const retryRun = async () => {
    if (!detail) return
    setActioning(true)
    try {
      const result = await api<RunRetryResponse>(`/api/runs/${detail.run_id}/retry`, { method: 'POST' })
      await Promise.all([refresh(), reloadDetail()])
      if (result.failed.length) {
        void notify.error(`重试后仍有 ${result.failed.length} 个工作项失败`)
      } else {
        void notify.success(`已完成 ${result.retried.length} 个工作项的阶段重试`)
      }
    } catch (error) {
      void notify.error(error instanceof Error ? error.message : '重试失败')
    } finally { setActioning(false) }
  }
  const retryDelivery = async () => {
    if (!detail?.digest) return
    setActioning(true)
    try {
      const result = await api<DeliveryRetryResponse>(`/api/digests/${detail.digest.digest_id}/retry-failed-segments`, { method: 'POST' })
      await reloadDetail()
      if (result.failed_segments) {
        void notify.error(`已重发 ${result.retried_segment_ids.length} 个分段，仍有 ${result.failed_segments} 个失败`)
      } else {
        void notify.success(`已成功重发 ${result.retried_segment_ids.length} 个失败分段`)
      }
    } catch (error) {
      void notify.error(error instanceof Error ? error.message : '分段重发失败')
    } finally { setActioning(false) }
  }
  const selectRunFromKeyboard = (event: KeyboardEvent<HTMLElement>, runId: string) => {
    if (event.key !== 'Enter' && event.key !== ' ') return
    event.preventDefault()
    setSelectedId(runId)
  }

  return (
    <div className="runs-page">
      <div className="page-header">
        <div><Title level={2}>运行记录</Title><Text type="secondary">追踪采集、处理、入库与投递状态，快速定位并恢复失败环节。</Text></div>
        <Button icon={<ReloadOutlined />} onClick={() => void refresh()}>刷新</Button>
      </div>
      <Row gutter={[16, 16]} className="runs-metrics">
        <Col xs={12} lg={6}><Card><Statistic title="今日运行" value={metrics.today} suffix="次" /></Card></Col>
        <Col xs={12} lg={6}><Card><Statistic title="成功率" value={metrics.success} suffix="%" /></Card></Col>
        <Col xs={12} lg={6}><Card><Statistic title="平均耗时" value={`${String(Math.floor(metrics.average / 60)).padStart(2, '0')}:${String(metrics.average % 60).padStart(2, '0')}`} /></Card></Col>
        <Col xs={12} lg={6}><Card><Statistic title="待处理告警" value={metrics.warnings} suffix="条" styles={{ content: { color: metrics.warnings ? '#f79009' : undefined } }} /></Card></Col>
      </Row>
      <Row gutter={[16, 16]} align="stretch">
        <Col xs={24} xl={15}>
          <Card title="执行记录" className="runs-panel">
            <Table rowKey="run_id" dataSource={runs} pagination={{ pageSize: 8 }} scroll={{ x: 720 }} onRow={(run) => ({ onClick: () => setSelectedId(run.run_id), onKeyDown: (event) => selectRunFromKeyboard(event, run.run_id), tabIndex: 0, 'aria-label': `查看运行详情：${run.run_id}`, className: effectiveSelectedId === run.run_id ? 'run-row-selected' : '' })} columns={[
              { title: '开始时间', dataIndex: 'started_at', render: formatTime },
              { title: '触发方式', dataIndex: 'trigger_type', render: (value: string) => triggerLabels[value] ?? value },
              { title: '耗时', render: (_, run: PipelineRun) => elapsed(run) },
              { title: '结果', dataIndex: 'status', render: (value: string) => <StatusBadge status={value} /> },
              { title: '处理量', render: (_, run: PipelineRun) => `${run.archived_count} 条` },
              { title: '操作', render: (_, run: PipelineRun) => <Button type="link" onClick={(event) => { event.stopPropagation(); setSelectedId(run.run_id) }}>详情</Button> },
            ]} />
          </Card>
        </Col>
        <Col xs={24} xl={9}>
          <Card title="运行详情" className="runs-panel">
            {loading ? <AsyncStateView state="loading" description="正在加载运行详情" /> : !detail ? <Empty description="请选择一条运行记录" /> : (
              <Space orientation="vertical" size="middle" className="full-width">
                <div className="run-detail-heading"><Text copyable={{ text: detail.run_id }}>运行 ID：{detail.run_id}</Text><StatusBadge status={detail.status} /></div>
                {detail.status === 'TIMED_OUT' && <Alert type="warning" showIcon title="任务已超时停止新工作" description="已完成内容已提交，未完成工作项保留为待重试，可通过补偿运行恢复。" />}
                {detail.status === 'REJECTED_DUPLICATE' && <Alert type="info" showIcon title="重复启动已拒绝" description="已有运行持有全局锁，本次请求未执行任何处理。" />}
                {detail.error_code === 'STALE_RUN_RECOVERED' && <Alert type="warning" showIcon title="已释放失活运行锁" description="系统确认原进程不再存活，工作已转为等待重试。" />}
                <div><Text strong>处理阶段</Text><List size="small" dataSource={detail.work_items} locale={{ emptyText: '本次运行没有工作项' }} renderItem={(item) => <List.Item extra={<StatusBadge status={item.status} />}><List.Item.Meta title={item.canonical_title} description={`${item.stage} · ${formatTime(item.updated_at)}`} /></List.Item>} /></div>
                {detail.source_failures.length > 0 && <div><Text strong>失败来源</Text><List size="small" dataSource={detail.source_failures} renderItem={(item) => <List.Item><List.Item.Meta title={`${item.source_id ?? '未知来源'} · ${item.stage} · ${item.status}`} description={`${item.reason} · 已重试 ${item.retry_count} 次 · ${formatTime(item.occurred_at)}`} /></List.Item>} /></div>}
                <Button type="primary" block disabled={!detail.retryable_work_items.length} loading={actioning} onClick={() => void retryRun()}>重试失败阶段及后续</Button>
                <div><Text strong>飞书投递分段</Text>{!detail.digest ? <Paragraph type="secondary">本次运行尚未生成本地日报。</Paragraph> : <><Paragraph type="secondary">本地日报已保留：{detail.digest.markdown_path}</Paragraph><List size="small" dataSource={detail.digest.segments} locale={{ emptyText: '未配置投递或尚未生成分段' }} renderItem={(segment) => <List.Item extra={<StatusBadge status={segment.status} />}>分段 {segment.segment_no} · 尝试 {segment.attempt_count} 次{segment.error_code ? ` · ${segment.error_code}` : ''}</List.Item>} /><Button block disabled={!detail.digest.segments.some((item) => item.status === 'FAILED')} loading={actioning} onClick={() => void retryDelivery()}>仅重发失败分段</Button></>}</div>
                <div><Text strong>关键事件</Text><List size="small" className="run-timeline" dataSource={detail.timeline} locale={{ emptyText: '暂无事件' }} renderItem={(item) => <List.Item><Text code>{formatTime(item.created_at)}</Text><Text>{item.event_type}{item.status ? ` · ${item.status}` : ''}{item.error_code ? ` · ${item.error_code}` : ''}</Text></List.Item>} /></div>
              </Space>
            )}
          </Card>
        </Col>
      </Row>
    </div>
  )
}
