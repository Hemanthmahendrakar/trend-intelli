import math

import pytest

from tests.helpers import NOW, make_article
from trendintel.trends.scoring import ScoringConfig, TopicActivity, growth_component, score_topics


def build_activities():
    # A: 4 current mentions over 3 sources, 1 previous
    a = [make_article(1, "HN", 1), make_article(2, "Reddit", 2), make_article(3, "TC", 3), make_article(4, "HN", 4), make_article(5, "HN", 30)]
    # B: 2 current mentions, 1 source, 2 previous
    b = [make_article(10, "HN", 5), make_article(11, "HN", 6), make_article(12, "HN", 28), make_article(13, "HN", 40)]
    # C: 3 current mentions, 0 previous (emerging)
    c = [make_article(20, "HN", 1), make_article(21, "Reddit", 2), make_article(22, "Reddit", 3)]
    # D: only 1 current mention -> below min_mentions
    d = [make_article(30, "HN", 1)]
    return [TopicActivity("a", "A", a), TopicActivity("b", "B", b), TopicActivity("c", "C", c), TopicActivity("d", "D", d)]


def test_growth_component_values():
    assert growth_component(4, 0) == pytest.approx(math.log2(5) / 3)
    assert growth_component(4, 4) == 0.0
    assert growth_component(2, 6) == 0.0  # declines are floored at zero
    assert growth_component(1000, 0) == 1.0  # capped


def test_scores_rank_and_filter():
    scores = score_topics(build_activities(), NOW, ScoringConfig(), total_sources=3, history_available=True)
    by = {s.slug: s for s in scores}
    assert "d" not in by
    assert all(0 <= s.total_score <= 100 for s in scores)
    assert by["a"].total_score > by["b"].total_score
    assert by["a"].mention_count == 4 and by["a"].prev_mention_count == 1
    assert by["a"].sources == ["HN", "Reddit", "TC"]
    assert by["a"].diversity_score == 1.0
    assert [s.slug for s in scores] == sorted(by, key=lambda k: (-by[k].total_score, -by[k].mention_count, k))


def test_emerging_flag():
    by = {s.slug: s for s in score_topics(build_activities(), NOW, ScoringConfig(), 3, True)}
    assert by["c"].is_emerging is True
    assert by["a"].is_emerging is False and by["b"].is_emerging is False


def test_without_history_growth_is_dropped_and_weights_rescaled():
    scores = score_topics(build_activities(), NOW, ScoringConfig(), 3, False)
    assert all(s.growth_score == 0.0 and not s.is_emerging and not s.history_available for s in scores)
    top = scores[0]
    expected = 100 * (0.30 * top.frequency_score + 0.25 * top.recency_score + 0.20 * top.diversity_score) / 0.75
    assert top.total_score == pytest.approx(expected, abs=0.01)


def test_recency_prefers_newer_mentions():
    fresh = TopicActivity("fresh", "Fresh", [make_article(1, "HN", 0.5), make_article(2, "HN", 1)])
    stale = TopicActivity("stale", "Stale", [make_article(3, "HN", 20), make_article(4, "HN", 22)])
    by = {s.slug: s for s in score_topics([fresh, stale], NOW, ScoringConfig(), 1, False)}
    assert by["fresh"].recency_score == 1.0
    assert by["stale"].recency_score < 0.2
    assert by["fresh"].total_score > by["stale"].total_score


def test_empty_input():
    assert score_topics([], NOW, ScoringConfig(), 1, True) == []


def test_config_validates_weights():
    with pytest.raises(ValueError):
        ScoringConfig(weight_frequency=0.9)
