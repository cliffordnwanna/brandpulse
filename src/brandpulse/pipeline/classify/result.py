"""Shared classification stage result shape (Engineering Design §10).

Every classification stage — sentiment, complaint category, emotion, intent,
urgency, competitor mention — returns exactly this shape. No stage returns a
bare label; ``confidence`` and ``reason`` are mandatory so every Gold field is
auditable, never a black-box guess.
"""

from __future__ import annotations

from pydantic import BaseModel


class StageResult(BaseModel):
    """One classification stage's output: label + confidence + reason."""

    label: str
    confidence: float
    reason: str
