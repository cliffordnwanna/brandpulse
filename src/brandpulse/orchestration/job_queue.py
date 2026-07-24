"""Ingestion job queue (Engineering Design §18).

One job per source x keyword. A worker pool executes jobs so a slow source
doesn't block a fast one. Local MVP implementation: a simple thread pool —
Phase 2 can map the same interface onto Fabric-native scheduling without
changing callers.
"""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass


@dataclass(frozen=True)
class Job:
    """One unit of ingestion work: a single source searching a single keyword."""

    source_name: str
    search_term: str


class JobQueue[T]:
    """Runs a list of ``Job``s across a worker pool, collecting each job's result."""

    def __init__(self, max_workers: int = 4) -> None:
        self._max_workers = max_workers

    def run(self, jobs: list[Job], handler: Callable[[Job], T]) -> list[tuple[Job, T]]:
        """Execute ``handler(job)`` for every job, in parallel, up to ``max_workers``.

        Returns ``(job, result)`` pairs in completion order (not submission
        order) — callers that need per-connector/per-keyword identity should
        rely on the returned ``Job``, not on list position.
        """
        results: list[tuple[Job, T]] = []
        with ThreadPoolExecutor(max_workers=self._max_workers) as executor:
            future_to_job = {executor.submit(handler, job): job for job in jobs}
            for future in as_completed(future_to_job):
                job = future_to_job[future]
                results.append((job, future.result()))
        return results
