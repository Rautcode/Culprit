"""Golden-set evaluation — the v1.0 Evaluation Metrics (SPEC_VERSION.md).

The regression suite gates pass/fail; this module produces the NUMBERS the
spec names, so layer and rule contributions are measured, not assumed:

  * precision@1 / precision@3, cold (no memory) and warm (leave-one-out
    memory — precedent only ever comes from OTHER incidents).
  * The per-layer gate: warm composite precision@1 must be >= the
    rule-only baseline, or the RAG layer is adding noise, not signal.
    (Cold composite IS the rule-only baseline: with rag and llm at zero
    the composite is monotone in rule_score.)
  * Per-rule precision@1: each rule ranking candidates ALONE, warm.
    Ties count as misses — a rule that can't discriminate gets no credit.
    This is the signal that feeds weight tuning (docs/07 § Evaluation);
    historical_pattern_match scoring low here is expected, not a bug: it
    only fires when a genuine cross-incident precedent exists.

Run via `culprit eval`; CI prints the report into the run summary.
"""
from __future__ import annotations

from .harness.scenarios import ALL_SCENARIOS
from .harness.schema import Scenario
from .knowledge_graph import KnowledgeGraph
from .memory import IncidentMemory
from .pipeline import run_scenario
from .ranking.rules import RULES


def _loo_memory(scenario: Scenario) -> IncidentMemory:
    memory = IncidentMemory()
    for other in ALL_SCENARIOS:
        if other.id != scenario.id:
            memory.learn_from_scenario(other)
    return memory


def _precision(hits: int, total: int) -> float:
    return hits / total if total else 0.0


def _single_rule_top(scenario: Scenario, rule, memory: IncidentMemory) -> str | None:
    """The deploy a single rule would rank first (mean over alerts, same
    aggregation as the pipeline) — None on a tie for first."""
    graph = KnowledgeGraph.from_edges(scenario.evidence.service_edges)
    scores: dict[str, float] = {}
    for deploy in scenario.evidence.deploys:
        total = sum(
            rule.evaluate(alert, deploy, scenario.evidence, graph, memory)[0]
            for alert in scenario.evidence.alerts
        )
        scores[deploy.id] = total / len(scenario.evidence.alerts)
    best = max(scores.values())
    leaders = [deploy_id for deploy_id, score in scores.items() if score == best]
    return leaders[0] if len(leaders) == 1 else None


def evaluate() -> dict:
    total = len(ALL_SCENARIOS)
    cold_p1 = cold_p3 = warm_p1 = warm_p3 = 0
    rule_hits = {rule.name: 0 for rule in RULES}

    for scenario in ALL_SCENARIOS:
        truth = scenario.ground_truth.root_cause_deploy_id

        cold = run_scenario(scenario)
        cold_ranked = [c.deploy_id for c in cold.candidates]
        cold_p1 += cold_ranked[:1] == [truth]
        cold_p3 += truth in cold_ranked[:3]

        memory = _loo_memory(scenario)
        warm = run_scenario(scenario, memory)
        warm_ranked = [c.deploy_id for c in warm.candidates]
        warm_p1 += warm_ranked[:1] == [truth]
        warm_p3 += truth in warm_ranked[:3]

        for rule in RULES:
            rule_hits[rule.name] += _single_rule_top(scenario, rule, memory) == truth

    return {
        "golden_set_size": total,
        "cold": {"p1": _precision(cold_p1, total), "p3": _precision(cold_p3, total)},
        "warm": {"p1": _precision(warm_p1, total), "p3": _precision(warm_p3, total)},
        "rule_only_baseline_p1": _precision(cold_p1, total),
        "per_rule_p1": {name: _precision(hits, total) for name, hits in rule_hits.items()},
    }


def format_report(metrics: dict) -> str:
    lines = [
        "## Golden-set evaluation (SPEC_VERSION.md § v1.0 Evaluation Metrics)",
        "",
        f"Golden set: {metrics['golden_set_size']} ground-truthed incidents "
        "(simulated — real-incident numbers are a Phase 1 exit criterion).",
        "",
        "| metric | precision@1 | precision@3 |",
        "|---|---|---|",
        f"| composite, cold (= rule-only baseline) | {metrics['cold']['p1']:.0%} | {metrics['cold']['p3']:.0%} |",
        f"| composite, warm (leave-one-out memory) | {metrics['warm']['p1']:.0%} | {metrics['warm']['p3']:.0%} |",
        "",
        "Per-layer gate: warm composite p@1 "
        f"{'>=' if metrics['warm']['p1'] >= metrics['rule_only_baseline_p1'] else '< FAILING'} "
        "rule-only baseline — "
        + ("RAG adds no noise." if metrics['warm']['p1'] >= metrics['rule_only_baseline_p1']
           else "RAG IS ADDING NOISE."),
        "",
        "| rule (ranking alone, warm; ties = miss) | precision@1 |",
        "|---|---|",
    ]
    for name, p1 in sorted(metrics["per_rule_p1"].items(), key=lambda kv: -kv[1]):
        lines.append(f"| {name} | {p1:.0%} |")

    best_rule, best_p1 = max(metrics["per_rule_p1"].items(), key=lambda kv: kv[1])
    if best_p1 >= metrics["warm"]["p1"]:
        lines += [
            "",
            f"⚠ Authored-data bias: `{best_rule}` ALONE matches the composite on "
            "this simulated set — the hand-built scenarios discriminate too "
            "cleanly on that signal. Real incidents are messier; this is why "
            "real-incident precision is a Phase 1 exit criterion and why the "
            "golden set must grow from usage disagreements, not more authoring.",
        ]
    else:
        lines += [
            "",
            f"No single rule matches the composite (best alone: {best_rule} at "
            f"{best_p1:.0%}) — the weighted combination is the product.",
        ]
    return "\n".join(lines)
