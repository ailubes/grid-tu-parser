from pathlib import Path


def test_schema_defines_pipeline_tables_keys_and_indexes():
    sql = Path('schema.sql').read_text(encoding='utf-8').lower()
    for table in ('tu_raw', 'tu_parsed', 'grid_nodes', 'node_metrics', 'pipeline_runs'):
        assert f'create table if not exists {table}' in sql
    assert 'record_key text primary key' in sql
    assert 'primary key (canonical_node_id, snapshot_date)' in sql
    assert 'references tu_raw(record_key)' in sql
    for index in (
        'idx_tu_raw_tu_date', 'idx_tu_parsed_node', 'idx_node_metrics_snapshot_date',
        'idx_pipeline_runs_started_at',
    ):
        assert index in sql


def test_schema_uses_timestamptz_and_jsonb_for_operational_data():
    sql = Path('schema.sql').read_text(encoding='utf-8').lower()
    assert 'timestamptz' in sql
    assert 'flags jsonb' in sql
    assert 'counts jsonb' in sql
