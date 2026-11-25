"""Duplicate removal.

Design note: duplicates are removed *within a source* only. The same story
appearing on Hacker News and on TechCrunch is not a duplicate for our purposes:
it is exactly the cross-source signal the "independent sources" part of the
trend score is meant to measure.
"""
from __future__ import annotations

import logging
from typing import Iterable

from ..models import Article

logger = logging.getLogger(__name__)


def deduplicate(articles: Iterable[Article]) -> list[Article]:
    """Drop articles repeating a (source, canonical URL) or (source, normalised title)."""
    by_url: dict[tuple[str, str], Article] = {}
    by_content: dict[tuple[str, str], Article] = {}
    unique: list[Article] = []
    dropped = 0
    for article in articles:
        url_key = (article.source, article.url_hash or article.url)
        content_key = (article.source, article.content_hash or article.title.lower())
        existing = by_url.get(url_key) or by_content.get(content_key)
        if existing is not None:
            dropped += 1
            if len(article.description) > len(existing.description):
                existing.description = article.description  # keep the richer copy
            continue
        by_url[url_key] = article
        by_content[content_key] = article
        unique.append(article)
    if dropped:
        logger.info("Removed %d duplicate article(s)", dropped)
    return unique
