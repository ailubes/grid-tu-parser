from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .identity import make_logical_tu_key, make_row_fingerprint
from .models import RawTURecord

MATERIAL_FIELDS = (
    "tu_date",
    "installation_type",
    "connection_point_raw",
    "voltage_raw",
    "requested_power_kw",
    "connection_type",
)


@dataclass(frozen=True)
class SnapshotResolution:
    logical_tu_key: str
    status: str
    representative_row_fingerprint: str | None
    observation_count: int
    row_version_count: int
    material_signature_count: int
    conflict_fields: tuple[str, ...]
    ambiguous_capacity_min_kw: float | None
    ambiguous_capacity_max_kw: float | None
    resolution_reason: str


@dataclass
class SnapshotResolutionResult:
    resolutions: list[SnapshotResolution]
    canonical_records: list[RawTURecord]
    ambiguous_groups: dict[str, list[RawTURecord]]
    metadata_collapsed_tu_count: int


def material_signature(record: RawTURecord) -> tuple[object, ...]:
    return tuple(getattr(record, field) for field in MATERIAL_FIELDS)


def _varying_fields(signatures: set[tuple[object, ...]]) -> tuple[str, ...]:
    return tuple(
        field
        for index, field in enumerate(MATERIAL_FIELDS)
        if len({signature[index] for signature in signatures}) > 1
    )


def resolve_snapshot(records: Iterable[RawTURecord]) -> SnapshotResolutionResult:
    observations = list(records)
    grouped: dict[str, list[RawTURecord]] = {}
    for record in observations:
        grouped.setdefault(make_logical_tu_key(record), []).append(record)

    resolutions: list[SnapshotResolution] = []
    canonical_records: list[RawTURecord] = []
    ambiguous_groups: dict[str, list[RawTURecord]] = {}
    metadata_collapsed_tu_count = 0

    for logical_tu_key in sorted(grouped):
        group = grouped[logical_tu_key]
        versions_by_fingerprint: dict[str, RawTURecord] = {}
        for record in group:
            fingerprint = make_row_fingerprint(record)
            versions_by_fingerprint.setdefault(fingerprint, record)
        fingerprints = sorted(versions_by_fingerprint)
        versions = [versions_by_fingerprint[fingerprint] for fingerprint in fingerprints]
        signatures = {material_signature(record) for record in versions}

        if len(signatures) == 1:
            representative_fingerprint = fingerprints[0]
            representative = versions_by_fingerprint[representative_fingerprint]
            if len(versions) > 1:
                metadata_collapsed_tu_count += 1
            resolutions.append(
                SnapshotResolution(
                    logical_tu_key=logical_tu_key,
                    status="canonical",
                    representative_row_fingerprint=representative_fingerprint,
                    observation_count=len(group),
                    row_version_count=len(versions),
                    material_signature_count=1,
                    conflict_fields=(),
                    ambiguous_capacity_min_kw=None,
                    ambiguous_capacity_max_kw=None,
                    resolution_reason="single_material_signature",
                )
            )
            canonical_records.append(representative)
            continue

        conflict_fields = _varying_fields(signatures)
        powers = [
            signature[MATERIAL_FIELDS.index("requested_power_kw")]
            for signature in signatures
            if signature[MATERIAL_FIELDS.index("requested_power_kw")] is not None
        ]
        ambiguous_min = min(float(power) for power in powers) if powers else None
        ambiguous_max = max(float(power) for power in powers) if powers else None
        resolutions.append(
            SnapshotResolution(
                logical_tu_key=logical_tu_key,
                status="ambiguous",
                representative_row_fingerprint=None,
                observation_count=len(group),
                row_version_count=len(versions),
                material_signature_count=len(signatures),
                conflict_fields=conflict_fields,
                ambiguous_capacity_min_kw=ambiguous_min,
                ambiguous_capacity_max_kw=ambiguous_max,
                resolution_reason="multiple_material_signatures",
            )
        )
        ambiguous_groups[logical_tu_key] = versions

    return SnapshotResolutionResult(
        resolutions=resolutions,
        canonical_records=canonical_records,
        ambiguous_groups=ambiguous_groups,
        metadata_collapsed_tu_count=metadata_collapsed_tu_count,
    )
