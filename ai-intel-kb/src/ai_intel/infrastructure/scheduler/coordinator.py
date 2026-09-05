"""Run lock, heartbeat, stale-owner recovery and catch-up selection."""

import os
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from typing import Protocol

from ai_intel.domain.pipeline import PipelineRunRecord, PipelineTrigger
from ai_intel.infrastructure.db.pipeline_repository import Phase6Repository


class Clock(Protocol):
    def now(self) -> datetime: ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


class PipelineCoordinator:
    def __init__(self, repository: Phase6Repository, clock: Clock | None = None) -> None:
        self.repository = repository
        self.clock = clock or SystemClock()

    def start(
        self,
        report_date: date,
        trigger: PipelineTrigger,
        *,
        owner_pid: int | None = None,
    ) -> tuple[PipelineRunRecord, bool]:
        return self.repository.try_start_run(
            report_date=report_date,
            trigger=trigger,
            started_at=self.clock.now(),
            owner_pid=os.getpid() if owner_pid is None else owner_pid,
        )

    def recover_stale(
        self,
        process_is_alive: Callable[[int], bool],
        *,
        stale_after: timedelta = timedelta(minutes=5),
    ) -> str | None:
        return self.repository.recover_stale_lock(
            checked_at=self.clock.now(),
            process_is_alive=process_is_alive,
            stale_after=stale_after,
        )

    def latest_catch_up_date(self) -> date | None:
        row = self.repository.latest_incomplete_run()
        return None if row is None else date.fromisoformat(str(row["report_date"]))

    def latest_missed_schedule(self, scheduled_at: tuple[datetime, ...]) -> datetime | None:
        completed = self.repository.completed_report_dates()
        eligible = (
            item
            for item in scheduled_at
            if item <= self.clock.now() and item.date() not in completed
        )
        return max(eligible, default=None)
