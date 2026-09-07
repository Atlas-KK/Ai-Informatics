import { Alert, Button, Card, Empty, Input, Space, Tag, Typography } from 'antd'
import { useRef, useState } from 'react'
import { api } from '../../../api'
import { ConfirmAction } from '../../../components'
import type {
  ExpansionSearchResponse,
  ExtensionFavoriteResponse,
  ExtensionResult,
} from '../../../types'

const { Paragraph, Text } = Typography

const statusMessages: Record<string, string> = {
  EXPANSION_PROVIDER_NOT_CONFIGURED: '扩展搜索服务未配置；原情报未发生变化。',
  EXPANSION_SEARCH_FAILED: '扩展搜索失败；原情报未发生变化。',
}

export function ExpansionSearchPanel({ eventId, initialQuery }: { eventId: string; initialQuery: string }) {
  const [query, setQuery] = useState(initialQuery)
  const [searching, setSearching] = useState(false)
  const [searchError, setSearchError] = useState('')
  const [searched, setSearched] = useState(false)
  const [results, setResults] = useState<ExtensionResult[]>([])
  const [saving, setSaving] = useState<string | null>(null)
  const [resultErrors, setResultErrors] = useState<Record<string, string>>({})
  const [outcomes, setOutcomes] = useState<Record<string, ExtensionFavoriteResponse>>({})
  const searchRequestId = useRef(0)

  const search = async () => {
    if (!query.trim()) return
    const requestId = searchRequestId.current + 1
    searchRequestId.current = requestId
    setSearching(true)
    setSearchError('')
    setSearched(true)
    try {
      const response = await api<ExpansionSearchResponse>(`/api/archive/${eventId}/expansion-search`, {
        method: 'POST', body: JSON.stringify({ query: query.trim() }),
      })
      if (requestId !== searchRequestId.current) return
      setResults(response.results)
      if (response.status !== 'SUCCEEDED') {
        setSearchError(statusMessages[response.error_code ?? ''] ?? '扩展搜索失败；原情报未发生变化。')
      }
    } catch (reason) {
      if (requestId !== searchRequestId.current) return
      setResults([])
      setSearchError(reason instanceof Error ? reason.message : '扩展搜索失败；原情报未发生变化。')
    } finally {
      if (requestId === searchRequestId.current) setSearching(false)
    }
  }

  const favorite = async (resultId: string) => {
    setSaving(resultId)
    setResultErrors((current) => ({ ...current, [resultId]: '' }))
    try {
      const outcome = await api<ExtensionFavoriteResponse>(`/api/extension-results/${resultId}/favorite`, {
        method: 'POST',
      })
      setOutcomes((current) => ({ ...current, [resultId]: outcome }))
    } catch (reason) {
      setResultErrors((current) => ({
        ...current,
        [resultId]: reason instanceof Error ? reason.message : '收藏归档失败，请重试',
      }))
    } finally {
      setSaving(null)
    }
  }

  return (
    <Card title="扩展搜索" extra={<Tag color="orange">临时结果</Tag>}>
      <Alert
        showIcon
        type="info"
        title="搜索结果不会自动入库"
        description="只有经过确认收藏、正式加工和去重门禁后，结果才会进入档案。"
      />
      <Space.Compact className="full-width expansion-search-input">
        <Input aria-label="扩展搜索关键词" disabled={searching} value={query} maxLength={500} onPressEnter={() => void search()} onChange={(event) => setQuery(event.target.value)} />
        <Button type="primary" loading={searching} disabled={!query.trim()} onClick={() => void search()}>
          扩展搜索
        </Button>
      </Space.Compact>
      {searchError && (
        <Alert
          className="section-alert"
          showIcon
          type="error"
          title="搜索未完成"
          description={searchError}
          action={<Button onClick={() => void search()}>重试搜索</Button>}
        />
      )}
      {searched && !searching && !searchError && results.length === 0 && <Empty description="没有找到扩展结果" />}
      <Space orientation="vertical" size="middle" className="full-width extension-results">
        {results.map((item) => {
          const outcome = outcomes[item.result_id]
          const error = resultErrors[item.result_id]
          return (
            <Card
              size="small"
              key={item.result_id}
              title={<a href={item.url} target="_blank" rel="noreferrer">{item.title}</a>}
              extra={outcome ? <Tag color="green">已归档</Tag> : (
                <ConfirmAction
                  title="确认收藏并归档？"
                  description="系统将执行正式加工和去重；取消不会写入档案。"
                  disabled={saving !== null}
                  onConfirm={() => favorite(item.result_id)}
                >
                  <Button loading={saving === item.result_id} disabled={saving !== null}>收藏并归档</Button>
                </ConfirmAction>
              )}
            >
              <Paragraph>{item.summary}</Paragraph>
              <Text type="secondary">{item.source_name} · 外部相关度 {item.score} · 临时结果</Text>
              {outcome && (
                <Alert
                  className="section-alert"
                  showIcon
                  type="success"
                  title={outcome.deduplicated ? '已关联已有情报' : '已新建正式情报'}
                  description={`事件 ID：${outcome.event_id}`}
                />
              )}
              {error && (
                <Alert
                  className="section-alert"
                  showIcon
                  type="error"
                  title="收藏归档失败"
                  description={error}
                  action={<Button disabled={saving !== null} onClick={() => void favorite(item.result_id)}>重试归档</Button>}
                />
              )}
            </Card>
          )
        })}
      </Space>
    </Card>
  )
}
