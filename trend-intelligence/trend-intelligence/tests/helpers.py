"""Shared test helpers."""
from datetime import datetime, timedelta, timezone

from trendintel.models import Article

NOW = datetime(2025, 1, 10, 12, 0, tzinfo=timezone.utc)


def make_article(i: int, source: str, hours_ago: float, title: str = "", description: str = "", collected_hours_ago: float | None = None) -> Article:
    when = NOW - timedelta(hours=hours_ago)
    collected = NOW - timedelta(hours=collected_hours_ago if collected_hours_ago is not None else hours_ago)
    return Article(
        id=i,
        source=source,
        title=title or f"title {i}",
        description=description,
        url=f"https://example.com/{i}",
        published_at=when,
        collected_at=collected,
    )
