import { render, screen, waitFor } from '@testing-library/react'
import { ConfigProvider } from 'antd'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { ArchiveItem, TopicSummary } from '../../types'
import { TopicsPage } from './TopicsPage'

const topics: TopicSummary[] = [
  { name: '大模型与智能体', count: 1, tags: [{ name: '智能体', count: 1 }] },
  { name: 'AI基础设施与算力', count: 0, tags: [] },
  { name: 'AI应用与商业化', count: 0, tags: [] },
  { name: '政策、资本与产业', count: 0, tags: [] },
]

const item: ArchiveItem = {
  event_id: 'event-topic-1',
  version_no: 1,
  change_type: 'NEW',
  title: 'Agent Platform launch',
  topic: '大模型与智能体',
  summary: '产品情报摘要',
  content: '正文',
  content_hash: 'b'.repeat(64),
  score_id: 'score-topic-1',
  quality_score: 91,
  score_version: 1,
  score_dimensions: {},
  tier: 'MUST_READ',
  published_at: '2026-09-04T01:00:00Z',
  source_ids: ['source-primary'],
  favorite: false,
  pinned: false,
  read_state: 'UNREAD',
  trash_state: 'ACTIVE',
  trash_reason: null,
  note: '',
  tags: ['智能体'],
}

beforeEach(() => vi.restoreAllMocks())

describe('TopicsPage', () => {
  it('loads the selected topic through the paged server endpoint', async () => {
    const fetchMock = vi.fn(async (input: string | URL | Request) => {
      void input
      return {
        ok: true,
        json: async () => ({ items: [item], total: 1, page: 1, page_size: 20 }),
      } as Response
    })
    vi.stubGlobal('fetch', fetchMock)

    render(
      <ConfigProvider>
        <TopicsPage topics={topics} initialTopic="大模型与智能体" onOpen={() => undefined} />
      </ConfigProvider>,
    )

    expect(await screen.findByText('Agent Platform launch')).toBeInTheDocument()
    expect(screen.getByText('1 条正式情报')).toBeInTheDocument()
    await waitFor(() => expect(fetchMock).toHaveBeenCalled())
    const url = new URL(String(fetchMock.mock.calls[0][0]))
    expect(url.pathname).toBe('/api/archive')
    expect(url.searchParams.get('topic')).toBe('大模型与智能体')
    expect(url.searchParams.get('sort')).toBe('TIER_PRIORITY')
    expect(url.searchParams.get('paged')).toBe('true')
  })
})
