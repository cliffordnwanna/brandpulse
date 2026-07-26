"""Integration test: orchestrator checkpoint/resume against NairalandConnector
specifically (Milestone 7 acceptance criterion — kill mid-pagination, restart,
confirm no re-fetch of completed pages). No live network calls: requests.get
is monkeypatched to a deterministic page sequence.

Nairaland IS keyword-scoped (``collection_scope="forum"``, unlike Google
Play/App Store's bounded-entity scope) — the orchestrator gives it one job
per configured keyword, checkpointed under that keyword string.
"""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from brandpulse.config.models import (
    Config,
    ConnectorsConfig,
    KeywordsConfig,
    NairalandConfig,
    OutputConfig,
    RateLimitConfig,
    RetryConfig,
    SourceConfig,
    TimeoutsConfig,
)
from brandpulse.connectors.nairaland import NairalandConnector
from brandpulse.orchestration.connector_health import JSONConnectorHealthStore
from brandpulse.orchestration.orchestrator import Orchestrator
from brandpulse.orchestration.state import RunStateStore
from brandpulse.registry.source_registry import SourceRegistry
from brandpulse.storage.local import LocalFileStorageBackend
from tests.fixtures.nairaland.sample_search_page import (
    EMPTY_SEARCH_PAGE_HTML,
    SAMPLE_SEARCH_PAGE_HTML,
)


def _config() -> Config:
    return Config(
        sources=[SourceConfig(name="nairaland", enabled=True, reliability="medium")],
        keywords=KeywordsConfig(base_list=["Wema"]),
        output=OutputConfig(directory="./output/", formats=["csv"]),
        retry=RetryConfig(max_attempts=3, backoff_seconds=[0, 0, 0]),
        timeouts=TimeoutsConfig(request_seconds=20),
        rate_limit=RateLimitConfig(requests_per_minute=6000, respect_robots_txt=False),
        connectors=ConnectorsConfig(nairaland=NairalandConfig(max_pages=2)),
    )


class _FakeResponse:
    def __init__(self, text: str):
        self.text = text

    def raise_for_status(self):
        pass


def _make_connector(health_store: JSONConnectorHealthStore) -> NairalandConnector:
    return NairalandConnector(
        config=_config().connectors.nairaland,
        rate_limit_config=_config().rate_limit,
        health_store=health_store,
    )


def test_restart_mid_pagination_resumes_without_refetching_completed_pages(
    tmp_path: Path, monkeypatch
):
    start = datetime(2000, 1, 1, tzinfo=UTC)
    end = datetime(2100, 1, 1, tzinfo=UTC)
    state_store = RunStateStore(tmp_path / "state")
    health_store = JSONConnectorHealthStore(tmp_path / "connector_health.json")
    storage_backend = LocalFileStorageBackend(tmp_path / "storage")
    registry = SourceRegistry(_config())

    # page 1 has results, page 2 is empty -> exhausted after 2 fetches (max_pages=2 anyway)
    pages = [SAMPLE_SEARCH_PAGE_HTML, EMPTY_SEARCH_PAGE_HTML]
    call_count = 0

    def _counting_get(url, params=None, headers=None, timeout=None):
        nonlocal call_count
        page_index = call_count
        call_count += 1
        return _FakeResponse(pages[page_index] if page_index < len(pages) else EMPTY_SEARCH_PAGE_HTML)

    monkeypatch.setattr("brandpulse.connectors.nairaland.requests.get", _counting_get)

    connector = _make_connector(health_store)
    run = state_store.load_or_create("run-1", ["Wema"], start, end)
    orchestrator = Orchestrator(
        registry,
        state_store,
        _config().retry,
        {"nairaland": connector},
        health_store,
        storage_backend,
    )
    orchestrator.run(run)

    checkpoint = run.connector_state_for("nairaland").checkpoint_for("Wema")
    assert checkpoint.exhausted is True
    assert checkpoint.records_written == 2  # 2 posts from page 1, page 2 empty
    assert call_count == 2  # both pages fetched exactly once

    # Simulate restart: fresh connector/orchestrator instance, same run_id and state dir.
    resumed_run = state_store.load_or_create("run-1", ["Wema"], start, end)
    fresh_connector = _make_connector(health_store)
    resumed_orchestrator = Orchestrator(
        registry,
        state_store,
        _config().retry,
        {"nairaland": fresh_connector},
        health_store,
        storage_backend,
    )
    resumed_orchestrator.run(resumed_run)

    resumed_checkpoint = resumed_run.connector_state_for("nairaland").checkpoint_for("Wema")
    assert resumed_checkpoint.records_written == 2
    assert call_count == 2  # unchanged — no additional fetch calls on resume
