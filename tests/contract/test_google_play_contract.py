"""Contract tests for GooglePlayConnector (Engineering Design §20, Milestone 3)."""

from pathlib import Path

import pytest

from brandpulse.config.models import GooglePlayConfig, RateLimitConfig
from brandpulse.connectors.google_play import GooglePlayConnector
from brandpulse.orchestration.connector_health import JSONConnectorHealthStore
from tests.contract.connector_contract import ConnectorContractTests
from tests.fixtures.google_play.sample_reviews import SAMPLE_REVIEW_POSITIVE


class TestGooglePlayContract(ConnectorContractTests):
    @pytest.fixture(autouse=True)
    def _state_dir(self, tmp_path: Path):
        self._tmp_path = tmp_path

    def make_connector(self) -> GooglePlayConnector:
        health_store = JSONConnectorHealthStore(self._tmp_path / "connector_health.json")
        return GooglePlayConnector(
            config=GooglePlayConfig(app_ids=["com.example.wema"]),
            rate_limit_config=RateLimitConfig(requests_per_minute=6000, respect_robots_txt=False),
            health_store=health_store,
        )

    def make_raw_item(self):
        return {"raw": SAMPLE_REVIEW_POSITIVE, "app_id": "com.example.wema"}

    def test_search_returns_valid_run_result(self, monkeypatch):
        monkeypatch.setattr(
            "brandpulse.connectors.google_play.fetch_reviews",
            lambda *a, **k: ([], None),
        )
        super().test_search_returns_valid_run_result()

    def test_health_responds(self, monkeypatch):
        monkeypatch.setattr(
            "brandpulse.connectors.google_play.fetch_app_details",
            lambda *a, **k: {"title": "Wema Bank"},
        )
        super().test_health_responds()
