"""Segmented Feishu outbox with stable idempotency and failed-only retries."""

from datetime import datetime

from ai_intel.config import MissingConfigurationError
from ai_intel.domain.pipeline import DeliveryResult, DeliverySegmentRecord, DeliveryStatus
from ai_intel.infrastructure.db.pipeline_repository import Phase6Repository
from ai_intel.infrastructure.telemetry import TelemetryEventType, TelemetryRecorder
from ai_intel.ports.feishu import FeishuSender


class DeliveryService:
    def __init__(
        self,
        repository: Phase6Repository,
        telemetry: TelemetryRecorder,
        sender: FeishuSender | None = None,
        *,
        max_segment_chars: int = 3500,
    ) -> None:
        if max_segment_chars < 100:
            raise ValueError("delivery segment limit must be at least 100 characters")
        self.repository = repository
        self.telemetry = telemetry
        self.sender = sender
        self.max_segment_chars = max_segment_chars

    def prepare(self, digest_id: str, *, created_at: datetime) -> tuple[DeliverySegmentRecord, ...]:
        digest = self.repository.get_digest(digest_id)
        return self.repository.ensure_segments(
            digest_id,
            self._split(digest.markdown),
            created_at=created_at,
        )

    def push(
        self, digest_id: str, *, pushed_at: datetime, run_id: str | None = None
    ) -> DeliveryResult:
        if self.sender is None:
            raise MissingConfigurationError("FEISHU_APP_ID")
        segments = self.prepare(digest_id, created_at=pushed_at)
        for segment in segments:
            if segment.status is DeliveryStatus.SENT:
                continue
            try:
                self.sender.send_private(segment)
            # The sender is an external boundary: network/client libraries expose
            # different Exception subclasses, but every failed attempt must reach
            # the outbox instead of aborting the remaining segments.
            except Exception:
                self.repository.mark_segment(
                    segment.segment_id,
                    status=DeliveryStatus.FAILED,
                    at=pushed_at,
                    error_code="FEISHU_SEND_FAILED",
                )
            else:
                self.repository.mark_segment(
                    segment.segment_id,
                    status=DeliveryStatus.SENT,
                    at=pushed_at,
                    error_code=None,
                )
        final = self.repository.list_segments(digest_id)
        successful = sum(item.status is DeliveryStatus.SENT for item in final)
        failed = sum(item.status is DeliveryStatus.FAILED for item in final)
        status = "SUCCESS" if failed == 0 else "FAILED" if successful == 0 else "PARTIAL"
        digest = self.repository.get_digest(digest_id)
        self.telemetry.record(
            TelemetryEventType.DAILY_DIGEST_PUSHED,
            {
                "date": digest.report_date,
                "status": status,
                "successful_segments": successful,
                "failed_segments": failed,
                "error_code": None if failed == 0 else "FEISHU_SEND_FAILED",
            },
            created_at=pushed_at,
            run_id=run_id,
        )
        return DeliveryResult(digest_id, status, successful, failed)

    def _split(self, markdown: str) -> tuple[str, ...]:
        segments: list[str] = []
        current = ""
        for line in markdown.splitlines(keepends=True):
            if current and len(current) + len(line) > self.max_segment_chars:
                segments.append(current.rstrip())
                current = ""
            while len(line) > self.max_segment_chars:
                available = self.max_segment_chars - len(current)
                current += line[:available]
                segments.append(current.rstrip())
                current = ""
                line = line[available:]
            current += line
        if current or not segments:
            segments.append(current.rstrip())
        return tuple(segments)
