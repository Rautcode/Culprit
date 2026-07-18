"""Scenario: CrashLoopBackOff after a container entrypoint change.

Category: Kubernetes. Difficulty: medium. Data sources: GitHub deploys +
Kubernetes events + Prometheus alert (all Phase 1 sources).

Harder than pool_exhaustion in one specific way: the second decoy is a
deploy on a *different* service that lands closer in time to the alert than
the same-service decoy — so pure time-proximity ranking would get this
wrong, and the pipeline has to use the Knowledge Graph (ownership distance)
to keep cross-service noise below the real cause.
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
    Scenario,
    ServiceEdge,
)

_T0 = datetime(2026, 7, 18, 9, 0, 0)

_CULPRIT_DEPLOY_ID = "deploy-b7c9e4"
_SAME_SERVICE_DECOY_ID = "deploy-11aa22"
_CROSS_SERVICE_DECOY_ID = "deploy-33cc44"
_ALERT_ID = "alert-crash-loop-1"


def build() -> Scenario:
    same_service_decoy = DeployEvent(
        id=_SAME_SERVICE_DECOY_ID,
        service="payments-service",
        source="github",
        git_sha="11aa22",
        diff_summary={"files_changed": ["templates/email.html"], "summary": "update receipt email copy"},
        deployed_by="priya",
        occurred_at=_T0,
    )
    culprit_deploy = DeployEvent(
        id=_CULPRIT_DEPLOY_ID,
        service="payments-service",
        source="github",
        git_sha="b7c9e4",
        diff_summary={
            "files_changed": ["Dockerfile", "deployment.yaml"],
            "summary": "change container entrypoint to ./run.sh and drop wrapper command",
        },
        deployed_by="sam",
        occurred_at=_T0 + timedelta(minutes=40),
    )
    cross_service_decoy = DeployEvent(
        id=_CROSS_SERVICE_DECOY_ID,
        service="ledger-service",
        source="github",
        git_sha="33cc44",
        diff_summary={"files_changed": ["report.py"], "summary": "add monthly settlement report"},
        deployed_by="wei",
        occurred_at=_T0 + timedelta(minutes=41),
    )
    alert = AlertEvent(
        id=_ALERT_ID,
        service="payments-service",
        title="Pod crash loop detected: payments-service restarting repeatedly",
        severity="critical",
        fired_at=_T0 + timedelta(minutes=43),
    )
    k8s_events = (
        K8sEvent(
            namespace="prod",
            involved_object="payments-service-7d9f8b-x2k4p",
            reason="BackOff",
            message="Back-off restarting failed container payments in pod payments-service-7d9f8b-x2k4p",
            occurred_at=_T0 + timedelta(minutes=41, seconds=30),
        ),
        K8sEvent(
            namespace="prod",
            involved_object="payments-service-7d9f8b-x2k4p",
            reason="CrashLoopBackOff",
            message='container payments in CrashLoopBackOff: "./run.sh: no such file or directory"',
            occurred_at=_T0 + timedelta(minutes=42, seconds=45),
        ),
    )
    git_commit = GitCommit(
        sha="b7c9e4",
        service="payments-service",
        message="change container entrypoint to ./run.sh",
        author="sam",
        files_changed=("Dockerfile", "deployment.yaml"),
        occurred_at=culprit_deploy.occurred_at,
    )
    edges = (
        ServiceEdge("checkout-service", "payments-service", "depends_on"),
        ServiceEdge("payments-service", "ledger-service", "depends_on"),
    )

    bundle = EvidenceBundle(
        deploys=(same_service_decoy, culprit_deploy, cross_service_decoy),
        alerts=(alert,),
        k8s_events=k8s_events,
        git_commits=(git_commit,),
        service_edges=edges,
    )

    return Scenario(
        id="crash_loop_backoff",
        name="CrashLoopBackOff after container entrypoint change",
        description=(
            "A deploy changes payments-service's container entrypoint to a "
            "script that doesn't exist in the image, sending pods into "
            "CrashLoopBackOff ~3 minutes later. Two decoys: an unrelated "
            "same-service deploy 40 minutes earlier, and a ledger-service "
            "deploy that lands *closer* to the alert than the culprit — "
            "time proximity alone would rank the wrong deploy first."
        ),
        difficulty=Difficulty.MEDIUM,
        evidence=bundle,
        ground_truth=GroundTruth(
            root_cause_deploy_id=_CULPRIT_DEPLOY_ID,
            explanation="entrypoint changed to ./run.sh, which doesn't exist in the image; container exits on start.",
        ),
        expected_root_cause=_CULPRIT_DEPLOY_ID,
        expected_evidence_keys=("time_proximity", "diff_keyword_match"),
        expected_confidence_min=0.25,
        expected_rollback="pr_revert:payments-service:b7c9e4",
        expected_timeline_refs=(_CULPRIT_DEPLOY_ID, _ALERT_ID),
        expected_rule_hits=("time_proximity", "ownership_distance", "diff_keyword_match", "blast_radius_weight"),
    )
