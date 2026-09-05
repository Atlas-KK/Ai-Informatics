import { render, screen } from '@testing-library/react'
import { ConfigProvider } from 'antd'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'

const emptyDashboard = {
  report_date: '2026-09-04',
  window_start: '2026-08-29',
  items: [],
  topic_counts: {},
  tier_counts: { MUST_READ: 0, IMPORTANT: 0, EXTENDED: 0 },
}

beforeEach(() => {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: string | URL | Request) => {
      const url = String(input)
      let data: unknown = []
      if (url.endsWith('/api/dashboard')) data = emptyDashboard
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

describe('Phase 7 local workbench', () => {
  it('renders navigation and the empty dashboard', async () => {
    render(<ConfigProvider><App /></ConfigProvider>)
    expect(screen.getByText('AI 产品经理情报知识库')).toBeInTheDocument()
    expect(screen.getByText('Phase 7 · Local')).toBeInTheDocument()
    expect(await screen.findByText('当前条件下暂无情报')).toBeInTheDocument()
    expect(screen.getByText('历史检索')).toBeInTheDocument()
    expect(screen.getByText('系统设置')).toBeInTheDocument()
  })
})
