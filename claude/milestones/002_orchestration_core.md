# Milestone 2 — Orchestration Core

## Objective
Build the orchestration layer: ingestion job queue, run/connector state with checkpointing, idempotent `mention_id` hashing, structured logging, retry/failure handling, and connector plugin auto-discovery. Still no real connectors — validate this milestone against a stub/fake connector.

## Read first
- `docs/EngineeringDesign.md` §5 (Orchestration State & Idempotency), §6 (Failure Strategy), §7 (Observability & Logging), §18 (Ingestion Job Queue)
- Milestone 1's `BaseConnector`, `SourceRegistry`, and config loader (this milestone builds directly on top of them)

## Requirements
1. Implement content-hash `mention_id` generation: `SHA256(platform + url + timestamp + normalized_text)` (Engineering Design §5).
2. Implement Run State, Connector State, and Checkpoint tracking — after every successful batch a connector writes, not just at run end. On restart, a connector resumes from its last checkpoint rather than from zero.
3. Implement the retry policy from Engineering Design §6: exponential backoff, max 3 attempts, only on `FAILED` (never on `NO_RESULTS`); auto-disable (via the Source Registry) a connector that fails 3 consecutive scheduled runs.
4. Implement structured (JSON) logging per the event examples in Engineering Design §7.
5. Implement the ingestion job queue (Engineering Design §18) — one job per source × keyword batch, worker pool executing them (simple async/thread pool is fine for now).
6. Implement plugin auto-discovery for connectors — a directory scan under `connectors/`, no `if platform == "x"` branching anywhere.
7. Build one fake/stub connector purely for testing this milestone (e.g. one that returns canned data, or deliberately fails on the Nth call) — this is test scaffolding, not a real source, and should live under `tests/`, not `connectors/`.

## Explicitly out of scope for this milestone
- Do NOT implement any real connector (Google Play, App Store, etc.) — that's Milestone 3.
- Do NOT implement Bronze/Silver storage — that's Milestone 4.
- Do NOT implement classification code.

## Acceptance Criteria
- [ ] The stub connector is picked up automatically by plugin discovery with zero manual registration.
- [ ] Running the stub connector, killing the process mid-run, and restarting resumes from the last checkpoint — no re-fetching of already-checkpointed batches.
- [ ] The same content run twice produces the same `mention_id` both times (idempotency proven with a test, not just asserted).
- [ ] A connector forced to fail 3 consecutive runs is auto-disabled and this is visible in the registry/logs.
- [ ] Structured logs are emitted for run start/end, per-connector status, and failures, matching the format in Engineering Design §7.
- [ ] Unit + integration tests cover checkpoint/resume, idempotency, and retry behavior.

## Stop condition
Stop when all acceptance criteria are met. Do not proceed to Milestone 3 without review.
