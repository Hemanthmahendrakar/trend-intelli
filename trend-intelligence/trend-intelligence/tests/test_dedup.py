from datetime import datetime, timezone

from trendintel.models import Article
from trendintel.processing.prepare import prepare_articles

NOW = datetime(2025, 1, 10, 12, tzinfo=timezone.utc)


def art(source, title, url, description=""):
    return Article(source=source, title=title, url=url, description=description)


def test_same_url_same_source_is_duplicate():
    result = prepare_articles([art("HN", "A story", "https://x.com/a?utm_source=1"), art("HN", "Other title", "https://www.x.com/a/")], NOW)
    assert len(result) == 1


def test_same_title_same_source_is_duplicate():
    result = prepare_articles([art("HN", "Big News!", "https://x.com/1"), art("HN", "big news", "https://x.com/2")], NOW)
    assert len(result) == 1


def test_same_url_different_sources_is_kept():
    result = prepare_articles([art("HN", "A story", "https://x.com/a"), art("Reddit", "A story", "https://x.com/a")], NOW)
    assert {a.source for a in result} == {"HN", "Reddit"}


def test_duplicate_keeps_richer_description():
    result = prepare_articles([art("HN", "A story", "https://x.com/a"), art("HN", "A story", "https://x.com/a", "Longer text")], NOW)
    assert len(result) == 1 and result[0].description == "Longer text"
