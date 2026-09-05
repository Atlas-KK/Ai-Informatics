import json
from pathlib import Path

import pytest
from sqlalchemy import func, select

import ai_intel.infrastructure.db.repository as repository_module
from ai_intel.domain.states import TrashState
from ai_intel.infrastructure.archive.recovery import ArchiveRecovery
from ai_intel.infrastructure.db.repository import ArchiveInvariantError
from ai_intel.infrastructure.db.schema import event_versions, events, notes, user_metadata
from tests.phase2.conftest import make_candidate


def test_trash_restore_cancel_and_confirmed_permanent_delete(runtime, archive_service) -> None:  # type: ignore[no-untyped-def]
    candidate = make_candidate(content="BODY-MUST-NOT-SURVIVE")
    record = archive_service.commit(candidate)
    archive_service.save_note(candidate.event_id, "User note")
    archive_service.update_user_metadata(candidate.event_id, favorite=True, pinned=True)

    with pytest.raises(ArchiveInvariantError, match="reason"):
        archive_service.move_to_trash(candidate.event_id, "  ")

    archive_service.move_to_trash(candidate.event_id, "Low relevance")
    assert archive_service.list_formal_archive() == []
    assert (
        runtime.repository.get_user_metadata(candidate.event_id).trash_state is TrashState.TRASHED
    )

    archive_service.restore_from_trash(candidate.event_id)
    assert runtime.repository.get_ready(candidate.event_id).primary_topic == candidate.primary_topic
    assert runtime.repository.get_note(candidate.event_id) == "User note"
    assert runtime.repository.get_user_metadata(candidate.event_id).favorite is True

    archive_service.move_to_trash(candidate.event_id, "Low relevance")
    assert archive_service.permanently_delete(candidate.event_id, confirmed=False) is False
    assert runtime.repository.get_ready(candidate.event_id, include_trashed=True).version_no == 1

    assert archive_service.permanently_delete(candidate.event_id, confirmed=True) is True
    assert not (runtime.data_dir / record.raw_path).exists()
    assert not (runtime.data_dir / record.archive_path).exists()
    with runtime.engine.connect() as connection:
        for table in (events, event_versions, notes, user_metadata):
            assert connection.execute(select(func.count()).select_from(table)).scalar_one() == 0

    audit = runtime.repository.get_deletion_audit(candidate.event_id)
    assert audit is not None
    assert audit.version_count == 1
    serialized = json.dumps(audit.__dict__ if hasattr(audit, "__dict__") else audit.content_hashes)
    assert "BODY-MUST-NOT-SURVIVE" not in serialized


def test_interrupted_permanent_delete_is_rolled_back_on_startup(
    runtime, archive_service, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    candidate = make_candidate(content="BODY-MUST-BE-RESTORED")
    record = archive_service.commit(candidate)
    archive_service.move_to_trash(candidate.event_id, "Interrupted deletion")
    original_replace = repository_module.os.replace
    interrupted = False

    def replace_then_interrupt(source: str | Path, target: str | Path) -> None:
        nonlocal interrupted
        original_replace(source, target)
        target_path = Path(target)
        if (
            not interrupted
            and ".deletion-staging" in target_path.parts
            and target_path.name != "manifest.json"
        ):
            interrupted = True
            raise SystemExit(23)

    monkeypatch.setattr(repository_module.os, "replace", replace_then_interrupt)
    with pytest.raises(SystemExit, match="23"):
        archive_service.permanently_delete(candidate.event_id, confirmed=True)
    monkeypatch.setattr(repository_module.os, "replace", original_replace)

    ArchiveRecovery(runtime.data_dir, runtime.repository).recover()

    restored = runtime.repository.get_ready(candidate.event_id, include_trashed=True)
    assert restored.version_no == 1
    assert (runtime.data_dir / record.raw_path).exists()
    archive_path = runtime.data_dir / record.archive_path
    assert "BODY-MUST-BE-RESTORED" in archive_path.read_text(encoding="utf-8")
    assert not (runtime.data_dir / ".deletion-staging").exists()
    assert any(
        audit["action"] == "interrupted_deletion_rolled_back"
        for audit in runtime.repository.list_recovery_audits()
    )


def test_committed_permanent_delete_purges_staged_body_on_startup(
    runtime, archive_service, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    candidate = make_candidate(content="BODY-MUST-BE-PURGED")
    archive_service.commit(candidate)
    archive_service.move_to_trash(candidate.event_id, "Committed deletion")
    original_purge = runtime.repository._purge_deletion_stage  # noqa: SLF001

    def interrupt_cleanup(_deletion_stage: Path) -> None:
        raise SystemExit(24)

    monkeypatch.setattr(runtime.repository, "_purge_deletion_stage", interrupt_cleanup)
    with pytest.raises(SystemExit, match="24"):
        archive_service.permanently_delete(candidate.event_id, confirmed=True)
    monkeypatch.setattr(runtime.repository, "_purge_deletion_stage", original_purge)

    assert not runtime.repository.event_exists(candidate.event_id)
    assert (runtime.data_dir / ".deletion-staging").exists()

    ArchiveRecovery(runtime.data_dir, runtime.repository).recover()

    assert not (runtime.data_dir / ".deletion-staging").exists()
    assert runtime.repository.get_deletion_audit(candidate.event_id) is not None
    assert any(
        audit["action"] == "interrupted_deletion_completed"
        for audit in runtime.repository.list_recovery_audits()
    )
