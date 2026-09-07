# ruff: noqa: E501
"""Read models, local search and transient extension state for Phase 7."""

import json
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import uuid4

from sqlalchemy import Engine, insert, select, text, update

from ai_intel.application.search import ExternalSearchHit, SearchDocument, SemanticRanker
from ai_intel.domain.fingerprint import normalize_url
from ai_intel.infrastructure.db.schema import (
    aggregate_evidence,
    aggregate_versions,
    archive_search_documents,
    collected_raw_snapshots,
    extension_search_results,
    extension_search_runs,
    formalization_links,
    github_discovery_settings,
    ui_settings,
)

TOPICS = (
    "大模型与智能体",
    "AI 产品形态与行业应用",
    "AI 产品实战",
    "AI 工程安全与可靠性",
)


class Phase7RepositoryError(RuntimeError):
    pass


def _iso(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must include a timezone")
    return value.astimezone(UTC).isoformat()


class Phase7Repository:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def get_settings(self) -> dict[str, Any]:
        with self.engine.connect() as connection:
            row = connection.execute(select(ui_settings)).mappings().one()
            github_row = connection.execute(select(github_discovery_settings)).mappings().one()
        return {
            "schedule_time": str(row["schedule_time"]),
            "selection_threshold": float(row["selection_threshold"]),
            "tier_caps": json.loads(str(row["tier_caps_json"])),
            "topic_order": json.loads(str(row["topic_order_json"])),
            "default_sort": str(row["default_sort"]),
            "github_rules": {
                "daily_trending": bool(github_row["daily_trending"]),
                "weekly_trending": bool(github_row["weekly_trending"]),
                "seven_day_star_growth": bool(github_row["seven_day_star_growth"]),
                "ai_relevance": bool(github_row["ai_relevance"]),
                "whitelist": json.loads(str(github_row["whitelist_json"])),
            },
            "updated_at": str(row["updated_at"]),
        }

    def update_settings(
        self,
        *,
        schedule_time: str,
        selection_threshold: float,
        tier_caps: Mapping[str, int],
        topic_order: Sequence[str],
        default_sort: str,
        github_rules: Mapping[str, Any],
        updated_at: datetime,
    ) -> dict[str, Any]:
        if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", schedule_time):
            raise ValueError("schedule_time must use 24-hour HH:MM format")
        if not 0 <= selection_threshold <= 100:
            raise ValueError("selection_threshold must be between 0 and 100")
        if set(topic_order) != set(TOPICS) or len(topic_order) != len(TOPICS):
            raise ValueError("topic_order must contain each supported topic exactly once")
        expected_tiers = {"MUST_READ", "IMPORTANT", "EXTENDED"}
        if set(tier_caps) != expected_tiers or any(value < 0 for value in tier_caps.values()):
            raise ValueError("tier_caps must contain non-negative values for all tiers")
        if default_sort not in {"PUBLISHED_DESC", "SCORE_DESC"}:
            raise ValueError("unsupported default_sort")
        expected_github_flags = {
            "daily_trending",
            "weekly_trending",
            "seven_day_star_growth",
            "ai_relevance",
        }
        if not expected_github_flags.issubset(github_rules):
            raise ValueError("github_rules is missing required discovery flags")
        whitelist = github_rules.get("whitelist")
        if not isinstance(whitelist, list) or any(
            not isinstance(item, str) or not re.fullmatch(r"[^/\s]+/[^/\s]+", item.strip())
            for item in whitelist
        ):
            raise ValueError("GitHub whitelist entries must use owner/repository format")
        normalized_whitelist = list(dict.fromkeys(item.strip() for item in whitelist))
        with self.engine.begin() as connection:
            connection.execute(
                update(ui_settings)
                .where(ui_settings.c.singleton_id == 1)
                .values(
                    schedule_time=schedule_time,
                    selection_threshold=selection_threshold,
                    tier_caps_json=json.dumps(dict(tier_caps), sort_keys=True),
                    topic_order_json=json.dumps(tuple(topic_order), ensure_ascii=False),
                    default_sort=default_sort,
                    updated_at=_iso(updated_at),
                )
            )
            connection.execute(
                update(github_discovery_settings)
                .where(github_discovery_settings.c.singleton_id == 1)
                .values(
                    **{key: bool(github_rules[key]) for key in expected_github_flags},
                    whitelist_json=json.dumps(normalized_whitelist, ensure_ascii=False),
                    updated_at=_iso(updated_at),
                )
            )
        return self.get_settings()

    @staticmethod
    def _archive_sql(*, include_trashed: bool) -> str:
        trash_condition = (
            "um.trash_state = 'TRASHED'" if include_trashed else "um.trash_state = 'ACTIVE'"
        )
        return f"""
            SELECT e.event_id, v.version_no, v.change_type, v.canonical_title, v.primary_topic,
                   v.summary, v.content, v.content_hash, ds.score_id AS feedback_score_id,
                   s.total AS quality_score, s.config_version AS score_version, s.tier,
                   s.dimensions_json,
                   MIN(ev.published_at) AS published_at,
                   GROUP_CONCAT(DISTINCT ev.source_id) AS source_ids,
                   um.favorite, um.pinned, um.read_state, um.trash_state, um.trash_reason,
                   COALESCE(n.body, '') AS note, COALESCE(MAX(p.tags_json), '[]') AS tags_json
            FROM events e
            JOIN event_versions v ON v.event_id=e.event_id AND v.version_no=e.current_version
            JOIN staged_commits sc ON sc.event_id=e.event_id AND sc.version_no=e.current_version AND sc.state='READY'
            JOIN scores s ON s.version_id=v.version_id
              AND s.config_version=(SELECT MAX(s2.config_version) FROM scores s2 WHERE s2.version_id=v.version_id)
            JOIN evidence ev ON ev.version_id=v.version_id
            JOIN user_metadata um ON um.event_id=e.event_id
            LEFT JOIN notes n ON n.event_id=e.event_id
            LEFT JOIN formalization_links f
              ON f.formal_event_id=e.event_id AND f.formal_version_no=v.version_no
            LEFT JOIN ai_processing_results p ON p.aggregate_version_id=f.aggregate_version_id
            LEFT JOIN daily_selections ds ON ds.selection_id=f.selection_id
            WHERE e.status='READY' AND {trash_condition}
            GROUP BY e.event_id, v.version_id, s.score_id, n.event_id
        """

    def list_archive(
        self,
        *,
        topic: str | None = None,
        tier: str | None = None,
        favorite: bool | None = None,
        unread: bool | None = None,
        read_state: str | None = None,
        include_trashed: bool = False,
        published_from: date | None = None,
        published_to: date | None = None,
        source_id: str | None = None,
        tag: str | None = None,
        minimum_score: float | None = None,
        event_ids: Sequence[str] | None = None,
        sort: str = "PUBLISHED_DESC",
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        page = self.query_archive(
            topic=topic,
            tier=tier,
            favorite=favorite,
            read_state=(
                read_state
                if read_state is not None
                else None
                if unread is None
                else ("UNREAD" if unread else "READ")
            ),
            include_trashed=include_trashed,
            published_from=published_from,
            published_to=published_to,
            source_id=source_id,
            tag=tag,
            minimum_score=minimum_score,
            event_ids=event_ids,
            sort=sort,
            page=1,
            page_size=limit,
        )
        return list(page["items"])

    def query_archive(
        self,
        *,
        topic: str | None = None,
        tier: str | None = None,
        favorite: bool | None = None,
        read_state: str | None = None,
        include_trashed: bool = False,
        published_from: date | None = None,
        published_to: date | None = None,
        source_id: str | None = None,
        tag: str | None = None,
        minimum_score: float | None = None,
        event_ids: Sequence[str] | None = None,
        sort: str = "PUBLISHED_DESC",
        page: int = 1,
        page_size: int = 50,
    ) -> dict[str, Any]:
        conditions: list[str] = []
        resolved_page = max(page, 1)
        resolved_page_size = min(max(page_size, 1), 20000)
        params: dict[str, object] = {
            "limit": resolved_page_size,
            "offset": (resolved_page - 1) * resolved_page_size,
        }
        if topic:
            conditions.append("primary_topic = :topic")
            params["topic"] = topic
        if tier:
            conditions.append("tier = :tier")
            params["tier"] = tier
        if favorite is not None:
            conditions.append("favorite = :favorite")
            params["favorite"] = favorite
        if read_state is not None:
            if read_state not in {"READ", "UNREAD"}:
                raise Phase7RepositoryError("unsupported read state")
            conditions.append("read_state = :read_state")
            params["read_state"] = read_state
        if published_from is not None:
            conditions.append("date(published_at) >= :published_from")
            params["published_from"] = published_from.isoformat()
        if published_to is not None:
            conditions.append("date(published_at) <= :published_to")
            params["published_to"] = published_to.isoformat()
        if source_id:
            conditions.append(
                "EXISTS (SELECT 1 FROM event_versions source_version "
                "JOIN evidence source_evidence ON source_evidence.version_id=source_version.version_id "
                "WHERE source_version.event_id=archive.event_id "
                "AND source_version.version_no=archive.version_no "
                "AND source_evidence.source_id=:source_id)"
            )
            params["source_id"] = source_id
        if tag:
            conditions.append(
                "EXISTS (SELECT 1 FROM json_each(tags_json) tag_value "
                "WHERE CAST(tag_value.value AS TEXT) = :tag)"
            )
            params["tag"] = tag
        if minimum_score is not None:
            conditions.append("quality_score >= :minimum_score")
            params["minimum_score"] = minimum_score
        if event_ids is not None:
            if not event_ids:
                return {
                    "items": [],
                    "total": 0,
                    "page": resolved_page,
                    "page_size": resolved_page_size,
                }
            conditions.append("event_id IN (SELECT value FROM json_each(:event_ids_json))")
            params["event_ids_json"] = json.dumps(tuple(event_ids))
        order_by = {
            "PUBLISHED_DESC": "pinned DESC, published_at DESC, event_id",
            "SCORE_DESC": "pinned DESC, quality_score DESC, published_at DESC, event_id",
            "TIER_PRIORITY": (
                "pinned DESC, CASE tier WHEN 'MUST_READ' THEN 0 WHEN 'IMPORTANT' THEN 1 "
                "ELSE 2 END, quality_score DESC, published_at DESC, event_id"
            ),
        }.get(sort)
        if order_by is None:
            raise Phase7RepositoryError("unsupported archive sort")
        where = "" if not conditions else " WHERE " + " AND ".join(conditions)
        base = f"FROM ({self._archive_sql(include_trashed=include_trashed)}) archive{where}"
        with self.engine.connect() as connection:
            total = int(connection.execute(text(f"SELECT COUNT(*) {base}"), params).scalar_one())
            rows = (
                connection.execute(
                    text(f"SELECT * {base} ORDER BY {order_by} LIMIT :limit OFFSET :offset"),
                    params,
                )
                .mappings()
                .all()
            )
        return {
            "items": [self._archive_item(dict(row)) for row in rows],
            "total": total,
            "page": resolved_page,
            "page_size": resolved_page_size,
        }

    def topic_summaries(self) -> list[dict[str, Any]]:
        base = self._archive_sql(include_trashed=False)
        with self.engine.connect() as connection:
            count_rows = (
                connection.execute(
                    text(
                        f"SELECT primary_topic, COUNT(*) AS total FROM ({base}) archive "
                        "GROUP BY primary_topic"
                    )
                )
                .mappings()
                .all()
            )
            tag_rows = (
                connection.execute(
                    text(
                        f"SELECT primary_topic, CAST(tag_value.value AS TEXT) AS tag, "
                        f"COUNT(*) AS total FROM ({base}) archive, json_each(tags_json) tag_value "
                        "GROUP BY primary_topic, tag_value.value "
                        "ORDER BY primary_topic, total DESC, tag"
                    )
                )
                .mappings()
                .all()
            )
        counts = {str(row["primary_topic"]): int(row["total"]) for row in count_rows}
        tags: dict[str, list[dict[str, Any]]] = {topic: [] for topic in TOPICS}
        for row in tag_rows:
            topic = str(row["primary_topic"])
            tags.setdefault(topic, []).append({"name": str(row["tag"]), "count": int(row["total"])})
        return [
            {"name": topic, "count": counts.get(topic, 0), "tags": tags.get(topic, [])[:8]}
            for topic in TOPICS
        ]

    @staticmethod
    def _archive_item(row: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "event_id": str(row["event_id"]),
            "version_no": int(row["version_no"]),
            "change_type": str(row["change_type"]),
            "title": str(row["canonical_title"]),
            "topic": str(row["primary_topic"]),
            "summary": str(row["summary"]),
            "content": str(row["content"]),
            "content_hash": str(row["content_hash"]),
            "score_id": (
                None if row["feedback_score_id"] is None else str(row["feedback_score_id"])
            ),
            "quality_score": float(row["quality_score"]),
            "score_version": int(row["score_version"]),
            "score_dimensions": json.loads(str(row["dimensions_json"])),
            "tier": str(row["tier"]),
            "published_at": str(row["published_at"]),
            "source_ids": tuple(filter(None, str(row["source_ids"] or "").split(","))),
            "favorite": bool(row["favorite"]),
            "pinned": bool(row["pinned"]),
            "read_state": str(row["read_state"]),
            "trash_state": str(row["trash_state"]),
            "trash_reason": None if row["trash_reason"] is None else str(row["trash_reason"]),
            "note": str(row["note"]),
            "tags": tuple(json.loads(str(row["tags_json"]))),
        }

    def dashboard(self, report_date: date) -> dict[str, Any]:
        start = report_date - timedelta(days=6)
        base = self._archive_sql(include_trashed=False)
        date_where = "date(published_at) BETWEEN :start AND :end"
        params = {"start": start.isoformat(), "end": report_date.isoformat()}
        with self.engine.connect() as connection:
            summary = (
                connection.execute(
                    text(
                        f"SELECT COUNT(*) AS total_count, "
                        "SUM(CASE WHEN date(published_at)=:end THEN 1 ELSE 0 END) AS today_count, "
                        "SUM(CASE WHEN change_type='NEW' THEN 1 ELSE 0 END) AS new_count, "
                        "SUM(CASE WHEN change_type<>'NEW' THEN 1 ELSE 0 END) AS updated_count "
                        f"FROM ({base}) archive WHERE {date_where}"
                    ),
                    params,
                )
                .mappings()
                .one()
            )
            topic_rows = (
                connection.execute(
                    text(
                        f"SELECT primary_topic, COUNT(*) AS total FROM ({base}) archive "
                        f"WHERE {date_where} GROUP BY primary_topic"
                    ),
                    params,
                )
                .mappings()
                .all()
            )
            tier_rows = (
                connection.execute(
                    text(
                        f"SELECT tier, COUNT(*) AS total FROM ({base}) archive "
                        f"WHERE {date_where} GROUP BY tier"
                    ),
                    params,
                )
                .mappings()
                .all()
            )
            source_rows = (
                connection.execute(
                    text(f"SELECT source_ids FROM ({base}) archive WHERE {date_where}"),
                    params,
                )
                .mappings()
                .all()
            )
            trend_rows = (
                connection.execute(
                    text(
                        f"SELECT date(published_at) AS day, COUNT(*) AS total FROM ({base}) archive "
                        f"WHERE {date_where} GROUP BY date(published_at)"
                    ),
                    params,
                )
                .mappings()
                .all()
            )
            latest_run = (
                connection.execute(
                    text(
                        "SELECT run_id, status, started_at, finished_at, attempted_sources, "
                        "successful_sources, failed_sources, archived_count, pending_count, error_code "
                        "FROM pipeline_runs WHERE report_date=:report_date "
                        "ORDER BY started_at DESC LIMIT 1"
                    ),
                    {"report_date": report_date.isoformat()},
                )
                .mappings()
                .first()
            )
        topic_counts = Counter({str(row["primary_topic"]): int(row["total"]) for row in topic_rows})
        tier_counts = Counter({str(row["tier"]): int(row["total"]) for row in tier_rows})
        source_counts: Counter[str] = Counter()
        for row in source_rows:
            source_counts.update(filter(None, str(row["source_ids"] or "").split(",")))
        trend_by_day = {str(row["day"]): int(row["total"]) for row in trend_rows}
        items = self.list_archive(
            published_from=start,
            published_to=report_date,
            sort="TIER_PRIORITY",
            limit=200,
        )
        latest_run_value = None if latest_run is None else dict(latest_run)
        data_complete = latest_run_value is None or (
            str(latest_run_value["status"]) == "SUCCEEDED"
            and int(latest_run_value["failed_sources"]) == 0
            and int(latest_run_value["pending_count"]) == 0
        )
        return {
            "report_date": report_date.isoformat(),
            "window_start": start.isoformat(),
            "total_count": int(summary["total_count"] or 0),
            "today_count": int(summary["today_count"] or 0),
            "items": items,
            "topic_summaries": self.topic_summaries(),
            "topic_counts": {topic: topic_counts[topic] for topic in TOPICS},
            "tier_counts": {
                tier: tier_counts[tier] for tier in ("MUST_READ", "IMPORTANT", "EXTENDED")
            },
            "source_counts": dict(sorted(source_counts.items())),
            "change_counts": {
                "NEW": int(summary["new_count"] or 0),
                "UPDATED": int(summary["updated_count"] or 0),
            },
            "seven_day_trend": {
                (start + timedelta(days=offset)).isoformat(): trend_by_day.get(
                    (start + timedelta(days=offset)).isoformat(), 0
                )
                for offset in range(7)
            },
            "latest_run": latest_run_value,
            "data_complete": data_complete,
        }

    def detail(self, event_id: str) -> dict[str, Any]:
        items = self.list_archive(event_ids=(event_id,), limit=1)
        if not items:
            items = self.list_archive(event_ids=(event_id,), include_trashed=True, limit=1)
        item = next((value for value in items if value["event_id"] == event_id), None)
        if item is None:
            raise Phase7RepositoryError("archive item was not found")
        version_sql = text(
            """
            SELECT v.version_no, v.change_type, v.canonical_title, v.summary, v.content,
                   v.content_hash, v.created_at,
                   p.source_language, p.original_text, p.zh_translation,
                   p.key_conclusions_json, p.pm_value, p.tags_json,
                   s.total AS quality_score, s.tier, s.config_version AS score_version,
                   s.dimensions_json AS score_dimensions_json, s.created_at AS scored_at,
                   cs.rationales_json AS score_rationales_json
            FROM event_versions v
            LEFT JOIN formalization_links f ON f.formal_event_id=v.event_id AND f.formal_version_no=v.version_no
            LEFT JOIN ai_processing_results p ON p.aggregate_version_id=f.aggregate_version_id
            LEFT JOIN scores s ON s.version_id=v.version_id AND s.config_version=(
                SELECT MAX(s2.config_version) FROM scores s2 WHERE s2.version_id=v.version_id
            )
            LEFT JOIN candidate_scores cs ON cs.aggregate_version_id=f.aggregate_version_id
                AND cs.config_version=s.config_version AND cs.score_revision=(
                    SELECT MAX(cs2.score_revision) FROM candidate_scores cs2
                    WHERE cs2.aggregate_version_id=f.aggregate_version_id
                      AND cs2.config_version=s.config_version
                )
            WHERE v.event_id=:event_id ORDER BY v.version_no DESC
            """
        )
        evidence_sql = text(
            """
            SELECT v.version_no, ev.evidence_id, ae.evidence_id AS aggregate_evidence_id,
                   ev.source_id, ev.url, ev.published_at,
                   ev.viewpoint, COALESCE(sc.name, ev.source_id) AS source_name,
                   COALESCE(sc.source_type, crs.source_type) AS source_type,
                   sc.state AS source_state,
                   crs.published_at_unknown, crs.first_seen_at,
                   av.supporting_source_count, av.valid_source_count,
                   ROUND(av.source_coverage_ratio * 100, 1) AS coverage_percent
            FROM event_versions v JOIN evidence ev ON ev.version_id=v.version_id
            LEFT JOIN source_configs sc ON sc.source_id=ev.source_id
            LEFT JOIN formalization_links f
                ON f.formal_event_id=v.event_id AND f.formal_version_no=v.version_no
            LEFT JOIN aggregate_evidence ae
                ON ae.aggregate_version_id=f.aggregate_version_id
               AND ae.source_id=ev.source_id AND ae.url=ev.url
            LEFT JOIN collected_raw_snapshots crs ON crs.snapshot_id=ae.upstream_snapshot_id
            LEFT JOIN aggregate_viewpoints av
                ON av.aggregate_version_id=f.aggregate_version_id
               AND av.normalized_statement=ae.normalized_viewpoint
            WHERE v.event_id=:event_id ORDER BY v.version_no DESC, ev.source_id, ev.url
            """
        )
        idea_sql = text(
            """
            SELECT ti.idea_id, ti.trigger, ti.title, ti.outline_json, ti.hook,
                   ti.support_evidence_ids_json, ti.created_at
            FROM topic_ideas ti JOIN formalization_links f ON f.aggregate_version_id=ti.aggregate_version_id
            WHERE f.formal_event_id=:event_id ORDER BY ti.created_at DESC LIMIT 1
            """
        )
        with self.engine.connect() as connection:
            versions = [
                dict(row)
                for row in connection.execute(version_sql, {"event_id": event_id}).mappings()
            ]
            evidence_rows = [
                dict(row)
                for row in connection.execute(evidence_sql, {"event_id": event_id}).mappings()
            ]
            idea = connection.execute(idea_sql, {"event_id": event_id}).mappings().first()
        for version in versions:
            for key in (
                "key_conclusions_json",
                "tags_json",
                "score_dimensions_json",
                "score_rationales_json",
            ):
                raw = version.pop(key)
                empty_value: list[Any] | dict[str, Any] = (
                    [] if key in ("key_conclusions_json", "tags_json") else {}
                )
                version[key.removesuffix("_json")] = (
                    empty_value if raw is None else json.loads(str(raw))
                )
            version["evidence"] = [
                value for value in evidence_rows if value["version_no"] == version["version_no"]
            ]
        item["versions"] = versions
        support_ids = [] if idea is None else json.loads(str(idea["support_evidence_ids_json"]))
        support_sources = {
            str(value["aggregate_evidence_id"]): {
                "evidence_id": str(value["aggregate_evidence_id"]),
                "source_name": str(value["source_name"]),
                "url": str(value["url"]),
                "viewpoint": str(value["viewpoint"]),
            }
            for value in evidence_rows
            if value["aggregate_evidence_id"] in support_ids
        }
        item["topic_idea"] = (
            None
            if idea is None
            else {
                "idea_id": str(idea["idea_id"]),
                "trigger": str(idea["trigger"]),
                "title": str(idea["title"]),
                "outline": json.loads(str(idea["outline_json"])),
                "hook": str(idea["hook"]),
                "support_evidence_ids": support_ids,
                "support_sources": [
                    support_sources[evidence_id]
                    for evidence_id in support_ids
                    if evidence_id in support_sources
                ],
                "created_at": str(idea["created_at"]),
            }
        )
        return item

    def current_aggregate_version_id(self, event_id: str) -> str | None:
        """Resolve the immutable aggregate version behind the current formal archive version."""
        with self.engine.connect() as connection:
            value = connection.execute(
                text(
                    "SELECT f.aggregate_version_id FROM events e "
                    "JOIN formalization_links f ON f.formal_event_id=e.event_id "
                    "AND f.formal_version_no=e.current_version "
                    "WHERE e.event_id=:event_id AND e.status='READY'"
                ),
                {"event_id": event_id},
            ).scalar_one_or_none()
        return None if value is None else str(value)

    def _sync_search_documents(self) -> None:
        live_query = """
            SELECT e.event_id, v.canonical_title AS title, v.summary, v.content,
                   GROUP_CONCAT(DISTINCT ev.source_id || ' ' || ev.url) AS sources,
                   COALESCE(MAX(p.tags_json), '') AS tags, COALESCE(n.body, '') AS note,
                   MAX(e.updated_at, COALESCE(n.updated_at, '')) AS source_updated_at
            FROM events e
            JOIN event_versions v ON v.event_id=e.event_id AND v.version_no=e.current_version
            JOIN staged_commits sc ON sc.event_id=e.event_id AND sc.version_no=e.current_version AND sc.state='READY'
            JOIN evidence ev ON ev.version_id=v.version_id
            LEFT JOIN formalization_links f ON f.formal_event_id=e.event_id AND f.formal_version_no=e.current_version
            LEFT JOIN ai_processing_results p ON p.aggregate_version_id=f.aggregate_version_id
            LEFT JOIN notes n ON n.event_id=e.event_id
            WHERE e.status='READY'
            GROUP BY e.event_id, v.version_id, n.event_id
            """
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "DELETE FROM archive_search_documents WHERE event_id NOT IN "
                    f"(SELECT event_id FROM ({live_query}) live)"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO archive_search_documents "
                    "(event_id,title,summary,content,sources,tags,note,source_updated_at) "
                    f"SELECT event_id,title,summary,content,sources,tags,note,source_updated_at "
                    f"FROM ({live_query}) live WHERE 1 "
                    "ON CONFLICT(event_id) DO UPDATE SET "
                    "title=excluded.title, summary=excluded.summary, content=excluded.content, "
                    "sources=excluded.sources, tags=excluded.tags, note=excluded.note, "
                    "source_updated_at=excluded.source_updated_at "
                    "WHERE archive_search_documents.source_updated_at <> excluded.source_updated_at"
                )
            )

    def search(
        self,
        query: str,
        *,
        semantic_ranker: SemanticRanker | None = None,
        topic: str | None = None,
        tier: str | None = None,
        source_id: str | None = None,
        tag: str | None = None,
        favorite: bool | None = None,
        read_state: str | None = None,
        published_from: date | None = None,
        published_to: date | None = None,
        minimum_score: float | None = None,
        sort: str = "RELEVANCE",
        page: int = 1,
        page_size: int = 50,
        limit: int | None = None,
    ) -> dict[str, Any]:
        if limit is not None:
            page_size = limit
        query = query.strip()
        if not query:
            return {
                "query": "",
                "mode": "KEYWORD",
                "degraded": semantic_ranker is None,
                "degraded_reason": "SEMANTIC_PROVIDER_NOT_CONFIGURED"
                if semantic_ranker is None
                else None,
                "total": 0,
                "page": max(page, 1),
                "page_size": min(max(page_size, 1), 200),
                "items": [],
            }
        self._sync_search_documents()
        tokens = tuple(filter(None, re.split(r"\s+", query)))
        fts_query = " AND ".join(f'"{token.replace(chr(34), chr(34) * 2)}"' for token in tokens)
        with self.engine.connect() as connection:
            try:
                keyword_rows = (
                    connection.execute(
                        text(
                            "SELECT d.*, bm25(archive_search_fts) AS rank FROM archive_search_fts "
                            "JOIN archive_search_documents d ON d.rowid=archive_search_fts.rowid "
                            "WHERE archive_search_fts MATCH :query ORDER BY rank LIMIT :limit"
                        ),
                        {"query": fts_query, "limit": 20000},
                    )
                    .mappings()
                    .all()
                )
            except Exception as exc:
                raise Phase7RepositoryError("invalid full-text query") from exc
            all_rows = (
                connection.execute(select(archive_search_documents)).mappings().all()
                if semantic_ranker is not None
                else ()
            )
        documents = tuple(
            SearchDocument(**{key: str(row[key]) for key in SearchDocument.__annotations__})
            for row in all_rows
        )
        keyword_rank = {str(row["event_id"]): index for index, row in enumerate(keyword_rows, 1)}
        semantic = {} if semantic_ranker is None else dict(semantic_ranker.rank(query, documents))
        candidate_ids = set(keyword_rank) | set(semantic)
        fused = sorted(
            candidate_ids,
            key=lambda event_id: (
                -(1 / (60 + keyword_rank[event_id]) if event_id in keyword_rank else 0)
                - (semantic.get(event_id, 0.0) / 60),
                event_id,
            ),
        )
        resolved_page = max(page, 1)
        resolved_page_size = min(max(page_size, 1), 200)
        archive_sort = "PUBLISHED_DESC" if sort == "RELEVANCE" else sort
        filtered = self.query_archive(
            topic=topic,
            tier=tier,
            source_id=source_id,
            tag=tag,
            favorite=favorite,
            read_state=read_state,
            published_from=published_from,
            published_to=published_to,
            minimum_score=minimum_score,
            event_ids=tuple(fused),
            sort=archive_sort,
            page=1 if sort == "RELEVANCE" else resolved_page,
            page_size=20000 if sort == "RELEVANCE" else resolved_page_size,
        )
        if sort == "RELEVANCE":
            active = {item["event_id"]: item for item in filtered["items"]}
            ordered = [active[event_id] for event_id in fused if event_id in active]
            start = (resolved_page - 1) * resolved_page_size
            items = ordered[start : start + resolved_page_size]
            total = len(ordered)
        else:
            items = list(filtered["items"])
            total = int(filtered["total"])
        return {
            "query": query,
            "mode": "HYBRID" if semantic_ranker is not None else "KEYWORD",
            "degraded": semantic_ranker is None,
            "degraded_reason": "SEMANTIC_PROVIDER_NOT_CONFIGURED"
            if semantic_ranker is None
            else None,
            "total": total,
            "page": resolved_page,
            "page_size": resolved_page_size,
            "items": items,
        }

    def list_runs(self, limit: int = 50) -> list[dict[str, Any]]:
        with self.engine.connect() as connection:
            rows = (
                connection.execute(
                    text(
                        "SELECT r.*, COUNT(w.work_item_id) AS work_item_count, "
                        "SUM(CASE WHEN w.status='WAITING_RETRY' THEN 1 ELSE 0 END) AS retry_count "
                        "FROM pipeline_runs r LEFT JOIN pipeline_work_items w ON w.run_id=r.run_id "
                        "GROUP BY r.run_id ORDER BY r.started_at DESC LIMIT :limit"
                    ),
                    {"limit": min(max(limit, 1), 200)},
                )
                .mappings()
                .all()
            )
        return [dict(row) for row in rows]

    def get_run_detail(self, run_id: str) -> dict[str, Any]:
        """Build the operational run read model without exposing raw log payloads."""
        with self.engine.connect() as connection:
            run = (
                connection.execute(
                    text("SELECT * FROM pipeline_runs WHERE run_id=:run_id"), {"run_id": run_id}
                )
                .mappings()
                .first()
            )
            if run is None:
                raise Phase7RepositoryError("run not found")
            work_items = (
                connection.execute(
                    text(
                        "SELECT w.aggregate_version_id, w.stage, w.status, w.updated_at, "
                        "av.canonical_title FROM pipeline_work_items w "
                        "JOIN aggregate_versions av ON av.aggregate_version_id=w.aggregate_version_id "
                        "WHERE w.run_id=:run_id ORDER BY w.updated_at, w.aggregate_version_id"
                    ),
                    {"run_id": run_id},
                )
                .mappings()
                .all()
            )
            event_rows = (
                connection.execute(
                    text(
                        "SELECT event_type, payload_json, created_at FROM telemetry_events "
                        "WHERE run_id=:run_id ORDER BY created_at, telemetry_event_id"
                    ),
                    {"run_id": run_id},
                )
                .mappings()
                .all()
            )

            digest_id: str | None = None
            timeline: list[dict[str, Any]] = []
            source_failures: list[dict[str, Any]] = []
            for row in event_rows:
                payload = json.loads(str(row["payload_json"]))
                event_type = str(row["event_type"])
                if event_type == "daily_digest_generated":
                    digest_id = str(payload.get("digest_id")) if payload.get("digest_id") else None
                if event_type == "source_fetch_finished" and payload.get("status") != "SUCCESS":
                    source_failures.append(
                        {
                            "source_id": payload.get("source_id"),
                            "source_type": payload.get("source_type"),
                            "stage": payload.get("error_stage") or "FETCH",
                            "status": payload.get("status"),
                            "reason": payload.get("failure_reason") or "UNKNOWN_FAILURE",
                            "retry_count": int(payload.get("retry_count") or 0),
                            "occurred_at": str(row["created_at"]),
                        }
                    )
                timeline.append(
                    {
                        "event_type": event_type,
                        "created_at": str(row["created_at"]),
                        "status": payload.get("status"),
                        "error_code": payload.get("error_code"),
                    }
                )

            digest: dict[str, Any] | None = None
            if digest_id is not None:
                digest_row = (
                    connection.execute(
                        text(
                            "SELECT digest_id, report_date, version_no, markdown_path, created_at "
                            "FROM daily_digests WHERE digest_id=:digest_id"
                        ),
                        {"digest_id": digest_id},
                    )
                    .mappings()
                    .first()
                )
                if digest_row is not None:
                    segments = (
                        connection.execute(
                            text(
                                "SELECT segment_id, segment_no, status, attempt_count, error_code, "
                                "updated_at FROM delivery_segments WHERE digest_id=:digest_id "
                                "ORDER BY segment_no"
                            ),
                            {"digest_id": digest_id},
                        )
                        .mappings()
                        .all()
                    )
                    digest = {**dict(digest_row), "segments": [dict(item) for item in segments]}

        retryable = [dict(item) for item in work_items if item["status"] == "WAITING_RETRY"]
        return {
            **dict(run),
            "work_items": [dict(item) for item in work_items],
            "retryable_work_items": retryable,
            "source_failures": source_failures,
            "timeline": timeline,
            "digest": digest,
        }

    def list_retry_work_items(self, run_id: str) -> list[dict[str, str]]:
        with self.engine.connect() as connection:
            rows = (
                connection.execute(
                    text(
                        "SELECT aggregate_version_id, stage FROM pipeline_work_items "
                        "WHERE run_id=:run_id AND status='WAITING_RETRY' "
                        "ORDER BY updated_at, aggregate_version_id"
                    ),
                    {"run_id": run_id},
                )
                .mappings()
                .all()
            )
        return [
            {
                "aggregate_version_id": str(row["aggregate_version_id"]),
                "stage": str(row["stage"]),
            }
            for row in rows
        ]

    def list_feedback(self) -> list[dict[str, Any]]:
        with self.engine.connect() as connection:
            rows = (
                connection.execute(
                    text(
                        "SELECT q.*, cs.aggregate_version_id, cs.config_version AS score_version, "
                        "cs.score_revision, av.canonical_title "
                        "FROM quality_feedback q "
                        "JOIN candidate_scores cs ON cs.score_id=q.score_id "
                        "JOIN aggregate_versions av "
                        "ON av.aggregate_version_id=cs.aggregate_version_id "
                        "ORDER BY q.created_at DESC"
                    )
                )
                .mappings()
                .all()
            )
        result = []
        for row in rows:
            value = dict(row)
            value["content_features"] = json.loads(str(value.pop("content_features_json")))
            result.append(value)
        return result

    def calibration_workbench(self) -> dict[str, Any]:
        """Return the complete read model for the user-controlled calibration UI."""
        with self.engine.connect() as connection:
            active_version = int(
                connection.execute(
                    text("SELECT config_version FROM active_scoring_config WHERE singleton_id=1")
                ).scalar_one()
            )
            configs = (
                connection.execute(
                    text("SELECT * FROM scoring_configs ORDER BY config_version DESC")
                )
                .mappings()
                .all()
            )
            proposals = (
                connection.execute(
                    text(
                        "SELECT p.*, d.decision, d.new_config_version, d.decided_at "
                        "FROM calibration_proposals p LEFT JOIN calibration_decisions d "
                        "ON d.proposal_id=p.proposal_id ORDER BY p.created_at DESC"
                    )
                )
                .mappings()
                .all()
            )
            audits = (
                connection.execute(
                    text("SELECT * FROM scoring_config_audits ORDER BY created_at DESC")
                )
                .mappings()
                .all()
            )
            targets = (
                connection.execute(
                    text(
                        "WITH affected AS ("
                        " SELECT DISTINCT cs.aggregate_version_id FROM quality_feedback q"
                        " JOIN candidate_scores cs ON cs.score_id=q.score_id"
                        "), latest AS ("
                        " SELECT cs.*, ROW_NUMBER() OVER ("
                        "  PARTITION BY cs.aggregate_version_id ORDER BY cs.created_at DESC,"
                        "  cs.config_version DESC, cs.score_revision DESC"
                        " ) AS row_no FROM candidate_scores cs JOIN affected a"
                        " ON a.aggregate_version_id=cs.aggregate_version_id"
                        ") SELECT av.aggregate_version_id, av.canonical_title, l.score_id,"
                        " l.total AS latest_score, l.config_version, l.score_revision, l.created_at,"
                        " (SELECT COUNT(*) FROM candidate_scores history"
                        "  WHERE history.aggregate_version_id=av.aggregate_version_id) AS score_count"
                        " FROM affected a JOIN aggregate_versions av"
                        " ON av.aggregate_version_id=a.aggregate_version_id"
                        " JOIN latest l ON l.aggregate_version_id=a.aggregate_version_id AND l.row_no=1"
                        " ORDER BY av.created_at DESC"
                    )
                )
                .mappings()
                .all()
            )

        config_values = []
        for row in configs:
            value = dict(row)
            value["version"] = int(value.pop("config_version"))
            value["weights"] = json.loads(str(value.pop("weights_json")))
            value["source_overrides"] = json.loads(str(value.pop("source_overrides_json")))
            value["is_active"] = value["version"] == active_version
            config_values.append(value)

        proposal_values = []
        for row in proposals:
            value = dict(row)
            for source, target in (
                ("affected_dimensions_json", "affected_dimensions"),
                ("suggested_weights_json", "suggested_weights"),
                ("suggested_source_overrides_json", "suggested_source_overrides"),
                ("estimated_impact_json", "estimated_impact"),
            ):
                value[target] = json.loads(str(value.pop(source)))
            proposal_values.append(value)

        return {
            "active_version": active_version,
            "configs": config_values,
            "proposals": proposal_values,
            "audits": [dict(row) for row in audits],
            "rescore_targets": [dict(row) for row in targets],
        }

    def save_extension_run(
        self,
        event_id: str,
        query: str,
        *,
        status: str,
        error_code: str | None,
        hits: Sequence[ExternalSearchHit],
        created_at: datetime,
    ) -> dict[str, Any]:
        run_id = str(uuid4())
        now = _iso(created_at)
        with self.engine.begin() as connection:
            connection.execute(
                insert(extension_search_runs).values(
                    search_run_id=run_id,
                    event_id=event_id,
                    query=query,
                    status=status,
                    error_code=error_code,
                    created_at=now,
                )
            )
            result_rows = []
            for hit in hits:
                result_id = str(uuid4())
                safe_url = normalize_url(hit.url)
                connection.execute(
                    insert(extension_search_results).values(
                        result_id=result_id,
                        search_run_id=run_id,
                        title=hit.title,
                        url=safe_url,
                        summary=hit.summary,
                        content=hit.content,
                        source_name=hit.source_name,
                        score=hit.score,
                        formal_event_id=None,
                        created_at=now,
                    )
                )
                result_rows.append(
                    {
                        "result_id": result_id,
                        "title": hit.title,
                        "url": safe_url,
                        "summary": hit.summary,
                        "content": hit.content,
                        "source_name": hit.source_name,
                        "score": hit.score,
                    }
                )
        return {
            "search_run_id": run_id,
            "status": status,
            "error_code": error_code,
            "results": result_rows,
        }

    def get_extension_result(self, result_id: str) -> dict[str, Any]:
        with self.engine.connect() as connection:
            row = (
                connection.execute(
                    select(extension_search_results).where(
                        extension_search_results.c.result_id == result_id
                    )
                )
                .mappings()
                .first()
            )
        if row is None:
            raise Phase7RepositoryError("extension result was not found")
        return dict(row)

    def extension_favorite_outcome(self, result_id: str) -> dict[str, object] | None:
        """Return the persisted response for an already completed favorite request."""

        result = self.get_extension_result(result_id)
        formal_event_id = result["formal_event_id"]
        if formal_event_id is None:
            return None
        with self.engine.connect() as connection:
            formal_version_no = connection.execute(
                select(formalization_links.c.formal_version_no)
                .join(
                    aggregate_versions,
                    aggregate_versions.c.aggregate_version_id
                    == formalization_links.c.aggregate_version_id,
                )
                .join(
                    aggregate_evidence,
                    aggregate_evidence.c.aggregate_version_id
                    == aggregate_versions.c.aggregate_version_id,
                )
                .join(
                    collected_raw_snapshots,
                    collected_raw_snapshots.c.snapshot_id
                    == aggregate_evidence.c.upstream_snapshot_id,
                )
                .where(
                    collected_raw_snapshots.c.external_id == result_id,
                    formalization_links.c.formal_event_id == formal_event_id,
                )
                .order_by(formalization_links.c.formal_version_no.desc())
                .limit(1)
            ).scalar_one_or_none()
        return {
            "event_id": str(formal_event_id),
            "deduplicated": formal_version_no is None or int(formal_version_no) > 1,
        }

    def mark_extension_favorite(self, result_id: str, event_id: str) -> None:
        with self.engine.begin() as connection:
            result = connection.execute(
                update(extension_search_results)
                .where(
                    extension_search_results.c.result_id == result_id,
                    extension_search_results.c.formal_event_id.is_(None),
                )
                .values(formal_event_id=event_id)
            )
        if result.rowcount != 1:
            raise Phase7RepositoryError("extension result was already archived")

    def find_event_by_source_url(self, url: str) -> str | None:
        with self.engine.connect() as connection:
            value = connection.execute(
                text(
                    "SELECT v.event_id FROM evidence ev "
                    "JOIN event_versions v ON v.version_id=ev.version_id "
                    "JOIN events e ON e.event_id=v.event_id AND e.status='READY' "
                    "WHERE ev.url=:url ORDER BY v.version_no DESC LIMIT 1"
                ),
                {"url": url},
            ).scalar_one_or_none()
        return None if value is None else str(value)
