from __future__ import annotations

import requests
from bs4 import BeautifulSoup

URL = "https://rtu.loe.lviv.ua/?page=1"


def describe_cells(cells):
    rows = []
    for i, cell in enumerate(cells):
        rows.append({
            "index": i,
            "tag": cell.name,
            "text": " ".join(cell.stripped_strings),
            "class": cell.get("class"),
            "style": cell.get("style"),
            "colspan": cell.get("colspan"),
        })
    return rows


def main() -> None:
    r = requests.get(URL, timeout=30)
    print("status", r.status_code, "bytes", len(r.content))
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    tables = soup.find_all("table")
    print("tables", len(tables))
    for ti, table in enumerate(tables):
        print("TABLE", ti, "class=", table.get("class"), "id=", table.get("id"))
        rows = table.find_all("tr")
        print("row_count", len(rows))
        for ri, row in enumerate(rows[:5]):
            direct = row.find_all(["th", "td"], recursive=False)
            print("ROW", ri, "direct_cell_count", len(direct), describe_cells(direct))


if __name__ == "__main__":
    main()
