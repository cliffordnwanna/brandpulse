"""Shared politeness controls every connector uses (Engineering Design §17).

Rate limiting is global, not per-connector — one shared limiter, so a burst
on one source can't starve another. robots.txt is checked programmatically
before a connector runs, not just documented as policy. Request delays are
randomized to avoid hammering a source.
"""

from __future__ import annotations

import random
import threading
import time
import urllib.robotparser
from collections.abc import Callable
from urllib.parse import urlparse

from brandpulse.config.models import RateLimitConfig


class RateLimiter:
    """Global requests-per-minute limiter, shared across all connectors.

    Simple token-bucket-by-sleep: blocks the caller just long enough to keep
    the long-run rate at or below ``requests_per_minute``. Thread-safe so
    multiple connectors running concurrently (via the job queue's worker
    pool) share one real ceiling instead of each getting their own.
    """

    def __init__(self, requests_per_minute: int) -> None:
        self._min_interval = 60.0 / requests_per_minute
        self._lock = threading.Lock()
        self._last_request_at: float = 0.0

    def acquire(self, sleep_fn: Callable[[float], None] = time.sleep) -> None:
        with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_request_at
            wait = self._min_interval - elapsed
            if wait > 0:
                sleep_fn(wait)
            self._last_request_at = time.monotonic()


def random_delay(min_seconds: float = 0.5, max_seconds: float = 2.0) -> float:
    """Return a randomized delay (seconds) to avoid hammering a source (§17)."""
    return random.uniform(min_seconds, max_seconds)


def is_allowed_by_robots_txt(url: str, user_agent: str) -> bool:
    """Check ``robots.txt`` for ``url`` before a connector is allowed to fetch it.

    Fails open (returns True) if robots.txt can't be fetched/parsed — an
    unreachable robots.txt is not itself grounds to block a well-behaved
    scraper, but a robots.txt that explicitly disallows the path is respected.
    """
    parsed = urlparse(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"

    parser = urllib.robotparser.RobotFileParser()
    parser.set_url(robots_url)
    try:
        parser.read()
    except OSError:
        return True

    return parser.can_fetch(user_agent, url)


def build_rate_limiter(rate_limit_config: RateLimitConfig) -> RateLimiter:
    """Construct the single shared ``RateLimiter`` from config (§8, §17)."""
    return RateLimiter(rate_limit_config.requests_per_minute)
