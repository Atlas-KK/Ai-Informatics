"""Deterministic Feishu test adapter with segment-level failure injection."""

from dataclasses import dataclass, field

from ai_intel.domain.pipeline import DeliverySegmentRecord


@dataclass(slots=True)
class FakeFeishuSender:
    fail_segment_numbers: set[int] = field(default_factory=set)
    attempts: list[str] = field(default_factory=list, init=False)
    sent: list[str] = field(default_factory=list, init=False)
    sent_segments: list[DeliverySegmentRecord] = field(default_factory=list, init=False)

    def send_private(self, segment: DeliverySegmentRecord) -> None:
        self.attempts.append(segment.idempotency_key)
        if segment.segment_no in self.fail_segment_numbers:
            raise RuntimeError("fake Feishu segment failure")
        self.sent.append(segment.idempotency_key)
        self.sent_segments.append(segment)
