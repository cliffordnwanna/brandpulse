"""Unit tests for shared connector politeness controls (Engineering Design §17)."""

import time

import pytest
import requests

from brandpulse.connectors.politeness import RateLimiter, is_allowed_by_robots_txt, random_delay


def test_random_delay_within_bounds():
    for _ in range(20):
        delay = random_delay(0.1, 0.5)
        assert 0.1 <= delay <= 0.5


def test_rate_limiter_enforces_minimum_interval():
    limiter = RateLimiter(requests_per_minute=60)  # 1 request/sec
    sleeps: list[float] = []

    fake_time = [100.0]  # nonzero start so "no prior request" isn't indistinguishable from "at t=0"

    def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)
        fake_time[0] += seconds

    original_monotonic = time.monotonic
    try:
        time.monotonic = lambda: fake_time[0]
        limiter.acquire(sleep_fn=fake_sleep)  # first call: nothing to wait for yet
        fake_time[0] += 0.1  # simulate 0.1s of work between requests
        limiter.acquire(sleep_fn=fake_sleep)
    finally:
        time.monotonic = original_monotonic

    assert len(sleeps) == 1
    assert sleeps[0] == pytest.approx(0.9)  # needed ~1s total interval, only slept the remainder


def test_is_allowed_by_robots_txt_fails_open_on_unreachable_robots_txt(monkeypatch):
    def _raise_get(*args, **kwargs):
        raise requests.ConnectionError("unreachable")

    monkeypatch.setattr("brandpulse.connectors.politeness.requests.get", _raise_get)

    assert is_allowed_by_robots_txt("https://example.com/x", "TestBot") is True


def test_is_allowed_by_robots_txt_fails_open_on_404(monkeypatch):
    class _FakeResponse:
        status_code = 404
        text = ""

    monkeypatch.setattr(
        "brandpulse.connectors.politeness.requests.get", lambda *a, **k: _FakeResponse()
    )

    assert is_allowed_by_robots_txt("https://example.com/x", "TestBot") is True


def test_is_allowed_by_robots_txt_respects_disallow(monkeypatch):
    class _FakeResponse:
        status_code = 200
        text = "User-agent: *\nDisallow: /blocked"

    monkeypatch.setattr(
        "brandpulse.connectors.politeness.requests.get", lambda *a, **k: _FakeResponse()
    )

    assert is_allowed_by_robots_txt("https://example.com/blocked", "TestBot") is False
    assert is_allowed_by_robots_txt("https://example.com/allowed", "TestBot") is True


def test_is_allowed_by_robots_txt_fetches_with_provided_user_agent(monkeypatch):
    """The robots.txt fetch itself must use the connector's real User-Agent
    header, not robotparser's default — this is the actual Milestone 7 fix:
    some sites 403 the bare-urllib fetch robotparser performs internally,
    which robotparser then misreads as "disallow everything" rather than
    "couldn't reach it," incorrectly blocking paths the site's real
    robots.txt permits."""
    seen_headers = {}

    class _FakeResponse:
        status_code = 200
        text = "User-agent: *\nAllow: /"

    def _fake_get(url, headers=None, timeout=None):
        seen_headers.update(headers or {})
        return _FakeResponse()

    monkeypatch.setattr("brandpulse.connectors.politeness.requests.get", _fake_get)

    is_allowed_by_robots_txt("https://example.com/x", "BrandPulseBot/0.1")

    assert seen_headers.get("User-Agent") == "BrandPulseBot/0.1"
