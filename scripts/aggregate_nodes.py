#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import fields
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from grid_tu_parser.aggregate import aggregate_nodes
from grid_tu_parser.export import write_csv, write_json
from grid_tu_parser.models import ParsedTURecord


def _load_records(path: Path) -> list[ParsedTURecord]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("Input JSON must contain a list of parsed TU records")
    allowed = {item.name for item in fields(ParsedTURecord)}
    records: list[ParsedTURecord] = []
    for item in payload:
        if not isinstance(item, dict):
            raise ValueError("Each parsed TU record must be a JSON object")
        values = {key: value for key, value in item.items() if key in allowed}
        fetched_at = values.get("fetched_at")
        if isinstance(fetched_at, str):
            values["fetched_at"] = datetime.fromisoformat(fetched_at.replace("Z", "+00:00"))
        records.append(ParsedTURecord(**values))
    return records


def main() -> int:
    parser = argparse.ArgumentParser(description="Aggregate parsed technical conditions by canonical grid node")
    parser.add_argument("--input", required=True, type=Path, help="parsed.json produced by the TU parser")
    parser.add_argument("--output", required=True, type=Path, help="Output .csv or .json node table")
    parser.add_argument("--as-of", type=date.fromisoformat, help="Analysis date in YYYY-MM-DD format; defaults to latest valid TU date")
    args = parser.parse_args()

    records = _load_records(args.input)
    result = aggregate_nodes(records, as_of=args.as_of)
    if args.output.suffix.lower() == ".json":
        write_json(result.nodes, args.output)
    else:
        write_csv(result.nodes, args.output)

    print(
        f"Aggregated {result.stats.mapped_records}/{result.stats.total_records} mapped records "
        f"into {len(result.nodes)} nodes as of {result.as_of.isoformat()}"
    )
    if result.stats.unmapped_records:
        print(f"Unmapped records: {result.stats.unmapped_records}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
