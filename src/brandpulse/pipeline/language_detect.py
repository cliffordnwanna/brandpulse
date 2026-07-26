"""Language detection (Engineering Design §9, §10; Milestone 4).

``lingua-py`` handles English, Yoruba, and 73 other languages well, but has
**no model at all** for Nigerian Pidgin, Hausa, or Igbo — they simply aren't
in its language set. Since these three matter for this project specifically,
a lightweight marker-word heuristic runs first and catches obvious cases;
anything it doesn't recognize falls through to lingua, and anything neither
layer is confident about maps to ``"und"`` (undetermined) rather than a
guess. This is a known, documented approximation, not a precise classifier —
see the milestone note: what matters is that ``language`` is always
populated, detection is consistent/reproducible, and it's usable as a
signal downstream, not that it's linguistically perfect.
"""

from __future__ import annotations

import re

from lingua import Language, LanguageDetectorBuilder

# ISO 639 codes used throughout Silver/Gold.
ENGLISH = "en"
YORUBA = "yo"
HAUSA = "ha"
IGBO = "ig"
NIGERIAN_PIDGIN = "pcm"
UNDETERMINED = "und"

_LINGUA_TO_CODE = {
    Language.ENGLISH: ENGLISH,
    Language.YORUBA: YORUBA,
}

_LINGUA_LANGUAGES = list(_LINGUA_TO_CODE.keys())

# Small, high-precision marker-word sets — deliberately conservative (common
# function words / distinctive terms unlikely to appear in English text) so
# a false-positive match is rare, even though this means recall is limited.
_PIDGIN_MARKERS = {
    "dey",
    "abeg",
    "wetin",
    "sha",
    "wahala",
    "na so",
    "no wahala",
    "gist",
    "sabi",
    "waka",
    "jare",
    "abi",
    "una",
    "wan",
}

_HAUSA_MARKERS = {
    "ina",
    "kana",
    "yaya",
    "nagode",
    "sannu",
    "lafiya",
    "kudi",
    "banki",
    "yau",
    "gobe",
}

_IGBO_MARKERS = {
    "kedu",
    "biko",
    "daalu",
    "unu",
    "nna",
    "nne",
    "ego",
    "ulo",
    "ndewo",
    "ego m",
}

_detector = LanguageDetectorBuilder.from_languages(*_LINGUA_LANGUAGES).build()


def _marker_match(tokens: set[str], token_sequence: list[str], markers: set[str]) -> bool:
    """True if any single-word marker is a token, or any multi-word marker
    appears as a consecutive run of tokens (word-boundary-aware — a naive
    substring check on raw text can false-positive across word boundaries,
    e.g. "...ya, ina son..." contains the raw substring "na so")."""
    if tokens & markers:
        return True

    phrase_markers = [marker.split() for marker in markers if " " in marker]
    for phrase in phrase_markers:
        phrase_len = len(phrase)
        for i in range(len(token_sequence) - phrase_len + 1):
            if token_sequence[i : i + phrase_len] == phrase:
                return True
    return False


def detect_language(text: str) -> str:
    """Detect the language of ``text``, returning an ISO 639 code or ``"und"``.

    Order of precedence: marker-word heuristics (Pidgin, Hausa, Igbo) first,
    since lingua has no model for these at all; then lingua (English,
    Yoruba, everything else it supports); then ``"und"`` if neither layer
    is confident.
    """
    if not text or not text.strip():
        return UNDETERMINED

    text_lower = text.lower()
    token_sequence = re.findall(r"[\w']+", text_lower)
    tokens = set(token_sequence)

    if _marker_match(tokens, token_sequence, _PIDGIN_MARKERS):
        return NIGERIAN_PIDGIN
    if _marker_match(tokens, token_sequence, _HAUSA_MARKERS):
        return HAUSA
    if _marker_match(tokens, token_sequence, _IGBO_MARKERS):
        return IGBO

    detected = _detector.detect_language_of(text)
    if detected is None:
        return UNDETERMINED

    return _LINGUA_TO_CODE.get(detected, UNDETERMINED)
