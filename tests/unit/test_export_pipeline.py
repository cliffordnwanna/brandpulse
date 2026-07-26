"""Unit tests for the export pipeline (Milestone 6): Gold export, no HTML/insights."""

import csv
import json
from pathlib import Path

import pytest

from brandpulse.pipeline.export_pipeline import export_gold
from brandpulse.storage.local import LocalFileStorageBackend
from tests.fixtures.seed_silver import seed_silver_record


def test_export_csv_produces_mentions_and_classifications(tmp_path: Path):
    backend = LocalFileStorageBackend(tmp_path / "storage")
    seed_silver_record(backend, "m1", "great app")
    backend.write(
        "gold",
        "m1_5a-v1",
        {
            "mention_id": "m1",
            "classifier_version": "5a-v1",
            "sentiment": {"label": "Positive", "confidence": 0.9, "reason": "r"},
            "complaint_category": {"label": "General Feedback", "confidence": 0.5, "reason": "r"},
        },
    )

    paths = export_gold(backend, tmp_path / "output", "run-1", fmt="csv")

    assert len(paths) == 2
    for path in paths:
        assert path.exists()

    mentions_path = next(p for p in paths if "mentions" in p.name)
    with mentions_path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert rows[0]["mention_id"] == "m1"


def test_export_json_produces_single_file_with_silver_and_gold(tmp_path: Path):
    backend = LocalFileStorageBackend(tmp_path / "storage")
    seed_silver_record(backend, "m1", "great app")
    backend.write(
        "gold",
        "m1_5a-v1",
        {
            "mention_id": "m1",
            "classifier_version": "5a-v1",
            "sentiment": {"label": "Positive", "confidence": 0.9, "reason": "r"},
            "complaint_category": {"label": "General Feedback", "confidence": 0.5, "reason": "r"},
        },
    )

    paths = export_gold(backend, tmp_path / "output", "run-1", fmt="json")

    assert len(paths) == 1
    data = json.loads(paths[0].read_text(encoding="utf-8"))
    assert len(data["silver"]) == 1
    assert len(data["gold"]) == 1


def test_export_uses_latest_gold_version_only(tmp_path: Path):
    backend = LocalFileStorageBackend(tmp_path / "storage")
    seed_silver_record(backend, "m1", "great app")
    backend.write(
        "gold",
        "m1_5a-v1",
        {"mention_id": "m1", "classifier_version": "5a-v1", "sentiment": {"label": "Positive"}},
    )
    backend.write(
        "gold",
        "m1_5a-v2",
        {"mention_id": "m1", "classifier_version": "5a-v2", "sentiment": {"label": "Negative"}},
    )

    paths = export_gold(backend, tmp_path / "output", "run-1", fmt="json")
    data = json.loads(paths[0].read_text(encoding="utf-8"))

    assert len(data["gold"]) == 1
    assert data["gold"][0]["classifier_version"] == "5a-v2"


def test_export_unsupported_format_raises(tmp_path: Path):
    backend = LocalFileStorageBackend(tmp_path / "storage")
    with pytest.raises(ValueError, match="xml"):
        export_gold(backend, tmp_path / "output", "run-1", fmt="xml")
