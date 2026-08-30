#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from grid_tu_parser import database as db
from grid_tu_parser.pipeline import run_update
from grid_tu_parser.quality import analyze_quality, render_console_report
from grid_tu_parser.quality_db import fetch_quality_records


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Daily grid TU pipeline for public DSO registry data")
    parser.add_argument("--base-url", default="https://rtu.loe.lviv.ua/", help="Registry base URL")
    parser.add_argument("--as-of", type=date.fromisoformat, help="Snapshot date in YYYY-MM-DD; defaults to current UTC date")
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

    schema_sql = (ROOT / "schema.sql").read_text(encoding="utf-8")
    conn = psycopg.connect(database_url, connect_timeout=20)
    try:
        db.apply_schema(conn, schema_sql)
        conn.commit()
        summary = run_update(conn, args.base_url, as_of=args.as_of)
    finally:
        conn.close()

    print(
        f"run_id={summary.run_id} snapshot={summary.snapshot_date.isoformat()} "
        f"raw={summary.raw_count} parsed={summary.parsed_count} mapped={summary.mapped_count} "
        f"nodes={summary.node_count} review={summary.review_count}"
    )

    quality_conn = psycopg.connect(database_url, connect_timeout=20)
    try:
        quality_rows = fetch_quality_records(quality_conn)
    finally:
        quality_conn.close()
    quality_report = analyze_quality(quality_rows, example_limit=10, pattern_limit=50)
    print(render_console_report(quality_report, top=20))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
