"""Silver-level near-duplicate detection (Engineering Design §11, Milestone 4).

Tier 1 (connector-level, exact-match within a batch) already happened before
Bronze — see each connector's ``_dedupe_batch``. This is tier 2: cross-
source/cross-run dedup via text hash. Embedding-similarity matching for
near-identical reposts is an explicit Phase 2 upgrade, not implemented here
(too slow/expensive for local MVP execution) — see Engineering Design §11.
"""

from __future__ import annotations

import hashlib

from brandpulse.orchestration.idempotency import normalize_text


def text_hash(text: str) -> str:
    """SHA256 of the normalized (whitespace-collapsed, lowercased) text.

    Used as the Silver-level dedup key — two records with the same
    normalized text are treated as duplicates regardless of source/run.
    """
    return hashlib.sha256(normalize_text(text).encode("utf-8")).hexdigest()
