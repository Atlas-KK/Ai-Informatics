"""User-initiated scoring calibration with confirm/reject/rollback gates."""

from dataclasses import dataclass
from datetime import datetime

from ai_intel.application.intelligence_processing import IntelligenceProcessingService
from ai_intel.domain.ai_processing import DIMENSIONS
from ai_intel.domain.scoring import ScoringConfig, calculate_score
from ai_intel.infrastructure.db.intelligence_repository import (
    CalibrationProposalRecord,
    SQLiteIntelligenceRepository,
)
from ai_intel.infrastructure.telemetry import TelemetryEventType, TelemetryRecorder

MIN_CALIBRATION_SAMPLES = 5


@dataclass(frozen=True, slots=True)
class CalibrationAssessment:
    sample_count: int
    uncertainty: str
    proposal: CalibrationProposalRecord | None


class CalibrationService:
    def __init__(
        self,
        repository: SQLiteIntelligenceRepository,
        telemetry: TelemetryRecorder | None = None,
    ) -> None:
        self.repository = repository
        self.telemetry = telemetry

    def submit_feedback(
        self,
        score_id: str,
        *,
        reason: str,
        affected_dimension: str,
        content_features: dict[str, object],
        removed: bool,
        submitted_at: datetime,
    ) -> str:
        if affected_dimension not in DIMENSIONS:
            raise ValueError("feedback must identify one of the five scoring dimensions")
        feedback_id = self.repository.save_feedback(
            score_id,
            reason=reason,
            affected_dimension=affected_dimension,
            content_features=content_features,
            outcome="REMOVED" if removed else "KEPT",
            created_at=submitted_at,
        )
        if self.telemetry is not None:
            score = self.repository.get_score(score_id)
            self.telemetry.record(
                TelemetryEventType.QUALITY_FEEDBACK_SUBMITTED,
                {
                    "item_id": score.aggregate_version_id,
                    "original_score": score.result.total,
                    "reason": reason,
                    "scoring_version": score.config_version,
                    "occurred_at": submitted_at.isoformat(),
                },
                created_at=submitted_at,
            )
        return feedback_id

    def propose(self, *, user_initiated: bool, proposed_at: datetime) -> CalibrationAssessment:
        if not user_initiated:
            raise ValueError("calibration must be explicitly initiated by the user")
        counts = self.repository.feedback_dimension_counts()
        sample_count = sum(counts.values())
        if sample_count < MIN_CALIBRATION_SAMPLES:
            return CalibrationAssessment(sample_count, "HIGH", None)
        base = self.repository.ensure_default_config(proposed_at)
        target = sorted(counts, key=lambda key: (-counts[key], key))[0]
        suggested = self._increase_weight(base, target)
        uncertainty = "LOW" if sample_count >= 20 else "MEDIUM"
        proposal, created = self.repository.save_calibration_proposal(
            base_config_version=base.version,
            sample_count=sample_count,
            uncertainty=uncertainty,
            affected_dimensions=tuple(sorted(counts)),
            suggested_weights=suggested,
            suggested_source_overrides=base.source_authority_overrides,
            estimated_impact={
                "scope": "future scores only",
                "dominant_feedback_dimension": target,
                "feedback_count": sample_count,
            },
            created_at=proposed_at,
        )
        if created and self.telemetry is not None:
            self.telemetry.record(
                TelemetryEventType.SCORING_CALIBRATION_PROPOSED,
                {
                    "current_version": base.version,
                    "feedback_count": sample_count,
                    "proposed_changes": suggested,
                    "created_at": proposed_at.isoformat(),
                },
                created_at=proposed_at,
            )
        return CalibrationAssessment(proposal.sample_count, proposal.uncertainty, proposal)

    @staticmethod
    def _increase_weight(config: ScoringConfig, target: str) -> dict[str, float]:
        delta = min(0.02, 1.0 - config.weights[target])
        remaining_before = 1.0 - config.weights[target]
        result = dict(config.weights)
        result[target] += delta
        if remaining_before:
            factor = (remaining_before - delta) / remaining_before
            for dimension in DIMENSIONS:
                if dimension != target:
                    result[dimension] *= factor
        return result

    def confirm(self, proposal_id: str, *, user_confirmed: bool, confirmed_at: datetime) -> int:
        if not user_confirmed:
            raise ValueError("new scoring configuration requires user confirmation")
        proposal = self.repository.get_calibration_proposal(proposal_id)
        version = self.repository.decide_calibration(
            proposal, confirm=True, decided_at=confirmed_at
        )
        assert version is not None
        if self.telemetry is not None:
            self.telemetry.record(
                TelemetryEventType.SCORING_CONFIG_CHANGED,
                {
                    "old_version": proposal.base_config_version,
                    "new_version": version,
                    "action": "CONFIRM",
                    "occurred_at": confirmed_at.isoformat(),
                },
                created_at=confirmed_at,
            )
        return version

    def reject(self, proposal_id: str, *, rejected_at: datetime) -> None:
        proposal = self.repository.get_calibration_proposal(proposal_id)
        self.repository.decide_calibration(proposal, confirm=False, decided_at=rejected_at)

    def rollback(self, config_version: int, *, user_confirmed: bool, changed_at: datetime) -> None:
        if not user_confirmed:
            raise ValueError("scoring rollback requires user confirmation")
        old_version = self.repository.get_active_config().version
        self.repository.rollback_config(config_version, changed_at=changed_at)
        if self.telemetry is not None:
            self.telemetry.record(
                TelemetryEventType.SCORING_CONFIG_CHANGED,
                {
                    "old_version": old_version,
                    "new_version": config_version,
                    "action": "ROLLBACK",
                    "occurred_at": changed_at.isoformat(),
                },
                created_at=changed_at,
            )

    def rescore_history(
        self,
        aggregate_version_ids: tuple[str, ...],
        *,
        user_initiated: bool,
        rescored_at: datetime,
    ) -> tuple[str, ...]:
        if not user_initiated:
            raise ValueError("historical rescoring must be explicitly initiated by the user")
        config = self.repository.get_active_config()
        score_ids: list[str] = []
        for aggregate_version_id in aggregate_version_ids:
            context = self.repository.get_candidate_context(aggregate_version_id)
            processed = self.repository.get_processed(aggregate_version_id)
            score = calculate_score(
                config,
                IntelligenceProcessingService.scoring_signals(context, processed, rescored_at),
            )
            score_ids.append(
                self.repository.save_rescore(
                    aggregate_version_id, processed.result_id, score, rescored_at
                )
            )
        return tuple(score_ids)
