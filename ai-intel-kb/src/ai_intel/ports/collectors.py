"""External collection contracts; adapters return data and never write formal archives."""

from collections.abc import Mapping
from typing import Protocol

from ai_intel.domain.source import CollectionBatch, CollectionWindow, SourceConfig


class Collector(Protocol):
    def collect(self, source: SourceConfig, window: CollectionWindow) -> CollectionBatch: ...


class FixtureGateway(Protocol):
    def load(self, source: SourceConfig) -> tuple[Mapping[str, object], ...]: ...


class GitHubFixtureGateway(Protocol):
    def ranking(self, period: str) -> tuple[Mapping[str, object], ...]: ...

    def project(self, repository: str) -> Mapping[str, object]: ...


class MediaDownloadPort(Protocol):
    def download_audio(self, url: str) -> bytes: ...


class SpeechRecognitionPort(Protocol):
    def transcribe(self, audio: bytes) -> str: ...
