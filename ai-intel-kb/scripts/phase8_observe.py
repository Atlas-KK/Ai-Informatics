"""Append one read-only scheduled-run observation to the Phase 8 soak evidence."""

from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import date
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATABASE = PROJECT_ROOT / "data" / "app.db"
DEFAULT_OUTPUT = PROJECT_ROOT / "docs" / "phase8" / "evidence" / "soak-observations.json"


def _load_payload(value: str) -> dict[str, Any]:
    loaded = json.loads(value)
    if not isinstance(loaded, dict):
        raise ValueError("telemetry payload must be an object")
    return loaded


def _observe(connection: sqlite3.Connection, report_date: date | None) -> dict[str, Any]:
    connection.row_factory = sqlite3.Row
    params: tuple[str, ...] = ()
    where = "WHERE trigger_type = 'SCHEDULED'"
    if report_date is not None:
        where += " AND report_date = ?"
        params = (report_date.isoformat(),)
    run = connection.execute(
        f"SELECT * FROM pipeline_runs {where} ORDER BY started_at DESC LIMIT 1",  # noqa: S608
        params,
    ).fetchone()
    if run is None:
        target = report_date.isoformat() if report_date else "latest"
        raise RuntimeError(f"no scheduled pipeline run found for {target}")

    telemetry = connection.execute(
        "SELECT event_type, payload_json FROM telemetry_events "
        "WHERE run_id = ? ORDER BY created_at",
        (run["run_id"],),
    ).fetchall()
    payloads = [
        (str(row["event_type"]), _load_payload(str(row["payload_json"]))) for row in telemetry
    ]
    source_payloads = [
        payload for event_type, payload in payloads if event_type == "source_fetch_finished"
    ]
    start_payloads = [
        payload for event_type, payload in payloads if event_type == "pipeline_run_started"
    ]
    final_payloads = [
        payload for event_type, payload in payloads if event_type == "pipeline_run_finished"
    ]
    digest_payloads = [
        payload for event_type, payload in payloads if event_type == "daily_digest_generated"
    ]
    enabled_values = (
        start_payloads[0].get("enabled_source_ids", []) if len(start_payloads) == 1 else []
    )
    enabled_source_ids = (
        tuple(str(value) for value in enabled_values) if isinstance(enabled_values, list) else ()
    )
    attempted_source_ids = tuple(str(item.get("source_id", "")) for item in source_payloads)
    failed_payloads = [item for item in source_payloads if item.get("status") == "FAILED"]
    final_payload = final_payloads[0] if len(final_payloads) == 1 else {}
    trace_complete = (
        len(start_payloads) == 1
        and len(final_payloads) == 1
        and len(set(enabled_source_ids)) == len(enabled_source_ids)
        and len(set(attempted_source_ids)) == len(attempted_source_ids)
        and len(attempted_source_ids) == int(run["attempted_sources"])
        and int(final_payload.get("attempted_sources", -1)) == int(run["attempted_sources"])
        and str(final_payload.get("status", "")) == str(run["status"])
        and all(item.get("error_stage") for item in failed_payloads)
    )
    digest_id = None
    if len(digest_payloads) == 1:
        claimed_digest_id = str(digest_payloads[0].get("digest_id", "")).strip()
        digest = connection.execute(
            "SELECT digest_id FROM daily_digests WHERE digest_id = ? AND report_date = ?",
            (claimed_digest_id, run["report_date"]),
        ).fetchone()
        if digest is not None:
            digest_id = str(digest["digest_id"])
    return {
        "report_date": str(run["report_date"]),
        "run_id": str(run["run_id"]),
        "trigger_type": str(run["trigger_type"]),
        "status": str(run["status"]),
        "started_at": str(run["started_at"]),
        "finished_at": None if run["finished_at"] is None else str(run["finished_at"]),
        "enabled_source_ids": list(enabled_source_ids),
        "attempted_source_ids": list(attempted_source_ids),
        "digest_id": digest_id,
        "failure_trace_complete": trace_complete,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--report-date", type=date.fromisoformat)
    args = parser.parse_args()
    database = args.database.resolve()
    if not database.is_file():
        raise SystemExit(f"database does not exist: {database}")
    connection = sqlite3.connect(f"file:{database.as_posix()}?mode=ro", uri=True)
    try:
        observation = _observe(connection, args.report_date)
    finally:
        connection.close()

    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    existing = json.loads(output.read_text(encoding="utf-8")) if output.exists() else {}
    observations = {str(item["run_id"]): item for item in existing.get("observations", [])}
    observations[str(observation["run_id"])] = observation
    payload = {
        "schema_version": 1,
        "evidence_kind": "ACTUAL_SCHEDULED_RUNS",
        "observations": sorted(
            observations.values(), key=lambda item: (item["report_date"], item["started_at"])
        ),
    }
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Recorded scheduled run {observation['run_id']} for {observation['report_date']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
