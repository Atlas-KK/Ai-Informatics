"""Repository protocol; callers cannot update immutable archive fields."""

from pathlib import Path
from typing import Protocol

from ai_intel.domain.models import (
    ArchiveCandidate,
    DeletionAuditShell,
    ReadyArchiveRecord,
    UserMetadataRecord,
)


class ArchiveRepository(Protocol):
    def stage_candidate(
        self,
        *,
        commit_id: str,
        candidate: ArchiveCandidate,
        raw_path: Path,
        raw_stage_path: Path,
        archive_path: Path,
        archive_stage_path: Path,
        archive_hash: str,
    ) -> None: ...

    def finalize_commit(self, commit_id: str) -> ReadyArchiveRecord: ...

    def list_ready(self, *, include_trashed: bool = False) -> list[ReadyArchiveRecord]: ...

    def get_user_metadata(self, event_id: str) -> UserMetadataRecord: ...

    def get_note(self, event_id: str) -> str | None: ...

    def get_deletion_audit(self, event_id: str) -> DeletionAuditShell | None: ...
