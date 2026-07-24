"""Unit tests for structured JSON logging (Engineering Design §7)."""

import io
import json
import logging

from brandpulse.orchestration.logging import get_logger, log_event


def _fresh_logger(stream: io.StringIO) -> logging.Logger:
    logger = logging.getLogger("brandpulse.orchestration")
    logger.handlers.clear()
    return get_logger(stream=stream)


def test_log_event_emits_one_json_line_per_event():
    stream = io.StringIO()
    logger = _fresh_logger(stream)

    log_event(
        logger,
        "connector_run_start",
        connector="google_play",
        search_term="ALAT",
        run_id="run-1",
    )

    line = stream.getvalue().strip()
    parsed = json.loads(line)

    assert parsed == {
        "event": "connector_run_start",
        "connector": "google_play",
        "search_term": "ALAT",
        "run_id": "run-1",
    }


def test_log_event_run_end_matches_expected_shape():
    stream = io.StringIO()
    logger = _fresh_logger(stream)

    log_event(
        logger,
        "connector_run_end",
        connector="nairaland",
        status="FAILED",
        reason="html_structure_changed",
    )

    parsed = json.loads(stream.getvalue().strip())

    assert parsed["event"] == "connector_run_end"
    assert parsed["status"] == "FAILED"
    assert parsed["reason"] == "html_structure_changed"
