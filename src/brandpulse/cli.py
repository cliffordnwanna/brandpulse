"""CLI entry point (Engineering Design §19).

Milestone 4 added ``rebuild-silver``: wipes and reprocesses the entire
Silver tier from Bronze, proving Silver is always derivable from Bronze
alone. Milestone 5 added ``classify`` (runs the classification pipeline over
every Silver record, writing Gold + a session log) and ``evaluate`` (runs
the 5a sentiment stage against the labeled eval set, writing
``output/metrics.csv``). Milestone 6 adds ``snapshot``/``incremental``/
``report``/``compare``/``export`` — see each command's docstring below. The
separation rule: ``snapshot``/``incremental`` stop at Gold; ``report`` reads
Gold and produces output; they work independently.
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import sys
from pathlib import Path

from brandpulse.config.loader import load_config
from brandpulse.orchestration.connector_health import JSONConnectorHealthStore
from brandpulse.orchestration.state import RunStateStore
from brandpulse.pipeline.eval_dataset import load_labeled_set
from brandpulse.pipeline.export_pipeline import export_gold
from brandpulse.pipeline.report_pipeline import generate_drift_report, generate_report
from brandpulse.pipeline.run_classification import run_classification
from brandpulse.pipeline.run_pipeline import DEFAULT_WINDOW, run_incremental, run_snapshot
from brandpulse.pipeline.silver import rebuild_silver_from_bronze
from brandpulse.storage.factory import StorageBackendFactory

DEFAULT_CONFIG_PATH = "config/config.yaml"
DEFAULT_LABELED_SET_PATH = "eval/labeled_v1.csv"
DEFAULT_STATE_DIR = "./state"
DEFAULT_HEALTH_PATH = "./state/connector_health.json"

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_env_file() -> None:
    """Load environment variables from .env file if it exists (for local
    development — credentials like YOUTUBE_API_KEY, AZURE_OPENAI_API_KEY, etc.
    are stored here and loaded on CLI startup)."""
    env_file = _REPO_ROOT / ".env"
    if env_file.exists():
        with env_file.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, value = line.split("=", 1)
                    key = key.strip()
                    value = value.strip().strip('"\'')
                    if key and not os.getenv(key):  # only set if not already in env
                        os.environ[key] = value


def _rebuild_silver(config_path: str) -> int:
    config = load_config(Path(config_path))
    backend = StorageBackendFactory.from_config(config.storage)
    written = rebuild_silver_from_bronze(backend)
    print(f"Rebuilt Silver from Bronze: {written} record(s) written.")
    return 0


def _classify(config_path: str) -> int:
    config = load_config(Path(config_path))
    backend = StorageBackendFactory.from_config(config.storage)
    session_summary = run_classification(backend, config)
    total = sum(session_summary["mention_counts_per_source"].values())
    print(f"Classified {total} record(s). Session log: run_id={session_summary['run_id']}")
    return 0


def _load_evaluate_module():
    """``eval/evaluate.py`` lives outside ``src/brandpulse`` (it's a project
    script, not part of the installable package) so it's loaded by path
    rather than a normal package import."""
    spec = importlib.util.spec_from_file_location(
        "brandpulse_eval", _REPO_ROOT / "eval" / "evaluate.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _evaluate(config_path: str, labeled_set_path: str) -> int:
    from brandpulse.pipeline.classify.model_factory import sentiment_model_from_config

    config = load_config(Path(config_path))
    sentiment_model = sentiment_model_from_config(config.classification.sentiment_model)

    evaluate_module = _load_evaluate_module()
    rows = load_labeled_set(labeled_set_path)
    metrics = evaluate_module.run_evaluation(rows, sentiment_model)

    output_path = Path(config.output.directory) / "metrics.csv"
    evaluate_module.write_metrics_csv(output_path, metrics)

    print(f"Evaluated {len(rows)} labeled example(s). Accuracy: {metrics['accuracy']}")
    print(f"Metrics written to {output_path}")
    return 0


def _snapshot(config_path: str, window: str) -> int:
    """``snapshot`` (default mode): scrape the last ``--window`` -> classify
    -> report scoped to just this run's mention_ids. A fresh run_id and
    checkpoint lineage every invocation — this is what "run the report"
    means for the common case of "give me today's picture," not a merge
    with everything ever collected."""
    config = load_config(Path(config_path))
    backend = StorageBackendFactory.from_config(config.storage)
    state_store = RunStateStore(DEFAULT_STATE_DIR)
    health_store = JSONConnectorHealthStore(DEFAULT_HEALTH_PATH)

    result = run_snapshot(backend, config, state_store, health_store, window=window)

    print(f"Snapshot complete: run_id={result['run_id']} (window={window})")
    print(f"Report: {result['report']['html_path']}")
    return 0


def _incremental(config_path: str) -> int:
    """``incremental``: the original checkpoint-based behavior — a stable,
    date-keyed run_id that resumes across invocations, building a
    historical archive. Session/report scope is cumulative."""
    config = load_config(Path(config_path))
    backend = StorageBackendFactory.from_config(config.storage)
    state_store = RunStateStore(DEFAULT_STATE_DIR)
    health_store = JSONConnectorHealthStore(DEFAULT_HEALTH_PATH)

    result = run_incremental(backend, config, state_store, health_store)

    print(f"Incremental run complete: run_id={result['run_id']}")
    print(f"Report: {result['report']['html_path']}")
    return 0


def _resolve_run_id(config_path: str, run_id: str) -> str:
    """``--run-id latest`` resolves to the most recently written session log."""
    if run_id != "latest":
        return run_id
    config = load_config(Path(config_path))
    sessions_dir = Path(config.output.directory) / "sessions"
    session_files = sorted(sessions_dir.glob("*.json"), key=lambda p: p.stat().st_mtime)
    if not session_files:
        raise FileNotFoundError(f"No session logs found under {sessions_dir} to resolve 'latest'.")
    return session_files[-1].stem


def _report(config_path: str, run_id: str) -> int:
    """``report``: read existing Gold/session data for ``run_id`` and produce
    the output/reports/ bundle. Never scrapes, never classifies."""
    config = load_config(Path(config_path))
    backend = StorageBackendFactory.from_config(config.storage)
    resolved_run_id = _resolve_run_id(config_path, run_id)

    result = generate_report(backend, config, resolved_run_id)
    print(f"Report generated for run_id={resolved_run_id}: {result['html_path']}")
    return 0


def _compare(config_path: str, run_id: str) -> int:
    """``compare``: drift between ``run_id`` and the previous session."""
    config = load_config(Path(config_path))
    resolved_run_id = _resolve_run_id(config_path, run_id)
    insight = generate_drift_report(config, resolved_run_id)

    print(insight.title)
    print(insight.description)
    if insight.data:
        for label, delta in insight.data.get("sentiment_pct_deltas", {}).items():
            print(f"  {label}: {delta:+}pp")
    return 0


def _export(config_path: str, run_id: str, fmt: str) -> int:
    """``export --format csv|json``: Gold export only, no HTML/insights."""
    config = load_config(Path(config_path))
    backend = StorageBackendFactory.from_config(config.storage)
    resolved_run_id = _resolve_run_id(config_path, run_id)

    paths = export_gold(backend, config.output.directory, resolved_run_id, fmt=fmt)
    for path in paths:
        print(f"Exported: {path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    _load_env_file()  # Load .env credentials before parsing args
    
    parser = argparse.ArgumentParser(prog="brandpulse")
    parser.add_argument(
        "--config", default=DEFAULT_CONFIG_PATH, help="Path to config.yaml (default: %(default)s)"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    snapshot_parser = subparsers.add_parser(
        "snapshot", help="Default mode: scrape --window + classify + report scoped to this run."
    )
    snapshot_parser.add_argument(
        "--window",
        default=DEFAULT_WINDOW,
        help="Lookback window, e.g. '7d', '1d', '90d', '12h' (default: %(default)s)",
    )

    subparsers.add_parser(
        "incremental", help="Checkpoint-based scrape + classify + report, cumulative archive."
    )

    subparsers.add_parser(
        "classify", help="Run the classification pipeline over every Silver record."
    )

    report_parser = subparsers.add_parser(
        "report", help="Generate a report from existing Gold data, no scraping/classifying."
    )
    report_parser.add_argument(
        "--run-id", required=True, help="Session run_id to report on, or 'latest'."
    )

    compare_parser = subparsers.add_parser(
        "compare", help="Drift report: current session vs previous."
    )
    compare_parser.add_argument(
        "--run-id", required=True, help="Session run_id to compare, or 'latest'."
    )

    export_parser = subparsers.add_parser("export", help="Export Gold to CSV/JSON only, no HTML.")
    export_parser.add_argument(
        "--run-id", required=True, help="Session run_id to export, or 'latest'."
    )
    export_parser.add_argument(
        "--format",
        choices=("csv", "json"),
        default="csv",
        help="Export format (default: %(default)s)",
    )

    evaluate_parser = subparsers.add_parser(
        "evaluate", help="Evaluate the 5a sentiment stage against the labeled eval set."
    )
    evaluate_parser.add_argument(
        "--labeled-set",
        default=DEFAULT_LABELED_SET_PATH,
        help="Path to the labeled CSV (default: %(default)s)",
    )

    subparsers.add_parser("rebuild-silver", help="Wipe and reprocess Silver from Bronze.")

    args = parser.parse_args(argv)

    if args.command == "snapshot":
        return _snapshot(args.config, args.window)
    if args.command == "incremental":
        return _incremental(args.config)
    if args.command == "classify":
        return _classify(args.config)
    if args.command == "report":
        return _report(args.config, args.run_id)
    if args.command == "compare":
        return _compare(args.config, args.run_id)
    if args.command == "export":
        return _export(args.config, args.run_id, args.format)
    if args.command == "evaluate":
        return _evaluate(args.config, args.labeled_set)
    if args.command == "rebuild-silver":
        return _rebuild_silver(args.config)

    parser.error(f"Unknown command: {args.command}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
