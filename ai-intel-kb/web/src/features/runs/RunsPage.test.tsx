import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { ConfigProvider } from 'antd'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { RunsPage } from './RunsPage'
import type { PipelineRun, PipelineRunDetail } from '../../types'

const run: PipelineRun = {
  run_id: 'run-1', report_date: '2026-09-04', trigger_type: 'MANUAL', status: 'TIMED_OUT',
  started_at: '2026-09-04T01:00:00Z', finished_at: '2026-09-04T01:03:48Z',
  attempted_sources: 2, successful_sources: 1, failed_sources: 1, archived_count: 1,
  pending_count: 1, error_code: 'PIPELINE_DEADLINE_EXCEEDED', retry_count: 1,
}

const detail: PipelineRunDetail = {
  ...run,
  window_start: '2026-08-29T00:00:00Z', window_end: '2026-09-04T00:00:00Z',
  deadline_at: '2026-09-04T03:00:00Z', heartbeat_at: '2026-09-04T01:03:48Z',
  work_items: [{ aggregate_version_id: 'version-1', canonical_title: '待恢复情报', stage: 'SCORING', status: 'WAITING_RETRY', updated_at: '2026-09-04T01:03:48Z' }],
  retryable_work_items: [{ aggregate_version_id: 'version-1', canonical_title: '待恢复情报', stage: 'SCORING', status: 'WAITING_RETRY', updated_at: '2026-09-04T01:03:48Z' }],
  source_failures: [{ source_id: 'source-1', source_type: 'WEB', stage: 'FETCH', status: 'FAILED', reason: '上游超时', retry_count: 2, occurred_at: '2026-09-04T01:01:00Z' }],
  timeline: [{ event_type: 'pipeline_run_finished', created_at: '2026-09-04T01:03:48Z', status: 'TIMED_OUT', error_code: 'PIPELINE_DEADLINE_EXCEEDED' }],
  digest: {
    digest_id: 'digest-1', report_date: '2026-09-04', version_no: 1,
    markdown_path: 'digests/2026-09-04-v0001.md', created_at: '2026-09-04T01:03:00Z',
    segments: [
      { segment_id: 'segment-1', segment_no: 1, status: 'SENT', attempt_count: 1, error_code: null, updated_at: '2026-09-04T01:03:00Z' },
      { segment_id: 'segment-2', segment_no: 2, status: 'FAILED', attempt_count: 1, error_code: 'FEISHU_SEND_FAILED', updated_at: '2026-09-04T01:03:00Z' },
    ],
  },
}

describe('RunsPage', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn(async (input: string | URL | Request) => {
      const url = String(input)
      if (url.endsWith('/api/runs/run-1')) return { ok: true, json: async () => detail } as Response
      if (url.endsWith('/api/runs/run-2')) return { ok: true, json: async () => ({ ...detail, run_id: 'run-2' }) } as Response
      if (url.endsWith('/api/runs/run-1/retry')) return { ok: true, json: async () => ({ retried: [{ aggregate_version_id: 'version-1', stage: 'SCORING' }], failed: [] }) } as Response
      if (url.endsWith('/api/digests/digest-1/retry-failed-segments')) return { ok: true, json: async () => ({ status: 'SUCCESS', retried_segment_ids: ['segment-2'], failed_segments: 0 }) } as Response
      throw new Error(`unexpected request: ${url}`)
    }))
  })

  it('closes the timeout recovery and failed-segment resend flows', async () => {
    const refresh = vi.fn(async () => undefined)
    const notify = { success: vi.fn(), error: vi.fn() }
    render(<ConfigProvider><RunsPage runs={[run]} refresh={refresh} notify={notify} /></ConfigProvider>)

    expect(await screen.findByText('任务已超时停止新工作')).toBeInTheDocument()
    expect(screen.getByText(/本地日报已保留/)).toHaveTextContent(detail.digest?.markdown_path ?? '')
    expect(screen.getByText(/分段 1/)).toHaveTextContent('SENT')
    expect(screen.getByText(/分段 2/)).toHaveTextContent('FEISHU_SEND_FAILED')
    expect(screen.getByText(/上游超时/)).toHaveTextContent('已重试 2 次')

    fireEvent.click(screen.getByRole('button', { name: '重试失败阶段及后续' }))
    await waitFor(() => expect(fetch).toHaveBeenCalledWith(expect.stringMatching(/\/api\/runs\/run-1\/retry$/), expect.objectContaining({ method: 'POST' })))
    await waitFor(() => expect(notify.success).toHaveBeenCalledWith('已完成 1 个工作项的阶段重试'))

    const resend = await screen.findByRole('button', { name: /仅重发失败分段/ })
    await waitFor(() => expect(resend).not.toHaveClass('ant-btn-loading'))
    fireEvent.click(resend)
    await waitFor(() => expect(fetch).toHaveBeenCalledWith(expect.stringMatching(/\/api\/digests\/digest-1\/retry-failed-segments$/), expect.objectContaining({ method: 'POST' })))
    await waitFor(() => expect(notify.success).toHaveBeenCalledWith('已成功重发 1 个失败分段'))
  })

  it('keeps business failures visible after both retry operations', async () => {
    vi.stubGlobal('fetch', vi.fn(async (input: string | URL | Request) => {
      const url = String(input)
      if (url.endsWith('/api/runs/run-1')) return { ok: true, json: async () => detail } as Response
      if (url.endsWith('/api/runs/run-1/retry')) return { ok: true, json: async () => ({ retried: [], failed: [{ aggregate_version_id: 'version-1', stage: 'SCORING', error_code: 'LLM_TIMEOUT' }] }) } as Response
      if (url.endsWith('/api/digests/digest-1/retry-failed-segments')) return { ok: true, json: async () => ({ status: 'PARTIAL', retried_segment_ids: ['segment-2'], failed_segments: 1 }) } as Response
      throw new Error(`unexpected request: ${url}`)
    }))
    const notify = { success: vi.fn(), error: vi.fn() }
    render(<ConfigProvider><RunsPage runs={[run]} refresh={async () => undefined} notify={notify} /></ConfigProvider>)

    fireEvent.click(await screen.findByRole('button', { name: '重试失败阶段及后续' }))
    await waitFor(() => expect(notify.error).toHaveBeenCalledWith('重试后仍有 1 个工作项失败'))

    const resend = screen.getByRole('button', { name: /仅重发失败分段/ })
    await waitFor(() => expect(resend).not.toHaveClass('ant-btn-loading'))
    fireEvent.click(resend)
    await waitFor(() => expect(notify.error).toHaveBeenCalledWith('已重发 1 个分段，仍有 1 个失败'))
  })

  it('selects a run row with the keyboard', async () => {
    const notify = { success: vi.fn(), error: vi.fn() }
    const secondRun = { ...run, run_id: 'run-2' }
    render(<ConfigProvider><RunsPage runs={[run, secondRun]} refresh={async () => undefined} notify={notify} /></ConfigProvider>)

    await screen.findByText('运行 ID：run-1')
    const secondRow = screen.getByRole('row', { name: '查看运行详情：run-2' })
    secondRow.focus()
    expect(secondRow).toHaveFocus()
    fireEvent.keyDown(secondRow, { key: 'Enter', code: 'Enter' })
    expect(await screen.findByText('运行 ID：run-2')).toBeInTheDocument()
  })
})
