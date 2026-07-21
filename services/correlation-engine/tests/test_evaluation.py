"""Golden-set evaluation tests — the SPEC's v1.0 Evaluation Metrics gates.

Exact per-rule numbers shift as the catalog evolves; what's pinned here is
what the spec froze: composite precision@1 = 100% on the golden set, the
per-layer gate (warm composite >= rule-only baseline), and that every
frozen rule is individually measured.
"""
from correlation_engine.cli import main
from correlation_engine.evaluation import evaluate, format_report
from correlation_engine.ranking.rules import RULE_NAMES


def test_spec_gates_hold():
    metrics = evaluate()
    assert metrics["golden_set_size"] >= 18
    assert metrics["cold"]["p1"] == 1.0          # precision@1 gate
    assert metrics["warm"]["p1"] == 1.0
    assert metrics["warm"]["p1"] >= metrics["rule_only_baseline_p1"]  # RAG adds no noise
    assert set(metrics["per_rule_p1"]) == set(RULE_NAMES)
    assert all(0.0 <= p1 <= 1.0 for p1 in metrics["per_rule_p1"].values())


def test_report_is_honest_about_authored_bias():
    metrics = evaluate()
    report = format_report(metrics)
    assert "precision@1" in report and "RAG" in report
    best_p1 = max(metrics["per_rule_p1"].values())
    if best_p1 >= metrics["warm"]["p1"]:
        assert "Authored-data bias" in report   # the finding must be surfaced, not hidden


def test_eval_cli_exit_code_is_the_gate(capsys):
    assert main(["eval"]) == 0
    assert "Golden-set evaluation" in capsys.readouterr().out
