"""Contract tests for NairalandConnector (Engineering Design §20, Milestone 7)."""

from pathlib import Path

import pytest

from brandpulse.config.models import NairalandConfig, RateLimitConfig
from brandpulse.connectors.nairaland import NairalandConnector
from brandpulse.orchestration.connector_health import JSONConnectorHealthStore
from tests.contract.connector_contract import ConnectorContractTests
from tests.fixtures.nairaland.sample_search_page import SAMPLE_SEARCH_PAGE_HTML


class _FakeResponse:
    def __init__(self, text: str):
        self.text = text

    def raise_for_status(self):
        pass


class TestNairalandContract(ConnectorContractTests):
    @pytest.fixture(autouse=True)
    def _state_dir(self, tmp_path: Path):
        self._tmp_path = tmp_path

    def make_connector(self) -> NairalandConnector:
        health_store = JSONConnectorHealthStore(self._tmp_path / "connector_health.json")
        return NairalandConnector(
            config=NairalandConfig(max_pages=3),
            rate_limit_config=RateLimitConfig(requests_per_minute=6000, respect_robots_txt=False),
            health_store=health_store,
        )

    def make_raw_item(self):
        from brandpulse.connectors.nairaland import _extract_posts

        posts = _extract_posts(SAMPLE_SEARCH_PAGE_HTML, "Wema Bank")
        return {"raw": posts[0], "search_url": "https://www.nairaland.com/search?q=Wema+Bank"}

    def test_search_returns_valid_run_result(self, monkeypatch):
        monkeypatch.setattr(
            "brandpulse.connectors.nairaland.requests.get",
            lambda *a, **k: _FakeResponse(SAMPLE_SEARCH_PAGE_HTML),
        )
        connector = self.make_connector()
        result = connector.search(["Wema"], *self._window())
        assert result is not None

    def test_health_responds(self, monkeypatch):
        monkeypatch.setattr(
            "brandpulse.connectors.nairaland.requests.get",
            lambda *a, **k: _FakeResponse(SAMPLE_SEARCH_PAGE_HTML),
        )
        super().test_health_responds()

    @staticmethod
    def _window():
        from datetime import UTC, datetime

        return datetime(2000, 1, 1, tzinfo=UTC), datetime(2100, 1, 1, tzinfo=UTC)
