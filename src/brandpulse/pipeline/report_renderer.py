"""HTML report renderer (Milestone 6).

Consumes a list of ``Insight`` objects (from ``insight_engine.py``) and
produces one self-contained HTML file — no analytics logic lives here, only
presentation. This module never reads Gold/Silver directly and never
computes a metric; if a number appears in the HTML, it came from an
``Insight.data`` dict. That separation is what lets a future PDF/Slack/Power
BI renderer reuse the same ``Insight`` list without this module changing.

"Self-contained" is a hard requirement: all CSS is inlined, the word cloud
is embedded as a base64 data URI, and the platform-limitations text is
embedded directly rather than linked — the file must open correctly with no
internet connection.
"""

from __future__ import annotations

import html
from pathlib import Path
from typing import Any

from brandpulse.pipeline.insight_engine import Insight

_CSS = """
body { font-family: -apple-system, Segoe UI, Roboto, Arial, sans-serif; margin: 0;
       background: #f4f5f7; color: #1c1e21; }
.container { max-width: 960px; margin: 0 auto; padding: 24px; }
header.report-header { background: #10243e; color: white; padding: 32px 24px; }
header.report-header h1 { margin: 0 0 8px 0; font-size: 28px; }
header.report-header p { margin: 0; opacity: 0.85; }
section { background: white; border-radius: 8px; padding: 20px 24px; margin: 20px 0;
          box-shadow: 0 1px 3px rgba(0,0,0,0.08); }
section h2 { margin-top: 0; font-size: 20px; border-bottom: 2px solid #eee; padding-bottom: 8px; }
table { width: 100%; border-collapse: collapse; margin-top: 12px; }
th, td { text-align: left; padding: 8px 10px; border-bottom: 1px solid #eee; font-size: 14px; }
th { background: #f9fafb; font-weight: 600; }
.badge { display: inline-block; padding: 2px 10px; border-radius: 12px; font-size: 12px;
         font-weight: 600; color: white; }
.badge-critical { background: #c0392b; }
.badge-high { background: #e67e22; }
.badge-medium { background: #d4ac0d; }
.badge-low { background: #7f8c8d; }
.badge-info { background: #2980b9; }
.trend-up { color: #c0392b; font-weight: 600; }
.trend-down { color: #27ae60; font-weight: 600; }
.trend-flat { color: #7f8c8d; }
.trend-new { color: #2980b9; font-weight: 600; }
.recommendation { background: #fff8e1; border-left: 4px solid #d4ac0d; padding: 10px 14px;
                   margin-top: 10px; font-size: 14px; }
.wordcloud-img { max-width: 100%; border-radius: 6px; }
.exec-summary-grid { display: flex; gap: 24px; flex-wrap: wrap; }
.exec-summary-stat { flex: 1; min-width: 140px; }
.exec-summary-stat .value { font-size: 28px; font-weight: 700; }
.exec-summary-stat .label { font-size: 13px; color: #666; }
footer { text-align: center; color: #999; font-size: 12px; padding: 24px; }
"""

_TREND_ARROWS = {"up": "&#9650;", "down": "&#9660;", "flat": "&#8226;", "new": "&#9733;"}


def _e(value: Any) -> str:
    """HTML-escape any value for safe interpolation."""
    return html.escape(str(value))


def _severity_badge(severity: str) -> str:
    return f'<span class="badge badge-{_e(severity)}">{_e(severity.upper())}</span>'


def _find(insights: list[Insight], insight_id_prefix: str) -> list[Insight]:
    return [i for i in insights if i.id.startswith(insight_id_prefix)]


def _find_one(insights: list[Insight], insight_id: str) -> Insight | None:
    for insight in insights:
        if insight.id == insight_id:
            return insight
    return None


def _render_recommendation(insight: Insight) -> str:
    if not insight.recommendation:
        return ""
    return (
        '<div class="recommendation"><strong>Recommendation:</strong> '
        f"{_e(insight.recommendation)}</div>"
    )


