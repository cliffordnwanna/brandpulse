# BrandPulse — Wema Bank Customer Voice Intelligence Platform
### Product Requirements Document — v2.2
**Owner:** Clifford Nwanna, Data Analytics & AI Team, Wema Bank
**Status:** Approved for MVP build
**Classification:** Internal — contains customer data handling design; DPIA and Legal/DPO sign-off required before any case-routing phase

**Changelog from v1.0:** Restructured into 3 delivery phases (MVP → Phase 2 Fabric build → Phase 3 documented-only). Replaced Postgres/Supabase design with Fabric-native Lakehouse (Bronze/Silver/Gold), Azure as fallback only. CSV export is now the primary MVP deliverable; dashboard deferred. Case routing/CLM moved out of near-term scope. Added predefined complaint taxonomy, confidence scores, and source reliability scoring. Raised source target from 5 to 8-12. Revised cost estimate range. Framework changed to Fabric-native orchestration (Option D).

**Changelog v2.0 → v2.1:** Success metrics now declared explicitly per phase (§5.1–5.3), each with its own pass/fail gate rather than one shared table. Added a concrete MVP validation plan (hand-labeled sample size, spot-check method, anonymization checklist) so "validate the MVP" has a defined procedure, not just a target number.

**Changelog v2.1 → v2.2:** MVP source count raised from 3 to 4 — added YouTube alongside Google Play, App Store, and Nairaland (kept all sources rather than trading any away, per explicit preference for source breadth). Labeled evaluation set raised to 500 examples with Positive/Negative/Neutral/Mixed/Spam classes, aligned with the companion Engineering Design Document. See the Engineering Design Document v2.0 for the accompanying production-hardening decisions (idempotency, checkpointing, classification queue, Bronze normalization contract, LLM-optional classification) — all now built into the MVP itself rather than deferred to Phase 2.

---

## 1. Executive Summary

Wema Bank currently has no systematic way of knowing what customers are saying about it — or about ALAT — outside of official complaint channels, while that conversation happens constantly across app store reviews, Nairaland, YouTube, Reddit, and beyond. This PRD defines a three-phase path to a **Customer Voice Intelligence Platform**:

- An **MVP** you can deploy immediately from your own repo: input keywords + a time window, get a structured report — no infrastructure dependency, anonymized data only.
- A **Phase 2** production build on **Microsoft Fabric** (Azure as fallback), deployed immediately after MVP validation, with a proper Bronze/Silver/Gold lakehouse and predefined complaint taxonomy.
- A **Phase 3** — governance-gated case routing and paid-source expansion — fully documented now, but **not built** until ingestion and classification have proven themselves in production.

The hard problem, confirmed by Phase 0 research, is reliable *collection* — not sentiment classification, which already has strong free tooling built specifically for Nigerian Pidgin/English. The architecture below is designed around that reality.

---

## 2. Delivery Phases (top-level structure)

| Phase | Scope | Data | Infra | Timing |
|---|---|---|---|---|
| **MVP** | Keyword + timeframe input → scraped, cleaned, classified → CSV/report output | Anonymized only (no PII, no account matching) | Runs from Clifford's own repo — Python scripts, no cloud dependency required | Build and deploy immediately |
| **Phase 2** | Same pipeline, productionized: scheduled ingestion, Bronze/Silver/Gold lakehouse, predefined taxonomy, confidence scoring, source reliability scoring | Anonymized, expanded source count (8-12) | Microsoft Fabric native; Azure (Functions/App Service/AI) as fallback only | Build and deploy immediately after MVP |
| **Phase 3** | Case routing to CLM, verified customer matching, paid-source expansion (X/Instagram/TikTok) | Requires DPIA + Legal/DPO sign-off before any PII-adjacent step | TBD, likely Fabric + Azure OpenAI | **Documented only for now — not built** |

---

## 3. Goals

1. Ship a working MVP immediately: keyword + time-window input → sentiment/complaint report, anonymized, zero infrastructure dependency.
2. Productionize the same pipeline on Fabric with scheduled ingestion across 8-12 free/cheap sources.
3. Classify every mention for sentiment, emotion, complaint category (predefined taxonomy + emerging-topic discovery), product, urgency, and competitor mentions — each with a confidence score and a source reliability rating.
4. Document (not build) the governance-gated path to case routing and CLM integration, so Phase 3 can start quickly once Legal/DPO clears it.
5. Keep the whole thing cheap relative to commercial social listening platforms.

