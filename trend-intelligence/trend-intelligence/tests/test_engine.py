from datetime import timedelta

from tests.helpers import NOW, make_article
from trendintel.trends.engine import analyze_articles
from trendintel.trends.scoring import ScoringConfig


def corpus():
    return [
        make_article(1, "Hacker News", 1, "OpenAI unveils GPT-5 model"),
        make_article(2, "Reddit", 2, "OpenAI GPT-5 benchmarks"),
        make_article(3, "TechCrunch", 3, "GPT-5 release hits developers"),
        make_article(4, "Hacker News", 2, "Rust compiler gets faster"),
        make_article(5, "Reddit", 4, "Quantum chips arrive"),
        make_article(6, "TechCrunch", 5, "Funding frenzy continues"),
    ]


def test_end_to_end_top_topic():
    scores = analyze_articles(corpus(), NOW, ScoringConfig())
    top = scores[0]
    assert top.slug == "gpt-5"
    assert top.mention_count == 3 and top.source_count == 3
    assert top.sources == ["Hacker News", "Reddit", "TechCrunch"]
    assert [a.id for a in top.articles] == [1, 2, 3]  # newest first


def test_history_flag_follows_first_collection_time():
    cfg = ScoringConfig()
    assert analyze_articles(corpus(), NOW, cfg, first_collected_at=NOW - timedelta(hours=2))[0].history_available is False
    assert analyze_articles(corpus(), NOW, cfg, first_collected_at=NOW - timedelta(hours=48))[0].history_available is True


def test_old_articles_are_ignored():
    old = [make_article(i, "HN", 100 + i, "Ancient GPT-5 news") for i in range(5)]
    assert analyze_articles(old, NOW, ScoringConfig()) == []
