# Milestone 1 — Project Scaffolding

## Objective
Create the project skeleton: directory structure, configuration system, the `BaseConnector` interface, the canonical data schema as code, and a Source Registry skeleton. No connectors, no orchestration logic, no classification code yet.

## Read first
- `docs/EngineeringDesign.md` §2 (Canonical Data Contract), §3 (Connector Interface), §4 (Source Registry), §8 (Configuration Layer), §19 (Directory Structure)
- `CLAUDE.md` (Architecture Invariants)

## Requirements
1. Set up the repo per the directory structure in Engineering Design §19 (empty placeholder files/folders where the real content comes in later milestones).
2. Implement the canonical `Mention` schema (Engineering Design §2) as a Pydantic model.
3. Implement `BaseConnector` as an abstract class (Engineering Design §3) — `search()`, `normalize()`, `validate()`, `health()` — with no concrete connectors yet.
4. Implement `RunResult` and `HealthStatus` types matching the failure-strategy statuses in Engineering Design §6 (`SUCCESS`, `PARTIAL_SUCCESS`, `FAILED`, `NO_RESULTS`).
5. Implement a config loader that reads `config.yaml` per the schema in Engineering Design §8 (sources, keywords, output, retry, timeouts, rate_limit).
6. Implement a `SourceRegistry` skeleton (Engineering Design §4) that reads the `sources:` block from config and exposes `enabled_sources()`, `priority()`, `schedule()`, `health_status()`, `reliability()` — health/schedule can be stubs for now, but the interface must be real.
7. Set up `pyproject.toml`, `ruff`, `black`, `pytest` per `CLAUDE.md` coding standards.

## Explicitly out of scope for this milestone
- Do NOT implement any real connector (Google Play, App Store, etc.) — that's Milestone 3.
- Do NOT implement the orchestrator, job queue, checkpointing, or idempotency logic — that's Milestone 2.
- Do NOT implement any classification code.

## Acceptance Criteria
- [ ] `Mention` Pydantic model matches Engineering Design §2 exactly, field for field.
- [ ] `BaseConnector` exists as an ABC with all four methods defined (no implementations required).
- [ ] `config.yaml` loads correctly and validates against a config schema.
- [ ] `SourceRegistry.enabled_sources()` correctly reflects the `sources:` block in `config.yaml`.
- [ ] Unit tests exist for the config loader and the Pydantic schema (valid + invalid input cases).
- [ ] `ruff` and `black` run clean.

## Stop condition
Stop when all acceptance criteria are met. Do not proceed to Milestone 2 without review.
