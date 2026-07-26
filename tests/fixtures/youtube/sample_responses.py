"""Saved (real-shaped) YouTube Data API v3 response fixtures.

Matches the shape confirmed against the live API during Milestone 7's build
(search.list / commentThreads.list responses).
"""

SAMPLE_SEARCH_RESPONSE = {
    "items": [
        {"id": {"videoId": "vid001"}, "snippet": {"title": "ALAT by Wema Review"}},
        {"id": {"videoId": "vid002"}, "snippet": {"title": "Wema Bank Customer Care"}},
    ]
}

SAMPLE_EMPTY_SEARCH_RESPONSE = {"items": []}

SAMPLE_COMMENT_TOP_LEVEL = {
    "id": "comment001",
    "snippet": {
        "authorDisplayName": "@Ada_O",
        "textDisplay": "My transfer failed and support never responded, terrible service.",
        "textOriginal": "My transfer failed and support never responded, terrible service.",
        "likeCount": 5,
        "publishedAt": "2026-01-15T10:30:00Z",
    },
}

SAMPLE_COMMENT_REPLY = {
    "id": "comment002",
    "snippet": {
        "authorDisplayName": "@Chuka_N",
        "textDisplay": "Same thing happened to me with ALAT!",
        "textOriginal": "Same thing happened to me with ALAT!",
        "likeCount": 1,
        "publishedAt": "2026-01-15T11:00:00Z",
    },
}

SAMPLE_COMMENT_THREADS_RESPONSE = {
    "items": [
        {
            "snippet": {"topLevelComment": SAMPLE_COMMENT_TOP_LEVEL},
            "replies": {"comments": [SAMPLE_COMMENT_REPLY]},
        }
    ]
}

SAMPLE_COMMENT_THREADS_RESPONSE_NO_REPLIES = {
    "items": [
        {
            "snippet": {"topLevelComment": SAMPLE_COMMENT_TOP_LEVEL},
        }
    ]
}

SAMPLE_EMPTY_COMMENT_THREADS_RESPONSE = {"items": []}
