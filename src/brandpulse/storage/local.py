"""Local file storage backend (Milestone 4) — the only concrete backend for MVP.

One JSON file per record, at ``{root}/{tier}/{mention_id}.json``. Writes are
idempotent (an existing file is left untouched, never overwritten) and
Bronze is append-only at this level: ``delete()``/``clear()`` raise
``OperationNotPermittedError`` for ``tier="bronze"`` rather than relying on
callers to simply not call them.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from brandpulse.storage.base import (
    OperationNotPermittedError,
    StorageBackend,
    Tier,
    assert_silver_write_allowed,
)


class LocalFileStorageBackend(StorageBackend):
    """Writes each tier's records as JSON files under a local root directory."""

    def __init__(self, root: str | Path) -> None:
        self._root = Path(root)
        for tier in ("bronze", "silver", "gold"):
            (self._root / tier).mkdir(parents=True, exist_ok=True)

    def _path_for(self, tier: Tier, mention_id: str) -> Path:
        return self._root / tier / f"{mention_id}.json"

    def write(self, tier: Tier, mention_id: str, record: dict[str, Any]) -> None:
        if tier == "silver":
            assert_silver_write_allowed()
        path = self._path_for(tier, mention_id)
        if path.exists():
            return
        path.write_text(json.dumps(record, default=str), encoding="utf-8")

    def exists(self, tier: Tier, mention_id: str) -> bool:
        return self._path_for(tier, mention_id).exists()

    def read_all(self, tier: Tier) -> Iterable[dict[str, Any]]:
        tier_dir = self._root / tier
        for path in sorted(tier_dir.glob("*.json")):
            yield json.loads(path.read_text(encoding="utf-8"))

    def delete(self, tier: Tier, mention_id: str) -> None:
        if tier == "bronze":
            raise OperationNotPermittedError("Bronze is append-only — records cannot be deleted.")
        path = self._path_for(tier, mention_id)
        path.unlink(missing_ok=True)

    def clear(self, tier: Tier) -> None:
        if tier == "bronze":
            raise OperationNotPermittedError("Bronze is append-only — the tier cannot be cleared.")
        tier_dir = self._root / tier
        for path in tier_dir.glob("*.json"):
            path.unlink()
