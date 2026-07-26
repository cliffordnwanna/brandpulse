"""Contract tests for YouTubeConnector (Engineering Design §20, Milestone 7)."""

from pathlib import Path

import pytest

from brandpulse.config.models import RateLimitConfig, YouTubeConfig
from brandpulse.connectors.youtube import YouTubeConnector
from brandpulse.orchestration.connector_health import JSONConnectorHealthStore
from tests.contract.connector_contract import ConnectorContractTests
from tests.fixtures.youtube.sample_responses import SAMPLE_COMMENT_TOP_LEVEL


class _FakeExecutable:
    def __init__(self, payload):
        self._payload = payload

    def execute(self):
        return self._payload


class _FakeListEndpoint:
    def list(self, **kwargs):
        return _FakeExecutable({"items": []})


class _FakeYouTubeClient:
    def search(self):
        return _FakeListEndpoint()

    def commentThreads(self):
        return _FakeListEndpoint()


class TestYouTubeContract(ConnectorContractTests):
    @pytest.fixture(autouse=True)
    def _state_dir(self, tmp_path: Path):
        self._tmp_path = tmp_path

    def make_connector(self) -> YouTubeConnector:
        health_store = JSONConnectorHealthStore(self._tmp_path / "connector_health.json")
        connector = YouTubeConnector(
            config=YouTubeConfig(),
            rate_limit_config=RateLimitConfig(requests_per_minute=6000, respect_robots_txt=False),
            health_store=health_store,
            api_key="fake-key-for-tests",
        )
        connector._client = lambda: _FakeYouTubeClient()
        return connector

    def make_raw_item(self):
        return {"raw": SAMPLE_COMMENT_TOP_LEVEL, "video_id": "vid001", "keyword": "Wema Bank"}
