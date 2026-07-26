"""Storage backend abstraction (Milestone 4).

All pipeline code (orchestrator, Silver processing, CLI) depends on this
interface, never on a concrete backend directly. That's what makes moving
from local files to Azure Blob/Fabric Lakehouse/S3 later a config change
(``StorageBackendFactory``) rather than a pipeline rewrite.
"""

from __future__ import annotations

import sys
from abc import ABC, abstractmethod
from collections.abc import Iterable
from typing import Any, Literal

Tier = Literal["bronze", "silver", "gold"]

_SILVER_WRITE_ENTRY_POINT = "process_bronze_record_to_silver"


class OperationNotPermittedError(Exception):
    """Raised when an operation would violate a tier's storage policy.

    E.g. deleting from Bronze — Bronze is append-only by architecture
    invariant (CLAUDE.md), enforced here at the backend level, not just by
    convention in calling code.
    """


def assert_silver_write_allowed() -> None:
    """Raise ``OperationNotPermittedError`` unless the call stack shows this
    write originated from ``pipeline.silver.process_bronze_record_to_silver``.

    Silver's dedup/language-detection/emoji-normalization logic all lives in
    that one function — a write to Silver from anywhere else would bypass
    all of it (e.g. raw, non-emoji-normalized text reaching Silver directly),
    silently breaking the "every Silver record went through Silver
    processing" guarantee the rest of the pipeline (word cloud, phrase
    mining, dedup) depends on. Concrete ``StorageBackend`` implementations
    call this at the top of ``write()`` for ``tier="silver"``.
    """
    frame = sys._getframe(1)
    while frame is not None:
        if frame.f_code.co_name == _SILVER_WRITE_ENTRY_POINT:
            return
        frame = frame.f_back
    raise OperationNotPermittedError(
        "Writes to the 'silver' tier must go through "
        "pipeline.silver.process_bronze_record_to_silver — direct backend.write("
        "'silver', ...) calls bypass dedup/language-detection/emoji-normalization."
    )


class StorageBackend(ABC):
    """Storage abstraction every tier (Bronze/Silver/Gold) is written through."""

    @abstractmethod
    def write(self, tier: Tier, mention_id: str, record: dict[str, Any]) -> None:
        """Write ``record`` under ``mention_id`` in ``tier``.

        Idempotent: writing the same ``mention_id`` twice is a no-op, not an
        overwrite and not a duplicate — this is what makes ingestion runs and
        Silver reprocessing safe to repeat.
        """
        raise NotImplementedError

    @abstractmethod
    def exists(self, tier: Tier, mention_id: str) -> bool:
        """Return whether a record for ``mention_id`` already exists in ``tier``."""
        raise NotImplementedError

    @abstractmethod
    def read_all(self, tier: Tier) -> Iterable[dict[str, Any]]:
        """Iterate every record currently stored in ``tier``."""
        raise NotImplementedError

    @abstractmethod
    def delete(self, tier: Tier, mention_id: str) -> None:
        """Delete a record from ``tier``.

        Concrete backends must raise ``OperationNotPermittedError`` for
        ``tier="bronze"`` — Bronze is append-only, enforced here rather than
        left to caller discipline.
        """
        raise NotImplementedError

    @abstractmethod
    def clear(self, tier: Tier) -> None:
        """Wipe every record in ``tier``.

        Used by Silver/Gold regeneration (never valid for Bronze — concrete
        backends must raise ``OperationNotPermittedError`` for ``tier="bronze"``
        here too, for the same append-only reason as ``delete``).
        """
        raise NotImplementedError
