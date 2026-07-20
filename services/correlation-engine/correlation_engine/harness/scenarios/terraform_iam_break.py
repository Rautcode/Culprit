"""Scenario: Terraform change revokes IAM permissions — delayed cross-layer failure.

Category: Infrastructure (Phase 2). Difficulty: medium. Data sources:
Terraform + GitHub deploys + Prometheus alert + logs.

First scenario with a Terraform-sourced culprit and the first to exercise
TerraformChange evidence end to end (bundle -> timeline). The cross-layer
shape is what makes IAM breaks hard in real life: an infrastructure change
surfaces as an application symptom, and the effect is DELAYED — the revoked
permission only bites when the service's cached credentials refresh, 50
minutes after apply. A same-service code deploy lands much closer to the
alert; time proximity favors it, and the diff keyword evidence
(access/object against the AccessDenied alert) must pull the Terraform
change back to the top.
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
    TerraformChange,
)

_T0 = datetime(2026, 7, 20, 9, 0, 0)

_CULPRIT_DEPLOY_ID = "deploy-a1m901"
_DECOY_DEPLOY_ID = "deploy-7humb5"
_ALERT_ID = "alert-uploads-access-denied-1"
_TF_RESOURCE = "aws_iam_role_policy.uploads_service"


def build() -> Scenario:
    culprit_deploy = DeployEvent(
        id=_CULPRIT_DEPLOY_ID,
        service="uploads-service",
        source="terraform",
        git_sha="a1m901",
        diff_summary={
            "files_changed": ["iam/uploads_role.tf"],
            "summary": "remove s3:GetObject and s3:ListBucket access from uploads-service role",
        },
        deployed_by="terraform-apply (pr #412)",
        occurred_at=_T0,
    )
    decoy_deploy = DeployEvent(
        id=_DECOY_DEPLOY_ID,
        service="uploads-service",
        source="github",
        git_sha="7humb5",
        diff_summary={
            "files_changed": ["thumbnails/generate.py"],
            "summary": "add thumbnail generation for image previews",
        },
        deployed_by="marta",
        occurred_at=_T0 + timedelta(minutes=40),
    )
    alert = AlertEvent(
        id=_ALERT_ID,
        service="uploads-service",
        title="uploads-service: S3 access denied (AccessDenied) on object downloads",
        severity="high",
        fired_at=_T0 + timedelta(minutes=50),
    )
    terraform_changes = (
        TerraformChange(
            resource=_TF_RESOURCE,
            action="update",
            diff={"statement.actions": {"removed": ["s3:GetObject", "s3:ListBucket"]}},
            occurred_at=_T0,
        ),
    )
    logs = (
        LogEntry(
            service="uploads-service",
            level="error",
            message="botocore.exceptions.ClientError: AccessDenied when calling GetObject on uploads-prod bucket",
            occurred_at=_T0 + timedelta(minutes=49),
        ),
    )
    git_commit = GitCommit(
        sha="a1m901",
        service="uploads-service",
        message="tighten uploads role to least privilege",
        author="devon",
        files_changed=("iam/uploads_role.tf",),
        occurred_at=culprit_deploy.occurred_at,
    )
    edges = (
        ServiceEdge("web-frontend", "uploads-service", "depends_on"),
        ServiceEdge("uploads-service", "media-store", "depends_on"),
    )

    bundle = EvidenceBundle(
        deploys=(culprit_deploy, decoy_deploy),
        alerts=(alert,),
        logs=logs,
        git_commits=(git_commit,),
        terraform_changes=terraform_changes,
        service_edges=edges,
    )

    return Scenario(
        id="terraform_iam_break",
        name="Terraform IAM revoke — delayed cross-layer failure",
        description=(
            "A least-privilege cleanup removes s3:GetObject from "
            "uploads-service's IAM role. Nothing fails until the service's "
            "cached credentials refresh 50 minutes later, when downloads "
            "start returning AccessDenied. A same-service code deploy "
            "(thumbnail generation) lands 10 minutes before the alert — "
            "time proximity favors it; the access/object keyword evidence "
            "must pull the Terraform change back to rank one."
        ),
        difficulty=Difficulty.MEDIUM,
        evidence=bundle,
        ground_truth=GroundTruth(
            root_cause_deploy_id=_CULPRIT_DEPLOY_ID,
            explanation="s3:GetObject revoked from the uploads role; AccessDenied begins at the next credential refresh, ~50 min after apply.",
        ),
        expected_root_cause=_CULPRIT_DEPLOY_ID,
        expected_evidence_keys=("diff_keyword_match", "time_proximity"),
        expected_confidence_min=0.24,
        expected_rollback="pr_revert:uploads-service:a1m901",
        expected_timeline_refs=(_CULPRIT_DEPLOY_ID, _ALERT_ID, _TF_RESOURCE),
        expected_rule_hits=("time_proximity", "ownership_distance", "diff_keyword_match", "blast_radius_weight"),
    )
