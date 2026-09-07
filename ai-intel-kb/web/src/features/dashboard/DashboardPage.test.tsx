import { fireEvent, render, screen } from '@testing-library/react'
import { ConfigProvider } from 'antd'
import { describe, expect, it, vi } from 'vitest'
import type { DashboardData } from '../../types'
import { DashboardPage } from './DashboardPage'

const emptyDashboard: DashboardData = {
  report_date: '2026-09-06',
  window_start: '2026-08-31',
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
  data_complete: false,
}

describe('DashboardPage', () => {
  it('shows empty and partial states without disguising missing charts as zero data', () => {
    const selectTopic = vi.fn()
    render(
      <ConfigProvider>
        <DashboardPage dashboard={emptyDashboard} onOpen={() => undefined} onSelectTopic={selectTopic} />
      </ConfigProvider>,
    )

    expect(screen.getByText('今日无达标情报')).toBeInTheDocument()
    expect(screen.getByText('统计数据不完整')).toBeInTheDocument()
    expect(screen.getByText('最近 7 天暂无可统计的正式情报')).toBeInTheDocument()
    const topic = screen.getByRole('button', { name: /大模型与智能体/ })
    fireEvent.click(topic)
    expect(selectTopic).toHaveBeenCalledWith('大模型与智能体')
  })
})
