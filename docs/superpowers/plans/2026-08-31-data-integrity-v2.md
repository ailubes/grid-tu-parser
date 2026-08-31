# Data Integrity v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make TU ingestion lossless and auditable by preserving all 12 registry columns and separating observation identity, row-version identity, and logical TU identity.

**Architecture:** Extend the raw model and collector to preserve every published column, shadow-write immutable row versions plus per-run observations, and produce an integrity audit that explains the legacy 274-row discrepancy. Legacy tables remain active during the first rollout so current aggregation and quality analytics continue to work.

**Tech Stack:** Python 3.11, requests, BeautifulSoup4, psycopg 3, PostgreSQL/Supabase, pytest, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-08-31-data-integrity-v2-design.md`

## Global Constraints

- Preserve all 12 public Lvivoblenergo registry columns.
- Never infer hidden topology, load, flows, or spare capacity.
- Every fetched row in a run must produce exactly one observation.
- Row-version identity must be derived from all 12 normalized source fields.
- Logical TU identity must be separate from observation identity and row fingerprint.
- Phase A is shadow-write only; no destructive migration of legacy tables.
- All production changes use TDD.

---

### Task 1: Extend the raw TU model to all 12 registry columns

**Files:**
- Modify: `grid_tu_parser/models.py`
- Modify: `grid_tu_parser/collector.py`
- Modify: `tests/test_collector.py`
- Modify: `tests/fixtures/lviv_registry_sample.html` only if the fixture lacks the four source columns.

**Interfaces:**
- Produces: `RawTURecord.source_row_index: int`
- Produces: `RawTURecord.contract_number: str | None`
- Produces: `RawTURecord.contract_date: str | None`
- Produces: `RawTURecord.commissioning_stages: str | None`
- Produces: `RawTURecord.payment_date: str | None`

- [ ] **Step 1: Write failing collector tests for all 12 columns**

Add a test using a row shaped like the live registry:

```python
def test_parse_registry_html_preserves_all_source_columns():
    rows = parse_registry_html(
        Path("tests/fixtures/lviv_registry_sample.html").read_text(),
        "https://rtu.loe.lviv.ua/?page=1",
        1,
        datetime(2026, 8, 31, tzinfo=timezone.utc),
    )
    row = rows[0]
    assert row.source_row_index == 1
    assert row.contract_number is not None
    assert row.contract_date is not None
    assert row.commissioning_stages is not None
    assert row.payment_date is not None
```

- [ ] **Step 2: Run the focused test and verify RED**

Run:

```bash
pytest tests/test_collector.py::test_parse_registry_html_preserves_all_source_columns -v
```

Expected: FAIL because the new `RawTURecord` fields do not exist.

- [ ] **Step 3: Extend header mappings and `RawTURecord`**

Add header keys for:

```python
"contract_number": ("№ договору", "номер договору"),
"contract_date": ("дата договору",),
"commissioning_stages": ("черги введення потужності",),
"payment_date": ("дата надходження коштів",),
```

Enumerate body rows with `start=1` and persist `source_row_index`.

- [ ] **Step 4: Run collector tests**

Run:

```bash
pytest tests/test_collector.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add grid_tu_parser/models.py grid_tu_parser/collector.py tests/test_collector.py tests/fixtures/lviv_registry_sample.html
git commit -m "feat: preserve all TU registry columns"
```

---

### Task 2: Add deterministic v2 identity functions

**Files:**
- Create: `grid_tu_parser/identity.py`
- Create: `tests/test_identity.py`

**Interfaces:**
- Produces: `make_row_fingerprint(record: RawTURecord) -> str`
- Produces: `make_logical_tu_key(record: RawTURecord) -> str`
- Produces: `make_observation_key(run_id: int, record: RawTURecord) -> str`
- Consumes: all 12 normalized source fields and `source_row_index`.

- [ ] **Step 1: Write failing identity tests**

```python
def test_row_fingerprint_changes_when_contract_date_changes():
    a = make_record(contract_date="2026-05-25")
    b = make_record(contract_date="2026-05-26")
    assert make_row_fingerprint(a) != make_row_fingerprint(b)


def test_identical_rows_share_row_fingerprint_but_not_observation_key():
    record = make_record(source_page=1, source_row_index=1)
    same_content_elsewhere = replace(record, source_page=2, source_row_index=7)
    assert make_row_fingerprint(record) == make_row_fingerprint(same_content_elsewhere)
    assert make_observation_key(10, record) != make_observation_key(10, same_content_elsewhere)


