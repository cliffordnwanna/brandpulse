"""Config loader — reads ``config.yaml`` and validates it against the config schema."""

from __future__ import annotations

from pathlib import Path

import yaml

from brandpulse.config.models import Config


def load_config(path: str | Path) -> Config:
    """Load and validate a config YAML file into a ``Config`` object.

    Raises ``pydantic.ValidationError`` if the file doesn't match the schema,
    and ``FileNotFoundError`` if the path doesn't exist.
    """
    path = Path(path)
    with path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    return Config.model_validate(raw)
