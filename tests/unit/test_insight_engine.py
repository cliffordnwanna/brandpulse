"""Unit tests for InsightEngine (Milestone 6) — the core of this milestone."""

from brandpulse.pipeline.insight_engine import (
    Insight,
    competitor_mentions,
    complaint_velocity,
    detect_emerging_issues,
    drift_summary,
    emoji_analysis,
    generate_insights,
    mine_phrases,
    platform_heatmap,
    sentiment_overview,
)


def _gold(mention_id, sentiment, category, **extra):
    return {
        "mention_id": mention_id,
        "classifier_version": "5a-v1",
        "sentiment": {"label": sentiment, "confidence": 0.9, "reason": "r"},
        "complaint_category": {"label": category, "confidence": 0.9, "reason": "r"},
        **extra,
    }


def _silver(mention_id, text, platform="google_play"):
    return {"mention_id": mention_id, "text": text, "platform": platform}


# --- Insight dataclass ---


def test_insight_is_a_plain_dataclass_with_expected_fields():
    insight = Insight(
        id="x",
        title="t",
        description="d",
        severity="info",
        confidence=1.0,
        data={},
        insight_type="trend",
    )
    assert insight.recommendation is None


# --- 1. Emerging Issues ---


def test_emerging_issues_no_baseline_when_no_previous_sessions():
    records = [_gold("m1", "Negative", "Transfers")]
    insights = detect_emerging_issues(records, previous_session_summaries=[])
    assert len(insights) == 1
    assert insights[0].id == "emerging_issues_no_baseline"
    assert insights[0].severity == "info"


def test_emerging_issues_detects_spike_above_threshold():
    current = [_gold(f"m{i}", "Negative", "Transfers") for i in range(10)]
    previous = [{"complaint_category_counts": {"Transfers": 4}}]

    insights = detect_emerging_issues(current, previous, spike_threshold=0.5)

    spike = next(i for i in insights if i.id == "emerging_issue_transfers")
    assert spike.severity in ("high", "critical")
    assert spike.data["current_count"] == 10
    assert spike.data["previous_average"] == 4.0


def test_emerging_issues_none_when_no_spike():
    current = [_gold("m1", "Negative", "Transfers")]
    previous = [{"complaint_category_counts": {"Transfers": 1}}]

    insights = detect_emerging_issues(current, previous, spike_threshold=0.5)

    assert any(i.id == "emerging_issues_none" for i in insights)


def test_emerging_issues_severity_critical_above_100_pct_increase():
    current = [_gold(f"m{i}", "Negative", "Fraud") for i in range(20)]
    previous = [{"complaint_category_counts": {"Fraud": 5}}]

    insights = detect_emerging_issues(current, previous, spike_threshold=0.5)
    spike = next(i for i in insights if i.id == "emerging_issue_fraud")
    assert spike.severity == "critical"


# --- 2. Complaint Velocity ---


def test_complaint_velocity_top_categories_and_trend():
    current = [_gold("m1", "Negative", "Transfers"), _gold("m2", "Negative", "Transfers")]
    previous = [{"complaint_category_counts": {"Transfers": 1}}]

    insight = complaint_velocity(current, previous, top_n=5)

    row = insight.data["top_categories"][0]
    assert row["category"] == "Transfers"
    assert row["count"] == 2
    assert row["trend"] == "up"


def test_complaint_velocity_new_category_trend():
    current = [_gold("m1", "Negative", "Fraud")]
    insight = complaint_velocity(current, previous_session_summaries=[])
    assert insight.data["top_categories"][0]["trend"] == "new"


# --- 3. Platform Heatmap ---


def test_platform_heatmap_groups_by_platform():
    records = [
        {**_gold("m1", "Negative", "Transfers"), "platform": "google_play"},
        {**_gold("m2", "Positive", "General Feedback"), "platform": "app_store"},
    ]
    insight = platform_heatmap(records)
    platforms = {p["platform"] for p in insight.data["platforms"]}
    assert platforms == {"google_play", "app_store"}


def test_platform_heatmap_computes_pct_correctly():
    records = [
        {**_gold("m1", "Negative", "Transfers"), "platform": "google_play"},
        {**_gold("m2", "Negative", "Transfers"), "platform": "google_play"},
        {**_gold("m3", "Positive", "General Feedback"), "platform": "google_play"},
    ]
    insight = platform_heatmap(records)
    row = insight.data["platforms"][0]
    assert row["negative_pct"] == round(200 / 3, 1)


# --- 4. Phrase Mining ---


def test_phrase_mining_finds_bigrams_in_negative_mentions():
    records = [
        {**_gold("m1", "Negative", "Transfers"), "text": "my transfer failed again badly"},
        {**_gold("m2", "Negative", "Transfers"), "text": "transfer failed and no refund"},
    ]
    insight = mine_phrases(records)
    phrases = {p["phrase"] for p in insight.data["phrases"]}
    assert "transfer failed" in phrases


def test_phrase_mining_excludes_positive_sentiment_text():
    records = [{**_gold("m1", "Positive", "General Feedback"), "text": "great app easy transfers"}]
    insight = mine_phrases(records)
    assert insight.data["phrases"] == []


