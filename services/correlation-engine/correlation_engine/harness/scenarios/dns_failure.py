"""Scenario: cluster DNS config change — shared-infrastructure blast radius.

Category: Network (Phase 2). Difficulty: medium. Data sources: GitHub
deploys + Prometheus alert + logs.

The culprit is a change to cluster-dns (CoreDNS), the purest
shared-infrastructure node yet: three services depend on it and it depends
on nothing. Its blast radius (3 dependents) is the largest in the catalog,
and the dns/resolver keyword class fires for the first time. The decoy is
a same-service checkout deploy landing much closer to the alert — the
same-service + time-proximity combination that beats naive ranking, which
the shared-infra culprit must overcome on ownership + keywords + blast.
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

_T0 = datetime(2026, 7, 20, 15, 0, 0)

_CULPRIT_DEPLOY_ID = "deploy-c0red5"
_DECOY_DEPLOY_ID = "deploy-h3r0e5"
_ALERT_ID = "alert-checkout-dns-1"


def build() -> Scenario:
    culprit_deploy = DeployEvent(
        id=_CULPRIT_DEPLOY_ID,
        service="cluster-dns",
        source="github",
        git_sha="c0red5",
        diff_summary={
            "files_changed": ["coredns/Corefile"],
            "summary": "tighten CoreDNS forward plugin: replace upstream resolver list",
        },
        deployed_by="platform-team",
        occurred_at=_T0,
    )
    decoy_deploy = DeployEvent(
        id=_DECOY_DEPLOY_ID,
        service="checkout-service",
        source="github",
        git_sha="h3r0e5",
        diff_summary={
            "files_changed": ["pages/product.tsx"],
            "summary": "update product page hero images",
        },
        deployed_by="ines",
        occurred_at=_T0 + timedelta(minutes=15),
    )
    alert = AlertEvent(
        id=_ALERT_ID,
        service="checkout-service",
        title="checkout-service: upstream hostname resolution failures (DNS)",
        severity="high",
        fired_at=_T0 + timedelta(minutes=20),
    )
    logs = (
        LogEntry(
            service="checkout-service",
            level="error",
            message="getaddrinfo ENOTFOUND payments.internal — name resolution failed",
            occurred_at=_T0 + timedelta(minutes=18),
        ),
        LogEntry(
            service="cluster-dns",
            level="warn",
            message="forward: no upstream resolvers responded for zone internal.",
            occurred_at=_T0 + timedelta(minutes=17),
        ),
    )
    git_commit = GitCommit(
        sha="c0red5",
        service="cluster-dns",
        message="tighten CoreDNS forward plugin",
        author="platform-team",
        files_changed=("coredns/Corefile",),
        occurred_at=culprit_deploy.occurred_at,
    )
    edges = (
        ServiceEdge("web-frontend", "checkout-service", "depends_on"),
        ServiceEdge("checkout-service", "cluster-dns", "depends_on"),
        ServiceEdge("payments-service", "cluster-dns", "depends_on"),
        ServiceEdge("orders-service", "cluster-dns", "depends_on"),
    )

    bundle = EvidenceBundle(
        deploys=(culprit_deploy, decoy_deploy),
        alerts=(alert,),
        logs=logs,
        git_commits=(git_commit,),
        service_edges=edges,
    )

    return Scenario(
        id="dns_failure",
        name="Cluster DNS config change — shared-infrastructure culprit",
        description=(
            "A CoreDNS Corefile change replaces the upstream resolver list "
            "and internal hostname resolution starts failing. The alert "
            "fires on checkout-service, one hop from cluster-dns — a node "
            "three services depend on. The decoy (a checkout hero-image "
            "deploy) is same-service and five minutes from the alert; the "
            "shared-infra culprit wins on the dns/resolver keyword class, "
            "its 3-dependent blast radius, and graph coupling."
        ),
        difficulty=Difficulty.MEDIUM,
        evidence=bundle,
        ground_truth=GroundTruth(
            root_cause_deploy_id=_CULPRIT_DEPLOY_ID,
            explanation="new upstream resolver list cannot resolve the internal zone; every service resolving internal names through CoreDNS degrades.",
        ),
        expected_root_cause=_CULPRIT_DEPLOY_ID,
        expected_evidence_keys=("diff_keyword_match", "blast_radius_weight"),
        expected_confidence_min=0.25,
        expected_rollback="pr_revert:cluster-dns:c0red5",
        expected_timeline_refs=(_CULPRIT_DEPLOY_ID, _ALERT_ID),
        expected_rule_hits=("time_proximity", "ownership_distance", "diff_keyword_match", "blast_radius_weight"),
    )
