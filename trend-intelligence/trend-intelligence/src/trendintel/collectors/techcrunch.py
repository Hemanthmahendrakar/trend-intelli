"""TechCrunch via its public RSS feed (headline + excerpt + link only)."""
from .rss import RssCollector


class TechCrunchCollector(RssCollector):
    name = "TechCrunch"
    key = "techcrunch"
    base_url = "https://techcrunch.com"
    feed_url = "https://techcrunch.com/feed/"
