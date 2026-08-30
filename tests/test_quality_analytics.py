from pathlib import Path

from grid_tu_parser.quality import analyze_quality, classify_connection_family, normalize_review_pattern


def _row(**overrides):
    values = {
        "record_key": "k1",
        "tu_number": "TU-1",
        "connection_point_raw": "РУ-10 кВ ПС 35/10 кВ №144 Страдч",
        "activity_type": "consumption",
        "canonical_node_id": "PS-144-STRADCH",
        "confidence": 1.0,
        "needs_review": False,
        "flags": [],
        "parse_error": None,
        "parent_object_type": "PS",
    }
    values.update(overrides)
    return values


def test_quality_report_counts_review_flags_and_families():
    rows = [
        _row(),
        _row(
            record_key="k2",
            tu_number="TU-2",
            connection_point_raw="ПЛ-10 кВ 201-37 Чишки",
            canonical_node_id=None,
            confidence=0.0,
            needs_review=True,
            flags=["unknown_object_type"],
            parent_object_type=None,
        ),
        _row(
            record_key="k3",
            tu_number="TU-3",
            connection_point_raw="РУ-35 кВ ПС 110/35/10 кВ №136 Перемишляни",
            confidence=0.6,
            needs_review=True,
            flags=["conflicting_voltage_context"],
        ),
    ]
    report = analyze_quality(rows)
    assert report["summary"]["total_records"] == 3
    assert report["summary"]["mapped_records"] == 2
    assert report["summary"]["review_records"] == 2
    flags = {item["flag"]: item["count"] for item in report["flag_counts"]}
    assert flags == {"conflicting_voltage_context": 1, "unknown_object_type": 1}
    families = {item["family"]: item["count"] for item in report["review_families"]}
    assert families == {"PL": 1, "RU": 1}


def test_pattern_normalization_and_family_are_stable():
    assert classify_connection_family("ПЛІ-0,4 кВ КТП-72-10 Л-2") == "PLI"
    assert classify_connection_family("невідомий опис") == "UNKNOWN"
    assert normalize_review_pattern("ПЛ-10 кВ 201-37 Чишки") == normalize_review_pattern("ПЛ-6 кВ 201-42 Чишки")


def test_daily_pipeline_includes_quality_hook():
    text = Path("scripts/update_grid_data.py").read_text(encoding="utf-8")
    assert "analyze_quality" in text
    assert "fetch_quality_records" in text
    assert "render_console_report" in text
