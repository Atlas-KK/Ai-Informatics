"""SQLite persistence for Phase 3 source configuration and collection queues."""

import json
import os
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

from sqlalchemy import Engine, delete, insert, select, update
from sqlalchemy.exc import IntegrityError

from ai_intel.domain.source import (
    CollectedItem,
    CollectionBatch,
    CollectionFailure,
    CollectionRunPlan,
    CollectionStatus,
    CollectionWindow,
    ExpertWhitelistEntry,
    SourceConfig,
    SourceDraft,
    SourceState,
    SourceType,
)
from ai_intel.domain.source_metrics import MetricSnapshot
from ai_intel.infrastructure.db.schema import (
    collected_raw_snapshots,
    collection_failures,
    collection_runs,
    expert_source_links,
    expert_whitelist,
    manual_inbox_imports,
    source_configs,
    source_metric_snapshots,
)
from ai_intel.infrastructure.telemetry.redaction import redact_text


class SourceRepositoryError(RuntimeError):
    pass


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat()


def _datetime(value: object) -> datetime:
    return datetime.fromisoformat(str(value))


def _mapping(row: Any) -> Mapping[str, Any]:
    return cast(Mapping[str, Any], row._mapping)  # noqa: SLF001


def _now() -> datetime:
    return datetime.now(UTC)


