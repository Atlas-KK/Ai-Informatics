"""Append-only telemetry events stored exclusively in local SQLite."""

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from sqlalchemy import Engine, insert, select

from ai_intel.infrastructure.db.schema import telemetry_events
from ai_intel.infrastructure.telemetry.redaction import redact_value


class TelemetryValidationError(ValueError):
    pass


class TelemetryEventType(StrEnum):
    PIPELINE_RUN_STARTED = "pipeline_run_started"
    PIPELINE_RUN_FINISHED = "pipeline_run_finished"
    SOURCE_FETCH_FINISHED = "source_fetch_finished"
    INTEL_CHANGE_DETECTED = "intel_change_detected"
    INTEL_ITEM_SCORED = "intel_item_scored"
    DAILY_DIGEST_GENERATED = "daily_digest_generated"
    DAILY_DIGEST_PUSHED = "daily_digest_pushed"
    QUALITY_FEEDBACK_SUBMITTED = "quality_feedback_submitted"
    SCORING_CALIBRATION_PROPOSED = "scoring_calibration_proposed"
    SCORING_CONFIG_CHANGED = "scoring_config_changed"
    INTEL_ITEM_ACTION = "intel_item_action"
    EXPANSION_SEARCH_FINISHED = "expansion_search_finished"


REQUIRED_FIELDS: Mapping[TelemetryEventType, frozenset[str]] = {
    TelemetryEventType.PIPELINE_RUN_STARTED: frozenset(
        {
            "run_id",
            "trigger_type",
            "window_start",
            "window_end",
            "started_at",
            "enabled_source_ids",
        }
    ),
    TelemetryEventType.PIPELINE_RUN_FINISHED: frozenset(
        {
            "run_id",
            "status",
            "duration",
            "attempted_sources",
            "successful_sources",
            "failed_sources",
            "archived_count",
        }
    ),
    TelemetryEventType.SOURCE_FETCH_FINISHED: frozenset(
        {"run_id", "source_id", "source_type", "status", "item_count", "error_stage"}
    ),
    TelemetryEventType.INTEL_CHANGE_DETECTED: frozenset(
        {"item_id", "event_id", "change_type", "source_id", "detected_at"}
    ),
    TelemetryEventType.INTEL_ITEM_SCORED: frozenset(
        {"item_id", "total_score", "dimension_scores", "scoring_version", "topic", "tier"}
    ),
    TelemetryEventType.DAILY_DIGEST_GENERATED: frozenset(
        {
            "date",
            "qualified_count",
            "archived_count",
            "must_read_count",
            "important_count",
            "extended_count",
            "digest_id",
        }
    ),
    TelemetryEventType.DAILY_DIGEST_PUSHED: frozenset(
        {"date", "status", "successful_segments", "failed_segments", "error_code"}
    ),
    TelemetryEventType.QUALITY_FEEDBACK_SUBMITTED: frozenset(
        {"item_id", "original_score", "reason", "scoring_version", "occurred_at"}
    ),
    TelemetryEventType.SCORING_CALIBRATION_PROPOSED: frozenset(
        {"current_version", "feedback_count", "proposed_changes", "created_at"}
    ),
    TelemetryEventType.SCORING_CONFIG_CHANGED: frozenset(
        {"old_version", "new_version", "action", "occurred_at"}
    ),
    TelemetryEventType.INTEL_ITEM_ACTION: frozenset({"item_id", "action", "occurred_at"}),
    TelemetryEventType.EXPANSION_SEARCH_FINISHED: frozenset(
        {"item_id", "result_count", "qualified_count", "duration", "status"}
    ),
}


class TelemetryRecorder:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def record(
        self,
        event_type: TelemetryEventType,
        payload: Mapping[str, Any],
        *,
        created_at: datetime,
        run_id: str | None = None,
    ) -> str:
        missing = REQUIRED_FIELDS[event_type] - set(payload)
        if missing:
            raise TelemetryValidationError(
                f"{event_type.value} is missing required fields: {', '.join(sorted(missing))}"
            )
        if created_at.tzinfo is None or created_at.utcoffset() is None:
            raise TelemetryValidationError("telemetry timestamp must include a timezone")
        clean = redact_value(dict(payload))
        event_id = str(uuid4())
        with self.engine.begin() as connection:
            connection.execute(
                insert(telemetry_events).values(
                    telemetry_event_id=event_id,
                    event_type=event_type.value,
                    run_id=run_id,
                    payload_json=json.dumps(clean, ensure_ascii=False, sort_keys=True),
                    created_at=created_at.astimezone(UTC).isoformat(),
                )
            )
        return event_id

    def list(self, run_id: str | None = None) -> tuple[dict[str, Any], ...]:
        statement = select(telemetry_events).order_by(telemetry_events.c.created_at)
        if run_id is not None:
            statement = statement.where(telemetry_events.c.run_id == run_id)
        with self.engine.connect() as connection:
            rows = connection.execute(statement).mappings().all()
        return tuple(
            {
                **dict(row),
                "payload": json.loads(str(row["payload_json"])),
            }
            for row in rows
        )
