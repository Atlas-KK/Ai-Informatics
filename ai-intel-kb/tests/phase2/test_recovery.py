import pytest

from ai_intel.infrastructure.archive.commit import FailurePoint, InjectedCommitFailure
from ai_intel.infrastructure.archive.recovery import ArchiveRecovery
from tests.phase2.conftest import make_candidate


@pytest.mark.parametrize("failure_point", list(FailurePoint))
def test_failure_injection_never_exposes_a_partial_record(
    runtime, archive_service, failure_point: FailurePoint
) -> None:  # type: ignore[no-untyped-def]
    candidate = make_candidate()
    with pytest.raises(InjectedCommitFailure):
        archive_service.commit(candidate, fail_at=failure_point)
    assert archive_service.list_formal_archive() == []

    ArchiveRecovery(runtime.data_dir, runtime.repository).recover()
    if failure_point is FailurePoint.TEMP_WRITTEN:
        assert archive_service.list_formal_archive() == []
        assert any(
            audit["action"] == "orphan_staging_quarantined"
            for audit in runtime.repository.list_recovery_audits()
        )
    else:
        assert runtime.repository.get_ready(candidate.event_id).version_no == 1


def test_missing_file_hash_drift_orphan_and_stale_lock_are_recovered(
    runtime, archive_service
) -> None:  # type: ignore[no-untyped-def]
    missing = make_candidate(
        event_id="00000000-0000-4000-8000-000000000010",
        snapshot_id="10000000-0000-4000-8000-000000000010",
    )
    with pytest.raises(InjectedCommitFailure):
        archive_service.commit(missing, fail_at=FailurePoint.SQLITE_STAGED)
    commit = runtime.repository.list_staged_commits()[0]
    (runtime.data_dir / str(commit["raw_stage_path"])).unlink()
    ArchiveRecovery(runtime.data_dir, runtime.repository).recover()
    assert all(item.event_id != missing.event_id for item in archive_service.list_formal_archive())

    ready = make_candidate(
        event_id="00000000-0000-4000-8000-000000000011",
        snapshot_id="10000000-0000-4000-8000-000000000011",
    )
    record = archive_service.commit(ready)
    (runtime.data_dir / record.archive_path).write_text("external drift", encoding="utf-8")
    orphan = runtime.data_dir / "raw" / "orphan.txt"
    orphan.write_text("orphan", encoding="utf-8")
    ArchiveRecovery(runtime.data_dir, runtime.repository).recover()
    assert all(item.event_id != ready.event_id for item in archive_service.list_formal_archive())
    assert list((runtime.data_dir / "quarantine" / "hash-drift").glob("*"))
    assert list((runtime.data_dir / "quarantine" / "orphan").glob("*"))

    locked = make_candidate(
        event_id="00000000-0000-4000-8000-000000000012",
        snapshot_id="10000000-0000-4000-8000-000000000012",
    )
    with pytest.raises(InjectedCommitFailure):
        archive_service.commit(locked, fail_at=FailurePoint.SQLITE_STAGED)
    runtime.repository.acquire_record_lock(locked.event_id, 999_999_999, "run-stale")
    ArchiveRecovery(runtime.data_dir, runtime.repository).recover(
        process_is_alive=lambda _pid: False
    )
    assert runtime.repository.list_record_locks() == []
    assert any(
        audit["action"] == "stale_lock_released"
        for audit in runtime.repository.list_recovery_audits()
    )


def test_failed_unpublished_version_can_be_retried(runtime, archive_service) -> None:  # type: ignore[no-untyped-def]
    candidate = make_candidate()
    with pytest.raises(InjectedCommitFailure):
        archive_service.commit(candidate, fail_at=FailurePoint.SQLITE_STAGED)

    commit = runtime.repository.list_staged_commits()[0]
    (runtime.data_dir / str(commit["raw_stage_path"])).unlink()
    ArchiveRecovery(runtime.data_dir, runtime.repository).recover()

    record = archive_service.commit(candidate)

    assert record.event_id == candidate.event_id
    assert record.version_no == 1
    assert runtime.repository.list_staged_commits() == []

    updated = make_candidate(
        event_id=candidate.event_id,
        snapshot_id="10000000-0000-4000-8000-000000000002",
        version_no=2,
        content="Authoritative content version 2.",
    )
    with pytest.raises(InjectedCommitFailure):
        archive_service.commit(updated, fail_at=FailurePoint.SQLITE_STAGED)
    failed_update = runtime.repository.list_staged_commits()[0]
    (runtime.data_dir / str(failed_update["archive_stage_path"])).unlink()
    ArchiveRecovery(runtime.data_dir, runtime.repository).recover()

    retried_update = archive_service.commit(updated)

    assert retried_update.version_no == 2
    assert retried_update.content == "Authoritative content version 2."
