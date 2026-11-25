"""Analysis stage: articles -> keywords -> topics -> scores (pure, no I/O)."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Sequence

from ..models import Article
from ..processing.keywords import extract_article_terms
from ..processing.topics import build_topics
from .scoring import ScoringConfig, TopicActivity, TrendScore, score_topics

logger = logging.getLogger(__name__)


def analyze_articles(
    articles: Sequence[Article],
    now: datetime,
    cfg: ScoringConfig,
    first_collected_at: datetime | None = None,
) -> list[TrendScore]:
    """Score topics found in ``articles`` (should span at least two windows).

    ``first_collected_at`` is when the system first stored any article; it decides
    whether enough history exists for growth to be meaningful.
    """
    current_start = now - timedelta(hours=cfg.window_hours)
    previous_start = now - timedelta(hours=2 * cfg.window_hours)
    relevant = [a for a in articles if a.effective_time > previous_start]
    if not relevant:
        return []

    article_terms = [extract_article_terms(a) for a in relevant]
    topics = build_topics(article_terms, min_df=cfg.min_mentions)
    activities = [
        TopicActivity(slug=t.slug, label=t.label, articles=[relevant[i] for i in t.article_indices]) for t in topics
    ]

    total_sources = len({a.source for a in relevant if a.effective_time > current_start})
    first = first_collected_at or min(a.collected_at for a in relevant)
    history_available = (now - first) >= timedelta(hours=cfg.min_history_hours)
    logger.info(
        "Analysing %d articles -> %d topics (history_available=%s)", len(relevant), len(topics), history_available
    )
    return score_topics(activities, now, cfg, total_sources, history_available)
