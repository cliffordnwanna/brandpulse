# Milestone 6 — Insight Engine + HTML Report

## Objective
Build the layer that turns Gold records into actionable insights, and an HTML renderer that presents those insights to executives. The key architectural requirement: **insights are computed once, rendering is separate**. The HTML renderer is the only renderer for MVP, but the InsightEngine must be usable by any future renderer (PDF, Power BI, Slack, Teams) without modification.

## Read first
- `docs/EngineeringDesign.md` §14 (Output Files), §12 (Search Strategy)
- Milestone 5's Gold record shape, session log format, classification output fields
- `CLAUDE.md` Architecture Invariants

---

## CLI (implement all five commands)

```bash
python -m brandpulse run                    # incremental scrape + classify (default)
python -m brandpulse run --fresh            # full re-scrape, ignore existing Bronze
python -m brandpulse classify               # classify existing Silver without scraping
python -m brandpulse report                 # generate report from existing Gold, no scraping
python -m brandpulse compare                # drift report: current session vs previous
python -m brandpulse export --format csv    # export Gold to CSV/JSON only, no HTML
```

**Separation rule:** `run` stops at Gold. `report` reads Gold and produces output. They must work independently — someone should be able to run `report` 10 times on the same Gold data and get the same output.

---

## Step 1 — Emoji normalization (implement first, before anything else)

Apply in the Silver pipeline's text cleaning step so every downstream stage sees normalized text:

```python
import emoji
emoji.demojize("😡😡😡") → ":angry_face: :angry_face: :angry_face:"
```

**Never strip emojis — normalize them.** In Nigerian social media text, emojis carry real sentiment signal. `:loudly_crying_face:` in the word cloud and phrase mining is correct — it represents actual customer expression.

Also add to the emoji analysis insight (see §InsightEngine below): count the top 20 emoji tokens across all mentions and show frequency. `😭 × 152`, `😡 × 94` is genuinely valuable signal.

---

## InsightEngine (the core of this milestone)

A dedicated module (`pipeline/insight_engine.py`) that reads Gold records and produces structured `Insight` objects. **Never produces HTML** — that's the renderer's job.

```python
@dataclass
class Insight:
    id: str                          # e.g. "complaint_velocity_transfers"
    title: str                       # e.g. "Transfer complaints up 84% this week"
    description: str                 # plain English, executive-readable
    severity: Literal["critical", "high", "medium", "low", "info"]
    confidence: float
    data: dict                       # raw numbers the renderer can use for charts
    insight_type: str                # "trend" | "spike" | "complaint" | "competitor" | "phrase" | "emoji"
    recommendation: str | None       # only populated when LLM enrichment enabled
```

### Insights the engine must produce (in priority order for the report):

**1. Emerging Issues / Anomaly Detection** ← put this first, not the word cloud
Detect complaint categories where current session volume is >50% higher than the previous session average. Example output:
```
Title: "Transfer failures up 84% vs last session"
Severity: high
Recommendation: "Investigate switch downtime between 2pm–5pm"
```
If no previous session exists → `Insight(title="First run — no baseline yet", severity="info")`.

**2. Complaint Velocity**
Top 5 complaint categories by volume + trend direction vs. previous session.

**3. Platform Heatmap**
Per-platform mention count and sentiment split. Which platform has the most complaints? Which has the most positive mentions?

**4. Phrase Mining** ← more actionable than word cloud
Top 50 bigrams and trigrams from complaint text, ranked by frequency:
```
"failed transfer"     84 mentions
"customer service"    71 mentions
"unable to login"     43 mentions
"money not reversed"  38 mentions
```
Use `nltk` or `sklearn` `CountVectorizer` for n-gram extraction.

**5. Competitor Mentions**
For each competitor mentioned (GTBank, Access, UBA, FirstBank, Opay, Moniepoint — from taxonomy):
```
Opay:      34 positive / 2 negative mentions
Moniepoint: 18 positive / 4 negative mentions
```
Direction matters — is the competitor being praised in the same breath a customer complains about us?

**6. Emoji Analysis**
Top 20 emoji tokens by frequency across all mentions. This is a uniquely Nigerian social media signal.

**7. Sentiment Overview**
Overall split + per-platform split. Trend vs previous session.

**8. Drift Summary** (for `compare` command)
Session-over-session changes in sentiment distribution, complaint category distribution, volume per source.

### Recommendation generation
```yaml
classification:
  enrichment:
    recommendations: false    # set true to have LLM generate Insight.recommendation
```
When disabled: `recommendation = None`. Template-based fallback is acceptable but optional.
When enabled: one LLM call per high/critical insight, using `prompts/recommendation_v1.txt`.

---

## Report Renderer (HTML only for MVP)

Reads a list of `Insight` objects and produces a self-contained HTML file. **No external dependencies** — CSS and charts inline, word cloud embedded as base64. Must open correctly with no internet connection (safe to email or put on a USB drive).

### Report sections (in this order):
1. **Executive Summary** — total mentions, date range, sources covered, top 3 complaint categories, one-line sentiment verdict
2. **Emerging Issues** — the anomaly/spike insights, most severe first
3. **Complaint Velocity** — bar chart of top complaint categories + trend arrows
4. **Phrase Mining** — top 20 phrases as a styled table
5. **Platform Breakdown** — per-source counts and sentiment
6. **Word Cloud** — generated from Gold text after stopword removal, emoji tokens included; save as PNG at 1200×600, embed as base64
7. **Competitor Mentions** — directional (positive/negative per competitor)
8. **Emoji Analysis** — frequency chart of top emoji tokens
9. **Session Drift** — if 2+ sessions: trend charts; if 1 session: "Run again to enable drift detection"
10. **Platform Limitations** — always present, always last

