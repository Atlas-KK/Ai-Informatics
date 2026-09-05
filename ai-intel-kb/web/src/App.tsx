import {
  BarChartOutlined,
  BookOutlined,
  ClockCircleOutlined,
  DatabaseOutlined,
  DeleteOutlined,
  DownOutlined,
  EditOutlined,
  HistoryOutlined,
  InboxOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  PlusOutlined,
  ReloadOutlined,
  SearchOutlined,
  SettingOutlined,
  StarFilled,
  StarOutlined,
  UpOutlined,
} from '@ant-design/icons'
import {
  Alert,
  Button,
  Card,
  Col,
  Descriptions,
  Divider,
  Drawer,
  Empty,
  Form,
  Input,
  InputNumber,
  Layout,
  Menu,
  message,
  Modal,
  Popconfirm,
  Progress,
  Result,
  Row,
  Select,
  Space,
  Statistic,
  Switch,
  Table,
  Tabs,
  Tag,
  Timeline,
  Typography,
} from 'antd'
import { lazy, Suspense, useCallback, useEffect, useMemo, useState } from 'react'
import { api } from './api'
import type {
  AppSettings,
  ArchiveDetail,
  ArchiveItem,
  CalibrationProposal,
  ConfigurationStatus,
  DashboardData,
  ExpertRecord,
  ExtensionResult,
  FeedbackRecord,
  PipelineRun,
  SourceRecord,
  Tier,
} from './types'

const { Content, Header, Sider } = Layout
const { Paragraph, Text, Title } = Typography
const MiniChart = lazy(() => import('./MiniChart'))

const menuItems = [
  { key: 'today', icon: <BarChartOutlined />, label: '今日情报' },
  { key: 'topics', icon: <BookOutlined />, label: '主题档案' },
  { key: 'history', icon: <HistoryOutlined />, label: '历史检索' },
  { key: 'sources', icon: <InboxOutlined />, label: '来源管理' },
  { key: 'quality', icon: <StarOutlined />, label: '质量反馈' },
  { key: 'runs', icon: <ClockCircleOutlined />, label: '运行记录' },
  { key: 'settings', icon: <SettingOutlined />, label: '系统设置' },
  { key: 'trash', icon: <DeleteOutlined />, label: '回收站' },
]

const tierLabels: Record<Tier, string> = {
  MUST_READ: '必读',
  IMPORTANT: '重要',
  EXTENDED: '延伸',
}
const tierColors: Record<Tier, string> = {
  MUST_READ: 'red',
  IMPORTANT: 'gold',
  EXTENDED: 'blue',
}
const dimensions = [
  'source_authority',
  'timeliness',
  'reach',
  'information_density',
  'innovation',
]

function ItemList({ items, open }: { items: ArchiveItem[]; open: (id: string) => void }) {
  if (!items.length) return <Empty description="当前条件下暂无情报" />
  return (
    <div className="intel-list">
      {items.map((item) => (
        <button
          type="button"
          key={item.event_id}
          onClick={() => open(item.event_id)}
          className="intel-list-item"
        >
          <Space orientation="vertical" size={4} align="start">
            <Space wrap>
              {item.pinned && <Tag color="blue">置顶</Tag>}
              <Text strong>{item.title}</Text>
              <Tag color={tierColors[item.tier]}>{tierLabels[item.tier]}</Tag>
              <Tag>{item.change_type === 'NEW' ? '新增' : '更新'}</Tag>
              {item.favorite && <StarFilled className="favorite-icon" aria-label="已收藏" />}
            </Space>
            <Text>{item.summary}</Text>
            <Space wrap size={4}>{item.tags.map((tag) => <Tag key={tag}>{tag}</Tag>)}</Space>
            <Text type="secondary">
              {item.topic} · {item.quality_score.toFixed(1)} 分 ·{' '}
              {new Date(item.published_at).toLocaleString()}
            </Text>
          </Space>
        </button>
      ))}
    </div>
  )
}

