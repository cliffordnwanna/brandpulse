"""Unit tests for --window parsing (Milestone 6)."""

from datetime import timedelta

import pytest

from brandpulse.pipeline.run_pipeline import InvalidWindowError, parse_window


def test_parse_window_days():
    assert parse_window("7d") == timedelta(days=7)


def test_parse_window_single_digit_day():
    assert parse_window("1d") == timedelta(days=1)


def test_parse_window_large_days():
    assert parse_window("90d") == timedelta(days=90)


def test_parse_window_hours():
    assert parse_window("12h") == timedelta(hours=12)


def test_parse_window_invalid_unit_raises():
    with pytest.raises(InvalidWindowError):
        parse_window("7w")


def test_parse_window_invalid_format_raises():
    with pytest.raises(InvalidWindowError):
        parse_window("not-a-window")


def test_parse_window_empty_raises():
    with pytest.raises(InvalidWindowError):
        parse_window("")
