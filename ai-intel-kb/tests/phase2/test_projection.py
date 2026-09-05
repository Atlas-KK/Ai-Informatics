import shutil

from ai_intel.domain.models import content_digest
from tests.phase2.conftest import make_candidate


def test_vault_projection_rebuilds_without_reverse_import_or_obsidian(
    runtime, archive_service
) -> None:  # type: ignore[no-untyped-def]
    candidate = make_candidate()
    record = archive_service.commit(candidate)
    archive_service.save_note(candidate.event_id, "Authoritative user note")
    raw = runtime.data_dir / record.raw_path
    archive = runtime.data_dir / record.archive_path
    authoritative_hashes = (
        content_digest(raw.read_text(encoding="utf-8")),
        content_digest(archive.read_text(encoding="utf-8")),
    )

    first = archive_service.rebuild_vault(full=True)
    event_projection = runtime.data_dir / "vault-view" / "10-events" / f"{candidate.event_id}.md"
    note_projection = runtime.data_dir / "vault-view" / "50-notes" / f"{candidate.event_id}.md"
    assert first.written == 2
    assert event_projection.exists()
    assert note_projection.exists()

    event_projection.write_text("external projection edit", encoding="utf-8")
    note_projection.write_text("external note edit", encoding="utf-8")
    second = archive_service.rebuild_vault()
    assert second.quarantined == 2
    assert candidate.canonical_title in event_projection.read_text(encoding="utf-8")
    assert runtime.repository.get_note(candidate.event_id) == "Authoritative user note"

    event_projection.unlink()
    archive_service.rebuild_vault()
    assert event_projection.exists()

    shutil.rmtree(runtime.data_dir / "vault-view")
    archive_service.rebuild_vault(full=True)
    assert event_projection.exists()
    assert authoritative_hashes == (
        content_digest(raw.read_text(encoding="utf-8")),
        content_digest(archive.read_text(encoding="utf-8")),
    )
