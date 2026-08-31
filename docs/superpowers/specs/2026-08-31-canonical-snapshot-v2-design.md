# Canonical Snapshot v2 Design

## Goal

Make Grid Intelligence metrics operate on one current, defensible technical state per logical TU, while preserving the full lossless history captured by Data Integrity v2.

The new layer must prevent duplicate and superseded row versions from inflating MW, TU counts, velocity, pressure, and future GridScore calculations.

## Approved Semantics

1. The latest successful registry run is the current state.
2. TU rows absent from the latest successful run are historical/disappeared and do not contribute to current metrics.
3. Metadata-only revisions collapse to one canonical TU.
4. Material conflicts are never resolved by guessing. They are classified as ambiguous and excluded from canonical MW/pressure.
5. Ambiguous power is represented as a range: `ambiguous_capacity_min_kw` to `ambiguous_capacity_max_kw`.
6. Legacy metrics remain available during rollout for A/B comparison and rollback.

## Material vs Metadata Fields

A material signature is built from these source fields:

- `tu_date`
- `installation_type`
- `connection_point_raw`
- `voltage_raw`
- `requested_power_kw`
- `connection_type`

These fields are material because changes can alter node assignment, activity classification, capacity, recency windows, connection semantics, or resulting node metrics.

The following fields are metadata for canonicalization:

- `contract_number`
- `contract_date`
- `commissioning_stages`
- `rem`
- `payment_date`

Metadata variants remain fully preserved in `tu_row_versions`; canonicalization does not delete or rewrite history.

## Snapshot Resolver

The resolver operates independently for each `run_id` and `logical_tu_key`.

For every logical TU observed in a run:

1. Load all observations for that `run_id + logical_tu_key` through `tu_observations -> tu_row_versions`.
2. Compute the distinct material signatures present in the group.
3. If there is exactly one material signature, classify the logical TU as `canonical`.
4. If there are two or more material signatures, classify it as `ambiguous`.
5. Record the source fields that differ across material signatures as `conflict_fields`.
6. For ambiguous groups, calculate the minimum and maximum non-null requested power values across material variants.

A canonical group may contain many observations and many row versions if those versions differ only in metadata.

## Canonical Representative Row

Canonical parsing requires one representative row fingerprint, but the representative must not encode hidden business meaning.

For a canonical group, all material fields are identical by definition. The resolver selects a deterministic representative row version by sorting the group's row fingerprints and choosing the lexicographically smallest fingerprint.

This choice is only a stable pointer to source data. It is not interpreted as the newest, most authoritative, or legally superior version. All metadata variants remain accessible through the original observation/version tables.

## Persistence

Add a non-destructive table `tu_snapshot_resolution` keyed by `(run_id, logical_tu_key)`.

Required fields:

- `run_id bigint`
- `logical_tu_key text`
- `status text` constrained to `canonical | ambiguous`
- `representative_row_fingerprint text null`
- `observation_count integer`
- `row_version_count integer`
- `material_signature_count integer`
- `conflict_fields jsonb`
- `ambiguous_capacity_min_kw double precision null`
- `ambiguous_capacity_max_kw double precision null`
- `resolution_reason text`
- `resolved_at timestamptz`

Foreign keys should point to `pipeline_runs` and, for canonical rows, `tu_row_versions`.

The table is append-by-run: historical resolutions are retained and never overwritten by later snapshots.

## Current Snapshot Semantics

The current Grid Intelligence snapshot is derived only from the latest successful pipeline run for the relevant source.

No current-state query should combine observations from multiple runs.

If a logical TU existed in run N but is absent from the latest successful run N+1, it is considered `disappeared` for current-state purposes. Its historical row versions and prior snapshot resolution remain intact.

A separate change-history feature may later expose appeared/disappeared/changed states. That is outside this Phase B implementation scope.

## Parser v2 Path

Phase B introduces a canonical parser path rather than immediately replacing legacy `tu_raw` / `tu_parsed`.

For each canonical resolution row:

1. Fetch its representative `tu_row_versions` record.
2. Convert it to the existing parser input shape or an equivalent v2 parser input.
3. Parse exactly once per logical TU.
4. Persist the parsed canonical result in a separate v2 table keyed by `(run_id, logical_tu_key)` or an equivalent stable snapshot identity.

Ambiguous logical TUs do not enter canonical parsing for MW/pressure calculations.

The initial implementation should reuse current deterministic parser rules wherever possible rather than fork parser logic unnecessarily.

## Ambiguity Handling

Ambiguous logical TUs are excluded from canonical capacity and pressure metrics.

For each ambiguous logical TU, the system retains:

- conflict fields;
- number of material variants;
- min/max requested capacity;
- full source row-version lineage.

If all material variants resolve to the same canonical grid node, ambiguity may be attributed to that node for uncertainty reporting only.

