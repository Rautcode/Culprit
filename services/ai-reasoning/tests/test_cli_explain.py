"""`culprit diagnose --explain` wiring tests.

Lives in the ai-reasoning suite because that's where conftest puts BOTH
packages on the path — the correlation-engine-only suite deliberately
can't import ai_reasoning, which is the exact reason the CLI's import is
lazy. A ScriptedModel is injected by monkeypatching the model seam, so the
full explain path runs in CI with no ANTHROPIC_API_KEY.
"""
import json

import pytest

from correlation_engine import cli
from correlation_engine.cli import main
from ai_reasoning.model import ScriptedModel


@pytest.fixture
def deploys_file(tmp_path):
    path = tmp_path / "deploys.json"
    path.write_text(json.dumps([
        {"service": "checkout-service", "occurred_at": "2026-07-22T09:00:00Z",
         "summary": "bump logging library version", "sha": "aaa111"},
        {"service": "checkout-service", "occurred_at": "2026-07-22T09:31:00Z",
         "summary": "reduce db.connectionPoolSize 50 -> 10", "sha": "bbb222"},
    ]), encoding="utf-8")
    return str(path)


def _diagnose(deploys_file, extra):
    return main([
        "diagnose",
        "--alert-title", "DB connection pool exhausted",
        "--alert-service", "checkout-service",
        "--fired-at", "2026-07-22T09:32:30Z",
        "--deploys-file", deploys_file,
        *extra,
    ])


def _inject(monkeypatch, response: str):
    monkeypatch.setattr(cli, "_default_explainer_model", lambda: ScriptedModel(response))


def test_explain_prints_grounded_narrative(monkeypatch, deploys_file, capsys):
    _inject(monkeypatch, json.dumps({
        "explanation": "The connection-pool reduction immediately precedes the exhaustion alert.",
        "top_candidate_id": "bbb222",
        "calibration": 0.4,
        "citations": ["time_proximity", "diff_keyword_match", "bbb222"],
    }))
    assert _diagnose(deploys_file, ["--explain"]) == 0
    out = capsys.readouterr().out
    assert "AI EXPLANATION" in out
    assert "immediately precedes" in out
    assert "cited evidence:" in out
    assert "LLM adjustment" in out
    assert "NOT boosted" not in out            # grounded → boosted


def test_explain_strips_hallucinated_citation_and_flags_it(monkeypatch, deploys_file, capsys):
    _inject(monkeypatch, json.dumps({
        "explanation": "Pool size dropped.",
        "top_candidate_id": "bbb222",
        "calibration": 0.9,
        "citations": ["time_proximity", "a-log-line-that-does-not-exist"],
    }))
    assert _diagnose(deploys_file, ["--explain"]) == 0
    out = capsys.readouterr().out
    assert "guardrail stripped ungrounded citations: a-log-line-that-does-not-exist" in out
    assert "NOT boosted" in out                # ungrounded → confidence not boosted


def test_no_explain_flag_leaves_output_untouched(monkeypatch, deploys_file, capsys):
    # The model seam must never be consulted without --explain.
    monkeypatch.setattr(cli, "_default_explainer_model",
                        lambda: (_ for _ in ()).throw(AssertionError("model built without --explain")))
    assert _diagnose(deploys_file, []) == 0
    assert "AI EXPLANATION" not in capsys.readouterr().out


def test_explain_degrades_when_no_model_available(monkeypatch, deploys_file, capsys):
    # No key / no client → None → deterministic verdict still stands, exit 0.
    monkeypatch.setattr(cli, "_default_explainer_model", lambda: None)
    assert _diagnose(deploys_file, ["--explain"]) == 0
    out = capsys.readouterr().out
    assert "ROOT CAUSE CANDIDATES" in out       # verdict printed
    assert "AI EXPLANATION" not in out          # explanation gracefully skipped
