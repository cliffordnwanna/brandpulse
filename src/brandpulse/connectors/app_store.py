"""Apple App Store reviews connector (Engineering Design §3, Milestone 7).

Collects **all** reviews for the configured numeric app_ids within the
requested window — same bounded-entity pattern as Google Play (Milestone 3):
no keyword filtering at collection time, ``collection_scope="app"``,
``collection_target=<app_id>``, ``search_term=None``.

Uses Apple's public customer-reviews RSS/JSON feed
(``itunes.apple.com/{country}/rss/customerreviews/...``) directly via
``requests`` rather than the ``app-store-scraper`` PyPI package: that
package authenticates against Apple's App Store *web app* by scraping a
bearer token out of the app's landing-page HTML, and Apple has since
restructured that page — the token is no longer present, so every request
the package makes 401s (confirmed against the real ALAT app page during
this milestone's build). The RSS feed requires no authentication at all,
is Apple's own documented-by-convention public interface for this data, and
is considerably more stable than scraping an SPA's internal token.
"""

from __future__ import annotations

import json
import re
import unicodedata
from datetime import UTC, datetime
from typing import Any

import requests

from brandpulse.config.models import AppStoreConfig, RateLimitConfig
from brandpulse.connectors.base import BaseConnector, HealthStatus, RunResult, RunStatus
from brandpulse.connectors.politeness import RateLimiter, is_allowed_by_robots_txt, random_delay
from brandpulse.orchestration.connector_health import ConnectorHealthStore
from brandpulse.orchestration.idempotency import compute_mention_id
from brandpulse.schema import Mention

USER_AGENT = "BrandPulseBot/0.1 (+https://github.com/wema-bank/brandpulse)"
FEED_URL_TEMPLATE = (
    "https://itunes.apple.com/{country}/rss/customerreviews/page={page}/id={app_id}/sortBy=mostRecent/json"
)
APP_PAGE_URL_TEMPLATE = "https://apps.apple.com/{country}/app/id{app_id}"
MAX_PAGE = 10  # the feed itself stops returning entries around page 10 (~500 most recent reviews)
REQUEST_TIMEOUT_SECONDS = 15


def _clean_text(text: str) -> str:
    """Bronze normalization (Engineering Design §3): whitespace-collapsed,
    control characters stripped, UTF-8-safe — never rewrites content."""
    normalized = unicodedata.normalize("NFC", text)
    utf8_safe = normalized.encode("utf-8", errors="replace").decode("utf-8")
    no_control_chars = "".join(
        ch for ch in utf8_safe if ch in ("\n", "\t") or not unicodedata.category(ch).startswith("C")
    )
    return re.sub(r"\s+", " ", no_control_chars).strip()


def _deserialize_cursor(cursor: str | None) -> tuple[int, int]:
    """``(app_index, page)`` — mirrors Google Play's app-index-plus-token
    cursor shape, except the App Store feed's pagination unit is a plain
    page number rather than an opaque continuation token."""
    if cursor is None:
        return 0, 1
    data = json.loads(cursor)
    return data["app_index"], data["page"]


