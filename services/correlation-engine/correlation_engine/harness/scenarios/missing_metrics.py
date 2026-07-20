"""Scenario: metrics vanish after a telemetry port rename — the absent-signal alert.

Category: Observability (Phase 2). Difficulty: medium. Data sources:
GitHub deploys + Prometheus alert + logs.

Every prior alert fired because something bad appeared — errors, latency,
restarts. This one fires because data DISAPPEARED: a deploy renames the
metrics port and moves the handler path, Prometheus scrapes fail, and the
absent-target alert triggers. The incident is evidence-light by nature (no
k8s events, no application errors — the service itself is healthy), which
is exactly what makes self-inflicted observability breakage confusing at
3am: everything is green except the monitoring.
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

_T0 = datetime(2026, 7, 20, 19, 0, 0)

_CULPRIT_DEPLOY_ID = "deploy-9464aa"
_DECOY_DEPLOY_ID = "deploy-r4nk3r"
_ALERT_ID = "alert-search-metrics-absent-1"


def build() -> Scenario:
    decoy_deploy = DeployEvent(
        id=_DECOY_DEPLOY_ID,
        service="search-service",
        source="github",
        git_sha="r4nk3r",
        diff_summary={
            "files_changed": ["ranking/boosts.py"],
            "summary": "tune ranking boost weights",
        },
        deployed_by="wei",
        occurred_at=_T0,
    )
    culprit_deploy = DeployEvent(
        id=_CULPRIT_DEPLOY_ID,
        service="search-service",
        source="github",
        git_sha="9464aa",
        diff_summary={
            "files_changed": ["telemetry/server.py", "deployment.yaml"],
            "summary": "rename metrics port 9090 to 9464 and move handler to /telemetry",
        },
        deployed_by="oscar",
        occurred_at=_T0 + timedelta(minutes=31),
    )
    alert = AlertEvent(
        id=_ALERT_ID,
        service="search-service",
        title="search-service: metrics absent — scrape target down",
        severity="high",
        fired_at=_T0 + timedelta(minutes=35),
    )
    logs = (
        LogEntry(
            service="prometheus",
            level="warn",
            message='scrape target search-service:9090/metrics failed: connection refused',
            occurred_at=_T0 + timedelta(minutes=33),
        ),
    )
    git_commit = GitCommit(
        sha="9464aa",
        service="search-service",
        message="rename metrics port and move handler",
        author="oscar",
        files_changed=("telemetry/server.py", "deployment.yaml"),
        occurred_at=culprit_deploy.occurred_at,
    )
    edges = (
        ServiceEdge("web-frontend", "search-service", "depends_on"),
    )

    bundle = EvidenceBundle(
        deploys=(decoy_deploy, culprit_deploy),
        alerts=(alert,),
        logs=logs,
        git_commits=(git_commit,),
        service_edges=edges,
    )

    return Scenario(
        id="missing_metrics",
        name="Metrics absent — telemetry port renamed, service healthy",
        description=(
            "A deploy renames search-service's metrics port (9090 -> 9464) "
            "and moves the handler; Prometheus scrapes hit connection "
            "refused and the absent-target alert fires four minutes later. "
            "The service itself is fully healthy — no errors, no k8s events "
            "— the only casualty is observability. The decoy is an earlier "
            "same-service ranking change with no telemetry keywords."
        ),
        difficulty=Difficulty.MEDIUM,
        evidence=bundle,
        ground_truth=GroundTruth(
            root_cause_deploy_id=_CULPRIT_DEPLOY_ID,
            explanation="scrape config still targets 9090/metrics; the handler now lives on 9464/telemetry, so every scrape fails.",
        ),
        expected_root_cause=_CULPRIT_DEPLOY_ID,
        expected_evidence_keys=("time_proximity", "diff_keyword_match"),
        expected_confidence_min=0.23,
        expected_rollback="pr_revert:search-service:9464aa",
        expected_timeline_refs=(_CULPRIT_DEPLOY_ID, _ALERT_ID),
        expected_rule_hits=("time_proximity", "ownership_distance", "diff_keyword_match", "blast_radius_weight"),
    )
