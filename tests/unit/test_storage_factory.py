"""Unit tests for StorageBackendFactory (Milestone 4)."""

from pathlib import Path

import pytest

from brandpulse.config.models import StorageConfig
from brandpulse.storage.factory import StorageBackendFactory, UnsupportedStorageBackendError
from brandpulse.storage.local import LocalFileStorageBackend


def test_local_backend_resolves_from_config(tmp_path: Path):
    config = StorageConfig(backend="local", root=str(tmp_path / "storage"))

    backend = StorageBackendFactory.from_config(config)

    assert isinstance(backend, LocalFileStorageBackend)


def test_unsupported_backend_raises_clear_error():
    config = StorageConfig(backend="azure_blob", root="az://container/brandpulse/")

    with pytest.raises(UnsupportedStorageBackendError, match="azure_blob"):
        StorageBackendFactory.from_config(config)
