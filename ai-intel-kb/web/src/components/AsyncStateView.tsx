import { Alert, Button, Card, Empty, Result } from 'antd'
import type { ReactNode } from 'react'

export type AsyncState = 'idle' | 'loading' | 'success' | 'empty' | 'partial' | 'error'

interface AsyncStateViewProps {
  state: AsyncState
  children?: ReactNode
  emptyTitle?: string
  errorTitle?: string
  description?: string
  onRetry?: () => void
}

export function AsyncStateView({
  state,
  children,
  emptyTitle = '暂无数据',
  errorTitle = '加载失败',
  description,
  onRetry,
}: AsyncStateViewProps) {
  if (state === 'loading') {
    return <div role="status" aria-live="polite"><Card loading aria-label={description ?? '正在加载'} /></div>
  }
  if (state === 'error') {
    return (
      <div role="alert" aria-live="assertive">
        <Result
          status="warning"
          title={errorTitle}
          subTitle={description}
          extra={onRetry && <Button onClick={onRetry}>重新加载</Button>}
        />
      </div>
    )
  }
  if (state === 'empty') return <div role="status"><Empty description={emptyTitle} /></div>
  return (
    <>
      {state === 'partial' && (
        <div role="status" aria-live="polite">
          <Alert
            className="async-state-alert"
            type="warning"
            showIcon
            title="部分数据暂不可用"
            description={description}
          />
        </div>
      )}
      {children}
    </>
  )
}
