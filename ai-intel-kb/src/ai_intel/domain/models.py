"""Immutable inputs and read models for the Phase 2 archive boundary."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from hashlib import sha256
from types import MappingProxyType
from uuid import UUID

from ai_intel.domain.states import ReadState, Tier, TrashState


def utc_now() -> datetime:
    return datetime.now(UTC)


def content_digest(content: str) -> str:
    """Hash normalized UTF-8 text while preserving the stored source content."""

    normalized = content.replace("\r\n", "\n").replace("\r", "\n")
    return sha256(normalized.encode("utf-8")).hexdigest()


def _require_aware(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must include a timezone")


def _require_uuid4(value: str, name: str) -> None:
    try:
        identifier = UUID(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be a UUID4") from exc
    if identifier.version != 4:
        raise ValueError(f"{name} must be a UUID4")


def _require_uuid(value: str, name: str) -> None:
    try:
        UUID(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be a UUID") from exc


@dataclass(frozen=True, slots=True)
class EvidenceInput:
    source_id: str
    url: str
    published_at: datetime
    viewpoint: str

    def __post_init__(self) -> None:
        _require_aware(self.published_at, "published_at")


@dataclass(frozen=True, slots=True)
class ScoreInput:
    config_version: int
    dimensions: Mapping[str, float]
    total: float
    tier: Tier

    def __post_init__(self) -> None:
        if self.config_version < 1:
            raise ValueError("config_version must be positive")
        if not 0 <= self.total <= 100:
            raise ValueError("total must be between 0 and 100")
        if any(not 0 <= value <= 100 for value in self.dimensions.values()):
            raise ValueError("dimension scores must be between 0 and 100")
        object.__setattr__(self, "dimensions", MappingProxyType(dict(self.dimensions)))


@dataclass(frozen=True, slots=True)
class ArchiveCandidate:
    event_id: str
    snapshot_id: str
    source_id: str
    canonical_title: str
    primary_topic: str
    change_type: str
    raw_content: str
    content: str
    summary: str
    evidence: tuple[EvidenceInput, ...]
    score: ScoreInput
    version_no: int = 1
    created_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        _require_aware(self.created_at, "created_at")
        _require_uuid(self.event_id, "event_id")
        _require_uuid4(self.snapshot_id, "snapshot_id")
        if self.version_no < 1:
            raise ValueError("version_no must be positive")
        if not self.event_id or not self.snapshot_id or not self.source_id:
            raise ValueError("event, snapshot and source identifiers are required")
        if not self.canonical_title.strip() or not self.primary_topic.strip():
            raise ValueError("title and primary topic are required")
        if not self.raw_content or not self.content:
            raise ValueError("raw and archive content are required")
        if not self.evidence:
            raise ValueError("at least one evidence source is required")
        if self.score.total < 70:
            raise ValueError("formal archive candidates must score at least 70")

    @property
    def raw_hash(self) -> str:
        return content_digest(self.raw_content)

    @property
    def content_hash(self) -> str:
        return content_digest(self.content)

    @property
    def source_ids(self) -> tuple[str, ...]:
        return tuple(sorted({item.source_id for item in self.evidence}))


@dataclass(frozen=True, slots=True)
class FormalizationInput:
    """Phase 5 provenance that must become visible with the archive READY switch."""

    selection_id: str
    aggregate_version_id: str
    archived_at: datetime

    def __post_init__(self) -> None:
        _require_aware(self.archived_at, "archived_at")
        _require_uuid4(self.selection_id, "selection_id")
        _require_uuid4(self.aggregate_version_id, "aggregate_version_id")


@dataclass(frozen=True, slots=True)
class UserMetadataRecord:
    event_id: str
    favorite: bool
    pinned: bool
    read_state: ReadState
    trash_state: TrashState
    trash_reason: str | None


@dataclass(frozen=True, slots=True)
class ReadyArchiveRecord:
    event_id: str
    version_no: int
    canonical_title: str
    primary_topic: str
    content: str
    summary: str
    content_hash: str
    archive_path: str
    raw_path: str
    raw_hash: str
    quality_score: float
    score_version: int
    tier: Tier
    source_ids: tuple[str, ...]
    published_at: datetime


@dataclass(frozen=True, slots=True)
class DeletionAuditShell:
    event_id: str
    deletion_reason: str
    deleted_at: datetime
    version_count: int
    content_hashes: tuple[str, ...]
