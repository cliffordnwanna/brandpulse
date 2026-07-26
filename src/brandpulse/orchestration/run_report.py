"""Per-run connector outcome collector (Milestone 6).

Distinct from ``ConnectorHealthStore`` (cross-run failure-streak state for
the auto-disable rule) — this is purely a per-run collector the orchestrator
appends one entry to per (connector, job) it executes, used to build
``connector_health.csv`` and ``errors.csv`` for that run's output files. Not
persisted independently; the ``run`` CLI command holds the instance for the
duration of one orchestrator run.
"""

from __future__ import annotations

from pydantic import BaseModel


class ConnectorRunOutcome(BaseModel):
    connector_name: str
    search_term: str
    status: str
    duration_s: float
    result_count: int
    reason: str | None = None
    auto_disabled: bool = False


class RunReport:
    """Collects one ``ConnectorRunOutcome`` per (connector, job) executed in a
    run, plus every ``mention_id`` written to Bronze during it.

    The ``mention_ids`` set (Milestone 6) is what makes "snapshot" mode
    possible: Bronze/Silver/Gold are cumulative, idempotent-keyed stores with
    no run_id field of their own (the same mention scraped in two different
    runs collapses to one record), so scoping a report to "just what this
    run collected" requires tracking which mention_ids this specific run's
    Bronze writes touched, separately from the stores themselves.
    """

    def __init__(self) -> None:
        self._outcomes: list[ConnectorRunOutcome] = []
        self._mention_ids: set[str] = set()

    def record(self, outcome: ConnectorRunOutcome) -> None:
        self._outcomes.append(outcome)

    def record_mention_id(self, mention_id: str) -> None:
        self._mention_ids.add(mention_id)

    @property
    def outcomes(self) -> list[ConnectorRunOutcome]:
        return list(self._outcomes)

    @property
    def mention_ids(self) -> set[str]:
        return set(self._mention_ids)

    def failed_or_partial(self) -> list[ConnectorRunOutcome]:
        return [o for o in self._outcomes if o.status in ("FAILED", "PARTIAL_SUCCESS")]

    def failed_connector_names(self) -> list[str]:
        return sorted({o.connector_name for o in self._outcomes if o.status == "FAILED"})
