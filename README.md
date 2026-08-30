# Grid TU Parser

MVP deterministic parser for public Ukrainian DSO technical-condition registries, starting with the Lvivoblenergo registry.

## What it does

- collects registry HTML pages;
- preserves every source row as an immutable raw record;
- normalizes activity into `generation`, `consumption`, `bess`, `mixed`, or `unknown`;
- separates parent network node from connection-side objects;
- builds stable canonical node IDs such as `PS-144-STRADCH`;
- flags ambiguous/unrecognized rows instead of silently guessing;
- writes raw JSON, normalized JSON, and normalized CSV;
- aggregates parsed TUs by `canonical_node_id` into Generation / Load / BESS pressure indicators.

## Install

```bash
python -m pip install -e ".[dev]"
```

## Smoke collection

```bash
python scripts/collect_lviv.py --start-page 1 --end-page 2 --output-dir sample_output
```

Outputs:

- `sample_output/raw.json`
- `sample_output/parsed.json`
- `sample_output/parsed.csv`

## Aggregate by grid node

After collecting and parsing the registry, aggregate technical conditions by canonical network node:

```bash
python scripts/aggregate_nodes.py \
  --input sample_output/parsed.json \
  --output sample_output/nodes.csv \
  --as-of 2026-08-30
```

`--as-of` is optional. When omitted, the latest valid TU date in the input is used.

Each node includes total and 3/6/12-month Generation, Load and BESS MW, TU counts, recent TU velocity, generation/load ratio, net TU imbalance, BESS share, review count and average parser confidence.

### Pressure scores

`generation_pressure`, `load_pressure`, and `bess_pressure` are **relative analytical indicators from 0 to 100**, not physical grid loading or available-capacity estimates.

For each activity type, the score is:

```text
pressure = 70% × percentile(total requested MW)
         + 30% × percentile(TUs issued in last 3 months / 3)
```

The percentile comparison is calculated across all mapped nodes in the same input dataset. A score of 90 therefore means that the node ranks near the top of the observed TU dataset for that type of connection pressure. It does **not** mean that the grid is 90% loaded.

Records without a `canonical_node_id` are excluded from node totals and reported separately as unmapped. `mixed` and `unknown` activity types are retained as `other` rather than being forced into generation or load.

## PostgreSQL / Supabase daily pipeline

The production pipeline stores current TU data plus daily node snapshots in PostgreSQL. It creates or updates these tables from the idempotent `schema.sql` file:

- `tu_raw`
- `tu_parsed`
- `grid_nodes`
- `node_metrics`
- `pipeline_runs`

Run locally with a PostgreSQL connection string in the environment:

```bash
export DATABASE_URL='postgresql://...'
python scripts/update_grid_data.py
```

The command applies `schema.sql`, collects the Lvivoblenergo registry, parses and upserts TU rows, recalculates node metrics, writes the daily snapshot, and records the pipeline run status.

### GitHub Actions deployment

The workflow `.github/workflows/update-grid-data.yml` runs every day at `00:00 UTC` and can also be started manually with `workflow_dispatch`.

Create a GitHub Actions repository secret named `DATABASE_URL` containing the PostgreSQL connection string. Do not commit database passwords, API keys, or connection strings to the repository.

After the secret is configured, open **Actions → Update grid data → Run workflow** once to initialize the schema and perform the first collection. Subsequent runs are scheduled automatically.

The pipeline is idempotent: TU rows use deterministic record keys, current nodes use `canonical_node_id`, and daily metrics use `(canonical_node_id, snapshot_date)`. Re-running the same day updates the same snapshot instead of creating duplicates.

## Important limitation

Technical conditions are commitments/permissions to connect and are not the same as actual physical load, generation, BESS dispatch, or available grid capacity. The normalized data is suitable for connection-pressure screening, not for claiming a real-time network reserve.
