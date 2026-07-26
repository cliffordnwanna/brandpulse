"""Unit tests for language detection (Milestone 4).

lingua-py has no model at all for Nigerian Pidgin, Hausa, or Igbo — a
marker-word heuristic layer catches these before falling back to lingua.
See brandpulse/pipeline/language_detect.py for the full rationale.
"""

from brandpulse.pipeline.language_detect import (
    ENGLISH,
    HAUSA,
    IGBO,
    NIGERIAN_PIDGIN,
    UNDETERMINED,
    YORUBA,
    detect_language,
)

PIDGIN_PHRASES = [
    "This app dey stress me, transfer no dey work.",
    "Abeg who dey experience this wahala with ALAT.",
    "Wetin dey happen na, my money don disappear.",
    "Una should fix this app jare, e dey slow well well.",
    "I don try transfer money since morning, na so e dey hang.",
]

ENGLISH_PHRASES = [
    "This app is great for easy transfers.",
    "Customer service was very responsive and helpful.",
    "I love the new update, everything works smoothly now.",
    "The interface is clean and intuitive to use.",
    "I had a small issue but support resolved it quickly.",
]


def test_five_pidgin_phrases_detected_as_pidgin():
    for phrase in PIDGIN_PHRASES:
        assert detect_language(phrase) == NIGERIAN_PIDGIN, phrase


def test_five_english_phrases_detected_as_english():
    for phrase in ENGLISH_PHRASES:
        assert detect_language(phrase) == ENGLISH, phrase


def test_pidgin_and_english_route_to_different_codes():
    pidgin_codes = {detect_language(p) for p in PIDGIN_PHRASES}
    english_codes = {detect_language(p) for p in ENGLISH_PHRASES}
    assert pidgin_codes.isdisjoint(english_codes)


def test_yoruba_marker_free_text_detected_via_lingua():
    # A longer, clearly Yoruba sentence gives lingua's model enough signal.
    text = "Mo dupe pupo fun iranlowo yin, eyi ti mo fe se ni pataki."
    assert detect_language(text) == YORUBA


def test_hausa_marker_phrase_detected():
    assert detect_language("Sannu, yaya lafiya, ina son duba kudi na a banki.") == HAUSA


def test_igbo_marker_phrase_detected():
    assert detect_language("Kedu, biko enyere m aka, ego m adighi na ulo akwukwo.") == IGBO


def test_empty_text_is_undetermined():
    assert detect_language("") == UNDETERMINED
    assert detect_language("   ") == UNDETERMINED


def test_detection_is_deterministic():
    text = "This app dey stress me, transfer no dey work."
    results = {detect_language(text) for _ in range(5)}
    assert len(results) == 1
