"""Unit tests for the staged classification pipeline (Milestone 5, Engineering Design §10).

Covers the core acceptance criteria: 5a always runs with label/confidence/reason,
enable_enrichment=false produces zero LLM calls, enable_enrichment=true only
triggers 5b for low-confidence/Unknown/Mixed mentions (not every mention),
and Gold records are versioned/never overwritten.
"""

from pathlib import Path

from brandpulse.config.models import ClassificationConfig
from brandpulse.pipeline.classify.complaint import KeywordComplaintClassifier
from brandpulse.pipeline.classify.result import StageResult
from brandpulse.pipeline.classify.sentiment import LexiconSentimentModel
from brandpulse.pipeline.classify_pipeline import (
    CLASSIFIER_VERSION_5A,
    classify_5a,
    classify_silver_record,
    needs_enrichment,
)
from brandpulse.pipeline.llm_client import LLMCallLogger
from brandpulse.storage.local import LocalFileStorageBackend
from tests.fixtures.fake_llm_client import FakeLLMClient


def _sentiment_model():
    return LexiconSentimentModel()


def _complaint_classifier():
    return KeywordComplaintClassifier()


def test_classify_5a_produces_label_confidence_reason_for_every_field():
    record = classify_5a(
        "Great app, easy transfers!", "en", _sentiment_model(), _complaint_classifier()
    )
    assert record["classifier_version"] == CLASSIFIER_VERSION_5A
    for field in ("sentiment", "complaint_category"):
        assert record[field]["label"]
        assert isinstance(record[field]["confidence"], float)
        assert record[field]["reason"]


def test_needs_enrichment_true_for_low_confidence():
    config = ClassificationConfig(confidence_threshold=0.99)
    sentiment = StageResult(label="Positive", confidence=0.6, reason="r")
    complaint = StageResult(label="Transfers", confidence=0.6, reason="r")
    assert needs_enrichment(sentiment, complaint, config) is True


def test_needs_enrichment_true_for_unknown_category():
    config = ClassificationConfig(confidence_threshold=0.5)
    sentiment = StageResult(label="Positive", confidence=0.9, reason="r")
    complaint = StageResult(label="Unknown", confidence=0.9, reason="r")
    assert needs_enrichment(sentiment, complaint, config) is True


def test_needs_enrichment_true_for_mixed_sentiment():
    config = ClassificationConfig(confidence_threshold=0.5)
    sentiment = StageResult(label="Mixed", confidence=0.9, reason="r")
    complaint = StageResult(label="Transfers", confidence=0.9, reason="r")
    assert needs_enrichment(sentiment, complaint, config) is True


def test_needs_enrichment_false_for_high_confidence_known_category():
    config = ClassificationConfig(confidence_threshold=0.5)
    sentiment = StageResult(label="Positive", confidence=0.9, reason="r")
    complaint = StageResult(label="Transfers", confidence=0.9, reason="r")
    assert needs_enrichment(sentiment, complaint, config) is False


def test_enrichment_disabled_produces_zero_llm_calls(tmp_path: Path):
    backend = LocalFileStorageBackend(tmp_path / "storage")
    config = ClassificationConfig(enable_enrichment=False)
    call_logger = LLMCallLogger()
    silver_record = {
        "mention_id": "m1",
        "text": "asdkjh random unclassifiable text",
        "language": "en",
    }

    classify_silver_record(
        silver_record,
        sentiment_model=_sentiment_model(),
        complaint_classifier=_complaint_classifier(),
        config=config,
        llm_client=None,
        call_logger=call_logger,
        backend=backend,
    )

    assert len(call_logger) == 0


def test_enrichment_enabled_only_triggers_for_flagged_mentions(tmp_path: Path):
    backend = LocalFileStorageBackend(tmp_path / "storage")
    config = ClassificationConfig(enable_enrichment=True, confidence_threshold=0.5)
    call_logger = LLMCallLogger()
    fake_client = FakeLLMClient(
        [
            ("Label: Fraud\nConfidence: 0.8\nReason: r", 10),  # complaint overflow reclassify
            ("Label: Frustration\nConfidence: 0.8\nReason: r", 10),
            ("Label: Complaint\nConfidence: 0.8\nReason: r", 10),
            ("Label: Low\nConfidence: 0.8\nReason: r", 10),
            ("Label: None\nConfidence: 0.8\nReason: r", 10),
            ("summary text", 10),
        ]
    )

    # High-confidence, clearly-categorized mention: should NOT trigger 5b.
    clean_record = {
        "mention_id": "m-clean",
        "text": "Great app, easy transfers, very fast and reliable!",
        "language": "en",
    }
    classify_silver_record(
        clean_record,
        sentiment_model=_sentiment_model(),
        complaint_classifier=_complaint_classifier(),
        config=config,
        llm_client=fake_client,
        call_logger=call_logger,
        backend=backend,
    )
    assert len(call_logger) == 0

    # Unclassifiable / Unknown-category mention: should trigger 5b.
    flagged_record = {
        "mention_id": "m-flagged",
        "text": "asdkjhaskdjh totally unclassifiable gibberish",
        "language": "en",
    }
    classify_silver_record(
        flagged_record,
        sentiment_model=_sentiment_model(),
        complaint_classifier=_complaint_classifier(),
        config=config,
        llm_client=fake_client,
        call_logger=call_logger,
        backend=backend,
    )
    # complaint overflow reclassify, emotion, intent, urgency, competitor, summary
    assert len(call_logger) == 6


def test_gold_record_written_and_versioned(tmp_path: Path):
    backend = LocalFileStorageBackend(tmp_path / "storage")
    config = ClassificationConfig(enable_enrichment=False)
    silver_record = {"mention_id": "m1", "text": "Great app!", "language": "en"}

    classify_silver_record(
        silver_record,
        sentiment_model=_sentiment_model(),
        complaint_classifier=_complaint_classifier(),
        config=config,
        llm_client=None,
        call_logger=LLMCallLogger(),
        backend=backend,
    )

    gold_records = list(backend.read_all("gold"))
    assert len(gold_records) == 1
    assert gold_records[0]["mention_id"] == "m1"
    assert gold_records[0]["classifier_version"] == CLASSIFIER_VERSION_5A


def test_rerunning_same_classifier_version_does_not_duplicate_gold(tmp_path: Path):
    backend = LocalFileStorageBackend(tmp_path / "storage")
    config = ClassificationConfig(enable_enrichment=False)
    silver_record = {"mention_id": "m1", "text": "Great app!", "language": "en"}

    for _ in range(2):
        classify_silver_record(
            silver_record,
            sentiment_model=_sentiment_model(),
            complaint_classifier=_complaint_classifier(),
            config=config,
            llm_client=None,
            call_logger=LLMCallLogger(),
            backend=backend,
        )

    assert len(list(backend.read_all("gold"))) == 1
