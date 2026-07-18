"""Scenario: OOMKilled after a memory-limit reduction in Helm values.

Category: Kubernetes. Difficulty: hard. Data sources: Helm + Kubernetes
events + Prometheus alert + metrics (all Phase 1 sources).

What this tests that pool_exhaustion and crash_loop_backoff don't: a
slow-burn failure. The culprit deploy lands 90 minutes before the alert
(memory climbs gradually until the reduced limit is hit), while a decoy
same-service deploy lands just 10 minutes before it. Time proximity favors
the decoy — diff keyword evidence must outweigh it for the ranking to be
right. This is the weighted-rule interplay case: no single rule wins alone.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from ..schema import (
    AlertEvent,
    DeployEvent,
    Difficulty,
    EvidenceBundle,
    GroundTruth,
    HelmRelease,
    K8sEvent,
    MetricSample,
    Scenario,
    ServiceEdge,
)

_T0 = datetime(2026, 7, 18, 11, 0, 0)

_CULPRIT_DEPLOY_ID = "deploy-e5f807"
_DECOY_DEPLOY_ID = "deploy-99bb00"
_ALERT_ID = "alert-oom-killed-1"


def build() -> Scenario:
    culprit_deploy = DeployEvent(
        id=_CULPRIT_DEPLOY_ID,
        service="inventory-service",
        source="helm",
        git_sha="e5f807",
        diff_summary={
            "files_changed": ["values.yaml"],
            "summary": "reduce container memory limit 512Mi to 256Mi in resources block",
        },
        deployed_by="derya",
        occurred_at=_T0,
    )
    decoy_deploy = DeployEvent(
        id=_DECOY_DEPLOY_ID,
        service="inventory-service",
        source="github",
        git_sha="99bb00",
        diff_summary={"files_changed": ["tracing.py"], "summary": "add tracing spans to stock lookup"},
        deployed_by="marco",
        occurred_at=_T0 + timedelta(minutes=80),
    )
    alert = AlertEvent(
        id=_ALERT_ID,
        service="inventory-service",
        title="Pod OOMKilled: memory usage exceeded limit",
        severity="high",
        fired_at=_T0 + timedelta(minutes=90),
    )
    k8s_events = (
        K8sEvent(
            namespace="prod",
            involved_object="inventory-service-5c6d7e-m9q1z",
            reason="OOMKilling",
            message="Memory cgroup out of memory: killed process (inventory) total-vm anon-rss exceeds limit 256Mi",
            occurred_at=_T0 + timedelta(minutes=89, seconds=30),
        ),
        K8sEvent(
            namespace="prod",
            involved_object="inventory-service-5c6d7e-m9q1z",
            reason="BackOff",
            message="Back-off restarting failed container inventory",
            occurred_at=_T0 + timedelta(minutes=90, seconds=15),
        ),
    )
    # Memory climbing steadily from deploy to kill — the slow burn, visible
    # in evidence even though no v1 rule consumes metrics yet.
    metrics = tuple(
        MetricSample(
            service="inventory-service",
            metric="container_memory_working_set_bytes",
            value=mb * 1024 * 1024,
            occurred_at=_T0 + timedelta(minutes=minute),
        )
        for minute, mb in ((5, 140), (30, 180), (60, 220), (85, 251))
    )
    helm_release = HelmRelease(
        service="inventory-service",
        revision=12,
        values_diff={"resources.limits.memory": {"old": "512Mi", "new": "256Mi"}},
        occurred_at=culprit_deploy.occurred_at,
    )
    edges = (
        ServiceEdge("checkout-service", "inventory-service", "depends_on"),
        ServiceEdge("inventory-service", "stock-cache", "depends_on"),
    )

    bundle = EvidenceBundle(
        deploys=(culprit_deploy, decoy_deploy),
        alerts=(alert,),
        k8s_events=k8s_events,
        metrics=metrics,
        helm_releases=(helm_release,),
        service_edges=edges,
    )

    return Scenario(
        id="oom_killed",
        name="OOMKilled after memory-limit reduction (slow burn)",
        description=(
            "A Helm values change halves inventory-service's memory limit. "
            "Memory climbs for 90 minutes before pods start getting "
            "OOMKilled. A decoy deploy (tracing instrumentation) lands just "
            "10 minutes before the alert — time proximity favors the decoy, "
            "and diff keyword evidence must outweigh it."
        ),
        difficulty=Difficulty.HARD,
        evidence=bundle,
        ground_truth=GroundTruth(
            root_cause_deploy_id=_CULPRIT_DEPLOY_ID,
            explanation="memory limit halved to 256Mi; working set exceeds it under normal load after ~90 min.",
        ),
        expected_root_cause=_CULPRIT_DEPLOY_ID,
        expected_evidence_keys=("diff_keyword_match", "time_proximity"),
        expected_confidence_min=0.2,
        expected_rollback="helm_rollback:inventory-service:11",
        expected_timeline_refs=(_CULPRIT_DEPLOY_ID, _ALERT_ID),
        expected_rule_hits=("time_proximity", "ownership_distance", "diff_keyword_match", "blast_radius_weight"),
    )
