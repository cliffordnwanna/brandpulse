"""Google Play reviews connector (Engineering Design §3, Milestone 3).

First real connector — proves the Milestone 1/2 abstractions (canonical
schema, BaseConnector, checkpoint/resume, idempotency, retry/auto-disable)
against a live source. Uses ``google-play-scraper`` (no API key required;
Google Play has no official public reviews API).

Collects **all** reviews for the configured app_ids within the requested
window — it does not filter by keyword. Google Play has no keyword-search
concept for reviews at all; filtering at collection time would make Bronze
permanently lossy (a review missing a configured keyword/alias might still
be relevant, and a new alias added later would require re-scraping instead
of reprocessing Bronze). Keyword/entity relevance matching is a Silver-or-
later concern (Engineering Design §2, §9). Accordingly this connector uses
``collection_scope="app"`` / ``collection_target=<app_id>`` rather than
``search_term`` — see the canonical schema docstring in ``schema.py``.
"""

from __future__ import annotations

import json
import re
import unicodedata
from datetime import UTC, datetime
from typing import Any

from google_play_scraper import Sort
from google_play_scraper import app as fetch_app_details
from google_play_scraper import reviews as fetch_reviews
from google_play_scraper.exceptions import NotFoundError
from google_play_scraper.features.reviews import _ContinuationToken

from brandpulse.config.models import GooglePlayConfig, RateLimitConfig
from brandpulse.connectors.base import BaseConnector, HealthStatus, RunResult, RunStatus
from brandpulse.connectors.politeness import RateLimiter, is_allowed_by_robots_txt, random_delay
from brandpulse.orchestration.connector_health import ConnectorHealthStore
from brandpulse.orchestration.idempotency import compute_mention_id
from brandpulse.schema import Mention

USER_AGENT = "BrandPulseBot/0.1 (+https://github.com/wema-bank/brandpulse)"
REVIEWS_URL_TEMPLATE = "https://play.google.com/store/apps/details?id={app_id}"
PAGE_SIZE = 100


def _clean_text(text: str) -> str:
    """Bronze normalization (Engineering Design §3): whitespace-collapsed,
    control characters stripped, UTF-8-safe — never rewrites content."""
    normalized = unicodedata.normalize("NFC", text)
    utf8_safe = normalized.encode("utf-8", errors="replace").decode("utf-8")
    no_control_chars = "".join(
        ch for ch in utf8_safe if ch in ("\n", "\t") or not unicodedata.category(ch).startswith("C")
    )
    return re.sub(r"\s+", " ", no_control_chars).strip()


def _serialize_token(token: _ContinuationToken | None) -> dict[str, Any] | None:
    if token is None or token.token is None:
        return None
    return {
        "token": token.token,
        "lang": token.lang,
        "country": token.country,
        "sort": token.sort,
        "count": token.count,
        "filter_score_with": token.filter_score_with,
        "filter_device_with": token.filter_device_with,
    }


def _deserialize_token(data: dict[str, Any] | None) -> _ContinuationToken | None:
    if data is None:
        return None
    return _ContinuationToken(
        data["token"],
        data["lang"],
        data["country"],
        data["sort"],
        data["count"],
        data["filter_score_with"],
        data["filter_device_with"],
    )


def _deserialize_cursor(cursor: str | None) -> tuple[int, _ContinuationToken | None]:
    if cursor is None:
        return 0, None
    data = json.loads(cursor)
    return data["app_index"], _deserialize_token(data["token"])


