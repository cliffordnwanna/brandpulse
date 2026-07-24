"""A fake connector used only to validate Milestone 2's orchestration core.

Not a real source — deliberately lives under tests/, not connectors/, per
Milestone 2 §7 ("this is test scaffolding, not a real source"). It returns
canned data in batches and can be configured to fail on specific calls, so
tests can exercise checkpoint/resume and retry/auto-disable behavior.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from brandpulse.connectors.base import BaseConnector, HealthStatus, RunResult, RunStatus
from brandpulse.schema import Mention


class StubConnector(BaseConnector):
    """Canned-data connector for exercising the orchestrator in tests.

    ``batches`` is a list of "pages" of raw items; each call to ``search``
    advances one batch starting from ``start_batch_index``. ``fail_on_calls``
    is a set of 1-indexed call numbers (across the connector's lifetime) that
    should return ``RunStatus.FAILED`` instead of succeeding.
    """

    name = "stub_source"
    version = "0.0.1"
    reliability = "high"

    def __init__(
        self,
        batches: list[list[dict[str, Any]]] | None = None,
        fail_on_calls: set[int] | None = None,
    ) -> None:
        self.batches = batches if batches is not None else [[{"id": "1", "text": "great app"}]]
        self.fail_on_calls = fail_on_calls or set()
        self.call_count = 0

    def search(
        self,
        keywords: list[str],
        start: datetime,
        end: datetime,
        cursor: str | None = None,
    ) -> RunResult:
        """Return canned results, honoring ``fail_on_calls`` for this call number.

        No real pagination — always returns ``next_cursor=None``, so the
        orchestrator treats a single successful call as exhausted (matches
        this stub's Milestone 2 behavior; ``cursor`` is accepted but unused).
        """
        self.call_count += 1
        if self.call_count in self.fail_on_calls:
            return RunResult(status=RunStatus.FAILED, records=[], reason="stub_forced_failure")

        if not self.batches:
            return RunResult(status=RunStatus.NO_RESULTS, records=[])

        all_records: list[Any] = [item for batch in self.batches for item in batch]
        return RunResult(status=RunStatus.SUCCESS, records=all_records, next_cursor=None)

    def normalize(self, raw_item: Any) -> Mention:
        now = datetime.now(UTC)
        return Mention(
            mention_id=f"stub-{raw_item['id']}",
            platform="google_play",
            source_type="review",
            collection_scope="keyword",
            search_term="stub",
            collection_target=None,
            author="stub_author",
            url=f"https://example.com/{raw_item['id']}",
            text=raw_item["text"],
            language=None,
            timestamp=now,
            scraped_at=now,
            raw_json="{}",
            reliability="high",
            connector_version=self.version,
            metadata={},
        )

    def validate(self, mention: Mention) -> bool:
        return bool(mention.text)

    def health(self) -> HealthStatus:
        return HealthStatus(healthy=True)
