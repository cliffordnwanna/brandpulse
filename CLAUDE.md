# BrandPulse — Project Instructions for Claude Code

This file is read automatically at the start of every Claude Code session in this repo. It is the behavioral contract for this project — treat it as ground truth alongside `docs/EngineeringDesign.md`.

## What this project is

BrandPulse — an AI-powered customer voice intelligence platform: a multi-source sentiment/complaint monitoring pipeline, built first for Wema Bank and ALAT. Full context: `docs/PRD.md` (what and why) and `docs/EngineeringDesign.md` (how). Read both before starting any milestone if you don't already have them in context.

Python package name: `brandpulse`, under `src/brandpulse/`.

## Documentation precedence

If documentation conflicts, resolve in this order: (1) this file, (2) the current milestone file in `claude/milestones/`, (3) `docs/EngineeringDesign.md`, (4) `docs/PRD.md`. If a conflict remains after that (e.g. it's a substantive architecture question, not a formatting detail), stop and ask rather than picking silently — as with the `src/` layout vs. Engineering Design §19's flat tree, where this file's `src/` layout wins and §19's tree is illustrative of module boundaries, not literal paths.

## Architecture Invariants — never violate these

```
1.  Never bypass the canonical schema (EngineeringDesign.md §2).
2.  Never let connectors communicate directly with classifiers — only through Bronze/Silver.
3.  Never overwrite Bronze — append-only, always.
4.  Never overwrite a classification — new classifier version = new Gold record, old one kept.
5.  Never hardcode prompts — every prompt is a versioned file under prompts/.
6.  Never hardcode keywords, source lists, timeouts, or rate limits — config.yaml only.
7.  Every new connector must inherit BaseConnector and pass the shared contract tests.
8.  Every classification pipeline stage must be independently executable and testable.
9.  Every output must be reproducible from Bronze alone.
10. Every ingestion run must be idempotent via content-hash mention_id.
11. Every module must have unit tests before merge.
12. NaijaBERT handles sentiment/emotion for every mention; the LLM is called only for
    summaries, unknown-topic overflow, and low-confidence cases — never as the default path.
```

## How we work — milestone discipline

- Work is broken into 7 milestones, defined in `TASKS.md` and detailed one-per-file in `claude/milestones/`.
- **Implement exactly one milestone at a time.** Read the milestone file, build only what it specifies, then stop.
- **Do not start the next milestone without being asked.** Each milestone ends with a human review — that review is not optional, and it's not a formality to skip through.
- Do not "helpfully" implement pieces of a later milestone while working on an earlier one, even if it looks convenient in the moment — that's how architectural drift happens.
- If a milestone's acceptance criteria can't be met as written, stop and flag it rather than quietly reinterpreting the requirement.

## Coding standards (default — adjust if you have existing conventions)

- Python 3.11+, `pyproject.toml`, `src/` layout
- Full type hints; Pydantic models for the canonical schema and config
- `pytest` for all tests; `ruff` for linting; `black` for formatting
- Composition over inheritance except where `BaseConnector` subclassing is the explicit pattern (Engineering Design §3)
- No global state — pass config/registry/state explicitly
- Keep functions small and single-purpose where practical

## When you finish a milestone

1. Run the full test suite.
2. Confirm every acceptance criterion in the milestone file explicitly — don't just say "done."
3. Update `TASKS.md` — check off the completed milestone.
4. Stop and report what was built, what passed, and anything that deviated from the spec and why.
