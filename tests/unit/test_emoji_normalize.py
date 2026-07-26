"""Unit tests for emoji normalization (Milestone 6)."""

from brandpulse.pipeline.emoji_normalize import extract_emoji_tokens, normalize_emoji


def test_normalize_emoji_converts_to_named_tokens():
    result = normalize_emoji("This app dey stress me 😡")
    assert "😡" not in result
    assert ":enraged_face:" in result


def test_normalize_emoji_handles_multiple_emoji():
    result = normalize_emoji("😭😭😭")
    assert result == ":loudly_crying_face::loudly_crying_face::loudly_crying_face:"


def test_normalize_emoji_leaves_plain_text_unchanged():
    result = normalize_emoji("Great app, no wahala!")
    assert result == "Great app, no wahala!"


def test_extract_emoji_tokens_finds_all_tokens():
    text = normalize_emoji("great app 😊 but transfer failed 😡")
    tokens = extract_emoji_tokens(text)
    assert tokens == [":smiling_face_with_smiling_eyes:", ":enraged_face:"]


def test_extract_emoji_tokens_empty_for_no_emoji():
    assert extract_emoji_tokens("plain text") == []
