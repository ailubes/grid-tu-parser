from __future__ import annotations

import argparse
from pathlib import Path

from grid_tu_parser.collector import CollectorError, collect_pages
from grid_tu_parser.export import write_csv, write_json
from grid_tu_parser.parser import parse_record


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Collect and parse Lvivoblenergo TU registry pages")
    parser.add_argument("--base-url", default="https://rtu.loe.lviv.ua/", help="Registry base URL")
    parser.add_argument("--start-page", type=int, default=1)
    parser.add_argument("--end-page", type=int)
    parser.add_argument("--output-dir", default="sample_output")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    output_dir = Path(args.output_dir)
    try:
        raw = collect_pages(args.base_url, args.start_page, args.end_page)
    except CollectorError as exc:
        raw = exc.partial_records
        print(f"collector stopped on page {exc.failed_page}: {exc}")

    parsed = [parse_record(record) for record in raw]
    write_json(raw, output_dir / "raw.json")
    write_json(parsed, output_dir / "parsed.json")
    write_csv(parsed, output_dir / "parsed.csv")

    reviewed = sum(1 for record in parsed if record.needs_review)
    with_node = sum(1 for record in parsed if record.canonical_node_id)
    print(f"raw={len(raw)} parsed={len(parsed)} canonical_nodes={with_node} needs_review={reviewed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
