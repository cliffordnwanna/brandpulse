"""Unit tests for session logging (Milestone 5 spec — new requirement)."""

from pathlib import Path

import pytest

from brandpulse.pipeline.session_log import build_session_summary, write_session_log


def _gold_records():
    return [
        {
            "mention_id": "m1",
            "sentiment": {"label": "Positive", "confidence": 0.9, "reason": "r"},
            "complaint_category": {"label": "Transfers", "confidence": 0.9, "reason": "r"},
        },
        {
            "mention_id": "m2",
            "sentiment": {"label": "Negative", "confidence": 0.4, "reason": "r"},
            "complaint_category": {"label": "Fraud", "confidence": 0.4, "reason": "r"},
        },
        {
            "mention_id": "m3",
            "sentiment": {"label": "Negative", "confidence": 0.6, "reason": "r"},
            "complaint_category": {"label": "Transfers", "confidence": 0.6, "reason": "r"},
        },
    ]


def test_build_session_summary_has_sentiment_distribution():
    summary = build_session_summary(
        run_id="run-1",
        sources_scraped=["google_play"],
        mention_counts_per_source={"google_play": 3},
        gold_records=_gold_records(),
        confidence_threshold=0.75,
        failed_connectors=[],
    )
    assert summary["sentiment_distribution"]["Negative"]["count"] == 2
    assert summary["sentiment_distribution"]["Positive"]["count"] == 1


def test_build_session_summary_top_complaint_categories():
    summary = build_session_summary(
        run_id="run-1",
        sources_scraped=["google_play"],
        mention_counts_per_source={"google_play": 3},
        gold_records=_gold_records(),
        confidence_threshold=0.75,
        failed_connectors=[],
    )
    top = {c["category"]: c["count"] for c in summary["top_complaint_categories"]}
    assert top["Transfers"] == 2
    assert top["Fraud"] == 1


def test_build_session_summary_confidence_distribution_below_threshold():
    summary = build_session_summary(
        run_id="run-1",
        sources_scraped=["google_play"],
        mention_counts_per_source={"google_play": 3},
        gold_records=_gold_records(),
        confidence_threshold=0.75,
        failed_connectors=[],
    )
    dist = summary["confidence_distribution"]
    assert dist["mean"] is not None
    assert dist["pct_below_threshold"] > 0


def test_build_session_summary_empty_gold_records_does_not_crash():
    summary = build_session_summary(
        run_id="run-1",
        sources_scraped=[],
        mention_counts_per_source={},
        gold_records=[],
        confidence_threshold=0.75,
        failed_connectors=["nairaland"],
    )
    assert summary["confidence_distribution"]["mean"] is None
    assert summary["failed_connectors"] == ["nairaland"]


def test_write_session_log_creates_file_under_sessions_dir(tmp_path: Path):
    summary = build_session_summary(
        run_id="run-1",
        sources_scraped=["google_play"],
        mention_counts_per_source={"google_play": 1},
        gold_records=_gold_records()[:1],
        confidence_threshold=0.75,
        failed_connectors=[],
    )
    path = write_session_log(tmp_path / "output", summary)
    assert path == tmp_path / "output" / "sessions" / "run-1.json"
    assert path.exists()


def test_write_session_log_never_overwrites_existing_session(tmp_path: Path):
    summary = build_session_summary(
        run_id="run-1",
        sources_scraped=[],
        mention_counts_per_source={},
        gold_records=[],
        confidence_threshold=0.75,
        failed_connectors=[],
    )
    write_session_log(tmp_path / "output", summary)
    with pytest.raises(FileExistsError):
        write_session_log(tmp_path / "output", summary)
