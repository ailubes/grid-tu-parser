# Data Integrity v2 Design

## Goal

Make the TU ingestion pipeline lossless and auditable: every source row observed in a registry run must be preserved, while logical TU identity and row-version identity are modeled separately.

## Problem

The production run fetched 8,285 registry rows, but quality analytics saw only 8,011 persisted parsed/raw records. The current `record_key` hashes only `source + tu_number + tu_date + connection_point_raw + requested_power_kw`; different source rows can therefore collide and be merged by `ON CONFLICT`.

The current raw model also stores only 8 of the registry's 12 public columns. Missing fields are:
- contract number;
- contract date;
- commissioning stages / year schedule;
- customer payment date.

This prevents a reliable audit of whether the 274 missing rows are true duplicate source rows, changed versions of the same TU, or accidental key collisions.

## Design principles

1. **Lossless observations** — every row seen in every run is stored once as an observation.
2. **Separate identities** — an observed row, a row version, and a logical TU are different concepts.
3. **No inference in identity** — identifiers use source-published values only.
4. **Idempotent reruns** — reprocessing the same run/page/row must not duplicate observations.
5. **Backward-compatible rollout** — existing tables are preserved until v2 data has been validated in production.
6. **Public-data only** — no hidden topology, load, flow, or spare-capacity inference is introduced.

## Source model

The Lvivoblenergo registry has 12 columns:

1. TU number
2. TU issue date
3. contract number
4. contract date
5. installation type / consumption-generation
6. commissioning stages by years
7. connection/supply point
8. voltage at connection point
9. requested power
10. connection type
11. DSO territorial unit
12. payment receipt date

`RawTURecord` will preserve all 12 values in normalized fields plus `raw_payload`.

## Three identities

### 1. Observation identity

`observation_key = sha256(source + run_id + source_page + source_row_index)`

An observation represents one physical row occurrence in one collection run.

Invariant:

`pipeline raw_count == count(tu_observations where run_id = current_run)`

This is the key invariant that prevents silent data loss.

### 2. Row-version identity

`row_fingerprint = sha256(source + all 12 normalized source columns)`

A row fingerprint identifies the exact published content of a row independent of where or when it was observed.

Two identical source rows on different pages or positions intentionally share a `row_fingerprint`, but remain separate observations.

### 3. Logical TU identity

`logical_tu_key = sha256(source + normalized TU number)` when a TU number exists.

Fallback for missing TU number:

`sha256(source + tu_date + contract_number + connection_point_raw + requested_power_kw)`

This key groups published versions of what appears to be the same TU without deciding that identical row content is the same observation.

## Database model

### New table: `tu_row_versions`

One row per unique `row_fingerprint`.

Fields:
- `row_fingerprint text primary key`
- `logical_tu_key text not null`
- `source text not null`
- all 12 source columns
- `raw_payload jsonb not null`
- `first_seen_at timestamptz not null`
- `last_seen_at timestamptz not null`

### New table: `tu_observations`

One row per row occurrence per pipeline run.

Fields:
- `observation_key text primary key`
- `run_id bigint not null references pipeline_runs(id)`
- `row_fingerprint text not null references tu_row_versions(row_fingerprint)`
- `source_page integer not null`
- `source_row_index integer not null`
- `fetched_at timestamptz not null`
- unique `(run_id, source_page, source_row_index)`

### Parsed data

`tu_parsed` v2 will be keyed by `row_fingerprint`, not the legacy `record_key`, because parsing is a function of row content rather than observation position.

The rollout will not destructively replace the current table until a production v2 run passes integrity checks. During transition, v2 data may be written to `tu_parsed_v2` and promoted afterward.

## Collector changes

`RawTURecord` gains:
- `source_row_index`
- `contract_number`
- `contract_date`
- `commissioning_stages`
- `payment_date`

Header matching expands to all 12 columns.

`source_row_index` is zero- or one-based consistently within each page; implementation will use 1-based indexing to match human inspection.

## Integrity audit

Each successful run produces:

- `fetched_rows`
- `observations_written`
- `unique_row_versions`
- `unique_logical_tus`
- `duplicate_observations` — identical row fingerprints occurring more than once in the same run
- `logical_tus_with_multiple_versions`
- `legacy_unique_records`
- `legacy_collision_loss = fetched_rows - legacy_unique_records`

For the current 8,285-row source snapshot, the audit must explain all 274 rows missing under the legacy key.

The report will include the top collision groups with:
- legacy record key;
- count of source observations;
- count of distinct row fingerprints;
- TU numbers;
- differing source fields.

## Migration strategy

Phase A — shadow-write v2:
- add v2 tables/fields;
- collector produces the full 12-column model;
- pipeline writes legacy tables and v2 tables in the same transaction;
- legacy consumers remain unchanged.

Phase B — validate:
- require `observations_written == fetched_rows`;
- run collision audit;
- compare v2 parsed/node aggregation against legacy output;
- inspect unexpected differences.

Phase C — promote:
- change quality analytics and aggregation to v2 row versions;
- keep observations for run-level lineage;
- remove legacy writes only in a later dedicated migration after stable operation.

No destructive migration is part of the first implementation PR.

## Quality semantics follow-up

After Data Integrity v2 is validated, parser quality will be refactored so that source-data warnings such as `conflicting_voltage_context` are separated from parser uncertainty. That work is intentionally out of scope for this design.

## Success criteria

A production run is successful for Data Integrity v2 when:

1. 8,285 fetched rows produce exactly 8,285 `tu_observations` for that run.
2. Every observation references a valid `tu_row_versions` row.
3. All 12 source fields are persisted.
4. The audit numerically explains the legacy 274-row discrepancy.
5. Rerunning ingestion is idempotent.
6. Existing grid aggregation continues to work during the shadow-write phase.
7. No destructive schema change is required to deploy Phase A.
