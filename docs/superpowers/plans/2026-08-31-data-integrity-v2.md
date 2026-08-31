# Data Integrity v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make TU ingestion lossless and auditable by preserving all 12 registry columns and separating observation identity, row-version identity, and logical TU identity.

**Architecture:** Extend the raw model and collector, add deterministic v2 identities, shadow-write immutable row versions plus per-run observations, and surface a collision audit. Legacy tables remain active until production validation is complete.

**Tech Stack:** Python 3.11, requests, BeautifulSoup4, psycopg 3, PostgreSQL/Supabase, pytest, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-08-31-data-integrity-v2-design.md`

## Global Constraints

- Preserve all 12 public registry columns.
- Every fetched row in a run must produce exactly one observation.
- Row-version identity is derived from all 12 normalized source fields.
- Logical TU identity is separate from observation identity and row fingerprint.
- Phase A is shadow-write only; no destructive migration of legacy tables.
- Source-published non-date values such as `Дані відсутні` must be preserved losslessly.
- Pull requests run the test suite only; the production database update is skipped for `pull_request` events.

## Tasks

1. Extend `RawTURecord` and collector with `source_row_index`, contract number/date, commissioning stages, and payment date. Add regression tests using live `th + td` row structure.
2. Add `identity.py` with `make_row_fingerprint`, `make_logical_tu_key`, and `make_observation_key`, with deterministic hashing tests.
3. Add idempotent `tu_row_versions` and `tu_observations` schema; do not drop or rename legacy objects.
4. Add `integrity_db.py` shadow writes using parameterized SQL and full `raw_payload`.
5. Wire v2 writes into `pipeline.py` in the same transaction as legacy writes; expose observation and row-version counts in `PipelineSummary`. Observation counts must be confirmed from `tu_observations` for the current `run_id`, not inferred from attempted inserts.
6. Add `integrity_audit.py` to distinguish true duplicate observations from legacy-key collisions and report differing fields.
7. Extend `scripts/update_grid_data.py` with stable `INTEGRITY` and collision-summary log lines.
8. Run full regression, compileall, review diff for destructive changes, open PR, merge only after CI review, then run production validation and verify `observations == raw` for the new run.

## Production Acceptance

The first successful run must emit an integrity line of the form:

```text
INTEGRITY fetched=... observations=... row_versions=... logical_tus=... legacy_unique=... legacy_loss=...
```

and `observations` must equal `fetched`. The collision audit must numerically explain the legacy discrepancy before any Phase B parser-quality changes are started.
