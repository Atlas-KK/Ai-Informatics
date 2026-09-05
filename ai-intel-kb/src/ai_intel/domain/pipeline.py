"""Phase 6 run, digest and delivery contracts."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum


class PipelineTrigger(StrEnum):
    SCHEDULED = "SCHEDULED"
    CATCH_UP = "CATCH_UP"
    MANUAL = "MANUAL"


class PipelineRunStatus(StrEnum):
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    TIMED_OUT = "TIMED_OUT"
    WAITING_RETRY = "WAITING_RETRY"
    REJECTED_DUPLICATE = "REJECTED_DUPLICATE"


class DeliveryStatus(StrEnum):
    PENDING = "PENDING"
    SENT = "SENT"
    FAILED = "FAILED"


@dataclass(frozen=True, slots=True)
class PipelineWindow:
    started_at: datetime
    window_start: datetime
    window_end: datetime
    deadline_at: datetime

    @classmethod
    def from_started_at(cls, started_at: datetime) -> "PipelineWindow":
        if started_at.tzinfo is None or started_at.utcoffset() is None:
            raise ValueError("pipeline start time must include a timezone")
        return cls(
            started_at=started_at,
            window_start=started_at - timedelta(days=7),
            window_end=started_at,
            deadline_at=started_at + timedelta(hours=2),
        )


@dataclass(frozen=True, slots=True)
class PipelineRunRecord:
    run_id: str
    trigger: PipelineTrigger
    status: PipelineRunStatus
    window: PipelineWindow
    heartbeat_at: datetime


@dataclass(frozen=True, slots=True)
class DigestRecord:
    digest_id: str
    report_date: str
    version_no: int
    selection_run_id: str
    markdown: str
    markdown_path: str
    content_hash: str
    event_ids: tuple[str, ...]
    tier_counts: dict[str, int]
    topic_order: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class DeliverySegmentRecord:
    segment_id: str
    digest_id: str
    segment_no: int
    idempotency_key: str
    content: str
    content_hash: str
    status: DeliveryStatus
    attempt_count: int
    error_code: str | None


@dataclass(frozen=True, slots=True)
class DeliveryResult:
    digest_id: str
    status: str
    successful_segments: int
    failed_segments: int


@dataclass(frozen=True, slots=True)
class PipelineRunResult:
    run_id: str
    status: PipelineRunStatus
    attempted_sources: int
    successful_sources: int
    failed_sources: int
    archived_count: int
    pending_count: int
    digest_id: str | None
