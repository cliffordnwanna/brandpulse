"""YouTube connector (Engineering Design §3, Milestone 7).

Genuinely keyword-searched (``collection_scope="keyword"``) — two-step
process per keyword: ``search.list`` finds videos mentioning the keyword,
then ``commentThreads.list`` fetches comments (and their replies) for each
video found. Video titles/descriptions are never collected as mention text
— only comments and comment replies, since those are customer voice, not
marketing copy (Milestone 7 spec).

Uses the YouTube Data API v3 via ``google-api-python-client``.
``YOUTUBE_API_KEY`` is read from the environment only — never from
config.yaml or any committed file (Engineering Design §17 / CLAUDE.md
"never hardcode source lists" invariant extends to credentials).
"""

from __future__ import annotations

import json
import os
import re
import unicodedata
from datetime import UTC, datetime
from typing import Any

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from brandpulse.config.models import RateLimitConfig, YouTubeConfig
from brandpulse.connectors.base import BaseConnector, HealthStatus, RunResult, RunStatus
from brandpulse.connectors.politeness import RateLimiter
from brandpulse.orchestration.connector_health import ConnectorHealthStore
from brandpulse.orchestration.idempotency import compute_mention_id
from brandpulse.schema import Mention

YOUTUBE_API_KEY_ENV_VAR = "YOUTUBE_API_KEY"
VIDEO_URL_TEMPLATE = "https://www.youtube.com/watch?v={video_id}"


def _clean_text(text: str) -> str:
    """Bronze normalization (Engineering Design §3): whitespace-collapsed,
    control characters stripped, UTF-8-safe — never rewrites content."""
    normalized = unicodedata.normalize("NFC", text)
    utf8_safe = normalized.encode("utf-8", errors="replace").decode("utf-8")
    no_control_chars = "".join(
        ch for ch in utf8_safe if ch in ("\n", "\t") or not unicodedata.category(ch).startswith("C")
    )
    return re.sub(r"\s+", " ", no_control_chars).strip()


def _error_reason(exc: HttpError) -> str:
    try:
        details = exc.error_details
        if details:
            return details[0].get("reason", str(exc))
    except Exception:
        pass
    return str(exc)


def _is_quota_error(exc: HttpError) -> bool:
    status = getattr(exc.resp, "status", None)
    return status == 403 and _error_reason(exc) in ("quotaExceeded", "dailyLimitExceeded")


def _is_comments_disabled_error(exc: HttpError) -> bool:
    return _error_reason(exc) == "commentsDisabled"


def _deserialize_cursor(cursor: str | None) -> dict[str, Any]:
    """Cursor state: which video (by index into this keyword's search
    results) we're on, plus that video's comment-page token. Video search
    results themselves aren't re-paginated within one job — ``max_videos_per_keyword``
    is fetched in a single ``search.list`` call, then walked one video at a time."""
    if cursor is None:
        return {"video_ids": None, "video_index": 0, "comment_page_token": None}
    return json.loads(cursor)


