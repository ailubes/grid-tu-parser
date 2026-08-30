from datetime import date, datetime, timezone

import pytest

from grid_tu_parser.aggregate import aggregate_nodes
from grid_tu_parser.models import ParsedTURecord


def record(node, activity, power_kw, tu_date, *, confidence=1.0, needs_review=False, number=None):
    return ParsedTURecord(
        source="test",
        source_url="https://example.test",
        source_page=1,
        fetched_at=datetime(2026, 8, 30, tzinfo=timezone.utc),
        tu_number=number or f"TU-{node}-{activity}-{tu_date}",
        tu_date=tu_date,
        installation_type=activity,
        activity_type=activity,
        requested_power_kw=power_kw,
        connection_type="нестандартне",
        rem="TEST REM",
        connection_point_raw=node,
        voltage_raw="10",
        canonical_node_id=node,
        confidence=confidence,
        needs_review=needs_review,
    )


def test_aggregate_groups_power_and_counts_by_canonical_node():
    records = [
        record("PS-149-TARTAKIV", "generation", 825, "2026-05-28"),
        record("PS-149-TARTAKIV", "generation", 825, "2026-05-28"),
        record("PS-149-TARTAKIV", "generation", 825, "2026-05-28"),
        record("PS-149-TARTAKIV", "consumption", 32, "2026-06-02"),
        record("PS-149-TARTAKIV", "mixed", 100, "2026-06-03"),
    ]

    result = aggregate_nodes(records, as_of=date(2026, 8, 30))
    node = result.nodes[0]

    assert node.canonical_node_id == "PS-149-TARTAKIV"
    assert node.generation_mw == pytest.approx(2.475)
    assert node.load_mw == pytest.approx(0.032)
    assert node.bess_mw == 0
    assert node.generation_tu_count == 3
    assert node.load_tu_count == 1
    assert node.other_tu_count == 1
    assert node.other_mw == pytest.approx(0.1)
    assert node.generation_load_ratio == pytest.approx(77.34375)
    assert node.net_tu_imbalance_mw == pytest.approx(2.443)


def test_aggregate_calculates_calendar_windows_and_uses_latest_tu_date_as_default_as_of():
    records = [
        record("PS-A", "generation", 1000, "2026-08-30"),
        record("PS-A", "generation", 2000, "2026-05-30"),
        record("PS-A", "generation", 4000, "2026-05-29"),
        record("PS-A", "consumption", 500, "2026-02-28"),
        record("PS-A", "bess", 300, "2025-08-30"),
        record("PS-A", "bess", 700, "2025-08-29"),
    ]

    result = aggregate_nodes(records)
    node = result.nodes[0]

    assert result.as_of == date(2026, 8, 30)
    assert node.generation_3m_mw == pytest.approx(3.0)
    assert node.generation_6m_mw == pytest.approx(7.0)
    assert node.load_6m_mw == pytest.approx(0.5)
    assert node.bess_12m_mw == pytest.approx(0.3)
    assert node.bess_mw == pytest.approx(1.0)


def test_pressure_scores_rank_nodes_by_capacity_and_recent_tu_velocity():
    records = [
        record("PS-LOW", "generation", 100, "2025-01-01"),
        record("PS-MID", "generation", 1000, "2026-07-01"),
        record("PS-HIGH", "generation", 4000, "2026-07-01"),
        record("PS-HIGH", "generation", 4000, "2026-08-01"),
    ]

    result = aggregate_nodes(records, as_of=date(2026, 8, 30))
    nodes = {node.canonical_node_id: node for node in result.nodes}

    assert nodes["PS-LOW"].generation_pressure == 0
    assert 0 < nodes["PS-MID"].generation_pressure < 100
    assert nodes["PS-HIGH"].generation_pressure == 100
    assert nodes["PS-HIGH"].generation_tu_velocity_3m_per_month == pytest.approx(2 / 3)


def test_quality_stats_keep_unmapped_records_out_of_node_aggregation():
    records = [
        record("PS-A", "consumption", 1000, "2026-08-01", confidence=0.9, needs_review=True),
        record(None, "generation", 500, "2026-08-01", confidence=0.4, needs_review=True),
    ]

    result = aggregate_nodes(records, as_of=date(2026, 8, 30))
    node = result.nodes[0]

    assert result.stats.total_records == 2
    assert result.stats.mapped_records == 1
    assert result.stats.unmapped_records == 1
    assert node.review_count == 1
    assert node.data_confidence == pytest.approx(90.0)
