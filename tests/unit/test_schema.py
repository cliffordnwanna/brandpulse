"""Unit tests for the canonical Mention schema (Engineering Design §2)."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from brandpulse.schema import Mention


def _valid_mention_kwargs() -> dict:
    return {
        "mention_id": "abc123",
        "platform": "google_play",
        "source_type": "review",
        "collection_scope": "app",
        "search_term": None,
        "collection_target": "com.alat.example",
        "author": "jane_doe",
        "url": "https://play.google.com/store/apps/details?id=com.alat",
        "text": "Great app, easy transfers.",
        "language": None,
        "timestamp": datetime(2026, 1, 1, tzinfo=UTC),
        "scraped_at": datetime(2026, 1, 2, tzinfo=UTC),
        "raw_json": '{"raw": true}',
        "reliability": "high",
        "connector_version": "1.0.0",
        "metadata": {"star_rating": 5},
    }


def test_valid_mention_constructs():
    mention = Mention(**_valid_mention_kwargs())
    assert mention.platform == "google_play"
    assert mention.language is None
    assert mention.metadata == {"star_rating": 5}


def test_mention_supports_keyword_collection_scope():
    kwargs = _valid_mention_kwargs()
    kwargs["collection_scope"] = "keyword"
    kwargs["search_term"] = "Wema fraud"
    kwargs["collection_target"] = None

    mention = Mention(**kwargs)

    assert mention.collection_scope == "keyword"
    assert mention.search_term == "Wema fraud"
    assert mention.collection_target is None


def test_mention_rejects_invalid_collection_scope():
    kwargs = _valid_mention_kwargs()
    kwargs["collection_scope"] = "hashtag"
    with pytest.raises(ValidationError):
        Mention(**kwargs)


def test_mention_allows_null_author_and_url():
    kwargs = _valid_mention_kwargs()
    kwargs["author"] = None
    kwargs["url"] = None
    mention = Mention(**kwargs)
    assert mention.author is None
    assert mention.url is None


def test_mention_rejects_invalid_platform():
    kwargs = _valid_mention_kwargs()
    kwargs["platform"] = "twitter"
    with pytest.raises(ValidationError):
        Mention(**kwargs)


def test_mention_rejects_invalid_reliability():
    kwargs = _valid_mention_kwargs()
    kwargs["reliability"] = "extreme"
    with pytest.raises(ValidationError):
        Mention(**kwargs)


def test_mention_rejects_missing_required_field():
    kwargs = _valid_mention_kwargs()
    del kwargs["mention_id"]
    with pytest.raises(ValidationError):
        Mention(**kwargs)


def test_mention_is_frozen():
    mention = Mention(**_valid_mention_kwargs())
    with pytest.raises(ValidationError):
        mention.text = "edited"
