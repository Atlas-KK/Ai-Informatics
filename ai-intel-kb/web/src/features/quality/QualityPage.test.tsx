import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { ConfigProvider, message } from 'antd'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { CalibrationWorkbench, FeedbackRecord } from '../../types'
import { QualityPage } from './QualityPage'

const feedback: FeedbackRecord[] = [{
  feedback_id: 'feedback-1',
  score_id: 'score-1',
  aggregate_version_id: 'aggregate-1',
  canonical_title: 'Agent 评测框架更新',
  reason: '信息密度偏低',
  affected_dimension: 'information_density',
  original_score: 72,
  outcome: 'REMOVED',
  content_features: { origin: 'DETAIL' },
  score_version: 1,
  score_revision: 1,
  created_at: '2026-09-04T01:00:00Z',
}]

const workbench: CalibrationWorkbench = {
  active_version: 2,
  configs: [
    { version: 2, weights: { information_density: 0.22 }, source_overrides: {}, status: 'ACTIVE', is_active: true, created_at: '2026-09-04T02:00:00Z' },
    { version: 1, weights: { information_density: 0.2 }, source_overrides: {}, status: 'INACTIVE', is_active: false, created_at: '2026-09-04T00:00:00Z' },
  ],
  proposals: [],
  audits: [{ audit_id: 'audit-1', old_config_version: 1, new_config_version: 2, action: 'CONFIRM', created_at: '2026-09-04T02:00:00Z' }],
  rescore_targets: [{ aggregate_version_id: 'aggregate-1', canonical_title: 'Agent 评测框架更新', score_id: 'score-1', latest_score: 72, config_version: 1, score_revision: 1, score_count: 1, created_at: '2026-09-04T01:00:00Z' }],
}

const notify = {
  success: vi.fn(),
  error: vi.fn(),
  warning: vi.fn(),
} as unknown as ReturnType<typeof message.useMessage>[0]

function response(data: unknown) {
  return { ok: true, json: async () => data } as Response
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('quality calibration workbench', () => {
  it('exposes feedback entry, real version history and manual rescore scope', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => response(workbench)))
    render(
      <ConfigProvider>
        <QualityPage feedback={feedback} refresh={vi.fn()} notify={notify} />
      </ConfigProvider>,
    )

    expect(await screen.findByRole('heading', { name: '质量反馈与评分校准' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '查看详情' })).toBeInTheDocument()

    fireEvent.click(screen.getByRole('tab', { name: '版本历史' }))
    expect((await screen.findAllByText('score-v2')).length).toBeGreaterThan(0)
    expect(screen.getByLabelText('选择历史评分版本')).toBeInTheDocument()
    expect(screen.queryByRole('spinbutton')).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('tab', { name: '历史重评分' }))
    expect(await screen.findByText('历史重评分是手动追加操作')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '执行历史重评分' })).toBeDisabled()
  }, 30_000)

  it('shows insufficient samples without creating a configuration', async () => {
    const fetchMock = vi.fn(async (input: string | URL | Request) => {
      const url = String(input)
      if (url.endsWith('/api/calibration/proposals')) {
        return response({ sample_count: 4, uncertainty: 'HIGH', proposal: null })
      }
      return response(workbench)
    })
    vi.stubGlobal('fetch', fetchMock)
    render(
      <ConfigProvider>
        <QualityPage feedback={feedback} refresh={vi.fn()} notify={notify} />
      </ConfigProvider>,
    )

    await screen.findByRole('heading', { name: '质量反馈与评分校准' })
    fireEvent.click(screen.getByRole('tab', { name: '校准工作台' }))
    fireEvent.click(screen.getByRole('button', { name: '基于当前反馈生成建议' }))

    expect(await screen.findByText('样本不足，未生成校准配置')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '审核并确认' })).not.toBeInTheDocument()
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/api/calibration/proposals'),
      expect.objectContaining({ method: 'POST' }),
    ))
  })

  it('restores an undecided proposal after a page refresh', async () => {
    const pendingWorkbench: CalibrationWorkbench = {
      ...workbench,
      proposals: [{
        proposal_id: 'proposal-pending',
        base_config_version: 2,
        sample_count: 8,
        uncertainty: 'MEDIUM',
        affected_dimensions: ['information_density'],
        suggested_weights: { information_density: 0.24 },
        estimated_impact: { scope: 'future scores only' },
        decision: null,
        new_config_version: null,
        created_at: '2026-09-04T03:00:00Z',
        decided_at: null,
      }],
    }
    vi.stubGlobal('fetch', vi.fn(async () => response(pendingWorkbench)))
    render(
      <ConfigProvider>
        <QualityPage feedback={feedback} refresh={vi.fn()} notify={notify} />
      </ConfigProvider>,
    )

    await screen.findByRole('heading', { name: '质量反馈与评分校准' })
    fireEvent.click(screen.getByRole('tab', { name: '校准工作台' }))
    expect(await screen.findByText('待确认建议 · 基于 score-v2')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '审核并确认' })).toBeEnabled()
    expect(screen.getByRole('button', { name: '基于当前反馈生成建议' })).toBeDisabled()
  }, 10_000)

  it('blocks confirmation when a pending proposal belongs to a stale base version', async () => {
    const staleWorkbench: CalibrationWorkbench = {
      ...workbench,
      proposals: [{
        proposal_id: 'proposal-stale', base_config_version: 1, sample_count: 5,
        uncertainty: 'MEDIUM', affected_dimensions: ['information_density'],
        suggested_weights: { information_density: 0.22 },
        estimated_impact: { scope: 'future scores only' }, decision: null,
        new_config_version: null, created_at: '2026-09-04T01:00:00Z', decided_at: null,
      }],
    }
    vi.stubGlobal('fetch', vi.fn(async () => response(staleWorkbench)))
    render(
      <ConfigProvider>
        <QualityPage feedback={feedback} refresh={vi.fn()} notify={notify} />
      </ConfigProvider>,
    )

    await screen.findByRole('heading', { name: '质量反馈与评分校准' })
    fireEvent.click(screen.getByRole('tab', { name: '校准工作台' }))
    expect(await screen.findByText('该提案基于非当前评分版本，不能再确认')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '审核并确认' })).toBeDisabled()
    expect(screen.getByRole('button', { name: '拒绝建议' })).toBeEnabled()
  }, 10_000)
})
