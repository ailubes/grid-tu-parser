from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from .database import make_record_key
from .identity import make_logical_tu_key, make_row_fingerprint
from .models import RawTURecord

_SOURCE_FIELDS = (
    "tu_number", "tu_date", "contract_number", "contract_date", "installation_type",
    "commissioning_stages", "connection_point_raw", "voltage_raw", "requested_power_kw",
    "connection_type", "rem", "payment_date",
)


def _differing_fields(records: list[RawTURecord]) -> list[str]:
    result: list[str] = []
    for field in _SOURCE_FIELDS:
        if len({getattr(record, field) for record in records}) > 1:
            result.append(field)
    return result


def build_integrity_audit(records: list[RawTURecord]) -> dict[str, Any]:
    legacy_groups: dict[str, list[RawTURecord]] = defaultdict(list)
    fingerprints = [make_row_fingerprint(record) for record in records]
    logical_keys = [make_logical_tu_key(record) for record in records]
    for record in records:
        legacy_groups[make_record_key(record)].append(record)

    fingerprint_counts = Counter(fingerprints)
    logical_versions: dict[str, set[str]] = defaultdict(set)
    for record in records:
        logical_versions[make_logical_tu_key(record)].add(make_row_fingerprint(record))

    collision_groups = []
    for legacy_key, group in legacy_groups.items():
        if len(group) <= 1:
            continue
        distinct_versions = {make_row_fingerprint(record) for record in group}
        collision_groups.append({
            "legacy_record_key": legacy_key,
            "observation_count": len(group),
            "distinct_row_versions": len(distinct_versions),
            "tu_numbers": sorted({record.tu_number for record in group if record.tu_number}),
            "differing_fields": _differing_fields(group),
        })
    collision_groups.sort(
        key=lambda item: (-item["observation_count"], -item["distinct_row_versions"], item["legacy_record_key"])
    )

    legacy_unique = len(legacy_groups)
    return {
        "fetched_rows": len(records),
        "legacy_unique_records": legacy_unique,
        "legacy_collision_loss": len(records) - legacy_unique,
        "unique_row_versions": len(set(fingerprints)),
        "unique_logical_tus": len(set(logical_keys)),
        "duplicate_observations": sum(count - 1 for count in fingerprint_counts.values() if count > 1),
        "logical_tus_with_multiple_versions": sum(1 for versions in logical_versions.values() if len(versions) > 1),
        "top_legacy_collision_groups": collision_groups[:20],
    }
