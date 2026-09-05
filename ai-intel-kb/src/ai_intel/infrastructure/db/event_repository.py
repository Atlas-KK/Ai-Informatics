"""SQLite repository for Phase 4 pre-scoring event aggregates."""

import json
from collections.abc import Mapping
from datetime import UTC, date, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

from sqlalchemy import Engine, insert, select, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from ai_intel.domain.event_matching import EventMatchProfile
from ai_intel.domain.fingerprint import CandidateOrigin, MatchKey, MatchKeyKind, SnapshotDraft
from ai_intel.domain.versioning import (
    ChangeDecision,
    ChangeType,
    EventVersionState,
    VersionDraft,
    VersionEvidence,
)
from ai_intel.infrastructure.db.schema import (
    aggregate_evidence,
    aggregate_versions,
    aggregate_viewpoints,
    aggregation_audits,
    collected_raw_snapshots,
    daily_event_candidates,
    event_aggregates,
    event_match_keys,
)


class EventRepositoryError(RuntimeError):
    pass


def _mapping(row: Any) -> Mapping[str, Any]:
    return cast(Mapping[str, Any], row._mapping)  # noqa: SLF001


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat()


class SQLiteEventRepository:
    def __init__(self, engine: Engine, data_dir: Path) -> None:
        self.engine = engine
        self.data_dir = data_dir.resolve()

    def load_snapshot_draft(
        self,
        snapshot_id: str,
        *,
        origin: CandidateOrigin | None = None,
        selected_for_ingestion: bool = True,
    ) -> SnapshotDraft:
        with self.engine.connect() as connection:
            row = connection.execute(
                select(collected_raw_snapshots).where(
                    collected_raw_snapshots.c.snapshot_id == snapshot_id
                )
            ).first()
        if row is None:
            raise EventRepositoryError(f"unknown collected snapshot: {snapshot_id}")
        value = _mapping(row)
        raw_path = (self.data_dir / str(value["raw_path"])).resolve()
        if self.data_dir not in raw_path.parents:
            raise EventRepositoryError("raw snapshot path escapes data directory")
        with raw_path.open("r", encoding="utf-8", newline="") as stream:
            raw_content = stream.read()
        if sha256(raw_content.encode("utf-8")).hexdigest() != str(value["content_hash"]):
            raise EventRepositoryError("raw snapshot hash mismatch")
        metadata = json.loads(str(value["metadata_json"]))
        entities_value = metadata.get("entities", ())
        entities = (
            tuple(str(item) for item in entities_value)
            if isinstance(entities_value, list | tuple)
            else ()
        )
        viewpoint = metadata.get("viewpoint")
        effective_origin = origin
        if effective_origin is None:
            effective_origin = (
                CandidateOrigin.MANUAL_INBOX
                if str(value["source_type"]) == "MANUAL_INBOX"
                else CandidateOrigin.COLLECTOR
            )
        return SnapshotDraft(
            snapshot_id=snapshot_id,
            source_id=str(value["source_id"]),
            title=str(value["title"]),
            url=str(value["url"]),
            author=None if value["author"] is None else str(value["author"]),
            published_at=datetime.fromisoformat(str(value["published_at"])),
            raw_content=raw_content,
            viewpoint=str(viewpoint) if isinstance(viewpoint, str) else str(value["title"]),
            entities=entities,
            origin=effective_origin,
            selected_for_ingestion=selected_for_ingestion,
            captured_at=datetime.fromisoformat(str(value["created_at"])),
        )

    def list_match_profiles(self) -> tuple[EventMatchProfile, ...]:
        with self.engine.connect() as connection:
            aggregate_rows = connection.execute(
                select(event_aggregates).order_by(event_aggregates.c.event_id)
            ).all()
            key_rows = connection.execute(
                select(event_match_keys).order_by(
                    event_match_keys.c.event_id,
                    event_match_keys.c.key_kind,
                    event_match_keys.c.key_value,
                )
            ).all()
            version_rows = connection.execute(
                select(aggregate_versions.c.event_id, aggregate_versions.c.entities_json)
                .where(aggregate_versions.c.version_no == event_aggregates.c.current_version)
                .select_from(
                    aggregate_versions.join(
                        event_aggregates,
                        aggregate_versions.c.event_id == event_aggregates.c.event_id,
                    )
                )
            ).all()
        keys: dict[str, list[tuple[MatchKeyKind, str]]] = {}
        for row in key_rows:
            item = _mapping(row)
            keys.setdefault(str(item["event_id"]), []).append(
                (MatchKeyKind(str(item["key_kind"])), str(item["key_value"]))
            )
        entities = {
            str(_mapping(row)["event_id"]): tuple(json.loads(str(_mapping(row)["entities_json"])))
            for row in version_rows
        }
        return tuple(
            EventMatchProfile(
                event_id=str(value["event_id"]),
                normalized_title=str(value["normalized_title"]),
                entities=entities.get(str(value["event_id"]), ()),
                keys=tuple(keys.get(str(value["event_id"]), ())),
            )
            for value in (_mapping(row) for row in aggregate_rows)
        )

    def get_current_state(self, event_id: str) -> EventVersionState | None:
        with self.engine.connect() as connection:
            version = connection.execute(
                select(aggregate_versions)
                .join(
                    event_aggregates,
                    aggregate_versions.c.event_id == event_aggregates.c.event_id,
                )
                .where(
                    event_aggregates.c.event_id == event_id,
                    aggregate_versions.c.version_no == event_aggregates.c.current_version,
                )
            ).first()
            if version is None:
                return None
            value = _mapping(version)
            rows = connection.execute(
                select(
                    aggregate_evidence,
                    collected_raw_snapshots.c.created_at.label("captured_at"),
                )
                .join(
                    collected_raw_snapshots,
                    aggregate_evidence.c.upstream_snapshot_id
                    == collected_raw_snapshots.c.snapshot_id,
                )
                .where(aggregate_evidence.c.aggregate_version_id == value["aggregate_version_id"])
                .order_by(
                    aggregate_evidence.c.source_id,
                    aggregate_evidence.c.url,
                    aggregate_evidence.c.upstream_snapshot_id,
                )
            ).all()
        evidence = tuple(
            VersionEvidence(
                snapshot_id=str(item["upstream_snapshot_id"]),
                source_id=str(item["source_id"]),
                url=str(item["url"]),
                published_at=str(item["published_at"]),
                captured_at=str(item["captured_at"]),
                viewpoint=str(item["viewpoint"]),
                normalized_viewpoint=str(item["normalized_viewpoint"]),
                normalized_content=str(item["normalized_content"]),
                content_hash=str(item["content_hash"]),
            )
            for item in (_mapping(row) for row in rows)
        )
        return EventVersionState(
            event_id=event_id,
            version_no=int(value["version_no"]),
            canonical_title=str(value["canonical_title"]),
            normalized_title=str(value["normalized_title"]),
            normalized_content=str(value["normalized_content"]),
            content_hash=str(value["content_hash"]),
            entities=tuple(json.loads(str(value["entities_json"]))),
            evidence=evidence,
        )

    def save_version(
        self,
        *,
        event_id: str,
        stable_key: str,
        match_keys: tuple[MatchKey, ...],
        decision: ChangeDecision,
        draft: VersionDraft,
        incoming_snapshot_ids: tuple[str, ...],
        report_date: date,
        observed_at: datetime,
    ) -> tuple[int, str]:
        if not decision.create_version or decision.change_type is ChangeType.NO_CHANGE:
            raise EventRepositoryError("save_version requires a material change")
        now = _iso(observed_at)
        existing = self.get_current_state(event_id)
        version_no = 1 if existing is None else existing.version_no + 1
        version_id = str(uuid4())
        with self.engine.begin() as connection:
            if existing is None:
                connection.execute(
                    insert(event_aggregates).values(
                        event_id=event_id,
                        stable_key=stable_key,
                        canonical_title=draft.canonical_title,
                        normalized_title=draft.normalized_title,
                        current_version=version_no,
                        created_at=now,
                        updated_at=now,
                    )
                )
            connection.execute(
                sqlite_insert(event_match_keys)
                .values(
                    [
                        {
                            "event_id": event_id,
                            "key_kind": key.kind.value,
                            "key_value": key.value,
                            "created_at": now,
                        }
                        for key in match_keys
                    ]
                )
                .on_conflict_do_nothing(index_elements=["event_id", "key_kind", "key_value"])
            )
            connection.execute(
                insert(aggregate_versions).values(
                    aggregate_version_id=version_id,
                    event_id=event_id,
                    version_no=version_no,
                    change_type=decision.change_type.value,
                    change_reasons_json=json.dumps([reason.value for reason in decision.reasons]),
                    canonical_title=draft.canonical_title,
                    normalized_title=draft.normalized_title,
                    normalized_content=draft.normalized_content,
                    content_hash=draft.content_hash,
                    entities_json=json.dumps(draft.entities, ensure_ascii=False),
                    created_at=now,
                )
            )
            connection.execute(
                insert(aggregate_evidence),
                [
                    {
                        "evidence_id": str(uuid4()),
                        "aggregate_version_id": version_id,
                        "upstream_snapshot_id": item.snapshot_id,
                        "source_id": item.source_id,
                        "url": item.url,
                        "published_at": item.published_at,
                        "viewpoint": item.viewpoint,
                        "normalized_viewpoint": item.normalized_viewpoint,
                        "normalized_content": item.normalized_content,
                        "content_hash": item.content_hash,
                    }
                    for item in draft.evidence
                ],
            )
            connection.execute(
                insert(aggregate_viewpoints),
                [
                    {
                        "viewpoint_id": str(uuid4()),
                        "aggregate_version_id": version_id,
                        "statement": item.statement,
                        "normalized_statement": next(
                            evidence.normalized_viewpoint
                            for evidence in draft.evidence
                            if evidence.viewpoint == item.statement
                        ),
                        "source_ids_json": json.dumps(item.source_ids),
                        "supporting_source_count": item.supporting_source_count,
                        "valid_source_count": item.valid_source_count,
                        "source_coverage_ratio": item.source_coverage_ratio,
                    }
                    for item in draft.viewpoints
                ],
            )
            if existing is not None:
                result = connection.execute(
                    update(event_aggregates)
                    .where(
                        event_aggregates.c.event_id == event_id,
                        event_aggregates.c.current_version == existing.version_no,
                    )
                    .values(
                        canonical_title=draft.canonical_title,
                        normalized_title=draft.normalized_title,
                        current_version=version_no,
                        updated_at=now,
                    )
                )
                if result.rowcount != 1:
                    raise EventRepositoryError("concurrent aggregate version update")
            candidate = sqlite_insert(daily_event_candidates).values(
                candidate_id=str(uuid4()),
                report_date=report_date.isoformat(),
                event_id=event_id,
                aggregate_version_id=version_id,
                change_type=decision.change_type.value,
                needs_scoring=decision.needs_scoring,
                created_at=now,
                updated_at=now,
            )
            connection.execute(
                candidate.on_conflict_do_update(
                    index_elements=["report_date", "event_id"],
                    set_={
                        "aggregate_version_id": version_id,
                        "change_type": decision.change_type.value,
                        "needs_scoring": decision.needs_scoring,
                        "updated_at": now,
                    },
                )
            )
            self._insert_audit(
                connection,
                event_id,
                incoming_snapshot_ids,
                decision,
                now,
            )
        return version_no, version_id

    def record_decision(
        self,
        event_id: str | None,
        snapshot_ids: tuple[str, ...],
        decision: ChangeDecision,
        observed_at: datetime,
    ) -> None:
        with self.engine.begin() as connection:
            self._insert_audit(connection, event_id, snapshot_ids, decision, _iso(observed_at))

    @staticmethod
    def _insert_audit(
        connection: Any,
        event_id: str | None,
        snapshot_ids: tuple[str, ...],
        decision: ChangeDecision,
        created_at: str,
    ) -> None:
        connection.execute(
            insert(aggregation_audits).values(
                audit_id=str(uuid4()),
                event_id=event_id,
                snapshot_ids_json=json.dumps(sorted(set(snapshot_ids))),
                change_type=decision.change_type.value,
                reasons_json=json.dumps([reason.value for reason in decision.reasons]),
                created_at=created_at,
            )
        )

    def table_rows(self, table: Any) -> tuple[Mapping[str, Any], ...]:
        with self.engine.connect() as connection:
            rows = connection.execute(select(table)).all()
        return tuple(dict(_mapping(row)) for row in rows)
