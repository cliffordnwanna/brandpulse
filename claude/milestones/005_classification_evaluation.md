# Milestone 5 — Classification Pipeline + Evaluation

## Objective
Build the staged classification pipeline with a classification queue, NaijaBERT-primary/LLM-conditional logic, and the automatic evaluation framework against a 500-example hand-labeled set.

## Read first
- `docs/EngineeringDesign.md` §10 (Classification Pipeline), §13 (Versioning), §15 (Human Validation & Evaluation Framework), §16 (Prompt Management)

## Requirements
1. Implement the Classification Queue between Silver and the classification stages (Engineering Design §10) — a simple async/multiprocessing queue is fine for MVP.
2. Implement the staged pipeline: language detection → translation (only where needed) → sentiment (NaijaBERT, always) → emotion (always) → intent → complaint category (predefined taxonomy first, BERTopic zero-shot for overflow) → product mentioned → severity/urgency → competitor mention → summary (LLM, always).
3. Enforce the LLM-conditional rule explicitly: the LLM is called ONLY for summary generation, unknown-topic overflow classification, and re-checking low-confidence NaijaBERT predictions (configurable threshold) — never for sentiment/emotion on every mention. Log every LLM call with its trigger reason so this is auditable.
4. Every stage outputs label + confidence + reason (Engineering Design §10 example format) — not just a label.
5. Store prompt versions as separate files under `prompts/` (Engineering Design §16), never hardcoded strings.
6. Build the hand-labeled evaluation set: 500 examples across Positive/Negative/Neutral/Mixed/Spam (Engineering Design §15). If Clifford hasn't supplied labeled data yet, stop and ask for it rather than fabricating labels.
7. Build the automatic evaluation runner: accuracy, precision, recall, F1, confusion matrix against the labeled set, output to `metrics.csv`.
8. Ensure classifications are versioned, never overwritten (Engineering Design §13) — a new classifier/prompt version produces a new Gold record alongside the old one.

## Explicitly out of scope for this milestone
- Do NOT implement the CSV/Gold output layer beyond what's needed to write classification results — full reporting is Milestone 6.

## Acceptance Criteria
- [ ] `metrics.csv` is produced by an automatic evaluation run and its accuracy/precision/recall/F1 numbers match a manual spot-check on a subset of the labeled set.
- [ ] A log of LLM calls during a real run shows they were only triggered for summaries, unknown-topic cases, or explicitly low-confidence predictions — not for every mention.
- [ ] Re-running classification with the same classifier version does not create duplicate Gold records; running a new classifier version does create new versioned records alongside the old ones.
- [ ] Every classification record includes label, confidence, and reason.

## Stop condition
Stop when all acceptance criteria are met. Do not proceed to Milestone 6 without review.
