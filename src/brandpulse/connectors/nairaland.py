"""Nairaland forum connector (Engineering Design §3, Milestone 7).

Genuinely keyword-searched (``collection_scope="forum"``) — unlike Google
Play/App Store's bounded-entity pattern, Nairaland has no fixed set of
"targets" to walk; it's searched per keyword from ``config.keywords.base_list``,
same as any other keyword-scoped connector in the orchestrator's job loop.

Uses ``requests`` + ``beautifulsoup4``/``lxml`` against Nairaland's static
HTML search results page (``nairaland.com/search?q=...&board=0&p=N``) —
confirmed during this milestone's build that the search endpoint returns
full server-rendered HTML with no JavaScript required (unlike
``nairaland.com/robots.txt``, which is behind a Cloudflare bot-check page;
the search endpoint itself is not). Playwright was evaluated and is not
needed here.

Both thread-opening posts and replies are collected — a thread's replies are
where the bulk of customer-voice signal actually lives (Milestone 7 spec:
"a thread about Wema Bank with 80 replies is 80 data points, not 1"). This
connector doesn't distinguish opening-post vs. reply structurally (Nairaland's
search results don't expose that distinction cleanly) — every matched post
row is collected as one ``source_type="forum_reply"`` mention; `Silver-level`
dedup collapses genuine duplicates across overlapping keyword searches, since
this connector never pre-filters (Engineering Design §11).
"""

from __future__ import annotations

import json
import re
import unicodedata
from datetime import UTC, datetime
from typing import Any

import requests
from bs4 import BeautifulSoup

from brandpulse.config.models import NairalandConfig, RateLimitConfig
from brandpulse.connectors.base import BaseConnector, HealthStatus, RunResult, RunStatus
from brandpulse.connectors.politeness import RateLimiter, is_allowed_by_robots_txt, random_delay
from brandpulse.orchestration.connector_health import ConnectorHealthStore
from brandpulse.orchestration.idempotency import compute_mention_id
from brandpulse.schema import Mention

USER_AGENT = "BrandPulseBot/0.1 (+https://github.com/wema-bank/brandpulse)"
BASE_URL = "https://www.nairaland.com"
SEARCH_URL = f"{BASE_URL}/search"
REQUEST_TIMEOUT_SECONDS = 15

_MONTHS = {
    "Jan": 1,
    "Feb": 2,
    "Mar": 3,
    "Apr": 4,
    "May": 5,
    "Jun": 6,
    "Jul": 7,
    "Aug": 8,
    "Sep": 9,
    "Oct": 10,
    "Nov": 11,
    "Dec": 12,
}
_TIMESTAMP_RE = re.compile(
    r"(?P<time>\d{1,2}:\d{2}(?:am|pm))\s+On\s+(?P<month>[A-Za-z]{3})\s+(?P<day>\d{1,2})"
    r"(?:,\s*(?P<year>\d{4}))?"
)


def _clean_text(text: str) -> str:
    """Bronze normalization (Engineering Design §3): whitespace-collapsed,
    control characters stripped, UTF-8-safe — never rewrites content."""
    normalized = unicodedata.normalize("NFC", text)
    utf8_safe = normalized.encode("utf-8", errors="replace").decode("utf-8")
    no_control_chars = "".join(
        ch for ch in utf8_safe if ch in ("\n", "\t") or not unicodedata.category(ch).startswith("C")
    )
    return re.sub(r"\s+", " ", no_control_chars).strip()


def _parse_timestamp(label: str, scraped_at: datetime) -> datetime | None:
    """Parse Nairaland's "6:51pm On Jul 23[, 2025]" timestamp format.

    Returns ``None`` if the text doesn't match at all (caller treats that as
    "assume in window" — fail open, same pattern as Google Play's
    ``_in_window``, since a parse miss shouldn't silently drop real data).
    Year is inferred from ``scraped_at`` when absent — Nairaland omits the
    year for posts made in the current year.
    """
    match = _TIMESTAMP_RE.search(label)
    if not match:
        return None
    month = _MONTHS.get(match.group("month"))
    if month is None:
        return None
    day = int(match.group("day"))
    year = int(match.group("year")) if match.group("year") else scraped_at.year
    time_str = match.group("time")
    try:
        time_part = datetime.strptime(time_str, "%I:%M%p")
    except ValueError:
        return None
    try:
        return datetime(
            year, month, day, time_part.hour, time_part.minute, tzinfo=UTC
        )
    except ValueError:
        return None


