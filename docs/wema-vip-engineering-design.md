# Wema Customer Voice Intelligence Platform (WVIP)
## Engineering Design Document — v2.0
**Companion to:** PRD v2.2
**Purpose:** The PRD answers *what we're building and why*. This document answers *how every component works*, in enough detail that a senior engineer (or Claude Code) can build it without guessing. Nothing here changes the PRD's phases, metrics, or scope — this is the implementation contract underneath it.

**Changelog v1.0 → v2.0:** Added Source Registry (§4) to own source metadata/priority/scheduling instead of the orchestrator knowing everything. Added Orchestration State & Idempotency (§5) — content-hash `mention_id`, run/connector checkpointing and resume — built now rather than deferred to Phase 2. Strengthened the connector contract (§3) to guarantee de-duplication, UTF-8 validity, and timestamp/timezone normalization before Bronze, while `raw_json` continues to preserve the untouched original payload. Added a Classification Queue (§10) between Silver and classification so ingestion never blocks on classification throughput. Made LLM usage conditional (§10) — NaijaBERT handles sentiment for every mention; the LLM is reserved for summaries, unknown-topic overflow, and low-confidence/ambiguous cases only. Added global rate limiting (§8), connector contract tests (§20), a connector health CSV (§7), and a new §23 Architecture Invariants section. MVP now includes YouTube as a fourth connector, and dedup/checkpointing/queueing are built in the MVP itself, not deferred to Phase 2.

---

## 1. Component Boundaries

```
┌──────────────────────────────────────────────────────────────┐
│  Source Registry (enabled sources, priority, schedule, health)   │
└───────────────┬──────────────────────────────────────────────┘
                │
┌───────────────▼──────────────────────────────────────────────┐
│  Orchestrator (job queue + scheduler + run/connector state)      │
└───────────────┬──────────────────────────────────────────────┘
                │
┌───────────────▼──────────────────────────────────────────────┐
│  Connector Layer (one module per source, common interface)      │
│  Each connector: search() → normalize() → validate() → health() │
│  Contract: dedupes exact matches, UTF-8-safe, timestamp/tz        │
│  normalized, before handing records to Bronze (§3)                │
└───────────────┬──────────────────────────────────────────────┘
                │  emits: canonical Mention records (§2)
┌───────────────▼──────────────────────────────────────────────┐
│  Bronze Store — lightly normalized per connector contract,       │
│  raw_json field preserves the untouched original payload          │
└───────────────┬──────────────────────────────────────────────┘
                │
┌───────────────▼──────────────────────────────────────────────┐
│  Silver Pipeline — near-duplicate detection, language-detect      │
└───────────────┬──────────────────────────────────────────────┘
                │
┌───────────────▼──────────────────────────────────────────────┐
│  Classification Queue — workers, so ingestion never blocks        │
│  on classification throughput (§10)                                │
└───────────────┬──────────────────────────────────────────────┘
                │
┌───────────────▼──────────────────────────────────────────────┐
│  Classification Pipeline — staged, independent steps;             │
│  NaijaBERT always, LLM only for summaries/unknowns/ambiguity (§10) │
└───────────────┬──────────────────────────────────────────────┘
                │
┌───────────────▼──────────────────────────────────────────────┐
│  Gold Store — analytics-ready, versioned classifications         │
└───────────────┬──────────────────────────────────────────────┘
                │
┌───────────────▼──────────────────────────────────────────────┐
│  Output Layer — CSV set (MVP) / Power BI semantic model (Phase 2) │
└──────────────────────────────────────────────────────────────┘
```

Each layer only talks to the layer directly above/below it through the canonical schema — a connector never knows about the classification pipeline, and the classification pipeline never knows where data came from beyond its `platform`/`reliability` fields. This is what lets sources grow from 4 to 40 without touching anything downstream.

---

## 2. Canonical Data Contract

Every connector, regardless of source, emits exactly this schema. No exceptions — a connector that can't populate a field emits `null`, it doesn't invent a different shape.

