from datetime import datetime, timezone
from pathlib import Path

from grid_tu_parser.collector import parse_registry_html


def test_parse_registry_html_uses_headers_and_preserves_rows():
    html = Path("tests/fixtures/lviv_registry_sample.html").read_text()
    fetched_at = datetime(2026, 8, 30, tzinfo=timezone.utc)
    rows = parse_registry_html(html, "https://rtu.loe.lviv.ua/?page=1", 1, fetched_at)
    assert len(rows) == 4
    assert rows[0].source == "lvivoblenergo"
    assert rows[0].source_page == 1
    assert rows[0].tu_number == "ТУ 002181 030626 1 13 2"
    assert rows[0].connection_point_raw == "РУ-10 кВ ПС 35/10 кВ №144 Страдч"
    assert rows[0].voltage_raw == "10"
    assert rows[0].requested_power_kw == 300.0
    assert rows[0].rem == "ЗАХІДНИЙ РЕМ"


def test_parse_registry_html_parses_decimal_comma_power():
    html = Path("tests/fixtures/lviv_registry_sample.html").read_text()
    rows = parse_registry_html(html, "https://example.test", 1, datetime.now(timezone.utc))
    assert rows[2].requested_power_kw == 3000.5


def test_parse_registry_html_keeps_row_with_bad_power():
    html = Path("tests/fixtures/lviv_registry_sample.html").read_text()
    rows = parse_registry_html(html, "https://example.test", 1, datetime.now(timezone.utc))
    assert rows[3].requested_power_kw is None
    assert rows[3].connection_point_raw == "ПС 35/10 кВ №149 Тартаків"
