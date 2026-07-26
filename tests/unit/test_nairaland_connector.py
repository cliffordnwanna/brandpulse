"""Unit tests for NairalandConnector against saved fixture HTML (Milestone 7).

No live calls in the automated suite — fixture-based per Engineering Design
§20's unit test guidance. The connector itself was validated against the
real, live nairaland.com search endpoint manually during development (see
module docstring in connectors/nairaland.py): static HTML, no JavaScript
required, robots.txt is Cloudflare-challenged but the search endpoint itself
is not.
"""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from brandpulse.config.models import NairalandConfig, RateLimitConfig
from brandpulse.connectors.nairaland import NairalandConnector, _clean_text, _parse_timestamp
from brandpulse.orchestration.connector_health import JSONConnectorHealthStore
from tests.fixtures.nairaland.sample_search_page import (
    EMPTY_SEARCH_PAGE_HTML,
    SAMPLE_SEARCH_PAGE_HTML,
)


class _FakeResponse:
    def __init__(self, text: str):
        self.text = text

    def raise_for_status(self):
        pass


@pytest.fixture
def connector(tmp_path: Path) -> NairalandConnector:
    health_store = JSONConnectorHealthStore(tmp_path / "connector_health.json")
    return NairalandConnector(
        config=NairalandConfig(max_pages=3),
        rate_limit_config=RateLimitConfig(requests_per_minute=6000, respect_robots_txt=False),
        health_store=health_store,
    )


def test_clean_text_collapses_whitespace():
    dirty = "Great   app\x00 with ALAT!  "
    cleaned = _clean_text(dirty)
    assert cleaned == "Great app with ALAT!"


def test_parse_timestamp_infers_current_year_when_absent():
    scraped_at = datetime(2026, 8, 1, tzinfo=UTC)
    parsed = _parse_timestamp("6:51pm On Jul 23", scraped_at)
    assert parsed == datetime(2026, 7, 23, 18, 51, tzinfo=UTC)


def test_parse_timestamp_uses_explicit_year_when_present():
    scraped_at = datetime(2026, 8, 1, tzinfo=UTC)
    parsed = _parse_timestamp("6:51pm On Jul 23, 2024", scraped_at)
    assert parsed == datetime(2024, 7, 23, 18, 51, tzinfo=UTC)


def test_parse_timestamp_returns_none_for_unrecognized_format():
    assert _parse_timestamp("not a timestamp", datetime(2026, 1, 1, tzinfo=UTC)) is None


def test_search_extracts_posts_and_replies(connector: NairalandConnector, monkeypatch):
    monkeypatch.setattr(
        "brandpulse.connectors.nairaland.requests.get",
        lambda *a, **k: _FakeResponse(SAMPLE_SEARCH_PAGE_HTML),
    )
    result = connector.search(["Wema Bank"], _distant_past(), _distant_future())

    assert result.status.value == "SUCCESS"
    assert len(result.records) == 2


def test_normalize_produces_mention_matching_canonical_schema(connector: NairalandConnector):
    from brandpulse.connectors.nairaland import _extract_posts

    posts = _extract_posts(SAMPLE_SEARCH_PAGE_HTML, "Wema Bank")
    raw_item = {"raw": posts[0], "search_url": "https://www.nairaland.com/search?q=Wema+Bank"}
    mention = connector.normalize(raw_item)

    assert mention.platform == "nairaland"
    assert mention.source_type == "forum_reply"
    assert mention.collection_scope == "forum"
    assert mention.collection_target == "nairaland.com"
    assert mention.search_term == "Wema Bank"
    assert mention.author == "maxinvile"
    assert mention.reliability == "medium"
    assert "fraud alert" in mention.text.lower()


def test_validate_rejects_empty_text(connector: NairalandConnector):
    raw_item = {
        "raw": {
            "post_id": "1",
            "title": "t",
            "permalink": "https://www.nairaland.com/1/t#1",
            "author": "x",
            "timestamp_label": "1:00pm On Jul 01",
            "content": "",
            "keyword": "Wema",
        },
        "search_url": "https://www.nairaland.com/search?q=Wema",
    }
    mention = connector.normalize(raw_item)
    assert connector.validate(mention) is False


def test_search_no_keywords_returns_no_results(connector: NairalandConnector):
    result = connector.search([], _distant_past(), _distant_future())
    assert result.status.value == "NO_RESULTS"