export default function App() {
  const [collapsed, setCollapsed] = useState(false)
  const [page, setPage] = useState('today')
  const [loading, setLoading] = useState(true)
  const [connectionError, setConnectionError] = useState('')
  const [dashboard, setDashboard] = useState<DashboardData | null>(null)
  const [archive, setArchive] = useState<ArchiveItem[]>([])
  const [sources, setSources] = useState<SourceRecord[]>([])
  const [experts, setExperts] = useState<ExpertRecord[]>([])
  const [runs, setRuns] = useState<PipelineRun[]>([])
  const [feedback, setFeedback] = useState<FeedbackRecord[]>([])
  const [settings, setSettings] = useState<AppSettings | null>(null)
  const [configuration, setConfiguration] = useState<ConfigurationStatus | null>(null)
  const [detail, setDetail] = useState<ArchiveDetail | null>(null)
  const [searchResult, setSearchResult] = useState<ArchiveItem[]>([])
  const [searchMeta, setSearchMeta] = useState('')
  const [searching, setSearching] = useState(false)
  const [messageApi, contextHolder] = message.useMessage()

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const results = await Promise.all([
        api<DashboardData>('/api/dashboard'),
        api<ArchiveItem[]>('/api/archive'),
        api<SourceRecord[]>('/api/sources'),
        api<ExpertRecord[]>('/api/experts'),
        api<PipelineRun[]>('/api/runs'),
        api<FeedbackRecord[]>('/api/feedback'),
        api<AppSettings>('/api/settings'),
        api<ConfigurationStatus>('/api/configuration-status'),
      ])
      setDashboard(results[0])
      setArchive(results[1])
      setSources(results[2])
      setExperts(results[3])
      setRuns(results[4])
      setFeedback(results[5])
      setSettings(results[6])
      setConfiguration(results[7])
      setConnectionError('')
    } catch (error) {
      setConnectionError(error instanceof Error ? error.message : '无法连接本地服务')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    const timer = window.setTimeout(() => void load(), 0)
    return () => window.clearTimeout(timer)
  }, [load])

  const openDetail = async (eventId: string) => {
    try {
      setDetail(await api<ArchiveDetail>(`/api/archive/${eventId}`))
    } catch (error) {
      void messageApi.error(error instanceof Error ? error.message : '详情加载失败')
    }
  }

  const updateMetadata = async (values: Record<string, unknown>) => {
    if (!detail) return
    await api(`/api/archive/${detail.event_id}/metadata`, {
      method: 'PATCH',
      body: JSON.stringify(values),
    })
    await openDetail(detail.event_id)
    await load()
  }

  const runSearch = async (query: string) => {
    if (!query.trim()) return
    setSearching(true)
    try {
      const result = await api<{ items: ArchiveItem[]; mode: string; degraded: boolean }>(
        `/api/search?q=${encodeURIComponent(query)}`,
      )
      setSearchResult(result.items)
      setSearchMeta(
        result.degraded ? '关键词检索（语义服务未配置）' : '关键词 + 语义融合检索',
      )
    } catch (error) {
      void messageApi.error(error instanceof Error ? error.message : '检索失败')
    } finally {
      setSearching(false)
    }
  }

  const topicGroups = useMemo(
    () =>
      (settings?.topic_order ?? []).map((topic) => ({
        topic,
        items: archive.filter((item) => item.topic === topic),
      })),
    [archive, settings],
  )

  const renderPage = () => {
    if (connectionError) {
      return (
        <Result
          status="warning"
          title="本地 API 未连接"
          subTitle={`${connectionError}。请确认服务仅监听 127.0.0.1:8000。`}
          extra={<Button onClick={() => void load()}>重新连接</Button>}
        />
      )
    }
    if (page === 'today') return <DashboardPage dashboard={dashboard} open={openDetail} />
    if (page === 'topics') {
      return (
        <Space orientation="vertical" size="large" className="full-width">
          <Title level={2}>主题档案</Title>
          {topicGroups.map(({ topic, items }) => (
            <Card key={topic} title={topic} extra={<Tag>{items.length} 条</Tag>}>
              <ItemList items={items} open={openDetail} />
            </Card>
          ))}
        </Space>
      )
    }
    if (page === 'history') {
      return (
        <HistoryPage
          archive={archive}
          searchResult={searchResult}
          searching={searching}
          searchMeta={searchMeta}
          search={runSearch}
          open={openDetail}
        />
      )
    }
    if (page === 'sources') {
      return (
        <SourcesPage
          sources={sources}
          experts={experts}
          topics={settings?.topic_order ?? []}
          refresh={load}
          notify={messageApi}
        />
      )
    }
    if (page === 'quality') {
      return <QualityPage feedback={feedback} refresh={load} notify={messageApi} />
    }
    if (page === 'runs') {
      return <RunsPage runs={runs} refresh={load} notify={messageApi} />
    }
    if (page === 'settings') {
      return (
        <SettingsPage
          settings={settings}
          configuration={configuration}
          saved={(value) => {
            setSettings(value)
            void messageApi.success('设置已保存')
          }}
          failed={(error) => void messageApi.error(error.message)}
        />
      )
    }
    return <TrashPage open={openDetail} refresh={load} />
  }

  return (
    <Layout className="app-shell">
      {contextHolder}
      <Sider
        collapsible
        collapsed={collapsed}
        trigger={null}
        breakpoint="lg"
        onBreakpoint={setCollapsed}
      >
        <div className="brand">
          <DatabaseOutlined /><span>{collapsed ? 'AI' : 'AI 情报知识库'}</span>
        </div>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[page]}
          items={menuItems}
          onClick={({ key }) => setPage(key)}
        />
      </Sider>
      <Layout>
        <Header className="app-header">
          <Button
            type="text"
            className="collapse-button"
            aria-label="切换导航"
            icon={collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
            onClick={() => setCollapsed(!collapsed)}
          />
          <Text className="app-title">AI 产品经理情报知识库</Text>
          <Tag color="processing">Phase 7 · Local</Tag>
        </Header>
        <Content className="app-content" aria-busy={loading}>{renderPage()}</Content>
      </Layout>
      {detail && (
        <DetailDrawer
          key={`${detail.event_id}:${detail.note}`}
          detail={detail}
          close={() => setDetail(null)}
          updateMetadata={updateMetadata}
          refresh={load}
          notify={messageApi}
        />
      )}
    </Layout>
  )
}

