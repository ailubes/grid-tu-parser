# PostgreSQL Daily Pipeline Design

Date: 2026-08-30

## Goal

Turn `grid-tu-parser` into an idempotent daily data pipeline that collects the public Lvivoblenergo TU registry, preserves raw and parsed records, aggregates canonical grid nodes, stores daily node snapshots, and records every pipeline run in PostgreSQL/Supabase.

## Architecture

`collect_pages()` -> `parse_record()` -> database upserts -> `aggregate_nodes()` -> node upserts -> daily metric snapshots -> `pipeline_runs` status.

The database is authoritative for historical snapshots. Raw and parsed TU rows are upserted by a stable source key so repeated daily runs do not create duplicates. Node metrics are keyed by `(canonical_node_id, snapshot_date)` so rerunning the same day replaces the snapshot instead of appending duplicates.

## Tables

- `tu_raw`: source registry record as collected, plus deterministic `record_key`.
- `tu_parsed`: normalized parser result keyed by `record_key` and linked to `tu_raw`.
- `grid_nodes`: one current row per `canonical_node_id` with last-seen metadata.
- `node_metrics`: immutable-in-time daily snapshots, upsertable for the same date.
- `pipeline_runs`: one row per execution with status, counts, timestamps, and error text.

## Idempotency

`record_key = sha256(source + tu_number + tu_date + connection_point_raw + requested_power_kw)`.

The collector may rediscover the same TU every day. `tu_raw.record_key` and `tu_parsed.record_key` are primary keys. `grid_nodes.canonical_node_id` is a primary key. `node_metrics` has primary key `(canonical_node_id, snapshot_date)`.

## Database access

Use `psycopg` 3 and a single `DATABASE_URL` environment variable. Transactions are explicit. The pipeline writes a `running` run row first, commits data atomically, then marks the run `success`; failures mark the run `failed` with a truncated error message.

## GitHub Actions

Run daily at `00:00 UTC` (03:00 Kyiv during EEST) and allow manual `workflow_dispatch`. Install package with dev dependencies, run tests, then run `python scripts/update_grid_data.py`. The secret `DATABASE_URL` lives only in GitHub Actions secrets.

## Security

No credentials in source control. `DATABASE_URL` uses TLS in hosted PostgreSQL/Supabase. The pipeline account needs only INSERT/UPDATE/SELECT on the five pipeline tables; public web/API access should later use separate roles/RLS.

## Non-goals

- No public API yet.
- No dashboard yet.
- No SCADA/real-time capacity claims.
- No deletion of historical records when a TU disappears from the source registry; disappearance tracking can be added separately.
