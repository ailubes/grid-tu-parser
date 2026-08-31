from dataclasses import replace
from datetime import datetime, timezone

from grid_tu_parser.canonical import analyze_ambiguity, parse_canonical_snapshot
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


def test_canonical_parser_runs_once_per_logical_tu():
    resolved = resolve_snapshot([rec(1), rec(2, payment_date="2026-08-22")])
    parsed = parse_canonical_snapshot(resolved)
    assert len(parsed) == 1
    assert parsed[0].logical_tu_key == resolved.resolutions[0].logical_tu_key
    assert parsed[0].representative_row_fingerprint == resolved.resolutions[0].representative_row_fingerprint
    assert parsed[0].parsed.requested_power_kw == 1000.0


def test_ambiguous_variants_are_attributed_only_when_all_map_to_same_node():
    resolved = resolve_snapshot([
        rec(1, requested_power_kw=1000.0),
        rec(2, requested_power_kw=1500.0),
    ])
    analysis = analyze_ambiguity(resolved)
    bucket = next(iter(analysis.by_node.values()))
    assert bucket.ambiguous_tu_count == 1
    assert bucket.capacity_min_mw == 1.0
    assert bucket.capacity_max_mw == 1.5
    assert analysis.unassigned.ambiguous_tu_count == 0


def test_conflicting_nodes_go_to_unassigned_bucket():
    resolved = resolve_snapshot([
        rec(1, connection_point_raw="РУ-10 кВ ПС 35/10 кВ №201 Чишки"),
        rec(2, connection_point_raw="РУ-10 кВ ПС 35/10 кВ №144 Страдч"),
    ])
    analysis = analyze_ambiguity(resolved)
    assert analysis.by_node == {}
    assert analysis.unassigned.ambiguous_tu_count == 1


def test_unknown_ambiguous_capacity_makes_bucket_range_unknown():
    resolved = resolve_snapshot([
        rec(1, requested_power_kw=None, voltage_raw="10"),
        rec(2, requested_power_kw=None, voltage_raw="6"),
    ])
    analysis = analyze_ambiguity(resolved)
    bucket = next(iter(analysis.by_node.values()))
    assert bucket.capacity_min_mw is None
    assert bucket.capacity_max_mw is None
