import json
from collections.abc import Iterator
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from ai_intel.application.event_aggregation import EventAggregationService
from ai_intel.config import Settings
from ai_intel.domain.source import CollectedItem, CollectionStatus, SourceType
from ai_intel.foundation import RuntimeContext, close_runtime, initialize_runtime

NOW = datetime(2026, 9, 3, 12, tzinfo=UTC)
REPORT_DATE = date(2026, 9, 3)


@pytest.fixture
def runtime(tmp_path: Path) -> Iterator[RuntimeContext]:
    context = initialize_runtime(Settings(data_dir=tmp_path))
    try:
        yield context
    finally:
        close_runtime(context)


def add_candidate(
    runtime: RuntimeContext,
    suffix: str,
    *,
    title: str,
    content: str,
    source_type: SourceType = SourceType.WEB,
    source_id: str | None = None,
    metadata: dict[str, object] | None = None,
) -> str:
    effective_source = source_id or f"source-{suffix}"
    snapshot_id = runtime.source_repository.save_item(
        None,
        CollectedItem(
            external_id=suffix,
            source_id=effective_source,
            source_type=source_type,
            title=title,
            url=f"https://{suffix}.example.test/item",
            author="Fixture Author",
            published_at=NOW,
            first_seen_at=NOW,
            published_at_unknown=False,
            raw_content=content,
            model_input=content,
            status=CollectionStatus.COLLECTED,
            metadata={
                "viewpoint": f"{title} is relevant",
                "entities": [suffix],
                **(metadata or {}),
            },
        ),
    )
    assert snapshot_id is not None
    result = EventAggregationService(runtime.event_repository).process_snapshot_ids(
        (snapshot_id,), report_date=REPORT_DATE, observed_at=NOW
    )[0]
    assert result.event_id is not None
    return runtime.event_repository.get_current_state(result.event_id).evidence[0].snapshot_id


def aggregate_version_for_snapshot(runtime: RuntimeContext, snapshot_id: str) -> str:
    rows = runtime.intelligence_repository.list_candidate_contexts(REPORT_DATE)
    return next(
        row.aggregate_version_id
        for row in rows
        if snapshot_id in {item.snapshot_id for item in row.evidence}
    )


def processing_response(
    evidence_id: str,
    *,
    language: str = "en",
    topic: str = "大模型与智能体",
    density: float = 90.0,
    innovation: float = 90.0,
    tags: list[str] | None = None,
) -> str:
    return json.dumps(
        {
            "schema_version": "phase5.processing.v1",
            "source_language": language,
            "zh_translation": "中文对照译文" if language == "en" else None,
            "zh_summary": "中文摘要",
            "key_conclusions": [{"text": "可追溯的关键结论", "evidence_ids": [evidence_id]}],
            "pm_value": "可用于 AI 产品决策",
            "primary_topic": topic,
            "tags": tags or ["AI", "fixture"],
            "dimension_scores": {
                "source_authority": 1,
                "timeliness": 1,
                "reach": 1,
                "information_density": density,
                "innovation": innovation,
            },
            "dimension_rationales": {
                "source_authority": "source",
                "timeliness": "time",
                "reach": "reach",
                "information_density": "dense facts",
                "innovation": "new capability",
            },
        },
        ensure_ascii=False,
    )


def topic_idea_response(evidence_id: str, suffix: str = "") -> str:
    return json.dumps(
        {
            "schema_version": "phase5.topic_idea.v1",
            "title": f"选题标题{suffix}",
            "outline": ["背景", "产品启示"],
            "hook": "一个值得关注的变化",
            "support_evidence_ids": [evidence_id],
        },
        ensure_ascii=False,
    )
