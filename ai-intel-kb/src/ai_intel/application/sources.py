"""Phase 3 source configuration, collection orchestration and metric services."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4

from ai_intel.domain.source import (
    CollectionBatch,
    CollectionFailure,
    CollectionRunPlan,
    CollectionStage,
    ExpertWhitelistEntry,
    SourceConfig,
    SourceDraft,
    SourceState,
    SourceType,
)
from ai_intel.domain.source_metrics import (
    MetricGrowth,
    MetricSnapshot,
    calculate_seven_day_growth,
)
from ai_intel.infrastructure.db.source_repository import SQLiteSourceRepository
from ai_intel.infrastructure.telemetry.redaction import redact_text
from ai_intel.ports.collectors import Collector


@dataclass(frozen=True, slots=True)
class CollectionRunResult:
    plan: CollectionRunPlan
    saved_snapshot_ids: tuple[str, ...]
    duplicate_count: int
    failures: tuple[CollectionFailure, ...]


class SourceService:
    def __init__(self, repository: SQLiteSourceRepository) -> None:
        self.repository = repository

    def create(self, draft: SourceDraft) -> SourceConfig:
        return self.repository.create_source(draft)

    def update(self, source_id: str, draft: SourceDraft) -> SourceConfig:
        return self.repository.update_source(source_id, draft)

    def pause(self, source_id: str) -> SourceConfig:
        return self.repository.set_source_state(source_id, SourceState.PAUSED)

    def resume(self, source_id: str) -> SourceConfig:
        return self.repository.set_source_state(source_id, SourceState.ACTIVE)

    def delete(self, source_id: str) -> SourceConfig:
        return self.repository.set_source_state(source_id, SourceState.DELETED)

    def list(self, *, include_deleted: bool = False) -> tuple[SourceConfig, ...]:
        return self.repository.list_sources(include_deleted=include_deleted)

    def create_expert(self, name: str, source_ids: tuple[str, ...]) -> ExpertWhitelistEntry:
        return self.repository.create_expert(name, source_ids)

    def update_expert(
        self, expert_id: str, name: str, source_ids: tuple[str, ...]
    ) -> ExpertWhitelistEntry:
        return self.repository.update_expert(expert_id, name, source_ids)

    def set_expert_state(self, expert_id: str, state: SourceState) -> ExpertWhitelistEntry:
        return self.repository.set_expert_state(expert_id, state)

    def list_experts(self, *, include_deleted: bool = False) -> tuple[ExpertWhitelistEntry, ...]:
        return self.repository.list_experts(include_deleted=include_deleted)


class CollectionService:
    def __init__(
        self,
        repository: SQLiteSourceRepository,
        collectors: Mapping[SourceType, Collector],
    ) -> None:
        self.repository = repository
        self.collectors = dict(collectors)

    def plan(self, started_at: datetime) -> CollectionRunPlan:
        return self.repository.plan_run(started_at)

    def execute(self, plan: CollectionRunPlan) -> CollectionRunResult:
        saved: list[str] = []
        failures: list[CollectionFailure] = []
        duplicates = 0
        for source in plan.sources:
            collector = self.collectors.get(source.source_type)
            if collector is None:
                batch = CollectionBatch(
                    (),
                    (
                        CollectionFailure(
                            source.source_id,
                            CollectionStage.FETCH,
                            f"collector is not configured for {source.source_type.value}",
                            plan.window.started_at,
                        ),
                    ),
                )
            else:
                try:
                    batch = collector.collect(source, plan.window)
                except Exception as exc:
                    batch = CollectionBatch(
                        (),
                        (
                            CollectionFailure(
                                source.source_id,
                                CollectionStage.FETCH,
                                redact_text(str(exc)),
                                plan.window.started_at,
                            ),
                        ),
                    )
            snapshot_ids = self.repository.save_batch(plan.run_id, batch)
            saved.extend(snapshot_ids)
            duplicates += len(batch.items) - len(snapshot_ids)
            failures.extend(batch.failures)
        self.repository.finish_run(plan.run_id)
        return CollectionRunResult(plan, tuple(saved), duplicates, tuple(failures))

    def run(self, started_at: datetime) -> CollectionRunResult:
        return self.execute(self.plan(started_at))


class MetricService:
    def __init__(self, repository: SQLiteSourceRepository) -> None:
        self.repository = repository

    def record_and_calculate(
        self,
        *,
        source_id: str,
        subject_key: str,
        metric_type: str,
        observed_at: datetime,
        value: int,
        response_id: str,
    ) -> MetricGrowth:
        current = MetricSnapshot(
            snapshot_id=str(uuid4()),
            source_id=source_id,
            subject_key=subject_key,
            metric_type=metric_type,
            observed_at=observed_at,
            value=value,
            response_id=response_id,
        )
        history = self.repository.metric_history(subject_key, metric_type)
        self.repository.add_metric_snapshot(current)
        return calculate_seven_day_growth(current, history)
