"""Unit tests for the shared LLM-stage parsing/logging plumbing (Milestone 5)."""

from brandpulse.pipeline.classify.llm_stage import parse_label_confidence_reason, run_llm_stage
from brandpulse.pipeline.llm_client import LLMCallLogger
from tests.fixtures.fake_llm_client import FakeLLMClient

_LABELS = ("Anger", "Frustration", "Neutral")


def test_parse_well_formed_response():
    completion = "Label: Anger\nConfidence: 0.9\nReason: customer is upset."
    result = parse_label_confidence_reason(completion, _LABELS)
    assert result.label == "Anger"
    assert result.confidence == 0.9
    assert result.reason == "customer is upset."


def test_parse_unrecognized_label_falls_back_safely():
    completion = "Label: NotARealLabel\nConfidence: 0.9\nReason: whatever."
    result = parse_label_confidence_reason(completion, _LABELS)
    assert result.label == _LABELS[-1]
    assert result.confidence == 0.3


def test_parse_missing_confidence_defaults_to_midpoint():
    completion = "Label: Neutral\nReason: no strong signal."
    result = parse_label_confidence_reason(completion, _LABELS)
    assert result.label == "Neutral"
    assert result.confidence == 0.5


def test_parse_confidence_clamped_to_0_1():
    completion = "Label: Neutral\nConfidence: 5\nReason: test."
    result = parse_label_confidence_reason(completion, _LABELS)
    assert result.confidence == 1.0


def test_run_llm_stage_logs_the_call():
    call_logger = LLMCallLogger()
    fake_client = FakeLLMClient([("Label: Anger\nConfidence: 0.8\nReason: upset.", 15)])

    result = run_llm_stage(
        mention_id="m1",
        stage="emotion",
        prompt_name="enrichment_emotion",
        prompt_version="v1",
        text="I am furious about this delay.",
        language="en",
        valid_labels=_LABELS,
        llm_client=fake_client,
        call_logger=call_logger,
    )

    assert result.label == "Anger"
    assert len(call_logger) == 1
    entry = call_logger.entries[0]
    assert entry.mention_id == "m1"
    assert entry.stage == "emotion"
    assert entry.tokens_used == 15
    assert len(fake_client.prompts_seen) == 1
