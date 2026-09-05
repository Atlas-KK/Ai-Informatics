"""Recovery for staged commits, stale locks, orphan files and hash drift."""

import json
import os
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any
from uuid import uuid4

from ai_intel.domain.models import content_digest
from ai_intel.infrastructure.db.repository import SQLiteArchiveRepository


class ArchiveRecovery:
    def __init__(
        self,
        data_dir: Path,
        repository: SQLiteArchiveRepository,
        extra_referenced_paths: Callable[[], set[str]] | None = None,
    ) -> None:
        self.data_dir = data_dir.resolve()
        self.repository = repository
        self.extra_referenced_paths = extra_referenced_paths

    def recover(self, *, process_is_alive: Callable[[int], bool] | None = None) -> None:
        self._recover_interrupted_deletions()
        alive = process_is_alive or _process_is_alive
        for lock in self.repository.list_record_locks():
            owner_pid = int(lock["owner_pid"])
            if not alive(owner_pid):
                self.repository.release_stale_lock(str(lock["event_id"]), owner_pid=owner_pid)

        for commit in self.repository.list_staged_commits():
            self._recover_commit(commit)

        self._verify_ready_commits()
        self._quarantine_orphans()

    def _recover_commit(self, commit: Mapping[str, Any]) -> None:
        pairs = (
            (str(commit["raw_stage_path"]), str(commit["raw_path"]), str(commit["raw_hash"])),
            (
                str(commit["archive_stage_path"]),
                str(commit["archive_path"]),
                str(commit["archive_hash"]),
            ),
        )
        for stage_name, final_name, expected_hash in pairs:
            stage = self._safe_path(stage_name)
            final = self._safe_path(final_name)
            if final.exists():
                if self._hash(final) != expected_hash:
                    quarantined = self._quarantine(final, "hash-drift")
                    self._fail_commit(
                        commit,
                        str(commit["commit_id"]),
                        action="hash_drift_quarantined",
                        details={"path": final_name, "quarantine": quarantined.as_posix()},
                    )
                    return
                continue
            if not stage.exists():
                self._fail_commit(
                    commit,
                    str(commit["commit_id"]),
                    action="staged_file_missing",
                    details={"path": final_name},
                )
                return
            if self._hash(stage) != expected_hash:
                quarantined = self._quarantine(stage, "hash-drift")
                self._fail_commit(
                    commit,
                    str(commit["commit_id"]),
                    action="staged_hash_drift_quarantined",
                    details={"path": stage_name, "quarantine": quarantined.as_posix()},
                )
                return
            final.parent.mkdir(parents=True, exist_ok=True)
            os.replace(stage, final)

        self.repository.finalize_commit(str(commit["commit_id"]))
        self.repository.add_recovery_audit(
            str(commit["event_id"]),
            "staged_commit_completed",
            {"commit_id": str(commit["commit_id"])},
        )
        self._remove_empty_parent(self._safe_path(str(commit["raw_stage_path"])).parent)

    def _verify_ready_commits(self) -> None:
        for commit in self.repository.list_ready_commits():
            for path_name, hash_name in (
                ("raw_path", "raw_hash"),
                ("archive_path", "archive_hash"),
            ):
                path = self._safe_path(str(commit[path_name]))
                if not path.exists():
                    self._fail_commit(
                        commit,
                        str(commit["commit_id"]),
                        action="ready_file_missing",
                        details={"path": str(commit[path_name])},
                    )
                    break
                if self._hash(path) != str(commit[hash_name]):
                    quarantined = self._quarantine(path, "hash-drift")
                    self._fail_commit(
                        commit,
                        str(commit["commit_id"]),
                        action="ready_hash_drift_quarantined",
                        details={
                            "path": str(commit[path_name]),
                            "quarantine": quarantined.as_posix(),
                        },
                    )
                    break

    def _recover_interrupted_deletions(self) -> None:
        deletion_root = self._safe_path(".deletion-staging")
        if not deletion_root.exists():
            return
        for stage_dir in sorted(path for path in deletion_root.iterdir() if path.is_dir()):
            manifest_path = stage_dir / "manifest.json"
            manifest = self._load_deletion_manifest(manifest_path, stage_dir)
            if manifest is None:
                self._purge_directory(stage_dir)
                self.repository.add_recovery_audit(
                    None,
                    "orphan_deletion_stage_purged",
                    {"stage": stage_dir.relative_to(self.data_dir).as_posix()},
                )
                continue
            event_id, entries = manifest
            if not self.repository.event_exists(event_id):
                self._purge_directory(stage_dir)
                self.repository.add_recovery_audit(
                    event_id,
                    "interrupted_deletion_completed",
                    {"stage": stage_dir.relative_to(self.data_dir).as_posix()},
                )
                continue

            conflicts: list[str] = []
            for entry in reversed(entries):
                source = self._safe_path(entry["source"])
                staged = self._safe_path(entry["staged"])
                if stage_dir != staged.parent:
                    conflicts.append(entry["staged"])
                    continue
                if not staged.exists():
                    continue
                source.parent.mkdir(parents=True, exist_ok=True)
                if source.exists():
                    expected = entry["content_hash"]
                    if expected and self._hash(source) != expected:
                        quarantined = self._quarantine(staged, "deletion-conflict")
                        conflicts.append(quarantined.as_posix())
                    else:
                        staged.unlink()
                    continue
                os.replace(staged, source)

            self._purge_directory(stage_dir)
            action = (
                "interrupted_deletion_conflict" if conflicts else "interrupted_deletion_rolled_back"
            )
            self.repository.add_recovery_audit(
                event_id,
                action,
                {
                    "stage": stage_dir.relative_to(self.data_dir).as_posix(),
                    "conflicts": conflicts,
                },
            )
        if deletion_root.exists() and not any(deletion_root.iterdir()):
            deletion_root.rmdir()

    def _load_deletion_manifest(
        self, manifest_path: Path, stage_dir: Path
    ) -> tuple[str, list[dict[str, str]]] | None:
        if not manifest_path.exists():
            return None
        try:
            value = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
        if not isinstance(value, dict) or not isinstance(value.get("event_id"), str):
            return None
        raw_entries = value.get("files")
        if not isinstance(raw_entries, list):
            return None
        entries: list[dict[str, str]] = []
        for item in raw_entries:
            if not isinstance(item, dict):
                return None
            source = item.get("source")
            staged = item.get("staged")
            content_hash = item.get("content_hash")
            if not all(isinstance(field, str) for field in (source, staged, content_hash)):
                return None
            staged_path = self._safe_path(str(staged))
            if staged_path.parent != stage_dir:
                return None
            entries.append(
                {
                    "source": str(source),
                    "staged": str(staged),
                    "content_hash": str(content_hash),
                }
            )
        return str(value["event_id"]), entries

    def _fail_commit(
        self,
        commit: Mapping[str, Any],
        commit_id: str,
        *,
        action: str,
        details: Mapping[str, Any],
    ) -> None:
        self.repository.mark_commit_error(commit_id, action=action, details=details)
        quarantined: list[str] = []
        for name in ("raw_stage_path", "archive_stage_path", "raw_path", "archive_path"):
            path = self._safe_path(str(commit[name]))
            if path.exists():
                target = self._quarantine(path, "failed-commit")
                quarantined.append(target.as_posix())
        if quarantined:
            self.repository.add_recovery_audit(
                str(commit["event_id"]),
                "failed_commit_remainders_quarantined",
                {"paths": quarantined},
            )

    @staticmethod
    def _purge_directory(directory: Path) -> None:
        if not directory.exists():
            return
        descendants = sorted(directory.rglob("*"), key=lambda path: len(path.parts), reverse=True)
        for path in descendants:
            if path.is_file() or path.is_symlink():
                path.unlink()
            elif path.is_dir():
                path.rmdir()
        directory.rmdir()

    def _quarantine_orphans(self) -> None:
        referenced = self.repository.list_all_commit_paths()
        if self.extra_referenced_paths is not None:
            referenced.update(self.extra_referenced_paths())
        for folder in ("raw", "archive"):
            root = self._safe_path(folder)
            if not root.exists():
                continue
            for path in sorted(item for item in root.rglob("*") if item.is_file()):
                relative = path.relative_to(self.data_dir).as_posix()
                if relative not in referenced:
                    quarantined = self._quarantine(path, "orphan")
                    self.repository.add_recovery_audit(
                        None,
                        "orphan_file_quarantined",
                        {"path": relative, "quarantine": quarantined.as_posix()},
                    )

        staging_root = self._safe_path(".staging")
        referenced_staging = {
            str(commit[name])
            for commit in self.repository.list_staged_commits()
            for name in ("raw_stage_path", "archive_stage_path")
        }
        if staging_root.exists():
            for path in sorted(item for item in staging_root.rglob("*") if item.is_file()):
                relative = path.relative_to(self.data_dir).as_posix()
                if relative not in referenced_staging:
                    quarantined = self._quarantine(path, "orphan-staging")
                    self.repository.add_recovery_audit(
                        None,
                        "orphan_staging_quarantined",
                        {"path": relative, "quarantine": quarantined.as_posix()},
                    )

    def _quarantine(self, path: Path, category: str) -> Path:
        target = self._safe_path(Path("quarantine") / category / f"{uuid4().hex}-{path.name}")
        target.parent.mkdir(parents=True, exist_ok=True)
        os.replace(path, target)
        return target.relative_to(self.data_dir)

    def _safe_path(self, relative_path: str | Path) -> Path:
        path = (self.data_dir / relative_path).resolve()
        if path != self.data_dir and self.data_dir not in path.parents:
            raise RuntimeError("recovery path escapes the configured data directory")
        return path

    @staticmethod
    def _hash(path: Path) -> str:
        return content_digest(path.read_text(encoding="utf-8"))

    def _remove_empty_parent(self, path: Path) -> None:
        staging_root = self._safe_path(".staging")
        if path.exists() and path != staging_root and not any(path.iterdir()):
            path.rmdir()
        if staging_root.exists() and not any(staging_root.iterdir()):
            staging_root.rmdir()


def _process_is_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True
