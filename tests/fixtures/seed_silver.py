"""Test helper for seeding Silver records through the real Silver pipeline.

``backend.write("silver", ...)`` directly is blocked outside
``pipeline.silver.process_bronze_record_to_silver`` (Milestone 6) — a direct
write would bypass dedup/language-detection/emoji-normalization, which is
exactly the class of bug that guard exists to catch. Tests that need
pre-existing Silver data seed it through this helper instead, which writes a
Bronze record and runs the real Silver pipeline over it — exercising actual
code rather than faking the shape of its output.
"""

from __future__ import annotations

from typing import Any

from brandpulse.pipeline.silver import process_bronze_record_to_silver
from brandpulse.storage.base import StorageBackend


def seed_silver_record(
    backend: StorageBackend, mention_id: str, text: str, platform: str = "google_play", **extra: Any
) -> dict[str, Any]:
    """Write a Bronze record for ``mention_id`` and process it into Silver.

    Returns the resulting Silver record. Extra keyword args are merged into
    the Bronze record before processing (e.g. ``author=...``).
    """
    bronze_record = {"mention_id": mention_id, "text": text, "platform": platform, **extra}
    backend.write("bronze", mention_id, bronze_record)
    process_bronze_record_to_silver(bronze_record, backend, seen_hashes=set())
    return next(r for r in backend.read_all("silver") if r["mention_id"] == mention_id)
