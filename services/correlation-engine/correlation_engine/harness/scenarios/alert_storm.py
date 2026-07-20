"""Scenario: alert storm — one root cause, four alerts across the dependency tree.

Category: Observability. Difficulty: hard. Data sources: GitHub deploys +
Kubernetes events + Prometheus alerts + logs (all Phase 1 sources).

The first multi-alert scenario, closing out the initial catalog of 10. A
payments-service deploy enables strict TLS verification with a broken CA
bundle; every outbound gateway call fails, and within four minutes alerts
fire on payments itself, both services that depend on it (checkout,
refunds), and api-gateway two hops up. The pipeline must treat the storm
as one incident: candidates are scored against every alert and aggregated,
so the culprit — causally coupled to all four alerts — outranks a decoy
that only matches its own service's alert. This scenario drove the
multi-alert aggregation in rank_candidates and is its permanent regression
guard; the 'alerts_correlated' evidence ("explains 4 of 4 alerts") is the
storm-grouping signal the future UI and LLM layers will cite.
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

_T0 = datetime(2026, 7, 19, 16, 0, 0)

_DECOY_DEPLOY_ID = "deploy-c4ec00"
_CULPRIT_DEPLOY_ID = "deploy-570rm1"
_ALERT_PAYMENTS = "alert-payments-500s-1"
_ALERT_CHECKOUT = "alert-checkout-payment-failures-1"
_ALERT_REFUNDS = "alert-refunds-failures-1"
_ALERT_GATEWAY = "alert-gateway-5xx-1"


def build() -> Scenario:
    decoy_deploy = DeployEvent(
        id=_DECOY_DEPLOY_ID,
        service="checkout-service",
        source="github",
        git_sha="c4ec00",
        diff_summary={"files_changed": ["templates/banner.html"], "summary": "update checkout page banner copy"},
        deployed_by="noor",
        occurred_at=_T0 + timedelta(minutes=20),
    )
    culprit_deploy = DeployEvent(
        id=_CULPRIT_DEPLOY_ID,
        service="payments-service",
        source="github",
        git_sha="570rm1",
        diff_summary={
            "files_changed": ["config/tls.py"],
            "summary": "enable strict TLS verification for outbound payment gateway connections",
        },
        deployed_by="sam",
        occurred_at=_T0 + timedelta(minutes=30),
    )
    alerts = (
        AlertEvent(
            id=_ALERT_PAYMENTS,
            service="payments-service",
            title="payments-service: HTTP 500 error rate critical",
            severity="critical",
            fired_at=_T0 + timedelta(minutes=32),
        ),
        AlertEvent(
            id=_ALERT_CHECKOUT,
            service="checkout-service",
            title="checkout-service: payment step failures spiking",
            severity="high",
            fired_at=_T0 + timedelta(minutes=33),
        ),
        AlertEvent(
            id=_ALERT_REFUNDS,
            service="refunds-service",
            title="refunds-service: refund processing failures",
            severity="high",
            fired_at=_T0 + timedelta(minutes=33, seconds=30),
        ),
        AlertEvent(
            id=_ALERT_GATEWAY,
            service="api-gateway",
            title="api-gateway: elevated 5xx from downstream",
            severity="high",
            fired_at=_T0 + timedelta(minutes=34),
        ),
    )
    k8s_events = (
        K8sEvent(
            namespace="prod",
            involved_object="payments-service-9e2f1a-k3d8s",
            reason="Started",
            message="Started container payments",
            occurred_at=_T0 + timedelta(minutes=30, seconds=45),
        ),
    )
    logs = (
        LogEntry(
            service="payments-service",
            level="error",
            message="TLS handshake failed: unable to verify payment gateway certificate (CA bundle empty)",
            occurred_at=_T0 + timedelta(minutes=31, seconds=20),
        ),
        LogEntry(
            service="checkout-service",
            level="error",
            message="payment call failed: 500 from payments-service",
            occurred_at=_T0 + timedelta(minutes=32, seconds=10),
        ),
        LogEntry(
            service="refunds-service",
            level="error",
            message="refund execution failed: 500 from payments-service",
            occurred_at=_T0 + timedelta(minutes=32, seconds=40),
        ),
    )
    git_commit = GitCommit(
        sha="570rm1",
        service="payments-service",
        message="enable strict TLS verification for outbound connections",
        author="sam",
        files_changed=("config/tls.py",),
        occurred_at=culprit_deploy.occurred_at,
    )
    edges = (
        ServiceEdge("api-gateway", "checkout-service", "depends_on"),
        ServiceEdge("api-gateway", "refunds-service", "depends_on"),
        ServiceEdge("checkout-service", "payments-service", "depends_on"),
        ServiceEdge("refunds-service", "payments-service", "depends_on"),
    )

    bundle = EvidenceBundle(
        deploys=(decoy_deploy, culprit_deploy),
        alerts=alerts,
        k8s_events=k8s_events,
        logs=logs,
        git_commits=(git_commit,),
        service_edges=edges,
    )

    return Scenario(
        id="alert_storm",
        name="Alert storm — one root cause, four alerts across the tree",
        description=(
            "payments-service enables strict TLS verification with a broken "
            "CA bundle; every outbound gateway call fails. Within four "
            "minutes, alerts fire on payments, checkout (1 hop), refunds "
            "(1 hop), and api-gateway (2 hops). The decoy — an unrelated "
            "checkout deploy 10 minutes before the culprit — scores well "
            "against the checkout alert alone but is causally invisible to "
            "the payments alert; averaging across the storm separates a "
            "cause that explains everything from one that explains one "
            "thing."
        ),
        difficulty=Difficulty.HARD,
        evidence=bundle,
        ground_truth=GroundTruth(
            root_cause_deploy_id=_CULPRIT_DEPLOY_ID,
            explanation="strict TLS verification shipped with an empty CA bundle; all outbound payment gateway calls fail, cascading 500s to every dependent service.",
        ),
        expected_root_cause=_CULPRIT_DEPLOY_ID,
        expected_evidence_keys=("ownership_distance", "blast_radius_weight", "diff_keyword_match"),
        expected_confidence_min=0.18,
        expected_rollback="pr_revert:payments-service:570rm1",
        expected_timeline_refs=(
            _CULPRIT_DEPLOY_ID,
            _ALERT_PAYMENTS,
            _ALERT_CHECKOUT,
            _ALERT_REFUNDS,
            _ALERT_GATEWAY,
        ),
        expected_rule_hits=("time_proximity", "ownership_distance", "diff_keyword_match", "blast_radius_weight"),
    )
