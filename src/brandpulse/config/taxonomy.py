"""Taxonomy loader (Milestone 6, reviewer feedback).

The complaint category list and competitor list are configuration, not code
— ``config/taxonomy.yaml`` is the sole source for both, read by the
classification pipeline (5a's ``KeywordComplaintClassifier``) and the
InsightEngine (competitor-mention insight). Never hardcode either list in
Python; a different organization retargets BrandPulse by editing this file.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel

DEFAULT_TAXONOMY_PATH = "config/taxonomy.yaml"


class Taxonomy(BaseModel):
    complaint_categories: tuple[str, ...]
    competitors: tuple[str, ...]


def load_taxonomy(path: str | Path = DEFAULT_TAXONOMY_PATH) -> Taxonomy:
    """Load and validate ``taxonomy.yaml``.

    Raises ``FileNotFoundError`` if the path doesn't exist — there is no
    hardcoded Python fallback, per the "never hardcode source lists"
    architecture invariant.
    """
    path = Path(path)
    with path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    return Taxonomy.model_validate(raw)
