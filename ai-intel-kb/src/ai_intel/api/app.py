"""FastAPI application factory."""

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import date, datetime
from threading import Lock
from typing import cast

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.exc import IntegrityError, NoResultFound

from ai_intel.api.schemas import (
    ConfirmationRequest,
    ExpansionSearchRequest,
    ExpertResponse,
    ExpertWriteRequest,
    FeedbackRequest,
    HealthResponse,
    NoteRequest,
    RescoreRequest,
    SettingsRequest,
    SourceResponse,
    SourceWriteRequest,
    StateRequest,
    TrashRequest,
    UserMetadataRequest,
)
from ai_intel.application.archive import ArchiveService
from ai_intel.application.calibration import CalibrationService
from ai_intel.application.delivery import NoFailedDeliverySegmentsError
from ai_intel.application.extension_ingestion import (
    ExtensionIngestionError,
    ExtensionIngestionService,
)
from ai_intel.application.intelligence_processing import ProcessingOutcome
from ai_intel.application.search import ExpansionSearchProvider, SemanticRanker
from ai_intel.application.sources import SourceService
from ai_intel.application.topic_ideas import TopicIdeaService, TopicIdeaTrigger
from ai_intel.config import Settings
from ai_intel.domain.ai_processing import ProcessingContractError
from ai_intel.domain.models import utc_now
from ai_intel.domain.pipeline import DeliveryRetryResult
from ai_intel.domain.source import SourceDraft, SourceState
from ai_intel.domain.states import ReadState
from ai_intel.foundation import RuntimeContext, close_runtime, initialize_runtime
from ai_intel.infrastructure.archive.commit import AtomicArchiveCommitter
from ai_intel.infrastructure.db.phase7_repository import Phase7RepositoryError
from ai_intel.infrastructure.db.repository import ArchiveInvariantError
from ai_intel.infrastructure.db.source_repository import SourceRepositoryError
from ai_intel.infrastructure.telemetry import TelemetryRecorder
from ai_intel.infrastructure.vault_projection.projector import VaultProjector
from ai_intel.ports.llm import StructuredLLM