def test_logical_tu_key_is_stable_across_row_versions():
    a = make_record(tu_number="ТУ 123", contract_date="2026-05-25")
    b = replace(a, contract_date="2026-05-26")
    assert make_logical_tu_key(a) == make_logical_tu_key(b)
```

- [ ] **Step 2: Verify RED**

Run:

```bash
pytest tests/test_identity.py -v
```

Expected: FAIL because `grid_tu_parser.identity` does not exist.

- [ ] **Step 3: Implement deterministic hashes**

Use canonical JSON arrays with `ensure_ascii=False` and compact separators before SHA-256 hashing. Do not include fetch position in `row_fingerprint`.

- [ ] **Step 4: Run identity tests**

```bash
pytest tests/test_identity.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add grid_tu_parser/identity.py tests/test_identity.py
git commit -m "feat: add TU v2 identities"
```

---

### Task 3: Add shadow-write v2 schema

**Files:**
- Modify: `schema.sql`
- Create: `tests/test_data_integrity_schema.py`

**Interfaces:**
- Produces table `tu_row_versions(row_fingerprint PK, logical_tu_key, all 12 fields, raw_payload, first_seen_at, last_seen_at)`.
- Produces table `tu_observations(observation_key PK, run_id FK, row_fingerprint FK, source_page, source_row_index, fetched_at)`.
- Produces uniqueness constraint `(run_id, source_page, source_row_index)`.

- [ ] **Step 1: Write schema tests**

Assert that `schema.sql` contains both tables, FKs, all four newly preserved source fields, and the run/page/row uniqueness constraint.

- [ ] **Step 2: Verify RED**

```bash
pytest tests/test_data_integrity_schema.py -v
```

Expected: FAIL because v2 tables are absent.

- [ ] **Step 3: Add idempotent PostgreSQL DDL**

Use `create table if not exists` and `create index if not exists`. Do not drop or rename legacy tables.

- [ ] **Step 4: Verify schema tests**

```bash
pytest tests/test_data_integrity_schema.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add schema.sql tests/test_data_integrity_schema.py
git commit -m "feat: add lossless TU observation schema"
```

---

### Task 4: Implement v2 database shadow writes

**Files:**
- Create: `grid_tu_parser/integrity_db.py`
- Create: `tests/test_integrity_db.py`

**Interfaces:**
- Produces: `upsert_row_versions(conn, records: Iterable[RawTURecord]) -> int`
- Produces: `insert_observations(conn, run_id: int, records: Iterable[RawTURecord]) -> int`
- Consumes identity functions from `grid_tu_parser.identity`.

- [ ] **Step 1: Write failing SQL contract tests**

Use fake cursor/connection objects to verify:
- row versions use `ON CONFLICT (row_fingerprint) DO UPDATE` only for `last_seen_at` and published content fields;
- observations use deterministic `observation_key`;
- each input row creates one observation parameter tuple;
- run ID, page, and row index are included.

- [ ] **Step 2: Verify RED**

```bash
pytest tests/test_integrity_db.py -v
```

Expected: FAIL because the module does not exist.

- [ ] **Step 3: Implement the two write functions**

Use `executemany()` and parameterized SQL only. Preserve `raw_payload` as the full `asdict(record)` JSON.

- [ ] **Step 4: Verify focused tests**

```bash
pytest tests/test_integrity_db.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add grid_tu_parser/integrity_db.py tests/test_integrity_db.py
git commit -m "feat: shadow-write TU row versions and observations"
```

---

### Task 5: Wire v2 writes into the existing pipeline without breaking legacy output

**Files:**
- Modify: `grid_tu_parser/pipeline.py`
- Modify: `tests/test_pipeline.py`

**Interfaces:**
- Consumes: `integrity_db.upsert_row_versions()` and `integrity_db.insert_observations()`.
- Extends `PipelineSummary` with `observation_count`, `row_version_count`.

- [ ] **Step 1: Add failing pipeline test**

Create a collector fixture containing duplicate-content rows at different row positions and assert:

```python
assert summary.raw_count == 3
assert summary.observation_count == 3
assert summary.row_version_count == 2
```

Also assert existing legacy upserts and aggregation are still called.

- [ ] **Step 2: Verify RED**

```bash
pytest tests/test_pipeline.py -v
```

Expected: FAIL because summary fields and v2 writes are absent.

- [ ] **Step 3: Implement shadow-write calls**

Perform v2 writes in the same transaction as current legacy writes. A v2 write failure must roll back the run rather than silently continue.

- [ ] **Step 4: Verify pipeline tests**

```bash
pytest tests/test_pipeline.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add grid_tu_parser/pipeline.py tests/test_pipeline.py
git commit -m "feat: shadow-write lossless TU observations"
```

---

### Task 6: Build the legacy collision audit

**Files:**
- Create: `grid_tu_parser/integrity_audit.py`
- Create: `tests/test_integrity_audit.py`

**Interfaces:**
- Produces: `build_integrity_audit(records: list[RawTURecord]) -> dict[str, Any]`
- Report keys:
  - `fetched_rows`
  - `legacy_unique_records`
  - `legacy_collision_loss`
  - `unique_row_versions`
  - `unique_logical_tus`
  - `duplicate_observations`
  - `logical_tus_with_multiple_versions`
  - `top_legacy_collision_groups`

- [ ] **Step 1: Write failing audit tests**

Construct four rows where:
- two are exact source duplicates;
- two collide under the legacy `make_record_key()` but differ in a newly preserved field.

Assert the audit distinguishes true duplicate observations from legacy-key collisions.

- [ ] **Step 2: Verify RED**

```bash
pytest tests/test_integrity_audit.py -v
```

Expected: FAIL because the module does not exist.

- [ ] **Step 3: Implement pure in-memory audit**

Reuse legacy `database.make_record_key()` only for comparison; use v2 identity functions for new counts.

For each top collision group return:

```python
{
    "legacy_record_key": "...",
    "observation_count": 3,
    "distinct_row_versions": 2,
    "tu_numbers": ["TU ..."],
    "differing_fields": ["contract_date"],
}
```

- [ ] **Step 4: Verify audit tests**

```bash
pytest tests/test_integrity_audit.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add grid_tu_parser/integrity_audit.py tests/test_integrity_audit.py
git commit -m "feat: explain legacy TU record collisions"
```

---

### Task 7: Surface integrity metrics in production logs

**Files:**
- Modify: `scripts/update_grid_data.py`
- Modify: `tests/test_update_cli.py`

**Interfaces:**
- Consumes `build_integrity_audit(raw_records)` or an equivalent audit returned by pipeline.
- Produces stable log lines beginning with `INTEGRITY`.

- [ ] **Step 1: Add failing CLI output test**

Expected output shape:

```text
INTEGRITY fetched=8285 observations=8285 row_versions=... logical_tus=... legacy_unique=8011 legacy_loss=274
```

and collision summaries:

```text
LEGACY COLLISIONS
  ... observations=... versions=... differs=contract_date
