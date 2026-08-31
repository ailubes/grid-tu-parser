from grid_tu_parser.quality_db import fetch_quality_records_v2


class Column:
    def __init__(self, name):
        self.name = name


class FakeCursor:
    def __init__(self):
        self.calls = []
        self.description = [Column(name) for name in (
            "record_key", "tu_number", "connection_point_raw", "activity_type",
            "canonical_node_id", "confidence", "needs_review", "flags",
            "parse_error", "parent_object_type",
        )]

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, sql, params=None):
        self.calls.append((sql, params))

    def fetchall(self):
        return [("logical-1", "ТУ 1", "ПС 35/10 кВ №201 Чишки", "generation", "PS-201-CHYSHKY", 1.0, False, [], None, "PS")]


class FakeConn:
    def __init__(self):
        self.cursor_obj = FakeCursor()

    def cursor(self):
        return self.cursor_obj


def test_fetch_quality_records_v2_is_scoped_to_exact_run():
    conn = FakeConn()
    rows = fetch_quality_records_v2(conn, 7)
    sql, params = conn.cursor_obj.calls[0]
    assert "from tu_canonical_parsed p" in sql.lower()
    assert "join tu_row_versions r" in sql.lower()
    assert "where p.run_id = %s" in sql.lower()
    assert params == (7,)
    assert rows[0]["record_key"] == "logical-1"
