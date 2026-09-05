"""Explainable, deterministic five-dimension quality scoring."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType

from ai_intel.domain.ai_processing import DIMENSIONS

DEFAULT_WEIGHTS: Mapping[str, float] = MappingProxyType(
    {
        "source_authority": 0.30,
        "timeliness": 0.25,
        "reach": 0.15,
        "information_density": 0.15,
        "innovation": 0.15,
    }
)


@dataclass(frozen=True, slots=True)
class ScoringConfig:
    version: int
    weights: Mapping[str, float]
    source_authority_overrides: Mapping[str, float]
    missing_reach_fallback: float = 70.0

    def __post_init__(self) -> None:
        if self.version < 1:
            raise ValueError("scoring config version must be positive")
        if set(self.weights) != set(DIMENSIONS):
            raise ValueError("scoring config must contain exactly five dimensions")
        if abs(sum(self.weights.values()) - 1.0) > 0.000001:
            raise ValueError("scoring weights must sum to one")
        if any(value < 0 or value > 1 for value in self.weights.values()):
            raise ValueError("scoring weights must be between zero and one")
        if any(value < 0 or value > 100 for value in self.source_authority_overrides.values()):
            raise ValueError("source authority overrides must be between zero and 100")
        if not 0 <= self.missing_reach_fallback <= 100:
            raise ValueError("missing reach fallback must be between zero and 100")
        object.__setattr__(self, "weights", MappingProxyType(dict(self.weights)))
        object.__setattr__(
            self,
            "source_authority_overrides",
            MappingProxyType(dict(self.source_authority_overrides)),
        )


@dataclass(frozen=True, slots=True)
class ScoringSignals:
    source_ids: tuple[str, ...]
    base_source_authority: float
    newest_published_at: datetime
    scored_at: datetime
    reach_score: float | None
    information_density: float
    innovation: float
    semantic_rationales: Mapping[str, str]
    source_authorities: Mapping[str, float] = MappingProxyType({})

    def __post_init__(self) -> None:
        if any(value < 0 or value > 100 for value in self.source_authorities.values()):
            raise ValueError("source authority signals must be between zero and 100")
        object.__setattr__(
            self,
            "source_authorities",
            MappingProxyType(dict(self.source_authorities)),
        )


@dataclass(frozen=True, slots=True)
class ScoreResult:
    config_version: int
    dimensions: Mapping[str, float]
    rationales: Mapping[str, str]
    total: float


def _timeliness_score(published_at: datetime, scored_at: datetime) -> float:
    if published_at.tzinfo is None or scored_at.tzinfo is None:
        raise ValueError("scoring timestamps must include a timezone")
    age_days = max(0.0, (scored_at - published_at).total_seconds() / 86400)
    if age_days <= 1:
        return 100.0
    if age_days <= 3:
        return 85.0
    if age_days <= 7:
        return 70.0
    return 0.0


def calculate_score(config: ScoringConfig, signals: ScoringSignals) -> ScoreResult:
    values_to_check = [
        signals.base_source_authority,
        signals.information_density,
        signals.innovation,
    ]
    if signals.reach_score is not None:
        values_to_check.append(signals.reach_score)
    if any(value < 0 or value > 100 for value in values_to_check):
        raise ValueError("scoring signals must be between zero and 100")

    per_source_authority = [
        config.source_authority_overrides.get(
            source_id,
            signals.source_authorities.get(source_id, signals.base_source_authority),
        )
        for source_id in signals.source_ids
    ]
    authority = max(per_source_authority, default=signals.base_source_authority)
    timeliness = _timeliness_score(signals.newest_published_at, signals.scored_at)
    reach = config.missing_reach_fallback if signals.reach_score is None else signals.reach_score
    dimensions = {
        "source_authority": round(authority, 2),
        "timeliness": round(timeliness, 2),
        "reach": round(reach, 2),
        "information_density": round(signals.information_density, 2),
        "innovation": round(signals.innovation, 2),
    }
    rationales = {
        "source_authority": "Applied the confirmed source-specific authority parameter.",
        "timeliness": "Calculated from the newest evidence timestamp.",
        "reach": (
            "Used the configured neutral fallback because public interaction data is missing."
            if signals.reach_score is None
            else "Calculated from available public interaction data."
        ),
        "information_density": signals.semantic_rationales["information_density"],
        "innovation": signals.semantic_rationales["innovation"],
    }
    total = round(sum(dimensions[key] * config.weights[key] for key in DIMENSIONS), 2)
    return ScoreResult(
        config.version,
        MappingProxyType(dimensions),
        MappingProxyType(rationales),
        total,
    )
