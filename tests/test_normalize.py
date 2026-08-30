from grid_tu_parser.normalize import normalize_text, slugify_ua


def test_normalize_text_unifies_spacing_dash_number_and_decimal_comma():
    value = " РУ–10  кВ   ПС 35/10 кВ N 144  Страдч  "
    assert normalize_text(value) == "РУ-10 кВ ПС 35/10 кВ №144 Страдч"


def test_normalize_text_decimal_comma_to_dot():
    assert normalize_text("ПЛ-0,4 кВ") == "ПЛ-0.4 кВ"


def test_slugify_ua_is_deterministic_ascii():
    assert slugify_ua("Львів-10") == "LVIV-10"
    assert slugify_ua("Страдч") == "STRADCH"
