from __future__ import annotations

import json
from typing import Any, Iterable

from . import database as db
from .aggregate import NodeAggregate
from .canonical import CanonicalParsedRecord
from .snapshot import SnapshotResolution

V2_EXTRA_METRIC_FIELDS = (
    "ambiguous_tu_count",
    "ambiguous_capacity_min_mw",
    "ambiguous_capacity_max_mw",
)


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)


def upsert_snapshot_resolutions(conn: Any, run_id: int, resolutions: Iterable[SnapshotResolution]) -> int:
    rows = list(resolutions)
    if not rows:
        return 0
    sql = """
        insert into tu_snapshot_resolution (
            run_id, logical_tu_key, status, representative_row_fingerprint,
            observation_count, row_version_count, material_signature_count,
            conflict_fields, ambiguous_capacity_min_kw, ambiguous_capacity_max_kw,
            resolution_reason, resolved_at
        ) values (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, now())
        on conflict (run_id, logical_tu_key) do update set
            status = excluded.status,
            representative_row_fingerprint = excluded.representative_row_fingerprint,
            observation_count = excluded.observation_count,
            row_version_count = excluded.row_version_count,
            material_signature_count = excluded.material_signature_count,
            conflict_fields = excluded.conflict_fields,
            ambiguous_capacity_min_kw = excluded.ambiguous_capacity_min_kw,
            ambiguous_capacity_max_kw = excluded.ambiguous_capacity_max_kw,
            resolution_reason = excluded.resolution_reason,
            resolved_at = now()
    """
    params = [(
        run_id,
        row.logical_tu_key,
        row.status,
        row.representative_row_fingerprint,
        row.observation_count,
        row.row_version_count,
        row.material_signature_count,
        _json(row.conflict_fields),
        row.ambiguous_capacity_min_kw,
        row.ambiguous_capacity_max_kw,
        row.resolution_reason,
    ) for row in rows]
    with conn.cursor() as cur:
        cur.executemany(sql, params)
    return len(rows)


def upsert_canonical_parsed(conn: Any, run_id: int, rows: Iterable[CanonicalParsedRecord]) -> int:
    rows = list(rows)
    if not rows:
        return 0
    sql = """
        insert into tu_canonical_parsed (
            run_id, logical_tu_key, representative_row_fingerprint,
            activity_type, requested_power_kw, connection_object_type,
            connection_voltage_kv, connection_object_number, connection_object_name,
            feeder_id, parent_object_type, parent_number, parent_name,
            parent_voltage_levels_kv, canonical_node_id, confidence, needs_review,
            flags, parse_error, parsed_payload, parsed_at
        ) values (
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s::jsonb, %s, %s, %s, %s::jsonb, %s, %s::jsonb, now()
        )
        on conflict (run_id, logical_tu_key) do update set
            representative_row_fingerprint = excluded.representative_row_fingerprint,
            activity_type = excluded.activity_type,
            requested_power_kw = excluded.requested_power_kw,
            connection_object_type = excluded.connection_object_type,
            connection_voltage_kv = excluded.connection_voltage_kv,
            connection_object_number = excluded.connection_object_number,
            connection_object_name = excluded.connection_object_name,
            feeder_id = excluded.feeder_id,
            parent_object_type = excluded.parent_object_type,
            parent_number = excluded.parent_number,
            parent_name = excluded.parent_name,
            parent_voltage_levels_kv = excluded.parent_voltage_levels_kv,
            canonical_node_id = excluded.canonical_node_id,
            confidence = excluded.confidence,
            needs_review = excluded.needs_review,
            flags = excluded.flags,
            parse_error = excluded.parse_error,
            parsed_payload = excluded.parsed_payload,
            parsed_at = now()
    """
    params = []
    for row in rows:
        parsed = row.parsed
        params.append((
            run_id,
            row.logical_tu_key,
            row.representative_row_fingerprint,
            parsed.activity_type,
            parsed.requested_power_kw,
            parsed.connection_object_type,
            parsed.connection_voltage_kv,
            parsed.connection_object_number,
            parsed.connection_object_name,
            parsed.feeder_id,
            parsed.parent_object_type,
            parsed.parent_number,
            parsed.parent_name,
            _json(parsed.parent_voltage_levels_kv),
            parsed.canonical_node_id,
            parsed.confidence,
            parsed.needs_review,
            _json(parsed.flags),
            parsed.parse_error,
            _json(parsed.to_dict()),
        ))
    with conn.cursor() as cur:
        cur.executemany(sql, params)
    return len(rows)


def upsert_node_metrics_v2(conn: Any, run_id: int, nodes: Iterable[NodeAggregate], snapshot_date: Any) -> int:
    nodes = list(nodes)
    if not nodes:
        return 0
    metric_fields = getattr(db, "METRIC_FIELDS", db._METRIC_FIELDS)
    fields = (*metric_fields, *V2_EXTRA_METRIC_FIELDS)
    columns = ", ".join(("run_id", "canonical_node_id", "snapshot_date", *fields))
    placeholders = ", ".join(["%s"] * (3 + len(fields)))
    updates = ", ".join(f"{field} = excluded.{field}" for field in (*fields, "snapshot_date"))
    sql = f"""
        insert into node_metrics_v2 ({columns}) values ({placeholders})
        on conflict (run_id, canonical_node_id) do update set {updates}, created_at = now()
    """
    params = [
        (run_id, node.canonical_node_id, snapshot_date, *(getattr(node, field) for field in fields))
        for node in nodes
    ]
    with conn.cursor() as cur:
        cur.executemany(sql, params)
    return len(nodes)
