"""Unit tests for GooglePlayConnector against saved fixture data (Milestone 3).

No live calls — fixture-based per Engineering Design §20's unit test guidance.

Collection is NOT keyword-filtered (corrected after initial review — see
module docstring in google_play.py): the connector fetches all reviews for
the configured app_ids and tags them with collection_scope="app" /
collection_target=<app_id>. Relevance/keyword matching is a downstream
(Silver/classification) concern, not a connector concern.
"""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from brandpulse.config.models import GooglePlayConfig, RateLimitConfig
from brandpulse.connectors.google_play import GooglePlayConnector, _clean_text
from brandpulse.orchestration.connector_health import JSONConnectorHealthStore
from tests.fixtures.google_play.sample_reviews import (
    SAMPLE_REVIEW_DUPLICATE_TEXT,
    SAMPLE_REVIEW_NEGATIVE,
    SAMPLE_REVIEW_POSITIVE,
)


@pytest.fixture
def connector(tmp_path: Path) -> GooglePlayConnector:
    health_store = JSONConnectorHealthStore(tmp_path / "connector_health.json")
    return GooglePlayConnector(
        config=GooglePlayConfig(app_ids=["com.example.wema"]),
        rate_limit_config=RateLimitConfig(requests_per_minute=6000, respect_robots_txt=False),
        health_store=health_store,
    )


def test_clean_text_collapses_whitespace_and_strips_control_chars():
    dirty = "Great app,   easy transfers with ALAT!  \x00\x01"
    cleaned = _clean_text(dirty)
    assert cleaned == "Great app, easy transfers with ALAT!"
    assert "\x00" not in cleaned


def test_clean_text_never_rewrites_content_semantically():
    """Bronze normalization only touches whitespace/control chars, never wording."""
    text = "Wema fraud alert - my transfer failed"
    assert _clean_text(text) == text


def test_normalize_produces_mention_matching_canonical_schema(connector: GooglePlayConnector):
    raw_item = {"raw": SAMPLE_REVIEW_POSITIVE, "app_id": "com.example.wema"}
    mention = connector.normalize(raw_item)

    assert mention.platform == "google_play"
    assert mention.source_type == "review"
    assert mention.collection_scope == "app"
    assert mention.collection_target == "com.example.wema"
    assert mention.search_term is None
    assert mention.author == "Ada O."
    assert mention.reliability == "high"
    assert mention.metadata["star_rating"] == 5
    assert "app_id" not in mention.metadata  # collection_target replaces it, not duplicated
    assert mention.language is None
    assert "\x00" not in mention.text


def test_normalize_preserves_raw_json_untouched(connector: GooglePlayConnector):
    raw_item = {"raw": SAMPLE_REVIEW_POSITIVE, "app_id": "com.example.wema"}
    mention = connector.normalize(raw_item)

    assert "\x00" in mention.raw_json or "\\u0000" in mention.raw_json


def test_validate_rejects_empty_text(connector: GooglePlayConnector):
    raw_item = {"raw": {**SAMPLE_REVIEW_POSITIVE, "content": ""}, "app_id": "com.example.wema"}
    mention = connector.normalize(raw_item)
    assert connector.validate(mention) is False


def test_validate_accepts_well_formed_mention(connector: GooglePlayConnector):
    raw_item = {"raw": SAMPLE_REVIEW_NEGATIVE, "app_id": "com.example.wema"}
    mention = connector.normalize(raw_item)
    assert connector.validate(mention) is True


def test_dedupe_batch_drops_same_author_and_text(connector: GooglePlayConnector):
    """Connector contract (§3): no exact duplicates within one batch —
    same (platform, author, text) tuple."""
    raws = [SAMPLE_REVIEW_NEGATIVE, SAMPLE_REVIEW_DUPLICATE_TEXT]

    deduped = connector._dedupe_batch(raws, "com.example.wema")

    assert len(deduped) == 1
    assert deduped[0]["reviewId"] == SAMPLE_REVIEW_NEGATIVE["reviewId"]


