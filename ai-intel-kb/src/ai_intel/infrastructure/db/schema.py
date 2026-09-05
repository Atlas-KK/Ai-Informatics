"""SQLAlchemy Core definitions matching the versioned SQLite schema."""

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Float,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
)

metadata = MetaData()

events = Table(
    "events",
    metadata,
    Column("event_id", String(36), primary_key=True),
    Column("canonical_title", Text, nullable=False),
    Column("primary_topic", Text, nullable=False),
    Column("current_version", Integer),
    Column("status", String(20), nullable=False),
    Column("created_at", String(40), nullable=False),
    Column("updated_at", String(40), nullable=False),
    CheckConstraint("status IN ('PROCESSING','READY','WAITING_RETRY')", name="ck_event_status"),
)

event_versions = Table(
    "event_versions",
    metadata,
    Column("version_id", String(36), primary_key=True),
    Column("event_id", ForeignKey("events.event_id", ondelete="CASCADE"), nullable=False),
    Column("version_no", Integer, nullable=False),
    Column("change_type", String(40), nullable=False),
    Column("canonical_title", Text, nullable=False),
    Column("primary_topic", Text, nullable=False),
    Column("content", Text, nullable=False),
    Column("summary", Text, nullable=False),
    Column("content_hash", String(64), nullable=False),
    Column("archive_path", Text, nullable=False),
    Column("created_at", String(40), nullable=False),
    UniqueConstraint("event_id", "version_no", name="uq_event_version"),
    CheckConstraint("version_no > 0", name="ck_version_positive"),
)

raw_snapshots = Table(
    "raw_snapshots",
    metadata,
    Column("snapshot_id", String(36), primary_key=True),
    Column(
        "version_id", ForeignKey("event_versions.version_id", ondelete="CASCADE"), nullable=False
    ),
    Column("source_id", String(100), nullable=False),
    Column("content_hash", String(64), nullable=False),
    Column("raw_path", Text, nullable=False, unique=True),
    Column("first_seen_at", String(40), nullable=False),
)

evidence = Table(
    "evidence",
    metadata,
    Column("evidence_id", String(36), primary_key=True),
    Column(
        "version_id", ForeignKey("event_versions.version_id", ondelete="CASCADE"), nullable=False
    ),
    Column("source_id", String(100), nullable=False),
    Column("url", Text, nullable=False),
    Column("published_at", String(40), nullable=False),
    Column("published_at_original", String(40), nullable=False),
    Column("published_timezone", String(20), nullable=False),
    Column("viewpoint", Text, nullable=False),
    UniqueConstraint("version_id", "source_id", "url", name="uq_version_source_url"),
)

scores = Table(
    "scores",
    metadata,
    Column("score_id", String(36), primary_key=True),
    Column(
        "version_id", ForeignKey("event_versions.version_id", ondelete="CASCADE"), nullable=False
    ),
    Column("config_version", Integer, nullable=False),
    Column("dimensions_json", Text, nullable=False),
    Column("total", Float, nullable=False),
    Column("tier", String(20), nullable=False),
    Column("created_at", String(40), nullable=False),
    UniqueConstraint("version_id", "config_version", name="uq_version_score_config"),
    CheckConstraint("total >= 0 AND total <= 100", name="ck_score_total"),
    CheckConstraint("config_version > 0", name="ck_score_config_positive"),
    CheckConstraint("tier IN ('MUST_READ','IMPORTANT','EXTENDED')", name="ck_score_tier"),
)

user_metadata = Table(
    "user_metadata",
    metadata,
    Column("event_id", ForeignKey("events.event_id", ondelete="CASCADE"), primary_key=True),
    Column("favorite", Boolean, nullable=False, default=False),
    Column("pinned", Boolean, nullable=False, default=False),
    Column("read_state", String(10), nullable=False),
    Column("trash_state", String(10), nullable=False),
    Column("trash_reason", Text),
    Column("updated_at", String(40), nullable=False),
    CheckConstraint("read_state IN ('UNREAD','READ')", name="ck_read_state"),
    CheckConstraint("trash_state IN ('ACTIVE','TRASHED')", name="ck_trash_state"),
    CheckConstraint(
        "(trash_state = 'ACTIVE' AND trash_reason IS NULL) OR "
        "(trash_state = 'TRASHED' AND length(trim(trash_reason)) > 0)",
        name="ck_trash_reason",
    ),
)

notes = Table(
    "notes",
    metadata,
    Column("event_id", ForeignKey("events.event_id", ondelete="CASCADE"), primary_key=True),
    Column("body", Text, nullable=False),
    Column("updated_at", String(40), nullable=False),
)

