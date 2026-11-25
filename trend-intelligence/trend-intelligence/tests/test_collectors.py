from dataclasses import replace
from datetime import datetime, timezone

import pytest

from trendintel.collectors import build_collectors
from trendintel.collectors.base import CollectorConfigError, CollectorError
from trendintel.collectors.google_trends import GoogleTrendsCollector
from trendintel.collectors.hackernews import HackerNewsCollector
from trendintel.collectors.producthunt import ProductHuntCollector
from trendintel.collectors.reddit import RedditCollector
from trendintel.collectors.rss import parse_feed
from trendintel.collectors.techcrunch import TechCrunchCollector
from trendintel.config import Settings

SETTINGS = Settings()

TECHCRUNCH_XML = b"""<?xml version="1.0"?><rss version="2.0"><channel><title>TC</title>
<item><title>Startup X raises $10M</title><link>https://techcrunch.com/2025/01/01/x/</link>
<pubDate>Wed, 01 Jan 2025 10:00:00 +0000</pubDate>
<description><![CDATA[<p>Great news. The post Startup X raises appeared first on TechCrunch.</p>]]></description></item>
<item><title>No link here</title></item></channel></rss>"""

PRODUCT_HUNT_XML = b"""<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>CoolApp</title>
<link rel="alternate" type="text/html" href="https://www.producthunt.com/posts/coolapp"/>
<published>2025-01-01T08:00:00-08:00</published><content type="html">&lt;p&gt;Tagline here&lt;/p&gt;</content></entry></feed>"""

GOOGLE_XML = b"""<rss xmlns:ht="https://trends.google.com/trending/rss" version="2.0"><channel><item>
<title>taylor swift</title><ht:approx_traffic>500K+</ht:approx_traffic>
<pubDate>Wed, 01 Jan 2025 10:00:00 -0800</pubDate>
<ht:news_item><ht:news_item_title>Swift announces tour</ht:news_item_title><ht:news_item_url>https://news.example.com/a</ht:news_item_url></ht:news_item>
</item></channel></rss>"""


class FakeResponse:
    def __init__(self, content=b""):
        self.content = content


class FakeHttp:
    def __init__(self, content=b"", json_payload=None, post_payload=None):
        self.content, self.json_payload, self.post_payload = content, json_payload, post_payload
        self.calls = []

    def get(self, url, **kw):
        self.calls.append(("get", url, kw))
        return FakeResponse(self.content)

    def get_json(self, url, **kw):
        self.calls.append(("get_json", url, kw))
        return self.json_payload

    def post_json(self, url, **kw):
        self.calls.append(("post_json", url, kw))
        return self.post_payload


def test_parse_feed_rss_and_atom():
    rss = parse_feed(TECHCRUNCH_XML)
    assert rss[0].title == "Startup X raises $10M" and rss[0].link.endswith("/x/")
    atom = parse_feed(PRODUCT_HUNT_XML)
    assert atom[0].link == "https://www.producthunt.com/posts/coolapp"
    assert atom[0].summary == "<p>Tagline here</p>"


def test_parse_feed_invalid_xml():
    with pytest.raises(CollectorError):
        parse_feed(b"<not xml")


def test_techcrunch_collector():
    articles = TechCrunchCollector(FakeHttp(TECHCRUNCH_XML), SETTINGS).fetch()
    assert len(articles) == 1  # entry without link skipped
    a = articles[0]
    assert a.source == "TechCrunch" and a.title.startswith("Startup X")
    assert a.published_at == datetime(2025, 1, 1, 10, tzinfo=timezone.utc)


def test_producthunt_collector_normalises_timezone():
    a = ProductHuntCollector(FakeHttp(PRODUCT_HUNT_XML), SETTINGS).fetch()[0]
    assert a.published_at == datetime(2025, 1, 1, 16, tzinfo=timezone.utc)


def test_google_trends_collector():
    http = FakeHttp(GOOGLE_XML)
    a = GoogleTrendsCollector(http, SETTINGS).fetch()[0]
    assert a.title == "taylor swift"
    assert "q=taylor+swift" in a.url
    assert a.description == "Swift announces tour"
    assert http.calls[0][1].endswith("geo=US")


def test_empty_feed_raises():
    with pytest.raises(CollectorError):
        TechCrunchCollector(FakeHttp(b"<rss><channel/></rss>"), SETTINGS).fetch()


def test_hackernews_collector():
    payload = {
        "hits": [
            {"objectID": "1", "title": "Show: thing", "url": "https://a.com/x", "created_at_i": 1735725600},
            {"objectID": "2", "title": "Ask: question", "url": None, "story_text": "<p>body</p>"},
            {"objectID": "3", "title": None},
        ]
    }
    articles = HackerNewsCollector(FakeHttp(json_payload=payload), SETTINGS).fetch()
    assert len(articles) == 2
    assert articles[1].url == "https://news.ycombinator.com/item?id=2"
    assert articles[0].published_at == datetime.fromtimestamp(1735725600, tz=timezone.utc)


def test_hackernews_bad_shape():
    with pytest.raises(CollectorError):
        HackerNewsCollector(FakeHttp(json_payload={"oops": 1}), SETTINGS).fetch()


def test_reddit_requires_credentials():
    with pytest.raises(CollectorConfigError):
        RedditCollector(FakeHttp(), SETTINGS).fetch()


def test_reddit_collector_filters_posts():
    settings = replace(SETTINGS, reddit_client_id="id", reddit_client_secret="secret")
    listing = {
        "data": {
            "children": [
                {"data": {"title": "Link post", "url": "https://news.com/a", "permalink": "/r/x/1", "created_utc": 1735725600, "id": "1"}},
                {"data": {"title": "Self post", "is_self": True, "url": "https://reddit.com/x", "permalink": "/r/x/2", "selftext": "body", "id": "2"}},
                {"data": {"title": "Pinned", "stickied": True, "permalink": "/r/x/3"}},
                {"data": {"title": "NSFW", "over_18": True, "permalink": "/r/x/4"}},
            ]
        }
    }
    http = FakeHttp(json_payload=listing, post_payload={"access_token": "tok"})
    articles = RedditCollector(http, settings).fetch()
    assert [a.title for a in articles] == ["Link post", "Self post"]
    assert articles[0].url == "https://news.com/a"
    assert articles[1].url == "https://www.reddit.com/r/x/2"
    get_call = [c for c in http.calls if c[0] == "get_json"][0]
    assert get_call[2]["headers"]["Authorization"] == "bearer tok"


def test_reddit_missing_token():
    settings = replace(SETTINGS, reddit_client_id="id", reddit_client_secret="secret")
    with pytest.raises(CollectorError):
        RedditCollector(FakeHttp(post_payload={}), settings).fetch()


def test_build_collectors_ignores_unknown_names():
    collectors = build_collectors(SETTINGS, FakeHttp(), ["hackernews", "nope"])
    assert [c.key for c in collectors] == ["hackernews"]
