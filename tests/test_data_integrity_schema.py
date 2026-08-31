from pathlib import Path


def test_schema_contains_lossless_integrity_tables():
    sql = Path("schema.sql").read_text(encoding="utf-8").lower()
    assert "create table if not exists tu_row_versions" in sql
    assert "create table if not exists tu_observations" in sql
    assert "contract_number text" in sql
    assert "contract_date text" in sql
    assert "commissioning_stages text" in sql
    assert "payment_date text" in sql
    assert "references pipeline_runs(id)" in sql
    assert "references tu_row_versions(row_fingerprint)" in sql
    assert "unique (run_id, source_page, source_row_index)" in sql