def create_app(
    settings: Settings | None = None,
    *,
    semantic_ranker: SemanticRanker | None = None,
    expansion_provider: ExpansionSearchProvider | None = None,
    processing_llm: StructuredLLM | None = None,
    retry_handler: Callable[[str, str], ProcessingOutcome] | None = None,
    delivery_retry_handler: Callable[[str], DeliveryRetryResult] | None = None,
) -> FastAPI:
    """Build an application instance with isolated runtime settings."""

    app_settings = settings or Settings()
    extension_favorite_lock = Lock()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        runtime = initialize_runtime(app_settings)
        app.state.runtime = runtime
        try:
            yield
        finally:
            close_runtime(runtime)

    app = FastAPI(title="AI Intelligence Knowledge Base", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=("http://127.0.0.1:5173", "http://localhost:5173"),
        allow_credentials=False,
        allow_methods=("GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"),
        allow_headers=("Content-Type",),
    )

    @app.get("/health", response_model=HealthResponse, tags=["foundation"])
    def health(request: Request) -> HealthResponse:
        cast(RuntimeContext, request.app.state.runtime)
        return HealthResponse(status="ok", storage="ready", phase="phase7")

    def source_service(request: Request) -> SourceService:
        runtime = cast(RuntimeContext, request.app.state.runtime)
        return SourceService(runtime.source_repository)

    def archive_service(request: Request) -> ArchiveService:
        runtime = cast(RuntimeContext, request.app.state.runtime)
        return ArchiveService(
            runtime.repository,
            AtomicArchiveCommitter(runtime.data_dir, runtime.repository),
            VaultProjector(runtime.data_dir, runtime.repository),
            TelemetryRecorder(runtime.engine),
        )

    def draft(payload: SourceWriteRequest) -> SourceDraft:
        return SourceDraft(
            name=payload.name,
            source_type=payload.source_type,
            url=payload.url,
            topic=payload.topic,
            authority_level=payload.authority_level,
            truncate_chars=payload.truncate_chars,
        )

    @app.post("/api/sources", response_model=SourceResponse, tags=["sources"])
    def create_source(payload: SourceWriteRequest, request: Request) -> object:
        try:
            return source_service(request).create(draft(payload))
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.get("/api/sources", response_model=list[SourceResponse], tags=["sources"])
    def list_sources(request: Request, include_deleted: bool = False) -> object:
        return source_service(request).list(include_deleted=include_deleted)

    @app.get("/api/source-operations", tags=["sources"])
    def list_source_operations(request: Request) -> object:
        runtime = cast(RuntimeContext, request.app.state.runtime)
        return runtime.source_repository.list_source_operations()

    @app.put("/api/sources/{source_id}", response_model=SourceResponse, tags=["sources"])
    def update_source(source_id: str, payload: SourceWriteRequest, request: Request) -> object:
        try:
            return source_service(request).update(source_id, draft(payload))
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except SourceRepositoryError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/api/sources/{source_id}/state", response_model=SourceResponse, tags=["sources"])
    def set_source_state(source_id: str, payload: StateRequest, request: Request) -> object:
        service = source_service(request)
        try:
            return (
                service.resume(source_id)
                if payload.state is SourceState.ACTIVE
                else service.pause(source_id)
            )
        except SourceRepositoryError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.delete("/api/sources/{source_id}", response_model=SourceResponse, tags=["sources"])
    def delete_source(source_id: str, request: Request) -> object:
        try:
            return source_service(request).delete(source_id)
        except SourceRepositoryError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/api/experts", response_model=ExpertResponse, tags=["experts"])
    def create_expert(payload: ExpertWriteRequest, request: Request) -> object:
        try:
            return source_service(request).create_expert(payload.name, payload.source_ids)
        except SourceRepositoryError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.get("/api/experts", response_model=list[ExpertResponse], tags=["experts"])
    def list_experts(request: Request, include_deleted: bool = False) -> object:
        return source_service(request).list_experts(include_deleted=include_deleted)

    @app.put("/api/experts/{expert_id}", response_model=ExpertResponse, tags=["experts"])
    def update_expert(expert_id: str, payload: ExpertWriteRequest, request: Request) -> object:
        try:
            return source_service(request).update_expert(
                expert_id, payload.name, payload.source_ids
            )
        except SourceRepositoryError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/api/experts/{expert_id}/state", response_model=ExpertResponse, tags=["experts"])
    def set_expert_state(expert_id: str, payload: StateRequest, request: Request) -> object:
        try:
            return source_service(request).set_expert_state(expert_id, payload.state)
        except SourceRepositoryError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.delete("/api/experts/{expert_id}", response_model=ExpertResponse, tags=["experts"])
    def delete_expert(expert_id: str, request: Request) -> object:
        try:
            return source_service(request).set_expert_state(expert_id, SourceState.DELETED)
        except SourceRepositoryError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/api/dashboard", tags=["phase7"])
    def dashboard(request: Request, report_date: date | None = None) -> object:
        runtime = cast(RuntimeContext, request.app.state.runtime)
        return runtime.phase7_repository.dashboard(
            report_date or datetime.now().astimezone().date()
        )

    @app.get("/api/topics", tags=["phase7"])
    def list_topics(request: Request) -> object:
        runtime = cast(RuntimeContext, request.app.state.runtime)
        settings_value = runtime.phase7_repository.get_settings()
        summaries = {item["name"]: item for item in runtime.phase7_repository.topic_summaries()}
        ordered = [summaries[topic] for topic in settings_value["topic_order"]]
        return {"topics": settings_value["topic_order"], "summaries": ordered}

    @app.get("/api/archive", tags=["phase7"])
    def list_archive(
        request: Request,
        topic: str | None = None,
        tier: str | None = None,
        source: str | None = None,
        tag: str | None = None,
        favorite: bool | None = None,
        unread: bool | None = None,
        read_state: str | None = Query(default=None, pattern="^(?:READ|UNREAD)$"),
        date_from: date | None = None,
        date_to: date | None = None,
        min_score: float | None = Query(default=None, ge=0, le=100),
        sort: str = Query(
            default="PUBLISHED_DESC", pattern="^(?:PUBLISHED_DESC|SCORE_DESC|TIER_PRIORITY)$"
        ),
        trash: bool = False,
        paged: bool = False,
        page: int = Query(default=1, ge=1),
        page_size: int = Query(default=50, ge=1, le=200),
        limit: int = Query(default=200, ge=1, le=1000),
    ) -> object:
        runtime = cast(RuntimeContext, request.app.state.runtime)
        resolved_read_state = read_state
        if resolved_read_state is None and unread is not None:
            resolved_read_state = "UNREAD" if unread else "READ"
        if paged:
            return runtime.phase7_repository.query_archive(
                topic=topic,
                tier=tier,
                source_id=source,
                tag=tag,
                favorite=favorite,
                read_state=resolved_read_state,
                include_trashed=trash,
                published_from=date_from,
                published_to=date_to,
                minimum_score=min_score,
                sort=sort,
                page=page,
                page_size=page_size,
            )
        return runtime.phase7_repository.list_archive(
            topic=topic,
            tier=tier,
            favorite=favorite,
            read_state=resolved_read_state,
            include_trashed=trash,
            published_from=date_from,
            published_to=date_to,
            source_id=source,
            tag=tag,
            minimum_score=min_score,
            sort=sort,
            limit=limit,
        )

    @app.get("/api/archive/{event_id}", tags=["phase7"])
    def archive_detail(event_id: str, request: Request) -> object:
        runtime = cast(RuntimeContext, request.app.state.runtime)
        try:
            return runtime.phase7_repository.detail(event_id)
        except Phase7RepositoryError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.put("/api/archive/{event_id}/note", tags=["phase7"])
    def save_note(event_id: str, payload: NoteRequest, request: Request) -> object:
        try:
            archive_service(request).save_note(event_id, payload.body)
            return {"event_id": event_id, "body": payload.body}
        except ArchiveInvariantError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.patch("/api/archive/{event_id}/metadata", tags=["phase7"])
    def update_metadata(event_id: str, payload: UserMetadataRequest, request: Request) -> object:
        try:
            return archive_service(request).update_user_metadata(
                event_id,
                favorite=payload.favorite,
                pinned=payload.pinned,
                read_state=None if payload.read_state is None else ReadState(payload.read_state),
            )
        except ArchiveInvariantError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/api/archive/{event_id}/trash", tags=["phase7"])
    def trash_archive(event_id: str, payload: TrashRequest, request: Request) -> object:
        try:
            archive_service(request).move_to_trash(event_id, payload.reason)
            return {"event_id": event_id, "trash_state": "TRASHED"}
        except ArchiveInvariantError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/api/archive/{event_id}/restore", tags=["phase7"])
    def restore_archive(event_id: str, request: Request) -> object:
        try:
            archive_service(request).restore_from_trash(event_id)
            return {"event_id": event_id, "trash_state": "ACTIVE"}
        except ArchiveInvariantError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.delete("/api/archive/{event_id}", tags=["phase7"])
    def delete_archive(event_id: str, request: Request, confirmed: bool = False) -> object:
        try:
            deleted = archive_service(request).permanently_delete(event_id, confirmed=confirmed)
            if not deleted:
                raise HTTPException(status_code=409, detail="explicit confirmation is required")
            return {"event_id": event_id, "deleted": True}
        except ArchiveInvariantError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.get("/api/search", tags=["phase7"])
    def local_search(
        request: Request,
        q: str = Query(min_length=1, max_length=500),
        topic: str | None = None,
        tier: str | None = None,
        source: str | None = None,
        tag: str | None = None,
        favorite: bool | None = None,
        read_state: str | None = Query(default=None, pattern="^(?:READ|UNREAD)$"),
        date_from: date | None = None,
        date_to: date | None = None,
        min_score: float | None = Query(default=None, ge=0, le=100),
        sort: str = Query(
            default="RELEVANCE", pattern="^(?:RELEVANCE|PUBLISHED_DESC|SCORE_DESC|TIER_PRIORITY)$"
        ),
        page: int = Query(default=1, ge=1),
        page_size: int | None = Query(default=None, ge=1, le=200),
        limit: int = Query(default=50, ge=1, le=200),
    ) -> object:
        runtime = cast(RuntimeContext, request.app.state.runtime)
        try:
            return runtime.phase7_repository.search(
                q,
                semantic_ranker=semantic_ranker,
                topic=topic,
                tier=tier,
                source_id=source,
                tag=tag,
                favorite=favorite,
                read_state=read_state,
                published_from=date_from,
                published_to=date_to,
                minimum_score=min_score,
                sort=sort,
                page=page,
                page_size=page_size or limit,
            )
        except Phase7RepositoryError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.get("/api/runs", tags=["phase7"])
    def list_runs(request: Request) -> object:
        runtime = cast(RuntimeContext, request.app.state.runtime)
        return runtime.phase7_repository.list_runs()

    @app.get("/api/runs/{run_id}", tags=["phase7"])
    def run_detail(run_id: str, request: Request) -> object:
        runtime = cast(RuntimeContext, request.app.state.runtime)
        try:
            return runtime.phase7_repository.get_run_detail(run_id)
        except Phase7RepositoryError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/api/runs/{run_id}/retry", tags=["phase7"])
    def retry_run(run_id: str, request: Request) -> object:
        runtime = cast(RuntimeContext, request.app.state.runtime)
        work_items = runtime.phase7_repository.list_retry_work_items(run_id)
        if not work_items:
            raise HTTPException(status_code=409, detail="run has no failed stage to retry")
        if retry_handler is None:
            raise HTTPException(status_code=503, detail="retry executor is not configured")
        completed: list[dict[str, str]] = []
        failed: list[dict[str, str]] = []
        for item in work_items:
            outcome = retry_handler(item["aggregate_version_id"], item["stage"])
            if outcome.succeeded:
                runtime.phase6_repository.mark_work_item(
                    run_id,
                    item["aggregate_version_id"],
                    status="COMPLETED",
                    stage=item["stage"],
                    at=utc_now(),
                )
                completed.append(item)
            else:
                failed.append({**item, "error_code": outcome.failure_code or "RETRY_FAILED"})
        remaining = runtime.phase6_repository.reconcile_run_after_retry(run_id, at=utc_now())
        return {
            "run_id": run_id,
            "retried": completed,
            "failed": failed,
            "remaining_retry_count": remaining,
        }

    @app.post("/api/digests/{digest_id}/retry-failed-segments", tags=["phase7"])
    def retry_failed_delivery_segments(digest_id: str, request: Request) -> object:
        runtime = cast(RuntimeContext, request.app.state.runtime)
        try:
            runtime.phase6_repository.get_digest(digest_id)
        except NoResultFound as exc:
            raise HTTPException(status_code=404, detail="digest not found") from exc
        if delivery_retry_handler is None:
            raise HTTPException(status_code=503, detail="delivery retry executor is not configured")
        try:
            result = delivery_retry_handler(digest_id)
        except NoFailedDeliverySegmentsError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {
            "digest_id": result.digest_id,
            "retried_segment_ids": list(result.retried_segment_ids),
            "status": result.status,
            "successful_segments": result.successful_segments,
            "failed_segments": result.failed_segments,
        }

    @app.get("/api/settings", tags=["phase7"])
    def get_settings(request: Request) -> object:
        runtime = cast(RuntimeContext, request.app.state.runtime)
        return runtime.phase7_repository.get_settings()

    @app.get("/api/configuration-status", tags=["phase7"])
    def configuration_status() -> object:
        services = {
            "semantic_search": semantic_ranker is not None,
            "expansion_search": expansion_provider is not None,
            "intelligence_processing": processing_llm is not None,
            "retry_executor": retry_handler is not None,
            "feishu": delivery_retry_handler is not None,
        }
        display_names = {
            "semantic_search": "语义检索服务",
            "expansion_search": "扩展搜索服务",
            "intelligence_processing": "情报处理模型",
            "retry_executor": "失败重试执行器",
            "feishu": "飞书推送",
        }
        return {
            **services,
            "services": services,
            "missing_items": [display_names[key] for key, ready in services.items() if not ready],
        }

    @app.get("/api/scoring-config", tags=["phase7"])
    def scoring_config(request: Request) -> object:
        runtime = cast(RuntimeContext, request.app.state.runtime)
        config = runtime.intelligence_repository.ensure_default_config(utc_now())
        return {"version": config.version, "weights": dict(config.weights)}

    @app.put("/api/settings", tags=["phase7"])
    def update_settings(payload: SettingsRequest, request: Request) -> object:
        runtime = cast(RuntimeContext, request.app.state.runtime)
        try:
            return runtime.phase7_repository.update_settings(
                schedule_time=payload.schedule_time,
                selection_threshold=payload.selection_threshold,
                tier_caps=payload.tier_caps,
                topic_order=payload.topic_order,
                default_sort=payload.default_sort,
                github_rules=payload.github_rules.model_dump(),
                updated_at=utc_now(),
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.get("/api/feedback", tags=["phase7"])
    def list_feedback(request: Request) -> object:
        runtime = cast(RuntimeContext, request.app.state.runtime)
        return runtime.phase7_repository.list_feedback()

    @app.post("/api/feedback", tags=["phase7"])
    def submit_feedback(payload: FeedbackRequest, request: Request) -> object:
        runtime = cast(RuntimeContext, request.app.state.runtime)
        try:
            feedback_id = CalibrationService(
                runtime.intelligence_repository, TelemetryRecorder(runtime.engine)
            ).submit_feedback(
                payload.score_id,
                reason=payload.reason,
                affected_dimension=payload.affected_dimension,
                content_features=payload.content_features,
                removed=payload.removed,
                submitted_at=utc_now(),
            )
            return {"feedback_id": feedback_id}
        except (ValueError, RuntimeError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.post("/api/calibration/proposals", tags=["phase7"])
    def propose_calibration(request: Request) -> object:
        runtime = cast(RuntimeContext, request.app.state.runtime)
        assessment = CalibrationService(
            runtime.intelligence_repository, TelemetryRecorder(runtime.engine)
        ).propose(user_initiated=True, proposed_at=utc_now())
        return {
            "sample_count": assessment.sample_count,
            "uncertainty": assessment.uncertainty,
            "proposal": assessment.proposal,
        }

    @app.post("/api/calibration/{proposal_id}/confirm", tags=["phase7"])
    def confirm_calibration(
        proposal_id: str, payload: ConfirmationRequest, request: Request
    ) -> object:
        runtime = cast(RuntimeContext, request.app.state.runtime)
        try:
            version = CalibrationService(
                runtime.intelligence_repository, TelemetryRecorder(runtime.engine)
            ).confirm(proposal_id, user_confirmed=payload.confirmed, confirmed_at=utc_now())
            return {"config_version": version}
        except (ValueError, RuntimeError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/api/calibration/{proposal_id}/reject", tags=["phase7"])
    def reject_calibration(proposal_id: str, request: Request) -> object:
        runtime = cast(RuntimeContext, request.app.state.runtime)
        try:
            CalibrationService(runtime.intelligence_repository).reject(
                proposal_id, rejected_at=utc_now()
            )
            return {"proposal_id": proposal_id, "decision": "REJECTED"}
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/api/calibration/config/{version}/rollback", tags=["phase7"])
    def rollback_calibration(
        version: int, payload: ConfirmationRequest, request: Request
    ) -> object:
        runtime = cast(RuntimeContext, request.app.state.runtime)
        try:
            CalibrationService(
                runtime.intelligence_repository, TelemetryRecorder(runtime.engine)
            ).rollback(version, user_confirmed=payload.confirmed, changed_at=utc_now())
            return {"config_version": version, "active": True}
        except (ValueError, RuntimeError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.get("/api/calibration/workbench", tags=["phase7"])
    def calibration_workbench(request: Request) -> object:
        runtime = cast(RuntimeContext, request.app.state.runtime)
        runtime.intelligence_repository.ensure_default_config(utc_now())
        return runtime.phase7_repository.calibration_workbench()

    @app.post("/api/calibration/rescore", tags=["phase7"])
    def rescore_history(payload: RescoreRequest, request: Request) -> object:
        runtime = cast(RuntimeContext, request.app.state.runtime)
        try:
            if not payload.confirmed:
                raise ValueError("historical rescoring requires user confirmation")
            unique_ids = tuple(dict.fromkeys(payload.aggregate_version_ids))
            eligible_ids = {
                str(value["aggregate_version_id"])
                for value in runtime.phase7_repository.calibration_workbench()["rescore_targets"]
            }
            if not set(unique_ids) <= eligible_ids:
                raise ValueError("historical rescoring is limited to feedback-linked items")
            # Validate the full scope before the first append so an invalid later item
            # cannot leave a partially rescored user operation.
            before = []
            for aggregate_version_id in unique_ids:
                runtime.intelligence_repository.get_candidate_context(aggregate_version_id)
                scores = runtime.intelligence_repository.score_history(aggregate_version_id)
                before.append(
                    {
                        "aggregate_version_id": aggregate_version_id,
                        "score_count": len(scores),
                        "latest_score": float(scores[-1]["total"]),
                    }
                )
            score_ids = CalibrationService(runtime.intelligence_repository).rescore_history(
                unique_ids, user_initiated=True, rescored_at=utc_now()
            )
            after = [runtime.intelligence_repository.get_score(score_id) for score_id in score_ids]
            return {
                "appended": [
                    {
                        **previous,
                        "new_score_id": score.score_id,
                        "new_score": score.result.total,
                        "config_version": score.config_version,
                        "score_count": cast(int, previous["score_count"]) + 1,
                    }
                    for previous, score in zip(before, after, strict=True)
                ]
            }
        except (ValueError, RuntimeError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/api/archive/{event_id}/expansion-search", tags=["phase7"])
    def expansion_search(
        event_id: str, payload: ExpansionSearchRequest, request: Request
    ) -> object:
        runtime = cast(RuntimeContext, request.app.state.runtime)
        try:
            runtime.repository.get_ready(event_id)
        except ArchiveInvariantError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        if expansion_provider is None:
            return runtime.phase7_repository.save_extension_run(
                event_id,
                payload.query,
                status="UNAVAILABLE",
                error_code="EXPANSION_PROVIDER_NOT_CONFIGURED",
                hits=(),
                created_at=utc_now(),
            )
        try:
            hits = expansion_provider.search(payload.query)
            return runtime.phase7_repository.save_extension_run(
                event_id,
                payload.query,
                status="SUCCEEDED",
                error_code=None,
                hits=hits,
                created_at=utc_now(),
            )
        except Exception:
            return runtime.phase7_repository.save_extension_run(
                event_id,
                payload.query,
                status="FAILED",
                error_code="EXPANSION_SEARCH_FAILED",
                hits=(),
                created_at=utc_now(),
            )

    @app.post("/api/archive/{event_id}/topic-idea", tags=["phase7"])
    def generate_topic_idea(event_id: str, request: Request) -> object:
        runtime = cast(RuntimeContext, request.app.state.runtime)
        try:
            runtime.repository.get_ready(event_id)
        except ArchiveInvariantError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        aggregate_version_id = runtime.phase7_repository.current_aggregate_version_id(event_id)
        if aggregate_version_id is None:
            raise HTTPException(
                status_code=409,
                detail="archive item has no traceable aggregate version",
            )

        def response_for(*, created: bool) -> dict[str, object]:
            idea = runtime.phase7_repository.detail(event_id)["topic_idea"]
            if idea is None:
                raise RuntimeError("topic idea was not persisted")
            return {
                "status": "SUCCEEDED",
                "created": created,
                "idea": idea,
            }

        existing = runtime.intelligence_repository.get_topic_idea(aggregate_version_id)
        if existing is not None:
            return response_for(created=False)
        if processing_llm is None:
            raise HTTPException(
                status_code=503,
                detail="topic idea generation is not configured",
            )
        try:
            TopicIdeaService(runtime.intelligence_repository, processing_llm).generate(
                aggregate_version_id,
                trigger=TopicIdeaTrigger.MANUAL,
                created_at=utc_now(),
            )
            return response_for(created=True)
        except IntegrityError:
            concurrent = runtime.intelligence_repository.get_topic_idea(aggregate_version_id)
            if concurrent is not None:
                return response_for(created=False)
            raise
        except TimeoutError as exc:
            raise HTTPException(
                status_code=502, detail="topic idea generation timed out; retry is available"
            ) from exc
        except ProcessingContractError as exc:
            raise HTTPException(
                status_code=502,
                detail="topic idea generation returned invalid output; retry is available",
            ) from exc
        except RuntimeError as exc:
            raise HTTPException(
                status_code=502, detail="topic idea generation failed; retry is available"
            ) from exc

    def _favorite_extension(result_id: str, request: Request) -> object:
        runtime = cast(RuntimeContext, request.app.state.runtime)
        try:
            result = runtime.phase7_repository.get_extension_result(result_id)
            completed = runtime.phase7_repository.extension_favorite_outcome(result_id)
            if completed is not None:
                runtime.repository.update_user_metadata(str(completed["event_id"]), favorite=True)
                return completed
            existing = runtime.phase7_repository.find_event_by_source_url(str(result["url"]))
            if existing is not None:
                runtime.repository.update_user_metadata(existing, favorite=True)
                runtime.phase7_repository.mark_extension_favorite(result_id, existing)
                return {"event_id": existing, "deduplicated": True}
            if processing_llm is None:
                raise HTTPException(
                    status_code=503, detail="intelligence processing is not configured"
                )
            ingested = ExtensionIngestionService(
                source_repository=runtime.source_repository,
                event_repository=runtime.event_repository,
                intelligence_repository=runtime.intelligence_repository,
                archive_service=archive_service(request),
                llm=processing_llm,
            ).ingest(
                result,
                selected_at=utc_now(),
                threshold=float(runtime.phase7_repository.get_settings()["selection_threshold"]),
            )
            runtime.repository.update_user_metadata(ingested.event_id, favorite=True)
            runtime.phase7_repository.mark_extension_favorite(result_id, ingested.event_id)
            return {
                "event_id": ingested.event_id,
                "deduplicated": ingested.deduplicated,
            }
        except (Phase7RepositoryError, ExtensionIngestionError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/api/extension-results/{result_id}/favorite", tags=["phase7"])
    def favorite_extension(result_id: str, request: Request) -> object:
        with extension_favorite_lock:
            return _favorite_extension(result_id, request)

    return app
