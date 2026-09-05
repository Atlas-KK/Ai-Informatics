import json
import runpy
from pathlib import Path

import pytest


def audit_namespace() -> dict[str, object]:
    script = Path(__file__).parents[2] / "scripts" / "phase8_audit.py"
    return runpy.run_path(str(script))


def test_quality_evidence_rejects_string_booleans(tmp_path: Path) -> None:
    load_quality = audit_namespace()["_load_quality"]
    evidence = tmp_path / "quality.json"
    evidence.write_text(
        json.dumps(
            {
                "formal_count": 1,
                "expected_must_read_ids": ["event-1"],
                "formal_records_without_valid_source": 0,
                "reviews": [
                    {
                        "event_id": "event-1",
                        "tier": "MUST_READ",
                        "relevant": "false",
                        "worth_priority": "false",
                        "conclusion_count": 1,
                        "traceable_conclusion_count": 1,
                        "major_hallucination": False,
                        "excluded_content": False,
                        "valid_source_count": 1,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="JSON boolean"):
        load_quality(evidence)  # type: ignore[operator]


def test_real_adapter_pass_requires_existing_local_evidence(tmp_path: Path) -> None:
    adapter_status = audit_namespace()["_external_adapter_status"]
    evidence = tmp_path / "real-adapters.json"
    evidence.write_text(
        json.dumps(
            {
                "authorization_reference": "approval-1",
                "checks": [{"adapter": "provider", "status": "PASS"}],
            }
        ),
        encoding="utf-8",
    )

    status, reasons = adapter_status(evidence)  # type: ignore[operator]
    assert status == "FAIL"
    assert "provider" in reasons[0]


def test_skip_commands_rejects_stale_source_fingerprint(tmp_path: Path) -> None:
    namespace = audit_namespace()
    load_existing = namespace["_load_existing_result"]
    load_existing.__globals__["_source_fingerprint"] = lambda: "current"  # type: ignore[attr-defined]
    evidence = tmp_path / "command.json"
    evidence.write_text(
        json.dumps(
            {
                "case_id": "P8-TC-01",
                "command": "quality",
                "started_at": "2026-09-04T00:00:00+00:00",
                "finished_at": "2026-09-04T00:01:00+00:00",
                "duration_seconds": 60,
                "exit_code": 0,
                "status": "PASS",
                "source_fingerprint": "stale",
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(SystemExit, match="stale"):
        load_existing("P8-TC-01", "full", evidence)  # type: ignore[operator]