class SQLiteSourceRepository:
    def __init__(self, engine: Engine, data_dir: Path) -> None:
        self.engine = engine
        self.data_dir = data_dir.resolve()
        self.raw_dir = self.data_dir / "raw" / "collected"
        self.raw_dir.mkdir(parents=True, exist_ok=True)

    def create_source(self, draft: SourceDraft) -> SourceConfig:
        now = _now()
        source_id = str(uuid4())
        with self.engine.begin() as connection:
            connection.execute(
                insert(source_configs).values(
                    source_id=source_id,
                    name=draft.name.strip(),
                    source_type=draft.source_type.value,
                    url=draft.url,
                    topic=draft.topic.strip(),
                    authority_level=draft.authority_level,
                    truncate_chars=draft.truncate_chars,
                    state=SourceState.ACTIVE.value,
                    created_at=_iso(now),
                    updated_at=_iso(now),
                    deleted_at=None,
                )
            )
        return self.get_source(source_id, include_deleted=True)

    def update_source(self, source_id: str, draft: SourceDraft) -> SourceConfig:
        current = self.get_source(source_id, include_deleted=True)
        if current.state is SourceState.DELETED:
            raise SourceRepositoryError("deleted source configuration is read-only")
        with self.engine.begin() as connection:
            connection.execute(
                update(source_configs)
                .where(source_configs.c.source_id == source_id)
                .values(
                    name=draft.name.strip(),
                    source_type=draft.source_type.value,
                    url=draft.url,
                    topic=draft.topic.strip(),
                    authority_level=draft.authority_level,
                    truncate_chars=draft.truncate_chars,
                    updated_at=_iso(_now()),
                )
            )
        return self.get_source(source_id, include_deleted=True)

    def set_source_state(self, source_id: str, state: SourceState) -> SourceConfig:
        current = self.get_source(source_id, include_deleted=True)
        if current.state is SourceState.DELETED:
            raise SourceRepositoryError("deleted source cannot be resumed or paused")
        now = _now()
        with self.engine.begin() as connection:
            connection.execute(
                update(source_configs)
                .where(source_configs.c.source_id == source_id)
                .values(
                    state=state.value,
                    updated_at=_iso(now),
                    deleted_at=_iso(now) if state is SourceState.DELETED else None,
                )
            )
        return self.get_source(source_id, include_deleted=True)

    def get_source(self, source_id: str, *, include_deleted: bool = False) -> SourceConfig:
        statement = select(source_configs).where(source_configs.c.source_id == source_id)
        if not include_deleted:
            statement = statement.where(source_configs.c.state != SourceState.DELETED.value)
        with self.engine.connect() as connection:
            row = connection.execute(statement).first()
        if row is None:
            raise SourceRepositoryError("unknown source")
        return self._source(_mapping(row))

    def list_sources(self, *, include_deleted: bool = False) -> tuple[SourceConfig, ...]:
        statement = select(source_configs).order_by(source_configs.c.created_at)
        if not include_deleted:
            statement = statement.where(source_configs.c.state != SourceState.DELETED.value)
        with self.engine.connect() as connection:
            rows = connection.execute(statement).all()
        return tuple(self._source(_mapping(row)) for row in rows)

    def create_expert(self, name: str, source_ids: Sequence[str]) -> ExpertWhitelistEntry:
        if not name.strip():
            raise SourceRepositoryError("expert name is required")
        normalized = tuple(dict.fromkeys(source_ids))
        for source_id in normalized:
            self.get_source(source_id)
        expert_id = str(uuid4())
        now = _now()
        with self.engine.begin() as connection:
            connection.execute(
                insert(expert_whitelist).values(
                    expert_id=expert_id,
                    name=name.strip(),
                    state=SourceState.ACTIVE.value,
                    created_at=_iso(now),
                    updated_at=_iso(now),
                    deleted_at=None,
                )
            )
            if normalized:
                connection.execute(
                    insert(expert_source_links),
                    [
                        {"expert_id": expert_id, "source_id": source_id, "created_at": _iso(now)}
                        for source_id in normalized
                    ],
                )
        return self.get_expert(expert_id, include_deleted=True)

    def update_expert(
        self, expert_id: str, name: str, source_ids: Sequence[str]
    ) -> ExpertWhitelistEntry:
        current = self.get_expert(expert_id, include_deleted=True)
        if current.state is SourceState.DELETED:
            raise SourceRepositoryError("deleted expert is read-only")
        if not name.strip():
            raise SourceRepositoryError("expert name is required")
        normalized = tuple(dict.fromkeys(source_ids))
        for source_id in normalized:
            self.get_source(source_id)
        now = _now()
        with self.engine.begin() as connection:
            connection.execute(
                update(expert_whitelist)
                .where(expert_whitelist.c.expert_id == expert_id)
                .values(name=name.strip(), updated_at=_iso(now))
            )
            connection.execute(
                delete(expert_source_links).where(expert_source_links.c.expert_id == expert_id)
            )
            if normalized:
                connection.execute(
                    insert(expert_source_links),
                    [
                        {"expert_id": expert_id, "source_id": source_id, "created_at": _iso(now)}
                        for source_id in normalized
                    ],
                )
        return self.get_expert(expert_id, include_deleted=True)

    def set_expert_state(self, expert_id: str, state: SourceState) -> ExpertWhitelistEntry:
        current = self.get_expert(expert_id, include_deleted=True)
        if current.state is SourceState.DELETED:
            raise SourceRepositoryError("deleted expert cannot be resumed or paused")
        now = _now()
        with self.engine.begin() as connection:
            connection.execute(
                update(expert_whitelist)
                .where(expert_whitelist.c.expert_id == expert_id)
                .values(
                    state=state.value,
                    updated_at=_iso(now),
                    deleted_at=_iso(now) if state is SourceState.DELETED else None,
                )
            )
        return self.get_expert(expert_id, include_deleted=True)

    def get_expert(self, expert_id: str, *, include_deleted: bool = False) -> ExpertWhitelistEntry:
        statement = select(expert_whitelist).where(expert_whitelist.c.expert_id == expert_id)
        if not include_deleted:
            statement = statement.where(expert_whitelist.c.state != SourceState.DELETED.value)
        with self.engine.connect() as connection:
            row = connection.execute(statement).first()
            if row is None:
                raise SourceRepositoryError("unknown expert")
            links = tuple(
                str(value)
                for value in connection.execute(
                    select(expert_source_links.c.source_id)
                    .where(expert_source_links.c.expert_id == expert_id)
                    .order_by(expert_source_links.c.source_id)
                ).scalars()
            )
        value = _mapping(row)
        return ExpertWhitelistEntry(
            expert_id=str(value["expert_id"]),
            name=str(value["name"]),
            source_ids=links,
            state=SourceState(str(value["state"])),
            created_at=_datetime(value["created_at"]),
            updated_at=_datetime(value["updated_at"]),
        )

    def list_experts(self, *, include_deleted: bool = False) -> tuple[ExpertWhitelistEntry, ...]:
        statement = select(expert_whitelist.c.expert_id).order_by(expert_whitelist.c.created_at)
        if not include_deleted:
            statement = statement.where(expert_whitelist.c.state != SourceState.DELETED.value)
        with self.engine.connect() as connection:
            expert_ids = tuple(str(value) for value in connection.execute(statement).scalars())
        return tuple(
            self.get_expert(expert_id, include_deleted=include_deleted) for expert_id in expert_ids
        )

    def plan_run(self, started_at: datetime) -> CollectionRunPlan:
        window = CollectionWindow.from_started_at(started_at)
        sources = tuple(
            source for source in self.list_sources() if source.state is SourceState.ACTIVE
        )
        run_id = str(uuid4())
        with self.engine.begin() as connection:
            connection.execute(
                insert(collection_runs).values(
                    run_id=run_id,
                    started_at=_iso(window.started_at),
                    window_start=_iso(window.window_start),
                    window_end=_iso(window.window_end),
                    automatic_source_count=len(sources),
                    status="PLANNED",
                )
            )
        return CollectionRunPlan(run_id, window, sources, len(sources))

    def finish_run(self, run_id: str) -> None:
        with self.engine.begin() as connection:
            result = connection.execute(
                update(collection_runs)
                .where(collection_runs.c.run_id == run_id)
                .values(status="FINISHED")
            )
        if result.rowcount != 1:
            raise SourceRepositoryError("unknown collection run")

    def save_batch(self, run_id: str | None, batch: CollectionBatch) -> tuple[str, ...]:
        snapshot_ids: list[str] = []
        for item in batch.items:
            snapshot_id = self.save_item(run_id, item)
            if snapshot_id is not None:
                snapshot_ids.append(snapshot_id)
        for failure in batch.failures:
            self.save_failure(run_id, failure)
        return tuple(snapshot_ids)

    def save_item(self, run_id: str | None, item: CollectedItem) -> str | None:
        if item.status not in {CollectionStatus.COLLECTED, CollectionStatus.METADATA_ONLY}:
            raise SourceRepositoryError("only collected or metadata-only items may enter the queue")
        content_hash = sha256(item.raw_content.encode("utf-8")).hexdigest()
        import_key = sha256(
            f"{item.source_id}\0{item.external_id}\0{content_hash}".encode()
        ).hexdigest()
        with self.engine.connect() as connection:
            existing = connection.execute(
                select(collected_raw_snapshots.c.snapshot_id).where(
                    collected_raw_snapshots.c.import_key == import_key
                )
            ).scalar_one_or_none()
        if existing is not None:
            return None

        snapshot_id = str(uuid4())
        relative_path = Path("raw") / "collected" / f"{snapshot_id}.txt"
        target = self.data_dir / relative_path
        temporary = target.with_suffix(".tmp")
        with temporary.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(item.raw_content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
        try:
            with self.engine.begin() as connection:
                connection.execute(
                    insert(collected_raw_snapshots).values(
                        snapshot_id=snapshot_id,
                        import_key=import_key,
                        run_id=run_id,
                        source_id=item.source_id,
                        source_type=item.source_type.value,
                        external_id=item.external_id,
                        url=item.url,
                        title=item.title,
                        author=item.author,
                        published_at=_iso(item.published_at),
                        published_at_unknown=item.published_at_unknown,
                        first_seen_at=_iso(item.first_seen_at),
                        content_hash=content_hash,
                        raw_path=relative_path.as_posix(),
                        model_input=item.model_input,
                        metadata_json=json.dumps(dict(item.metadata), ensure_ascii=False),
                        status=item.status.value,
                        created_at=_iso(_now()),
                    )
                )
        except IntegrityError:
            target.unlink(missing_ok=True)
            return None
        return snapshot_id

    def save_failure(self, run_id: str | None, failure: CollectionFailure) -> str:
        failure_id = str(uuid4())
        with self.engine.begin() as connection:
            connection.execute(
                insert(collection_failures).values(
                    failure_id=failure_id,
                    run_id=run_id,
                    source_id=failure.source_id,
                    stage=failure.stage.value,
                    reason=redact_text(failure.reason),
                    occurred_at=_iso(failure.occurred_at),
                    retry_count=failure.retry_count,
                )
            )
        return failure_id

    def list_failures(self, run_id: str | None = None) -> tuple[Mapping[str, Any], ...]:
        statement = select(collection_failures).order_by(collection_failures.c.occurred_at)
        if run_id is not None:
            statement = statement.where(collection_failures.c.run_id == run_id)
        with self.engine.connect() as connection:
            rows = connection.execute(statement).all()
        return tuple(dict(_mapping(row)) for row in rows)

    def list_collected(self, run_id: str | None = None) -> tuple[Mapping[str, Any], ...]:
        statement = select(collected_raw_snapshots).order_by(collected_raw_snapshots.c.created_at)
        if run_id is not None:
            statement = statement.where(collected_raw_snapshots.c.run_id == run_id)
        with self.engine.connect() as connection:
            rows = connection.execute(statement).all()
        return tuple(dict(_mapping(row)) for row in rows)

    def list_collected_paths(self) -> set[str]:
        with self.engine.connect() as connection:
            paths = connection.execute(select(collected_raw_snapshots.c.raw_path)).scalars()
            return {str(path) for path in paths}

    def add_metric_snapshot(self, snapshot: MetricSnapshot) -> None:
        with self.engine.begin() as connection:
            connection.execute(
                insert(source_metric_snapshots).values(
                    snapshot_id=snapshot.snapshot_id,
                    source_id=snapshot.source_id,
                    subject_key=snapshot.subject_key,
                    metric_type=snapshot.metric_type,
                    observed_at=_iso(snapshot.observed_at),
                    value=snapshot.value,
                    response_id=snapshot.response_id,
                )
            )

    def metric_history(self, subject_key: str, metric_type: str) -> tuple[MetricSnapshot, ...]:
        with self.engine.connect() as connection:
            rows = connection.execute(
                select(source_metric_snapshots)
                .where(
                    source_metric_snapshots.c.subject_key == subject_key,
                    source_metric_snapshots.c.metric_type == metric_type,
                )
                .order_by(source_metric_snapshots.c.observed_at)
            ).all()
        return tuple(
            MetricSnapshot(
                snapshot_id=str(value["snapshot_id"]),
                source_id=str(value["source_id"]),
                subject_key=str(value["subject_key"]),
                metric_type=str(value["metric_type"]),
                observed_at=_datetime(value["observed_at"]),
                value=int(value["value"]),
                response_id=str(value["response_id"]),
            )
            for value in (_mapping(row) for row in rows)
        )

    def get_manual_import(self, file_hash: str) -> Mapping[str, Any] | None:
        with self.engine.connect() as connection:
            row = connection.execute(
                select(manual_inbox_imports).where(manual_inbox_imports.c.file_hash == file_hash)
            ).first()
        return None if row is None else dict(_mapping(row))

    def record_manual_import(
        self,
        *,
        file_hash: str,
        file_path: str,
        status: str,
        error: str | None,
        retry_count: int,
        snapshot_id: str | None,
        imported_at: datetime,
    ) -> str:
        import_id = str(uuid4())
        with self.engine.begin() as connection:
            connection.execute(
                insert(manual_inbox_imports).values(
                    import_id=import_id,
                    file_hash=file_hash,
                    file_path=file_path,
                    status=status,
                    error=error,
                    retry_count=retry_count,
                    snapshot_id=snapshot_id,
                    imported_at=_iso(imported_at),
                )
            )
        return import_id

    def update_manual_failure(
        self,
        *,
        file_hash: str,
        error: str,
        retry_count: int,
        imported_at: datetime,
    ) -> None:
        with self.engine.begin() as connection:
            result = connection.execute(
                update(manual_inbox_imports)
                .where(manual_inbox_imports.c.file_hash == file_hash)
                .values(
                    error=error,
                    retry_count=retry_count,
                    imported_at=_iso(imported_at),
                )
            )
        if result.rowcount != 1:
            raise SourceRepositoryError("unknown Manual Inbox import")

    @staticmethod
    def _source(value: Mapping[str, Any]) -> SourceConfig:
        return SourceConfig(
            source_id=str(value["source_id"]),
            name=str(value["name"]),
            source_type=SourceType(str(value["source_type"])),
            url=str(value["url"]),
            topic=str(value["topic"]),
            authority_level=int(value["authority_level"]),
            truncate_chars=int(value["truncate_chars"]),
            state=SourceState(str(value["state"])),
            created_at=_datetime(value["created_at"]),
            updated_at=_datetime(value["updated_at"]),
        )
