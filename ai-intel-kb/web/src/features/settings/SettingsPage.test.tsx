import { fireEvent, render, screen } from '@testing-library/react'
import { ConfigProvider } from 'antd'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { api } from '../../api'
import type { AppSettings } from '../../types'
import { SettingsPage } from './SettingsPage'

vi.mock('../../api', () => ({ api: vi.fn() }))

const settings: AppSettings = {
  schedule_time: '23:00', selection_threshold: 70,
  tier_caps: { MUST_READ: 10, IMPORTANT: 20, EXTENDED: 20 },
  topic_order: ['大模型与智能体', 'AI 产品形态与行业应用', 'AI 产品实战', 'AI 工程安全与可靠性'],
  default_sort: 'PUBLISHED_DESC',
  github_rules: { daily_trending: true, weekly_trending: true, seven_day_star_growth: true, ai_relevance: true, whitelist: [] },
  updated_at: '2026-09-06T00:00:00Z',
}

describe('SettingsPage', () => {
  beforeEach(() => {
    vi.mocked(api).mockReset()
    vi.mocked(api).mockResolvedValue({ version: 2, weights: { source_authority: 0.3, timeliness: 0.25, reach: 0.15, information_density: 0.15, innovation: 0.15 } })
  })

  it('closes the four-tab settings flow without exposing secret values', async () => {
    render(<ConfigProvider><SettingsPage settings={settings} configuration={{ services: { semantic_search: false }, missing_items: ['语义检索服务'] }} saved={vi.fn()} failed={vi.fn()} openQuality={vi.fn()} /></ConfigProvider>)
    expect(screen.getByRole('heading', { name: '系统设置' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: '采集调度' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('tab', { name: '评分分层' }))
    expect(await screen.findByText('当前评分配置 v2')).toBeInTheDocument()
    expect(screen.getByText(/权重由评分校准流程版本化管理/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('tab', { name: '显示顺序' }))
    expect(screen.getByText(/下一次飞书日报/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('tab', { name: '服务状态' }))
    expect(screen.getByText(/缺失配置：语义检索服务/)).toBeInTheDocument()
    expect(screen.queryByText(/token|secret|密钥值/i)).not.toBeInTheDocument()
  })
})
