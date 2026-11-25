"""Data-access layer.

Purpose: all SQL lives here. The rest of the code base talks to this class and
never builds queries itself, which keeps the pipeline testable (swap in a fake
repository) and the SQL reviewable in one place.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from importlib import resources
from typing import Any, Sequence

from sqlalchemy import text
from sqlalchemy.engine import Engine

from ..models import Article
from ..trends.scoring import TrendScore

logger = logging.getLogger(__name__)

_TREND_COLUMNS = """
    t.id AS topic_id, t.slug, t.label, ts.computed_at, ts.window_hours, ts.mention_count,
    ts.prev_mention_count, ts.source_count, ts.sources, ts.frequency_score, ts.recency_score,
    ts.growth_score, ts.diversity_score, ts.total_score, ts.is_emerging, ts.history_available
"""
_LATEST = "ts.computed_at = (SELECT MAX(computed_at) FROM trend_scores)"


class Repository:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    # ------------------------------------------------------------------ schema
    def init_schema(self) -> None:
        sql = resources.files("trendintel.db").joinpath("schema.sql").read_text(encoding="utf-8")
        with self.engine.begin() as conn:
            conn.exec_driver_sql(sql)
        logger.info("Database schema is up to date")

    # --------------------------------------------------------------- collection
    def upsert_source(self, name: str, kind: str, base_url: str) -> int:
        with self.engine.begin() as conn:
            return conn.execute(
                text(
                    """INSERT INTO sources (name, kind, base_url) VALUES (:name, :kind, :base_url)
                       ON CONFLICT (name) DO UPDATE SET kind = EXCLUDED.kind, base_url = EXCLUDED.base_url
                       RETURNING id"""
                ),
                {"name": name, "kind": kind, "base_url": base_url},
            ).scalar_one()

    def start_run(self, source_id: int) -> int:
        with self.engine.begin() as conn:
            return conn.execute(
                text("INSERT INTO collection_runs (source_id) VALUES (:sid) RETURNING id"), {"sid": source_id}
            ).scalar_one()

    def finish_run(self, run_id: int, status: str, fetched: int = 0, inserted: int = 0, error: str | None = None) -> None:
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """UPDATE collection_runs SET finished_at = now(), status = :status,
                       items_fetched = :fetched, items_inserted = :inserted, error_message = :error
                       WHERE id = :id"""
                ),
                {"id": run_id, "status": status, "fetched": fetched, "inserted": inserted, "error": (error or None)},
            )

    def insert_articles(self, source_id: int, run_id: int, articles: Sequence[Article]) -> int:
        """Insert articles, silently skipping ones already stored. Returns the number newly inserted."""
        sql = text(
            """INSERT INTO articles (source_id, run_id, external_id, title, description, url,
                                     url_hash, content_hash, published_at, collected_at)
               VALUES (:source_id, :run_id, :external_id, :title, :description, :url,
                       :url_hash, :content_hash, :published_at, :collected_at)
               ON CONFLICT DO NOTHING"""
        )
        inserted = 0
        with self.engine.begin() as conn:
            for a in articles:
                result = conn.execute(
                    sql,
                    {
                        "source_id": source_id,
                        "run_id": run_id,
                        "external_id": a.external_id,
                        "title": a.title,
                        "description": a.description,
                        "url": a.url,
                        "url_hash": a.url_hash,
                        "content_hash": a.content_hash,
                        "published_at": a.published_at,
                        "collected_at": a.collected_at,
                    },
                )
                inserted += result.rowcount or 0
        return inserted

    # ----------------------------------------------------------------- analysis
    def fetch_articles_since(self, since: datetime) -> list[Article]:
        with self.engine.connect() as conn:
            rows = conn.execute(
                text(
                    """SELECT a.id, s.name AS source, a.external_id, a.title, a.description, a.url,
                              a.published_at, a.collected_at
                       FROM articles a JOIN sources s ON s.id = a.source_id
                       WHERE COALESCE(a.published_at, a.collected_at) >= :since
                       ORDER BY COALESCE(a.published_at, a.collected_at) DESC"""
                ),
                {"since": since},
            ).mappings()
            return [Article(**dict(row)) for row in rows]

    def first_collected_at(self) -> datetime | None:
        with self.engine.connect() as conn:
            return conn.execute(text("SELECT MIN(collected_at) FROM articles")).scalar_one()

    def save_trend_snapshot(self, scores: Sequence[TrendScore], computed_at: datetime) -> None:
        """Persist topics, article links and one trend_scores row per topic, atomically."""
        with self.engine.begin() as conn:
            for score in scores:
                topic_id = conn.execute(
                    text(
                        """INSERT INTO topics (slug, label, first_seen_at, last_seen_at)
                           VALUES (:slug, :label, :ts, :ts)
                           ON CONFLICT (slug) DO UPDATE SET label = EXCLUDED.label, last_seen_at = EXCLUDED.last_seen_at
                           RETURNING id"""
                    ),
                    {"slug": score.slug, "label": score.label, "ts": computed_at},
                ).scalar_one()
                conn.execute(
                    text(
                        """INSERT INTO trend_scores (topic_id, computed_at, window_hours, mention_count,
                               prev_mention_count, source_count, sources, frequency_score, recency_score,
                               growth_score, diversity_score, total_score, is_emerging, history_available)
                           VALUES (:topic_id, :computed_at, :window_hours, :mention_count, :prev_mention_count,
                               :source_count, CAST(:sources AS JSONB), :frequency_score, :recency_score,
                               :growth_score, :diversity_score, :total_score, :is_emerging, :history_available)
                           ON CONFLICT (topic_id, computed_at) DO NOTHING"""
                    ),
                    {
                        "topic_id": topic_id,
                        "computed_at": computed_at,
                        "window_hours": score.window_hours,
                        "mention_count": score.mention_count,
                        "prev_mention_count": score.prev_mention_count,
                        "source_count": score.source_count,
                        "sources": json.dumps(score.sources),
                        "frequency_score": score.frequency_score,
                        "recency_score": score.recency_score,
                        "growth_score": score.growth_score,
                        "diversity_score": score.diversity_score,
                        "total_score": score.total_score,
                        "is_emerging": score.is_emerging,
                        "history_available": score.history_available,
                    },
                )
                links = [{"a": a.id, "t": topic_id} for a in score.articles if a.id is not None]
                if links:
                    conn.execute(
                        text("INSERT INTO article_topics (article_id, topic_id) VALUES (:a, :t) ON CONFLICT DO NOTHING"),
                        links,
                    )
        logger.info("Saved trend snapshot with %d topics", len(scores))

    # ------------------------------------------------------------------ queries
    def _rows(self, sql: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        with self.engine.connect() as conn:
            return [dict(r) for r in conn.execute(text(sql), params or {}).mappings()]

    def latest_trends(self, limit: int = 10, emerging_only: bool = False) -> list[dict[str, Any]]:
        where = f"{_LATEST}" + (" AND ts.is_emerging" if emerging_only else "")
        order = "ts.mention_count DESC, ts.total_score DESC" if emerging_only else "ts.total_score DESC"
        return self._rows(
            f"SELECT {_TREND_COLUMNS} FROM trend_scores ts JOIN topics t ON t.id = ts.topic_id "
            f"WHERE {where} ORDER BY {order} LIMIT :limit",
            {"limit": limit},
        )

    def topic_articles(self, topic_id: int, limit: int = 50) -> list[dict[str, Any]]:
        return self._rows(
            """SELECT a.id, a.title, a.url, s.name AS source, a.published_at, a.collected_at
               FROM article_topics atp
               JOIN articles a ON a.id = atp.article_id
               JOIN sources s ON s.id = a.source_id
               WHERE atp.topic_id = :tid
               ORDER BY COALESCE(a.published_at, a.collected_at) DESC LIMIT :limit""",
            {"tid": topic_id, "limit": limit},
        )

    def trend_history(self, topic_ids: Sequence[int], days: int = 7) -> list[dict[str, Any]]:
        since = datetime.now(timezone.utc) - timedelta(days=days)
        return self._rows(
            """SELECT t.id AS topic_id, t.label, ts.computed_at, ts.total_score, ts.mention_count, ts.source_count
               FROM trend_scores ts JOIN topics t ON t.id = ts.topic_id
               WHERE ts.topic_id = ANY(:ids) AND ts.computed_at >= :since
               ORDER BY ts.computed_at""",
            {"ids": list(topic_ids), "since": since},
        )

    def platform_topics(self, hours: int = 24, per_source: int = 5) -> list[dict[str, Any]]:
        since = datetime.now(timezone.utc) - timedelta(hours=hours)
        rows = self._rows(
            f"""SELECT s.name AS source, t.id AS topic_id, t.label, COUNT(*) AS mentions
                FROM article_topics atp
                JOIN articles a ON a.id = atp.article_id
                JOIN sources s ON s.id = a.source_id
                JOIN topics t ON t.id = atp.topic_id
                WHERE COALESCE(a.published_at, a.collected_at) >= :since
                  AND t.id IN (SELECT ts.topic_id FROM trend_scores ts WHERE {_LATEST})
                GROUP BY s.name, t.id, t.label
                ORDER BY s.name, mentions DESC""",
            {"since": since},
        )
        kept: list[dict[str, Any]] = []
        counts: dict[str, int] = {}
        for row in rows:
            counts[row["source"]] = counts.get(row["source"], 0) + 1
            if counts[row["source"]] <= per_source:
                kept.append(row)
        return kept

    def list_sources(self) -> list[dict[str, Any]]:
        return self._rows(
            """SELECT s.id, s.name, s.kind, s.base_url,
                      (SELECT COUNT(*) FROM articles a WHERE a.source_id = s.id) AS article_count,
                      (SELECT MAX(r.finished_at) FROM collection_runs r
                        WHERE r.source_id = s.id AND r.status = 'success') AS last_success_at
               FROM sources s ORDER BY s.name"""
        )

    def recent_runs(self, limit: int = 30) -> list[dict[str, Any]]:
        return self._rows(
            """SELECT r.id, s.name AS source, r.started_at, r.finished_at, r.status,
                      r.items_fetched, r.items_inserted, r.error_message
               FROM collection_runs r JOIN sources s ON s.id = r.source_id
               ORDER BY r.started_at DESC LIMIT :limit""",
            {"limit": limit},
        )
