from dataclasses import replace
from datetime import datetime, timezone

from grid_tu_parser.integrity_audit import build_integrity_audit
from grid_tu_parser.integrity_db import insert_observations, upsert_row_versions
from grid_tu_parser.models import RawTURecord


class FakeCursor:
    def __init__(self): self.calls = []
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def executemany(self, sql, params): self.calls.append((sql, list(params)))


class FakeConn:
    def __init__(self): self.cursor_obj = FakeCursor()
    def cursor(self): return self.cursor_obj


def rec(page=1, row=1, contract_date="2026-05-25", tu_number="ТУ 123"):
    return RawTURecord(
        source="lvivoblenergo", source_url="https://example.test", source_page=page,
        source_row_index=row, fetched_at=datetime(2026, 8, 31, tzinfo=timezone.utc),
        tu_number=tu_number, tu_date="2026-06-03", installation_type="споживання",
        connection_point_raw="РУ-10 кВ ПС 35/10 кВ №201 Чишки", voltage_raw="10",
        requested_power_kw=442.0, connection_type="нестандартне", rem="ЛМЕМ",
        contract_number="Д-1", contract_date=contract_date, commissioning_stages="2026",
        payment_date="2026-06-01",
    )


def test_shadow_writes_preserve_versions_and_observations():
    conn = FakeConn()
    a = rec(page=1, row=1)
    duplicate_elsewhere = replace(a, source_page=2, source_row_index=7)
    assert upsert_row_versions(conn, [a, duplicate_elsewhere]) == 1
    assert insert_observations(conn, 10, [a, duplicate_elsewhere]) == 2
    row_sql, row_params = conn.cursor_obj.calls[0]
    obs_sql, obs_params = conn.cursor_obj.calls[1]
    assert "on conflict (row_fingerprint) do update" in row_sql.lower()
    assert len(row_params) == 1
    assert "on conflict (observation_key) do nothing" in obs_sql.lower()
    assert len(obs_params) == 2
    assert obs_params[0][0] != obs_params[1][0]


def test_audit_distinguishes_exact_duplicates_from_changed_versions():
    a = rec(1, 1, "2026-05-25")
    exact_duplicate = replace(a, source_page=2, source_row_index=1)
    changed_version = rec(3, 1, "2026-05-26")
    different_tu = rec(4, 1, "2026-05-25", "ТУ 999")
    report = build_integrity_audit([a, exact_duplicate, changed_version, different_tu])
    assert report["fetched_rows"] == 4
    assert report["legacy_unique_records"] == 2
    assert report["legacy_collision_loss"] == 2
    assert report["unique_row_versions"] == 3
    assert report["unique_logical_tus"] == 2
    assert report["duplicate_observations"] == 1
    assert report["logical_tus_with_multiple_versions"] == 1
    group = report["top_legacy_collision_groups"][0]
    assert group["observation_count"] == 3
    assert group["distinct_row_versions"] == 2
    assert "contract_date" in group["differing_fields"]
