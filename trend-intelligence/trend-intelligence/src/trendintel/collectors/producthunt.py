"""Product Hunt via its public Atom feed.

If you later obtain Product Hunt API access (GraphQL, token in an env var) you
can replace ``feed_url`` handling with an API collector without touching the
rest of the system.
"""
from .rss import RssCollector


class ProductHuntCollector(RssCollector):
    name = "Product Hunt"
    key = "producthunt"
    base_url = "https://www.producthunt.com"
    feed_url = "https://www.producthunt.com/feed"
