"""The regression suite the Incident Simulation Harness exists to run.

Every registered scenario flows through the complete deterministic pipeline
(Evidence -> Knowledge Graph -> Rule Engine -> Confidence -> Timeline) and
is verified against its full hand-authored expectation set. No AI involved —
see SPEC_VERSION.md "v1.0 Build Sequence" step 1 and docs/07-ai-architecture.md.
"""
import pytest

from correlation_engine.harness.schema import Scenario
from correlation_engine.harness.scenarios import ALL_SCENARIOS
from correlation_engine.pipeline import RCAResult, run_scenario


def assert_scenario_expectations(scenario: Scenario, result: RCAResult) -> None:
    assert result.top_candidate is not None, f"{scenario.id}: pipeline produced no candidates"

    top = result.top_candidate
    assert top.deploy_id == scenario.expected_root_cause, (
        f"{scenario.id}: expected root cause {scenario.expected_root_cause}, got {top.deploy_id}"
    )
    assert top.confidence.composite >= scenario.expected_confidence_min, (
        f"{scenario.id}: confidence {top.confidence.composite:.3f} "
        f"below floor {scenario.expected_confidence_min}"
    )
    assert set(scenario.expected_rule_hits) == set(top.rule_hits), (
        f"{scenario.id}: expected rule hits {scenario.expected_rule_hits}, got {top.rule_hits}"
    )
    for key in scenario.expected_evidence_keys:
        assert key in top.evidence, (
            f"{scenario.id}: expected evidence citation for rule '{key}', found none"
        )

    # Every decoy must rank strictly below the real cause — a tie means the
    # ranking can't actually distinguish culprit from noise.
    for decoy in result.candidates[1:]:
        assert decoy.confidence.composite < top.confidence.composite, (
            f"{scenario.id}: decoy {decoy.deploy_id} ties or beats the culprit "
            f"({decoy.confidence.composite:.3f} vs {top.confidence.composite:.3f})"
        )

    timeline_refs = [event["ref"] for event in result.timeline]
    for ref in scenario.expected_timeline_refs:
        assert ref in timeline_refs, (
            f"{scenario.id}: expected timeline ref {ref} missing from {timeline_refs}"
        )

    occurred_ats = [event["occurred_at"] for event in result.timeline]
    assert occurred_ats == sorted(occurred_ats), f"{scenario.id}: timeline is not chronologically ordered"


def test_scenarios_registered():
    assert ALL_SCENARIOS, "no scenarios registered"


@pytest.mark.parametrize("scenario", ALL_SCENARIOS, ids=lambda s: s.id)
def test_scenario_end_to_end(scenario: Scenario):
    result = run_scenario(scenario)
    assert_scenario_expectations(scenario, result)
