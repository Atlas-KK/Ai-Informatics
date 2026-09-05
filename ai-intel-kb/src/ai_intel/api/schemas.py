"""Foundation HTTP response contracts."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ai_intel.domain.source import SourceState, SourceType


class HealthResponse(BaseModel):
    """Non-sensitive process health information."""

    status: Literal["ok"]
    storage: Literal["ready"]
    phase: Literal["phase7"]


class SourceWriteRequest(BaseModel):
    name: str = Field(min_length=1)
    source_type: SourceType
    url: str
    topic: str = Field(min_length=1)
    authority_level: int = Field(ge=1, le=5)
    truncate_chars: Literal[10000, 20000, 50000] = 20000


class SourceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

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


class StateRequest(BaseModel):
    state: Literal[SourceState.ACTIVE, SourceState.PAUSED]


class ExpertWriteRequest(BaseModel):
    name: str = Field(min_length=1)
    source_ids: tuple[str, ...] = ()


class ExpertResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    expert_id: str
    name: str
    source_ids: tuple[str, ...]
    state: SourceState
    created_at: datetime
    updated_at: datetime


class NoteRequest(BaseModel):
    body: str = Field(max_length=20000)


class UserMetadataRequest(BaseModel):
    favorite: bool | None = None
    pinned: bool | None = None
    read_state: Literal["UNREAD", "READ"] | None = None


class TrashRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


class SettingsRequest(BaseModel):
    schedule_time: str
    selection_threshold: float = Field(ge=0, le=100)
    tier_caps: dict[str, int]
    topic_order: tuple[str, ...]
    default_sort: Literal["PUBLISHED_DESC", "SCORE_DESC"]


class ExpansionSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)


class FeedbackRequest(BaseModel):
    score_id: str
    reason: str = Field(min_length=1, max_length=1000)
    affected_dimension: str
    content_features: dict[str, object] = Field(default_factory=dict)
    removed: bool = True


class ConfirmationRequest(BaseModel):
    confirmed: bool
