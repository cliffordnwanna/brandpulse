# Milestone 6 — Reporting

## Objective
Produce the full MVP output set from a single CLI run: keyword(s) + timeframe in, seven output files out.

## Read first
- `docs/EngineeringDesign.md` §14 (Output Files), §12 (Search Strategy — CLI keyword/timeframe entry point)

## Requirements
1. Build the CLI entry point (`cli.py`) accepting keyword list + timeframe, merging user-supplied keywords with the base keyword list from config (never replacing it).
2. Wire the full pipeline end-to-end: CLI input → connectors (Google Play only is fine at this milestone; more sources arrive in Milestone 7) → Bronze → Silver → Classification Queue → Gold → output files.
3. Produce all seven output files per Engineering Design §14: `mentions.csv`, `classifications.csv`, `summary.csv`, `errors.csv`, `metrics.csv`, `connector_health.csv`, `run_metadata.json`.

## Explicitly out of scope for this milestone
- Do NOT add new connectors — that's Milestone 7.
- Do NOT build a dashboard — the PRD explicitly defers this.

## Acceptance Criteria
- [ ] A single CLI invocation with a keyword list and a date range produces all seven output files with no manual intervention.
- [ ] `errors.csv` correctly reflects any `FAILED`/`PARTIAL_SUCCESS` events from the run.
- [ ] `connector_health.csv` shows per-connector status, latency, and record count.
- [ ] Output is anonymized per the PRD's checklist — no email addresses, phone numbers, or any field that could resolve to a real customer identity.

## Stop condition
Stop when all acceptance criteria are met. Do not proceed to Milestone 7 without review.
