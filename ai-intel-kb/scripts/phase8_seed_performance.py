"""Create an isolated 10k-record database for real-browser performance verification."""

from __future__ import annotations

import argparse
import json
import os
import platform
from datetime import UTC, date, datetime
from pathlib import Path

from ai_intel.config import Settings
from ai_intel.foundation import close_runtime, initialize_runtime
from ai_intel.infrastructure.db.schema import (
    event_versions,
    events,
    evidence,
    scores,
    staged_commits,
    user_metadata,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--report-date", type=date.fromisoformat, required=True)
    parser.add_argument("--count", type=int, default=10_000)
    args = parser.parse_args()
    if args.count < 1:
        raise SystemExit("count must be positive")

    runtime = initialize_runtime(Settings(data_dir=args.data_dir))
    timestamp = datetime.combine(args.report_date, datetime.min.time(), tzinfo=UTC).isoformat()
    try:
        event_rows = []
        version_rows = []
        commit_rows = []
        score_rows = []
        evidence_rows = []
        metadata_rows = []
        for index in range(args.count):
            event_id = f"{index:08x}-0000-4000-8000-{index:012x}"
            version_id = f"v{index:035d}"
            event_rows.append(
                {
                    "event_id": event_id,
                    "canonical_title": f"Archive {index}",
                    "primary_topic": "大模型与智能体",
                    "current_version": 1,
                    "status": "READY",
                    "created_at": timestamp,
                    "updated_at": timestamp,
                }
            )
            version_rows.append(
                {
                    "version_id": version_id,
                    "event_id": event_id,
                    "version_no": 1,
                    "change_type": "NEW",
                    "canonical_title": f"Archive {index}",
                    "primary_topic": "大模型与智能体",
                    "content": "performance fixture content",
                    "summary": "performance fixture summary",
                    "content_hash": f"{index:064x}",
                    "archive_path": f"archive/{event_id}/v0001.md",
                    "created_at": timestamp,
                }
            )
            commit_rows.append(
                {
                    "commit_id": f"c{index:035d}",
                    "event_id": event_id,
                    "version_no": 1,
                    "raw_path": f"raw/{index}.txt",
                    "raw_stage_path": f".staging/{index}/raw.tmp",
                    "raw_hash": f"{index:064x}",
                    "archive_path": f"archive/{event_id}/v0001.md",
                    "archive_stage_path": f".staging/{index}/archive.tmp",
                    "archive_hash": f"{index + 1:064x}",
                    "state": "READY",
                    "created_at": timestamp,
                    "updated_at": timestamp,
                }
            )
            score_rows.append(
                {
                    "score_id": f"s{index:035d}",
                    "version_id": version_id,
                    "config_version": 1,
                    "dimensions_json": "{}",
                    "total": 80,
                    "tier": "IMPORTANT",
                    "created_at": timestamp,
                }
            )
            evidence_rows.append(
                {
                    "evidence_id": f"e{index:035d}",
                    "version_id": version_id,
                    "source_id": "performance-source",
                    "url": f"https://example.test/{index}",
                    "published_at": timestamp,
                    "published_at_original": timestamp,
                    "published_timezone": "UTC",
                    "viewpoint": "fixture",
                }
            )
            metadata_rows.append(
                {
                    "event_id": event_id,
                    "favorite": False,
                    "pinned": False,
                    "read_state": "UNREAD",
                    "trash_state": "ACTIVE",
                    "trash_reason": None,
                    "updated_at": timestamp,
                }
            )
        with runtime.engine.begin() as connection:
            connection.execute(events.insert(), event_rows)
            connection.execute(event_versions.insert(), version_rows)
            connection.execute(staged_commits.insert(), commit_rows)
            connection.execute(scores.insert(), score_rows)
            connection.execute(evidence.insert(), evidence_rows)
            connection.execute(user_metadata.insert(), metadata_rows)
    finally:
        close_runtime(runtime)

    print(
        json.dumps(
            {
                "records": args.count,
                "platform": platform.platform(),
                "machine": platform.machine(),
                "processor": platform.processor() or "unavailable",
                "cpu_count": os.cpu_count(),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