def test_search_empty_results_returns_no_results_not_failed(connector: NairalandConnector, monkeypatch):
    """Empty search results are a valid NO_RESULTS, not a FAILED (spec: this
    is an explicit failure mode Nairaland must distinguish)."""
    monkeypatch.setattr(
        "brandpulse.connectors.nairaland.requests.get",
        lambda *a, **k: _FakeResponse(EMPTY_SEARCH_PAGE_HTML),
    )
    result = connector.search(["zzznonexistent"], _distant_past(), _distant_future())
    assert result.status.value == "NO_RESULTS"


def test_search_network_error_returns_failed(connector: NairalandConnector, monkeypatch):
    def _raise(*args, **kwargs):
        raise ConnectionError("simulated network failure")

    monkeypatch.setattr("brandpulse.connectors.nairaland.requests.get", _raise)
    result = connector.search(["Wema"], _distant_past(), _distant_future())
    assert result.status.value == "FAILED"


def test_search_two_keywords_produce_separate_records_no_connector_level_dedup(
    connector: NairalandConnector, monkeypatch
):
    """Searching two different keywords must not be pre-filtered/deduped at
    the connector level — Silver-level dedup handles cross-search duplicates
    (Engineering Design §11); the connector's own dedup is only within a
    single batch/call."""
    monkeypatch.setattr(
        "brandpulse.connectors.nairaland.requests.get",
        lambda *a, **k: _FakeResponse(SAMPLE_SEARCH_PAGE_HTML),
    )
    result_alat = connector.search(["ALAT"], _distant_past(), _distant_future())
    result_alat_wema = connector.search(["ALAT by Wema"], _distant_past(), _distant_future())

    assert len(result_alat.records) == 2
    assert len(result_alat_wema.records) == 2
    mention_alat = connector.normalize(result_alat.records[0])
    mention_alat_wema = connector.normalize(result_alat_wema.records[0])
    assert mention_alat.search_term == "ALAT"
    assert mention_alat_wema.search_term == "ALAT by Wema"


def test_search_pagination_stops_at_max_pages(monkeypatch, tmp_path: Path):
    health_store = JSONConnectorHealthStore(tmp_path / "connector_health.json")
    limited_connector = NairalandConnector(
        config=NairalandConfig(max_pages=2),
        rate_limit_config=RateLimitConfig(requests_per_minute=6000, respect_robots_txt=False),
        health_store=health_store,
    )
    monkeypatch.setattr(
        "brandpulse.connectors.nairaland.requests.get",
        lambda *a, **k: _FakeResponse(SAMPLE_SEARCH_PAGE_HTML),
    )

    page1 = limited_connector.search(["Wema"], _distant_past(), _distant_future(), cursor=None)
    assert page1.next_cursor == "2"

    page2 = limited_connector.search(
        ["Wema"], _distant_past(), _distant_future(), cursor=page1.next_cursor
    )
    assert page2.next_cursor is None  # max_pages reached


def test_search_checks_robots_txt_before_fetching(tmp_path: Path, monkeypatch):
    health_store = JSONConnectorHealthStore(tmp_path / "connector_health.json")
    connector_with_robots_check = NairalandConnector(
        config=NairalandConfig(max_pages=3),
        rate_limit_config=RateLimitConfig(requests_per_minute=6000, respect_robots_txt=True),
        health_store=health_store,
    )

    fetch_was_called = False

    def _fetch_should_not_be_called(*args, **kwargs):
        nonlocal fetch_was_called
        fetch_was_called = True
        return _FakeResponse(SAMPLE_SEARCH_PAGE_HTML)

    monkeypatch.setattr("brandpulse.connectors.nairaland.requests.get", _fetch_should_not_be_called)
    monkeypatch.setattr(
        "brandpulse.connectors.nairaland.is_allowed_by_robots_txt", lambda url, ua: False
    )

    result = connector_with_robots_check.search(["Wema"], _distant_past(), _distant_future())

    assert result.status.value == "FAILED"
    assert result.reason == "disallowed_by_robots_txt"
    assert fetch_was_called is False


def test_idempotent_mention_id_for_same_raw_item(connector: NairalandConnector):
    from brandpulse.connectors.nairaland import _extract_posts

    posts = _extract_posts(SAMPLE_SEARCH_PAGE_HTML, "Wema Bank")
    raw_item = {"raw": posts[0], "search_url": "https://www.nairaland.com/search?q=Wema+Bank"}
    m1 = connector.normalize(raw_item)
    m2 = connector.normalize(raw_item)
    assert m1.mention_id == m2.mention_id


def _distant_past() -> datetime:
    return datetime(2000, 1, 1, tzinfo=UTC)


def _distant_future() -> datetime:
    return datetime(2100, 1, 1, tzinfo=UTC)