def _render_executive_summary(
    total_mentions: int,
    date_range: str,
    sources: list[str],
    top_categories: list[str],
    sentiment_verdict: str,
) -> str:
    return f"""
    <section id="executive-summary">
      <h2>Executive Summary</h2>
      <div class="exec-summary-grid">
        <div class="exec-summary-stat"><div class="value">{_e(total_mentions)}</div>
          <div class="label">Total mentions</div></div>
        <div class="exec-summary-stat"><div class="value">{_e(date_range)}</div>
          <div class="label">Date range</div></div>
        <div class="exec-summary-stat"><div class="value">{_e(", ".join(sources) or "None")}</div>
          <div class="label">Sources covered</div></div>
      </div>
      <p><strong>Top complaint categories:</strong> {_e(", ".join(top_categories) or "None")}</p>
      <p><strong>Sentiment verdict:</strong> {_e(sentiment_verdict)}</p>
    </section>
    """


def _render_emerging_issues(insights: list[Insight]) -> str:
    rows = "".join(f"""<li>{_severity_badge(i.severity)} <strong>{_e(i.title)}</strong>
            <p>{_e(i.description)}</p>{_render_recommendation(i)}</li>""" for i in insights)
    return f"""
    <section id="emerging-issues">
      <h2>Emerging Issues</h2>
      <ul>{rows}</ul>
    </section>
    """


def _render_complaint_velocity(insight: Insight | None) -> str:
    if insight is None:
        return ""
    rows = "".join(f"""<tr><td>{_e(r["category"])}</td><td>{_e(r["count"])}</td>
            <td>{_e(r["previous_count"])}</td>
            <td class="trend-{_e(r["trend"])}">{_TREND_ARROWS.get(r["trend"], "")}
            {_e(r["trend"])}</td></tr>""" for r in insight.data.get("top_categories", []))
    return f"""
    <section id="complaint-velocity">
      <h2>Complaint Velocity</h2>
      <table>
        <tr><th>Category</th><th>Count</th><th>Previous</th><th>Trend</th></tr>
        {rows}
      </table>
    </section>
    """


def _render_phrase_mining(insight: Insight | None) -> str:
    if insight is None:
        return ""
    rows = "".join(
        f"<tr><td>{_e(p['phrase'])}</td><td>{_e(p['count'])}</td></tr>"
        for p in insight.data.get("phrases", [])[:20]
    )
    return f"""
    <section id="phrase-mining">
      <h2>Phrase Mining</h2>
      <table>
        <tr><th>Phrase</th><th>Mentions</th></tr>
        {rows or "<tr><td colspan='2'>No recurring phrases found.</td></tr>"}
      </table>
    </section>
    """


def _render_platform_breakdown(insight: Insight | None) -> str:
    if insight is None:
        return ""
    rows = "".join(
        f"""<tr><td>{_e(p["platform"])}</td><td>{_e(p["total"])}</td>
            <td>{_e(p["positive_pct"])}%</td><td>{_e(p["negative_pct"])}%</td></tr>"""
        for p in insight.data.get("platforms", [])
    )
    return f"""
    <section id="platform-breakdown">
      <h2>Platform Breakdown</h2>
      <table>
        <tr><th>Platform</th><th>Mentions</th><th>Positive %</th><th>Negative %</th></tr>
        {rows}
      </table>
    </section>
    """


def _render_wordcloud(wordcloud_data_uri: str | None) -> str:
    if not wordcloud_data_uri:
        return ""
    return f"""
    <section id="word-cloud">
      <h2>Word Cloud</h2>
      <img class="wordcloud-img" src="{_e(wordcloud_data_uri)}" alt="Word cloud of mention text" />
    </section>
    """


def _render_competitor_mentions(insight: Insight | None) -> str:
    if insight is None:
        return ""
    rows = "".join(
        f"""<tr><td>{_e(c["competitor"])}</td><td>{_e(c["positive"])}</td>
            <td>{_e(c["negative"])}</td><td>{_e(c["neutral"])}</td><td>{_e(c["mixed"])}</td></tr>"""
        for c in insight.data.get("competitors", [])
    )
    return f"""
    <section id="competitor-mentions">
      <h2>Competitor Mentions</h2>
      <table>
        <tr><th>Competitor</th><th>Positive</th><th>Negative</th><th>Neutral</th><th>Mixed</th></tr>
        {rows or "<tr><td colspan='5'>No competitor mentions detected.</td></tr>"}
      </table>
    </section>
    """


