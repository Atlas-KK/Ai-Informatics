"""Append-only source metric snapshots and local GitHub growth calculation."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum


class MetricStatus(StrEnum):
    OK = "ok"
    INSUFFICIENT_HISTORY = "insufficient_history"


@dataclass(frozen=True, slots=True)
class MetricSnapshot:
    snapshot_id: str
    source_id: str
    subject_key: str
    metric_type: str
    observed_at: datetime
    value: int
    response_id: str


@dataclass(frozen=True, slots=True)
class MetricGrowth:
    status: MetricStatus
    growth: int | None
    start_snapshot_id: str | None
    end_snapshot_id: str
    start_observed_at: datetime | None
    end_observed_at: datetime
    actual_interval_seconds: int | None


def calculate_seven_day_growth(
    current: MetricSnapshot, history: tuple[MetricSnapshot, ...]
) -> MetricGrowth:
    target = current.observed_at.astimezone(UTC) - timedelta(days=7)
    candidates = [
        snapshot
        for snapshot in history
        if snapshot.subject_key == current.subject_key
        and snapshot.metric_type == current.metric_type
        and snapshot.observed_at.astimezone(UTC) <= target
    ]
    if not candidates:
        return MetricGrowth(
            status=MetricStatus.INSUFFICIENT_HISTORY,
            growth=None,
            start_snapshot_id=None,
            end_snapshot_id=current.snapshot_id,
            start_observed_at=None,
            end_observed_at=current.observed_at,
            actual_interval_seconds=None,
        )
    baseline = max(candidates, key=lambda snapshot: snapshot.observed_at)
    interval = current.observed_at.astimezone(UTC) - baseline.observed_at.astimezone(UTC)
    return MetricGrowth(
        status=MetricStatus.OK,
        growth=current.value - baseline.value,
        start_snapshot_id=baseline.snapshot_id,
        end_snapshot_id=current.snapshot_id,
        start_observed_at=baseline.observed_at,
        end_observed_at=current.observed_at,
        actual_interval_seconds=int(interval.total_seconds()),
    )
