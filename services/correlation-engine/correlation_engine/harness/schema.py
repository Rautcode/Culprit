"""Incident Simulation Harness — evidence and scenario contracts.

A Scenario is a fully synthetic, deterministic bundle of evidence (deploys,
alerts, logs, metrics, traces, k8s events, git commits, helm releases,
terraform changes, service topology) plus a ground truth and a set of
expectations. No live cluster and no AI is involved in producing or scoring
a scenario — see docs/07-ai-architecture.md and SPEC_VERSION.md "v1.0
Architecture": the harness proves the deterministic layers (Rule Engine +
Knowledge Graph) before anything touches an LLM.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class Difficulty(str, Enum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


@dataclass(frozen=True)
class DeployEvent:
    id: str
    service: str
    source: str  # github|argocd|terraform|helm
    git_sha: str | None
    diff_summary: dict
    deployed_by: str
    occurred_at: datetime


@dataclass(frozen=True)
class AlertEvent:
    id: str
    service: str
    title: str
    severity: str
    fired_at: datetime


@dataclass(frozen=True)
class LogEntry:
    service: str
    level: str
    message: str
    occurred_at: datetime


@dataclass(frozen=True)
class MetricSample:
    service: str
    metric: str
    value: float
    occurred_at: datetime


@dataclass(frozen=True)
class TraceSpan:
    service: str
    operation: str
    duration_ms: float
    error: bool
    occurred_at: datetime


@dataclass(frozen=True)
class K8sEvent:
    namespace: str
    involved_object: str
    reason: str
    message: str
    occurred_at: datetime


@dataclass(frozen=True)
class GitCommit:
    sha: str
    service: str
    message: str
    author: str
    files_changed: tuple[str, ...]
    occurred_at: datetime


@dataclass(frozen=True)
class HelmRelease:
    service: str
    revision: int
    values_diff: dict
    occurred_at: datetime


@dataclass(frozen=True)
class TerraformChange:
    resource: str
    action: str  # create|update|delete
    diff: dict
    occurred_at: datetime


@dataclass(frozen=True)
class ServiceEdge:
    from_service: str
    to_service: str
    edge_type: str  # depends_on|owned_by|deployed_via|shares_namespace


@dataclass(frozen=True)
class EvidenceBundle:
    """Everything the deterministic pipeline is allowed to see. Mirrors the
    real evidence sources named in docs/03-architecture.md; in production
    each list here is populated from Postgres/Loki/the Collector agent, in
    the harness it's authored by hand per scenario."""

    deploys: tuple[DeployEvent, ...] = field(default_factory=tuple)
    alerts: tuple[AlertEvent, ...] = field(default_factory=tuple)
    logs: tuple[LogEntry, ...] = field(default_factory=tuple)
    metrics: tuple[MetricSample, ...] = field(default_factory=tuple)
    traces: tuple[TraceSpan, ...] = field(default_factory=tuple)
    k8s_events: tuple[K8sEvent, ...] = field(default_factory=tuple)
    git_commits: tuple[GitCommit, ...] = field(default_factory=tuple)
    helm_releases: tuple[HelmRelease, ...] = field(default_factory=tuple)
    terraform_changes: tuple[TerraformChange, ...] = field(default_factory=tuple)
    service_edges: tuple[ServiceEdge, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class GroundTruth:
    root_cause_deploy_id: str
    explanation: str


@dataclass(frozen=True)
class Scenario:
    """The regression-suite unit. Every field below is required — a
    scenario without an explicit expectation isn't a test, it's a fixture."""

    id: str
    name: str
    description: str
    difficulty: Difficulty
    evidence: EvidenceBundle
    ground_truth: GroundTruth
    expected_root_cause: str                    # deploy id the pipeline must rank #1
    expected_evidence_keys: tuple[str, ...]      # rule names whose evidence must be citable
    expected_confidence_min: float               # floor, not a target — see confidence.py
    expected_rollback: str | None                # e.g. "helm_rollback:checkout-service:47"
    expected_timeline_refs: tuple[str, ...]      # event refs that must appear, in order
    expected_rule_hits: tuple[str, ...]          # rule names expected to fire for the top candidate