## 4. Non-Goals (MVP and Phase 2)

- No PII extraction, no customer-record matching, no automated account actions — deferred to Phase 3, gated on DPIA/Legal sign-off.
- No dashboard build in MVP — CSV/report export is the deliverable until ingestion and classification are proven.
- No paid X/Instagram/TikTok ingestion until Phase 3 budget approval.

## 5. Success Metrics — Declared Per Phase

Each phase has its own gate. A phase is not "done" until its own metrics are met — Phase 2 doesn't start on faith that the MVP worked, and Phase 3 doesn't get built at all until Phase 2's metrics hold up over time.

### 5.1 MVP success metrics (must validate before Phase 2 starts)

| Metric | Target | How it's validated |
|---|---|---|
| Sources live and returning data | 4 (Google Play, App Store, Nairaland, YouTube), 100% free APIs/scraping — no paid connector in MVP | Manual run log per source |
| Report runs end-to-end from keyword + timeframe input | Yes, no manual intervention mid-run | Run the tool 5+ times with different keyword/timeframe combos, confirm CSV output each time |
| Sentiment classification accuracy | ≥75% agreement with a human-labeled sample (Clifford hand-labels 500 mentions across Positive/Negative/Neutral/Mixed/Spam, including Pidgin/code-mixed examples — see companion Engineering Design Document §13 for the full evaluation framework) | Manual comparison, logged as a labeled validation set kept for reuse in Phase 2 |
| Complaint category accuracy (predefined taxonomy) | ≥70% agreement with human-labeled sample | Same labeled set as above |
| Coverage against sampled manual search | Spot-check: pick 10 known Wema/ALAT mentions found by manual search, confirm the pipeline also surfaces them | Manual comparison, not a numeric recall claim |
| Cost | Near-zero — free-tier APIs/scraping only, no paid inference beyond free tiers | Track actual spend during MVP run period |
| Anonymization | Zero PII fields in any output file (verified against a checklist: no emails, phone numbers, or matched customer identifiers) | Manual review of CSV columns before first real run |

**MVP is the validation gate for the whole project.** If sentiment/complaint accuracy comes in materially below target here, that's the signal to fix the NLP/data approach *before* investing in the Fabric build — not after.

### 5.2 Phase 2 success metrics (Fabric build, deployed immediately after MVP passes its gate)

| Metric | Target |
|---|---|
| Sources live and ingesting | 8–12 |
| Ingestion cadence | Scheduled and automated (no manual trigger needed) via Fabric Data Pipeline |
| Sentiment classification accuracy | ≥80% agreement with human-labeled sample (expanded from the MVP labeled set) |
| Complaint category accuracy | ≥75% agreement with human-labeled sample |
| Every classification includes confidence score + source reliability rating | Yes, 100% of records |
| Coverage against sampled manual searches | Tracked quantitatively per run, not just spot-checked |
| Cost | Target <$100/month; realistic range $30–150/month depending on mention volume |
| Output format | CSV + Power BI-ready Gold tables |
| Reprocessing capability | Bronze layer allows full reprocessing when the classifier improves, without re-scraping |

Dashboard adoption is intentionally **not** a Phase 2 KPI — it only becomes one once a dashboard is actually built, which is a later decision point (§10).

### 5.3 Phase 3 success metrics (documented now, only measured once Phase 3 is actually built)

| Metric | Target |
|---|---|
| DPIA and Legal/DPO sign-off | 100% complete before any case-routing code goes live — this is a gate, not a metric to trend |
| False-positive rate on "urgent" case flags (human-reviewed) | <20% |
| Cases created with full audit trail (why flagged, what triggered it) | 100% |
| Automated PII matching to customer records | 0% — by design, never automated, human-verified consent only |
| Paid-source cost vs. budget approval | Tracked against whatever budget is approved at the time, using real MVP/Phase 2 volume data rather than estimates |

These are declared now so Phase 3 has a ready-made success bar the moment it's greenlit — they are not being measured yet.

---

## 6. Phase 0 Research Findings — What Already Exists

*(Unchanged from v1.0 research — summarized here; see appendix note if full detail is needed.)*

