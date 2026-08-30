from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any

from . import database as db
from .aggregate import aggregate_nodes
from .collector import collect_pages
from .parser import parse_record


@dataclass(frozen=True)
class PipelineSummary:
    run_id: int
    snapshot_date: date
    raw_count: int
    parsed_count: int
    mapped_count: int
    node_count: int
    review_count: int


def run_update(conn: Any, base_url: str = "https://rtu.loe.lviv.ua/", *, as_of: date | None = None) -> PipelineSummary:
    source = "lvivoblenergo"
    run_id = db.start_pipeline_run(conn, source)
    conn.commit()

    counts = {"raw": 0, "parsed": 0, "mapped": 0, "nodes": 0, "review": 0}
    try:
        raw_records = collect_pages(base_url)
        counts["raw"] = len(raw_records)
        parsed_records = [parse_record(record) for record in raw_records]
        counts["parsed"] = len(parsed_records)
        counts["mapped"] = sum(1 for record in parsed_records if record.canonical_node_id)
        counts["review"] = sum(1 for record in parsed_records if record.needs_review)

        db.upsert_raw_records(conn, raw_records)
        db.upsert_parsed_records(conn, parsed_records)

        snapshot_date = as_of or datetime.now(timezone.utc).date()
        aggregation = aggregate_nodes(parsed_records, as_of=snapshot_date)
        seen_at = datetime.now(timezone.utc)
        db.upsert_nodes(conn, parsed_records, seen_at)
        db.upsert_node_metrics(conn, aggregation.nodes, snapshot_date)
        counts["nodes"] = len(aggregation.nodes)

        db.finish_pipeline_run(conn, run_id, "success", counts)
        conn.commit()
        return PipelineSummary(
            run_id=run_id,
            snapshot_date=snapshot_date,
            raw_count=counts["raw"],
            parsed_count=counts["parsed"],
            mapped_count=counts["mapped"],
            node_count=counts["nodes"],
            review_count=counts["review"],
        )
    except Exception as exc:
        conn.rollback()
        db.finish_pipeline_run(conn, run_id, "failed", counts, error=str(exc))
        conn.commit()
        raise
