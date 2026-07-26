"""Session logging (Milestone 5 spec — new requirement).

Every classification run creates a timestamped, never-overwritten record at
``output/sessions/{run_id}.json`` — the analytical summary of what was
found (sentiment distribution, top complaint categories, confidence
distribution), distinct from ``run_metadata.json``'s operational/orchestration
log. Keeping every session lets drift be detected by comparing distributions
across files over time.
"""

from __future__ import annotations

import json
import statistics
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def build_session_summary(
    run_id: str,
    sources_scraped: list[str],
    mention_counts_per_source: dict[str, int],
    gold_records: list[dict[str, Any]],
    confidence_threshold: float,
    failed_connectors: list[str],
) -> dict[str, Any]:
    sentiment_counts = Counter(r["sentiment"]["label"] for r in gold_records)
    total = sum(sentiment_counts.values())
    sentiment_distribution = {
        label: {
            "count": count,
            "pct": round(100 * count / total, 2) if total else 0.0,
        }
        for label, count in sentiment_counts.items()
    }

    complaint_counts = Counter(r["complaint_category"]["label"] for r in gold_records)
    top_complaint_categories = [
        {"category": category, "count": count}
        for category, count in complaint_counts.most_common(10)
    ]
    # Full (not just top-10) counts — needed as the baseline for Milestone 6's
    # emerging-issue/spike detection, which must compare every category's
    # current volume against its own previous-session average, not just the
    # categories that happened to be in the top 10 last time.
    complaint_category_counts = dict(complaint_counts)

    all_confidences = [r["sentiment"]["confidence"] for r in gold_records] + [
        r["complaint_category"]["confidence"] for r in gold_records
    ]
    below_threshold = sum(1 for c in all_confidences if c < confidence_threshold)
    confidence_distribution = {
        "mean": round(statistics.mean(all_confidences), 4) if all_confidences else None,
        "median": round(statistics.median(all_confidences), 4) if all_confidences else None,
        "pct_below_threshold": (
            round(100 * below_threshold / len(all_confidences), 2) if all_confidences else 0.0
        ),
    }

    return {
        "run_id": run_id,
        "run_timestamp": datetime.now(UTC).isoformat(),
        "sources_scraped": sources_scraped,
        "mention_counts_per_source": mention_counts_per_source,
        # The actual mention_id set this session covers (Milestone 6's
        # "snapshot" mode) — `report`/`compare` read this back to scope
        # InsightEngine/word-cloud input to just this session's data,
        # since Gold/Silver themselves are cumulative stores with no
        # per-session field of their own.
        "mention_ids": sorted({r["mention_id"] for r in gold_records}),
        "sentiment_distribution": sentiment_distribution,
        "top_complaint_categories": top_complaint_categories,
        "complaint_category_counts": complaint_category_counts,
        "confidence_distribution": confidence_distribution,
        "failed_connectors": failed_connectors,
    }


def write_session_log(output_dir: str | Path, session_summary: dict[str, Any]) -> Path:
    """Write ``session_summary`` to ``{output_dir}/sessions/{run_id}.json``.

    Every session is kept — a session file is never overwritten; a second
    call with the same ``run_id`` raises rather than silently clobbering a
    prior session's record.
    """
    sessions_dir = Path(output_dir) / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)
    path = sessions_dir / f"{session_summary['run_id']}.json"
    if path.exists():
        raise FileExistsError(
            f"Session log already exists for run_id={session_summary['run_id']!r}: {path}"
        )
    path.write_text(json.dumps(session_summary, indent=2, default=str), encoding="utf-8")
    return path
