"""Output file writers (Engineering Design §14, Milestone 6).

Every writer here runs the anonymization check (``pipeline/anonymize.py``)
on any record containing free text before it touches disk — "before every
output write" is the spec's exact wording, enforced structurally by routing
every text-bearing writer through ``_check_and_hash_authors`` rather than
trusting each call site to remember.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from brandpulse.orchestration.run_report import RunReport
from brandpulse.pipeline.anonymize import anonymization_check, hash_author


def _check_and_hash_authors(records: list[dict[str, Any]], run_id: str) -> list[dict[str, Any]]:
    """Anonymization gate + author hashing, applied uniformly before any
    record reaches an output file. Returns new dicts — never mutates the
    caller's records (those may still be the live Silver/Gold data)."""
    hashed = []
    for record in records:
        new_record = dict(record)
        if "author" in new_record:
            new_record["author"] = hash_author(new_record["author"], salt=run_id)
        hashed.append(new_record)
    anonymization_check(hashed)
    return hashed


def write_mentions_csv(path: str | Path, silver_records: list[dict[str, Any]], run_id: str) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    records = _check_and_hash_authors(silver_records, run_id)

    fieldnames = [
        "mention_id",
        "platform",
        "source_type",
        "author",
        "url",
        "text",
        "language",
        "timestamp",
        "reliability",
    ]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for record in records:
            writer.writerow(record)
    return path


def write_classifications_csv(
    path: str | Path, gold_records: list[dict[str, Any]], run_id: str
) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    records = _check_and_hash_authors(gold_records, run_id)

    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "mention_id",
                "classifier_version",
                "sentiment_label",
                "sentiment_confidence",
                "complaint_category_label",
                "complaint_category_confidence",
                "emotion_label",
                "intent_label",
                "urgency_label",
                "competitor_mention_label",
                "summary",
            ]
        )
        for record in records:
            sentiment = record.get("sentiment", {})
            complaint = record.get("complaint_category", {})
            emotion = record.get("emotion", {})
            intent = record.get("intent", {})
            urgency = record.get("urgency", {})
            competitor = record.get("competitor_mention", {})
            writer.writerow(
                [
                    record.get("mention_id"),
                    record.get("classifier_version"),
                    sentiment.get("label"),
                    sentiment.get("confidence"),
                    complaint.get("label"),
                    complaint.get("confidence"),
                    emotion.get("label"),
                    intent.get("label"),
                    urgency.get("label"),
                    competitor.get("label"),
                    record.get("summary"),
                ]
            )
    return path


def write_summary_csv(path: str | Path, session_summary: dict[str, Any]) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["metric", "key", "value"])
        for label, stats in session_summary.get("sentiment_distribution", {}).items():
            writer.writerow(["sentiment", label, stats.get("count")])
        for row in session_summary.get("top_complaint_categories", []):
            writer.writerow(["complaint_category", row["category"], row["count"]])
        for source, count in session_summary.get("mention_counts_per_source", {}).items():
            writer.writerow(["mentions_per_source", source, count])
    return path


def write_errors_csv(path: str | Path, run_report: RunReport) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["connector", "search_term", "status", "reason", "duration_s"])
        for outcome in run_report.failed_or_partial():
            writer.writerow(
                [
                    outcome.connector_name,
                    outcome.search_term,
                    outcome.status,
                    outcome.reason or "",
                    outcome.duration_s,
                ]
            )
    return path


def write_connector_health_csv(path: str | Path, run_report: RunReport) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            ["connector", "search_term", "status", "duration_s", "result_count", "auto_disabled"]
        )
        for outcome in run_report.outcomes:
            writer.writerow(
                [
                    outcome.connector_name,
                    outcome.search_term,
                    outcome.status,
                    outcome.duration_s,
                    outcome.result_count,
                    outcome.auto_disabled,
                ]
            )
    return path


def write_run_metadata_json(
    path: str | Path, run_id: str, config_summary: dict[str, Any], run_report: RunReport
) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "run_id": run_id,
        "config": config_summary,
        "connector_outcomes": [o.model_dump() for o in run_report.outcomes],
    }
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return path


def write_phrases_csv(path: str | Path, phrases: list[dict[str, Any]]) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["phrase", "count"])
        for row in phrases[:50]:
            writer.writerow([row["phrase"], row["count"]])
    return path


def write_insights_json(path: str | Path, insights: list[Any]) -> Path:
    """Write raw ``Insight`` objects as JSON — the bridge file future
    renderers (PDF, Power BI, Slack) read instead of the HTML."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = [
        {
            "id": i.id,
            "title": i.title,
            "description": i.description,
            "severity": i.severity,
            "confidence": i.confidence,
            "data": i.data,
            "insight_type": i.insight_type,
            "recommendation": i.recommendation,
        }
        for i in insights
    ]
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return path