If material variants imply different nodes, or node assignment is not reliable, the TU is placed in an unassigned ambiguity bucket. The system must not choose a node by heuristic.

Uncertainty reporting is additive context; it does not enter canonical MW totals.

## Node Metrics v2

Add a separate `node_metrics_v2` table for the rollout period rather than overwriting `node_metrics`.

Canonical metrics should use only canonical logical TUs from one run.

The table should retain the existing core metrics where meaningful, including:

- generation/load/BESS MW;
- TU counts;
- 3/6/12 month MW;
- 3/12 month TU velocity;
- generation/load ratio;
- net TU imbalance;
- BESS share;
- review count;
- data confidence;
- generation/load/BESS pressure.

It should additionally store or be accompanied by ambiguity metrics, including:

- `ambiguous_tu_count`;
- `ambiguous_capacity_min_mw`;
- `ambiguous_capacity_max_mw`.

Unassigned ambiguity should be reported separately and not forced into a node row.

Each v2 metric snapshot must be traceable to a specific `run_id` as well as `snapshot_date`.

## Quality Analytics v2

Quality analytics must be recomputed over the canonical parsed set rather than legacy `tu_raw + tu_parsed`.

This produces a parser-quality baseline that is not distorted by exact duplicates, metadata revisions, or material variants counted as independent TUs.

During B1, output both legacy and v2 quality summaries so the difference is observable.

No parser-rule improvement should be mixed into the first canonicalization rollout. Parser tuning follows after the new baseline is established.

## Pipeline Flow

During Phase B1 the production pipeline becomes:

`collect -> row_versions/observations -> snapshot resolver -> canonical parser v2 -> node_metrics_v2`

while the legacy path continues in parallel:

`collect -> legacy raw/parsed -> legacy node_metrics`

Both paths are generated from the same source run. This allows direct A/B comparison without changing current production consumers.

## Transaction and Failure Behavior

Snapshot resolution, canonical parsing, and v2 metrics for a run should be written in the same data transaction as the existing run data where practical.

A partially written canonical snapshot must not be marked successful.

Resolver or v2 persistence failures should cause the data transaction to roll back and the pipeline run to be marked failed, preserving the current failure semantics.

The latest successful run, not merely the highest run ID, remains the authoritative current snapshot.

## Validation and Logging

Production logs should add a stable canonical summary, for example:

```text
CANONICAL run_id=... logical_tus=... canonical=... ambiguous=... metadata_collapsed=... ambiguous_min_mw=... ambiguous_max_mw=... unassigned_ambiguous=...
```

During B1, log a compact legacy-vs-v2 comparison for the same run, including:

- logical/canonical TU count vs legacy record count;
- mapped count/rate;
- review count/rate;
- node count;
- generation/load/BESS MW;
- ambiguity counts and capacity ranges.

## Acceptance Criteria

The implementation is acceptable when all of the following hold:

1. `canonical + ambiguous == unique logical TUs in the run`.
2. Metadata-only revisions produce exactly one canonical TU.
3. Material conflicts always produce `status=ambiguous` and non-empty `conflict_fields`.
4. No ambiguous TU contributes to canonical MW, TU counts, velocity, or pressure.
5. `ambiguous_capacity_min_kw <= ambiguous_capacity_max_kw` whenever both are present.
6. Current metrics use only the latest successful run.
7. Logical TUs absent from the latest successful run do not contribute to current metrics.
8. Every v2 metric row is traceable to a `run_id`.
9. Legacy and v2 metrics can coexist for the same snapshot without overwriting each other.
10. Resolver output is deterministic for identical input observations.
11. Existing Data Integrity v2 invariants remain valid, especially `observations == fetched`.
12. Existing production consumers continue to read legacy metrics during B1.

## Rollout

### B1 - Shadow Canonical Pipeline

- Add snapshot resolver and persistence.
- Add canonical parsed persistence.
- Add `node_metrics_v2` and ambiguity reporting.
- Add v2 quality summary.
- Keep all legacy writes and consumers unchanged.
- Run on production for 2-3 successful snapshots.

### B2 - Promotion

After 2-3 successful production snapshots:

1. Compare legacy and v2 TU counts, MW, node counts, mapped/review rates, pressure distribution, and ambiguity.
2. Investigate material differences until they are numerically explainable by canonicalization or known parser behavior.
3. Switch dashboard/API consumers to v2 only after explicit approval.
4. Retain legacy tables during an additional rollback period.

Dropping or migrating legacy tables is explicitly outside the scope of this design.

## Out of Scope

- Guessing which material variant is legally authoritative.
- Manual resolution workflow for ambiguous TUs.
- Parser-rule improvements unrelated to canonicalization.
- DSO-specific legal interpretation of revisions.
- Deleting legacy tables.
- Reconstructing hidden grid topology, flows, utilization, or spare capacity.
- Historical appeared/disappeared/change UI beyond retaining the data needed to build it later.
