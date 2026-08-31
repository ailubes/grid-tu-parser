from __future__ import annotations

from dataclasses import dataclass

from .identity import make_row_fingerprint
from .models import ParsedTURecord, RawTURecord
from .parser import parse_record
from .snapshot import SnapshotResolutionResult, material_signature


@dataclass(frozen=True)
class CanonicalParsedRecord:
    logical_tu_key: str
    representative_row_fingerprint: str
    parsed: ParsedTURecord


@dataclass(frozen=True)
class AmbiguityBucket:
    canonical_node_id: str | None
    ambiguous_tu_count: int
    capacity_min_mw: float | None
    capacity_max_mw: float | None


@dataclass
class AmbiguityAnalysis:
    by_node: dict[str, AmbiguityBucket]
    unassigned: AmbiguityBucket
    node_evidence_records: list[ParsedTURecord]


def parse_canonical_snapshot(result: SnapshotResolutionResult) -> list[CanonicalParsedRecord]:
    resolution_by_fp = {
        item.representative_row_fingerprint: item
        for item in result.resolutions
        if item.status == "canonical" and item.representative_row_fingerprint
    }
    rows: list[CanonicalParsedRecord] = []
    for raw in result.canonical_records:
        fingerprint = make_row_fingerprint(raw)
        resolution = resolution_by_fp[fingerprint]
        rows.append(
            CanonicalParsedRecord(
                logical_tu_key=resolution.logical_tu_key,
                representative_row_fingerprint=fingerprint,
                parsed=parse_record(raw),
            )
        )
    return sorted(rows, key=lambda item: item.logical_tu_key)


def _distinct_material_variants(records: list[RawTURecord]) -> list[RawTURecord]:
    best: dict[tuple[object, ...], tuple[str, RawTURecord]] = {}
    for record in records:
        signature = material_signature(record)
        fingerprint = make_row_fingerprint(record)
        existing = best.get(signature)
        if existing is None or fingerprint < existing[0]:
            best[signature] = (fingerprint, record)
    return [item[1] for item in sorted(best.values(), key=lambda pair: pair[0])]


def _merge_ranges(
    current_min: float | None,
    current_max: float | None,
    add_min: float | None,
    add_max: float | None,
    *,
    current_count: int,
) -> tuple[float | None, float | None]:
    if add_min is None or add_max is None:
        return None, None
    if current_count == 0:
        return add_min, add_max
    if current_min is None or current_max is None:
        return None, None
    return current_min + add_min, current_max + add_max


def analyze_ambiguity(result: SnapshotResolutionResult) -> AmbiguityAnalysis:
    resolution_by_key = {item.logical_tu_key: item for item in result.resolutions}
    node_state: dict[str, tuple[int, float | None, float | None]] = {}
    unassigned_count = 0
    unassigned_min: float | None = 0.0
    unassigned_max: float | None = 0.0
    evidence: list[ParsedTURecord] = []

    for logical_tu_key, records in sorted(result.ambiguous_groups.items()):
        variants = _distinct_material_variants(records)
        parsed_variants = [parse_record(record) for record in variants]
        evidence.extend(parsed_variants)
        node_ids = {item.canonical_node_id for item in parsed_variants}
        resolution = resolution_by_key[logical_tu_key]
        cap_min = None if resolution.ambiguous_capacity_min_kw is None else resolution.ambiguous_capacity_min_kw / 1000.0
        cap_max = None if resolution.ambiguous_capacity_max_kw is None else resolution.ambiguous_capacity_max_kw / 1000.0

        if len(node_ids) == 1 and None not in node_ids:
            node_id = next(iter(node_ids))
            count, current_min, current_max = node_state.get(node_id, (0, 0.0, 0.0))
            merged_min, merged_max = _merge_ranges(
                current_min,
                current_max,
                cap_min,
                cap_max,
                current_count=count,
            )
            node_state[node_id] = (count + 1, merged_min, merged_max)
        else:
            merged_min, merged_max = _merge_ranges(
                unassigned_min,
                unassigned_max,
                cap_min,
                cap_max,
                current_count=unassigned_count,
            )
            unassigned_count += 1
            unassigned_min, unassigned_max = merged_min, merged_max

    by_node = {
        node_id: AmbiguityBucket(node_id, count, cap_min, cap_max)
        for node_id, (count, cap_min, cap_max) in sorted(node_state.items())
    }
    if unassigned_count == 0:
        unassigned_min = 0.0
        unassigned_max = 0.0
    return AmbiguityAnalysis(
        by_node=by_node,
        unassigned=AmbiguityBucket(None, unassigned_count, unassigned_min, unassigned_max),
        node_evidence_records=evidence,
    )
