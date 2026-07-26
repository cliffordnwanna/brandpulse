"""Unit tests for output file writers (Milestone 6).

Every writer must run the anonymization check before writing — these tests
verify both the file contents and that author fields get hashed.
"""

import csv
import json
from pathlib import Path

from brandpulse.orchestration.run_report import ConnectorRunOutcome, RunReport
from brandpulse.pipeline.insight_engine import Insight
from brandpulse.pipeline.output_writers import (
    write_classifications_csv,
    write_connector_health_csv,
    write_errors_csv,
    write_insights_json,
    write_mentions_csv,
    write_phrases_csv,
    write_run_metadata_json,
    write_summary_csv,
)


def test_write_mentions_csv_hashes_author(tmp_path: Path):
    records = [{"mention_id": "m1", "text": "hi", "platform": "google_play", "author": "john_doe"}]
    path = write_mentions_csv(tmp_path / "mentions.csv", records, run_id="run-1")

    with path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    assert rows[0]["author"].startswith("User#")
    assert rows[0]["author"] != "john_doe"


def test_write_mentions_csv_columns(tmp_path: Path):
    records = [{"mention_id": "m1", "text": "hi", "platform": "google_play"}]
    path = write_mentions_csv(tmp_path / "mentions.csv", records, run_id="run-1")

    with path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    assert rows[0]["mention_id"] == "m1"
    assert rows[0]["text"] == "hi"


def test_write_classifications_csv_flattens_stage_results(tmp_path: Path):
    records = [
        {
            "mention_id": "m1",
            "classifier_version": "5a-v1",
            "sentiment": {"label": "Negative", "confidence": 0.9},
            "complaint_category": {"label": "Transfers", "confidence": 0.8},
        }
    ]
    path = write_classifications_csv(tmp_path / "classifications.csv", records, run_id="run-1")

    with path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    assert rows[0]["sentiment_label"] == "Negative"
    assert rows[0]["complaint_category_label"] == "Transfers"


def test_write_summary_csv_contains_sentiment_and_categories(tmp_path: Path):
    session_summary = {
        "sentiment_distribution": {"Negative": {"count": 5, "pct": 50.0}},
        "top_complaint_categories": [{"category": "Transfers", "count": 5}],
        "mention_counts_per_source": {"google_play": 10},
    }
    path = write_summary_csv(tmp_path / "summary.csv", session_summary)
    content = path.read_text(encoding="utf-8")
    assert "Negative" in content
    assert "Transfers" in content
    assert "google_play" in content


def test_write_errors_csv_only_includes_failed_or_partial(tmp_path: Path):
    run_report = RunReport()
    run_report.record(
        ConnectorRunOutcome(
            connector_name="google_play",
            search_term="_all",
            status="FAILED",
            duration_s=1.0,
            result_count=0,
            reason="timeout",
        )
    )
    run_report.record(
        ConnectorRunOutcome(
            connector_name="google_play",
            search_term="_all",
            status="SUCCESS",
            duration_s=1.0,
            result_count=5,
        )
    )
    path = write_errors_csv(tmp_path / "errors.csv", run_report)

    with path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    assert len(rows) == 1
    assert rows[0]["status"] == "FAILED"
    assert rows[0]["reason"] == "timeout"


def test_write_connector_health_csv_includes_all_outcomes(tmp_path: Path):
    run_report = RunReport()
    run_report.record(
        ConnectorRunOutcome(
            connector_name="google_play",
            search_term="_all",
            status="SUCCESS",
            duration_s=2.5,
            result_count=10,
        )
    )
    path = write_connector_health_csv(tmp_path / "connector_health.csv", run_report)

    with path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    assert rows[0]["connector"] == "google_play"
    assert rows[0]["result_count"] == "10"


def test_write_run_metadata_json_structure(tmp_path: Path):
    run_report = RunReport()
    run_report.record(
        ConnectorRunOutcome(
            connector_name="google_play",
            search_term="_all",
            status="SUCCESS",
            duration_s=1.0,
            result_count=3,
        )
    )
    path = write_run_metadata_json(
        tmp_path / "run_metadata.json", "run-1", {"key": "value"}, run_report
    )

    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["run_id"] == "run-1"
    assert data["config"] == {"key": "value"}
    assert len(data["connector_outcomes"]) == 1


def test_write_phrases_csv_limits_to_50(tmp_path: Path):
    phrases = [{"phrase": f"phrase {i}", "count": i} for i in range(60)]
    path = write_phrases_csv(tmp_path / "phrases.csv", phrases)

    with path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    assert len(rows) == 50


def test_write_insights_json_roundtrips_insight_fields(tmp_path: Path):
    insights = [
        Insight(
            id="x",
            title="t",
            description="d",
            severity="high",
            confidence=0.9,
            data={"a": 1},
            insight_type="spike",
            recommendation="do this",
        )
    ]
    path = write_insights_json(tmp_path / "insights.json", insights)

    data = json.loads(path.read_text(encoding="utf-8"))
    assert data[0]["id"] == "x"
    assert data[0]["severity"] == "high"
    assert data[0]["recommendation"] == "do this"
    assert data[0]["data"] == {"a": 1}
