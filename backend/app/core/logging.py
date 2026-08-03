"""Logging configuration.

A single entry point so every service shares the same format and level.
Structured/JSON logging can be swapped in here later without touching callers.
"""

import logging
import sys

from app.core.config import settings

_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"


def configure_logging(*, level: str | None = None) -> None:
    effective = (level or settings.log_level).upper()
    logging.basicConfig(
        level=effective,
        format=_FORMAT,
        stream=sys.stdout,
        force=True,
    )
    logging.getLogger("uvicorn").handlers = logging.getLogger().handlers
    logging.getLogger("uvicorn.access").handlers = logging.getLogger().handlers
