"""Unit tests for run_classification (Milestone 5): Silver -> queue -> Gold -> session log."""

from pathlib import Path

from brandpulse.config.models import (
    ClassificationConfig,
    Config,
    KeywordsConfig,
    OutputConfig,
    RateLimitConfig,
    RetryConfig,
    SourceConfig,
    TimeoutsConfig,
)
from brandpulse.pipeline.run_classification import run_classification
from brandpulse.storage.local import LocalFileStorageBackend
from tests.fixtures.seed_silver import seed_silver_record


def _config(tmp_path: Path, enable_enrichment: bool = False) -> Config:
    return Config(
        sources=[SourceConfig(name="google_play", enabled=True, reliability="high")],
        keywords=KeywordsConfig(base_list=["Wema"]),
        output=OutputConfig(directory=str(tmp_path / "output"), formats=["csv"]),
        retry=RetryConfig(max_attempts=3, backoff_seconds=[0, 0, 0]),
        timeouts=TimeoutsConfig(request_seconds=20),
        rate_limit=RateLimitConfig(requests_per_minute=6000, respect_robots_txt=False),
        classification=ClassificationConfig(enable_enrichment=enable_enrichment),
    )


def test_run_classification_writes_gold_for_every_silver_record(tmp_path: Path):
    backend = LocalFileStorageBackend(tmp_path / "storage")
    seed_silver_record(backend, "m1", "Great app!")
    seed_silver_record(backend, "m2", "Terrible service.")

    run_classification(backend, _config(tmp_path), run_id="run-test-1")

    gold_records = list(backend.read_all("gold"))
    assert len(gold_records) == 2


def test_run_classification_writes_session_log(tmp_path: Path):
    backend = LocalFileStorageBackend(tmp_path / "storage")
    seed_silver_record(backend, "m1", "Great app!")

    config = _config(tmp_path)
    summary = run_classification(backend, config, run_id="run-test-2")

    session_path = Path(config.output.directory) / "sessions" / "run-test-2.json"
    assert session_path.exists()
    assert summary["run_id"] == "run-test-2"
    assert summary["mention_counts_per_source"]["google_play"] == 1


def test_run_classification_with_enrichment_disabled_makes_no_llm_calls(
    tmp_path: Path, monkeypatch
):
    backend = LocalFileStorageBackend(tmp_path / "storage")
    seed_silver_record(backend, "m1", "asdkjh gibberish")

    def _fail_if_called(*args, **kwargs):
        raise AssertionError(
            "llm_client_from_config should not be called when enrichment is disabled"
        )

    monkeypatch.setattr(
        "brandpulse.pipeline.run_classification.llm_client_from_config", _fail_if_called
    )

    run_classification(backend, _config(tmp_path, enable_enrichment=False), run_id="run-test-3")

    gold_records = list(backend.read_all("gold"))
    assert len(gold_records) == 1