class YouTubeConnector(BaseConnector):
    """Searches YouTube per configured keyword, collecting video comments + replies."""

    name = "youtube"
    version = "0.1.0"
    reliability = "high"
    collection_scope = "keyword"
    is_keyword_driven = True

    def __init__(
        self,
        config: YouTubeConfig,
        rate_limit_config: RateLimitConfig,
        health_store: ConnectorHealthStore,
        rate_limiter: RateLimiter | None = None,
        api_key: str | None = None,
    ) -> None:
        self._config = config
        self._rate_limit_config = rate_limit_config
        self._health_store = health_store
        self._rate_limiter = rate_limiter or RateLimiter(rate_limit_config.requests_per_minute)
        # ``api_key`` param exists only so tests can inject a fake key without
        # touching process env vars; production always reads the environment.
        self._api_key = api_key or os.environ.get(YOUTUBE_API_KEY_ENV_VAR)

    def _client(self):
        return build("youtube", "v3", developerKey=self._api_key)

    def search(
        self,
        keywords: list[str],
        start: datetime,
        end: datetime,
        cursor: str | None = None,
    ) -> RunResult:
        """Fetch one page of comments (across the keyword's found videos).

        Each call is one page/batch for orchestrator checkpointing purposes.
        The orchestrator drives this connector with one job per configured
        keyword, so ``keywords`` here is always the single keyword for this job.
        """
        if not keywords:
            return RunResult(status=RunStatus.NO_RESULTS, records=[], next_cursor=None)

        if not self._api_key:
            return RunResult(
                status=RunStatus.FAILED,
                records=[],
                reason=f"Set {YOUTUBE_API_KEY_ENV_VAR} environment variable",
            )

        keyword = keywords[0]
        state = _deserialize_cursor(cursor)

        try:
            youtube = self._client()

            if state["video_ids"] is None:
                self._rate_limiter.acquire()
                search_response = youtube.search().list(
                    q=keyword,
                    part="snippet",
                    type="video",
                    maxResults=self._config.max_videos_per_keyword,
                    publishedAfter=start.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    publishedBefore=end.strftime("%Y-%m-%dT%H:%M:%SZ"),
                ).execute()
                state["video_ids"] = [
                    item["id"]["videoId"] for item in search_response.get("items", [])
                ]
                state["video_index"] = 0
                state["comment_page_token"] = None

            video_ids: list[str] = state["video_ids"]

            if not video_ids:
                return RunResult(status=RunStatus.NO_RESULTS, records=[], next_cursor=None)

            records: list[dict[str, Any]] = []
            video_index = state["video_index"]

            while video_index < len(video_ids):
                video_id = video_ids[video_index]
                self._rate_limiter.acquire()
                try:
                    comments_response = youtube.commentThreads().list(
                        videoId=video_id,
                        part="snippet,replies",
                        maxResults=min(self._config.max_comments_per_video, 100),
                        textFormat="plainText",
                        pageToken=state["comment_page_token"],
                    ).execute()
                except HttpError as exc:
                    if _is_comments_disabled_error(exc):
                        video_index += 1
                        state["comment_page_token"] = None
                        continue
                    if _is_quota_error(exc):
                        next_cursor = json.dumps(
                            {
                                "video_ids": video_ids,
                                "video_index": video_index,
                                "comment_page_token": state["comment_page_token"],
                            }
                        )
                        return RunResult(
                            status=RunStatus.PARTIAL_SUCCESS,
                            records=records,
                            reason="quotaExceeded",
                            next_cursor=next_cursor,
                        )
                    raise

                for thread in comments_response.get("items", []):
                    records.append(
                        {"raw": thread["snippet"]["topLevelComment"], "video_id": video_id, "keyword": keyword}
                    )
                    for reply in thread.get("replies", {}).get("comments", []):
                        records.append({"raw": reply, "video_id": video_id, "keyword": keyword})

                next_page_token = comments_response.get("nextPageToken")
                if next_page_token is None:
                    video_index += 1
                    state["comment_page_token"] = None
                    break  # yield this batch; resume at the next video on the following call
                else:
                    state["comment_page_token"] = next_page_token
                    break  # yield this batch; resume this same video's next comment page

        except HttpError as exc:
            if _is_quota_error(exc):
                return RunResult(status=RunStatus.PARTIAL_SUCCESS, records=[], reason="quotaExceeded")
            return RunResult(status=RunStatus.FAILED, records=[], reason=_error_reason(exc))
        except Exception as exc:  # network errors, etc.
            return RunResult(status=RunStatus.FAILED, records=[], reason=str(exc))

        state["video_index"] = video_index
        exhausted = video_index >= len(video_ids)
        next_cursor = None if exhausted else json.dumps(state)

        if not records and exhausted:
            return RunResult(status=RunStatus.NO_RESULTS, records=[], next_cursor=None)

        deduped = self._dedupe_batch(records)

        return RunResult(
            status=RunStatus.SUCCESS,
            records=deduped,
            next_cursor=next_cursor,
        )

    def _dedupe_batch(self, raws: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Connector contract (§3): no exact duplicates within the connector's
        own batch — same comment id."""
        seen: set[str] = set()
        deduped: list[dict[str, Any]] = []
        for item in raws:
            comment_id = item["raw"].get("id", "")
            if comment_id in seen:
                continue
            seen.add(comment_id)
            deduped.append(item)
        return deduped

    def normalize(self, raw_item: Any) -> Mention:
        raw = raw_item["raw"]
        video_id = raw_item["video_id"]
        keyword = raw_item["keyword"]
        snippet = raw.get("snippet", {})

        published_at = snippet.get("publishedAt")
        try:
            timestamp = (
                datetime.strptime(published_at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
                if published_at
                else datetime.now(UTC)
            )
        except ValueError:
            timestamp = datetime.now(UTC)

        text = _clean_text(snippet.get("textDisplay") or snippet.get("textOriginal") or "")
        comment_id = raw.get("id", "")
        url = f"{VIDEO_URL_TEMPLATE.format(video_id=video_id)}&lc={comment_id}"
        now = datetime.now(UTC)

        return Mention(
            mention_id=compute_mention_id("youtube", url, timestamp, text),
            platform="youtube",
            source_type="comment",
            collection_scope="keyword",
            search_term=keyword,
            collection_target=video_id,
            author=snippet.get("authorDisplayName"),
            url=url,
            text=text,
            language=None,
            timestamp=timestamp,
            scraped_at=now,
            raw_json=json.dumps(raw, default=str),
            reliability=self.reliability,
            connector_version=self.version,
            metadata={
                "like_count": snippet.get("likeCount"),
                "video_id": video_id,
            },
        )

    def validate(self, mention: Mention) -> bool:
        return bool(mention.text) and bool(mention.mention_id)

    def health(self) -> HealthStatus:
        """Lightweight reachability check: is a valid API key configured and
        can we reach the API at all right now. Consults the shared
        ``ConnectorHealthStore`` — same pattern as the other connectors."""
        cross_run_health = self._health_store.get(self.name)
        if cross_run_health.consecutive_failures >= 3:
            return HealthStatus(
                healthy=False,
                reason="auto_disabled_after_consecutive_failures",
                checked_at=datetime.now(UTC),
            )

        if not self._api_key:
            return HealthStatus(
                healthy=False,
                reason=f"Set {YOUTUBE_API_KEY_ENV_VAR} environment variable",
                checked_at=datetime.now(UTC),
            )

        try:
            youtube = self._client()
            youtube.search().list(q="test", part="id", type="video", maxResults=1).execute()
            return HealthStatus(healthy=True, checked_at=datetime.now(UTC))
        except HttpError as exc:
            return HealthStatus(healthy=False, reason=_error_reason(exc), checked_at=datetime.now(UTC))
        except Exception as exc:
            return HealthStatus(healthy=False, reason=str(exc), checked_at=datetime.now(UTC))
