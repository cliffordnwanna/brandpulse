"""Unit tests for YouTubeConnector against saved fixture data (Milestone 7).

No live calls — fixture-based per Engineering Design §20's unit test
guidance. The connector was validated against the real, live YouTube Data
API v3 manually during development (search, comment/reply fetching,
pagination/exhaustion, missing-key handling, idempotency — all confirmed
against a real API key).
"""

from datetime import UTC, datetime
from pathlib import Path

import pytest
from googleapiclient.errors import HttpError

from brandpulse.config.models import RateLimitConfig, YouTubeConfig
from brandpulse.connectors.youtube import YOUTUBE_API_KEY_ENV_VAR, YouTubeConnector, _clean_text
from brandpulse.orchestration.connector_health import JSONConnectorHealthStore
from tests.fixtures.youtube.sample_responses import (
    SAMPLE_COMMENT_THREADS_RESPONSE,
    SAMPLE_COMMENT_THREADS_RESPONSE_NO_REPLIES,
    SAMPLE_EMPTY_COMMENT_THREADS_RESPONSE,
    SAMPLE_EMPTY_SEARCH_RESPONSE,
    SAMPLE_SEARCH_RESPONSE,
)


class _FakeExecutable:
    def __init__(self, payload):
        self._payload = payload

    def execute(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class _FakeListEndpoint:
    def __init__(self, responses):
        # responses: list of payloads, consumed in order across successive .list() calls
        self._responses = list(responses)
        self.calls = []

    def list(self, **kwargs):
        self.calls.append(kwargs)
        payload = self._responses.pop(0) if self._responses else {"items": []}
        return _FakeExecutable(payload)


class _FakeYouTubeClient:
    def __init__(self, search_responses, comment_responses):
        self.search_endpoint = _FakeListEndpoint(search_responses)
        self.comments_endpoint = _FakeListEndpoint(comment_responses)

    def search(self):
        return self.search_endpoint

    def commentThreads(self):
        return self.comments_endpoint


def _connector_with_fake_client(
    tmp_path: Path, search_responses, comment_responses, config: YouTubeConfig | None = None
) -> tuple[YouTubeConnector, _FakeYouTubeClient]:
    health_store = JSONConnectorHealthStore(tmp_path / "connector_health.json")
    connector = YouTubeConnector(
        config=config or YouTubeConfig(max_videos_per_keyword=5, max_comments_per_video=20),
        rate_limit_config=RateLimitConfig(requests_per_minute=6000, respect_robots_txt=False),
        health_store=health_store,
        api_key="fake-key-for-tests",
    )
    fake_client = _FakeYouTubeClient(search_responses, comment_responses)
    connector._client = lambda: fake_client
    return connector, fake_client


def test_clean_text_collapses_whitespace():
    dirty = "Great app,   easy transfers!  \x00\x01"
    cleaned = _clean_text(dirty)
    assert cleaned == "Great app, easy transfers!"


def test_search_fetches_comments_and_replies(tmp_path: Path):
    connector, _ = _connector_with_fake_client(
        tmp_path, [SAMPLE_SEARCH_RESPONSE], [SAMPLE_COMMENT_THREADS_RESPONSE, {"items": []}]
    )
    result = connector.search(["Wema Bank"], _distant_past(), _distant_future())

    assert result.status.value == "SUCCESS"
    # top-level comment + its 1 reply
    assert len(result.records) == 2


def test_normalize_produces_mention_matching_canonical_schema(tmp_path: Path):
    connector, _ = _connector_with_fake_client(
        tmp_path, [SAMPLE_SEARCH_RESPONSE], [SAMPLE_COMMENT_THREADS_RESPONSE, {"items": []}]
    )
    result = connector.search(["Wema Bank"], _distant_past(), _distant_future())
    mention = connector.normalize(result.records[0])

    assert mention.platform == "youtube"
    assert mention.source_type == "comment"
    assert mention.collection_scope == "keyword"
    assert mention.search_term == "Wema Bank"
    assert mention.collection_target == "vid001"
    assert mention.author == "@Ada_O"
    assert "transfer failed" in mention.text.lower()
    assert mention.metadata["like_count"] == 5


def test_validate_rejects_empty_text(tmp_path: Path):
    connector, _ = _connector_with_fake_client(tmp_path, [SAMPLE_SEARCH_RESPONSE], [{"items": []}])
    empty_comment = {
        "id": "c1",
        "snippet": {"authorDisplayName": "x", "textDisplay": "", "publishedAt": "2026-01-01T00:00:00Z"},
    }
    mention = connector.normalize({"raw": empty_comment, "video_id": "vid001", "keyword": "Wema"})
    assert connector.validate(mention) is False


def test_search_no_keywords_returns_no_results(tmp_path: Path):
    connector, _ = _connector_with_fake_client(tmp_path, [], [])
    result = connector.search([], _distant_past(), _distant_future())
    assert result.status.value == "NO_RESULTS"


def test_search_no_videos_found_returns_no_results(tmp_path: Path):
    connector, _ = _connector_with_fake_client(tmp_path, [SAMPLE_EMPTY_SEARCH_RESPONSE], [])
    result = connector.search(["zzznonexistent"], _distant_past(), _distant_future())
    assert result.status.value == "NO_RESULTS"


def test_search_video_with_no_comments_is_skipped_gracefully(tmp_path: Path):
    """Videos with no comments matching the window are a valid NO_RESULTS
    outcome for that video, not a failure — the connector moves on."""
    connector, _ = _connector_with_fake_client(
        tmp_path, [SAMPLE_SEARCH_RESPONSE], [SAMPLE_EMPTY_COMMENT_THREADS_RESPONSE, {"items": []}]
    )
    result = connector.search(["Wema"], _distant_past(), _distant_future())
    # Falls through to video 2 in the same call since video 1 had no comments.
    assert result.status.value in ("SUCCESS", "NO_RESULTS")


def test_search_comments_disabled_skips_video(tmp_path: Path):
    """Comments disabled on a video is skipped gracefully, not a FAILED."""

    class _FakeHttpError(HttpError):
        def __init__(self):
            self.resp = type("Resp", (), {"status": 403})()
            self.error_details = [{"reason": "commentsDisabled"}]
            self.content = b"{}"

        def __str__(self):
            return "commentsDisabled"

    connector, fake_client = _connector_with_fake_client(
        tmp_path, [SAMPLE_SEARCH_RESPONSE], [_FakeHttpError(), SAMPLE_COMMENT_THREADS_RESPONSE]
    )
    result = connector.search(["Wema"], _distant_past(), _distant_future())

    assert result.status.value == "SUCCESS"
    assert len(result.records) == 2  # from the second video, whose comments succeeded


def test_search_quota_exhaustion_returns_partial_success(tmp_path: Path):
    """Quota exhaustion returns PARTIAL_SUCCESS with what was collected, not FAILED."""

    class _FakeQuotaError(HttpError):
        def __init__(self):
            self.resp = type("Resp", (), {"status": 403})()
            self.error_details = [{"reason": "quotaExceeded"}]
            self.content = b"{}"

        def __str__(self):
            return "quotaExceeded"

    connector, _ = _connector_with_fake_client(
        tmp_path, [SAMPLE_SEARCH_RESPONSE], [_FakeQuotaError()]
    )
    result = connector.search(["Wema"], _distant_past(), _distant_future())

    assert result.status.value == "PARTIAL_SUCCESS"
    assert result.reason == "quotaExceeded"


def test_search_missing_api_key_returns_failed_with_clear_message(tmp_path: Path, monkeypatch):
    monkeypatch.delenv(YOUTUBE_API_KEY_ENV_VAR, raising=False)
    health_store = JSONConnectorHealthStore(tmp_path / "connector_health.json")
    connector = YouTubeConnector(
        config=YouTubeConfig(),
        rate_limit_config=RateLimitConfig(requests_per_minute=6000, respect_robots_txt=False),
        health_store=health_store,
        api_key=None,
    )
    result = connector.search(["Wema"], _distant_past(), _distant_future())

    assert result.status.value == "FAILED"
    assert "YOUTUBE_API_KEY" in result.reason


def test_health_missing_api_key_reports_unhealthy_with_clear_message(tmp_path: Path, monkeypatch):
    monkeypatch.delenv(YOUTUBE_API_KEY_ENV_VAR, raising=False)
    health_store = JSONConnectorHealthStore(tmp_path / "connector_health.json")
    connector = YouTubeConnector(
        config=YouTubeConfig(),
        rate_limit_config=RateLimitConfig(requests_per_minute=6000, respect_robots_txt=False),
        health_store=health_store,
        api_key=None,
    )
    status = connector.health()
    assert status.healthy is False
    assert "YOUTUBE_API_KEY" in status.reason


def test_idempotent_mention_id_for_same_raw_item(tmp_path: Path):
    connector, _ = _connector_with_fake_client(
        tmp_path, [SAMPLE_SEARCH_RESPONSE], [SAMPLE_COMMENT_THREADS_RESPONSE_NO_REPLIES, {"items": []}]
    )
    result = connector.search(["Wema"], _distant_past(), _distant_future())
    m1 = connector.normalize(result.records[0])
    m2 = connector.normalize(result.records[0])
    assert m1.mention_id == m2.mention_id


def _distant_past() -> datetime:
    return datetime(2000, 1, 1, tzinfo=UTC)


def _distant_future() -> datetime:
    return datetime(2100, 1, 1, tzinfo=UTC)
