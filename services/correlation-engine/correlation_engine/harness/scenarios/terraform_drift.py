"""Scenario: Terraform drift — an out-of-band console change with NO git commit.

Category: Infrastructure (Phase 2). Difficulty: hard. Data sources:
Terraform drift detection + GitHub deploys + Prometheus alert + logs.

The defining property of drift: the change never went through version
control. The culprit change event has no git SHA, no files_changed, no
corresponding GitCommit anywhere in the evidence — someone edited a
security group in the AWS console. This is the first scenario proving the
pipeline ranks correctly when the strongest evidence types (commits,
diffs-from-PRs) simply don't exist for the true cause, and the alert fires
one dependency hop downstream of it (payments-service alerts; the drifted
resource belongs to payments-db).

expected_rollback is None deliberately: the v1 remediation allow-list
(helm_rollback / pr_revert / scale_deployment) has no terraform-reapply
action — drift remediation is surfaced as a manual step until the action
set is broadened (docs/10-roadmap.md, Phase 4).
"""
from __future__ import annotations

from datetime import datetime, timedelta

from ..schema import (
    AlertEvent,
    DeployEvent,
    Difficulty,
    EvidenceBundle,
    GroundTruth,
    LogEntry,
    Scenario,
    ServiceEdge,
    TerraformChange,
)

_T0 = datetime(2026, 7, 20, 13, 0, 0)

_CULPRIT_DEPLOY_ID = "deploy-dr1f7d"
_DECOY_DEPLOY_ID = "deploy-1nv01c"
_ALERT_ID = "alert-payments-db-timeouts-1"
_TF_RESOURCE = "aws_security_group.payments_db"


def build() -> Scenario:
    decoy_deploy = DeployEvent(
        id=_DECOY_DEPLOY_ID,
        service="payments-service",
        source="github",
        git_sha="1nv01c",
        diff_summary={
            "files_changed": ["emails/invoice.html"],
            "summary": "restructure invoice email templates",
        },
        deployed_by="noor",
        occurred_at=_T0 + timedelta(minutes=13),
    )
    culprit_deploy = DeployEvent(
        id=_CULPRIT_DEPLOY_ID,
        service="payments-db",
        source="terraform",
        git_sha=None,  # drift: the change never touched version control
        diff_summary={
            "files_changed": [],
            "summary": "drift detected: security group ingress rule removed — postgres 5432 database access from payments subnet",
        },
        deployed_by="out-of-band (console)",
        occurred_at=_T0 + timedelta(minutes=30),
    )
    alert = AlertEvent(
        id=_ALERT_ID,
        service="payments-service",
        title="payments-service: database connection timeouts spiking",
        severity="critical",
        fired_at=_T0 + timedelta(minutes=38),
    )
    terraform_changes = (
        TerraformChange(
            resource=_TF_RESOURCE,
            action="update",
            diff={"ingress": {"removed": {"port": 5432, "source": "payments-subnet"}}},
            occurred_at=culprit_deploy.occurred_at,
        ),
    )
    logs = (
        LogEntry(
            service="payments-service",
            level="error",
            message="psycopg2.OperationalError: connection to payments-db timed out (10s)",
            occurred_at=_T0 + timedelta(minutes=36, seconds=30),
        ),
    )
    edges = (
        ServiceEdge("checkout-service", "payments-service", "depends_on"),
        ServiceEdge("payments-service", "payments-db", "depends_on"),
        ServiceEdge("billing-service", "payments-db", "depends_on"),
    )

    bundle = EvidenceBundle(
        deploys=(decoy_deploy, culprit_deploy),
        alerts=(alert,),
        logs=logs,
        terraform_changes=terraform_changes,
        service_edges=edges,
    )

    return Scenario(
        id="terraform_drift",
        name="Terraform drift — console change with no commit trail",
        description=(
            "Someone tightens payments-db's security group in the AWS "
            "console; the drift detector captures the delta. Five-minute-old "
            "connections start timing out and payments-service alerts — one "
            "hop downstream of the drifted resource. The true cause has no "
            "git SHA, no changed files, and no commit in evidence; the decoy "
            "(a same-service email-template deploy) has all three and must "
            "still lose."
        ),
        difficulty=Difficulty.HARD,
        evidence=bundle,
        ground_truth=GroundTruth(
            root_cause_deploy_id=_CULPRIT_DEPLOY_ID,
            explanation="ingress rule for postgres 5432 removed out-of-band; payments-service connections to payments-db time out.",
        ),
        expected_root_cause=_CULPRIT_DEPLOY_ID,
        expected_evidence_keys=("ownership_distance", "diff_keyword_match"),
        expected_confidence_min=0.2,
        expected_rollback=None,
        expected_timeline_refs=(_CULPRIT_DEPLOY_ID, _ALERT_ID, _TF_RESOURCE),
        expected_rule_hits=("time_proximity", "ownership_distance", "diff_keyword_match", "blast_radius_weight"),
    )
