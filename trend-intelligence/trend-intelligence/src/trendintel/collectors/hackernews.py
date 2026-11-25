"""Hacker News front page via the public HN Search (Algolia) API: one request."""
from __future__ import annotations

from ..models import Article
from ..processing.cleaning import parse_timestamp
from .base import BaseCollector, CollectorError


class HackerNewsCollector(BaseCollector):
    name = "Hacker News"
    key = "hackernews"
    kind = "api"
    base_url = "https://news.ycombinator.com"
    api_url = "https://hn.algolia.com/api/v1/search"

    def fetch(self) -> list[Article]:
        payload = self.http.get_json(
            self.api_url, params={"tags": "front_page", "hitsPerPage": self.settings.hn_limit}
        )
        hits = payload.get("hits") if isinstance(payload, dict) else None
        if not isinstance(hits, list):
            raise CollectorError("Unexpected Hacker News API response shape")

        articles: list[Article] = []
        for hit in hits:
            title = hit.get("title") or hit.get("story_title")
            if not title:
                continue
            object_id = str(hit.get("objectID", ""))
            articles.append(
                Article(
                    source=self.name,
                    title=title,
                    url=hit.get("url") or f"{self.base_url}/item?id={object_id}",
                    description=hit.get("story_text") or "",
                    published_at=parse_timestamp(hit.get("created_at_i") or hit.get("created_at")),
                    external_id=object_id or None,
                )
            )
        return articles
