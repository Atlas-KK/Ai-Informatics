import { Popconfirm } from 'antd'
import type { ReactElement, ReactNode } from 'react'

interface ConfirmActionProps {
  children: ReactElement
  title: ReactNode
  description?: ReactNode
  disabled?: boolean
  onConfirm: () => void | Promise<void>
}

export function ConfirmAction({ children, title, description, disabled, onConfirm }: ConfirmActionProps) {
  return (
    <Popconfirm
      title={title}
      description={description}
      disabled={disabled}
      onConfirm={() => void onConfirm()}
    >
      {children}
    </Popconfirm>
  )
}