scoring_configs = Table(
    "scoring_configs",
    metadata,
    Column("config_version", Integer, primary_key=True),
    Column("weights_json", Text, nullable=False),
    Column("source_overrides_json", Text, nullable=False),
    Column("status", String(10), nullable=False),
    Column("created_at", String(40), nullable=False),
    CheckConstraint("config_version > 0", name="ck_scoring_version_positive"),
    CheckConstraint("status IN ('ACTIVE','INACTIVE')", name="ck_scoring_status"),
)

active_scoring_config = Table(
    "active_scoring_config",
    metadata,
    Column("singleton_id", Integer, primary_key=True),
    Column(
        "config_version",
        ForeignKey("scoring_configs.config_version", ondelete="RESTRICT"),
        nullable=False,
    ),
    Column("changed_at", String(40), nullable=False),
    CheckConstraint("singleton_id = 1", name="ck_active_scoring_singleton"),
)

staged_commits = Table(
    "staged_commits",
    metadata,
    Column("commit_id", String(36), primary_key=True),
    Column("event_id", ForeignKey("events.event_id", ondelete="CASCADE"), nullable=False),
    Column("version_no", Integer, nullable=False),
    Column("raw_path", Text, nullable=False),
    Column("raw_stage_path", Text, nullable=False),
    Column("raw_hash", String(64), nullable=False),
    Column("archive_path", Text, nullable=False),
    Column("archive_stage_path", Text, nullable=False),
    Column("archive_hash", String(64), nullable=False),
    Column("state", String(10), nullable=False),
    Column("formalization_selection_id", String(36)),
    Column("formalization_aggregate_version_id", String(36)),
    Column("formalization_archived_at", String(40)),
    Column("created_at", String(40), nullable=False),
    Column("updated_at", String(40), nullable=False),
    UniqueConstraint("event_id", "version_no", name="uq_staged_event_version"),
    CheckConstraint("state IN ('STAGED','READY','ERROR')", name="ck_commit_state"),
)

record_locks = Table(
    "record_locks",
    metadata,
    Column("event_id", ForeignKey("events.event_id", ondelete="CASCADE"), primary_key=True),
    Column("owner_pid", Integer, nullable=False),
    Column("run_id", String(36), nullable=False),
    Column("acquired_at", String(40), nullable=False),
)

recovery_audits = Table(
    "recovery_audits",
    metadata,
    Column("audit_id", String(36), primary_key=True),
    Column("event_id", String(36)),
    Column("action", String(50), nullable=False),
    Column("details_json", Text, nullable=False),
    Column("created_at", String(40), nullable=False),
)

deletion_audits = Table(
    "deletion_audits",
    metadata,
    Column("audit_id", String(36), primary_key=True),
    Column("event_id", String(36), nullable=False, unique=True),
    Column("deletion_reason", Text, nullable=False),
    Column("deleted_at", String(40), nullable=False),
    Column("version_count", Integer, nullable=False),
    Column("content_hashes_json", Text, nullable=False),
    CheckConstraint("version_count > 0", name="ck_deleted_version_count"),
)

projection_manifests = Table(
    "projection_manifests",
    metadata,
    Column("projection_version", Integer, primary_key=True),
    Column("generated_at", String(40), nullable=False),
    Column("source_hashes_json", Text, nullable=False),
    Column("target_paths_json", Text, nullable=False),
)

source_configs = Table(
    "source_configs",
    metadata,
    Column("source_id", String(36), primary_key=True),
    Column("name", Text, nullable=False),
    Column("source_type", String(20), nullable=False),
    Column("url", Text, nullable=False),
    Column("topic", Text, nullable=False),
    Column("authority_level", Integer, nullable=False),
    Column("truncate_chars", Integer, nullable=False),
    Column("state", String(20), nullable=False),
    Column("created_at", String(40), nullable=False),
    Column("updated_at", String(40), nullable=False),
    Column("deleted_at", String(40)),
    CheckConstraint("source_type IN ('WEB','RSS','GITHUB','VIDEO')", name="ck_source_type"),
    CheckConstraint("authority_level BETWEEN 1 AND 5", name="ck_source_authority"),
    CheckConstraint("truncate_chars IN (10000,20000,50000)", name="ck_source_truncate_chars"),
    CheckConstraint("state IN ('ACTIVE','PAUSED','DELETED')", name="ck_source_state"),
)

