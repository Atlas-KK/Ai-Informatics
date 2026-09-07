import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { ConfigProvider } from 'antd'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { ArchiveDetail } from '../../types'
import { ExpansionSearchPanel } from './expansion/ExpansionSearchPanel'
import { TopicIdeaPanel } from './topic-ideas/TopicIdeaPanel'

const detail: ArchiveDetail = {
  event_id: 'event-1', version_no: 1, change_type: 'NEW', title: 'Agent product',
  topic: '大模型与智能体', summary: '摘要', content: '原情报正文', content_hash: 'hash',
  score_id: 'score-1', quality_score: 80, score_version: 1, score_dimensions: {}, tier: 'IMPORTANT',
  published_at: '2026-09-04T08:00:00Z', source_ids: ['source-1'], favorite: false, pinned: false,
  read_state: 'UNREAD', trash_state: 'ACTIVE', trash_reason: null, note: '', tags: [], topic_idea: null,
  versions: [{
    version_no: 1, change_type: 'NEW', canonical_title: 'Agent product', summary: '摘要', content: '原情报正文',
    content_hash: 'hash', created_at: '2026-09-04T08:00:00Z', source_language: 'zh', original_text: null,
    zh_translation: null, key_conclusions: [], pm_value: '产品价值', tags: [], quality_score: 80,
    tier: 'IMPORTANT', score_version: 1, score_dimensions: {}, score_rationales: {}, scored_at: null,
    evidence: [{
      evidence_id: 'evidence-1', source_id: 'source-1', url: 'https://source.test',
      published_at: '2026-09-04T08:00:00Z', viewpoint: '来源观点', source_name: '官方来源',
      source_type: 'WEB', source_state: 'ACTIVE', published_at_unknown: false,
      first_seen_at: '2026-09-04T08:00:00Z', supporting_source_count: 1,
      valid_source_count: 1, coverage_percent: 100,
    }],
  }],
}

const response = (value: unknown, ok = true, status = 200) => ({
  ok, status, json: async () => value,
}) as Response

beforeEach(() => vi.restoreAllMocks())

describe('UI-7 expansion search and topic ideas', () => {
  it('generates a bounded manual idea and resolves its supporting source', async () => {
    const fetch = vi.fn(async () => response({
      status: 'SUCCEEDED', created: true,
      idea: {
        idea_id: 'idea-1', trigger: 'MANUAL', title: '选题标题',
        outline: ['背景', '产品启示'], hook: '核心爆点',
        support_evidence_ids: ['evidence-1'], created_at: '2026-09-04T09:00:00Z',
        support_sources: [{ evidence_id: 'evidence-1', source_name: '官方来源', url: 'https://source.test', viewpoint: '来源观点' }],
      },
    }))
    vi.stubGlobal('fetch', fetch)
    render(<ConfigProvider><TopicIdeaPanel detail={detail} /></ConfigProvider>)

    fireEvent.click(screen.getByRole('button', { name: '生成选题建议' }))
    await waitFor(() => expect(screen.getByRole('heading', { name: '选题标题' })).toBeInTheDocument())
    expect(screen.getByText('手动生成')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /官方来源/ })).toHaveAttribute('href', 'https://source.test')
    expect(fetch).toHaveBeenCalledWith(expect.stringContaining('/api/archive/event-1/topic-idea'), expect.objectContaining({ method: 'POST' }))
    expect(screen.queryByText(/完整文章|自动发布/)).not.toBeInTheDocument()
  })

  it('keeps a manual-generation failure retryable', async () => {
    const fetch = vi.fn().mockResolvedValue(
      response({ detail: 'topic idea generation timed out; retry is available' }, false, 502),
    )
    vi.stubGlobal('fetch', fetch)
    render(<ConfigProvider><TopicIdeaPanel detail={detail} /></ConfigProvider>)

    fireEvent.click(screen.getByRole('button', { name: '生成选题建议' }))
    await screen.findByText('topic idea generation timed out; retry is available')
    expect(screen.getByRole('button', { name: /重试生成/ })).toBeInTheDocument()
    expect(fetch).toHaveBeenCalledTimes(1)
  })

  it('keeps results transient until confirmation and shows the new archive branch', async () => {
    const fetch = vi.fn(async (url: string) => {
      if (url.endsWith('/expansion-search')) return response({
        search_run_id: 'search-1', status: 'SUCCEEDED', error_code: null,
        results: [{ result_id: 'result-1', title: '扩展结果', url: 'https://result.test', summary: '补充资料', source_name: '外部来源', score: 88 }],
      })
      return response({ event_id: 'new-event', deduplicated: false })
    })
    vi.stubGlobal('fetch', fetch)
    render(<ConfigProvider><ExpansionSearchPanel eventId="event-1" initialQuery="Agent" /></ConfigProvider>)

    fireEvent.click(screen.getByRole('button', { name: '扩展搜索' }))
    await screen.findByRole('link', { name: '扩展结果' })
    expect(screen.getAllByText(/临时结果/).length).toBeGreaterThanOrEqual(1)
    expect(fetch).toHaveBeenCalledTimes(1)

    fireEvent.click(screen.getByRole('button', { name: '收藏并归档' }))
    expect(fetch).toHaveBeenCalledTimes(1)
    fireEvent.click(await screen.findByRole('button', { name: 'OK' }))
    await screen.findByText('已新建正式情报')
    expect(screen.getByText('事件 ID：new-event')).toBeInTheDocument()
    expect(fetch).toHaveBeenCalledTimes(2)
  })

  it('shows explicit search failure and preserves a retry entry', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => response({
      search_run_id: 'search-2', status: 'FAILED', error_code: 'EXPANSION_SEARCH_FAILED', results: [],
    })))
    render(<ConfigProvider><ExpansionSearchPanel eventId="event-1" initialQuery="Agent" /></ConfigProvider>)

    fireEvent.click(screen.getByRole('button', { name: '扩展搜索' }))
    await screen.findByText('扩展搜索失败；原情报未发生变化。')
    expect(screen.getByRole('button', { name: '重试搜索' })).toBeInTheDocument()
    expect(screen.getByDisplayValue('Agent')).toBeInTheDocument()
  })
})
