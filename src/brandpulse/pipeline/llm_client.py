"""LLM client abstraction for Tier 5b enrichment (Engineering Design §10, Milestone 5).

Every call is logged with mention_id/stage/model/tokens/cost — the audit
trail that keeps LLM cost visible and proves the "LLM is conditional, never
default" invariant (CLAUDE.md #12), since ``enable_enrichment: false`` must
produce zero entries in this log.

Credentials are read from environment variables only, never from
``config.yaml`` or any committed file (Azure OpenAI: ``AZURE_OPENAI_API_KEY``,
``AZURE_OPENAI_ENDPOINT``, ``AZURE_OPENAI_DEPLOYMENT``; Groq: ``GROQ_API_KEY``).

Real network calls to Azure OpenAI/Groq aren't exercised by the test suite —
``FakeLLMClient`` (in ``tests/fixtures``) stands in for tests. The real
clients (``AzureOpenAILLMClient``, ``GroqLLMClient``) defer their SDK imports
to ``__init__`` so importing this module never requires those packages.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Protocol

from pydantic import BaseModel


class LLMCallLogEntry(BaseModel):
    """One audit-log entry for a single LLM call."""

    mention_id: str
    stage: str
    model: str
    prompt_version: str
    tokens_used: int
    cost_estimate_usd: float
    called_at: datetime


class MissingCredentialsError(Exception):
    """Raised when a required environment variable for an LLM client isn't set."""


class LLMClient(Protocol):
    """Interface every LLM backend (Azure OpenAI, Groq, fakes for tests) satisfies."""

    model_name: str

    def complete(self, prompt: str) -> tuple[str, int]:
        """Send ``prompt``, return ``(completion_text, tokens_used)``."""
        ...


class LLMCallLogger:
    """Accumulates ``LLMCallLogEntry`` records for every LLM call made during a run."""

    def __init__(self) -> None:
        self._entries: list[LLMCallLogEntry] = []

    def record(
        self,
        mention_id: str,
        stage: str,
        model: str,
        prompt_version: str,
        tokens_used: int,
        cost_estimate_usd: float,
    ) -> None:
        self._entries.append(
            LLMCallLogEntry(
                mention_id=mention_id,
                stage=stage,
                model=model,
                prompt_version=prompt_version,
                tokens_used=tokens_used,
                cost_estimate_usd=cost_estimate_usd,
                called_at=datetime.now(UTC),
            )
        )

    @property
    def entries(self) -> list[LLMCallLogEntry]:
        return list(self._entries)

    def __len__(self) -> int:
        return len(self._entries)


# Rough per-1K-token cost estimates for audit-log purposes only — not billing-accurate.
_COST_PER_1K_TOKENS_USD = {
    "azure_openai": 0.002,
    "groq": 0.0005,
}


def estimate_cost_usd(model_name: str, tokens_used: int) -> float:
    rate = _COST_PER_1K_TOKENS_USD.get(model_name, 0.0)
    return round((tokens_used / 1000) * rate, 6)


class AzureOpenAILLMClient:
    """Real Azure OpenAI-backed client. Requires the ``openai`` package."""

    model_name = "azure_openai"

    def __init__(self) -> None:
        api_key = os.environ.get("AZURE_OPENAI_API_KEY")
        endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT")
        deployment = os.environ.get("AZURE_OPENAI_DEPLOYMENT")
        missing = [
            name
            for name, value in (
                ("AZURE_OPENAI_API_KEY", api_key),
                ("AZURE_OPENAI_ENDPOINT", endpoint),
                ("AZURE_OPENAI_DEPLOYMENT", deployment),
            )
            if not value
        ]
        if missing:
            raise MissingCredentialsError(
                f"Missing required environment variable(s) for Azure OpenAI: {', '.join(missing)}."
            )

        from openai import AzureOpenAI  # noqa: PLC0415

        self._deployment = deployment
        self._client = AzureOpenAI(
            api_key=api_key, azure_endpoint=endpoint, api_version="2024-06-01"
        )

    def complete(self, prompt: str) -> tuple[str, int]:
        response = self._client.chat.completions.create(
            model=self._deployment,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.choices[0].message.content or ""
        tokens_used = response.usage.total_tokens if response.usage else 0
        return text, tokens_used


class GroqLLMClient:
    """Real Groq-backed client. Requires the ``groq`` package."""

    model_name = "groq"

    def __init__(self, model: str = "llama-3.1-8b-instant") -> None:
        api_key = os.environ.get("GROQ_API_KEY")
        if not api_key:
            raise MissingCredentialsError(
                "Missing required environment variable for Groq: GROQ_API_KEY."
            )

        from groq import Groq  # noqa: PLC0415

        self._model = model
        self._client = Groq(api_key=api_key)

    def complete(self, prompt: str) -> tuple[str, int]:
        response = self._client.chat.completions.create(
            model=self._model,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.choices[0].message.content or ""
        tokens_used = response.usage.total_tokens if response.usage else 0
        return text, tokens_used


class UnsupportedLLMClientError(Exception):
    """Raised when a configured ``enrichment_model`` name isn't implemented."""


def llm_client_from_config(name: str) -> LLMClient:
    if name == "azure_openai":
        return AzureOpenAILLMClient()
    if name == "groq":
        return GroqLLMClient()
    raise UnsupportedLLMClientError(
        f"Unsupported enrichment_model: {name!r}. Supported: 'azure_openai', 'groq'."
    )
