"""Saved (hand-constructed, realistically shaped) Google Play review fixtures.

Used by unit/contract tests instead of live calls — matches the dict shape
returned by ``google_play_scraper.reviews()`` (keys per
``google_play_scraper.features.reviews.ElementSpecs.Review``).
"""

from datetime import UTC, datetime

SAMPLE_REVIEW_POSITIVE = {
    "reviewId": "abc-123",
    "userName": "Ada O.",
    "userImage": "https://example.com/avatar.png",
    "content": "Great app,   easy transfers with ALAT!  \x00\x01",
    "score": 5,
    "thumbsUpCount": 12,
    "reviewCreatedVersion": "3.2.1",
    "at": datetime(2026, 1, 15, 10, 30, tzinfo=UTC),
    "replyContent": None,
    "repliedAt": None,
    "appVersion": "3.2.1",
}

SAMPLE_REVIEW_NEGATIVE = {
    "reviewId": "def-456",
    "userName": "Chuka N.",
    "userImage": "https://example.com/avatar2.png",
    "content": "Wema fraud alert - my transfer failed and support never responded.",
    "score": 1,
    "thumbsUpCount": 45,
    "reviewCreatedVersion": "3.2.0",
    "at": datetime(2026, 1, 10, 8, 0, tzinfo=UTC),
    "replyContent": None,
    "repliedAt": None,
    "appVersion": "3.2.0",
}

SAMPLE_REVIEW_DUPLICATE_TEXT = {
    "reviewId": "ghi-789",
    "userName": "Chuka N.",
    "userImage": "https://example.com/avatar2.png",
    "content": "Wema fraud alert - my transfer failed and support never responded.",
    "score": 1,
    "thumbsUpCount": 2,
    "reviewCreatedVersion": "3.2.0",
    "at": datetime(2026, 1, 11, 9, 0, tzinfo=UTC),
    "replyContent": None,
    "repliedAt": None,
    "appVersion": "3.2.0",
}
