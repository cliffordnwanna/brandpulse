"""Config schema (Engineering Design §8) as Pydantic models."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class SourceConfig(BaseModel):
    name: str
    enabled: bool
    reliability: Literal["high", "medium", "low"]


class GooglePlayConfig(BaseModel):
    """Connector-specific config for Google Play (Milestone 3).

    ``app_ids`` are configuration, not code — per the "never hardcode source
    lists" invariant, this is what lets a new bank/app be onboarded by editing
    config.yaml alone, no connector code change.
    """

    app_ids: list[str]
    country: str = "ng"
    language: str = "en"
    max_reviews_per_run: int = 500


class ConnectorsConfig(BaseModel):
    """Per-connector settings, keyed by connector name.

    Deliberately its own top-level block (distinct from ``sources:``, which
    only carries enable/reliability) so each connector can grow its own
    settings — e.g. ``reddit.subreddits``, ``youtube.channels`` — without
    changing this schema's shape.
    """

    google_play: GooglePlayConfig | None = None


class KeywordsConfig(BaseModel):
    base_list: list[str]


class OutputConfig(BaseModel):
    directory: str
    formats: list[str]


class RetryConfig(BaseModel):
    max_attempts: int
    backoff_seconds: list[int]


class TimeoutsConfig(BaseModel):
    request_seconds: int


class RateLimitConfig(BaseModel):
    requests_per_minute: int
    respect_robots_txt: bool


class Config(BaseModel):
    """Root config object, backed by ``config.yaml`` (Engineering Design §8)."""

    sources: list[SourceConfig]
    keywords: KeywordsConfig
    output: OutputConfig
    retry: RetryConfig
    timeouts: TimeoutsConfig
    rate_limit: RateLimitConfig
    connectors: ConnectorsConfig = ConnectorsConfig()
