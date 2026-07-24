"""Orchestrator (Engineering Design §1, §18).

Ties together the job queue, run/connector state + checkpointing, the retry
policy, and structured logging. Runs one job per (connector, keyword),
looping over pagination: each ``connector.search()`` call is one page/batch,
checkpointed (including the connector's opaque cursor) after every successful
call, so a crash mid-pagination resumes from the last completed page rather
than refetching from the start (Milestone 3 requirement).
"""

from __future__ import annotations

import time
from collections.abc import Callable
from datetime import datetime

from brandpulse.config.models import RetryConfig
from brandpulse.connectors.base import BaseConnector, RunResult, RunStatus
from brandpulse.orchestration.connector_health import ConnectorHealthStore
from brandpulse.orchestration.job_queue import Job, JobQueue
from brandpulse.orchestration.logging import get_logger, log_event
from brandpulse.orchestration.retry import apply_auto_disable, run_with_retry
from brandpulse.orchestration.state import NON_KEYWORD_JOB_KEY, Checkpoint, Run, RunStateStore
from brandpulse.registry.source_registry import SourceRegistry


class Orchestrator:
    """Runs connectors against keywords, checkpointing after each page/batch."""

    def __init__(
        self,
        registry: SourceRegistry,
        state_store: RunStateStore,
        retry_config: RetryConfig,
        connectors: dict[str, BaseConnector],
        health_store: ConnectorHealthStore,
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> None:
        self._registry = registry
        self._state_store = state_store
        self._retry_config = retry_config
        self._connectors = connectors
        self._health_store = health_store
        self._sleep_fn = sleep_fn
        self._logger = get_logger()

    def run(self, run: Run) -> Run:
        """Execute every job for this run.

        Connectors with ``collection_scope="keyword"`` get one job per
        configured keyword (the classic case). Connectors with any other
        scope (Google Play's ``"app"``, etc.) get exactly one job for the
        whole run — keywords don't apply to how they collect, so spawning
        one job per keyword would just re-walk identical data redundantly.

        A job already checkpointed ``exhausted`` is skipped entirely, so
        calling ``run`` again with the same ``run.run_id`` resumes rather
        than re-fetching work that already completed pagination.
        """
        jobs = []
        for source in self._registry.enabled_sources():
            connector = self._connectors.get(source.name)
            if connector is not None and connector.collection_scope != "keyword":
                jobs.append(Job(source_name=source.name, search_term=NON_KEYWORD_JOB_KEY))
            else:
                jobs.extend(Job(source_name=source.name, search_term=term) for term in run.keywords)

        queue: JobQueue[None] = JobQueue(max_workers=4)
        queue.run(jobs, lambda job: self._run_job(run, job))
        return run

    def _run_job(self, run: Run, job: Job) -> None:
        connector = self._connectors.get(job.source_name)
        if connector is None:
            return

        connector_state = run.connector_state_for(job.source_name)
        checkpoint = connector_state.checkpoint_for(job.search_term)

        if checkpoint.exhausted:
            # Already fully paginated for this (connector, keyword) — a
            # restart resumes past it instead of re-running the search.
            return

        log_event(
            self._logger,
            "connector_run_start",
            connector=job.source_name,
            search_term=job.search_term,
            run_id=run.run_id,
        )

        start_time = time.monotonic()
        total_records = 0
        final_status = RunStatus.NO_RESULTS
        final_reason: str | None = None
        auto_disabled = False

        search_keywords = [] if job.search_term == NON_KEYWORD_JOB_KEY else [job.search_term]

        while not checkpoint.exhausted:
            result = run_with_retry(
                search_fn=lambda: connector.search(
                    search_keywords, run.start, run.end, cursor=checkpoint.cursor
                ),
                retry_config=self._retry_config,
                sleep_fn=self._sleep_fn,
            )
            final_status = result.status
            final_reason = result.reason

            if result.status == RunStatus.FAILED:
                auto_disabled = apply_auto_disable(
                    self._registry, self._health_store, job.source_name, run_failed=True
                )
                break

            apply_auto_disable(
                self._registry, self._health_store, job.source_name, run_failed=False
            )
            self._checkpoint_page(run, checkpoint, result)
            total_records += len(result.records)

            if result.status in (RunStatus.NO_RESULTS, RunStatus.PARTIAL_SUCCESS):
                break

            if result.next_cursor is None:
                checkpoint.exhausted = True
                self._state_store.save(run)
                break

        log_event(
            self._logger,
            "connector_run_end",
            connector=job.source_name,
            search_term=job.search_term,
            run_id=run.run_id,
            status=final_status.value,
            duration_s=round(time.monotonic() - start_time, 3),
            result_count=total_records,
            reason=final_reason,
            auto_disabled=auto_disabled,
        )

    def _checkpoint_page(self, run: Run, checkpoint: Checkpoint, result: RunResult) -> None:
        checkpoint.last_batch_index += 1
        checkpoint.records_written += len(result.records)
        checkpoint.cursor = result.next_cursor
        checkpoint.last_successful_timestamp = datetime.now(run.start.tzinfo)
        self._state_store.save(run)
