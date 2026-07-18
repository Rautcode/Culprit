"""The deterministic pipeline — steps 2-4 of docs/07-ai-architecture.md
"Agent architecture" (Evidence -> Knowledge Graph -> Rule Engine), stopping
before RAG/LLM (steps 5-6), which don't exist yet. This is what the
Incident Simulation Harness runs a Scenario through.
"""
from __future__ import annotations

from dataclasses import dataclass

from .harness.schema import EvidenceBundle, Scenario
from .knowledge_graph import KnowledgeGraph
from .ranking.confidence import ConfidenceBreakdown, compute_confidence
from .ranking.rules import RULES, TOTAL_WEIGHT


@dataclass(frozen=True)
class RCACandidate:
    deploy_id: str
    rule_score: float
    rule_hits: tuple[str, ...]
    evidence: dict
    confidence: ConfidenceBreakdown


@dataclass(frozen=True)
class RCAResult:
    candidates: tuple[RCACandidate, ...]  # ranked, highest confidence first
    timeline: tuple[dict, ...]

    @property
    def top_candidate(self) -> RCACandidate | None:
        return self.candidates[0] if self.candidates else None


def build_timeline(bundle: EvidenceBundle) -> tuple[dict, ...]:
    events: list[dict] = []
    events += [{"type": "deploy", "occurred_at": d.occurred_at, "ref": d.id} for d in bundle.deploys]
    events += [{"type": "alert", "occurred_at": a.fired_at, "ref": a.id} for a in bundle.alerts]
    events += [{"type": "k8s_event", "occurred_at": k.occurred_at, "ref": k.reason} for k in bundle.k8s_events]
    events += [{"type": "git_commit", "occurred_at": g.occurred_at, "ref": g.sha} for g in bundle.git_commits]
    events += [{"type": "helm_release", "occurred_at": h.occurred_at, "ref": f"rev{h.revision}"} for h in bundle.helm_releases]
    events += [{"type": "terraform_change", "occurred_at": t.occurred_at, "ref": t.resource} for t in bundle.terraform_changes]
    events.sort(key=lambda e: e["occurred_at"])
    return tuple(events)


def rank_candidates(bundle: EvidenceBundle, graph: KnowledgeGraph) -> tuple[RCACandidate, ...]:
    if not bundle.alerts:
        return ()
    alert = bundle.alerts[0]  # v1: single-alert scenarios only

    candidates = []
    for deploy in bundle.deploys:
        hits: list[str] = []
        evidence: dict = {}
        weighted_total = 0.0
        for rule in RULES:
            score, rule_evidence = rule.evaluate(alert, deploy, bundle, graph)
            if score > 0:
                hits.append(rule.name)
                evidence[rule.name] = rule_evidence
            weighted_total += score * rule.weight
        rule_score = min(weighted_total / TOTAL_WEIGHT, 1.0) if TOTAL_WEIGHT else 0.0
        confidence = compute_confidence(rule_score=rule_score)
        candidates.append(
            RCACandidate(
                deploy_id=deploy.id,
                rule_score=rule_score,
                rule_hits=tuple(hits),
                evidence=evidence,
                confidence=confidence,
            )
        )

    return tuple(sorted(candidates, key=lambda c: c.confidence.composite, reverse=True))


def run_scenario(scenario: Scenario) -> RCAResult:
    graph = KnowledgeGraph.from_edges(scenario.evidence.service_edges)
    candidates = rank_candidates(scenario.evidence, graph)
    timeline = build_timeline(scenario.evidence)
    return RCAResult(candidates=candidates, timeline=timeline)
