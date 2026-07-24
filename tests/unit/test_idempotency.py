"""Unit tests for content-hash mention_id generation (Engineering Design §5)."""

from datetime import UTC, datetime

from brandpulse.orchestration.idempotency import compute_mention_id


def test_same_content_produces_same_mention_id():
    ts = datetime(2026, 1, 1, tzinfo=UTC)

    first = compute_mention_id("google_play", "https://example.com/1", ts, "Great app!")
    second = compute_mention_id("google_play", "https://example.com/1", ts, "Great app!")

    assert first == second


def test_rerunning_produces_same_id_even_with_whitespace_variance():
    """Idempotency must survive trivial whitespace differences between runs."""
    ts = datetime(2026, 1, 1, tzinfo=UTC)

    first = compute_mention_id("google_play", "https://example.com/1", ts, "Great   app!")
    second = compute_mention_id("google_play", "https://example.com/1", ts, "Great app!")

    assert first == second


def test_different_text_produces_different_id():
    ts = datetime(2026, 1, 1, tzinfo=UTC)

    first = compute_mention_id("google_play", "https://example.com/1", ts, "Great app!")
    second = compute_mention_id("google_play", "https://example.com/1", ts, "Terrible app!")

    assert first != second


def test_different_platform_produces_different_id():
    ts = datetime(2026, 1, 1, tzinfo=UTC)

    first = compute_mention_id("google_play", "https://example.com/1", ts, "Great app!")
    second = compute_mention_id("app_store", "https://example.com/1", ts, "Great app!")

    assert first != second


def test_null_url_is_handled():
    ts = datetime(2026, 1, 1, tzinfo=UTC)
    mention_id = compute_mention_id("nairaland", None, ts, "some forum post")
    assert isinstance(mention_id, str) and len(mention_id) == 64
