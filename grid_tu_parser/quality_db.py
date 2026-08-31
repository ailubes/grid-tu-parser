from __future__ import annotations

from typing import Any


def _rows_to_dicts(cur: Any, rows: list[Any]) -> list[dict[str, Any]]:
    description = cur.description or []
    columns = [getattr(item, "name", item[0]) for item in description]
    result: list[dict[str, Any]] = []
    for row in rows:
        if isinstance(row, dict):
            result.append(dict(row))
        else:
            result.append(dict(zip(columns, row)))
    return result


def fetch_quality_records(conn: Any) -> list[dict[str, Any]]:
    sql = """
        select
            p.record_key,
            r.tu_number,
            r.connection_point_raw,
            p.activity_type,
            p.canonical_node_id,
            p.confidence,
            p.needs_review,
            p.flags,
            p.parse_error,
            p.parent_object_type
        from tu_parsed p
        join tu_raw r on r.record_key = p.record_key
        order by p.record_key
    """
    with conn.cursor() as cur:
        cur.execute(sql)
        rows = cur.fetchall()
        return _rows_to_dicts(cur, rows)


def fetch_quality_records_v2(conn: Any, run_id: int) -> list[dict[str, Any]]:
    sql = """
        select
            p.logical_tu_key as record_key,
            r.tu_number,
            r.connection_point_raw,
            p.activity_type,
            p.canonical_node_id,
            p.confidence,
            p.needs_review,
            p.flags,
            p.parse_error,
            p.parent_object_type
        from tu_canonical_parsed p
        join tu_row_versions r on r.row_fingerprint = p.representative_row_fingerprint
        where p.run_id = %s
        order by p.logical_tu_key
    """
    with conn.cursor() as cur:
        cur.execute(sql, (run_id,))
        rows = cur.fetchall()
        return _rows_to_dicts(cur, rows)
