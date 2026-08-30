from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import Any, Iterable

from .normalize import normalize_text

_FAMILY_PATTERNS = (
    ("PLI", re.compile(r"(?<![А-ЯІЇЄҐA-Z])ПЛІ(?=[-\s]|$)", re.IGNORECASE)),
    ("RU", re.compile(r"(?<![А-ЯІЇЄҐA-Z])РУ(?=[-\s]|$)", re.IGNORECASE)),
    ("PL", re.compile(r"(?<![А-ЯІЇЄҐA-Z])ПЛ(?=[-\s]|$)", re.IGNORECASE)),
    ("KL", re.compile(r"(?<![А-ЯІЇЄҐA-Z])КЛ(?=[-\s]|$)", re.IGNORECASE)),
    ("PS", re.compile(r"(?<![А-ЯІЇЄҐA-Z])ПС(?=[-\s]|$)", re.IGNORECASE)),
    ("KTP", re.compile(r"(?<![А-ЯІЇЄҐA-Z])(?:КТПП|СКТП|КТП)(?=[-\s]|$)", re.IGNORECASE)),
    ("ZTP", re.compile(r"(?<![А-ЯІЇЄҐA-Z])ЗТП(?=[-\s]|$)", re.IGNORECASE)),
    ("TP", re.compile(r"(?<![А-ЯІЇЄҐA-Z])(?:ЩТП|ТП)(?=[-\s]|$)", re.IGNORECASE)),
    ("CRP", re.compile(r"(?<![А-ЯІЇЄҐA-Z])ЦРП(?=[-\s]|$)", re.IGNORECASE)),
    ("RP", re.compile(r"(?<![А-ЯІЇЄҐA-Z])РП(?=[-\s]|$)", re.IGNORECASE)),
)
_NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)?")
_SPACE_RE = re.compile(r"\s+")


def classify_connection_family(text: str | None) -> str:
    normalized = normalize_text(text or "").upper()
    for family, pattern in _FAMILY_PATTERNS:
        if pattern.search(normalized):
            return family
    return "UNKNOWN"


def normalize_review_pattern(text: str | None) -> str:
    normalized = normalize_text(text or "").upper()
    normalized = _NUMBER_RE.sub("{N}", normalized)
    normalized = _SPACE_RE.sub(" ", normalized).strip()
    return normalized or "<EMPTY>"


def _pct(part: int, whole: int) -> float:
    return round(100.0 * part / whole, 2) if whole else 0.0


def _confidence_bucket(value: Any) -> str:
    try:
        confidence = float(value or 0.0)
    except (TypeError, ValueError):
        confidence = 0.0
    if confidence >= 0.90:
        return "high_0_90_1_00"
    if confidence >= 0.75:
        return "medium_0_75_0_89"
    if confidence >= 0.50:
        return "low_0_50_0_74"
    return "critical_0_00_0_49"


def _flags(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, tuple):
        return [str(item) for item in value]
    if not value:
        return []
    return [str(value)]


