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
from ai_intel.infrastructure.db.schema import (
    archive_search_documents,
    extension_search_results,
    extension_search_runs,
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
        return {
            "schedule_time": str(row["schedule_time"]),
            "selection_threshold": float(row["selection_threshold"]),
            "tier_caps": json.loads(str(row["tier_caps_json"])),
            "topic_order": json.loads(str(row["topic_order_json"])),
            "default_sort": str(row["default_sort"]),
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
        include_trashed: bool = False,
        published_from: date | None = None,
        published_to: date | None = None,
        event_ids: Sequence[str] | None = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        conditions: list[str] = []
        params: dict[str, object] = {"limit": min(max(limit, 1), 20000)}
        if topic:
            conditions.append("primary_topic = :topic")
            params["topic"] = topic
        if tier:
            conditions.append("tier = :tier")
            params["tier"] = tier
        if favorite is not None:
            conditions.append("favorite = :favorite")
            params["favorite"] = favorite
        if unread is not None:
            conditions.append("read_state = :read_state")
            params["read_state"] = "UNREAD" if unread else "READ"
        if published_from is not None:
            conditions.append("date(published_at) >= :published_from")
            params["published_from"] = published_from.isoformat()
        if published_to is not None:
            conditions.append("date(published_at) <= :published_to")
            params["published_to"] = published_to.isoformat()
        if event_ids is not None:
            if not event_ids:
                return []
            placeholders = []
            for index, event_id in enumerate(event_ids):
                key = f"event_id_{index}"
                placeholders.append(f":{key}")
                params[key] = event_id
            conditions.append(f"event_id IN ({', '.join(placeholders)})")
        where = "" if not conditions else " WHERE " + " AND ".join(conditions)
        sql = f"SELECT * FROM ({self._archive_sql(include_trashed=include_trashed)}) archive{where} ORDER BY pinned DESC, published_at DESC, event_id LIMIT :limit"
        with self.engine.connect() as connection:
            rows = connection.execute(text(sql), params).mappings().all()
        return [self._archive_item(dict(row)) for row in rows]

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
            limit=200,
        )
        return {
            "report_date": report_date.isoformat(),
            "window_start": start.isoformat(),
            "total_count": int(summary["total_count"] or 0),
            "items": items,
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
            "latest_run": None if latest_run is None else dict(latest_run),
            "data_complete": True,
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
                   p.key_conclusions_json, p.pm_value, p.tags_json
            FROM event_versions v
            LEFT JOIN formalization_links f ON f.formal_event_id=v.event_id AND f.formal_version_no=v.version_no
            LEFT JOIN ai_processing_results p ON p.aggregate_version_id=f.aggregate_version_id
            WHERE v.event_id=:event_id ORDER BY v.version_no DESC
            """
        )
        evidence_sql = text(
            """
            SELECT v.version_no, ev.evidence_id, ev.source_id, ev.url, ev.published_at,
                   ev.viewpoint
            FROM event_versions v JOIN evidence ev ON ev.version_id=v.version_id
            WHERE v.event_id=:event_id ORDER BY v.version_no DESC, ev.source_id, ev.url
            """
        )
        idea_sql = text(
            """
            SELECT ti.title, ti.outline_json, ti.hook, ti.support_evidence_ids_json
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
            for key in ("key_conclusions_json", "tags_json"):
                raw = version.pop(key)
                version[key.removesuffix("_json")] = [] if raw is None else json.loads(str(raw))
            version["evidence"] = [
                value for value in evidence_rows if value["version_no"] == version["version_no"]
            ]
        item["versions"] = versions
        item["topic_idea"] = (
            None
            if idea is None
            else {
                "title": str(idea["title"]),
                "outline": json.loads(str(idea["outline_json"])),
                "hook": str(idea["hook"]),
                "support_evidence_ids": json.loads(str(idea["support_evidence_ids_json"])),
            }
        )
        return item

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
        self, query: str, *, semantic_ranker: SemanticRanker | None = None, limit: int = 50
    ) -> dict[str, Any]:
        query = query.strip()
        if not query:
            return {
                "query": "",
                "mode": "KEYWORD",
                "degraded": semantic_ranker is None,
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
                        {"query": fts_query, "limit": min(max(limit, 1), 200)},
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
        )[:limit]
        active = {
            item["event_id"]: item
            for item in self.list_archive(event_ids=tuple(fused), limit=max(len(fused), 1))
        }
        items = [active[event_id] for event_id in fused if event_id in active]
        return {
            "query": query,
            "mode": "HYBRID" if semantic_ranker is not None else "KEYWORD",
            "degraded": semantic_ranker is None,
            "degraded_reason": "SEMANTIC_PROVIDER_NOT_CONFIGURED"
            if semantic_ranker is None
            else None,
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
                connection.execute(text("SELECT * FROM quality_feedback ORDER BY created_at DESC"))
                .mappings()
                .all()
            )
        return [dict(row) for row in rows]

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
                connection.execute(
                    insert(extension_search_results).values(
                        result_id=result_id,
                        search_run_id=run_id,
                        title=hit.title,
                        url=hit.url,
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
                        "url": hit.url,
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
