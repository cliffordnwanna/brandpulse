"""Unit tests for AppStoreConnector against saved fixture data (Milestone 7).

No live calls — fixture-based per Engineering Design §20's unit test
guidance (the connector was validated against the real, live App Store RSS
feed manually during development; see the module docstring in
``connectors/app_store.py`` for why that feed is used instead of the
``app-store-scraper`` PyPI package, which is broken against Apple's current
site).

Collection is NOT keyword-filtered, same pattern as Google Play: the
connector fetches all reviews for the configured numeric app_ids and tags
them with collection_scope="app" / collection_target=<app_id>.
"""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from brandpulse.config.models import AppStoreConfig, RateLimitConfig
from brandpulse.connectors.app_store import AppStoreConnector, _clean_text
from brandpulse.orchestration.connector_health import JSONConnectorHealthStore
from tests.fixtures.app_store.sample_reviews import SAMPLE_REVIEW_NEGATIVE, SAMPLE_REVIEW_POSITIVE


@pytest.fixture
def connector(tmp_path: Path) -> AppStoreConnector:
    health_store = JSONConnectorHealthStore(tmp_path / "connector_health.json")
    return AppStoreConnector(
        config=AppStoreConfig(app_ids=["1222853161"]),
        rate_limit_config=RateLimitConfig(requests_per_minute=6000, respect_robots_txt=False),
        health_store=health_store,
    )


class _FakeResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def _feed_response(entries: list[dict]) -> _FakeResponse:
    return _FakeResponse({"feed": {"entry": entries}})


def test_clean_text_collapses_whitespace_and_strips_control_chars():
    dirty = "Great app,   easy transfers with ALAT!  \x00\x01"
    cleaned = _clean_text(dirty)
    assert cleaned == "Great app, easy transfers with ALAT!"
    assert "\x00" not in cleaned


def test_normalize_produces_mention_matching_canonical_schema(connector: AppStoreConnector):
    raw_item = {
        "raw": SAMPLE_REVIEW_POSITIVE,
        "app_id": "1222853161",
        "app_page_url": "https://apps.apple.com/ng/app/id1222853161",
    }
    mention = connector.normalize(raw_item)

    assert mention.platform == "app_store"
    assert mention.source_type == "review"
    assert mention.collection_scope == "app"
    assert mention.collection_target == "1222853161"
    assert mention.search_term is None
    assert mention.author == "Ada O."
    assert mention.reliability == "high"
    assert mention.metadata["star_rating"] == "5"
    assert mention.language is None
    assert "\x00" not in mention.text


def test_validate_rejects_empty_text(connector: AppStoreConnector):
    empty_review = {
        **SAMPLE_REVIEW_POSITIVE,
        "content": {"label": "", "attributes": {"type": "text"}},
    }
    raw_item = {
        "raw": empty_review,
        "app_id": "1222853161",
        "app_page_url": "https://apps.apple.com/ng/app/id1222853161",
    }
    mention = connector.normalize(raw_item)
    assert connector.validate(mention) is False


def test_validate_accepts_well_formed_mention(connector: AppStoreConnector):
    raw_item = {
        "raw": SAMPLE_REVIEW_NEGATIVE,
        "app_id": "1222853161",
        "app_page_url": "https://apps.apple.com/ng/app/id1222853161",
    }
    mention = connector.normalize(raw_item)
    assert connector.validate(mention) is True


def test_search_does_not_filter_by_keyword(connector: AppStoreConnector, monkeypatch):
    """Collection is unfiltered — keywords are accepted but ignored (bounded
    entity, same as Google Play)."""
    monkeypatch.setattr(
        "brandpulse.connectors.app_store.requests.get",
        lambda *a, **k: _feed_response([SAMPLE_REVIEW_POSITIVE]),
    )

    result_no_kw = connector.search([], _distant_past(), _distant_future())
    result_with_kw = connector.search(
        ["this term matches nothing"], _distant_past(), _distant_future(), cursor=None
    )

    assert result_no_kw.status.value == "SUCCESS"
    assert len(result_no_kw.records) == 1
    assert [r["raw"]["id"]["label"] for r in result_no_kw.records] == [
        r["raw"]["id"]["label"] for r in result_with_kw.records
    ]