def test_search_does_not_filter_by_keyword(connector: GooglePlayConnector, monkeypatch):
    """Collection is unfiltered — a review that doesn't mention the passed
    'keyword' at all is still collected. Keyword relevance is a downstream
    concern, never a connector concern (corrected after initial review)."""
    monkeypatch.setattr(
        "brandpulse.connectors.google_play.fetch_reviews",
        lambda *a, **k: ([SAMPLE_REVIEW_POSITIVE], None),
    )
    result = connector.search(["this term matches nothing"], _distant_past(), _distant_future())

    assert result.status.value == "SUCCESS"
    assert len(result.records) == 1


def test_search_returns_no_results_when_no_app_ids_configured(tmp_path: Path):
    health_store = JSONConnectorHealthStore(tmp_path / "connector_health.json")
    empty_connector = GooglePlayConnector(
        config=GooglePlayConfig(app_ids=[]),
        rate_limit_config=RateLimitConfig(requests_per_minute=6000, respect_robots_txt=False),
        health_store=health_store,
    )

    result = empty_connector.search([], _distant_past(), _distant_future())

    assert result.status.value == "NO_RESULTS"


def test_search_returns_failed_on_app_not_found(connector: GooglePlayConnector, monkeypatch):
    from google_play_scraper.exceptions import NotFoundError

    def _raise(*args, **kwargs):
        raise NotFoundError()

    monkeypatch.setattr("brandpulse.connectors.google_play.fetch_reviews", _raise)
    result = connector.search([], _distant_past(), _distant_future())
    assert result.status.value == "FAILED"
    assert result.reason == "app_not_found"


def test_search_advances_cursor_to_next_app_once_first_app_exhausted(monkeypatch, tmp_path: Path):
    """Multi-app_ids: once app 0's pagination is exhausted, the cursor should
    move on to app 1 rather than reporting the whole job exhausted."""
    health_store = JSONConnectorHealthStore(tmp_path / "connector_health.json")
    multi_app_connector = GooglePlayConnector(
        config=GooglePlayConfig(app_ids=["com.example.wema", "com.example.alat"]),
        rate_limit_config=RateLimitConfig(requests_per_minute=6000, respect_robots_txt=False),
        health_store=health_store,
    )

    seen_app_ids = []

    def _fake_fetch(app_id, lang, country, sort, count, continuation_token=None):
        seen_app_ids.append(app_id)
        return [SAMPLE_REVIEW_POSITIVE], None  # exhausted after one page, always

    monkeypatch.setattr("brandpulse.connectors.google_play.fetch_reviews", _fake_fetch)

    first = multi_app_connector.search([], _distant_past(), _distant_future(), cursor=None)
    assert first.status.value == "SUCCESS"
    assert first.next_cursor is not None  # more apps remain

    second = multi_app_connector.search(
        [], _distant_past(), _distant_future(), cursor=first.next_cursor
    )
    assert second.status.value == "SUCCESS"
    assert second.next_cursor is None  # both apps now exhausted

    assert seen_app_ids == ["com.example.wema", "com.example.alat"]


def test_search_checks_robots_txt_before_fetching(tmp_path: Path, monkeypatch):
    """robots.txt is checked programmatically before the connector runs (§17)."""
    health_store = JSONConnectorHealthStore(tmp_path / "connector_health.json")
    connector_with_robots_check = GooglePlayConnector(
        config=GooglePlayConfig(app_ids=["com.example.wema"]),
        rate_limit_config=RateLimitConfig(requests_per_minute=6000, respect_robots_txt=True),
        health_store=health_store,
    )

    fetch_was_called = False

    def _fetch_should_not_be_called(*args, **kwargs):
        nonlocal fetch_was_called
        fetch_was_called = True
        return [], None

    monkeypatch.setattr(
        "brandpulse.connectors.google_play.fetch_reviews", _fetch_should_not_be_called
    )
    monkeypatch.setattr(
        "brandpulse.connectors.google_play.is_allowed_by_robots_txt", lambda url, ua: False
    )

    result = connector_with_robots_check.search([], _distant_past(), _distant_future())

    assert result.status.value == "FAILED"
    assert result.reason == "disallowed_by_robots_txt"
    assert fetch_was_called is False


def _distant_past() -> datetime:
    return datetime(2000, 1, 1, tzinfo=UTC)


def _distant_future() -> datetime:
    return datetime(2100, 1, 1, tzinfo=UTC)
