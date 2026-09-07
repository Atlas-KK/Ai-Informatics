import { Alert, Card, Col, Empty, Row, Space, Statistic, Tag, Typography } from 'antd'
import { lazy, Suspense } from 'react'
import { tierLabels } from '../../app/labels'
import { AsyncStateView, IntelList, PageHeader } from '../../components'
import type { DashboardData, Tier } from '../../types'

const { Text } = Typography
const MiniChart = lazy(() => import('../../MiniChart'))

interface DashboardPageProps {
  dashboard: DashboardData | null
  onOpen: (id: string) => void
  onSelectTopic: (topic: string) => void
}

export function DashboardPage({ dashboard, onOpen, onSelectTopic }: DashboardPageProps) {
  if (!dashboard) return <AsyncStateView state="loading" description="正在加载今日情报" />
  const run = dashboard.latest_run
  const hasHistory = dashboard.total_count > 0

  return (
    <Space orientation="vertical" size="large" className="full-width">
      <PageHeader
        title="今日情报"
        description={`${dashboard.window_start} 至 ${dashboard.report_date} · 最近 7 天滚动窗口`}
      />
      {dashboard.today_count === 0 && (
        <Alert type="info" showIcon title="今日无达标情报" description="不会降低 70 分阈值补足数量。" />
      )}
      {!dashboard.data_complete && (
        <Alert
          type="warning"
          showIcon
          title="统计数据不完整"
          description="部分来源失败或仍在处理中；已完成并正式归档的情报仍可查看。"
        />
      )}
      <Alert
        showIcon
        type={run?.status === 'SUCCEEDED' ? 'success' : run ? 'warning' : 'info'}
        title={`任务状态：${run?.status ?? '今日尚未运行'}`}
        description={run
          ? `归档 ${run.archived_count} 条，失败来源 ${run.failed_sources} 个，待处理 ${run.pending_count} 条`
          : undefined}
      />
      <Row gutter={[16, 16]}>
        <Col xs={12} md={6}><Card><Statistic title="情报总数" value={dashboard.total_count} suffix="条" /></Card></Col>
        {(['MUST_READ', 'IMPORTANT', 'EXTENDED'] as Tier[]).map((tier) => (
          <Col xs={12} md={6} key={tier}>
            <Card><Statistic title={tierLabels[tier]} value={dashboard.tier_counts[tier]} /></Card>
          </Col>
        ))}
      </Row>
      <section aria-labelledby="topic-entry-title">
        <Space orientation="vertical" size="middle" className="full-width">
          <div className="section-heading">
            <div>
              <Typography.Title level={3} id="topic-entry-title">专题入口</Typography.Title>
              <Text type="secondary">进入专题后可按二级标签和层级继续筛选</Text>
            </div>
          </div>
          <Row gutter={[16, 16]}>
            {dashboard.topic_summaries.map((topic) => (
              <Col xs={24} md={12} xl={6} key={topic.name}>
                <button className="topic-entry" type="button" onClick={() => onSelectTopic(topic.name)}>
                  <span className="topic-entry-heading">
                    <Text strong>{topic.name}</Text>
                    <Tag color="blue">{topic.count} 条</Tag>
                  </span>
                  <span className="topic-entry-tags">
                    {topic.tags.length
                      ? topic.tags.slice(0, 3).map((tag) => <Tag key={tag.name}>{tag.name}</Tag>)
                      : <Text type="secondary">暂无二级标签</Text>}
                  </span>
                </button>
              </Col>
            ))}
          </Row>
        </Space>
      </section>
      {hasHistory ? (
        <Row gutter={[16, 16]}>
          <Suspense fallback={<Col span={24}><Card loading /></Col>}>
            <Col xs={24} lg={12}><Card title="专题分布"><MiniChart data={dashboard.topic_counts} /></Card></Col>
            <Col xs={24} lg={12}><Card title="来源构成"><MiniChart data={dashboard.source_counts} /></Card></Col>
            <Col xs={24} lg={12}><Card title="新增 / 更新"><MiniChart data={dashboard.change_counts} /></Card></Col>
            <Col xs={24} lg={12}><Card title="过去 7 天趋势"><MiniChart data={dashboard.seven_day_trend} /></Card></Col>
          </Suspense>
        </Row>
      ) : (
        <Card title="趋势与分布"><Empty description="最近 7 天暂无可统计的正式情报" /></Card>
      )}
      <Card
        title="情报清单"
        extra={dashboard.total_count > dashboard.items.length
          ? <Text type="secondary">展示最近 {dashboard.items.length} 条</Text>
          : undefined}
      >
        <IntelList
          items={dashboard.items}
          onOpen={onOpen}
          emptyDescription="最近 7 天暂无达标情报"
        />
      </Card>
    </Space>
  )
}
