"""Unit tests for the two LLM-conditional edge-case stages (Milestone 5, §10):
low-confidence sentiment re-check and Unknown-category complaint overflow.
"""

from brandpulse.pipeline.classify.complaint import COMPLAINT_TAXONOMY, UNKNOWN_CATEGORY
from brandpulse.pipeline.classify.complaint_overflow import reclassify_unknown_complaint
from brandpulse.pipeline.classify.result import StageResult
from brandpulse.pipeline.classify.sentiment_fallback import recheck_low_confidence_sentiment
from brandpulse.pipeline.llm_client import LLMCallLogger
from tests.fixtures.fake_llm_client import FakeLLMClient


def test_recheck_low_confidence_sentiment_returns_valid_label():
    fake = FakeLLMClient([("Label: Negative\nConfidence: 0.7\nReason: r", 10)])
    primary = StageResult(label="Neutral", confidence=0.4, reason="weak signal")
    result = recheck_low_confidence_sentiment("m1", "text", "en", primary, fake, LLMCallLogger())
    assert result.label == "Negative"


def test_recheck_includes_primary_guess_in_prompt():
    fake = FakeLLMClient([("Label: Negative\nConfidence: 0.7\nReason: r", 10)])
    primary = StageResult(label="Neutral", confidence=0.4, reason="weak signal")
    recheck_low_confidence_sentiment("m1", "some text", "en", primary, fake, LLMCallLogger())
    assert "Neutral" in fake.prompts_seen[0]
    assert "0.4" in fake.prompts_seen[0]


def test_recheck_logs_as_sentiment_fallback_stage():
    fake = FakeLLMClient([("Label: Negative\nConfidence: 0.7\nReason: r", 10)])
    primary = StageResult(label="Neutral", confidence=0.4, reason="weak signal")
    call_logger = LLMCallLogger()
    recheck_low_confidence_sentiment("m1", "text", "en", primary, fake, call_logger)
    assert call_logger.entries[0].stage == "sentiment_fallback"


def test_reclassify_unknown_complaint_returns_taxonomy_label():
    fake = FakeLLMClient([("Label: Fraud\nConfidence: 0.8\nReason: r", 10)])
    result = reclassify_unknown_complaint("m1", "text", "en", fake, LLMCallLogger())
    assert result.label in (*COMPLAINT_TAXONOMY, UNKNOWN_CATEGORY)
    assert result.label == "Fraud"


def test_reclassify_unknown_complaint_can_confirm_unknown():
    fake = FakeLLMClient([("Label: Unknown\nConfidence: 0.6\nReason: r", 10)])
    result = reclassify_unknown_complaint("m1", "text", "en", fake, LLMCallLogger())
    assert result.label == UNKNOWN_CATEGORY


def test_reclassify_logs_as_complaint_category_overflow_stage():
    fake = FakeLLMClient([("Label: Fraud\nConfidence: 0.8\nReason: r", 10)])
    call_logger = LLMCallLogger()
    reclassify_unknown_complaint("m1", "text", "en", fake, call_logger)
    assert call_logger.entries[0].stage == "complaint_category_overflow"
