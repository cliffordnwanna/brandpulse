"""Unit tests for privacy: author hashing + PII scan gate (Milestone 6)."""

import logging

from brandpulse.pipeline.anonymize import anonymization_check, hash_author, scan_for_pii


def test_hash_author_produces_user_hash_format():
    result = hash_author("john_doe", salt="run-1")
    assert result.startswith("User#")
    assert len(result) == len("User#") + 5


def test_hash_author_is_deterministic_within_same_salt():
    a = hash_author("john_doe", salt="run-1")
    b = hash_author("john_doe", salt="run-1")
    assert a == b


def test_hash_author_differs_across_salts():
    a = hash_author("john_doe", salt="run-1")
    b = hash_author("john_doe", salt="run-2")
    assert a != b


def test_hash_author_none_passes_through():
    assert hash_author(None, salt="run-1") is None


def test_scan_for_pii_detects_email():
    findings = scan_for_pii("contact me at john@example.com")
    assert "email" in findings
    assert findings["email"] == ["john@example.com"]


def test_scan_for_pii_detects_nigerian_phone():
    findings = scan_for_pii("call me on 08031234567")
    assert "nigerian_phone" in findings


def test_scan_for_pii_detects_bvn_like_number():
    findings = scan_for_pii("my bvn is 12345678901")
    assert "bvn_like" in findings


def test_scan_for_pii_clean_text_returns_empty():
    assert scan_for_pii("Great app, no wahala!") == {}


def test_anonymization_check_returns_true_for_clean_records():
    records = [{"mention_id": "m1", "text": "Great app!"}]
    assert anonymization_check(records) is True


def test_anonymization_check_returns_false_and_logs_warning_for_pii(caplog):
    records = [{"mention_id": "m1", "text": "email me at john@example.com"}]
    with caplog.at_level(logging.WARNING, logger="brandpulse.anonymize"):
        result = anonymization_check(records)

    assert result is False
    assert any("PII" in record.message for record in caplog.records)


def test_anonymization_check_never_mutates_records():
    records = [{"mention_id": "m1", "text": "email me at john@example.com"}]
    original = dict(records[0])
    anonymization_check(records)
    assert records[0] == original
