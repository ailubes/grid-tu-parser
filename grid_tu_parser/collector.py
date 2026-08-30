from __future__ import annotations

import re
import time
from datetime import datetime, timezone
from urllib.parse import urlencode, urlsplit, urlunsplit, parse_qsl

import requests
from bs4 import BeautifulSoup

from .models import RawTURecord
from .normalize import normalize_text


class CollectorError(RuntimeError):
    def __init__(self, message: str, failed_page: int, partial_records: list[RawTURecord]):
        super().__init__(message)
        self.failed_page = failed_page
        self.partial_records = partial_records


_HEADER_KEYS = {
    "tu_number": ("номер ту",),
    "tu_date": ("дата видачі ту", "дата видачи ту"),
    "installation_type": ("тип електроустановки",),
    "connection_point_raw": ("точка забезпечення потужності",),
    "voltage_raw": ("напруга в точці приєднання",),
    "requested_power_kw": ("потужність замовлена до приєднання",),
    "connection_type": ("тип приєднання",),
    "rem": ("назва територіальної одиниці оср",),
}


def _header_key(text: str) -> str | None:
    lowered = normalize_text(text).lower()
    for key, markers in _HEADER_KEYS.items():
        if any(marker in lowered for marker in markers):
            return key
    return None


def _parse_power(value: str | None) -> float | None:
    if not value:
        return None
    text = normalize_text(value).replace(" ", "")
    match = re.fullmatch(r"[-+]?\d+(?:\.\d+)?", text)
    if not match:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _parse_date(value: str | None) -> str | None:
    if not value:
        return None
    text = normalize_text(value)
    for fmt in ("%d-%m-%Y %H:%M:%S", "%d-%m-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    return text or None


def parse_registry_html(html: str, source_url: str, source_page: int, fetched_at: datetime) -> list[RawTURecord]:
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table")
    if table is None:
        return []

    header_cells = table.find_all("th")
    header_map: dict[int, str] = {}
    for idx, cell in enumerate(header_cells):
        key = _header_key(cell.get_text(" ", strip=True))
        if key:
            header_map[idx] = key

    records: list[RawTURecord] = []
    for row in table.find_all("tr"):
        cells = row.find_all("td")
        if not cells:
            continue
        values = [normalize_text(cell.get_text(" ", strip=True)) for cell in cells]
        mapped: dict[str, str | None] = {key: None for key in _HEADER_KEYS}
        for idx, key in header_map.items():
            if idx < len(values):
                mapped[key] = values[idx] or None
        records.append(RawTURecord(
            source="lvivoblenergo",
            source_url=source_url,
            source_page=source_page,
            fetched_at=fetched_at,
            tu_number=mapped["tu_number"],
            tu_date=_parse_date(mapped["tu_date"]),
            installation_type=mapped["installation_type"],
            connection_point_raw=mapped["connection_point_raw"],
            voltage_raw=mapped["voltage_raw"],
            requested_power_kw=_parse_power(mapped["requested_power_kw"]),
            connection_type=mapped["connection_type"],
            rem=mapped["rem"],
        ))
    return records


def _url_for_page(base_url: str, page: int) -> str:
    split = urlsplit(base_url)
    query = dict(parse_qsl(split.query, keep_blank_values=True))
    query["page"] = str(page)
    return urlunsplit((split.scheme, split.netloc, split.path, urlencode(query), split.fragment))


def _discover_last_page(html: str, fallback: int) -> int:
    soup = BeautifulSoup(html, "html.parser")
    pages = [fallback]
    for link in soup.find_all("a", href=True):
        match = re.search(r"[?&]page=(\d+)", link.get("href", ""))
        if match:
            pages.append(int(match.group(1)))
        label = normalize_text(link.get_text(" ", strip=True))
        if label.isdigit():
            pages.append(int(label))
    return max(pages)


def _fetch_with_retries(session: requests.Session, url: str, timeout: float, retries: int) -> requests.Response:
    last_exc: Exception | None = None
    for attempt in range(retries + 1):
        try:
            response = session.get(url, timeout=timeout)
            if response.status_code >= 500 or response.status_code == 429:
                response.raise_for_status()
            if response.status_code >= 400:
                response.raise_for_status()
            return response
        except requests.RequestException as exc:
            last_exc = exc
            if attempt >= retries:
                break
            time.sleep(0.25 * (attempt + 1))
    assert last_exc is not None
    raise last_exc


def collect_pages(base_url: str, start_page: int = 1, end_page: int | None = None, *, timeout: float = 15.0, retries: int = 2, session: requests.Session | None = None) -> list[RawTURecord]:
    own_session = session is None
    session = session or requests.Session()
    records: list[RawTURecord] = []
    try:
        page = start_page
        discovered_end = end_page
        while True:
            if discovered_end is not None and page > discovered_end:
                break
            url = _url_for_page(base_url, page)
            try:
                response = _fetch_with_retries(session, url, timeout, retries)
            except requests.RequestException as exc:
                raise CollectorError(f"Failed to fetch registry page {page}: {exc}", failed_page=page, partial_records=records.copy()) from exc
            fetched_at = datetime.now(timezone.utc)
            page_records = parse_registry_html(response.text, url, page, fetched_at)
            records.extend(page_records)
            if discovered_end is None:
                discovered_end = _discover_last_page(response.text, page)
            if page >= discovered_end:
                break
            page += 1
    finally:
        if own_session:
            session.close()
    return records
