# Milestone 7 — Expand Connectors

## Objective
Add the remaining three MVP connectors — App Store, Nairaland, YouTube — one at a time, each fully validated before moving to the next. MVP is complete (4 sources total) once this milestone is done.

## Read first
- `docs/EngineeringDesign.md` §3 (Connector Interface), §17 (Security)
- Milestone 3's Google Play connector, as the reference implementation

## Requirements — implement and validate one connector at a time, in this order
1. **App Store** — reviews for the Wema Bank and ALAT apps. Same contract as Google Play (§3): dedup, UTF-8, timestamp normalization, robots.txt/rate limiting.
2. **Nairaland** — forum scraping. Handle its specific failure modes: HTML structure changes, pagination, thread discovery for Wema/ALAT-relevant threads.
3. **YouTube** — official Data API, comments on Wema/ALAT-relevant videos. Handle quota management explicitly (this is the one failure mode that's about API limits, not scraping fragility).

Do not start the next connector in this list until the current one passes its own acceptance criteria below.

## Explicitly out of scope for this milestone
- Do NOT add Reddit or any Phase 2 source — those come later, and Reddit was explicitly decided against for MVP.

## Acceptance Criteria (per connector, repeat for each of the three)
- [ ] Running the connector against real keywords produces valid records matching the canonical schema exactly.
- [ ] Re-running produces zero duplicate records (idempotency holds).
- [ ] Contract tests pass.
- [ ] Checkpoint/resume works against this connector.
- [ ] Connector-specific failure modes (per the list above) are handled explicitly, not left to crash.

## Final MVP acceptance (after all three are done)
- [ ] A single CLI run with a keyword list and timeframe now returns results from all 4 sources (Google Play, App Store, Nairaland, YouTube) in one report.
- [ ] `connector_health.csv` shows all 4 connectors' status in a single run.

## Stop condition
Stop after each connector for review. Stop again after all three are done — this completes the MVP.