def analyze_quality(rows: Iterable[dict[str, Any]], *, example_limit: int = 5, pattern_limit: int = 30) -> dict[str, Any]:
    records = list(rows)
    total = len(records)
    mapped = sum(1 for row in records if row.get("canonical_node_id"))
    reviews = [row for row in records if bool(row.get("needs_review"))]
    parse_errors = sum(1 for row in records if row.get("parse_error"))
    unknown_activity = sum(1 for row in records if row.get("activity_type") == "unknown")

    flag_counter: Counter[str] = Counter()
    flag_unmapped: Counter[str] = Counter()
    examples: dict[str, list[dict[str, Any]]] = defaultdict(list)
    family_counter: Counter[str] = Counter()
    pattern_counter: Counter[str] = Counter()
    pattern_unmapped: Counter[str] = Counter()
    pattern_family: dict[str, str] = {}
    confidence_counter: Counter[str] = Counter(_confidence_bucket(row.get("confidence")) for row in records)

    for row in reviews:
        family = classify_connection_family(row.get("connection_point_raw"))
        family_counter[family] += 1
        pattern = normalize_review_pattern(row.get("connection_point_raw"))
        pattern_counter[pattern] += 1
        pattern_family.setdefault(pattern, family)
        if not row.get("canonical_node_id"):
            pattern_unmapped[pattern] += 1
        issues = _flags(row.get("flags")) or ["review_without_flag"]
        for issue in issues:
            flag_counter[issue] += 1
            if not row.get("canonical_node_id"):
                flag_unmapped[issue] += 1
            if len(examples[issue]) < example_limit:
                examples[issue].append({
                    "tu_number": row.get("tu_number"),
                    "connection_point_raw": row.get("connection_point_raw"),
                    "confidence": row.get("confidence"),
                    "canonical_node_id": row.get("canonical_node_id"),
                    "parse_error": row.get("parse_error"),
                })

    flag_counts = [
        {"flag": flag, "count": count, "pct_of_review": _pct(count, len(reviews)), "unmapped_count": flag_unmapped[flag]}
        for flag, count in sorted(flag_counter.items(), key=lambda item: (-item[1], item[0]))
    ]
    review_families = [
        {"family": family, "count": count, "pct_of_review": _pct(count, len(reviews))}
        for family, count in sorted(family_counter.items(), key=lambda item: (-item[1], item[0]))
    ]
    top_review_patterns = [
        {"pattern": pattern, "family": pattern_family[pattern], "count": count, "unmapped_count": pattern_unmapped[pattern]}
        for pattern, count in sorted(pattern_counter.items(), key=lambda item: (-item[1], item[0]))[:pattern_limit]
    ]
    quick_wins = [
        {"issue": issue, "review_count": count, "unmapped_count": flag_unmapped[issue], "pct_of_review": _pct(count, len(reviews))}
        for issue, count in sorted(flag_counter.items(), key=lambda item: (-flag_unmapped[item[0]], -item[1], item[0]))
    ]
    return {
        "summary": {
            "total_records": total,
            "mapped_records": mapped,
            "mapped_pct": _pct(mapped, total),
            "review_records": len(reviews),
            "review_pct": _pct(len(reviews), total),
            "parse_error_records": parse_errors,
            "unknown_activity_records": unknown_activity,
        },
        "flag_counts": flag_counts,
        "confidence_buckets": {
            "high_0_90_1_00": confidence_counter["high_0_90_1_00"],
            "medium_0_75_0_89": confidence_counter["medium_0_75_0_89"],
            "low_0_50_0_74": confidence_counter["low_0_50_0_74"],
            "critical_0_00_0_49": confidence_counter["critical_0_00_0_49"],
        },
        "review_families": review_families,
        "top_review_patterns": top_review_patterns,
        "quick_wins": quick_wins,
        "examples": dict(sorted(examples.items())),
    }


def write_quality_json(report: dict[str, Any], path: Any) -> None:
    import json
    from pathlib import Path
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


def write_review_csv(rows: Iterable[dict[str, Any]], path: Any) -> None:
    import csv
    from pathlib import Path
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fields = ["record_key", "tu_number", "connection_point_raw", "family", "activity_type", "canonical_node_id", "confidence", "flags", "parse_error", "parent_object_type"]
    with target.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            if not bool(row.get("needs_review")):
                continue
            writer.writerow({
                "record_key": row.get("record_key"),
                "tu_number": row.get("tu_number"),
                "connection_point_raw": row.get("connection_point_raw"),
                "family": classify_connection_family(row.get("connection_point_raw")),
                "activity_type": row.get("activity_type"),
                "canonical_node_id": row.get("canonical_node_id"),
                "confidence": row.get("confidence"),
                "flags": "|".join(_flags(row.get("flags"))),
                "parse_error": row.get("parse_error"),
                "parent_object_type": row.get("parent_object_type"),
            })


def render_console_report(report: dict[str, Any], *, top: int = 10) -> str:
    summary = report["summary"]
    lines = [
        f"QUALITY total={summary['total_records']} mapped={summary['mapped_records']} ({summary['mapped_pct']}%) review={summary['review_records']} ({summary['review_pct']}%) parse_errors={summary['parse_error_records']} unknown_activity={summary['unknown_activity_records']}",
        "TOP FLAGS",
    ]
    for item in report["flag_counts"][:top]:
        lines.append(f"  {item['flag']}: review={item['count']} unmapped={item['unmapped_count']} ({item['pct_of_review']}% of review)")
    lines.append("REVIEW FAMILIES")
    for item in report["review_families"][:top]:
        lines.append(f"  {item['family']}: {item['count']} ({item['pct_of_review']}%)")
    lines.append("QUICK WINS")
    for item in report["quick_wins"][:top]:
        lines.append(f"  {item['issue']}: unmapped={item['unmapped_count']} review={item['review_count']}")
    lines.append("TOP REVIEW PATTERNS")
    for item in report["top_review_patterns"][:top]:
        lines.append(f"  {item['family']} count={item['count']} unmapped={item['unmapped_count']} :: {item['pattern']}")
    return "\n".join(lines)
