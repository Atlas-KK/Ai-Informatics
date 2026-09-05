"""Daily threshold, deterministic ordering and three-tier assignment."""

from dataclasses import dataclass

from ai_intel.domain.states import Tier


@dataclass(frozen=True, slots=True)
class ScoredCandidate:
    event_id: str
    aggregate_version_id: str
    score_id: str
    total: float
    timeliness: float
    source_authority: float


@dataclass(frozen=True, slots=True)
class RankedCandidate:
    candidate: ScoredCandidate
    rank: int
    tier: Tier


def tier_for_rank(rank: int) -> Tier:
    if not 1 <= rank <= 50:
        raise ValueError("daily rank must be between 1 and 50")
    if rank <= 10:
        return Tier.MUST_READ
    if rank <= 30:
        return Tier.IMPORTANT
    return Tier.EXTENDED


def select_daily(
    candidates: tuple[ScoredCandidate, ...], *, threshold: float = 70.0, limit: int = 50
) -> tuple[RankedCandidate, ...]:
    if not 0 <= threshold <= 100:
        raise ValueError("threshold must be between zero and 100")
    if not 1 <= limit <= 50:
        raise ValueError("daily limit must be between one and 50")
    by_event: dict[str, ScoredCandidate] = {}
    for candidate in candidates:
        if candidate.total < threshold:
            continue
        current = by_event.get(candidate.event_id)
        order = (candidate.total, candidate.timeliness, candidate.source_authority)
        if current is None or order > (
            current.total,
            current.timeliness,
            current.source_authority,
        ):
            by_event[candidate.event_id] = candidate
    ordered = sorted(
        by_event.values(),
        key=lambda item: (-item.total, -item.timeliness, -item.source_authority, item.event_id),
    )[:limit]
    return tuple(
        RankedCandidate(item, rank, tier_for_rank(rank))
        for rank, item in enumerate(ordered, start=1)
    )
