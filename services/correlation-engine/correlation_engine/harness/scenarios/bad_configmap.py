"""Scenario: bad ConfigMap value — alert fires DOWNSTREAM of the true cause.

Category: Kubernetes. Difficulty: hard. Data sources: ArgoCD sync +
Kubernetes events + Prometheus alert + logs (all Phase 1 sources).

The most important case in the catalog so far: the culprit and the alert
are on *different services*. A ConfigMap change on payments-service sets an
HTTP client timeout to 50 (milliseconds, meant 5000) — payments' outbound
gateway calls start timing out, and the user-visible alert fires on
checkout-service, which depends on payments. Every prior scenario had a
same-service culprit; this one requires the Knowledge Graph traversal to
run in the causally correct direction (alert.service -> deploy.service),
and writing it exposed that both time_proximity and ownership_distance had
that direction wrong. The rules were fixed; this scenario is the permanent
regression guard for that fix.
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
    K8sEvent,
    LogEntry,
    Scenario,
    ServiceEdge,
)

_T0 = datetime(2026, 7, 18, 18, 0, 0)

_CULPRIT_DEPLOY_ID = "deploy-c0ff33"
_DECOY_DEPLOY_ID = "deploy-55dd66"
_ALERT_ID = "alert-payment-timeouts-1"


def build() -> Scenario:
    decoy_deploy = DeployEvent(
        id=_DECOY_DEPLOY_ID,
        service="checkout-service",
        source="github",
        git_sha="55dd66",
        diff_summary={"files_changed": ["cart/session.py"], "summary": "refactor cart session handling"},
        deployed_by="noor",
        occurred_at=_T0 + timedelta(minutes=15),
    )
    culprit_deploy = DeployEvent(
        id=_CULPRIT_DEPLOY_ID,
        service="payments-service",
        source="argocd",
        git_sha="c0ff33",
        diff_summary={
            "files_changed": ["configmap.yaml"],
            "summary": "set HTTP_CLIENT_TIMEOUT_MS to 50 in payments ConfigMap",
        },
        deployed_by="argocd-sync",
        occurred_at=_T0 + timedelta(minutes=33),
    )
    alert = AlertEvent(
        id=_ALERT_ID,
        service="checkout-service",
        title="checkout-service: payment request timeouts spiking",
        severity="high",
        fired_at=_T0 + timedelta(minutes=35),
    )
    k8s_events = (
        K8sEvent(
            namespace="prod",
            involved_object="payments-service-6b3c9d-w8n2v",
            reason="Killing",
            message="Stopping container payments (rolling update after config checksum change)",
            occurred_at=_T0 + timedelta(minutes=33, seconds=10),
        ),
        K8sEvent(
            namespace="prod",
            involved_object="payments-service-6b3c9d-q5j7x",
            reason="Started",
            message="Started container payments",
            occurred_at=_T0 + timedelta(minutes=33, seconds=40),
        ),
    )
    logs = (
        LogEntry(
            service="payments-service",
            level="error",
            message="gateway request timed out after 50ms (HTTP_CLIENT_TIMEOUT_MS=50)",
            occurred_at=_T0 + timedelta(minutes=34, seconds=20),
        ),
        LogEntry(
            service="checkout-service",
            level="error",
            message="payment authorization failed: upstream timeout from payments-service",
            occurred_at=_T0 + timedelta(minutes=34, seconds=50),
        ),
    )
    git_commit = GitCommit(
        sha="c0ff33",
        service="payments-service",
        message="tune payments http client timeout",
        author="dana",
        files_changed=("configmap.yaml",),
        occurred_at=culprit_deploy.occurred_at,
    )
    edges = (
        ServiceEdge("checkout-service", "payments-service", "depends_on"),
        ServiceEdge("payments-service", "fraud-service", "depends_on"),
    )

    bundle = EvidenceBundle(
        deploys=(decoy_deploy, culprit_deploy),
        alerts=(alert,),
        k8s_events=k8s_events,
        logs=logs,
        git_commits=(git_commit,),
        service_edges=edges,
    )

    return Scenario(
        id="bad_configmap",
        name="Bad ConfigMap value — alert fires downstream of the cause",
        description=(
            "A ConfigMap change (via ArgoCD sync) sets payments-service's "
            "HTTP client timeout to 50ms instead of 5000ms. Payments' "
            "outbound calls start timing out, and the alert fires on "
            "checkout-service — one dependency hop away from the true "
            "cause. The decoy is a same-service checkout deploy 20 minutes "
            "before the alert. A pipeline that can't traverse the graph in "
            "the causal direction ranks the decoy first."
        ),
        difficulty=Difficulty.HARD,
        evidence=bundle,
        ground_truth=GroundTruth(
            root_cause_deploy_id=_CULPRIT_DEPLOY_ID,
            explanation="HTTP_CLIENT_TIMEOUT_MS set to 50 (unit confusion, meant 5000); payments gateway calls time out, surfacing as checkout payment failures.",
        ),
        expected_root_cause=_CULPRIT_DEPLOY_ID,
        expected_evidence_keys=("ownership_distance", "diff_keyword_match"),
        expected_confidence_min=0.2,
        expected_rollback="pr_revert:payments-service:c0ff33",
        expected_timeline_refs=(_CULPRIT_DEPLOY_ID, _ALERT_ID),
        expected_rule_hits=("time_proximity", "ownership_distance", "diff_keyword_match", "blast_radius_weight"),
    )
