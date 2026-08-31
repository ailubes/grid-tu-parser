from datetime import datetime, timezone

from grid_tu_parser.collector import parse_registry_html


def test_collector_preserves_all_12_columns_and_source_date_markers():
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
        <th scope="row">ТУ 002185 030626 1 13 1</th><td>03-06-2026 12:06:00</td>
        <td>ТУ 002185 030626 1 13 1</td><td>25-05-2026 12:05:00</td>
        <td>електроустановка, призначена для споживання електричної енергії</td><td>Дані відсутні</td>
        <td>ПЛ-0,4 кВ КТП-208-11 Л-2</td><td>0.23</td><td>5.0</td><td>стандартне приєднання</td>
        <td>ПІВНІЧНИЙ РЕМ</td><td>Дані відсутні</td>
      </tr></tbody>
    </table>
    '''
    rows = parse_registry_html(html, "https://rtu.loe.lviv.ua/?page=1", 1, datetime(2026, 8, 31, tzinfo=timezone.utc))
    row = rows[0]
    assert row.source_row_index == 1
    assert row.tu_number == "ТУ 002185 030626 1 13 1"
    assert row.tu_date == "2026-06-03"
    assert row.contract_number == "ТУ 002185 030626 1 13 1"
    assert row.contract_date == "25-05-2026 12:05:00"
    assert row.commissioning_stages == "Дані відсутні"
    assert row.connection_point_raw == "ПЛ-0.4 кВ КТП-208-11 Л-2"
    assert row.voltage_raw == "0.23"
    assert row.requested_power_kw == 5.0
    assert row.connection_type == "стандартне приєднання"
    assert row.rem == "ПІВНІЧНИЙ РЕМ"
    assert row.payment_date == "Дані відсутні"
