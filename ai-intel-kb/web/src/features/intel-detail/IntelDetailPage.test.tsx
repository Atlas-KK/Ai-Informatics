import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { ConfigProvider } from 'antd'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { ArchiveDetail, ArchiveVersion } from '../../types'
import { IntelDetailPage } from './IntelDetailPage'

const evidence = {
  evidence_id: 'evidence-1',
  source_id: 'source-1',
  url: 'https://example.test/story',
  published_at: '2026-09-04T08:00:00Z',
  viewpoint: '多智能体协作将进入可观测阶段',
  source_name: '示例研究院',
  source_type: 'WEB' as const,
  source_state: 'DELETED' as const,
  published_at_unknown: true,
  first_seen_at: '2026-09-04T09:00:00Z',
  supporting_source_count: 2,
  valid_source_count: 3,
  coverage_percent: 66.7,
}

function version(versionNo: number, summary: string): ArchiveVersion {
  return {
    version_no: versionNo,
    change_type: versionNo === 1 ? 'NEW' : 'UPDATED',
    canonical_title: 'Agent Observability',
    summary,
    content: versionNo === 2 ? "正文 <script>alert('xss')</script>" : '首版正文',
    content_hash: `hash-${versionNo}`,
    created_at: `2026-09-0${versionNo + 2}T08:00:00Z`,
    source_language: 'en',
    original_text: 'Original text',
    zh_translation: '中文译文',
    key_conclusions: ['结论一'],
    pm_value: '可用于规划可观测能力',
    tags: ['agent'],
    quality_score: 91,
    tier: 'MUST_READ',
    score_version: 3,
    score_dimensions: { source_authority: 18 },
    score_rationales: { source_authority: '来自权威研究机构' },
    scored_at: '2026-09-04T10:00:00Z',
    evidence: [evidence],
  }
}

const detail: ArchiveDetail = {
  event_id: 'event-1',
  version_no: 2,
  change_type: 'UPDATED',
  title: 'Agent Observability',
  topic: '大模型与智能体',
  summary: '最新版摘要',
  content: '最新版正文',
  content_hash: '1234567890abcdef',
  score_id: 'score-1',
  quality_score: 91,
  score_version: 3,
  score_dimensions: { source_authority: 18 },
  tier: 'MUST_READ',
  published_at: '2026-09-04T08:00:00Z',
  source_ids: ['source-1'],
  favorite: false,
  pinned: false,
  read_state: 'UNREAD',
  trash_state: 'ACTIVE',
  trash_reason: null,
  note: '不要覆盖的笔记',
  tags: ['agent'],
  versions: [version(2, '最新版摘要'), version(1, '首版摘要')],
  topic_idea: {
    title: '为什么 Agent 需要可观测性',
    outline: ['问题', '方案'],
    hook: '从一次失控任务开始',
    support_evidence_ids: ['evidence-1'],
  },
}

const renderPage = () => render(
  <ConfigProvider>
    <IntelDetailPage
      detail={detail}
      close={vi.fn()}
      updateMetadata={vi.fn(async () => undefined)}
      refresh={vi.fn(async () => undefined)}
      notify={{ success: vi.fn(), error: vi.fn() }}
    />
  </ConfigProvider>,
)

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, json: async () => ({}) }) as Response))
})

describe('intelligence detail workspace', () => {
  it('renders readonly content and keeps the personal note while switching versions', async () => {
    const { container } = renderPage()
    expect(screen.getByText('系统归档内容为只读')).toBeInTheDocument()
    expect(screen.getByText('最新版摘要')).toBeInTheDocument()
    expect(container.querySelector('script')).toBeNull()
    const note = screen.getByDisplayValue('不要覆盖的笔记')
    expect(note).toHaveValue('不要覆盖的笔记')

    fireEvent.click(screen.getByRole('tab', { name: '历史版本' }))
    fireEvent.click(screen.getByRole('button', { name: /首\s*版/ }))
    expect(screen.getByText(/当前查看 v1/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('tab', { name: '只读正文' }))
    expect(screen.getByText('首版摘要')).toBeInTheDocument()
    expect(screen.getByDisplayValue('不要覆盖的笔记')).toHaveValue('不要覆盖的笔记')
  })

  it('shows server-provided coverage, unknown publication time, and retained deleted source configuration', () => {
    renderPage()
    fireEvent.click(screen.getByRole('tab', { name: '来源与观点' }))
    expect(screen.getByText('来源配置已删除，本地内容已保留')).toBeInTheDocument()
    expect(screen.queryByText('来源不可访问，本地内容已保留')).not.toBeInTheDocument()
    expect(screen.getByText(/发布时间未知/)).toBeInTheDocument()
    expect(screen.getByText('66.7%（2/3 个来源）')).toBeInTheDocument()
    expect(screen.getByText(/不代表观点置信度/)).toBeInTheDocument()
  })

  it('preserves note input when saving fails', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({
      ok: false,
      status: 500,
      json: async () => ({ detail: '磁盘写入失败' }),
    }) as Response))
    renderPage()
    const note = screen.getByDisplayValue('不要覆盖的笔记')
    fireEvent.change(note, { target: { value: '尚未保存的新笔记' } })
    fireEvent.click(screen.getByRole('button', { name: '保存笔记' }))
    await waitFor(() => expect(screen.getByText('磁盘写入失败')).toBeInTheDocument())
    expect(note).toHaveValue('尚未保存的新笔记')
  })
})
