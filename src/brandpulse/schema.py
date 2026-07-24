"""Canonical data contract (Engineering Design §2).

Every connector, regardless of source, emits exactly this schema. A connector
that can't populate a field emits ``None`` — it never invents a different shape.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

Platform = Literal["google_play", "app_store", "nairaland", "youtube", "reddit"]
SourceType = Literal["review", "comment", "post", "forum_reply"]
Reliability = Literal["high", "medium", "low"]
CollectionScope = Literal["keyword", "app", "channel", "subreddit", "forum"]


class Mention(BaseModel):
    """The canonical Mention record (Engineering Design §2).

    ``collection_scope``/``collection_target`` describe *how* a connector
    collected this record — some sources (Nairaland, forums) are genuinely
    keyword-searched; others (Google Play, YouTube channels) collect
    everything available for a fixed target (an app package ID, a channel ID)
    and have no keyword concept at retrieval time at all. Filtering by
    relevance/keyword is a downstream (Silver/classification) concern, never
    a connector concern — a connector that filtered at collection time would
    make Bronze permanently lossy: adding a new alias/keyword later would
    require re-scraping instead of just reprocessing Bronze (Engineering
    Design §9's "Silver/Gold regenerable from Bronze alone" guarantee would
    be broken for anything the old keyword list missed).

    ``search_term`` is populated only when ``collection_scope="keyword"``;
    ``collection_target`` is populated only when ``collection_scope`` is one
    of the non-keyword scopes (the concrete app package ID, channel ID,
    subreddit name, etc. collected against).
    """

    model_config = ConfigDict(frozen=True)

    mention_id: str
    platform: Platform
    source_type: SourceType
    collection_scope: CollectionScope
    search_term: str | None
    collection_target: str | None
    author: str | None
    url: str | None
    text: str
    language: str | None
    timestamp: datetime
    scraped_at: datetime
    raw_json: str
    reliability: Reliability
    connector_version: str
    metadata: dict[str, Any]
