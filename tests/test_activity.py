from grid_tu_parser.activity import normalize_activity


def test_bess_activity():
    assert normalize_activity("УЗЕ") == "bess"
    assert normalize_activity("установка зберігання енергії") == "bess"


def test_generation_and_consumption_activity():
    assert normalize_activity("виробництво електричної енергії") == "generation"
    assert normalize_activity("споживання") == "consumption"


def test_mixed_activity():
    assert normalize_activity("генерація та споживання") == "mixed"


def test_unknown_activity():
    assert normalize_activity("інше") == "unknown"