class AppStoreConnector(BaseConnector):
    """Fetches *all* App Store reviews for configured numeric app_ids (Milestone 7).

    Not keyword-filtered — see module docstring. ``BaseConnector.search()``'s
    ``keywords`` parameter is accepted (interface compatibility) but ignored.
    """

    name = "app_store"
    version = "0.1.0"
    reliability = "high"
    collection_scope = "app"
    is_keyword_driven = False

    def __init__(
        self,
        config: AppStoreConfig,
        rate_limit_config: RateLimitConfig,
        health_store: ConnectorHealthStore,
        rate_limiter: RateLimiter | None = None,
    ) -> None:
        self._config = config
        self._rate_limit_config = rate_limit_config
        self._health_store = health_store
        self._rate_limiter = rate_limiter or RateLimiter(rate_limit_config.requests_per_minute)

    def search(
        self,
        keywords: list[str],
        start: datetime,
        end: datetime,
        cursor: str | None = None,
    ) -> RunResult:
        """Fetch one page of reviews for the current app_id in the configured list.

        ``keywords`` is ignored — see class/module docstring. Each call is
        one page/batch for orchestrator checkpointing purposes; the cursor
        also tracks which app_id in ``config.app_ids`` is currently being
        paginated, so a single job walks every configured app in turn.
        """
        if not self._config.app_ids:
            return RunResult(status=RunStatus.NO_RESULTS, records=[], next_cursor=None)

        app_index, page = _deserialize_cursor(cursor)
        if app_index >= len(self._config.app_ids):
            return RunResult(status=RunStatus.NO_RESULTS, records=[], next_cursor=None)

        app_id = self._config.app_ids[app_index]
        feed_url = FEED_URL_TEMPLATE.format(country=self._config.country, page=page, app_id=app_id)
        app_page_url = APP_PAGE_URL_TEMPLATE.format(country=self._config.country, app_id=app_id)

        if self._rate_limit_config.respect_robots_txt and not is_allowed_by_robots_txt(
            feed_url, USER_AGENT
        ):
            return RunResult(status=RunStatus.FAILED, records=[], reason="disallowed_by_robots_txt")

        self._rate_limiter.acquire()

        try:
            response = requests.get(
                feed_url,
                headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            data = response.json()
        except Exception as exc:  # network errors, non-JSON body, rate limiting, etc.
            return RunResult(status=RunStatus.FAILED, records=[], reason=str(exc))

        random_delay()

        entries = data.get("feed", {}).get("entry", [])
        # A single-review feed response has `entry` as one dict instead of a
        # list — normalize to a list so downstream code doesn't special-case it.
        if isinstance(entries, dict):
            entries = [entries]

        reviews = [e for e in entries if "content" in e and "im:rating" in e]
        in_window = [r for r in reviews if self._in_window(r, start, end)]
        deduped = self._dedupe_batch(in_window, app_id)

        next_app_index = app_index
        next_page = page + 1
        if not reviews or page >= MAX_PAGE:
            # This app's pagination is exhausted — advance to the next app_id.
            next_app_index = app_index + 1
            next_page = 1

        exhausted = next_app_index >= len(self._config.app_ids)
        next_cursor = (
            None if exhausted else json.dumps({"app_index": next_app_index, "page": next_page})
        )

        return RunResult(
            status=RunStatus.SUCCESS,
            records=[{"raw": r, "app_id": app_id, "app_page_url": app_page_url} for r in deduped],
            next_cursor=next_cursor,
        )

    def _in_window(self, raw: dict[str, Any], start: datetime, end: datetime) -> bool:
        updated = raw.get("updated", {}).get("label")
        if not updated:
            return True
        try:
            timestamp = datetime.fromisoformat(updated)
        except ValueError:
            return True
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=UTC)
        return start <= timestamp <= end

    def _dedupe_batch(self, raws: list[dict[str, Any]], app_id: str) -> list[dict[str, Any]]:
        """Connector contract (§3): no exact duplicates within the connector's
        own batch — same ``url``, or same ``(platform, author, text)`` tuple."""
        seen: set[tuple[str, str, str]] = set()
        deduped: list[dict[str, Any]] = []
        for raw in raws:
            review_id = raw.get("id", {}).get("label") or ""
            key = (app_id, review_id, raw.get("content", {}).get("label") or "")
            if key in seen:
                continue
            seen.add(key)
            deduped.append(raw)
        return deduped

    def normalize(self, raw_item: Any) -> Mention:
        raw = raw_item["raw"]
        app_id = raw_item["app_id"]
        app_page_url = raw_item["app_page_url"]

        updated = raw.get("updated", {}).get("label")
        try:
            timestamp = datetime.fromisoformat(updated) if updated else datetime.now(UTC)
        except ValueError:
            timestamp = datetime.now(UTC)
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=UTC)

        text = _clean_text(raw.get("content", {}).get("label") or "")
        review_id = raw.get("id", {}).get("label") or ""
        url = raw.get("link", {}).get("attributes", {}).get("href") or (
            f"{app_page_url}?review_id={review_id}"
        )
        now = datetime.now(UTC)

        return Mention(
            mention_id=compute_mention_id("app_store", url, timestamp, text),
            platform="app_store",
            source_type="review",
            collection_scope="app",
            search_term=None,
            collection_target=app_id,
            author=raw.get("author", {}).get("name", {}).get("label"),
            url=url,
            text=text,
            language=None,
            timestamp=timestamp,
            scraped_at=now,
            raw_json=json.dumps(raw, default=str),
            reliability=self.reliability,
            connector_version=self.version,
            metadata={
                "star_rating": raw.get("im:rating", {}).get("label"),
                "app_version": raw.get("im:version", {}).get("label"),
                "title": raw.get("title", {}).get("label"),
                "vote_count": raw.get("im:voteCount", {}).get("label"),
            },
        )

    def validate(self, mention: Mention) -> bool:
        return bool(mention.text) and bool(mention.mention_id)

    def health(self) -> HealthStatus:
        """Lightweight reachability check: can we fetch the reviews feed at all
        right now. Consults the shared ``ConnectorHealthStore`` — same pattern
        as Google Play, no separate connector-local failure counter."""
        cross_run_health = self._health_store.get(self.name)
        if cross_run_health.consecutive_failures >= 3:
            return HealthStatus(
                healthy=False,
                reason="auto_disabled_after_consecutive_failures",
                checked_at=datetime.now(UTC),
            )

        if not self._config.app_ids:
            return HealthStatus(
                healthy=False, reason="no_app_ids_configured", checked_at=datetime.now(UTC)
            )

        try:
            feed_url = FEED_URL_TEMPLATE.format(
                country=self._config.country, page=1, app_id=self._config.app_ids[0]
            )
            response = requests.get(
                feed_url,
                headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            response.json()
            return HealthStatus(healthy=True, checked_at=datetime.now(UTC))
        except Exception as exc:
            return HealthStatus(healthy=False, reason=str(exc), checked_at=datetime.now(UTC))
