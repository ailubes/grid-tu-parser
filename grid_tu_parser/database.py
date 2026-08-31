from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from datetime import date, datetime
from typing import Any, Iterable

from .aggregate import NodeAggregate
from .models import ParsedTURecord, RawTURecord


def _json_default(value: Any) -> str:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=_json_default)


def make_record_key(record: RawTURecord | ParsedTURecord) -> str:
    identity = [
        record.source or "",
        record.tu_number or "",
        record.tu_date or "",
        record.connection_point_raw or "",
        "" if record.requested_power_kw is None else format(float(record.requested_power_kw), ".12g"),
    ]
    payload = "\x1f".join(identity).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def upsert_raw_records(conn: Any, records: Iterable[RawTURecord]) -> int:
    records = list(records)
    if not records:
        return 0
    sql = """
        insert into tu_raw (
            record_key, source, source_url, source_page, fetched_at, tu_number, tu_date,
            installation_type, connection_point_raw, voltage_raw, requested_power_kw,
            connection_type, rem, raw_payload, first_seen_at, last_seen_at
        ) values (
            %s, %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s
        )
        on conflict (record_key) do update set
            source_url = excluded.source_url,
            source_page = excluded.source_page,
            fetched_at = excluded.fetched_at,
            installation_type = excluded.installation_type,
            connection_point_raw = excluded.connection_point_raw,
            voltage_raw = excluded.voltage_raw,
            requested_power_kw = excluded.requested_power_kw,
            connection_type = excluded.connection_type,
            rem = excluded.rem,
            raw_payload = excluded.raw_payload,
            last_seen_at = excluded.last_seen_at
    """
    params = []
    for record in records:
        payload = asdict(record)
        params.append((
            make_record_key(record), record.source, record.source_url, record.source_page,
            record.fetched_at, record.tu_number, record.tu_date, record.installation_type,
            record.connection_point_raw, record.voltage_raw, record.requested_power_kw,
            record.connection_type, record.rem, _json(payload), record.fetched_at, record.fetched_at,
        ))
    with conn.cursor() as cur:
        cur.executemany(sql, params)
    return len(records)


