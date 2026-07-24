"""Unit tests for the config loader (Engineering Design §8)."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from brandpulse.config.loader import load_config

VALID_CONFIG = """
sources:
  - name: google_play
    enabled: true
    reliability: high
  - name: nairaland
    enabled: false
    reliability: medium

keywords:
  base_list: ["Wema", "ALAT"]

output:
  directory: "./output/"
  formats: ["csv", "json"]

retry:
  max_attempts: 3
  backoff_seconds: [5, 30, 120]

timeouts:
  request_seconds: 20

rate_limit:
  requests_per_minute: 60
  respect_robots_txt: true
"""

INVALID_CONFIG_BAD_RELIABILITY = """
sources:
  - name: google_play
    enabled: true
    reliability: extreme

keywords:
  base_list: ["Wema"]

output:
  directory: "./output/"
  formats: ["csv"]

retry:
  max_attempts: 3
  backoff_seconds: [5]

timeouts:
  request_seconds: 20

rate_limit:
  requests_per_minute: 60
  respect_robots_txt: true
"""

INVALID_CONFIG_MISSING_SECTION = """
sources:
  - name: google_play
    enabled: true
    reliability: high

keywords:
  base_list: ["Wema"]
"""


def test_load_valid_config(tmp_path: Path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(VALID_CONFIG, encoding="utf-8")

    config = load_config(config_path)

    assert len(config.sources) == 2
    assert config.sources[0].name == "google_play"
    assert config.keywords.base_list == ["Wema", "ALAT"]
    assert config.rate_limit.requests_per_minute == 60


def test_load_config_rejects_invalid_reliability(tmp_path: Path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(INVALID_CONFIG_BAD_RELIABILITY, encoding="utf-8")

    with pytest.raises(ValidationError):
        load_config(config_path)


def test_load_config_rejects_missing_section(tmp_path: Path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(INVALID_CONFIG_MISSING_SECTION, encoding="utf-8")

    with pytest.raises(ValidationError):
        load_config(config_path)


def test_load_config_missing_file_raises(tmp_path: Path):
    missing_path = tmp_path / "does_not_exist.yaml"
    with pytest.raises(FileNotFoundError):
        load_config(missing_path)


def test_repo_config_yaml_loads_correctly():
    repo_config = Path(__file__).parents[2] / "config" / "config.yaml"
    config = load_config(repo_config)
    names = {source.name for source in config.sources}
    assert names == {"google_play", "app_store", "nairaland", "youtube"}
