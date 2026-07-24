"""Retry policy and failure handling (Engineering Design §6).

Exponential backoff, max attempts, only for ``FAILED`` — never for
``NO_RESULTS``. A connector that fails ``max_attempts`` consecutive
scheduled runs is auto-disabled via the Source Registry.
"""

from __future__ import annotations

import time
from collections.abc import Callable

from brandpulse.config.models import RetryConfig
from brandpulse.connectors.base import RunResult, RunStatus
from brandpulse.orchestration.connector_health import ConnectorHealthStore
from brandpulse.registry.source_registry import SourceRegistry

AUTO_DISABLE_THRESHOLD = 3


def run_with_retry(
    search_fn: Callable[[], RunResult],
    retry_config: RetryConfig,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> RunResult:
    """Run ``search_fn``, retrying on ``FAILED`` per the exponential backoff policy.

    ``NO_RESULTS`` is never retried — it's a legitimate outcome, not a
    failure. This function only handles in-run retries; cross-run failure
    streaks (for the "3 consecutive scheduled runs" auto-disable rule) are
    tracked separately via ``ConnectorHealthStore`` — see ``apply_auto_disable``.
    """
    last_result: RunResult | None = None

    for attempt in range(retry_config.max_attempts):
        result = search_fn()
        last_result = result

        if result.status != RunStatus.FAILED:
            return result

        is_last_attempt = attempt == retry_config.max_attempts - 1
        if not is_last_attempt:
            backoff_index = min(attempt, len(retry_config.backoff_seconds) - 1)
            sleep_fn(retry_config.backoff_seconds[backoff_index])

    assert last_result is not None
    return last_result


def apply_auto_disable(
    registry: SourceRegistry,
    health_store: ConnectorHealthStore,
    source_name: str,
    run_failed: bool,
    threshold: int = AUTO_DISABLE_THRESHOLD,
) -> bool:
    """Record this scheduled run's outcome and disable the source if it's
    now failed ``threshold`` consecutive scheduled runs (Engineering Design §6).

    Returns True if the source is disabled after this call (whether newly
    disabled here or already disabled beforehand).
    """
    health = health_store.record_result(source_name, failed=run_failed)
    if health.consecutive_failures >= threshold:
        registry.disable(source_name)
        return True
    return registry.is_enabled(source_name) is False
