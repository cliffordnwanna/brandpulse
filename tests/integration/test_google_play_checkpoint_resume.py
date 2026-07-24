"""Integration test: orchestrator checkpoint/resume against GooglePlayConnector
specifically (Milestone 3 acceptance criterion — kill mid-pagination, restart,
confirm no re-fetch of completed pages). No live network calls: fetch_reviews
is monkeypatched to a deterministic 3-page sequence.

Google Play is not keyword-scoped (corrected after initial review — see
GooglePlayConnector's module docstring): the orchestrator gives it exactly
one job per run, checkpointed under NON_KEYWORD_JOB_KEY, not one per keyword.
"""

from datetime import UTC, datetime
from pathlib import Path

import pytest
from google_play_scraper.features.reviews import _ContinuationToken

from brandpulse.config.models import (
    Config,
    ConnectorsConfig,
    GooglePlayConfig,
    KeywordsConfig,
    OutputConfig,
    RateLimitConfig,
    RetryConfig,
    SourceConfig,
    TimeoutsConfig,
)
from brandpulse.connectors.google_play import GooglePlayConnector
from brandpulse.orchestration.connector_health import JSONConnectorHealthStore
from brandpulse.orchestration.orchestrator import Orchestrator
from brandpulse.orchestration.state import NON_KEYWORD_JOB_KEY, RunStateStore
from brandpulse.registry.source_registry import SourceRegistry
from tests.fixtures.google_play.sample_reviews import SAMPLE_REVIEW_NEGATIVE, SAMPLE_REVIEW_POSITIVE


def _config() -> Config:
    return Config(
        sources=[SourceConfig(name="google_play", enabled=True, reliability="high")],
        keywords=KeywordsConfig(base_list=["Wema"]),
        output=OutputConfig(directory="./output/", formats=["csv"]),
        retry=RetryConfig(max_attempts=3, backoff_seconds=[0, 0, 0]),
        timeouts=TimeoutsConfig(request_seconds=20),
        rate_limit=RateLimitConfig(requests_per_minute=6000, respect_robots_txt=False),
        connectors=ConnectorsConfig(google_play=GooglePlayConfig(app_ids=["com.example.wema"])),
    )


def _paged_fetch_reviews(pages: list[list[dict]]):
    """Build a fake fetch_reviews(app_id, ..., continuation_token=None) that
    walks through `pages` one at a time, driven by an integer-encoded token."""

    def _fake(app_id, lang, country, sort, count, continuation_token=None):
        page_index = 0 if continuation_token is None else continuation_token.token
        page = pages[page_index]
        next_index = page_index + 1
        next_token = (
            _ContinuationToken(next_index, lang, country, sort, count, None, None)
            if next_index < len(pages)
            else _ContinuationToken(None, lang, country, sort, count, None, None)
        )
        return page, next_token

    return _fake


@pytest.fixture(autouse=True)
def _patch_fetch_reviews(monkeypatch):
    pages = [[SAMPLE_REVIEW_POSITIVE], [SAMPLE_REVIEW_NEGATIVE], []]
    monkeypatch.setattr(
        "brandpulse.connectors.google_play.fetch_reviews", _paged_fetch_reviews(pages)
    )


