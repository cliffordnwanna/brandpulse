"""Unit tests for Gold storage writes (Engineering Design §13, Milestone 5)."""

from pathlib import Path

from brandpulse.pipeline.gold import gold_record_key, write_gold_record
from brandpulse.storage.local import LocalFileStorageBackend


def test_gold_record_key_combines_mention_id_and_version():
    assert gold_record_key("m1", "5a-v1") == "m1_5a-v1"


def test_write_gold_record_is_readable_back(tmp_path: Path):
    backend = LocalFileStorageBackend(tmp_path / "storage")
    write_gold_record(backend, "m1", "5a-v1", {"mention_id": "m1", "sentiment": "Positive"})

    records = list(backend.read_all("gold"))
    assert len(records) == 1
    assert records[0]["mention_id"] == "m1"


def test_new_classifier_version_creates_new_record_alongside_old(tmp_path: Path):
    backend = LocalFileStorageBackend(tmp_path / "storage")
    write_gold_record(backend, "m1", "5a-v1", {"mention_id": "m1", "classifier_version": "5a-v1"})
    write_gold_record(backend, "m1", "5a-v2", {"mention_id": "m1", "classifier_version": "5a-v2"})

    records = list(backend.read_all("gold"))
    assert len(records) == 2
    versions = {r["classifier_version"] for r in records}
    assert versions == {"5a-v1", "5a-v2"}


def test_rerunning_same_version_does_not_duplicate(tmp_path: Path):
    backend = LocalFileStorageBackend(tmp_path / "storage")
    write_gold_record(backend, "m1", "5a-v1", {"mention_id": "m1", "sentiment": "Positive"})
    write_gold_record(backend, "m1", "5a-v1", {"mention_id": "m1", "sentiment": "Negative"})

    records = list(backend.read_all("gold"))
    assert len(records) == 1
    # first write wins — idempotent, not overwritten, per StorageBackend.write contract
    assert records[0]["sentiment"] == "Positive"
