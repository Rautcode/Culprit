"""LLM Explanation Layer tests (build step 7).

Every test drives the real explainer with a ScriptedModel — the guardrail
contract (grounding, candidate validation, calibration bounds, graceful
degradation, cost short-circuit) is pinned deterministically in CI with no
network access. The AnthropicModel client satisfies the same one-method
protocol and slots in at deploy time.
"""
import json

from ai_reasoning.explain import explain
from ai_reasoning.model import ScriptedModel
from correlation_engine.harness.scenarios import get
from correlation_engine.pipeline import RCAResult, run_scenario
from correlation_engine.ranking.confidence import LLM_ADJUSTMENT_BOUND, W_LLM


def _scripted(top_id: str, calibration: float, citations: list[str]) -> ScriptedModel:
    return ScriptedModel(json.dumps({
        "explanation": "The pool-size reduction directly precedes the exhaustion alert.",
        "top_candidate_id": top_id,
        "calibration": calibration,
        "citations": citations,
    }))


def test_valid_explanation_applies_bounded_calibration():
    result = run_scenario(get("pool_exhaustion"))
    top = result.top_candidate
    model = _scripted(top.deploy_id, 0.5, ["time_proximity", top.deploy_id])

    explanation = explain(result, model)

    assert explanation.grounded
    assert explanation.narrative.startswith("The pool-size reduction")
    assert explanation.citations == ("time_proximity", top.deploy_id)
    # calibration 0.5 -> adjustment W_LLM * 0.5 = 0.1, under the 0.15 cap
    expected = top.confidence.composite + W_LLM * 0.5
    assert abs(explanation.confidence.composite - expected) < 1e-9
    # The prompt carried the real candidates, not a summary the model made up.
    system, prompt = model.calls[0]
    assert top.deploy_id in prompt and "valid_refs" in prompt


def test_calibration_effect_is_capped_at_bound():
    result = run_scenario(get("pool_exhaustion"))
    top = result.top_candidate
    explanation = explain(result, _scripted(top.deploy_id, 1.0, []))

    # W_LLM * 1.0 = 0.2 would exceed the frozen +/-0.15 bound — must clamp.
    assert abs(explanation.confidence.composite - top.confidence.composite - LLM_ADJUSTMENT_BOUND) < 1e-9


def test_hallucinated_citation_is_stripped_and_calibration_zeroed():
    result = run_scenario(get("pool_exhaustion"))
    top = result.top_candidate
    model = _scripted(top.deploy_id, 0.9, ["time_proximity", "log-line-that-does-not-exist"])

    explanation = explain(result, model)

    assert explanation.stripped_citations == ("log-line-that-does-not-exist",)
    assert explanation.citations == ("time_proximity",)
    assert not explanation.grounded
    assert explanation.calibration == 0.0
    assert explanation.confidence.composite == top.confidence.composite  # no boost from ungrounded output


def test_invented_candidate_is_overridden_to_deterministic_top():
    result = run_scenario(get("pool_exhaustion"))
    explanation = explain(result, _scripted("deploy-invented-by-llm", 0.8, []))

    assert explanation.top_candidate_id == result.top_candidate.deploy_id
    assert explanation.calibration == 0.0
    assert not explanation.grounded


def test_malformed_output_degrades_to_deterministic_answer():
    result = run_scenario(get("pool_exhaustion"))
    explanation = explain(result, ScriptedModel("I believe the root cause is probably the deploy."))

    assert not explanation.grounded
    assert explanation.top_candidate_id == result.top_candidate.deploy_id
    assert explanation.confidence.composite == result.top_candidate.confidence.composite
    assert "Deterministic analysis ranks" in explanation.narrative


def test_no_candidates_short_circuits_without_model_call():
    model = _scripted("anything", 0.0, [])
    assert explain(RCAResult(candidates=(), timeline=()), model) is None
    assert model.calls == []


class _RaisingModel:
    """A model whose API call fails — network down, rate limit, expired key
    that passed the env check. The contract is that this degrades, not crashes."""
    def complete(self, system: str, prompt: str) -> str:
        raise RuntimeError("connection reset by peer")


def test_model_call_failure_degrades_to_deterministic_fallback():
    result = run_scenario(get("pool_exhaustion"))
    explanation = explain(result, _RaisingModel())          # must not raise
    assert explanation is not None
    assert not explanation.grounded
    assert explanation.top_candidate_id == result.top_candidate.deploy_id
    assert explanation.confidence.composite == result.top_candidate.confidence.composite
    assert "model call failed" in explanation.narrative
