"""Scenario: ImagePullBackOff after a deploy references an unpushed image tag.

Category: Kubernetes. Difficulty: medium. Data sources: GitHub deploys +
Kubernetes events + Prometheus alert (all Phase 1 sources).

What this tests that the first three don't: keyword-strength
discrimination. The decoy is a registry-credentials rotation on the same
service whose diff *also* matches the alert's keyword set (partially) —
both candidates fire diff_keyword_match, and the ranking must separate
them by how many keywords matched plus timing, not by whether the rule
fired at all. This scenario also drove the addition of the "pull" trigger
to the keyword table — the harness surfacing a heuristic coverage gap.
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

_T0 = datetime(2026, 7, 18, 16, 0, 0)

_CULPRIT_DEPLOY_ID = "deploy-f4a3d1"
_DECOY_DEPLOY_ID = "deploy-77ee88"
_ALERT_ID = "alert-image-pull-1"


def build() -> Scenario:
    decoy_deploy = DeployEvent(
        id=_DECOY_DEPLOY_ID,
        service="notifications-service",
        source="github",
        git_sha="77ee88",
        diff_summary={
            "files_changed": ["secrets.yaml"],
            "summary": "rotate container registry credentials",
        },
        deployed_by="lena",
        occurred_at=_T0,
    )
    culprit_deploy = DeployEvent(
        id=_CULPRIT_DEPLOY_ID,
        service="notifications-service",
        source="github",
        git_sha="f4a3d1",
        diff_summary={
            "files_changed": ["deployment.yaml"],
            "summary": "bump image tag to v2.4.1",
        },
        deployed_by="oscar",
        occurred_at=_T0 + timedelta(minutes=20),
    )
    alert = AlertEvent(
        id=_ALERT_ID,
        service="notifications-service",
        title="Deployment replicas unavailable: image pull failure",
        severity="high",
        fired_at=_T0 + timedelta(minutes=22),
    )
    k8s_events = (
        K8sEvent(
            namespace="prod",
            involved_object="notifications-service-8a1b2c-p4r7t",
            reason="ErrImagePull",
            message='Failed to pull image "registry.internal/notifications:v2.4.1": manifest unknown: tag v2.4.1 not found',
            occurred_at=_T0 + timedelta(minutes=20, seconds=40),
        ),
        K8sEvent(
            namespace="prod",
            involved_object="notifications-service-8a1b2c-p4r7t",
            reason="ImagePullBackOff",
            message='Back-off pulling image "registry.internal/notifications:v2.4.1"',
            occurred_at=_T0 + timedelta(minutes=21, seconds=30),
        ),
    )
    git_commit = GitCommit(
        sha="f4a3d1",
        service="notifications-service",
        message="bump image tag to v2.4.1",
        author="oscar",
        files_changed=("deployment.yaml",),
        occurred_at=culprit_deploy.occurred_at,
    )
    edges = (
        ServiceEdge("api-gateway", "notifications-service", "depends_on"),
        ServiceEdge("notifications-service", "template-service", "depends_on"),
    )

    bundle = EvidenceBundle(
        deploys=(decoy_deploy, culprit_deploy),
        alerts=(alert,),
        k8s_events=k8s_events,
        git_commits=(git_commit,),
        service_edges=edges,
    )

    return Scenario(
        id="image_pull_backoff",
        name="ImagePullBackOff after deploy references unpushed image tag",
        description=(
            "A deploy bumps notifications-service to image tag v2.4.1, which "
            "was never pushed to the registry (should have been v2.4.0); "
            "pods immediately fail to pull. The decoy is a same-service "
            "registry-credentials rotation 20 minutes earlier whose diff "
            "partially matches the alert's keywords (registry) — both "
            "candidates fire diff_keyword_match, so the ranking must "
            "discriminate on keyword strength and timing, not rule presence."
        ),
        difficulty=Difficulty.MEDIUM,
        evidence=bundle,
        ground_truth=GroundTruth(
            root_cause_deploy_id=_CULPRIT_DEPLOY_ID,
            explanation="image tag v2.4.1 referenced in deployment.yaml was never pushed; pull fails with manifest unknown.",
        ),
        expected_root_cause=_CULPRIT_DEPLOY_ID,
        expected_evidence_keys=("time_proximity", "diff_keyword_match"),
        expected_confidence_min=0.25,
        expected_rollback="pr_revert:notifications-service:f4a3d1",
        expected_timeline_refs=(_CULPRIT_DEPLOY_ID, _ALERT_ID),
        expected_rule_hits=("time_proximity", "ownership_distance", "diff_keyword_match", "blast_radius_weight"),
    )
