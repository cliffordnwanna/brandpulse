"""A scripted fake LLMClient for tests — never makes a real network call."""

from __future__ import annotations


class FakeLLMClient:
    """Returns a fixed completion (or one popped from a queue) for every call."""

    model_name = "fake"

    def __init__(self, completions: list[tuple[str, int]] | None = None) -> None:
        self._completions = list(completions) if completions else None
        self.prompts_seen: list[str] = []

    def complete(self, prompt: str) -> tuple[str, int]:
        self.prompts_seen.append(prompt)
        if self._completions:
            return self._completions.pop(0)
        return "Label: Neutral\nConfidence: 0.6\nReason: fake response.", 10
