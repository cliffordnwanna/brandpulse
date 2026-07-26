"""Unit tests for Silver-level text-hash dedup (Engineering Design §11, Milestone 4)."""

from brandpulse.pipeline.dedupe import text_hash


def test_same_text_produces_same_hash():
    assert text_hash("Great app!") == text_hash("Great   app!  ")


def test_same_text_different_case_produces_same_hash():
    assert text_hash("Great App!") == text_hash("great app!")


def test_different_text_produces_different_hash():
    assert text_hash("Great app!") != text_hash("Terrible app!")
