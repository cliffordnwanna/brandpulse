# Milestone 5 — Classification Pipeline + Evaluation

## Objective
Build the full AI classification pipeline in two clearly separated tiers: **5a (core, always runs)** and **5b (optional enrichment, configurable off)**. Every mention gets 5a. Only flagged or sampled mentions get 5b. This keeps cost predictable and the pipeline fast, while making BrandPulse genuinely differentiated.

## Read first
- `docs/EngineeringDesign.md` §10 (Classification Pipeline), §13 (Versioning), §15 (Evaluation Framework), §16 (Prompt Management)
- `CLAUDE.md` Architecture Invariants — especially: NaijaBERT handles sentiment/emotion for every mention; LLM called only for summaries/unknowns/low-confidence; classifications never overwritten, always versioned.

---

## Tier 5a — Core Pipeline (always runs, every mention)

### Models
- **Primary sentiment + complaint category:** `cardiffnlp/twitter-xlm-roberta-base-sentiment` or `Davlan/naija-twitter-sentiment-afriberta-large` — use whichever is available on HuggingFace; the Naija-specific model is strongly preferred for Pidgin accuracy.
- **Fallback for standard English:** `cardiffnlp/twitter-roberta-base-sentiment-latest` — only used when `language == "en"` AND NaijaBERT confidence is below threshold.
- Do NOT use vanilla RoBERTa or VADER as the primary model — they misclassify Nigerian Pidgin and code-mixed text.

### Classification stages (each independently executable, §10)

```
1. Sentiment         → Positive | Negative | Neutral | Mixed
2. Complaint Category → predefined taxonomy (see below) | Unknown
```

**Predefined complaint taxonomy** (from Engineering Design §9.1):
`Transfers | Debit Issues | Credit Delay | Login Issues | App Crash | Card Problems | ATM | POS | USSD | Fraud | Loans | Customer Service | Branches | Charges | Account Opening | KYC | General Feedback | Competitor Mention`

Use zero-shot classification (`facebook/bart-large-mnli` or equivalent) against this list. Anything below confidence threshold → `Unknown` (fed to BERTopic or LLM in 5b).

### Output per mention (5a)
```json
{
  "mention_id": "...",
  "classifier_version": "5a-v1",
  "sentiment": { "label": "Negative", "confidence": 0.91, "reason": "Contains complaint about failed transfer" },
  "complaint_category": { "label": "Transfers", "confidence": 0.87, "reason": "..." },
  "language_routed_as": "pcm",
  "processed_at": "..."
}
```
Every field must include `label`, `confidence`, and `reason`. No exceptions.

---

## Tier 5b — Optional Enrichment (configurable, runs only when enabled)

Controlled by `config.yaml`:
```yaml
classification:
  enable_enrichment: false    # set true to run 5b
  enrichment_model: azure_openai   # or: groq
  enrichment_trigger: low_confidence   # options: low_confidence | all | sampled
  confidence_threshold: 0.75
```

When `enable_enrichment: true`, run these additional stages **only** for mentions where 5a confidence is below threshold, OR `complaint_category == "Unknown"`, OR `sentiment == "Mixed"`:

```
3. Emotion          → Anger | Frustration | Appreciation | Confusion | Trust | Neutral
4. Intent           → Complaint | Praise | Query | Warning | Neutral
5. Urgency          → Critical | High | Medium | Low  (Critical = possible fraud/account loss)
6. Competitor Mention → GTBank | Access | UBA | FirstBank | Opay | Moniepoint | None
7. Summary          → 1-2 sentence plain-English gist (always LLM-generated, always runs in 5b)
```

**Azure OpenAI / Groq usage:**
- Use Azure OpenAI if `enrichment_model: azure_openai` — read credentials from environment variables (`AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_DEPLOYMENT`), never from config.yaml or committed files.
- Use Groq if `enrichment_model: groq` — `GROQ_API_KEY` from environment.
- Every LLM call must be logged with: which mention triggered it, which stage, which model, tokens used, cost estimate. This is the audit trail that keeps cost visible.

**Prompts** — all LLM prompts live as versioned files in `prompts/`. Never hardcoded strings. Example: `prompts/enrichment_emotion_v1.txt`, `prompts/enrichment_summary_v1.txt`. The Gold record stores which prompt version was used.

### Output per mention (5b adds to 5a record)
```json
{
  "emotion": { "label": "Frustration", "confidence": 0.84, "reason": "..." },
  "intent": { "label": "Complaint", "confidence": 0.91, "reason": "..." },
  "urgency": { "label": "High", "confidence": 0.88, "reason": "..." },
  "competitor_mention": { "label": "Opay", "confidence": 0.95, "reason": "Customer comparing to Opay's transfer speed" },
  "summary": "Customer reports repeated failed transfers and no response from support over 3 days.",
  "enrichment_model": "azure_openai",
  "enrichment_prompt_versions": { "emotion": "v1", "summary": "v1" }
}
```