- **Commercial platforms** (Brandwatch, Talkwalker, Meltwater, Sprinklr, Sprout Social) all rely on **licensed API partnerships** with the platforms plus proprietary crawling — their moat is data-access licensing, not clever NLP. We can't replicate their source breadth on our budget; we replicate their *pipeline shape*.
- **Open-source references**: `brightdata/social-listening-agent` (LangGraph 8-stage pipeline), `HasData/social-listening-tool` (SERP API + LLM + 24-hour cron cycle), `nama1arpit/reddit-streaming-pipeline` (Kafka/Spark/Cassandra/Grafana — heavier than we need), Octolens (unified paid mentions API as a possible Phase 3 alternative to DIY connectors).
- **Nigerian-specific prior art**: an SVM sentiment study on Nigerian bank tweets, and a GTBank/Access/First Bank/UBA/Zenith social media competitive analysis — both useful as methodology and benchmark references.
- **NLP finding that matters most**: NaijaSenti corpus + NaijaBERT / `Davlan/bert-base-multilingual-cased-finetuned-naija` on HuggingFace are free, peer-reviewed, and purpose-built for Nigerian Pidgin/English code-mixing — directly solving the "generic sentiment tools misread Naija slang" problem (e.g. "ginger" = motivation, "tank" = gratitude — meanings standard English models get wrong).
- **Topic/complaint classification**: BERTopic with zero-shot seeding lets us combine a predefined taxonomy with discovery of emerging topics.
- **Cheap LLM inference**: Groq (Llama 3.1 8B at $0.05/million input tokens, usable free tier) is the practical cost anchor for LLM-assisted classification at volume.
- **Confirmed dead-end sources**: snscrape/Twint/Nitter for X are confirmed non-functional in 2026; Instagram/TikTok have no free API path for public data at scale. These remain documented, not built, until Phase 3.

---

## 7. Data Source Strategy

### 7.1 MVP sources (build first, proof of concept)

| Source | Access | Cost | Priority |
|---|---|---|---|
| Google Play reviews (Wema, ALAT apps) | Scraping, no auth | Free–~$2/1,000 | ⭐⭐⭐⭐⭐ |
| Apple App Store reviews (Wema, ALAT apps) | Scraping, no auth | Free–~$2/1,000 | ⭐⭐⭐⭐⭐ |
| Nairaland | Scraping, no auth | Free | ⭐⭐⭐⭐⭐ |
| YouTube comments | Official Data API | Free (daily quota) | ⭐⭐⭐⭐⭐ |

Four sources, not three — kept App Store rather than trading it for YouTube, since source breadth is a stated priority. The four also happen to cover three genuinely different data shapes (star-rated app review, long-form forum thread, short video comment), which is useful for validating the canonical schema against real variety.

### 7.2 Phase 2 sources (expand to 8–12 total)

Add: Reddit (official API, free tier), Google Business reviews, Google Search results, Trustpilot, banking/news blogs, RSS feeds, Medium. Each source gets a **reliability rating** (see §9) so downstream trend reporting can be weighted, not treated as uniformly trustworthy.

### 7.3 Documented, not built — no reliable free workaround

| Source | Why | Status |
|---|---|---|
| X/Twitter | snscrape/Twint/Nitter confirmed dead 2026; remaining libraries need logged-in accounts + proxies + break every 2-4 weeks | Paid connector only, Phase 3 decision |
| Instagram | No free API for public data at scale (deliberate Meta design); cookie-free scrapers cap ~10-20 comments/post | Paid connector only, Phase 3 decision |
| TikTok | Same structural pattern as Instagram | Paid connector only, Phase 3 decision |

### 7.4 Search term strategy

Config-driven keyword list (never hardcoded), covering: `Wema`, `Wema Bank`, `ALAT`, `ALAT by Wema`, `ALAT Bank`, `Wema mobile app`, `Wema transfer`, `Wema POS`, `Wema debit`, `Wema customer care`, `Wema fraud`, `Wema loan`, `Wema account`, `Wema app`, `Wema banking`, plus misspellings and hashtag variants. MVP input adds a **user-supplied keyword + timeframe** on top of this base list, so ad-hoc queries (e.g. "ALAT fraud, last 30 days") are supported without redeploying anything.