function DashboardPage({
  dashboard,
  open,
}: {
  dashboard: DashboardData | null
  open: (id: string) => void
}) {
  const run = dashboard?.latest_run
  return (
    <Space orientation="vertical" size="large" className="full-width">
      <div>
        <Title level={2}>今日情报</Title>
        <Text type="secondary">
          {dashboard?.window_start} 至 {dashboard?.report_date} · 最近 7 天滚动窗口
        </Text>
      </div>
      {!dashboard?.data_complete && <Alert type="warning" showIcon title="统计数据不完整" />}
      <Alert
        showIcon
        type={run?.status === 'SUCCEEDED' ? 'success' : run ? 'warning' : 'info'}
        title={`任务状态：${run?.status ?? '今日尚未运行'}`}
        description={run ? `归档 ${run.archived_count} 条，失败来源 ${run.failed_sources} 个，待处理 ${run.pending_count} 条` : undefined}
      />
      <Row gutter={[16, 16]}>
        <Col xs={12} md={6}><Card><Statistic title="情报总数" value={dashboard?.total_count ?? 0} suffix="条" /></Card></Col>
        {(['MUST_READ', 'IMPORTANT', 'EXTENDED'] as Tier[]).map((tier) => (
          <Col xs={12} md={6} key={tier}>
            <Card><Statistic title={tierLabels[tier]} value={dashboard?.tier_counts[tier] ?? 0} /></Card>
          </Col>
        ))}
      </Row>
      <Row gutter={[16, 16]}>
        <Suspense fallback={<Col span={24}><Card loading /></Col>}>
          <Col xs={24} lg={12}><Card title="专题分布"><MiniChart data={dashboard?.topic_counts ?? {}} /></Card></Col>
          <Col xs={24} lg={12}><Card title="来源构成"><MiniChart data={dashboard?.source_counts ?? {}} /></Card></Col>
          <Col xs={24} lg={12}><Card title="新增 / 更新"><MiniChart data={dashboard?.change_counts ?? {}} /></Card></Col>
          <Col xs={24} lg={12}><Card title="过去 7 天趋势"><MiniChart data={dashboard?.seven_day_trend ?? {}} /></Card></Col>
        </Suspense>
      </Row>
      <Card
        title="情报清单"
        extra={(dashboard?.total_count ?? 0) > (dashboard?.items.length ?? 0)
          ? <Text type="secondary">展示最近 {dashboard?.items.length} 条</Text>
          : undefined}
      >
        <ItemList items={dashboard?.items ?? []} open={open} />
      </Card>
    </Space>
  )
}

function HistoryPage({
  archive,
  searchResult,
  searching,
  searchMeta,
  search,
  open,
}: {
  archive: ArchiveItem[]
  searchResult: ArchiveItem[]
  searching: boolean
  searchMeta: string
  search: (query: string) => Promise<void>
  open: (id: string) => void
}) {
  const [queryUsed, setQueryUsed] = useState(false)
  const [topic, setTopic] = useState<string>()
  const [tier, setTier] = useState<Tier>()
  const [source, setSource] = useState('')
  const [tag, setTag] = useState('')
  const [favorite, setFavorite] = useState<string>()
  const [read, setRead] = useState<string>()
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [minimumScore, setMinimumScore] = useState(0)
  const [sort, setSort] = useState<'PUBLISHED_DESC' | 'SCORE_DESC'>('PUBLISHED_DESC')
  const base = queryUsed ? searchResult : archive
  const filtered = useMemo(
    () => base
      .filter((item) =>
        (!topic || item.topic === topic)
        && (!tier || item.tier === tier)
        && (!source || item.source_ids.some((value) => value.toLowerCase().includes(source.toLowerCase())))
        && (!tag || item.tags.some((value) => value.toLowerCase().includes(tag.toLowerCase())))
        && (!favorite || item.favorite === (favorite === 'yes'))
        && (!read || item.read_state === read)
        && (!dateFrom || item.published_at.slice(0, 10) >= dateFrom)
        && (!dateTo || item.published_at.slice(0, 10) <= dateTo)
        && item.quality_score >= minimumScore)
      .sort((a, b) => sort === 'SCORE_DESC'
        ? b.quality_score - a.quality_score
        : b.published_at.localeCompare(a.published_at)),
    [base, topic, tier, source, tag, favorite, read, dateFrom, dateTo, minimumScore, sort],
  )
  return (
    <Card title="历史检索">
      <Space orientation="vertical" size="middle" className="full-width">
        <Input.Search
          allowClear
          enterButton={<><SearchOutlined /> 检索</>}
          loading={searching}
          placeholder="检索标题、摘要、正文、来源、标签和笔记"
          onSearch={(value) => {
            setQueryUsed(Boolean(value.trim()))
            if (value.trim()) void search(value)
          }}
        />
        <Space wrap>
          <Select allowClear placeholder="专题" className="filter-select" value={topic} onChange={setTopic} options={[...new Set(archive.map((item) => item.topic))].map((value) => ({ value }))} />
          <Select allowClear placeholder="层级" className="filter-select" value={tier} onChange={setTier} options={(Object.keys(tierLabels) as Tier[]).map((value) => ({ value, label: tierLabels[value] }))} />
          <Input placeholder="来源" value={source} onChange={(event) => setSource(event.target.value)} className="filter-input" />
          <Input placeholder="标签" value={tag} onChange={(event) => setTag(event.target.value)} className="filter-input" />
          <Select allowClear placeholder="收藏" className="filter-select" value={favorite} onChange={setFavorite} options={[{ value: 'yes', label: '已收藏' }, { value: 'no', label: '未收藏' }]} />
          <Select allowClear placeholder="阅读状态" className="filter-select" value={read} onChange={setRead} options={[{ value: 'READ', label: '已读' }, { value: 'UNREAD', label: '未读' }]} />
          <Input type="date" value={dateFrom} onChange={(event) => setDateFrom(event.target.value)} className="date-input" aria-label="开始日期" />
          <Input type="date" value={dateTo} onChange={(event) => setDateTo(event.target.value)} className="date-input" aria-label="结束日期" />
          <InputNumber min={0} max={100} value={minimumScore} onChange={(value) => setMinimumScore(value ?? 0)} addonAfter="最低分" />
          <Select value={sort} onChange={setSort} className="filter-select" options={[{ value: 'PUBLISHED_DESC', label: '按时间' }, { value: 'SCORE_DESC', label: '按评分' }]} />
        </Space>
        {searchMeta && queryUsed && <Alert type="info" showIcon title={searchMeta} />}
        <Text type="secondary">匹配 {filtered.length} 条</Text>
        <ItemList items={filtered} open={open} />
      </Space>
    </Card>
  )
}

