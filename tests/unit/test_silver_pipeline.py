"""Unit tests for the Silver pipeline (Milestone 4): dedup, language tagging,
incremental processing, and full rebuild from Bronze.
"""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from brandpulse.pipeline.silver import (
    process_bronze_batch_to_silver,
    process_bronze_record_to_silver,
    rebuild_silver_from_bronze,
)
from brandpulse.storage.local import LocalFileStorageBackend


@pytest.fixture
def backend(tmp_path: Path) -> LocalFileStorageBackend:
    return LocalFileStorageBackend(tmp_path / "storage")


def _bronze_record(mention_id: str, text: str) -> dict:
    now = datetime(2026, 1, 1, tzinfo=UTC).isoformat()
    return {
        "mention_id": mention_id,
        "platform": "google_play",
        "source_type": "review",
        "collection_scope": "app",
        "search_term": None,
        "collection_target": "com.example.wema",
        "author": "someone",
        "url": f"https://example.com/{mention_id}",
        "text": text,
        "language": None,
        "timestamp": now,
        "scraped_at": now,
        "raw_json": "{}",
        "reliability": "high",
        "connector_version": "0.1.0",
        "metadata": {},
    }


def test_new_record_is_written_to_silver(backend: LocalFileStorageBackend):
    record = _bronze_record("id-1", "Great app!")
    seen_hashes: set[str] = set()

    written = process_bronze_record_to_silver(record, backend, seen_hashes)

    assert written is True
    assert backend.exists("silver", "id-1")


def test_record_gets_non_null_language(backend: LocalFileStorageBackend):
    record = _bronze_record("id-1", "This app dey stress me well well.")
    process_bronze_record_to_silver(record, backend, set())

    silver_record = next(iter(backend.read_all("silver")))
    assert silver_record["language"] is not None
    assert silver_record["language"] == "pcm"


def test_duplicate_mention_id_is_skipped(backend: LocalFileStorageBackend):
    record = _bronze_record("id-1", "Great app!")
    seen_hashes: set[str] = set()

    first = process_bronze_record_to_silver(record, backend, seen_hashes)
    second = process_bronze_record_to_silver(record, backend, seen_hashes)

    assert first is True
    assert second is False
    assert len(list(backend.read_all("silver"))) == 1


def test_cross_source_text_duplicate_is_skipped(backend: LocalFileStorageBackend):
    """Same normalized text, different mention_id (e.g. reposted across
    sources/runs) — Silver-level tier-2 dedup, distinct from the connector's
    own within-batch tier-1 dedup (Engineering Design §11)."""
    record_a = _bronze_record("id-1", "Great app, easy transfers!")
    record_b = _bronze_record("id-2", "great app, easy transfers!")  # same text, different case
    seen_hashes: set[str] = set()

    written_a = process_bronze_record_to_silver(record_a, backend, seen_hashes)
    written_b = process_bronze_record_to_silver(record_b, backend, seen_hashes)

    assert written_a is True
    assert written_b is False
    assert len(list(backend.read_all("silver"))) == 1


def test_process_batch_reflects_dedup_across_the_whole_batch(backend: LocalFileStorageBackend):
    batch = [
        _bronze_record("id-1", "Great app!"),
        _bronze_record("id-2", "Great app!"),  # duplicate of id-1
        _bronze_record("id-3", "Terrible app!"),
    ]

    written_count = process_bronze_batch_to_silver(batch, backend)

    assert written_count == 2
    assert len(list(backend.read_all("silver"))) == 2


def test_rebuild_produces_identical_result_to_incremental(backend: LocalFileStorageBackend):
    records = [
        _bronze_record("id-1", "Great app!"),
        _bronze_record("id-2", "Great app!"),  # duplicate
        _bronze_record("id-3", "Terrible app, transfer failed."),
        _bronze_record("id-4", "This app dey stress me well well."),
    ]
    for record in records:
        backend.write("bronze", record["mention_id"], record)

    incremental_written = process_bronze_batch_to_silver(records, backend)
    incremental_result = {r["mention_id"]: r["language"] for r in backend.read_all("silver")}

    rebuilt_written = rebuild_silver_from_bronze(backend)
    rebuilt_result = {r["mention_id"]: r["language"] for r in backend.read_all("silver")}

    assert incremental_written == rebuilt_written
    assert incremental_result == rebuilt_result


def test_rebuild_wipes_existing_silver_first(backend: LocalFileStorageBackend):
    backend.write("bronze", "id-1", _bronze_record("id-1", "Great app!"))
    process_bronze_record_to_silver(_bronze_record("stale-record", "stale"), backend, set())

    rebuild_silver_from_bronze(backend)

    ids = {r["mention_id"] for r in backend.read_all("silver")}
    assert "stale-record" not in ids
    assert "id-1" in ids


def test_rebuild_from_empty_bronze_produces_empty_silver(backend: LocalFileStorageBackend):
    written = rebuild_silver_from_bronze(backend)
    assert written == 0
    assert list(backend.read_all("silver")) == []
