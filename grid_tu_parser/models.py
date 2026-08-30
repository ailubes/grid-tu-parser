from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class RawTURecord:
    source: str
    source_url: str
    source_page: int
    fetched_at: datetime
    tu_number: str | None
    tu_date: str | None
    installation_type: str | None
    connection_point_raw: str | None
    voltage_raw: str | None = None
    requested_power_kw: float | None = None
    connection_type: str | None = None
    rem: str | None = None


@dataclass
class ParsedTURecord:
    source: str
    source_url: str
    source_page: int
    fetched_at: datetime
    tu_number: str | None
    tu_date: str | None
    installation_type: str | None
    activity_type: str
    requested_power_kw: float | None
    connection_type: str | None
    rem: str | None
    connection_point_raw: str | None
    voltage_raw: str | None
    connection_object_type: str | None = None
    connection_voltage_kv: float | None = None
    connection_object_number: str | None = None
    connection_object_name: str | None = None
    feeder_id: str | None = None
    parent_object_type: str | None = None
    parent_number: str | None = None
    parent_name: str | None = None
    parent_voltage_levels_kv: list[float] = field(default_factory=list)
    canonical_node_id: str | None = None
    confidence: float = 0.0
    needs_review: bool = True
    flags: list[str] = field(default_factory=list)
    parse_error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data = self.__dict__.copy()
        data["fetched_at"] = self.fetched_at.isoformat()
        return data