def _extract_posts(html: str, keyword: str) -> list[dict[str, Any]]:
    """Parse one search-results page into a list of raw post dicts.

    Each result on the page is a ``<td class="bold l pu">`` row (title,
    section, author, permalink, timestamp) immediately followed by a
    ``<td id="pb{post_id}">`` row (the post body text).
    """
    soup = BeautifulSoup(html, "lxml")
    title_rows = soup.select("td.bold.l.pu")
    posts: list[dict[str, Any]] = []

    for title_row in title_rows:
        content_row = title_row.find_next("td", id=re.compile(r"^pb\d+"))
        if content_row is None:
            continue

        post_id_match = re.match(r"pb(\d+)", content_row.get("id", ""))
        post_id = post_id_match.group(1) if post_id_match else None
        if post_id is None:
            continue

        permalink_tag = None
        for a_tag in title_row.find_all("a"):
            href = a_tag.get("href") or ""
            if href.startswith("/") and re.search(r"#\d+$", href):
                permalink_tag = a_tag
                break

        author_tag = title_row.find("a", class_="user")
        timestamp_tag = title_row.find("span", class_="s")

        posts.append(
            {
                "post_id": post_id,
                "title": permalink_tag.get_text(strip=True) if permalink_tag else "",
                "permalink": (BASE_URL + permalink_tag["href"]) if permalink_tag else None,
                "author": author_tag.get_text(strip=True) if author_tag else None,
                "timestamp_label": timestamp_tag.get_text(" ", strip=True) if timestamp_tag else "",
                "content": content_row.get_text(" ", strip=True),
                "keyword": keyword,
            }
        )

    return posts


