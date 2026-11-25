"""Orchestration: collect -> clean/dedupe -> store -> analyse -> persist.

Purpose: wires the independent components together. Each source is isolated: a
failure in one collector is logged and recorded in ``collection_runs`` but
never stops the others.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Sequence

from .collectors import BaseCollector, CollectorConfigError
from .config import Settings
from .models import Article
from .processing.prepare import prepare_articles
from .trends.engine import analyze_articles
from .trends.scoring import ScoringConfig, TrendScore

if TYPE_CHECKING:  # keep the pipeline importable/testable without a DB driver
    from .db.repository import Repository

logger = logging.getLogger(__name__)


@dataclass
class CollectionOutcome:
    source: str
    status: str  # success | failed | skipped
    fetched: int = 0
    inserted: int = 0
    error: str | None = None


def collect_in_memory(collectors: Sequence[BaseCollector]) -> list[Article]:
    """Collect and prepare articles without a database (used by the ``preview`` command)."""
    articles: list[Article] = []
    for collector in collectors:
        try:
            articles.extend(prepare_articles(collector.fetch()))
        except CollectorConfigError as exc:
            logger.warning("%s skipped: %s", collector.name, exc)
        except Exception as exc:  # noqa: BLE001 - one bad source must not stop the rest
            logger.error("%s failed: %s", collector.name, exc)
    return articles


class Pipeline:
    def __init__(self, settings: Settings, repo: Repository, collectors: Sequence[BaseCollector]) -> None:
        self.settings = settings
        self.repo = repo
        self.collectors = list(collectors)

    def collect(self) -> list[CollectionOutcome]:
        outcomes: list[CollectionOutcome] = []
        for collector in self.collectors:
            outcomes.append(self._collect_one(collector))
        ok = sum(o.status == "success" for o in outcomes)
        logger.info("Collection finished: %d/%d sources succeeded", ok, len(outcomes))
        return outcomes

    def _collect_one(self, collector: BaseCollector) -> CollectionOutcome:
        source_id = self.repo.upsert_source(collector.name, collector.kind, collector.base_url)
        run_id = self.repo.start_run(source_id)
        try:
            raw = collector.fetch()
            prepared = prepare_articles(raw)
            inserted = self.repo.insert_articles(source_id, run_id, prepared)
            self.repo.finish_run(run_id, "success", fetched=len(raw), inserted=inserted)
            logger.info("%s: fetched %d, %d new", collector.name, len(raw), inserted)
            return CollectionOutcome(collector.name, "success", len(raw), inserted)
        except CollectorConfigError as exc:
            logger.warning("%s skipped: %s", collector.name, exc)
            self.repo.finish_run(run_id, "skipped", error=str(exc))
            return CollectionOutcome(collector.name, "skipped", error=str(exc))
        except Exception as exc:  # noqa: BLE001 - isolate failures per source
            logger.exception("%s failed", collector.name)
            self.repo.finish_run(run_id, "failed", error=str(exc)[:1000])
            return CollectionOutcome(collector.name, "failed", error=str(exc))

    def analyze(self, now: datetime | None = None) -> list[TrendScore]:
        now = now or datetime.now(timezone.utc)
        cfg = ScoringConfig.from_settings(self.settings)
        articles = self.repo.fetch_articles_since(now - timedelta(hours=2 * cfg.window_hours))
        if not articles:
            logger.warning("No articles in the last %.0f hours; run `collect` first", 2 * cfg.window_hours)
            return []
        scores = analyze_articles(articles, now, cfg, first_collected_at=self.repo.first_collected_at())
        if scores:
            self.repo.save_trend_snapshot(scores[: self.settings.trend_persist_top_n], now)
        else:
            logger.warning("No topic reached the minimum of %d mentions", cfg.min_mentions)
        return scores

    def run_once(self) -> list[TrendScore]:
        self.collect()
        return self.analyze()
