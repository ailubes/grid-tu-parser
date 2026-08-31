from dataclasses import replace
from datetime import datetime, timezone

from grid_tu_parser.identity import make_logical_tu_key, make_observation_key, make_row_fingerprint
from grid_tu_parser.models import RawTURecord


def make_record(**overrides):
    data = dict(
        source="lvivoblenergo", source_url="https://rtu.loe.lviv.ua/?page=1", source_page=1,
        source_row_index=1, fetched_at=datetime(2026, 8, 31, tzinfo=timezone.utc),
        tu_number="ТУ 123", tu_date="2026-06-03", installation_type="споживання",
        connection_point_raw="РУ-10 кВ ПС 35/10 кВ №201 Чишки", voltage_raw="10",
        requested_power_kw=442.0, connection_type="нестандартне", rem="ЛМЕМ",
        contract_number="Д-1", contract_date="2026-05-25", commissioning_stages="2026",
        payment_date="2026-06-01",
    )
    data.update(overrides)
    return RawTURecord(**data)


def test_row_fingerprint_changes_when_contract_date_changes():
    assert make_row_fingerprint(make_record(contract_date="2026-05-25")) != make_row_fingerprint(make_record(contract_date="2026-05-26"))


def test_identical_rows_share_fingerprint_but_not_observation_key():
    record = make_record(source_page=1, source_row_index=1)
    same_content_elsewhere = replace(record, source_page=2, source_row_index=7)
    assert make_row_fingerprint(record) == make_row_fingerprint(same_content_elsewhere)
    assert make_observation_key(10, record) != make_observation_key(10, same_content_elsewhere)


def test_logical_tu_key_is_stable_across_row_versions():
    record = make_record(contract_date="2026-05-25")
    assert make_logical_tu_key(record) == make_logical_tu_key(replace(record, contract_date="2026-05-26"))
