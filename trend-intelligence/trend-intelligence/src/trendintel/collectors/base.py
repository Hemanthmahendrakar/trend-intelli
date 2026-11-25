"""Collector interface.

Purpose: a collector knows how to talk to exactly one source and return a list
of raw ``Article`` objects. It does not clean, dedupe or store anything; the
pipeline does that. Adding a new source means adding one subclass.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from ..config import Settings
from ..http_client import PoliteHttpClient
from ..models import Article


class CollectorError(RuntimeError):
    """The source responded, but not in a form we can use."""


class CollectorConfigError(CollectorError):
    """The collector is not configured (e.g. missing credentials); skip it, don't fail."""


class BaseCollector(ABC):
    name: str = ""       # display name stored in the ``sources`` table
    key: str = ""        # machine key used in ENABLED_SOURCES
    kind: str = "api"    # "api" or "rss"
    base_url: str = ""

    def __init__(self, http: PoliteHttpClient, settings: Settings) -> None:
        self.http = http
        self.settings = settings

    @abstractmethod
    def fetch(self) -> list[Article]:
        """Return raw articles. May raise HttpError / CollectorError."""
