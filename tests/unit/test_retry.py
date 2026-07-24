"""Unit tests for retry policy and auto-disable (Engineering Design §6)."""

from pathlib import Path

from brandpulse.config.models import (
    Config,
    KeywordsConfig,
    OutputConfig,
    RateLimitConfig,
    RetryConfig,
    SourceConfig,
    TimeoutsConfig,
)
from brandpulse.connectors.base import RunResult, RunStatus
from brandpulse.orchestration.connector_health import JSONConnectorHealthStore
from brandpulse.orchestration.retry import apply_auto_disable, run_with_retry
from brandpulse.registry.source_registry import SourceRegistry


def _retry_config() -> RetryConfig:
    return RetryConfig(max_attempts=3, backoff_seconds=[0, 0, 0])


def _registry_with(source_name: str) -> SourceRegistry:
    config = Config(
        sources=[SourceConfig(name=source_name, enabled=True, reliability="high")],
        keywords=KeywordsConfig(base_list=["Wema"]),
        output=OutputConfig(directory="./output/", formats=["csv"]),
        retry=_retry_config(),
        timeouts=TimeoutsConfig(request_seconds=20),
        rate_limit=RateLimitConfig(requests_per_minute=60, respect_robots_txt=True),
    )
    return SourceRegistry(config)


def test_no_results_is_never_retried():
    call_count = 0

    def search_fn() -> RunResult:
        nonlocal call_count
        call_count += 1
        return RunResult(status=RunStatus.NO_RESULTS, records=[])

    result = run_with_retry(search_fn, _retry_config(), sleep_fn=lambda _: None)

    assert result.status == RunStatus.NO_RESULTS
    assert call_count == 1


def test_failed_retries_up_to_max_attempts():
    call_count = 0

    def search_fn() -> RunResult:
        nonlocal call_count
        call_count += 1
        return RunResult(status=RunStatus.FAILED, records=[], reason="timeout")

    result = run_with_retry(search_fn, _retry_config(), sleep_fn=lambda _: None)

    assert result.status == RunStatus.FAILED
    assert call_count == 3


def test_success_after_failures_returns_success():
    attempts = [RunStatus.FAILED, RunStatus.FAILED, RunStatus.SUCCESS]

    def search_fn() -> RunResult:
        return RunResult(status=attempts.pop(0), records=[])

    result = run_with_retry(search_fn, _retry_config(), sleep_fn=lambda _: None)

    assert result.status == RunStatus.SUCCESS


def test_consecutive_run_failures_trigger_auto_disable(tmp_path: Path):
    """3 consecutive *scheduled runs* failing (not 3 in-run retries) should auto-disable."""
    registry = _registry_with("google_play")
    health_store = JSONConnectorHealthStore(tmp_path / "connector_health.json")

    for _ in range(3):
        apply_auto_disable(registry, health_store, "google_play", run_failed=True)

    assert registry.is_enabled("google_play") is False
    assert "google_play" not in {s.name for s in registry.enabled_sources()}


def test_fewer_than_threshold_failures_does_not_disable(tmp_path: Path):
    registry = _registry_with("google_play")
    health_store = JSONConnectorHealthStore(tmp_path / "connector_health.json")

    for _ in range(2):
        apply_auto_disable(registry, health_store, "google_play", run_failed=True)

    assert registry.is_enabled("google_play") is True


def test_success_resets_failure_streak(tmp_path: Path):
    registry = _registry_with("google_play")
    health_store = JSONConnectorHealthStore(tmp_path / "connector_health.json")

    apply_auto_disable(registry, health_store, "google_play", run_failed=True)
    apply_auto_disable(registry, health_store, "google_play", run_failed=True)
    apply_auto_disable(registry, health_store, "google_play", run_failed=False)
    apply_auto_disable(registry, health_store, "google_play", run_failed=True)
    apply_auto_disable(registry, health_store, "google_play", run_failed=True)

    assert registry.is_enabled("google_play") is True
