"""Privacy: author-handle hashing and a PII scan gate before every output write (Milestone 6).

Two distinct mechanisms:

1. ``hash_author`` — deterministically replaces a public handle/reviewer name
   with ``User#XXXXX`` (SHA256, first 5 hex chars), consistent within a run
   (a ``salt`` — typically the run_id — makes the mapping vary run-to-run
   rather than being a stable fingerprint across reports).
2. ``scan_for_pii`` — a regex gate run before every output file is written:
   catches email addresses, Nigerian phone numbers, and 11-digit BVN-shaped
   numbers. Findings are logged as warnings, never silently dropped — per
   the spec, this is a detection gate, not a redaction step; a match means
   something upstream (a connector, a summary) leaked PII into content that
   was supposed to be public-handle-level only, and that needs a human to
   look at it, not a silent scrub that hides the leak.
"""

from __future__ import annotations

import hashlib
import logging
import re

logger = logging.getLogger("brandpulse.anonymize")

_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
_NIGERIAN_PHONE_RE = re.compile(r"(?:\+234|0)[789][01]\d{8}\b")
_BVN_RE = re.compile(r"\b\d{11}\b")

_PII_PATTERNS = {
    "email": _EMAIL_RE,
    "nigerian_phone": _NIGERIAN_PHONE_RE,
    "bvn_like": _BVN_RE,
}


def hash_author(author: str | None, salt: str) -> str | None:
    """Replace ``author`` with a deterministic ``User#XXXXX`` pseudonym.

    ``None`` passes through unchanged — a missing author isn't a PII leak to
    hide, it's just absent data. Hashing is salted with ``salt`` (the run_id)
    so the same underlying author maps to a different pseudonym in a
    different run's report, rather than being a stable cross-report
    fingerprint.
    """
    if author is None:
        return None
    digest = hashlib.sha256(f"{salt}:{author}".encode()).hexdigest()
    return f"User#{digest[:5]}"


def scan_for_pii(text: str) -> dict[str, list[str]]:
    """Return ``{pii_type: [matches]}`` for every PII pattern found in ``text``.

    Empty dict means clean. Never mutates or redacts ``text`` — this is a
    detection gate, the caller decides what to do with a positive finding.
    """
    findings: dict[str, list[str]] = {}
    for pii_type, pattern in _PII_PATTERNS.items():
        matches = pattern.findall(text)
        if matches:
            findings[pii_type] = matches
    return findings


def anonymization_check(
    records: list[dict], text_fields: tuple[str, ...] = ("text", "summary")
) -> bool:
    """Scan ``records`` for PII across ``text_fields`` before an output write.

    Logs a warning per finding (never raises, never drops data — per spec,
    "log a warning if found, never silently drop"). Returns ``True`` if the
    records are clean, ``False`` if anything was flagged, so callers can
    track the outcome without parsing log output.
    """
    clean = True
    for record in records:
        mention_id = record.get("mention_id", "<unknown>")
        for field in text_fields:
            value = record.get(field)
            if not isinstance(value, str):
                continue
            findings = scan_for_pii(value)
            if findings:
                clean = False
                logger.warning(
                    "Possible PII detected in %s field of mention_id=%s: %s",
                    field,
                    mention_id,
                    {k: len(v) for k, v in findings.items()},
                )
    return clean
