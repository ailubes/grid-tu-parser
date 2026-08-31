# Canonical Snapshot v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a shadow canonical-snapshot pipeline that resolves one defensible current technical state per logical TU, excludes material conflicts from canonical MW/pressure, persists uncertainty, and produces parallel v2 metrics and quality analytics without changing legacy consumers.

**Architecture:** Keep Data Integrity v2 (`tu_row_versions`, `tu_observations`) as the immutable source. Add a pure snapshot resolver that classifies each `run_id + logical_tu_key` as canonical or ambiguous from six material fields, reuse the existing deterministic parser for canonical records, attribute ambiguity only when every material variant maps to the same node, and persist parallel `tu_snapshot_resolution`, `tu_canonical_parsed`, and `node_metrics_v2` outputs. Legacy `tu_raw`, `tu_parsed`, and `node_metrics` continue unchanged during B1.

**Tech Stack:** Python 3.11, dataclasses, hashlib/JSON identity already present, psycopg 3, PostgreSQL/Supabase, pytest, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-08-31-canonical-snapshot-v2-design.md`

## Global Constraints

- The latest successful registry run is the current state.
- TU rows absent from the latest successful run are historical/disappeared and do not contribute to current metrics.
- Metadata-only revisions collapse to one canonical TU.
- Material conflicts are never resolved by guessing; ambiguous TUs are excluded from canonical MW/pressure.
- Material fields are exactly: `tu_date`, `installation_type`, `connection_point_raw`, `voltage_raw`, `requested_power_kw`, `connection_type`.
- Metadata fields are: `contract_number`, `contract_date`, `commissioning_stages`, `rem`, `payment_date`.
- Ambiguous power is represented as `min/max`, not a single guessed number.
- All legacy tables and current consumers remain active during B1.
- Existing Data Integrity v2 invariant `observations == fetched` must remain intact.
- No parser-rule tuning is mixed into canonicalization work.
- No destructive DDL.

---

## File Structure

### New files

- `grid_tu_parser/snapshot.py` — pure material-signature grouping and canonical/ambiguous resolution; no SQL.
- `grid_tu_parser/canonical.py` — canonical parsing wrapper plus ambiguous-node attribution using the existing `parse_record()`.
- `grid_tu_parser/canonical_db.py` — persistence for snapshot resolutions, canonical parsed rows, and v2 node metrics.
- `tests/test_snapshot.py` — resolver behavior and determinism.
- `tests/test_canonical.py` — canonical parse and ambiguity attribution.
- `tests/test_canonical_db.py` — parameterized SQL/persistence contracts.
- `tests/test_canonical_schema.py` — additive schema and current-view assertions.
- `tests/test_canonical_pipeline.py` — end-to-end orchestration of the B1 shadow path.
- `tests/test_canonical_cli.py` — stable `CANONICAL` and `QUALITY_V2` logging.

### Modified files

- `schema.sql` — add `tu_snapshot_resolution`, `tu_canonical_parsed`, `node_metrics_v2`, and `current_node_metrics_v2` view.
- `grid_tu_parser/aggregate.py` — add ambiguity fields to `NodeAggregate`; legacy aggregation still leaves them at zero.
- `grid_tu_parser/database.py` — expose `METRIC_FIELDS` for reuse while retaining `_METRIC_FIELDS` compatibility.
- `grid_tu_parser/pipeline.py` — run canonical shadow flow in the same data transaction and extend `PipelineSummary`.
- `grid_tu_parser/quality.py` — allow a report label so legacy and v2 output are distinguishable without duplicating analytics.
- `grid_tu_parser/quality_db.py` — fetch quality rows from `tu_canonical_parsed` for a specific run.
- `scripts/update_grid_data.py` — render canonical summary and v2 quality after the existing integrity/legacy output.
- `tests/test_pipeline.py`, `tests/test_database.py`, `tests/test_quality_analytics.py`, `tests/test_schema.py` — regression coverage for changed public interfaces.
- `README.md` — document B1 shadow semantics and production acceptance checks.

---

### Task 1: Pure Snapshot Resolver

**Files:**
- Create: `grid_tu_parser/snapshot.py`
- Create: `tests/test_snapshot.py`

**Interfaces:**
- Consumes: `RawTURecord`, `make_logical_tu_key(record)`, `make_row_fingerprint(record)`.
- Produces:
  - `MATERIAL_FIELDS: tuple[str, ...]`
  - `SnapshotResolution`
  - `SnapshotResolutionResult`
  - `material_signature(record: RawTURecord) -> tuple[object, ...]`
  - `resolve_snapshot(records: Iterable[RawTURecord]) -> SnapshotResolutionResult`

- [ ] **Step 1: Write failing tests for metadata collapse, material conflict, ranges, and determinism**

```python
from dataclasses import replace
from datetime import datetime, timezone

from grid_tu_parser.models import RawTURecord
from grid_tu_parser.snapshot import resolve_snapshot


def rec(row: int, **changes) -> RawTURecord:
    base = RawTURecord(
        source="lvivoblenergo",
        source_url="https://example.test",
        source_page=1,
        source_row_index=row,
        fetched_at=datetime(2026, 8, 31, tzinfo=timezone.utc),
        tu_number="ТУ 123",
        tu_date="2026-08-30",
        installation_type="генерація",
        connection_point_raw="РУ-10 кВ ПС 35/10 кВ №201 Чишки",
        voltage_raw="10",
        requested_power_kw=1000.0,
        connection_type="нестандартне",
        rem="ЛМЕМ",
        contract_number="D-1",
        contract_date="2026-08-20",
        commissioning_stages="2026",
        payment_date="2026-08-21",
    )
    return replace(base, **changes)


