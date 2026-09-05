"""Versioned local daily digest generated only from formal READY archives."""

import json
import os
from collections import Counter
from datetime import date, datetime

from ai_intel.application.archive import ArchiveService
from ai_intel.application.daily_selection import DailySelectionResult
from ai_intel.domain.models import ReadyArchiveRecord
from ai_intel.domain.pipeline import DigestRecord
from ai_intel.domain.states import Tier
from ai_intel.domain.tiering import RankedCandidate
from ai_intel.domain.topics import PrimaryTopic
from ai_intel.infrastructure.db.intelligence_repository import SQLiteIntelligenceRepository
from ai_intel.infrastructure.db.pipeline_repository import Phase6Repository
from ai_intel.infrastructure.telemetry import TelemetryEventType, TelemetryRecorder

DEFAULT_TOPIC_ORDER = tuple(item.value for item in PrimaryTopic)
_TIER_ORDER = {Tier.MUST_READ: 0, Tier.IMPORTANT: 1, Tier.EXTENDED: 2}
_TIER_LABEL = {Tier.MUST_READ: "必读", Tier.IMPORTANT: "重要", Tier.EXTENDED: "扩展"}


class DigestService:
    def __init__(
        self,
        repository: Phase6Repository,
        intelligence_repository: SQLiteIntelligenceRepository,
        archive_service: ArchiveService,
        telemetry: TelemetryRecorder,
        *,
        topic_order: tuple[str, ...] = DEFAULT_TOPIC_ORDER,
    ) -> None:
        self.repository = repository
        self.intelligence_repository = intelligence_repository
        self.archive_service = archive_service
        self.telemetry = telemetry
        self.topic_order = topic_order

    def generate(
        self,
        report_date: date,
        selection: DailySelectionResult,
        *,
        generated_at: datetime,
        topic_order: tuple[str, ...] | None = None,
        run_id: str | None = None,
    ) -> DigestRecord:
        if len(selection.ranked) != len(selection.formal_event_ids):
            raise ValueError("daily digest requires every selected item to be formally archived")
        effective_topic_order = self.topic_order if topic_order is None else topic_order
        topic_rank = {topic: index for index, topic in enumerate(effective_topic_order)}
        entries = []
        for ranked, event_id in zip(selection.ranked, selection.formal_event_ids, strict=True):
            ready = self.archive_service.repository.get_ready(event_id)
            entries.append((ranked, ready))
        entries.sort(
            key=lambda item: (
                _TIER_ORDER[item[0].tier],
                topic_rank.get(item[1].primary_topic, len(topic_rank)),
                item[0].rank,
            )
        )
        markdown = self._render(report_date, tuple(entries))
        counts = Counter(item.tier.value for item, _ in entries)
        tier_counts = {tier.value: counts[tier.value] for tier in Tier}
        digest = self.repository.save_digest(
            report_date=report_date,
            selection_run_id=selection.selection_run_id,
            markdown=markdown,
            event_ids=tuple(ready.event_id for _, ready in entries),
            tier_counts=tier_counts,
            topic_order=effective_topic_order,
            created_at=generated_at,
        )
        self._write_digest(digest)
        self.telemetry.record(
            TelemetryEventType.DAILY_DIGEST_GENERATED,
            {
                "digest_id": digest.digest_id,
                "date": report_date.isoformat(),
                "qualified_count": len(selection.ranked),
                "archived_count": len(selection.formal_event_ids),
                "must_read_count": tier_counts[Tier.MUST_READ.value],
                "important_count": tier_counts[Tier.IMPORTANT.value],
                "extended_count": tier_counts[Tier.EXTENDED.value],
            },
            created_at=generated_at,
            run_id=run_id,
        )
        return digest

    def _render(
        self,
        report_date: date,
        entries: tuple[tuple[RankedCandidate, ReadyArchiveRecord], ...],
    ) -> str:
        lines = [f"# AI 情报日报 · {report_date.isoformat()}", ""]
        if not entries:
            return "\n".join((*lines, "今日无达标情报", ""))
        for ranked, ready in entries:
            change_type, sources = self.archive_service.repository.get_delivery_metadata(
                ready.event_id
            )
            idea = self.intelligence_repository.get_topic_idea(
                ranked.candidate.aggregate_version_id
            )
            lines.extend(
                (
                    f"## {_TIER_LABEL[ranked.tier]} · {ready.primary_topic}",
                    "",
                    f"### {ranked.rank}. {ready.canonical_title}",
                    "",
                    f"- 标识：{change_type}",
                    f"- 质量分：{ready.quality_score:.2f}",
                    f"- 中文摘要：{ready.summary}",
                    "- 来源：" + "；".join(f"[{source_id}]({url})" for source_id, url in sources),
                )
            )
            if idea is not None:
                outline = " / ".join(json.loads(str(idea["outline_json"])))
                lines.extend(
                    (
                        f"- 选题标题：{idea['title']}",
                        f"- 内容大纲：{outline}",
                        f"- 核心爆点：{idea['hook']}",
                    )
                )
            lines.append("")
        return "\n".join(lines)

    def _write_digest(self, digest: DigestRecord) -> None:
        target = (self.repository.data_dir / digest.markdown_path).resolve()
        if self.repository.data_dir not in target.parents:
            raise RuntimeError("digest path escapes configured data directory")
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(".tmp")
        with temporary.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(digest.markdown)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
