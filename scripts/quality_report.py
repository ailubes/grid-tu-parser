#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from grid_tu_parser.quality import analyze_quality, render_console_report, write_quality_json, write_review_csv
from grid_tu_parser.quality_db import fetch_quality_records


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Quality analytics for parsed grid TU records")
    parser.add_argument("--output-dir", default="quality_output", help="Directory for JSON and CSV outputs")
    parser.add_argument("--examples", type=int, default=5, help="Representative examples per review flag")
    parser.add_argument("--patterns", type=int, default=30, help="Number of top normalized review patterns")
    parser.add_argument("--top", type=int, default=15, help="Number of items shown per console section")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("DATABASE_URL environment variable is required", file=sys.stderr)
        return 2

    try:
        import psycopg
    except ModuleNotFoundError:
        print("psycopg is required; install the project dependencies first", file=sys.stderr)
        return 2

    conn = psycopg.connect(database_url, connect_timeout=20)
    try:
        rows = fetch_quality_records(conn)
    finally:
        conn.close()

    report = analyze_quality(rows, example_limit=args.examples, pattern_limit=args.patterns)
    output_dir = Path(args.output_dir)
    json_path = output_dir / "quality_report.json"
    csv_path = output_dir / "quality_review.csv"
    write_quality_json(report, json_path)
    write_review_csv(rows, csv_path)

    print(render_console_report(report, top=args.top))
    print(f"json={json_path} csv={csv_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
