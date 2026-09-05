"""Fixture-backed collectors used to enforce contracts without real network access."""

from collections.abc import Mapping
from datetime import datetime

from ai_intel.domain.source import (
    CollectedItem,
    CollectionBatch,
    CollectionFailure,
    CollectionStage,
    CollectionStatus,
    CollectionWindow,
    SourceConfig,
    effective_publication,
    truncate_for_model,
)
from ai_intel.ports.collectors import (
    FixtureGateway,
    GitHubFixtureGateway,
    MediaDownloadPort,
    SpeechRecognitionPort,
)


class FixtureContractError(ValueError):
    pass


def _text(payload: Mapping[str, object], key: str, *, required: bool = True) -> str:
    value = payload.get(key)
    if isinstance(value, str) and (value or not required):
        return value
    if not required and value is None:
        return ""
    raise FixtureContractError(f"fixture field {key} must be a string")


def _published(payload: Mapping[str, object]) -> datetime | None:
    value = payload.get("published_at")
    if value is None:
        return None
    if not isinstance(value, datetime):
        raise FixtureContractError("fixture field published_at must be a datetime or null")
    return value


def _integer(payload: Mapping[str, object], key: str) -> int:
    value = payload.get(key)
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    raise FixtureContractError(f"fixture field {key} must be an integer")


def _base_item(
    source: SourceConfig,
    payload: Mapping[str, object],
    window: CollectionWindow,
    *,
    raw_content: str,
    status: CollectionStatus = CollectionStatus.COLLECTED,
    metadata: Mapping[str, object] | None = None,
) -> CollectedItem | None:
    published, unknown = effective_publication(_published(payload), window.started_at)
    if not window.contains(None if unknown else published, window.started_at):
        return None
    return CollectedItem(
        external_id=_text(payload, "external_id"),
        source_id=source.source_id,
        source_type=source.source_type,
        title=_text(payload, "title"),
        url=_text(payload, "url"),
        author=_text(payload, "author", required=False) or None,
        published_at=published,
        first_seen_at=window.started_at,
        published_at_unknown=unknown,
        raw_content=raw_content,
        model_input=truncate_for_model(raw_content, source.truncate_chars),
        status=status,
        metadata={} if metadata is None else metadata,
    )


class WebCollector:
    def __init__(self, gateway: FixtureGateway) -> None:
        self.gateway = gateway

    def collect(self, source: SourceConfig, window: CollectionWindow) -> CollectionBatch:
        try:
            payloads = self.gateway.load(source)
        except Exception as exc:
            return CollectionBatch(
                (),
                (
                    CollectionFailure(
                        source.source_id, CollectionStage.FETCH, str(exc), window.started_at
                    ),
                ),
            )

        items: list[CollectedItem] = []
        failures: list[CollectionFailure] = []
        for payload in payloads:
            try:
                content = _text(payload, "content")
            except FixtureContractError as exc:
                try:
                    metadata = _base_item(
                        source,
                        payload,
                        window,
                        raw_content="",
                        status=CollectionStatus.METADATA_ONLY,
                        metadata={"extraction_failed": True},
                    )
                except (FixtureContractError, TypeError, ValueError) as metadata_exc:
                    failures.append(
                        CollectionFailure(
                            source.source_id,
                            CollectionStage.EXTRACT,
                            str(metadata_exc),
                            window.started_at,
                        )
                    )
                else:
                    if metadata is not None:
                        items.append(metadata)
                    failures.append(
                        CollectionFailure(
                            source.source_id, CollectionStage.EXTRACT, str(exc), window.started_at
                        )
                    )
                continue
            try:
                item = _base_item(source, payload, window, raw_content=content)
                if item is not None:
                    items.append(item)
            except (FixtureContractError, TypeError, ValueError) as exc:
                failures.append(
                    CollectionFailure(
                        source.source_id, CollectionStage.EXTRACT, str(exc), window.started_at
                    )
                )
        return CollectionBatch(tuple(items), tuple(failures))


class RssCollector(WebCollector):
    pass


