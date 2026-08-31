from grid_tu_parser.aggregate import NodeAggregate, apply_ambiguity
from grid_tu_parser.canonical import AmbiguityAnalysis, AmbiguityBucket


def test_apply_ambiguity_does_not_change_canonical_capacity():
    node = NodeAggregate(canonical_node_id="PS-201-CHYSHKY", generation_mw=1.0)
    analysis = AmbiguityAnalysis(
        by_node={
            "PS-201-CHYSHKY": AmbiguityBucket(
                canonical_node_id="PS-201-CHYSHKY",
                ambiguous_tu_count=1,
                capacity_min_mw=1.5,
                capacity_max_mw=2.0,
            )
        },
        unassigned=AmbiguityBucket(None, 0, 0.0, 0.0),
        node_evidence_records=[],
    )
    result = apply_ambiguity([node], analysis)
    assert result[0].generation_mw == 1.0
    assert result[0].ambiguous_tu_count == 1
    assert result[0].ambiguous_capacity_min_mw == 1.5
    assert result[0].ambiguous_capacity_max_mw == 2.0


def test_apply_ambiguity_creates_uncertainty_only_node():
    analysis = AmbiguityAnalysis(
        by_node={"PS-144-STRADCH": AmbiguityBucket("PS-144-STRADCH", 1, 0.5, 0.8)},
        unassigned=AmbiguityBucket(None, 0, 0.0, 0.0),
        node_evidence_records=[],
    )
    result = apply_ambiguity([], analysis)
    assert len(result) == 1
    assert result[0].generation_mw == 0.0
    assert result[0].ambiguous_capacity_min_mw == 0.5
