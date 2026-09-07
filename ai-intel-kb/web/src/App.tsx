import {
  Alert,
  Button,
  Card,
  message,
  Space,
  Typography,
} from 'antd'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { api } from './api'
import { AppShell } from './app/AppShell'
import { initialViewState, type AppPage, type ViewState } from './app/viewState'
import { AsyncStateView, ConfirmAction, type AsyncState } from './components'
import { DashboardPage } from './features/dashboard/DashboardPage'
import { HistorySearchPage } from './features/search/HistorySearchPage'
import { IntelDetailPage } from './features/intel-detail/IntelDetailPage'
import { TopicsPage } from './features/topics/TopicsPage'
import { SourcesPage } from './features/sources/SourcesPage'
import { SettingsPage } from './features/settings/SettingsPage'
import { QualityPage } from './features/quality/QualityPage'
import { RunsPage } from './features/runs/RunsPage'
import type {
  AppSettings,
  ArchiveDetail,
  ArchiveItem,
  ConfigurationStatus,
  DashboardData,
  ExpertRecord,
  FeedbackRecord,
  PipelineRun,
  SourceRecord,
} from './types'

const { Text } = Typography

type BootstrapResource = 'sources' | 'experts' | 'runs' | 'feedback' | 'settings' | 'configuration'

const bootstrapResourceLabels: Record<BootstrapResource, string> = {
  sources: '来源配置',
  experts: '专家配置',
  runs: '运行记录',
  feedback: '反馈与质量数据',
  settings: '系统设置',
  configuration: '服务配置状态',
}

function errorMessage(error: unknown, fallback: string) {
  return error instanceof Error ? error.message : fallback
}

