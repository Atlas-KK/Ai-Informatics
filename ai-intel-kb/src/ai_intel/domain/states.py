"""Storage-facing states whose transitions are enforced by application services."""

from enum import StrEnum


class EventStatus(StrEnum):
    PROCESSING = "PROCESSING"
    READY = "READY"
    WAITING_RETRY = "WAITING_RETRY"


class CommitState(StrEnum):
    STAGED = "STAGED"
    READY = "READY"
    ERROR = "ERROR"


class TrashState(StrEnum):
    ACTIVE = "ACTIVE"
    TRASHED = "TRASHED"


class ReadState(StrEnum):
    UNREAD = "UNREAD"
    READ = "READ"


class Tier(StrEnum):
    MUST_READ = "MUST_READ"
    IMPORTANT = "IMPORTANT"
    EXTENDED = "EXTENDED"


class ScoringConfigStatus(StrEnum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
