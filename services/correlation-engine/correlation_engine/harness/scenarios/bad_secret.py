"""Scenario: bad JWT secret rotation on a shared dependency — alert two hops away.

Category: Kubernetes. Difficulty: hard. Data sources: GitHub deploys +
Kubernetes events + Prometheus alert + logs (all Phase 1 sources).

Two firsts. (1) The culprit is TWO dependency hops from the alerting
service (api-gateway -> user-service -> auth-service), exercising graded
hop scoring and traversal depth — prior scenarios only covered 0 and 1
hops. (2) Graph distance favors the *decoy* for the first time: the decoy
deploy sits at 1 hop, closer than the culprit's 2 — but auth-service is a
classic shared dependency (depends on nothing, depended on by everything),
so the fixed blast_radius_weight plus keyword evidence must overcome the
ownership deficit. Writing this scenario exposed the blast-radius direction
bug (it counted the deployer's dependencies instead of its dependents,
scoring auth-type services at zero); this scenario is its permanent
regression guard.
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

_T0 = datetime(2026, 7, 18, 21, 0, 0)

_CULPRIT_DEPLOY_ID = "deploy-5ec4e7"
_DECOY_DEPLOY_ID = "deploy-22ff11"
_ALERT_ID = "alert-auth-401-spike-1"


def build() -> Scenario:
    decoy_deploy = DeployEvent(
        id=_DECOY_DEPLOY_ID,
        service="user-service",
        source="github",
        git_sha="22ff11",
        diff_summary={"files_changed": ["profile/query.py"], "summary": "optimize profile query caching"},
        deployed_by="ravi",
        occurred_at=_T0 + timedelta(minutes=24),
    )
    culprit_deploy = DeployEvent(
        id=_CULPRIT_DEPLOY_ID,
        service="auth-service",
        source="github",
        git_sha="5ec4e7",
        diff_summary={
            "files_changed": ["secrets/jwt-signing-key.yaml"],
            "summary": "rotate JWT signing secret for auth-service",
        },
        deployed_by="ines",
        occurred_at=_T0 + timedelta(minutes=50),
    )
    alert = AlertEvent(
        id=_ALERT_ID,
        service="api-gateway",
        title="api-gateway: 401 spike after token secret validation failures",
        severity="critical",
        fired_at=_T0 + timedelta(minutes=54),
    )
    k8s_events = (
        K8sEvent(
            namespace="prod",
            involved_object="auth-service-4f8e2a-h6k9m",
            reason="Killing",
            message="Stopping container auth (rolling update after secret checksum change)",
            occurred_at=_T0 + timedelta(minutes=50, seconds=15),
        ),
        K8sEvent(
            namespace="prod",
            involved_object="auth-service-4f8e2a-t3w5y",
            reason="Started",
            message="Started container auth",
            occurred_at=_T0 + timedelta(minutes=50, seconds=50),
        ),
    )
    logs = (
        LogEntry(
            service="auth-service",
            level="info",
            message="loaded signing key from secret auth-jwt-key (version 2)",
            occurred_at=_T0 + timedelta(minutes=51),
        ),
        LogEntry(
            service="api-gateway",
            level="error",
            message="token validation failed: JWT signature mismatch (kid=v1 not found in keyset)",
            occurred_at=_T0 + timedelta(minutes=53, seconds=30),
        ),
    )
    git_commit = GitCommit(
        sha="5ec4e7",
        service="auth-service",
        message="rotate JWT signing secret",
        author="ines",
        files_changed=("secrets/jwt-signing-key.yaml",),
        occurred_at=culprit_deploy.occurred_at,
    )
    edges = (
        ServiceEdge("api-gateway", "user-service", "depends_on"),
        ServiceEdge("user-service", "auth-service", "depends_on"),
    )

    bundle = EvidenceBundle(
        deploys=(decoy_deploy, culprit_deploy),
        alerts=(alert,),
        k8s_events=k8s_events,
        logs=logs,
        git_commits=(git_commit,),
        service_edges=edges,
    )

    return Scenario(
        id="bad_secret",
        name="Bad JWT secret rotation on a shared dependency (two-hop alert)",
        description=(
            "auth-service rotates its JWT signing secret, but tokens issued "
            "under the old key are still in flight and the gateway's cached "
            "keyset no longer validates them — 401s spike at api-gateway, "
            "two dependency hops from the cause. The decoy (a user-service "
            "query optimization) sits only one hop away, so graph distance "
            "favors the decoy; auth's blast radius as a shared dependency "
            "plus the secret keyword evidence must overcome it."
        ),
        difficulty=Difficulty.HARD,
        evidence=bundle,
        ground_truth=GroundTruth(
            root_cause_deploy_id=_CULPRIT_DEPLOY_ID,
            explanation="JWT signing secret rotated without key-rollover overlap; in-flight tokens and cached keysets fail validation gateway-wide.",
        ),
        expected_root_cause=_CULPRIT_DEPLOY_ID,
        expected_evidence_keys=("ownership_distance", "diff_keyword_match", "blast_radius_weight"),
        expected_confidence_min=0.18,
        expected_rollback="pr_revert:auth-service:5ec4e7",
        expected_timeline_refs=(_CULPRIT_DEPLOY_ID, _ALERT_ID),
        expected_rule_hits=("time_proximity", "ownership_distance", "diff_keyword_match", "blast_radius_weight"),
    )