---

## Classification Queue
Silver records flow into a queue before classification (Engineering Design §10) — ingestion never blocks on classification. For MVP this is a simple in-process queue (asyncio or threading.Queue). The queue is what lets 5a and 5b run at different rates without stalling the pipeline.

## Gold Storage
Write classified records to `StorageBackend.write("gold", mention_id, record)`. Classifications are **never overwritten** — a new classifier version writes a new Gold record alongside the old one, keyed `{mention_id}_{classifier_version}`. The `StorageBackend` from Milestone 4 handles this without changes.

## Evaluation Framework
Build this before running against real data — it's what tells you whether the models are actually working:

1. **Labeled set:** 500 mentions across `Positive | Negative | Neutral | Mixed | Spam` — if the labeled CSV doesn't exist yet at `eval/labeled_v1.csv`, generate a realistic synthetic set from the Silver records already collected (clearly marked as synthetic, not a substitute for real labels but usable for pipeline validation).
2. **Automatic evaluation:** `python -m brandpulse evaluate` — runs the full 5a pipeline against the labeled set, outputs accuracy/precision/recall/F1/confusion matrix to `output/metrics.csv`.
3. **Per-run evaluation:** Every real pipeline run should log its own confidence distribution to `output/run_metadata.json` so drift is visible over time.

## Session Logging (new requirement from this session)
Every pipeline run creates a timestamped session record in `output/sessions/{run_id}.json` containing:
- Run timestamp, sources scraped, mention counts per source
- Sentiment distribution (positive/negative/neutral counts and %)
- Top complaint categories
- Confidence distribution (mean, median, % below threshold)
- Any connectors that failed

This is separate from `run_metadata.json` (operational/orchestration log) — this is the analytical summary of what was found. Each session is kept; nothing is overwritten. Drift between sessions is detectable by comparing distributions across session files.

## Model availability note (added by Claude Code before implementation)
The development/build sandbox this milestone was implemented in has no `transformers`/`torch` installed and no HuggingFace Hub network access — downloading the actual NaijaBERT/XLM-R/BART-MNLI weights specified above is not possible in that environment. Per explicit direction from Clifford:
- A clean model-adapter interface (`SentimentModel`, `ComplaintClassifier` protocols) is the seam between pipeline logic and any specific model implementation — same pattern as `StorageBackend` in Milestone 4.
- The **default** implementation behind that interface is a lexicon/rule-based classifier (Pidgin-aware where feasible), so the full pipeline is runnable, testable, and produces real label/confidence/reason output entirely offline, without any model download.
- A HuggingFace-backed adapter implementing the same interface is also wired (not a stub) against the exact model IDs specified above, selectable via config, for use once `transformers`/`torch`/model downloads are available.
- `docs/models.md` documents the manual `pip install` step and exact model IDs required to switch from the default to the HuggingFace adapter in a real environment.
- This is a documented environment constraint, not a scope reduction: every acceptance criterion below (label+confidence+reason per stage, LLM-conditional logic, Gold versioning, evaluation framework) is still met using the default adapter.

## Explicitly out of scope
- Do NOT build the word cloud or final report output — that's Milestone 6.
- Do NOT add new connectors.
- Do NOT build a dashboard.

## Acceptance Criteria
- [ ] 5a pipeline runs on every Silver record and produces sentiment + complaint category with confidence + reason.
- [ ] NaijaBERT/Naija-specific model is the primary sentiment model; vanilla RoBERTa is only a fallback for high-confidence English text. (Satisfied via the adapter interface + documented model IDs — see "Model availability note" above for what runs by default in this environment.)
- [ ] `enable_enrichment: false` in config produces zero LLM calls — verified by checking the LLM call log.
- [ ] `enable_enrichment: true` triggers 5b only for mentions below confidence threshold or Unknown category — not every mention.
- [ ] Every LLM call is logged with mention_id, stage, model, tokens, cost estimate.
- [ ] Gold records are versioned, never overwritten.
- [ ] `python -m brandpulse evaluate` produces `output/metrics.csv` with accuracy/precision/recall/F1.
- [ ] Session log created at `output/sessions/{run_id}.json` for every run.
- [ ] All prompts are versioned files in `prompts/`, no hardcoded strings.
- [ ] Full test suite passes; new tests cover 5a classification, 5b trigger logic, Gold versioning, session logging.

## Stop condition
Stop when all acceptance criteria are met. Update `TASKS.md`. Do not proceed to Milestone 6 without review.
