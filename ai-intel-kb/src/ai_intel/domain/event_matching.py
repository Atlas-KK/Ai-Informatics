"""Deterministic event matching without model or UI state."""

from collections.abc import Sequence
from dataclasses import dataclass
from difflib import SequenceMatcher
from enum import StrEnum
from hashlib import sha256
from uuid import UUID, uuid5

from ai_intel.domain.fingerprint import MatchKeyKind, NormalizedSnapshot

EVENT_NAMESPACE = UUID("3e94e3e3-97fb-4f22-b45a-b61f3bb05aa8")
TITLE_SIMILARITY_THRESHOLD = 0.82
ENTITY_OVERLAP_THRESHOLD = 0.5


class MatchReason(StrEnum):
    NORMALIZED_URL = "NORMALIZED_URL"
    CONTENT_FINGERPRINT = "CONTENT_FINGERPRINT"
    TITLE_AND_ENTITIES = "TITLE_AND_ENTITIES"
    NONE = "NONE"


@dataclass(frozen=True, slots=True)
class MatchResult:
    matched: bool
    reasons: tuple[MatchReason, ...]
    title_similarity: float
    entity_overlap: float


@dataclass(frozen=True, slots=True)
class EventMatchProfile:
    event_id: str
    normalized_title: str
    entities: tuple[str, ...]
    keys: tuple[tuple[MatchKeyKind, str], ...]


def title_similarity(left: str, right: str) -> float:
    return SequenceMatcher(None, left, right, autojunk=False).ratio()


def entity_overlap(left: tuple[str, ...], right: tuple[str, ...]) -> float:
    left_set, right_set = set(left), set(right)
    if not left_set or not right_set:
        return 0.0
    return len(left_set & right_set) / len(left_set | right_set)


def match_snapshots(left: NormalizedSnapshot, right: NormalizedSnapshot) -> MatchResult:
    left_keys = {(key.kind, key.value) for key in left.match_keys}
    right_keys = {(key.kind, key.value) for key in right.match_keys}
    shared = left_keys & right_keys
    reasons: list[MatchReason] = []
    if any(kind == MatchKeyKind.URL for kind, _ in shared):
        reasons.append(MatchReason.NORMALIZED_URL)
    if any(kind == MatchKeyKind.CONTENT for kind, _ in shared):
        reasons.append(MatchReason.CONTENT_FINGERPRINT)
    similarity = title_similarity(left.normalized_title, right.normalized_title)
    overlap = entity_overlap(left.entities, right.entities)
    if similarity >= TITLE_SIMILARITY_THRESHOLD and overlap >= ENTITY_OVERLAP_THRESHOLD:
        reasons.append(MatchReason.TITLE_AND_ENTITIES)
    return MatchResult(
        matched=bool(reasons),
        reasons=tuple(reasons) if reasons else (MatchReason.NONE,),
        title_similarity=similarity,
        entity_overlap=overlap,
    )


def match_snapshot_to_profile(
    snapshot: NormalizedSnapshot, profile: EventMatchProfile
) -> MatchResult:
    snapshot_keys = {(key.kind, key.value) for key in snapshot.match_keys}
    shared = snapshot_keys & set(profile.keys)
    reasons: list[MatchReason] = []
    if any(kind == MatchKeyKind.URL for kind, _ in shared):
        reasons.append(MatchReason.NORMALIZED_URL)
    if any(kind == MatchKeyKind.CONTENT for kind, _ in shared):
        reasons.append(MatchReason.CONTENT_FINGERPRINT)
    similarity = title_similarity(snapshot.normalized_title, profile.normalized_title)
    overlap = entity_overlap(snapshot.entities, profile.entities)
    if similarity >= TITLE_SIMILARITY_THRESHOLD and overlap >= ENTITY_OVERLAP_THRESHOLD:
        reasons.append(MatchReason.TITLE_AND_ENTITIES)
    return MatchResult(
        matched=bool(reasons),
        reasons=tuple(reasons) if reasons else (MatchReason.NONE,),
        title_similarity=similarity,
        entity_overlap=overlap,
    )


def connected_components(
    snapshots: Sequence[NormalizedSnapshot],
) -> tuple[tuple[NormalizedSnapshot, ...], ...]:
    ordered = tuple(sorted(snapshots, key=lambda item: item.snapshot_id))
    parents = list(range(len(ordered)))

    def find(index: int) -> int:
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    def union(left: int, right: int) -> None:
        left_root, right_root = find(left), find(right)
        if left_root != right_root:
            parents[max(left_root, right_root)] = min(left_root, right_root)

    for left in range(len(ordered)):
        for right in range(left + 1, len(ordered)):
            if match_snapshots(ordered[left], ordered[right]).matched:
                union(left, right)
    groups: dict[int, list[NormalizedSnapshot]] = {}
    for index, snapshot in enumerate(ordered):
        groups.setdefault(find(index), []).append(snapshot)
    return tuple(
        tuple(group) for group in sorted(groups.values(), key=lambda values: values[0].snapshot_id)
    )


def stable_event_identity(snapshots: Sequence[NormalizedSnapshot]) -> tuple[str, str]:
    if not snapshots:
        raise ValueError("at least one snapshot is required")
    anchor = min(
        snapshots,
        key=lambda item: (
            item.captured_at,
            item.normalized_url,
            item.content_hash,
            item.normalized_title,
            item.source_id,
        ),
    )
    atomic_keys = sorted({f"{key.kind.value}:{key.value}" for key in anchor.match_keys})
    stable_key = sha256("\n".join(atomic_keys).encode("utf-8")).hexdigest()
    return str(uuid5(EVENT_NAMESPACE, stable_key)), stable_key


def canonical_title(snapshots: Sequence[NormalizedSnapshot]) -> str:
    if not snapshots:
        raise ValueError("at least one snapshot is required")
    return min(snapshots, key=lambda item: (item.normalized_title, item.title)).title