def test_metadata_only_versions_collapse_to_one_canonical_tu():
    result = resolve_snapshot([
        rec(1),
        rec(2, payment_date="2026-08-22", rem="ІНШИЙ РЕМ"),
    ])
    resolution = result.resolutions[0]
    assert resolution.status == "canonical"
    assert resolution.observation_count == 2
    assert resolution.row_version_count == 2
    assert resolution.material_signature_count == 1
    assert resolution.conflict_fields == ()
    assert result.metadata_collapsed_tu_count == 1
    assert len(result.canonical_records) == 1


def test_power_conflict_is_ambiguous_and_excluded_from_canonical_records():
    result = resolve_snapshot([
        rec(1, requested_power_kw=1000.0),
        rec(2, requested_power_kw=1500.0),
    ])
    resolution = result.resolutions[0]
    assert resolution.status == "ambiguous"
    assert resolution.conflict_fields == ("requested_power_kw",)
    assert resolution.ambiguous_capacity_min_kw == 1000.0
    assert resolution.ambiguous_capacity_max_kw == 1500.0
    assert result.canonical_records == []
    assert len(result.ambiguous_groups[resolution.logical_tu_key]) == 2


def test_representative_fingerprint_is_deterministic_for_metadata_variants():
    first = resolve_snapshot([rec(1), rec(2, payment_date="2026-08-22")])
    second = resolve_snapshot([rec(2, payment_date="2026-08-22"), rec(1)])
    assert first.resolutions[0].representative_row_fingerprint == second.resolutions[0].representative_row_fingerprint
    assert first.resolutions[0].representative_row_fingerprint is not None
```

- [ ] **Step 2: Run the resolver tests and verify RED**

Run:

```bash
pytest tests/test_snapshot.py -v
```

Expected: FAIL because `grid_tu_parser.snapshot` does not exist.

- [ ] **Step 3: Implement the resolver dataclasses and exact six-field material signature**

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .identity import make_logical_tu_key, make_row_fingerprint
from .models import RawTURecord

MATERIAL_FIELDS = (
    "tu_date",
    "installation_type",
    "connection_point_raw",
    "voltage_raw",
    "requested_power_kw",
    "connection_type",
)


@dataclass(frozen=True)
class SnapshotResolution:
    logical_tu_key: str
    status: str
    representative_row_fingerprint: str | None
    observation_count: int
    row_version_count: int
    material_signature_count: int
    conflict_fields: tuple[str, ...]
    ambiguous_capacity_min_kw: float | None
    ambiguous_capacity_max_kw: float | None
    resolution_reason: str


@dataclass
class SnapshotResolutionResult:
    resolutions: list[SnapshotResolution]
    canonical_records: list[RawTURecord]
    ambiguous_groups: dict[str, list[RawTURecord]]
    metadata_collapsed_tu_count: int


def material_signature(record: RawTURecord) -> tuple[object, ...]:
    return tuple(getattr(record, field) for field in MATERIAL_FIELDS)
```

Implement `resolve_snapshot()` with these exact rules:

```python
# group observations by make_logical_tu_key(record)
# dedupe row versions by make_row_fingerprint(record)
# compute distinct material_signature(record) values from distinct row versions
# one signature => canonical
# 2+ signatures => ambiguous
# representative canonical fingerprint => lexicographically smallest row fingerprint
# conflict_fields => MATERIAL_FIELDS whose values vary across material signatures, preserving MATERIAL_FIELDS order
# ambiguous min/max => min/max non-null requested_power_kw across distinct material signatures
# canonical_records => representative RawTURecord only, sorted by logical_tu_key
# ambiguous_groups => distinct row-version RawTURecords for ambiguous keys, sorted by row fingerprint
# metadata_collapsed_tu_count => canonical logical TUs with row_version_count > 1
```

- [ ] **Step 4: Add edge-case tests for exact duplicates and null power**

```python
def test_exact_duplicate_observations_do_not_create_extra_row_versions():
    a = rec(1)
    duplicate = replace(a, source_page=2, source_row_index=8)
    result = resolve_snapshot([a, duplicate])
    resolution = result.resolutions[0]
    assert resolution.observation_count == 2
    assert resolution.row_version_count == 1
    assert resolution.material_signature_count == 1
    assert resolution.status == "canonical"


def test_ambiguous_group_with_no_published_power_keeps_range_null():
    result = resolve_snapshot([
        rec(1, requested_power_kw=None, voltage_raw="10"),
        rec(2, requested_power_kw=None, voltage_raw="6"),
    ])
    resolution = result.resolutions[0]
    assert resolution.status == "ambiguous"
    assert resolution.ambiguous_capacity_min_kw is None
    assert resolution.ambiguous_capacity_max_kw is None
```

- [ ] **Step 5: Run Task 1 tests and full identity/integrity regression**