function SourcesPage({
  sources,
  experts,
  topics,
  refresh,
  notify,
}: {
  sources: SourceRecord[]
  experts: ExpertRecord[]
  topics: string[]
  refresh: () => Promise<void>
  notify: ReturnType<typeof message.useMessage>[0]
}) {
  const [sourceOpen, setSourceOpen] = useState(false)
  const [expertOpen, setExpertOpen] = useState(false)
  const [editingSource, setEditingSource] = useState<SourceRecord | null>(null)
  const [editingExpert, setEditingExpert] = useState<ExpertRecord | null>(null)
  const [sourceForm] = Form.useForm()
  const [expertForm] = Form.useForm()

  const openSource = (value: SourceRecord | null) => {
    setEditingSource(value)
    sourceForm.setFieldsValue(value ?? {
      source_type: 'WEB', authority_level: 3, truncate_chars: 20000, topic: topics[0],
    })
    setSourceOpen(true)
  }
  const openExpert = (value: ExpertRecord | null) => {
    setEditingExpert(value)
    expertForm.setFieldsValue(value ?? { source_ids: [] })
    setExpertOpen(true)
  }
  const saveSource = async (values: Omit<SourceRecord, 'source_id' | 'state'>) => {
    await api(editingSource ? `/api/sources/${editingSource.source_id}` : '/api/sources', {
      method: editingSource ? 'PUT' : 'POST', body: JSON.stringify(values),
    })
    setSourceOpen(false)
    await refresh()
    void notify.success('来源已保存')
  }
  const saveExpert = async (values: { name: string; source_ids: string[] }) => {
    await api(editingExpert ? `/api/experts/${editingExpert.expert_id}` : '/api/experts', {
      method: editingExpert ? 'PUT' : 'POST', body: JSON.stringify(values),
    })
    setExpertOpen(false)
    await refresh()
    void notify.success('专家白名单已保存')
  }
  const setState = async (
    kind: 'sources' | 'experts', id: string, state: 'ACTIVE' | 'PAUSED',
  ) => {
    await api(`/api/${kind}/${id}/state`, { method: 'POST', body: JSON.stringify({ state }) })
    await refresh()
  }
  const remove = async (kind: 'sources' | 'experts', id: string) => {
    await api(`/api/${kind}/${id}`, { method: 'DELETE' })
    await refresh()
  }

  return (
    <Space orientation="vertical" size="large" className="full-width">
      <Card
        title="来源管理"
        extra={<Button type="primary" icon={<PlusOutlined />} onClick={() => openSource(null)}>新增来源</Button>}
      >
        <Table
          rowKey="source_id"
          dataSource={sources}
          scroll={{ x: 900 }}
          columns={[
            { title: '名称', dataIndex: 'name' },
            { title: '类型', dataIndex: 'source_type' },
            { title: '专题', dataIndex: 'topic' },
            { title: '权威等级', dataIndex: 'authority_level' },
            { title: '截断字符', dataIndex: 'truncate_chars' },
            { title: '状态', dataIndex: 'state', render: (value) => <Tag>{value}</Tag> },
            {
              title: '操作',
              render: (_, row: SourceRecord) => (
                <Space>
                  <Button icon={<EditOutlined />} onClick={() => openSource(row)}>编辑</Button>
                  <Button onClick={() => void setState('sources', row.source_id, row.state === 'ACTIVE' ? 'PAUSED' : 'ACTIVE')}>{row.state === 'ACTIVE' ? '暂停' : '恢复'}</Button>
                  <Popconfirm title="停用该来源？" onConfirm={() => void remove('sources', row.source_id)}><Button danger>删除</Button></Popconfirm>
                </Space>
              ),
            },
          ]}
        />
      </Card>
      <Card
        title="专家白名单"
        extra={<Button icon={<PlusOutlined />} onClick={() => openExpert(null)}>新增专家</Button>}
      >
        <Table
          rowKey="expert_id"
          dataSource={experts}
          columns={[
            { title: '姓名', dataIndex: 'name' },
            { title: '关联来源', dataIndex: 'source_ids', render: (value: string[]) => value.join('、') || '—' },
            { title: '状态', dataIndex: 'state', render: (value) => <Tag>{value}</Tag> },
            {
              title: '操作',
              render: (_, row: ExpertRecord) => (
                <Space>
                  <Button onClick={() => openExpert(row)}>编辑</Button>
                  <Button onClick={() => void setState('experts', row.expert_id, row.state === 'ACTIVE' ? 'PAUSED' : 'ACTIVE')}>{row.state === 'ACTIVE' ? '暂停' : '恢复'}</Button>
                  <Popconfirm title="停用该专家？" onConfirm={() => void remove('experts', row.expert_id)}><Button danger>删除</Button></Popconfirm>
                </Space>
              ),
            },
          ]}
        />
      </Card>
      <Modal
        title={editingSource ? '编辑来源' : '新增来源'}
        open={sourceOpen}
        onCancel={() => setSourceOpen(false)}
        onOk={() => sourceForm.submit()}
        destroyOnHidden
      >
        <Form form={sourceForm} layout="vertical" onFinish={(values) => void saveSource(values)}>
          <Form.Item name="name" label="名称" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="source_type" label="类型" rules={[{ required: true }]}><Select options={['WEB', 'RSS', 'GITHUB', 'VIDEO'].map((value) => ({ value }))} /></Form.Item>
          <Form.Item name="url" label="URL" rules={[{ required: true, type: 'url' }]}><Input /></Form.Item>
          <Form.Item name="topic" label="专题" rules={[{ required: true }]}><Select options={topics.map((value) => ({ value }))} /></Form.Item>
          <Form.Item name="authority_level" label="权威等级" rules={[{ required: true }]}><InputNumber min={1} max={5} /></Form.Item>
          <Form.Item name="truncate_chars" label="模型输入上限"><Select options={[10000, 20000, 50000].map((value) => ({ value }))} /></Form.Item>
        </Form>
      </Modal>
      <Modal
        title={editingExpert ? '编辑专家' : '新增专家'}
        open={expertOpen}
        onCancel={() => setExpertOpen(false)}
        onOk={() => expertForm.submit()}
        destroyOnHidden
      >
        <Form form={expertForm} layout="vertical" onFinish={(values) => void saveExpert(values)}>
          <Form.Item name="name" label="姓名" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="source_ids" label="关联来源"><Select mode="multiple" options={sources.map((item) => ({ value: item.source_id, label: item.name }))} /></Form.Item>
        </Form>
      </Modal>
    </Space>
  )
}

