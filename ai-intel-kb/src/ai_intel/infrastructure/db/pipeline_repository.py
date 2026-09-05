"""SQLite state for Phase 6 orchestration, digests and delivery outbox."""

import json
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy import Engine, delete, func, insert, select, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from ai_intel.domain.models import content_digest
from ai_intel.domain.pipeline import (
    DeliverySegmentRecord,
    DeliveryStatus,
    DigestRecord,
    PipelineRunRecord,
    PipelineRunStatus,
    PipelineTrigger,
    PipelineWindow,
)
from ai_intel.infrastructure.db.schema import (
    daily_digests,
    delivery_segments,
    pipeline_lock,
    pipeline_runs,
    pipeline_work_items,
)


def _iso(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must include a timezone")
    return value.astimezone(UTC).isoformat()


class Phase6Repository:
    def __init__(self, engine: Engine, data_dir: Path) -> None:
        self.engine = engine
        self.data_dir = data_dir.resolve()

    def try_start_run(
        self,
        *,
        report_date: date,
        trigger: PipelineTrigger,
        started_at: datetime,
        owner_pid: int,
    ) -> tuple[PipelineRunRecord, bool]:
        window = PipelineWindow.from_started_at(started_at)
        run_id = str(uuid4())
        with self.engine.begin() as connection:
            connection.execute(
                insert(pipeline_runs).values(
                    run_id=run_id,
                    report_date=report_date.isoformat(),
                    trigger_type=trigger.value,
                    window_start=_iso(window.window_start),
                    window_end=_iso(window.window_end),
                    deadline_at=_iso(window.deadline_at),
                    status=PipelineRunStatus.REJECTED_DUPLICATE.value,
                    owner_pid=owner_pid,
                    started_at=_iso(started_at),
                    heartbeat_at=_iso(started_at),
                    finished_at=_iso(started_at),
                    attempted_sources=0,
                    successful_sources=0,
                    failed_sources=0,
                    archived_count=0,
                    pending_count=0,
                    error_code="PIPELINE_ALREADY_RUNNING",
                )
            )
            lock_result = connection.execute(
                sqlite_insert(pipeline_lock)
                .values(
                    singleton_id=1,
                    run_id=run_id,
                    owner_pid=owner_pid,
                    acquired_at=_iso(started_at),
                    heartbeat_at=_iso(started_at),
                )
                .on_conflict_do_nothing(index_elements=["singleton_id"])
            )
            acquired = lock_result.rowcount == 1
            status = PipelineRunStatus.RUNNING if acquired else PipelineRunStatus.REJECTED_DUPLICATE
            if acquired:
                connection.execute(
                    update(pipeline_runs)
                    .where(pipeline_runs.c.run_id == run_id)
                    .values(status=status.value, finished_at=None, error_code=None)
                )
        return PipelineRunRecord(run_id, trigger, status, window, started_at), acquired

    def heartbeat(self, run_id: str, at: datetime) -> None:
        with self.engine.begin() as connection:
            result = connection.execute(
                update(pipeline_lock)
                .where(pipeline_lock.c.run_id == run_id)
                .values(heartbeat_at=_iso(at))
            )
            if result.rowcount != 1:
                raise RuntimeError("pipeline run does not own the active lock")
            connection.execute(
                update(pipeline_runs)
                .where(pipeline_runs.c.run_id == run_id)
                .values(heartbeat_at=_iso(at))
            )

    def finish_run(
        self,
        run_id: str,
        *,
        status: PipelineRunStatus,
        finished_at: datetime,
        attempted_sources: int,
        successful_sources: int,
        failed_sources: int,
        archived_count: int,
        pending_count: int,
        error_code: str | None = None,
    ) -> None:
        with self.engine.begin() as connection:
            connection.execute(
                update(pipeline_runs)
                .where(pipeline_runs.c.run_id == run_id)
                .values(
                    status=status.value,
                    heartbeat_at=_iso(finished_at),
                    finished_at=_iso(finished_at),
                    attempted_sources=attempted_sources,
                    successful_sources=successful_sources,
                    failed_sources=failed_sources,
                    archived_count=archived_count,
                    pending_count=pending_count,
                    error_code=error_code,
                )
            )
            connection.execute(delete(pipeline_lock).where(pipeline_lock.c.run_id == run_id))

    def recover_stale_lock(
        self,
        *,
        checked_at: datetime,
        process_is_alive: Callable[[int], bool],
        stale_after: timedelta = timedelta(minutes=5),
    ) -> str | None:
        with self.engine.begin() as connection:
            row = connection.execute(select(pipeline_lock)).mappings().first()
            if row is None:
                return None
            heartbeat = datetime.fromisoformat(str(row["heartbeat_at"]))
            owner_pid = int(row["owner_pid"])
            if checked_at - heartbeat <= stale_after or process_is_alive(owner_pid):
                return None
            run_id = str(row["run_id"])
            connection.execute(
                update(pipeline_runs)
                .where(pipeline_runs.c.run_id == run_id)
                .values(
                    status=PipelineRunStatus.WAITING_RETRY.value,
                    finished_at=_iso(checked_at),
                    heartbeat_at=_iso(checked_at),
                    error_code="STALE_RUN_RECOVERED",
                )
            )
            connection.execute(delete(pipeline_lock).where(pipeline_lock.c.singleton_id == 1))
        return run_id

    def latest_incomplete_run(self) -> Mapping[str, Any] | None:
        later_run = pipeline_runs.alias("later_run")
        resolved_by_later_success = (
            select(later_run.c.run_id)
            .where(
                later_run.c.report_date == pipeline_runs.c.report_date,
                later_run.c.status == PipelineRunStatus.SUCCEEDED.value,
                later_run.c.started_at > pipeline_runs.c.started_at,
            )
            .exists()
        )
        with self.engine.connect() as connection:
            row = (
                connection.execute(
                    select(pipeline_runs)
                    .where(
                        pipeline_runs.c.status.in_(
                            (
                                PipelineRunStatus.WAITING_RETRY.value,
                                PipelineRunStatus.FAILED.value,
                                PipelineRunStatus.TIMED_OUT.value,
                            )
                        ),
                        ~resolved_by_later_success,
                    )
                    .order_by(pipeline_runs.c.started_at.desc())
                    .limit(1)
                )
                .mappings()
                .first()
            )
        return None if row is None else dict(row)

    def completed_report_dates(self) -> frozenset[date]:
        with self.engine.connect() as connection:
            values = connection.execute(
                select(pipeline_runs.c.report_date).where(
                    pipeline_runs.c.status == PipelineRunStatus.SUCCEEDED.value
                )
            ).scalars()
            return frozenset(date.fromisoformat(str(value)) for value in values)

    def get_run(self, run_id: str) -> Mapping[str, Any]:
        with self.engine.connect() as connection:
            row = (
                connection.execute(select(pipeline_runs).where(pipeline_runs.c.run_id == run_id))
                .mappings()
                .one()
            )
        return dict(row)

    def add_work_items(
        self, run_id: str, aggregate_version_ids: Sequence[str], *, at: datetime
    ) -> None:
        if not aggregate_version_ids:
            return
        with self.engine.begin() as connection:
            connection.execute(
                insert(pipeline_work_items),
                [
                    {
                        "work_item_id": str(uuid4()),
                        "run_id": run_id,
                        "aggregate_version_id": version_id,
                        "stage": "PROCESSING",
                        "status": "PENDING",
                        "updated_at": _iso(at),
                    }
                    for version_id in aggregate_version_ids
                ],
            )

    def mark_work_item(
        self, run_id: str, aggregate_version_id: str, *, status: str, stage: str, at: datetime
    ) -> None:
        with self.engine.begin() as connection:
            connection.execute(
                update(pipeline_work_items)
                .where(
                    pipeline_work_items.c.run_id == run_id,
                    pipeline_work_items.c.aggregate_version_id == aggregate_version_id,
                )
                .values(status=status, stage=stage, updated_at=_iso(at))
            )

    def save_digest(
        self,
        *,
        report_date: date,
        selection_run_id: str,
        markdown: str,
        event_ids: tuple[str, ...],
        tier_counts: Mapping[str, int],
        topic_order: tuple[str, ...],
        created_at: datetime,
    ) -> DigestRecord:
        with self.engine.begin() as connection:
            latest = connection.execute(
                select(func.max(daily_digests.c.version_no)).where(
                    daily_digests.c.report_date == report_date.isoformat()
                )
            ).scalar_one()
            version_no = 1 if latest is None else int(latest) + 1
            digest_id = str(uuid4())
            relative_path = Path("digests") / f"{report_date.isoformat()}-v{version_no:04d}.md"
            digest_hash = content_digest(markdown)
            connection.execute(
                insert(daily_digests).values(
                    digest_id=digest_id,
                    report_date=report_date.isoformat(),
                    version_no=version_no,
                    selection_run_id=selection_run_id,
                    markdown=markdown,
                    markdown_path=relative_path.as_posix(),
                    content_hash=digest_hash,
                    event_ids_json=json.dumps(event_ids),
                    tier_counts_json=json.dumps(dict(tier_counts), sort_keys=True),
                    topic_order_json=json.dumps(topic_order, ensure_ascii=False),
                    created_at=_iso(created_at),
                )
            )
        return DigestRecord(
            digest_id,
            report_date.isoformat(),
            version_no,
            selection_run_id,
            markdown,
            relative_path.as_posix(),
            digest_hash,
            event_ids,
            dict(tier_counts),
            topic_order,
        )

    def get_digest(self, digest_id: str) -> DigestRecord:
        with self.engine.connect() as connection:
            row = (
                connection.execute(
                    select(daily_digests).where(daily_digests.c.digest_id == digest_id)
                )
                .mappings()
                .one()
            )
        return DigestRecord(
            digest_id=str(row["digest_id"]),
            report_date=str(row["report_date"]),
            version_no=int(row["version_no"]),
            selection_run_id=str(row["selection_run_id"]),
            markdown=str(row["markdown"]),
            markdown_path=str(row["markdown_path"]),
            content_hash=str(row["content_hash"]),
            event_ids=tuple(json.loads(str(row["event_ids_json"]))),
            tier_counts=dict(json.loads(str(row["tier_counts_json"]))),
            topic_order=tuple(json.loads(str(row["topic_order_json"]))),
        )

    def ensure_segments(
        self, digest_id: str, contents: tuple[str, ...], *, created_at: datetime
    ) -> tuple[DeliverySegmentRecord, ...]:
        existing = self.list_segments(digest_id)
        if existing:
            return existing
        with self.engine.begin() as connection:
            for segment_no, content in enumerate(contents, start=1):
                content_hash = content_digest(content)
                key = content_digest(f"{digest_id}:{segment_no}:{content_hash}")
                connection.execute(
                    insert(delivery_segments).values(
                        segment_id=str(uuid4()),
                        digest_id=digest_id,
                        segment_no=segment_no,
                        idempotency_key=key,
                        content=content,
                        content_hash=content_hash,
                        status=DeliveryStatus.PENDING.value,
                        attempt_count=0,
                        error_code=None,
                        created_at=_iso(created_at),
                        updated_at=_iso(created_at),
                    )
                )
        return self.list_segments(digest_id)

    def list_segments(self, digest_id: str) -> tuple[DeliverySegmentRecord, ...]:
        with self.engine.connect() as connection:
            rows = (
                connection.execute(
                    select(delivery_segments)
                    .where(delivery_segments.c.digest_id == digest_id)
                    .order_by(delivery_segments.c.segment_no)
                )
                .mappings()
                .all()
            )
        return tuple(
            DeliverySegmentRecord(
                segment_id=str(row["segment_id"]),
                digest_id=str(row["digest_id"]),
                segment_no=int(row["segment_no"]),
                idempotency_key=str(row["idempotency_key"]),
                content=str(row["content"]),
                content_hash=str(row["content_hash"]),
                status=DeliveryStatus(str(row["status"])),
                attempt_count=int(row["attempt_count"]),
                error_code=None if row["error_code"] is None else str(row["error_code"]),
            )
            for row in rows
        )

    def mark_segment(
        self,
        segment_id: str,
        *,
        status: DeliveryStatus,
        at: datetime,
        error_code: str | None,
    ) -> None:
        with self.engine.begin() as connection:
            connection.execute(
                update(delivery_segments)
                .where(delivery_segments.c.segment_id == segment_id)
                .values(
                    status=status.value,
                    attempt_count=delivery_segments.c.attempt_count + 1,
                    error_code=error_code,
                    updated_at=_iso(at),
                )
            )
