from datetime import datetime, timezone

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from trendintel.api.main import app, get_repository  # noqa: E402

TREND = {
    "topic_id": 1, "slug": "gpt-5", "label": "GPT-5", "computed_at": datetime(2025, 1, 10, tzinfo=timezone.utc),
    "window_hours": 24.0, "mention_count": 3, "prev_mention_count": 0, "source_count": 2, "sources": ["HN", "Reddit"],
    "frequency_score": 1.0, "recency_score": 1.0, "growth_score": 0.5, "diversity_score": 1.0, "total_score": 90.0,
    "is_emerging": True, "history_available": True,
}


class FakeRepo:
    def latest_trends(self, limit=10, emerging_only=False):
        return [TREND][:limit]

    def topic_articles(self, topic_id, limit=50):
        return [{"id": 1, "title": "t", "url": "https://x.com", "source": "HN", "published_at": None, "collected_at": datetime(2025, 1, 10, tzinfo=timezone.utc)}]

    def trend_history(self, topic_ids, days=7):
        return [{"topic_id": topic_ids[0], "label": "GPT-5", "computed_at": datetime(2025, 1, 10, tzinfo=timezone.utc), "total_score": 90.0, "mention_count": 3, "source_count": 2}]

    def platform_topics(self, hours=24, per_source=5):
        return [{"source": "HN", "topic_id": 1, "label": "GPT-5", "mentions": 2}]

    def list_sources(self):
        return []

    def recent_runs(self, limit=30):
        return []


def client():
    app.dependency_overrides[get_repository] = lambda: FakeRepo()
    return TestClient(app)


def test_health():
    assert client().get("/health").json() == {"status": "ok"}


def test_trends_and_emerging():
    c = client()
    body = c.get("/trends?limit=5").json()
    assert body[0]["label"] == "GPT-5" and body[0]["sources"] == ["HN", "Reddit"]
    assert c.get("/trends/emerging").status_code == 200


def test_articles_history_platforms():
    c = client()
    assert c.get("/topics/1/articles").json()[0]["url"] == "https://x.com"
    assert c.get("/trends/history?topic_ids=1&days=3").json()[0]["total_score"] == 90.0
    assert c.get("/platforms/topics").json()[0]["source"] == "HN"


def test_validation():
    c = client()
    assert c.get("/trends?limit=0").status_code == 422
    assert c.get("/trends/history").status_code == 422  # topic_ids required
