"""Full/incremental Vault View generation from authoritative local records."""

import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, cast
from uuid import uuid4

from ai_intel.domain.models import ReadyArchiveRecord, content_digest
from ai_intel.infrastructure.db.repository import SQLiteArchiveRepository


class ProjectionIntegrityError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ProjectionResult:
    projection_version: int
    written: int
    unchanged: int
    quarantined: int


class VaultProjector:
    def __init__(self, data_dir: Path, repository: SQLiteArchiveRepository) -> None:
        self.data_dir = data_dir.resolve()
        self.vault_dir = self.data_dir / "vault-view"
        self.repository = repository

    def rebuild(self, mode: Literal["full", "incremental"] = "incremental") -> ProjectionResult:
        self._verify_authoritative_files()
        previous = self._load_file_manifest()
        previous_targets = (
            cast(dict[str, str], previous.get("target_paths", {})) if previous else {}
        )
        desired: dict[str, str] = {}
        source_hashes: dict[str, str] = {}
        written = 0
        unchanged = 0
        quarantined = 0

        for record in self.repository.list_ready():
            event_target = f"10-events/{record.event_id}.md"
            desired[event_target] = self._render_event(record)
            source_hashes[f"{record.event_id}:v{record.version_no}"] = content_digest(
                self._safe_data_path(record.archive_path).read_text(encoding="utf-8")
            )
            note = self.repository.get_note(record.event_id)
            if note is not None:
                note_target = f"50-notes/{record.event_id}.md"
                desired[note_target] = self._render_note(record.event_id, note)
                source_hashes[f"{record.event_id}:note"] = content_digest(note)

        target_hashes: dict[str, str] = {}
        for relative, content in sorted(desired.items()):
            expected = content_digest(content)
            target_hashes[relative] = expected
            target = self._safe_vault_path(relative)
            actual = content_digest(target.read_text(encoding="utf-8")) if target.exists() else None
            previous_hash = previous_targets.get(relative)
            if target.exists() and previous_hash is not None and actual != previous_hash:
                self._quarantine_external(target)
                quarantined += 1
                actual = None
            if mode == "full" or actual != expected:
                self._write_atomic(target, content)
                written += 1
            else:
                unchanged += 1

        for relative in sorted(set(previous_targets) - set(desired)):
            target = self._safe_vault_path(relative)
            if target.exists():
                self._quarantine_external(target, category="obsolete")
                quarantined += 1

        version = self.repository.save_projection_manifest(source_hashes, target_hashes)
        manifest = {
            "projection_version": version,
            "generated_at": datetime.now(UTC).isoformat(),
            "source_hashes": source_hashes,
            "target_paths": target_hashes,
            "generated": True,
            "do_not_edit": True,
        }
        self._write_atomic(
            self.vault_dir / ".projection-manifest.json",
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        )
        return ProjectionResult(version, written, unchanged, quarantined)

    def _verify_authoritative_files(self) -> None:
        for commit in self.repository.list_ready_commits():
            for path_key, hash_key in (
                ("raw_path", "raw_hash"),
                ("archive_path", "archive_hash"),
            ):
                path = self._safe_data_path(str(commit[path_key]))
                if not path.exists() or content_digest(path.read_text(encoding="utf-8")) != str(
                    commit[hash_key]
                ):
                    raise ProjectionIntegrityError(
                        f"authoritative file failed integrity verification: {commit[path_key]}"
                    )

    def _load_file_manifest(self) -> dict[str, object] | None:
        path = self.vault_dir / ".projection-manifest.json"
        if not path.exists():
            return None
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            self._quarantine_external(path, category="manifest-drift")
            return None
        if not isinstance(value, dict):
            self._quarantine_external(path, category="manifest-drift")
            return None
        return value

    @staticmethod
    def _render_event(record: ReadyArchiveRecord) -> str:
        properties: tuple[tuple[str, object], ...] = (
            ("event_id", record.event_id),
            ("version_no", record.version_no),
            ("primary_topic", record.primary_topic),
            ("source_ids", list(record.source_ids)),
            ("published_at", record.published_at.isoformat()),
            ("quality_score", record.quality_score),
            ("score_version", record.score_version),
            ("content_hash", record.content_hash),
            ("generated", True),
            ("do_not_edit", True),
        )
        frontmatter = "\n".join(
            f"{key}: {json.dumps(value, ensure_ascii=False, separators=(',', ':'))}"
            for key, value in properties
        )
        return (
            f"---\n{frontmatter}\n---\n\n# {record.canonical_title}\n\n"
            f"{record.summary}\n\n{record.content}\n"
        )

    @staticmethod
    def _render_note(event_id: str, note: str) -> str:
        return (
            "---\n"
            f"event_id: {json.dumps(event_id)}\n"
            "generated: true\n"
            "do_not_edit: true\n"
            "---\n\n"
            f"{note}\n"
        )

    def _write_atomic(self, target: Path, content: str) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(f".{target.name}.{uuid4().hex}.tmp")
        temporary.write_text(content, encoding="utf-8", newline="\n")
        os.replace(temporary, target)

    def _quarantine_external(self, path: Path, category: str = "external-changes") -> Path:
        target = self.vault_dir / f".{category}" / f"{uuid4().hex}-{path.name}"
        target.parent.mkdir(parents=True, exist_ok=True)
        os.replace(path, target)
        return target

    def _safe_vault_path(self, relative: str) -> Path:
        path = (self.vault_dir / relative).resolve()
        vault = self.vault_dir.resolve()
        if path != vault and vault not in path.parents:
            raise ProjectionIntegrityError("projection target escapes vault-view")
        return path

    def _safe_data_path(self, relative: str) -> Path:
        path = (self.data_dir / relative).resolve()
        if path != self.data_dir and self.data_dir not in path.parents:
            raise ProjectionIntegrityError("authoritative path escapes data directory")
        return path
