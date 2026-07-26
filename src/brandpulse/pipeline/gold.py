"""Gold storage writes (Engineering Design §13, Milestone 5).

Classifications are never overwritten — a new classifier version writes a
new Gold record alongside the old one, keyed ``{mention_id}_{classifier_version}``.
``StorageBackend.write`` (Milestone 4) is already idempotent per key, so
re-running the *same* classifier version over the *same* mention is a no-op
here for free — this module only needs to compute the versioned key.
"""

from __future__ import annotations

from typing import Any

from brandpulse.storage.base import StorageBackend


def gold_record_key(mention_id: str, classifier_version: str) -> str:
    return f"{mention_id}_{classifier_version}"


def write_gold_record(
    backend: StorageBackend, mention_id: str, classifier_version: str, record: dict[str, Any]
) -> None:
    key = gold_record_key(mention_id, classifier_version)
    backend.write("gold", key, record)
