"""Command-line entry point: ``trendintel <command>``."""
from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import datetime, timezone

import pandas as pd

from .collectors import build_collectors
from .config import ConfigError, Settings
from .db.connection import get_engine
from .db.repository import Repository
from .http_client import PoliteHttpClient
from .logging_setup import setup_logging
from .pipeline import Pipeline, collect_in_memory
from .trends.engine import analyze_articles
from .trends.scoring import ScoringConfig

logger = logging.getLogger("trendintel.cli")


def _names(value: str | None) -> list[str] | None:
    return [p.strip() for p in value.split(",") if p.strip()] if value else None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="trendintel", description="Internet Trend Intelligence System")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init-db", help="create database tables")
    collect = sub.add_parser("collect", help="fetch, clean and store articles")
    collect.add_argument("--sources", help="comma-separated subset, e.g. hackernews,techcrunch")
    sub.add_parser("analyze", help="score topics from stored articles and save a snapshot")
    run = sub.add_parser("run", help="collect + analyze (optionally in a loop)")
    run.add_argument("--sources")
    run.add_argument("--every-minutes", type=float, help="repeat forever with this interval")
    preview = sub.add_parser("preview", help="collect + analyze in memory, no database needed")
    preview.add_argument("--sources")
    preview.add_argument("--top", type=int, default=10)
    return parser


def _pipeline(settings: Settings, sources: list[str] | None) -> Pipeline:
    repo = Repository(get_engine(settings.require_database_url()))
    http = PoliteHttpClient.from_settings(settings)
    return Pipeline(settings, repo, build_collectors(settings, http, sources))


def _print_scores(scores, top: int) -> None:
    if not scores:
        print("No trending topics found (need at least a few articles that share a topic).")
        return
    frame = pd.DataFrame(
        [
            {
                "topic": s.label,
                "score": s.total_score,
                "mentions": s.mention_count,
                "prev": s.prev_mention_count,
                "sources": ", ".join(s.sources),
                "emerging": "yes" if s.is_emerging else "",
            }
            for s in scores[:top]
        ]
    )
    print(frame.to_string(index=False))
    if not scores[0].history_available:
        print("\nNote: not enough collection history yet, so growth is excluded from the score.")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        settings = Settings.from_env()
        setup_logging(settings.log_level, settings.log_file)

        if args.command == "init-db":
            Repository(get_engine(settings.require_database_url())).init_schema()
        elif args.command == "collect":
            _pipeline(settings, _names(args.sources)).collect()
        elif args.command == "analyze":
            _print_scores(_pipeline(settings, None).analyze(), 10)
        elif args.command == "run":
            pipeline = _pipeline(settings, _names(args.sources))
            while True:
                _print_scores(pipeline.run_once(), 10)
                if not args.every_minutes:
                    break
                logger.info("Sleeping %.1f minutes", args.every_minutes)
                time.sleep(args.every_minutes * 60)
        elif args.command == "preview":
            http = PoliteHttpClient.from_settings(settings)
            articles = collect_in_memory(build_collectors(settings, http, _names(args.sources)))
            scores = analyze_articles(articles, datetime.now(timezone.utc), ScoringConfig.from_settings(settings))
            _print_scores(scores, args.top)
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
