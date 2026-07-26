"""Unit tests for taxonomy loading (Milestone 6, reviewer feedback)."""

from pathlib import Path

import pytest
import yaml

from brandpulse.config.taxonomy import load_taxonomy


def test_load_real_taxonomy_yaml():
    taxonomy = load_taxonomy("config/taxonomy.yaml")
    assert "Transfers" in taxonomy.complaint_categories
    assert "Fraud" in taxonomy.complaint_categories
    assert "Opay" in taxonomy.competitors
    assert "GTBank" in taxonomy.competitors


def test_load_taxonomy_from_custom_path(tmp_path: Path):
    custom = {
        "complaint_categories": ["Transfers", "Fraud"],
        "competitors": ["GTBank"],
    }
    path = tmp_path / "custom_taxonomy.yaml"
    path.write_text(yaml.dump(custom), encoding="utf-8")

    taxonomy = load_taxonomy(path)

    assert taxonomy.complaint_categories == ("Transfers", "Fraud")
    assert taxonomy.competitors == ("GTBank",)


def test_load_taxonomy_missing_file_raises():
    with pytest.raises(FileNotFoundError):
        load_taxonomy("does/not/exist.yaml")
