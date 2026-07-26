"""InsightEngine (Milestone 6) — Gold records in, structured ``Insight`` objects out.

This module never produces HTML, CSV, or any other rendered form — that is
strictly the renderer's job (``pipeline/report_renderer.py``). Keeping the
two separate is the point of this milestone: any future renderer (PDF, Power
BI, Slack, Teams) can consume the same ``Insight`` list without this module
changing at all.

Gold records (keyed ``{mention_id}_{classifier_version}``) carry only the
classification fields (Engineering Design §13) — they don't duplicate
``text``/``platform``/``author`` from Silver. ``_enrich_gold_records`` joins
each Gold record back to its Silver record via ``mention_id`` so insights
that need the original text (phrase mining, word cloud, emoji analysis) have
it, without Gold ever having to duplicate Silver's fields.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Literal

from sklearn.feature_extraction.text import CountVectorizer

from brandpulse.pipeline.emoji_normalize import extract_emoji_tokens

Severity = Literal["critical", "high", "medium", "low", "info"]


@dataclass
class Insight:
    id: str
    title: str
    description: str
    severity: Severity
    confidence: float
    data: dict[str, Any]
    insight_type: str
    recommendation: str | None = None


def _enrich_gold_records(
    gold_records: list[dict[str, Any]], silver_by_mention_id: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    """Join each Gold record to its Silver record's text/platform/author.

    A Gold record with no matching Silver record (shouldn't normally happen,
    but Silver could theoretically be rebuilt/pruned after Gold was written)
    is skipped rather than crashing the whole report.
    """
    enriched = []
    for gold in gold_records:
        silver = silver_by_mention_id.get(gold["mention_id"])
        if silver is None:
            continue
        merged = {**gold, **{k: v for k, v in silver.items() if k not in gold}}
        enriched.append(merged)
    return enriched


def _sentiment_counts(records: list[dict[str, Any]]) -> Counter:
    return Counter(r["sentiment"]["label"] for r in records)


def _complaint_counts(records: list[dict[str, Any]]) -> Counter:
    return Counter(r["complaint_category"]["label"] for r in records)


# ---------------------------------------------------------------------------
# 1. Emerging Issues / Anomaly Detection
# ---------------------------------------------------------------------------


def detect_emerging_issues(
    current_records: list[dict[str, Any]],
    previous_session_summaries: list[dict[str, Any]],
    spike_threshold: float = 0.5,
) -> list[Insight]:
    """Complaint categories where current volume is >``spike_threshold`` higher
    than the previous-session average. Returns a single "no baseline yet"
    info insight if no previous session exists — never an empty list, so the
    "Emerging Issues" report section always has something to show.
    """
    if not previous_session_summaries:
        return [
            Insight(
                id="emerging_issues_no_baseline",
                title="First run — no baseline yet",
                description=(
                    "This is the first classified session for this dataset. Emerging-issue "
                    "detection compares volume against previous sessions — run again to enable it."
                ),
                severity="info",
                confidence=1.0,
                data={},
                insight_type="spike",
            )
        ]

    current_counts = _complaint_counts(current_records)
    previous_averages: dict[str, float] = {}
    for category in set(current_counts) | {
        c for s in previous_session_summaries for c in s.get("complaint_category_counts", {})
    }:
        prior_values = [
            s.get("complaint_category_counts", {}).get(category, 0)
            for s in previous_session_summaries
        ]
        previous_averages[category] = sum(prior_values) / len(prior_values) if prior_values else 0.0

    insights: list[Insight] = []
    for category, current_count in current_counts.items():
        baseline = previous_averages.get(category, 0.0)
        if baseline <= 0:
            continue
        pct_change = (current_count - baseline) / baseline
        if pct_change > spike_threshold:
            severity: Severity = "critical" if pct_change > 1.0 else "high"
            insights.append(
                Insight(
                    id=f"emerging_issue_{_slug(category)}",
                    title=f"{category} complaints up {round(pct_change * 100)}% vs last session",
                    description=(
                        f"{category} mentions rose from an average of {round(baseline, 1)} "
                        f"to {current_count} this session, a {round(pct_change * 100)}% increase."
                    ),
                    severity=severity,
                    confidence=min(0.5 + pct_change / 2, 0.95),
                    data={
                        "category": category,
                        "current_count": current_count,
                        "previous_average": round(baseline, 2),
                        "pct_change": round(pct_change * 100, 1),
                    },
                    insight_type="spike",
                )
            )

    insights.sort(key=lambda i: i.data.get("pct_change", 0), reverse=True)

    if not insights:
        insights.append(
            Insight(
                id="emerging_issues_none",
                title="No emerging issues detected",
                description="No complaint category rose more than "
                f"{round(spike_threshold * 100)}% above its previous-session average.",
                severity="info",
                confidence=1.0,
                data={},
                insight_type="spike",
            )
        )
    return insights


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


# ---------------------------------------------------------------------------
# 2. Complaint Velocity
# ---------------------------------------------------------------------------


def complaint_velocity(
    current_records: list[dict[str, Any]],
    previous_session_summaries: list[dict[str, Any]],
    top_n: int = 5,
) -> Insight:
    current_counts = _complaint_counts(current_records)
    top = current_counts.most_common(top_n)

    previous_counts: Counter = Counter()
    if previous_session_summaries:
        previous_counts = Counter(
            previous_session_summaries[-1].get("complaint_category_counts", {})
        )

    rows = []
    for category, count in top:
        prior = previous_counts.get(category, 0)
        if prior == 0:
            trend = "new" if count > 0 else "flat"
        elif count > prior:
            trend = "up"
        elif count < prior:
            trend = "down"
        else:
            trend = "flat"
        rows.append({"category": category, "count": count, "previous_count": prior, "trend": trend})

    return Insight(
        id="complaint_velocity",
        title="Top complaint categories this session",
        description=f"The {len(rows)} highest-volume complaint categories, with trend vs. the "
        "previous session.",
        severity="info",
        confidence=1.0,
        data={"top_categories": rows},
        insight_type="trend",
    )


# ---------------------------------------------------------------------------
# 3. Platform Heatmap
# ---------------------------------------------------------------------------


def platform_heatmap(records: list[dict[str, Any]]) -> Insight:
    per_platform: dict[str, Counter] = {}
    for record in records:
        platform = record.get("platform", "unknown")
        per_platform.setdefault(platform, Counter())[record["sentiment"]["label"]] += 1

    rows = []
    for platform, counts in per_platform.items():
        total = sum(counts.values())
        rows.append(
            {
                "platform": platform,
                "total": total,
                "sentiment_counts": dict(counts),
                "negative_pct": round(100 * counts.get("Negative", 0) / total, 1) if total else 0.0,
                "positive_pct": round(100 * counts.get("Positive", 0) / total, 1) if total else 0.0,
            }
        )
    rows.sort(key=lambda r: r["total"], reverse=True)

    return Insight(
        id="platform_heatmap",
        title="Mentions and sentiment by platform",
        description="Per-platform mention volume and sentiment split.",
        severity="info",
        confidence=1.0,
        data={"platforms": rows},
        insight_type="trend",
    )


# ---------------------------------------------------------------------------
# 4. Phrase Mining
# ---------------------------------------------------------------------------


def mine_phrases(records: list[dict[str, Any]], top_n: int = 50) -> Insight:
    """Top bigrams/trigrams from complaint text (Negative/Mixed sentiment),
    via ``CountVectorizer`` — includes emoji tokens (``:angry_face:``) since
    they're already normalized into ordinary word-like tokens by Silver.
    """
    texts = [
        r["text"]
        for r in records
        if r.get("text") and r["sentiment"]["label"] in ("Negative", "Mixed")
    ]

    if not texts:
        return Insight(
            id="phrase_mining",
            title="Top phrases in complaint text",
            description="No negative/mixed-sentiment mentions to mine phrases from.",
            severity="info",
            confidence=1.0,
            data={"phrases": []},
            insight_type="phrase",
        )

    vectorizer = CountVectorizer(
        ngram_range=(2, 3),
        stop_words="english",
        # Keeps emoji tokens (":angry_face:") intact as single tokens instead
        # of a plain \b word boundary stripping their leading/trailing colons.
        token_pattern=r"(?u)(?<!\w):?[\w'-]+:?(?!\w)",
    )
    try:
        matrix = vectorizer.fit_transform(texts)
    except ValueError:
        # Every candidate phrase was filtered out as a pure-stopword n-gram.
        return Insight(
            id="phrase_mining",
            title="Top phrases in complaint text",
            description="No recurring phrases found in negative/mixed-sentiment mentions.",
            severity="info",
            confidence=1.0,
            data={"phrases": []},
            insight_type="phrase",
        )

    counts = matrix.sum(axis=0).A1
    phrases = sorted(
        zip(vectorizer.get_feature_names_out(), counts, strict=True),
        key=lambda item: item[1],
        reverse=True,
    )[:top_n]

    rows = [{"phrase": phrase, "count": int(count)} for phrase, count in phrases if count > 0]

    return Insight(
        id="phrase_mining",
        title="Top phrases in complaint text",
        description=f"The {len(rows)} most frequent bigrams/trigrams across negative/mixed "
        "mentions.",
        severity="info",
        confidence=1.0,
        data={"phrases": rows},
        insight_type="phrase",
    )


# ---------------------------------------------------------------------------
# 5. Competitor Mentions
# ---------------------------------------------------------------------------


def competitor_mentions(records: list[dict[str, Any]], competitors: tuple[str, ...]) -> Insight:
    """Directional (positive/negative) counts per competitor, from Tier 5b's
    ``competitor_mention`` field where present. Records without 5b enrichment
    simply don't contribute — this insight is naturally sparser when
    enrichment is disabled, not an error.
    """
    per_competitor: dict[str, Counter] = {c: Counter() for c in competitors}

    for record in records:
        mention = record.get("competitor_mention")
        if not mention or mention.get("label") in (None, "None"):
            continue
        label = mention["label"]
        if label not in per_competitor:
            continue
        per_competitor[label][record["sentiment"]["label"]] += 1

    rows = [
        {
            "competitor": competitor,
            "positive": counts.get("Positive", 0),
            "negative": counts.get("Negative", 0),
            "neutral": counts.get("Neutral", 0),
            "mixed": counts.get("Mixed", 0),
            "total": sum(counts.values()),
        }
        for competitor, counts in per_competitor.items()
        if sum(counts.values()) > 0
    ]
    rows.sort(key=lambda r: r["total"], reverse=True)

    return Insight(
        id="competitor_mentions",
        title="Competitor mentions",
        description="Directional sentiment for each competitor mentioned alongside our brand.",
        severity="info",
        confidence=1.0,
        data={"competitors": rows},
        insight_type="competitor",
    )


# ---------------------------------------------------------------------------
# 6. Emoji Analysis
# ---------------------------------------------------------------------------


def emoji_analysis(records: list[dict[str, Any]], top_n: int = 20) -> Insight:
    counter: Counter = Counter()
    for record in records:
        text = record.get("text", "")
        counter.update(extract_emoji_tokens(text))

    rows = [{"emoji": token, "count": count} for token, count in counter.most_common(top_n)]

    return Insight(
        id="emoji_analysis",
        title="Top emoji tokens",
        description=f"The {len(rows)} most frequent emoji tokens across all mentions.",
        severity="info",
        confidence=1.0,
        data={"emoji": rows},
        insight_type="emoji",
    )


# ---------------------------------------------------------------------------
# 7. Sentiment Overview
# ---------------------------------------------------------------------------


def sentiment_overview(
    records: list[dict[str, Any]], previous_session_summaries: list[dict[str, Any]]
) -> Insight:
    counts = _sentiment_counts(records)
    total = sum(counts.values())
    overall = {
        label: {"count": count, "pct": round(100 * count / total, 1) if total else 0.0}
        for label, count in counts.items()
    }

    per_platform: dict[str, Counter] = {}
    for record in records:
        platform = record.get("platform", "unknown")
        per_platform.setdefault(platform, Counter())[record["sentiment"]["label"]] += 1
    per_platform_rows = {
        platform: {label: count for label, count in c.items()}
        for platform, c in per_platform.items()
    }

    trend = None
    if previous_session_summaries:
        previous = previous_session_summaries[-1].get("sentiment_distribution", {})
        prev_negative_pct = previous.get("Negative", {}).get("pct")
        current_negative_pct = overall.get("Negative", {}).get("pct")
        if prev_negative_pct is not None and current_negative_pct is not None:
            trend = round(current_negative_pct - prev_negative_pct, 1)

    return Insight(
        id="sentiment_overview",
        title="Overall sentiment",
        description="Sentiment split across all classified mentions this session.",
        severity="info",
        confidence=1.0,
        data={
            "overall": overall,
            "per_platform": per_platform_rows,
            "negative_pct_change_vs_previous": trend,
        },
        insight_type="trend",
    )


# ---------------------------------------------------------------------------
# 8. Drift Summary (for `compare`)
# ---------------------------------------------------------------------------


def drift_summary(
    current_session: dict[str, Any], previous_session: dict[str, Any] | None
) -> Insight:
    if previous_session is None:
        return Insight(
            id="drift_summary_no_baseline",
            title="Run again to enable drift detection",
            description="Only one session exists so far — drift comparison needs at least two.",
            severity="info",
            confidence=1.0,
            data={},
            insight_type="trend",
        )

    current_sentiment = current_session.get("sentiment_distribution", {})
    previous_sentiment = previous_session.get("sentiment_distribution", {})
    sentiment_deltas = {
        label: round(
            current_sentiment.get(label, {}).get("pct", 0)
            - previous_sentiment.get(label, {}).get("pct", 0),
            1,
        )
        for label in set(current_sentiment) | set(previous_sentiment)
    }

    current_volume = sum(current_session.get("mention_counts_per_source", {}).values())
    previous_volume = sum(previous_session.get("mention_counts_per_source", {}).values())

    return Insight(
        id="drift_summary",
        title="Session-over-session drift",
        description=f"Comparing session {current_session.get('run_id')} against "
        f"{previous_session.get('run_id')}.",
        severity="info",
        confidence=1.0,
        data={
            "sentiment_pct_deltas": sentiment_deltas,
            "current_volume": current_volume,
            "previous_volume": previous_volume,
            "volume_pct_change": (
                round(100 * (current_volume - previous_volume) / previous_volume, 1)
                if previous_volume
                else None
            ),
        },
        insight_type="trend",
    )


# ---------------------------------------------------------------------------
# Top-level entry point
# ---------------------------------------------------------------------------


@dataclass
class InsightEngineResult:
    insights: list[Insight] = field(default_factory=list)


def generate_insights(
    gold_records: list[dict[str, Any]],
    silver_records: list[dict[str, Any]],
    competitors: tuple[str, ...],
    previous_session_summaries: list[dict[str, Any]] | None = None,
) -> list[Insight]:
    """Produce every report-section insight, in priority order (spec order)."""
    previous_session_summaries = previous_session_summaries or []
    silver_by_mention_id = {r["mention_id"]: r for r in silver_records}
    enriched = _enrich_gold_records(gold_records, silver_by_mention_id)

    insights: list[Insight] = []
    insights.extend(detect_emerging_issues(enriched, previous_session_summaries))
    insights.append(complaint_velocity(enriched, previous_session_summaries))
    insights.append(platform_heatmap(enriched))
    insights.append(mine_phrases(enriched))
    insights.append(competitor_mentions(enriched, competitors))
    insights.append(emoji_analysis(enriched))
    insights.append(sentiment_overview(enriched, previous_session_summaries))
    return insights
