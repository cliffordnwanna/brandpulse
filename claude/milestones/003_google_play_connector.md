# Milestone 3 — Google Play Connector

## Objective
Implement the first real connector: Google Play reviews for the Wema Bank and ALAT apps. This is the proof that the abstraction from Milestones 1-2 actually works against a live source.

## Read first
- `docs/EngineeringDesign.md` §3 (Connector Interface + contract guarantees), §17 (Security — robots.txt/rate limits/user agent)
- Milestone 1's `BaseConnector` and canonical schema; Milestone 2's orchestration core

## Requirements
1. Implement `GooglePlayConnector(BaseConnector)` — `search()`, `normalize()`, `validate()`, `health()`.
2. Fulfill the connector contract from Engineering Design §3 before any record reaches Bronze: no exact duplicates within the batch, UTF-8-safe text, timestamp normalized to UTC, text lightly cleaned (whitespace/control characters only — never rewritten), and `raw_json` carrying the fully untouched original response.
3. Respect `robots.txt`, apply the global rate limiter, use randomized request delays (Engineering Design §17).
4. Handle the specific Google Play failure modes explicitly: request timeout, pagination failures, HTML/response structure changes, rate-limit responses (back off and reschedule, don't treat as `FAILED`).
5. Use the retry/checkpoint/idempotency machinery from Milestone 2 — don't reimplement any of it inside this connector.

## Explicitly out of scope for this milestone
- Do NOT implement any other connector.
- Do NOT implement Silver-stage processing (dedup across sources, language detection) — that's Milestone 4.
- Do NOT implement classification.

## Acceptance Criteria
- [ ] Running the connector against real Wema Bank / ALAT app keywords produces valid records matching the canonical schema in Engineering Design §2 exactly.
- [ ] Re-running the same search produces zero duplicate Bronze rows (idempotency holds against a real source, not just the stub).
- [ ] Contract tests (shared suite, once it exists — flag if it doesn't exist yet and needs building here) pass for this connector.
- [ ] Checkpoint/resume works against this connector specifically (kill mid-pagination, restart, confirm no re-fetch of completed pages).
- [ ] `robots.txt` is checked before the connector runs.

## Stop condition
Stop when all acceptance criteria are met. Do not proceed to Milestone 4 without review.