**Comments over posts, always** — replies, review text, and discussion threads are the unit of value; top-level marketing posts are noise.

---

## 8. MVP Architecture (build and deploy now)

```
User input: keyword(s) + timeframe
            │
            ▼
   Source Connectors (Google Play, App Store, Nairaland, YouTube)
            │
            ▼
   Cleaning → Deduplication → Language Detection
            │
            ▼
   NLP Classification
   • Sentiment (NaijaBERT) + confidence score
   • Complaint category (predefined taxonomy, §9) + confidence score
   • Source reliability rating
            │
            ▼
   Report output: CSV (mentions.csv, classified_mentions.csv, summary.csv)
```

- Lives in Clifford's own repo. Plain Python — no cloud dependency required to run it.
- Anonymized data only: store comment text, platform, public handle, URL, timestamp — never resolve to an internal customer record.
- Runs on demand: pass a keyword list and a date range, get CSVs back.

---

## 9. Phase 2 Architecture (Fabric-native, deploy immediately after MVP)

```
Source Connectors (8-12 sources, scheduled)
            │
            ▼
   Fabric Data Pipeline (scheduled trigger)
            │
            ▼
   Fabric Notebook — ingestion & normalization
            │
            ▼
   Lakehouse — BRONZE  (raw JSON, exactly as collected)
            │
            ▼
   Fabric Notebook — cleaning, dedup, language detection
            │
            ▼
   Lakehouse — SILVER  (cleaned, normalized records)
            │
            ▼
   NLP Classification (sentiment, emotion, complaint category,
   product, urgency, competitor mention — each with a confidence score)
            │
            ▼
   Lakehouse — GOLD  (analytics-ready, source-reliability-weighted)
            │
            ▼
   Semantic Model → Power BI  /  CSV export
```

