"""Integration tests for report generation from Gold (Milestone 6).

Covers the spec's explicit separation rule ("someone should be able to run
`report` 10 times on the same Gold data and get the same output") and
session-scoping (a session log's `mention_ids` restricts what a report
covers, vs. the pre-Milestone-6 cumulative behavior for older session logs).
"""

from pathlib import Path

from brandpulse.config.models import (
    ClassificationConfig,
    Config,
    KeywordsConfig,
    OutputConfig,
    RateLimitConfig,
    RetryConfig,
    SourceConfig,
    TimeoutsConfig,
)
from brandpulse.pipeline.report_pipeline import generate_report
from brandpulse.pipeline.session_log import build_session_summary, write_session_log
from brandpulse.storage.local import LocalFileStorageBackend
from tests.fixtures.seed_silver import seed_silver_record


def _config(tmp_path: Path) -> Config:
    return Config(
        sources=[SourceConfig(name="google_play", enabled=True, reliability="high")],
        keywords=KeywordsConfig(base_list=["Wema"]),
        output=OutputConfig(directory=str(tmp_path / "output"), formats=["csv"]),
        retry=RetryConfig(max_attempts=3, backoff_seconds=[0, 0, 0]),
        timeouts=TimeoutsConfig(request_seconds=20),
        rate_limit=RateLimitConfig(requests_per_minute=6000, respect_robots_txt=False),
        classification=ClassificationConfig(enable_enrichment=False),
    )


def _seed_gold(backend, mention_id, text, sentiment, category):
    seed_silver_record(backend, mention_id, text)
    backend.write(
        "gold",
        f"{mention_id}_5a-v1",
        {
            "mention_id": mention_id,
            "classifier_version": "5a-v1",
            "sentiment": {"label": sentiment, "confidence": 0.9, "reason": "r"},
            "complaint_category": {"label": category, "confidence": 0.9, "reason": "r"},
        },
    )


def test_report_raises_if_no_session_log(tmp_path: Path):
    import pytest

    backend = LocalFileStorageBackend(tmp_path / "storage")
    config = _config(tmp_path)

    with pytest.raises(FileNotFoundError):
        generate_report(backend, config, "no-such-run")


def test_report_produces_all_bridge_files(tmp_path: Path):
    backend = LocalFileStorageBackend(tmp_path / "storage")
    config = _config(tmp_path)

    _seed_gold(backend, "m1", "transfer failed badly", "Negative", "Transfers")
    gold_records = list(backend.read_all("gold"))
    session = build_session_summary(
        "run-1", ["google_play"], {"google_play": 1}, gold_records, 0.75, []
    )
    write_session_log(config.output.directory, session)

    result = generate_report(backend, config, "run-1")

    assert Path(result["html_path"]).exists()
    assert Path(result["wordcloud_path"]).exists()
    assert Path(result["phrases_path"]).exists()
    assert Path(result["insights_path"]).exists()
    assert Path(result["platform_limitations_path"]).exists()


def test_report_is_byte_identical_across_repeated_calls(tmp_path: Path):
    """The spec's explicit acceptance criterion: run `report` repeatedly on
    unchanged Gold data and get the same output every time."""
    backend = LocalFileStorageBackend(tmp_path / "storage")
    config = _config(tmp_path)

    _seed_gold(backend, "m1", "transfer failed badly, no refund", "Negative", "Transfers")
    _seed_gold(backend, "m2", "great app, easy transfers", "Positive", "General Feedback")
    gold_records = list(backend.read_all("gold"))
    session = build_session_summary(
        "run-1", ["google_play"], {"google_play": 2}, gold_records, 0.75, []
    )
    write_session_log(config.output.directory, session)

    result_1 = generate_report(backend, config, "run-1")
    html_1 = Path(result_1["html_path"]).read_bytes()
    png_1 = Path(result_1["wordcloud_path"]).read_bytes()

    result_2 = generate_report(backend, config, "run-1")
    html_2 = Path(result_2["html_path"]).read_bytes()
    png_2 = Path(result_2["wordcloud_path"]).read_bytes()

    assert html_1 == html_2
    assert png_1 == png_2


def test_report_never_writes_to_bronze_silver_or_gold(tmp_path: Path):
    """`report` must never scrape or classify — only read existing data."""
    backend = LocalFileStorageBackend(tmp_path / "storage")
    config = _config(tmp_path)

    _seed_gold(backend, "m1", "transfer failed", "Negative", "Transfers")
    gold_records = list(backend.read_all("gold"))
    session = build_session_summary(
        "run-1", ["google_play"], {"google_play": 1}, gold_records, 0.75, []
    )
    write_session_log(config.output.directory, session)

    bronze_before = list(backend.read_all("bronze"))
    silver_before = list(backend.read_all("silver"))
    gold_before = list(backend.read_all("gold"))

    generate_report(backend, config, "run-1")

    assert list(backend.read_all("bronze")) == bronze_before
    assert list(backend.read_all("silver")) == silver_before
    assert list(backend.read_all("gold")) == gold_before


def test_report_scopes_to_session_mention_ids_when_present(tmp_path: Path):
    """Only mention_ids recorded in the session log's `mention_ids` field
    should appear in the report — even if more Gold data exists overall
    (from a different session)."""
    backend = LocalFileStorageBackend(tmp_path / "storage")
    config = _config(tmp_path)

    _seed_gold(backend, "m1", "transfer failed this session", "Negative", "Transfers")
    _seed_gold(backend, "m2", "old complaint from a different session", "Negative", "Fraud")

    # session log only claims m1 — simulating "snapshot" mode scoping
    session = {
        "run_id": "run-1",
        "run_timestamp": "2026-01-01T00:00:00+00:00",
        "sources_scraped": ["google_play"],
        "mention_counts_per_source": {"google_play": 1},
        "mention_ids": ["m1"],
        "sentiment_distribution": {},
        "top_complaint_categories": [],
        "complaint_category_counts": {},
        "confidence_distribution": {},
        "failed_connectors": [],
    }
    write_session_log(config.output.directory, session)

    result = generate_report(backend, config, "run-1")
    insights_json = Path(result["insights_path"]).read_text(encoding="utf-8")

    assert (
        "transfer failed this session" not in insights_json
    )  # text isn't in insights.json directly
    # but phrase mining should only reflect m1's text, not m2's
    phrases_csv = Path(result["phrases_path"]).read_text(encoding="utf-8")
    assert "old complaint" not in phrases_csv
