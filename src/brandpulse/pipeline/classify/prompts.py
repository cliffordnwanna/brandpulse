"""Prompt loading (Engineering Design §16) — every LLM prompt is a versioned
file under ``prompts/``, never a hardcoded string in pipeline code.
"""

from __future__ import annotations

from pathlib import Path

_PROMPTS_DIR = Path(__file__).resolve().parents[3].parent / "prompts"


def load_prompt(name: str, version: str) -> str:
    """Load ``prompts/{name}_{version}.txt`` and return its raw template text."""
    path = _PROMPTS_DIR / f"{name}_{version}.txt"
    return path.read_text(encoding="utf-8")


def render_prompt(name: str, version: str, **fields: str) -> str:
    """Load and ``.format(**fields)`` the named prompt template."""
    return load_prompt(name, version).format(**fields)