def test_phrase_mining_includes_emoji_tokens():
    records = [
        {
            **_gold("m1", "Negative", "Transfers"),
            "text": "transfer failed :enraged_face: transfer failed :enraged_face:",
        }
    ]
    insight = mine_phrases(records)
    phrases = " ".join(p["phrase"] for p in insight.data["phrases"])
    assert ":enraged_face:" in phrases


def test_phrase_mining_empty_when_no_negative_text():
    insight = mine_phrases([])
    assert insight.data["phrases"] == []


# --- 5. Competitor Mentions ---


def test_competitor_mentions_directional_counts():
    records = [
        {**_gold("m1", "Positive", "General Feedback"), "competitor_mention": {"label": "Opay"}},
        {**_gold("m2", "Negative", "General Feedback"), "competitor_mention": {"label": "Opay"}},
    ]
    insight = competitor_mentions(records, ("Opay", "GTBank"))
    opay = next(c for c in insight.data["competitors"] if c["competitor"] == "Opay")
    assert opay["positive"] == 1
    assert opay["negative"] == 1


def test_competitor_mentions_ignores_none_label():
    records = [
        {**_gold("m1", "Positive", "General Feedback"), "competitor_mention": {"label": "None"}}
    ]
    insight = competitor_mentions(records, ("Opay",))
    assert insight.data["competitors"] == []


def test_competitor_mentions_ignores_missing_field():
    records = [_gold("m1", "Positive", "General Feedback")]
    insight = competitor_mentions(records, ("Opay",))
    assert insight.data["competitors"] == []


# --- 6. Emoji Analysis ---


def test_emoji_analysis_counts_tokens():
    records = [
        _silver("m1", "great app :smiling_face: :smiling_face:"),
        _silver("m2", "bad experience :enraged_face:"),
    ]
    insight = emoji_analysis(records)
    counts = {e["emoji"]: e["count"] for e in insight.data["emoji"]}
    assert counts[":smiling_face:"] == 2
    assert counts[":enraged_face:"] == 1


def test_emoji_analysis_empty_when_no_emoji():
    records = [_silver("m1", "plain text")]
    insight = emoji_analysis(records)
    assert insight.data["emoji"] == []


# --- 7. Sentiment Overview ---


def test_sentiment_overview_computes_distribution():
    records = [_gold("m1", "Negative", "Transfers"), _gold("m2", "Positive", "General Feedback")]
    insight = sentiment_overview(records, previous_session_summaries=[])
    assert insight.data["overall"]["Negative"]["count"] == 1
    assert insight.data["overall"]["Positive"]["count"] == 1


def test_sentiment_overview_trend_vs_previous():
    records = [_gold("m1", "Negative", "Transfers")]
    previous = [{"sentiment_distribution": {"Negative": {"pct": 20.0}}}]
    insight = sentiment_overview(records, previous)
    assert insight.data["negative_pct_change_vs_previous"] == 80.0


# --- 8. Drift Summary ---


def test_drift_summary_no_baseline():
    insight = drift_summary({"run_id": "r2"}, previous_session=None)
    assert insight.id == "drift_summary_no_baseline"


def test_drift_summary_computes_deltas():
    current = {
        "run_id": "r2",
        "sentiment_distribution": {"Negative": {"pct": 40.0}},
        "mention_counts_per_source": {"google_play": 20},
    }
    previous = {
        "run_id": "r1",
        "sentiment_distribution": {"Negative": {"pct": 20.0}},
        "mention_counts_per_source": {"google_play": 10},
    }
    insight = drift_summary(current, previous)
    assert insight.data["sentiment_pct_deltas"]["Negative"] == 20.0
    assert insight.data["volume_pct_change"] == 100.0


# --- Top-level generate_insights ---


def test_generate_insights_produces_all_sections():
    gold_records = [_gold("m1", "Negative", "Transfers")]
    silver_records = [_silver("m1", "transfer failed")]

    insights = generate_insights(
        gold_records, silver_records, ("Opay",), previous_session_summaries=[]
    )

    ids = {i.id for i in insights}
    assert "emerging_issues_no_baseline" in ids
    assert "complaint_velocity" in ids
    assert "platform_heatmap" in ids
    assert "phrase_mining" in ids
    assert "competitor_mentions" in ids
    assert "emoji_analysis" in ids
    assert "sentiment_overview" in ids


def test_generate_insights_joins_gold_with_silver_text():
    """Gold has no 'text' field of its own — generate_insights must join it
    back from Silver via mention_id for phrase mining/word cloud to work."""
    gold_records = [_gold("m1", "Negative", "Transfers")]
    silver_records = [_silver("m1", "transfer failed repeatedly")]

    insights = generate_insights(gold_records, silver_records, (), previous_session_summaries=[])

    phrase_insight = next(i for i in insights if i.id == "phrase_mining")
    phrases = " ".join(p["phrase"] for p in phrase_insight.data["phrases"])
    assert "transfer failed" in phrases


def test_generate_insights_skips_gold_record_with_no_matching_silver():
    gold_records = [_gold("orphan", "Negative", "Transfers")]
    insights = generate_insights(gold_records, [], (), previous_session_summaries=[])
    sentiment_insight = next(i for i in insights if i.id == "sentiment_overview")
    assert sentiment_insight.data["overall"] == {}
