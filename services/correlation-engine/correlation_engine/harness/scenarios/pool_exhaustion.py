"""Scenario: DB connection pool exhaustion after a Helm values change.

Category: Database. Difficulty: easy. Data sources: Helm + Kubernetes events
+ Prometheus alert (all Phase 1 sources, see docs/10-roadmap.md).
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
    HelmRelease,
    K8sEvent,
    Scenario,
    ServiceEdge,
)

_T0 = datetime(2026, 7, 18, 14, 0, 0)

_DECOY_DEPLOY_ID = "deploy-d9e102"
_CULPRIT_DEPLOY_ID = "deploy-a3f21c"
_ALERT_ID = "alert-pool-exhausted-1"


def build() -> Scenario:
    decoy_deploy = DeployEvent(
        id=_DECOY_DEPLOY_ID,
        service="checkout-service",
        source="github",
        git_sha="d9e102",
        diff_summary={"files_changed": ["logging.py"], "summary": "bump logging library version"},
        deployed_by="alice",
        occurred_at=_T0,
    )
    culprit_deploy = DeployEvent(
        id=_CULPRIT_DEPLOY_ID,
        service="checkout-service",
        source="helm",
        git_sha="a3f21c",
        diff_summary={"files_changed": ["values.yaml"], "summary": "reduce db.connectionPoolSize 50 -> 10"},
        deployed_by="jmartin",
        occurred_at=_T0 + timedelta(minutes=31),
    )
    alert = AlertEvent(
        id=_ALERT_ID,
        service="checkout-service",
        title="DB connection pool exhausted",
        severity="high",
        fired_at=_T0 + timedelta(minutes=32, seconds=30),
    )
    k8s_event = K8sEvent(
        namespace="prod",
        involved_object="checkout-service",
        reason="PoolExhausted",
        message="connection pool exhausted, waiting for available connection",
        occurred_at=alert.fired_at,
    )
    helm_release = HelmRelease(
        service="checkout-service",
        revision=48,
        values_diff={"db.connectionPoolSize": {"old": 50, "new": 10}},
        occurred_at=culprit_deploy.occurred_at,
    )
    git_commit = GitCommit(
        sha="a3f21c",
        service="checkout-service",
        message="reduce db connection pool size",
        author="jmartin",
        files_changed=("values.yaml",),
        occurred_at=culprit_deploy.occurred_at,
    )
    edges = (
        ServiceEdge("checkout-service", "payments-service", "depends_on"),
        ServiceEdge("checkout-service", "inventory-service", "depends_on"),
    )

    bundle = EvidenceBundle(
        deploys=(decoy_deploy, culprit_deploy),
        alerts=(alert,),
        k8s_events=(k8s_event,),
        helm_releases=(helm_release,),
        git_commits=(git_commit,),
        service_edges=edges,
    )

    return Scenario(
        id="pool_exhaustion",
        name="DB connection pool exhaustion after Helm values change",
        description=(
            "A Helm values change shrinks checkout-service's DB connection "
            "pool from 50 to 10, causing a pool-exhausted alert ~90s later. "
            "A decoy deploy (unrelated logging-library bump) happened 31 "
            "minutes earlier and must be ranked below the real cause."
        ),
        difficulty=Difficulty.EASY,
        evidence=bundle,
        ground_truth=GroundTruth(
            root_cause_deploy_id=_CULPRIT_DEPLOY_ID,
            explanation="connectionPoolSize reduced 50->10 in Helm values; pool exhausted under normal load.",
        ),
        expected_root_cause=_CULPRIT_DEPLOY_ID,
        expected_evidence_keys=("time_proximity", "diff_keyword_match"),
        expected_confidence_min=0.25,
        expected_rollback="helm_rollback:checkout-service:47",
        expected_timeline_refs=(_CULPRIT_DEPLOY_ID, _ALERT_ID),
        expected_rule_hits=("time_proximity", "ownership_distance", "diff_keyword_match", "blast_radius_weight"),
    )
