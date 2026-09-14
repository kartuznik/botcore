"""Single place where logging is configured for the whole process."""

from __future__ import annotations

import logging

LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
FALLBACK_LEVEL = logging.INFO


def resolve_level(level: str) -> int:
    """Translate a level name into its numeric value, falling back to INFO."""
    return logging.getLevelNamesMapping().get(level.strip().upper(), FALLBACK_LEVEL)


def setup_logging(level: str = "INFO") -> None:
    """Configure the root logger; safe to call more than once."""
    logging.basicConfig(
        level=resolve_level(level),
        format=LOG_FORMAT,
        datefmt=DATE_FORMAT,
        force=True,
    )


def get_logger(name: str) -> logging.Logger:
    """Return a logger that renders its own name in every record."""
    return logging.getLogger(name)
