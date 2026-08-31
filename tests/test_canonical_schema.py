from pathlib import Path


def test_schema_adds_non_destructive_canonical_tables_and_current_view():
    sql = Path("schema.sql").read_text(encoding="utf-8").lower()
    assert "create table if not exists tu_snapshot_resolution" in sql
    assert "primary key (run_id, logical_tu_key)" in sql
    assert "status in ('canonical', 'ambiguous')" in sql
    assert "ambiguous_capacity_min_kw" in sql
    assert "ambiguous_capacity_max_kw" in sql
    assert "create table if not exists tu_canonical_parsed" in sql
    assert "create table if not exists node_metrics_v2" in sql
    assert "primary key (run_id, canonical_node_id)" in sql
    assert "create or replace view current_node_metrics_v2" in sql
    assert "r2.status = 'success'" in sql
    assert "drop table" not in sql
    assert "drop column" not in sql
