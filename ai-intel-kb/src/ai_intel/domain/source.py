"""Source configuration and collection contracts for the Phase 3 boundary."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from types import MappingProxyType
from urllib.parse import urlsplit

DEFAULT_TRUNCATE_CHARS = 20_000
ALLOWED_TRUNCATE_CHARS = frozenset({10_000, 20_000, 50_000})


class SourceType(StrEnum):
    WEB = "WEB"
    RSS = "RSS"
    GITHUB = "GITHUB"
    VIDEO = "VIDEO"
    MANUAL_INBOX = "MANUAL_INBOX"


class SourceState(StrEnum):
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    DELETED = "DELETED"


class CollectionStage(StrEnum):
    FETCH = "FETCH"
    EXTRACT = "EXTRACT"
    RANKING = "RANKING"
    IMPORT = "IMPORT"


class CollectionStatus(StrEnum):
    COLLECTED = "COLLECTED"
    METADATA_ONLY = "METADATA_ONLY"
    DUPLICATE = "DUPLICATE"
    FAILED = "FAILED"


def _require_aware(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must include a timezone")


def _validate_url(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("source URL must be an absolute HTTP(S) URL")
    return value


@dataclass(frozen=True, slots=True)
class SourceDraft:
    name: str
    source_type: SourceType
    url: str
    topic: str
    authority_level: int
    truncate_chars: int = DEFAULT_TRUNCATE_CHARS

    def __post_init__(self) -> None:
        if not self.name.strip() or not self.topic.strip():
            raise ValueError("source name and topic are required")
        if self.source_type is SourceType.MANUAL_INBOX:
            raise ValueError("Manual Inbox is not an automatic source configuration")
        _validate_url(self.url)
        if not 1 <= self.authority_level <= 5:
            raise ValueError("authority_level must be between 1 and 5")
        if self.truncate_chars not in ALLOWED_TRUNCATE_CHARS:
            raise ValueError("truncate_chars must be one of 10000, 20000 or 50000")


@dataclass(frozen=True, slots=True)
class SourceConfig:
    source_id: str
    name: str
    source_type: SourceType
    url: str
    topic: str
    authority_level: int
    truncate_chars: int
    state: SourceState
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class ExpertWhitelistEntry:
    expert_id: str
    name: str
    source_ids: tuple[str, ...]
    state: SourceState
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class CollectionWindow:
    started_at: datetime
    window_start: datetime
    window_end: datetime

    @classmethod
    def from_started_at(cls, started_at: datetime) -> "CollectionWindow":
        _require_aware(started_at, "started_at")
        end = started_at.astimezone(UTC)
        return cls(started_at=end, window_start=end - timedelta(days=7), window_end=end)

    def contains(self, published_at: datetime | None, first_seen_at: datetime) -> bool:
        _require_aware(first_seen_at, "first_seen_at")
        effective = first_seen_at if published_at is None else published_at
        _require_aware(effective, "published_at")
        normalized = effective.astimezone(UTC)
        return self.window_start <= normalized <= self.window_end


@dataclass(frozen=True, slots=True)
class CollectedItem:
    external_id: str
    source_id: str
    source_type: SourceType
    title: str
    url: str
    author: str | None
    published_at: datetime
    first_seen_at: datetime
    published_at_unknown: bool
    raw_content: str
    model_input: str
    status: CollectionStatus
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.external_id or not self.source_id or not self.title.strip():
            raise ValueError("collected item identity and title are required")
        _validate_url(self.url)
        _require_aware(self.published_at, "published_at")
        _require_aware(self.first_seen_at, "first_seen_at")
        if len(self.model_input) > len(self.raw_content):
            raise ValueError("model input cannot exceed the immutable raw content")
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))


@dataclass(frozen=True, slots=True)
class CollectionFailure:
    source_id: str | None
    stage: CollectionStage
    reason: str
    occurred_at: datetime
    retry_count: int = 0

    def __post_init__(self) -> None:
        _require_aware(self.occurred_at, "occurred_at")
        if not self.reason.strip():
            raise ValueError("failure reason is required")


@dataclass(frozen=True, slots=True)
class CollectionBatch:
    items: tuple[CollectedItem, ...]
    failures: tuple[CollectionFailure, ...] = ()


@dataclass(frozen=True, slots=True)
class CollectionRunPlan:
    run_id: str
    window: CollectionWindow
    sources: tuple[SourceConfig, ...]
    automatic_source_count: int


def effective_publication(
    published_at: datetime | None, first_seen_at: datetime
) -> tuple[datetime, bool]:
    _require_aware(first_seen_at, "first_seen_at")
    if published_at is None:
        return first_seen_at.astimezone(UTC), True
    _require_aware(published_at, "published_at")
    return published_at.astimezone(UTC), False


def truncate_for_model(raw_content: str, truncate_chars: int | None) -> str:
    limit = DEFAULT_TRUNCATE_CHARS if truncate_chars is None else truncate_chars
    if limit not in ALLOWED_TRUNCATE_CHARS:
        raise ValueError("truncate_chars must be one of 10000, 20000 or 50000")
    return raw_content[:limit]
