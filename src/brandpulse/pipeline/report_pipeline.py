"""Report generation from existing Gold data (Milestone 6).

This is the ``report`` CLI command's implementation, and is also called by
``run`` after classification — but it never scrapes or classifies anything
itself. It only reads Gold/Silver/session-log data already on disk and
produces the ``output/reports/`` bundle. That separation is the spec's
"separation rule": ``report`` must produce identical output run 10 times in
a row against unchanged Gold data.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from brandpulse.config.models import Config
from brandpulse.config.taxonomy import load_taxonomy
from brandpulse.pipeline.insight_engine import Insight, generate_insights
from brandpulse.pipeline.llm_client import LLMCallLogger, llm_client_from_config
from brandpulse.pipeline.output_writers import write_insights_json, write_phrases_csv
from brandpulse.pipeline.recommendation import add_recommendations
from brandpulse.pipeline.report_renderer import render_html_report, write_html_report
from brandpulse.pipeline.wordcloud_gen import generate_wordcloud_png, png_to_data_uri
from brandpulse.storage.base import StorageBackend

_PLATFORM_LIMITATIONS_PATH = "docs/platform-limitations.md"


def _load_previous_sessions(output_dir: str | Path, exclude_run_id: str) -> list[dict[str, Any]]:
    sessions_dir = Path(output_dir) / "sessions"
    if not sessions_dir.exists():
        return []
    sessions = []
    for path in sorted(sessions_dir.glob("*.json")):
        if path.stem == exclude_run_id:
            continue
        sessions.append(json.loads(path.read_text(encoding="utf-8")))
    sessions.sort(key=lambda s: s.get("run_timestamp", ""))
    return sessions


def _load_session(output_dir: str | Path, run_id: str) -> dict[str, Any] | None:
    path = Path(output_dir) / "sessions" / f"{run_id}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def latest_gold_records(backend: StorageBackend) -> list[dict[str, Any]]:
    """Return the newest classifier-version Gold record per mention_id.

    Gold is versioned and never overwritten (Engineering Design §13) — a
    mention can have multiple Gold records across classifier versions. The
    report always reflects the latest version, keeping "most recent
    classification wins" implicit rather than the renderer/InsightEngine
    having to know about versioning at all.
    """
    latest: dict[str, dict[str, Any]] = {}
    for record in backend.read_all("gold"):
        mention_id = record["mention_id"]
        existing = latest.get(mention_id)
        if existing is None or record.get("classifier_version", "") >= existing.get(
            "classifier_version", ""
        ):
            latest[mention_id] = record
    return list(latest.values())


def generate_report(
    backend: StorageBackend,
    config: Config,
    run_id: str,
) -> dict[str, Any]:
    """Build the full ``output/reports/`` bundle for ``run_id`` from existing
    Gold/Silver/session data alone. Returns a summary dict of what was written.
    """
    session_summary = _load_session(config.output.directory, run_id)
    if session_summary is None:
        raise FileNotFoundError(
            f"No session log found for run_id={run_id!r} — run `classify` before `report`."
        )

    all_gold_records = latest_gold_records(backend)
    all_silver_records = list(backend.read_all("silver"))
    taxonomy = load_taxonomy()
    previous_sessions = _load_previous_sessions(config.output.directory, exclude_run_id=run_id)

    # Scope to this session's mention_ids when the session log recorded them
    # (Milestone 6 "snapshot" mode) — older session logs written before this
    # field existed have no `mention_ids` key, and fall back to reporting
    # over everything currently in Gold/Silver (the pre-Milestone-6 "classify
    # is cumulative" behavior), rather than silently reporting on nothing.
    session_mention_ids = session_summary.get("mention_ids")
    if session_mention_ids:
        scope = set(session_mention_ids)
        gold_records = [r for r in all_gold_records if r["mention_id"] in scope]
        silver_records = [r for r in all_silver_records if r["mention_id"] in scope]
    else:
        gold_records = all_gold_records
        silver_records = all_silver_records

    insights = generate_insights(
        gold_records, silver_records, taxonomy.competitors, previous_sessions
    )

    if config.classification.recommendations:
        llm_client = llm_client_from_config(config.classification.enrichment_model)
        add_recommendations(insights, llm_client, LLMCallLogger())

    silver_by_mention_id = {r["mention_id"]: r for r in silver_records}
    enriched = [
        {
            **g,
            **{
                k: v for k, v in silver_by_mention_id.get(g["mention_id"], {}).items() if k not in g
            },
        }
        for g in gold_records
    ]

    brand_terms = tuple(config.keywords.base_list)
    wordcloud_png = generate_wordcloud_png(enriched, brand_terms=brand_terms)
    wordcloud_data_uri = png_to_data_uri(wordcloud_png)

    platform_limitations_text = Path(_PLATFORM_LIMITATIONS_PATH).read_text(encoding="utf-8")

    sources = sorted(session_summary.get("mention_counts_per_source", {}).keys())
    total_mentions = sum(session_summary.get("mention_counts_per_source", {}).values())
    date_range = session_summary.get("run_timestamp", "unknown")[:10]

    html_content = render_html_report(
        run_id=run_id,
        insights=insights,
        total_mentions=total_mentions,
        date_range=date_range,
        sources=sources,
        wordcloud_data_uri=wordcloud_data_uri,
        platform_limitations_markdown=platform_limitations_text,
    )

    reports_dir = Path(config.output.directory) / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    html_path = write_html_report(reports_dir / f"{run_id}_report.html", html_content)
    wordcloud_path = reports_dir / f"{run_id}_wordcloud.png"
    wordcloud_path.write_bytes(wordcloud_png)

    phrase_insight = next((i for i in insights if i.id == "phrase_mining"), None)
    phrases = phrase_insight.data.get("phrases", []) if phrase_insight else []
    phrases_path = write_phrases_csv(reports_dir / f"{run_id}_phrases.csv", phrases)

    insights_path = write_insights_json(reports_dir / f"{run_id}_insights.json", insights)

    platform_limitations_copy = reports_dir / "platform_limitations.md"
    platform_limitations_copy.write_text(platform_limitations_text, encoding="utf-8")

    return {
        "run_id": run_id,
        "html_path": str(html_path),
        "wordcloud_path": str(wordcloud_path),
        "phrases_path": str(phrases_path),
        "insights_path": str(insights_path),
        "platform_limitations_path": str(platform_limitations_copy),
        "insight_count": len(insights),
    }


def generate_drift_report(config: Config, run_id: str) -> Insight:
    """The ``compare`` command: drift between ``run_id`` and the previous session."""
    current = _load_session(config.output.directory, run_id)
    if current is None:
        raise FileNotFoundError(f"No session log found for run_id={run_id!r}.")

    previous_sessions = _load_previous_sessions(config.output.directory, exclude_run_id=run_id)
    previous = previous_sessions[-1] if previous_sessions else None

    from brandpulse.pipeline.insight_engine import drift_summary

    return drift_summary(current, previous)
