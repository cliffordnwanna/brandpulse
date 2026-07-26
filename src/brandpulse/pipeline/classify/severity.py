"""Severity/urgency classification — Tier 5b enrichment, LLM-backed (Engineering Design §10).

``Critical`` means the comment suggests possible fraud, unauthorized access,
or risk of the customer losing funds/access to their account.
"""

from __future__ import annotations

from brandpulse.pipeline.classify.llm_stage import run_llm_stage
from brandpulse.pipeline.classify.result import StageResult
from brandpulse.pipeline.llm_client import LLMCallLogger, LLMClient

URGENCY_LABELS = ("Critical", "High", "Medium", "Low")
PROMPT_VERSION = "v1"


def classify_urgency(
    mention_id: str,
    text: str,
    language: str | None,
    llm_client: LLMClient,
    call_logger: LLMCallLogger,
) -> StageResult:
    return run_llm_stage(
        mention_id=mention_id,
        stage="urgency",
        prompt_name="enrichment_urgency",
        prompt_version=PROMPT_VERSION,
        text=text,
        language=language,
        valid_labels=URGENCY_LABELS,
        llm_client=llm_client,
        call_logger=call_logger,
    )
