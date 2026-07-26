"""Unit tests for LocalFileStorageBackend (Milestone 4)."""

from pathlib import Path

import pytest

from brandpulse.storage.base import OperationNotPermittedError
from brandpulse.storage.local import LocalFileStorageBackend


@pytest.fixture
def backend(tmp_path: Path) -> LocalFileStorageBackend:
    return LocalFileStorageBackend(tmp_path / "storage")


def test_write_then_exists(backend: LocalFileStorageBackend):
    backend.write("bronze", "abc123", {"mention_id": "abc123", "text": "hello"})
    assert backend.exists("bronze", "abc123") is True
    assert backend.exists("bronze", "does-not-exist") is False


def test_write_is_idempotent(backend: LocalFileStorageBackend):
    backend.write("bronze", "abc123", {"mention_id": "abc123", "text": "first"})
    backend.write("bronze", "abc123", {"mention_id": "abc123", "text": "second"})

    records = list(backend.read_all("bronze"))

    assert len(records) == 1
    assert records[0]["text"] == "first"  # first write wins, second is a no-op


def test_read_all_returns_every_written_record(backend: LocalFileStorageBackend):
    backend.write("gold", "id-1", {"mention_id": "id-1"})
    backend.write("gold", "id-2", {"mention_id": "id-2"})

    ids = {record["mention_id"] for record in backend.read_all("gold")}

    assert ids == {"id-1", "id-2"}


def test_read_all_on_empty_tier_returns_nothing(backend: LocalFileStorageBackend):
    assert list(backend.read_all("gold")) == []


def test_delete_raises_for_bronze(backend: LocalFileStorageBackend):
    backend.write("bronze", "abc123", {"mention_id": "abc123"})

    with pytest.raises(OperationNotPermittedError):
        backend.delete("bronze", "abc123")

    assert backend.exists("bronze", "abc123") is True  # untouched


def test_delete_works_for_silver_and_gold(backend: LocalFileStorageBackend):
    backend.write("gold", "abc123", {"mention_id": "abc123"})
    backend.delete("gold", "abc123")
    assert backend.exists("gold", "abc123") is False


def test_clear_raises_for_bronze(backend: LocalFileStorageBackend):
    backend.write("bronze", "abc123", {"mention_id": "abc123"})

    with pytest.raises(OperationNotPermittedError):
        backend.clear("bronze")

    assert backend.exists("bronze", "abc123") is True  # untouched


def test_clear_wipes_silver(backend: LocalFileStorageBackend):
    backend.write("gold", "id-1", {"mention_id": "id-1"})
    backend.write("gold", "id-2", {"mention_id": "id-2"})

    backend.clear("gold")

    assert list(backend.read_all("gold")) == []


def test_storage_root_created_on_construction(tmp_path: Path):
    root = tmp_path / "fresh_storage_root"
    assert not root.exists()

    LocalFileStorageBackend(root)

    assert (root / "bronze").is_dir()
    assert (root / "silver").is_dir()
    assert (root / "gold").is_dir()
