"""Competitor mention classification — Tier 5b enrichment, LLM-backed (Engineering Design §10)."""

from __future__ import annotations

from brandpulse.pipeline.classify.llm_stage import run_llm_stage
from brandpulse.pipeline.classify.result import StageResult
from brandpulse.pipeline.llm_client import LLMCallLogger, LLMClient

COMPETITOR_LABELS = ("GTBank", "Access", "UBA", "FirstBank", "Opay", "Moniepoint", "None")
PROMPT_VERSION = "v1"


def classify_competitor_mention(
    mention_id: str,
    text: str,
    language: str | None,
    llm_client: LLMClient,
    call_logger: LLMCallLogger,
) -> StageResult:
    return run_llm_stage(
        mention_id=mention_id,
        stage="competitor_mention",
        prompt_name="enrichment_competitor",
        prompt_version=PROMPT_VERSION,
        text=text,
        language=language,
        valid_labels=COMPETITOR_LABELS,
        llm_client=llm_client,
        call_logger=call_logger,
    )
