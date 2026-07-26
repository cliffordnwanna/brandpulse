# Milestone 4 — Bronze + Silver Storage

## Objective
Build a storage abstraction layer with Bronze and Silver tiers. The key design requirement is **storage-backend independence** — the pipeline should write to local files today, and swap to Azure Blob Storage, Fabric Lakehouse, or any other backend in the future by changing one config value, not by rewriting the pipeline.

## Read first
- `docs/EngineeringDesign.md` §9 (Storage Design), §11 (Deduplication Strategy)
- `CLAUDE.md` Architecture Invariants (Bronze append-only, Silver regenerable from Bronze)
- Milestone 3's `GooglePlayConnector` output shape — what Bronze actually needs to receive

## Core design requirement — storage abstraction

Define a `StorageBackend` abstract interface **before** implementing any concrete backend:

```python
class StorageBackend(ABC):
    def write(self, tier: Literal["bronze", "silver", "gold"], mention_id: str, record: dict) -> None:
        """Idempotent — writing the same mention_id twice is a no-op."""

    def exists(self, tier: str, mention_id: str) -> bool: ...

    def read_all(self, tier: str) -> Iterable[dict]: ...

    def delete(self, tier: str, mention_id: str) -> None:
        """Bronze must never call this — raise NotImplementedError or enforce via policy."""
```

Then implement `LocalFileStorageBackend` (JSON files under `storage/bronze/`, `storage/silver/`, `storage/gold/`) as the only concrete backend for now.

The path root (`storage/`) comes from config — never hardcoded — so switching to `az://container/brandpulse/` or `/mnt/fabric/lakehouse/` later is one config line, no code change.

## Requirements

1. **`StorageBackend` ABC** — defined in `storage/base.py`. All pipeline code depends on this interface, never on `LocalFileStorageBackend` directly.

2. **`LocalFileStorageBackend`** — in `storage/local.py`. Writes each record as a JSON file keyed by `mention_id` under `{root}/{tier}/{mention_id}.json`. `write()` is idempotent: if the file exists, do nothing. `delete()` raises `OperationNotPermittedError` for Bronze tier — enforces append-only at the backend level, not just by convention.

3. **Backend is injected, never imported directly** — the orchestrator and pipeline receive a `StorageBackend` instance via constructor, resolved from config at startup. This is what makes swapping backends a config change, not a code change.

4. **Config-driven backend selection** — add a `storage:` block to `config.yaml`:
   ```yaml
   storage:
     backend: local          # future values: azure_blob, fabric_lakehouse, s3
     root: ./storage          # local path, or container URL for cloud backends
   ```
   A `StorageBackendFactory.from_config(config)` function resolves this to the right concrete class. Adding a new backend later = new class + one new branch in the factory, nothing else changes.

5. **Bronze write** — connector output (a `RunResult`) flows into `StorageBackend.write("bronze", mention_id, record)` immediately after each page/batch, checkpointed per Milestone 2's orchestrator loop. Every record written to Bronze must include the full `raw_json` field — never stripped at this stage.

6. **Silver pipeline** — reads from Bronze, applies:
   - **Tier-1 dedup** (connector already handled exact-match within a batch; Silver handles cross-source/cross-run): text hash dedup — `SHA256(normalized_text)`. If hash already exists in Silver, skip. No embedding similarity for MVP (too slow/expensive locally) — document that as a Phase 2 upgrade, don't implement now.
   - **Language detection** — use `lingua-py` (not `langdetect`, which confidently misclassifies short Pidgin/code-mixed text). Detect and tag: English, Nigerian Pidgin, Yoruba, Hausa, Igbo. Unknown/ambiguous → `"und"`. Store the detected language in the Silver record's `language` field (the canonical schema field that was `null` at Bronze).
   - Write to `StorageBackend.write("silver", mention_id, record)`.

7. **Silver regeneration** — a `rebuild_silver_from_bronze(backend: StorageBackend)` function that wipes Silver and reprocesses every Bronze record from scratch. This is the guarantee that Silver is never the source of truth — Bronze is. Expose this as a CLI command: `python -m brandpulse rebuild-silver`.

8. **Wire into the orchestrator** — after each connector page's Bronze write, trigger Silver processing for that batch (incremental, not full-rebuild). Full rebuild is only for the explicit CLI command.

## Language detection note
Nigerian Pidgin is genuinely hard to detect automatically — `lingua-py` will sometimes still misclassify it as English. That's acceptable for MVP. What matters is that the `language` field is always populated in Silver (never `null`), the detection is consistent and reproducible, and the field is easy for the classifier in Milestone 5 to read and act on.

## Explicitly out of scope for this milestone
- Do NOT implement Gold or any classification logic — that's Milestone 5.
- Do NOT implement Azure Blob, Fabric, or any cloud backend — `LocalFileStorageBackend` only.
- Do NOT implement embedding-similarity near-duplicate detection — text hash only for MVP.
- Do NOT implement additional connectors.

## Acceptance Criteria
- [ ] `StorageBackend` ABC exists and all pipeline code depends on it, not on `LocalFileStorageBackend` directly.
- [ ] Swapping `storage.backend: local` to a hypothetical `storage.backend: azure_blob` in config requires zero code changes outside of `storage/` and `StorageBackendFactory`.
- [ ] Bronze is append-only at the backend level — calling `backend.delete("bronze", id)` raises `OperationNotPermittedError`.
- [ ] Writing the same `mention_id` to Bronze twice produces exactly one record, not two.
- [ ] A deliberately duplicated input run through the full Silver pipeline produces exactly one Silver record.
- [ ] `rebuild_silver_from_bronze()` produces an identical Silver dataset to the incrementally-built one (tested with a fixed set of Bronze records).
- [ ] Every Silver record has a non-null `language` field.
- [ ] A hand-checked sample of at least 5 Pidgin phrases and 5 standard English phrases are routed to different language codes.
- [ ] Full test suite still passes; new unit tests cover backend write/idempotency, Silver dedup, language detection, and the rebuild function.

## Stop condition
Stop when all acceptance criteria are met. Update `TASKS.md`. Do not proceed to Milestone 5 without review.
