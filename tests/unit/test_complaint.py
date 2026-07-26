"""Unit tests for the default (keyword) complaint classifier (Milestone 5)."""

from brandpulse.pipeline.classify.complaint import (
    COMPLAINT_TAXONOMY,
    UNKNOWN_CATEGORY,
    KeywordComplaintClassifier,
)


def test_transfer_keyword_classified_as_transfers():
    result = KeywordComplaintClassifier().classify("My transfer to a beneficiary failed.", "en")
    assert result.label == "Transfers"
    assert result.label in COMPLAINT_TAXONOMY


def test_fraud_keyword_classified_as_fraud():
    result = KeywordComplaintClassifier().classify(
        "This looks like fraud, unauthorized access.", "en"
    )
    assert result.label == "Fraud"


def test_no_match_falls_through_to_unknown():
    result = KeywordComplaintClassifier().classify("asdkfjhasdkjfh random gibberish", "en")
    assert result.label == UNKNOWN_CATEGORY


def test_generic_words_only_fall_back_to_general_feedback():
    result = KeywordComplaintClassifier().classify("The bank app service was fine.", "en")
    assert result.label == "General Feedback"


def test_multiword_phrase_matches():
    result = KeywordComplaintClassifier().classify(
        "I want to open an account, what is needed?", "en"
    )
    assert result.label == "Account Opening"


def test_result_always_has_label_confidence_reason():
    result = KeywordComplaintClassifier().classify("branch teller was slow", "en")
    assert result.label
    assert isinstance(result.confidence, float)
    assert result.reason
