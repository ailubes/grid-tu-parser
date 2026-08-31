from grid_tu_parser import database as db


def test_database_exposes_public_metric_fields_without_breaking_legacy_alias():
    assert db.METRIC_FIELDS
    assert db._METRIC_FIELDS is db.METRIC_FIELDS
    assert "generation_mw" in db.METRIC_FIELDS
    assert "bess_pressure" in db.METRIC_FIELDS