```bash
pytest tests/test_snapshot.py tests/test_identity.py tests/test_integrity_v2.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit Task 1**

```bash
git add grid_tu_parser/snapshot.py tests/test_snapshot.py
git commit -m "feat: add canonical snapshot resolver"
```

---

### Task 2: Additive Canonical Schema and Resolution Persistence

**Files:**
- Modify: `schema.sql`
- Create: `grid_tu_parser/canonical_db.py`
- Create: `tests/test_canonical_schema.py`
- Create: `tests/test_canonical_db.py`

**Interfaces:**
- Consumes: `SnapshotResolution` from Task 1.
- Produces:
  - `upsert_snapshot_resolutions(conn, run_id: int, resolutions: Iterable[SnapshotResolution]) -> int`
  - additive table `tu_snapshot_resolution`.

- [ ] **Step 1: Write failing schema tests**

```python
from pathlib import Path


def test_schema_adds_non_destructive_snapshot_resolution_table():
    sql = Path("schema.sql").read_text(encoding="utf-8").lower()
    assert "create table if not exists tu_snapshot_resolution" in sql
    assert "primary key (run_id, logical_tu_key)" in sql
    assert "status in ('canonical', 'ambiguous')" in sql
    assert "ambiguous_capacity_min_kw" in sql
    assert "ambiguous_capacity_max_kw" in sql
    assert "references tu_row_versions(row_fingerprint)" in sql
    assert "drop table" not in sql
    assert "drop column" not in sql
```

- [ ] **Step 2: Run schema test and verify RED**

```bash
pytest tests/test_canonical_schema.py::test_schema_adds_non_destructive_snapshot_resolution_table -v
```

Expected: FAIL because the table is absent.

- [ ] **Step 3: Add the table with checks that enforce resolver invariants**

Add to `schema.sql`:

```sql
create table if not exists tu_snapshot_resolution (
    run_id bigint not null references pipeline_runs(id),
    logical_tu_key text not null,
    status text not null check (status in ('canonical', 'ambiguous')),
    representative_row_fingerprint text references tu_row_versions(row_fingerprint),
    observation_count integer not null check (observation_count >= 1),
    row_version_count integer not null check (row_version_count >= 1),
    material_signature_count integer not null check (material_signature_count >= 1),
    conflict_fields jsonb not null default '[]'::jsonb,
    ambiguous_capacity_min_kw double precision,
    ambiguous_capacity_max_kw double precision,
    resolution_reason text not null,
    resolved_at timestamptz not null default now(),
    primary key (run_id, logical_tu_key),
    check (
        ambiguous_capacity_min_kw is null
        or ambiguous_capacity_max_kw is null
        or ambiguous_capacity_min_kw <= ambiguous_capacity_max_kw
    ),
    check (
        (status = 'canonical' and representative_row_fingerprint is not null)
        or (status = 'ambiguous' and representative_row_fingerprint is null)
    )
);

create index if not exists idx_tu_snapshot_resolution_run_status
    on tu_snapshot_resolution(run_id, status);
```

- [ ] **Step 4: Write failing persistence test using a fake cursor**

```python
from grid_tu_parser.canonical_db import upsert_snapshot_resolutions
from grid_tu_parser.snapshot import SnapshotResolution


def test_upsert_snapshot_resolutions_is_idempotent_and_parameterized(fake_conn):
    row = SnapshotResolution(
        logical_tu_key="logical-1",
        status="canonical",
        representative_row_fingerprint="fp-1",
        observation_count=2,
        row_version_count=2,
        material_signature_count=1,
        conflict_fields=(),
        ambiguous_capacity_min_kw=None,
        ambiguous_capacity_max_kw=None,
        resolution_reason="single_material_signature",
    )
    assert upsert_snapshot_resolutions(fake_conn, 7, [row]) == 1
    sql, params = fake_conn.cursor_obj.calls[0]
    assert "on conflict (run_id, logical_tu_key) do update" in sql.lower()
    assert params[0][0:3] == (7, "logical-1", "canonical")
```

Use the existing fake-connection style from `tests/test_integrity_v2.py`; define the fake in this test file rather than creating a shared fixture.

- [ ] **Step 5: Run persistence test and verify RED**

```bash
pytest tests/test_canonical_db.py::test_upsert_snapshot_resolutions_is_idempotent_and_parameterized -v
```

Expected: FAIL because `canonical_db.py` does not exist.

- [ ] **Step 6: Implement minimal resolution upsert**

`canonical_db.py` should JSON-encode `conflict_fields` with `ensure_ascii=False` and use `executemany()` with parameter placeholders only. The upsert updates all derived resolution columns and `resolved_at = now()`.

- [ ] **Step 7: Run Task 2 tests**

```bash
pytest tests/test_canonical_schema.py tests/test_canonical_db.py tests/test_data_integrity_schema.py -v
```

Expected: PASS.

- [ ] **Step 8: Commit Task 2**

```bash
git add schema.sql grid_tu_parser/canonical_db.py tests/test_canonical_schema.py tests/test_canonical_db.py
git commit -m "feat: persist canonical snapshot resolutions"
```

---

### Task 3: Canonical Parser Wrapper and Canonical Parsed Persistence

**Files:**
- Create: `grid_tu_parser/canonical.py`
- Modify: `grid_tu_parser/canonical_db.py`
- Modify: `schema.sql`
- Create: `tests/test_canonical.py`
- Modify: `tests/test_canonical_db.py`
- Modify: `tests/test_canonical_schema.py`

**Interfaces:**
- Consumes: `SnapshotResolutionResult`, existing `parse_record(RawTURecord) -> ParsedTURecord`.
- Produces:
  - `CanonicalParsedRecord(logical_tu_key: str, representative_row_fingerprint: str, parsed: ParsedTURecord)`
  - `parse_canonical_snapshot(result: SnapshotResolutionResult) -> list[CanonicalParsedRecord]`
  - `upsert_canonical_parsed(conn, run_id: int, rows: Iterable[CanonicalParsedRecord]) -> int`
  - additive table `tu_canonical_parsed`.

- [ ] **Step 1: Write failing canonical parser test**

```python
from grid_tu_parser.canonical import parse_canonical_snapshot
from grid_tu_parser.snapshot import resolve_snapshot


