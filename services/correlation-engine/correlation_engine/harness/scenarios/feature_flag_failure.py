"""Scenario: feature flag ramp — a change event with no code artifact at all.

Category: Deployment (Phase 2). Difficulty: medium. Data sources: feature
flag service + GitHub deploys + Prometheus alert + metrics + logs.

The culprit is a flag ramp (0% -> 100%), not a deploy: no git SHA, no
changed files, no rollout — just a console click captured as a change
event. Real incident data says these are among the most commonly missed
causes precisely because most tooling only looks at deploys. The scenario
proves a flag flip competes as a first-class candidate against a real code
deploy on the same service.

expected_rollback documents the ideal action (revert the flag) even though
the v1 remediation allow-list doesn't include flag actions yet — the
allow-list broadens in Phase 4 (docs/10-roadmap.md).
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

_T0 = datetime(2026, 7, 20, 17, 0, 0)

_CULPRIT_DEPLOY_ID = "deploy-f1a6up"
_DECOY_DEPLOY_ID = "deploy-cc0nv3"
_ALERT_ID = "alert-pricing-errors-1"


def build() -> Scenario:
    decoy_deploy = DeployEvent(
        id=_DECOY_DEPLOY_ID,
        service="pricing-service",
        source="github",
        git_sha="cc0nv3",
        diff_summary={
            "files_changed": ["currency/convert.py"],
            "summary": "refactor currency conversion helpers",
        },
        deployed_by="tomas",
        occurred_at=_T0,
    )
    culprit_deploy = DeployEvent(
        id=_CULPRIT_DEPLOY_ID,
        service="pricing-service",
        source="feature_flag",
        git_sha=None,  # a console click, not a commit
        diff_summary={
            "files_changed": [],
            "summary": "ramp flag new-pricing-engine 0% -> 100% for pricing-service",
        },
        deployed_by="lena (flag console)",
        occurred_at=_T0 + timedelta(minutes=42),
    )
    alert = AlertEvent(
        id=_ALERT_ID,
        service="pricing-service",
        title="pricing-service: pricing calculation errors spiking",
        severity="high",
        fired_at=_T0 + timedelta(minutes=45),
    )
    metrics = tuple(
        MetricSample(
            service="pricing-service",
            metric="pricing_calculation_errors_per_second",
            value=value,
            occurred_at=_T0 + timedelta(minutes=minute),
        )
        for minute, value in ((20, 0.1), (40, 0.1), (43, 9.8), (44, 12.4))
    )
    logs = (
        LogEntry(
            service="pricing-service",
            level="error",
            message="PricingEngineError: new-pricing-engine returned negative total for bundle SKUs",
            occurred_at=_T0 + timedelta(minutes=43, seconds=30),
        ),
    )
    git_commit = GitCommit(
        sha="cc0nv3",
        service="pricing-service",
        message="refactor currency conversion helpers",
        author="tomas",
        files_changed=("currency/convert.py",),
        occurred_at=decoy_deploy.occurred_at,
    )
    edges = (
        ServiceEdge("api-gateway", "pricing-service", "depends_on"),
        ServiceEdge("checkout-service", "pricing-service", "depends_on"),
    )

    bundle = EvidenceBundle(
        deploys=(decoy_deploy, culprit_deploy),
        alerts=(alert,),
        metrics=metrics,
        logs=logs,
        git_commits=(git_commit,),
        service_edges=edges,
    )

    return Scenario(
        id="feature_flag_failure",
        name="Feature flag ramp — the change that isn't a deploy",
        description=(
            "The new-pricing-engine flag ramps 0% -> 100% and pricing "
            "errors spike three minutes later: negative totals on bundle "
            "SKUs. The flag flip has no commit, no files, no rollout — the "
            "same-service decoy (a currency refactor deployed 45 minutes "
            "earlier) has all the code artifacts and must still lose to a "
            "console click."
        ),
        difficulty=Difficulty.MEDIUM,
        evidence=bundle,
        ground_truth=GroundTruth(
            root_cause_deploy_id=_CULPRIT_DEPLOY_ID,
            explanation="new-pricing-engine mishandles bundle SKUs; errors begin the moment the ramp reaches full traffic.",
        ),
        expected_root_cause=_CULPRIT_DEPLOY_ID,
        expected_evidence_keys=("time_proximity", "diff_keyword_match"),
        expected_confidence_min=0.23,
        expected_rollback="flag_revert:new-pricing-engine",
        expected_timeline_refs=(_CULPRIT_DEPLOY_ID, _ALERT_ID),
        expected_rule_hits=("time_proximity", "ownership_distance", "diff_keyword_match", "blast_radius_weight"),
    )