```

- [ ] **Step 2: Verify RED**

```bash
pytest tests/test_update_cli.py -v
```

Expected: FAIL because integrity output is absent.

- [ ] **Step 3: Add compact production reporting**

Do not print customer names or any data beyond the already public registry fields needed to identify patterns. Limit collision groups to 20 in CI logs.

- [ ] **Step 4: Verify CLI tests**

```bash
pytest tests/test_update_cli.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/update_grid_data.py tests/test_update_cli.py
git commit -m "feat: report TU ingestion integrity"
```

---

### Task 8: Full regression and production validation

**Files:**
- Modify: `README.md` if command/output documentation needs updating.

**Interfaces:**
- No new interfaces; verifies all prior tasks together.

- [ ] **Step 1: Run the complete test suite**

```bash
pytest -q
```

Expected: all tests pass with zero failures.

- [ ] **Step 2: Compile all Python modules**

```bash
python -m compileall grid_tu_parser scripts
```

Expected: exit code 0.

- [ ] **Step 3: Review the branch diff**

```bash
git diff main...HEAD --stat
git diff main...HEAD
```

Confirm no destructive DDL and no unrelated parser-rule changes.

- [ ] **Step 4: Open PR and let normal CI run**

PR description must explicitly state that v2 is shadow-write and does not replace legacy tables yet.

- [ ] **Step 5: After merge, run `Update grid data` manually**

Production acceptance requires:

```text
INTEGRITY fetched=8285 observations=8285 ...
```

and `legacy_loss` must numerically explain the current discrepancy.

- [ ] **Step 6: Inspect Supabase counts**

Verify for the successful run:

```sql
select count(*) from tu_observations where run_id = <run_id>;
select count(*) from tu_row_versions;
```

The first query must equal the pipeline `raw` count.

- [ ] **Step 7: Only after validation, plan Phase B parser-quality work**

Do not change `conflicting_voltage_context` semantics in this PR.
