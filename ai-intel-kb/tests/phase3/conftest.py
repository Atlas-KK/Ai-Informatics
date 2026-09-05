from collections.abc import Iterator, Mapping
from datetime import UTC, datetime
from pathlib import Path

import pytest

from ai_intel.application.sources import SourceService
from ai_intel.config import Settings
from ai_intel.domain.source import SourceConfig, SourceDraft, SourceType
from ai_intel.foundation import RuntimeContext, close_runtime, initialize_runtime


class FixedGateway:
    def __init__(self, payloads: Mapping[str, tuple[Mapping[str, object], ...]]) -> None:
        self.payloads = payloads

    def load(self, source: SourceConfig) -> tuple[Mapping[str, object], ...]:
        return self.payloads[source.source_id]


@pytest.fixture
def runtime(tmp_path: Path) -> Iterator[RuntimeContext]:
    context = initialize_runtime(Settings(data_dir=tmp_path))
    try:
        yield context
    finally:
        close_runtime(context)


@pytest.fixture
def source_service(runtime: RuntimeContext) -> SourceService:
    return SourceService(runtime.source_repository)


def make_source(
    service: SourceService,
    source_type: SourceType,
    *,
    name: str | None = None,
    truncate_chars: int = 20_000,
) -> SourceConfig:
    label = source_type.value.lower()
    return service.create(
        SourceDraft(
            name=name or label,
            source_type=source_type,
            url=f"https://{label}.example.test/feed",
            topic="AI product intelligence",
            authority_level=4,
            truncate_chars=truncate_chars,
        )
    )


def payload(
    external_id: str,
    *,
    published_at: datetime | None = datetime(2026, 9, 1, tzinfo=UTC),
    content: str = "fixed fixture content",
) -> dict[str, object]:
    return {
        "external_id": external_id,
        "title": f"Title {external_id}",
        "url": f"https://content.example.test/{external_id}",
        "author": "Fixture Author",
        "published_at": published_at,
        "content": content,
    }
