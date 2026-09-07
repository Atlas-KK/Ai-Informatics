import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { ConfigProvider } from 'antd'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { ArchiveItem, TopicSummary } from '../../types'
import { HistorySearchPage } from './HistorySearchPage'

const topics: TopicSummary[] = [{ name: '大模型与智能体', count: 1, tags: [] }]
const item: ArchiveItem = {
  event_id: 'event-1',
  version_no: 1,
  change_type: 'NEW',
  title: 'Agent Platform launch',
  topic: '大模型与智能体',
  summary: '产品情报摘要',
  content: '正文',
  content_hash: 'a'.repeat(64),
  score_id: 'score-1',
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

describe('HistorySearchPage', () => {
  it('runs the query on the server and exposes semantic degradation', async () => {
    const fetchMock = vi.fn(async (input: string | URL | Request) => {
      const url = String(input)
      const data = url.includes('/api/search?')
        ? {
            items: [item], total: 1, page: 1, page_size: 20,
            query: 'Agent', mode: 'KEYWORD', degraded: true,
            degraded_reason: 'SEMANTIC_PROVIDER_NOT_CONFIGURED',
          }
        : { items: [], total: 0, page: 1, page_size: 20 }
      return { ok: true, json: async () => data } as Response
    })
    vi.stubGlobal('fetch', fetchMock)
    render(<ConfigProvider><HistorySearchPage topics={topics} onOpen={() => undefined} /></ConfigProvider>)
    await screen.findByText('没有匹配的历史情报，可调整或清空筛选条件')

    fireEvent.change(screen.getByPlaceholderText('检索标题、摘要、正文、来源、标签和笔记'), {
      target: { value: 'Agent' },
    })
    fireEvent.click(screen.getByRole('button', { name: /检索/ }))

    expect(await screen.findByText('当前使用关键词检索')).toBeInTheDocument()
    expect(screen.getByText('Agent Platform launch')).toBeInTheDocument()
    await waitFor(() => expect(fetchMock.mock.calls.some(([input]) => {
      const url = new URL(String(input))
      return url.pathname === '/api/search' && url.searchParams.get('q') === 'Agent'
    })).toBe(true))

    fireEvent.click(screen.getByRole('button', { name: '清空条件' }))
    await waitFor(() => expect(fetchMock.mock.calls.some(([input]) => {
      const url = new URL(String(input))
      return url.pathname === '/api/archive' && url.searchParams.get('paged') === 'true'
    })).toBe(true))
  })

  it('keeps a visible retry path when the server request fails', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({
      ok: false,
      json: async () => ({ detail: '筛选服务暂不可用' }),
    }) as Response))
    render(<ConfigProvider><HistorySearchPage topics={topics} onOpen={() => undefined} /></ConfigProvider>)

    expect(await screen.findByText('历史检索失败')).toBeInTheDocument()
    expect(screen.getByText('筛选服务暂不可用')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '重新加载' })).toBeInTheDocument()
  })
})
