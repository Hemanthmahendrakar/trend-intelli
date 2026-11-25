"""Central configuration.

Purpose: every tunable value (credentials, limits, scoring parameters) is read
from environment variables here and nowhere else, so no secret is ever
hard-coded and every module receives an immutable ``Settings`` object.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

try:  # python-dotenv is a convenience for local development only
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # pragma: no cover
    pass

ALL_SOURCES = ("hackernews", "reddit", "google_trends", "techcrunch", "producthunt")
DEFAULT_USER_AGENT = "trendintel/0.1 (set USER_AGENT in .env with a contact address)"


class ConfigError(RuntimeError):
    """Raised when configuration is missing or malformed."""


def _get_str(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name)
    return value.strip() if value and value.strip() else default


def _get_int(name: str, default: int) -> int:
    raw = _get_str(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer, got {raw!r}") from exc


def _get_float(name: str, default: float) -> float:
    raw = _get_str(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be a number, got {raw!r}") from exc


def _get_list(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    raw = _get_str(name)
    if raw is None:
        return default
    return tuple(part.strip() for part in raw.split(",") if part.strip())


@dataclass(frozen=True)
class Settings:
    # Database / logging
    database_url: str | None = None
    log_level: str = "INFO"
    log_file: str | None = None

    # HTTP behaviour
    user_agent: str = DEFAULT_USER_AGENT
    request_timeout: float = 15.0
    request_min_interval: float = 1.0
    max_retries: int = 3

    # Sources
    enabled_sources: tuple[str, ...] = ALL_SOURCES
    hn_limit: int = 30
    rss_limit: int = 30
    reddit_client_id: str | None = None
    reddit_client_secret: str | None = None
    reddit_user_agent: str = DEFAULT_USER_AGENT
    reddit_subreddits: tuple[str, ...] = ("technology", "programming", "MachineLearning", "worldnews")
    reddit_limit: int = 50
    google_trends_geo: str = "US"

    # Scoring
    trend_window_hours: float = 24.0
    trend_half_life_hours: float = 6.0
    trend_min_mentions: int = 2
    trend_emerging_min_mentions: int = 3
    trend_min_history_hours: float = 36.0
    trend_persist_top_n: int = 100

    # Dashboard
    api_base_url: str = "http://localhost:8000"

    @classmethod
    def from_env(cls) -> "Settings":
        user_agent = _get_str("USER_AGENT", DEFAULT_USER_AGENT) or DEFAULT_USER_AGENT
        return cls(
            database_url=_get_str("DATABASE_URL"),
            log_level=(_get_str("LOG_LEVEL", "INFO") or "INFO").upper(),
            log_file=_get_str("LOG_FILE"),
            user_agent=user_agent,
            request_timeout=_get_float("REQUEST_TIMEOUT", 15.0),
            request_min_interval=_get_float("REQUEST_MIN_INTERVAL", 1.0),
            max_retries=_get_int("MAX_RETRIES", 3),
            enabled_sources=_get_list("ENABLED_SOURCES", ALL_SOURCES),
            hn_limit=_get_int("HN_LIMIT", 30),
            rss_limit=_get_int("RSS_LIMIT", 30),
            reddit_client_id=_get_str("REDDIT_CLIENT_ID"),
            reddit_client_secret=_get_str("REDDIT_CLIENT_SECRET"),
            reddit_user_agent=_get_str("REDDIT_USER_AGENT", user_agent) or user_agent,
            reddit_subreddits=_get_list(
                "REDDIT_SUBREDDITS", ("technology", "programming", "MachineLearning", "worldnews")
            ),
            reddit_limit=_get_int("REDDIT_LIMIT", 50),
            google_trends_geo=(_get_str("GOOGLE_TRENDS_GEO", "US") or "US").upper(),
            trend_window_hours=_get_float("TREND_WINDOW_HOURS", 24.0),
            trend_half_life_hours=_get_float("TREND_HALF_LIFE_HOURS", 6.0),
            trend_min_mentions=_get_int("TREND_MIN_MENTIONS", 2),
            trend_emerging_min_mentions=_get_int("TREND_EMERGING_MIN_MENTIONS", 3),
            trend_min_history_hours=_get_float("TREND_MIN_HISTORY_HOURS", 36.0),
            trend_persist_top_n=_get_int("TREND_PERSIST_TOP_N", 100),
            api_base_url=_get_str("API_BASE_URL", "http://localhost:8000") or "http://localhost:8000",
        )

    def require_database_url(self) -> str:
        if not self.database_url:
            raise ConfigError("DATABASE_URL is not set. Copy .env.example to .env and configure it.")
        return self.database_url


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings.from_env()
