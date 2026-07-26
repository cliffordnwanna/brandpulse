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


class AppStoreConfig(BaseModel):
    """Connector-specific config for the Apple App Store (Milestone 7).

    ``app_ids`` are Apple's numeric track IDs (not bundle IDs) — configuration,
    not code, same "never hardcode source lists" reasoning as
    ``GooglePlayConfig.app_ids``.
    """

    app_ids: list[str] = []
    country: str = "ng"
    max_reviews_per_run: int = 500


class NairalandConfig(BaseModel):
    """Connector-specific config for Nairaland (Milestone 7).

    Nairaland is genuinely keyword-searched (``collection_scope="forum"``,
    but driven by the orchestrator's per-keyword job loop same as any other
    keyword-scoped connector) — this block only carries the pagination/
    politeness knobs that are specific to how Nairaland's search works, not
    the keyword list itself (that stays in the shared ``keywords.base_list``).
    """

    max_pages: int = 5


class YouTubeConfig(BaseModel):
    """Connector-specific config for YouTube (Milestone 7).

    ``YOUTUBE_API_KEY`` is read from the environment, never from this config
    block or any committed file — see ``connectors/youtube.py``.
    """

    max_videos_per_keyword: int = 10
    max_comments_per_video: int = 100


class ConnectorsConfig(BaseModel):
    """Per-connector settings, keyed by connector name.

    Deliberately its own top-level block (distinct from ``sources:``, which
    only carries enable/reliability) so each connector can grow its own
    settings — e.g. ``reddit.subreddits``, ``youtube.channels`` — without
    changing this schema's shape.
    """

    google_play: GooglePlayConfig | None = None
    app_store: AppStoreConfig | None = None
    nairaland: NairalandConfig | None = None
    youtube: YouTubeConfig | None = None


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


class StorageConfig(BaseModel):
    """Storage backend selection (Milestone 4).

    ``backend`` picked here is the *only* thing that changes to move from
    local files to a cloud backend later — ``StorageBackendFactory`` reads
    this and resolves the concrete class; no other code depends on which
    backend is active. Deliberately typed as ``str``, not a ``Literal`` of
    only currently-implemented backends: an unsupported value should fail
    with a clear error from ``StorageBackendFactory`` (naming what's actually
    supported), not a generic Pydantic validation error at config-load time
    that looks like a config file mistake rather than a "not built yet" gap.
    """

    backend: str = "local"
    root: str = "./storage"


class ClassificationConfig(BaseModel):
    """Classification pipeline settings (Milestone 5).

    5a (sentiment + complaint category) always runs on every Silver record.
    5b (emotion/intent/urgency/competitor/summary) is optional enrichment,
    off by default (``enable_enrichment: false``) — this is what keeps LLM
    cost predictable, per the "LLM is conditional, never the default path"
    architecture invariant. ``enrichment_model``/``enrichment_trigger`` are
    plain ``str``, not ``Literal``, for the same reason as
    ``StorageConfig.backend``: an unsupported value should fail with a clear
    error from the code that resolves it, not an opaque Pydantic error.
    """

    enable_enrichment: bool = False
    enrichment_model: str = "azure_openai"
    enrichment_trigger: str = "low_confidence"
    confidence_threshold: float = 0.75
    sentiment_model: str = "lexicon"
    complaint_model: str = "keyword"
    recommendations: bool = False
    """Milestone 6: generate an LLM recommendation for each high/critical
    Insight when true. Flat field, not nested under an ``enrichment:`` block,
    consistent with the rest of this config's style (see ``StorageConfig``'s
    docstring for the same reasoning re: not over-nesting config shape)."""


class Config(BaseModel):
    """Root config object, backed by ``config.yaml`` (Engineering Design §8)."""

    sources: list[SourceConfig]
    keywords: KeywordsConfig
    output: OutputConfig
    retry: RetryConfig
    timeouts: TimeoutsConfig
    rate_limit: RateLimitConfig
    connectors: ConnectorsConfig = ConnectorsConfig()
    storage: StorageConfig = StorageConfig()
    classification: ClassificationConfig = ClassificationConfig()