def test_canonical_parser_runs_once_per_logical_tu():
    resolved = resolve_snapshot([
        rec(1),
        rec(2, payment_date="2026-08-22"),
    ])
    parsed = parse_canonical_snapshot(resolved)
    assert len(parsed) == 1
    assert parsed[0].logical_tu_key == resolved.resolutions[0].logical_tu_key
    assert parsed[0].representative_row_fingerprint == resolved.resolutions[0].representative_row_fingerprint
    assert parsed[0].parsed.requested_power_kw == 1000.0
```

Reuse a local `rec()` helper in `tests/test_canonical.py`; do not import test helpers from another test module.

- [ ] **Step 2: Run and verify RED**

```bash
pytest tests/test_canonical.py::test_canonical_parser_runs_once_per_logical_tu -v
```

Expected: FAIL because `canonical.py` is absent.

- [ ] **Step 3: Implement `CanonicalParsedRecord` and wrapper**

```python
@dataclass(frozen=True)
class CanonicalParsedRecord:
    logical_tu_key: str
    representative_row_fingerprint: str
    parsed: ParsedTURecord


def parse_canonical_snapshot(result: SnapshotResolutionResult) -> list[CanonicalParsedRecord]:
    resolution_by_fp = {
        item.representative_row_fingerprint: item
        for item in result.resolutions
        if item.status == "canonical" and item.representative_row_fingerprint
    }
    rows = []
    for raw in result.canonical_records:
        fp = make_row_fingerprint(raw)
        resolution = resolution_by_fp[fp]
        rows.append(CanonicalParsedRecord(resolution.logical_tu_key, fp, parse_record(raw)))
    return sorted(rows, key=lambda item: item.logical_tu_key)
```

- [ ] **Step 4: Add `tu_canonical_parsed` schema test, then schema**

Test for:

```text
create table if not exists tu_canonical_parsed
primary key (run_id, logical_tu_key)
representative_row_fingerprint ... references tu_row_versions(row_fingerprint)
canonical_node_id
confidence
needs_review
flags
parsed_payload
```

Add a table mirroring the useful parsed fields from `tu_parsed`, but keyed by `(run_id, logical_tu_key)` and carrying `representative_row_fingerprint`. Include `requested_power_kw`, `activity_type`, node/parent fields, confidence/review/flags/error, and `parsed_payload`.

- [ ] **Step 5: Write failing DB upsert test**

Assert that `upsert_canonical_parsed(conn, 7, rows)` uses `ON CONFLICT (run_id, logical_tu_key) DO UPDATE`, writes the representative fingerprint, and returns row count.

- [ ] **Step 6: Implement `upsert_canonical_parsed`**

Serialize `parent_voltage_levels_kv`, `flags`, and `parsed.to_dict()` to JSON using the same compact UTF-8 rules already used in the project.

- [ ] **Step 7: Run Task 3 tests plus existing parser tests**

```bash
pytest tests/test_canonical.py tests/test_canonical_db.py tests/test_canonical_schema.py tests/test_parser.py -v
```

Expected: PASS, with no changes to parser rules.

- [ ] **Step 8: Commit Task 3**

```bash
git add grid_tu_parser/canonical.py grid_tu_parser/canonical_db.py schema.sql tests/test_canonical.py tests/test_canonical_db.py tests/test_canonical_schema.py
git commit -m "feat: add canonical parsed snapshot path"
```

---

### Task 4: Ambiguous Node Attribution Without Guessing

**Files:**
- Modify: `grid_tu_parser/canonical.py`
- Modify: `tests/test_canonical.py`

**Interfaces:**
- Consumes: `SnapshotResolutionResult.ambiguous_groups`, existing `parse_record()`.
- Produces:
  - `AmbiguityBucket`
  - `AmbiguityAnalysis`
  - `analyze_ambiguity(result: SnapshotResolutionResult) -> AmbiguityAnalysis`

`AmbiguityBucket` fields:

```python
@dataclass(frozen=True)
class AmbiguityBucket:
    canonical_node_id: str | None
    ambiguous_tu_count: int
    capacity_min_mw: float | None
    capacity_max_mw: float | None
```

`AmbiguityAnalysis` fields:

```python
@dataclass
class AmbiguityAnalysis:
    by_node: dict[str, AmbiguityBucket]
    unassigned: AmbiguityBucket
    node_evidence_records: list[ParsedTURecord]
