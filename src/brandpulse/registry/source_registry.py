"""Source Registry (Engineering Design §4).

Owns everything about *which* sources exist and *how* they should run —
backed by the ``sources:`` block in config.yaml plus (in later milestones)
live health data from each connector's ``health()`` call.

Milestone 1 scope: skeleton only. ``schedule()`` and ``health_status()`` are
stubs — real scheduling and live health checks land with the orchestrator
(Milestone 2) and real connectors (Milestone 3+).

Milestone 2 adds ``disable()``: a connector that fails 3 consecutive
scheduled runs is auto-disabled here (Engineering Design §6), which is why
``enabled_sources()`` must reflect live mutable state, not just the original
config snapshot.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from brandpulse.config.models import Config, SourceConfig
from brandpulse.connectors.base import HealthStatus


class Schedule(BaseModel):
    """Placeholder schedule type — real scheduling logic lands in Milestone 2."""

    cron: str | None = None


class SourceRegistry:
    """Reads the ``sources:`` block from config and exposes source metadata."""

    def __init__(self, config: Config) -> None:
        self._config = config
        self._sources_by_name = {source.name: source for source in config.sources}

    def enabled_sources(self) -> list[SourceConfig]:
        """Return the configured sources with ``enabled: true``."""
        return [source for source in self._config.sources if source.enabled]

    def priority(self, source_name: str) -> int:
        """Return the run priority for a source.

        Milestone 1 stub: priority is derived from declaration order in
        config.yaml (earlier = higher priority) until real prioritization
        logic is defined.
        """
        names = [source.name for source in self._config.sources]
        return names.index(source_name)

    def schedule(self, source_name: str) -> Schedule:
        """Return the run schedule for a source. Stub for Milestone 1."""
        self._require_known(source_name)
        return Schedule()

    def health_status(self, source_name: str) -> HealthStatus:
        """Return the last-known health status for a source. Stub for Milestone 1."""
        self._require_known(source_name)
        return HealthStatus(healthy=True, reason=None, checked_at=None)

    def reliability(self, source_name: str) -> Literal["high", "medium", "low"]:
        """Return the configured reliability rating for a source."""
        return self._require_known(source_name).reliability

    def disable(self, source_name: str) -> None:
        """Mark a source disabled — e.g. after it fails 3 consecutive runs (§6).

        Mutates the registry's live view of the source; ``enabled_sources()``
        reflects this immediately. Does not write back to config.yaml.
        """
        source = self._require_known(source_name)
        source.enabled = False

    def is_enabled(self, source_name: str) -> bool:
        """Return whether a source is currently enabled (live, post-``disable()``)."""
        return self._require_known(source_name).enabled

    def _require_known(self, source_name: str) -> SourceConfig:
        try:
            return self._sources_by_name[source_name]
        except KeyError:
            raise KeyError(f"Unknown source: {source_name!r}") from None
