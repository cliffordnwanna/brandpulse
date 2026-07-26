"""LLM-backed complaint category overflow classification (Engineering Design §10, §16).

``KeywordComplaintClassifier`` (5a) returns ``Unknown`` for text that matches
no taxonomy keyword. Per the LLM-conditional rule, unknown-topic overflow is
one of the three cases the LLM is allowed to handle — this stage re-asks the
LLM to place the text into the taxonomy (or confirm ``Unknown``), using
``prompts/complaint_classification_v1.txt``. Only called from Tier 5b, only
when 5a's category was ``Unknown`` — never run unconditionally.
"""

from __future__ import annotations

from brandpulse.pipeline.classify.complaint import COMPLAINT_TAXONOMY, UNKNOWN_CATEGORY
from brandpulse.pipeline.classify.llm_stage import run_llm_stage
from brandpulse.pipeline.classify.result import StageResult
from brandpulse.pipeline.llm_client import LLMCallLogger, LLMClient

_VALID_LABELS = (*COMPLAINT_TAXONOMY, UNKNOWN_CATEGORY)
PROMPT_VERSION = "v1"


def reclassify_unknown_complaint(
    mention_id: str,
    text: str,
    language: str | None,
    llm_client: LLMClient,
    call_logger: LLMCallLogger,
) -> StageResult:
    return run_llm_stage(
        mention_id=mention_id,
        stage="complaint_category_overflow",
        prompt_name="complaint_classification",
        prompt_version=PROMPT_VERSION,
        text=text,
        language=language,
        valid_labels=_VALID_LABELS,
        llm_client=llm_client,
        call_logger=call_logger,
    )
