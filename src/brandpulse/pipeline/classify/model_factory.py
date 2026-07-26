"""Resolves ``config.classification.{sentiment_model,complaint_model}`` to concrete
model adapter instances (Milestone 5) — same pattern as ``StorageBackendFactory``
(Milestone 4): the only place that knows which concrete classes exist.
"""

from __future__ import annotations

from brandpulse.pipeline.classify.complaint import (
    ComplaintClassifier,
    HuggingFaceZeroShotComplaintClassifier,
    KeywordComplaintClassifier,
)
from brandpulse.pipeline.classify.sentiment import (
    HuggingFaceSentimentModel,
    LexiconSentimentModel,
    SentimentModel,
)


class UnsupportedModelError(Exception):
    """Raised when a configured model name isn't implemented."""


def sentiment_model_from_config(name: str) -> SentimentModel:
    if name == "lexicon":
        return LexiconSentimentModel()
    if name == "huggingface":
        return HuggingFaceSentimentModel()
    raise UnsupportedModelError(
        f"Unsupported sentiment_model: {name!r}. Supported: 'lexicon', 'huggingface' "
        "('huggingface' requires transformers/torch — see docs/models.md)."
    )


def complaint_model_from_config(name: str) -> ComplaintClassifier:
    if name == "keyword":
        return KeywordComplaintClassifier()
    if name == "huggingface":
        return HuggingFaceZeroShotComplaintClassifier()
    raise UnsupportedModelError(
        f"Unsupported complaint_model: {name!r}. Supported: 'keyword', 'huggingface' "
        "('huggingface' requires transformers/torch — see docs/models.md)."
    )
