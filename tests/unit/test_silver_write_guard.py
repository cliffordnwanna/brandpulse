"""Unit tests for the Silver-write guard (Milestone 6 bug fix).

Direct ``backend.write("silver", ...)`` calls bypass Silver's dedup/
language-detection/emoji-normalization (all of which live inside
``process_bronze_record_to_silver``) — this guard makes that a hard error
rather than a silent data-quality bug, since the failure mode (unnormalized
text quietly reaching downstream phrase mining / word cloud / dedup) would
otherwise be invisible until someone noticed a report looked wrong.
"""

from pathlib import Path

import pytest

from brandpulse.pipeline.silver import process_bronze_record_to_silver
from brandpulse.storage.base import OperationNotPermittedError
from brandpulse.storage.local import LocalFileStorageBackend
from tests.fixtures.seed_silver import seed_silver_record


def test_direct_silver_write_raises(tmp_path: Path):
    backend = LocalFileStorageBackend(tmp_path / "storage")
    with pytest.raises(OperationNotPermittedError, match="process_bronze_record_to_silver"):
        backend.write("silver", "id-1", {"mention_id": "id-1", "text": "hi"})


def test_write_via_process_bronze_record_to_silver_succeeds(tmp_path: Path):
    backend = LocalFileStorageBackend(tmp_path / "storage")
    record = {"mention_id": "id-1", "text": "hi", "platform": "google_play"}

    written = process_bronze_record_to_silver(record, backend, seen_hashes=set())

    assert written is True
    assert backend.exists("silver", "id-1")


def test_seed_silver_record_helper_goes_through_the_real_pipeline(tmp_path: Path):
    """The test-fixture helper itself must exercise real Silver processing
    (emoji normalization, language detection) — not just fake the guard."""
    backend = LocalFileStorageBackend(tmp_path / "storage")
    silver_record = seed_silver_record(backend, "id-1", "This app dey stress me 😡")

    assert silver_record["language"] == "pcm"
    assert "😡" not in silver_record["text"]
    assert ":enraged_face:" in silver_record["text"]


def test_writes_to_bronze_and_gold_are_unaffected_by_the_guard(tmp_path: Path):
    backend = LocalFileStorageBackend(tmp_path / "storage")
    backend.write("bronze", "id-1", {"mention_id": "id-1"})
    backend.write("gold", "id-1_5a-v1", {"mention_id": "id-1"})
    assert backend.exists("bronze", "id-1")
    assert backend.exists("gold", "id-1_5a-v1")