def _render_emoji_analysis(insight: Insight | None) -> str:
    if insight is None:
        return ""
    rows = "".join(
        f"<tr><td>{_e(e['emoji'])}</td><td>{_e(e['count'])}</td></tr>"
        for e in insight.data.get("emoji", [])
    )
    return f"""
    <section id="emoji-analysis">
      <h2>Emoji Analysis</h2>
      <table>
        <tr><th>Emoji token</th><th>Count</th></tr>
        {rows or "<tr><td colspan='2'>No emoji found in mentions.</td></tr>"}
      </table>
    </section>
    """


def _render_session_drift(insight: Insight | None) -> str:
    if insight is None:
        return ""
    if not insight.data:
        return f"""
        <section id="session-drift">
          <h2>Session Drift</h2>
          <p>{_e(insight.description)}</p>
        </section>
        """
    deltas = "".join(
        f"<tr><td>{_e(label)}</td><td>{_e(delta):+}pp</td></tr>"
        for label, delta in insight.data.get("sentiment_pct_deltas", {}).items()
    )
    return f"""
    <section id="session-drift">
      <h2>Session Drift</h2>
      <table>
        <tr><th>Sentiment</th><th>Change vs previous session</th></tr>
        {deltas}
      </table>
      <p>Volume: {_e(insight.data.get("current_volume"))} vs
         {_e(insight.data.get("previous_volume"))} previous
         ({_e(insight.data.get("volume_pct_change"))}% change)</p>
    </section>
    """


def _render_platform_limitations(platform_limitations_markdown: str) -> str:
    escaped = _e(platform_limitations_markdown)
    return f"""
    <section id="platform-limitations">
      <h2>Platform Limitations</h2>
      <pre style="white-space: pre-wrap; font-family: inherit;">{escaped}</pre>
    </section>
    """


def render_html_report(
    run_id: str,
    insights: list[Insight],
    total_mentions: int,
    date_range: str,
    sources: list[str],
    wordcloud_data_uri: str | None,
    platform_limitations_markdown: str,
) -> str:
    """Render the full self-contained HTML report from ``insights`` alone.

    Section order matches the spec exactly: Executive Summary, Emerging
    Issues, Complaint Velocity, Phrase Mining, Platform Breakdown, Word
    Cloud, Competitor Mentions, Emoji Analysis, Session Drift, Platform
    Limitations (always last).
    """
    emerging_issues = _find(insights, "emerging_issue")
    complaint_velocity = _find_one(insights, "complaint_velocity")
    phrase_mining = _find_one(insights, "phrase_mining")
    platform_heatmap = _find_one(insights, "platform_heatmap")
    competitor_mentions = _find_one(insights, "competitor_mentions")
    emoji_analysis = _find_one(insights, "emoji_analysis")
    session_drift = _find_one(insights, "drift_summary") or _find_one(
        insights, "drift_summary_no_baseline"
    )
    sentiment_overview = _find_one(insights, "sentiment_overview")

    top_categories = [
        row["category"]
        for row in (
            complaint_velocity.data.get("top_categories", []) if complaint_velocity else []
        )[:3]
    ]
    sentiment_verdict = "No sentiment data available."
    if sentiment_overview:
        overall = sentiment_overview.data.get("overall", {})
        if overall:
            dominant = max(overall.items(), key=lambda item: item[1]["count"])
            sentiment_verdict = f"Majority {dominant[0]} ({dominant[1]['pct']}%)"

    body = "".join(
        [
            _render_executive_summary(
                total_mentions, date_range, sources, top_categories, sentiment_verdict
            ),
            _render_emerging_issues(emerging_issues),
            _render_complaint_velocity(complaint_velocity),
            _render_phrase_mining(phrase_mining),
            _render_platform_breakdown(platform_heatmap),
            _render_wordcloud(wordcloud_data_uri),
            _render_competitor_mentions(competitor_mentions),
            _render_emoji_analysis(emoji_analysis),
            _render_session_drift(session_drift),
            _render_platform_limitations(platform_limitations_markdown),
        ]
    )

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title>BrandPulse Report — {_e(run_id)}</title>
<style>{_CSS}</style>
</head>
<body>
<header class="report-header">
  <h1>BrandPulse Report</h1>
  <p>Run ID: {_e(run_id)} &middot; {_e(date_range)}</p>
</header>
<div class="container">
{body}
</div>
<footer>Generated by BrandPulse. Author handles are hashed; no email addresses, phone
numbers, or BVNs are included.</footer>
</body>
</html>
"""


def write_html_report(path: str | Path, html_content: str) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html_content, encoding="utf-8")
    return path
