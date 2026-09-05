"""Feishu adapters. Only deterministic fakes are enabled by default."""

from ai_intel.adapters.feishu.fake import FakeFeishuSender

__all__ = ["FakeFeishuSender"]
