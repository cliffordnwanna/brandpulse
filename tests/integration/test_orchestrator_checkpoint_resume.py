"""Integration tests: orchestrator checkpoint/resume and auto-disable end-to-end.

Uses the StubConnector (tests/fixtures/stub_connectors) as the only connector
under test — never a real source, per Milestone 2 scope.
"""

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
from tests.fixtures.stub_connectors.stub_connector import StubConnector


def _config() -> Config:
    return Config(
        sources=[SourceConfig(name="stub_source", enabled=True, reliability="high")],
        keywords=KeywordsConfig(base_list=["Wema"]),
        output=OutputConfig(directory="./output/", formats=["csv"]),
        retry=RetryConfig(max_attempts=3, backoff_seconds=[0, 0, 0]),
        timeouts=TimeoutsConfig(request_seconds=20),
        rate_limit=RateLimitConfig(requests_per_minute=60, respect_robots_txt=True),
    )


def test_restart_resumes_from_checkpoint_without_reprocessing(tmp_path: Path):
    """A connector that 'crashes' after checkpointing must resume, not restart from zero."""
    start = datetime(2026, 1, 1, tzinfo=UTC)
    end = datetime(2026, 1, 31, tzinfo=UTC)
    state_store = RunStateStore(tmp_path / "state")
    health_store = JSONConnectorHealthStore(tmp_path / "connector_health.json")

    registry = SourceRegistry(_config())
    stub = StubConnector(batches=[[{"id": "1", "text": "great app"}]])

    run = state_store.load_or_create("run-1", ["Wema"], start, end)
    orchestrator = Orchestrator(
        registry, state_store, _config().retry, {"stub_source": stub}, health_store
    )
    orchestrator.run(run)

    checkpoint = run.connector_state_for("stub_source").checkpoint_for("Wema")
    assert checkpoint.last_batch_index == 0
    assert checkpoint.records_written == 1
    assert stub.call_count == 1

    # Simulate process restart: fresh Orchestrator/connector instance, same run_id.
    resumed_run = state_store.load_or_create("run-1", ["Wema"], start, end)
    fresh_stub = StubConnector(batches=[[{"id": "1", "text": "great app"}]])
    resumed_orchestrator = Orchestrator(
        registry, state_store, _config().retry, {"stub_source": fresh_stub}, health_store
    )
    resumed_orchestrator.run(resumed_run)

    # Already-checkpointed job must not be re-run against the fresh connector.
    assert fresh_stub.call_count == 0
    resumed_checkpoint = resumed_run.connector_state_for("stub_source").checkpoint_for("Wema")
    assert resumed_checkpoint.records_written == 1


def test_same_run_produces_same_mention_id_across_restarts(tmp_path: Path):
    """Idempotency proven end-to-end: normalizing the same raw item twice, across
    separate connector instances (simulating a restart), yields the same mention_id."""
    stub_first = StubConnector()
    stub_second = StubConnector()
    raw_item = {"id": "1", "text": "great app"}

    mention_first = stub_first.normalize(raw_item)
    mention_second = stub_second.normalize(raw_item)

    assert mention_first.mention_id == mention_second.mention_id


def test_three_consecutive_failed_runs_auto_disables_connector(tmp_path: Path):
    """The failure streak must survive across separate Run objects/run_ids —
    i.e. across separate scheduled runs, simulating separate process restarts,
    via a health store shared the same way it would be shared on disk."""
    start = datetime(2026, 1, 1, tzinfo=UTC)
    end = datetime(2026, 1, 31, tzinfo=UTC)
    registry = SourceRegistry(_config())
    health_store = JSONConnectorHealthStore(tmp_path / "connector_health.json")

    # Fails every single retry attempt (3 max_attempts) across 3 separate runs
    # => 9 calls total, but only 3 "scheduled run" failures should count.
    stub = StubConnector(fail_on_calls=set(range(1, 10)))

    for i in range(3):
        state_store = RunStateStore(tmp_path / f"state-{i}")
        run = state_store.load_or_create(f"run-{i}", ["Wema"], start, end)
        orchestrator = Orchestrator(
            registry, state_store, _config().retry, {"stub_source": stub}, health_store
        )
        orchestrator.run(run)

    assert registry.is_enabled("stub_source") is False


def test_success_between_failures_does_not_trigger_auto_disable(tmp_path: Path):
    start = datetime(2026, 1, 1, tzinfo=UTC)
    end = datetime(2026, 1, 31, tzinfo=UTC)
    registry = SourceRegistry(_config())
    health_store = JSONConnectorHealthStore(tmp_path / "connector_health.json")

    # Calls 1-3 fail (run 0's retries), call 4 succeeds (run 1), calls 5-7 fail (run 2's retries).
    stub = StubConnector(
        batches=[[{"id": "1", "text": "great app"}]],
        fail_on_calls={1, 2, 3, 5, 6, 7},
    )

    for i in range(3):
        state_store = RunStateStore(tmp_path / f"state-{i}")
        run = state_store.load_or_create(f"run-{i}", ["Wema"], start, end)
        orchestrator = Orchestrator(
            registry, state_store, _config().retry, {"stub_source": stub}, health_store
        )
        orchestrator.run(run)

    assert registry.is_enabled("stub_source") is True