```

- [ ] **Step 1: Write failing same-node and different-node tests**

```python
def test_ambiguous_variants_are_attributed_only_when_all_map_to_same_node():
    resolved = resolve_snapshot([
        rec(1, requested_power_kw=1000.0),
        rec(2, requested_power_kw=1500.0),
    ])
    analysis = analyze_ambiguity(resolved)
    bucket = next(iter(analysis.by_node.values()))
    assert bucket.ambiguous_tu_count == 1
    assert bucket.capacity_min_mw == 1.0
    assert bucket.capacity_max_mw == 1.5
    assert analysis.unassigned.ambiguous_tu_count == 0


def test_conflicting_nodes_go_to_unassigned_bucket():
    resolved = resolve_snapshot([
        rec(1, connection_point_raw="РУ-10 кВ ПС 35/10 кВ №201 Чишки"),
        rec(2, connection_point_raw="РУ-10 кВ ПС 35/10 кВ №144 Страдч"),
    ])
    analysis = analyze_ambiguity(resolved)
    assert analysis.by_node == {}
    assert analysis.unassigned.ambiguous_tu_count == 1
```

- [ ] **Step 2: Run and verify RED**

```bash
pytest tests/test_canonical.py -k ambiguity -v
```

Expected: FAIL because ambiguity analysis does not exist.

- [ ] **Step 3: Implement material-variant parsing and conservative attribution**

For each ambiguous logical TU:

1. Deduplicate variants by `material_signature()`.
2. For each signature choose the lexicographically smallest row fingerprint only as deterministic parser input.
3. Parse those distinct material variants using `parse_record()`.
4. Attribute to a node only when every parsed variant has the same non-null `canonical_node_id`.
5. If any variant is unmapped or maps to a different node, use the unassigned bucket.
6. Sum TU-level min/max ranges across attributed groups.
7. If any TU in a bucket has no known capacity range, set the bucket min/max to `None` rather than presenting a false aggregate bound.

- [ ] **Step 4: Add null-capacity conservative aggregation test**

```python
def test_unknown_ambiguous_capacity_makes_bucket_range_unknown():
    resolved = resolve_snapshot([
        rec(1, requested_power_kw=None, voltage_raw="10"),
        rec(2, requested_power_kw=None, voltage_raw="6"),
    ])
    analysis = analyze_ambiguity(resolved)
    bucket = next(iter(analysis.by_node.values()))
    assert bucket.capacity_min_mw is None
    assert bucket.capacity_max_mw is None
```

- [ ] **Step 5: Run canonical and parser regressions**

```bash
pytest tests/test_canonical.py tests/test_parser.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit Task 4**

```bash
git add grid_tu_parser/canonical.py tests/test_canonical.py
git commit -m "feat: attribute ambiguous TU ranges conservatively"
```

---

### Task 5: V2 Node Metrics and Current Successful Snapshot View

**Files:**
- Modify: `grid_tu_parser/aggregate.py`
- Modify: `grid_tu_parser/database.py`
- Modify: `grid_tu_parser/canonical_db.py`
- Modify: `schema.sql`
- Modify: `tests/test_aggregate.py`
- Modify: `tests/test_database.py`
- Modify: `tests/test_canonical_db.py`
- Modify: `tests/test_canonical_schema.py`

**Interfaces:**
- Consumes: existing `aggregate_nodes()`, `AmbiguityAnalysis`.
- Produces:
  - `NodeAggregate.ambiguous_tu_count`
  - `NodeAggregate.ambiguous_capacity_min_mw`
  - `NodeAggregate.ambiguous_capacity_max_mw`
  - `apply_ambiguity(nodes: Iterable[NodeAggregate], analysis: AmbiguityAnalysis) -> list[NodeAggregate]`
  - `METRIC_FIELDS` public alias in `database.py`
  - `upsert_node_metrics_v2(conn, run_id, nodes, snapshot_date) -> int`
  - tables/view `node_metrics_v2`, `current_node_metrics_v2`.

- [ ] **Step 1: Write failing aggregation test**

```python
def test_apply_ambiguity_adds_uncertainty_without_changing_canonical_mw():
    canonical = aggregate_nodes([parsed_generation_1mw], as_of=date(2026, 8, 31)).nodes
    analysis = AmbiguityAnalysis(
        by_node={
            canonical[0].canonical_node_id: AmbiguityBucket(
                canonical_node_id=canonical[0].canonical_node_id,
                ambiguous_tu_count=1,
                capacity_min_mw=1.5,
                capacity_max_mw=2.0,
            )
        },
        unassigned=AmbiguityBucket(None, 0, 0.0, 0.0),
        node_evidence_records=[],
    )
    combined = apply_ambiguity(canonical, analysis)
    assert combined[0].generation_mw == 1.0
    assert combined[0].ambiguous_tu_count == 1
    assert combined[0].ambiguous_capacity_min_mw == 1.5
    assert combined[0].ambiguous_capacity_max_mw == 2.0
```

Also test that an ambiguity-only node creates a zero-canonical-MW `NodeAggregate` row with ambiguity fields populated.

- [ ] **Step 2: Run and verify RED**

```bash
pytest tests/test_aggregate.py -k ambiguity -v
```

Expected: FAIL because fields/helper are absent.

- [ ] **Step 3: Extend `NodeAggregate` with default-zero ambiguity fields and implement `apply_ambiguity()`**