def test_search_returns_no_results_when_no_app_ids_configured(tmp_path: Path):
    health_store = JSONConnectorHealthStore(tmp_path / "connector_health.json")
    empty_connector = AppStoreConnector(
        config=AppStoreConfig(app_ids=[]),
        rate_limit_config=RateLimitConfig(requests_per_minute=6000, respect_robots_txt=False),
        health_store=health_store,
    )

    result = empty_connector.search([], _distant_past(), _distant_future())

    assert result.status.value == "NO_RESULTS"


def test_search_returns_failed_on_non_json_response(connector: AppStoreConnector, monkeypatch):
    class _BrokenResponse:
        def raise_for_status(self):
            pass

        def json(self):
            raise ValueError("Expecting value: line 1 column 1 (char 0)")

    monkeypatch.setattr(
        "brandpulse.connectors.app_store.requests.get", lambda *a, **k: _BrokenResponse()
    )
    result = connector.search([], _distant_past(), _distant_future())
    assert result.status.value == "FAILED"


def test_search_advances_cursor_to_next_page_within_same_app(connector: AppStoreConnector, monkeypatch):
    monkeypatch.setattr(
        "brandpulse.connectors.app_store.requests.get",
        lambda *a, **k: _feed_response([SAMPLE_REVIEW_POSITIVE]),
    )

    result = connector.search([], _distant_past(), _distant_future(), cursor=None)

    assert result.status.value == "SUCCESS"
    assert result.next_cursor is not None
    import json

    cursor_data = json.loads(result.next_cursor)
    assert cursor_data == {"app_index": 0, "page": 2}


def test_search_advances_cursor_to_next_app_once_first_app_exhausted(monkeypatch, tmp_path: Path):
    """Multi-app_ids: once app 0's pagination is exhausted (empty page),
    cursor should move on to app 1 rather than reporting the whole job done."""
    health_store = JSONConnectorHealthStore(tmp_path / "connector_health.json")
    multi_app_connector = AppStoreConnector(
        config=AppStoreConfig(app_ids=["1222853161", "1582348672"]),
        rate_limit_config=RateLimitConfig(requests_per_minute=6000, respect_robots_txt=False),
        health_store=health_store,
    )

    seen_urls = []

    def _fake_get(url, headers=None, timeout=None):
        seen_urls.append(url)
        return _feed_response([])  # empty -> exhausted immediately for each app

    monkeypatch.setattr("brandpulse.connectors.app_store.requests.get", _fake_get)

    first = multi_app_connector.search([], _distant_past(), _distant_future(), cursor=None)
    assert first.status.value == "SUCCESS"
    assert first.next_cursor is not None  # more apps remain

    second = multi_app_connector.search(
        [], _distant_past(), _distant_future(), cursor=first.next_cursor
    )
    assert second.status.value == "SUCCESS"
    assert second.next_cursor is None  # both apps now exhausted

    assert "1222853161" in seen_urls[0]
    assert "1582348672" in seen_urls[1]


def test_search_checks_robots_txt_before_fetching(tmp_path: Path, monkeypatch):
    """robots.txt is checked programmatically before the connector runs (§17)."""
    health_store = JSONConnectorHealthStore(tmp_path / "connector_health.json")
    connector_with_robots_check = AppStoreConnector(
        config=AppStoreConfig(app_ids=["1222853161"]),
        rate_limit_config=RateLimitConfig(requests_per_minute=6000, respect_robots_txt=True),
        health_store=health_store,
    )

    fetch_was_called = False

    def _fetch_should_not_be_called(*args, **kwargs):
        nonlocal fetch_was_called
        fetch_was_called = True
        return _feed_response([])

    monkeypatch.setattr("brandpulse.connectors.app_store.requests.get", _fetch_should_not_be_called)
    monkeypatch.setattr(
        "brandpulse.connectors.app_store.is_allowed_by_robots_txt", lambda url, ua: False
    )

    result = connector_with_robots_check.search([], _distant_past(), _distant_future())

    assert result.status.value == "FAILED"
    assert result.reason == "disallowed_by_robots_txt"
    assert fetch_was_called is False


def test_idempotent_mention_id_for_same_raw_item(connector: AppStoreConnector):
    raw_item = {
        "raw": SAMPLE_REVIEW_POSITIVE,
        "app_id": "1222853161",
        "app_page_url": "https://apps.apple.com/ng/app/id1222853161",
    }
    m1 = connector.normalize(raw_item)
    m2 = connector.normalize(raw_item)
    assert m1.mention_id == m2.mention_id


def _distant_past() -> datetime:
    return datetime(2000, 1, 1, tzinfo=UTC)


def _distant_future() -> datetime:
    return datetime(2100, 1, 1, tzinfo=UTC)