class NairalandConnector(BaseConnector):
    """Searches Nairaland per configured keyword, collecting posts + replies.

    ``collection_scope="forum"`` — genuinely keyword-driven (Engineering
    Design §2), the opposite of Google Play/App Store's bounded-entity scope.
    """

    name = "nairaland"
    version = "0.1.0"
    reliability = "medium"
    collection_scope = "forum"
    is_keyword_driven = True

    def __init__(
        self,
        config: NairalandConfig,
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
        """Fetch one page of search results for the current keyword.

        Each call is one page/batch for orchestrator checkpointing purposes.
        The orchestrator drives this connector with one job per configured
        keyword (``collection_scope="forum"`` — a keyword-scoped connector),
        so ``keywords`` here is always the single keyword for this job.
        """
        if not keywords:
            return RunResult(status=RunStatus.NO_RESULTS, records=[], next_cursor=None)

        keyword = keywords[0]
        page = int(cursor) if cursor else 1

        if page > self._config.max_pages:
            return RunResult(status=RunStatus.NO_RESULTS, records=[], next_cursor=None)

        params = {"q": keyword, "board": 0, "p": page}
        search_url = f"{SEARCH_URL}?q={requests.utils.quote(keyword)}&board=0&p={page}"

        if self._rate_limit_config.respect_robots_txt and not is_allowed_by_robots_txt(
            SEARCH_URL, USER_AGENT
        ):
            return RunResult(status=RunStatus.FAILED, records=[], reason="disallowed_by_robots_txt")

        self._rate_limiter.acquire()

        try:
            response = requests.get(
                SEARCH_URL,
                params=params,
                headers={"User-Agent": USER_AGENT},
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            html = response.text
        except Exception as exc:  # network errors, HTML structure changes, rate limiting, etc.
            return RunResult(status=RunStatus.FAILED, records=[], reason=str(exc))

        random_delay()

        scraped_at = datetime.now(UTC)
        try:
            posts = _extract_posts(html, keyword)
        except Exception as exc:  # defensive: a layout change shouldn't crash the run
            return RunResult(status=RunStatus.FAILED, records=[], reason=f"parse_error: {exc}")

        if not posts:
            # An empty *first* page is a genuine no-results search. An empty
            # *later* page means pagination naturally ran out (Nairaland's
            # search doesn't expose a total-pages count up front) — that's
            # "successfully finished with nothing more," not "no results at
            # all," so it must report SUCCESS/next_cursor=None rather than
            # NO_RESULTS, which the orchestrator treats as "stop without
            # marking this keyword exhausted" (a NO_RESULTS run should be
            # retried on a future run, unlike genuine pagination exhaustion).
            if page == 1:
                return RunResult(status=RunStatus.NO_RESULTS, records=[], next_cursor=None)
            return RunResult(status=RunStatus.SUCCESS, records=[], next_cursor=None)

        in_window = [p for p in posts if self._in_window(p, start, end, scraped_at)]
        deduped = self._dedupe_batch(in_window)

        next_page = page + 1
        next_cursor = None if next_page > self._config.max_pages else str(next_page)

        return RunResult(
            status=RunStatus.SUCCESS,
            records=[{"raw": p, "search_url": search_url} for p in deduped],
            next_cursor=next_cursor,
        )

    def _in_window(
        self, raw: dict[str, Any], start: datetime, end: datetime, scraped_at: datetime
    ) -> bool:
        timestamp = _parse_timestamp(raw["timestamp_label"], scraped_at)
        if timestamp is None:
            return True  # fail open — parse miss shouldn't drop real data
        return start <= timestamp <= end

    def _dedupe_batch(self, raws: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Connector contract (§3): no exact duplicates within the connector's
        own batch — same permalink, or same (author, content) tuple. Does
        NOT dedupe across separate keyword searches — Silver-level dedup
        handles cross-search/cross-run duplicates (Engineering Design §11)."""
        seen: set[tuple[str, str]] = set()
        deduped: list[dict[str, Any]] = []
        for raw in raws:
            key = (raw.get("permalink") or raw["post_id"], raw.get("content") or "")
            if key in seen:
                continue
            seen.add(key)
            deduped.append(raw)
        return deduped

    def normalize(self, raw_item: Any) -> Mention:
        raw = raw_item["raw"]
        search_url = raw_item["search_url"]

        scraped_at = datetime.now(UTC)
        timestamp = _parse_timestamp(raw["timestamp_label"], scraped_at) or scraped_at
        text = _clean_text(raw.get("content") or "")
        url = raw.get("permalink") or f"{BASE_URL}/post/{raw['post_id']}"

        return Mention(
            mention_id=compute_mention_id("nairaland", url, timestamp, text),
            platform="nairaland",
            source_type="forum_reply",
            collection_scope="forum",
            search_term=raw.get("keyword"),
            collection_target="nairaland.com",
            author=raw.get("author"),
            url=url,
            text=text,
            language=None,
            timestamp=timestamp,
            scraped_at=scraped_at,
            raw_json=json.dumps(raw, default=str),
            reliability=self.reliability,
            connector_version=self.version,
            metadata={
                "title": raw.get("title"),
                "post_id": raw.get("post_id"),
                "search_url": search_url,
            },
        )

    def validate(self, mention: Mention) -> bool:
        return bool(mention.text) and bool(mention.mention_id)

    def health(self) -> HealthStatus:
        """Lightweight reachability check: can we reach the search endpoint
        at all right now. Consults the shared ``ConnectorHealthStore`` — same
        pattern as Google Play/App Store, no separate failure counter."""
        cross_run_health = self._health_store.get(self.name)
        if cross_run_health.consecutive_failures >= 3:
            return HealthStatus(
                healthy=False,
                reason="auto_disabled_after_consecutive_failures",
                checked_at=datetime.now(UTC),
            )

        try:
            response = requests.get(
                SEARCH_URL,
                params={"q": "test", "board": 0, "p": 1},
                headers={"User-Agent": USER_AGENT},
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            return HealthStatus(healthy=True, checked_at=datetime.now(UTC))
        except Exception as exc:
            return HealthStatus(healthy=False, reason=str(exc), checked_at=datetime.now(UTC))
