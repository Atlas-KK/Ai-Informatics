"""Source-based viewpoint aggregation; coverage is never factual confidence."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ViewpointEvidence:
    statement: str
    normalized_statement: str
    source_id: str


@dataclass(frozen=True, slots=True)
class ViewpointAggregate:
    statement: str
    source_ids: tuple[str, ...]
    supporting_source_count: int
    valid_source_count: int
    source_coverage_ratio: float


def aggregate_viewpoints(
    evidence: tuple[ViewpointEvidence, ...], valid_source_ids: tuple[str, ...]
) -> tuple[ViewpointAggregate, ...]:
    valid_sources = set(valid_source_ids)
    if not valid_sources:
        return ()
    grouped: dict[str, tuple[str, set[str]]] = {}
    for item in evidence:
        if item.source_id not in valid_sources:
            continue
        statement, sources = grouped.setdefault(item.normalized_statement, (item.statement, set()))
        sources.add(item.source_id)
        grouped[item.normalized_statement] = (statement, sources)
    total = len(valid_sources)
    return tuple(
        ViewpointAggregate(
            statement=statement,
            source_ids=tuple(sorted(sources)),
            supporting_source_count=len(sources),
            valid_source_count=total,
            source_coverage_ratio=len(sources) / total,
        )
        for _, (statement, sources) in sorted(grouped.items())
    )
