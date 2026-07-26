"""Unit tests for the LLM client abstraction and call logger (Milestone 5)."""

import pytest

from brandpulse.pipeline.llm_client import (
    AzureOpenAILLMClient,
    GroqLLMClient,
    LLMCallLogger,
    MissingCredentialsError,
    UnsupportedLLMClientError,
    estimate_cost_usd,
    llm_client_from_config,
)


def test_call_logger_records_entries_with_all_fields():
    logger = LLMCallLogger()
    logger.record(
        mention_id="m1",
        stage="summary",
        model="azure_openai",
        prompt_version="v1",
        tokens_used=42,
        cost_estimate_usd=0.0001,
    )
    assert len(logger) == 1
    entry = logger.entries[0]
    assert entry.mention_id == "m1"
    assert entry.stage == "summary"
    assert entry.model == "azure_openai"
    assert entry.prompt_version == "v1"
    assert entry.tokens_used == 42
    assert entry.cost_estimate_usd == 0.0001
    assert entry.called_at is not None


def test_call_logger_starts_empty():
    logger = LLMCallLogger()
    assert len(logger) == 0
    assert logger.entries == []


def test_estimate_cost_usd_scales_with_tokens():
    low = estimate_cost_usd("azure_openai", 100)
    high = estimate_cost_usd("azure_openai", 1000)
    assert high > low


def test_azure_client_raises_when_env_vars_missing(monkeypatch):
    monkeypatch.delenv("AZURE_OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("AZURE_OPENAI_ENDPOINT", raising=False)
    monkeypatch.delenv("AZURE_OPENAI_DEPLOYMENT", raising=False)
    with pytest.raises(MissingCredentialsError, match="AZURE_OPENAI_API_KEY"):
        AzureOpenAILLMClient()


def test_groq_client_raises_when_env_var_missing(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    with pytest.raises(MissingCredentialsError, match="GROQ_API_KEY"):
        GroqLLMClient()


def test_llm_client_from_config_unsupported_raises_clear_error():
    with pytest.raises(UnsupportedLLMClientError, match="not_a_real_backend"):
        llm_client_from_config("not_a_real_backend")