function QualityPage({
  feedback,
  refresh,
  notify,
}: {
  feedback: FeedbackRecord[]
  refresh: () => Promise<void>
  notify: ReturnType<typeof message.useMessage>[0]
}) {
  const [proposal, setProposal] = useState<CalibrationProposal | null>(null)
  const [rollbackVersion, setRollbackVersion] = useState<number | null>(null)
  const calibrate = async () => {
    try {
      setProposal(await api<CalibrationProposal>('/api/calibration/proposals', { method: 'POST' }))
    } catch (error) {
      void notify.error(error instanceof Error ? error.message : '校准失败')
    }
  }
  const decide = async (action: 'confirm' | 'reject') => {
    if (!proposal) return
    const id = proposal.proposal.proposal_id
    await api(`/api/calibration/${id}/${action}`, {
      method: 'POST',
      body: action === 'confirm' ? JSON.stringify({ confirmed: true }) : undefined,
    })
    setProposal(null)
    await refresh()
    void notify.success(action === 'confirm' ? '新评分版本已启用' : '建议已拒绝')
  }
  const rollback = async () => {
    if (!rollbackVersion) return
    await api(`/api/calibration/config/${rollbackVersion}/rollback`, {
      method: 'POST', body: JSON.stringify({ confirmed: true }),
    })
    void notify.success(`已回退到评分配置 v${rollbackVersion}`)
  }
  return (
    <Space orientation="vertical" size="large" className="full-width">
      <Card title="质量反馈" extra={<Button onClick={() => void calibrate()}>发起校准评估</Button>}>
        {!feedback.length ? <Empty description="尚无质量反馈" /> : (
          <Table
            rowKey="feedback_id"
            dataSource={feedback}
            columns={[
              { title: '原因', dataIndex: 'reason' },
              { title: '影响维度', dataIndex: 'affected_dimension' },
              { title: '原评分', dataIndex: 'original_score' },
              { title: '时间', dataIndex: 'created_at' },
            ]}
          />
        )}
      </Card>
      {proposal && (
        <Card
          title="评分校准建议"
          extra={<Space><Button onClick={() => void decide('reject')}>拒绝</Button><Button type="primary" onClick={() => void decide('confirm')}>确认应用</Button></Space>}
        >
          <Descriptions
            bordered
            column={1}
            items={[
              { key: 'sample', label: '样本量', children: proposal.sample_count },
              { key: 'uncertainty', label: '不确定性', children: proposal.uncertainty },
              { key: 'dimensions', label: '影响维度', children: proposal.proposal.affected_dimensions.join('、') },
              { key: 'weights', label: '建议权重', children: JSON.stringify(proposal.proposal.suggested_weights) },
              { key: 'impact', label: '预计影响', children: JSON.stringify(proposal.proposal.estimated_impact) },
            ]}
          />
        </Card>
      )}
      <Card title="评分版本回退">
        <Space>
          <InputNumber min={1} placeholder="配置版本" value={rollbackVersion} onChange={setRollbackVersion} />
          <Popconfirm title={`确认回退到 v${rollbackVersion ?? ''}？`} onConfirm={() => void rollback()} disabled={!rollbackVersion}>
            <Button disabled={!rollbackVersion}>确认回退</Button>
          </Popconfirm>
        </Space>
      </Card>
    </Space>
  )
}