def upsert_parsed_records(conn: Any, records: Iterable[ParsedTURecord]) -> int:
    records = list(records)
    if not records:
        return 0
    sql = """
        insert into tu_parsed (
            record_key, activity_type, requested_power_kw, connection_object_type,
            connection_voltage_kv, connection_object_number, connection_object_name, feeder_id,
            parent_object_type, parent_number, parent_name, parent_voltage_levels_kv,
            canonical_node_id, confidence, needs_review, flags, parse_error, parsed_payload, parsed_at
        ) values (
            %s, %s, %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s::jsonb, %s, %s, %s, %s::jsonb, %s, %s::jsonb, now()
        )
        on conflict (record_key) do update set
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
    for record in records:
        payload = record.to_dict()
        params.append((
            make_record_key(record), record.activity_type, record.requested_power_kw,
            record.connection_object_type, record.connection_voltage_kv,
            record.connection_object_number, record.connection_object_name, record.feeder_id,
            record.parent_object_type, record.parent_number, record.parent_name,
            _json(record.parent_voltage_levels_kv), record.canonical_node_id, record.confidence,
            record.needs_review, _json(record.flags), record.parse_error, _json(payload),
        ))
    with conn.cursor() as cur:
        cur.executemany(sql, params)
    return len(records)


def upsert_nodes(conn: Any, parsed_records: Iterable[ParsedTURecord], seen_at: datetime) -> int:
    best: dict[str, ParsedTURecord] = {}
    for record in parsed_records:
        if not record.canonical_node_id:
            continue
        existing = best.get(record.canonical_node_id)
        if existing is None or record.confidence > existing.confidence:
            best[record.canonical_node_id] = record
    if not best:
        return 0
    sql = """
        insert into grid_nodes (
            canonical_node_id, parent_object_type, parent_number, parent_name,
            parent_voltage_levels_kv, first_seen_at, last_seen_at
        ) values (%s, %s, %s, %s, %s::jsonb, %s, %s)
        on conflict (canonical_node_id) do update set
            parent_object_type = coalesce(excluded.parent_object_type, grid_nodes.parent_object_type),
            parent_number = coalesce(excluded.parent_number, grid_nodes.parent_number),
            parent_name = coalesce(excluded.parent_name, grid_nodes.parent_name),
            parent_voltage_levels_kv = case
                when excluded.parent_voltage_levels_kv <> '[]'::jsonb then excluded.parent_voltage_levels_kv
                else grid_nodes.parent_voltage_levels_kv
            end,
            first_seen_at = least(grid_nodes.first_seen_at, excluded.first_seen_at),
            last_seen_at = greatest(grid_nodes.last_seen_at, excluded.last_seen_at)
    """
    params = [(
        node_id, record.parent_object_type, record.parent_number, record.parent_name,
        _json(record.parent_voltage_levels_kv), seen_at, seen_at,
    ) for node_id, record in sorted(best.items())]
    with conn.cursor() as cur:
        cur.executemany(sql, params)
    return len(params)


METRIC_FIELDS = (
    "generation_mw", "load_mw", "bess_mw", "other_mw",
    "generation_tu_count", "load_tu_count", "bess_tu_count", "other_tu_count",
    "generation_3m_mw", "generation_6m_mw", "generation_12m_mw",
    "load_3m_mw", "load_6m_mw", "load_12m_mw",
    "bess_3m_mw", "bess_6m_mw", "bess_12m_mw",
    "generation_tu_velocity_3m_per_month", "load_tu_velocity_3m_per_month", "bess_tu_velocity_3m_per_month",
    "generation_tu_velocity_12m_per_month", "load_tu_velocity_12m_per_month", "bess_tu_velocity_12m_per_month",
    "generation_load_ratio", "net_tu_imbalance_mw", "bess_share", "review_count", "data_confidence",
    "generation_pressure", "load_pressure", "bess_pressure",
)
_METRIC_FIELDS = METRIC_FIELDS


def upsert_node_metrics(conn: Any, nodes: Iterable[NodeAggregate], snapshot_date: date) -> int:
    nodes = list(nodes)
    if not nodes:
        return 0
    columns = ", ".join(("canonical_node_id", "snapshot_date", *METRIC_FIELDS))
    placeholders = ", ".join(["%s"] * (2 + len(METRIC_FIELDS)))
    updates = ", ".join(f"{field} = excluded.{field}" for field in METRIC_FIELDS)
    sql = f"""
        insert into node_metrics ({columns}) values ({placeholders})
        on conflict (canonical_node_id, snapshot_date) do update set {updates}, created_at = now()
    """
    params = [
        (node.canonical_node_id, snapshot_date, *(getattr(node, field) for field in METRIC_FIELDS))
        for node in nodes
    ]
    with conn.cursor() as cur:
        cur.executemany(sql, params)
    return len(nodes)


def start_pipeline_run(conn: Any, source: str) -> int:
    sql = """
        insert into pipeline_runs (source, status, counts)
        values (%s, 'running', '{}'::jsonb)
        returning id
    """
    with conn.cursor() as cur:
        cur.execute(sql, (source,))
        row = cur.fetchone()
    if not row:
        raise RuntimeError("Could not create pipeline run")
    return int(row[0])


def finish_pipeline_run(conn: Any, run_id: int, status: str, counts: dict[str, int], error: str | None = None) -> None:
    if status not in {"success", "failed"}:
        raise ValueError("status must be success or failed")
    sql = """
        update pipeline_runs
        set status = %s, finished_at = now(), counts = %s::jsonb, error = %s
        where id = %s
    """
    safe_error = error[:4000] if error else None
    with conn.cursor() as cur:
        cur.execute(sql, (status, _json(counts), safe_error, run_id))


def apply_schema(conn: Any, sql: str) -> None:
    with conn.cursor() as cur:
        cur.execute(sql)
