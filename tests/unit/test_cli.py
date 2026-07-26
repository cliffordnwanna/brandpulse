"""Unit tests for the CLI (Milestone 4): rebuild-silver command."""

from pathlib import Path

import yaml

from brandpulse.cli import main
from brandpulse.storage.local import LocalFileStorageBackend
from tests.fixtures.seed_silver import seed_silver_record


def _write_config(
    tmp_path: Path, storage_root: Path, output_dir: Path | None = None, with_connector: bool = False
) -> Path:
    config = {
        "sources": [{"name": "google_play", "enabled": True, "reliability": "high"}],
        "keywords": {"base_list": ["Wema"]},
        "output": {"directory": str(output_dir or tmp_path / "output"), "formats": ["csv"]},
        "retry": {"max_attempts": 1, "backoff_seconds": [0]},
        "timeouts": {"request_seconds": 20},
        "rate_limit": {"requests_per_minute": 6000, "respect_robots_txt": False},
        "storage": {"backend": "local", "root": str(storage_root)},
    }
    if with_connector:
        config["connectors"] = {
            "google_play": {
                "app_ids": [],
                "country": "ng",
                "language": "en",
                "max_reviews_per_run": 10,
            }
        }
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.dump(config), encoding="utf-8")
    return config_path


def test_rebuild_silver_command_runs_end_to_end(tmp_path: Path, capsys):
    storage_root = tmp_path / "storage"
    config_path = _write_config(tmp_path, storage_root)

    backend = LocalFileStorageBackend(storage_root)
    backend.write(
        "bronze",
        "id-1",
        {
            "mention_id": "id-1",
            "text": "Great app!",
            "platform": "google_play",
        },
    )

    exit_code = main(["--config", str(config_path), "rebuild-silver"])

    assert exit_code == 0
    silver_records = list(backend.read_all("silver"))
    assert len(silver_records) == 1
    assert silver_records[0]["language"] is not None

    captured = capsys.readouterr()
    assert "1 record" in captured.out


def test_classify_command_runs_end_to_end(tmp_path: Path, capsys):
    storage_root = tmp_path / "storage"
    output_dir = tmp_path / "output"
    config_path = _write_config(tmp_path, storage_root, output_dir)

    backend = LocalFileStorageBackend(storage_root)
    seed_silver_record(backend, "id-1", "Great app!")

    exit_code = main(["--config", str(config_path), "classify"])

    assert exit_code == 0
    gold_records = list(backend.read_all("gold"))
    assert len(gold_records) == 1

    sessions = list((output_dir / "sessions").glob("*.json"))
    assert len(sessions) == 1

    captured = capsys.readouterr()
    assert "Classified 1 record" in captured.out


def test_evaluate_command_runs_end_to_end(tmp_path: Path, capsys):
    storage_root = tmp_path / "storage"
    output_dir = tmp_path / "output"
    config_path = _write_config(tmp_path, storage_root, output_dir)

    labeled_set_path = tmp_path / "labeled.csv"
    labeled_set_path.write_text(
        "mention_id,text,label,synthetic\n"
        "id-1,Great app easy transfers,Positive,true\n"
        "id-2,Terrible failed transfer no response,Negative,true\n",
        encoding="utf-8",
    )

    exit_code = main(
        ["--config", str(config_path), "evaluate", "--labeled-set", str(labeled_set_path)]
    )

    assert exit_code == 0
    metrics_path = output_dir / "metrics.csv"
    assert metrics_path.exists()

    captured = capsys.readouterr()
    assert "Evaluated 2 labeled example" in captured.out


def test_snapshot_command_runs_end_to_end_with_no_results(tmp_path: Path, capsys):
    storage_root = tmp_path / "storage"
    output_dir = tmp_path / "output"
    config_path = _write_config(tmp_path, storage_root, output_dir, with_connector=True)

    exit_code = main(["--config", str(config_path), "snapshot", "--window", "7d"])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "Snapshot complete" in captured.out
    assert (output_dir / "reports").exists()


def test_incremental_command_runs_end_to_end_with_no_results(tmp_path: Path, capsys):
    storage_root = tmp_path / "storage"
    output_dir = tmp_path / "output"
    config_path = _write_config(tmp_path, storage_root, output_dir, with_connector=True)

    exit_code = main(["--config", str(config_path), "incremental"])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "Incremental run complete" in captured.out
    assert (output_dir / "reports").exists()


def test_report_command_with_explicit_run_id(tmp_path: Path, capsys):
    storage_root = tmp_path / "storage"
    output_dir = tmp_path / "output"
    config_path = _write_config(tmp_path, storage_root, output_dir)

    backend = LocalFileStorageBackend(storage_root)
    seed_silver_record(backend, "id-1", "Great app!")
    main(["--config", str(config_path), "classify"])
    capsys.readouterr()

    run_id = next((output_dir / "sessions").glob("*.json")).stem
    exit_code = main(["--config", str(config_path), "report", "--run-id", run_id])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "Report generated" in captured.out


def test_report_command_with_latest_run_id(tmp_path: Path, capsys):
    storage_root = tmp_path / "storage"
    output_dir = tmp_path / "output"
    config_path = _write_config(tmp_path, storage_root, output_dir)

    backend = LocalFileStorageBackend(storage_root)
    seed_silver_record(backend, "id-1", "Great app!")
    main(["--config", str(config_path), "classify"])
    capsys.readouterr()

    exit_code = main(["--config", str(config_path), "report", "--run-id", "latest"])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "Report generated" in captured.out


def test_compare_command_first_session_reports_no_baseline(tmp_path: Path, capsys):
    storage_root = tmp_path / "storage"
    output_dir = tmp_path / "output"
    config_path = _write_config(tmp_path, storage_root, output_dir)

    backend = LocalFileStorageBackend(storage_root)
    seed_silver_record(backend, "id-1", "Great app!")
    main(["--config", str(config_path), "classify"])
    capsys.readouterr()

    exit_code = main(["--config", str(config_path), "compare", "--run-id", "latest"])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "Run again to enable drift detection" in captured.out


def test_export_command_csv_format(tmp_path: Path, capsys):
    storage_root = tmp_path / "storage"
    output_dir = tmp_path / "output"
    config_path = _write_config(tmp_path, storage_root, output_dir)

    backend = LocalFileStorageBackend(storage_root)
    seed_silver_record(backend, "id-1", "Great app!")
    main(["--config", str(config_path), "classify"])
    capsys.readouterr()

    exit_code = main(
        ["--config", str(config_path), "export", "--run-id", "latest", "--format", "csv"]
    )

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "Exported" in captured.out
    assert (output_dir / "exports").exists()
