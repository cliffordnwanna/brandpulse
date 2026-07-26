"""BaseConnector interface (Engineering Design §3) and its supporting types.

Milestone 1 scope: interface only — no concrete connectors, no orchestration,
no retry/checkpoint logic (that's Milestone 2), no real search/normalize logic
(that's Milestone 3 onward).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel

from brandpulse.schema import CollectionScope, Mention


class RunStatus(StrEnum):
    """Failure-strategy statuses (Engineering Design §6)."""

    SUCCESS = "SUCCESS"
    PARTIAL_SUCCESS = "PARTIAL_SUCCESS"
    FAILED = "FAILED"
    NO_RESULTS = "NO_RESULTS"


class RunResult(BaseModel):
    """Return type of ``BaseConnector.search()`` (Engineering Design §6).

    ``search()`` never raises for expected failure modes — it always returns
    one of these instead.

    ``next_cursor``: for connectors that paginate (Milestone 3+), an opaque,
    connector-serialized pagination position — ``None`` means pagination is
    exhausted (or the connector has no pagination concept at all, e.g. the
    Milestone 2 stub). The orchestrator persists this on the ``Checkpoint``
    and hands it back on the next call; it never interprets the value.
    """

    status: RunStatus
    records: list[Any] = []
    reason: str | None = None
    next_cursor: str | None = None


class HealthStatus(BaseModel):
    """Return type of ``BaseConnector.health()`` (Engineering Design §3)."""

    healthy: bool
    reason: str | None = None
    checked_at: datetime | None = None


class BaseConnector(ABC):
    """Common interface every source connector subclasses (Engineering Design §3).

    Each source lives in its own module under ``connectors/`` and subclasses
    this ABC. The Source Registry auto-discovers connectors at startup
    (directory scan, no ``if platform == "reddit"`` branching anywhere).

    ``collection_scope`` describes *how a Mention was collected* — it matches
    ``Mention.collection_scope`` in the canonical schema (§2) exactly, and
    ranges over every value in that schema (``"keyword"``, ``"app"``,
    ``"channel"``, ``"subreddit"``, ``"forum"``).

    ``is_keyword_driven`` is a separate, orchestrator-facing signal: whether
    this connector's ``search()`` genuinely needs one job per configured
    keyword. Every concrete connector sets it explicitly (same discipline as
    ``collection_scope`` — no implicit inheritance). Most of the time it
    matches ``collection_scope == "keyword"`` — non-keyword scopes usually
    mean "collect everything for a fixed target, one job total" (Google
    Play's ``"app"``, a fixed YouTube ``"channel"``, etc., see Milestone 3's
    Google Play correction). But a connector can be keyword-searched with a
    *different* canonical ``collection_scope`` — Nairaland is
    ``collection_scope="forum"`` (that's what its Mention records should
    say they are) while still needing one job per keyword (that's how it's
    actually searched); it sets ``is_keyword_driven=True`` explicitly rather
    than being forced to lie about ``collection_scope`` just to get correct
    job dispatch.
    """

    name: str
    version: str
    reliability: Literal["high", "medium", "low"]
    collection_scope: CollectionScope = "keyword"
    is_keyword_driven: bool = True
    """Default True to match the historical ``collection_scope=="keyword"``
    default above — a connector with a non-"keyword" ``collection_scope``
    must override this to ``False`` explicitly (Google Play/App Store do)."""

    @abstractmethod
    def search(
        self,
        keywords: list[str],
        start: datetime,
        end: datetime,
        cursor: str | None = None,
    ) -> RunResult:
        """Execute the search/scrape, optionally resuming from ``cursor``.

        Never raises on expected failure modes (timeouts, empty results,
        blocked requests) — returns a ``RunResult`` instead.

        ``cursor``: an opaque pagination position previously returned as
        ``RunResult.next_cursor`` by this same connector — connectors with no
        pagination concept ignore it and always return ``next_cursor=None``.
        """
        raise NotImplementedError

    @abstractmethod
    def normalize(self, raw_item: Any) -> Mention:
        """Convert one source-native record into the canonical schema (§2)."""
        raise NotImplementedError

    @abstractmethod
    def validate(self, mention: Mention) -> bool:
        """Reject malformed records before they reach Bronze.

        E.g. empty text, missing mention_id, timestamp outside the requested
        window.
        """
        raise NotImplementedError

    @abstractmethod
    def health(self) -> HealthStatus:
        """Lightweight reachability check the orchestrator can call before a run."""
        raise NotImplementedError
