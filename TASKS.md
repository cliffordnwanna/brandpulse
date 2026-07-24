# BrandPulse Build Milestones

Full detail for each milestone lives in `claude/milestones/00X_*.md`. This file is the tracker — check items off as they're completed and reviewed.

- [x] **Milestone 1 — Project Scaffolding** (`claude/milestones/001_project_scaffold.md`)
  Directory structure, config system, BaseConnector interface, canonical schema, Source Registry skeleton.

- [x] **Milestone 2 — Orchestration Core** (`claude/milestones/002_orchestration_core.md`)
  Job queue, run/connector state + checkpointing, idempotent mention_id hashing, logging, retry/failure handling, plugin auto-discovery.

- [x] **Milestone 3 — Google Play Connector** (`claude/milestones/003_google_play_connector.md`)
  First real connector, validated against the canonical schema and contract tests.

- [ ] **Milestone 4 — Bronze + Silver Storage** (`claude/milestones/004_bronze_silver_storage.md`)
  ⚠ `search_term` is now nullable (`collection_scope`/`collection_target` added in Milestone 3) — Silver-stage dedup/grouping must not assume `search_term` is always a string.
  Storage layer, Silver-level near-duplicate detection, language detection.

- [ ] **Milestone 5 — Classification Pipeline + Evaluation** (`claude/milestones/005_classification_evaluation.md`)
  Staged classification pipeline, classification queue, NaijaBERT-primary/LLM-conditional logic, 500-example labeled set, automatic accuracy/precision/recall/F1.

- [ ] **Milestone 6 — Reporting** (`claude/milestones/006_reporting.md`)
  Full CSV output set + Gold tables.

- [ ] **Milestone 7 — Expand Connectors** (`claude/milestones/007_expand_connectors.md`)
  App Store, Nairaland, YouTube — one at a time, each re-validated against the schema and contract tests.

**Rule:** don't start a milestone until the previous one is checked off *and reviewed* — not just checked off.