expert_whitelist = Table(
    "expert_whitelist",
    metadata,
    Column("expert_id", String(36), primary_key=True),
    Column("name", Text, nullable=False),
    Column("state", String(20), nullable=False),
    Column("created_at", String(40), nullable=False),
    Column("updated_at", String(40), nullable=False),
    Column("deleted_at", String(40)),
    CheckConstraint("state IN ('ACTIVE','PAUSED','DELETED')", name="ck_expert_state"),
)

expert_source_links = Table(
    "expert_source_links",
    metadata,
    Column(
        "expert_id",
        String(36),
        ForeignKey("expert_whitelist.expert_id", ondelete="RESTRICT"),
        primary_key=True,
    ),
    Column(
        "source_id",
        String(36),
        ForeignKey("source_configs.source_id", ondelete="RESTRICT"),
        primary_key=True,
    ),
    Column("created_at", String(40), nullable=False),
)

collection_runs = Table(
    "collection_runs",
    metadata,
    Column("run_id", String(36), primary_key=True),
    Column("started_at", String(40), nullable=False),
    Column("window_start", String(40), nullable=False),
    Column("window_end", String(40), nullable=False),
    Column("automatic_source_count", Integer, nullable=False),
    Column("status", String(20), nullable=False),
    CheckConstraint("automatic_source_count >= 0", name="ck_run_source_count"),
    CheckConstraint("status IN ('PLANNED','FINISHED')", name="ck_run_status"),
)

collection_failures = Table(
    "collection_failures",
    metadata,
    Column("failure_id", String(36), primary_key=True),
    Column("run_id", String(36), ForeignKey("collection_runs.run_id", ondelete="RESTRICT")),
    Column("source_id", String(36)),
    Column("stage", String(20), nullable=False),
    Column("reason", Text, nullable=False),
    Column("occurred_at", String(40), nullable=False),
    Column("retry_count", Integer, nullable=False),
    CheckConstraint("stage IN ('FETCH','EXTRACT','RANKING','IMPORT')", name="ck_failure_stage"),
    CheckConstraint("retry_count >= 0", name="ck_failure_retry_count"),
)

collected_raw_snapshots = Table(
    "collected_raw_snapshots",
    metadata,
    Column("snapshot_id", String(36), primary_key=True),
    Column("import_key", String(64), nullable=False, unique=True),
    Column("run_id", String(36), ForeignKey("collection_runs.run_id", ondelete="RESTRICT")),
    Column("source_id", String(100), nullable=False),
    Column("source_type", String(20), nullable=False),
    Column("external_id", Text, nullable=False),
    Column("url", Text, nullable=False),
    Column("title", Text, nullable=False),
    Column("author", Text),
    Column("published_at", String(40), nullable=False),
    Column("published_at_unknown", Boolean, nullable=False),
    Column("first_seen_at", String(40), nullable=False),
    Column("content_hash", String(64), nullable=False),
    Column("raw_path", Text, nullable=False, unique=True),
    Column("model_input", Text, nullable=False),
    Column("metadata_json", Text, nullable=False),
    Column("status", String(20), nullable=False),
    Column("created_at", String(40), nullable=False),
    CheckConstraint(
        "source_type IN ('WEB','RSS','GITHUB','VIDEO','MANUAL_INBOX')",
        name="ck_collected_source_type",
    ),
    CheckConstraint("status IN ('COLLECTED','METADATA_ONLY')", name="ck_collected_status"),
)

source_metric_snapshots = Table(
    "source_metric_snapshots",
    metadata,
    Column("snapshot_id", String(36), primary_key=True),
    Column("source_id", String(36), nullable=False),
    Column("subject_key", Text, nullable=False),
    Column("metric_type", String(30), nullable=False),
    Column("observed_at", String(40), nullable=False),
    Column("value", Integer, nullable=False),
    Column("response_id", Text, nullable=False),
    UniqueConstraint("subject_key", "metric_type", "observed_at", name="uq_metric_observation"),
    CheckConstraint("value >= 0", name="ck_metric_nonnegative"),
)

manual_inbox_imports = Table(
    "manual_inbox_imports",
    metadata,
    Column("import_id", String(36), primary_key=True),
    Column("file_hash", String(64), nullable=False, unique=True),
    Column("file_path", Text, nullable=False),
    Column("status", String(20), nullable=False),
    Column("error", Text),
    Column("retry_count", Integer, nullable=False),
    Column("snapshot_id", String(36)),
    Column("imported_at", String(40), nullable=False),
    CheckConstraint("status IN ('IMPORTED','DUPLICATE','FAILED')", name="ck_manual_status"),
    CheckConstraint("retry_count >= 0", name="ck_manual_retry_count"),
)

