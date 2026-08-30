from datetime import date, datetime, timezone

from grid_tu_parser.aggregate import NodeAggregate
from grid_tu_parser.models import ParsedTURecord, RawTURecord


class RecordingCursor:
    def __init__(self, returned_id=7):
        self.calls = []
        self.returned_id = returned_id
        self._fetchone = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params=None):
        self.calls.append(("execute", " ".join(sql.split()), params))
        if "returning id" in sql.lower():
            self._fetchone = (self.returned_id,)

    def executemany(self, sql, params_seq):
        params_seq = list(params_seq)
        self.calls.append(("executemany", " ".join(sql.split()), params_seq))

    def fetchone(self):
        return self._fetchone


class RecordingConnection:
    def __init__(self):
        self.cursor_obj = RecordingCursor()

    def cursor(self):
        return self.cursor_obj


def raw_record(**overrides):
    values = dict(
        source="lvivoblenergo",
        source_url="https://rtu.loe.lviv.ua/?page=1",
        source_page=1,
        fetched_at=datetime(2026, 8, 30, 0, 0, tzinfo=timezone.utc),
        tu_number="TU-1",
        tu_date="2026-08-01",
        installation_type="УЗЕ",
        connection_point_raw="РУ-10 кВ ПС 35/10 кВ №144 Страдч",
        voltage_raw="10",
        requested_power_kw=3000.0,
        connection_type="нестандартне",
        rem="ЗАХІДНИЙ РЕМ",
    )
    values.update(overrides)
    return RawTURecord(**values)


def parsed_record(**overrides):
    values = dict(
        source="lvivoblenergo",
        source_url="https://rtu.loe.lviv.ua/?page=1",
        source_page=1,
        fetched_at=datetime(2026, 8, 30, 0, 0, tzinfo=timezone.utc),
        tu_number="TU-1",
        tu_date="2026-08-01",
        installation_type="УЗЕ",
        activity_type="bess",
        requested_power_kw=3000.0,
        connection_type="нестандартне",
        rem="ЗАХІДНИЙ РЕМ",
        connection_point_raw="РУ-10 кВ ПС 35/10 кВ №144 Страдч",
        voltage_raw="10",
        parent_object_type="PS",
        parent_number="144",
        parent_name="Страдч",
        parent_voltage_levels_kv=[35.0, 10.0],
        canonical_node_id="PS-144-STRADCH",
        confidence=1.0,
        needs_review=False,
        flags=[],
    )
    values.update(overrides)
    return ParsedTURecord(**values)


def test_make_record_key_is_stable_and_uses_source_identity_fields():
    from grid_tu_parser.database import make_record_key

    a = make_record_key(raw_record(fetched_at=datetime(2026, 8, 30, tzinfo=timezone.utc)))
    b = make_record_key(raw_record(fetched_at=datetime(2026, 8, 31, tzinfo=timezone.utc)))
    c = make_record_key(raw_record(requested_power_kw=3001.0))

    assert a == b
    assert len(a) == 64
    assert a != c


def test_upsert_raw_and_parsed_records_use_conflict_keys():
    from grid_tu_parser.database import upsert_parsed_records, upsert_raw_records

    conn = RecordingConnection()
    raw = raw_record()
    parsed = parsed_record()

    assert upsert_raw_records(conn, [raw]) == 1
    assert upsert_parsed_records(conn, [parsed]) == 1

    raw_call, parsed_call = conn.cursor_obj.calls
    assert raw_call[0] == "executemany"
    assert "insert into tu_raw" in raw_call[1].lower()
    assert "on conflict (record_key) do update" in raw_call[1].lower()
    assert parsed_call[0] == "executemany"
    assert "insert into tu_parsed" in parsed_call[1].lower()
    assert "on conflict (record_key) do update" in parsed_call[1].lower()


def test_upsert_nodes_and_daily_metrics_are_idempotent():
    from grid_tu_parser.database import upsert_node_metrics, upsert_nodes

    conn = RecordingConnection()
    parsed = parsed_record()
    node = NodeAggregate(canonical_node_id="PS-144-STRADCH", bess_mw=3.0, bess_pressure=100)
    seen_at = datetime(2026, 8, 30, tzinfo=timezone.utc)

    assert upsert_nodes(conn, [parsed], seen_at) == 1
    assert upsert_node_metrics(conn, [node], date(2026, 8, 30)) == 1

    node_call, metrics_call = conn.cursor_obj.calls
    assert "on conflict (canonical_node_id) do update" in node_call[1].lower()
    assert "on conflict (canonical_node_id, snapshot_date) do update" in metrics_call[1].lower()


def test_pipeline_run_logging_returns_id_and_records_finish_state():
    from grid_tu_parser.database import finish_pipeline_run, start_pipeline_run

    conn = RecordingConnection()
    run_id = start_pipeline_run(conn, "lvivoblenergo")
    finish_pipeline_run(conn, run_id, "success", {"raw": 20, "nodes": 5})

    assert run_id == 7
    start_call, finish_call = conn.cursor_obj.calls
    assert "insert into pipeline_runs" in start_call[1].lower()
    assert "returning id" in start_call[1].lower()
    assert "update pipeline_runs" in finish_call[1].lower()
    assert finish_call[2][0] == "success"


def test_apply_schema_executes_full_idempotent_ddl():
    from grid_tu_parser.database import apply_schema

    conn = RecordingConnection()
    sql = "create table if not exists example(id integer primary key);"
    apply_schema(conn, sql)

    call = conn.cursor_obj.calls[0]
    assert call[0] == "execute"
    assert call[1] == sql
