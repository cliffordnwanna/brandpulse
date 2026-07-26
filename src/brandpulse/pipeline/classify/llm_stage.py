"""Shared plumbing for LLM-backed 5b enrichment stages (Engineering Design §10, §16).

Each stage (emotion, intent, urgency, competitor_mention) renders its own
versioned prompt, calls the configured ``LLMClient``, parses the fixed
``Label:``/``Confidence:``/``Reason:`` response format, and logs the call via
``LLMCallLogger`` — this is the single place that shape is implemented so
every stage's parsing/logging behaves identically.
"""

from __future__ import annotations

import re

from brandpulse.pipeline.classify.prompts import render_prompt
from brandpulse.pipeline.classify.result import StageResult
from brandpulse.pipeline.llm_client import LLMCallLogger, LLMClient, estimate_cost_usd

_LABEL_RE = re.compile(r"Label:\s*(.+)", re.IGNORECASE)
_CONFIDENCE_RE = re.compile(r"Confidence:\s*([0-9.]+)", re.IGNORECASE)
_REASON_RE = re.compile(r"Reason:\s*(.+)", re.IGNORECASE)


def parse_label_confidence_reason(completion: str, valid_labels: tuple[str, ...]) -> StageResult:
    """Parse the fixed ``Label:``/``Confidence:``/``Reason:`` prompt response format.

    Falls back to the first ``valid_labels`` entry with low confidence if the
    completion doesn't parse cleanly or names a label outside the allowed set
    — an LLM response is untrusted input, never assumed well-formed.
    """
    label_match = _LABEL_RE.search(completion)
    confidence_match = _CONFIDENCE_RE.search(completion)
    reason_match = _REASON_RE.search(completion)

    label = label_match.group(1).strip() if label_match else None
    if label not in valid_labels:
        return StageResult(
            label=valid_labels[-1],
            confidence=0.3,
            reason="LLM response did not name a recognized label; defaulted.",
        )

    confidence = float(confidence_match.group(1)) if confidence_match else 0.5
    confidence = max(0.0, min(confidence, 1.0))
    reason = reason_match.group(1).strip() if reason_match else "No reason provided."

    return StageResult(label=label, confidence=confidence, reason=reason)


def run_llm_stage(
    *,
    mention_id: str,
    stage: str,
    prompt_name: str,
    prompt_version: str,
    text: str,
    language: str | None,
    valid_labels: tuple[str, ...],
    llm_client: LLMClient,
    call_logger: LLMCallLogger,
) -> StageResult:
    """Render the stage's prompt, call the LLM, parse the result, and log the call."""
    prompt = render_prompt(prompt_name, prompt_version, text=text, language=language or "und")
    completion, tokens_used = llm_client.complete(prompt)

    call_logger.record(
        mention_id=mention_id,
        stage=stage,
        model=llm_client.model_name,
        prompt_version=prompt_version,
        tokens_used=tokens_used,
        cost_estimate_usd=estimate_cost_usd(llm_client.model_name, tokens_used),
    )

    return parse_label_confidence_reason(completion, valid_labels)
