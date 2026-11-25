"""Plain data objects passed between the collection, processing and scoring layers."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class Article:
    """One piece of public content (post, story, search trend) from a source."""

    source: str
    title: str
    url: str
    description: str = ""
    published_at: datetime | None = None
    external_id: str | None = None
    collected_at: datetime = field(default_factory=utcnow)
    # Filled by processing.cleaning.clean_article
    url_hash: str | None = None
    content_hash: str | None = None
    # Filled when loaded from the database
    id: int | None = None

    @property
    def effective_time(self) -> datetime:
        """Time used for windowing: publication time, else when we collected it."""
        return self.published_at or self.collected_at
