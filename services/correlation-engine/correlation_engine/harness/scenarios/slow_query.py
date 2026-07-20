"""Scenario: p99 latency degradation after an index-dropping migration.

Category: Database. Difficulty: hard. Data sources: GitHub deploys +
Prometheus alert + metrics + logs (all Phase 1 sources).

The counterweight to deadlock: there, sibling coupling had to be strong
enough to surface a shared-resource culprit; here it must not be TOO
generous. The culprit is a same-service "cleanup" migration that drops an
index believed unused — p99 climbs gradually as order-history queries fall
back to sequential scans. The decoy is a billing-service hourly report job
that reads the same orders table and lands just 15 minutes before the
alert: sibling-coupled via orders-db, keyword-adjacent ("orders table"),
and close in time, it fires ALL FOUR rules — the first decoy to do so —
and must still rank below the culprit. Third scenario with no Kubernetes
events (the failure lives in query plans, not pods).
"""
from __future__ import annotations

from datetime import datetime, timedelta

from ..schema import (
    AlertEvent,
    DeployEvent,
    Difficulty,
    EvidenceBundle,
    GitCommit,
    GroundTruth,
    LogEntry,
    MetricSample,
    Scenario,
    ServiceEdge,
)

_T0 = datetime(2026, 7, 19, 14, 0, 0)

_CULPRIT_DEPLOY_ID = "deploy-fa57db"
_DECOY_DEPLOY_ID = "deploy-b1111n6"
_ALERT_ID = "alert-orders-p99-1"


def build() -> Scenario:
    culprit_deploy = DeployEvent(
        id=_CULPRIT_DEPLOY_ID,
        service="orders-service",
        source="github",
        git_sha="fa57db",
        diff_summary={
            "files_changed": ["migrations/0042_drop_order_history_index.sql"],
            "summary": "drop unused index idx_orders_customer_created on orders table",
        },
        deployed_by="felix",
        occurred_at=_T0,
    )
    decoy_deploy = DeployEvent(
        id=_DECOY_DEPLOY_ID,
        service="billing-service",
        source="github",
        git_sha="b1111n6",
        diff_summary={
            "files_changed": ["jobs/revenue_report.py"],
            "summary": "add hourly revenue report job reading orders table",
        },
        deployed_by="grace",
        occurred_at=_T0 + timedelta(minutes=55),
    )
    alert = AlertEvent(
        id=_ALERT_ID,
        service="orders-service",
        title="orders-service: p99 latency high on order history queries",
        severity="high",
        fired_at=_T0 + timedelta(minutes=70),
    )
    # p99 climbing steadily from the migration onward — degradation begins
    # well before the decoy deploy exists, which is the human-readable
    # tiebreaker the metrics evidence preserves for the UI/LLM layers.
    metrics = tuple(
        MetricSample(
            service="orders-service",
            metric="http_request_duration_p99_ms",
            value=value,
            occurred_at=_T0 + timedelta(minutes=minute),
        )
        for minute, value in ((10, 120), (30, 180), (50, 260), (65, 410), (69, 640))
    )
    logs = (
        LogEntry(
            service="orders-service",
            level="warn",
            message="slow query (1840ms): SELECT ... FROM orders WHERE customer_id = $1 ORDER BY created_at DESC — Seq Scan on orders (2.4M rows)",
            occurred_at=_T0 + timedelta(minutes=66),
        ),
        LogEntry(
            service="orders-service",
            level="warn",
            message="slow query (2310ms): order history lookup exceeded 2s budget",
            occurred_at=_T0 + timedelta(minutes=68, seconds=30),
        ),
    )
    git_commit = GitCommit(
        sha="fa57db",
        service="orders-service",
        message="drop unused index on orders table",
        author="felix",
        files_changed=("migrations/0042_drop_order_history_index.sql",),
        occurred_at=culprit_deploy.occurred_at,
    )
    edges = (
        ServiceEdge("api-gateway", "orders-service", "depends_on"),
        ServiceEdge("api-gateway", "billing-service", "depends_on"),
        ServiceEdge("orders-service", "orders-db", "depends_on"),
        ServiceEdge("billing-service", "orders-db", "depends_on"),
    )

    bundle = EvidenceBundle(
        deploys=(culprit_deploy, decoy_deploy),
        alerts=(alert,),
        metrics=metrics,
        logs=logs,
        git_commits=(git_commit,),
        service_edges=edges,
    )

    return Scenario(
        id="slow_query",
        name="p99 degradation after index-dropping migration (strong sibling decoy)",
        description=(
            "An orders-service 'cleanup' migration drops an index believed "
            "unused; order-history queries fall back to sequential scans and "
            "p99 climbs for 70 minutes. The decoy — a billing-service report "
            "job reading the same orders table — is sibling-coupled via "
            "orders-db, keyword-adjacent, and lands 15 minutes before the "
            "alert: it fires all four rules and must still lose to the "
            "same-service culprit with the stronger diff match."
        ),
        difficulty=Difficulty.HARD,
        evidence=bundle,
        ground_truth=GroundTruth(
            root_cause_deploy_id=_CULPRIT_DEPLOY_ID,
            explanation="idx_orders_customer_created was load-bearing for order-history lookups; dropping it degrades p99 as the table is seq-scanned.",
        ),
        expected_root_cause=_CULPRIT_DEPLOY_ID,
        expected_evidence_keys=("diff_keyword_match", "time_proximity"),
        expected_confidence_min=0.22,
        expected_rollback="pr_revert:orders-service:fa57db",
        expected_timeline_refs=(_CULPRIT_DEPLOY_ID, _ALERT_ID),
        expected_rule_hits=("time_proximity", "ownership_distance", "diff_keyword_match", "blast_radius_weight"),
    )