export default function App() {
  const [view, setView] = useState<ViewState>(initialViewState)
  const [loading, setLoading] = useState(true)
  const [connectionError, setConnectionError] = useState('')
  const [resourceErrors, setResourceErrors] = useState<Partial<Record<BootstrapResource, string>>>({})
  const [dashboard, setDashboard] = useState<DashboardData | null>(null)
  const [sources, setSources] = useState<SourceRecord[]>([])
  const [experts, setExperts] = useState<ExpertRecord[]>([])
  const [runs, setRuns] = useState<PipelineRun[]>([])
  const [feedback, setFeedback] = useState<FeedbackRecord[]>([])
  const [settings, setSettings] = useState<AppSettings | null>(null)
  const [configuration, setConfiguration] = useState<ConfigurationStatus | null>(null)
  const [detail, setDetail] = useState<ArchiveDetail | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [detailError, setDetailError] = useState('')
  const detailRequestId = useRef(0)
  const [messageApi, contextHolder] = message.useMessage()

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const results = await Promise.allSettled([
        api<DashboardData>('/api/dashboard'),
        api<SourceRecord[]>('/api/sources'),
        api<ExpertRecord[]>('/api/experts'),
        api<PipelineRun[]>('/api/runs'),
        api<FeedbackRecord[]>('/api/feedback'),
        api<AppSettings>('/api/settings'),
        api<ConfigurationStatus>('/api/configuration-status'),
      ])

      const nextErrors: Partial<Record<BootstrapResource, string>> = {}
      const applyResult = <T,>(
        result: PromiseSettledResult<T>,
        resource: BootstrapResource,
        apply: (value: T) => void,
      ) => {
        if (result.status === 'fulfilled') apply(result.value)
        else nextErrors[resource] = errorMessage(result.reason, `${bootstrapResourceLabels[resource]}加载失败`)
      }

      applyResult(results[1], 'sources', setSources)
      applyResult(results[2], 'experts', setExperts)
      applyResult(results[3], 'runs', setRuns)
      applyResult(results[4], 'feedback', setFeedback)
      applyResult(results[5], 'settings', setSettings)
      applyResult(results[6], 'configuration', setConfiguration)
      setResourceErrors(nextErrors)

      if (results[0].status === 'fulfilled') {
        setDashboard(results[0].value)
        setConnectionError('')
      } else {
        setConnectionError(errorMessage(results[0].reason, '无法连接本地服务'))
      }
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    const timer = window.setTimeout(() => void load(), 0)
    return () => window.clearTimeout(timer)
  }, [load])

  const openDetail = async (eventId: string) => {
    const requestId = ++detailRequestId.current
    setView((current) => ({ ...current, detailEventId: eventId }))
    setDetailLoading(true)
    setDetailError('')
    try {
      const nextDetail = await api<ArchiveDetail>(`/api/archive/${eventId}`)
      if (requestId !== detailRequestId.current) return
      setDetail(nextDetail)
    } catch (error) {
      if (requestId !== detailRequestId.current) return
      setDetail(null)
      setDetailError(error instanceof Error ? error.message : '详情加载失败')
    } finally {
      if (requestId === detailRequestId.current) setDetailLoading(false)
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

  const topicSummaries = useMemo(
    () => dashboard?.topic_summaries
      ?? (settings?.topic_order ?? []).map((name) => ({ name, count: 0, tags: [] })),
    [dashboard, settings],
  )

  const renderPage = () => {
    if (connectionError) {
      return (
        <AsyncStateView
          state="error"
          errorTitle="本地 API 未连接"
          description={`${connectionError}。请确认服务仅监听 127.0.0.1:8000。`}
          onRetry={() => void load()}
        />
      )
    }
    if (loading && !dashboard) {
      return <AsyncStateView state="loading" description="正在加载本地情报数据" />
    }
    if (view.detailEventId) {
      if (detailLoading) return <AsyncStateView state="loading" description="正在加载情报详情" />
      if (detailError) {
        return (
          <AsyncStateView
            state="error"
            errorTitle="情报详情加载失败"
            description={detailError}
            onRetry={() => void openDetail(view.detailEventId as string)}
          />
        )
      }
      if (detail) {
        return (
          <IntelDetailPage
            key={detail.event_id}
            detail={detail}
            close={() => {
              detailRequestId.current += 1
              setDetail(null)
              setView((current) => ({ ...current, detailEventId: null }))
            }}
            updateMetadata={updateMetadata}
            refresh={load}
            notify={messageApi}
          />
        )
      }
    }
    if (view.page === 'today') {
      return (
        <DashboardPage
          dashboard={dashboard}
          onOpen={openDetail}
          onSelectTopic={(topic) => setView({ page: 'topics', detailEventId: null, selectedTopic: topic })}
        />
      )
    }
    if (view.page === 'topics') {
      return <TopicsPage topics={topicSummaries} initialTopic={view.selectedTopic} onOpen={openDetail} />
    }
    if (view.page === 'history') {
      return <HistorySearchPage topics={topicSummaries} onOpen={openDetail} />
    }
    if (view.page === 'sources') {
      if (resourceErrors.sources) {
        return <ResourceError title="来源配置加载失败" description={resourceErrors.sources} retry={load} />
      }
      if (!settings) {
        return resourceErrors.settings
          ? <ResourceError title="系统设置加载失败" description={resourceErrors.settings} retry={load} />
          : <AsyncStateView state="loading" description="正在加载来源配置" />
      }
      return (
        <SourcesPage
          sources={sources}
          experts={experts}
          settings={settings}
          refresh={load}
          settingsSaved={setSettings}
          notify={messageApi}
        />
      )
    }
    if (view.page === 'quality') {
      if (resourceErrors.feedback) {
        return <ResourceError title="反馈与质量数据加载失败" description={resourceErrors.feedback} retry={load} />
      }
      return <QualityPage feedback={feedback} refresh={load} notify={messageApi} />
    }
    if (view.page === 'runs') {
      if (resourceErrors.runs) {
        return <ResourceError title="运行记录加载失败" description={resourceErrors.runs} retry={load} />
      }
      return <RunsPage runs={runs} refresh={load} notify={messageApi} />
    }
    if (view.page === 'settings') {
      if (!settings) {
        return resourceErrors.settings
          ? <ResourceError title="系统设置加载失败" description={resourceErrors.settings} retry={load} />
          : <AsyncStateView state="loading" description="正在加载系统设置" />
      }
      return (
        <SettingsPage
          settings={settings}
          configuration={configuration}
          saved={(value) => {
            setSettings(value)
            void messageApi.success('设置已保存')
          }}
          failed={(error) => void messageApi.error(error.message)}
          openQuality={() => setView({ page: 'quality', detailEventId: null, selectedTopic: null })}
        />
      )
    }
    return <TrashPage open={openDetail} refresh={load} />
  }

  return (
    <>
      {contextHolder}
      <AppShell
        activePage={view.page}
        busy={loading}
        onNavigate={(page: AppPage) => {
          detailRequestId.current += 1
          setView({ page, detailEventId: null, selectedTopic: null })
          setDetail(null)
        }}
      >
        {!connectionError && Object.keys(resourceErrors).length > 0 ? (
          <AsyncStateView
            state="partial"
            description={`无法加载：${Object.keys(resourceErrors)
              .map((key) => bootstrapResourceLabels[key as BootstrapResource])
              .join('、')}。其他已成功加载的内容仍可使用。`}
          >
            {renderPage()}
          </AsyncStateView>
        ) : renderPage()}
      </AppShell>
    </>
  )
}

function ResourceError({ title, description, retry }: {
  title: string
  description: string
  retry: () => Promise<void>
}) {
  return (
    <AsyncStateView
      state="error"
      errorTitle={title}
      description={description}
      onRetry={() => void retry()}
    />
  )
}

function TrashPage({ open, refresh }: { open: (id: string) => void; refresh: () => Promise<void> }) {
  const [items, setItems] = useState<ArchiveItem[]>([])
  const [state, setState] = useState<AsyncState>('loading')
  const [loadError, setLoadError] = useState('')
  const [actionError, setActionError] = useState('')
  const [pendingAction, setPendingAction] = useState('')
  const loadTrash = useCallback(async () => {
    setState('loading')
    setLoadError('')
    try {
      const nextItems = await api<ArchiveItem[]>('/api/archive?trash=true')
      setItems(nextItems)
      setState(nextItems.length > 0 ? 'success' : 'empty')
    } catch (error) {
      setLoadError(errorMessage(error, '回收站加载失败'))
      setState('error')
    }
  }, [])

  const runAction = async (item: ArchiveItem, action: 'restore' | 'delete') => {
    const actionKey = `${item.event_id}:${action}`
    setPendingAction(actionKey)
    setActionError('')
    try {
      if (action === 'restore') {
        await api(`/api/archive/${item.event_id}/restore`, { method: 'POST' })
      } else {
        await api(`/api/archive/${item.event_id}?confirmed=true`, { method: 'DELETE' })
      }
      await loadTrash()
      await refresh()
    } catch (error) {
      const label = action === 'restore' ? '恢复' : '永久删除'
      setActionError(`${label}“${item.title}”失败：${errorMessage(error, '请求失败')}`)
    } finally {
      setPendingAction('')
    }
  }

  useEffect(() => { void loadTrash() }, [loadTrash])
  return (
    <Card title="回收站">
      {actionError && (
        <Alert
          className="section-alert"
          type="error"
          showIcon
          title="操作未完成"
          description={actionError}
          closable
          onClose={() => setActionError('')}
        />
      )}
      <AsyncStateView
        state={state}
        emptyTitle="回收站为空"
        errorTitle="回收站加载失败"
        description={loadError || '正在加载回收站'}
        onRetry={() => void loadTrash()}
      >
        <div className="simple-list">
          {items.map((item) => (
            <div className="trash-row" key={item.event_id}>
              <div><Button type="link" onClick={() => open(item.event_id)}>{item.title}</Button><br /><Text type="secondary">{item.trash_reason}</Text></div>
              <Space>
                <Button
                  loading={pendingAction === `${item.event_id}:restore`}
                  disabled={Boolean(pendingAction)}
                  onClick={() => void runAction(item, 'restore')}
                >恢复</Button>
                <ConfirmAction
                  title="永久删除后不可恢复，确认删除？"
                  disabled={Boolean(pendingAction)}
                  onConfirm={() => runAction(item, 'delete')}
                >
                  <Button
                    danger
                    loading={pendingAction === `${item.event_id}:delete`}
                    disabled={Boolean(pendingAction)}
                  >永久删除</Button>
                </ConfirmAction>
              </Space>
            </div>
          ))}
        </div>
      </AsyncStateView>
    </Card>
  )
}
