import {
  ArrowLeftOutlined,
  DeleteOutlined,
  LinkOutlined,
  PushpinFilled,
  PushpinOutlined,
  StarFilled,
  StarOutlined,
} from '@ant-design/icons'
import {
  Alert,
  Button,
  Card,
  Descriptions,
  Divider,
  Form,
  Input,
  Modal,
  Select,
  Space,
  Tabs,
  Tag,
  Timeline,
  Typography,
} from 'antd'
import { useMemo, useState } from 'react'
import { api } from '../../api'
import { scoreDimensionLabels, scoreDimensions, tierColors, tierLabels } from '../../app/labels'
import type { ArchiveDetail } from '../../types'
import { ExpansionSearchPanel } from './expansion/ExpansionSearchPanel'
import { ScoreBreakdown } from './ScoreBreakdown'
import { TopicIdeaPanel } from './topic-ideas/TopicIdeaPanel'

const { Paragraph, Text, Title } = Typography

type Notify = {
  success: (content: string) => unknown
  error: (content: string) => unknown
}

export function IntelDetailPage({
  detail,
  close,
  updateMetadata,
  refresh,
  notify,
}: {
  detail: ArchiveDetail
  close: () => void
  updateMetadata: (values: Record<string, unknown>) => Promise<void>
  refresh: () => Promise<void>
  notify: Notify
}) {
  const latestVersion = detail.versions[0]
  const [selectedVersionNo, setSelectedVersionNo] = useState(latestVersion?.version_no ?? detail.version_no)
  const [note, setNote] = useState(detail.note)
  const [noteSaving, setNoteSaving] = useState(false)
  const [noteError, setNoteError] = useState('')
  const [metadataSaving, setMetadataSaving] = useState(false)
  const [trashOpen, setTrashOpen] = useState(false)
  const [reason, setReason] = useState('')
  const [affectedDimension, setAffectedDimension] = useState(scoreDimensions[3])
  const selectedVersion = useMemo(
    () => detail.versions.find((version) => version.version_no === selectedVersionNo) ?? latestVersion,
    [detail.versions, latestVersion, selectedVersionNo],
  )
  const oldestVersion = detail.versions.at(-1)

  const changeMetadata = async (values: Record<string, unknown>) => {
    setMetadataSaving(true)
    try {
      await updateMetadata(values)
    } catch (error) {
      void notify.error(error instanceof Error ? error.message : '状态更新失败')
    } finally {
      setMetadataSaving(false)
    }
  }
  const saveNote = async () => {
    setNoteSaving(true)
    setNoteError('')
    try {
      await api(`/api/archive/${detail.event_id}/note`, {
        method: 'PUT', body: JSON.stringify({ body: note }),
      })
      void notify.success('笔记已保存')
    } catch (error) {
      setNoteError(error instanceof Error ? error.message : '笔记保存失败，请重试')
    } finally {
      setNoteSaving(false)
    }
  }
  const trash = async () => {
    if (!reason.trim()) return
    if (detail.score_id) {
      await api('/api/feedback', {
        method: 'POST',
        body: JSON.stringify({
          score_id: detail.score_id,
          reason: reason.trim(),
          affected_dimension: affectedDimension,
          content_features: { event_id: detail.event_id },
          removed: true,
        }),
      })
    }
    await api(`/api/archive/${detail.event_id}/trash`, {
      method: 'POST', body: JSON.stringify({ reason: reason.trim() }),
    })
    setTrashOpen(false)
    close()
    await refresh()
  }
  const bodyTab = selectedVersion ? (
    <Space orientation="vertical" size="large" className="full-width">
      <Alert showIcon type="info" title="系统归档内容为只读" description="正文、来源、评分和版本记录不可编辑；个人笔记与收藏状态独立保存。" />
      <Card title="中文摘要与结论">
        <Paragraph className="archive-content">{selectedVersion.summary}</Paragraph>
        {selectedVersion.key_conclusions.length > 0 && (
          <ul>{selectedVersion.key_conclusions.map((item) => <li key={item}>{item}</li>)}</ul>
        )}
        {selectedVersion.pm_value && <Alert type="success" title="产品经理价值" description={selectedVersion.pm_value} />}
      </Card>
      {selectedVersion.source_language === 'en' && (
        <Card title="英文原文与中文译文">
          <Text strong>英文原文</Text>
          <Paragraph className="archive-content">{selectedVersion.original_text || '未提供英文原文'}</Paragraph>
          <Divider />
          <Text strong>中文译文</Text>
          <Paragraph className="archive-content">{selectedVersion.zh_translation || '未提供中文译文'}</Paragraph>
        </Card>
      )}
      <Card title="归档正文"><Paragraph className="archive-content">{selectedVersion.content}</Paragraph></Card>
      <ScoreBreakdown
        total={selectedVersion.quality_score}
        version={selectedVersion.score_version}
        dimensions={selectedVersion.score_dimensions}
        rationales={selectedVersion.score_rationales}
      />
      <Card title="个人笔记" extra={<Tag color="green">用户数据</Tag>}>
        <Input.TextArea aria-label="个人笔记" value={note} rows={5} maxLength={20000} onChange={(event) => setNote(event.target.value)} />
        {noteError && <Alert className="section-alert" showIcon type="error" title="保存失败" description={noteError} />}
        <Button className="note-save" loading={noteSaving} onClick={() => void saveNote()}>保存笔记</Button>
      </Card>
    </Space>
  ) : null

  const evidenceTab = (
    <div className="detail-evidence-grid">
      {(selectedVersion?.evidence ?? []).map((evidence) => (
        <Card
          key={evidence.evidence_id}
          title={evidence.source_name}
          extra={<a href={evidence.url} target="_blank" rel="noreferrer">查看来源 <LinkOutlined /></a>}
        >
          {evidence.source_state === 'DELETED' && (
            <Alert className="section-alert" showIcon type="warning" title="来源配置已删除，本地内容已保留" />
          )}
          <Descriptions
            size="small"
            column={1}
            items={[
              { key: 'type', label: '来源类型', children: evidence.source_type ?? '未知' },
              {
                key: 'published',
                label: '时间',
                children: evidence.published_at_unknown
                  ? `发布时间未知 · 首次发现 ${evidence.first_seen_at ? new Date(evidence.first_seen_at).toLocaleString() : '未提供'}`
                  : new Date(evidence.published_at).toLocaleString(),
              },
              { key: 'viewpoint', label: '观点', children: evidence.viewpoint },
              {
                key: 'coverage',
                label: '来源覆盖率',
                children: evidence.coverage_percent === null
                  ? '未提供'
                  : `${evidence.coverage_percent}%（${evidence.supporting_source_count}/${evidence.valid_source_count} 个来源）`,
              },
            ]}
          />
          <Text type="secondary">覆盖率表示支持该观点的来源占比，不代表观点置信度。</Text>
        </Card>
      ))}
      {!selectedVersion?.evidence.length && <Alert type="warning" title="该版本没有可展示的来源记录" />}
    </div>
  )

  const versionsTab = (
    <Card
      title="历史版本"
      extra={<Space>
        <Button disabled={!oldestVersion} onClick={() => oldestVersion && setSelectedVersionNo(oldestVersion.version_no)}>首版</Button>
        <Button disabled={!latestVersion} onClick={() => latestVersion && setSelectedVersionNo(latestVersion.version_no)}>最新版</Button>
      </Space>}
    >
      <Timeline items={detail.versions.map((version) => ({
        color: version.version_no === selectedVersion?.version_no ? 'blue' : 'gray',
        content: (
          <Button type="link" className="version-link" onClick={() => setSelectedVersionNo(version.version_no)}>
            v{version.version_no} · {version.change_type} · {new Date(version.created_at).toLocaleString()}
          </Button>
        ),
      }))} />
      {selectedVersion && (
        <Alert
          showIcon
          type="info"
          title={`当前查看 v${selectedVersion.version_no}`}
          description={`${selectedVersion.summary}（切换版本不会覆盖个人笔记）`}
        />
      )}
    </Card>
  )

  const ideasTab = (
    <Space orientation="vertical" size="large" className="full-width">
      <TopicIdeaPanel detail={detail} />
      <ExpansionSearchPanel eventId={detail.event_id} initialQuery={detail.title} />
    </Space>
  )

  return (
    <Space orientation="vertical" size="large" className="full-width intel-detail-page">
      <Button type="text" icon={<ArrowLeftOutlined />} onClick={close} className="detail-back">返回</Button>
      <div className="detail-heading">
        <div>
          <Space wrap><Tag color={tierColors[detail.tier]}>{tierLabels[detail.tier]}</Tag><Tag>{detail.topic}</Tag><Tag>v{selectedVersion?.version_no ?? detail.version_no}</Tag></Space>
          <Title level={2}>{detail.title}</Title>
          <Text type="secondary">{new Date(detail.published_at).toLocaleString()} · {detail.source_ids.length} 个来源 · 校验 {detail.content_hash.slice(0, 12)}</Text>
        </div>
        <Space wrap>
          <Button loading={metadataSaving} icon={detail.favorite ? <StarFilled /> : <StarOutlined />} onClick={() => void changeMetadata({ favorite: !detail.favorite })}>{detail.favorite ? '已收藏' : '收藏'}</Button>
          <Button loading={metadataSaving} icon={detail.pinned ? <PushpinFilled /> : <PushpinOutlined />} onClick={() => void changeMetadata({ pinned: !detail.pinned })}>{detail.pinned ? '已置顶' : '置顶'}</Button>
          <Button loading={metadataSaving} onClick={() => void changeMetadata({ read_state: detail.read_state === 'READ' ? 'UNREAD' : 'READ' })}>{detail.read_state === 'READ' ? '标为未读' : '标为已读'}</Button>
          <Button danger icon={<DeleteOutlined />} onClick={() => setTrashOpen(true)}>剔除并移入回收站</Button>
        </Space>
      </div>
      <Tabs
        className="detail-tabs"
        items={[
          { key: 'body', label: '只读正文', children: bodyTab },
          { key: 'evidence', label: '来源与观点', children: evidenceTab },
          { key: 'versions', label: '历史版本', children: versionsTab },
          { key: 'ideas', label: '选题建议', children: ideasTab },
        ]}
      />
      <Modal title="填写剔除原因" open={trashOpen} onCancel={() => setTrashOpen(false)} onOk={() => void trash()} okButtonProps={{ disabled: !reason.trim() }}>
        <Form layout="vertical">
          <Form.Item label="原因" required><Input.TextArea value={reason} maxLength={500} rows={4} onChange={(event) => setReason(event.target.value)} placeholder="请说明内容质量问题" /></Form.Item>
          <Form.Item label="主要影响维度"><Select value={affectedDimension} onChange={setAffectedDimension} options={scoreDimensions.map((value) => ({ value, label: scoreDimensionLabels[value] }))} /></Form.Item>
        </Form>
      </Modal>
    </Space>
  )
}
