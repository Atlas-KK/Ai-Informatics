"""Staged commit protocol: files and SQLite become visible only at the READY switch."""

import os
from enum import StrEnum
from pathlib import Path
from uuid import uuid4

from ai_intel.domain.models import (
    ArchiveCandidate,
    FormalizationInput,
    ReadyArchiveRecord,
    content_digest,
)
from ai_intel.infrastructure.archive.rendering import render_archive
from ai_intel.infrastructure.db.repository import ArchiveInvariantError, SQLiteArchiveRepository


class FailurePoint(StrEnum):
    TEMP_WRITTEN = "TEMP_WRITTEN"
    SQLITE_STAGED = "SQLITE_STAGED"
    RAW_MOVED = "RAW_MOVED"
    ARCHIVE_MOVED = "ARCHIVE_MOVED"
    BEFORE_READY = "BEFORE_READY"


class InjectedCommitFailure(RuntimeError):
    pass


class AtomicArchiveCommitter:
    def __init__(self, data_dir: Path, repository: SQLiteArchiveRepository) -> None:
        self.data_dir = data_dir.resolve()
        self.repository = repository

    def commit(
        self,
        candidate: ArchiveCandidate,
        *,
        formalization: FormalizationInput | None = None,
        fail_at: FailurePoint | None = None,
    ) -> ReadyArchiveRecord:
        commit_id = str(uuid4())
        stage_root = Path(".staging") / commit_id
        raw_stage = stage_root / "raw.tmp"
        archive_stage = stage_root / "archive.tmp"
        raw_path = Path("raw") / f"{candidate.snapshot_id}.txt"
        archive_path = Path("archive") / candidate.event_id / f"v{candidate.version_no:04d}.md"
        archive_text = render_archive(candidate)

        self._write_new(raw_stage, candidate.raw_content)
        self._write_new(archive_stage, archive_text)
        self._inject(fail_at, FailurePoint.TEMP_WRITTEN)

        self.repository.stage_candidate(
            commit_id=commit_id,
            candidate=candidate,
            raw_path=raw_path,
            raw_stage_path=raw_stage,
            archive_path=archive_path,
            archive_stage_path=archive_stage,
            archive_hash=content_digest(archive_text),
            formalization=formalization,
        )
        self._inject(fail_at, FailurePoint.SQLITE_STAGED)

        self._publish(raw_stage, raw_path)
        self._inject(fail_at, FailurePoint.RAW_MOVED)
        self._publish(archive_stage, archive_path)
        self._inject(fail_at, FailurePoint.ARCHIVE_MOVED)
        self._inject(fail_at, FailurePoint.BEFORE_READY)

        record = self.repository.finalize_commit(commit_id)
        self._remove_empty_stage(stage_root)
        return record

    def _write_new(self, relative_path: Path, content: str) -> None:
        path = self._safe_path(relative_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())

    def _publish(self, source_relative: Path, target_relative: Path) -> None:
        source = self._safe_path(source_relative)
        target = self._safe_path(target_relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            raise ArchiveInvariantError(
                f"append-only target already exists: {target_relative.as_posix()}"
            )
        os.replace(source, target)

    def _safe_path(self, relative_path: Path) -> Path:
        path = (self.data_dir / relative_path).resolve()
        if path != self.data_dir and self.data_dir not in path.parents:
            raise ArchiveInvariantError("archive path escapes the configured data directory")
        return path

    def _remove_empty_stage(self, stage_root: Path) -> None:
        current = self._safe_path(stage_root)
        staging_root = self._safe_path(Path(".staging"))
        if current.exists() and not any(current.iterdir()):
            current.rmdir()
        if staging_root.exists() and not any(staging_root.iterdir()):
            staging_root.rmdir()

    @staticmethod
    def _inject(selected: FailurePoint | None, current: FailurePoint) -> None:
        if selected == current:
            raise InjectedCommitFailure(f"injected failure at {current.value}")
