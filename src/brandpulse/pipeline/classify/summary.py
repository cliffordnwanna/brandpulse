"""Summary generation — the only stage that always calls the LLM (Engineering Design §10).

Unlike the other 5b stages, the summary prompt returns free text (a 1-2
sentence gist), not a label/confidence/reason triple — there's no fixed
taxonomy for a summary to belong to.
"""

from __future__ import annotations

from brandpulse.pipeline.classify.prompts import render_prompt
from brandpulse.pipeline.llm_client import LLMCallLogger, LLMClient, estimate_cost_usd

PROMPT_VERSION = "v1"


def generate_summary(
    mention_id: str,
    text: str,
    language: str | None,
    llm_client: LLMClient,
    call_logger: LLMCallLogger,
) -> str:
    prompt = render_prompt("summary", PROMPT_VERSION, text=text, language=language or "und")
    completion, tokens_used = llm_client.complete(prompt)

    call_logger.record(
        mention_id=mention_id,
        stage="summary",
        model=llm_client.model_name,
        prompt_version=PROMPT_VERSION,
        tokens_used=tokens_used,
        cost_estimate_usd=estimate_cost_usd(llm_client.model_name, tokens_used),
    )

    return completion.strip()
