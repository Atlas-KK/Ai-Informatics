"""SQLite persistence for Phase 5 pre-archive intelligence decisions."""

import json
import math
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from types import MappingProxyType
from typing import Any, cast
from uuid import uuid4

from sqlalchemy import Engine, func, insert, select, update

from ai_intel.domain.ai_processing import (
    ConclusionPayload,
    ProcessedIntelligence,
    ProcessingPayload,
    SourceLanguage,
)
from ai_intel.domain.fingerprint import CandidateOrigin
from ai_intel.domain.scoring import DEFAULT_WEIGHTS, ScoreResult, ScoringConfig
from ai_intel.domain.states import ScoringConfigStatus
from ai_intel.domain.tiering import RankedCandidate, ScoredCandidate
from ai_intel.domain.topics import PrimaryTopic
from ai_intel.infrastructure.db.schema import (
    active_scoring_config,
    aggregate_evidence,
    aggregate_versions,
    ai_processing_failures,
    ai_processing_results,
    calibration_decisions,
    calibration_proposals,
    candidate_scores,
    collected_raw_snapshots,
    daily_event_candidates,
    daily_selection_runs,
    daily_selections,
    formalization_links,
    quality_feedback,
    scoring_config_audits,
    scoring_configs,
    source_configs,
    topic_ideas,
)


class IntelligenceRepositoryError(RuntimeError):
    pass


def _mapping(row: Any) -> Mapping[str, Any]:
    return cast(Mapping[str, Any], row._mapping)  # noqa: SLF001


