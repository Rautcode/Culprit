"""Postgres backend tests — run against a real database.

Locally these skip unless POSTGRES_DSN is set (no Docker required to run
the rest of the suite); in CI a pgvector/pg16 service container provides
the database, so every push proves the backends against real Postgres.

The headline tests are drop-in equivalence (the same raw-payload
end-to-end flow as test_collection.py, but through PostgresEvidenceStore —
same culprit, same evidence) and durability (a NEW PostgresIncidentMemory
on the same database sees incidents a previous instance learned — the
restart-survival property that is the entire point of persistence).
"""
import os

import pytest

psycopg = pytest.importorskip("psycopg")

from correlation_engine.collection.adapters import (  # noqa: E402
    parse_alertmanager,
    parse_github_deployment,
    parse_k8s_event,
)
from correlation_engine.db.postgres import (  # noqa: E402
    PostgresEvidenceStore,
    PostgresIncidentMemory,
    apply_schema,
)
from correlation_engine.harness.scenarios import get  # noqa: E402
from correlation_engine.harness.schema import ServiceEdge  # noqa: E402
from correlation_engine.knowledge_graph import KnowledgeGraph  # noqa: E402
from correlation_engine.memory import ResolvedIncident  # noqa: E402
from correlation_engine.pipeline import rank_candidates  # noqa: E402
from tests.test_collection import (  # noqa: E402
    ALERTMANAGER_WEBHOOK,
    CULPRIT_DEPLOY_WEBHOOK,
    DECOY_DEPLOY_WEBHOOK,
    K8S_EVENT,
    STALE_DEPLOY_WEBHOOK,
)

DSN = os.environ.get("POSTGRES_DSN")
pytestmark = pytest.mark.skipif(not DSN, reason="POSTGRES_DSN not set — Postgres tests run in CI")


@pytest.fixture
def conn():
    with psycopg.connect(DSN, autocommit=True) as connection:
        apply_schema(connection)
        connection.execute(
            "TRUNCATE deploy_events, alerts, k8s_events, service_edges, services, resolved_incidents"
        )
        yield connection


def _populated_store(conn) -> PostgresEvidenceStore:
    store = PostgresEvidenceStore(conn)
    for webhook in (DECOY_DEPLOY_WEBHOOK, CULPRIT_DEPLOY_WEBHOOK, STALE_DEPLOY_WEBHOOK):
        store.add_deploy(parse_github_deployment(webhook))
    for alert in parse_alertmanager(ALERTMANAGER_WEBHOOK):
        store.add_alert(alert)
    store.add_k8s_event(parse_k8s_event(K8S_EVENT))
    store.add_edge(ServiceEdge("web-frontend", "checkout-service", "depends_on"))
    store.add_edge(ServiceEdge("checkout-service", "payments-service", "depends_on"))
    return store


def test_idempotent_under_webhook_retry(conn):
    store = _populated_store(conn)
    assert store.add_deploy(parse_github_deployment(CULPRIT_DEPLOY_WEBHOOK)) is False
    assert store.add_alert(parse_alertmanager(ALERTMANAGER_WEBHOOK)[0]) is False
    assert store.add_k8s_event(parse_k8s_event(K8S_EVENT)) is False
    assert store.add_edge(ServiceEdge("web-frontend", "checkout-service", "depends_on")) is False
    bundle = store.bundle_for_alerts()
    assert len(bundle.deploys) == 2 and len(bundle.alerts) == 1


def test_raw_payloads_to_rca_through_postgres(conn):
    """Drop-in equivalence with the in-memory store: same raw webhooks,
    same windowing (the 09:00 deploy excluded), same culprit ranked first."""
    store = _populated_store(conn)
    bundle = store.bundle_for_alerts()

    assert {d.id for d in bundle.deploys} == {"gh-2001", "gh-2002"}
    assert bundle.k8s_events and bundle.k8s_events[0].reason == "PoolExhausted"
    assert len(bundle.service_edges) == 2

    candidates = rank_candidates(bundle, KnowledgeGraph.from_edges(bundle.service_edges))
    assert candidates[0].deploy_id == "gh-2002"
    assert "diff_keyword_match" in candidates[0].evidence


def test_incident_memory_survives_restart(conn):
    writer = PostgresIncidentMemory(conn)
    writer.learn_from_scenario(get("pool_exhaustion"))
    writer.learn(ResolvedIncident(
        incident_id="manual-1",
        title="orders-service: p99 latency high",
        culprit_service="orders-service",
        root_cause_summary="dropped index on orders table",
        resolution="pr_revert:orders-service:abc",
    ))

    # A fresh instance on the same database — the "process restarted" case.
    reader = PostgresIncidentMemory(conn)
    assert len(reader) == 2
    matches = reader.match(
        "DB connection pool exhausted",
        "checkout-service reduce db.connectionPoolSize 50 -> 10",
    )
    assert matches and matches[0][1].incident_id == "pool_exhaustion"
    assert matches[0][1].resolution == "helm_rollback:checkout-service:47"


def test_incident_memory_relearn_updates_not_duplicates(conn):
    memory = PostgresIncidentMemory(conn)
    memory.learn_from_scenario(get("pool_exhaustion"))
    memory.learn_from_scenario(get("pool_exhaustion"))
    assert len(PostgresIncidentMemory(conn)) == 1


