from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any, Iterable

from .identity import make_logical_tu_key, make_observation_key, make_row_fingerprint
from .models import RawTURecord


def _json(record: RawTURecord) -> str:
    return json.dumps(asdict(record), ensure_ascii=False, separators=(",", ":"), default=str)


def upsert_row_versions(conn: Any, records: Iterable[RawTURecord]) -> int:
    unique: dict[str, RawTURecord] = {}
    for record in records:
        unique.setdefault(make_row_fingerprint(record), record)
    if not unique:
        return 0
    sql = """
        insert into tu_row_versions (
            row_fingerprint, logical_tu_key, source, tu_number, tu_date,
            contract_number, contract_date, installation_type, commissioning_stages,
            connection_point_raw, voltage_raw, requested_power_kw, connection_type,
            rem, payment_date, raw_payload, first_seen_at, last_seen_at
        ) values (
            %s, %s, %s, %s, %s,
            %s, %s, %s, %s,
            %s, %s, %s, %s,
            %s, %s, %s::jsonb, %s, %s
        )
        on conflict (row_fingerprint) do update set
            logical_tu_key = excluded.logical_tu_key,
            source = excluded.source,
            tu_number = excluded.tu_number,
            tu_date = excluded.tu_date,
            contract_number = excluded.contract_number,
            contract_date = excluded.contract_date,
            installation_type = excluded.installation_type,
            commissioning_stages = excluded.commissioning_stages,
            connection_point_raw = excluded.connection_point_raw,
            voltage_raw = excluded.voltage_raw,
            requested_power_kw = excluded.requested_power_kw,
            connection_type = excluded.connection_type,
            rem = excluded.rem,
            payment_date = excluded.payment_date,
            raw_payload = excluded.raw_payload,
            last_seen_at = greatest(tu_row_versions.last_seen_at, excluded.last_seen_at)
    """
    params = []
    for fingerprint, record in unique.items():
        params.append((
            fingerprint, make_logical_tu_key(record), record.source,
            record.tu_number, record.tu_date, record.contract_number, record.contract_date,
            record.installation_type, record.commissioning_stages, record.connection_point_raw,
            record.voltage_raw, record.requested_power_kw, record.connection_type, record.rem,
            record.payment_date, _json(record), record.fetched_at, record.fetched_at,
        ))
    with conn.cursor() as cur:
        cur.executemany(sql, params)
    return len(params)


def insert_observations(conn: Any, run_id: int, records: Iterable[RawTURecord]) -> int:
    records = list(records)
    if not records:
        return 0
    sql = """
        insert into tu_observations (
            observation_key, run_id, row_fingerprint, source_page, source_row_index, fetched_at
        ) values (%s, %s, %s, %s, %s, %s)
        on conflict (observation_key) do nothing
    """
    params = [(
        make_observation_key(run_id, record), run_id, make_row_fingerprint(record),
        record.source_page, record.source_row_index, record.fetched_at,
    ) for record in records]
    with conn.cursor() as cur:
        cur.executemany(sql, params)
    return len(records)
