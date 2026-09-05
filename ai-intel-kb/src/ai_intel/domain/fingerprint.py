"""Deterministic normalization and fingerprints for Phase 4 matching."""

import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256
from html.parser import HTMLParser
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from ai_intel.domain.models import content_digest

TRACKING_QUERY_KEYS = frozenset({"fbclid", "gclid", "mc_cid", "mc_eid"})
IGNORED_HTML_TAGS = frozenset({"script", "style", "nav", "header", "footer", "aside"})


class CandidateOrigin(StrEnum):
    COLLECTOR = "COLLECTOR"
    MANUAL_INBOX = "MANUAL_INBOX"
    EXTENDED_SEARCH = "EXTENDED_SEARCH"


class MatchKeyKind(StrEnum):
    URL = "URL"
    CONTENT = "CONTENT"
    TITLE_ENTITIES = "TITLE_ENTITIES"


@dataclass(frozen=True, slots=True, order=True)
class MatchKey:
    kind: MatchKeyKind
    value: str


@dataclass(frozen=True, slots=True)
class SnapshotDraft:
    snapshot_id: str
    source_id: str
    title: str
    url: str
    author: str | None
    published_at: datetime
    raw_content: str
    viewpoint: str
    entities: tuple[str, ...] = ()
    origin: CandidateOrigin = CandidateOrigin.COLLECTOR
    selected_for_ingestion: bool = True
    captured_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class NormalizedSnapshot:
    snapshot_id: str
    source_id: str
    title: str
    normalized_title: str
    normalized_url: str
    normalized_author: str | None
    published_at: datetime
    captured_at: datetime
    normalized_content: str
    content_hash: str
    viewpoint: str
    normalized_viewpoint: str
    entities: tuple[str, ...]
    origin: CandidateOrigin
    selected_for_ingestion: bool
    match_keys: tuple[MatchKey, ...]


class _VisibleTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._ignored_depth = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        if tag.casefold() in IGNORED_HTML_TAGS:
            self._ignored_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() in IGNORED_HTML_TAGS and self._ignored_depth:
            self._ignored_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self._ignored_depth:
            self.parts.append(data)


def _normalized_words(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    normalized = re.sub(r"[^\w\u3400-\u9fff]+", " ", normalized, flags=re.UNICODE)
    return " ".join(normalized.split())


def normalize_title(value: str) -> str:
    result = _normalized_words(value)
    if not result:
        raise ValueError("title must contain searchable characters")
    return result


def normalize_author(value: str | None) -> str | None:
    if value is None or not value.strip():
        return None
    return " ".join(unicodedata.normalize("NFKC", value).split())


def normalize_url(value: str) -> str:
    parsed = urlsplit(value.strip())
    scheme = parsed.scheme.casefold()
    hostname = (parsed.hostname or "").casefold()
    if scheme not in {"http", "https"} or not hostname:
        raise ValueError("URL must be an absolute HTTP(S) URL")
    port = parsed.port
    default_port = (scheme == "http" and port == 80) or (scheme == "https" and port == 443)
    netloc = hostname if port is None or default_port else f"{hostname}:{port}"
    path = re.sub(r"/{2,}", "/", parsed.path or "/")
    if path != "/":
        path = path.rstrip("/")
    query = urlencode(
        sorted(
            (key, value)
            for key, value in parse_qsl(parsed.query, keep_blank_values=True)
            if not key.casefold().startswith("utm_") and key.casefold() not in TRACKING_QUERY_KEYS
        ),
        doseq=True,
    )
    return urlunsplit((scheme, netloc, path, query, ""))


def normalize_content(value: str) -> str:
    parser = _VisibleTextParser()
    parser.feed(value)
    visible = " ".join(parser.parts) if "<" in value and ">" in value else value
    normalized = unicodedata.normalize("NFKC", visible)
    return " ".join(normalized.split())


def normalize_entities(values: Iterable[str]) -> tuple[str, ...]:
    normalized = (_normalized_words(value) for value in values)
    return tuple(sorted({value for value in normalized if value}))


def fingerprint_content(value: str) -> str:
    return content_digest(normalize_content(value))


def normalize_snapshot(draft: SnapshotDraft) -> NormalizedSnapshot:
    if draft.published_at.tzinfo is None or draft.published_at.utcoffset() is None:
        raise ValueError("published_at must include a timezone")
    if not draft.snapshot_id or not draft.source_id or not draft.viewpoint.strip():
        raise ValueError("snapshot, source and viewpoint are required")
    captured_at = draft.published_at if draft.captured_at is None else draft.captured_at
    if captured_at.tzinfo is None or captured_at.utcoffset() is None:
        raise ValueError("captured_at must include a timezone")
    normalized_title = normalize_title(draft.title)
    normalized_url = normalize_url(draft.url)
    normalized_content = normalize_content(draft.raw_content)
    if not normalized_content:
        raise ValueError("normalized content must not be empty")
    entities = normalize_entities(draft.entities)
    content_hash = sha256(normalized_content.encode("utf-8")).hexdigest()
    normalized_viewpoint = _normalized_words(draft.viewpoint)
    keys = [
        MatchKey(MatchKeyKind.URL, normalized_url),
        MatchKey(MatchKeyKind.CONTENT, content_hash),
    ]
    if entities:
        signature = sha256(f"{normalized_title}\0{'|'.join(entities)}".encode()).hexdigest()
        keys.append(MatchKey(MatchKeyKind.TITLE_ENTITIES, signature))
    return NormalizedSnapshot(
        snapshot_id=draft.snapshot_id,
        source_id=draft.source_id,
        title=" ".join(draft.title.split()),
        normalized_title=normalized_title,
        normalized_url=normalized_url,
        normalized_author=normalize_author(draft.author),
        published_at=draft.published_at.astimezone(UTC),
        captured_at=captured_at.astimezone(UTC),
        normalized_content=normalized_content,
        content_hash=content_hash,
        viewpoint=" ".join(draft.viewpoint.split()),
        normalized_viewpoint=normalized_viewpoint,
        entities=entities,
        origin=draft.origin,
        selected_for_ingestion=draft.selected_for_ingestion,
        match_keys=tuple(keys),
    )
