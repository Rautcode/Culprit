"""Scenario: bad rollout — app-level regression among three same-service deploys.

Category: Deployment. Difficulty: hard. Data sources: GitHub deploys +
Prometheus alert + metrics + logs (all Phase 1 sources).

Three firsts. (1) Multiple same-service deploys in the window — time,
ownership, and blast radius are IDENTICAL across all three candidates, so
only diff evidence can discriminate. (2) The culprit is the *middle* deploy:
the regression (broken discount-code validation) sits dormant until a
marketing campaign drives traffic into the broken path 105 minutes later,
so the newest deploy is closest to the alert and time favors the wrong
candidate. (3) No Kubernetes events at all — pods are healthy, containers
run fine; the failure is purely application-level, testing that the
pipeline doesn't silently depend on k8s events existing.

Writing it drove the diff_keyword_match token upgrade: the culprit's
discriminating word is "discount" — a domain word no class-based keyword
table can enumerate — so the rule now also matches salient alert-title
tokens against the diff.
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

_T0 = datetime(2026, 7, 18, 11, 50, 0)

_OLD_DECOY_ID = "deploy-aa0011"
_CULPRIT_DEPLOY_ID = "deploy-d15c07"
_NEW_DECOY_ID = "deploy-bb2233"
_ALERT_ID = "alert-checkout-500s-1"


def build() -> Scenario:
    old_decoy = DeployEvent(
        id=_OLD_DECOY_ID,
        service="checkout-service",
        source="github",
        git_sha="aa0011",
        diff_summary={"files_changed": ["seo/meta.py"], "summary": "update SEO metadata rendering"},
        deployed_by="tomas",
        occurred_at=_T0,
    )
    culprit_deploy = DeployEvent(
        id=_CULPRIT_DEPLOY_ID,
        service="checkout-service",
        source="github",
        git_sha="d15c07",
        diff_summary={
            "files_changed": ["cart/discount.py"],
            "summary": "rework discount code validation in cart flow",
        },
        deployed_by="anika",
        occurred_at=_T0 + timedelta(minutes=10),
    )
    new_decoy = DeployEvent(
        id=_NEW_DECOY_ID,
        service="checkout-service",
        source="github",
        git_sha="bb2233",
        diff_summary={"files_changed": ["clients/payment.py"], "summary": "adjust logging verbosity for payment client"},
        deployed_by="tomas",
        occurred_at=_T0 + timedelta(minutes=75),
    )
    alert = AlertEvent(
        id=_ALERT_ID,
        service="checkout-service",
        title="checkout-service: 500 error rate spike on /cart/discount",
        severity="high",
        fired_at=_T0 + timedelta(minutes=115),
    )
    # Error rate flat through both later deploys — the regression is dormant
    # until the campaign drives traffic into the broken path at ~13:40.
    metrics = tuple(
        MetricSample(
            service="checkout-service",
            metric="http_requests_errors_per_second",
            value=value,
            occurred_at=_T0 + timedelta(minutes=minute),
        )
        for minute, value in ((20, 0.2), (60, 0.3), (90, 0.2), (110, 14.7), (114, 18.2))
    )
    logs = (
        LogEntry(
            service="checkout-service",
            level="error",
            message="DiscountCodeValidationError: legacy code format SUMMER26 rejected by new validator",
            occurred_at=_T0 + timedelta(minutes=111),
        ),
        LogEntry(
            service="checkout-service",
            level="error",
            message="500 on POST /cart/discount: unhandled DiscountCodeValidationError",
            occurred_at=_T0 + timedelta(minutes=112),
        ),
    )
    git_commit = GitCommit(
        sha="d15c07",
        service="checkout-service",
        message="rework discount code validation in cart flow",
        author="anika",
        files_changed=("cart/discount.py",),
        occurred_at=culprit_deploy.occurred_at,
    )
    edges = (
        ServiceEdge("web-frontend", "checkout-service", "depends_on"),
        ServiceEdge("checkout-service", "payments-service", "depends_on"),
    )

    bundle = EvidenceBundle(
        deploys=(old_decoy, culprit_deploy, new_decoy),
        alerts=(alert,),
        metrics=metrics,
        logs=logs,
        git_commits=(git_commit,),
        service_edges=edges,
    )

    return Scenario(
        id="bad_rollout",
        name="Bad rollout — dormant regression among three same-service deploys",
        description=(
            "checkout-service ships three deploys in one afternoon with no "
            "canary. The middle one reworks discount-code validation and "
            "silently rejects legacy code formats; nothing fails until a "
            "marketing campaign (SUMMER26) drives traffic into the broken "
            "path 105 minutes later. All three candidates tie on time-window "
            "presence, ownership, and blast radius, and the newest deploy is "
            "closest to the alert — only the 'discount'/'cart' tokens from "
            "the alert title link the diff to the failure."
        ),
        difficulty=Difficulty.HARD,
        evidence=bundle,
        ground_truth=GroundTruth(
            root_cause_deploy_id=_CULPRIT_DEPLOY_ID,
            explanation="discount validation rework rejects legacy code formats; 500s begin when campaign traffic hits /cart/discount.",
        ),
        expected_root_cause=_CULPRIT_DEPLOY_ID,
        expected_evidence_keys=("diff_keyword_match", "time_proximity"),
        expected_confidence_min=0.19,
        expected_rollback="pr_revert:checkout-service:d15c07",
        expected_timeline_refs=(_CULPRIT_DEPLOY_ID, _ALERT_ID),
        expected_rule_hits=("time_proximity", "ownership_distance", "diff_keyword_match", "blast_radius_weight"),
    )
