"""Classification Queue (Engineering Design §10).

Silver output lands here rather than being classified inline during
ingestion, so a slow classification stage (or an LLM call in 5b) never
blocks connectors from continuing to collect. For MVP this is a simple
in-process ``queue.Queue`` with worker threads pulling independently — same
interface Phase 2's Fabric-native scheduling would sit behind, per §10.
"""

from __future__ import annotations

import queue
import threading
from collections.abc import Callable, Iterable
from typing import Any

_SENTINEL = object()


class ClassificationQueue:
    """A bounded, thread-drained queue of Silver records awaiting classification."""

    def __init__(self, maxsize: int = 0) -> None:
        self._queue: queue.Queue[Any] = queue.Queue(maxsize=maxsize)

    def put(self, record: dict[str, Any]) -> None:
        self._queue.put(record)

    def put_all(self, records: Iterable[dict[str, Any]]) -> None:
        for record in records:
            self.put(record)

    def drain_with_workers(
        self,
        process_fn: Callable[[dict[str, Any]], None],
        num_workers: int = 4,
    ) -> None:
        """Run ``num_workers`` threads pulling records until the queue is empty,
        then return once every enqueued record has been processed.

        A per-worker sentinel is used to signal shutdown rather than relying
        on ``Queue.empty()`` (which races under concurrent consumers).
        """
        for _ in range(num_workers):
            self._queue.put(_SENTINEL)

        def _worker() -> None:
            while True:
                item = self._queue.get()
                try:
                    if item is _SENTINEL:
                        return
                    process_fn(item)
                finally:
                    self._queue.task_done()

        threads = [threading.Thread(target=_worker) for _ in range(num_workers)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

    def qsize(self) -> int:
        return self._queue.qsize()
