"""Structured JSON logging configuration."""

from __future__ import annotations

import logging
import sys

try:
    from pythonjsonlogger import jsonlogger

    _HAS_JSON_LOGGER = True
except ImportError:  # pragma: no cover - fallback when dependency missing
    _HAS_JSON_LOGGER = False


def configure_logging(level: str = "INFO") -> None:
    """Configure root logging with structured JSON output to stdout."""
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    handler = logging.StreamHandler(sys.stdout)
    if _HAS_JSON_LOGGER:
        formatter = jsonlogger.JsonFormatter(
            "%(asctime)s %(levelname)s %(name)s %(message)s"
        )
    else:  # pragma: no cover - fallback formatting
        formatter = logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s %(message)s"
        )
    handler.setFormatter(formatter)

    root_logger.handlers = [handler]