def _make_connector(tmp_path: Path, health_store: JSONConnectorHealthStore) -> GooglePlayConnector:
    return GooglePlayConnector(
        config=_config().connectors.google_play,
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
    registry = SourceRegistry(_config())

    pages = [[SAMPLE_REVIEW_POSITIVE], [SAMPLE_REVIEW_NEGATIVE], []]
    real_fetch = _paged_fetch_reviews(pages)
    call_count = 0

    def _counting_fetch(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        return real_fetch(*args, **kwargs)

    monkeypatch.setattr("brandpulse.connectors.google_play.fetch_reviews", _counting_fetch)

    connector = _make_connector(tmp_path, health_store)
    run = state_store.load_or_create("run-1", ["Wema"], start, end)
    orchestrator = Orchestrator(
        registry, state_store, _config().retry, {"google_play": connector}, health_store
    )
    orchestrator.run(run)

    checkpoint = run.connector_state_for("google_play").checkpoint_for(NON_KEYWORD_JOB_KEY)
    assert checkpoint.exhausted is True
    # All reviews across both non-empty pages are collected — no keyword filter.
    assert checkpoint.records_written == 2
    assert call_count == 3  # all 3 pages fetched exactly once

    # Simulate restart: fresh connector/orchestrator instance, same run_id and state dir.
    resumed_run = state_store.load_or_create("run-1", ["Wema"], start, end)
    fresh_connector = _make_connector(tmp_path, health_store)
    resumed_orchestrator = Orchestrator(
        registry, state_store, _config().retry, {"google_play": fresh_connector}, health_store
    )
    resumed_orchestrator.run(resumed_run)

    # Already exhausted — must not re-fetch any page at all.
    resumed_checkpoint = resumed_run.connector_state_for("google_play").checkpoint_for(
        NON_KEYWORD_JOB_KEY
    )
    assert resumed_checkpoint.records_written == 2
    assert call_count == 3  # unchanged — no additional fetch calls on resume


def test_mid_pagination_crash_resumes_from_last_checkpointed_cursor(tmp_path: Path, monkeypatch):
    """Simulates a crash after page 0 but before page 1 by running the
    orchestrator against a connector that raises on the 2nd fetch call, then
    restarting with a working connector — must resume from page 1, not page 0."""
    start = datetime(2000, 1, 1, tzinfo=UTC)
    end = datetime(2100, 1, 1, tzinfo=UTC)
    state_store = RunStateStore(tmp_path / "state")
    health_store = JSONConnectorHealthStore(tmp_path / "connector_health.json")
    registry = SourceRegistry(_config())

    pages = [[SAMPLE_REVIEW_POSITIVE], [SAMPLE_REVIEW_NEGATIVE], []]
    real_fetch = _paged_fetch_reviews(pages)
    calls_before_crash = 0
    calls_after_crash = 0

    def _crash_on_second_call(*args, **kwargs):
        nonlocal calls_before_crash
        calls_before_crash += 1
        if calls_before_crash == 2:
            raise RuntimeError("simulated crash")
        return real_fetch(*args, **kwargs)

    monkeypatch.setattr("brandpulse.connectors.google_play.fetch_reviews", _crash_on_second_call)

    connector = _make_connector(tmp_path, health_store)
    run = state_store.load_or_create("run-2", ["Wema"], start, end)
    orchestrator = Orchestrator(
        registry,
        state_store,
        RetryConfig(max_attempts=1, backoff_seconds=[0]),
        {"google_play": connector},
        health_store,
    )
    orchestrator.run(run)

    checkpoint = run.connector_state_for("google_play").checkpoint_for(NON_KEYWORD_JOB_KEY)
    assert checkpoint.exhausted is False
    # Page 0's review was successfully checkpointed before the crash on page 1's fetch call.
    assert checkpoint.records_written == 1
    assert checkpoint.cursor is not None

    # Restart with a fetch_reviews that works from here on, counting calls
    # from zero again so we can prove page 0 is never re-requested.
    def _counting_fetch(*args, **kwargs):
        nonlocal calls_after_crash
        calls_after_crash += 1
        return real_fetch(*args, **kwargs)

    monkeypatch.setattr("brandpulse.connectors.google_play.fetch_reviews", _counting_fetch)
    resumed_run = state_store.load_or_create("run-2", ["Wema"], start, end)
    fresh_connector = _make_connector(tmp_path, health_store)
    resumed_orchestrator = Orchestrator(
        registry, state_store, _config().retry, {"google_play": fresh_connector}, health_store
    )
    resumed_orchestrator.run(resumed_run)

    resumed_checkpoint = resumed_run.connector_state_for("google_play").checkpoint_for(
        NON_KEYWORD_JOB_KEY
    )
    assert resumed_checkpoint.exhausted is True
    assert resumed_checkpoint.records_written == 2
    # Only pages 1 and 2 are fetched on resume — page 0 (already checkpointed
    # before the crash) is never re-requested.
    assert calls_after_crash == 2


def test_only_one_job_is_created_for_a_non_keyword_scoped_connector(tmp_path: Path):
    """Google Play must get exactly one job for the whole run, not one per
    configured keyword — spawning N redundant jobs would re-walk identical
    app data N times for no benefit (the bug this test guards against)."""
    start = datetime(2000, 1, 1, tzinfo=UTC)
    end = datetime(2100, 1, 1, tzinfo=UTC)
    state_store = RunStateStore(tmp_path / "state")
    health_store = JSONConnectorHealthStore(tmp_path / "connector_health.json")
    registry = SourceRegistry(_config())

    connector = _make_connector(tmp_path, health_store)
    run = state_store.load_or_create("run-3", ["Wema", "ALAT", "Wema Bank", "fraud"], start, end)
    orchestrator = Orchestrator(
        registry, state_store, _config().retry, {"google_play": connector}, health_store
    )
    orchestrator.run(run)

    connector_state = run.connector_state_for("google_play")
    assert set(connector_state.checkpoints.keys()) == {NON_KEYWORD_JOB_KEY}


def test_idempotent_mention_id_holds_against_real_connector_normalize(tmp_path: Path):
    """Idempotency proven against this real connector: re-normalizing the same
    raw review, across separate connector instances, yields the same mention_id."""
    health_store = JSONConnectorHealthStore(tmp_path / "connector_health.json")
    connector_a = _make_connector(tmp_path, health_store)
    connector_b = _make_connector(tmp_path, health_store)

    raw_item = {"raw": SAMPLE_REVIEW_POSITIVE, "app_id": "com.example.wema"}

    mention_a = connector_a.normalize(raw_item)
    mention_b = connector_b.normalize(raw_item)

    assert mention_a.mention_id == mention_b.mention_id