event_aggregates = Table(
    "event_aggregates",
    metadata,
    Column("event_id", String(36), primary_key=True),
    Column("stable_key", String(64), nullable=False, unique=True),
    Column("canonical_title", Text, nullable=False),
    Column("normalized_title", Text, nullable=False),
    Column("current_version", Integer, nullable=False),
    Column("created_at", String(40), nullable=False),
    Column("updated_at", String(40), nullable=False),
    CheckConstraint("current_version > 0", name="ck_aggregate_version_positive"),
)

event_match_keys = Table(
    "event_match_keys",
    metadata,
    Column(
        "event_id",
        ForeignKey("event_aggregates.event_id", ondelete="RESTRICT"),
        primary_key=True,
    ),
    Column("key_kind", String(20), primary_key=True),
    Column("key_value", Text, primary_key=True),
    Column("created_at", String(40), nullable=False),
    UniqueConstraint("key_kind", "key_value", name="uq_aggregate_match_key"),
    CheckConstraint("key_kind IN ('URL','CONTENT','TITLE_ENTITIES')", name="ck_match_key_kind"),
)

aggregate_versions = Table(
    "aggregate_versions",
    metadata,
    Column("aggregate_version_id", String(36), primary_key=True),
    Column(
        "event_id",
        ForeignKey("event_aggregates.event_id", ondelete="RESTRICT"),
        nullable=False,
    ),
    Column("version_no", Integer, nullable=False),
    Column("change_type", String(20), nullable=False),
    Column("change_reasons_json", Text, nullable=False),
    Column("canonical_title", Text, nullable=False),
    Column("normalized_title", Text, nullable=False),
    Column("normalized_content", Text, nullable=False),
    Column("content_hash", String(64), nullable=False),
    Column("entities_json", Text, nullable=False),
    Column("created_at", String(40), nullable=False),
    UniqueConstraint("event_id", "version_no", name="uq_aggregate_version"),
    CheckConstraint("version_no > 0", name="ck_aggregate_version_no"),
    CheckConstraint("change_type IN ('NEW_EVENT','UPDATED')", name="ck_aggregate_change_type"),
)

aggregate_evidence = Table(
    "aggregate_evidence",
    metadata,
    Column("evidence_id", String(36), primary_key=True),
    Column(
        "aggregate_version_id",
        ForeignKey("aggregate_versions.aggregate_version_id", ondelete="RESTRICT"),
        nullable=False,
    ),
    Column(
        "upstream_snapshot_id",
        ForeignKey("collected_raw_snapshots.snapshot_id", ondelete="RESTRICT"),
        nullable=False,
    ),
    Column("source_id", String(100), nullable=False),
    Column("url", Text, nullable=False),
    Column("published_at", String(40), nullable=False),
    Column("viewpoint", Text, nullable=False),
    Column("normalized_viewpoint", Text, nullable=False),
    Column("normalized_content", Text, nullable=False),
    Column("content_hash", String(64), nullable=False),
    UniqueConstraint(
        "aggregate_version_id", "upstream_snapshot_id", name="uq_aggregate_evidence_snapshot"
    ),
)

aggregate_viewpoints = Table(
    "aggregate_viewpoints",
    metadata,
    Column("viewpoint_id", String(36), primary_key=True),
    Column(
        "aggregate_version_id",
        ForeignKey("aggregate_versions.aggregate_version_id", ondelete="RESTRICT"),
        nullable=False,
    ),
    Column("statement", Text, nullable=False),
    Column("normalized_statement", Text, nullable=False),
    Column("source_ids_json", Text, nullable=False),
    Column("supporting_source_count", Integer, nullable=False),
    Column("valid_source_count", Integer, nullable=False),
    Column("source_coverage_ratio", Float, nullable=False),
    UniqueConstraint("aggregate_version_id", "normalized_statement", name="uq_aggregate_viewpoint"),
    CheckConstraint(
        "supporting_source_count > 0 AND valid_source_count > 0 "
        "AND supporting_source_count <= valid_source_count",
        name="ck_viewpoint_source_counts",
    ),
    CheckConstraint(
        "source_coverage_ratio >= 0 AND source_coverage_ratio <= 1",
        name="ck_viewpoint_coverage",
    ),
)