Legacy `aggregate_nodes()` must remain unchanged except the dataclass gets new defaults, so existing `node_metrics` behavior is identical.

- [ ] **Step 4: Expose metric field list without breaking existing code**

In `database.py`:

```python
METRIC_FIELDS = (
    # exact existing `_METRIC_FIELDS` contents
)
_METRIC_FIELDS = METRIC_FIELDS
```

Update internal uses to `METRIC_FIELDS` or retain `_METRIC_FIELDS`; the alias exists so existing imports/tests cannot break.

- [ ] **Step 5: Write failing schema tests for `node_metrics_v2` and current view**

Require:

```sql
create table if not exists node_metrics_v2
run_id bigint not null references pipeline_runs(id)
canonical_node_id text not null references grid_nodes(canonical_node_id)
ambiguous_tu_count integer not null default 0
ambiguous_capacity_min_mw double precision
ambiguous_capacity_max_mw double precision
primary key (run_id, canonical_node_id)
```

and:

```sql
create or replace view current_node_metrics_v2 as
```

The view must join `pipeline_runs`, require `status = 'success'`, and choose the maximum successful `run_id` per source. It must not use merely the highest run regardless of status.

- [ ] **Step 6: Add schema and v2 metric DB upsert**

`upsert_node_metrics_v2()` should reuse `database.METRIC_FIELDS` and append exactly these uncertainty fields:

```python
V2_EXTRA_METRIC_FIELDS = (
    "ambiguous_tu_count",
    "ambiguous_capacity_min_mw",
    "ambiguous_capacity_max_mw",
)
```

Use `(run_id, canonical_node_id)` conflict target. Include `snapshot_date` as a stored trace field.

- [ ] **Step 7: Add DB test that run IDs isolate snapshots**

Assert params for identical node IDs under run 7 and run 8 contain different run IDs and the SQL conflict key is `(run_id, canonical_node_id)`.

- [ ] **Step 8: Run Task 5 and legacy aggregate/database tests**

```bash
pytest tests/test_aggregate.py tests/test_database.py tests/test_canonical_db.py tests/test_canonical_schema.py -v
```

Expected: PASS.

- [ ] **Step 9: Commit Task 5**

```bash
git add grid_tu_parser/aggregate.py grid_tu_parser/database.py grid_tu_parser/canonical_db.py schema.sql tests/test_aggregate.py tests/test_database.py tests/test_canonical_db.py tests/test_canonical_schema.py
git commit -m "feat: add canonical node metrics v2"
```

---

### Task 6: V2 Quality Data Source

**Files:**
- Modify: `grid_tu_parser/quality_db.py`
- Modify: `grid_tu_parser/quality.py`
- Modify: `tests/test_quality_analytics.py`
- Create or modify: `tests/test_quality_db.py` if the repository already has one; otherwise create it.

**Interfaces:**
- Consumes: `tu_canonical_parsed`, `tu_row_versions`.
- Produces:
  - `fetch_quality_records_v2(conn, run_id: int) -> list[dict[str, Any]]`
  - backward-compatible `render_console_report(report, *, top=10, label="QUALITY") -> str`.

- [ ] **Step 1: Write failing SQL-shape test for v2 quality fetch**

The test fake cursor should return columns matching the existing `analyze_quality()` contract. Assert SQL:

```text
from tu_canonical_parsed p
join tu_row_versions r on r.row_fingerprint = p.representative_row_fingerprint
where p.run_id = %s
```

The resulting row dict must expose `record_key` as `logical_tu_key`, plus `tu_number`, `connection_point_raw`, `activity_type`, `canonical_node_id`, `confidence`, `needs_review`, `flags`, `parse_error`, and `parent_object_type`.

- [ ] **Step 2: Run and verify RED**

```bash
pytest tests/test_quality_db.py -v
```

Expected: FAIL because `fetch_quality_records_v2` is absent.

- [ ] **Step 3: Implement v2 quality query**

Use a parameterized `run_id`. Do not query multiple runs and do not infer current run inside this function.

- [ ] **Step 4: Write failing report-label test**

```python
def test_console_report_accepts_v2_label():
    report = analyze_quality([])
    text = render_console_report(report, label="QUALITY_V2")
    assert text.splitlines()[0].startswith("QUALITY_V2 total=0")
```

- [ ] **Step 5: Implement optional label with legacy default**

Change only the first-line prefix; all existing section names and analytics remain identical.

- [ ] **Step 6: Run quality tests**

```bash
pytest tests/test_quality_analytics.py tests/test_quality_db.py -v
```

Expected: PASS and existing legacy output tests remain green.

- [ ] **Step 7: Commit Task 6**

```bash
git add grid_tu_parser/quality.py grid_tu_parser/quality_db.py tests/test_quality_analytics.py tests/test_quality_db.py
git commit -m "feat: add canonical quality analytics source"
```

---

### Task 7: Integrate B1 Shadow Flow Into the Production Pipeline

**Files:**
- Modify: `grid_tu_parser/pipeline.py`
- Modify: `tests/test_pipeline.py`
- Create: `tests/test_canonical_pipeline.py`

**Interfaces:**
- Consumes all Task 1–6 functions.
- Produces an extended `PipelineSummary` with:
  - `canonical_count: int`
  - `ambiguous_count: int`
  - `metadata_collapsed_count: int`
  - `canonical_mapped_count: int`
  - `canonical_review_count: int`
  - `canonical_node_count: int`
  - `unassigned_ambiguous_count: int`
  - `ambiguous_capacity_min_mw: float | None`
  - `ambiguous_capacity_max_mw: float | None`

