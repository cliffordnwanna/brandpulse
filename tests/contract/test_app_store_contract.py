"""Contract tests for AppStoreConnector (Engineering Design §20, Milestone 7)."""

from pathlib import Path

import pytest

from brandpulse.config.models import AppStoreConfig, RateLimitConfig
from brandpulse.connectors.app_store import AppStoreConnector
from brandpulse.orchestration.connector_health import JSONConnectorHealthStore
from tests.contract.connector_contract import ConnectorContractTests
from tests.fixtures.app_store.sample_reviews import SAMPLE_REVIEW_POSITIVE


class TestAppStoreContract(ConnectorContractTests):
    @pytest.fixture(autouse=True)
    def _state_dir(self, tmp_path: Path):
        self._tmp_path = tmp_path

    def make_connector(self) -> AppStoreConnector:
        health_store = JSONConnectorHealthStore(self._tmp_path / "connector_health.json")
        return AppStoreConnector(
            config=AppStoreConfig(app_ids=["1222853161"]),
            rate_limit_config=RateLimitConfig(requests_per_minute=6000, respect_robots_txt=False),
            health_store=health_store,
        )

    def make_raw_item(self):
        return {
            "raw": SAMPLE_REVIEW_POSITIVE,
            "app_id": "1222853161",
            "app_page_url": "https://apps.apple.com/ng/app/id1222853161",
        }

    def test_search_returns_valid_run_result(self, monkeypatch):
        class _FakeResponse:
            def raise_for_status(self):
                pass

            def json(self):
                return {"feed": {"entry": []}}

        monkeypatch.setattr(
            "brandpulse.connectors.app_store.requests.get", lambda *a, **k: _FakeResponse()
        )
        super().test_search_returns_valid_run_result()

    def test_health_responds(self, monkeypatch):
        class _FakeResponse:
            def raise_for_status(self):
                pass

            def json(self):
                return {"feed": {"entry": [SAMPLE_REVIEW_POSITIVE]}}

        monkeypatch.setattr(
            "brandpulse.connectors.app_store.requests.get", lambda *a, **k: _FakeResponse()
        )
        super().test_health_responds()
