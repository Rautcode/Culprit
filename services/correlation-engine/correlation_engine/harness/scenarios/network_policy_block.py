"""Scenario: NetworkPolicy hardening blocks a legitimate caller.

Category: Network (Phase 2). Difficulty: medium. Data sources: ArgoCD
policy-as-code + GitHub deploys + Prometheus alert + logs.

Coverage scenario, honestly labeled: the coupling shape (alert one hop
downstream of the true cause) is already guarded by bad_configmap and
terraform_drift — this row exists because security-hardening lockouts are
a distinct, recurring incident class whose vocabulary (NetworkPolicy,
ingress selectors, connection refused) belongs in the catalog and the
incident memory. The distinct data profile: an IMMEDIATE, TOTAL failure —
connection refused the instant the policy applies, unlike terraform_drift's
slow timeout onset — caused by policy-as-code that is correct YAML doing
exactly what it says; the bug is that checkout's pods lack the new label.
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

_T0 = datetime(2026, 7, 21, 14, 0, 0)

_CULPRIT_DEPLOY_ID = "deploy-n37p01"
_DECOY_DEPLOY_ID = "deploy-3mp7y5"
_ALERT_ID = "alert-checkout-refused-1"


def build() -> Scenario:
    decoy_deploy = DeployEvent(
        id=_DECOY_DEPLOY_ID,
        service="checkout-service",
        source="github",
        git_sha="3mp7y5",
        diff_summary={
            "files_changed": ["cart/empty_state.tsx"],
            "summary": "improve cart empty-state illustration",
        },
        deployed_by="marta",
        occurred_at=_T0 + timedelta(minutes=10),
    )
    culprit_deploy = DeployEvent(
        id=_CULPRIT_DEPLOY_ID,
        service="payments-service",
        source="argocd",
        git_sha="n37p01",
        diff_summary={
            "files_changed": ["policies/payments-netpol.yaml"],
            "summary": "restrict payments ingress NetworkPolicy to pods labeled part-of=payments",
        },
        deployed_by="argocd-sync (security-hardening pr #533)",
        occurred_at=_T0 + timedelta(minutes=25),
    )
    alert = AlertEvent(
        id=_ALERT_ID,
        service="checkout-service",
        title="checkout-service: connection refused to payments-service upstream",
        severity="critical",
        fired_at=_T0 + timedelta(minutes=30),
    )
    logs = (
        LogEntry(
            service="checkout-service",
            level="error",
            message="ECONNREFUSED payments.internal:8443 — 100% of payment authorizations failing",
            occurred_at=_T0 + timedelta(minutes=27),
        ),
        LogEntry(
            service="payments-service",
            level="info",
            message="NetworkPolicy payments-ingress applied: ingress now requires label part-of=payments",
            occurred_at=_T0 + timedelta(minutes=25, seconds=20),
        ),
    )
    git_commit = GitCommit(
        sha="n37p01",
        service="payments-service",
        message="harden payments namespace ingress policy",
        author="security-team",
        files_changed=("policies/payments-netpol.yaml",),
        occurred_at=culprit_deploy.occurred_at,
    )
    edges = (
        ServiceEdge("web-frontend", "checkout-service", "depends_on"),
        ServiceEdge("checkout-service", "payments-service", "depends_on"),
    )

    bundle = EvidenceBundle(
        deploys=(decoy_deploy, culprit_deploy),
        alerts=(alert,),
        logs=logs,
        git_commits=(git_commit,),
        service_edges=edges,
    )

    return Scenario(
        id="network_policy_block",
        name="NetworkPolicy hardening blocks a legitimate caller",
        description=(
            "A security-hardening PR restricts payments-namespace ingress "
            "to pods carrying a new label; checkout's pods don't carry it, "
            "and 100% of payment authorizations fail with connection "
            "refused the moment the policy syncs. The alert fires on "
            "checkout, one hop downstream of the policy change. The YAML is "
            "correct and does exactly what it says — the failure is a "
            "missing label on the caller. The decoy is a checkout frontend "
            "deploy 20 minutes before the alert."
        ),
        difficulty=Difficulty.MEDIUM,
        evidence=bundle,
        ground_truth=GroundTruth(
            root_cause_deploy_id=_CULPRIT_DEPLOY_ID,
            explanation="new ingress selector requires part-of=payments; checkout's pods lack the label, so every connection is refused at the CNI layer.",
        ),
        expected_root_cause=_CULPRIT_DEPLOY_ID,
        expected_evidence_keys=("ownership_distance", "diff_keyword_match"),
        expected_confidence_min=0.2,
        expected_rollback="pr_revert:payments-service:n37p01",
        expected_timeline_refs=(_CULPRIT_DEPLOY_ID, _ALERT_ID),
        expected_rule_hits=("time_proximity", "ownership_distance", "diff_keyword_match", "blast_radius_weight"),
    )
