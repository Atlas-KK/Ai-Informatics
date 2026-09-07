import { Space, Typography } from 'antd'
import type { ReactNode } from 'react'

const { Text, Title } = Typography

interface PageHeaderProps {
  title: string
  description?: ReactNode
  extra?: ReactNode
}

export function PageHeader({ title, description, extra }: PageHeaderProps) {
  return (
    <div className="page-header">
      <Space orientation="vertical" size={2}>
        <Title level={2}>{title}</Title>
        {description && <Text type="secondary">{description}</Text>}
      </Space>
      {extra && <div className="page-header-extra">{extra}</div>}
    </div>
  )
}
