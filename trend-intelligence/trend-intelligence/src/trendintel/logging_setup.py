"""Logging configuration shared by the CLI, API and workers."""
from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler

LOG_FORMAT = "%(asctime)s %(levelname)-8s %(name)s: %(message)s"


def setup_logging(level: str = "INFO", log_file: str | None = None) -> None:
    """Configure root logging to the console and, optionally, a rotating file."""
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    if log_file:
        directory = os.path.dirname(log_file)
        if directory:
            os.makedirs(directory, exist_ok=True)
        handlers.append(RotatingFileHandler(log_file, maxBytes=2_000_000, backupCount=3, encoding="utf-8"))
    logging.basicConfig(level=getattr(logging, level.upper(), logging.INFO), format=LOG_FORMAT, handlers=handlers, force=True)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