```json
{
  "mention_id": "SHA256 hash of (platform, url, timestamp, normalized_text) — see §5",
  "platform": "google_play | app_store | nairaland | youtube | reddit | ...",
  "source_type": "review | comment | post | forum_reply",
  "search_term": "the keyword/query that surfaced this record",
  "author": "public handle or reviewer name — never a real customer identity",
  "url": "canonical link back to the original content",
  "text": "comment/review text, UTF-8-safe and lightly normalized per connector contract (§3)",
  "language": "detected in Silver stage — null at Bronze",
  "timestamp": "when the content was originally posted (source-reported, normalized to UTC)",
  "scraped_at": "when our connector retrieved it",
  "raw_json": "full untouched response payload from the source, as a string",
  "reliability": "high | medium | low — set per source, see PRD §9.3",
  "connector_version": "semver of the connector that produced this record",
  "metadata": { "...source-specific fields, e.g. star_rating, app_version, upvotes" }
}
```

This is the single most important design decision in the system: **everything downstream assumes this shape and nothing else.**

---

## 3. Connector Interface

```python
class BaseConnector(ABC):
    name: str
    version: str
    reliability: Literal["high", "medium", "low"]

    def search(self, keywords: list[str], start: datetime, end: datetime) -> RunResult:
        """Executes the search/scrape. Returns a RunResult, never raises on
        expected failure modes (timeouts, empty results, blocked requests)."""

    def normalize(self, raw_item: Any) -> Mention:
        """Converts one source-native record into the canonical schema (§2)."""

    def validate(self, mention: Mention) -> bool:
        """Rejects malformed records before they reach Bronze — e.g. empty
        text, missing mention_id, timestamp outside the requested window."""

    def health(self) -> HealthStatus:
        """Lightweight check the orchestrator can call before a full run —
        e.g. 'can I reach this endpoint at all right now.'"""
```

**Connector contract — guaranteed before a record reaches Bronze:**
- No exact duplicates within the connector's own batch (same `url`, or same `(platform, author, text)` tuple)
- Text is UTF-8-safe (no corrupted bytes/mojibake)
- `timestamp` normalized to UTC, timezone-aware
- `text` lightly cleaned (whitespace-collapsed, control characters stripped) — **note this is normalization, not content rewriting**; the original content itself is never altered or summarized
- `raw_json` always carries the fully untouched original payload, regardless of what normalization happened to the canonical fields — so nothing is ever actually lost, even though Bronze is no longer "raw" in the strictest sense

Every source lives in its own file under `connectors/`, subclassing `BaseConnector`. The Source Registry (§4) auto-discovers connectors at startup (directory scan, no `if platform == "reddit"` branching anywhere in the codebase). Adding Reddit later is a new file, not a rewrite.

```
connectors/
  __init__.py          # auto-discovery loader
  base.py               # BaseConnector, RunResult, HealthStatus
  google_play.py
  app_store.py
  nairaland.py
  youtube.py
  reddit.py             # added in Phase 2
  ...
```

---

## 4. Source Registry

A dedicated component — not the orchestrator's implicit knowledge — owning everything about *which* sources exist and *how* they should run:

```python
class SourceRegistry:
    def enabled_sources(self) -> list[SourceConfig]: ...
    def priority(self, source_name: str) -> int: ...
    def schedule(self, source_name: str) -> Schedule: ...
    def health_status(self, source_name: str) -> HealthStatus: ...
    def reliability(self, source_name: str) -> Literal["high", "medium", "low"]: ...
```

Backed by the `sources:` block in `config.yaml` (§8) plus live health data from each connector's `health()` call. The orchestrator asks the registry "what should I run, in what order, how often" instead of holding that logic itself — this is what lets source count grow without the orchestrator's code changing at all.

---

## 5. Orchestration State & Idempotency

Two related concerns, both built into the MVP from day one because retrofitting either after real data exists is expensive.

**Idempotency — content-hash `mention_id`:**
```
mention_id = SHA256(platform + url + timestamp + normalized_text)
```
Re-running a connector (deliberately or after a crash) produces the same `mention_id` for the same underlying content, so Bronze/Silver/Gold writes are naturally idempotent — a second write with the same ID is a no-op, not a duplicate row. This is the single design decision that makes "what if the same job runs twice" a non-issue everywhere downstream.

**Run state & checkpointing:**
```
Run           — one execution of the orchestrator (run_id, started_at, keyword set, timeframe)
Connector State — per-connector, per-run: last successful page/batch, records written so far
Checkpoint     — written after every successful batch, not just at run end
Resume Position — on restart, each connector resumes from its own last checkpoint, not from zero
```
If Google Play returns 300 reviews and crashes on review 301, a restart resumes from the checkpoint rather than re-fetching (and re-processing) the first 300. Combined with idempotent `mention_id`s, even a full re-run from scratch is safe — it just re-confirms records that already exist rather than duplicating them.

