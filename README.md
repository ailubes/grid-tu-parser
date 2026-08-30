# Grid TU Parser

MVP deterministic parser for public Ukrainian DSO technical-condition registries, starting with the Lvivoblenergo registry.

## What it does

- collects registry HTML pages;
- preserves every source row as an immutable raw record;
- normalizes activity into `generation`, `consumption`, `bess`, `mixed`, or `unknown`;
- separates parent network node from connection-side objects;
- builds stable canonical node IDs such as `PS-144-STRADCH`;
- flags ambiguous/unrecognized rows instead of silently guessing;
- writes raw JSON, normalized JSON, and normalized CSV.

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

## Important limitation

Technical conditions are commitments/permissions to connect and are not the same as actual physical load, generation, BESS dispatch, or available grid capacity. The normalized data is suitable for connection-pressure screening, not for claiming a real-time network reserve.
