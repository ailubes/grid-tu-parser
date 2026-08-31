from datetime import date, datetime, timezone

from grid_tu_parser.aggregate import NodeAggregate
from grid_tu_parser.canonical import CanonicalParsedRecord
from grid_tu_parser.canonical_db import (
    upsert_canonical_parsed,
    upsert_node_metrics_v2,
    upsert_snapshot_resolutions,
)
from grid_tu_parser.models import RawTURecord
from grid_tu_parser.parser import parse_record
from grid_tu_parser.snapshot import SnapshotResolution


class FakeCursor:
    def __init__(self):
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def executemany(self, sql, params):
        self.calls.append((sql, list(params)))


class FakeConn:
    def __init__(self):
        self.cursor_obj = FakeCursor()

    def cursor(self):
        return self.cursor_obj


def test_upsert_snapshot_resolutions_is_idempotent_and_parameterized():
    conn = FakeConn()
    row = SnapshotResolution(
        logical_tu_key="logical-1",
        status="canonical",
        representative_row_fingerprint="fp-1",
        observation_count=2,
        row_version_count=2,
        material_signature_count=1,
        conflict_fields=(),
        ambiguous_capacity_min_kw=None,
        ambiguous_capacity_max_kw=None,
        resolution_reason="single_material_signature",
    )
    assert upsert_snapshot_resolutions(conn, 7, [row]) == 1
    sql, params = conn.cursor_obj.calls[0]
    assert "on conflict (run_id, logical_tu_key) do update" in sql.lower()
    assert params[0][0:3] == (7, "logical-1", "canonical")


def test_upsert_canonical_parsed_is_scoped_by_run_and_logical_tu():
    conn = FakeConn()
    raw = RawTURecord(
        source="lvivoblenergo",
        source_url="https://example.test",
        source_page=1,
        source_row_index=1,
        fetched_at=datetime(2026, 8, 31, tzinfo=timezone.utc),
        tu_number="ТУ 1",
        tu_date="2026-08-30",
        installation_type="генерація",
        connection_point_raw="РУ-10 кВ ПС 35/10 кВ №201 Чишки",
        voltage_raw="10",
        requested_power_kw=1000.0,
        connection_type="нестандартне",
        rem="TEST",
    )
    row = CanonicalParsedRecord(
        logical_tu_key="logical-1",
        representative_row_fingerprint="fp-1",
        parsed=parse_record(raw),
    )
    assert upsert_canonical_parsed(conn, 7, [row]) == 1
    sql, params = conn.cursor_obj.calls[0]
    assert "on conflict (run_id, logical_tu_key) do update" in sql.lower()
    assert params[0][0:3] == (7, "logical-1", "fp-1")
    assert params[0][4] == 1000.0


def test_v2_metrics_are_scoped_by_run_id():
    conn = FakeConn()
    node = NodeAggregate(canonical_node_id="PS-201-CHYSHKY", generation_mw=1.0)
    assert upsert_node_metrics_v2(conn, 7, [node], date(2026, 8, 31)) == 1
    sql, params = conn.cursor_obj.calls[0]
    assert "on conflict (run_id, canonical_node_id) do update" in sql.lower()
    assert params[0][0] == 7
    assert params[0][1] == "PS-201-CHYSHKY"
