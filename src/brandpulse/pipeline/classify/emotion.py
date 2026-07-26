"""Emotion classification — Tier 5b enrichment, LLM-backed (Engineering Design §10)."""

from __future__ import annotations

from brandpulse.pipeline.classify.llm_stage import run_llm_stage
from brandpulse.pipeline.classify.result import StageResult
from brandpulse.pipeline.llm_client import LLMCallLogger, LLMClient

EMOTION_LABELS = ("Anger", "Frustration", "Appreciation", "Confusion", "Trust", "Neutral")
PROMPT_VERSION = "v1"


def classify_emotion(
    mention_id: str,
    text: str,
    language: str | None,
    llm_client: LLMClient,
    call_logger: LLMCallLogger,
) -> StageResult:
    return run_llm_stage(
        mention_id=mention_id,
        stage="emotion",
        prompt_name="enrichment_emotion",
        prompt_version=PROMPT_VERSION,
        text=text,
        language=language,
        valid_labels=EMOTION_LABELS,
        llm_client=llm_client,
        call_logger=call_logger,
    )
