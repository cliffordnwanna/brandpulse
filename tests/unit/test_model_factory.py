"""Unit tests for the model adapter factory (Milestone 5)."""

import pytest

from brandpulse.pipeline.classify.complaint import KeywordComplaintClassifier
from brandpulse.pipeline.classify.model_factory import (
    UnsupportedModelError,
    complaint_model_from_config,
    sentiment_model_from_config,
)
from brandpulse.pipeline.classify.sentiment import LexiconSentimentModel


def test_lexicon_resolves_to_lexicon_sentiment_model():
    model = sentiment_model_from_config("lexicon")
    assert isinstance(model, LexiconSentimentModel)


def test_keyword_resolves_to_keyword_complaint_classifier():
    model = complaint_model_from_config("keyword")
    assert isinstance(model, KeywordComplaintClassifier)


def test_unsupported_sentiment_model_raises_clear_error():
    with pytest.raises(UnsupportedModelError, match="not_a_real_model"):
        sentiment_model_from_config("not_a_real_model")


def test_unsupported_complaint_model_raises_clear_error():
    with pytest.raises(UnsupportedModelError, match="not_a_real_model"):
        complaint_model_from_config("not_a_real_model")


def test_huggingface_sentiment_model_constructs_without_network(monkeypatch):
    """transformers/torch are project dependencies (Milestone 7), so
    'huggingface' must resolve to the right class — verified without an
    actual model download/load, which needs network access and can be slow
    or unavailable in constrained environments (not something a unit test
    should depend on)."""
    monkeypatch.setattr(
        "brandpulse.pipeline.classify.model_factory.HuggingFaceSentimentModel",
        lambda: "fake_hf_model_instance",
    )
    model = sentiment_model_from_config("huggingface")
    assert model == "fake_hf_model_instance"
