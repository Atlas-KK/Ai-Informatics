from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest

from ai_intel.application.archive import ArchiveService
from ai_intel.config import Settings
from ai_intel.domain.models import ArchiveCandidate, EvidenceInput, ScoreInput
from ai_intel.domain.states import Tier
from ai_intel.foundation import RuntimeContext, close_runtime, initialize_runtime
from ai_intel.infrastructure.archive.commit import AtomicArchiveCommitter
from ai_intel.infrastructure.vault_projection.projector import VaultProjector


@pytest.fixture
def runtime(tmp_path: Path) -> Iterator[RuntimeContext]:
    context = initialize_runtime(Settings(data_dir=tmp_path))
    try:
        yield context
    finally:
        close_runtime(context)


@pytest.fixture
def archive_service(runtime: RuntimeContext) -> ArchiveService:
    return ArchiveService(
        runtime.repository,
        AtomicArchiveCommitter(runtime.data_dir, runtime.repository),
        VaultProjector(runtime.data_dir, runtime.repository),
    )


def make_candidate(
    *,
    event_id: str = "00000000-0000-4000-8000-000000000001",
    snapshot_id: str = "10000000-0000-4000-8000-000000000001",
    version_no: int = 1,
    content: str = "Authoritative content version 1.",
    score_version: int = 1,
) -> ArchiveCandidate:
    created_at = datetime(2026, 9, 3, 1, version_no, tzinfo=UTC)
    return ArchiveCandidate(
        event_id=event_id,
        snapshot_id=snapshot_id,
        source_id="source-primary",
        canonical_title=f"AI intelligence event v{version_no}",
        primary_topic="AI 产品与技术趋势",
        change_type="NEW" if version_no == 1 else "UPDATED",
        raw_content=f"Raw source snapshot v{version_no}.",
        content=content,
        summary=f"Summary v{version_no}.",
        evidence=(
            EvidenceInput(
                source_id="source-primary",
                url=f"https://example.test/event?v={version_no}",
                published_at=created_at,
                viewpoint="Primary source statement.",
            ),
            EvidenceInput(
                source_id="source-secondary",
                url=f"https://secondary.test/event?v={version_no}",
                published_at=created_at,
                viewpoint="Independent supporting statement.",
            ),
        ),
        score=ScoreInput(
            config_version=score_version,
            dimensions={"authority": 88.0, "relevance": 92.0},
            total=90.0,
            tier=Tier.MUST_READ,
        ),
        version_no=version_no,
        created_at=created_at,
    )
