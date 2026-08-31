from datetime import date, datetime, timezone

import pytest

from grid_tu_parser.models import RawTURecord


class FakeConnection:
    def __init__(self):
        self.commits = 0
        self.rollbacks = 0

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


def raw(number, activity, power, point, row_index=1):
    return RawTURecord(
        source="lvivoblenergo",
        source_url="https://example.test",
        source_page=1,
        source_row_index=row_index,
        fetched_at=datetime(2026, 8, 30, tzinfo=timezone.utc),
        tu_number=number,
        tu_date="2026-08-29",
        installation_type=activity,
        connection_point_raw=point,
        voltage_raw="10",
        requested_power_kw=power,
        connection_type="нестандартне",
        rem="TEST",
    )


def test_run_update_orchestrates_collection_persistence_and_daily_snapshot(monkeypatch):
    import grid_tu_parser.pipeline as pipeline

    conn = FakeConnection()
    records = [
        raw("1", "генерація", 1000, "ПС 35/10 кВ №149 Тартаків", 1),
        raw("2", "УЗЕ", 500, "ПС 35/10 кВ №149 Тартаків", 2),
    ]
    calls = []

    monkeypatch.setattr(pipeline, "collect_pages", lambda base_url: records)
    monkeypatch.setattr(pipeline.db, "start_pipeline_run", lambda conn, source: calls.append(("start", source)) or 42)
    monkeypatch.setattr(pipeline.integrity_db, "upsert_row_versions", lambda conn, rows: calls.append(("row_versions", len(rows))) or len(rows))
    monkeypatch.setattr(pipeline.integrity_db, "insert_observations", lambda conn, run_id, rows: calls.append(("observations", run_id, len(rows))) or len(rows))
    monkeypatch.setattr(pipeline.db, "upsert_raw_records", lambda conn, rows: calls.append(("raw", len(rows))) or len(rows))
    monkeypatch.setattr(pipeline.db, "upsert_parsed_records", lambda conn, rows: calls.append(("parsed", len(rows))) or len(rows))
    monkeypatch.setattr(pipeline.db, "upsert_nodes", lambda conn, rows, seen_at: calls.append(("nodes", len(rows))) or 1)
    monkeypatch.setattr(pipeline.db, "upsert_node_metrics", lambda conn, nodes, snapshot_date: calls.append(("metrics", len(nodes), snapshot_date)) or len(nodes))
    monkeypatch.setattr(pipeline.db, "finish_pipeline_run", lambda conn, run_id, status, counts, error=None: calls.append(("finish", run_id, status, counts, error)))

    summary = pipeline.run_update(conn, "https://example.test", as_of=date(2026, 8, 30))

    assert summary.raw_count == 2
    assert summary.parsed_count == 2
    assert summary.node_count == 1
    assert summary.observation_count == 2
    assert summary.row_version_count == 2
    assert summary.snapshot_date == date(2026, 8, 30)
    assert calls[0] == ("start", "lvivoblenergo")
    assert ("observations", 42, 2) in calls
    assert ("metrics", 1, date(2026, 8, 30)) in calls
    assert calls[-1][0:3] == ("finish", 42, "success")
    assert conn.commits == 2
    assert conn.rollbacks == 0


def test_run_update_rolls_back_data_and_marks_failed_run(monkeypatch):
    import grid_tu_parser.pipeline as pipeline

    conn = FakeConnection()
    calls = []
    monkeypatch.setattr(pipeline.db, "start_pipeline_run", lambda conn, source: 9)
    monkeypatch.setattr(pipeline, "collect_pages", lambda base_url: (_ for _ in ()).throw(RuntimeError("registry unavailable")))
    monkeypatch.setattr(pipeline.db, "finish_pipeline_run", lambda conn, run_id, status, counts, error=None: calls.append((run_id, status, counts, error)))

    with pytest.raises(RuntimeError, match="registry unavailable"):
        pipeline.run_update(conn, "https://example.test", as_of=date(2026, 8, 30))

    assert conn.commits == 2
    assert conn.rollbacks == 1
    assert calls[0][0:2] == (9, "failed")
    assert "registry unavailable" in calls[0][3]
