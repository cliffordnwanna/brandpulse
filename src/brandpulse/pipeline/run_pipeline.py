"""The ``snapshot``/``incremental`` CLI commands' implementation (Milestone 6).

Ties together everything built in Milestones 1-6: discover connectors,
drive the orchestrator (scrape -> Bronze -> Silver), classify (Silver ->
Gold), then generate the report (Gold -> HTML + bridge files).

Two modes, both always scrape into the same append-only Bronze store — the
difference is entirely in *checkpointing and report scope*, never in
Bronze's write behavior:

- **snapshot** (default): a fresh run_id and a fresh ``Run``/checkpoint
  lineage every invocation — this run starts pagination from scratch for
  its ``--window``, and the resulting session log/report cover only the
  mention_ids this specific invocation collected (via ``RunReport.mention_ids``,
  see ``orchestration/run_report.py``), not the full historical Gold store.
  This is what executives actually want from "run the report": today's
  snapshot, not everything ever collected merged together.
- **incremental**: the original Milestone 2 checkpoint-based behavior — a
  stable, date-keyed run_id that resumes from its own prior checkpoints
  across invocations, and a session log/report scoped to everything
  currently classified (cumulative), for building a historical archive.
"""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from brandpulse.config.models import Config
from brandpulse.connectors import discover_connectors
from brandpulse.connectors.app_store import AppStoreConnector
from brandpulse.connectors.base import BaseConnector
from brandpulse.connectors.google_play import GooglePlayConnector
from brandpulse.connectors.nairaland import NairalandConnector
from brandpulse.connectors.youtube import YouTubeConnector
from brandpulse.orchestration.connector_health import JSONConnectorHealthStore
from brandpulse.orchestration.orchestrator import Orchestrator
from brandpulse.orchestration.run_report import RunReport
from brandpulse.orchestration.state import RunStateStore
from brandpulse.pipeline.output_writers import (
    write_classifications_csv,
    write_connector_health_csv,
    write_errors_csv,
    write_mentions_csv,
    write_run_metadata_json,
    write_summary_csv,
)
from brandpulse.pipeline.report_pipeline import generate_report, latest_gold_records
from brandpulse.pipeline.run_classification import run_classification
from brandpulse.registry.source_registry import SourceRegistry
from brandpulse.storage.base import StorageBackend

DEFAULT_WINDOW = "7d"
_WINDOW_RE = re.compile(r"^(\d+)([dh])$")


class InvalidWindowError(Exception):
    """Raised when ``--window`` doesn't parse as ``<int>d`` or ``<int>h``."""


def parse_window(window: str) -> timedelta:
    match = _WINDOW_RE.match(window.strip())
    if not match:
        raise InvalidWindowError(
            f"Invalid --window value: {window!r}. Expected a number followed by 'd' or 'h', "
            "e.g. '7d', '1d', '90d', '12h'."
        )
    amount, unit = int(match.group(1)), match.group(2)
    return timedelta(days=amount) if unit == "d" else timedelta(hours=amount)


def _build_connectors(
    config: Config, health_store: JSONConnectorHealthStore
) -> dict[str, BaseConnector]:
    """Instantiate every enabled, known connector.

    ``discover_connectors`` finds every ``BaseConnector`` subclass under
    ``connectors/`` with zero manual registration (Engineering Design §3),
    but each concrete connector still needs its own config-specific
    constructor args — this is the one place that maps discovered classes
    to their actual instances. Four connectors exist as of Milestone 7:
    Google Play, App Store, Nairaland, YouTube.
    """
    discovered = discover_connectors()
    connectors: dict[str, BaseConnector] = {}

    if "google_play" in discovered and config.connectors.google_play is not None:
        connectors["google_play"] = GooglePlayConnector(
            config.connectors.google_play, config.rate_limit, health_store
        )

    if "app_store" in discovered and config.connectors.app_store is not None:
        connectors["app_store"] = AppStoreConnector(
            config.connectors.app_store, config.rate_limit, health_store
        )

    if "nairaland" in discovered and config.connectors.nairaland is not None:
        connectors["nairaland"] = NairalandConnector(
            config.connectors.nairaland, config.rate_limit, health_store
        )

    if "youtube" in discovered and config.connectors.youtube is not None:
        connectors["youtube"] = YouTubeConnector(
            config.connectors.youtube, config.rate_limit, health_store
        )

    return connectors


