"""Run state, connector state, and checkpointing (Engineering Design §5).

Checkpoints are written after every successful batch, not just at run end.
On restart, each connector resumes from its own last checkpoint rather than
from zero. State is persisted as JSON on disk so a killed process can resume
without losing progress.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from pydantic import BaseModel

NON_KEYWORD_JOB_KEY = "_all"
"""Fixed checkpoint key for connectors whose ``collection_scope`` isn't
``"keyword"`` (Engineering Design §2/§3) — they get exactly one job/checkpoint
per run, not one per configured keyword, since keywords don't apply to how
they collect (e.g. Google Play walks all configured app_ids once)."""


class Checkpoint(BaseModel):
    """Progress marker for one connector's unit of collection work within a run.

    ``search_term`` holds the real keyword for ``collection_scope="keyword"``
    connectors, or ``NON_KEYWORD_JOB_KEY`` for connectors that collect
    everything for a fixed target instead (Google Play app_ids, a YouTube
    channel, etc.) — those get exactly one Checkpoint per run, not one per
    keyword.

    Scoped to a single ``Run`` — cross-run concerns like the auto-disable
    failure streak live in ``ConnectorHealthStore`` instead, since a
    Checkpoint is deliberately reset per execution (that's what makes
    per-run resume correct) and can't also serve as cross-run state.

    ``cursor`` is an opaque, connector-serialized pagination position (e.g.
    Google Play's continuation token, JSON-encoded) — the orchestrator and
    state store never interpret it, only persist and hand it back. Connectors
    with no pagination concept (or that treat one ``search()`` call as one
    atomic batch, Milestone 2's stub) simply leave it ``None``.

    ``cursor_version`` lets a connector recognize (and discard rather than
    misinterpret) a cursor serialized by a previous, incompatible version of
    its own pagination format, without breaking the schema for every other
    connector.
    """

    search_term: str
    last_batch_index: int = -1
    records_written: int = 0
    last_successful_timestamp: datetime | None = None
    cursor: str | None = None
    cursor_version: int = 1
    exhausted: bool = False


class ConnectorState(BaseModel):
    """Per-connector, per-run state: one Checkpoint per keyword being searched."""

    connector_name: str
    checkpoints: dict[str, Checkpoint] = {}

    def checkpoint_for(self, search_term: str) -> Checkpoint:
        return self.checkpoints.setdefault(search_term, Checkpoint(search_term=search_term))


class Run(BaseModel):
    """One execution of the orchestrator (Engineering Design §5)."""

    run_id: str
    started_at: datetime
    keywords: list[str]
    start: datetime
    end: datetime
    connector_states: dict[str, ConnectorState] = {}

    def connector_state_for(self, connector_name: str) -> ConnectorState:
        return self.connector_states.setdefault(
            connector_name, ConnectorState(connector_name=connector_name)
        )


class RunStateStore:
    """Persists ``Run`` state to disk as JSON, one file per run_id.

    This is the mechanism that makes checkpoint/resume possible: writing after
    every successful batch means a killed-and-restarted process can pick a run
    back up from its last on-disk checkpoint instead of re-fetching from zero.
    """

    def __init__(self, state_dir: str | Path) -> None:
        self._state_dir = Path(state_dir)
        self._state_dir.mkdir(parents=True, exist_ok=True)

    def _path_for(self, run_id: str) -> Path:
        return self._state_dir / f"{run_id}.json"

    def save(self, run: Run) -> None:
        path = self._path_for(run.run_id)
        path.write_text(run.model_dump_json(indent=2), encoding="utf-8")

    def load(self, run_id: str) -> Run | None:
        path = self._path_for(run_id)
        if not path.exists():
            return None
        return Run.model_validate_json(path.read_text(encoding="utf-8"))

    def load_or_create(
        self, run_id: str, keywords: list[str], start: datetime, end: datetime
    ) -> Run:
        """Resume an existing run's state, or start a fresh one for a new run_id."""
        existing = self.load(run_id)
        if existing is not None:
            return existing
        run = Run(
            run_id=run_id,
            started_at=datetime.now(start.tzinfo),
            keywords=keywords,
            start=start,
            end=end,
        )
        self.save(run)
        return run
