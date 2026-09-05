"""Strict, immutable model-output contracts for Phase 5."""

import json
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from ai_intel.domain.topics import PrimaryTopic


class ProcessingContractError(ValueError):
    pass


class SourceLanguage(StrEnum):
    ENGLISH = "en"
    CHINESE = "zh"


class ConclusionPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    text: Annotated[str, Field(min_length=1)]
    evidence_ids: Annotated[list[str], Field(min_length=1)]

    @field_validator("text")
    @classmethod
    def text_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("conclusion text must not be blank")
        return value.strip()


class ProcessingPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["phase5.processing.v1"]
    source_language: SourceLanguage
    zh_translation: str | None
    zh_summary: Annotated[str, Field(min_length=1)]
    key_conclusions: Annotated[list[ConclusionPayload], Field(min_length=1)]
    pm_value: Annotated[str, Field(min_length=1)]
    primary_topic: PrimaryTopic
    tags: list[str]
    dimension_scores: dict[str, float]
    dimension_rationales: dict[str, str]

    @field_validator("zh_summary", "pm_value")
    @classmethod
    def non_blank_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("text field must not be blank")
        return value.strip()

    @field_validator("tags")
    @classmethod
    def normalize_tags(cls, value: list[str]) -> list[str]:
        normalized = list(dict.fromkeys(item.strip() for item in value if item.strip()))
        if len(normalized) != len(value):
            raise ValueError("tags must be non-blank and unique")
        return normalized


class TopicIdeaPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["phase5.topic_idea.v1"]
    title: Annotated[str, Field(min_length=1)]
    outline: Annotated[list[str], Field(min_length=1)]
    hook: Annotated[str, Field(min_length=1)]
    support_evidence_ids: Annotated[list[str], Field(min_length=1)]

    @field_validator("title", "hook")
    @classmethod
    def non_blank_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("text field must not be blank")
        return value.strip()

    @field_validator("outline")
    @classmethod
    def non_blank_outline(cls, value: list[str]) -> list[str]:
        if any(not item.strip() for item in value):
            raise ValueError("outline entries must not be blank")
        return [item.strip() for item in value]


DIMENSIONS = (
    "source_authority",
    "timeliness",
    "reach",
    "information_density",
    "innovation",
)


def detect_source_language(value: str) -> SourceLanguage:
    cjk = sum("\u3400" <= character <= "\u9fff" for character in value)
    letters = sum(character.isalpha() for character in value)
    return SourceLanguage.CHINESE if letters and cjk / letters >= 0.2 else SourceLanguage.ENGLISH


def parse_processing_payload(
    raw_json: str,
    *,
    source_text: str,
    valid_evidence_ids: frozenset[str],
) -> ProcessingPayload:
    try:
        raw_value = json.loads(raw_json)
        payload = ProcessingPayload.model_validate(raw_value)
    except (json.JSONDecodeError, ValidationError) as exc:
        raise ProcessingContractError("model output does not match processing schema") from exc

    expected_language = detect_source_language(source_text)
    if payload.source_language is not expected_language:
        raise ProcessingContractError("model source language disagrees with the source text")
    if expected_language is SourceLanguage.ENGLISH:
        if payload.zh_translation is None or not payload.zh_translation.strip():
            raise ProcessingContractError("English content requires a Chinese translation")
    elif payload.zh_translation is not None:
        raise ProcessingContractError("Chinese content must not contain a duplicate translation")

    keys = set(payload.dimension_scores)
    rationales = set(payload.dimension_rationales)
    if keys != set(DIMENSIONS) or rationales != set(DIMENSIONS):
        raise ProcessingContractError("all five scoring dimensions and rationales are required")
    if any(not 0 <= value <= 100 for value in payload.dimension_scores.values()):
        raise ProcessingContractError("dimension scores must be between 0 and 100")
    if any(not value.strip() for value in payload.dimension_rationales.values()):
        raise ProcessingContractError("dimension rationales must not be blank")
    for conclusion in payload.key_conclusions:
        if not set(conclusion.evidence_ids).issubset(valid_evidence_ids):
            raise ProcessingContractError("conclusion references unknown evidence")
    return payload


def parse_topic_idea_payload(
    raw_json: str, *, valid_evidence_ids: frozenset[str]
) -> TopicIdeaPayload:
    try:
        raw_value = json.loads(raw_json)
        payload = TopicIdeaPayload.model_validate(raw_value)
    except (json.JSONDecodeError, ValidationError) as exc:
        raise ProcessingContractError("model output does not match topic-idea schema") from exc
    if not set(payload.support_evidence_ids).issubset(valid_evidence_ids):
        raise ProcessingContractError("topic idea references unknown evidence")
    return payload


@dataclass(frozen=True, slots=True)
class ProcessedIntelligence:
    result_id: str
    aggregate_version_id: str
    source_language: SourceLanguage
    original_text: str
    zh_translation: str | None
    zh_summary: str
    key_conclusions: tuple[ConclusionPayload, ...]
    pm_value: str
    primary_topic: PrimaryTopic
    tags: tuple[str, ...]
    dimension_scores: Mapping[str, float]
    dimension_rationales: Mapping[str, str]
    origin: str