def _run_common(
    backend: StorageBackend,
    config: Config,
    state_store: RunStateStore,
    health_store: JSONConnectorHealthStore,
    run_id: str,
    start: datetime,
    end: datetime,
) -> tuple[dict[str, Any], RunReport]:
    registry = SourceRegistry(config)
    connectors = _build_connectors(config, health_store)
    run_report = RunReport()

    run = state_store.load_or_create(run_id, config.keywords.base_list, start, end)
    orchestrator = Orchestrator(
        registry,
        state_store,
        config.retry,
        connectors,
        health_store,
        backend,
        run_report=run_report,
    )
    orchestrator.run(run)
    return {"run_id": run_id}, run_report


def _write_operational_outputs(
    backend: StorageBackend, config: Config, run_id: str, run_report: RunReport, session_summary: dict[str, Any]
) -> None:
    """Write the operational/debugging output set (Engineering Design §14):
    ``mentions.csv``, ``classifications.csv``, ``summary.csv``, ``errors.csv``,
    ``connector_health.csv``, ``run_metadata.json``. Distinct from the
    ``output/reports/`` bundle (``generate_report``) — this is the flat,
    always-produced CSV/JSON set every run leaves behind for debugging,
    regardless of whether the report itself renders anything interesting.
    """
    output_dir = Path(config.output.directory)
    silver_records = list(backend.read_all("silver"))
    gold_records = latest_gold_records(backend)

    write_mentions_csv(output_dir / "mentions.csv", silver_records, run_id)
    write_classifications_csv(output_dir / "classifications.csv", gold_records, run_id)
    write_summary_csv(output_dir / "summary.csv", session_summary)
    write_errors_csv(output_dir / "errors.csv", run_report)
    write_connector_health_csv(output_dir / "connector_health.csv", run_report)
    write_run_metadata_json(
        output_dir / "run_metadata.json",
        run_id,
        config.model_dump(mode="json"),
        run_report,
    )


def run_snapshot(
    backend: StorageBackend,
    config: Config,
    state_store: RunStateStore,
    health_store: JSONConnectorHealthStore,
    window: str = DEFAULT_WINDOW,
) -> dict[str, Any]:
    """A fresh run_id/checkpoint lineage, scraping only ``--window`` back from
    now, with the session log/report scoped to just this invocation's
    mention_ids — never merged with prior snapshots' data."""
    run_id = f"snapshot-{uuid.uuid4().hex}"
    end = datetime.now(UTC)
    start = end - parse_window(window)

    _, run_report = _run_common(backend, config, state_store, health_store, run_id, start, end)

    session_summary = run_classification(
        backend, config, run_id=run_id, session_mention_ids=run_report.mention_ids
    )
    report_result = generate_report(backend, config, run_id)
    _write_operational_outputs(backend, config, run_id, run_report, session_summary)

    return {
        "run_id": run_id,
        "mode": "snapshot",
        "window": window,
        "connector_outcomes": [o.model_dump() for o in run_report.outcomes],
        "session_summary": session_summary,
        "report": report_result,
    }


def run_incremental(
    backend: StorageBackend,
    config: Config,
    state_store: RunStateStore,
    health_store: JSONConnectorHealthStore,
    lookback_days: int = 30,
) -> dict[str, Any]:
    """A stable, date-keyed run_id resuming from its own checkpoints across
    invocations, with the session log/report scoped to everything currently
    classified (cumulative) — for building a historical archive."""
    run_id = datetime.now(UTC).strftime("incremental-%Y%m%d")
    end = datetime.now(UTC)
    start = end - timedelta(days=lookback_days)

    _, run_report = _run_common(backend, config, state_store, health_store, run_id, start, end)

    session_summary = run_classification(backend, config, run_id=run_id)
    report_result = generate_report(backend, config, run_id)
    _write_operational_outputs(backend, config, run_id, run_report, session_summary)

    return {
        "run_id": run_id,
        "mode": "incremental",
        "connector_outcomes": [o.model_dump() for o in run_report.outcomes],
        "session_summary": session_summary,
        "report": report_result,
    }
