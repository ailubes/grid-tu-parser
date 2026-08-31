from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any

from . import canonical_db
from . import database as db
from . import integrity_db
from .aggregate import aggregate_nodes, apply_ambiguity
from .canonical import analyze_ambiguity, parse_canonical_snapshot
from .collector import collect_pages
from .integrity_audit import build_integrity_audit
from .parser import parse_record
from .snapshot import resolve_snapshot


@dataclass(frozen=True)
class PipelineSummary:
    run_id: int
    snapshot_date: date
    raw_count: int
    parsed_count: int
    mapped_count: int
    node_count: int
    review_count: int
    observation_count: int
    row_version_count: int
    integrity_audit: dict[str, Any]
    canonical_count: int
    ambiguous_count: int
    metadata_collapsed_count: int
    canonical_mapped_count: int
    canonical_review_count: int
    canonical_node_count: int
    unassigned_ambiguous_count: int
    ambiguous_capacity_min_mw: float | None
    ambiguous_capacity_max_mw: float | None


def _global_ambiguous_range(snapshot: Any) -> tuple[float | None, float | None]:
    ambiguous = [item for item in snapshot.resolutions if item.status == "ambiguous"]
    if not ambiguous:
        return 0.0, 0.0
    if any(
        item.ambiguous_capacity_min_kw is None or item.ambiguous_capacity_max_kw is None
        for item in ambiguous
    ):
        return None, None
    return (
        sum(item.ambiguous_capacity_min_kw for item in ambiguous) / 1000.0,
        sum(item.ambiguous_capacity_max_kw for item in ambiguous) / 1000.0,
    )


def run_update(conn: Any, base_url: str = "https://rtu.loe.lviv.ua/", *, as_of: date | None = None) -> PipelineSummary:
    source = "lvivoblenergo"
    run_id = db.start_pipeline_run(conn, source)
    conn.commit()

    counts = {
        "raw": 0,
        "parsed": 0,
        "mapped": 0,
        "nodes": 0,
        "review": 0,
        "observations": 0,
        "row_versions": 0,
        "canonical": 0,
        "ambiguous": 0,
        "metadata_collapsed": 0,
        "canonical_mapped": 0,
        "canonical_review": 0,
        "canonical_nodes": 0,
        "unassigned_ambiguous": 0,
    }
    try:
        raw_records = collect_pages(base_url)
        counts["raw"] = len(raw_records)
        integrity_audit = build_integrity_audit(raw_records)
        counts["row_versions"] = integrity_db.upsert_row_versions(conn, raw_records)
        counts["observations"] = integrity_db.insert_observations(conn, run_id, raw_records)

        snapshot = resolve_snapshot(raw_records)
        canonical_db.upsert_snapshot_resolutions(conn, run_id, snapshot.resolutions)
        canonical_rows = parse_canonical_snapshot(snapshot)
        canonical_db.upsert_canonical_parsed(conn, run_id, canonical_rows)
        ambiguity = analyze_ambiguity(snapshot)
        canonical_parsed = [row.parsed for row in canonical_rows]

        counts["canonical"] = len(canonical_rows)
        counts["ambiguous"] = sum(1 for item in snapshot.resolutions if item.status == "ambiguous")
        counts["metadata_collapsed"] = snapshot.metadata_collapsed_tu_count
        counts["canonical_mapped"] = sum(1 for record in canonical_parsed if record.canonical_node_id)
        counts["canonical_review"] = sum(1 for record in canonical_parsed if record.needs_review)
        counts["unassigned_ambiguous"] = ambiguity.unassigned.ambiguous_tu_count

        parsed_records = [parse_record(record) for record in raw_records]
        counts["parsed"] = len(parsed_records)
        counts["mapped"] = sum(1 for record in parsed_records if record.canonical_node_id)
        counts["review"] = sum(1 for record in parsed_records if record.needs_review)

        db.upsert_raw_records(conn, raw_records)
        db.upsert_parsed_records(conn, parsed_records)

        snapshot_date = as_of or datetime.now(timezone.utc).date()
        aggregation = aggregate_nodes(parsed_records, as_of=snapshot_date)
        canonical_aggregation = aggregate_nodes(canonical_parsed, as_of=snapshot_date)
        v2_nodes = apply_ambiguity(canonical_aggregation.nodes, ambiguity)

        seen_at = datetime.now(timezone.utc)
        db.upsert_nodes(conn, parsed_records, seen_at)
        db.upsert_node_metrics(conn, aggregation.nodes, snapshot_date)
        canonical_db.upsert_node_metrics_v2(conn, run_id, v2_nodes, snapshot_date)
        counts["nodes"] = len(aggregation.nodes)
        counts["canonical_nodes"] = len(v2_nodes)

        ambiguous_min_mw, ambiguous_max_mw = _global_ambiguous_range(snapshot)
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
            observation_count=counts["observations"],
            row_version_count=counts["row_versions"],
            integrity_audit=integrity_audit,
            canonical_count=counts["canonical"],
            ambiguous_count=counts["ambiguous"],
            metadata_collapsed_count=counts["metadata_collapsed"],
            canonical_mapped_count=counts["canonical_mapped"],
            canonical_review_count=counts["canonical_review"],
            canonical_node_count=counts["canonical_nodes"],
            unassigned_ambiguous_count=counts["unassigned_ambiguous"],
            ambiguous_capacity_min_mw=ambiguous_min_mw,
            ambiguous_capacity_max_mw=ambiguous_max_mw,
        )
    except Exception as exc:
        conn.rollback()
        db.finish_pipeline_run(conn, run_id, "failed", counts, error=str(exc))
        conn.commit()
        raise
