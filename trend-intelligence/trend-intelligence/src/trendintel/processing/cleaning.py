"""Text cleaning, URL canonicalisation and timestamp normalisation.

Purpose: collectors return messy, source-specific data (HTML fragments, RSS
boilerplate, tracking parameters, mixed date formats). This module turns each
raw ``Article`` into a uniform one so that later stages (dedup, keywords,
windowing) can rely on consistent data.
"""
from __future__ import annotations

import hashlib
import html
import logging
import re
import unicodedata
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from bs4 import BeautifulSoup

from ..models import Article, utcnow

logger = logging.getLogger(__name__)

_WS_RE = re.compile(r"\s+")
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
_WP_FOOTER_RE = re.compile(r"\s*The post .{0,300}? appeared first on .{0,100}$", re.IGNORECASE)
_TRACKING_PARAMS = {"fbclid", "gclid", "ref", "ref_src", "mc_cid", "mc_eid", "igshid", "yclid", "_hsenc", "_hsmi"}
MAX_TITLE_LEN = 500
MAX_DESCRIPTION_LEN = 1000


def clean_text(text: str | None, max_length: int | None = None) -> str:
    """Strip HTML, decode entities, normalise unicode/whitespace and drop feed boilerplate."""
    if not text:
        return ""
    if "<" in text and ">" in text:
        text = BeautifulSoup(text, "html.parser").get_text(" ")
    text = html.unescape(text)
    text = unicodedata.normalize("NFKC", text)
    text = _CONTROL_RE.sub(" ", text)
    text = _WS_RE.sub(" ", text).strip()
    text = _WP_FOOTER_RE.sub("", text).strip()
    if max_length and len(text) > max_length:
        text = text[: max_length - 1].rstrip() + "…"
    return text


def canonicalize_url(url: str | None) -> str:
    """Lower-case host, drop ``www.``, fragments, tracking parameters and trailing slashes."""
    if not url:
        return ""
    parts = urlsplit(url.strip())
    if not parts.netloc:
        return ""
    scheme = "https" if parts.scheme.lower() in ("http", "https") else parts.scheme.lower()
    host = parts.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    query = sorted(
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if not k.lower().startswith("utm_") and k.lower() not in _TRACKING_PARAMS
    )
    path = parts.path.rstrip("/")
    return urlunsplit((scheme, host, path, urlencode(query), ""))


def parse_timestamp(value: Any) -> datetime | None:
    """Parse RFC-822, ISO-8601, epoch seconds or datetimes into timezone-aware UTC."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, (int, float)):
        try:
            dt = datetime.fromtimestamp(value, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    else:
        text = str(value).strip()
        dt = None
        try:
            dt = parsedate_to_datetime(text)
        except (TypeError, ValueError, IndexError):
            dt = None
        if dt is None:
            try:
                dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
            except ValueError:
                return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def hash_url(canonical_url: str) -> str:
    return hashlib.sha256(canonical_url.encode("utf-8")).hexdigest()


def hash_title(title: str) -> str:
    """Hash of the title ignoring case, punctuation and spacing (catches re-posted headlines)."""
    normalized = re.sub(r"[^a-z0-9]+", "", title.lower())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def clean_article(article: Article, now: datetime | None = None) -> Article | None:
    """Return a cleaned copy of ``article`` or ``None`` if it is unusable."""
    now = now or utcnow()
    title = clean_text(article.title, MAX_TITLE_LEN)
    url = canonicalize_url(article.url)
    if not title or not url.startswith(("http://", "https://")):
        logger.debug("Dropping unusable article from %s: %r", article.source, article.title)
        return None

    published = parse_timestamp(article.published_at)
    if published and published > now + timedelta(hours=1):
        logger.debug("Ignoring future publication date for %r", title)
        published = None

    collected = parse_timestamp(article.collected_at) or now
    return replace(
        article,
        title=title,
        description=clean_text(article.description, MAX_DESCRIPTION_LEN),
        url=url,
        published_at=published,
        collected_at=collected,
        url_hash=hash_url(url),
        content_hash=hash_title(title),
    )
