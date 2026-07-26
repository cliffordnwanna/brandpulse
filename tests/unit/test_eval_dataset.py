"""Unit tests for the synthetic labeled evaluation set generator (Milestone 5, §15)."""

from pathlib import Path

from brandpulse.pipeline.eval_dataset import (
    CLASSES,
    generate_labeled_set,
    load_labeled_set,
    write_labeled_set,
)


def test_generate_labeled_set_produces_n_per_class():
    rows = generate_labeled_set(n_per_class=10, seed=1)
    assert len(rows) == 10 * len(CLASSES)
    counts = {}
    for row in rows:
        counts[row["label"]] = counts.get(row["label"], 0) + 1
    for label in CLASSES:
        assert counts[label] == 10


def test_generated_rows_are_marked_synthetic():
    rows = generate_labeled_set(n_per_class=5, seed=1)
    assert all(row["synthetic"] == "true" for row in rows)


def test_generated_rows_have_unique_mention_ids():
    rows = generate_labeled_set(n_per_class=20, seed=1)
    ids = [row["mention_id"] for row in rows]
    assert len(ids) == len(set(ids))


def test_generation_is_deterministic_given_seed():
    rows_a = generate_labeled_set(n_per_class=10, seed=7)
    rows_b = generate_labeled_set(n_per_class=10, seed=7)
    assert rows_a == rows_b


def test_write_and_load_roundtrip(tmp_path: Path):
    rows = generate_labeled_set(n_per_class=5, seed=1)
    path = tmp_path / "labeled.csv"
    write_labeled_set(path, rows)

    loaded = load_labeled_set(path)
    assert len(loaded) == len(rows)
    assert {r["label"] for r in loaded} == set(CLASSES)


def test_committed_labeled_v1_csv_has_500_rows():
    """The actual eval/labeled_v1.csv shipped in the repo — 100 per class x 5 classes."""
    repo_root = Path(__file__).resolve().parents[2]
    rows = load_labeled_set(repo_root / "eval" / "labeled_v1.csv")
    assert len(rows) == 500
    assert all(row["synthetic"] == "true" for row in rows)
