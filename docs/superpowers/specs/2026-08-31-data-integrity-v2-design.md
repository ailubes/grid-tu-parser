# Data Integrity v2 Design

## Goal

Make the TU ingestion pipeline lossless and auditable: every source row observed in a registry run must be preserved, while logical TU identity and row-version identity are modeled separately.

## Problem

The production run fetched 8,285 registry rows, but quality analytics saw only 8,011 persisted parsed/raw records. The current `record_key` hashes only `source + tu_number + tu_date + connection_point_raw + requested_power_kw`; different source rows can therefore collide and be merged by `ON CONFLICT`.

The current raw model also stores only 8 of the registry's 12 public columns. Missing fields are contract number, contract date, commissioning stages/year schedule, and customer payment date.

## Design principles

1. Lossless observations — every row seen in every run is stored once as an observation.
2. Separate identities — an observed row, a row version, and a logical TU are different concepts.
3. No inference in identity — identifiers use source-published values only.
4. Idempotent reruns — reprocessing the same run/page/row must not duplicate observations.
5. Backward-compatible rollout — existing tables are preserved until v2 data has been validated in production.
6. Public-data only — no hidden topology, load, flow, or spare-capacity inference is introduced.

## Source model

The Lvivoblenergo registry has 12 columns: TU number, TU issue date, contract number, contract date, installation type, commissioning stages, connection point, voltage, requested power, connection type, DSO territorial unit, and payment receipt date.

## Three identities

### Observation identity

`observation_key = sha256(source + run_id + source_page + source_row_index)`

Invariant: `pipeline raw_count == count(tu_observations where run_id = current_run)`.

### Row-version identity

`row_fingerprint = sha256(source + all 12 normalized source columns)`

Identical source rows can share a fingerprint while remaining separate observations.

### Logical TU identity

`logical_tu_key = sha256(source + normalized TU number)` when a TU number exists. A deterministic source-field fallback is used when it does not.

## Database model

`tu_row_versions` stores one row per unique published row fingerprint and all 12 source fields. `tu_observations` stores one row occurrence per pipeline run, keyed by observation identity and linked to its row version.

Source-published contract/payment date fields are stored losslessly as text because the registry may publish non-date values such as `Дані відсутні`.

## Migration strategy

Phase A is shadow-write only: collector emits the full source model, pipeline writes legacy and v2 data in the same transaction, and existing consumers remain unchanged. Phase B validates observation counts and collision audit. Phase C promotes v2 consumers in a later dedicated change.

No destructive migration is part of this implementation PR.

## Integrity audit

Each successful run reports fetched rows, observations written, unique row versions, unique logical TUs, duplicate observations, legacy unique records, and legacy collision loss. Collision groups identify which newly preserved source fields explain legacy-key merges.

## Success criteria

1. Every fetched row produces exactly one observation for its run.
2. Every observation references a valid row version.
3. All 12 source fields are persisted losslessly.
4. The audit numerically explains the legacy row discrepancy.
5. Rerunning ingestion is idempotent.
6. Existing grid aggregation keeps working during shadow-write rollout.
7. No destructive schema change is required.
