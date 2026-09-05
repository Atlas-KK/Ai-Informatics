"""Qualified extension-search ingestion through the existing Phase 3-5 boundaries."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime

from ai_intel.application.archive import ArchiveService
from ai_intel.application.daily_selection import DailySelectionService
from ai_intel.application.event_aggregation import EventAggregationService
from ai_intel.application.intelligence_processing import IntelligenceProcessingService
from ai_intel.domain.fingerprint import CandidateOrigin
from ai_intel.domain.source import CollectedItem, CollectionStatus, SourceType, truncate_for_model
from ai_intel.infrastructure.db.event_repository import SQLiteEventRepository
from ai_intel.infrastructure.db.intelligence_repository import SQLiteIntelligenceRepository
from ai_intel.infrastructure.db.source_repository import SQLiteSourceRepository
from ai_intel.ports.llm import StructuredLLM


class ExtensionIngestionError(RuntimeError):
    """An extension result could not safely enter the formal archive."""


@dataclass(frozen=True, slots=True)
class ExtensionIngestionResult:
    event_id: str
    deduplicated: bool


class ExtensionIngestionService:
    """Turn a selected transient hit into a traceable formal archive record."""

    def __init__(
        self,
        *,
        source_repository: SQLiteSourceRepository,
        event_repository: SQLiteEventRepository,
        intelligence_repository: SQLiteIntelligenceRepository,
        archive_service: ArchiveService,
        llm: StructuredLLM,
    ) -> None:
        self.source_repository = source_repository
        self.event_repository = event_repository
        self.intelligence_repository = intelligence_repository
        self.archive_service = archive_service
        self.llm = llm

    def ingest(
        self,
        result: Mapping[str, object],
        *,
        selected_at: datetime,
        threshold: float,
    ) -> ExtensionIngestionResult:
        source_name = str(result["source_name"]).strip() or "external"
        source_id = f"extended:{source_name[:80]}"
        raw_content = str(result["content"])
        score_value = result["score"]
        if not isinstance(score_value, int | float) or isinstance(score_value, bool):
            raise ExtensionIngestionError("extension result score is invalid")
        snapshot_id = self.source_repository.save_item(
            None,
            CollectedItem(
                external_id=str(result["result_id"]),
                source_id=source_id,
                source_type=SourceType.WEB,
                title=str(result["title"]),
                url=str(result["url"]),
                author=None,
                published_at=selected_at,
                first_seen_at=selected_at,
                published_at_unknown=True,
                raw_content=raw_content,
                model_input=truncate_for_model(raw_content, None),
                status=CollectionStatus.COLLECTED,
                metadata={
                    "origin": CandidateOrigin.EXTENDED_SEARCH.value,
                    "viewpoint": str(result["summary"]),
                    "external_provider_score": float(score_value),
                },
            ),
        )
        if snapshot_id is None:
            raise ExtensionIngestionError("extension result was already ingested")

        aggregation = EventAggregationService(self.event_repository).process_snapshot_ids(
            (snapshot_id,),
            report_date=selected_at.date(),
            observed_at=selected_at,
            origin=CandidateOrigin.EXTENDED_SEARCH,
            selected_for_ingestion=True,
        )[0]
        if aggregation.event_id is None:
            raise ExtensionIngestionError("extension result did not produce an event")
        if not aggregation.needs_scoring:
            identity = self.intelligence_repository.formal_identity(aggregation.event_id)
            if identity is None:
                raise ExtensionIngestionError("matching event has no formal archive")
            return ExtensionIngestionResult(identity[0], True)

        if aggregation.version_no is None:
            raise ExtensionIngestionError("extension event version was not created")
        contexts = self.intelligence_repository.list_candidate_contexts(selected_at.date())
        context = next(
            (
                item
                for item in contexts
                if item.event_id == aggregation.event_id
                and item.aggregate_version_no == aggregation.version_no
            ),
            None,
        )
        if context is None:
            raise ExtensionIngestionError("extension candidate context was not created")

        outcome = IntelligenceProcessingService(
            self.intelligence_repository, self.llm
        ).process_context(context, processed_at=selected_at)
        if not outcome.succeeded or outcome.score_id is None:
            raise ExtensionIngestionError(
                f"extension processing failed: {outcome.failure_code or 'UNKNOWN'}"
            )
        selection = DailySelectionService(
            self.intelligence_repository,
            self.archive_service,
        ).select_candidate(
            outcome.score_id,
            report_date=selected_at.date(),
            selected_at=selected_at,
            archive=True,
            threshold=threshold,
        )
        if not selection.formal_event_ids:
            raise ExtensionIngestionError("result does not meet archive threshold")
        return ExtensionIngestionResult(selection.formal_event_ids[0], False)
