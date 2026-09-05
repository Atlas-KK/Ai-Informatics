"""Outbound Feishu boundary; implementations never receive credentials in messages."""

from typing import Protocol

from ai_intel.domain.pipeline import DeliverySegmentRecord


class FeishuSender(Protocol):
    def send_private(self, segment: DeliverySegmentRecord) -> None: ...