### Word cloud implementation:
- `wordcloud` Python library
- Include emoji tokens (`:angry_face:` appears as a word — correct)
- Exclude: bank/product name variants (searching for "Wema" in a Wema report is noise), pure stopwords
- Sentiment-weighted coloring where possible (negative words → warmer tones)
- Min frequency: 3; max words: 150; background: white

### Privacy (mandatory):
- Hash author handles: `@john_doe` → `User#48291` (SHA256 first 5 hex chars, consistent within a run)
- Anonymization check before every output write: regex scan for email addresses, Nigerian phone numbers (08xx, +234xx), BVN patterns (11-digit numbers). Log a warning if found — never silently drop.

---

## Output files

```
output/
  mentions.csv
  classifications.csv
  summary.csv
  errors.csv
  metrics.csv               # only if eval/labeled_v1.csv exists — skip with warning if not
  connector_health.csv
  run_metadata.json
  sessions/{run_id}.json

  reports/
    {run_id}_report.html    # self-contained HTML
    {run_id}_wordcloud.png  # also embedded in HTML
    {run_id}_phrases.csv    # top 50 phrases
    {run_id}_insights.json  # raw Insight objects — for future renderers / Power BI
    platform_limitations.md # always included
```

`{run_id}_insights.json` is the bridge to future renderers. A Power BI connector, a Slack bot, or a PDF renderer in Phase 2 reads this file, not the HTML.

---

## Platform limitations doc
Create `docs/platform-limitations.md` — plain language explanation per platform, plus the table below. Copied into `output/reports/` with every run.

| Platform | Status | Reason | Official docs |
|---|---|---|---|
| X/Twitter | Paid API required | Basic tier ~$100/month minimum | https://developer.twitter.com/en/docs/twitter-api |
| Instagram | Page admin access required | Meta Graph API needs page access token | https://developers.facebook.com/docs/instagram-api |
| Facebook | Page admin access required | Meta Graph API needs page access token | https://developers.facebook.com/docs/graph-api |
| TikTok | Research API approval required | Application review process, not instant | https://developers.tiktok.com/doc/overview |

---

## Taxonomy externalization (from reviewer feedback)
Move the complaint taxonomy out of Python and into `config/taxonomy.yaml`:
```yaml
complaint_categories:
  - Transfers
  - Debit Issues
  - Credit Delay
  - Login Issues
  - App Crash
  - Card Problems
  - ATM
  - POS
  - USSD
  - Fraud
  - Loans
  - Customer Service
  - Branches
  - Charges
  - Account Opening
  - KYC
  - General Feedback
  - Competitor Mention

competitors:
  - GTBank
  - Access Bank
  - UBA
  - FirstBank
  - Opay
  - Moniepoint
  - Kuda
  - Palmpay
```
The classification pipeline reads this file. A different organization can customize it without touching code.

---

## Explicitly out of scope
- No web server, no live dashboard — static files only
- No PDF, email, Teams, or Slack renderers — those are Phase 2
- No new connectors
- No real-time streaming

## Dependency note (added by Claude Code before implementation)
`wordcloud`, `scikit-learn`, and `emoji` are installed and used directly (real implementations, no fallbacks — confirmed with Clifford before implementation). Phrase mining uses `sklearn.feature_extraction.text.CountVectorizer` with its built-in English stopword list rather than `nltk`'s stopword corpus, to avoid a separate `nltk.download()` step at runtime — `sklearn` was already a Milestone 5 dependency reused here for a small win, functionally equivalent for this purpose.

`classification.enrichment.recommendations` from the spec's YAML sample is implemented as a flat `classification.recommendations: bool` field on `ClassificationConfig`, consistent with this project's existing flat config style (`enable_enrichment`, `confidence_threshold`, etc. are already flat, not nested under an `enrichment:` block).

## Acceptance Criteria
- [ ] All five CLI commands work independently
- [ ] `report` command runs on existing Gold without touching the scraper or classifier
- [ ] InsightEngine produces structured `Insight` objects (not HTML)
- [ ] HTML renderer consumes `Insight` objects — no analytics logic inside the renderer
- [ ] `{run_id}_insights.json` produced alongside the HTML (future-renderer bridge)
- [ ] Emerging issues / anomaly detection is the first section in the report
- [ ] Phrase mining produces top 50 bigrams/trigrams
- [ ] Competitor mentions show directional sentiment (positive/negative counts per competitor)
- [ ] Emoji tokens normalized and appear in word cloud and phrase mining
- [ ] Author handles hashed in all output
- [ ] Anonymization check runs before every output write
- [ ] Platform limitations section always present in HTML report
- [ ] Drift section present (graceful "first run" message when only one session exists)
- [ ] `config/taxonomy.yaml` exists and is the sole source of complaint categories and competitor list
- [ ] HTML report is self-contained — opens with no internet connection
- [ ] Full test suite passes; new tests cover InsightEngine outputs, emoji normalization, anonymization check, phrase mining, drift detection
- [ ] `docs/platform-limitations.md` created

## Stop condition
Stop when all acceptance criteria are met. Update `TASKS.md`. Do not proceed to Milestone 7 without review.