daily_event_candidates = Table(
    "daily_event_candidates",
    metadata,
    Column("candidate_id", String(36), primary_key=True),
    Column("report_date", String(10), nullable=False),
    Column(
        "event_id",
        ForeignKey("event_aggregates.event_id", ondelete="RESTRICT"),
        nullable=False,
    ),
    Column(
        "aggregate_version_id",
        ForeignKey("aggregate_versions.aggregate_version_id", ondelete="RESTRICT"),
        nullable=False,
    ),
    Column("change_type", String(20), nullable=False),
    Column("needs_scoring", Boolean, nullable=False),
    Column("created_at", String(40), nullable=False),
    Column("updated_at", String(40), nullable=False),
    UniqueConstraint("report_date", "event_id", name="uq_daily_event_candidate"),
    CheckConstraint("change_type IN ('NEW_EVENT','UPDATED')", name="ck_candidate_change_type"),
)

aggregation_audits = Table(
    "aggregation_audits",
    metadata,
    Column("audit_id", String(36), primary_key=True),
    Column("event_id", String(36)),
    Column("snapshot_ids_json", Text, nullable=False),
    Column("change_type", String(20), nullable=False),
    Column("reasons_json", Text, nullable=False),
    Column("created_at", String(40), nullable=False),
    CheckConstraint(
        "change_type IN ('NEW_EVENT','UPDATED','NO_CHANGE','IGNORED')",
        name="ck_aggregation_audit_type",
    ),
)

