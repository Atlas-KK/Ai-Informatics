export type Tier = 'MUST_READ' | 'IMPORTANT' | 'EXTENDED'

export interface TopicTagSummary {
  name: string
  count: number
}

export interface TopicSummary {
  name: string
  count: number
  tags: TopicTagSummary[]
}

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
  quality_score: number | null
  tier: Tier | null
  score_version: number | null
  score_dimensions: Record<string, number>
  score_rationales: Record<string, string>
  scored_at: string | null
  evidence: Array<{
    evidence_id: string
    aggregate_evidence_id?: string | null
    source_id: string
    url: string
    published_at: string
    viewpoint: string
    source_name: string
    source_type: SourceRecord['source_type'] | null
    source_state: SourceRecord['state'] | null
    published_at_unknown: boolean | null
    first_seen_at: string | null
    supporting_source_count: number | null
    valid_source_count: number | null
    coverage_percent: number | null
  }>
}

export interface ArchiveDetail extends ArchiveItem {
  versions: ArchiveVersion[]
  topic_idea: TopicIdea | null
}

export interface TopicIdea {
  idea_id?: string
  trigger?: 'AUTO' | 'MANUAL'
  title: string
  outline: string[]
  hook: string
  support_evidence_ids: string[]
  support_sources?: Array<{
    evidence_id: string
    source_name: string
    url: string
    viewpoint: string
  }>
  created_at?: string
}

export interface TopicIdeaGenerationResponse {
  status: 'SUCCEEDED'
  created: boolean
  idea: TopicIdea
}

export interface DashboardData {
  report_date: string
  window_start: string
  total_count: number
  today_count: number
  items: ArchiveItem[]
  topic_summaries: TopicSummary[]
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
  github_rules: GitHubRules
  updated_at: string
}

export interface GitHubRules {
  daily_trending: boolean
  weekly_trending: boolean
  seven_day_star_growth: boolean
  ai_relevance: boolean
  whitelist: string[]
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
  work_item_count?: number
}

export interface PipelineRunDetail extends PipelineRun {
  window_start: string
  window_end: string
  deadline_at: string
  heartbeat_at: string
  work_items: Array<{
    aggregate_version_id: string
    canonical_title: string
    stage: 'PROCESSING' | 'SCORING' | 'ARCHIVE'
    status: 'PENDING' | 'COMPLETED' | 'WAITING_RETRY'
    updated_at: string
  }>
  retryable_work_items: PipelineRunDetail['work_items']
  source_failures: Array<{
    source_id: string | null
    source_type: string | null
    stage: string
    status: string
    reason: string
    retry_count: number
    occurred_at: string
  }>
  timeline: Array<{
    event_type: string
    created_at: string
    status: string | null
    error_code: string | null
  }>
  digest: null | {
    digest_id: string
    report_date: string
    version_no: number
    markdown_path: string
    created_at: string
    segments: Array<{
      segment_id: string
      segment_no: number
      status: 'PENDING' | 'SENT' | 'FAILED'
      attempt_count: number
      error_code: string | null
      updated_at: string
    }>
  }
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

export interface SourceOperation {
  source_id: string
  latest_collection: null | {
    created_at: string
    status: string
    title: string
  }
  latest_failure: null | {
    stage: string
    reason: string
    occurred_at: string
    retry_count: number
  }
}

export interface ExpertRecord {
  expert_id: string
  name: string
  source_ids: string[]
  state: 'ACTIVE' | 'PAUSED' | 'DELETED'
}

export interface FeedbackRecord {
  feedback_id: string
  score_id: string
  aggregate_version_id: string
  canonical_title: string
  reason: string
  affected_dimension: string
  original_score: number
  outcome: 'REMOVED' | 'KEPT'
  content_features: Record<string, unknown>
  score_version: number
  score_revision: number
  created_at: string
}

export interface CalibrationProposal {
  sample_count: number
  uncertainty: string
  proposal: null | {
    proposal_id: string
    base_config_version: number
    affected_dimensions: string[]
    suggested_weights: Record<string, number>
    estimated_impact: Record<string, unknown>
  }
}

export interface CalibrationWorkbench {
  active_version: number
  configs: Array<{
    version: number
    weights: Record<string, number>
    source_overrides: Record<string, number>
    status: 'ACTIVE' | 'INACTIVE'
    is_active: boolean
    created_at: string
  }>
  proposals: Array<{
    proposal_id: string
    base_config_version: number
    sample_count: number
    uncertainty: string
    affected_dimensions: string[]
    suggested_weights: Record<string, number>
    estimated_impact: Record<string, unknown>
    decision: 'CONFIRMED' | 'REJECTED' | null
    new_config_version: number | null
    created_at: string
    decided_at: string | null
  }>
  audits: Array<{
    audit_id: string
    old_config_version: number | null
    new_config_version: number
    action: 'INITIALIZE' | 'CONFIRM' | 'ROLLBACK'
    created_at: string
  }>
  rescore_targets: Array<{
    aggregate_version_id: string
    canonical_title: string
    score_id: string
    latest_score: number
    config_version: number
    score_revision: number
    score_count: number
    created_at: string
  }>
}

export interface ExtensionResult {
  result_id: string
  title: string
  url: string
  summary: string
  source_name: string
  score: number
}

export interface ExpansionSearchResponse {
  search_run_id: string
  status: 'SUCCEEDED' | 'FAILED' | 'UNAVAILABLE'
  error_code: string | null
  results: ExtensionResult[]
}

export interface ExtensionFavoriteResponse {
  event_id: string
  deduplicated: boolean
}

export interface ConfigurationStatus {
  semantic_search?: boolean
  expansion_search?: boolean
  intelligence_processing?: boolean
  retry_executor?: boolean
  feishu?: boolean
  services: Record<string, boolean>
  missing_items: string[]
}

export interface ScoringConfig {
  version: number
  weights: Record<string, number>
}
