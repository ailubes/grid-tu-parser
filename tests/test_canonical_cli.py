from types import SimpleNamespace

from grid_tu_parser.quality import analyze_quality, render_console_report
from scripts.update_grid_data import render_canonical_report


def test_render_canonical_report_has_stable_acceptance_fields():
    summary = SimpleNamespace(
        run_id=7,
        canonical_count=7400,
        ambiguous_count=300,
        metadata_collapsed_count=200,
        unassigned_ambiguous_count=20,
        ambiguous_capacity_min_mw=12.5,
        ambiguous_capacity_max_mw=18.0,
    )
    text = render_canonical_report(summary)
    assert text == (
        "CANONICAL run_id=7 canonical=7400 ambiguous=300 "
        "metadata_collapsed=200 ambiguous_min_mw=12.5 "
        "ambiguous_max_mw=18 unassigned_ambiguous=20"
    )


def test_console_report_accepts_v2_label():
    report = analyze_quality([])
    text = render_console_report(report, label="QUALITY_V2")
    assert text.splitlines()[0].startswith("QUALITY_V2 total=0")


def test_unknown_ambiguous_range_is_not_rendered_as_zero():
    summary = SimpleNamespace(
        run_id=8,
        canonical_count=1,
        ambiguous_count=1,
        metadata_collapsed_count=0,
        unassigned_ambiguous_count=1,
        ambiguous_capacity_min_mw=None,
        ambiguous_capacity_max_mw=None,
    )
    text = render_canonical_report(summary)
    assert "ambiguous_min_mw=unknown" in text
    assert "ambiguous_max_mw=unknown" in text
