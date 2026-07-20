"""Scenario: database deadlocks — culprit is a SIBLING through a shared database.

Category: Database. Difficulty: hard. Data sources: GitHub deploys +
Prometheus alert + metrics + logs (all Phase 1 sources).

First scenario where the culprit and the alerting service have NO
depends_on path between them in either direction: billing-service and
orders-service are siblings that both write to orders-db. billing ships an
invoice-reconciliation job that batch-updates the orders table; lock
ordering now collides with orders-service's row updates, and orders-service
alerts on deadlock errors. Before this scenario, the graph could only
couple services through direct dependency chains — the sibling-through-
shared-resource path (the canonical deadlock topology) scored the true
culprit at zero on both ownership and time gating. This scenario drove the
KnowledgeGraph.coupling() extension and is its permanent regression guard.
Like bad_rollout, it has no Kubernetes events — pods are healthy; the
failure lives entirely in the database.
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

_T0 = datetime(2026, 7, 19, 10, 0, 0)

_DECOY_DEPLOY_ID = "deploy-0rd3r5"
_CULPRIT_DEPLOY_ID = "deploy-dead10"
_ALERT_ID = "alert-orders-deadlock-1"


def build() -> Scenario:
    decoy_deploy = DeployEvent(
        id=_DECOY_DEPLOY_ID,
        service="orders-service",
        source="github",
        git_sha="0rd3r5",
        diff_summary={"files_changed": ["search/pagination.py"], "summary": "improve order search pagination"},
        deployed_by="felix",
        occurred_at=_T0,
    )
    culprit_deploy = DeployEvent(
        id=_CULPRIT_DEPLOY_ID,
        service="billing-service",
        source="github",
        git_sha="dead10",
        diff_summary={
            "files_changed": ["jobs/reconcile_invoices.py"],
            "summary": "add invoice reconciliation job that batch-updates orders table in a transaction",
        },
        deployed_by="grace",
        occurred_at=_T0 + timedelta(minutes=41),
    )
    alert = AlertEvent(
        id=_ALERT_ID,
        service="orders-service",
        title="orders-service: database deadlock errors spiking",
        severity="high",
        fired_at=_T0 + timedelta(minutes=45),
    )
    metrics = tuple(
        MetricSample(
            service="orders-service",
            metric="pg_stat_database_deadlocks_total",
            value=value,
            occurred_at=_T0 + timedelta(minutes=minute),
        )
        for minute, value in ((10, 0), (30, 0), (42, 3), (44, 17))
    )
    logs = (
        LogEntry(
            service="billing-service",
            level="info",
            message="invoice reconciliation job started (batch size 5000, table: orders)",
            occurred_at=_T0 + timedelta(minutes=41, seconds=40),
        ),
        LogEntry(
            service="orders-service",
            level="error",
            message="deadlock detected (40P01): process 4123 waits for ShareLock on transaction 887766; blocked by process 4907",
            occurred_at=_T0 + timedelta(minutes=43, seconds=20),
        ),
    )
    git_commit = GitCommit(
        sha="dead10",
        service="billing-service",
        message="add invoice reconciliation job",
        author="grace",
        files_changed=("jobs/reconcile_invoices.py",),
        occurred_at=culprit_deploy.occurred_at,
    )
    edges = (
        ServiceEdge("api-gateway", "orders-service", "depends_on"),
        ServiceEdge("api-gateway", "billing-service", "depends_on"),
        ServiceEdge("orders-service", "orders-db", "depends_on"),
        ServiceEdge("billing-service", "orders-db", "depends_on"),
    )

    bundle = EvidenceBundle(
        deploys=(decoy_deploy, culprit_deploy),
        alerts=(alert,),
        metrics=metrics,
        logs=logs,
        git_commits=(git_commit,),
        service_edges=edges,
    )

    return Scenario(
        id="deadlock",
        name="Database deadlocks — sibling culprit through a shared database",
        description=(
            "billing-service ships an invoice-reconciliation job that "
            "batch-updates the orders table; its lock ordering collides "
            "with orders-service's row updates and deadlocks spike 4 "
            "minutes later. There is no depends_on path between the two "
            "services in either direction — they are coupled only as "
            "co-writers of orders-db. The decoy is a same-service "
            "orders-service deploy 45 minutes before the alert; a graph "
            "that can't see sibling coupling ranks the decoy first."
        ),
        difficulty=Difficulty.HARD,
        evidence=bundle,
        ground_truth=GroundTruth(
            root_cause_deploy_id=_CULPRIT_DEPLOY_ID,
            explanation="reconciliation job batch-updates orders rows in a transaction with lock ordering opposite to orders-service's update path; concurrent load deadlocks.",
        ),
        expected_root_cause=_CULPRIT_DEPLOY_ID,
        expected_evidence_keys=("ownership_distance", "diff_keyword_match"),
        expected_confidence_min=0.18,
        expected_rollback="pr_revert:billing-service:dead10",
        expected_timeline_refs=(_CULPRIT_DEPLOY_ID, _ALERT_ID),
        expected_rule_hits=("time_proximity", "ownership_distance", "diff_keyword_match", "blast_radius_weight"),
    )
