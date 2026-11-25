"""Glue: raw collector output -> cleaned, de-duplicated articles."""
from __future__ import annotations

from datetime import datetime
from typing import Iterable

from ..models import Article
from .cleaning import clean_article
from .dedup import deduplicate


def prepare_articles(raw: Iterable[Article], now: datetime | None = None) -> list[Article]:
    cleaned = [a for a in (clean_article(item, now) for item in raw) if a is not None]
    return deduplicate(cleaned)
