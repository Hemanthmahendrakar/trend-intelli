"""Read-only REST API over the stored trend data.

Purpose: decouples the dashboard (or any other client) from the database. The
data is written only by the pipeline; the API never mutates anything.
Run with: ``uvicorn trendintel.api.main:app``  (docs at /docs).
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Query
from pydantic import BaseModel

from ..config import get_settings
from ..db.connection import get_engine
from ..db.repository import Repository
from ..logging_setup import setup_logging

logger = logging.getLogger(__name__)


class TrendOut(BaseModel):
    topic_id: int
    slug: str
    label: str
    computed_at: datetime
    window_hours: float
    mention_count: int
    prev_mention_count: int
    source_count: int
    sources: list[str]
    frequency_score: float
    recency_score: float
    growth_score: float
    diversity_score: float
    total_score: float
    is_emerging: bool
    history_available: bool


class ArticleOut(BaseModel):
    id: int
    title: str
    url: str
    source: str
    published_at: datetime | None = None
    collected_at: datetime


class HistoryPoint(BaseModel):
    topic_id: int
    label: str
    computed_at: datetime
    total_score: float
    mention_count: int
    source_count: int


class PlatformTopic(BaseModel):
    source: str
    topic_id: int
    label: str
    mentions: int


def get_repository() -> Repository:
    settings = get_settings()
    if not settings.database_url:
        raise HTTPException(status_code=503, detail="DATABASE_URL is not configured")
    return Repository(get_engine(settings.database_url))


def create_app() -> FastAPI:
    settings = get_settings()
    setup_logging(settings.log_level, settings.log_file)
    app = FastAPI(title="Internet Trend Intelligence API", version="0.1.0")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/trends", response_model=list[TrendOut])
    def trends(limit: int = Query(10, ge=1, le=100), repo: Repository = Depends(get_repository)) -> Any:
        """Top topics from the most recent analysis snapshot."""
        return repo.latest_trends(limit=limit)

    @app.get("/trends/emerging", response_model=list[TrendOut])
    def emerging(limit: int = Query(10, ge=1, le=100), repo: Repository = Depends(get_repository)) -> Any:
        """Topics with no mentions in the previous window but several in the current one."""
        return repo.latest_trends(limit=limit, emerging_only=True)

    @app.get("/trends/history", response_model=list[HistoryPoint])
    def history(
        topic_ids: list[int] = Query(...),
        days: int = Query(7, ge=1, le=90),
        repo: Repository = Depends(get_repository),
    ) -> Any:
        """Score and mention history for the given topics."""
        return repo.trend_history(topic_ids, days=days)

    @app.get("/topics/{topic_id}/articles", response_model=list[ArticleOut])
    def topic_articles(
        topic_id: int, limit: int = Query(50, ge=1, le=200), repo: Repository = Depends(get_repository)
    ) -> Any:
        """Articles (title + clickable URL + source) linked to a topic."""
        return repo.topic_articles(topic_id, limit=limit)

    @app.get("/platforms/topics", response_model=list[PlatformTopic])
    def platform_topics(
        hours: int = Query(24, ge=1, le=168),
        per_source: int = Query(5, ge=1, le=20),
        repo: Repository = Depends(get_repository),
    ) -> Any:
        """What each platform is discussing among the currently trending topics."""
        return repo.platform_topics(hours=hours, per_source=per_source)

    @app.get("/sources")
    def sources(repo: Repository = Depends(get_repository)) -> Any:
        return repo.list_sources()

    @app.get("/runs")
    def runs(limit: int = Query(30, ge=1, le=200), repo: Repository = Depends(get_repository)) -> Any:
        """Recent collection runs (status, counts, errors) for health monitoring."""
        return repo.recent_runs(limit=limit)

    return app


app = create_app()
