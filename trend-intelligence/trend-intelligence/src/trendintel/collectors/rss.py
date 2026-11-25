"""Generic RSS 2.0 / Atom support shared by the feed-based collectors."""
from __future__ import annotations

from dataclasses import dataclass, field

try:  # defusedxml protects against entity-expansion attacks in untrusted feeds
    from defusedxml import ElementTree as ET
except ImportError:  # pragma: no cover
    from xml.etree import ElementTree as ET  # type: ignore[no-redef]

from ..models import Article
from ..processing.cleaning import parse_timestamp
from .base import BaseCollector, CollectorError


@dataclass
class FeedEntry:
    title: str = ""
    link: str = ""
    summary: str = ""
    published: str | None = None
    extras: dict[str, str] = field(default_factory=dict)
    news_items: list[dict[str, str]] = field(default_factory=list)


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def parse_feed(content: bytes | str) -> list[FeedEntry]:
    """Parse RSS or Atom into ``FeedEntry`` objects, ignoring namespaces."""
    try:
        root = ET.fromstring(content)
    except ET.ParseError as exc:
        raise CollectorError(f"Feed is not valid XML: {exc}") from exc

    entries: list[FeedEntry] = []
    for element in root.iter():
        if _local(element.tag) not in ("item", "entry"):
            continue
        data: dict[str, str] = {}
        news: list[dict[str, str]] = []
        for child in element:
            name = _local(child.tag)
            if name == "link":
                href = child.attrib.get("href") or (child.text or "").strip()
                if href and child.attrib.get("rel", "alternate") == "alternate" and "link" not in data:
                    data["link"] = href
            elif name == "news_item":
                item = {_local(g.tag).replace("news_item_", ""): (g.text or "").strip() for g in child}
                news.append(item)
            else:
                data.setdefault(name, (child.text or "").strip())
        entries.append(
            FeedEntry(
                title=data.get("title", ""),
                link=data.get("link", ""),
                summary=data.get("description") or data.get("summary") or data.get("content") or "",
                published=data.get("pubDate") or data.get("published") or data.get("updated"),
                extras=data,
                news_items=news,
            )
        )
    return entries


class RssCollector(BaseCollector):
    kind = "rss"
    feed_url: str = ""

    def entry_to_article(self, entry: FeedEntry) -> Article | None:
        if not entry.title or not entry.link:
            return None
        return Article(
            source=self.name,
            title=entry.title,
            url=entry.link,
            description=entry.summary,
            published_at=parse_timestamp(entry.published),
            external_id=entry.link,
        )

    def fetch(self) -> list[Article]:
        response = self.http.get(self.feed_url)
        entries = parse_feed(response.content)[: self.settings.rss_limit]
        articles = [a for a in (self.entry_to_article(e) for e in entries) if a is not None]
        if not articles:
            raise CollectorError(f"{self.name}: feed contained no usable entries")
        return articles
