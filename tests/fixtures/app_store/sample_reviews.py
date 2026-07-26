"""Saved (real-shaped) App Store RSS review-feed entry fixtures.

Matches the shape of one ``feed.entry[i]`` item from
``itunes.apple.com/{country}/rss/customerreviews/.../json`` — captured
against the real feed structure during Milestone 7's build (see
``connectors/app_store.py``'s module docstring for why this feed is used
instead of the ``app-store-scraper`` package).
"""

SAMPLE_REVIEW_POSITIVE = {
    "author": {
        "uri": {"label": "https://itunes.apple.com/ng/reviews/id1111111111"},
        "name": {"label": "Ada O."},
        "label": "",
    },
    "updated": {"label": "2026-01-15T10:30:00-07:00"},
    "im:rating": {"label": "5"},
    "im:version": {"label": "3.2.1"},
    "id": {"label": "10000000001"},
    "title": {"label": "Great app"},
    "content": {
        "label": "Great app,   easy transfers with ALAT!  ",
        "attributes": {"type": "text"},
    },
    "link": {
        "attributes": {
            "rel": "related",
            "href": "https://itunes.apple.com/ng/review?id=1222853161&type=Purple%20Software",
        }
    },
    "im:voteSum": {"label": "0"},
    "im:contentType": {"attributes": {"term": "Application", "label": "Application"}},
    "im:voteCount": {"label": "0"},
}

SAMPLE_REVIEW_NEGATIVE = {
    "author": {
        "uri": {"label": "https://itunes.apple.com/ng/reviews/id2222222222"},
        "name": {"label": "Chuka N."},
        "label": "",
    },
    "updated": {"label": "2026-01-10T08:00:00-07:00"},
    "im:rating": {"label": "1"},
    "im:version": {"label": "3.2.0"},
    "id": {"label": "10000000002"},
    "title": {"label": "Fraud alert"},
    "content": {
        "label": "Wema fraud alert - my transfer failed and support never responded.",
        "attributes": {"type": "text"},
    },
    "link": {
        "attributes": {
            "rel": "related",
            "href": "https://itunes.apple.com/ng/review?id=1222853161&type=Purple%20Software",
        }
    },
    "im:voteSum": {"label": "0"},
    "im:contentType": {"attributes": {"term": "Application", "label": "Application"}},
    "im:voteCount": {"label": "45"},
}
