"""LLM-backed low-confidence sentiment re-check (Engineering Design §10, §16).

Re-checking a low-confidence NaijaBERT/lexicon sentiment prediction is one of
the three cases the LLM-conditional rule allows the LLM to run for — this
stage re-asks using ``prompts/sentiment_fallback_v1.txt``, passing the
primary classifier's own guess as context. Only called from Tier 5b, only
when 5a's sentiment confidence was below threshold — never run unconditionally.
"""

from __future__ import annotations

from brandpulse.pipeline.classify.llm_stage import parse_label_confidence_reason
from brandpulse.pipeline.classify.prompts import render_prompt
from brandpulse.pipeline.classify.result import StageResult
from brandpulse.pipeline.classify.sentiment import SENTIMENT_LABELS
from brandpulse.pipeline.llm_client import LLMCallLogger, LLMClient, estimate_cost_usd

PROMPT_VERSION = "v1"


def recheck_low_confidence_sentiment(
    mention_id: str,
    text: str,
    language: str | None,
    primary_result: StageResult,
    llm_client: LLMClient,
    call_logger: LLMCallLogger,
) -> StageResult:
    prompt = render_prompt(
        "sentiment_fallback",
        PROMPT_VERSION,
        text=text,
        language=language or "und",
        primary_label=primary_result.label,
        primary_confidence=primary_result.confidence,
    )
    completion, tokens_used = llm_client.complete(prompt)

    call_logger.record(
        mention_id=mention_id,
        stage="sentiment_fallback",
        model=llm_client.model_name,
        prompt_version=PROMPT_VERSION,
        tokens_used=tokens_used,
        cost_estimate_usd=estimate_cost_usd(llm_client.model_name, tokens_used),
    )

    return parse_label_confidence_reason(completion, SENTIMENT_LABELS)
