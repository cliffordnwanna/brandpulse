"""Insight recommendation generation (Milestone 6).

Populates ``Insight.recommendation`` for high/critical-severity insights,
one LLM call per insight, using ``prompts/recommendation_v1.txt``. Gated by
``config.classification.recommendations`` (default off) — when off, this
module is never called and ``recommendation`` stays ``None`` throughout,
same "LLM is conditional, never default" pattern as Tier 5b (CLAUDE.md #12).
"""

from __future__ import annotations

from brandpulse.pipeline.classify.prompts import render_prompt
from brandpulse.pipeline.insight_engine import Insight
from brandpulse.pipeline.llm_client import LLMCallLogger, LLMClient, estimate_cost_usd

PROMPT_VERSION = "v1"
_RECOMMENDABLE_SEVERITIES = ("critical", "high")


def generate_recommendation(
    insight: Insight, llm_client: LLMClient, call_logger: LLMCallLogger
) -> str:
    prompt = render_prompt(
        "recommendation",
        PROMPT_VERSION,
        title=insight.title,
        description=insight.description,
        severity=insight.severity,
    )
    completion, tokens_used = llm_client.complete(prompt)

    call_logger.record(
        mention_id=insight.id,
        stage="recommendation",
        model=llm_client.model_name,
        prompt_version=PROMPT_VERSION,
        tokens_used=tokens_used,
        cost_estimate_usd=estimate_cost_usd(llm_client.model_name, tokens_used),
    )
    return completion.strip()


def add_recommendations(
    insights: list[Insight], llm_client: LLMClient, call_logger: LLMCallLogger
) -> list[Insight]:
    """Populate ``recommendation`` on every high/critical insight in place.

    Only called when ``config.classification.recommendations`` is true — the
    caller is responsible for that gate, same as Tier 5b's ``llm_client``
    being ``None`` when enrichment is disabled.
    """
    for insight in insights:
        if insight.severity in _RECOMMENDABLE_SEVERITIES:
            insight.recommendation = generate_recommendation(insight, llm_client, call_logger)
    return insights
