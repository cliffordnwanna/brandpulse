"""Emoji normalization (Milestone 6, Silver pipeline text cleaning step).

Nigerian social media text carries real sentiment signal in emojis — never
strip them, normalize them to their text form instead (``😡`` →
``:enraged_face:``) so every downstream stage (phrase mining, word cloud,
sentiment) sees them as ordinary tokens rather than losing the signal
entirely. Applied in Silver, before anything else in this milestone, per the
spec's explicit ordering.
"""

from __future__ import annotations

import re

import emoji

_EMOJI_TOKEN_RE = re.compile(r":[a-z0-9_&'-]+:")


def normalize_emoji(text: str) -> str:
    """Replace emoji characters in ``text`` with their ``:name:`` token form."""
    return emoji.demojize(text)


def extract_emoji_tokens(text: str) -> list[str]:
    """Return every ``:name:`` emoji token present in already-normalized text."""
    return _EMOJI_TOKEN_RE.findall(text)
