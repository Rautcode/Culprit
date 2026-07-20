"""Evidence Collection tests (build step 2).

The headline test is the end-to-end slice: raw GitHub/Alertmanager/K8s
payloads -> adapters -> EvidenceStore (idempotent) -> correlation-window
bundle -> Knowledge Graph + Rule Engine -> correct culprit. Same pipeline
the harness scenarios exercise, now fed from source-shaped data instead of
hand-authored schema objects.
"""
from correlation_engine.collection.adapters import (
    parse_alertmanager,
    parse_github_deployment,
    parse_k8s_event,
)
from correlation_engine.collection.store import EvidenceStore
from correlation_engine.harness.schema import ServiceEdge
from correlation_engine.knowledge_graph import KnowledgeGraph
from correlation_engine.pipeline import build_timeline, rank_candidates

DECOY_DEPLOY_WEBHOOK = {
    "action": "created",
    "deployment": {
        "id": 2001,
        "sha": "d9e102f",
        "description": "bump logging library version",
        "creator": {"login": "alice"},
        "created_at": "2026-07-18T14:00:00Z",
    },
    "repository": {"name": "checkout-service"},
}

CULPRIT_DEPLOY_WEBHOOK = {
    "action": "created",
    "deployment": {
        "id": 2002,
        "sha": "a3f21c9",
        "description": "reduce db.connectionPoolSize 50 -> 10",
        "creator": {"login": "jmartin"},
        "created_at": "2026-07-18T14:31:00Z",
    },
    "repository": {"name": "checkout-service"},
}

STALE_DEPLOY_WEBHOOK = {
    "action": "created",
    "deployment": {
        "id": 1990,
        "sha": "0ld0ld0",
        "description": "update dependencies",
        "creator": {"login": "bot"},
        "created_at": "2026-07-18T09:00:00Z",
    },
    "repository": {"name": "checkout-service"},
}

ALERTMANAGER_WEBHOOK = {
    "version": "4",
    "status": "firing",
    "alerts": [
        {
            "status": "firing",
            "fingerprint": "f00dfeed",
            "labels": {"alertname": "DBConnectionPoolExhausted", "service": "checkout-service", "severity": "high"},
            "annotations": {"summary": "DB connection pool exhausted"},
            "startsAt": "2026-07-18T14:32:30Z",
        },
        {
            "status": "resolved",
            "fingerprint": "deadbeef",
            "labels": {"alertname": "OldAlert", "service": "checkout-service", "severity": "low"},
            "annotations": {"summary": "already resolved, must be ignored"},
            "startsAt": "2026-07-18T13:00:00Z",
        },
    ],
}

K8S_EVENT = {
    "metadata": {"uid": "aaa-bbb", "namespace": "prod"},
    "involvedObject": {"name": "checkout-service-7d9f8b-x2k4p", "namespace": "prod"},
    "reason": "PoolExhausted",
    "message": "connection pool exhausted, waiting for available connection",
    "lastTimestamp": "2026-07-18T14:32:30Z",
}


def test_github_adapter():
    event = parse_github_deployment(CULPRIT_DEPLOY_WEBHOOK)
    assert event.id == "gh-2002"
    assert event.service == "checkout-service"
    assert event.git_sha == "a3f21c9"
    assert event.deployed_by == "jmartin"
    assert "connectionPoolSize" in event.diff_summary["summary"]


def test_alertmanager_adapter_skips_resolved():
    events = parse_alertmanager(ALERTMANAGER_WEBHOOK)
    assert len(events) == 1
    alert = events[0]
    assert alert.id == "am-f00dfeed"
    assert alert.title == "DB connection pool exhausted"
    assert alert.service == "checkout-service"


def test_k8s_adapter():
    event = parse_k8s_event(K8S_EVENT)
    assert event.namespace == "prod"
    assert event.reason == "PoolExhausted"


def _populated_store() -> EvidenceStore:
    store = EvidenceStore()
    for webhook in (DECOY_DEPLOY_WEBHOOK, CULPRIT_DEPLOY_WEBHOOK, STALE_DEPLOY_WEBHOOK):
        store.add_deploy(parse_github_deployment(webhook))
    for alert in parse_alertmanager(ALERTMANAGER_WEBHOOK):
        store.add_alert(alert)
    store.add_k8s_event(parse_k8s_event(K8S_EVENT))
    store.add_edge(ServiceEdge("web-frontend", "checkout-service", "depends_on"))
    store.add_edge(ServiceEdge("checkout-service", "payments-service", "depends_on"))
    return store


def test_store_is_idempotent_under_webhook_retry():
    store = _populated_store()
    assert store.add_deploy(parse_github_deployment(CULPRIT_DEPLOY_WEBHOOK)) is False
    assert store.add_alert(parse_alertmanager(ALERTMANAGER_WEBHOOK)[0]) is False
    assert store.add_k8s_event(parse_k8s_event(K8S_EVENT)) is False
    bundle = store.bundle_for_alerts()
    assert len(bundle.deploys) == 2  # replay added nothing
    assert len(bundle.alerts) == 1


def test_raw_payloads_to_rca_end_to_end():
    store = _populated_store()
    bundle = store.bundle_for_alerts()

    # Window: the 09:00 deploy is outside ±2h of the 14:32 alert.
    assert {d.id for d in bundle.deploys} == {"gh-2001", "gh-2002"}

    graph = KnowledgeGraph.from_edges(bundle.service_edges)
    candidates = rank_candidates(bundle, graph)
    assert candidates[0].deploy_id == "gh-2002", "culprit deploy must rank first"
    assert candidates[0].confidence.composite > candidates[-1].confidence.composite
    assert "diff_keyword_match" in candidates[0].evidence

    timeline = build_timeline(bundle)
    occurred = [event["occurred_at"] for event in timeline]
    assert occurred == sorted(occurred)
    refs = [event["ref"] for event in timeline]
    assert "gh-2002" in refs and "am-f00dfeed" in refs
