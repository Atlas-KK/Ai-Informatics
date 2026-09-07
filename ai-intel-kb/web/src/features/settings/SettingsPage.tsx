import { DownOutlined, UpOutlined } from '@ant-design/icons'
import {
  Alert,
  Button,
  Card,
  Col,
  Descriptions,
  Form,
  Input,
  InputNumber,
  Row,
  Select,
  Space,
  Tabs,
  Tag,
  Typography,
} from 'antd'
import { useEffect, useState } from 'react'
import { api } from '../../api'
import { tierLabels } from '../../app/labels'
import { PageHeader } from '../../components'
import type { AppSettings, ConfigurationStatus, ScoringConfig, Tier } from '../../types'

const { Text } = Typography
const weightLabels: Record<string, string> = {
  source_authority: '来源权威性',
  timeliness: '时效性',
  reach: '传播影响力',
  information_density: '信息密度',
  innovation: '创新性',
}
const serviceLabels: Record<string, string> = {
  semantic_search: '语义检索服务',
  expansion_search: '扩展搜索服务',
  intelligence_processing: '情报处理模型',
  retry_executor: '失败重试执行器',
  feishu: '飞书推送',
}

interface SettingsPageProps {
  settings: AppSettings
  configuration: ConfigurationStatus | null
  saved: (value: AppSettings) => void
  failed: (error: Error) => void
  openQuality: () => void
}

export function SettingsPage({ settings, configuration, saved, failed, openQuality }: SettingsPageProps) {
  const [form] = Form.useForm<AppSettings>()
  const [topicOrder, setTopicOrder] = useState(settings.topic_order)
  const [scoring, setScoring] = useState<ScoringConfig | null>(null)

  useEffect(() => {
    form.setFieldsValue(settings)
  }, [form, settings])
  useEffect(() => {
    let active = true
    void api<ScoringConfig>('/api/scoring-config')
      .then((value) => { if (active) setScoring(value) })
      .catch(() => { if (active) setScoring(null) })
    return () => { active = false }
  }, [])

  const move = (index: number, offset: number) => {
    const next = [...topicOrder]
    const target = index + offset
    if (target < 0 || target >= next.length) return
    ;[next[index], next[target]] = [next[target], next[index]]
    setTopicOrder(next)
  }
  const submit = () => {
    void form.validateFields().then((values) => api<AppSettings>('/api/settings', {
      method: 'PUT',
      body: JSON.stringify({ ...settings, ...values, topic_order: topicOrder, updated_at: undefined }),
    })).then(saved).catch((error: unknown) => failed(error instanceof Error ? error : new Error('设置保存失败')))
  }

  const schedule = (
    <Card>
      <Alert className="section-alert" showIcon type="info" message="配置保存后于下一次任务生效。采集窗口固定为任务开始前连续 7×24 小时。" />
      <Form.Item label="每日执行时间 / Asia/Shanghai" name="schedule_time" rules={[
        { required: true },
        { pattern: /^(?:[01]\d|2[0-3]):[0-5]\d$/, message: '请输入 24 小时制 HH:MM' },
      ]}><Input placeholder="23:00" /></Form.Item>
      <Descriptions bordered column={1} items={[
        { key: 'window', label: '采集窗口', children: '任务开始前连续 7×24 小时；缺少发布时间时使用首次发现时间。' },
        { key: 'resume', label: '补跑策略', children: '恢复后补跑最近一次未完成任务；最长 2 小时；只允许一个运行实例。' },
      ]} />
      <Button className="settings-save" type="primary" onClick={submit}>保存设置</Button>
    </Card>
  )

  const score = (
    <Card>
      <Alert showIcon type="warning" message="五维权重由评分校准流程版本化管理，此处只读，不能直接修改。" />
      <Row gutter={16} className="settings-grid">
        <Col xs={24} md={8}><Form.Item label="入选阈值" name="selection_threshold" rules={[{ required: true }]}><InputNumber min={0} max={100} className="full-width" /></Form.Item></Col>
        {(['MUST_READ', 'IMPORTANT', 'EXTENDED'] as Tier[]).map((tier) => (
          <Col xs={24} md={8} key={tier}><Form.Item label={`${tierLabels[tier]}数量上限`} name={['tier_caps', tier]} rules={[{ required: true }]}><InputNumber min={0} max={50} className="full-width" /></Form.Item></Col>
        ))}
      </Row>
      <Descriptions title={`当前评分配置 ${scoring ? `v${scoring.version}` : ''}`} bordered column={{ xs: 1, md: 2 }} items={Object.entries(scoring?.weights ?? {}).map(([key, value]) => ({ key, label: weightLabels[key] ?? key, children: `${Math.round(value * 100)}%` }))} />
      <Space className="settings-save"><Button type="primary" onClick={submit}>保存阈值与分层</Button><Button onClick={openQuality}>进入评分校准</Button></Space>
    </Card>
  )

  const order = (
    <Card>
      <Alert showIcon type="info" message="专题顺序保存后同时用于网页展示与下一次飞书日报；历史日报不会重排。" />
      <div className="order-list settings-order">
        {topicOrder.map((topic, index) => (
          <div key={topic}>
            <Text>{index + 1}. {topic}</Text>
            <Space>
              <Button aria-label={`上移${topic}`} icon={<UpOutlined />} disabled={!index} onClick={() => move(index, -1)} />
              <Button aria-label={`下移${topic}`} icon={<DownOutlined />} disabled={index === topicOrder.length - 1} onClick={() => move(index, 1)} />
            </Space>
          </div>
        ))}
      </div>
      <Form.Item className="settings-sort" label="默认排序" name="default_sort"><Select options={[{ value: 'PUBLISHED_DESC', label: '发布时间倒序' }, { value: 'SCORE_DESC', label: '质量分倒序' }]} /></Form.Item>
      <Button type="primary" onClick={submit}>保存显示顺序</Button>
    </Card>
  )

  const services = (
    <Card>
      {configuration?.missing_items.length ? <Alert showIcon type="warning" message="存在未配置服务" description={`缺失配置：${configuration.missing_items.join('、')}。页面不会显示密钥或其他敏感值。`} /> : <Alert showIcon type="success" message="服务配置完整" />}
      <div className="service-status-grid">
        {Object.entries(configuration?.services ?? {}).map(([key, ready]) => (
          <div key={key}><Text>{serviceLabels[key] ?? key}</Text><Tag color={ready ? 'green' : 'default'}>{ready ? '已配置' : '未配置'}</Tag></div>
        ))}
      </div>
    </Card>
  )

  return (
    <Space orientation="vertical" size="large" className="full-width">
      <PageHeader title="系统设置" description="管理采集调度、评分分层、显示顺序和本地服务状态。" extra={<Tag color="blue">本地配置</Tag>} />
      <Form form={form} layout="vertical" initialValues={settings}>
        <Tabs items={[
          { key: 'schedule', label: '采集调度', children: schedule },
          { key: 'score', label: '评分分层', children: score },
          { key: 'order', label: '显示顺序', children: order },
          { key: 'services', label: '服务状态', children: services },
        ]} />
      </Form>
    </Space>
  )
}
