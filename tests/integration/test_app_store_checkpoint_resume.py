"""Integration test: orchestrator checkpoint/resume against AppStoreConnector
specifically (Milestone 7 acceptance criterion — kill mid-pagination, restart,
confirm no re-fetch of completed pages). No live network calls: requests.get
is monkeypatched to a deterministic page sequence.

App Store is not keyword-scoped (bounded entity, same as Google Play): the
orchestrator gives it exactly one job per run, checkpointed under
NON_KEYWORD_JOB_KEY, not one per keyword.
"""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from brandpulse.config.models import (
    AppStoreConfig,
    Config,
    ConnectorsConfig,
    KeywordsConfig,
    OutputConfig,
    RateLimitConfig,
    RetryConfig,
    SourceConfig,
    TimeoutsConfig,
)
from brandpulse.connectors.app_store import AppStoreConnector
from brandpulse.orchestration.connector_health import JSONConnectorHealthStore
from brandpulse.orchestration.orchestrator import Orchestrator
from brandpulse.orchestration.state import NON_KEYWORD_JOB_KEY, RunStateStore
from brandpulse.registry.source_registry import SourceRegistry
from brandpulse.storage.local import LocalFileStorageBackend
from tests.fixtures.app_store.sample_reviews import SAMPLE_REVIEW_NEGATIVE, SAMPLE_REVIEW_POSITIVE


def _config() -> Config:
    return Config(
        sources=[SourceConfig(name="app_store", enabled=True, reliability="high")],
        keywords=KeywordsConfig(base_list=["Wema"]),
        output=OutputConfig(directory="./output/", formats=["csv"]),
        retry=RetryConfig(max_attempts=3, backoff_seconds=[0, 0, 0]),
        timeouts=TimeoutsConfig(request_seconds=20),
        rate_limit=RateLimitConfig(requests_per_minute=6000, respect_robots_txt=False),
        connectors=ConnectorsConfig(app_store=AppStoreConfig(app_ids=["1222853161"])),
    )


class _FakeResponse:
    def __init__(self, entries: list[dict]):
        self._entries = entries

    def raise_for_status(self):
        pass

    def json(self):
        return {"feed": {"entry": self._entries}}


def _paged_get(pages: list[list[dict]]):
    """Fake requests.get(feed_url, ...) that returns page N's entries based
    on the ``page=N`` segment embedded in the URL."""

    def _fake(url, headers=None, timeout=None):
        import re

        match = re.search(r"page=(\d+)", url)
        page_num = int(match.group(1)) if match else 1
        page_index = page_num - 1
        entries = pages[page_index] if page_index < len(pages) else []
        return _FakeResponse(entries)

    return _fake


def _make_connector(health_store: JSONConnectorHealthStore) -> AppStoreConnector:
    return AppStoreConnector(
        config=_config().connectors.app_store,
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

    pages = [[SAMPLE_REVIEW_POSITIVE], [SAMPLE_REVIEW_NEGATIVE], []]
    real_get = _paged_get(pages)
    call_count = 0

    def _counting_get(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        return real_get(*args, **kwargs)

    monkeypatch.setattr("brandpulse.connectors.app_store.requests.get", _counting_get)

    connector = _make_connector(health_store)
    run = state_store.load_or_create("run-1", ["Wema"], start, end)
    orchestrator = Orchestrator(
        registry,
        state_store,
        _config().retry,
        {"app_store": connector},
        health_store,
        storage_backend,
    )
    orchestrator.run(run)

    checkpoint = run.connector_state_for("app_store").checkpoint_for(NON_KEYWORD_JOB_KEY)
    assert checkpoint.exhausted is True
    assert checkpoint.records_written == 2
    assert call_count == 3  # all 3 pages fetched exactly once

    # Simulate restart: fresh connector/orchestrator instance, same run_id and state dir.
    resumed_run = state_store.load_or_create("run-1", ["Wema"], start, end)
    fresh_connector = _make_connector(health_store)
    resumed_orchestrator = Orchestrator(
        registry,
        state_store,
        _config().retry,
        {"app_store": fresh_connector},
        health_store,
        storage_backend,
    )
    resumed_orchestrator.run(resumed_run)

    resumed_checkpoint = resumed_run.connector_state_for("app_store").checkpoint_for(
        NON_KEYWORD_JOB_KEY
    )
    assert resumed_checkpoint.records_written == 2
    assert call_count == 3  # unchanged — no additional fetch calls on resume
