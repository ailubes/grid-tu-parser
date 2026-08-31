from dataclasses import replace
from datetime import datetime, timezone

from grid_tu_parser.models import RawTURecord
from grid_tu_parser.snapshot import resolve_snapshot


def rec(row: int, **changes) -> RawTURecord:
    base = RawTURecord(
        source="lvivoblenergo",
        source_url="https://example.test",
        source_page=1,
        source_row_index=row,
        fetched_at=datetime(2026, 8, 31, tzinfo=timezone.utc),
        tu_number="ТУ 123",
        tu_date="2026-08-30",
        installation_type="генерація",
        connection_point_raw="РУ-10 кВ ПС 35/10 кВ №201 Чишки",
        voltage_raw="10",
        requested_power_kw=1000.0,
        connection_type="нестандартне",
        rem="ЛМЕМ",
        contract_number="D-1",
        contract_date="2026-08-20",
        commissioning_stages="2026",
        payment_date="2026-08-21",
    )
    return replace(base, **changes)


def test_metadata_only_versions_collapse_to_one_canonical_tu():
    result = resolve_snapshot([
        rec(1),
        rec(2, payment_date="2026-08-22", rem="ІНШИЙ РЕМ"),
    ])
    resolution = result.resolutions[0]
    assert resolution.status == "canonical"
    assert resolution.observation_count == 2
    assert resolution.row_version_count == 2
    assert resolution.material_signature_count == 1
    assert resolution.conflict_fields == ()
    assert result.metadata_collapsed_tu_count == 1
    assert len(result.canonical_records) == 1


def test_power_conflict_is_ambiguous_and_excluded_from_canonical_records():
    result = resolve_snapshot([
        rec(1, requested_power_kw=1000.0),
        rec(2, requested_power_kw=1500.0),
    ])
    resolution = result.resolutions[0]
    assert resolution.status == "ambiguous"
    assert resolution.conflict_fields == ("requested_power_kw",)
    assert resolution.ambiguous_capacity_min_kw == 1000.0
    assert resolution.ambiguous_capacity_max_kw == 1500.0
    assert result.canonical_records == []
    assert len(result.ambiguous_groups[resolution.logical_tu_key]) == 2


def test_representative_fingerprint_is_deterministic_for_metadata_variants():
    first = resolve_snapshot([rec(1), rec(2, payment_date="2026-08-22")])
    second = resolve_snapshot([rec(2, payment_date="2026-08-22"), rec(1)])
    assert first.resolutions[0].representative_row_fingerprint == second.resolutions[0].representative_row_fingerprint
    assert first.resolutions[0].representative_row_fingerprint is not None


def test_exact_duplicate_observations_do_not_create_extra_row_versions():
    a = rec(1)
    duplicate = replace(a, source_page=2, source_row_index=8)
    result = resolve_snapshot([a, duplicate])
    resolution = result.resolutions[0]
    assert resolution.observation_count == 2
    assert resolution.row_version_count == 1
    assert resolution.material_signature_count == 1
    assert resolution.status == "canonical"


def test_ambiguous_group_with_no_published_power_keeps_range_null():
    result = resolve_snapshot([
        rec(1, requested_power_kw=None, voltage_raw="10"),
        rec(2, requested_power_kw=None, voltage_raw="6"),
    ])
    resolution = result.resolutions[0]
    assert resolution.status == "ambiguous"
    assert resolution.ambiguous_capacity_min_kw is None
    assert resolution.ambiguous_capacity_max_kw is None
