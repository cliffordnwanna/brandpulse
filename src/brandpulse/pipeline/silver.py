"""Silver pipeline (Milestone 4): Bronze -> dedup -> language detect -> Silver.

Silver is always derivable from Bronze alone (Engineering Design §9,
CLAUDE.md invariant #9) — ``rebuild_silver_from_bronze`` is the proof: it
wipes Silver and reprocesses every Bronze record from scratch, and must
produce the same result as the incrementally-built version.

Milestone 6 adds emoji normalization as the first text-cleaning step, run
before dedup/language-detection so both operate on the normalized text
(``😡`` -> ``:enraged_face:``) — emojis carry real sentiment signal in
Nigerian social media text and must never be stripped.
"""

from __future__ import annotations

from typing import Any

from brandpulse.pipeline.dedupe import text_hash
from brandpulse.pipeline.emoji_normalize import normalize_emoji
from brandpulse.pipeline.language_detect import detect_language
from brandpulse.storage.base import StorageBackend


def _seen_text_hashes(backend: StorageBackend) -> set[str]:
    """Reconstruct the set of text hashes already present in Silver.

    Silver records store their dedup hash under ``_text_hash`` so this can be
    rebuilt from ``read_all`` alone — no separate in-memory-only state that
    would be lost on restart and make dedup depend on process lifetime.
    """
    return {record["_text_hash"] for record in backend.read_all("silver") if "_text_hash" in record}


def process_bronze_record_to_silver(
    bronze_record: dict[str, Any],
    backend: StorageBackend,
    seen_hashes: set[str],
) -> bool:
    """Process one Bronze record into Silver: dedup, detect language, write.

    Returns True if a new Silver record was written, False if it was skipped
    as a cross-source/cross-run duplicate. ``seen_hashes`` is mutated in place
    so callers processing a batch of records share dedup state within that
    batch without re-reading Silver after every single record.
    """
    mention_id = bronze_record["mention_id"]

    if backend.exists("silver", mention_id):
        return False

    normalized_text = normalize_emoji(bronze_record["text"])
    hash_ = text_hash(normalized_text)
    if hash_ in seen_hashes:
        return False

    silver_record = dict(bronze_record)
    silver_record["text"] = normalized_text
    silver_record["language"] = detect_language(normalized_text)
    silver_record["_text_hash"] = hash_

    backend.write("silver", mention_id, silver_record)
    seen_hashes.add(hash_)
    return True


def process_bronze_batch_to_silver(
    bronze_records: list[dict[str, Any]], backend: StorageBackend
) -> int:
    """Process a batch of Bronze records into Silver incrementally.

    Used by the orchestrator after each connector page's Bronze write — not
    a full rebuild, just this batch. Returns the number of new Silver
    records written.
    """
    seen_hashes = _seen_text_hashes(backend)
    written = 0
    for record in bronze_records:
        if process_bronze_record_to_silver(record, backend, seen_hashes):
            written += 1
    return written


def rebuild_silver_from_bronze(backend: StorageBackend) -> int:
    """Wipe Silver and reprocess every Bronze record from scratch.

    This is the guarantee that Silver is never the source of truth — Bronze
    is, and Silver can always be regenerated identically from it. Returns
    the number of Silver records written.
    """
    backend.clear("silver")
    seen_hashes: set[str] = set()
    written = 0
    for bronze_record in backend.read_all("bronze"):
        if process_bronze_record_to_silver(bronze_record, backend, seen_hashes):
            written += 1
    return written
