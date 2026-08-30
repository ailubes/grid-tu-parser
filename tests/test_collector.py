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


def test_parse_registry_html_ignores_leading_service_cell():
    html = '''
    <table>
      <thead><tr>
        <th>Номер ТУ</th><th>Дата Видачі ТУ</th><th>№ Договору (за наявності)</th><th>Дата Договору</th>
        <th>Тип електроустановки, споживання/генерація</th><th>Черги введення потужності за роками</th>
        <th>Точка забезпечення потужності (назва ПС, ТП,KТП тощо)</th><th>Напруга в точці приєднання</th>
        <th>Потужність замовлена до приєднання</th><th>Тип приєднання</th><th>Назва територіальної одиниці ОСР</th>
        <th>Дата надходження коштів від замовника</th>
      </tr></thead>
      <tbody><tr>
        <td class="service-cell"></td>
        <td>ТУ 002185 030626 1 13 1</td><td>03-06-2026 12:06:00</td><td>ТУ 002185 030626 1 13 1</td><td>25-05-2026 12:05:00</td>
        <td>електроустановка, призначена для споживання електричної енергії</td><td>Дані відсутні</td>
        <td>ПЛ-0,4 кВ КТП-208-11 Л-2</td><td>0.23</td><td>5.0</td><td>стандартне приєднання</td><td>ПІВНІЧНИЙ РЕМ</td><td>Дані відсутні</td>
      </tr></tbody>
    </table>
    '''
    rows = parse_registry_html(html, "https://example.test", 1, datetime.now(timezone.utc))
    assert rows[0].tu_number == "ТУ 002185 030626 1 13 1"
    assert rows[0].tu_date == "2026-06-03"
    assert rows[0].installation_type.startswith("електроустановка")
    assert rows[0].connection_point_raw == "ПЛ-0.4 кВ КТП-208-11 Л-2"
    assert rows[0].requested_power_kw == 5.0


def test_parse_registry_html_includes_row_header_cell_for_tu_number():
    html = '''
    <table>
      <thead><tr>
        <th>Номер ТУ</th><th>Дата Видачі ТУ</th><th>№ Договору (за наявності)</th><th>Дата Договору</th>
        <th>Тип електроустановки, споживання/генерація</th><th>Черги введення потужності за роками</th>
        <th>Точка забезпечення потужності (назва ПС, ТП,KТП тощо)</th><th>Напруга в точці приєднання</th>
        <th>Потужність замовлена до приєднання</th><th>Тип приєднання</th><th>Назва територіальної одиниці ОСР</th>
        <th>Дата надходження коштів від замовника</th>
      </tr></thead>
      <tbody><tr>
        <th>ТУ 002185 030626 1 13 1</th><td>03-06-2026 12:06:00</td><td>ТУ 002185 030626 1 13 1</td><td>25-05-2026 12:05:00</td>
        <td>електроустановка, призначена для споживання електричної енергії</td><td>Дані відсутні</td>
        <td>ПЛ-0,4 кВ КТП-208-11 Л-2</td><td>0.23</td><td>5.0</td><td>стандартне приєднання</td><td>ПІВНІЧНИЙ РЕМ</td><td>Дані відсутні</td>
      </tr></tbody>
    </table>
    '''
    rows = parse_registry_html(html, "https://rtu.loe.lviv.ua/?page=1", 1, datetime.now(timezone.utc))
    assert rows[0].tu_number == "ТУ 002185 030626 1 13 1"
    assert rows[0].tu_date == "2026-06-03"
    assert rows[0].installation_type == "електроустановка, призначена для споживання електричної енергії"
    assert rows[0].connection_point_raw == "ПЛ-0.4 кВ КТП-208-11 Л-2"
    assert rows[0].voltage_raw == "0.23"
    assert rows[0].requested_power_kw == 5.0
    assert rows[0].rem == "ПІВНІЧНИЙ РЕМ"
