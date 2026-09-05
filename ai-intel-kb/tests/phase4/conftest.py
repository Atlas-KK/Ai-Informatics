from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest

from ai_intel.config import Settings
from ai_intel.domain.source import CollectedItem, CollectionStatus, SourceType
from ai_intel.foundation import RuntimeContext, close_runtime, initialize_runtime

OBSERVED = datetime(2026, 9, 3, 12, tzinfo=UTC)


@pytest.fixture
def runtime(tmp_path: Path) -> Iterator[RuntimeContext]:
    context = initialize_runtime(Settings(data_dir=tmp_path))
    try:
        yield context
    finally:
        close_runtime(context)


def add_snapshot(
    runtime: RuntimeContext,
    suffix: str,
    *,
    source_id: str = "source-a",
    source_type: SourceType = SourceType.WEB,
    title: str = "OpenAI releases Agent Kit",
    url: str = "https://news.example.test/agent-kit",
    content: str = "Agent Kit adds deterministic orchestration for AI applications.",
    viewpoint: str = "Agent Kit improves orchestration",
    entities: tuple[str, ...] = ("OpenAI", "Agent Kit"),
    published_at: datetime = OBSERVED,
) -> str:
    snapshot_id = runtime.source_repository.save_item(
        None,
        CollectedItem(
            external_id=suffix,
            source_id=source_id,
            source_type=source_type,
            title=title,
            url=url,
            author="Fixture Analyst",
            published_at=published_at,
            first_seen_at=OBSERVED,
            published_at_unknown=False,
            raw_content=content,
            model_input=content,
            status=CollectionStatus.COLLECTED,
            metadata={"viewpoint": viewpoint, "entities": list(entities)},
        ),
    )
    assert snapshot_id is not None
    return snapshot_id