- [ ] **Step 1: Write failing orchestration test that proves legacy and v2 both run**

Monkeypatch the new components and assert order-sensitive calls include:

```text
row_versions
observations
resolve_snapshot
snapshot_resolutions
canonical_parse
canonical_parsed
ambiguity
legacy raw/parsed
legacy metrics
v2 metrics
finish success
```

The test must also assert ambiguous logical TUs are not passed to canonical aggregation.

- [ ] **Step 2: Run and verify RED**

```bash
pytest tests/test_canonical_pipeline.py -v
```

Expected: FAIL because pipeline does not invoke the canonical shadow path.

- [ ] **Step 3: Integrate resolver immediately after integrity writes**

In `run_update()`:

```python
snapshot = resolve_snapshot(raw_records)
canonical_db.upsert_snapshot_resolutions(conn, run_id, snapshot.resolutions)
canonical_rows = parse_canonical_snapshot(snapshot)
canonical_db.upsert_canonical_parsed(conn, run_id, canonical_rows)
ambiguity = analyze_ambiguity(snapshot)
```

Then keep the existing legacy parse/persistence/aggregation sequence intact.

- [ ] **Step 4: Build v2 aggregation only from canonical parsed rows**

```python
canonical_parsed = [row.parsed for row in canonical_rows]
v2_aggregation = aggregate_nodes(canonical_parsed, as_of=snapshot_date)
v2_nodes = apply_ambiguity(v2_aggregation.nodes, ambiguity)
canonical_db.upsert_node_metrics_v2(conn, run_id, v2_nodes, snapshot_date)
```

Before v2 metric insert, ensure `grid_nodes` contains all v2 node IDs. During B1, the existing legacy `db.upsert_nodes(conn, parsed_records, seen_at)` already sees every source row. Add an assertion-oriented test that the legacy node upsert occurs before v2 metric persistence so the foreign key is satisfied.

- [ ] **Step 5: Compute summary counts without guessing capacity**

Rules:

```python
canonical_count = len(canonical_rows)
ambiguous_count = sum(1 for r in snapshot.resolutions if r.status == "ambiguous")
metadata_collapsed_count = snapshot.metadata_collapsed_tu_count
canonical_mapped_count = sum(1 for row in canonical_parsed if row.canonical_node_id)
canonical_review_count = sum(1 for row in canonical_parsed if row.needs_review)
canonical_node_count = len(v2_nodes)
unassigned_ambiguous_count = ambiguity.unassigned.ambiguous_tu_count
```

Global ambiguous range is the sum of TU-level known ranges only when every ambiguous TU has a non-null range; otherwise expose `None/None`. This follows the same conservative rule used for ambiguity buckets.

- [ ] **Step 6: Extend `counts` JSON with stable v2 keys**

Add:

```text
canonical
ambiguous
metadata_collapsed
canonical_mapped
canonical_review
canonical_nodes
unassigned_ambiguous
```

Keep all current legacy/integrity count keys unchanged.

- [ ] **Step 7: Verify failure semantics**

Add a test where `canonical_db.upsert_node_metrics_v2` raises `RuntimeError("v2 write failed")`. Assert:

```python
assert conn.rollbacks == 1
assert finish_call.status == "failed"
assert "v2 write failed" in finish_call.error
```

No partial v2 snapshot may be committed as successful.

- [ ] **Step 8: Run pipeline tests**

```bash
pytest tests/test_pipeline.py tests/test_canonical_pipeline.py -v
```

Expected: PASS.

- [ ] **Step 9: Commit Task 7**

```bash
git add grid_tu_parser/pipeline.py tests/test_pipeline.py tests/test_canonical_pipeline.py
git commit -m "feat: shadow canonical pipeline alongside legacy metrics"
```

---

### Task 8: Production Logging and Parallel Quality Output

**Files:**
- Modify: `scripts/update_grid_data.py`
- Create: `tests/test_canonical_cli.py`
- Modify: `tests/test_integrity_cli.py`

**Interfaces:**
- Produces:
  - `render_canonical_report(summary) -> str`
  - stable `CANONICAL ...` line
  - `QUALITY_V2 ...` block for `summary.run_id`.

- [ ] **Step 1: Write failing canonical log test**

```python
def test_render_canonical_report_has_stable_acceptance_fields():
    summary = SimpleNamespace(
        run_id=7,
        canonical_count=7400,
        ambiguous_count=300,
        metadata_collapsed_count=200,
        unassigned_ambiguous_count=20,
        ambiguous_capacity_min_mw=12.5,
        ambiguous_capacity_max_mw=18.0,
    )
    text = render_canonical_report(summary)
    assert text == (
        "CANONICAL run_id=7 canonical=7400 ambiguous=300 "
        "metadata_collapsed=200 ambiguous_min_mw=12.5 "
        "ambiguous_max_mw=18.0 unassigned_ambiguous=20"
    )
```

- [ ] **Step 2: Run and verify RED**

```bash
pytest tests/test_canonical_cli.py -v
```

Expected: FAIL because renderer is absent.