function RunsPage({
  runs,
  refresh,
  notify,
}: {
  runs: PipelineRun[]
  refresh: () => Promise<void>
  notify: ReturnType<typeof message.useMessage>[0]
}) {
  const retry = async (runId: string) => {
    try {
      await api(`/api/runs/${runId}/retry`, { method: 'POST' })
      await refresh()
      void notify.success('失败阶段已重新执行')
    } catch (error) {
      void notify.error(error instanceof Error ? error.message : '重试失败')
    }
  }
  return (
    <Card title="运行记录" extra={<Button icon={<ReloadOutlined />} onClick={() => void refresh()}>刷新</Button>}>
      <Table
        rowKey="run_id"
        dataSource={runs}
        scroll={{ x: 900 }}
        columns={[
          { title: '日期', dataIndex: 'report_date' },
          { title: '触发', dataIndex: 'trigger_type' },
          { title: '状态', dataIndex: 'status', render: (value) => <Tag>{value}</Tag> },
          { title: '来源', render: (_, row: PipelineRun) => `${row.successful_sources}/${row.attempted_sources}` },
          { title: '归档', dataIndex: 'archived_count' },
          { title: '待重试', dataIndex: 'retry_count' },
          { title: '错误码', dataIndex: 'error_code', render: (value) => value || '—' },
          { title: '操作', render: (_, row: PipelineRun) => <Button disabled={!row.retry_count} onClick={() => void retry(row.run_id)}>重试失败阶段</Button> },
        ]}
      />
    </Card>
  )
}

function SettingsPage({
  settings,
  configuration,
  saved,
  failed,
}: {
  settings: AppSettings | null
  configuration: ConfigurationStatus | null
  saved: (value: AppSettings) => void
  failed: (error: Error) => void
}) {
  const [form] = Form.useForm<AppSettings>()
  const [topicOrder, setTopicOrder] = useState(settings?.topic_order ?? [])
  const move = (index: number, offset: number) => {
    const next = [...topicOrder]
    const target = index + offset
    if (target < 0 || target >= next.length) return
    ;[next[index], next[target]] = [next[target], next[index]]
    setTopicOrder(next)
  }
  const submit = (values: AppSettings) => {
    void api<AppSettings>('/api/settings', {
      method: 'PUT', body: JSON.stringify({ ...values, topic_order: topicOrder }),
    }).then(saved).catch(failed)
  }
  return (
    <Space orientation="vertical" size="large" className="full-width">
      <Card title="系统设置" extra={<Tag color="blue">本地配置</Tag>}>
        <Form form={form} initialValues={settings ?? undefined} layout="vertical" onFinish={submit}>
          <Row gutter={16}>
            <Col xs={24} md={8}><Form.Item label="每日执行时间" name="schedule_time" rules={[{ required: true }]}><Input placeholder="08:30" /></Form.Item></Col>
            <Col xs={24} md={8}><Form.Item label="入选阈值" name="selection_threshold" rules={[{ required: true }]}><InputNumber min={0} max={100} className="full-width" /></Form.Item></Col>
            <Col xs={24} md={8}><Form.Item label="默认排序" name="default_sort"><Select options={[{ value: 'PUBLISHED_DESC', label: '发布时间' }, { value: 'SCORE_DESC', label: '质量分' }]} /></Form.Item></Col>
          </Row>
          <Row gutter={16}>
            {(['MUST_READ', 'IMPORTANT', 'EXTENDED'] as Tier[]).map((tier) => (
              <Col xs={24} md={8} key={tier}>
                <Form.Item label={`${tierLabels[tier]}数量上限`} name={['tier_caps', tier]} rules={[{ required: true }]}>
                  <InputNumber min={0} max={50} className="full-width" />
                </Form.Item>
              </Col>
            ))}
          </Row>
          <Form.Item label="专题显示顺序">
            <div className="order-list">
              {topicOrder.map((topic, index) => (
                <div key={topic}>
                  <Text>{index + 1}. {topic}</Text>
                  <Space>
                    <Button aria-label={`上移${topic}`} icon={<UpOutlined />} disabled={!index} onClick={() => move(index, -1)} />
                    <Button aria-label={`下移${topic}`} icon={<DownOutlined />} disabled={index === topicOrder.length - 1} onClick={() => move(index, 1)} />
                  </Space>
                </div>
              ))}
            </div>
          </Form.Item>
          <Button type="primary" htmlType="submit">保存设置</Button>
        </Form>
      </Card>
      <Card title="服务配置状态">
        <Space wrap>
          {configuration && Object.entries(configuration).map(([key, value]) => (
            <Tag color={value ? 'green' : 'default'} key={key}>{key}: {value ? '已配置' : '未配置'}</Tag>
          ))}
        </Space>
      </Card>
    </Space>
  )
}

