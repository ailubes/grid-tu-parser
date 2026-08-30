from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date
from typing import Iterable

from .models import ParsedTURecord


@dataclass
class AggregationStats:
    total_records: int
    mapped_records: int
    unmapped_records: int
    invalid_date_records: int


@dataclass
class NodeAggregate:
    canonical_node_id: str
    generation_mw: float = 0.0
    load_mw: float = 0.0
    bess_mw: float = 0.0
    other_mw: float = 0.0
    generation_tu_count: int = 0
    load_tu_count: int = 0
    bess_tu_count: int = 0
    other_tu_count: int = 0
    generation_3m_mw: float = 0.0
    generation_6m_mw: float = 0.0
    generation_12m_mw: float = 0.0
    load_3m_mw: float = 0.0
    load_6m_mw: float = 0.0
    load_12m_mw: float = 0.0
    bess_3m_mw: float = 0.0
    bess_6m_mw: float = 0.0
    bess_12m_mw: float = 0.0
    generation_tu_3m_count: int = 0
    load_tu_3m_count: int = 0
    bess_tu_3m_count: int = 0
    generation_tu_12m_count: int = 0
    load_tu_12m_count: int = 0
    bess_tu_12m_count: int = 0
    generation_tu_velocity_3m_per_month: float = 0.0
    load_tu_velocity_3m_per_month: float = 0.0
    bess_tu_velocity_3m_per_month: float = 0.0
    generation_tu_velocity_12m_per_month: float = 0.0
    load_tu_velocity_12m_per_month: float = 0.0
    bess_tu_velocity_12m_per_month: float = 0.0
    generation_load_ratio: float | None = None
    net_tu_imbalance_mw: float = 0.0
    bess_share: float = 0.0
    review_count: int = 0
    data_confidence: float = 0.0
    generation_pressure: int = 0
    load_pressure: int = 0
    bess_pressure: int = 0


@dataclass
class AggregationResult:
    as_of: date
    nodes: list[NodeAggregate]
    stats: AggregationStats


def _parse_tu_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except (TypeError, ValueError):
        return None


def _subtract_months(value: date, months: int) -> date:
    month_index = value.year * 12 + value.month - 1 - months
    year, month_zero = divmod(month_index, 12)
    month = month_zero + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def _percentile_rank(value: float, values: list[float]) -> float:
    if value <= 0:
        return 0.0
    if len(values) <= 1:
        return 100.0
    less = sum(item < value for item in values)
    equal = sum(item == value for item in values)
    average_zero_based_rank = less + (equal - 1) / 2
    return 100.0 * average_zero_based_rank / (len(values) - 1)


def _activity_prefix(activity: str) -> str:
    if activity == "generation":
        return "generation"
    if activity == "consumption":
        return "load"
    if activity == "bess":
        return "bess"
    return "other"


def aggregate_nodes(records: Iterable[ParsedTURecord], as_of: date | None = None) -> AggregationResult:
    records = list(records)
    parsed_dates = [_parse_tu_date(record.tu_date) for record in records]
    valid_dates = [item for item in parsed_dates if item is not None]
    if as_of is None:
        if valid_dates:
            as_of = max(valid_dates)
        elif records:
            as_of = max(record.fetched_at.date() for record in records)
        else:
            as_of = date.today()

    thresholds = {months: _subtract_months(as_of, months) for months in (3, 6, 12)}
    grouped: dict[str, list[tuple[ParsedTURecord, date | None]]] = {}
    unmapped = 0
    invalid_dates = 0
    for record, tu_date in zip(records, parsed_dates):
        if tu_date is None:
            invalid_dates += 1
        if not record.canonical_node_id:
            unmapped += 1
            continue
        grouped.setdefault(record.canonical_node_id, []).append((record, tu_date))

    nodes: list[NodeAggregate] = []
    for node_id, node_records in grouped.items():
        node = NodeAggregate(canonical_node_id=node_id)
        confidence_values: list[float] = []
        for record, tu_date in node_records:
            prefix = _activity_prefix(record.activity_type)
            power_mw = (record.requested_power_kw or 0.0) / 1000.0
            setattr(node, f"{prefix}_mw", getattr(node, f"{prefix}_mw") + power_mw)
            setattr(node, f"{prefix}_tu_count", getattr(node, f"{prefix}_tu_count") + 1)
            node.review_count += int(record.needs_review)
            confidence_values.append(record.confidence)

            if prefix != "other" and tu_date is not None and tu_date <= as_of:
                for months in (3, 6, 12):
                    if tu_date >= thresholds[months]:
                        setattr(node, f"{prefix}_{months}m_mw", getattr(node, f"{prefix}_{months}m_mw") + power_mw)
                        if months in (3, 12):
                            setattr(node, f"{prefix}_tu_{months}m_count", getattr(node, f"{prefix}_tu_{months}m_count") + 1)

        node.generation_load_ratio = node.generation_mw / node.load_mw if node.load_mw > 0 else None
        node.net_tu_imbalance_mw = node.generation_mw - node.load_mw
        classified_total = node.generation_mw + node.load_mw + node.bess_mw
        node.bess_share = node.bess_mw / classified_total if classified_total > 0 else 0.0
        node.data_confidence = 100.0 * sum(confidence_values) / len(confidence_values) if confidence_values else 0.0
        for prefix in ("generation", "load", "bess"):
            setattr(node, f"{prefix}_tu_velocity_3m_per_month", getattr(node, f"{prefix}_tu_3m_count") / 3.0)
            setattr(node, f"{prefix}_tu_velocity_12m_per_month", getattr(node, f"{prefix}_tu_12m_count") / 12.0)
        nodes.append(node)

    for prefix in ("generation", "load", "bess"):
        capacities = [getattr(node, f"{prefix}_mw") for node in nodes]
        velocities = [getattr(node, f"{prefix}_tu_velocity_3m_per_month") for node in nodes]
        for node in nodes:
            capacity_rank = _percentile_rank(getattr(node, f"{prefix}_mw"), capacities)
            velocity_rank = _percentile_rank(getattr(node, f"{prefix}_tu_velocity_3m_per_month"), velocities)
            setattr(node, f"{prefix}_pressure", round(0.7 * capacity_rank + 0.3 * velocity_rank))

    nodes.sort(key=lambda item: item.canonical_node_id)
    stats = AggregationStats(
        total_records=len(records),
        mapped_records=len(records) - unmapped,
        unmapped_records=unmapped,
        invalid_date_records=invalid_dates,
    )
    return AggregationResult(as_of=as_of, nodes=nodes, stats=stats)
