import { Alert, Button, Card, Space, Tag, Typography } from 'antd'
import { useMemo, useState } from 'react'
import { api } from '../../../api'
import type { ArchiveDetail, TopicIdea, TopicIdeaGenerationResponse } from '../../../types'

const { Text, Title } = Typography

export function TopicIdeaPanel({ detail }: { detail: ArchiveDetail }) {
  const [idea, setIdea] = useState<TopicIdea | null>(detail.topic_idea)
  const [generating, setGenerating] = useState(false)
  const [error, setError] = useState('')
  const evidence = useMemo(
    () => new Map(detail.versions.flatMap((version) => version.evidence).map((item) => [item.evidence_id, item])),
    [detail.versions],
  )

  const generate = async () => {
    setGenerating(true)
    setError('')
    try {
      const result = await api<TopicIdeaGenerationResponse>(`/api/archive/${detail.event_id}/topic-idea`, {
        method: 'POST',
      })
      setIdea(result.idea)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '选题建议生成失败，请重试')
    } finally {
      setGenerating(false)
    }
  }

  if (!idea) {
    return (
      <Alert
        showIcon
        type={error ? 'error' : 'info'}
        title={error ? '选题建议生成失败' : '当前情报尚未生成选题建议'}
        description={error || '必读情报会自动生成；重要和扩展情报可在这里手动生成。'}
        action={<Button loading={generating} onClick={() => void generate()}>{error ? '重试生成' : '生成选题建议'}</Button>}
      />
    )
  }

  return (
    <Card
      title="选题建议"
      extra={<Tag color={idea.trigger === 'MANUAL' ? 'blue' : 'green'}>{idea.trigger === 'MANUAL' ? '手动生成' : '自动生成'}</Tag>}
    >
      <Title level={3}>{idea.title}</Title>
      <Alert type="info" title="核心爆点" description={idea.hook} />
      <Title level={5}>内容大纲</Title>
      <ol>{idea.outline.map((item) => <li key={item}>{item}</li>)}</ol>
      <Title level={5}>支撑来源</Title>
      <Space orientation="vertical" size="small">
        {(idea.support_sources ?? []).map((source) => (
          <a key={source.evidence_id} href={source.url} target="_blank" rel="noreferrer">{source.source_name} · {source.viewpoint}</a>
        ))}
        {!idea.support_sources && idea.support_evidence_ids.map((evidenceId) => {
          const source = evidence.get(evidenceId)
          return source
            ? <a key={evidenceId} href={source.url} target="_blank" rel="noreferrer">{source.source_name} · {source.viewpoint}</a>
            : <Text key={evidenceId} type="secondary">证据 {evidenceId}（来源信息未提供）</Text>
        })}
        {!idea.support_evidence_ids.length && <Text type="secondary">未提供支撑来源</Text>}
      </Space>
    </Card>
  )
}
