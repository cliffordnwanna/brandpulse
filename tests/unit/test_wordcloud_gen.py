"""Unit tests for word cloud generation (Milestone 6)."""

from brandpulse.pipeline.wordcloud_gen import (
    build_word_frequencies,
    generate_wordcloud_png,
    png_to_data_uri,
)


def _records():
    return [
        {
            "text": "transfer failed transfer failed transfer failed",
            "sentiment": {"label": "Negative"},
        },
        {"text": "great app great app great app easy", "sentiment": {"label": "Positive"}},
    ]


def test_build_word_frequencies_counts_words_above_min_frequency():
    frequencies, _ = build_word_frequencies(_records())
    assert frequencies["transfer"] == 3
    assert frequencies["failed"] == 3
    assert frequencies["great"] == 3


def test_build_word_frequencies_excludes_brand_terms():
    records = [
        {"text": "wema wema wema great app great app great", "sentiment": {"label": "Positive"}}
    ]
    frequencies, _ = build_word_frequencies(records, brand_terms=("Wema",))
    assert "wema" not in frequencies


def test_build_word_frequencies_negative_skewed_words():
    _, negative_skewed = build_word_frequencies(_records())
    assert "failed" in negative_skewed
    assert "great" not in negative_skewed


def test_build_word_frequencies_below_min_frequency_excluded():
    records = [{"text": "onlyonce", "sentiment": {"label": "Neutral"}}]
    frequencies, _ = build_word_frequencies(records)
    assert "onlyonce" not in frequencies


def test_generate_wordcloud_png_returns_valid_png_bytes():
    png_bytes = generate_wordcloud_png(_records())
    assert png_bytes[:8] == b"\x89PNG\r\n\x1a\n"  # PNG magic number


def test_generate_wordcloud_png_deterministic_for_same_input():
    png1 = generate_wordcloud_png(_records())
    png2 = generate_wordcloud_png(_records())
    assert png1 == png2


def test_generate_wordcloud_png_handles_empty_records():
    png_bytes = generate_wordcloud_png([])
    assert png_bytes[:8] == b"\x89PNG\r\n\x1a\n"


def test_png_to_data_uri_format():
    png_bytes = generate_wordcloud_png(_records())
    uri = png_to_data_uri(png_bytes)
    assert uri.startswith("data:image/png;base64,")
