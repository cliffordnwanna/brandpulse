# Milestone 4 — Bronze + Silver Storage

## Objective
Build the storage layer: Bronze (append-only, lightly normalized per connector contract) and Silver (cross-source/cross-run near-duplicate detection, language detection).

## Read first
- `docs/EngineeringDesign.md` §9 (Storage Design), §11 (Deduplication Strategy)

## Requirements
1. Implement Bronze storage — local file-based for MVP (a `bronze/` folder of records), append-only, keyed by the idempotent `mention_id`. A write with an existing `mention_id` is a no-op, not a duplicate.
2. Implement Silver-stage processing: near-duplicate detection (text hash for likely duplicates, embedding similarity for near-identical reposts) and language detection (routing Pidgin/English/Yoruba/Hausa/Igbo).
3. Ensure Silver is fully regenerable from Bronze alone — write a function/command that rebuilds Silver from scratch and confirm it produces the same result as the incremental version.
4. Wire this into the connector output from Milestone 3 — Google Play records should now flow all the way to Silver.

## Explicitly out of scope for this milestone
- Do NOT implement Gold or classification — that's Milestone 5.
- Do NOT implement additional connectors — that's Milestone 7.

## Acceptance Criteria
- [ ] Bronze is append-only — no code path modifies or deletes an existing Bronze record.
- [ ] A deliberately duplicated input (same content submitted twice) produces exactly one Silver record, not two.
- [ ] Rebuilding Silver from Bronze from scratch produces an identical result to the incrementally-built version.
- [ ] Language detection correctly routes at least a small hand-checked sample of Pidgin vs. English text differently.

## Stop condition
Stop when all acceptance criteria are met. Do not proceed to Milestone 5 without review.
