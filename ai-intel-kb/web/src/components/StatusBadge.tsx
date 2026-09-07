import { Tag } from 'antd'

const statusColors: Record<string, string> = {
  ACTIVE: 'green',
  PAUSED: 'gold',
  DELETED: 'default',
  SUCCEEDED: 'green',
  FAILED: 'red',
  TIMED_OUT: 'volcano',
  REJECTED_DUPLICATE: 'default',
  WAITING_RETRY: 'gold',
  RUNNING: 'blue',
  PENDING: 'default',
  SENT: 'green',
}

export function StatusBadge({ status }: { status: string }) {
  return <Tag color={statusColors[status] ?? 'default'}>{status}</Tag>
}
