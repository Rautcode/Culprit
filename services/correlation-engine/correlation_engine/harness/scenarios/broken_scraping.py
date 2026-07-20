"""Scenario: broken scraping — a monitoring-stack change blinds three services.

Category: Observability (Phase 2). Difficulty: hard. Data sources: GitHub
deploys + Prometheus alerts + logs.

The scenario that required extending the Knowledge Graph (ADR 0002): a
Prometheus scrape-config rewrite breaks target relabeling, and
absent-metrics alerts fire on three services within two minutes. The
services do NOT depend on Prometheus at runtime — they are healthy, and no
depends_on path exists in either direction — so before the monitored_by
edge type, the true culprit was causally invisible. The monitoring channel
is deliberately narrow: it couples a monitoring-stack change only to
observability-shaped alerts, so a Prometheus deploy can never look like a
plausible cause for a checkout 500 spike.

Also exercises the interplay of monitored_by with storm aggregation: the
culprit explains all three alerts through the monitoring path; the decoy
(a checkout deploy) explains only its own service's alert, and the mean
drags it far down. blast_radius_weight deliberately does NOT count
monitored services (runtime dependents only) — noted as a possible future
refinement in ADR 0002, not silently blended in.
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
    Scenario,
    ServiceEdge,
)

_T0 = datetime(2026, 7, 20, 21, 0, 0)

_CULPRIT_DEPLOY_ID = "deploy-5cr4p3"
_DECOY_DEPLOY_ID = "deploy-61f7c4"
_ALERT_CHECKOUT = "alert-checkout-metrics-absent-1"
_ALERT_PAYMENTS = "alert-payments-metrics-absent-1"
_ALERT_ORDERS = "alert-orders-metrics-absent-1"


def build() -> Scenario:
    decoy_deploy = DeployEvent(
        id=_DECOY_DEPLOY_ID,
        service="checkout-service",
        source="github",
        git_sha="61f7c4",
        diff_summary={
            "files_changed": ["cart/giftcards.py"],
            "summary": "add gift card support to cart",
        },
        deployed_by="priya",
        occurred_at=_T0,
    )
    culprit_deploy = DeployEvent(
        id=_CULPRIT_DEPLOY_ID,
        service="prometheus",
        source="github",
        git_sha="5cr4p3",
        diff_summary={
            "files_changed": ["prometheus/scrape_configs.yaml"],
            "summary": "consolidate scrape configs: rewrite job relabeling for service targets",
        },
        deployed_by="platform-team",
        occurred_at=_T0 + timedelta(minutes=10),
    )
    alerts = (
        AlertEvent(
            id=_ALERT_CHECKOUT,
            service="checkout-service",
            title="checkout-service: metrics absent — scrape target down",
            severity="high",
            fired_at=_T0 + timedelta(minutes=16),
        ),
        AlertEvent(
            id=_ALERT_PAYMENTS,
            service="payments-service",
            title="payments-service: metrics absent — scrape target down",
            severity="high",
            fired_at=_T0 + timedelta(minutes=17),
        ),
        AlertEvent(
            id=_ALERT_ORDERS,
            service="orders-service",
            title="orders-service: metrics absent — scrape target down",
            severity="high",
            fired_at=_T0 + timedelta(minutes=18),
        ),
    )
    logs = (
        LogEntry(
            service="prometheus",
            level="warn",
            message='relabel config dropped all targets for jobs "checkout-service", "payments-service", "orders-service"',
            occurred_at=_T0 + timedelta(minutes=12),
        ),
    )
    git_commit = GitCommit(
        sha="5cr4p3",
        service="prometheus",
        message="consolidate scrape configs",
        author="platform-team",
        files_changed=("prometheus/scrape_configs.yaml",),
        occurred_at=culprit_deploy.occurred_at,
    )
    edges = (
        # Runtime topology — note Prometheus appears in none of it.
        ServiceEdge("web-frontend", "checkout-service", "depends_on"),
        ServiceEdge("checkout-service", "payments-service", "depends_on"),
        # Monitoring topology — the new causal channel (ADR 0002).
        ServiceEdge("checkout-service", "prometheus", "monitored_by"),
        ServiceEdge("payments-service", "prometheus", "monitored_by"),
        ServiceEdge("orders-service", "prometheus", "monitored_by"),
    )

    bundle = EvidenceBundle(
        deploys=(decoy_deploy, culprit_deploy),
        alerts=alerts,
        logs=logs,
        git_commits=(git_commit,),
        service_edges=edges,
    )

    return Scenario(
        id="broken_scraping",
        name="Broken scraping — monitoring-stack change blinds three services",
        description=(
            "A scrape-config consolidation rewrites job relabeling and "
            "drops every service target; absent-metrics alerts fire on "
            "checkout, payments, and orders within two minutes. All three "
            "services are healthy and none depends on Prometheus at "
            "runtime — the culprit is reachable only through monitored_by "
            "edges, gated to observability-shaped symptoms. The decoy (a "
            "checkout gift-card deploy) explains one alert of three; storm "
            "aggregation buries it."
        ),
        difficulty=Difficulty.HARD,
        evidence=bundle,
        ground_truth=GroundTruth(
            root_cause_deploy_id=_CULPRIT_DEPLOY_ID,
            explanation="rewritten relabeling rules drop all service targets; every scrape fails and absent-metrics alerts cascade across monitored services.",
        ),
        expected_root_cause=_CULPRIT_DEPLOY_ID,
        expected_evidence_keys=("ownership_distance", "diff_keyword_match"),
        expected_confidence_min=0.24,
        expected_rollback="pr_revert:prometheus:5cr4p3",
        expected_timeline_refs=(_CULPRIT_DEPLOY_ID, _ALERT_CHECKOUT, _ALERT_PAYMENTS, _ALERT_ORDERS),
        expected_rule_hits=("time_proximity", "ownership_distance", "diff_keyword_match"),
    )