function TrashPage({ open, refresh }: { open: (id: string) => void; refresh: () => Promise<void> }) {
  const [items, setItems] = useState<ArchiveItem[]>([])
  const loadTrash = useCallback(
    () => api<ArchiveItem[]>('/api/archive?trash=true').then(setItems).catch(() => setItems([])),
    [],
  )
  useEffect(() => { void loadTrash() }, [loadTrash])
  return (
    <Card title="回收站">
      {!items.length ? <Empty description="回收站为空" /> : (
        <div className="simple-list">
          {items.map((item) => (
            <div className="trash-row" key={item.event_id}>
              <div><Button type="link" onClick={() => open(item.event_id)}>{item.title}</Button><br /><Text type="secondary">{item.trash_reason}</Text></div>
              <Space>
                <Button onClick={() => void api(`/api/archive/${item.event_id}/restore`, { method: 'POST' }).then(async () => { await loadTrash(); await refresh() })}>恢复</Button>
                <Popconfirm title="永久删除后不可恢复，确认删除？" onConfirm={() => void api(`/api/archive/${item.event_id}?confirmed=true`, { method: 'DELETE' }).then(async () => { await loadTrash(); await refresh() })}><Button danger>永久删除</Button></Popconfirm>
              </Space>
            </div>
          ))}
        </div>
      )}
    </Card>
  )
}