def _iso(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must include a timezone")
    return value.astimezone(UTC).isoformat()


@dataclass(frozen=True, slots=True)
class CandidateEvidence:
    evidence_id: str
    snapshot_id: str
    source_id: str
    url: str
    published_at: datetime
    viewpoint: str
    normalized_content: str


@dataclass(frozen=True, slots=True)
class CandidateContext:
    candidate_id: str
    report_date: date
    event_id: str
    aggregate_version_id: str
    aggregate_version_no: int
    change_type: str
    canonical_title: str
    original_text: str
    origin: CandidateOrigin
    evidence: tuple[CandidateEvidence, ...]
    base_source_authority: float
    source_authorities: Mapping[str, float]
    reach_score: float | None


@dataclass(frozen=True, slots=True)
class StoredCandidateScore:
    score_id: str
    aggregate_version_id: str
    event_id: str
    config_version: int
    result: ScoreResult

    def as_rankable(self) -> ScoredCandidate:
        return ScoredCandidate(
            event_id=self.event_id,
            aggregate_version_id=self.aggregate_version_id,
            score_id=self.score_id,
            total=self.result.total,
            timeliness=self.result.dimensions["timeliness"],
            source_authority=self.result.dimensions["source_authority"],
        )


@dataclass(frozen=True, slots=True)
class SavedSelection:
    selection_id: str
    ranked: RankedCandidate


@dataclass(frozen=True, slots=True)
class CalibrationProposalRecord:
    proposal_id: str
    base_config_version: int
    sample_count: int
    uncertainty: str
    affected_dimensions: tuple[str, ...]
    suggested_weights: Mapping[str, float]
    suggested_source_overrides: Mapping[str, float]
    estimated_impact: Mapping[str, Any]


class SQLiteIntelligenceRepository:
    def __init__(self, engine: Engine, data_dir: Path) -> None:
        self.engine = engine
        self.data_dir = data_dir.resolve()

    def list_candidate_contexts(self, report_date: date) -> tuple[CandidateContext, ...]:
        with self.engine.connect() as connection:
            candidate_rows = connection.execute(
                select(
                    daily_event_candidates,
                    aggregate_versions.c.version_no,
                    aggregate_versions.c.canonical_title,
                )
                .join(
                    aggregate_versions,
                    daily_event_candidates.c.aggregate_version_id
                    == aggregate_versions.c.aggregate_version_id,
                )
                .where(daily_event_candidates.c.report_date == report_date.isoformat())
                .order_by(daily_event_candidates.c.event_id)
            ).all()
            values = tuple(_mapping(row) for row in candidate_rows)
            version_ids = tuple(str(value["aggregate_version_id"]) for value in values)
            if not version_ids:
                return ()
            evidence_rows = connection.execute(
                self._candidate_evidence_query().where(
                    aggregate_evidence.c.aggregate_version_id.in_(version_ids)
                )
            ).all()
            authority_rows = connection.execute(
                select(source_configs.c.source_id, source_configs.c.authority_level)
            ).all()
        evidence_by_version: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
        for row in evidence_rows:
            item = _mapping(row)
            evidence_by_version[str(item["aggregate_version_id"])].append(item)
        authority = self._authority_levels(authority_rows)
        return tuple(
            self._candidate_context(
                value,
                evidence_by_version[str(value["aggregate_version_id"])],
                authority,
            )
            for value in values
        )

    def get_candidate_context(self, aggregate_version_id: str) -> CandidateContext:
        with self.engine.connect() as connection:
            row = connection.execute(
                select(
                    daily_event_candidates,
                    aggregate_versions.c.version_no,
                    aggregate_versions.c.canonical_title,
                )
                .join(
                    aggregate_versions,
                    daily_event_candidates.c.aggregate_version_id
                    == aggregate_versions.c.aggregate_version_id,
                )
                .where(daily_event_candidates.c.aggregate_version_id == aggregate_version_id)
            ).first()
            if row is None:
                raise IntelligenceRepositoryError("unknown daily candidate")
            value = _mapping(row)
            evidence_rows = connection.execute(
                self._candidate_evidence_query().where(
                    aggregate_evidence.c.aggregate_version_id == aggregate_version_id
                )
            ).all()
            authority_rows = connection.execute(
                select(source_configs.c.source_id, source_configs.c.authority_level)
            ).all()
        return self._candidate_context(
            value,
            tuple(_mapping(item) for item in evidence_rows),
            self._authority_levels(authority_rows),
        )

    @staticmethod
    def _candidate_evidence_query() -> Any:
        return (
            select(
                aggregate_evidence,
                collected_raw_snapshots.c.source_type,
                collected_raw_snapshots.c.metadata_json,
                collected_raw_snapshots.c.model_input,
            )
            .join(
                collected_raw_snapshots,
                aggregate_evidence.c.upstream_snapshot_id == collected_raw_snapshots.c.snapshot_id,
            )
            .order_by(
                aggregate_evidence.c.aggregate_version_id,
                aggregate_evidence.c.source_id,
                aggregate_evidence.c.evidence_id,
            )
        )

    @staticmethod
    def _authority_levels(rows: Sequence[Any]) -> dict[str, int]:
        return {
            str(_mapping(item)["source_id"]): int(_mapping(item)["authority_level"])
            for item in rows
        }

    def _candidate_context(
        self,
        value: Mapping[str, Any],
        items: list[Mapping[str, Any]] | tuple[Mapping[str, Any], ...],
        authority: Mapping[str, int],
    ) -> CandidateContext:
        if not items:
            raise IntelligenceRepositoryError("candidate has no evidence")
        evidence = tuple(
            CandidateEvidence(
                evidence_id=str(item["evidence_id"]),
                snapshot_id=str(item["upstream_snapshot_id"]),
                source_id=str(item["source_id"]),
                url=str(item["url"]),
                published_at=datetime.fromisoformat(str(item["published_at"])),
                viewpoint=str(item["viewpoint"]),
                normalized_content=str(item["normalized_content"]),
            )
            for item in items
        )
        source_types = {str(item["source_type"]) for item in items}
        metadata_origins = {
            str(origin_value)
            for item in items
            if isinstance(
                (origin_value := json.loads(str(item["metadata_json"])).get("origin")), str
            )
        }
        if metadata_origins == {CandidateOrigin.EXTENDED_SEARCH.value}:
            origin = CandidateOrigin.EXTENDED_SEARCH
        elif source_types == {"MANUAL_INBOX"}:
            origin = CandidateOrigin.MANUAL_INBOX
        else:
            origin = CandidateOrigin.COLLECTOR
        source_authorities = {
            item.source_id: min(40.0 + (authority.get(item.source_id, 3) - 1) * 15.0, 100.0)
            for item in evidence
        }
        authority_score = max(source_authorities.values(), default=70.0)
        reach_values = [
            score
            for item in items
            if (score := self._reach_from_metadata(str(item["metadata_json"]))) is not None
        ]
        original_text = "\n\n".join(str(item["model_input"]) for item in items)
        return CandidateContext(
            candidate_id=str(value["candidate_id"]),
            report_date=date.fromisoformat(str(value["report_date"])),
            event_id=str(value["event_id"]),
            aggregate_version_id=str(value["aggregate_version_id"]),
            aggregate_version_no=int(value["version_no"]),
            change_type=str(value["change_type"]),
            canonical_title=str(value["canonical_title"]),
            original_text=original_text,
            origin=origin,
            evidence=evidence,
            base_source_authority=min(authority_score, 100.0),
            source_authorities=MappingProxyType(source_authorities),
            reach_score=max(reach_values) if reach_values else None,
        )

    @staticmethod
    def _reach_from_metadata(raw_json: str) -> float | None:
        value = json.loads(raw_json)
        direct = value.get("reach_score")
        if isinstance(direct, int | float) and not isinstance(direct, bool):
            return max(0.0, min(100.0, float(direct)))
        stars = value.get("stars")
        if isinstance(stars, int | float) and not isinstance(stars, bool) and stars >= 0:
            return min(100.0, round(20.0 * math.log10(float(stars) + 1.0), 2))
        return None

    def ensure_default_config(self, created_at: datetime) -> ScoringConfig:
        with self.engine.begin() as connection:
            current = connection.execute(
                select(active_scoring_config.c.config_version).where(
                    active_scoring_config.c.singleton_id == 1
                )
            ).scalar_one_or_none()
            if current is None:
                existing_one = connection.execute(
                    select(scoring_configs.c.config_version).where(
                        scoring_configs.c.config_version == 1
                    )
                ).scalar_one_or_none()
                if existing_one is None:
                    connection.execute(
                        insert(scoring_configs).values(
                            config_version=1,
                            weights_json=json.dumps(dict(DEFAULT_WEIGHTS), sort_keys=True),
                            source_overrides_json="{}",
                            status=ScoringConfigStatus.ACTIVE.value,
                            created_at=_iso(created_at),
                        )
                    )
                else:
                    connection.execute(
                        update(scoring_configs)
                        .where(scoring_configs.c.config_version == 1)
                        .values(status=ScoringConfigStatus.ACTIVE.value)
                    )
                connection.execute(
                    insert(active_scoring_config).values(
                        singleton_id=1,
                        config_version=1,
                        changed_at=_iso(created_at),
                    )
                )
                connection.execute(
                    insert(scoring_config_audits).values(
                        audit_id=str(uuid4()),
                        old_config_version=None,
                        new_config_version=1,
                        action="INITIALIZE",
                        proposal_id=None,
                        created_at=_iso(created_at),
                    )
                )
        return self.get_active_config()

    def get_active_config(self) -> ScoringConfig:
        with self.engine.connect() as connection:
            row = connection.execute(
                select(scoring_configs)
                .join(
                    active_scoring_config,
                    active_scoring_config.c.config_version == scoring_configs.c.config_version,
                )
                .where(active_scoring_config.c.singleton_id == 1)
            ).first()
        if row is None:
            raise IntelligenceRepositoryError("no active scoring configuration")
        return self._config_from_row(_mapping(row))

    def get_config(self, version: int) -> ScoringConfig:
        with self.engine.connect() as connection:
            row = connection.execute(
                select(scoring_configs).where(scoring_configs.c.config_version == version)
            ).first()
        if row is None:
            raise IntelligenceRepositoryError("unknown scoring configuration")
        return self._config_from_row(_mapping(row))

    @staticmethod
    def _config_from_row(value: Mapping[str, Any]) -> ScoringConfig:
        return ScoringConfig(
            version=int(value["config_version"]),
            weights=json.loads(str(value["weights_json"])),
            source_authority_overrides=json.loads(str(value["source_overrides_json"])),
        )

    def save_processed_score(
        self,
        context: CandidateContext,
        payload: ProcessingPayload,
        primary_topic: PrimaryTopic,
        score: ScoreResult,
        created_at: datetime,
    ) -> tuple[str, str]:
        result_id = str(uuid4())
        score_id = str(uuid4())
        conclusions = [item.model_dump(mode="json") for item in payload.key_conclusions]
        with self.engine.begin() as connection:
            connection.execute(
                insert(ai_processing_results).values(
                    result_id=result_id,
                    aggregate_version_id=context.aggregate_version_id,
                    source_language=payload.source_language.value,
                    original_text=context.original_text,
                    zh_translation=payload.zh_translation,
                    zh_summary=payload.zh_summary,
                    key_conclusions_json=json.dumps(conclusions, ensure_ascii=False),
                    pm_value=payload.pm_value,
                    primary_topic=primary_topic.value,
                    tags_json=json.dumps(payload.tags, ensure_ascii=False),
                    dimension_scores_json=json.dumps(payload.dimension_scores, sort_keys=True),
                    dimension_rationales_json=json.dumps(
                        payload.dimension_rationales, ensure_ascii=False, sort_keys=True
                    ),
                    origin=context.origin.value,
                    created_at=_iso(created_at),
                )
            )
            connection.execute(
                insert(candidate_scores).values(
                    score_id=score_id,
                    aggregate_version_id=context.aggregate_version_id,
                    processing_result_id=result_id,
                    config_version=score.config_version,
                    score_revision=1,
                    dimensions_json=json.dumps(dict(score.dimensions), sort_keys=True),
                    rationales_json=json.dumps(
                        dict(score.rationales), ensure_ascii=False, sort_keys=True
                    ),
                    total=score.total,
                    created_at=_iso(created_at),
                )
            )
        return result_id, score_id

    def record_failure(
        self,
        aggregate_version_id: str,
        *,
        stage: str,
        error_code: str,
        retryable: bool,
        created_at: datetime,
    ) -> str:
        failure_id = str(uuid4())
        with self.engine.begin() as connection:
            connection.execute(
                insert(ai_processing_failures).values(
                    failure_id=failure_id,
                    aggregate_version_id=aggregate_version_id,
                    stage=stage,
                    error_code=error_code,
                    retryable=retryable,
                    created_at=_iso(created_at),
                )
            )
        return failure_id

    def get_processed(self, aggregate_version_id: str) -> ProcessedIntelligence:
        with self.engine.connect() as connection:
            row = connection.execute(
                select(ai_processing_results).where(
                    ai_processing_results.c.aggregate_version_id == aggregate_version_id
                )
            ).first()
        if row is None:
            raise IntelligenceRepositoryError("candidate has no processing result")
        value = _mapping(row)
        conclusions = tuple(
            ConclusionPayload.model_validate(item)
            for item in json.loads(str(value["key_conclusions_json"]))
        )
        return ProcessedIntelligence(
            result_id=str(value["result_id"]),
            aggregate_version_id=aggregate_version_id,
            source_language=SourceLanguage(str(value["source_language"])),
            original_text=str(value["original_text"]),
            zh_translation=(
                None if value["zh_translation"] is None else str(value["zh_translation"])
            ),
            zh_summary=str(value["zh_summary"]),
            key_conclusions=conclusions,
            pm_value=str(value["pm_value"]),
            primary_topic=PrimaryTopic(str(value["primary_topic"])),
            tags=tuple(json.loads(str(value["tags_json"]))),
            dimension_scores=json.loads(str(value["dimension_scores_json"])),
            dimension_rationales=json.loads(str(value["dimension_rationales_json"])),
            origin=str(value["origin"]),
        )

    def processed_exists(self, aggregate_version_id: str) -> bool:
        with self.engine.connect() as connection:
            value = connection.execute(
                select(ai_processing_results.c.result_id).where(
                    ai_processing_results.c.aggregate_version_id == aggregate_version_id
                )
            ).scalar_one_or_none()
        return value is not None

    def list_scores_for_date(
        self, report_date: date, config_version: int
    ) -> tuple[StoredCandidateScore, ...]:
        latest_revisions = (
            select(
                candidate_scores.c.aggregate_version_id,
                func.max(candidate_scores.c.score_revision).label("score_revision"),
            )
            .where(candidate_scores.c.config_version == config_version)
            .group_by(candidate_scores.c.aggregate_version_id)
            .subquery()
        )
        with self.engine.connect() as connection:
            rows = connection.execute(
                select(candidate_scores, daily_event_candidates.c.event_id)
                .join(
                    latest_revisions,
                    (
                        latest_revisions.c.aggregate_version_id
                        == candidate_scores.c.aggregate_version_id
                    )
                    & (latest_revisions.c.score_revision == candidate_scores.c.score_revision),
                )
                .join(
                    daily_event_candidates,
                    daily_event_candidates.c.aggregate_version_id
                    == candidate_scores.c.aggregate_version_id,
                )
                .where(
                    daily_event_candidates.c.report_date == report_date.isoformat(),
                    candidate_scores.c.config_version == config_version,
                )
                .order_by(daily_event_candidates.c.event_id)
            ).all()
        return tuple(self._stored_score(_mapping(row)) for row in rows)

    def get_score(self, score_id: str) -> StoredCandidateScore:
        with self.engine.connect() as connection:
            row = connection.execute(
                select(candidate_scores, aggregate_versions.c.event_id)
                .join(
                    aggregate_versions,
                    aggregate_versions.c.aggregate_version_id
                    == candidate_scores.c.aggregate_version_id,
                )
                .where(candidate_scores.c.score_id == score_id)
            ).first()
        if row is None:
            raise IntelligenceRepositoryError("unknown candidate score")
        return self._stored_score(_mapping(row))

    @staticmethod
    def _stored_score(value: Mapping[str, Any]) -> StoredCandidateScore:
        dimensions = json.loads(str(value["dimensions_json"]))
        rationales = json.loads(str(value["rationales_json"]))
        return StoredCandidateScore(
            score_id=str(value["score_id"]),
            aggregate_version_id=str(value["aggregate_version_id"]),
            event_id=str(value["event_id"]),
            config_version=int(value["config_version"]),
            result=ScoreResult(
                config_version=int(value["config_version"]),
                dimensions=dimensions,
                rationales=rationales,
                total=float(value["total"]),
            ),
        )

    def save_selection_run(
        self,
        report_date: date,
        config_version: int,
        ranked: tuple[RankedCandidate, ...],
        created_at: datetime,
        *,
        threshold: float = 70.0,
        max_items: int = 50,
    ) -> tuple[str, tuple[SavedSelection, ...]]:
        run_id = str(uuid4())
        saved = tuple(SavedSelection(str(uuid4()), item) for item in ranked)
        with self.engine.begin() as connection:
            connection.execute(
                insert(daily_selection_runs).values(
                    selection_run_id=run_id,
                    report_date=report_date.isoformat(),
                    config_version=config_version,
                    threshold=threshold,
                    max_items=max_items,
                    qualified_count=len(ranked),
                    created_at=_iso(created_at),
                )
            )
            if saved:
                connection.execute(
                    insert(daily_selections),
                    [
                        {
                            "selection_id": item.selection_id,
                            "selection_run_id": run_id,
                            "event_id": item.ranked.candidate.event_id,
                            "aggregate_version_id": item.ranked.candidate.aggregate_version_id,
                            "score_id": item.ranked.candidate.score_id,
                            "rank": item.ranked.rank,
                            "tier": item.ranked.tier.value,
                            "created_at": _iso(created_at),
                        }
                        for item in saved
                    ],
                )
        return run_id, saved

    def formal_identity(self, aggregate_event_id: str) -> tuple[str, int] | None:
        with self.engine.connect() as connection:
            row = connection.execute(
                select(
                    formalization_links.c.formal_event_id,
                    formalization_links.c.formal_version_no,
                )
                .join(
                    aggregate_versions,
                    aggregate_versions.c.aggregate_version_id
                    == formalization_links.c.aggregate_version_id,
                )
                .where(aggregate_versions.c.event_id == aggregate_event_id)
                .order_by(formalization_links.c.formal_version_no.desc())
                .limit(1)
            ).first()
        if row is None:
            return None
        value = _mapping(row)
        return str(value["formal_event_id"]), int(value["formal_version_no"]) + 1

    def existing_formalization(self, aggregate_version_id: str) -> str | None:
        with self.engine.connect() as connection:
            value = connection.execute(
                select(formalization_links.c.formal_event_id).where(
                    formalization_links.c.aggregate_version_id == aggregate_version_id
                )
            ).scalar_one_or_none()
        return None if value is None else str(value)

    def save_formalization_link(
        self,
        selection_id: str,
        aggregate_version_id: str,
        formal_event_id: str,
        formal_version_no: int,
        archived_at: datetime,
    ) -> None:
        with self.engine.begin() as connection:
            connection.execute(
                insert(formalization_links).values(
                    link_id=str(uuid4()),
                    selection_id=selection_id,
                    aggregate_version_id=aggregate_version_id,
                    formal_event_id=formal_event_id,
                    formal_version_no=formal_version_no,
                    archived_at=_iso(archived_at),
                )
            )

    def save_feedback(
        self,
        score_id: str,
        *,
        reason: str,
        affected_dimension: str,
        content_features: Mapping[str, Any],
        outcome: str,
        created_at: datetime,
    ) -> str:
        if not reason.strip():
            raise ValueError("feedback reason is required")
        with self.engine.connect() as connection:
            original_score = connection.execute(
                select(candidate_scores.c.total).where(candidate_scores.c.score_id == score_id)
            ).scalar_one_or_none()
        if original_score is None:
            raise IntelligenceRepositoryError("unknown candidate score")
        feedback_id = str(uuid4())
        with self.engine.begin() as connection:
            connection.execute(
                insert(quality_feedback).values(
                    feedback_id=feedback_id,
                    score_id=score_id,
                    reason=reason.strip(),
                    affected_dimension=affected_dimension,
                    content_features_json=json.dumps(dict(content_features), sort_keys=True),
                    original_score=float(original_score),
                    outcome=outcome,
                    created_at=_iso(created_at),
                )
            )
        return feedback_id

    def feedback_dimension_counts(self) -> Counter[str]:
        with self.engine.connect() as connection:
            values = connection.execute(select(quality_feedback.c.affected_dimension)).scalars()
            return Counter(str(value) for value in values)

    def save_calibration_proposal(
        self,
        *,
        base_config_version: int,
        sample_count: int,
        uncertainty: str,
        affected_dimensions: tuple[str, ...],
        suggested_weights: Mapping[str, float],
        suggested_source_overrides: Mapping[str, float],
        estimated_impact: Mapping[str, Any],
        created_at: datetime,
    ) -> CalibrationProposalRecord:
        proposal_id = str(uuid4())
        with self.engine.begin() as connection:
            connection.execute(
                insert(calibration_proposals).values(
                    proposal_id=proposal_id,
                    base_config_version=base_config_version,
                    sample_count=sample_count,
                    uncertainty=uncertainty,
                    affected_dimensions_json=json.dumps(affected_dimensions),
                    suggested_weights_json=json.dumps(dict(suggested_weights), sort_keys=True),
                    suggested_source_overrides_json=json.dumps(
                        dict(suggested_source_overrides), sort_keys=True
                    ),
                    estimated_impact_json=json.dumps(dict(estimated_impact), sort_keys=True),
                    created_at=_iso(created_at),
                )
            )
        return CalibrationProposalRecord(
            proposal_id,
            base_config_version,
            sample_count,
            uncertainty,
            affected_dimensions,
            dict(suggested_weights),
            dict(suggested_source_overrides),
            dict(estimated_impact),
        )

    def get_calibration_proposal(self, proposal_id: str) -> CalibrationProposalRecord:
        with self.engine.connect() as connection:
            row = connection.execute(
                select(calibration_proposals).where(
                    calibration_proposals.c.proposal_id == proposal_id
                )
            ).first()
        if row is None:
            raise IntelligenceRepositoryError("unknown calibration proposal")
        value = _mapping(row)
        return CalibrationProposalRecord(
            proposal_id=proposal_id,
            base_config_version=int(value["base_config_version"]),
            sample_count=int(value["sample_count"]),
            uncertainty=str(value["uncertainty"]),
            affected_dimensions=tuple(json.loads(str(value["affected_dimensions_json"]))),
            suggested_weights=json.loads(str(value["suggested_weights_json"])),
            suggested_source_overrides=json.loads(str(value["suggested_source_overrides_json"])),
            estimated_impact=json.loads(str(value["estimated_impact_json"])),
        )

    def decide_calibration(
        self,
        proposal: CalibrationProposalRecord,
        *,
        confirm: bool,
        decided_at: datetime,
    ) -> int | None:
        with self.engine.begin() as connection:
            existing = connection.execute(
                select(calibration_decisions.c.decision_id).where(
                    calibration_decisions.c.proposal_id == proposal.proposal_id
                )
            ).scalar_one_or_none()
            if existing is not None:
                raise IntelligenceRepositoryError("calibration proposal was already decided")
            new_version: int | None = None
            if confirm:
                active = connection.execute(
                    select(active_scoring_config.c.config_version).where(
                        active_scoring_config.c.singleton_id == 1
                    )
                ).scalar_one()
                if int(active) != proposal.base_config_version:
                    raise IntelligenceRepositoryError(
                        "active scoring config changed since proposal"
                    )
                maximum = connection.execute(
                    select(func.max(scoring_configs.c.config_version))
                ).scalar_one()
                new_version = int(maximum) + 1
                connection.execute(
                    insert(scoring_configs).values(
                        config_version=new_version,
                        weights_json=json.dumps(dict(proposal.suggested_weights), sort_keys=True),
                        source_overrides_json=json.dumps(
                            dict(proposal.suggested_source_overrides), sort_keys=True
                        ),
                        status=ScoringConfigStatus.ACTIVE.value,
                        created_at=_iso(decided_at),
                    )
                )
                connection.execute(
                    update(scoring_configs)
                    .where(scoring_configs.c.config_version == int(active))
                    .values(status=ScoringConfigStatus.INACTIVE.value)
                )
                connection.execute(
                    update(active_scoring_config)
                    .where(active_scoring_config.c.singleton_id == 1)
                    .values(config_version=new_version, changed_at=_iso(decided_at))
                )
                connection.execute(
                    insert(scoring_config_audits).values(
                        audit_id=str(uuid4()),
                        old_config_version=int(active),
                        new_config_version=new_version,
                        action="CONFIRM",
                        proposal_id=proposal.proposal_id,
                        created_at=_iso(decided_at),
                    )
                )
            connection.execute(
                insert(calibration_decisions).values(
                    decision_id=str(uuid4()),
                    proposal_id=proposal.proposal_id,
                    decision="CONFIRMED" if confirm else "REJECTED",
                    new_config_version=new_version,
                    decided_at=_iso(decided_at),
                )
            )
        return new_version

    def rollback_config(self, version: int, *, changed_at: datetime) -> None:
        with self.engine.begin() as connection:
            exists = connection.execute(
                select(scoring_configs.c.config_version).where(
                    scoring_configs.c.config_version == version
                )
            ).scalar_one_or_none()
            if exists is None:
                raise IntelligenceRepositoryError("unknown scoring configuration")
            active = int(
                connection.execute(
                    select(active_scoring_config.c.config_version).where(
                        active_scoring_config.c.singleton_id == 1
                    )
                ).scalar_one()
            )
            connection.execute(
                update(scoring_configs)
                .where(scoring_configs.c.config_version == active)
                .values(status=ScoringConfigStatus.INACTIVE.value)
            )
            connection.execute(
                update(scoring_configs)
                .where(scoring_configs.c.config_version == version)
                .values(status=ScoringConfigStatus.ACTIVE.value)
            )
            connection.execute(
                update(active_scoring_config)
                .where(active_scoring_config.c.singleton_id == 1)
                .values(config_version=version, changed_at=_iso(changed_at))
            )
            connection.execute(
                insert(scoring_config_audits).values(
                    audit_id=str(uuid4()),
                    old_config_version=active,
                    new_config_version=version,
                    action="ROLLBACK",
                    proposal_id=None,
                    created_at=_iso(changed_at),
                )
            )

    def save_rescore(
        self,
        aggregate_version_id: str,
        processing_result_id: str,
        score: ScoreResult,
        created_at: datetime,
    ) -> str:
        score_id = str(uuid4())
        with self.engine.begin() as connection:
            latest_revision = connection.execute(
                select(func.max(candidate_scores.c.score_revision)).where(
                    candidate_scores.c.aggregate_version_id == aggregate_version_id,
                    candidate_scores.c.config_version == score.config_version,
                )
            ).scalar_one()
            score_revision = 1 if latest_revision is None else int(latest_revision) + 1
            connection.execute(
                insert(candidate_scores).values(
                    score_id=score_id,
                    aggregate_version_id=aggregate_version_id,
                    processing_result_id=processing_result_id,
                    config_version=score.config_version,
                    score_revision=score_revision,
                    dimensions_json=json.dumps(dict(score.dimensions), sort_keys=True),
                    rationales_json=json.dumps(
                        dict(score.rationales), ensure_ascii=False, sort_keys=True
                    ),
                    total=score.total,
                    created_at=_iso(created_at),
                )
            )
        return score_id

    def save_topic_idea(
        self,
        aggregate_version_id: str,
        *,
        trigger: str,
        title: str,
        outline: tuple[str, ...],
        hook: str,
        support_evidence_ids: tuple[str, ...],
        created_at: datetime,
    ) -> str:
        idea_id = str(uuid4())
        with self.engine.begin() as connection:
            connection.execute(
                insert(topic_ideas).values(
                    idea_id=idea_id,
                    aggregate_version_id=aggregate_version_id,
                    trigger=trigger,
                    title=title,
                    outline_json=json.dumps(outline, ensure_ascii=False),
                    hook=hook,
                    support_evidence_ids_json=json.dumps(support_evidence_ids),
                    created_at=_iso(created_at),
                )
            )
        return idea_id

    def get_topic_idea(self, aggregate_version_id: str) -> Mapping[str, Any] | None:
        with self.engine.connect() as connection:
            row = (
                connection.execute(
                    select(topic_ideas)
                    .where(topic_ideas.c.aggregate_version_id == aggregate_version_id)
                    .order_by(topic_ideas.c.trigger, topic_ideas.c.created_at)
                    .limit(1)
                )
                .mappings()
                .first()
            )
        return None if row is None else dict(row)

    def table_rows(self, table: Any) -> tuple[Mapping[str, Any], ...]:
        with self.engine.connect() as connection:
            rows = connection.execute(select(table)).all()
        return tuple(dict(_mapping(row)) for row in rows)
