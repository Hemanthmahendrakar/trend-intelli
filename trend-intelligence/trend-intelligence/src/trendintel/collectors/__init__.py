"""Source collectors and their registry."""
from __future__ import annotations

import logging
from typing import Iterable

from ..config import Settings
from ..http_client import PoliteHttpClient
from .base import BaseCollector, CollectorConfigError, CollectorError
from .google_trends import GoogleTrendsCollector
from .hackernews import HackerNewsCollector
from .producthunt import ProductHuntCollector
from .reddit import RedditCollector
from .techcrunch import TechCrunchCollector

logger = logging.getLogger(__name__)

COLLECTOR_CLASSES: dict[str, type[BaseCollector]] = {
    cls.key: cls
    for cls in (HackerNewsCollector, RedditCollector, GoogleTrendsCollector, TechCrunchCollector, ProductHuntCollector)
}


def build_collectors(
    settings: Settings, http: PoliteHttpClient, names: Iterable[str] | None = None
) -> list[BaseCollector]:
    """Instantiate collectors for ``names`` (default: ENABLED_SOURCES); unknown names are warned about."""
    selected = list(names) if names else list(settings.enabled_sources)
    collectors: list[BaseCollector] = []
    for name in selected:
        cls = COLLECTOR_CLASSES.get(name.strip().lower())
        if cls is None:
            logger.warning("Unknown source %r ignored (known: %s)", name, ", ".join(COLLECTOR_CLASSES))
            continue
        collectors.append(cls(http, settings))
    return collectors


__all__ = [
    "BaseCollector",
    "CollectorConfigError",
    "CollectorError",
    "COLLECTOR_CLASSES",
    "build_collectors",
]
