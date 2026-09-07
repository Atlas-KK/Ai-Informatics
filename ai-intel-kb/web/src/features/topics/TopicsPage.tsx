import { Card, Pagination, Select, Space, Tabs, Tag, Typography } from 'antd'
import { useEffect, useMemo, useState } from 'react'
import { api } from '../../api'
import { tierLabels } from '../../app/labels'
import { AsyncStateView, IntelList, PageHeader } from '../../components'
import { buildBrowsePath } from '../../services/browse'
import type { ArchivePageResponse } from '../../services/contracts'
import type { Tier, TopicSummary } from '../../types'

const { Text } = Typography
const pageSize = 20

interface TopicsPageProps {
  topics: TopicSummary[]
  initialTopic: string | null
  onOpen: (id: string) => void
}

export function TopicsPage({ topics, initialTopic, onOpen }: TopicsPageProps) {
  const defaultTopic = initialTopic && topics.some((topic) => topic.name === initialTopic)
    ? initialTopic
    : topics[0]?.name
  const [activeTopic, setActiveTopic] = useState(defaultTopic)
  const [tier, setTier] = useState<Tier>()
  const [tag, setTag] = useState<string>()
  const [sort, setSort] = useState<'TIER_PRIORITY' | 'PUBLISHED_DESC' | 'SCORE_DESC'>('TIER_PRIORITY')
  const [page, setPage] = useState(1)
  const [reloadKey, setReloadKey] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [result, setResult] = useState<ArchivePageResponse>({ items: [], total: 0, page: 1, page_size: pageSize })

  useEffect(() => {
    if (!activeTopic) return
    const controller = new AbortController()
    const path = buildBrowsePath({
      query: '',
      topic: activeTopic,
      tier,
      source: '',
      tag: tag ?? '',
      dateFrom: '',
      dateTo: '',
      minimumScore: 0,
      sort,
    }, page, pageSize)
    void api<ArchivePageResponse>(path, { signal: controller.signal })
      .then(setResult)
      .catch((reason: unknown) => {
        if (reason instanceof DOMException && reason.name === 'AbortError') return
        setError(reason instanceof Error ? reason.message : '专题情报加载失败')
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false)
      })
    return () => controller.abort()
  }, [activeTopic, page, reloadKey, sort, tag, tier])

  const summary = topics.find((topic) => topic.name === activeTopic)
  const tagOptions = useMemo(
    () => (summary?.tags ?? []).map((item) => ({ value: item.name, label: `${item.name}（${item.count}）` })),
    [summary],
  )

  return (
    <Space orientation="vertical" size="large" className="full-width">
      <PageHeader title="专题档案" description="按四个一级专题、二级标签和情报层级浏览正式档案" />
      <Card>
        <Tabs
          activeKey={activeTopic}
          onChange={(value) => {
            setLoading(true)
            setError('')
            setActiveTopic(value)
            setTier(undefined)
            setTag(undefined)
            setPage(1)
          }}
          items={topics.map((topic) => ({
            key: topic.name,
            label: <span>{topic.name} <Tag>{topic.count}</Tag></span>,
          }))}
        />
        <div className="browse-toolbar">
          <Space wrap>
            <Select<Tier>
              allowClear
              aria-label="按层级筛选"
              placeholder="全部层级"
              value={tier}
              onChange={(value) => {
                setLoading(true)
                setError('')
                setTier(value)
                setPage(1)
              }}
              options={(Object.keys(tierLabels) as Tier[]).map((value) => ({ value, label: tierLabels[value] }))}
            />
            <Select<string>
              allowClear
              aria-label="按二级标签筛选"
              placeholder="全部二级标签"
              value={tag}
              onChange={(value) => {
                setLoading(true)
                setError('')
                setTag(value)
                setPage(1)
              }}
              options={tagOptions}
              className="tag-filter"
            />
            <Select
              aria-label="专题排序"
              value={sort}
              onChange={(value) => {
                setLoading(true)
                setError('')
                setSort(value)
                setPage(1)
              }}
              options={[
                { value: 'TIER_PRIORITY', label: '按层级优先' },
                { value: 'PUBLISHED_DESC', label: '按发布时间' },
                { value: 'SCORE_DESC', label: '按质量分' },
              ]}
              className="sort-filter"
            />
          </Space>
          <Text type="secondary">{summary?.count ?? 0} 条正式情报</Text>
        </div>
        <AsyncStateView
          state={!activeTopic ? 'empty' : loading ? 'loading' : error ? 'error' : result.total ? 'success' : 'empty'}
          errorTitle="专题情报加载失败"
          description={error}
          emptyTitle="当前专题和筛选条件下暂无情报"
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
      </Card>
    </Space>
  )
}
