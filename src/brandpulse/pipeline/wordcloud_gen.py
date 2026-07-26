"""Word cloud generation (Milestone 6).

Built from Gold-classified Silver text, stopwords removed, emoji tokens
included (they're already normalized to ``:name:`` word-like tokens by
Silver, so no special-casing is needed here — ``WordCloud`` treats them as
ordinary words). Bank/product name variants are excluded — searching for
"Wema" in a Wema report is noise, not signal. Sentiment-weighted coloring:
words that appear more often in Negative/Mixed mentions than Positive ones
render in warmer tones.

Rendered once to a PNG at 1200x600 and returned as both raw PNG bytes (for
``{run_id}_wordcloud.png``) and a base64 data URI (for inline embedding in
the self-contained HTML report — the report must open with zero external
requests, so the image can't be a separate linked file there).
"""

from __future__ import annotations

import base64
import io
import re
from collections import Counter
from typing import Any

from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS
from wordcloud import WordCloud

_TOKEN_RE = re.compile(r"(?<!\w):?[\w'-]+:?(?!\w)")

MIN_FREQUENCY = 3
MAX_WORDS = 150
WIDTH = 1200
HEIGHT = 600


def _default_excluded_terms(brand_terms: tuple[str, ...]) -> set[str]:
    """Bank/product name variants to exclude — a Wema report full of the
    word "Wema" is noise, not signal, since it's the search term itself."""
    excluded = set()
    for term in brand_terms:
        for word in term.lower().split():
            excluded.add(word)
    return excluded


def _tokenize_for_wordcloud(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text)]


def build_word_frequencies(
    records: list[dict[str, Any]], brand_terms: tuple[str, ...] = ()
) -> tuple[Counter, set[str]]:
    """Return (word frequencies, set of words that skew negative/mixed).

    A word "skews negative" if it appears more often across Negative/Mixed
    mentions than Positive/Neutral ones — used for sentiment-weighted color.
    """
    excluded = ENGLISH_STOP_WORDS | _default_excluded_terms(brand_terms)

    frequencies: Counter = Counter()
    negative_counts: Counter = Counter()
    positive_counts: Counter = Counter()

    for record in records:
        text = record.get("text", "")
        sentiment = record.get("sentiment", {}).get("label")
        tokens = [t for t in _tokenize_for_wordcloud(text) if t not in excluded and len(t) > 1]
        frequencies.update(tokens)
        if sentiment in ("Negative", "Mixed"):
            negative_counts.update(set(tokens))
        elif sentiment in ("Positive", "Neutral"):
            positive_counts.update(set(tokens))

    negative_skewed = {
        word for word in frequencies if negative_counts.get(word, 0) > positive_counts.get(word, 0)
    }

    filtered = Counter(
        {word: count for word, count in frequencies.items() if count >= MIN_FREQUENCY}
    )
    return filtered, negative_skewed


def _sentiment_color_func(negative_skewed: set[str]):
    def color_func(word, font_size, position, orientation, random_state=None, **kwargs):
        if word.lower() in negative_skewed:
            return "hsl(10, 80%, 45%)"  # warm red/orange for negative-skewed terms
        return "hsl(210, 60%, 40%)"  # cool blue for everything else

    return color_func


def generate_wordcloud_png(
    records: list[dict[str, Any]], brand_terms: tuple[str, ...] = ()
) -> bytes:
    """Render the word cloud to PNG bytes. Returns a 1x1 transparent PNG
    placeholder if there's no text to render from, rather than raising —
    an empty dataset is a valid (if uninteresting) report state."""
    frequencies, negative_skewed = build_word_frequencies(records, brand_terms)

    if not frequencies:
        frequencies = Counter({"no_data": 1})

    cloud = WordCloud(
        width=WIDTH,
        height=HEIGHT,
        background_color="white",
        max_words=MAX_WORDS,
        color_func=_sentiment_color_func(negative_skewed),
        # Fixed seed — layout placement is otherwise randomized per call, which
        # would make `report` non-idempotent (same Gold data, different PNG
        # bytes) and break the "run report 10 times, get the same output"
        # acceptance criterion. The seed value itself is arbitrary; what
        # matters is that it's fixed, not date/run-derived.
        random_state=42,
    ).generate_from_frequencies(frequencies)

    buffer = io.BytesIO()
    cloud.to_image().save(buffer, format="PNG")
    return buffer.getvalue()


def png_to_data_uri(png_bytes: bytes) -> str:
    encoded = base64.b64encode(png_bytes).decode("ascii")
    return f"data:image/png;base64,{encoded}"
