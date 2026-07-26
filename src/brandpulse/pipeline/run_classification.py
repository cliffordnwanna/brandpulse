"""Runs the classification pipeline over every Silver record (Milestone 5).

This is the ``python -m brandpulse classify`` entry point's implementation:
reads all Silver records, drains them through the ``ClassificationQueue``
(so a slow/enrichment-heavy record never blocks the others), classifies each
via ``classify_silver_record``, writes Gold, and produces the session log.
"""

from __future__ import annotations

import uuid
from typing import Any

from brandpulse.config.models import Config
from brandpulse.pipeline.classification_queue import ClassificationQueue
from brandpulse.pipeline.classify.model_factory import (
    complaint_model_from_config,
    sentiment_model_from_config,
)
from brandpulse.pipeline.classify_pipeline import classify_silver_record
from brandpulse.pipeline.llm_client import LLMCallLogger, LLMClient, llm_client_from_config
from brandpulse.pipeline.session_log import build_session_summary, write_session_log
from brandpulse.storage.base import StorageBackend


def run_classification(
    backend: StorageBackend,
    config: Config,
    run_id: str | None = None,
    num_workers: int = 4,
    session_mention_ids: set[str] | None = None,
) -> dict[str, Any]:
    """Classify every Silver record, write Gold, and write a session log.

    5a classification always runs over the *entire* Silver tier regardless
    of scope — Gold is a cumulative store, and writes are idempotent
    per-mention (re-classifying an already-Gold mention is a cheap no-op),
    so there is no correctness or architectural reason to skip any Silver
    record here.

    ``session_mention_ids``, when given, scopes the *session log* (Milestone
    6's "snapshot" mode) to only those mention_ids — the session summary's
    sentiment/complaint/confidence distributions describe just what this
    run collected, not the full cumulative Gold history. Omit it (the
    default) for "incremental" mode, where the session log reflects
    everything currently classified.

    Returns the session summary dict that was written.
    """
    run_id = run_id or uuid.uuid4().hex

    sentiment_model = sentiment_model_from_config(config.classification.sentiment_model)
    complaint_classifier = complaint_model_from_config(config.classification.complaint_model)
    call_logger = LLMCallLogger()

    llm_client: LLMClient | None = None
    if config.classification.enable_enrichment:
        llm_client = llm_client_from_config(config.classification.enrichment_model)

    silver_records = list(backend.read_all("silver"))
    gold_records: list[dict[str, Any]] = []
    session_gold_records: list[dict[str, Any]] = []
    mention_counts_per_source: dict[str, int] = {}

    def _process(record: dict[str, Any]) -> None:
        gold_record = classify_silver_record(
            record,
            sentiment_model=sentiment_model,
            complaint_classifier=complaint_classifier,
            config=config.classification,
            llm_client=llm_client,
            call_logger=call_logger,
            backend=backend,
        )
        gold_records.append(gold_record)
        # 5a classifies every Silver record regardless of scope (Gold is
        # cumulative, writes are idempotent) — this filter only decides
        # what counts toward *this session's* summary, not what gets
        # classified.
        if session_mention_ids is None or record["mention_id"] in session_mention_ids:
            session_gold_records.append(gold_record)
            platform = record.get("platform", "unknown")
            mention_counts_per_source[platform] = mention_counts_per_source.get(platform, 0) + 1

    classification_queue = ClassificationQueue()
    classification_queue.put_all(silver_records)
    classification_queue.drain_with_workers(_process, num_workers=num_workers)

    session_summary = build_session_summary(
        run_id=run_id,
        sources_scraped=sorted(mention_counts_per_source.keys()),
        mention_counts_per_source=mention_counts_per_source,
        gold_records=session_gold_records,
        confidence_threshold=config.classification.confidence_threshold,
        failed_connectors=[],
    )
    write_session_log(config.output.directory, session_summary)

    return session_summary