class VideoTranscriptCollector:
    def __init__(
        self,
        gateway: FixtureGateway,
        media_downloader: MediaDownloadPort,
        speech_recognizer: SpeechRecognitionPort,
    ) -> None:
        self.gateway = gateway
        self._media_downloader = media_downloader
        self._speech_recognizer = speech_recognizer

    def collect(self, source: SourceConfig, window: CollectionWindow) -> CollectionBatch:
        items: list[CollectedItem] = []
        failures: list[CollectionFailure] = []
        try:
            payloads = self.gateway.load(source)
        except Exception as exc:
            return CollectionBatch(
                (),
                (
                    CollectionFailure(
                        source.source_id, CollectionStage.FETCH, str(exc), window.started_at
                    ),
                ),
            )
        for payload in payloads:
            try:
                transcript = payload.get("official_english_transcript")
                description = _text(payload, "description", required=False)
                has_transcript = isinstance(transcript, str) and bool(transcript.strip())
                raw = str(transcript) if has_transcript else description
                item = _base_item(
                    source,
                    payload,
                    window,
                    raw_content=raw,
                    status=(
                        CollectionStatus.COLLECTED
                        if has_transcript
                        else CollectionStatus.METADATA_ONLY
                    ),
                    metadata={"official_english_transcript": has_transcript},
                )
                if item is not None:
                    items.append(item)
            except (FixtureContractError, TypeError, ValueError) as exc:
                failures.append(
                    CollectionFailure(
                        source.source_id, CollectionStage.EXTRACT, str(exc), window.started_at
                    )
                )
        return CollectionBatch(tuple(items), tuple(failures))


class GitHubCollector:
    def __init__(self, gateway: GitHubFixtureGateway, whitelist: tuple[str, ...] = ()) -> None:
        self.gateway = gateway
        self.whitelist = whitelist

    def collect(self, source: SourceConfig, window: CollectionWindow) -> CollectionBatch:
        return self.collect_discovery(source, window, self.whitelist)

    def collect_discovery(
        self,
        source: SourceConfig,
        window: CollectionWindow,
        whitelist: tuple[str, ...],
    ) -> CollectionBatch:
        discovered: dict[str, tuple[Mapping[str, object], set[str]]] = {}
        failures: list[CollectionFailure] = []
        for period, rule in (("daily", "daily_trending"), ("weekly", "weekly_trending")):
            try:
                for payload in self.gateway.ranking(period):
                    if payload.get("ai_relevant") is not True:
                        continue
                    repository = _text(payload, "repository")
                    current_payload, rules = discovered.get(repository, (payload, set()))
                    rules.add(rule)
                    rules.add("ai_relevance")
                    discovered[repository] = (current_payload, rules)
            except Exception as exc:
                failures.append(
                    CollectionFailure(
                        source.source_id,
                        CollectionStage.RANKING,
                        f"{period}: {exc}",
                        window.started_at,
                    )
                )
        for repository in whitelist:
            try:
                payload = self.gateway.project(repository)
                current_payload, rules = discovered.get(repository, (payload, set()))
                rules.add("whitelist")
                discovered[repository] = (current_payload, rules)
            except Exception as exc:
                failures.append(
                    CollectionFailure(
                        source.source_id, CollectionStage.FETCH, str(exc), window.started_at
                    )
                )

        items: list[CollectedItem] = []
        for repository, (payload, rules) in sorted(discovered.items()):
            try:
                readme = _text(payload, "readme")
                item = _base_item(
                    source,
                    payload,
                    window,
                    raw_content=readme,
                    metadata={
                        "repository": repository,
                        "stars": _integer(payload, "stars"),
                        "response_id": _text(payload, "response_id"),
                        "discovery_rules": sorted(rules),
                    },
                )
                if item is not None:
                    items.append(item)
            except (FixtureContractError, TypeError, ValueError) as exc:
                failures.append(
                    CollectionFailure(
                        source.source_id, CollectionStage.EXTRACT, str(exc), window.started_at
                    )
                )
        return CollectionBatch(tuple(items), tuple(failures))