function DetailDrawer({
  detail,
  close,
  updateMetadata,
  refresh,
  notify,
}: {
  detail: ArchiveDetail
  close: () => void
  updateMetadata: (values: Record<string, unknown>) => Promise<void>
  refresh: () => Promise<void>
  notify: ReturnType<typeof message.useMessage>[0]
}) {
  const [note, setNote] = useState(detail.note)
  const [trashOpen, setTrashOpen] = useState(false)
  const [reason, setReason] = useState('')
  const [affectedDimension, setAffectedDimension] = useState(dimensions[3])
  const [expansionQuery, setExpansionQuery] = useState(detail.title)
  const [expansionStatus, setExpansionStatus] = useState('')
  const [extensionResults, setExtensionResults] = useState<ExtensionResult[]>([])
  const currentEvidence = detail.versions[0]?.evidence ?? []

  const saveNote = async () => {
    await api(`/api/archive/${detail.event_id}/note`, {
      method: 'PUT', body: JSON.stringify({ body: note }),
    })
    void notify.success('笔记已保存')
  }
  const trash = async () => {
    if (!reason.trim()) return
    if (detail.score_id) {
      await api('/api/feedback', {
        method: 'POST',
        body: JSON.stringify({
          score_id: detail.score_id,
          reason: reason.trim(),
          affected_dimension: affectedDimension,
          content_features: { event_id: detail.event_id },
          removed: true,
        }),
      })
    }
    await api(`/api/archive/${detail.event_id}/trash`, {
      method: 'POST', body: JSON.stringify({ reason: reason.trim() }),
    })
    setTrashOpen(false)
    close()
    await refresh()
  }
  const expansion = async () => {
    try {
      const result = await api<{
        status: string
        error_code: string | null
        results: ExtensionResult[]
      }>(`/api/archive/${detail.event_id}/expansion-search`, {
        method: 'POST', body: JSON.stringify({ query: expansionQuery }),
      })
      setExpansionStatus(result.error_code ?? result.status)
      setExtensionResults(result.results)
    } catch (error) {
      setExpansionStatus(error instanceof Error ? error.message : '扩展搜索失败')
    }
  }
  const favoriteExtension = async (resultId: string) => {
    try {
      await api(`/api/extension-results/${resultId}/favorite`, { method: 'POST' })
      await refresh()
      void notify.success('扩展结果已通过加工并收藏')
    } catch (error) {
      void notify.error(error instanceof Error ? error.message : '收藏失败')
    }
  }

  return (
    <Drawer size={720} open onClose={close} title={detail.title}>
      <Space orientation="vertical" size="large" className="full-width">
        <Space wrap>
          <Tag color={tierColors[detail.tier]}>{tierLabels[detail.tier]}</Tag>
          <Tag>{detail.topic}</Tag>
          <Text type="secondary">评分配置 v{detail.score_version}</Text>
        </Space>
        <Progress percent={detail.quality_score} format={(value) => `${value} 分`} />
        <Descriptions
          size="small"
          column={2}
          bordered
          items={[
            { key: 'version', label: '当前版本', children: `v${detail.version_no}` },
            { key: 'published', label: '发布时间', children: new Date(detail.published_at).toLocaleString() },
            { key: 'sources', label: '来源数', children: detail.source_ids.length },
            { key: 'hash', label: '内容校验', children: detail.content_hash.slice(0, 12) },
          ]}
        />
        <Card size="small" title="五维评分解释">
          <Descriptions size="small" column={1} items={Object.entries(detail.score_dimensions).map(([key, value]) => ({ key, label: key, children: `${value} 分` }))} />
        </Card>
        <Space wrap>
          <Text>收藏</Text><Switch checked={detail.favorite} onChange={(value) => void updateMetadata({ favorite: value })} />
          <Text>置顶</Text><Switch checked={detail.pinned} onChange={(value) => void updateMetadata({ pinned: value })} />
          <Button onClick={() => void updateMetadata({ read_state: detail.read_state === 'READ' ? 'UNREAD' : 'READ' })}>{detail.read_state === 'READ' ? '标为未读' : '标为已读'}</Button>
        </Space>
        <Tabs
          items={[
            { key: 'archive', label: '只读档案', children: <Paragraph className="archive-content">{detail.content}</Paragraph> },
            {
              key: 'versions',
              label: `版本（${detail.versions.length}）`,
              children: <Timeline items={detail.versions.map((version) => ({ children: (
                <Space orientation="vertical">
                  <Text strong>v{version.version_no} · {version.change_type}</Text>
                  <Text>{version.summary}</Text>
                  {version.source_language === 'en' && <><Text type="secondary">原文</Text><Paragraph>{version.original_text}</Paragraph><Text type="secondary">中文译文</Text><Paragraph>{version.zh_translation}</Paragraph></>}
                </Space>
              ) }))} />,
            },
            {
              key: 'evidence',
              label: '来源与观点',
              children: <div className="simple-list">{currentEvidence.map((evidence) => <div key={evidence.evidence_id}><Space orientation="vertical"><a href={evidence.url} target="_blank" rel="noreferrer">{evidence.source_id}</a><Text>{evidence.viewpoint}</Text></Space></div>)}</div>,
            },
          ]}
        />
        {detail.topic_idea && (
          <Card title="选题建议">
            <Title level={4}>{detail.topic_idea.title}</Title>
            <Paragraph>{detail.topic_idea.hook}</Paragraph>
            <ol>{detail.topic_idea.outline.map((item) => <li key={item}>{item}</li>)}</ol>
          </Card>
        )}
        <Card title="扩展搜索">
          <Space.Compact className="full-width">
            <Input value={expansionQuery} onChange={(event) => setExpansionQuery(event.target.value)} />
            <Button type="primary" onClick={() => void expansion()}>搜索互联网</Button>
          </Space.Compact>
          {expansionStatus && (
            <Alert
              className="section-alert"
              showIcon
              type={expansionStatus === 'SUCCEEDED' ? 'success' : 'warning'}
              title={expansionStatus}
              action={expansionStatus !== 'SUCCEEDED' ? <Button size="small" onClick={() => void expansion()}>重试</Button> : undefined}
            />
          )}
          {extensionResults.map((item) => (
            <Card
              size="small"
              key={item.result_id}
              title={<a href={item.url} target="_blank" rel="noreferrer">{item.title}</a>}
              extra={<Button onClick={() => void favoriteExtension(item.result_id)}>收藏并归档</Button>}
            >
              <Paragraph>{item.summary}</Paragraph>
              <Text type="secondary">{item.source_name} · 外部相关度 {item.score}</Text>
            </Card>
          ))}
        </Card>
        <Divider />
        <div>
          <Text strong>个人笔记</Text>
          <Input.TextArea value={note} rows={4} maxLength={20000} onChange={(event) => setNote(event.target.value)} />
          <Button className="note-save" onClick={() => void saveNote()}>保存笔记</Button>
        </div>
        <Button danger icon={<DeleteOutlined />} onClick={() => setTrashOpen(true)}>剔除并移入回收站</Button>
        <Modal
          title="填写剔除原因"
          open={trashOpen}
          onCancel={() => setTrashOpen(false)}
          onOk={() => void trash()}
          okButtonProps={{ disabled: !reason.trim() }}
        >
          <Form layout="vertical">
            <Form.Item label="原因" required><Input.TextArea value={reason} maxLength={500} rows={4} onChange={(event) => setReason(event.target.value)} placeholder="请说明内容质量问题" /></Form.Item>
            <Form.Item label="主要影响维度"><Select value={affectedDimension} onChange={setAffectedDimension} options={dimensions.map((value) => ({ value }))} /></Form.Item>
          </Form>
        </Modal>
      </Space>
    </Drawer>
  )
}
