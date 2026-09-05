export type Tier = 'MUST_READ' | 'IMPORTANT' | 'EXTENDED'

export interface ArchiveItem {
  event_id: string
  version_no: number
  change_type: string
  title: string
  topic: string
  summary: string
  content: string
  content_hash: string
  score_id: string | null
  quality_score: number
  score_version: number
  score_dimensions: Record<string, number>
  tier: Tier
  published_at: string
  source_ids: string[]
  favorite: boolean
  pinned: boolean
  read_state: 'READ' | 'UNREAD'
  trash_state: 'ACTIVE' | 'TRASHED'
  trash_reason: string | null
  note: string
  tags: string[]
}

export interface ArchiveVersion {
  version_no: number
  change_type: string
  canonical_title: string
  summary: string
  content: string
  content_hash: string
  created_at: string
  source_language: 'en' | 'zh' | null
  original_text: string | null
  zh_translation: string | null
  key_conclusions: string[]
  pm_value: string | null
  tags: string[]
  evidence: Array<{
    evidence_id: string
    source_id: string
    url: string
    published_at: string
    viewpoint: string
  }>
}

export interface ArchiveDetail extends ArchiveItem {
  versions: ArchiveVersion[]
  topic_idea: null | { title: string; outline: string[]; hook: string }
}

export interface DashboardData {
  report_date: string
  window_start: string
  total_count: number
  items: ArchiveItem[]
  topic_counts: Record<string, number>
  tier_counts: Record<Tier, number>
  source_counts: Record<string, number>
  change_counts: Record<'NEW' | 'UPDATED', number>
  seven_day_trend: Record<string, number>
  latest_run: PipelineRun | null
  data_complete: boolean
}

export interface AppSettings {
  schedule_time: string
  selection_threshold: number
  tier_caps: Record<Tier, number>
  topic_order: string[]
  default_sort: 'PUBLISHED_DESC' | 'SCORE_DESC'
  updated_at: string
}

export interface PipelineRun {
  run_id: string
  report_date: string
  trigger_type: string
  status: string
  started_at: string
  finished_at: string | null
  attempted_sources: number
  successful_sources: number
  failed_sources: number
  archived_count: number
  pending_count: number
  error_code: string | null
  retry_count: number
}

export interface SourceRecord {
  source_id: string
  name: string
  source_type: 'WEB' | 'RSS' | 'GITHUB' | 'VIDEO'
  url: string
  topic: string
  authority_level: number
  truncate_chars: 10000 | 20000 | 50000
  state: 'ACTIVE' | 'PAUSED' | 'DELETED'
}

export interface ExpertRecord {
  expert_id: string
  name: string
  source_ids: string[]
  state: 'ACTIVE' | 'PAUSED' | 'DELETED'
}

export interface FeedbackRecord {
  feedback_id: string
  reason: string
  affected_dimension: string
  original_score: number
  created_at: string
}

export interface CalibrationProposal {
  sample_count: number
  uncertainty: string
  proposal: {
    proposal_id: string
    affected_dimensions: string[]
    suggested_weights: Record<string, number>
    estimated_impact: Record<string, unknown>
  }
}

export interface ExtensionResult {
  result_id: string
  title: string
  url: string
  summary: string
  source_name: string
  score: number
}

export interface ConfigurationStatus {
  semantic_search: boolean
  expansion_search: boolean
  intelligence_processing: boolean
  retry_executor: boolean
  feishu: boolean
}
