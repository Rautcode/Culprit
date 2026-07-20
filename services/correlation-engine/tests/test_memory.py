"""RAG Retrieval tests (build step 6).

The headline test is the recurrence story — the product's core compounding
claim: an incident the memory has seen before resolves with HIGHER
confidence than it did cold, with the past incident and its resolution
cited as evidence. The counterpart test proves the guardrail: unrelated
memory must not inflate anything.
"""
from correlation_engine.harness.scenarios import get
from correlation_engine.memory import IncidentMemory, ResolvedIncident, _cosine, _vectorize
from correlation_engine.pipeline import run_scenario


def test_cosine_similarity_bounds():
    assert _cosine(_vectorize("connection pool exhausted"), _vectorize("connection pool exhausted")) == 1.0
    assert _cosine(_vectorize("connection pool exhausted"), _vectorize("dns resolver flapping")) == 0.0


def test_learn_and_retrieve():
    memory = IncidentMemory()
    memory.learn_from_scenario(get("pool_exhaustion"))
    matches = memory.most_similar("DB connection pool exhausted after connectionPoolSize change")
    assert matches, "expected a retrieval hit"
    similarity, incident = matches[0]
    assert incident.incident_id == "pool_exhaustion"
    assert similarity > 0.3
    assert incident.resolution == "helm_rollback:checkout-service:47"


def test_recurrence_resolves_with_higher_confidence_and_cites_precedent():
    scenario = get("pool_exhaustion")

    cold = run_scenario(scenario)
    assert "historical_pattern_match" not in cold.top_candidate.rule_hits

    memory = IncidentMemory()
    memory.learn_from_scenario(scenario)
    warm = run_scenario(scenario, memory)

    assert warm.top_candidate.deploy_id == scenario.expected_root_cause
    assert warm.top_candidate.confidence.composite > cold.top_candidate.confidence.composite, (
        "a recurrence of a known incident must score higher than it did cold"
    )
    assert "historical_pattern_match" in warm.top_candidate.rule_hits
    historical = warm.top_candidate.evidence["historical_pattern_match"]
    assert historical["incident_id"] == "pool_exhaustion"
    assert historical["past_resolution"] == "helm_rollback:checkout-service:47"
    assert warm.top_candidate.evidence["similar_past_incidents"][0]["incident_id"] == "pool_exhaustion"
    assert warm.top_candidate.confidence.rag_score > 0.5

    # The precedent must strengthen the culprit more than the decoy — the
    # decoy shares the alert but not the diff, so its similarity is lower.
    warm_decoy = warm.candidates[-1]
    assert warm.top_candidate.confidence.rag_score > warm_decoy.confidence.rag_score


def test_unrelated_memory_does_not_inflate():
    memory = IncidentMemory()
    memory.learn_from_scenario(get("pool_exhaustion"))

    scenario = get("deadlock")
    cold = run_scenario(scenario)
    warm = run_scenario(scenario, memory)

    assert warm.top_candidate.deploy_id == scenario.expected_root_cause
    assert "historical_pattern_match" not in warm.top_candidate.rule_hits, (
        "a pool-exhaustion precedent must not fire against a deadlock incident"
    )
    assert abs(warm.top_candidate.confidence.composite - cold.top_candidate.confidence.composite) < 0.05


def test_every_scenario_still_resolves_correctly_with_full_memory():
    """The all-scenarios regression, warm: memory seeded with every OTHER
    resolved scenario (leave-one-out, so exact self-matches prove nothing) —
    cross-incident precedent must never flip a ranking."""
    from correlation_engine.harness.scenarios import ALL_SCENARIOS

    for scenario in ALL_SCENARIOS:
        memory = IncidentMemory()
        for other in ALL_SCENARIOS:
            if other.id != scenario.id:
                memory.learn_from_scenario(other)
        result = run_scenario(scenario, memory)
        assert result.top_candidate.deploy_id == scenario.expected_root_cause, (
            f"{scenario.id}: ranking flipped under leave-one-out memory"
        )
