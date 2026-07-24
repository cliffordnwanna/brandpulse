"""Unit tests for run/connector state and checkpoint persistence (Engineering Design §5)."""

from datetime import UTC, datetime
from pathlib import Path

from brandpulse.orchestration.state import RunStateStore


def test_load_or_create_creates_new_run(tmp_path: Path):
    store = RunStateStore(tmp_path)
    start = datetime(2026, 1, 1, tzinfo=UTC)
    end = datetime(2026, 1, 31, tzinfo=UTC)

    run = store.load_or_create("run-1", ["Wema"], start, end)

    assert run.run_id == "run-1"
    assert run.keywords == ["Wema"]
    assert (tmp_path / "run-1.json").exists()


def test_load_or_create_resumes_existing_run_state(tmp_path: Path):
    store = RunStateStore(tmp_path)
    start = datetime(2026, 1, 1, tzinfo=UTC)
    end = datetime(2026, 1, 31, tzinfo=UTC)

    run = store.load_or_create("run-1", ["Wema"], start, end)
    checkpoint = run.connector_state_for("google_play").checkpoint_for("Wema")
    checkpoint.last_batch_index = 0
    checkpoint.records_written = 42
    store.save(run)

    resumed = store.load_or_create("run-1", ["Wema"], start, end)
    resumed_checkpoint = resumed.connector_state_for("google_play").checkpoint_for("Wema")

    assert resumed_checkpoint.last_batch_index == 0
    assert resumed_checkpoint.records_written == 42


def test_checkpoint_persists_after_every_save_not_just_run_end(tmp_path: Path):
    """Simulates a crash: state saved mid-run must be recoverable without a clean finish."""
    store = RunStateStore(tmp_path)
    start = datetime(2026, 1, 1, tzinfo=UTC)
    end = datetime(2026, 1, 31, tzinfo=UTC)

    run = store.load_or_create("run-1", ["Wema", "ALAT"], start, end)
    run.connector_state_for("google_play").checkpoint_for("Wema").last_batch_index = 0
    store.save(run)
    # "Crash" here — no further save call happens for "ALAT".

    reloaded = RunStateStore(tmp_path).load("run-1")

    assert reloaded is not None
    assert reloaded.connector_state_for("google_play").checkpoint_for("Wema").last_batch_index == 0
    assert reloaded.connector_state_for("google_play").checkpoint_for("ALAT").last_batch_index == -1
