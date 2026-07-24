"""Unit tests for cross-run connector health tracking (Engineering Design §6)."""

from pathlib import Path

from brandpulse.orchestration.connector_health import JSONConnectorHealthStore


def test_unseen_connector_defaults_to_zero_failures(tmp_path: Path):
    store = JSONConnectorHealthStore(tmp_path / "health.json")
    assert store.get("google_play").consecutive_failures == 0


def test_record_result_increments_on_failure(tmp_path: Path):
    store = JSONConnectorHealthStore(tmp_path / "health.json")

    store.record_result("google_play", failed=True)
    health = store.record_result("google_play", failed=True)

    assert health.consecutive_failures == 2


def test_record_result_resets_on_success(tmp_path: Path):
    store = JSONConnectorHealthStore(tmp_path / "health.json")

    store.record_result("google_play", failed=True)
    store.record_result("google_play", failed=True)
    health = store.record_result("google_play", failed=False)

    assert health.consecutive_failures == 0


def test_health_persists_across_store_instances(tmp_path: Path):
    """A fresh process re-instantiating the store must see prior failure counts."""
    path = tmp_path / "health.json"
    JSONConnectorHealthStore(path).record_result("google_play", failed=True)

    reloaded = JSONConnectorHealthStore(path)

    assert reloaded.get("google_play").consecutive_failures == 1


def test_reset_clears_failure_streak(tmp_path: Path):
    store = JSONConnectorHealthStore(tmp_path / "health.json")
    store.record_result("google_play", failed=True)
    store.record_result("google_play", failed=True)

    store.reset("google_play")

    assert store.get("google_play").consecutive_failures == 0
