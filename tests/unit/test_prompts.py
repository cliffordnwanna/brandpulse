"""Unit tests for prompt loading (Milestone 5, Engineering Design §16)."""

from brandpulse.pipeline.classify.prompts import load_prompt, render_prompt


def test_load_prompt_reads_versioned_file():
    text = load_prompt("summary", "v1")
    assert "{text}" in text
    assert "{language}" in text


def test_render_prompt_fills_in_fields():
    rendered = render_prompt("summary", "v1", text="Hello world", language="en")
    assert "Hello world" in rendered
    assert "{text}" not in rendered
    assert "{language}" not in rendered


def test_every_stage_prompt_file_loads_and_renders():
    for name in (
        "complaint_classification",
        "enrichment_emotion",
        "enrichment_intent",
        "enrichment_urgency",
        "enrichment_competitor",
        "summary",
    ):
        rendered = render_prompt(name, "v1", text="sample text", language="en")
        assert "sample text" in rendered


def test_sentiment_fallback_prompt_renders_with_primary_classifier_fields():
    rendered = render_prompt(
        "sentiment_fallback",
        "v1",
        text="sample text",
        language="en",
        primary_label="Neutral",
        primary_confidence=0.4,
    )
    assert "sample text" in rendered
    assert "Neutral" in rendered
