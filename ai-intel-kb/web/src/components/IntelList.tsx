import { Empty, Space, Tag, Typography } from 'antd'
import { StarFilled } from '@ant-design/icons'
import { tierColors, tierLabels } from '../app/labels'
import type { ArchiveItem } from '../types'

const { Text } = Typography

interface IntelListProps {
  items: ArchiveItem[]
  onOpen: (id: string) => void
  emptyDescription?: string
}

export function IntelList({ items, onOpen, emptyDescription = '当前条件下暂无情报' }: IntelListProps) {
  if (!items.length) return <Empty description={emptyDescription} />
  return (
    <div className="intel-list">
      {items.map((item) => (
        <button
          type="button"
          key={item.event_id}
          onClick={() => onOpen(item.event_id)}
          className="intel-list-item"
          aria-label={`查看情报：${item.title}`}
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
