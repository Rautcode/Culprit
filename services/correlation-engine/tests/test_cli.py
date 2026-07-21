"""Phase 0 CLI tests — the validation artifact must not rot.

demo is exercised against a real scenario (verdict must be correct and the
confidence breakdown printed); diagnose is exercised end to end from
files on disk shaped like what a design partner would actually export
(`kubectl get events -o json`, a simple deploys list, an edges list).
"""
import json

import pytest

from correlation_engine.cli import main


def test_demo_lists_scenarios(capsys):
    assert main(["demo", "list"]) == 0
    out = capsys.readouterr().out
    assert "pool_exhaustion" in out and "broken_scraping" in out


def test_demo_runs_pipeline_and_verdict_is_correct(capsys):
    assert main(["demo", "deadlock"]) == 0
    out = capsys.readouterr().out
    assert "deploy-dead10" in out                      # the true culprit ranks
    assert "pipeline verdict is correct" in out
    assert "confidence" in out and "TIMELINE" in out


def test_demo_surfaces_precedent_when_memory_has_one(capsys):
    # broken_scraping and missing_metrics genuinely share scrape/target
    # vocabulary, so leave-one-out retrieval fires — deadlock deliberately
    # has none (its isolation is itself asserted in test_memory.py).
    assert main(["demo", "broken_scraping"]) == 0
    out = capsys.readouterr().out
    assert "precedent: missing_metrics" in out


def test_demo_unknown_scenario_fails_cleanly(capsys):
    assert main(["demo", "nope"]) == 2


def test_diagnose_from_partner_shaped_files(tmp_path, capsys):
    (tmp_path / "deploys.json").write_text(json.dumps([
        {"service": "checkout-service", "occurred_at": "2026-07-21T14:00:00Z",
         "summary": "bump logging library version", "sha": "aaa111", "deployed_by": "alice"},
        {"service": "checkout-service", "occurred_at": "2026-07-21T14:31:00Z",
         "summary": "reduce db.connectionPoolSize 50 -> 10", "sha": "bbb222", "deployed_by": "jmartin"},
    ]), encoding="utf-8")
    # kubectl get events -o json shape: a List with .items
    (tmp_path / "events.json").write_text(json.dumps({"items": [{
        "metadata": {"namespace": "prod"},
        "involvedObject": {"name": "checkout-service-abc", "namespace": "prod"},
        "reason": "PoolExhausted",
        "message": "connection pool exhausted",
        "lastTimestamp": "2026-07-21T14:32:30Z",
    }]}), encoding="utf-8")
    (tmp_path / "edges.json").write_text(json.dumps([
        {"from": "web-frontend", "to": "checkout-service"},
    ]), encoding="utf-8")

    assert main([
        "diagnose",
        "--alert-title", "DB connection pool exhausted",
        "--alert-service", "checkout-service",
        "--fired-at", "2026-07-21T14:32:30Z",
        "--deploys-file", str(tmp_path / "deploys.json"),
        "--events-file", str(tmp_path / "events.json"),
        "--edges-file", str(tmp_path / "edges.json"),
    ]) == 0

    out = capsys.readouterr().out
    # The pool-size deploy must rank first, with cited keyword evidence.
    first_candidate = out.split("#1")[1].split("#2")[0]
    assert "bbb222" in first_candidate
    assert "diff_keyword_match" in first_candidate
    assert "PoolExhausted" in out                      # k8s events made the timeline


def test_diagnose_missing_field_fails_cleanly(tmp_path):
    (tmp_path / "deploys.json").write_text(
        json.dumps([{"occurred_at": "2026-07-22T09:00:00Z"}]), encoding="utf-8")  # no 'service'
    with pytest.raises(SystemExit) as exc:
        main(["diagnose", "--alert-title", "x", "--alert-service", "checkout-service",
              "--fired-at", "2026-07-22T09:00:00Z", "--deploys-file", str(tmp_path / "deploys.json")])
    assert "input error" in str(exc.value) and "service" in str(exc.value)


def test_diagnose_bad_timestamp_fails_cleanly(tmp_path):
    (tmp_path / "deploys.json").write_text(
        json.dumps([{"service": "checkout-service", "occurred_at": "not-a-date"}]), encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        main(["diagnose", "--alert-title", "x", "--alert-service", "checkout-service",
              "--fired-at", "2026-07-22T09:00:00Z", "--deploys-file", str(tmp_path / "deploys.json")])
    assert "ISO-8601" in str(exc.value)


def test_diagnose_missing_file_fails_cleanly():
    with pytest.raises(SystemExit) as exc:
        main(["diagnose", "--alert-title", "x", "--alert-service", "s",
              "--fired-at", "2026-07-22T09:00:00Z", "--deploys-file", "/no/such/file.json"])
    assert "file not found" in str(exc.value)


def test_diagnose_malformed_events_file_fails_cleanly(tmp_path):
    (tmp_path / "deploys.json").write_text(
        json.dumps([{"service": "checkout-service", "occurred_at": "2026-07-22T09:31:00Z"}]),
        encoding="utf-8")
    (tmp_path / "events.json").write_text(json.dumps({"foo": "bar"}), encoding="utf-8")  # no items, wrong shape
    with pytest.raises(SystemExit) as exc:
        main(["diagnose", "--alert-title", "x", "--alert-service", "checkout-service",
              "--fired-at", "2026-07-22T09:32:00Z",
              "--deploys-file", str(tmp_path / "deploys.json"),
              "--events-file", str(tmp_path / "events.json")])
    assert "input error" in str(exc.value) and "Event objects" in str(exc.value)
