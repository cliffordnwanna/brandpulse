"""Storage backend factory (Milestone 4).

Resolves ``config.storage`` to a concrete ``StorageBackend`` — this is the
single place that knows which concrete classes exist. Adding a new backend
later means a new class under ``storage/`` and one new branch here; no other
code (orchestrator, pipeline, CLI) needs to change.
"""

from __future__ import annotations

from brandpulse.config.models import StorageConfig
from brandpulse.storage.base import StorageBackend
from brandpulse.storage.local import LocalFileStorageBackend


class UnsupportedStorageBackendError(Exception):
    """Raised when ``config.storage.backend`` names a backend that isn't implemented."""


class StorageBackendFactory:
    """Resolves a ``StorageBackend`` instance from config."""

    @staticmethod
    def from_config(storage_config: StorageConfig) -> StorageBackend:
        if storage_config.backend == "local":
            return LocalFileStorageBackend(storage_config.root)

        raise UnsupportedStorageBackendError(
            f"Unsupported storage backend: {storage_config.backend!r}. "
            "Supported: 'local'. (azure_blob/fabric_lakehouse/s3 are planned, not yet implemented.)"
        )
