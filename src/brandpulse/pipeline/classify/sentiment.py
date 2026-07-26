"""Sentiment classification — NaijaBERT-class model, always runs (Engineering Design §10).

``SentimentModel`` is the seam between pipeline logic and any specific model
implementation — the same pattern as ``StorageBackend`` (Milestone 4). Two
implementations exist:

- ``LexiconSentimentModel`` (default): a Pidgin-aware keyword/lexicon scorer.
  No model download, no network, runs anywhere. This is what actually runs
  in this build environment, which has no ``transformers``/``torch`` or
  HuggingFace Hub access — see ``docs/models.md``.
- ``HuggingFaceSentimentModel`` (wired, not default): loads the real model
  IDs named in the milestone spec via ``transformers.pipeline``. Selected by
  setting ``classification.sentiment_model: huggingface`` in config, once
  the dependencies from ``docs/models.md`` are installed.

Never call either implementation directly from pipeline code — always go
through ``SentimentModel`` so swapping is a config change, not a rewrite.
"""

from __future__ import annotations

import re
from typing import Protocol

from brandpulse.pipeline.classify.result import StageResult

SENTIMENT_LABELS = ("Positive", "Negative", "Neutral", "Mixed")

# HuggingFace model IDs from the milestone spec — see docs/models.md for the
# install step required before HuggingFaceSentimentModel can actually load them.
NAIJA_SENTIMENT_MODEL_ID = "Davlan/naija-twitter-sentiment-afriberta-large"
XLM_R_SENTIMENT_MODEL_ID = "cardiffnlp/twitter-xlm-roberta-base-sentiment"
ENGLISH_FALLBACK_MODEL_ID = "cardiffnlp/twitter-roberta-base-sentiment-latest"


class SentimentModel(Protocol):
    """Interface every sentiment model implementation satisfies."""

    def predict(self, text: str, language: str | None) -> StageResult:
        """Predict sentiment for ``text`` (already language-tagged in Silver)."""
        ...


_POSITIVE_WORDS = {
    "great",
    "good",
    "excellent",
    "love",
    "awesome",
    "fast",
    "easy",
    "helpful",
    "reliable",
    "smooth",
    "best",
    "amazing",
    "sweet",
    "correct",
    "nice",
    "happy",
    "thank",
    "thanks",
    "works",
    "working",
    "perfect",
    "recommend",
    "impressed",
}

_NEGATIVE_WORDS = {
    "bad",
    "terrible",
    "worst",
    "fraud",
    "scam",
    "fail",
    "failed",
    "failing",
    "stuck",
    "delay",
    "delayed",
    "slow",
    "crash",
    "crashed",
    "crashing",
    "wahala",
    "stress",
    "stressful",
    "useless",
    "annoying",
    "angry",
    "disappointed",
    "disappointing",
    "hate",
    "poor",
    "wrong",
    "error",
    "problem",
    "issue",
    "complaint",
    "complain",
    "debited",
    "reversed",
    "unresponsive",
    "horrible",
    "awful",
    "broken",
    "not working",
    "no response",
    "waste",
}

_NEGATION_WORDS = {"not", "never", "no", "cannot", "can't", "cant", "dont", "don't"}


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[\w']+", text.lower())


def _score_tokens(tokens: list[str]) -> tuple[int, int, list[str]]:
    """Return (positive_hits, negative_hits, matched_words), with simple
    negation handling: a positive word preceded within 2 tokens by a negation
    word counts as negative instead (and vice versa)."""
    positive_hits = 0
    negative_hits = 0
    matched: list[str] = []

    for i, token in enumerate(tokens):
        window = tokens[max(0, i - 2) : i]
        negated = bool(window and _NEGATION_WORDS & set(window))

        if token in _POSITIVE_WORDS:
            matched.append(token)
            if negated:
                negative_hits += 1
            else:
                positive_hits += 1
        elif token in _NEGATIVE_WORDS:
            matched.append(token)
            if negated:
                positive_hits += 1
            else:
                negative_hits += 1

    return positive_hits, negative_hits, matched


class LexiconSentimentModel:
    """Default sentiment model: Pidgin-aware keyword/lexicon scoring.

    Offline, deterministic, no model download. Confidence is derived from
    how lopsided the positive/negative signal is, not a calibrated
    probability — documented as an approximation, same spirit as the
    Milestone 4 language-detection heuristic layer.
    """

    def predict(self, text: str, language: str | None) -> StageResult:
        tokens = _tokenize(text)
        positive_hits, negative_hits, matched = _score_tokens(tokens)

        if positive_hits == 0 and negative_hits == 0:
            return StageResult(
                label="Neutral",
                confidence=0.55,
                reason="No sentiment-bearing words matched the lexicon.",
            )

        if positive_hits > 0 and negative_hits > 0:
            total = positive_hits + negative_hits
            confidence = 0.5 + 0.1 * min(abs(positive_hits - negative_hits), 3)
            return StageResult(
                label="Mixed",
                confidence=round(min(confidence, 0.85), 2),
                reason=(
                    f"Both positive ({positive_hits}) and negative ({negative_hits}) "
                    f"signal words matched: {', '.join(matched[:6])}."
                ),
            )

        total = positive_hits + negative_hits
        confidence = round(min(0.6 + 0.1 * total, 0.97), 2)
        if positive_hits > negative_hits:
            return StageResult(
                label="Positive",
                confidence=confidence,
                reason=f"Positive signal words matched: {', '.join(matched[:6])}.",
            )
        return StageResult(
            label="Negative",
            confidence=confidence,
            reason=f"Negative signal words matched: {', '.join(matched[:6])}.",
        )


class HuggingFaceSentimentModel:
    """Real NaijaBERT/XLM-R-backed sentiment model (Engineering Design §10, Milestone spec).

    Not the default — requires ``transformers``/``torch`` and a HuggingFace
    Hub download, neither available in the environment this milestone was
    built in. See ``docs/models.md`` for the exact install step. Import of
    ``transformers`` is deferred to ``__init__`` so simply importing this
    module (e.g. for the factory to reference the class) never requires the
    dependency to be installed.
    """

    def __init__(self, model_id: str = NAIJA_SENTIMENT_MODEL_ID) -> None:
        from transformers import pipeline  # noqa: PLC0415

        self._model_id = model_id
        self._pipeline = pipeline("sentiment-analysis", model=model_id)

    def predict(self, text: str, language: str | None) -> StageResult:
        result = self._pipeline(text, truncation=True)[0]
        return StageResult(
            label=str(result["label"]),
            confidence=float(result["score"]),
            reason=f"{self._model_id} prediction.",
        )
