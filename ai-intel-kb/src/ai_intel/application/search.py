"""Ports for optional Phase 7 semantic and external search capabilities."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class SearchDocument:
    event_id: str
    title: str
    summary: str
    content: str
    sources: str
    tags: str
    note: str


class SemanticRanker(Protocol):
    """Optional local embedding adapter; absence must degrade to keyword search."""

    def rank(self, query: str, documents: Sequence[SearchDocument]) -> Mapping[str, float]: ...


@dataclass(frozen=True, slots=True)
class ExternalSearchHit:
    title: str
    url: str
    summary: str
    content: str
    source_name: str
    score: float


class ExpansionSearchProvider(Protocol):
    """Explicitly injected adapter; production defaults never access the network."""

    def search(self, query: str) -> Sequence[ExternalSearchHit]: ...