**Fallback (only where Fabric can't do something):** Azure Functions, Azure App Service, Azure Storage, Azure SQL, Azure OpenAI. Postgres/Supabase is dropped from the design — Fabric's Lakehouse is the primary store, matching Wema's existing Fabric/Azure ML environment from the Enterprise AI Programme.

**Bronze/Silver/Gold rationale:** keeping raw data in Bronze means we can reprocess from scratch whenever the classifier improves, without re-scraping. This is the standard Fabric Lakehouse pattern, not a custom scheme.

### 9.1 Predefined complaint taxonomy

Rather than relying mainly on open-ended topic discovery, Phase 2 seeds a fixed taxonomy for stable, business-readable reporting:

`Transfers · Debit Issues · Credit Delay · Login Issues · App Crash · Card Problems · ATM · POS · USSD · Fraud · Loans · Customer Service · Branches · Charges · Account Opening · KYC`

BERTopic runs in zero-shot mode against this list; anything that doesn't match becomes an **"unknown/emerging"** cluster for review — giving stable core reporting plus a discovery mechanism for new complaint types (e.g. a new fee, a new outage pattern) without redefining the whole taxonomy.

### 9.2 Confidence scores (mandatory on every classification)

Every classifier output includes a confidence value, e.g.:
```
Sentiment: Negative       Confidence: 91%
Emotion: Frustration      Confidence: 84%
Topic: Transfer Failure   Confidence: 88%
```
This lets reviewers filter out low-confidence predictions instead of trusting every row equally — especially important given the Nigerian Pidgin/code-mixing challenge.

### 9.3 Source reliability rating

Each source is tagged so trend reporting can be weighted rather than treated as uniform:

| Source type | Reliability |
|---|---|
| Official app store review | High |
| Forum (Nairaland, Reddit) | Medium |
| News article comment | Medium |
| Random blog / low-traffic site | Low |

This directly answers the "how much should we trust this trend" question stakeholders will eventually ask.

---

## 10. Dashboard (deferred, not MVP or early Phase 2)

CSV/Gold-table export is the primary deliverable until ingestion and classification are proven in production. Once trust is established:
- Phase 2 output is already Power-BI-ready (Gold layer) — a Power BI report can be layered on with minimal extra work.
- A lightweight Fabric-hosted or Azure Web App interface can follow for broader sharing.
- No dashboard-adoption KPI exists until a dashboard is actually built and scoped as its own deliverable.

---

## 11. Phase 3 (documented only — not built yet)

This phase remains fully specified so it can start quickly once cleared, but nothing here gets built until ingestion and classification (MVP + Phase 2) have proven themselves and Legal/DPO has signed off.

**Scope:**
- Case queue: flagged high-severity/high-confidence complaints become a case (comment + platform + handle + classification) — no automated PII extraction or customer-record matching.
- Human-verified escalation: a social-care agent follows Wema's existing identity-verification procedure before any account record is touched.
- CLM integration: routes verified cases into **Customer Lifecycle Management** (confirmed meaning — see §12) once identity is verified.
- Paid-source expansion: revisit X/Instagram/TikTok via a paid connector, using real cost/volume data from MVP + Phase 2 rather than estimates.

**Hard gates before any of this is built:**
- DPIA completed and owned by Legal/DPO (separate function from Data & AI team).
- Retention policy defined for scraped comments/handles post-case-closure.
- Audit trail requirement defined (why a case was created, what triggered it) — relevant given CBN examination exposure.
- No automated matching of scraped identifiers to customer records under any circumstance, even in Phase 3 — matching only happens after human-verified consent.

---

## 12. Resolved Open Questions (from v1.0)

| Question | Answer |
|---|---|
| CLM meaning | Customer Lifecycle Management |
| Social handles collected at onboarding? | No — Wema onboarding does not collect customer social media handles; Phase 3 matching, if it ever happens, cannot rely on this and must go through human-verified consent instead |
| DPIA owner | Separate Legal/DPO function; required before any Phase 3 case-routing goes live |
| Dashboard audience | MVP/Phase 2: Data & AI team only, CSV-based; a lightweight Fabric/Azure Web App interface may follow later for broader sharing |
| Infrastructure | Fabric-native from day one; Azure services (Functions, App Service, AI) as fallback only where Fabric can't do something |

---

## 13. Indicative Cost Model

| Item | MVP | Phase 2 |
|---|---|---|
| Scraping (Google Play, App Store, Nairaland) | Near-zero (own compute, low volume) | ~$2–20/month at moderate review volume across 8-12 sources |
| YouTube/Reddit APIs | N/A (Phase 2) | Free within quota/rate limits |
| LLM classification (Groq) | Minimal (proof-of-concept volume) | Scales with mention volume — realistically $30-150/month depending on volume, not a flat <$100 promise |
| Fabric compute | N/A | Depends on Wema's existing Fabric capacity allocation |
| Hosting | Local/repo execution | Existing Fabric/Azure allocation — marginal incremental cost |

Real numbers get tracked from MVP week one so the Phase 3 paid-source decision is made on actual data.

---

## 14. Framework Decision — Resolved

**Option D — Fabric-native orchestration** is the chosen framework, replacing the earlier lean-cron recommendation:

```
Fabric Data Pipeline → Scheduled Notebook → Lakehouse (Bronze)
→ Notebook Processing → Lakehouse (Silver) → NLP Classification
→ Lakehouse (Gold) → Power BI / CSV Export
```

Azure Functions/App Service/AI are used only where Fabric doesn't provide the needed capability. This keeps Phase 2 aligned with Wema's existing Microsoft ecosystem (per the Enterprise AI Programme) and avoids infrastructure sprawl. The **MVP stays framework-light by design** — plain Python in Clifford's repo, no Fabric dependency — specifically so it can ship immediately without waiting on any Fabric provisioning or approval.

---

## 15. Engineering Roadmap (revised, natural build order)

| Phase | Scope |
|---|---|
| 1 — Connectors | Google Play, App Store, Nairaland (MVP); expand to 8-12 (Phase 2) |
| 2 — Cleaning, dedup, storage | MVP: in-memory/local; Phase 2: Bronze → Silver in Fabric Lakehouse |
| 3 — Classification | Sentiment, complaint taxonomy, confidence scores, source reliability |
| 4 — Analytics output | CSV (MVP + Phase 2); Gold tables + Power BI (Phase 2) |
| 5 — Automation | Scheduled Fabric pipeline triggers (Phase 2) |
| 6 — Governance | DPIA, retention policy, audit trail (prerequisite for Phase 3, not built until cleared) |
| 7 — Paid sources & case routing | Phase 3 — documented only, gated on Phase 6 completion + budget approval |
