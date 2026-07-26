"""Integration test: orchestrator checkpoint/resume against YouTubeConnector
specifically (Milestone 7 acceptance criterion — kill mid-pagination, restart,
confirm no re-fetch of completed work). No live network calls.

YouTube IS keyword-scoped (``collection_scope="keyword"``) — the orchestrator
gives it one job per configured keyword, checkpointed under that keyword.
"""

from datetime import UTC, datetime
from pathlib import Path

from brandpulse.config.models import (
    Config,
    ConnectorsConfig,
    KeywordsConfig,
    OutputConfig,
    RateLimitConfig,
    RetryConfig,
    SourceConfig,
    TimeoutsConfig,
    YouTubeConfig,
)
from brandpulse.connectors.youtube import YouTubeConnector
from brandpulse.orchestration.connector_health import JSONConnectorHealthStore
from brandpulse.orchestration.orchestrator import Orchestrator
from brandpulse.orchestration.state import RunStateStore
from brandpulse.registry.source_registry import SourceRegistry
from brandpulse.storage.local import LocalFileStorageBackend
from tests.fixtures.youtube.sample_responses import (
    SAMPLE_COMMENT_THREADS_RESPONSE_NO_REPLIES,
    SAMPLE_SEARCH_RESPONSE,
)


def _config() -> Config:
    return Config(
        sources=[SourceConfig(name="youtube", enabled=True, reliability="high")],
        keywords=KeywordsConfig(base_list=["Wema"]),
        output=OutputConfig(directory="./output/", formats=["csv"]),
        retry=RetryConfig(max_attempts=3, backoff_seconds=[0, 0, 0]),
        timeouts=TimeoutsConfig(request_seconds=20),
        rate_limit=RateLimitConfig(requests_per_minute=6000, respect_robots_txt=False),
        connectors=ConnectorsConfig(
            youtube=YouTubeConfig(max_videos_per_keyword=2, max_comments_per_video=20)
        ),
    )


class _FakeExecutable:
    def __init__(self, payload):
        self._payload = payload

    def execute(self):
        return self._payload


class _FakeListEndpoint:
    def __init__(self, responses, on_call=None):
        self._responses = list(responses)
        self._on_call = on_call

    def list(self, **kwargs):
        if self._on_call:
            self._on_call()
        payload = self._responses.pop(0) if self._responses else {"items": []}
        return _FakeExecutable(payload)


class _FakeYouTubeClient:
    def __init__(self, search_responses, comment_responses, on_comment_call=None):
        self._search_endpoint = _FakeListEndpoint(search_responses)
        self._comments_endpoint = _FakeListEndpoint(comment_responses, on_call=on_comment_call)

    def search(self):
        return self._search_endpoint

    def commentThreads(self):
        return self._comments_endpoint


def _make_connector(
    health_store: JSONConnectorHealthStore, comment_call_counter: list[int]
) -> YouTubeConnector:
    connector = YouTubeConnector(
        config=_config().connectors.youtube,
        rate_limit_config=_config().rate_limit,
        health_store=health_store,
        api_key="fake-key-for-tests",
    )
    # 2 videos, each with one comment page (no replies), then exhausted.
    fake_client = _FakeYouTubeClient(
        [SAMPLE_SEARCH_RESPONSE],
        [
            SAMPLE_COMMENT_THREADS_RESPONSE_NO_REPLIES,
            SAMPLE_COMMENT_THREADS_RESPONSE_NO_REPLIES,
        ],
        on_comment_call=lambda: comment_call_counter.append(1),
    )
    connector._client = lambda: fake_client
    return connector


def test_restart_mid_pagination_resumes_without_refetching_completed_work(tmp_path: Path):
    start = datetime(2000, 1, 1, tzinfo=UTC)
    end = datetime(2100, 1, 1, tzinfo=UTC)
    state_store = RunStateStore(tmp_path / "state")
    health_store = JSONConnectorHealthStore(tmp_path / "connector_health.json")
    storage_backend = LocalFileStorageBackend(tmp_path / "storage")
    registry = SourceRegistry(_config())

    comment_calls: list[int] = []
    connector = _make_connector(health_store, comment_calls)

    run = state_store.load_or_create("run-1", ["Wema"], start, end)
    orchestrator = Orchestrator(
        registry,
        state_store,
        _config().retry,
        {"youtube": connector},
        health_store,
        storage_backend,
    )
    orchestrator.run(run)

    checkpoint = run.connector_state_for("youtube").checkpoint_for("Wema")
    assert checkpoint.exhausted is True
    assert checkpoint.records_written == 2  # one comment per video, 2 videos
    calls_after_first_run = len(comment_calls)

    # Simulate restart: fresh connector/orchestrator instance, same run_id and state dir.
    resumed_run = state_store.load_or_create("run-1", ["Wema"], start, end)
    fresh_connector = _make_connector(health_store, comment_calls)
    resumed_orchestrator = Orchestrator(
        registry,
        state_store,
        _config().retry,
        {"youtube": fresh_connector},
        health_store,
        storage_backend,
    )
    resumed_orchestrator.run(resumed_run)

    resumed_checkpoint = resumed_run.connector_state_for("youtube").checkpoint_for("Wema")
    assert resumed_checkpoint.records_written == 2
    assert len(comment_calls) == calls_after_first_run  # unchanged — no additional fetches
