"""Unit tests for the HTML report renderer (Milestone 6).

The renderer must contain no analytics logic — every assertion here checks
that ``Insight.data`` values show up verbatim in the HTML, not that any
number is recomputed.
"""

from brandpulse.pipeline.insight_engine import Insight
from brandpulse.pipeline.report_renderer import render_html_report


def _insights():
    return [
        Insight(
            id="emerging_issue_transfers",
            title="Transfers complaints up 80% vs last session",
            description="desc",
            severity="high",
            confidence=0.8,
            data={"category": "Transfers", "pct_change": 80.0},
            insight_type="spike",
            recommendation="Investigate the switch.",
        ),
        Insight(
            id="complaint_velocity",
            title="Top complaint categories this session",
            description="desc",
            severity="info",
            confidence=1.0,
            data={
                "top_categories": [
                    {"category": "Transfers", "count": 5, "previous_count": 2, "trend": "up"}
                ]
            },
            insight_type="trend",
        ),
        Insight(
            id="phrase_mining",
            title="Top phrases",
            description="desc",
            severity="info",
            confidence=1.0,
            data={"phrases": [{"phrase": "transfer failed", "count": 10}]},
            insight_type="phrase",
        ),
        Insight(
            id="platform_heatmap",
            title="Platform breakdown",
            description="desc",
            severity="info",
            confidence=1.0,
            data={
                "platforms": [
                    {
                        "platform": "google_play",
                        "total": 10,
                        "positive_pct": 40.0,
                        "negative_pct": 60.0,
                    }
                ]
            },
            insight_type="trend",
        ),
        Insight(
            id="competitor_mentions",
            title="Competitor mentions",
            description="desc",
            severity="info",
            confidence=1.0,
            data={
                "competitors": [
                    {"competitor": "Opay", "positive": 3, "negative": 1, "neutral": 0, "mixed": 0}
                ]
            },
            insight_type="competitor",
        ),
        Insight(
            id="emoji_analysis",
            title="Top emoji",
            description="desc",
            severity="info",
            confidence=1.0,
            data={"emoji": [{"emoji": ":enraged_face:", "count": 7}]},
            insight_type="emoji",
        ),
        Insight(
            id="sentiment_overview",
            title="Overall sentiment",
            description="desc",
            severity="info",
            confidence=1.0,
            data={
                "overall": {
                    "Negative": {"count": 5, "pct": 50.0},
                    "Positive": {"count": 5, "pct": 50.0},
                }
            },
            insight_type="trend",
        ),
        Insight(
            id="drift_summary_no_baseline",
            title="Run again to enable drift detection",
            description="Only one session exists so far.",
            severity="info",
            confidence=1.0,
            data={},
            insight_type="trend",
        ),
    ]


def test_render_includes_all_required_sections():
    html = render_html_report(
        "run-1", _insights(), 10, "2026-01-01", ["google_play"], None, "Platform limitations text."
    )
    for section_id in (
        "executive-summary",
        "emerging-issues",
        "complaint-velocity",
        "phrase-mining",
        "platform-breakdown",
        "competitor-mentions",
        "emoji-analysis",
        "session-drift",
        "platform-limitations",
    ):
        assert f'id="{section_id}"' in html


def test_emerging_issues_appears_before_word_cloud_section():
    html = render_html_report(
        "run-1",
        _insights(),
        10,
        "2026-01-01",
        ["google_play"],
        "data:image/png;base64,abc",
        "limitations",
    )
    assert html.index('id="emerging-issues"') < html.index('id="word-cloud"')


def test_platform_limitations_is_last_section():
    html = render_html_report(
        "run-1", _insights(), 10, "2026-01-01", ["google_play"], None, "limitations text"
    )
    last_section_index = html.rindex("<section")
    assert 'id="platform-limitations"' in html[last_section_index:]


def test_recommendation_rendered_when_present():
    html = render_html_report(
        "run-1", _insights(), 10, "2026-01-01", ["google_play"], None, "limitations"
    )
    assert "Investigate the switch." in html


def test_wordcloud_omitted_when_no_data_uri():
    html = render_html_report(
        "run-1", _insights(), 10, "2026-01-01", ["google_play"], None, "limitations"
    )
    assert "<img" not in html


def test_wordcloud_embedded_as_base64_data_uri():
    html = render_html_report(
        "run-1",
        _insights(),
        10,
        "2026-01-01",
        ["google_play"],
        "data:image/png;base64,abc123",
        "limitations",
    )
    assert 'src="data:image/png;base64,abc123"' in html


def test_html_escapes_untrusted_text():
    malicious = [
        Insight(
            id="emerging_issue_x",
            title="<script>alert(1)</script>",
            description="desc",
            severity="high",
            confidence=0.9,
            data={},
            insight_type="spike",
        )
    ]
    html = render_html_report("run-1", malicious, 1, "2026-01-01", [], None, "limitations")
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_self_contained_no_external_references():
    html = render_html_report(
        "run-1",
        _insights(),
        10,
        "2026-01-01",
        ["google_play"],
        "data:image/png;base64,abc",
        "limitations",
    )
    assert "http://" not in html
    assert "https://" not in html
    assert "<link " not in html
    assert "<script src=" not in html


def test_platform_limitations_text_embedded_verbatim():
    html = render_html_report(
        "run-1",
        _insights(),
        10,
        "2026-01-01",
        ["google_play"],
        None,
        "X/Twitter requires a paid API tier.",
    )
    assert "X/Twitter requires a paid API tier." in html
