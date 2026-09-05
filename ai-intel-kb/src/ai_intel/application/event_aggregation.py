"""Phase 4 orchestration from immutable raw snapshots to scoring candidates."""

from dataclasses import dataclass
from datetime import date, datetime

from ai_intel.domain.event_matching import (
    canonical_title,
    connected_components,
    match_snapshot_to_profile,
    stable_event_identity,
)
from ai_intel.domain.fingerprint import CandidateOrigin, SnapshotDraft, normalize_snapshot
from ai_intel.domain.versioning import (
    ChangeDecision,
    ChangeReason,
    ChangeType,
    build_version,
    decide_change,
)
from ai_intel.infrastructure.db.event_repository import SQLiteEventRepository


class AmbiguousEventMatchError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class AggregationResult:
    event_id: str | None
    version_no: int | None
    change_type: ChangeType
    reasons: tuple[ChangeReason, ...]
    needs_scoring: bool


class EventAggregationService:
    def __init__(self, repository: SQLiteEventRepository) -> None:
        self.repository = repository

    def process_snapshot_ids(
        self,
        snapshot_ids: tuple[str, ...],
        *,
        report_date: date,
        observed_at: datetime,
        origin: CandidateOrigin | None = None,
        selected_for_ingestion: bool = True,
    ) -> tuple[AggregationResult, ...]:
        drafts = tuple(
            self.repository.load_snapshot_draft(
                snapshot_id,
                origin=origin,
                selected_for_ingestion=selected_for_ingestion,
            )
            for snapshot_id in snapshot_ids
        )
        return self.process(drafts, report_date=report_date, observed_at=observed_at)

    def process(
        self,
        drafts: tuple[SnapshotDraft, ...],
        *,
        report_date: date,
        observed_at: datetime,
    ) -> tuple[AggregationResult, ...]:
        if observed_at.tzinfo is None or observed_at.utcoffset() is None:
            raise ValueError("observed_at must include a timezone")
        results: list[AggregationResult] = []
        eligible = []
        for draft in drafts:
            if draft.origin is CandidateOrigin.EXTENDED_SEARCH and not draft.selected_for_ingestion:
                decision = ChangeDecision(
                    ChangeType.IGNORED,
                    (ChangeReason.NOT_SELECTED,),
                    create_version=False,
                    needs_scoring=False,
                )
                self.repository.record_decision(None, (draft.snapshot_id,), decision, observed_at)
                results.append(AggregationResult(None, None, *self._decision_values(decision)))
                continue
            eligible.append(normalize_snapshot(draft))

        for component in connected_components(eligible):
            matched_ids = {
                profile.event_id
                for profile in self.repository.list_match_profiles()
                if any(match_snapshot_to_profile(item, profile).matched for item in component)
            }
            if len(matched_ids) > 1:
                raise AmbiguousEventMatchError(
                    f"component matches multiple existing events: {sorted(matched_ids)}"
                )
            if matched_ids:
                event_id = next(iter(matched_ids))
                stable_key = event_id
                existing = self.repository.get_current_state(event_id)
            else:
                event_id, stable_key = stable_event_identity(component)
                existing = None
            decision = decide_change(existing, component)
            if existing is None:
                title = canonical_title(component)
                normalized_title = min(item.normalized_title for item in component)
            else:
                incoming_title = canonical_title(component)
                incoming_normalized = min(item.normalized_title for item in component)
                if (incoming_normalized, incoming_title) < (
                    existing.normalized_title,
                    existing.canonical_title,
                ):
                    title, normalized_title = incoming_title, incoming_normalized
                else:
                    title = existing.canonical_title
                    normalized_title = existing.normalized_title
            if not decision.create_version:
                self.repository.record_decision(
                    event_id,
                    tuple(item.snapshot_id for item in component),
                    decision,
                    observed_at,
                )
                version_no = existing.version_no if existing is not None else None
            else:
                version = build_version(title, normalized_title, existing, component)
                match_keys = tuple(
                    sorted(
                        {key for item in component for key in item.match_keys},
                        key=lambda key: (key.kind.value, key.value),
                    )
                )
                version_no, _ = self.repository.save_version(
                    event_id=event_id,
                    stable_key=stable_key,
                    match_keys=match_keys,
                    decision=decision,
                    draft=version,
                    incoming_snapshot_ids=tuple(item.snapshot_id for item in component),
                    report_date=report_date,
                    observed_at=observed_at,
                )
            results.append(
                AggregationResult(event_id, version_no, *self._decision_values(decision))
            )
        return tuple(results)

    @staticmethod
    def _decision_values(
        decision: ChangeDecision,
    ) -> tuple[ChangeType, tuple[ChangeReason, ...], bool]:
        return decision.change_type, decision.reasons, decision.needs_scoring
