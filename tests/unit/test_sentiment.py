"""Unit tests for the default (lexicon) sentiment model (Milestone 5)."""

from brandpulse.pipeline.classify.sentiment import LexiconSentimentModel


def test_positive_text_classified_positive():
    result = LexiconSentimentModel().predict("Great app, easy transfers, very fast!", "en")
    assert result.label == "Positive"
    assert 0.0 < result.confidence <= 1.0
    assert result.reason


def test_negative_text_classified_negative():
    result = LexiconSentimentModel().predict(
        "Terrible service, my transfer failed and support is unresponsive.", "en"
    )
    assert result.label == "Negative"


def test_neutral_text_with_no_sentiment_words():
    result = LexiconSentimentModel().predict("What time does the branch open?", "en")
    assert result.label == "Neutral"


def test_mixed_text_with_both_signals():
    result = LexiconSentimentModel().predict(
        "The app is fast but customer service is really slow and disappointing.", "en"
    )
    assert result.label == "Mixed"


def test_negation_flips_positive_to_negative():
    result = LexiconSentimentModel().predict("This app is not good at all.", "en")
    assert result.label == "Negative"


def test_result_always_has_label_confidence_reason():
    result = LexiconSentimentModel().predict("random text with no signal", "en")
    assert result.label
    assert isinstance(result.confidence, float)
    assert isinstance(result.reason, str) and result.reason
