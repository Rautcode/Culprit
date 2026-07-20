"""Scenario: mesh routing shift — a stalled canary gets 80% of traffic.

Category: Network (Phase 2). Difficulty: medium. Data sources: Istio/GitOps
routing config + GitHub deploys + Prometheus alert + metrics + logs.

Coverage scenario, honestly labeled: the ranking mechanics here (same-service
config change beats a time-closer decoy on keyword evidence) are already
guarded by oom_killed and feature_flag_failure — this row exists because
traffic-shift regressions are one of the most common mesh-era incident
classes, and the catalog should carry its failure vocabulary. What IS new
is the data profile: the first PARTIAL failure (error rate proportional to
the canary weight — 2% of requests failing at 20% weight was below alert
threshold for a week; 80% weight crosses it), and the first istio-sourced
change event. No code deployed today — the bad version was already running;
only its traffic share changed.
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

_T0 = datetime(2026, 7, 21, 10, 0, 0)

_CULPRIT_DEPLOY_ID = "deploy-m35hv2"
_DECOY_DEPLOY_ID = "deploy-w1d637"
_ALERT_ID = "alert-checkout-canary-500s-1"


def build() -> Scenario:
    culprit_deploy = DeployEvent(
        id=_CULPRIT_DEPLOY_ID,
        service="checkout-service",
        source="istio",
        git_sha="m35hv2",
        diff_summary={
            "files_changed": ["mesh/checkout-virtualservice.yaml"],
            "summary": "shift checkout route weights across subsets: v1 80->20, canary v2 20->80",
        },
        deployed_by="argocd-sync (pr #519)",
        occurred_at=_T0,
    )
    decoy_deploy = DeployEvent(
        id=_DECOY_DEPLOY_ID,
        service="checkout-service",
        source="github",
        git_sha="w1d637",
        diff_summary={
            "files_changed": ["widgets/recommendations.css"],
            "summary": "update recommendation widget styles",
        },
        deployed_by="ines",
        occurred_at=_T0 + timedelta(minutes=22),
    )
    alert = AlertEvent(
        id=_ALERT_ID,
        service="checkout-service",
        title="checkout-service: elevated 500 rate on canary subset v2",
        severity="high",
        fired_at=_T0 + timedelta(minutes=30),
    )
    # Error rate tracks the traffic weight, not a deploy moment: ~2% while
    # the canary held 20% (below the 5% alert threshold, invisible for a
    # week), stepping to ~15% as sessions migrate onto the 80% weight.
    metrics = tuple(
        MetricSample(
            service="checkout-service",
            metric="http_5xx_rate_percent",
            value=value,
            occurred_at=_T0 + timedelta(minutes=minute),
        )
        for minute, value in ((-30, 2.1), (5, 4.8), (15, 9.6), (25, 14.2), (29, 15.3))
    )
    logs = (
        LogEntry(
            service="checkout-service",
            level="error",
            message="v2 pod checkout-v2-6b9c4d: NullPointerException in loyalty-points pricing path",
            occurred_at=_T0 + timedelta(minutes=26),
        ),
    )
    git_commit = GitCommit(
        sha="m35hv2",
        service="checkout-service",
        message="promote checkout canary to 80%",
        author="sam",
        files_changed=("mesh/checkout-virtualservice.yaml",),
        occurred_at=culprit_deploy.occurred_at,
    )
    edges = (
        ServiceEdge("web-frontend", "checkout-service", "depends_on"),
        ServiceEdge("checkout-service", "payments-service", "depends_on"),
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
        id="mesh_routing",
        name="Mesh routing shift — stalled canary promoted to 80%",
        description=(
            "A VirtualService change promotes checkout's v2 canary from 20% "
            "to 80% of traffic. v2 has carried a latent loyalty-points bug "
            "all week — at 20% weight the ~2% error rate sat below the "
            "alert threshold. No code shipped today; only the traffic split "
            "moved. The decoy (a widget CSS deploy) lands 8 minutes before "
            "the alert; the canary/subset keyword evidence must outrank it."
        ),
        difficulty=Difficulty.MEDIUM,
        evidence=bundle,
        ground_truth=GroundTruth(
            root_cause_deploy_id=_CULPRIT_DEPLOY_ID,
            explanation="v2 canary mishandles loyalty-points pricing; error rate scaled with its traffic weight and crossed the alert threshold at 80%.",
        ),
        expected_root_cause=_CULPRIT_DEPLOY_ID,
        expected_evidence_keys=("diff_keyword_match", "time_proximity"),
        expected_confidence_min=0.25,
        expected_rollback="pr_revert:checkout-service:m35hv2",
        expected_timeline_refs=(_CULPRIT_DEPLOY_ID, _ALERT_ID),
        expected_rule_hits=("time_proximity", "ownership_distance", "diff_keyword_match", "blast_radius_weight"),
    )
