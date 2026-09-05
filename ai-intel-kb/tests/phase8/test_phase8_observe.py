import json
import runpy
import sqlite3
import subprocess
from datetime import date
from pathlib import Path


def test_phase8_soak_observer_reads_scheduled_run_and_appends_evidence(tmp_path: Path) -> None:
    database = tmp_path / "app.db"
    output = tmp_path / "soak-observations.json"
    connection = sqlite3.connect(database)
    try:
        connection.executescript(
            """
            CREATE TABLE pipeline_runs (
                run_id TEXT, report_date TEXT, trigger_type TEXT, status TEXT,
                started_at TEXT, finished_at TEXT, attempted_sources INTEGER
            );
            CREATE TABLE telemetry_events (
                run_id TEXT, event_type TEXT, payload_json TEXT, created_at TEXT
            );
            CREATE TABLE daily_digests (
                digest_id TEXT, report_date TEXT, version_no INTEGER
            );
            INSERT INTO pipeline_runs VALUES (
                'run-actual', '2026-09-04', 'SCHEDULED', 'SUCCEEDED',
                '2026-09-04T00:00:00+00:00', '2026-09-04T00:20:00+00:00', 2
            );
            INSERT INTO telemetry_events VALUES (
                'run-actual', 'pipeline_run_started',
                '{"enabled_source_ids":["web","rss"]}',
                '2026-09-04T00:00:00+00:00'
            );
            INSERT INTO telemetry_events VALUES (
                'run-actual', 'source_fetch_finished',
                '{"source_id":"web","status":"SUCCESS","error_stage":null}',
                '2026-09-04T00:05:00+00:00'
            );
            INSERT INTO telemetry_events VALUES (
                'run-actual', 'source_fetch_finished',
                '{"source_id":"rss","status":"FAILED","error_stage":"FETCH"}',
                '2026-09-04T00:06:00+00:00'
            );
            INSERT INTO telemetry_events VALUES (
                'run-actual', 'daily_digest_generated',
                '{"digest_id":"digest-actual"}', '2026-09-04T00:19:00+00:00'
            );
            INSERT INTO telemetry_events VALUES (
                'run-actual', 'pipeline_run_finished',
                '{"status":"SUCCEEDED","attempted_sources":2}',
                '2026-09-04T00:20:00+00:00'
            );
            INSERT INTO daily_digests VALUES ('digest-actual', '2026-09-04', 1);
            """
        )
        connection.commit()
    finally:
        connection.close()

    script = Path(__file__).parents[2] / "scripts" / "phase8_observe.py"
    result = subprocess.run(
        [
            str(Path(__file__).parents[2] / ".venv" / "Scripts" / "python.exe"),
            "-B",
            str(script),
            "--database",
            str(database),
            "--output",
            str(output),
            "--report-date",
            "2026-09-04",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["evidence_kind"] == "ACTUAL_SCHEDULED_RUNS"
    assert payload["observations"] == [
        {
            "report_date": "2026-09-04",
            "run_id": "run-actual",
            "trigger_type": "SCHEDULED",
            "status": "SUCCEEDED",
            "started_at": "2026-09-04T00:00:00+00:00",
            "finished_at": "2026-09-04T00:20:00+00:00",
            "enabled_source_ids": ["web", "rss"],
            "attempted_source_ids": ["web", "rss"],
            "digest_id": "digest-actual",
            "failure_trace_complete": True,
        }
    ]


def test_observer_rejects_duplicate_sources_and_unrelated_digest() -> None:
    script = Path(__file__).parents[2] / "scripts" / "phase8_observe.py"
    observe = runpy.run_path(str(script))["_observe"]
    connection = sqlite3.connect(":memory:")
    connection.executescript(
        """
        CREATE TABLE pipeline_runs (
            run_id TEXT, report_date TEXT, trigger_type TEXT, status TEXT,
            started_at TEXT, finished_at TEXT, attempted_sources INTEGER
        );
        CREATE TABLE telemetry_events (
            run_id TEXT, event_type TEXT, payload_json TEXT, created_at TEXT
        );
        CREATE TABLE daily_digests (
            digest_id TEXT, report_date TEXT, version_no INTEGER
        );
        INSERT INTO pipeline_runs VALUES (
            'run-failed', '2026-09-04', 'SCHEDULED', 'FAILED',
            '2026-09-04T00:00:00+00:00', '2026-09-04T00:20:00+00:00', 2
        );
        INSERT INTO telemetry_events VALUES (
            'run-failed', 'pipeline_run_started',
            '{"enabled_source_ids":["web","rss"]}', '2026-09-04T00:00:00+00:00'
        );
        INSERT INTO telemetry_events VALUES (
            'run-failed', 'source_fetch_finished',
            '{"source_id":"web","status":"SUCCESS"}', '2026-09-04T00:05:00+00:00'
        );
        INSERT INTO telemetry_events VALUES (
            'run-failed', 'source_fetch_finished',
            '{"source_id":"web","status":"SUCCESS"}', '2026-09-04T00:06:00+00:00'
        );
        INSERT INTO telemetry_events VALUES (
            'run-failed', 'pipeline_run_finished',
            '{"status":"FAILED","attempted_sources":2}', '2026-09-04T00:20:00+00:00'
        );
        INSERT INTO daily_digests VALUES ('unrelated-digest', '2026-09-04', 1);
        """
    )

    observation = observe(connection, date(2026, 9, 4))  # type: ignore[operator]
    assert observation["enabled_source_ids"] == ["web", "rss"]
    assert observation["attempted_source_ids"] == ["web", "web"]
    assert observation["digest_id"] is None
    assert observation["failure_trace_complete"] is False
