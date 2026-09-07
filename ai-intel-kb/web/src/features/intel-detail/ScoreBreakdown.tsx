import { Card, Col, Progress, Row, Space, Tag, Typography } from 'antd'
import { scoreDimensionLabels } from '../../app/labels'

const { Text } = Typography

export function ScoreBreakdown({
  total,
  version,
  dimensions,
  rationales,
}: {
  total: number | null
  version: number | null
  dimensions: Record<string, number>
  rationales: Record<string, string>
}) {
  return (
    <Card
      className="detail-score-card"
      title="评分记录"
      extra={version === null ? <Tag>配置版本未提供</Tag> : <Tag color="blue">评分配置 v{version}</Tag>}
    >
      {total === null ? <Text type="secondary">该历史版本未提供评分记录</Text> : (
        <Space orientation="vertical" size="middle" className="full-width">
          <Progress percent={total} format={(value) => `${value} 分`} />
          <Row gutter={[12, 12]}>
            {Object.entries(dimensions).map(([key, value]) => (
              <Col xs={24} md={12} xl={8} key={key}>
                <div className="score-dimension">
                  <Space><Text strong>{scoreDimensionLabels[key] ?? key}</Text><Tag>{value} 分</Tag></Space>
                  <Text type="secondary">{rationales[key] || '本版本未提供评分依据'}</Text>
                </div>
              </Col>
            ))}
          </Row>
        </Space>
      )}
    </Card>
  )
}
