"""Structured (JSON) logging (Engineering Design §7).

One JSON object per event, so logs are queryable rather than just readable.
"""

from __future__ import annotations

import json
import logging
import sys
from typing import Any

_LOGGER_NAME = "brandpulse.orchestration"


def get_logger(stream: Any = None) -> logging.Logger:
    """Return the orchestration logger, configured to emit one JSON line per event."""
    logger = logging.getLogger(_LOGGER_NAME)
    if not logger.handlers:
        handler = logging.StreamHandler(stream or sys.stdout)
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
    return logger


def log_event(logger: logging.Logger, event: str, **fields: Any) -> None:
    """Emit one structured JSON log line for ``event`` plus arbitrary fields.

    Matches the shape in Engineering Design §7, e.g.:
    ``{"event": "connector_run_start", "connector": "google_play", ...}``
    """
    record = {"event": event, **fields}
    logger.info(json.dumps(record, default=str))
