"""Pure Phase 8 acceptance evaluators.

The evaluators deliberately separate deterministic local/Fake verification from
evidence that can only be produced by elapsed natural days, human review or an
explicitly authorised external adapter check.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import StrEnum


class AcceptanceStatus(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    BLOCKED = "BLOCKED"
    NOT_RUN = "NOT_RUN"


@dataclass(frozen=True, slots=True)
class SoakObservation:
    report_date: date
    run_id: str
    trigger_type: str
    status: str
    started_at: datetime
    finished_at: datetime | None
    enabled_source_ids: tuple[str, ...]
    attempted_source_ids: tuple[str, ...]
    digest_id: str | None
    failure_trace_complete: bool = True


@dataclass(frozen=True, slots=True)
class QualityReview:
    event_id: str
    tier: str
    relevant: bool
    worth_priority: bool | None
    conclusion_count: int
    traceable_conclusion_count: int
    major_hallucination: bool
    excluded_content: bool
    valid_source_count: int


@dataclass(frozen=True, slots=True)
class AcceptanceAssessment:
    status: AcceptanceStatus
    metrics: dict[str, int | float | str]
    reasons: tuple[str, ...]


_TERMINAL_RUN_STATUSES = frozenset({"SUCCEEDED", "FAILED", "TIMED_OUT", "WAITING_RETRY"})


def assess_seven_day_soak(observations: tuple[SoakObservation, ...]) -> AcceptanceAssessment:
    """Assess seven consecutive natural-day scheduled runs without inventing elapsed time."""

    reasons: list[str] = []
    all_ordered = sorted(observations, key=lambda item: (item.report_date, item.started_at))
    latest_by_date = {item.report_date: item for item in all_ordered}
    dates = tuple(sorted(latest_by_date))[-7:]
    ordered = tuple(latest_by_date[item] for item in dates)
    if len(ordered) != 7:
        reasons.append("需要至少 7 个不同自然日的运行记录")
    if dates and any(
        right - left != timedelta(days=1) for left, right in zip(dates, dates[1:], strict=False)
    ):
        reasons.append("7 个报告日期必须连续")

    run_ids = [item.run_id for item in ordered]
    if any(not run_id.strip() for run_id in run_ids) or len(set(run_ids)) != len(run_ids):
        reasons.append("每次运行必须具有非空且唯一的 run_id")
    if any(item.trigger_type != "SCHEDULED" for item in ordered):
        reasons.append("所有试运行证据必须来自 SCHEDULED 触发")
    if any(item.status not in _TERMINAL_RUN_STATUSES for item in ordered):
        reasons.append("每次运行必须在 2 小时内进入可审计终态")
    if any(item.finished_at is None for item in ordered):
        reasons.append("每次运行必须记录 finished_at")
    durations = tuple(
        (item.finished_at - item.started_at).total_seconds()
        for item in ordered
        if item.finished_at is not None
    )
    if any(duration < 0 or duration > 2 * 60 * 60 for duration in durations):
        reasons.append("每次运行耗时必须在 0 到 2 小时之间")
    if any(
        set(item.enabled_source_ids) != set(item.attempted_source_ids)
        or len(item.enabled_source_ids) != len(item.attempted_source_ids)
        or len(set(item.enabled_source_ids)) != len(item.enabled_source_ids)
        or len(set(item.attempted_source_ids)) != len(item.attempted_source_ids)
        for item in ordered
    ):
        reasons.append("每次运行必须尝试全部且仅限当次启用来源")
    if any(item.digest_id is None or not item.digest_id.strip() for item in ordered):
        reasons.append("每次运行必须生成正式或空日报")
    if any(not item.failure_trace_complete for item in ordered):
        reasons.append("来源或任务失败必须具有完整追踪记录")

    metrics: dict[str, int | float | str] = {
        "observed_runs": len(ordered),
        "natural_days": len(dates),
        "total_observed_runs": len(all_ordered),
        "scheduled_runs": sum(item.trigger_type == "SCHEDULED" for item in ordered),
        "digests": sum(bool(item.digest_id) for item in ordered),
        "max_duration_seconds": max(durations, default=0.0),
    }
    status = AcceptanceStatus.PASS if not reasons else AcceptanceStatus.FAIL
    return AcceptanceAssessment(status, metrics, tuple(reasons))


def assess_quality_sample(
    reviews: tuple[QualityReview, ...],
    *,
    formal_count: int,
    expected_must_read_ids: frozenset[str],
    formal_records_without_valid_source: int,
) -> AcceptanceAssessment:
    """Apply the PRD sample size and quality thresholds to human-review evidence."""

    reasons: list[str] = []
    expected_sample_size = min(30, formal_count)
    unique_event_ids = {item.event_id for item in reviews}
    if len(reviews) != expected_sample_size or len(unique_event_ids) != len(reviews):
        reasons.append(f"抽样必须包含 {expected_sample_size} 条唯一正式档案")
    if not expected_must_read_ids.issubset(unique_event_ids):
        reasons.append("必须覆盖抽样周期内的全部必读项")
    if formal_records_without_valid_source:
        reasons.append("存在没有有效来源的正式档案")

    sample_size = len(reviews)
    relevance = sum(item.relevant for item in reviews) / sample_size if sample_size else 0.0
    must_read = tuple(item for item in reviews if item.tier == "MUST_READ")
    missing_priority = any(item.worth_priority is None for item in must_read)
    if missing_priority:
        reasons.append("每条必读都必须给出是否值得优先阅读的二值判定")
    priority = (
        sum(item.worth_priority is True for item in must_read) / len(must_read)
        if must_read
        else 1.0
    )
    conclusion_count = sum(item.conclusion_count for item in reviews)
    traceable_count = sum(item.traceable_conclusion_count for item in reviews)
    invalid_conclusion_counts = any(
        item.conclusion_count < 0
        or item.traceable_conclusion_count < 0
        or item.traceable_conclusion_count > item.conclusion_count
        for item in reviews
    )
    if invalid_conclusion_counts:
        reasons.append("结论总数与可追溯结论数必须合法")
    traceability = traceable_count / conclusion_count if conclusion_count else 0.0
    hallucinations = sum(item.major_hallucination for item in reviews)
    excluded = sum(item.excluded_content for item in reviews)
    source_coverage = (
        sum(item.valid_source_count > 0 for item in reviews) / sample_size if sample_size else 0.0
    )

    if relevance < 0.90:
        reasons.append("情报相关性低于 90%")
    if priority < 0.90:
        reasons.append("必读值得优先阅读比例低于 90%")
    if traceability < 0.95:
        reasons.append("关键结论可追溯率低于 95%")
    if hallucinations:
        reasons.append("重大事实编造必须为 0")
    if excluded:
        reasons.append("明确排除内容必须为 0")
    if source_coverage < 1.0:
        reasons.append("抽样档案有效来源覆盖率必须为 100%")

    metrics: dict[str, int | float | str] = {
        "formal_count": formal_count,
        "sample_size": sample_size,
        "expected_sample_size": expected_sample_size,
        "must_read_count": len(must_read),
        "relevance_ratio": relevance,
        "must_read_priority_ratio": priority,
        "conclusion_traceability_ratio": traceability,
        "major_hallucinations": hallucinations,
        "excluded_content_items": excluded,
        "sample_source_coverage_ratio": source_coverage,
        "formal_records_without_valid_source": formal_records_without_valid_source,
    }
    status = AcceptanceStatus.PASS if not reasons else AcceptanceStatus.FAIL
    return AcceptanceAssessment(status, metrics, tuple(reasons))


def assess_rolling_thirty_days(
    observations: tuple[SoakObservation, ...],
) -> AcceptanceAssessment:
    """Keep the 30-day metric observing until a complete rolling window exists."""

    latest_by_date = {item.report_date: item for item in observations}
    dates = sorted(latest_by_date)
    if len(dates) < 30:
        return AcceptanceAssessment(
            AcceptanceStatus.NOT_RUN,
            {"observed_days": len(dates), "required_days": 30, "state": "OBSERVING"},
            ("未满 30 个自然日，不得提前宣称稳定性指标通过",),
        )
    window_dates = dates[-30:]
    if any(
        right - left != timedelta(days=1)
        for left, right in zip(window_dates, window_dates[1:], strict=False)
    ):
        return AcceptanceAssessment(
            AcceptanceStatus.FAIL,
            {"observed_days": len(window_dates), "required_days": 30, "state": "INCOMPLETE"},
            ("最近 30 天观测窗口不连续",),
        )
    successes = sum(
        latest_by_date[item].status == "SUCCEEDED" and bool(latest_by_date[item].digest_id)
        for item in window_dates
    )
    ratio = successes / 30
    status = AcceptanceStatus.PASS if ratio >= 0.95 else AcceptanceStatus.FAIL
    reasons = () if status is AcceptanceStatus.PASS else ("30 日成功生成日报比例低于 95%",)
    return AcceptanceAssessment(
        status,
        {
            "observed_days": 30,
            "required_days": 30,
            "successful_digest_days": successes,
            "success_ratio": ratio,
            "state": "COMPLETE",
        },
        reasons,
    )