def test_pgvector_memory_two_sided_guardrail_and_survival(conn):
    from correlation_engine.db.postgres import PgVectorIncidentMemory
    from correlation_engine.embeddings import HashingEmbedder

    embedder = HashingEmbedder()
    writer = PgVectorIncidentMemory(conn, embedder)
    writer.learn_from_scenario(get("pool_exhaustion"))
    writer.learn(ResolvedIncident(
        incident_id="boilerplate-twin",
        # Shares alert boilerplate with the query below but a completely
        # different confirmed cause — the false-precedent shape the
        # two-sided product exists to reject.
        title="checkout-service: DB connection pool exhausted",
        culprit_service="frontend-service",
        root_cause_summary="hero image carousel autoplay regression",
        resolution="pr_revert:frontend-service:zzz",
    ))

    # A fresh instance on the same database (restart survival), scored in SQL.
    reader = PgVectorIncidentMemory(conn, embedder)
    assert len(reader) == 2

    matches = reader.match(
        "DB connection pool exhausted",
        "checkout-service reduce db.connectionPoolSize 50 -> 10",
    )
    assert matches, "true precedent must clear the floor"
    assert matches[0][1].incident_id == "pool_exhaustion"
    assert matches[0][1].resolution == "helm_rollback:checkout-service:47"
    # The boilerplate twin matches on symptom but not on change — the SQL
    # product must keep it below the floor, exactly like the lexical path.
    assert all(m[1].incident_id != "boilerplate-twin" for m in matches)

    assert reader.most_similar("connection pool exhausted checkout")[0][1].incident_id == "pool_exhaustion"


def test_pgvector_and_lexical_memories_agree_on_the_precedent(conn):
    """Behavior parity: both backends retrieve the same top precedent for
    the same query — the embedder approximates the lexical signal by
    construction, and this pins that they don't drift apart silently."""
    from correlation_engine.db.postgres import PgVectorIncidentMemory
    from correlation_engine.embeddings import HashingEmbedder
    from correlation_engine.memory import IncidentMemory

    lexical = IncidentMemory()
    vector = PgVectorIncidentMemory(conn, HashingEmbedder())
    for sid in ("pool_exhaustion", "broken_scraping", "missing_metrics"):
        lexical.learn_from_scenario(get(sid))
        vector.learn_from_scenario(get(sid))

    symptom = "payments-service: metrics absent — scrape target down"
    change = "prometheus consolidate scrape configs rewrite job relabeling"
    lexical_top = lexical.match(symptom, change)[0][1].incident_id
    vector_top = vector.match(symptom, change)[0][1].incident_id
    assert lexical_top == vector_top


@pytest.mark.parametrize("backend", ["lexical", "pgvector"])
def test_cli_learn_then_diagnose_cites_precedent(conn, tmp_path, capsys, backend):
    """The full loop through the CLI: learn a confirmed incident, then a
    diagnose run on partner-shaped files cites it as precedent — for both
    memory backends, proving the pgvector path is wired end to end."""
    from correlation_engine.cli import main
    import json as jsonlib

    assert main([
        "learn", "--memory-dsn", DSN, "--memory-backend", backend,
        "--from-scenario", "pool_exhaustion",
    ]) == 0
    assert "memory now holds 1" in capsys.readouterr().out

    (tmp_path / "deploys.json").write_text(jsonlib.dumps([
        {"service": "checkout-service", "occurred_at": "2026-07-22T09:00:00Z",
         "summary": "bump logging library version", "sha": "aaa111"},
        {"service": "checkout-service", "occurred_at": "2026-07-22T09:31:00Z",
         "summary": "reduce db.connectionPoolSize 50 -> 8", "sha": "ccc333"},
    ]), encoding="utf-8")

    assert main([
        "diagnose",
        "--alert-title", "DB connection pool exhausted",
        "--alert-service", "checkout-service",
        "--fired-at", "2026-07-22T09:32:30Z",
        "--deploys-file", str(tmp_path / "deploys.json"),
        "--memory-dsn", DSN, "--memory-backend", backend,
    ]) == 0

    out = capsys.readouterr().out
    first_candidate = out.split("#1")[1].split("#2")[0]
    assert "ccc333" in first_candidate
    assert "precedent: pool_exhaustion" in first_candidate
    assert "helm_rollback:checkout-service:47" in first_candidate  # the past resolution, surfaced
    assert f"Incident memory: {backend} backend, 1 resolved incident(s)" in out
    assert "running without incident memory" not in out


def test_cli_learn_manual_record(conn, capsys):
    from correlation_engine.cli import main

    assert main([
        "learn", "--memory-dsn", DSN, "--memory-backend", "pgvector",
        "--incident-id", "real-001",
        "--title", "orders-service: p99 latency high on order history",
        "--culprit-service", "orders-service",
        "--root-cause", "dropped covering index on orders table",
        "--resolution", "pr_revert:orders-service:fa57db",
    ]) == 0
    assert "learned 'real-001'" in capsys.readouterr().out

    from correlation_engine.db.postgres import PgVectorIncidentMemory
    from correlation_engine.embeddings import HashingEmbedder
    reader = PgVectorIncidentMemory(conn, HashingEmbedder())
    matches = reader.match(
        "orders-service: p99 latency high on order history",
        "orders-service dropped covering index on orders table",
    )
    assert matches and matches[0][1].incident_id == "real-001"


def test_cli_learn_without_dsn_fails_cleanly(capsys):
    from correlation_engine.cli import main
    assert main(["learn", "--from-scenario", "pool_exhaustion"]) == 2
