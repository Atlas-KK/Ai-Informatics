import { ReloadOutlined, SearchOutlined } from '@ant-design/icons'
import {
  Alert,
  Button,
  Card,
  Input,
  InputNumber,
  Pagination,
  Select,
  Space,
  Typography,
} from 'antd'
import { useEffect, useState } from 'react'
import { api } from '../../api'
import { tierLabels } from '../../app/labels'
import { AsyncStateView, IntelList, PageHeader } from '../../components'
import { buildBrowsePath, emptyBrowseFilters } from '../../services/browse'
import type {
  ArchivePageResponse,
  BrowseFilters,
  BrowseSort,
  SearchPageResponse,
} from '../../services/contracts'
import type { Tier, TopicSummary } from '../../types'

const { Text } = Typography
const pageSize = 20

interface HistorySearchPageProps {
  topics: TopicSummary[]
  onOpen: (id: string) => void
}

interface SearchMeta {
  mode: 'KEYWORD' | 'HYBRID' | null
  degraded: boolean
  degradedReason: string | null
}

export function HistorySearchPage({ topics, onOpen }: HistorySearchPageProps) {
  const [draft, setDraft] = useState<BrowseFilters>({ ...emptyBrowseFilters })
  const [applied, setApplied] = useState<BrowseFilters>({ ...emptyBrowseFilters })
  const [page, setPage] = useState(1)
  const [reloadKey, setReloadKey] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [result, setResult] = useState<ArchivePageResponse>({ items: [], total: 0, page: 1, page_size: pageSize })
  const [meta, setMeta] = useState<SearchMeta>({ mode: null, degraded: false, degradedReason: null })

  useEffect(() => {
    const controller = new AbortController()
    const path = buildBrowsePath(applied, page, pageSize)
    void api<ArchivePageResponse | SearchPageResponse>(path, { signal: controller.signal })
      .then((response) => {
        setResult(response)
        if ('mode' in response) {
          setMeta({
            mode: response.mode,
            degraded: response.degraded,
            degradedReason: response.degraded_reason,
          })
        } else {
          setMeta({ mode: null, degraded: false, degradedReason: null })
        }
      })
      .catch((reason: unknown) => {
        if (reason instanceof DOMException && reason.name === 'AbortError') return
        setError(reason instanceof Error ? reason.message : '历史情报加载失败')
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false)
      })
    return () => controller.abort()
  }, [applied, page, reloadKey])

  const updateDraft = <Key extends keyof BrowseFilters>(key: Key, value: BrowseFilters[Key]) => {
    setDraft((current) => ({ ...current, [key]: value }))
  }
  const applyFilters = () => {
    setLoading(true)
    setError('')
    setApplied({ ...draft })
    setPage(1)
  }
  const clearFilters = () => {
    const cleared = { ...emptyBrowseFilters }
    setLoading(true)
    setError('')
    setDraft(cleared)
    setApplied(cleared)
    setPage(1)
  }

  return (
    <Space orientation="vertical" size="large" className="full-width">
      <PageHeader title="历史检索" description="检索正式档案；筛选、排序和分页均由本地服务端执行" />
      <Card>
        <Space orientation="vertical" size="middle" className="full-width">
          <Input.Search
            allowClear
            enterButton={<><SearchOutlined aria-hidden /> 检索</>}
            loading={loading}
            value={draft.query}
            placeholder="检索标题、摘要、正文、来源、标签和笔记"
            onChange={(event) => updateDraft('query', event.target.value)}
            onSearch={applyFilters}
          />
          <div className="search-filters" aria-label="历史情报筛选条件">
            <Select
              allowClear
              placeholder="专题"
              aria-label="筛选专题"
              value={draft.topic}
              onChange={(value) => updateDraft('topic', value)}
              options={topics.map((topic) => ({ value: topic.name, label: topic.name }))}
            />
            <Select<Tier>
              allowClear
              placeholder="层级"
              aria-label="筛选层级"
              value={draft.tier}
              onChange={(value) => updateDraft('tier', value)}
              options={(Object.keys(tierLabels) as Tier[]).map((value) => ({ value, label: tierLabels[value] }))}
            />
            <Input placeholder="来源 ID" aria-label="筛选来源" value={draft.source} onChange={(event) => updateDraft('source', event.target.value)} />
            <Input placeholder="二级标签" aria-label="筛选标签" value={draft.tag} onChange={(event) => updateDraft('tag', event.target.value)} />
            <Select
              allowClear
              placeholder="收藏状态"
              aria-label="筛选收藏状态"
              value={draft.favorite}
              onChange={(value) => updateDraft('favorite', value)}
              options={[{ value: true, label: '已收藏' }, { value: false, label: '未收藏' }]}
            />
            <Select
              allowClear
              placeholder="阅读状态"
              aria-label="筛选阅读状态"
              value={draft.readState}
              onChange={(value) => updateDraft('readState', value)}
              options={[{ value: 'READ', label: '已读' }, { value: 'UNREAD', label: '未读' }]}
            />
            <Input type="date" aria-label="开始日期" value={draft.dateFrom} onChange={(event) => updateDraft('dateFrom', event.target.value)} />
            <Input type="date" aria-label="结束日期" value={draft.dateTo} onChange={(event) => updateDraft('dateTo', event.target.value)} />
            <InputNumber
              min={0}
              max={100}
              aria-label="最低评分"
              placeholder="最低分"
              value={draft.minimumScore}
              onChange={(value) => updateDraft('minimumScore', value ?? 0)}
            />
            <Select<BrowseSort>
              aria-label="结果排序"
              value={draft.sort}
              onChange={(value) => updateDraft('sort', value)}
              options={[
                { value: 'RELEVANCE', label: '按相关度' },
                { value: 'PUBLISHED_DESC', label: '按发布时间' },
                { value: 'SCORE_DESC', label: '按质量分' },
                { value: 'TIER_PRIORITY', label: '按层级优先' },
              ]}
            />
          </div>
          <Space wrap>
            <Button type="primary" icon={<SearchOutlined aria-hidden />} onClick={applyFilters}>应用筛选</Button>
            <Button icon={<ReloadOutlined aria-hidden />} onClick={clearFilters}>清空条件</Button>
          </Space>
          {meta.mode && applied.query && (
            <Alert
              type={meta.degraded ? 'warning' : 'info'}
              showIcon
              title={meta.degraded ? '当前使用关键词检索' : '关键词与语义融合检索'}
              description={meta.degraded
                ? `语义检索未配置，已自动降级且仍保留全部筛选条件。${meta.degradedReason ? ` 原因：${meta.degradedReason}` : ''}`
                : undefined}
            />
          )}
          {!loading && !error && <Text type="secondary">匹配 {result.total} 条</Text>}
          <AsyncStateView
            state={loading ? 'loading' : error ? 'error' : result.total ? 'success' : 'empty'}
            errorTitle="历史检索失败"
            description={error}
            emptyTitle="没有匹配的历史情报，可调整或清空筛选条件"
            onRetry={() => {
              setLoading(true)
              setError('')
              setReloadKey((value) => value + 1)
            }}
          >
            <IntelList items={result.items} onOpen={onOpen} />
            {result.total > pageSize && (
              <Pagination
                className="browse-pagination"
                current={page}
                pageSize={pageSize}
                total={result.total}
                showSizeChanger={false}
                showTotal={(total) => `共 ${total} 条`}
                onChange={(value) => {
                  setLoading(true)
                  setError('')
                  setPage(value)
                }}
              />
            )}
          </AsyncStateView>
        </Space>
      </Card>
    </Space>
  )
}
