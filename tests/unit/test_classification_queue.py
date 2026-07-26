"""Unit tests for the Classification Queue (Milestone 5, Engineering Design §10)."""

import threading

from brandpulse.pipeline.classification_queue import ClassificationQueue


def test_all_records_are_processed_exactly_once():
    queue_ = ClassificationQueue()
    queue_.put_all([{"id": i} for i in range(20)])

    processed: list[int] = []
    lock = threading.Lock()

    def process(record):
        with lock:
            processed.append(record["id"])

    queue_.drain_with_workers(process, num_workers=4)

    assert sorted(processed) == list(range(20))


def test_empty_queue_drains_immediately():
    queue_ = ClassificationQueue()
    calls = []
    queue_.drain_with_workers(lambda r: calls.append(r), num_workers=2)
    assert calls == []


def test_single_worker_processes_in_fifo_order():
    queue_ = ClassificationQueue()
    queue_.put_all([{"id": i} for i in range(5)])

    processed: list[int] = []
    queue_.drain_with_workers(lambda r: processed.append(r["id"]), num_workers=1)

    assert processed == [0, 1, 2, 3, 4]
