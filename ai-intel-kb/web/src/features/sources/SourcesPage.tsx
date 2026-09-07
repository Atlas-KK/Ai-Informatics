import { EditOutlined, PlusOutlined } from '@ant-design/icons'
import {
  Alert,
  Button,
  Card,
  Checkbox,
  Form,
  Input,
  InputNumber,
  message,
  Modal,
  Select,
  Space,
  Table,
  Tabs,
  Tag,
  Typography,
} from 'antd'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { api } from '../../api'
import { ConfirmAction, PageHeader, StatusBadge } from '../../components'
import type {
  AppSettings,
  ExpertRecord,
  GitHubRules,
  SourceOperation,
  SourceRecord,
} from '../../types'

const { Paragraph, Text } = Typography

interface SourcesPageProps {
  sources: SourceRecord[]
  experts: ExpertRecord[]
  settings: AppSettings
  refresh: () => Promise<void>
  settingsSaved: (value: AppSettings) => void
  notify: ReturnType<typeof message.useMessage>[0]
}

export function SourcesPage({
  sources,
  experts,
  settings,
  refresh,
  settingsSaved,
  notify,
}: SourcesPageProps) {
  const [sourceOpen, setSourceOpen] = useState(false)
  const [expertOpen, setExpertOpen] = useState(false)
  const [editingSource, setEditingSource] = useState<SourceRecord | null>(null)
  const [editingExpert, setEditingExpert] = useState<ExpertRecord | null>(null)
  const [operations, setOperations] = useState<SourceOperation[]>([])
  const [sourceForm] = Form.useForm()
  const [expertForm] = Form.useForm()
  const [githubForm] = Form.useForm<GitHubRules>()

  const loadOperations = useCallback(() => {
    void api<SourceOperation[]>('/api/source-operations').then(setOperations).catch(() => setOperations([]))
  }, [])
  useEffect(() => {
    let active = true
    void api<SourceOperation[]>('/api/source-operations')
      .then((value) => { if (active) setOperations(value) })
      .catch(() => { if (active) setOperations([]) })
    return () => { active = false }
  }, [])
  useEffect(() => githubForm.setFieldsValue(settings.github_rules), [githubForm, settings])

  const operationBySource = useMemo(
    () => new Map(operations.map((item) => [item.source_id, item])),
    [operations],
  )
  const reload = async () => {
    await refresh()
    loadOperations()
  }
  const openSource = (value: SourceRecord | null) => {
    setEditingSource(value)
    sourceForm.setFieldsValue(value ?? {
      source_type: 'WEB', authority_level: 3, truncate_chars: 20000,
      topic: settings.topic_order[0],
    })
    setSourceOpen(true)
  }
  const openExpert = (value: ExpertRecord | null) => {
    setEditingExpert(value)
    expertForm.setFieldsValue(value ?? { source_ids: [] })
    setExpertOpen(true)
  }
  const saveSource = async (values: Omit<SourceRecord, 'source_id' | 'state'>) => {
    try {
      await api(editingSource ? `/api/sources/${editingSource.source_id}` : '/api/sources', {
        method: editingSource ? 'PUT' : 'POST', body: JSON.stringify(values),
      })
      setSourceOpen(false)
      await reload()
      void notify.success('来源已保存；截断配置将在下一次采集生效')
    } catch (error) {
      void notify.error(error instanceof Error ? error.message : '来源保存失败')
    }
  }
  const saveExpert = async (values: { name: string; source_ids: string[] }) => {
    try {
      await api(editingExpert ? `/api/experts/${editingExpert.expert_id}` : '/api/experts', {
        method: editingExpert ? 'PUT' : 'POST', body: JSON.stringify(values),
      })
      setExpertOpen(false)
      await reload()
      void notify.success('专家白名单已保存；仅影响后续采集')
    } catch (error) {
      void notify.error(error instanceof Error ? error.message : '专家白名单保存失败')
    }
  }
  const setState = async (
    kind: 'sources' | 'experts', id: string, state: 'ACTIVE' | 'PAUSED',
  ) => {
    await api(`/api/${kind}/${id}/state`, { method: 'POST', body: JSON.stringify({ state }) })
    await reload()
  }
  const remove = async (kind: 'sources' | 'experts', id: string) => {
    await api(`/api/${kind}/${id}`, { method: 'DELETE' })
    await reload()
    void notify.success('已停止后续采集，历史归档保持不变')
  }
  const saveGithub = async (values: GitHubRules) => {
    try {
      const updated = await api<AppSettings>('/api/settings', {
        method: 'PUT', body: JSON.stringify({ ...settings, github_rules: values, updated_at: undefined }),
      })
      settingsSaved(updated)
      void notify.success('GitHub 发现规则已保存，将于下一次采集生效')
    } catch (error) {
      void notify.error(error instanceof Error ? error.message : 'GitHub 规则保存失败')
    }
  }

  const sourceTable = (
    <Card extra={<Button type="primary" icon={<PlusOutlined />} onClick={() => openSource(null)}>新增来源</Button>}>
      <Table
        rowKey="source_id"
        dataSource={sources}
        scroll={{ x: 1280 }}
        columns={[
          { title: '名称', dataIndex: 'name', fixed: 'left', width: 160 },
          { title: '类型', dataIndex: 'source_type', width: 90 },
          { title: '地址', dataIndex: 'url', width: 220, ellipsis: true },
          { title: '专题', dataIndex: 'topic', width: 190 },
          { title: '权威', dataIndex: 'authority_level', width: 70 },
          { title: '模型输入上限', dataIndex: 'truncate_chars', width: 120 },
          {
            title: '最近采集', width: 180,
            render: (_, row: SourceRecord) => {
              const latest = operationBySource.get(row.source_id)?.latest_collection
              return latest ? <Space orientation="vertical" size={0}><Text>{latest.status}</Text><Text type="secondary">{latest.created_at}</Text></Space> : '尚无记录'
            },
          },
          {
            title: '最近失败', width: 180,
            render: (_, row: SourceRecord) => {
              const failure = operationBySource.get(row.source_id)?.latest_failure
              return failure ? <Text type="danger">{failure.stage} · {failure.reason}</Text> : '—'
            },
          },
          { title: '状态', dataIndex: 'state', width: 90, render: (value: string) => <StatusBadge status={value} /> },
          {
            title: '操作', fixed: 'right', width: 245,
            render: (_, row: SourceRecord) => (
              <Space>
                <Button icon={<EditOutlined />} onClick={() => openSource(row)}>编辑</Button>
                <Button onClick={() => void setState('sources', row.source_id, row.state === 'ACTIVE' ? 'PAUSED' : 'ACTIVE')}>{row.state === 'ACTIVE' ? '暂停' : '恢复'}</Button>
                <ConfirmAction title="仅停止后续采集，历史归档不会删除。确认停用？" onConfirm={() => remove('sources', row.source_id)}><Button danger>删除</Button></ConfirmAction>
              </Space>
            ),
          },
        ]}
      />
    </Card>
  )

  const expertTable = (
    <Card extra={<Button type="primary" icon={<PlusOutlined />} onClick={() => openExpert(null)}>新增专家</Button>}>
      <Alert showIcon type="info" message="移除或暂停专家只影响后续采集，既有情报与证据仍保留。" />
      <Table
        className="section-table"
        rowKey="expert_id"
        dataSource={experts}
        columns={[
          { title: '姓名', dataIndex: 'name' },
          { title: '关联来源', dataIndex: 'source_ids', render: (value: string[]) => value.map((id) => sources.find((item) => item.source_id === id)?.name ?? id).join('、') || '—' },
          { title: '状态', dataIndex: 'state', render: (value: string) => <StatusBadge status={value} /> },
          {
            title: '操作',
            render: (_, row: ExpertRecord) => (
              <Space>
                <Button onClick={() => openExpert(row)}>编辑</Button>
                <Button onClick={() => void setState('experts', row.expert_id, row.state === 'ACTIVE' ? 'PAUSED' : 'ACTIVE')}>{row.state === 'ACTIVE' ? '暂停' : '恢复'}</Button>
                <ConfirmAction title="停止该专家的后续采集？历史情报不会删除。" onConfirm={() => remove('experts', row.expert_id)}><Button danger>删除</Button></ConfirmAction>
              </Space>
            ),
          },
        ]}
      />
    </Card>
  )

  const githubRules = (
    <Card>
      <Alert showIcon type="info" message="榜单不可用时仍执行白名单采集并记录失败；7 日 Star 增长基于本地快照计算，历史不足时会明确标注。" />
      <Form form={githubForm} layout="vertical" initialValues={settings.github_rules} onFinish={(values) => void saveGithub(values)}>
        <Form.Item label="发现规则">
          <Space orientation="vertical">
            <Form.Item name="daily_trending" valuePropName="checked" noStyle><Checkbox>GitHub 日榜</Checkbox></Form.Item>
            <Form.Item name="weekly_trending" valuePropName="checked" noStyle><Checkbox>GitHub 周榜</Checkbox></Form.Item>
            <Form.Item name="seven_day_star_growth" valuePropName="checked" noStyle><Checkbox>本地 7 日 Star 增长</Checkbox></Form.Item>
            <Form.Item name="ai_relevance" valuePropName="checked" noStyle><Checkbox>AI 相关性过滤</Checkbox></Form.Item>
          </Space>
        </Form.Item>
        <Form.Item name="whitelist" label="仓库白名单" extra="每项使用 owner/repository 格式；白名单不依赖榜单结果。">
          <Select mode="tags" tokenSeparators={[',', '\n']} placeholder="例如 openai/openai-python" />
        </Form.Item>
        <Button type="primary" htmlType="submit">保存 GitHub 规则</Button>
      </Form>
    </Card>
  )

  return (
    <Space orientation="vertical" size="large" className="full-width">
      <PageHeader title="来源管理" description="管理来源、专家白名单及 GitHub 发现规则。删除仅停止后续采集。" />
      <Tabs items={[
        { key: 'sources', label: '信息源', children: sourceTable },
        { key: 'experts', label: '专家白名单', children: expertTable },
        { key: 'github', label: 'GitHub 规则', children: githubRules },
      ]} />
      <Modal title={editingSource ? '编辑来源' : '新增来源'} open={sourceOpen} onCancel={() => setSourceOpen(false)} onOk={() => sourceForm.submit()} destroyOnHidden forceRender>
        <Form form={sourceForm} layout="vertical" onFinish={(values) => void saveSource(values)}>
          <Form.Item name="name" label="名称" rules={[{ required: true, whitespace: true }]}><Input /></Form.Item>
          <Form.Item name="source_type" label="类型" rules={[{ required: true }]}><Select options={['WEB', 'RSS', 'GITHUB', 'VIDEO'].map((value) => ({ value }))} /></Form.Item>
          <Form.Item name="url" label="URL" rules={[{ required: true, type: 'url' }]}><Input /></Form.Item>
          <Form.Item name="topic" label="专题" rules={[{ required: true }]}><Select options={settings.topic_order.map((value) => ({ value }))} /></Form.Item>
          <Form.Item name="authority_level" label="权威等级" rules={[{ required: true }]}><InputNumber min={1} max={5} /></Form.Item>
          <Form.Item name="truncate_chars" label="模型输入上限" extra="仅影响下一次模型输入，原始快照与历史归档不会被截断。"><Select options={[10000, 20000, 50000].map((value) => ({ value }))} /></Form.Item>
          <Form.Item noStyle shouldUpdate={(before, after) => before.source_type !== after.source_type}>
            {({ getFieldValue }) => getFieldValue('source_type') === 'VIDEO' ? <Paragraph type="secondary">视频仅采集节目元数据及官方英文字幕；无官方英文字幕时只保留公开元数据，不下载音视频、不执行 ASR。</Paragraph> : null}
          </Form.Item>
        </Form>
      </Modal>
      <Modal title={editingExpert ? '编辑专家' : '新增专家'} open={expertOpen} onCancel={() => setExpertOpen(false)} onOk={() => expertForm.submit()} destroyOnHidden forceRender>
        <Form form={expertForm} layout="vertical" onFinish={(values) => void saveExpert(values)}>
          <Form.Item name="name" label="姓名" rules={[{ required: true, whitespace: true }]}><Input /></Form.Item>
          <Form.Item name="source_ids" label="关联来源"><Select mode="multiple" options={sources.map((item) => ({ value: item.source_id, label: item.name }))} /></Form.Item>
        </Form>
      </Modal>
      <Tag color="blue">本地配置 · 变更于下一次采集生效</Tag>
    </Space>
  )
}
