"""Unit tests for the SourceRegistry skeleton (Engineering Design §4)."""

import pytest

from brandpulse.config.models import (
    Config,
    KeywordsConfig,
    OutputConfig,
    RateLimitConfig,
    RetryConfig,
    SourceConfig,
    TimeoutsConfig,
)
from brandpulse.registry.source_registry import SourceRegistry


def _config_with_sources(sources: list[SourceConfig]) -> Config:
    return Config(
        sources=sources,
        keywords=KeywordsConfig(base_list=["Wema"]),
        output=OutputConfig(directory="./output/", formats=["csv"]),
        retry=RetryConfig(max_attempts=3, backoff_seconds=[5, 30, 120]),
        timeouts=TimeoutsConfig(request_seconds=20),
        rate_limit=RateLimitConfig(requests_per_minute=60, respect_robots_txt=True),
    )


def test_enabled_sources_reflects_config():
    config = _config_with_sources(
        [
            SourceConfig(name="google_play", enabled=True, reliability="high"),
            SourceConfig(name="nairaland", enabled=False, reliability="medium"),
        ]
    )
    registry = SourceRegistry(config)

    enabled_names = {source.name for source in registry.enabled_sources()}

    assert enabled_names == {"google_play"}


def test_reliability_reflects_config():
    config = _config_with_sources(
        [SourceConfig(name="google_play", enabled=True, reliability="high")]
    )
    registry = SourceRegistry(config)

    assert registry.reliability("google_play") == "high"


def test_priority_reflects_declaration_order():
    config = _config_with_sources(
        [
            SourceConfig(name="google_play", enabled=True, reliability="high"),
            SourceConfig(name="youtube", enabled=True, reliability="high"),
        ]
    )
    registry = SourceRegistry(config)

    assert registry.priority("google_play") < registry.priority("youtube")


def test_unknown_source_raises():
    config = _config_with_sources(
        [SourceConfig(name="google_play", enabled=True, reliability="high")]
    )
    registry = SourceRegistry(config)

    with pytest.raises(KeyError):
        registry.reliability("reddit")


def test_health_status_stub_reports_healthy():
    config = _config_with_sources(
        [SourceConfig(name="google_play", enabled=True, reliability="high")]
    )
    registry = SourceRegistry(config)

    status = registry.health_status("google_play")

    assert status.healthy is True
