"""Unit tests for the individual Tier 5b enrichment stage modules (Milestone 5)."""

from brandpulse.pipeline.classify.competitor import COMPETITOR_LABELS, classify_competitor_mention
from brandpulse.pipeline.classify.emotion import EMOTION_LABELS, classify_emotion
from brandpulse.pipeline.classify.intent import INTENT_LABELS, classify_intent
from brandpulse.pipeline.classify.severity import URGENCY_LABELS, classify_urgency
from brandpulse.pipeline.classify.summary import generate_summary
from brandpulse.pipeline.llm_client import LLMCallLogger
from tests.fixtures.fake_llm_client import FakeLLMClient


def test_classify_emotion_returns_valid_label():
    fake = FakeLLMClient([("Label: Frustration\nConfidence: 0.85\nReason: annoyed.", 10)])
    result = classify_emotion("m1", "text", "en", fake, LLMCallLogger())
    assert result.label in EMOTION_LABELS
    assert result.label == "Frustration"


def test_classify_intent_returns_valid_label():
    fake = FakeLLMClient([("Label: Complaint\nConfidence: 0.9\nReason: complaining.", 10)])
    result = classify_intent("m1", "text", "en", fake, LLMCallLogger())
    assert result.label in INTENT_LABELS
    assert result.label == "Complaint"


def test_classify_urgency_returns_valid_label():
    fake = FakeLLMClient([("Label: Critical\nConfidence: 0.95\nReason: possible fraud.", 10)])
    result = classify_urgency("m1", "text", "en", fake, LLMCallLogger())
    assert result.label in URGENCY_LABELS
    assert result.label == "Critical"


def test_classify_competitor_mention_returns_valid_label():
    fake = FakeLLMClient([("Label: Opay\nConfidence: 0.9\nReason: mentions Opay.", 10)])
    result = classify_competitor_mention("m1", "text", "en", fake, LLMCallLogger())
    assert result.label in COMPETITOR_LABELS
    assert result.label == "Opay"


def test_generate_summary_returns_stripped_text():
    fake = FakeLLMClient([("  A short factual summary.  ", 8)])
    summary = generate_summary("m1", "text", "en", fake, LLMCallLogger())
    assert summary == "A short factual summary."


def test_each_5b_stage_logs_exactly_one_llm_call():
    call_logger = LLMCallLogger()
    fake = FakeLLMClient(
        [
            ("Label: Frustration\nConfidence: 0.8\nReason: r", 10),
            ("Label: Complaint\nConfidence: 0.8\nReason: r", 10),
            ("Label: High\nConfidence: 0.8\nReason: r", 10),
            ("Label: None\nConfidence: 0.8\nReason: r", 10),
            ("Summary text.", 10),
        ]
    )
    classify_emotion("m1", "t", "en", fake, call_logger)
    classify_intent("m1", "t", "en", fake, call_logger)
    classify_urgency("m1", "t", "en", fake, call_logger)
    classify_competitor_mention("m1", "t", "en", fake, call_logger)
    generate_summary("m1", "t", "en", fake, call_logger)

    assert len(call_logger) == 5
    stages_logged = {entry.stage for entry in call_logger.entries}
    assert stages_logged == {"emotion", "intent", "urgency", "competitor_mention", "summary"}
