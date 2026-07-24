"""Cross-run connector health tracking (Engineering Design §6).

``consecutive_failures`` for the auto-disable rule ("3 consecutive scheduled
runs") must survive across separate ``Run`` objects/run_ids — it is a
genuinely distinct concern from per-run ``Checkpoint`` state (which is
deliberately scoped to one execution so it can be resumed) and from
``SourceRegistry`` (which must stay fully reconstructable from ``config.yaml``
alone — the moment it holds mutable cross-run state that isn't in config,
rebuilding the registry would silently lose it).

``ConnectorHealthStore`` is an abstract interface so the persistence backend
(flat JSON now, SQLite/Fabric-native later) can change without touching the
orchestrator or Source Registry.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from pathlib import Path

from pydantic import BaseModel


class ConnectorHealth(BaseModel):
    """Cross-run health record for one connector."""

    connector_name: str
    consecutive_failures: int = 0


class ConnectorHealthStore(ABC):
    """Persists per-connector failure streaks across scheduled runs."""

    @abstractmethod
    def get(self, connector_name: str) -> ConnectorHealth:
        """Return the current health record for a connector (default if unseen)."""
        raise NotImplementedError

    @abstractmethod
    def record_result(self, connector_name: str, failed: bool) -> ConnectorHealth:
        """Record one scheduled run's outcome for a connector.

        Increments ``consecutive_failures`` on ``failed=True``, resets to 0
        otherwise. Returns the updated record.
        """
        raise NotImplementedError

    @abstractmethod
    def reset(self, connector_name: str) -> None:
        """Reset a connector's failure streak to zero (e.g. after manual re-enable)."""
        raise NotImplementedError


class JSONConnectorHealthStore(ConnectorHealthStore):
    """Flat-JSON-backed ``ConnectorHealthStore`` — the MVP/local implementation."""

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        if not self._path.exists():
            self._write({})

    def _read(self) -> dict[str, ConnectorHealth]:
        raw = json.loads(self._path.read_text(encoding="utf-8"))
        return {name: ConnectorHealth.model_validate(record) for name, record in raw.items()}

    def _write(self, records: dict[str, ConnectorHealth]) -> None:
        raw = {name: record.model_dump() for name, record in records.items()}
        self._path.write_text(json.dumps(raw, indent=2, default=str), encoding="utf-8")

    def get(self, connector_name: str) -> ConnectorHealth:
        records = self._read()
        return records.get(connector_name, ConnectorHealth(connector_name=connector_name))

    def record_result(self, connector_name: str, failed: bool) -> ConnectorHealth:
        records = self._read()
        record = records.get(connector_name, ConnectorHealth(connector_name=connector_name))
        record.consecutive_failures = record.consecutive_failures + 1 if failed else 0
        records[connector_name] = record
        self._write(records)
        return record

    def reset(self, connector_name: str) -> None:
        records = self._read()
        records[connector_name] = ConnectorHealth(connector_name=connector_name)
        self._write(records)
