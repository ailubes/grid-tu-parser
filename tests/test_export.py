import csv
import json
from datetime import datetime, timezone

from grid_tu_parser.export import write_csv, write_json
from grid_tu_parser.models import ParsedTURecord


def _record():
    return ParsedTURecord(
        source="lvivoblenergo",
        source_url="https://example.test",
        source_page=1,
        fetched_at=datetime(2026, 8, 30, tzinfo=timezone.utc),
        tu_number="ТУ 1",
        tu_date="2026-05-28",
        installation_type="УЗЕ",
        activity_type="bess",
        requested_power_kw=3000.0,
        connection_type="нестандартне",
        rem="ЗАХІДНИЙ РЕМ",
        connection_point_raw="РУ-10 кВ ПС 35/10 кВ №144 Страдч",
        voltage_raw="10",
        canonical_node_id="PS-144-STRADCH",
        parent_object_type="PS",
        parent_number="144",
        parent_name="Страдч",
        parent_voltage_levels_kv=[35.0, 10.0],
        confidence=1.0,
        needs_review=False,
    )


def test_write_json_preserves_key_fields(tmp_path):
    path = tmp_path / "parsed.json"
    write_json([_record()], path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload[0]["canonical_node_id"] == "PS-144-STRADCH"
    assert payload[0]["activity_type"] == "bess"
    assert payload[0]["requested_power_kw"] == 3000.0


def test_write_csv_preserves_key_fields(tmp_path):
    path = tmp_path / "parsed.csv"
    write_csv([_record()], path)
    with path.open(encoding="utf-8", newline="") as handle:
        row = next(csv.DictReader(handle))
    assert row["canonical_node_id"] == "PS-144-STRADCH"
    assert row["activity_type"] == "bess"
    assert float(row["requested_power_kw"]) == 3000.0
    assert json.loads(row["parent_voltage_levels_kv"]) == [35.0, 10.0]
