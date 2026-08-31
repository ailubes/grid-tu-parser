from __future__ import annotations

import hashlib
import json

from .models import RawTURecord

_SOURCE_FIELDS = (
    "tu_number",
    "tu_date",
    "contract_number",
    "contract_date",
    "installation_type",
    "commissioning_stages",
    "connection_point_raw",
    "voltage_raw",
    "requested_power_kw",
    "connection_type",
    "rem",
    "payment_date",
)


def _hash_parts(parts: list[object]) -> str:
    payload = json.dumps(parts, ensure_ascii=False, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def make_row_fingerprint(record: RawTURecord) -> str:
    return _hash_parts([record.source, *(getattr(record, field) for field in _SOURCE_FIELDS)])


def make_logical_tu_key(record: RawTURecord) -> str:
    if record.tu_number:
        return _hash_parts([record.source, record.tu_number])
    return _hash_parts([
        record.source,
        record.tu_date,
        record.contract_number,
        record.connection_point_raw,
        record.requested_power_kw,
    ])


def make_observation_key(run_id: int, record: RawTURecord) -> str:
    return _hash_parts([record.source, run_id, record.source_page, record.source_row_index])
