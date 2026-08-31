import importlib.util
from pathlib import Path
from types import SimpleNamespace


def load_update_script():
    path = Path(__file__).parents[1] / "scripts" / "update_grid_data.py"
    spec = importlib.util.spec_from_file_location("update_grid_data", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_integrity_report_has_stable_summary_and_collision_lines():
    module = load_update_script()
    summary = SimpleNamespace(
        observation_count=8285,
        integrity_audit={
            "fetched_rows": 8285,
            "unique_row_versions": 8015,
            "unique_logical_tus": 7900,
            "legacy_unique_records": 8011,
            "legacy_collision_loss": 274,
            "duplicate_observations": 270,
            "logical_tus_with_multiple_versions": 4,
            "top_legacy_collision_groups": [
                {
                    "observation_count": 3,
                    "distinct_row_versions": 2,
                    "tu_numbers": ["ТУ 123"],
                    "differing_fields": ["contract_date"],
                }
            ],
        },
    )
    output = module.render_integrity_report(summary)
    assert "INTEGRITY fetched=8285 observations=8285" in output
    assert "legacy_unique=8011 legacy_loss=274" in output
    assert "LEGACY COLLISIONS" in output
    assert "ТУ 123: observations=3 versions=2 differs=contract_date" in output
