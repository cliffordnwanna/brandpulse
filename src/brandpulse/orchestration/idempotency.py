"""Content-hash mention_id generation (Engineering Design §5).

``mention_id = SHA256(platform + url + timestamp + normalized_text)``

Re-running a connector (deliberately or after a crash) produces the same
``mention_id`` for the same underlying content, so Bronze/Silver/Gold writes
are naturally idempotent.
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime


def normalize_text(text: str) -> str:
    """Collapse whitespace and lowercase for hashing purposes only.

    This is separate from the Bronze normalization contract's text cleaning
    (Engineering Design §3) — it only affects what goes into the hash input,
    never the ``Mention.text`` field itself.
    """
    return re.sub(r"\s+", " ", text).strip().lower()


def compute_mention_id(platform: str, url: str | None, timestamp: datetime, text: str) -> str:
    """Compute the SHA256 content-hash mention_id (Engineering Design §5)."""
    normalized = normalize_text(text)
    payload = f"{platform}|{url or ''}|{timestamp.isoformat()}|{normalized}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