- [ ] **Step 3: Implement canonical renderer with explicit `unknown` for null ranges**

If either aggregate range is `None`, render that value as `unknown`, never `0`.

- [ ] **Step 4: Add v2 quality output after legacy quality**

After legacy `QUALITY`, open one new DB connection or reuse a safely scoped connection and run:

```python
quality_v2_rows = fetch_quality_records_v2(quality_conn, summary.run_id)
quality_v2_report = analyze_quality(quality_v2_rows, example_limit=10, pattern_limit=50)
print(render_console_report(quality_v2_report, top=20, label="QUALITY_V2"))
```

Do not select “latest” here; use the exact `summary.run_id` that produced the metrics.

- [ ] **Step 5: Add CLI test that legacy integrity/quality remain present**

Assert output still contains `INTEGRITY`, `QUALITY`, and now `CANONICAL`, `QUALITY_V2`. Existing integrity line format must remain unchanged.

- [ ] **Step 6: Run CLI tests**

```bash
pytest tests/test_integrity_cli.py tests/test_canonical_cli.py tests/test_update_cli.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit Task 8**

```bash
git add scripts/update_grid_data.py tests/test_canonical_cli.py tests/test_integrity_cli.py
git commit -m "feat: report canonical pipeline quality and uncertainty"
```

---

### Task 9: Documentation, Full Regression, and B1 Production Acceptance

**Files:**
- Modify: `README.md`
- Modify if required by exact schema assertions: `tests/test_schema.py`
- Verify: `.github/workflows/update-grid-data.yml`

**Interfaces:**
- No new runtime interface; this task establishes deployment evidence and operating instructions.

- [ ] **Step 1: Document B1 semantics in README**

Add a concise section with these exact points:

```text
Canonical Snapshot v2 is shadow-only during B1.
Legacy node_metrics remain the current consumer source.
Canonical current state is the latest successful run, not the highest attempted run.
Material conflicts are excluded from canonical MW and reported as min/max uncertainty.
After 2-3 successful production snapshots, compare legacy vs v2 before promotion.
```

Include the new production log labels `CANONICAL` and `QUALITY_V2`.

- [ ] **Step 2: Run the complete test suite**

```bash
pytest -q
```

Expected: all tests pass, zero failures.

- [ ] **Step 3: Run compile verification**

```bash
python -m compileall grid_tu_parser scripts
```

Expected: exit code 0.

- [ ] **Step 4: Inspect schema diff for destructive DDL**

```bash
git diff main...HEAD -- schema.sql
```

Expected: only additive tables/indexes/view plus no `DROP TABLE`, `DROP COLUMN`, destructive `ALTER`, or legacy rename.

- [ ] **Step 5: Commit documentation if not already committed**

```bash
git add README.md tests/test_schema.py
git commit -m "docs: document canonical shadow rollout"
```

- [ ] **Step 6: Push feature branch and open PR**

PR body must state:

```text
B1 only: legacy consumers remain unchanged.
Acceptance before merge: GitHub PR CI green.
Acceptance after merge: production run keeps observations == fetched and emits CANONICAL + QUALITY_V2.
Promotion to B2 is not part of this PR.
```

- [ ] **Step 7: Verify GitHub PR CI**

Expected GitHub Actions PR job:

```text
Run tests: success
Update grid data: skipped
```

Do not merge on local-only evidence.

- [ ] **Step 8: Merge only after explicit review, then run one manual production update**

Use `main` and `workflow_dispatch`. Verify the job succeeds and collect the exact log lines.

- [ ] **Step 9: Check production invariants from the run log**

Required:

```text
INTEGRITY fetched=<N> observations=<N>
```

with equality.

Also require:

```text
CANONICAL run_id=<R> canonical=<C> ambiguous=<A> ...
QUALITY_V2 total=<C> ...
```

and verify numerically:

```text
C + A == logical_tus from the same run's INTEGRITY line
```

`QUALITY_V2 total` must equal canonical count.

- [ ] **Step 10: Record B1 comparison for 2-3 successful snapshots before any promotion**

For each snapshot capture:

```text
run_id
legacy record count
logical TU count
canonical TU count
ambiguous TU count
legacy mapped/review rates
v2 mapped/review rates
legacy node count
v2 node count
legacy generation/load/BESS MW
v2 generation/load/BESS MW
ambiguous min/max MW
unassigned ambiguous TU count
```

Do not change dashboard/API consumers until those differences are explainable and the user explicitly approves B2.

---

## Plan Self-Review

- Spec coverage: resolver semantics, material/metadata split, deterministic representative, ambiguous min/max, latest-successful semantics, disappeared exclusion, canonical parser reuse, node uncertainty, v2 metrics, v2 quality, B1 transaction behavior, logging, and 2-3 snapshot rollout are each mapped to tasks above.
- Placeholder scan: no `TBD`, `TODO`, “implement later”, or undefined follow-up action remains.
- Type consistency: `SnapshotResolutionResult` feeds `parse_canonical_snapshot()` and `analyze_ambiguity()`; both feed pipeline Task 7. `NodeAggregate` is reused for v2 metrics with three additive ambiguity fields. `run_id` is carried through every persisted v2 snapshot table.
- Scope: B1 shadow canonicalization is one coherent pipeline change. B2 dashboard/API promotion and parser-rule tuning remain explicitly outside this implementation plan.
