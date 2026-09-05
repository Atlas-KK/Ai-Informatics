"""Daily score selection and the only Phase 5 path into the formal archive."""

from dataclasses import dataclass
from datetime import date, datetime
from uuid import uuid4

from ai_intel.application.archive import ArchiveService
from ai_intel.application.topic_ideas import TopicIdeaService, TopicIdeaTrigger
from ai_intel.domain.models import ArchiveCandidate, EvidenceInput, FormalizationInput, ScoreInput
from ai_intel.domain.states import Tier
from ai_intel.domain.tiering import RankedCandidate, select_daily
from ai_intel.infrastructure.db.intelligence_repository import (
    SavedSelection,
    SQLiteIntelligenceRepository,
)


@dataclass(frozen=True, slots=True)
class DailySelectionResult:
    selection_run_id: str
    ranked: tuple[RankedCandidate, ...]
    formal_event_ids: tuple[str, ...]

    @property
    def is_empty(self) -> bool:
        return not self.ranked

    @property
    def message(self) -> str:
        return "今日无达标情报" if self.is_empty else ""


class DailySelectionService:
    def __init__(
        self,
        repository: SQLiteIntelligenceRepository,
        archive_service: ArchiveService | None = None,
        topic_idea_service: TopicIdeaService | None = None,
    ) -> None:
        self.repository = repository
        self.archive_service = archive_service
        self.topic_idea_service = topic_idea_service

    def select(
        self,
        report_date: date,
        *,
        selected_at: datetime,
        archive: bool = False,
    ) -> DailySelectionResult:
        config = self.repository.ensure_default_config(selected_at)
        scores = self.repository.list_scores_for_date(report_date, config.version)
        ranked = select_daily(tuple(item.as_rankable() for item in scores))
        run_id, saved = self.repository.save_selection_run(
            report_date, config.version, ranked, selected_at
        )
        if self.topic_idea_service is not None:
            for item in ranked:
                if item.tier is Tier.MUST_READ:
                    self.topic_idea_service.generate(
                        item.candidate.aggregate_version_id,
                        trigger=TopicIdeaTrigger.AUTO,
                        tier=item.tier,
                        created_at=selected_at,
                    )
        formal_ids: tuple[str, ...] = ()
        if archive:
            if self.archive_service is None:
                raise ValueError("archive service is required for formalization")
            formal_ids = tuple(self._formalize(item, selected_at) for item in saved)
        return DailySelectionResult(run_id, ranked, formal_ids)

    def select_candidate(
        self,
        score_id: str,
        *,
        report_date: date,
        selected_at: datetime,
        archive: bool = False,
        threshold: float = 70.0,
    ) -> DailySelectionResult:
        """Apply the normal Phase 5 selection/formalization gate to one user-selected item."""

        stored_score = self.repository.get_score(score_id)
        ranked = select_daily((stored_score.as_rankable(),), threshold=threshold, limit=1)
        run_id, saved = self.repository.save_selection_run(
            report_date,
            stored_score.config_version,
            ranked,
            selected_at,
            threshold=threshold,
            max_items=1,
        )
        formal_ids: tuple[str, ...] = ()
        if archive and saved:
            if self.archive_service is None:
                raise ValueError("archive service is required for formalization")
            formal_ids = tuple(self._formalize(item, selected_at) for item in saved)
        return DailySelectionResult(run_id, ranked, formal_ids)

    def _formalize(self, saved: SavedSelection, archived_at: datetime) -> str:
        assert self.archive_service is not None
        ranked = saved.ranked
        existing = self.repository.existing_formalization(ranked.candidate.aggregate_version_id)
        if existing is not None:
            return existing
        context = self.repository.get_candidate_context(ranked.candidate.aggregate_version_id)
        processed = self.repository.get_processed(ranked.candidate.aggregate_version_id)
        stored_score = self.repository.get_score(ranked.candidate.score_id)
        identity = self.repository.formal_identity(context.event_id)
        # The aggregate event ID is already a UUID4 and is the stable cross-stage identity.
        formal_event_id, formal_version_no = identity or (context.event_id, 1)
        translation = (
            ""
            if processed.zh_translation is None
            else f"## 中文对照译文\n\n{processed.zh_translation}\n\n"
        )
        conclusions = "\n".join(
            f"- {item.text} [evidence: {', '.join(item.evidence_ids)}]"
            for item in processed.key_conclusions
        )
        content = (
            f"## 原文\n\n{processed.original_text}\n\n"
            f"{translation}"
            f"## 关键结论\n\n{conclusions}\n\n"
            f"## 对 AI 产品经理的价值\n\n{processed.pm_value}\n\n"
            f"## 二级标签\n\n{', '.join(processed.tags)}"
        )
        candidate = ArchiveCandidate(
            event_id=formal_event_id,
            snapshot_id=str(uuid4()),
            source_id=context.evidence[0].source_id,
            canonical_title=context.canonical_title,
            primary_topic=processed.primary_topic.value,
            change_type="NEW" if formal_version_no == 1 else "UPDATED",
            raw_content=context.original_text,
            content=content,
            summary=processed.zh_summary,
            evidence=tuple(
                EvidenceInput(
                    source_id=item.source_id,
                    url=item.url,
                    published_at=item.published_at,
                    viewpoint=item.viewpoint,
                )
                for item in {
                    (evidence.source_id, evidence.url): evidence for evidence in context.evidence
                }.values()
            ),
            score=ScoreInput(
                config_version=stored_score.config_version,
                dimensions=stored_score.result.dimensions,
                total=ranked.candidate.total,
                tier=ranked.tier,
            ),
            version_no=formal_version_no,
            created_at=archived_at,
        )
        self.archive_service.commit(
            candidate,
            formalization=FormalizationInput(
                selection_id=saved.selection_id,
                aggregate_version_id=context.aggregate_version_id,
                archived_at=archived_at,
            ),
        )
        return formal_event_id
