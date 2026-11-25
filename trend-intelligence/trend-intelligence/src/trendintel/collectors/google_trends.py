"""Google Trends "Trending now" via Google's public RSS feed.

Each feed item is a trending *search term* with a few related news headlines.
We store the term as the title and the headlines as the description so keyword
extraction sees the surrounding context. The feed format is not a documented
API and may change; failures are handled like any other collector failure.
"""
from __future__ import annotations

from urllib.parse import quote_plus

from ..models import Article
from ..processing.cleaning import parse_timestamp
from .rss import FeedEntry, RssCollector


class GoogleTrendsCollector(RssCollector):
    name = "Google Trends"
    key = "google_trends"
    base_url = "https://trends.google.com"

    @property
    def feed_url(self) -> str:  # type: ignore[override]
        return f"{self.base_url}/trending/rss?geo={self.settings.google_trends_geo}"

    def entry_to_article(self, entry: FeedEntry) -> Article | None:
        term = entry.title.strip()
        if not term:
            return None
        headlines = [n["title"] for n in entry.news_items if n.get("title")]
        geo = self.settings.google_trends_geo
        return Article(
            source=self.name,
            title=term,
            url=f"{self.base_url}/trends/explore?q={quote_plus(term)}&geo={geo}",
            description=". ".join(headlines[:2]),
            published_at=parse_timestamp(entry.published),
            external_id=term.lower(),
        )
