"""Pure Phase 4 event change detection and immutable version construction."""

from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256

from ai_intel.domain.fingerprint import NormalizedSnapshot
from ai_intel.domain.viewpoints import (
    ViewpointAggregate,
    ViewpointEvidence,
    aggregate_viewpoints,
)


class ChangeType(StrEnum):
    NEW_EVENT = "NEW_EVENT"
    UPDATED = "UPDATED"
    NO_CHANGE = "NO_CHANGE"
    IGNORED = "IGNORED"


class ChangeReason(StrEnum):
    NEW_EVENT = "NEW_EVENT"
    NEW_FACT = "NEW_FACT"
    NEW_VIEWPOINT = "NEW_VIEWPOINT"
    NEW_SOURCE = "NEW_SOURCE"
    NEW_EVIDENCE = "NEW_EVIDENCE"
    CONTENT_CHANGE = "CONTENT_CHANGE"
    EQUIVALENT_CONTENT = "EQUIVALENT_CONTENT"
    NOT_SELECTED = "NOT_SELECTED"


@dataclass(frozen=True, slots=True)
class VersionEvidence:
    snapshot_id: str
    source_id: str
    url: str
    published_at: str
    captured_at: str
    viewpoint: str
    normalized_viewpoint: str
    normalized_content: str
    content_hash: str

    @property
    def semantic_key(self) -> tuple[str, str, str, str]:
        return self.source_id, self.url, self.content_hash, self.normalized_viewpoint


@dataclass(frozen=True, slots=True)
class EventVersionState:
    event_id: str
    version_no: int
    canonical_title: str
    normalized_title: str
    normalized_content: str
    content_hash: str
    entities: tuple[str, ...]
    evidence: tuple[VersionEvidence, ...]


@dataclass(frozen=True, slots=True)
class ChangeDecision:
    change_type: ChangeType
    reasons: tuple[ChangeReason, ...]
    create_version: bool
    needs_scoring: bool


@dataclass(frozen=True, slots=True)
class VersionDraft:
    canonical_title: str
    normalized_title: str
    normalized_content: str
    content_hash: str
    entities: tuple[str, ...]
    evidence: tuple[VersionEvidence, ...]
    viewpoints: tuple[ViewpointAggregate, ...]


def decide_change(
    existing: EventVersionState | None,
    incoming: tuple[NormalizedSnapshot, ...],
) -> ChangeDecision:
    if not incoming:
        return ChangeDecision(
            ChangeType.IGNORED,
            (ChangeReason.NOT_SELECTED,),
            create_version=False,
            needs_scoring=False,
        )
    if existing is None:
        return ChangeDecision(
            ChangeType.NEW_EVENT,
            (ChangeReason.NEW_EVENT,),
            create_version=True,
            needs_scoring=True,
        )

    previous_sources = {item.source_id for item in existing.evidence}
    previous_viewpoints = {item.normalized_viewpoint for item in existing.evidence}
    previous_entities = set(existing.entities)
    previous_by_source_url: dict[tuple[str, str], VersionEvidence] = {}
    for item in existing.evidence:
        key = item.source_id, item.url
        current = previous_by_source_url.get(key)
        if current is None or (item.captured_at, item.snapshot_id) > (
            current.captured_at,
            current.snapshot_id,
        ):
            previous_by_source_url[key] = item
    previous_snapshot_ids = {item.snapshot_id for item in existing.evidence}
    previous_evidence = {item.semantic_key for item in existing.evidence}
    reasons: set[ChangeReason] = set()
    if any(item.source_id not in previous_sources for item in incoming):
        reasons.add(ChangeReason.NEW_SOURCE)
    if any(
        (
            item.source_id,
            item.normalized_url,
            item.content_hash,
            item.normalized_viewpoint,
        )
        not in previous_evidence
        for item in incoming
    ):
        reasons.add(ChangeReason.NEW_EVIDENCE)
    if any(item.normalized_viewpoint not in previous_viewpoints for item in incoming):
        reasons.add(ChangeReason.NEW_VIEWPOINT)
    if any(set(item.entities) - previous_entities for item in incoming):
        reasons.add(ChangeReason.NEW_FACT)
    if any(
        item.snapshot_id not in previous_snapshot_ids
        and (current_evidence := previous_by_source_url.get((item.source_id, item.normalized_url)))
        is not None
        and item.content_hash != current_evidence.content_hash
        for item in incoming
    ):
        reasons.add(ChangeReason.CONTENT_CHANGE)
    if not reasons:
        return ChangeDecision(
            ChangeType.NO_CHANGE,
            (ChangeReason.EQUIVALENT_CONTENT,),
            create_version=False,
            needs_scoring=False,
        )
    return ChangeDecision(
        ChangeType.UPDATED,
        tuple(sorted(reasons, key=str)),
        create_version=True,
        needs_scoring=True,
    )


def build_version(
    canonical_title: str,
    normalized_title: str,
    existing: EventVersionState | None,
    incoming: tuple[NormalizedSnapshot, ...],
) -> VersionDraft:
    evidence_by_snapshot: dict[str, VersionEvidence] = {}
    contents: dict[str, str] = {}
    entities = set(existing.entities if existing else ())
    if existing is not None:
        for prior_evidence in existing.evidence:
            evidence_by_snapshot[prior_evidence.snapshot_id] = prior_evidence
            contents[prior_evidence.content_hash] = prior_evidence.normalized_content
    for snapshot in sorted(incoming, key=lambda value: value.snapshot_id):
        next_evidence = VersionEvidence(
            snapshot_id=snapshot.snapshot_id,
            source_id=snapshot.source_id,
            url=snapshot.normalized_url,
            published_at=snapshot.published_at.isoformat(),
            captured_at=snapshot.captured_at.isoformat(),
            viewpoint=snapshot.viewpoint,
            normalized_viewpoint=snapshot.normalized_viewpoint,
            normalized_content=snapshot.normalized_content,
            content_hash=snapshot.content_hash,
        )
        evidence_by_snapshot.setdefault(next_evidence.snapshot_id, next_evidence)
        contents[snapshot.content_hash] = snapshot.normalized_content
        entities.update(snapshot.entities)
    version_evidence = tuple(
        sorted(
            evidence_by_snapshot.values(),
            key=lambda item: (item.source_id, item.url, item.snapshot_id),
        )
    )
    normalized_content = "\n\n--- source ---\n\n".join(contents[key] for key in sorted(contents))
    viewpoints = aggregate_viewpoints(
        tuple(
            ViewpointEvidence(item.viewpoint, item.normalized_viewpoint, item.source_id)
            for item in version_evidence
        ),
        tuple(sorted({item.source_id for item in version_evidence})),
    )
    return VersionDraft(
        canonical_title=canonical_title,
        normalized_title=normalized_title,
        normalized_content=normalized_content,
        content_hash=sha256(normalized_content.encode("utf-8")).hexdigest(),
        entities=tuple(sorted(entities)),
        evidence=version_evidence,
        viewpoints=viewpoints,
    )
