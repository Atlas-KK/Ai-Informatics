import { fireEvent, render, screen } from '@testing-library/react'
import { ConfigProvider } from 'antd'
import { describe, expect, it, vi } from 'vitest'
import { AsyncStateView } from './AsyncStateView'
import { IntelList } from './IntelList'
import { StatusBadge } from './StatusBadge'
import type { ArchiveItem } from '../types'

const item: ArchiveItem = {
  event_id: 'event-1',
  version_no: 1,
  change_type: 'NEW',
  title: '智能体产品更新',
  topic: '大模型与智能体',
  summary: '一条用于组件验证的摘要',
  content: '正文',
  content_hash: 'a'.repeat(64),
  score_id: 'score-1',
  quality_score: 88,
  score_version: 1,
  score_dimensions: {},
  tier: 'EXTENDED',
  published_at: '2026-09-04T01:00:00Z',
  source_ids: ['source-1'],
  favorite: false,
  pinned: false,
  read_state: 'UNREAD',
  trash_state: 'ACTIVE',
  trash_reason: null,
  note: '',
  tags: ['智能体'],
}

describe('shared UI components', () => {
  it('renders loading, empty, partial and error states with an observable retry', () => {
    const { rerender } = render(<ConfigProvider><AsyncStateView state="loading" /></ConfigProvider>)
    expect(screen.getByRole('status')).toBeInTheDocument()
    expect(screen.getByLabelText('正在加载')).toBeInTheDocument()

    rerender(<ConfigProvider><AsyncStateView state="empty" emptyTitle="暂无情报" /></ConfigProvider>)
    expect(screen.getByText('暂无情报')).toBeInTheDocument()
    expect(screen.getByRole('status')).toBeInTheDocument()

    rerender(
      <ConfigProvider>
        <AsyncStateView state="partial" description="两个来源暂不可用">
          <span>已完成内容</span>
        </AsyncStateView>
      </ConfigProvider>,
    )
    expect(screen.getByText('部分数据暂不可用')).toBeInTheDocument()
    expect(screen.getByRole('status')).toHaveAttribute('aria-live', 'polite')
    expect(screen.getByText('已完成内容')).toBeInTheDocument()

    const retry = vi.fn()
    rerender(
      <ConfigProvider>
        <AsyncStateView state="error" errorTitle="连接失败" onRetry={retry} />
      </ConfigProvider>,
    )
    fireEvent.click(screen.getByRole('button', { name: '重新加载' }))
    expect(screen.getByRole('alert')).toHaveAttribute('aria-live', 'assertive')
    expect(retry).toHaveBeenCalledOnce()
  })

  it('renders semantic status and a keyboard-focusable intelligence item', () => {
    const open = vi.fn()
    render(
      <ConfigProvider>
        <StatusBadge status="SUCCEEDED" />
        <IntelList items={[item]} onOpen={open} />
      </ConfigProvider>,
    )

    expect(screen.getByText('SUCCEEDED')).toBeInTheDocument()
    expect(screen.getByText('扩展')).toBeInTheDocument()
    const button = screen.getByRole('button', { name: '查看情报：智能体产品更新' })
    button.focus()
    expect(button).toHaveFocus()
    fireEvent.click(button)
    expect(open).toHaveBeenCalledWith('event-1')
  })
})
