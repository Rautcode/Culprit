"""Rule Engine — v1.0 frozen rule set (SPEC_VERSION.md "v1.0 Rule Engine").

Five named, independently testable rules. Each is a pure function taking
(alert, deploy, bundle, graph) and returning (score: 0-1, evidence: dict).
No LLM anywhere in this file — see docs/07-ai-architecture.md "Rule Engine".
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from ..harness.schema import AlertEvent, DeployEvent, EvidenceBundle
from ..knowledge_graph import KnowledgeGraph

RuleFn = Callable[[AlertEvent, DeployEvent, EvidenceBundle, KnowledgeGraph], tuple[float, dict]]

TIME_WINDOW_SECONDS = 2 * 60 * 60  # matches the +/-2h evidence-gather window in docs/07-ai-architecture.md

# Naive keyword heuristic for v1 - maps a signal found in the alert title to
# keywords that would appear in a genuinely related diff. Upgrade to
# embedding similarity only if precision on the golden eval set (see
# docs/07-ai-architecture.md "Evaluation") demands it - not before.
# ponytail: this is the ceiling of this rule until real incident data exists
# to justify something smarter.
_KEYWORD_SIGNALS: dict[str, tuple[str, ...]] = {
    "pool": ("pool", "connection", "connectionpool", "maxpoolsize"),
    "memory": ("memory", "limit", "resources", "oom"),
    "crash": ("command", "entrypoint", "image", "readinessprobe", "livenessprobe"),
    "pull": ("image", "tag", "registry", "repository"),
    "timeout": ("timeout", "deadline"),
    "config": ("configmap", "config", "env"),
    "secret": ("secret", "credentials"),
    "dns": ("dns", "resolver", "hostname"),
    "deadlock": ("lock", "transaction", "isolation"),
}


def _keywords_for(alert_title: str) -> tuple[str, ...]:
    title = alert_title.lower()
    hits: list[str] = []
    for trigger, keywords in _KEYWORD_SIGNALS.items():
        if trigger in title:
            hits.extend(keywords)
    return tuple(hits)


def time_proximity(alert: AlertEvent, deploy: DeployEvent, bundle: EvidenceBundle, graph: KnowledgeGraph) -> tuple[float, dict]:
    if deploy.service != alert.service:
        return 0.0, {}
    delta = (alert.fired_at - deploy.occurred_at).total_seconds()
    if delta < 0 or delta > TIME_WINDOW_SECONDS:
        return 0.0, {}
    score = max(0.0, 1 - delta / TIME_WINDOW_SECONDS)
    return score, {"gap_seconds": delta, "deploy_id": deploy.id}


def ownership_distance(alert: AlertEvent, deploy: DeployEvent, bundle: EvidenceBundle, graph: KnowledgeGraph) -> tuple[float, dict]:
    hops = graph.hop_distance(deploy.service, alert.service)
    if hops is None:
        return 0.0, {}
    score = max(0.0, 1 - hops / 3)
    return score, {"hops": hops, "deploy_service": deploy.service, "alert_service": alert.service}


def diff_keyword_match(alert: AlertEvent, deploy: DeployEvent, bundle: EvidenceBundle, graph: KnowledgeGraph) -> tuple[float, dict]:
    keywords = _keywords_for(alert.title)
    if not keywords:
        return 0.0, {}
    diff_text = str(deploy.diff_summary).lower()
    matched = tuple(sorted({kw for kw in keywords if kw in diff_text}))
    if not matched:
        return 0.0, {}
    score = min(1.0, 0.4 * len(matched))
    return score, {"matched_keywords": matched, "deploy_id": deploy.id}


def historical_pattern_match(alert: AlertEvent, deploy: DeployEvent, bundle: EvidenceBundle, graph: KnowledgeGraph) -> tuple[float, dict]:
    # v1: no RAG store wired up yet (build step 6). Always 0 until then -
    # see docs/07-ai-architecture.md "RAG (incident memory)". This rule is
    # defined now so its weight/name exist in confidence breakdowns from
    # day one, not bolted on later.
    return 0.0, {}


def blast_radius_weight(alert: AlertEvent, deploy: DeployEvent, bundle: EvidenceBundle, graph: KnowledgeGraph) -> tuple[float, dict]:
    count = graph.downstream_count(deploy.service)
    if count == 0:
        return 0.0, {}
    score = min(1.0, count / 10)
    return score, {"downstream_count": count, "service": deploy.service}


@dataclass(frozen=True)
class Rule:
    name: str
    weight: float
    evaluate: RuleFn


RULES: tuple[Rule, ...] = (
    Rule("time_proximity", 1.0, time_proximity),
    Rule("ownership_distance", 0.8, ownership_distance),
    Rule("diff_keyword_match", 1.2, diff_keyword_match),
    Rule("historical_pattern_match", 1.0, historical_pattern_match),
    Rule("blast_radius_weight", 0.6, blast_radius_weight),
)

RULE_NAMES: tuple[str, ...] = tuple(rule.name for rule in RULES)
TOTAL_WEIGHT: float = sum(rule.weight for rule in RULES)