ai_processing_results = Table(
    "ai_processing_results",
    metadata,
    Column("result_id", String(36), primary_key=True),
    Column(
        "aggregate_version_id",
        ForeignKey("aggregate_versions.aggregate_version_id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
    ),
    Column("source_language", String(2), nullable=False),
    Column("original_text", Text, nullable=False),
    Column("zh_translation", Text),
    Column("zh_summary", Text, nullable=False),
    Column("key_conclusions_json", Text, nullable=False),
    Column("pm_value", Text, nullable=False),
    Column("primary_topic", Text, nullable=False),
    Column("tags_json", Text, nullable=False),
    Column("dimension_scores_json", Text, nullable=False),
    Column("dimension_rationales_json", Text, nullable=False),
    Column("origin", String(20), nullable=False),
    Column("created_at", String(40), nullable=False),
    CheckConstraint("source_language IN ('en','zh')", name="ck_processing_language"),
    CheckConstraint(
        "origin IN ('COLLECTOR','MANUAL_INBOX','EXTENDED_SEARCH')",
        name="ck_processing_origin",
    ),
    CheckConstraint(
        "primary_topic IN ('大模型与智能体','AI 产品形态与行业应用',"
        "'AI 产品实战','AI 工程安全与可靠性')",
        name="ck_processing_topic",
    ),
)

ai_processing_failures = Table(
    "ai_processing_failures",
    metadata,
    Column("failure_id", String(36), primary_key=True),
    Column(
        "aggregate_version_id",
        ForeignKey("aggregate_versions.aggregate_version_id", ondelete="RESTRICT"),
        nullable=False,
    ),
    Column("stage", String(20), nullable=False),
    Column("error_code", String(50), nullable=False),
    Column("retryable", Boolean, nullable=False),
    Column("created_at", String(40), nullable=False),
    CheckConstraint(
        "stage IN ('FILTER','PROCESSING','SCORING','TOPIC_IDEA')",
        name="ck_ai_failure_stage",
    ),
)

candidate_scores = Table(
    "candidate_scores",
    metadata,
    Column("score_id", String(36), primary_key=True),
    Column(
        "aggregate_version_id",
        ForeignKey("aggregate_versions.aggregate_version_id", ondelete="RESTRICT"),
        nullable=False,
    ),
    Column(
        "processing_result_id",
        ForeignKey("ai_processing_results.result_id", ondelete="RESTRICT"),
        nullable=False,
    ),
    Column(
        "config_version",
        ForeignKey("scoring_configs.config_version", ondelete="RESTRICT"),
        nullable=False,
    ),
    Column("score_revision", Integer, nullable=False),
    Column("dimensions_json", Text, nullable=False),
    Column("rationales_json", Text, nullable=False),
    Column("total", Float, nullable=False),
    Column("created_at", String(40), nullable=False),
    UniqueConstraint(
        "aggregate_version_id",
        "config_version",
        "score_revision",
        name="uq_candidate_score_revision",
    ),
    CheckConstraint("score_revision > 0", name="ck_candidate_score_revision"),
    CheckConstraint("total >= 0 AND total <= 100", name="ck_candidate_score_total"),
)

daily_selection_runs = Table(
    "daily_selection_runs",
    metadata,
    Column("selection_run_id", String(36), primary_key=True),
    Column("report_date", String(10), nullable=False),
    Column(
        "config_version",
        ForeignKey("scoring_configs.config_version", ondelete="RESTRICT"),
        nullable=False,
    ),
    Column("threshold", Float, nullable=False),
    Column("max_items", Integer, nullable=False),
    Column("qualified_count", Integer, nullable=False),
    Column("created_at", String(40), nullable=False),
    CheckConstraint("threshold >= 0 AND threshold <= 100", name="ck_selection_threshold"),
    CheckConstraint("max_items >= 1 AND max_items <= 50", name="ck_selection_limit"),
    CheckConstraint("qualified_count >= 0", name="ck_selection_count"),
)

daily_selections = Table(
    "daily_selections",
    metadata,
    Column("selection_id", String(36), primary_key=True),
    Column(
        "selection_run_id",
        ForeignKey("daily_selection_runs.selection_run_id", ondelete="RESTRICT"),
        nullable=False,
    ),
    Column("event_id", String(36), nullable=False),
    Column(
        "aggregate_version_id",
        ForeignKey("aggregate_versions.aggregate_version_id", ondelete="RESTRICT"),
        nullable=False,
    ),
    Column(
        "score_id",
        ForeignKey("candidate_scores.score_id", ondelete="RESTRICT"),
        nullable=False,
    ),
    Column("rank", Integer, nullable=False),
    Column("tier", String(20), nullable=False),
    Column("created_at", String(40), nullable=False),
    UniqueConstraint("selection_run_id", "event_id", name="uq_selection_event"),
    UniqueConstraint("selection_run_id", "rank", name="uq_selection_rank"),
    CheckConstraint("rank >= 1 AND rank <= 50", name="ck_selection_rank"),
    CheckConstraint("tier IN ('MUST_READ','IMPORTANT','EXTENDED')", name="ck_selection_tier"),
)

formalization_links = Table(
    "formalization_links",
    metadata,
    Column("link_id", String(36), primary_key=True),
    Column(
        "selection_id",
        ForeignKey("daily_selections.selection_id"),
        nullable=False,
        unique=True,
    ),
    Column(
        "aggregate_version_id",
        ForeignKey("aggregate_versions.aggregate_version_id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
    ),
    Column("formal_event_id", String(36), nullable=False),
    Column("formal_version_no", Integer, nullable=False),
    Column("archived_at", String(40), nullable=False),
    UniqueConstraint("formal_event_id", "formal_version_no", name="uq_formalized_version"),
    CheckConstraint("formal_version_no > 0", name="ck_formalized_version"),
)

quality_feedback = Table(
    "quality_feedback",
    metadata,
    Column("feedback_id", String(36), primary_key=True),
    Column(
        "score_id",
        ForeignKey("candidate_scores.score_id", ondelete="RESTRICT"),
        nullable=False,
    ),
    Column("reason", Text, nullable=False),
    Column("affected_dimension", String(30), nullable=False),
    Column("content_features_json", Text, nullable=False),
    Column("original_score", Float, nullable=False),
    Column("outcome", String(20), nullable=False),
    Column("created_at", String(40), nullable=False),
    CheckConstraint("length(trim(reason)) > 0", name="ck_feedback_reason"),
    CheckConstraint("original_score >= 0 AND original_score <= 100", name="ck_feedback_score"),
    CheckConstraint("outcome IN ('REMOVED','KEPT')", name="ck_feedback_outcome"),
)

calibration_proposals = Table(
    "calibration_proposals",
    metadata,
    Column("proposal_id", String(36), primary_key=True),
    Column("base_config_version", ForeignKey("scoring_configs.config_version"), nullable=False),
    Column("sample_count", Integer, nullable=False),
    Column("uncertainty", String(20), nullable=False),
    Column("affected_dimensions_json", Text, nullable=False),
    Column("suggested_weights_json", Text, nullable=False),
    Column("suggested_source_overrides_json", Text, nullable=False),
    Column("estimated_impact_json", Text, nullable=False),
    Column("created_at", String(40), nullable=False),
    CheckConstraint("sample_count > 0", name="ck_calibration_sample_count"),
    CheckConstraint("uncertainty IN ('LOW','MEDIUM','HIGH')", name="ck_calibration_uncertainty"),
)

calibration_decisions = Table(
    "calibration_decisions",
    metadata,
    Column("decision_id", String(36), primary_key=True),
    Column(
        "proposal_id",
        ForeignKey("calibration_proposals.proposal_id"),
        nullable=False,
        unique=True,
    ),
    Column("decision", String(20), nullable=False),
    Column("new_config_version", ForeignKey("scoring_configs.config_version")),
    Column("decided_at", String(40), nullable=False),
    CheckConstraint("decision IN ('CONFIRMED','REJECTED')", name="ck_calibration_decision"),
)

scoring_config_audits = Table(
    "scoring_config_audits",
    metadata,
    Column("audit_id", String(36), primary_key=True),
    Column("old_config_version", Integer),
    Column("new_config_version", ForeignKey("scoring_configs.config_version"), nullable=False),
    Column("action", String(20), nullable=False),
    Column("proposal_id", String(36)),
    Column("created_at", String(40), nullable=False),
    CheckConstraint(
        "action IN ('INITIALIZE','CONFIRM','ROLLBACK')",
        name="ck_scoring_audit_action",
    ),
)

topic_ideas = Table(
    "topic_ideas",
    metadata,
    Column("idea_id", String(36), primary_key=True),
    Column(
        "aggregate_version_id",
        ForeignKey("aggregate_versions.aggregate_version_id", ondelete="RESTRICT"),
        nullable=False,
    ),
    Column("trigger", String(10), nullable=False),
    Column("title", Text, nullable=False),
    Column("outline_json", Text, nullable=False),
    Column("hook", Text, nullable=False),
    Column("support_evidence_ids_json", Text, nullable=False),
    Column("created_at", String(40), nullable=False),
    UniqueConstraint("aggregate_version_id", "trigger", name="uq_topic_idea_trigger"),
    CheckConstraint("trigger IN ('AUTO','MANUAL')", name="ck_topic_idea_trigger"),
)

pipeline_runs = Table(
    "pipeline_runs",
    metadata,
    Column("run_id", String(36), primary_key=True),
    Column("report_date", String(10), nullable=False),
    Column("trigger_type", String(20), nullable=False),
    Column("window_start", String(40), nullable=False),
    Column("window_end", String(40), nullable=False),
    Column("deadline_at", String(40), nullable=False),
    Column("status", String(30), nullable=False),
    Column("owner_pid", Integer, nullable=False),
    Column("started_at", String(40), nullable=False),
    Column("heartbeat_at", String(40), nullable=False),
    Column("finished_at", String(40)),
    Column("attempted_sources", Integer, nullable=False, default=0),
    Column("successful_sources", Integer, nullable=False, default=0),
    Column("failed_sources", Integer, nullable=False, default=0),
    Column("archived_count", Integer, nullable=False, default=0),
    Column("pending_count", Integer, nullable=False, default=0),
    Column("error_code", String(50)),
    CheckConstraint(
        "trigger_type IN ('SCHEDULED','CATCH_UP','MANUAL')", name="ck_pipeline_trigger"
    ),
    CheckConstraint(
        "status IN ('RUNNING','SUCCEEDED','FAILED','TIMED_OUT',"
        "'WAITING_RETRY','REJECTED_DUPLICATE')",
        name="ck_pipeline_status",
    ),
    CheckConstraint(
        "attempted_sources >= 0 AND successful_sources >= 0 AND failed_sources >= 0 "
        "AND archived_count >= 0 AND pending_count >= 0",
        name="ck_pipeline_counts",
    ),
)

pipeline_lock = Table(
    "pipeline_lock",
    metadata,
    Column("singleton_id", Integer, primary_key=True),
    Column("run_id", ForeignKey("pipeline_runs.run_id", ondelete="CASCADE"), nullable=False),
    Column("owner_pid", Integer, nullable=False),
    Column("acquired_at", String(40), nullable=False),
    Column("heartbeat_at", String(40), nullable=False),
    CheckConstraint("singleton_id = 1", name="ck_pipeline_lock_singleton"),
)

pipeline_work_items = Table(
    "pipeline_work_items",
    metadata,
    Column("work_item_id", String(36), primary_key=True),
    Column("run_id", ForeignKey("pipeline_runs.run_id", ondelete="CASCADE"), nullable=False),
    Column(
        "aggregate_version_id",
        ForeignKey("aggregate_versions.aggregate_version_id", ondelete="RESTRICT"),
        nullable=False,
    ),
    Column("stage", String(20), nullable=False),
    Column("status", String(20), nullable=False),
    Column("updated_at", String(40), nullable=False),
    UniqueConstraint("run_id", "aggregate_version_id", name="uq_pipeline_work_item"),
    CheckConstraint("stage IN ('PROCESSING','SCORING','ARCHIVE')", name="ck_pipeline_work_stage"),
    CheckConstraint(
        "status IN ('PENDING','COMPLETED','WAITING_RETRY')", name="ck_pipeline_work_status"
    ),
)

daily_digests = Table(
    "daily_digests",
    metadata,
    Column("digest_id", String(36), primary_key=True),
    Column("report_date", String(10), nullable=False),
    Column("version_no", Integer, nullable=False),
    Column(
        "selection_run_id",
        ForeignKey("daily_selection_runs.selection_run_id", ondelete="RESTRICT"),
        nullable=False,
    ),
    Column("markdown", Text, nullable=False),
    Column("markdown_path", Text, nullable=False, unique=True),
    Column("content_hash", String(64), nullable=False),
    Column("event_ids_json", Text, nullable=False),
    Column("tier_counts_json", Text, nullable=False),
    Column("topic_order_json", Text, nullable=False),
    Column("created_at", String(40), nullable=False),
    UniqueConstraint("report_date", "version_no", name="uq_daily_digest_version"),
    CheckConstraint("version_no > 0", name="ck_daily_digest_version"),
)

delivery_segments = Table(
    "delivery_segments",
    metadata,
    Column("segment_id", String(36), primary_key=True),
    Column("digest_id", ForeignKey("daily_digests.digest_id", ondelete="RESTRICT"), nullable=False),
    Column("segment_no", Integer, nullable=False),
    Column("idempotency_key", String(64), nullable=False, unique=True),
    Column("content", Text, nullable=False),
    Column("content_hash", String(64), nullable=False),
    Column("status", String(20), nullable=False),
    Column("attempt_count", Integer, nullable=False),
    Column("error_code", String(50)),
    Column("created_at", String(40), nullable=False),
    Column("updated_at", String(40), nullable=False),
    UniqueConstraint("digest_id", "segment_no", name="uq_delivery_segment_no"),
    CheckConstraint("segment_no > 0", name="ck_delivery_segment_no"),
    CheckConstraint("attempt_count >= 0", name="ck_delivery_attempt_count"),
    CheckConstraint("status IN ('PENDING','SENT','FAILED')", name="ck_delivery_status"),
)

telemetry_events = Table(
    "telemetry_events",
    metadata,
    Column("telemetry_event_id", String(36), primary_key=True),
    Column("event_type", String(50), nullable=False),
    Column("run_id", String(36)),
    Column("payload_json", Text, nullable=False),
    Column("created_at", String(40), nullable=False),
)

ui_settings = Table(
    "ui_settings",
    metadata,
    Column("singleton_id", Integer, primary_key=True),
    Column("schedule_time", String(5), nullable=False),
    Column("selection_threshold", Float, nullable=False),
    Column("tier_caps_json", Text, nullable=False),
    Column("topic_order_json", Text, nullable=False),
    Column("default_sort", String(20), nullable=False),
    Column("updated_at", String(40), nullable=False),
    CheckConstraint("singleton_id = 1", name="ck_ui_settings_singleton"),
    CheckConstraint(
        "selection_threshold >= 0 AND selection_threshold <= 100",
        name="ck_ui_settings_threshold",
    ),
    CheckConstraint(
        "default_sort IN ('PUBLISHED_DESC','SCORE_DESC')",
        name="ck_ui_settings_sort",
    ),
)

archive_search_documents = Table(
    "archive_search_documents",
    metadata,
    Column("event_id", String(36), primary_key=True),
    Column("title", Text, nullable=False),
    Column("summary", Text, nullable=False),
    Column("content", Text, nullable=False),
    Column("sources", Text, nullable=False),
    Column("tags", Text, nullable=False),
    Column("note", Text, nullable=False),
    Column("source_updated_at", String(40), nullable=False),
)

extension_search_runs = Table(
    "extension_search_runs",
    metadata,
    Column("search_run_id", String(36), primary_key=True),
    Column("event_id", String(36), nullable=False),
    Column("query", Text, nullable=False),
    Column("status", String(20), nullable=False),
    Column("error_code", String(50)),
    Column("created_at", String(40), nullable=False),
    CheckConstraint(
        "status IN ('SUCCEEDED','FAILED','UNAVAILABLE')",
        name="ck_extension_search_status",
    ),
)

extension_search_results = Table(
    "extension_search_results",
    metadata,
    Column("result_id", String(36), primary_key=True),
    Column(
        "search_run_id",
        ForeignKey("extension_search_runs.search_run_id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("title", Text, nullable=False),
    Column("url", Text, nullable=False),
    Column("summary", Text, nullable=False),
    Column("content", Text, nullable=False),
    Column("source_name", Text, nullable=False),
    Column("score", Float, nullable=False),
    Column("formal_event_id", String(36)),
    Column("created_at", String(40), nullable=False),
    UniqueConstraint("search_run_id", "url", name="uq_extension_result_url"),
    CheckConstraint("score >= 0 AND score <= 100", name="ck_extension_result_score"),
)