**Incremental ingestion:** each connector's state also tracks `last_successful_timestamp` per keyword. Scheduled runs (Phase 2, and optionally MVP if run repeatedly) fetch only records newer than that timestamp instead of re-searching the entire window every time.

---

## 6. Failure Strategy

`search()` never raises for expected failure modes. It returns one of:

| Status | Meaning | Orchestrator behavior |
|---|---|---|
| `SUCCESS` | Results returned, no issues | Proceed to Bronze write, advance checkpoint |
| `PARTIAL_SUCCESS` | Some results returned, some pages/requests failed | Write what succeeded, checkpoint that progress, log the gap, don't retry the whole run |
| `FAILED` | Nothing usable returned (timeout, blocked, HTML changed) | Log with reason, retry per policy below from last checkpoint, alert if retries exhausted |
| `NO_RESULTS` | Ran fine, genuinely nothing matched | Log as normal — not an error, checkpoint still advances |

**Retry policy:** exponential backoff, max 3 attempts, only for `FAILED` — never retry `NO_RESULTS`. A connector that fails 3 consecutive scheduled runs is auto-disabled (via the Source Registry, §4) and flagged for manual review (likely a source-side HTML/API change) rather than silently retried forever.

**Specific failure modes to handle explicitly per connector:** request timeout, HTTP 4xx/5xx, HTML structure changed (parse failure), CAPTCHA/bot-check triggered, network interruption, rate-limit response (back off and reschedule, don't treat as `FAILED`).

---

## 7. Observability & Logging

Structured (JSON) logs, one line per event, so they're queryable rather than just readable:

```json
{"event": "connector_run_start", "connector": "google_play", "search_term": "ALAT", "run_id": "..."}
{"event": "connector_run_end", "connector": "google_play", "status": "SUCCESS", "duration_s": 18, "result_count": 241}
{"event": "connector_run_end", "connector": "nairaland", "status": "FAILED", "reason": "html_structure_changed"}
```

Every run produces a `run_metadata.json` **and** a `connector_health.csv` (see §14) — the latter specifically so connector health (healthy/failed/latency/records) is glanceable without opening logs at all, even though the MVP has no dashboard yet.

---

## 8. Configuration Layer

Nothing hardcoded. One `config.yaml` (or per-environment override) drives:

```yaml
sources:
  - name: google_play
    enabled: true
    reliability: high
  - name: app_store
    enabled: true
    reliability: high
  - name: nairaland
    enabled: true
    reliability: medium
  - name: youtube
    enabled: true
    reliability: high

keywords:
  base_list: ["Wema", "Wema Bank", "ALAT", "ALAT by Wema", "Wema fraud", ...]
  # user-supplied keywords at MVP runtime are merged with, not replacing, this base list

output:
  directory: "./output/"
  formats: ["csv", "json"]

retry:
  max_attempts: 3
  backoff_seconds: [5, 30, 120]

timeouts:
  request_seconds: 20

rate_limit:
  # global, not per-connector — one shared limiter the Source Registry allocates
  # requests across, so a burst on one source can't starve another
  requests_per_minute: 60
  respect_robots_txt: true
```

---

## 9. Storage Design — Bronze / Silver / Gold

| Layer | Contents | Mutability |
|---|---|---|
| **Bronze** | Connector-normalized records per the contract in §3 (deduped within-batch, UTF-8-safe, timestamps normalized) — `raw_json` preserves the fully untouched original payload alongside it | Append-only, never modified or deleted; idempotent writes via content-hash `mention_id` (§5) |
| **Silver** | Cross-source/cross-run near-duplicate detection, language-detected records in the canonical schema | Derived from Bronze; can be fully regenerated by reprocessing Bronze |
| **Gold** | Classified, versioned, analytics-ready — joins Silver records with classification outputs | Derived from Silver; regenerated whenever the classifier version changes |

**Why Bronze still matters even though it's lightly normalized:** the connector contract only touches encoding/timestamp/exact-duplicate concerns — the actual comment/review text is never rewritten or summarized, and `raw_json` guarantees the true original payload is always recoverable. So reprocessing Silver/Gold from Bronze remains fully possible; what changed is only that Bronze no longer carries broken encodings, wrong timezones, or trivial repeat rows.

---

## 10. Classification Pipeline — Staged, Independent Steps, Queued, LLM-Optional

**Classification Queue:** Silver output lands in a queue rather than being classified inline during ingestion — so a slow classification stage (or an LLM call) never blocks connectors from continuing to collect. Workers pull from the queue independently:

```
Silver output → Classification Queue → Workers → Gold
```

Locally in MVP this is a simple async/multiprocessing queue; in Phase 2 it maps onto Fabric-native scheduling. Same interface either way.

**Staged pipeline**, each stage its own function/module with its own input/output contract:

```
Language Detection
        ↓
Translation (Pidgin/Yoruba/Hausa/Igbo → normalized, only where the LLM stage needs it)
        ↓
Sentiment (NaijaBERT — always runs, every mention, no LLM call)
        ↓
Emotion (NaijaBERT/rule-based — always runs)
        ↓
Intent
        ↓
Complaint Category (predefined taxonomy match first; BERTopic zero-shot only for overflow)
        ↓
Product Mentioned
        ↓
Severity/Urgency
        ↓
Competitor Mention
        ↓
Summary (LLM — only stage that always uses one)
```

**LLM usage is conditional, not default.** NaijaBERT (free, fast, purpose-built for Nigerian Pidgin/English) handles sentiment and emotion for every mention. The LLM (Groq-hosted) is reserved for exactly three cases:
1. Generating the human-readable **summary** field
2. Classifying mentions that fall into the **unknown/emerging topic** overflow (didn't match the predefined taxonomy)
3. Re-checking **low-confidence** NaijaBERT predictions (below a configurable confidence threshold)

This keeps the common case — "great app" / "bad transfer" — cheap and fast, and spends LLM tokens only where they add real value, which is most of the cost savings identified in the PRD's cost model.

Each stage outputs its result plus a **confidence score** and a **reason** — not just a label:

```json
{
  "stage": "sentiment",
  "label": "Negative",
  "confidence": 0.91,
  "reason": "Contains complaint about failed transfer and unresponsive customer care."
}
```

---

## 11. Deduplication Strategy

Two tiers, split by where they run:

1. **Connector-level, before Bronze (mandatory, §3 contract):** exact match on `url` or `(platform, author, text)` — dropped within the connector's own batch before it ever reaches Bronze.
2. **Silver-level, across sources/runs:** near-duplicate detection — text hash (normalized, whitespace-collapsed) for likely duplicates flagged for review, plus embedding-similarity matching for near-identical reposts (e.g. the same complaint reworded slightly). Built into the MVP itself, not deferred to Phase 2 scale, per the production-hardening decision.

Idempotent `mention_id` (§5) is a third layer underneath both of these — even if tiers 1 and 2 both somehow miss a duplicate, a genuinely identical record still can't produce two Bronze/Silver/Gold rows.

---

## 12. Search Strategy

MVP supports keyword search (a keyword list + timeframe, as specified). Phase 2 adds:
- **Boolean** (`"Wema" OR "ALAT"`, `"Wema" AND "fraud"`)
- **Regex** for pattern-based misspelling capture (e.g. `Wem[ao]`)

The base keyword list lives in config (§8); user-supplied MVP keywords are merged with it at runtime, never replacing it.

---

## 13. Versioning (everything, always)

- **Connector version** — bumped on any change to a connector's scraping/parsing logic; stored per-record in Bronze.
- **Classifier version** — bumped on any model/prompt change.
- **Prompt version** — every LLM prompt lives in a versioned file (`prompts/complaint_classification_v1.txt`, `v2.txt`...), never edited in place.
- **Data versioning** — classifications are **never overwritten**. A new classifier version produces a new Gold record (`classification_v1`, `classification_v2`...) alongside the old one, so you can compare "did v2 actually improve things" against the same underlying Silver record.

This is what answers the "why did predictions change six months from now" problem directly.

---

## 14. Output Files (MVP and Phase 2)

Instead of a single `mentions.csv`, every run produces:

```
mentions.csv            # raw normalized mentions (Silver)
classifications.csv     # one row per mention per classification stage, versioned
summary.csv             # aggregated counts by sentiment/category/platform
errors.csv              # every FAILED/PARTIAL_SUCCESS event with reason
metrics.csv             # accuracy/precision/recall/F1 against the labeled set, if evaluation was run
connector_health.csv     # per-connector: healthy/failed, latency, record count, last checkpoint
run_metadata.json         # per-connector status, duration, result counts, config used
```

This makes debugging a bad run (or explaining a good one) possible without re-running anything.

---

## 15. Human Validation & Evaluation Framework

- **Labeled set: 500 hand-labeled mentions**, covering classes: `Positive, Negative, Neutral, Mixed, Spam`. Spam/off-topic matters because scraped forum/review data will contain noise that isn't about Wema/ALAT at all.
- Stored as a fixed, versioned reference set (`eval/labeled_v1.csv`) — reused across every classifier version so improvements are measured against the same ground truth.
- **Every release runs an automatic evaluation** against this set, producing: accuracy, precision, recall, F1, and a confusion matrix — written to `metrics.csv` (§14). This is what tells you whether classifier v2 actually improved on v1, rather than just "feels better."

---

## 16. Prompt Management

Every LLM prompt used in the classification pipeline is a versioned file, never a hardcoded string:
```
prompts/
  sentiment_fallback_v1.txt      # only used for low-confidence NaijaBERT cases
  complaint_classification_v1.txt
  complaint_classification_v2.txt   # kept alongside v1, not overwritten
  summary_v1.txt
```
The Gold record stores which prompt version produced each classification (§13), so a prompt change is auditable the same way a model change is.

---

## 17. Security

- **Respect `robots.txt`** for every scraped source — checked programmatically before a connector runs, not just a policy statement.
- **Rate limiting**: global limiter (§8), enforced in the connector base class via the Source Registry, not left to each connector to remember or to per-connector config that can drift out of sync.
- **Request delays**: randomized delay between requests to avoid hammering a source.
- **User agent**: identifies the scraper honestly rather than spoofing a browser, where the source's terms make that appropriate; documented per-connector where a real browser UA is required for the page to render at all.
- No credentials, API keys, or proxy configuration ever committed to the repo — environment variables / secrets manager only.

---

## 18. Ingestion Job Queue

Even running locally, connectors are queued rather than executed as one long sequential script:

```
Search Jobs (one per source × keyword batch)
        ↓
Worker Pool (local: simple async/thread pool; Phase 2: Fabric-native scheduling)
        ↓
Results → Bronze
```

This keeps a slow source (e.g. Nairaland pagination) from blocking a fast one (e.g. Google Play), and gives a natural place to plug in real distributed workers later without restructuring anything. This is distinct from the Classification Queue (§10), which sits further downstream between Silver and the classification stages.

---

## 19. Directory Structure (MVP repo)

```
wema-vip/
  connectors/
    base.py
    google_play.py
    app_store.py
    nairaland.py
    youtube.py
  registry/
    source_registry.py
  orchestration/
    orchestrator.py
    state.py              # run state, connector state, checkpoints
    idempotency.py         # mention_id hashing
    job_queue.py            # ingestion job queue (§18)
  pipeline/
    clean.py
    dedupe.py               # tier 2 (Silver-level) dedup, §11
    language_detect.py
    classification_queue.py  # §10
    classify/
      sentiment.py
      emotion.py
      complaint.py
      severity.py
      summary.py             # only stage that always calls the LLM
  prompts/
    sentiment_fallback_v1.txt
    complaint_classification_v1.txt
    summary_v1.txt
  eval/
    labeled_v1.csv
    evaluate.py
  config/
    config.yaml
  storage/
    bronze/
    silver/
    gold/
  output/
    mentions.csv
    classifications.csv
    summary.csv
    errors.csv
    metrics.csv
    connector_health.csv
    run_metadata.json
  cli.py            # keyword + timeframe entry point
  tests/
    unit/
    contract/          # shared connector contract tests, §20
    integration/
    e2e/
```

---

## 20. Testing Strategy

- **Unit tests**: each connector's `normalize()`/`validate()` against fixture data (saved real responses, not live calls); each classification stage against known input/output pairs.
- **Contract tests**: one shared test suite every connector must pass — `search()` returns a valid `RunResult`, `normalize()` output matches the canonical schema exactly, `validate()` rejects malformed input, `health()` responds — run before any connector is merged, not just informally checked.
- **Integration tests**: one connector end-to-end against a live source (rate-limited, run sparingly, not on every commit).
- **End-to-end tests**: full pipeline against a small fixed keyword/timeframe, asserting the output files exist and have the expected shape — not asserting exact classification results, since those can shift with model updates.
- **Evaluation runs** (§15) are separate from tests — they measure model quality, not code correctness.

---

## 21. Deployment Strategy

| Phase | Deployment |
|---|---|
| MVP | Runs from Clifford's repo, local execution or a simple scheduled cron if desired — no cloud dependency required |
| Phase 2 | Fabric Data Pipeline triggers the same connector/pipeline code, now writing to Fabric Lakehouse Bronze/Silver/Gold instead of local folders — the connector and classification code itself doesn't need to change, only the storage layer target |
| Phase 3 | TBD, pending governance sign-off (see PRD §11) |

The MVP and Phase 2 codebases should be **the same codebase with a swappable storage backend** (local files vs. Fabric Lakehouse), not two separate implementations — this is why the canonical schema (§2) and layered architecture (§1) matter as much as they do.

---

## 22. Extensibility for Future AI (Phase 3+ direction, not built now)

The staged classification pipeline (§10) and Gold layer are designed so this sequence can be added later **without touching connectors at all**:

```
Sentiment/Classification (existing)
        ↓
Root Cause Analysis (why is sentiment dropping — cluster on Gold data)
        ↓
Trend Detection (week-over-week shifts per category/platform)
        ↓
Recommendation (surfaced to CX/product teams)
        ↓
Weekly Executive Report (auto-generated summary)
```

This is a Gold-layer-and-above concern — the connector/classification boundary already isolates it from the collection layer, which is the whole point of the layered design.

---

## 23. Architecture Invariants

Rules that never get violated during implementation, by Claude Code or anyone else — these are what keep the system aligned with this design as it's built, rather than drifting one "reasonable local decision" at a time:

```
1.  Never bypass the canonical schema (§2).
2.  Never let connectors communicate directly with classifiers — only through Bronze/Silver.
3.  Never overwrite Bronze — append-only, always.
4.  Never overwrite a classification — new classifier version = new Gold record, old one kept (§13).
5.  Never hardcode prompts — every prompt is a versioned file (§16).
6.  Never hardcode keywords, source lists, timeouts, or rate limits — config only (§8).
7.  Every new connector must inherit BaseConnector (§3) and pass the shared contract tests (§20).
8.  Every classification pipeline stage must be independently executable and testable (§10).
9.  Every output must be reproducible from Bronze alone.
10. Every ingestion run must be idempotent via content-hash mention_id (§5).
11. Every module must have unit tests before merge.
12. NaijaBERT handles sentiment/emotion for every mention; the LLM is called only for summaries, unknown-topic overflow, and low-confidence cases (§10) — never as the default path.
```

---

## 24. Recommended Build Milestones (for Claude Code)

Don't ask for "build the project" — break it into gated milestones, each with acceptance criteria checked before moving to the next. **Stop after each milestone for review before starting the next one** — this is the process control that keeps the implementation from drifting off the architecture above.

1. **Project scaffolding** — directory structure (§19), config system (§8), `BaseConnector` interface (§3), canonical schema (§2) as code (e.g. a Pydantic model), Source Registry (§4) skeleton. *Acceptance: schema and interface exist, no connectors yet, `config.yaml` loads correctly, registry reads the source list from config.*
2. **Orchestration core** — job queue (§18), run/connector state + checkpointing (§5), idempotent `mention_id` hashing (§5), logging (§7), retry/failure handling (§6), plugin auto-discovery. *Acceptance: a stub/fake connector can be dropped into `connectors/` and gets picked up automatically; killing and restarting a run resumes from checkpoint without duplicating records.*
3. **First real connector — Google Play** — implement, validate against the canonical schema and the connector contract tests (§20). *Acceptance: running it against real keywords produces valid Bronze records matching §2 exactly, and re-running it produces zero duplicate rows.*
4. **Bronze + Silver** — storage layer, connector-level dedup (already in §3 contract), Silver-level near-duplicate detection (§11), language detection. *Acceptance: Bronze is append-only; Silver is fully regenerable from Bronze alone; a deliberately duplicated input produces one Silver record, not two.*
5. **Classification pipeline + queue + evaluation** — staged pipeline (§10), classification queue, NaijaBERT-primary/LLM-conditional logic, 500-example labeled set (§15), automatic accuracy/precision/recall/F1 reporting. *Acceptance: metrics.csv is produced and matches manual spot-checks; a log of LLM calls shows they were only triggered for summaries/unknowns/low-confidence cases, not every mention.*
6. **Reporting** — full CSV output set (§14) plus Gold tables. *Acceptance: all seven output files are produced from a single CLI run.*
7. **Expand connectors** — App Store, Nairaland, YouTube, then Phase 2 sources one at a time, each validated against the schema and contract tests before moving to the next. *Acceptance per connector: same as milestone 3.*

Each milestone is independently reviewable — this is what turns "build the project" into something that can actually be checked at each step rather than discovered broken at the end.
