import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { ConfigProvider, message } from 'antd'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { api } from '../../api'
import type { AppSettings } from '../../types'
import { SourcesPage } from './SourcesPage'

vi.mock('../../api', () => ({ api: vi.fn() }))

const settings: AppSettings = {
  schedule_time: '23:00',
  selection_threshold: 70,
  tier_caps: { MUST_READ: 10, IMPORTANT: 20, EXTENDED: 20 },
  topic_order: ['大模型与智能体', 'AI 产品形态与行业应用', 'AI 产品实战', 'AI 工程安全与可靠性'],
  default_sort: 'PUBLISHED_DESC',
  github_rules: {
    daily_trending: true,
    weekly_trending: true,
    seven_day_star_growth: true,
    ai_relevance: true,
    whitelist: [],
  },
  updated_at: '2026-09-06T00:00:00Z',
}

function Harness() {
  const [notify, holder] = message.useMessage()
  return <ConfigProvider>{holder}<SourcesPage sources={[]} experts={[]} settings={settings} refresh={vi.fn()} settingsSaved={vi.fn()} notify={notify} /></ConfigProvider>
}

describe('SourcesPage', () => {
  beforeEach(() => {
    vi.mocked(api).mockReset()
    vi.mocked(api).mockImplementation(async (path) => {
      if (path === '/api/source-operations') return []
      if (path === '/api/settings') return settings
      return {}
    })
  })

  it('exposes source, expert and GitHub rule workflows', async () => {
    render(<Harness />)
    expect(screen.getByRole('heading', { name: '来源管理' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: '信息源' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: '专家白名单' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('tab', { name: 'GitHub 规则' }))
    expect(screen.getByText(/榜单不可用时仍执行白名单采集/)).toBeInTheDocument()
    fireEvent.click(screen.getByText('GitHub 周榜'))
    fireEvent.click(screen.getByRole('button', { name: '保存 GitHub 规则' }))
    await waitFor(() => expect(api).toHaveBeenCalledWith('/api/settings', expect.objectContaining({ method: 'PUT' })))
    const request = vi.mocked(api).mock.calls.find(([path]) => path === '/api/settings')?.[1]
    expect(JSON.parse(String(request?.body)).github_rules.weekly_trending).toBe(false)
  })

  it('shows the video collection boundary in the source form', async () => {
    render(<Harness />)
    fireEvent.click(screen.getByRole('button', { name: /新增来源/ }))
    fireEvent.mouseDown(screen.getByLabelText('类型'))
    fireEvent.click(await screen.findByText('VIDEO'))
    expect(screen.getByText(/不下载音视频、不执行 ASR/)).toBeInTheDocument()
  })
})
