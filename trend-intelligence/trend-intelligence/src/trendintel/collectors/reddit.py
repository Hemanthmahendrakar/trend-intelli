"""Reddit via the official OAuth API (application-only auth).

Requires REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET. Without them the collector
raises ``CollectorConfigError`` and the pipeline records the run as "skipped".
Use of Reddit data is governed by Reddit's Data API Terms; review them before
any commercial use.
"""
from __future__ import annotations

from ..models import Article
from ..processing.cleaning import parse_timestamp
from .base import BaseCollector, CollectorConfigError, CollectorError

TOKEN_URL = "https://www.reddit.com/api/v1/access_token"
API_URL = "https://oauth.reddit.com"


class RedditCollector(BaseCollector):
    name = "Reddit"
    key = "reddit"
    kind = "api"
    base_url = "https://www.reddit.com"

    def _get_token(self) -> str:
        s = self.settings
        if not (s.reddit_client_id and s.reddit_client_secret):
            raise CollectorConfigError("REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET not set; skipping Reddit")
        payload = self.http.post_json(
            TOKEN_URL,
            auth=(s.reddit_client_id, s.reddit_client_secret),
            data={"grant_type": "client_credentials"},
            headers={"User-Agent": s.reddit_user_agent},
        )
        token = payload.get("access_token") if isinstance(payload, dict) else None
        if not token:
            raise CollectorError("Reddit did not return an access token")
        return token

    def fetch(self) -> list[Article]:
        token = self._get_token()
        s = self.settings
        listing = self.http.get_json(
            f"{API_URL}/r/{'+'.join(s.reddit_subreddits)}/hot",
            params={"limit": s.reddit_limit, "raw_json": 1},
            headers={"Authorization": f"bearer {token}", "User-Agent": s.reddit_user_agent},
        )
        try:
            children = listing["data"]["children"]
        except (KeyError, TypeError) as exc:
            raise CollectorError("Unexpected Reddit listing response shape") from exc

        articles: list[Article] = []
        for child in children:
            post = child.get("data", {})
            if post.get("stickied") or post.get("over_18") or not post.get("title"):
                continue
            permalink = f"{self.base_url}{post.get('permalink', '')}"
            url = permalink if post.get("is_self") else (post.get("url") or permalink)
            articles.append(
                Article(
                    source=self.name,
                    title=post["title"],
                    url=url,
                    description=post.get("selftext", "")[:500],
                    published_at=parse_timestamp(post.get("created_utc")),
                    external_id=post.get("id"),
                )
            )
        return articles
