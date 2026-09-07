"""End-to-end Phase 6 orchestration with bounded work and local observability."""

from collections import Counter
from datetime import date, datetime

from ai_intel.application.daily_selection import DailySelectionService
from ai_intel.application.delivery import DeliveryService
from ai_intel.application.digest import DigestService
from ai_intel.application.event_aggregation import EventAggregationService
from ai_intel.application.intelligence_processing import (
    IntelligenceProcessingService,
    ProcessingOutcome,
)
from ai_intel.application.sources import CollectionService
from ai_intel.domain.pipeline import PipelineRunResult, PipelineRunStatus, PipelineTrigger
from ai_intel.infrastructure.db.pipeline_repository import Phase6Repository
from ai_intel.infrastructure.scheduler.coordinator import Clock, PipelineCoordinator
from ai_intel.infrastructure.telemetry import TelemetryEventType, TelemetryRecorder


class PipelineService:
    def __init__(
        self,
        *,
        repository: Phase6Repository,
        coordinator: PipelineCoordinator,
        telemetry: TelemetryRecorder,
        collection: CollectionService,
        aggregation: EventAggregationService,
        processing: IntelligenceProcessingService,
        selection: DailySelectionService,
        digest: DigestService,
        clock: Clock,
        delivery: DeliveryService | None = None,
    ) -> None:
        self.repository = repository
        self.coordinator = coordinator
        self.telemetry = telemetry
        self.collection = collection
        self.aggregation = aggregation
        self.processing = processing
        self.selection = selection
        self.digest = digest
        self.clock = clock
        self.delivery = delivery

    def retry_candidate(
        self, aggregate_version_id: str, *, retried_at: datetime
    ) -> ProcessingOutcome:
        """Resume at processing; immutable collection and aggregation inputs are reused."""

        return self.processing.process_candidate(aggregate_version_id, processed_at=retried_at)

    def run(
        self,
        report_date: date,
        *,
        trigger: PipelineTrigger,
        owner_pid: int | None = None,
    ) -> PipelineRunResult:
        run, acquired = self.coordinator.start(report_date, trigger, owner_pid=owner_pid)
        if not acquired:
            self._record_finished(
                run.run_id, run.window.started_at, PipelineRunStatus.REJECTED_DUPLICATE, 0, 0, 0, 0
            )
            return PipelineRunResult(
                run.run_id, PipelineRunStatus.REJECTED_DUPLICATE, 0, 0, 0, 0, 0, None
            )

        attempted = successful = failed = archived = pending = 0
        digest_id: str | None = None
        deadline_exceeded = False
        started_recorded = False
        scored_outcomes: list[tuple[str, str]] = []
        try:
            plan = self.collection.plan(run.window.started_at)
            self._record_started(
                run.run_id,
                trigger,
                run.window.window_start,
                run.window.window_end,
                run.window.started_at,
                tuple(source.source_id for source in plan.sources),
            )
            started_recorded = True
            attempted = plan.automatic_source_count
            collection = self.collection.execute(plan)
            failures_by_source = Counter(
                item.source_id for item in collection.failures if item.source_id is not None
            )
            failure_details = {
                item.source_id: item for item in collection.failures if item.source_id is not None
            }
            collected_rows = self.collection.repository.list_collected(plan.run_id)
            items_by_source = Counter(str(row["source_id"]) for row in collected_rows)
            for source in plan.sources:
                source_failed = source.source_id in failures_by_source
                failure = failure_details.get(source.source_id)
                self.telemetry.record(
                    TelemetryEventType.SOURCE_FETCH_FINISHED,
                    {
                        "run_id": run.run_id,
                        "source_id": source.source_id,
                        "source_type": source.source_type.value,
                        "status": "FAILED" if source_failed else "SUCCESS",
                        "item_count": items_by_source[source.source_id],
                        "error_stage": None if failure is None else failure.stage.value,
                        "failure_reason": None if failure is None else failure.reason,
                        "retry_count": 0 if failure is None else failure.retry_count,
                    },
                    created_at=self.clock.now(),
                    run_id=run.run_id,
                )
            failed = len(failures_by_source)
            successful = attempted - failed
            self.repository.heartbeat(run.run_id, self.clock.now())

            changes = self.aggregation.process_snapshot_ids(
                collection.saved_snapshot_ids,
                report_date=report_date,
                observed_at=self.clock.now(),
            )
            for index, change in enumerate(changes):
                row = collected_rows[min(index, len(collected_rows) - 1)] if collected_rows else {}
                self.telemetry.record(
                    TelemetryEventType.INTEL_CHANGE_DETECTED,
                    {
                        "item_id": str(row.get("snapshot_id", "none")),
                        "event_id": change.event_id or "none",
                        "change_type": change.change_type.value,
                        "source_id": str(row.get("source_id", "none")),
                        "detected_at": self.clock.now().isoformat(),
                    },
                    created_at=self.clock.now(),
                    run_id=run.run_id,
                )

            contexts = self.processing.repository.list_candidate_contexts(report_date)
            pending_contexts = tuple(
                context
                for context in contexts
                if not self.processing.repository.processed_exists(context.aggregate_version_id)
            )
            self.repository.add_work_items(
                run.run_id,
                tuple(item.aggregate_version_id for item in pending_contexts),
                at=self.clock.now(),
            )
            for index, context in enumerate(pending_contexts):
                if self.clock.now() >= run.window.deadline_at:
                    remaining = pending_contexts[index:]
                    for item in remaining:
                        self.repository.mark_work_item(
                            run.run_id,
                            item.aggregate_version_id,
                            status="WAITING_RETRY",
                            stage="PROCESSING",
                            at=self.clock.now(),
                        )
                    pending += len(remaining)
                    deadline_exceeded = True
                    break
                outcome = self.processing.process_context(context, processed_at=self.clock.now())
                self.repository.mark_work_item(
                    run.run_id,
                    context.aggregate_version_id,
                    status="COMPLETED" if outcome.succeeded else "WAITING_RETRY",
                    stage="ARCHIVE" if outcome.succeeded else "PROCESSING",
                    at=self.clock.now(),
                )
                if outcome.succeeded and outcome.score_id is not None:
                    scored_outcomes.append((context.aggregate_version_id, outcome.score_id))
                else:
                    pending += 1
                self.repository.heartbeat(run.run_id, self.clock.now())
                if self.clock.now() >= run.window.deadline_at:
                    remaining = pending_contexts[index + 1 :]
                    for item in remaining:
                        self.repository.mark_work_item(
                            run.run_id,
                            item.aggregate_version_id,
                            status="WAITING_RETRY",
                            stage="PROCESSING",
                            at=self.clock.now(),
                        )
                    pending += len(remaining)
                    deadline_exceeded = True
                    break

            selection = self.selection.select(
                report_date, selected_at=self.clock.now(), archive=True
            )
            tiers_by_score_id = {
                item.candidate.score_id: item.tier.value for item in selection.ranked
            }
            for aggregate_version_id, score_id in scored_outcomes:
                score = self.processing.repository.get_score(score_id)
                processed = self.processing.repository.get_processed(aggregate_version_id)
                self.telemetry.record(
                    TelemetryEventType.INTEL_ITEM_SCORED,
                    {
                        "item_id": aggregate_version_id,
                        "total_score": score.result.total,
                        "dimension_scores": dict(score.result.dimensions),
                        "scoring_version": score.config_version,
                        "topic": processed.primary_topic.value,
                        "tier": tiers_by_score_id.get(score_id),
                    },
                    created_at=self.clock.now(),
                    run_id=run.run_id,
                )
            archived = len(selection.formal_event_ids)
            digest = self.digest.generate(
                report_date,
                selection,
                generated_at=self.clock.now(),
                run_id=run.run_id,
            )
            digest_id = digest.digest_id
            if self.delivery is not None:
                self.delivery.push(digest.digest_id, pushed_at=self.clock.now(), run_id=run.run_id)
            deadline_exceeded = deadline_exceeded or self.clock.now() >= run.window.deadline_at
            if deadline_exceeded:
                final_status = PipelineRunStatus.TIMED_OUT
                error_code = "PIPELINE_DEADLINE_EXCEEDED"
            elif pending:
                final_status = PipelineRunStatus.WAITING_RETRY
                error_code = "WORK_ITEMS_WAITING_RETRY"
            else:
                final_status = PipelineRunStatus.SUCCEEDED
                error_code = None
            self.repository.finish_run(
                run.run_id,
                status=final_status,
                finished_at=self.clock.now(),
                attempted_sources=attempted,
                successful_sources=successful,
                failed_sources=failed,
                archived_count=archived,
                pending_count=pending,
                error_code=error_code,
            )
            self._record_finished(
                run.run_id,
                run.window.started_at,
                final_status,
                attempted,
                successful,
                failed,
                archived,
            )
            return PipelineRunResult(
                run.run_id,
                final_status,
                attempted,
                successful,
                failed,
                archived,
                pending,
                digest_id,
            )
        except Exception as exc:
            if not started_recorded:
                self._record_started(
                    run.run_id,
                    trigger,
                    run.window.window_start,
                    run.window.window_end,
                    run.window.started_at,
                    (),
                )
            self.repository.finish_run(
                run.run_id,
                status=PipelineRunStatus.FAILED,
                finished_at=self.clock.now(),
                attempted_sources=attempted,
                successful_sources=successful,
                failed_sources=failed,
                archived_count=archived,
                pending_count=pending,
                error_code=type(exc).__name__,
            )
            self._record_finished(
                run.run_id,
                run.window.started_at,
                PipelineRunStatus.FAILED,
                attempted,
                successful,
                failed,
                archived,
            )
            raise

    def _record_started(
        self,
        run_id: str,
        trigger: PipelineTrigger,
        window_start: datetime,
        window_end: datetime,
        started_at: datetime,
        enabled_source_ids: tuple[str, ...],
    ) -> None:
        self.telemetry.record(
            TelemetryEventType.PIPELINE_RUN_STARTED,
            {
                "run_id": run_id,
                "trigger_type": trigger.value,
                "window_start": window_start.isoformat(),
                "window_end": window_end.isoformat(),
                "started_at": started_at.isoformat(),
                "enabled_source_ids": list(enabled_source_ids),
            },
            created_at=started_at,
            run_id=run_id,
        )

    def _record_finished(
        self,
        run_id: str,
        started_at: datetime,
        status: PipelineRunStatus,
        attempted: int,
        successful: int,
        failed: int,
        archived: int,
    ) -> None:
        self.telemetry.record(
            TelemetryEventType.PIPELINE_RUN_FINISHED,
            {
                "run_id": run_id,
                "status": status.value,
                "duration": max(0.0, (self.clock.now() - started_at).total_seconds()),
                "attempted_sources": attempted,
                "successful_sources": successful,
                "failed_sources": failed,
                "archived_count": archived,
            },
            created_at=self.clock.now(),
            run_id=run_id,
        )
