"""SQLite implementation of immutable archive and mutable user-data boundaries."""

import json
import os
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, NoReturn, cast
from uuid import uuid4

from sqlalchemy import Connection, Engine, and_, delete, func, insert, select, update
from sqlalchemy.exc import IntegrityError

from ai_intel.domain.models import (
    ArchiveCandidate,
    DeletionAuditShell,
    FormalizationInput,
    ReadyArchiveRecord,
    ScoreInput,
    UserMetadataRecord,
    content_digest,
    utc_now,
)
from ai_intel.domain.states import (
    CommitState,
    EventStatus,
    ReadState,
    ScoringConfigStatus,
    Tier,
    TrashState,
)
from ai_intel.infrastructure.db.schema import (
    active_scoring_config,
    deletion_audits,
    event_versions,
    events,
    evidence,
    formalization_links,
    notes,
    projection_manifests,
    raw_snapshots,
    record_locks,
    recovery_audits,
    scores,
    scoring_configs,
    staged_commits,
    user_metadata,
)


class ArchiveInvariantError(RuntimeError):
    pass


class ReadOnlyArchiveError(ArchiveInvariantError):
    pass


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat()


def _datetime(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _mapping(row: Any) -> Mapping[str, Any]:
    return cast(Mapping[str, Any], row._mapping)  # noqa: SLF001


class SQLiteArchiveRepository:
    def __init__(self, engine: Engine, data_dir: Path) -> None:
        self.engine = engine
        self.data_dir = data_dir.resolve()

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
        formalization: FormalizationInput | None = None,
    ) -> None:
        now = _iso(utc_now())
        version_id = str(uuid4())
        try:
            with self.engine.begin() as connection:
                event_row = connection.execute(
                    select(events).where(events.c.event_id == candidate.event_id)
                ).first()
                if event_row is None:
                    if candidate.version_no != 1:
                        raise ArchiveInvariantError("a new event must start at version 1")
                    connection.execute(
                        insert(events).values(
                            event_id=candidate.event_id,
                            canonical_title=candidate.canonical_title,
                            primary_topic=candidate.primary_topic,
                            current_version=None,
                            status=EventStatus.PROCESSING.value,
                            created_at=_iso(candidate.created_at),
                            updated_at=now,
                        )
                    )
                    connection.execute(
                        insert(user_metadata).values(
                            event_id=candidate.event_id,
                            favorite=False,
                            pinned=False,
                            read_state=ReadState.UNREAD.value,
                            trash_state=TrashState.ACTIVE.value,
                            trash_reason=None,
                            updated_at=now,
                        )
                    )
                else:
                    current_version = _mapping(event_row)["current_version"]
                    expected_version = 1 if current_version is None else int(current_version) + 1
                    if candidate.version_no != expected_version:
                        raise ArchiveInvariantError(
                            f"event version must append as version {expected_version}"
                        )
                    self._discard_errored_version(
                        connection,
                        event_id=candidate.event_id,
                        version_no=candidate.version_no,
                    )

                connection.execute(
                    insert(event_versions).values(
                        version_id=version_id,
                        event_id=candidate.event_id,
                        version_no=candidate.version_no,
                        change_type=candidate.change_type,
                        canonical_title=candidate.canonical_title,
                        primary_topic=candidate.primary_topic,
                        content=candidate.content,
                        summary=candidate.summary,
                        content_hash=candidate.content_hash,
                        archive_path=archive_path.as_posix(),
                        created_at=_iso(candidate.created_at),
                    )
                )
                connection.execute(
                    insert(raw_snapshots).values(
                        snapshot_id=candidate.snapshot_id,
                        version_id=version_id,
                        source_id=candidate.source_id,
                        content_hash=candidate.raw_hash,
                        raw_path=raw_path.as_posix(),
                        first_seen_at=_iso(candidate.created_at),
                    )
                )
                connection.execute(
                    insert(evidence),
                    [
                        {
                            "evidence_id": str(uuid4()),
                            "version_id": version_id,
                            "source_id": item.source_id,
                            "url": item.url,
                            "published_at": _iso(item.published_at),
                            "published_at_original": item.published_at.isoformat(),
                            "published_timezone": item.published_at.strftime("%z"),
                            "viewpoint": item.viewpoint,
                        }
                        for item in candidate.evidence
                    ],
                )
                self._insert_score(connection, version_id, candidate.score, candidate.created_at)
                connection.execute(
                    insert(staged_commits).values(
                        commit_id=commit_id,
                        event_id=candidate.event_id,
                        version_no=candidate.version_no,
                        raw_path=raw_path.as_posix(),
                        raw_stage_path=raw_stage_path.as_posix(),
                        raw_hash=candidate.raw_hash,
                        archive_path=archive_path.as_posix(),
                        archive_stage_path=archive_stage_path.as_posix(),
                        archive_hash=archive_hash,
                        state=CommitState.STAGED.value,
                        formalization_selection_id=(
                            None if formalization is None else formalization.selection_id
                        ),
                        formalization_aggregate_version_id=(
                            None if formalization is None else formalization.aggregate_version_id
                        ),
                        formalization_archived_at=(
                            None if formalization is None else _iso(formalization.archived_at)
                        ),
                        created_at=now,
                        updated_at=now,
                    )
                )
        except IntegrityError as exc:
            raise ArchiveInvariantError(
                "archive identity or append-only constraint failed"
            ) from exc

    def finalize_commit(self, commit_id: str) -> ReadyArchiveRecord:
        now = _iso(utc_now())
        with self.engine.begin() as connection:
            commit_row = connection.execute(
                select(staged_commits).where(staged_commits.c.commit_id == commit_id)
            ).first()
            if commit_row is None:
                raise ArchiveInvariantError("unknown staged commit")
            commit = _mapping(commit_row)
            if commit["state"] == CommitState.ERROR.value:
                raise ArchiveInvariantError("an errored commit cannot become ready")
            connection.execute(
                update(staged_commits)
                .where(staged_commits.c.commit_id == commit_id)
                .values(state=CommitState.READY.value, updated_at=now)
            )
            connection.execute(
                update(events)
                .where(events.c.event_id == commit["event_id"])
                .values(
                    current_version=commit["version_no"],
                    status=EventStatus.READY.value,
                    updated_at=now,
                )
            )
            if commit["formalization_selection_id"] is not None:
                connection.execute(
                    insert(formalization_links).values(
                        link_id=str(uuid4()),
                        selection_id=commit["formalization_selection_id"],
                        aggregate_version_id=commit["formalization_aggregate_version_id"],
                        formal_event_id=commit["event_id"],
                        formal_version_no=commit["version_no"],
                        archived_at=commit["formalization_archived_at"],
                    )
                )
        return self.get_ready(str(commit["event_id"]), include_trashed=True)

    def mark_commit_error(self, commit_id: str, *, action: str, details: Mapping[str, Any]) -> None:
        now = _iso(utc_now())
        with self.engine.begin() as connection:
            commit_row = connection.execute(
                select(staged_commits).where(staged_commits.c.commit_id == commit_id)
            ).first()
            if commit_row is None:
                return
            commit = _mapping(commit_row)
            connection.execute(
                update(staged_commits)
                .where(staged_commits.c.commit_id == commit_id)
                .values(state=CommitState.ERROR.value, updated_at=now)
            )
            event_row = connection.execute(
                select(events.c.current_version).where(events.c.event_id == commit["event_id"])
            ).first()
            if event_row is not None and (
                event_row.current_version is None
                or int(event_row.current_version) == int(commit["version_no"])
            ):
                previous_version = connection.execute(
                    select(func.max(staged_commits.c.version_no)).where(
                        staged_commits.c.event_id == commit["event_id"],
                        staged_commits.c.state == CommitState.READY.value,
                        staged_commits.c.version_no < commit["version_no"],
                    )
                ).scalar_one_or_none()
                connection.execute(
                    update(events)
                    .where(events.c.event_id == commit["event_id"])
                    .values(
                        current_version=previous_version,
                        status=(
                            EventStatus.READY.value
                            if previous_version is not None
                            else EventStatus.WAITING_RETRY.value
                        ),
                        updated_at=now,
                    )
                )
            self._audit(connection, str(commit["event_id"]), action, details)

    def list_staged_commits(self) -> list[Mapping[str, Any]]:
        with self.engine.connect() as connection:
            rows = connection.execute(
                select(staged_commits).where(staged_commits.c.state == CommitState.STAGED.value)
            ).all()
        return [dict(_mapping(row)) for row in rows]

    def list_all_commit_paths(self) -> set[str]:
        with self.engine.connect() as connection:
            rows = connection.execute(
                select(staged_commits.c.raw_path, staged_commits.c.archive_path).where(
                    staged_commits.c.state.in_((CommitState.STAGED.value, CommitState.READY.value))
                )
            ).all()
        return {str(path) for row in rows for path in row}

    def list_ready_commits(self) -> list[Mapping[str, Any]]:
        with self.engine.connect() as connection:
            rows = connection.execute(
                select(staged_commits).where(staged_commits.c.state == CommitState.READY.value)
            ).all()
        return [dict(_mapping(row)) for row in rows]

    def list_ready(self, *, include_trashed: bool = False) -> list[ReadyArchiveRecord]:
        with self.engine.connect() as connection:
            source = (
                events.outerjoin(
                    event_versions,
                    and_(
                        event_versions.c.event_id == events.c.event_id,
                        event_versions.c.version_no == events.c.current_version,
                    ),
                )
                .outerjoin(
                    staged_commits,
                    and_(
                        staged_commits.c.event_id == events.c.event_id,
                        staged_commits.c.version_no == events.c.current_version,
                        staged_commits.c.state == CommitState.READY.value,
                    ),
                )
                .outerjoin(
                    raw_snapshots,
                    raw_snapshots.c.version_id == event_versions.c.version_id,
                )
            )
            if not include_trashed:
                source = source.join(user_metadata, user_metadata.c.event_id == events.c.event_id)
            statement = (
                select(
                    events.c.event_id,
                    event_versions.c.version_id,
                    event_versions.c.version_no,
                    event_versions.c.canonical_title,
                    event_versions.c.primary_topic,
                    event_versions.c.content,
                    event_versions.c.summary,
                    event_versions.c.content_hash,
                    event_versions.c.archive_path,
                    raw_snapshots.c.raw_path,
                    raw_snapshots.c.content_hash.label("raw_hash"),
                    staged_commits.c.state.label("commit_state"),
                )
                .select_from(source)
                .where(events.c.status == EventStatus.READY.value)
                .order_by(events.c.created_at, events.c.event_id)
            )
            if not include_trashed:
                statement = statement.where(user_metadata.c.trash_state == TrashState.ACTIVE.value)
            archive_rows = connection.execute(statement).all()
            if not archive_rows:
                return []

            archive_by_event: dict[str, Mapping[str, Any]] = {}
            version_ids: list[str] = []
            for row in archive_rows:
                value = _mapping(row)
                event_id = str(value["event_id"])
                if event_id in archive_by_event:
                    raise ArchiveInvariantError(
                        "ready event has multiple authoritative raw snapshots"
                    )
                if value["version_id"] is None:
                    raise ArchiveInvariantError("ready event has no current version")
                if value["commit_state"] != CommitState.READY.value:
                    raise ArchiveInvariantError("current version is not atomically committed")
                if value["raw_path"] is None or value["raw_hash"] is None:
                    raise ArchiveInvariantError("ready event has no raw snapshot")
                archive_by_event[event_id] = value
                version_ids.append(str(value["version_id"]))

            score_rows = connection.execute(
                select(scores)
                .where(scores.c.version_id.in_(version_ids))
                .order_by(
                    scores.c.version_id,
                    scores.c.created_at.desc(),
                    scores.c.config_version.desc(),
                )
            ).all()
            scores_by_version: dict[str, Mapping[str, Any]] = {}
            for row in score_rows:
                value = _mapping(row)
                scores_by_version.setdefault(str(value["version_id"]), value)

            evidence_rows = connection.execute(
                select(evidence)
                .where(evidence.c.version_id.in_(version_ids))
                .order_by(evidence.c.version_id, evidence.c.source_id)
            ).all()
            evidence_by_version: dict[str, list[Mapping[str, Any]]] = {}
            for row in evidence_rows:
                value = _mapping(row)
                evidence_by_version.setdefault(str(value["version_id"]), []).append(value)

            records: list[ReadyArchiveRecord] = []
            for event_id, archive in archive_by_event.items():
                version_id = str(archive["version_id"])
                score = scores_by_version.get(version_id)
                relationships = evidence_by_version.get(version_id, [])
                if score is None:
                    raise ArchiveInvariantError("ready event has no score")
                if not relationships:
                    raise ArchiveInvariantError("ready event has no evidence")
                records.append(
                    ReadyArchiveRecord(
                        event_id=event_id,
                        version_no=int(archive["version_no"]),
                        canonical_title=str(archive["canonical_title"]),
                        primary_topic=str(archive["primary_topic"]),
                        content=str(archive["content"]),
                        summary=str(archive["summary"]),
                        content_hash=str(archive["content_hash"]),
                        archive_path=str(archive["archive_path"]),
                        raw_path=str(archive["raw_path"]),
                        raw_hash=str(archive["raw_hash"]),
                        quality_score=float(score["total"]),
                        score_version=int(score["config_version"]),
                        tier=Tier(str(score["tier"])),
                        source_ids=tuple(
                            sorted({str(item["source_id"]) for item in relationships})
                        ),
                        published_at=min(
                            _datetime(str(item["published_at"])) for item in relationships
                        ),
                    )
                )
            return records

    def get_ready(self, event_id: str, *, include_trashed: bool = False) -> ReadyArchiveRecord:
        with self.engine.connect() as connection:
            if not include_trashed:
                state = connection.execute(
                    select(user_metadata.c.trash_state).where(user_metadata.c.event_id == event_id)
                ).scalar_one_or_none()
                if state != TrashState.ACTIVE.value:
                    raise ArchiveInvariantError("event is not available in the formal archive")
            return self._ready_record(connection, event_id)

    def get_delivery_metadata(self, event_id: str) -> tuple[str, tuple[tuple[str, str], ...]]:
        """Return the current change marker and ordered source links for a digest."""

        with self.engine.connect() as connection:
            current = connection.execute(
                select(events.c.current_version).where(events.c.event_id == event_id)
            ).scalar_one()
            change_type = connection.execute(
                select(event_versions.c.change_type).where(
                    event_versions.c.event_id == event_id,
                    event_versions.c.version_no == current,
                )
            ).scalar_one()
            sources = connection.execute(
                select(evidence.c.source_id, evidence.c.url)
                .join(event_versions, evidence.c.version_id == event_versions.c.version_id)
                .where(
                    event_versions.c.event_id == event_id,
                    event_versions.c.version_no == current,
                )
                .order_by(evidence.c.source_id, evidence.c.url)
            ).all()
        return str(change_type), tuple((str(row[0]), str(row[1])) for row in sources)

    def _ready_record(self, connection: Connection, event_id: str) -> ReadyArchiveRecord:
        event_row = connection.execute(
            select(events).where(
                events.c.event_id == event_id,
                events.c.status == EventStatus.READY.value,
            )
        ).first()
        if event_row is None:
            raise ArchiveInvariantError("event is not ready")
        event = _mapping(event_row)
        version_row = connection.execute(
            select(event_versions).where(
                event_versions.c.event_id == event_id,
                event_versions.c.version_no == event["current_version"],
            )
        ).first()
        if version_row is None:
            raise ArchiveInvariantError("ready event has no current version")
        version = _mapping(version_row)
        commit_state = connection.execute(
            select(staged_commits.c.state).where(
                staged_commits.c.event_id == event_id,
                staged_commits.c.version_no == event["current_version"],
            )
        ).scalar_one_or_none()
        if commit_state != CommitState.READY.value:
            raise ArchiveInvariantError("current version is not atomically committed")
        raw = _mapping(
            connection.execute(
                select(raw_snapshots).where(raw_snapshots.c.version_id == version["version_id"])
            ).one()
        )
        score = _mapping(
            connection.execute(
                select(scores)
                .where(scores.c.version_id == version["version_id"])
                .order_by(scores.c.created_at.desc(), scores.c.config_version.desc())
                .limit(1)
            ).one()
        )
        evidence_rows = connection.execute(
            select(evidence)
            .where(evidence.c.version_id == version["version_id"])
            .order_by(evidence.c.source_id)
        ).all()
        return ReadyArchiveRecord(
            event_id=event_id,
            version_no=int(version["version_no"]),
            canonical_title=str(version["canonical_title"]),
            primary_topic=str(version["primary_topic"]),
            content=str(version["content"]),
            summary=str(version["summary"]),
            content_hash=str(version["content_hash"]),
            archive_path=str(version["archive_path"]),
            raw_path=str(raw["raw_path"]),
            raw_hash=str(raw["content_hash"]),
            quality_score=float(score["total"]),
            score_version=int(score["config_version"]),
            tier=Tier(str(score["tier"])),
            source_ids=tuple(sorted({str(_mapping(row)["source_id"]) for row in evidence_rows})),
            published_at=min(
                _datetime(str(_mapping(row)["published_at"])) for row in evidence_rows
            ),
        )

    def reject_system_update(self, _event_id: str, **_changes: object) -> NoReturn:
        raise ReadOnlyArchiveError("system-generated archive fields are read-only")

    def save_note(self, event_id: str, body: str) -> None:
        now = _iso(utc_now())
        with self.engine.begin() as connection:
            self._require_ready(connection, event_id)
            existing = connection.execute(
                select(notes.c.event_id).where(notes.c.event_id == event_id)
            ).first()
            if existing is None:
                connection.execute(
                    insert(notes).values(event_id=event_id, body=body, updated_at=now)
                )
            else:
                connection.execute(
                    update(notes)
                    .where(notes.c.event_id == event_id)
                    .values(body=body, updated_at=now)
                )

    def get_note(self, event_id: str) -> str | None:
        with self.engine.connect() as connection:
            value = connection.execute(
                select(notes.c.body).where(notes.c.event_id == event_id)
            ).scalar_one_or_none()
        return None if value is None else str(value)

    def update_user_metadata(
        self,
        event_id: str,
        *,
        favorite: bool | None = None,
        pinned: bool | None = None,
        read_state: ReadState | None = None,
    ) -> UserMetadataRecord:
        values: dict[str, object] = {"updated_at": _iso(utc_now())}
        if favorite is not None:
            values["favorite"] = favorite
        if pinned is not None:
            values["pinned"] = pinned
        if read_state is not None:
            values["read_state"] = read_state.value
        with self.engine.begin() as connection:
            self._require_ready(connection, event_id)
            connection.execute(
                update(user_metadata).where(user_metadata.c.event_id == event_id).values(**values)
            )
        return self.get_user_metadata(event_id)

    def get_user_metadata(self, event_id: str) -> UserMetadataRecord:
        with self.engine.connect() as connection:
            row = connection.execute(
                select(user_metadata).where(user_metadata.c.event_id == event_id)
            ).first()
        if row is None:
            raise ArchiveInvariantError("unknown event metadata")
        value = _mapping(row)
        return UserMetadataRecord(
            event_id=event_id,
            favorite=bool(value["favorite"]),
            pinned=bool(value["pinned"]),
            read_state=ReadState(str(value["read_state"])),
            trash_state=TrashState(str(value["trash_state"])),
            trash_reason=None if value["trash_reason"] is None else str(value["trash_reason"]),
        )

    def move_to_trash(self, event_id: str, reason: str) -> None:
        if not reason.strip():
            raise ArchiveInvariantError("a removal reason is required")
        with self.engine.begin() as connection:
            self._require_ready(connection, event_id)
            connection.execute(
                update(user_metadata)
                .where(user_metadata.c.event_id == event_id)
                .values(
                    trash_state=TrashState.TRASHED.value,
                    trash_reason=reason.strip(),
                    updated_at=_iso(utc_now()),
                )
            )

    def restore_from_trash(self, event_id: str) -> None:
        with self.engine.begin() as connection:
            result = connection.execute(
                update(user_metadata)
                .where(
                    user_metadata.c.event_id == event_id,
                    user_metadata.c.trash_state == TrashState.TRASHED.value,
                )
                .values(
                    trash_state=TrashState.ACTIVE.value,
                    trash_reason=None,
                    updated_at=_iso(utc_now()),
                )
            )
            if result.rowcount != 1:
                raise ArchiveInvariantError("event is not in the trash")

    def permanently_delete(self, event_id: str, *, confirmed: bool) -> bool:
        if not confirmed:
            return False
        with self.engine.connect() as connection:
            metadata_state = connection.execute(
                select(user_metadata.c.trash_state, user_metadata.c.trash_reason).where(
                    user_metadata.c.event_id == event_id
                )
            ).first()
            if metadata_state is None or metadata_state.trash_state != TrashState.TRASHED.value:
                raise ArchiveInvariantError("only a trashed event can be permanently deleted")
            version_rows = connection.execute(
                select(event_versions.c.content_hash, event_versions.c.archive_path).where(
                    event_versions.c.event_id == event_id
                )
            ).all()
            raw_paths = connection.execute(
                select(raw_snapshots.c.raw_path)
                .join(event_versions, raw_snapshots.c.version_id == event_versions.c.version_id)
                .where(event_versions.c.event_id == event_id)
            ).scalars()
            paths = [str(row.archive_path) for row in version_rows] + [
                str(path) for path in raw_paths
            ]
            hashes = [str(row.content_hash) for row in version_rows]
            reason = str(metadata_state.trash_reason)

        audit_id = str(uuid4())
        deletion_stage = self.data_dir / ".deletion-staging" / audit_id
        deletion_stage.mkdir(parents=True, exist_ok=False)
        file_entries: list[dict[str, str]] = []
        for index, relative_path in enumerate(paths):
            source = self._safe_data_path(relative_path)
            staged = deletion_stage / f"{index:04d}-{source.name}"
            file_entries.append(
                {
                    "source": source.relative_to(self.data_dir).as_posix(),
                    "staged": staged.relative_to(self.data_dir).as_posix(),
                    "content_hash": (
                        content_digest(source.read_text(encoding="utf-8"))
                        if source.exists()
                        else ""
                    ),
                }
            )
        manifest: dict[str, object] = {
            "audit_id": audit_id,
            "event_id": event_id,
            "files": file_entries,
        }
        self._write_deletion_manifest(deletion_stage, manifest)
        try:
            for entry in file_entries:
                source = self._safe_data_path(entry["source"])
                if source.exists():
                    staged = self._safe_data_path(entry["staged"])
                    os.replace(source, staged)
            with self.engine.begin() as connection:
                connection.execute(
                    insert(deletion_audits).values(
                        audit_id=audit_id,
                        event_id=event_id,
                        deletion_reason=reason,
                        deleted_at=_iso(utc_now()),
                        version_count=len(version_rows),
                        content_hashes_json=json.dumps(hashes),
                    )
                )
                connection.execute(delete(events).where(events.c.event_id == event_id))
        except Exception:
            self._restore_deletion_files(file_entries)
            self._purge_deletion_stage(deletion_stage)
            raise
        self._purge_deletion_stage(deletion_stage)
        return True

    def event_exists(self, event_id: str) -> bool:
        with self.engine.connect() as connection:
            value = connection.execute(
                select(events.c.event_id).where(events.c.event_id == event_id)
            ).scalar_one_or_none()
        return value is not None

    def get_deletion_audit(self, event_id: str) -> DeletionAuditShell | None:
        with self.engine.connect() as connection:
            row = connection.execute(
                select(deletion_audits).where(deletion_audits.c.event_id == event_id)
            ).first()
        if row is None:
            return None
        value = _mapping(row)
        return DeletionAuditShell(
            event_id=event_id,
            deletion_reason=str(value["deletion_reason"]),
            deleted_at=_datetime(str(value["deleted_at"])),
            version_count=int(value["version_count"]),
            content_hashes=tuple(json.loads(str(value["content_hashes_json"]))),
        )

    def add_score(self, event_id: str, version_no: int, score: ScoreInput) -> None:
        with self.engine.begin() as connection:
            version_id = connection.execute(
                select(event_versions.c.version_id).where(
                    event_versions.c.event_id == event_id,
                    event_versions.c.version_no == version_no,
                )
            ).scalar_one_or_none()
            if version_id is None:
                raise ArchiveInvariantError("unknown event version")
            self._insert_score(connection, str(version_id), score, utc_now())

    def add_scoring_config(
        self,
        config_version: int,
        weights: Mapping[str, float],
        source_overrides: Mapping[str, float],
    ) -> None:
        with self.engine.begin() as connection:
            connection.execute(
                insert(scoring_configs).values(
                    config_version=config_version,
                    weights_json=json.dumps(dict(weights), sort_keys=True),
                    source_overrides_json=json.dumps(dict(source_overrides), sort_keys=True),
                    status=ScoringConfigStatus.INACTIVE.value,
                    created_at=_iso(utc_now()),
                )
            )

    def activate_scoring_config(self, config_version: int, *, user_confirmed: bool) -> None:
        if not user_confirmed:
            raise ArchiveInvariantError(
                "scoring configuration activation requires user confirmation"
            )
        now = _iso(utc_now())
        with self.engine.begin() as connection:
            exists = connection.execute(
                select(scoring_configs.c.config_version).where(
                    scoring_configs.c.config_version == config_version
                )
            ).scalar_one_or_none()
            if exists is None:
                raise ArchiveInvariantError("unknown scoring configuration")
            connection.execute(
                update(scoring_configs)
                .where(scoring_configs.c.status == ScoringConfigStatus.ACTIVE.value)
                .values(status=ScoringConfigStatus.INACTIVE.value)
            )
            connection.execute(
                update(scoring_configs)
                .where(scoring_configs.c.config_version == config_version)
                .values(status=ScoringConfigStatus.ACTIVE.value)
            )
            active = connection.execute(select(active_scoring_config.c.singleton_id)).first()
            if active is None:
                connection.execute(
                    insert(active_scoring_config).values(
                        singleton_id=1, config_version=config_version, changed_at=now
                    )
                )
            else:
                connection.execute(
                    update(active_scoring_config)
                    .where(active_scoring_config.c.singleton_id == 1)
                    .values(config_version=config_version, changed_at=now)
                )

    def get_active_scoring_version(self) -> int | None:
        with self.engine.connect() as connection:
            value = connection.execute(
                select(active_scoring_config.c.config_version).where(
                    active_scoring_config.c.singleton_id == 1
                )
            ).scalar_one_or_none()
        return None if value is None else int(value)

    def acquire_record_lock(self, event_id: str, owner_pid: int, run_id: str) -> None:
        with self.engine.begin() as connection:
            connection.execute(
                insert(record_locks).values(
                    event_id=event_id,
                    owner_pid=owner_pid,
                    run_id=run_id,
                    acquired_at=_iso(utc_now()),
                )
            )

    def list_record_locks(self) -> list[Mapping[str, Any]]:
        with self.engine.connect() as connection:
            rows = connection.execute(select(record_locks)).all()
        return [dict(_mapping(row)) for row in rows]

    def release_stale_lock(self, event_id: str, *, owner_pid: int) -> None:
        with self.engine.begin() as connection:
            result = connection.execute(
                delete(record_locks).where(
                    record_locks.c.event_id == event_id,
                    record_locks.c.owner_pid == owner_pid,
                )
            )
            if result.rowcount != 1:
                return
            event_row = connection.execute(
                select(events.c.current_version).where(events.c.event_id == event_id)
            ).first()
            if event_row is not None and event_row.current_version is None:
                connection.execute(
                    update(events)
                    .where(events.c.event_id == event_id)
                    .values(status=EventStatus.WAITING_RETRY.value, updated_at=_iso(utc_now()))
                )
            self._audit(
                connection,
                event_id,
                "stale_lock_released",
                {"owner_pid": owner_pid, "next_state": EventStatus.WAITING_RETRY.value},
            )

    def add_recovery_audit(
        self, event_id: str | None, action: str, details: Mapping[str, Any]
    ) -> None:
        with self.engine.begin() as connection:
            self._audit(connection, event_id, action, details)

    def list_recovery_audits(self) -> list[Mapping[str, Any]]:
        with self.engine.connect() as connection:
            rows = connection.execute(
                select(recovery_audits).order_by(recovery_audits.c.created_at)
            ).all()
        return [dict(_mapping(row)) for row in rows]

    def latest_projection_manifest(self) -> Mapping[str, Any] | None:
        with self.engine.connect() as connection:
            row = connection.execute(
                select(projection_manifests)
                .order_by(projection_manifests.c.projection_version.desc())
                .limit(1)
            ).first()
        return None if row is None else dict(_mapping(row))

    def save_projection_manifest(
        self,
        source_hashes: Mapping[str, str],
        target_paths: Mapping[str, str],
    ) -> int:
        with self.engine.begin() as connection:
            current = connection.execute(
                select(func.max(projection_manifests.c.projection_version))
            ).scalar_one_or_none()
            version = 1 if current is None else int(current) + 1
            connection.execute(
                insert(projection_manifests).values(
                    projection_version=version,
                    generated_at=_iso(utc_now()),
                    source_hashes_json=json.dumps(dict(source_hashes), sort_keys=True),
                    target_paths_json=json.dumps(dict(target_paths), sort_keys=True),
                )
            )
        return version

    def _insert_score(
        self, connection: Connection, version_id: str, score: ScoreInput, created_at: datetime
    ) -> None:
        connection.execute(
            insert(scores).values(
                score_id=str(uuid4()),
                version_id=version_id,
                config_version=score.config_version,
                dimensions_json=json.dumps(dict(score.dimensions), sort_keys=True),
                total=score.total,
                tier=score.tier.value,
                created_at=_iso(created_at),
            )
        )

    def _discard_errored_version(
        self,
        connection: Connection,
        *,
        event_id: str,
        version_no: int,
    ) -> None:
        errored_commit = connection.execute(
            select(staged_commits.c.commit_id).where(
                staged_commits.c.event_id == event_id,
                staged_commits.c.version_no == version_no,
                staged_commits.c.state == CommitState.ERROR.value,
            )
        ).scalar_one_or_none()
        if errored_commit is None:
            return
        connection.execute(
            delete(staged_commits).where(staged_commits.c.commit_id == errored_commit)
        )
        connection.execute(
            delete(event_versions).where(
                event_versions.c.event_id == event_id,
                event_versions.c.version_no == version_no,
            )
        )

    def _write_deletion_manifest(
        self, deletion_stage: Path, manifest: Mapping[str, object]
    ) -> None:
        temporary = deletion_stage / "manifest.tmp"
        target = deletion_stage / "manifest.json"
        with temporary.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(manifest, stream, ensure_ascii=False, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)

    def _restore_deletion_files(self, entries: list[dict[str, str]]) -> None:
        for entry in reversed(entries):
            source = self._safe_data_path(entry["source"])
            staged = self._safe_data_path(entry["staged"])
            if not staged.exists():
                continue
            source.parent.mkdir(parents=True, exist_ok=True)
            if source.exists():
                expected = entry["content_hash"]
                actual = content_digest(source.read_text(encoding="utf-8"))
                if expected and actual != expected:
                    raise ArchiveInvariantError(
                        f"cannot restore interrupted deletion over changed file: {entry['source']}"
                    )
                staged.unlink()
                continue
            os.replace(staged, source)

    def _purge_deletion_stage(self, deletion_stage: Path) -> None:
        if not deletion_stage.exists():
            return
        descendants = sorted(
            deletion_stage.rglob("*"), key=lambda path: len(path.parts), reverse=True
        )
        for path in descendants:
            if path.is_file() or path.is_symlink():
                path.unlink()
            elif path.is_dir():
                path.rmdir()
        deletion_stage.rmdir()
        deletion_root = deletion_stage.parent
        if deletion_root.exists() and not any(deletion_root.iterdir()):
            deletion_root.rmdir()

    def _require_ready(self, connection: Connection, event_id: str) -> None:
        status = connection.execute(
            select(events.c.status).where(events.c.event_id == event_id)
        ).scalar_one_or_none()
        if status != EventStatus.READY.value:
            raise ArchiveInvariantError("user operations require a ready event")

    def _audit(
        self,
        connection: Connection,
        event_id: str | None,
        action: str,
        details: Mapping[str, Any],
    ) -> None:
        connection.execute(
            insert(recovery_audits).values(
                audit_id=str(uuid4()),
                event_id=event_id,
                action=action,
                details_json=json.dumps(dict(details), sort_keys=True),
                created_at=_iso(utc_now()),
            )
        )

    def _safe_data_path(self, relative_path: str) -> Path:
        path = (self.data_dir / relative_path).resolve()
        if path != self.data_dir and self.data_dir not in path.parents:
            raise ArchiveInvariantError("archive path escapes the configured data directory")
        return path
