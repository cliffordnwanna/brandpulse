"""The staged classification pipeline (Engineering Design §10, Milestone 5).

Tier 5a (sentiment + complaint category) runs on every Silver record,
unconditionally — no LLM call. Tier 5b (emotion/intent/urgency/competitor/
summary) is optional enrichment, gated by ``ClassificationConfig.enable_enrichment``
and, when enabled, further gated per-mention by the trigger rule (Engineering
Design §10): a mention only reaches 5b if 5a's confidence was low, its
complaint category came back ``Unknown``, or its sentiment was ``Mixed``.
This is what keeps ``enable_enrichment: false`` producing *zero* LLM calls,
and ``enable_enrichment: true`` still only calling the LLM for the mentions
that actually need it — never every mention (CLAUDE.md invariant #12).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from brandpulse.config.models import ClassificationConfig
from brandpulse.pipeline.classify.competitor import classify_competitor_mention
from brandpulse.pipeline.classify.complaint import UNKNOWN_CATEGORY, ComplaintClassifier
from brandpulse.pipeline.classify.complaint_overflow import reclassify_unknown_complaint
from brandpulse.pipeline.classify.emotion import classify_emotion
from brandpulse.pipeline.classify.intent import classify_intent
from brandpulse.pipeline.classify.result import StageResult
from brandpulse.pipeline.classify.sentiment import SentimentModel
from brandpulse.pipeline.classify.sentiment_fallback import recheck_low_confidence_sentiment
from brandpulse.pipeline.classify.severity import classify_urgency
from brandpulse.pipeline.classify.summary import generate_summary
from brandpulse.pipeline.gold import write_gold_record
from brandpulse.pipeline.llm_client import LLMCallLogger, LLMClient
from brandpulse.storage.base import StorageBackend

CLASSIFIER_VERSION_5A = "5a-v1"


def needs_enrichment(
    sentiment: StageResult, complaint_category: StageResult, config: ClassificationConfig
) -> bool:
    """The 5b trigger rule (Engineering Design §10): low confidence, Unknown
    category, or Mixed sentiment. ``enrichment_trigger: all`` bypasses the
    rule and enriches every mention; any other unrecognized trigger value
    behaves as ``low_confidence`` (the safest/cheapest default)."""
    if config.enrichment_trigger == "all":
        return True

    low_confidence = (
        sentiment.confidence < config.confidence_threshold
        or complaint_category.confidence < config.confidence_threshold
    )
    return (
        low_confidence or complaint_category.label == UNKNOWN_CATEGORY or sentiment.label == "Mixed"
    )


def classify_5a(
    text: str,
    language: str | None,
    sentiment_model: SentimentModel,
    complaint_classifier: ComplaintClassifier,
) -> dict[str, Any]:
    """Run Tier 5a — sentiment + complaint category. No LLM call, ever."""
    sentiment = sentiment_model.predict(text, language)
    complaint_category = complaint_classifier.classify(text, language)

    return {
        "classifier_version": CLASSIFIER_VERSION_5A,
        "sentiment": sentiment.model_dump(),
        "complaint_category": complaint_category.model_dump(),
        "language_routed_as": language,
        "processed_at": datetime.now(UTC).isoformat(),
    }


def classify_5b(
    mention_id: str,
    text: str,
    language: str | None,
    sentiment: StageResult,
    complaint_category: StageResult,
    config: ClassificationConfig,
    llm_client: LLMClient,
    call_logger: LLMCallLogger,
) -> dict[str, Any]:
    """Run Tier 5b — emotion/intent/urgency/competitor/summary, plus the two
    other LLM-conditional cases (Engineering Design §10): a low-confidence
    sentiment re-check and Unknown-category overflow reclassification, each
    only invoked if that specific case actually applies to this mention.
    Every call made here goes through ``call_logger``, since every 5b stage
    is LLM-backed."""
    prompt_versions = {
        "emotion": "v1",
        "intent": "v1",
        "urgency": "v1",
        "competitor_mention": "v1",
        "summary": "v1",
    }

    result: dict[str, Any] = {}

    if sentiment.confidence < config.confidence_threshold:
        rechecked_sentiment = recheck_low_confidence_sentiment(
            mention_id, text, language, sentiment, llm_client, call_logger
        )
        result["sentiment"] = rechecked_sentiment.model_dump()
        prompt_versions["sentiment_fallback"] = "v1"

    if complaint_category.label == UNKNOWN_CATEGORY:
        reclassified_category = reclassify_unknown_complaint(
            mention_id, text, language, llm_client, call_logger
        )
        result["complaint_category"] = reclassified_category.model_dump()
        prompt_versions["complaint_classification"] = "v1"

    emotion = classify_emotion(mention_id, text, language, llm_client, call_logger)
    intent = classify_intent(mention_id, text, language, llm_client, call_logger)
    urgency = classify_urgency(mention_id, text, language, llm_client, call_logger)
    competitor = classify_competitor_mention(mention_id, text, language, llm_client, call_logger)
    summary = generate_summary(mention_id, text, language, llm_client, call_logger)

    result.update(
        {
            "emotion": emotion.model_dump(),
            "intent": intent.model_dump(),
            "urgency": urgency.model_dump(),
            "competitor_mention": competitor.model_dump(),
            "summary": summary,
            "enrichment_model": llm_client.model_name,
            "enrichment_prompt_versions": prompt_versions,
        }
    )
    return result


def classify_silver_record(
    silver_record: dict[str, Any],
    *,
    sentiment_model: SentimentModel,
    complaint_classifier: ComplaintClassifier,
    config: ClassificationConfig,
    llm_client: LLMClient | None,
    call_logger: LLMCallLogger,
    backend: StorageBackend,
) -> dict[str, Any]:
    """Classify one Silver record end-to-end and write it to Gold.

    ``llm_client`` may be ``None`` only when ``config.enable_enrichment`` is
    ``False`` — enforced by the caller (``config`` gates whether 5b ever runs
    at all, independent of any single mention's trigger evaluation), so this
    function never has to guess whether an enrichment-capable client exists.
    """
    mention_id = silver_record["mention_id"]
    text = silver_record["text"]
    language = silver_record.get("language")

    record: dict[str, Any] = {"mention_id": mention_id}
    record.update(classify_5a(text, language, sentiment_model, complaint_classifier))

    if config.enable_enrichment and llm_client is not None:
        sentiment = StageResult.model_validate(record["sentiment"])
        complaint_category = StageResult.model_validate(record["complaint_category"])
        if needs_enrichment(sentiment, complaint_category, config):
            record.update(
                classify_5b(
                    mention_id,
                    text,
                    language,
                    sentiment,
                    complaint_category,
                    config,
                    llm_client,
                    call_logger,
                )
            )

    write_gold_record(backend, mention_id, CLASSIFIER_VERSION_5A, record)
    return record
