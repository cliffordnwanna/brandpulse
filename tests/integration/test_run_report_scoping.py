"""Integration tests for RunReport.mention_ids tracking and session-scoped
classification (Milestone 6's "snapshot" mode building block).
"""

from datetime import UTC, datetime
from pathlib import Path

from brandpulse.config.models import (
    ClassificationConfig,
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
from brandpulse.orchestration.run_report import RunReport
from brandpulse.orchestration.state import RunStateStore
from brandpulse.pipeline.run_classification import run_classification
from brandpulse.registry.source_registry import SourceRegistry
from brandpulse.storage.local import LocalFileStorageBackend
from tests.fixtures.seed_silver import seed_silver_record
from tests.fixtures.stub_connectors.stub_connector import StubConnector


def _config(tmp_path: Path) -> Config:
    return Config(
        sources=[SourceConfig(name="stub_source", enabled=True, reliability="high")],
        keywords=KeywordsConfig(base_list=["Wema"]),
        output=OutputConfig(directory=str(tmp_path / "output"), formats=["csv"]),
        retry=RetryConfig(max_attempts=3, backoff_seconds=[0, 0, 0]),
        timeouts=TimeoutsConfig(request_seconds=20),
        rate_limit=RateLimitConfig(requests_per_minute=6000, respect_robots_txt=False),
        classification=ClassificationConfig(enable_enrichment=False),
    )


def test_run_report_tracks_mention_ids_written_this_run(tmp_path: Path):
    state_store = RunStateStore(tmp_path / "state")
    health_store = JSONConnectorHealthStore(tmp_path / "connector_health.json")
    storage_backend = LocalFileStorageBackend(tmp_path / "storage")
    config = _config(tmp_path)
    registry = SourceRegistry(config)
    stub = StubConnector(
        batches=[[{"id": "1", "text": "great app"}, {"id": "2", "text": "bad app"}]]
    )
    run_report = RunReport()

    orchestrator = Orchestrator(
        registry,
        state_store,
        config.retry,
        {"stub_source": stub},
        health_store,
        storage_backend,
        run_report=run_report,
    )
    run = state_store.load_or_create(
        "run-1", ["Wema"], datetime(2026, 1, 1, tzinfo=UTC), datetime(2026, 1, 31, tzinfo=UTC)
    )
    orchestrator.run(run)

    assert run_report.mention_ids == {"stub-1", "stub-2"}


def test_run_classification_session_scoping_excludes_older_gold(tmp_path: Path):
    """Simulates snapshot mode: a second run's session summary should only
    reflect mention_ids collected in that run, not everything in Gold."""
    backend = LocalFileStorageBackend(tmp_path / "storage")
    config = _config(tmp_path)

    seed_silver_record(backend, "old-1", "old complaint from a prior run")
    seed_silver_record(backend, "new-1", "new complaint from this run")

    # First, classify everything cumulatively (simulating a prior run already covered old-1).
    run_classification(backend, config, run_id="prior-run")

    # Now simulate a snapshot run that only collected new-1.
    session_summary = run_classification(
        backend, config, run_id="snapshot-run", session_mention_ids={"new-1"}
    )

    assert session_summary["mention_counts_per_source"] == {"google_play": 1}
    assert session_summary["mention_ids"] == ["new-1"]

    # But Gold itself still has both — classification is cumulative even
    # though the session log is scoped.
    gold_records = list(backend.read_all("gold"))
    assert {r["mention_id"] for r in gold_records} == {"old-1", "new-1"}
