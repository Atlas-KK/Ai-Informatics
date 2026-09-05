"""Use cases for formal archive commits and independent user data."""

from ai_intel.domain.models import (
    ArchiveCandidate,
    FormalizationInput,
    ReadyArchiveRecord,
    UserMetadataRecord,
    utc_now,
)
from ai_intel.domain.states import ReadState
from ai_intel.infrastructure.archive.commit import AtomicArchiveCommitter, FailurePoint
from ai_intel.infrastructure.db.repository import SQLiteArchiveRepository
from ai_intel.infrastructure.telemetry import TelemetryEventType, TelemetryRecorder
from ai_intel.infrastructure.vault_projection.projector import ProjectionResult, VaultProjector


class ArchiveService:
    def __init__(
        self,
        repository: SQLiteArchiveRepository,
        committer: AtomicArchiveCommitter,
        projector: VaultProjector,
        telemetry: TelemetryRecorder | None = None,
    ) -> None:
        self.repository = repository
        self.committer = committer
        self.projector = projector
        self.telemetry = telemetry

    def commit(
        self,
        candidate: ArchiveCandidate,
        *,
        formalization: FormalizationInput | None = None,
        fail_at: FailurePoint | None = None,
    ) -> ReadyArchiveRecord:
        return self.committer.commit(candidate, formalization=formalization, fail_at=fail_at)

    def list_formal_archive(self) -> list[ReadyArchiveRecord]:
        return self.repository.list_ready()

    def save_note(self, event_id: str, body: str) -> None:
        self.repository.save_note(event_id, body)
        self._record_action(event_id, "NOTE_UPDATED")

    def update_user_metadata(
        self,
        event_id: str,
        *,
        favorite: bool | None = None,
        pinned: bool | None = None,
        read_state: ReadState | None = None,
    ) -> UserMetadataRecord:
        result = self.repository.update_user_metadata(
            event_id,
            favorite=favorite,
            pinned=pinned,
            read_state=read_state,
        )
        self._record_action(event_id, "USER_METADATA_UPDATED")
        return result

    def move_to_trash(self, event_id: str, reason: str) -> None:
        self.repository.move_to_trash(event_id, reason)
        self._record_action(event_id, "MOVED_TO_TRASH")

    def restore_from_trash(self, event_id: str) -> None:
        self.repository.restore_from_trash(event_id)
        self._record_action(event_id, "RESTORED")

    def permanently_delete(self, event_id: str, *, confirmed: bool) -> bool:
        deleted = self.repository.permanently_delete(event_id, confirmed=confirmed)
        if deleted:
            self._record_action(event_id, "PERMANENTLY_DELETED")
        return deleted

    def rebuild_vault(self, *, full: bool = False) -> ProjectionResult:
        return self.projector.rebuild("full" if full else "incremental")

    def _record_action(self, event_id: str, action: str) -> None:
        if self.telemetry is None:
            return
        occurred_at = utc_now()
        self.telemetry.record(
            TelemetryEventType.INTEL_ITEM_ACTION,
            {"item_id": event_id, "action": action, "occurred_at": occurred_at.isoformat()},
            created_at=occurred_at,
        )
