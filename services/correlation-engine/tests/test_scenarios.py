"""The regression suite the Incident Simulation Harness exists to run.

This is the "walking skeleton" check: one incident flowing through the
complete deterministic pipeline (Evidence -> Knowledge Graph -> Rule Engine
-> Confidence -> Timeline) with output verified against a hand-authored
ground truth. No AI involved — see SPEC_VERSION.md "v1.0 Build Sequence"
step 1 and docs/07-ai-architecture.md.
"""
from correlation_engine.harness.scenarios import ALL_SCENARIOS, get
from correlation_engine.pipeline import run_scenario


def test_pool_exhaustion_end_to_end():
    scenario = get("pool_exhaustion")
    result = run_scenario(scenario)

    assert result.top_candidate is not None, "pipeline produced no candidates"

    top = result.top_candidate
    assert top.deploy_id == scenario.expected_root_cause, (
        f"expected root cause {scenario.expected_root_cause}, got {top.deploy_id}"
    )
    assert top.confidence.composite >= scenario.expected_confidence_min, (
        f"confidence {top.confidence.composite:.3f} below floor {scenario.expected_confidence_min}"
    )
    assert set(scenario.expected_rule_hits) == set(top.rule_hits), (
        f"expected rule hits {scenario.expected_rule_hits}, got {top.rule_hits}"
    )
    for key in scenario.expected_evidence_keys:
        assert key in top.evidence, f"expected evidence citation for rule '{key}', found none"

    # The decoy must rank below the real cause, not just "the real cause is present somewhere."
    assert result.candidates[0].deploy_id != result.candidates[-1].deploy_id
    assert result.candidates[0].confidence.composite > result.candidates[-1].confidence.composite

    timeline_refs = [event["ref"] for event in result.timeline]
    for ref in scenario.expected_timeline_refs:
        assert ref in timeline_refs, f"expected timeline ref {ref} missing from {timeline_refs}"

    occurred_ats = [event["occurred_at"] for event in result.timeline]
    assert occurred_ats == sorted(occurred_ats), "timeline is not chronologically ordered"


def test_all_registered_scenarios_pass():
    """Every scenario added to the harness must resolve correctly — this is
    the regression gate for any future rule/weight change."""
    assert ALL_SCENARIOS, "no scenarios registered"
    for scenario in ALL_SCENARIOS:
        result = run_scenario(scenario)
        assert result.top_candidate is not None, f"{scenario.id}: no candidates"
        assert result.top_candidate.deploy_id == scenario.expected_root_cause, (
            f"{scenario.id}: expected {scenario.expected_root_cause}, "
            f"got {result.top_candidate.deploy_id}"
        )
