import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { ConfigProvider } from 'antd'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import type { ArchiveDetail, ArchiveItem } from './types'

const emptyDashboard = {
  report_date: '2026-09-04',
  window_start: '2026-08-29',
  total_count: 0,
  today_count: 0,
  items: [],
  topic_summaries: [
    { name: '大模型与智能体', count: 0, tags: [] },
    { name: 'AI 产品形态与行业应用', count: 0, tags: [] },
    { name: 'AI 产品实战', count: 0, tags: [] },
    { name: 'AI 工程安全与可靠性', count: 0, tags: [] },
  ],
  topic_counts: {},
  tier_counts: { MUST_READ: 0, IMPORTANT: 0, EXTENDED: 0 },
  source_counts: {},
  change_counts: { NEW: 0, UPDATED: 0 },
  seven_day_trend: {},
  latest_run: null,
  data_complete: true,
}

function archiveItem(eventId: string, title: string): ArchiveItem {
  return {
    event_id: eventId,
    version_no: 1,
    change_type: 'NEW',
    title,
    topic: '大模型与智能体',
    summary: `${title} 摘要`,
    content: `${title} 正文`,
    content_hash: 'a'.repeat(64),
    score_id: null,
    quality_score: 80,
    score_version: 1,
    score_dimensions: { source_authority: 80 },
    tier: 'IMPORTANT',
    published_at: '2026-09-04T08:00:00Z',
    source_ids: ['source-1'],
    favorite: false,
    pinned: false,
    read_state: 'UNREAD',
    trash_state: 'ACTIVE',
    trash_reason: null,
    note: '',
    tags: [],
  }
}

function archiveDetail(item: ArchiveItem): ArchiveDetail {
  return {
    ...item,
    versions: [{
      version_no: 1,
      change_type: 'NEW',
      canonical_title: item.title,
      summary: item.summary,
      content: item.content,
      content_hash: item.content_hash,
      created_at: item.published_at,
      source_language: 'zh',
      original_text: item.content,
      zh_translation: null,
      key_conclusions: [],
      pm_value: null,
      tags: [],
      quality_score: 80,
      tier: 'IMPORTANT',
      score_version: 1,
      score_dimensions: { source_authority: 80 },
      score_rationales: {},
      scored_at: item.published_at,
      evidence: [],
    }],
    topic_idea: null,
  }
}

beforeEach(() => {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: string | URL | Request) => {
      const url = String(input)
      let data: unknown = []
      if (url.endsWith('/api/dashboard')) data = emptyDashboard
      if (url.includes('/api/archive?')) {
        data = { items: [], total: 0, page: 1, page_size: 20 }
      }
      if (url.endsWith('/api/settings')) {
        data = {
          schedule_time: '08:30',
          selection_threshold: 70,
          tier_caps: { MUST_READ: 3, IMPORTANT: 7, EXTENDED: 10 },
          topic_order: [
            '大模型与智能体',
            'AI 产品形态与行业应用',
            'AI 产品实战',
            'AI 工程安全与可靠性',
          ],
          default_sort: 'PUBLISHED_DESC',
          updated_at: '2026-09-04T00:00:00Z',
        }
      }
      return { ok: true, json: async () => data } as Response
    }),
  )
})

describe('local intelligence workbench shell', () => {
  it('renders the approved navigation labels and the empty dashboard', async () => {
    render(<ConfigProvider><App /></ConfigProvider>)
    expect(screen.getByText('AI 产品经理情报知识库')).toBeInTheDocument()
    expect(screen.getByText('Local Workspace')).toBeInTheDocument()
    expect(await screen.findByText('今日无达标情报')).toBeInTheDocument()
    expect(screen.getByText('最近 7 天暂无达标情报')).toBeInTheDocument()
    expect(screen.getByText('专题档案')).toBeInTheDocument()
    expect(screen.getByText('历史检索')).toBeInTheDocument()
    expect(screen.getByText('系统设置')).toBeInTheDocument()
    expect(screen.queryByText('主题档案')).not.toBeInTheDocument()
    expect(screen.getByText('扩展')).toBeInTheDocument()
  })

  it('keeps the selected navigation item in sync with the rendered page', async () => {
    render(<ConfigProvider><App /></ConfigProvider>)
    await screen.findByText('今日无达标情报')

    fireEvent.click(screen.getByRole('menuitem', { name: '专题档案' }))

    expect(await screen.findByRole('heading', { name: '专题档案' })).toBeInTheDocument()
    expect(screen.getByRole('menuitem', { name: '专题档案' })).toHaveClass('ant-menu-item-selected')
  })

  it('ignores a stale detail response after the user opens another item', async () => {
    const first = archiveItem('event-a', '情报 A')
    const second = archiveItem('event-b', '情报 B')
    let resolveFirst: ((response: Response) => void) | undefined
    let resolveSecond: ((response: Response) => void) | undefined
    const response = (data: unknown) => ({ ok: true, json: async () => data }) as Response
    vi.stubGlobal('fetch', vi.fn((input: string | URL | Request) => {
      const url = String(input)
      if (url.endsWith('/api/archive/event-a')) {
        return new Promise<Response>((resolve) => { resolveFirst = resolve })
      }
      if (url.endsWith('/api/archive/event-b')) {
        return new Promise<Response>((resolve) => { resolveSecond = resolve })
      }
      if (url.endsWith('/api/dashboard')) {
        return Promise.resolve(response({
          ...emptyDashboard,
          total_count: 2,
          today_count: 2,
          items: [first, second],
          topic_summaries: [{ name: '大模型与智能体', count: 2, tags: [] }],
          tier_counts: { MUST_READ: 0, IMPORTANT: 2, EXTENDED: 0 },
        }))
      }
      if (url.includes('/api/archive?')) {
        return Promise.resolve(response({ items: [first, second], total: 2, page: 1, page_size: 20 }))
      }
      if (url.endsWith('/api/settings')) {
        return Promise.resolve(response({
          schedule_time: '08:30', selection_threshold: 70,
          tier_caps: { MUST_READ: 3, IMPORTANT: 7, EXTENDED: 10 },
          topic_order: ['大模型与智能体'], default_sort: 'PUBLISHED_DESC',
          updated_at: '2026-09-04T00:00:00Z',
        }))
      }
      return Promise.resolve(response([]))
    }))

    render(<ConfigProvider><App /></ConfigProvider>)
    fireEvent.click(await screen.findByText('情报 A'))
    await waitFor(() => expect(resolveFirst).toBeDefined())
    fireEvent.click(screen.getByRole('menuitem', { name: '专题档案' }))
    await screen.findByRole('heading', { name: '专题档案' })
    fireEvent.click(await screen.findByText('情报 B'))
    await waitFor(() => expect(resolveSecond).toBeDefined())

    await act(async () => resolveSecond?.(response(archiveDetail(second))))
    expect(await screen.findByRole('heading', { name: '情报 B' })).toBeInTheDocument()
    await act(async () => resolveFirst?.(response(archiveDetail(first))))
    expect(screen.getByRole('heading', { name: '情报 B' })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: '情报 A' })).not.toBeInTheDocument()
  }, 30_000)
})