class GooglePlayConnector(BaseConnector):
    """Fetches *all* Google Play reviews for configured app_ids (Milestone 3).

    Not keyword-filtered — see module docstring. ``BaseConnector.search()``'s
    ``keywords`` parameter is accepted (interface compatibility with other
    connectors) but ignored; this connector's collection unit is the
    configured app_ids, not a keyword list.
    """

    name = "google_play"
    version = "0.1.0"
    reliability = "high"
    collection_scope = "app"

    def __init__(
        self,
        config: GooglePlayConfig,
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

        ``keywords`` is ignored — see class/module docstring. Each call is one
        page/batch for orchestrator checkpointing purposes; the opaque
        ``cursor`` also tracks which app_id in ``config.app_ids`` is currently
        being paginated, so a single job walks every configured app in turn.
        """
        if not self._config.app_ids:
            return RunResult(status=RunStatus.NO_RESULTS, records=[], next_cursor=None)

        app_index, continuation_token = _deserialize_cursor(cursor)
        if app_index >= len(self._config.app_ids):
            return RunResult(status=RunStatus.NO_RESULTS, records=[], next_cursor=None)

        app_id = self._config.app_ids[app_index]
        review_url = REVIEWS_URL_TEMPLATE.format(app_id=app_id)

        if self._rate_limit_config.respect_robots_txt and not is_allowed_by_robots_txt(
            review_url, USER_AGENT
        ):
            return RunResult(status=RunStatus.FAILED, records=[], reason="disallowed_by_robots_txt")

        self._rate_limiter.acquire()

        try:
            raw_reviews, next_token = fetch_reviews(
                app_id,
                lang=self._config.language,
                country=self._config.country,
                sort=Sort.NEWEST,
                count=PAGE_SIZE,
                continuation_token=continuation_token,
            )
        except NotFoundError:
            return RunResult(status=RunStatus.FAILED, records=[], reason="app_not_found")
        except Exception as exc:  # network errors, HTML/response structure changes, etc.
            return RunResult(status=RunStatus.FAILED, records=[], reason=str(exc))

        random_delay()

        in_window = [raw for raw in raw_reviews if self._in_window(raw, start, end)]
        deduped = self._dedupe_batch(in_window, app_id)

        next_app_index = app_index
        next_serialized_token = _serialize_token(next_token)
        if next_serialized_token is None:
            # This app's pagination is exhausted — advance to the next app_id.
            next_app_index = app_index + 1
            next_serialized_token = None

        exhausted = next_app_index >= len(self._config.app_ids)
        next_cursor = (
            None
            if exhausted
            else json.dumps({"app_index": next_app_index, "token": next_serialized_token})
        )

        return RunResult(
            status=RunStatus.SUCCESS,
            records=[{"raw": raw, "app_id": app_id} for raw in deduped],
            next_cursor=next_cursor,
        )

    def _in_window(self, raw: dict[str, Any], start: datetime, end: datetime) -> bool:
        at = raw.get("at")
        if at is None:
            return True
        at_utc = at if at.tzinfo else at.replace(tzinfo=UTC)
        return start <= at_utc <= end

    def _dedupe_batch(self, raws: list[dict[str, Any]], app_id: str) -> list[dict[str, Any]]:
        """Connector contract (§3): no exact duplicates within the connector's
        own batch — same ``url``, or same ``(platform, author, text)`` tuple."""
        seen: set[tuple[str, str, str]] = set()
        deduped: list[dict[str, Any]] = []
        for raw in raws:
            key = (app_id, raw.get("userName") or "", raw.get("content") or "")
            if key in seen:
                continue
            seen.add(key)
            deduped.append(raw)
        return deduped

    def normalize(self, raw_item: Any) -> Mention:
        raw = raw_item["raw"]
        app_id = raw_item["app_id"]

        at = raw.get("at")
        timestamp = (at if at and at.tzinfo else (at.replace(tzinfo=UTC) if at else None)) or (
            datetime.now(UTC)
        )
        text = _clean_text(raw.get("content") or "")
        url = f"{REVIEWS_URL_TEMPLATE.format(app_id=app_id)}&reviewId={raw.get('reviewId', '')}"
        now = datetime.now(UTC)

        return Mention(
            mention_id=compute_mention_id("google_play", url, timestamp, text),
            platform="google_play",
            source_type="review",
            collection_scope="app",
            search_term=None,
            collection_target=app_id,
            author=raw.get("userName"),
            url=url,
            text=text,
            language=None,
            timestamp=timestamp,
            scraped_at=now,
            raw_json=json.dumps(raw, default=str),
            reliability=self.reliability,
            connector_version=self.version,
            metadata={
                "star_rating": raw.get("score"),
                "app_version": raw.get("appVersion") or raw.get("reviewCreatedVersion"),
                "thumbs_up_count": raw.get("thumbsUpCount"),
            },
        )

    def validate(self, mention: Mention) -> bool:
        return bool(mention.text) and bool(mention.mention_id)

    def health(self) -> HealthStatus:
        """Lightweight reachability check: can we fetch app details at all right now.

        Consults the shared ``ConnectorHealthStore`` (the same one the
        orchestrator's auto-disable logic writes to, Milestone 2) rather than
        keeping any separate, connector-local failure counter.
        """
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
            fetch_app_details(self._config.app_ids[0], country=self._config.country)
            return HealthStatus(healthy=True, checked_at=datetime.now(UTC))
        except Exception as exc:
            return HealthStatus(healthy=False, reason=str(exc), checked_at=datetime.now(UTC))
