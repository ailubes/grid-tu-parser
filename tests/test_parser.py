from datetime import datetime, timezone

from grid_tu_parser.models import RawTURecord
from grid_tu_parser.parser import parse_connection_point, parse_record


def test_ru_ps_stradch():
    result = parse_connection_point("РУ-10 кВ ПС 35/10 кВ №144 Страдч")
    assert result["connection_object_type"] == "RU"
    assert result["connection_voltage_kv"] == 10.0
    assert result["parent_object_type"] == "PS"
    assert result["parent_number"] == "144"
    assert result["parent_name"] == "Страдч"
    assert result["parent_voltage_levels_kv"] == [35.0, 10.0]
    assert result["canonical_node_id"] == "PS-144-STRADCH"
    assert result["confidence"] == 1.0
    assert result["needs_review"] is False


def test_ru_ps_lviv_10():
    result = parse_connection_point("РУ-6 кВ ПС 110/10/6 кВ №249 Львів-10")
    assert result["canonical_node_id"] == "PS-249-LVIV-10"
    assert result["parent_voltage_levels_kv"] == [110.0, 10.0, 6.0]
    assert result["connection_voltage_kv"] == 6.0


def test_pl_ktp_feeder():
    result = parse_connection_point("ПЛ-0,4 кВ КТП-208-11 Л-2")
    assert result["connection_object_type"] == "PL"
    assert result["connection_voltage_kv"] == 0.4
    assert result["parent_object_type"] == "KTP"
    assert result["parent_number"] == "208-11"
    assert result["feeder_id"] == "L-2"
    assert result["canonical_node_id"] == "KTP-208-11"


def test_textual_variants_share_canonical_id():
    a = parse_connection_point("ПС 35/10 кВ №144 Страдч")
    b = parse_connection_point("ПС №144 Страдч")
    assert a["canonical_node_id"] == b["canonical_node_id"] == "PS-144-STRADCH"


def test_missing_number_name_only_at_threshold_is_not_review():
    result = parse_connection_point("ПС 35/10 кВ Страдч")
    assert result["parent_object_type"] == "PS"
    assert result["parent_name"] == "Страдч"
    assert result["confidence"] == 0.75
    assert result["needs_review"] is False
    assert "missing_parent_identifier" in result["flags"]
    assert result["canonical_node_id"] == "PS-STRADCH"


def test_two_parent_candidates_needs_review():
    result = parse_connection_point("ПС №144 Страдч КТП-208-11")
    assert result["needs_review"] is True
    assert result["confidence"] <= 0.60
    assert "multiple_parent_candidates" in result["flags"]


def test_ztp_and_tp_variants():
    ztp = parse_connection_point("ЗТП-17 10/0,4 кВ")
    tp = parse_connection_point("ТП №55")
    assert ztp["parent_object_type"] == "ZTP"
    assert ztp["parent_number"] == "17"
    assert ztp["canonical_node_id"] == "ZTP-17"
    assert tp["parent_object_type"] == "TP"
    assert tp["parent_number"] == "55"
    assert tp["canonical_node_id"] == "TP-55"


def test_malformed_spacing_and_number_sign():
    result = parse_connection_point("  РУ–10 кВ   ПС 35/10 кВ N 144   Страдч ")
    assert result["canonical_node_id"] == "PS-144-STRADCH"
    assert result["connection_voltage_kv"] == 10.0


def test_unknown_text_needs_review():
    result = parse_connection_point("точка приєднання біля дороги")
    assert result["canonical_node_id"] is None
    assert result["needs_review"] is True
    assert result["confidence"] == 0.0
    assert "unknown_object_type" in result["flags"]


def test_parse_record_preserves_raw_and_normalizes_activity():
    raw = RawTURecord(source="lvivoblenergo", source_url="https://example.test", source_page=1, fetched_at=datetime(2026, 8, 30, tzinfo=timezone.utc), tu_number="002055", tu_date="2026-05-28", installation_type="УЗЕ", connection_point_raw="РУ-10 кВ ПС 35/10 кВ №144 Страдч", requested_power_kw=3000.0)
    parsed = parse_record(raw)
    assert parsed.activity_type == "bess"
    assert parsed.canonical_node_id == "PS-144-STRADCH"
    assert parsed.connection_point_raw == raw.connection_point_raw
    assert parsed.requested_power_kw == 3000.0


def test_live_lviv_variant_pli_normalizes_to_pl():
    result = parse_connection_point("ПЛІ-0,4 кВ КТП-72-10 Л-2")
    assert result["connection_object_type"] == "PL"
    assert result["connection_voltage_kv"] == 0.4
    assert result["canonical_node_id"] == "KTP-72-10"


def test_live_lviv_variant_compound_ztp_identifier_omits_address_from_id():
    result = parse_connection_point("КЛ-0,4 кВ ЗТП-2258-КВ-19788 вул. Щирецька, 30/І")
    assert result["parent_object_type"] == "ZTP"
    assert result["parent_number"] == "2258-КВ-19788"
    assert result["canonical_node_id"] == "ZTP-2258-KV-19788"


def test_live_lviv_transformer_variants_normalize_to_base_types():
    ktpp = parse_connection_point("ПЛ-0,4 кВ КТПП-1140-22 Л-1 с.Ріпчичі 12")
    sktp = parse_connection_point("СКТП-572-09 Зимна Вода")
    schtp = parse_connection_point("ПЛ-0,4 кВ ЩТП-37-42 Л-4 с.Горбків")
    assert ktpp["parent_object_type"] == "KTP"
    assert ktpp["canonical_node_id"] == "KTP-1140-22"
    assert sktp["parent_object_type"] == "KTP"
    assert sktp["canonical_node_id"] == "KTP-572-09"
    assert schtp["parent_object_type"] == "TP"
    assert schtp["canonical_node_id"] == "TP-37-42"


def test_low_voltage_node_address_does_not_change_canonical_id():
    a = parse_connection_point("РУ-0,4 кВ ЗТП-233-30 м.Моршин")
    b = parse_connection_point("ЗТП-233-30")
    assert a["canonical_node_id"] == b["canonical_node_id"] == "ZTP-233-30"


def test_parse_record_flags_conflicting_voltage_context():
    raw = RawTURecord(source="lvivoblenergo", source_url="https://example.test", source_page=1, fetched_at=datetime(2026, 8, 30, tzinfo=timezone.utc), tu_number="ТУ conflict", tu_date="2026-06-03", installation_type="споживання", connection_point_raw="РУ-35 кВ ПС 110/35/10 кВ №136 Перемишляни", voltage_raw="10", requested_power_kw=150.0)
    parsed = parse_record(raw)
    assert "conflicting_voltage_context" in parsed.flags
    assert parsed.needs_review is True
    assert parsed.confidence <= 0.60


def test_parse_record_converts_parser_exception_to_review_record():
    class BadText:
        def __str__(self):
            raise ValueError("broken source text")
    raw = RawTURecord(source="lvivoblenergo", source_url="https://example.test", source_page=1, fetched_at=datetime(2026, 8, 30, tzinfo=timezone.utc), tu_number="ТУ bad", tu_date="2026-06-03", installation_type="споживання", connection_point_raw=BadText())
    parsed = parse_record(raw)
    assert parsed.needs_review is True
    assert parsed.confidence == 0.0
    assert parsed.flags == ["parse_error"]
    assert "broken source text" in parsed.parse_error
