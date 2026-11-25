"""Transparent trend scoring.

Purpose: convert per-topic mention data into a 0-100 score using four
documented components. Nothing here is learned or hidden; every number can be
reproduced by hand from the formula below.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Sequence

from ..models import Article

METHODOLOGY_MD = """
**Windows.** *Current window* = the last `W` hours (default 24). *Previous window* = the `W` hours before that.
A topic's **mentions** `M` are the distinct articles in the current window that match it; `M_prev` is the same for the previous window.
Articles are placed in a window by publication time (falling back to collection time).

**Components** (each scaled to 0-1 across the topics being ranked):

| Component | Definition |
|---|---|
| Frequency `F` | `ln(1 + M) / ln(1 + M_max)` |
| Recency `R` | `Σ 0.5^(age_hours / half_life)` over current-window mentions, divided by the largest such sum (half-life default 6 h) |
| Growth `G` | `clip(log2((M + 1) / (M_prev + 1)), 0, 3) / 3` — declines score 0, they are not penalised further |
| Source diversity `S` | `distinct sources mentioning the topic / distinct sources active in the window` |

**Score** = `100 × (0.30·F + 0.25·R + 0.25·G + 0.20·S)`

**Emerging** = enough history exists, `M_prev = 0`, and `M ≥ 3`.

**If there is not yet enough collection history** (default: 36 h), growth cannot be measured, so `G` is dropped and the other weights are rescaled to sum to 1; nothing is flagged as emerging.

**Limitations.**
- Scores are *relative* to the topics found in the same run, not absolute popularity; a score of 80 today and 80 next week are not directly comparable.
- Mentions count articles *we collected*. Only five sources are covered, each with a limited number of items, so the system measures attention within this sample, not the whole internet.
- Source diversity treats an aggregator link-post (e.g. a Reddit post linking a TechCrunch article) as a separate source. That is intended, but it is not proof of independent reporting.
- Topics come from keyword matching, not language understanding: homonyms merge ("Apple" the company vs the fruit), and paraphrased stories about one event can split into several topics.
- Google Trends items are search terms, not articles, and a term that stays popular is stored once, so long-running trends may look flat.
- Weights (0.30/0.25/0.25/0.20) and the half-life are judgement calls, not fitted to data. Tune them in `ScoringConfig`.
- Small samples are noisy: with only 2-3 mentions a single extra post changes the ranking.
- Collection gaps (a failed run) lower mention counts and can appear as a decline.
"""


@dataclass(frozen=True)
class ScoringConfig:
    window_hours: float = 24.0
    half_life_hours: float = 6.0
    min_mentions: int = 2
    emerging_min_mentions: int = 3
    min_history_hours: float = 36.0
    growth_cap: float = 3.0
    weight_frequency: float = 0.30
    weight_recency: float = 0.25
    weight_growth: float = 0.25
    weight_diversity: float = 0.20

    def __post_init__(self) -> None:
        total = self.weight_frequency + self.weight_recency + self.weight_growth + self.weight_diversity
        if abs(total - 1.0) > 1e-9:
            raise ValueError(f"Scoring weights must sum to 1.0, got {total}")
        if self.window_hours <= 0 or self.half_life_hours <= 0:
            raise ValueError("window_hours and half_life_hours must be positive")

    @classmethod
    def from_settings(cls, settings) -> "ScoringConfig":
        return cls(
            window_hours=settings.trend_window_hours,
            half_life_hours=settings.trend_half_life_hours,
            min_mentions=settings.trend_min_mentions,
            emerging_min_mentions=settings.trend_emerging_min_mentions,
            min_history_hours=settings.trend_min_history_hours,
        )


@dataclass
class TopicActivity:
    """A topic with every article (both windows) that matched it."""

    slug: str
    label: str
    articles: Sequence[Article]


@dataclass
class TrendScore:
    slug: str
    label: str
    mention_count: int
    prev_mention_count: int
    source_count: int
    sources: list[str]
    frequency_score: float
    recency_score: float
    growth_score: float
    diversity_score: float
    total_score: float
    is_emerging: bool
    history_available: bool
    window_hours: float
    articles: list[Article] = field(default_factory=list)  # current-window articles, newest first

    def explain(self) -> str:
        return (
            f"{self.label}: score {self.total_score:.1f} = F {self.frequency_score:.2f}, R {self.recency_score:.2f}, "
            f"G {self.growth_score:.2f}, S {self.diversity_score:.2f} "
            f"({self.mention_count} mentions vs {self.prev_mention_count} before, {self.source_count} sources)"
        )


def growth_component(mentions: int, prev_mentions: int, cap: float = 3.0) -> float:
    """Smoothed log2 growth ratio, floored at 0 and capped, scaled to 0-1."""
    raw = math.log2((mentions + 1) / (prev_mentions + 1))
    return min(max(raw, 0.0), cap) / cap


def score_topics(
    activities: Sequence[TopicActivity],
    now: datetime,
    cfg: ScoringConfig,
    total_sources: int,
    history_available: bool,
) -> list[TrendScore]:
    current_start = now - timedelta(hours=cfg.window_hours)
    previous_start = now - timedelta(hours=2 * cfg.window_hours)

    rows = []
    for activity in activities:
        current = [a for a in activity.articles if a.effective_time > current_start]
        previous = [a for a in activity.articles if previous_start < a.effective_time <= current_start]
        if len(current) < cfg.min_mentions:
            continue
        recency = sum(
            0.5 ** (max(0.0, (now - a.effective_time).total_seconds() / 3600.0) / cfg.half_life_hours) for a in current
        )
        rows.append((activity, current, len(previous), recency))
    if not rows:
        return []

    max_mentions = max(len(current) for _, current, _, _ in rows)
    max_recency = max(r for _, _, _, r in rows)

    w_f, w_r, w_g, w_s = cfg.weight_frequency, cfg.weight_recency, cfg.weight_growth, cfg.weight_diversity
    if not history_available:
        remaining = 1.0 - w_g
        w_f, w_r, w_s, w_g = w_f / remaining, w_r / remaining, w_s / remaining, 0.0

    scores: list[TrendScore] = []
    for activity, current, prev_count, recency_raw in rows:
        mentions = len(current)
        sources = sorted({a.source for a in current})
        frequency = math.log1p(mentions) / math.log1p(max_mentions)
        recency = recency_raw / max_recency if max_recency else 0.0
        growth = growth_component(mentions, prev_count, cfg.growth_cap) if history_available else 0.0
        diversity = min(1.0, len(sources) / max(total_sources, 1))
        total = 100.0 * (w_f * frequency + w_r * recency + w_g * growth + w_s * diversity)
        scores.append(
            TrendScore(
                slug=activity.slug,
                label=activity.label,
                mention_count=mentions,
                prev_mention_count=prev_count,
                source_count=len(sources),
                sources=sources,
                frequency_score=round(frequency, 4),
                recency_score=round(recency, 4),
                growth_score=round(growth, 4),
                diversity_score=round(diversity, 4),
                total_score=round(total, 2),
                is_emerging=history_available and prev_count == 0 and mentions >= cfg.emerging_min_mentions,
                history_available=history_available,
                window_hours=cfg.window_hours,
                articles=sorted(current, key=lambda a: a.effective_time, reverse=True),
            )
        )
    scores.sort(key=lambda s: (-s.total_score, -s.mention_count, s.slug))
    return scores
