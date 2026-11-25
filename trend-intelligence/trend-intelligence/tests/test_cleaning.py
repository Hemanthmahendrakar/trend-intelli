from datetime import datetime, timedelta, timezone

from trendintel.models import Article
from trendintel.processing.cleaning import (
    canonicalize_url,
    clean_article,
    clean_text,
    hash_title,
    parse_timestamp,
)

NOW = datetime(2025, 1, 10, 12, tzinfo=timezone.utc)


def test_clean_text_strips_html_entities_and_whitespace():
    assert clean_text("<p>Hello&nbsp;<b>World</b> &amp;   friends</p>") == "Hello World & friends"


def test_clean_text_removes_wordpress_footer():
    raw = "<p>Great story. The post Startup raises appeared first on TechCrunch.</p>"
    assert clean_text(raw) == "Great story."


def test_clean_text_truncates():
    assert len(clean_text("word " * 100, max_length=20)) <= 20


def test_clean_text_handles_none():
    assert clean_text(None) == ""


def test_canonicalize_url_removes_tracking_and_normalises():
    url = "HTTP://www.Example.com/path/?utm_source=x&b=2&a=1&fbclid=zzz#frag"
    assert canonicalize_url(url) == "https://example.com/path?a=1&b=2"


def test_canonicalize_url_rejects_garbage():
    assert canonicalize_url("not a url") == ""
    assert canonicalize_url(None) == ""


def test_parse_timestamp_formats():
    expected = datetime(2023, 1, 2, 15, 4, 5, tzinfo=timezone.utc)
    assert parse_timestamp("Mon, 02 Jan 2023 15:04:05 +0000") == expected
    assert parse_timestamp("2023-01-02T15:04:05Z") == expected
    assert parse_timestamp("2023-01-02T20:34:05+05:30") == expected
    assert parse_timestamp(0) == datetime(1970, 1, 1, tzinfo=timezone.utc)
    assert parse_timestamp("2023-01-02 15:04:05") == expected  # naive assumed UTC


def test_parse_timestamp_invalid():
    assert parse_timestamp("garbage") is None
    assert parse_timestamp("") is None
    assert parse_timestamp(None) is None


def test_hash_title_ignores_case_and_punctuation():
    assert hash_title("Hello, World!") == hash_title("hello world")


def test_clean_article_sets_hashes_and_cleans_fields():
    raw = Article(source="S", title="  <b>Big</b> News  ", url="https://www.x.com/a/?utm_medium=z", description="<p>d</p>")
    cleaned = clean_article(raw, NOW)
    assert cleaned is not None
    assert cleaned.title == "Big News"
    assert cleaned.url == "https://x.com/a"
    assert cleaned.description == "d"
    assert cleaned.url_hash and cleaned.content_hash


def test_clean_article_drops_unusable():
    assert clean_article(Article(source="S", title="", url="https://x.com"), NOW) is None
    assert clean_article(Article(source="S", title="t", url="ftp://x.com/a"), NOW) is None
    assert clean_article(Article(source="S", title="t", url=""), NOW) is None


def test_clean_article_ignores_future_publication_dates():
    raw = Article(source="S", title="t", url="https://x.com/a", published_at=NOW + timedelta(days=3))
    assert clean_article(raw, NOW).published_at is None
