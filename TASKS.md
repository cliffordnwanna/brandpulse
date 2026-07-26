# BrandPulse Build Milestones

Full detail for each milestone lives in `claude/milestones/00X_*.md`. This file is the tracker — check items off as they're completed and reviewed.

- [x] **Milestone 1 — Project Scaffolding** (`claude/milestones/001_project_scaffold.md`)
  Directory structure, config system, BaseConnector interface, canonical schema, Source Registry skeleton.

- [x] **Milestone 2 — Orchestration Core** (`claude/milestones/002_orchestration_core.md`)
  Job queue, run/connector state + checkpointing, idempotent mention_id hashing, logging, retry/failure handling, plugin auto-discovery.

- [x] **Milestone 3 — Google Play Connector** (`claude/milestones/003_google_play_connector.md`)
  First real connector, validated against the canonical schema and contract tests.

- [x] **Milestone 4 — Bronze + Silver Storage** (`claude/milestones/004_bronze_silver_storage.md`)
  Storage backend abstraction (`StorageBackend` ABC + `LocalFileStorageBackend` + config-driven factory), Silver-level text-hash dedup, language detection (lingua-py + marker-word heuristics for Pidgin/Hausa/Igbo, which lingua doesn't support), `rebuild_silver_from_bronze` CLI command.

- [x] **Milestone 5 — Classification Pipeline + Evaluation** (`claude/milestones/005_classification_evaluation.md`)
  Tier 5a (sentiment + complaint category, always runs, no LLM) and Tier 5b (emotion/intent/urgency/competitor/summary + low-confidence sentiment re-check + Unknown-category overflow, LLM-conditional, off by default), Classification Queue, versioned Gold writes, `python -m brandpulse classify`/`evaluate` CLI commands, synthetic 500-example labeled set + accuracy/precision/recall/F1/confusion-matrix evaluation, session logging. Model adapters (sentiment/complaint) are pluggable — a lexicon/keyword default runs offline in this environment (no `transformers`/`torch` available here); a HuggingFace adapter is wired against the real spec'd model IDs, documented in `docs/models.md` for switching later.

- [x] **Milestone 6 — Insight Engine + HTML Report** (`claude/milestones/006_reporting.md`)
  `InsightEngine` (Gold -> structured `Insight` objects: emerging issues/anomaly detection, complaint velocity, platform heatmap, phrase mining, competitor mentions, emoji analysis, sentiment overview, drift) fully decoupled from the self-contained HTML renderer (inline CSS, base64 word cloud, no external requests) and from `{run_id}_insights.json` (the bridge file for future PDF/Slack/Power BI renderers). Emoji normalization in Silver (`emoji.demojize`, never stripped). Privacy: author-handle hashing + PII regex scan gate before every output write. `config/taxonomy.yaml` is now the sole source of the complaint taxonomy and competitor list. CLI: `snapshot --window` (default mode, fresh run_id + session-scoped report), `incremental` (checkpoint-based, cumulative archive), `report --run-id <id>|latest`, `compare --run-id <id>|latest`, `export --format csv|json`. `docs/platform-limitations.md` added, embedded in every report.

- [x] **Milestone 7 — Expand Connectors** (`claude/milestones/007_expand_connectors.md`)
  App Store, Nairaland, YouTube — one at a time, each re-validated against the schema and contract tests.

**Rule:** don't start a milestone until the previous one is checked off *and reviewed* — not just checked off.
