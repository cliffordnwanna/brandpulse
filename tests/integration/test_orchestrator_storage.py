"""Integration tests: orchestrator writes through to Bronze/Silver (Milestone 4)."""

from datetime import UTC, datetime
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
from brandpulse.orchestration.connector_health import JSONConnectorHealthStore
from brandpulse.orchestration.orchestrator import Orchestrator
from brandpulse.orchestration.state import RunStateStore
from brandpulse.registry.source_registry import SourceRegistry
from brandpulse.storage.local import LocalFileStorageBackend
from tests.fixtures.stub_connectors.stub_connector import StubConnector


def _config() -> Config:
    return Config(
        sources=[SourceConfig(name="stub_source", enabled=True, reliability="high")],
        keywords=KeywordsConfig(base_list=["Wema"]),
        output=OutputConfig(directory="./output/", formats=["csv"]),
        retry=RetryConfig(max_attempts=3, backoff_seconds=[0, 0, 0]),
        timeouts=TimeoutsConfig(request_seconds=20),
        rate_limit=RateLimitConfig(requests_per_minute=6000, respect_robots_txt=False),
    )


def test_orchestrator_writes_normalized_records_to_bronze(tmp_path: Path):
    state_store = RunStateStore(tmp_path / "state")
    health_store = JSONConnectorHealthStore(tmp_path / "connector_health.json")
    storage_backend = LocalFileStorageBackend(tmp_path / "storage")
    registry = SourceRegistry(_config())
    stub = StubConnector(batches=[[{"id": "1", "text": "great app"}]])

    run = state_store.load_or_create(
        "run-1", ["Wema"], datetime(2026, 1, 1, tzinfo=UTC), datetime(2026, 1, 31, tzinfo=UTC)
    )
    orchestrator = Orchestrator(
        registry, state_store, _config().retry, {"stub_source": stub}, health_store, storage_backend
    )
    orchestrator.run(run)

    bronze_records = list(storage_backend.read_all("bronze"))
    assert len(bronze_records) == 1
    assert bronze_records[0]["text"] == "great app"
    assert bronze_records[0]["raw_json"] == "{}"  # never stripped


def test_orchestrator_writes_through_to_silver_with_language_tagged(tmp_path: Path):
    state_store = RunStateStore(tmp_path / "state")
    health_store = JSONConnectorHealthStore(tmp_path / "connector_health.json")
    storage_backend = LocalFileStorageBackend(tmp_path / "storage")
    registry = SourceRegistry(_config())
    stub = StubConnector(batches=[[{"id": "1", "text": "This app dey stress me well well."}]])

    run = state_store.load_or_create(
        "run-1", ["Wema"], datetime(2026, 1, 1, tzinfo=UTC), datetime(2026, 1, 31, tzinfo=UTC)
    )
    orchestrator = Orchestrator(
        registry, state_store, _config().retry, {"stub_source": stub}, health_store, storage_backend
    )
    orchestrator.run(run)

    silver_records = list(storage_backend.read_all("silver"))
    assert len(silver_records) == 1
    assert silver_records[0]["language"] == "pcm"


def test_duplicated_input_produces_exactly_one_silver_record(tmp_path: Path):
    """A deliberately duplicated input (same text, different mention_id via
    different source item id) run through the full pipeline must still
    produce exactly one Silver record — Silver-level cross-run dedup."""
    state_store = RunStateStore(tmp_path / "state")
    health_store = JSONConnectorHealthStore(tmp_path / "connector_health.json")
    storage_backend = LocalFileStorageBackend(tmp_path / "storage")
    registry = SourceRegistry(_config())
    stub = StubConnector(
        batches=[
            [
                {"id": "1", "text": "Great app, easy transfers!"},
                {"id": "2", "text": "Great app, easy transfers!"},
            ]
        ]
    )

    run = state_store.load_or_create(
        "run-1", ["Wema"], datetime(2026, 1, 1, tzinfo=UTC), datetime(2026, 1, 31, tzinfo=UTC)
    )
    orchestrator = Orchestrator(
        registry, state_store, _config().retry, {"stub_source": stub}, health_store, storage_backend
    )
    orchestrator.run(run)

    bronze_records = list(storage_backend.read_all("bronze"))
    silver_records = list(storage_backend.read_all("silver"))

    assert len(bronze_records) == 2  # both distinct mention_ids reach Bronze
    assert len(silver_records) == 1  # but only one distinct-text Silver record
