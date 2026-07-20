"""Incident memory — deterministic RAG retrieval over resolved incidents.

Build step 6 (SPEC_VERSION.md). This is the "Learn" end of the core loop
feeding back into "Correlate": each resolved incident is stored as a
structured summary (docs/07-ai-architecture.md "RAG (incident memory)" —
title, root cause, affected service, resolution; never raw logs), and new
incidents retrieve the most similar precedents. It powers both the
historical_pattern_match rule and the rag_score term of the frozen
confidence formula — the mechanism that makes a customer's 50th incident
resolve faster than their 5th.

Precedent scoring is two-sided by design: symptom-to-symptom similarity
(current alerts vs the past incident's alerts) multiplied by
change-to-change similarity (the candidate deploy's diff vs the past
confirmed root cause). The product means shared alert boilerplate alone can
never clear the floor — a lesson enforced by the leave-one-out regression
in test_memory.py, which caught title-vocabulary overlap inflating an
unrelated decoy above a true culprit.

Placement: retrieval is deterministic (pipeline step 5, "deterministic
retrieval, no generation yet"), so it lives in correlation-engine; the
ai-reasoning service will consume the same memory for LLM context
injection in build step 7.

Similarity: bag-of-words cosine, computed in-process. ponytail: this IS
cosine-over-vectors — pgvector + learned embeddings replace the backend
behind the same interface when Postgres lands (Phase 2); upgrade only if
golden-set precision shows lexical overlap missing real matches. Org
scoping is a Postgres-RLS concern, absent here by design.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass

from .harness.schema import Scenario

SIMILARITY_FLOOR = 0.2   # whole-text retrieval below this is noise
PRECEDENT_FLOOR = 0.15   # symptom*change product below this must not score
TOP_K = 3                # docs/07: retrieved precedents are capped at top-3

# Vocabulary shared by virtually every incident text — service-name suffixes
# and generic symptom words. Left in, they dominate cosine similarity and
# manufacture precedent where none exists.
_STOPWORDS = frozenset({
    "and", "after", "critical", "detected", "error", "errors", "failure",
    "failures", "for", "from", "high", "rate", "request", "requests",
    "service", "spike", "spiking", "the", "warning", "with",
})


def _vectorize(text: str) -> Counter:
    return Counter(
        token
        for token in re.findall(r"[a-z0-9]+", text.lower())
        if len(token) >= 3 and token not in _STOPWORDS
    )


def _cosine(a: Counter, b: Counter) -> float:
    if not a or not b:
        return 0.0
    dot = sum(count * b[token] for token, count in a.items())
    norm = math.sqrt(sum(c * c for c in a.values())) * math.sqrt(sum(c * c for c in b.values()))
    return min(1.0, dot / norm) if norm else 0.0


@dataclass(frozen=True)
class ResolvedIncident:
    incident_id: str
    title: str                 # alert title(s) of the incident — the symptom
    culprit_service: str
    root_cause_summary: str    # culprit diff summary + confirmed explanation — the change
    resolution: str            # the action that fixed it, e.g. "helm_rollback:checkout-service:47"

    @classmethod
    def from_scenario(cls, scenario: Scenario) -> "ResolvedIncident":
        """A harness scenario's ground truth is exactly a resolved incident —
        this is how the golden memory gets seeded before real customers exist."""
        culprit = next(
            d for d in scenario.evidence.deploys if d.id == scenario.ground_truth.root_cause_deploy_id
        )
        return cls(
            incident_id=scenario.id,
            title=" ".join(a.title for a in scenario.evidence.alerts),
            culprit_service=culprit.service,
            root_cause_summary=f"{culprit.diff_summary} {scenario.ground_truth.explanation}",
            resolution=scenario.expected_rollback or "manual",
        )

    def text(self) -> str:
        return f"{self.title} {self.culprit_service} {self.root_cause_summary}"


class IncidentMemory:
    def __init__(self) -> None:
        self._incidents: dict[str, tuple[ResolvedIncident, Counter, Counter]] = {}

    def learn(self, incident: ResolvedIncident) -> None:
        self._incidents[incident.incident_id] = (
            incident,
            _vectorize(incident.title),
            _vectorize(f"{incident.culprit_service} {incident.root_cause_summary}"),
        )

    def learn_from_scenario(self, scenario: Scenario) -> None:
        self.learn(ResolvedIncident.from_scenario(scenario))

    def __len__(self) -> int:
        return len(self._incidents)

    def match(self, symptom_text: str, change_text: str, k: int = TOP_K) -> list[tuple[float, ResolvedIncident]]:
        """Precedent score = symptom similarity x change similarity, so a
        match requires the alert to resemble a past alert AND the candidate
        change to resemble that incident's confirmed root cause. Below
        PRECEDENT_FLOOR is dropped — false precedent is worse than none."""
        symptom_vector = _vectorize(symptom_text)
        change_vector = _vectorize(change_text)
        scored = sorted(
            (
                (_cosine(symptom_vector, title_vec) * _cosine(change_vector, cause_vec), incident)
                for incident, title_vec, cause_vec in self._incidents.values()
            ),
            key=lambda pair: pair[0],
            reverse=True,
        )
        return [(score, incident) for score, incident in scored[:k] if score >= PRECEDENT_FLOOR]

    def most_similar(self, query: str, k: int = TOP_K) -> list[tuple[float, ResolvedIncident]]:
        """Whole-text retrieval (used for generic lookup and, later, LLM
        context injection) — one-sided, so gated by the higher floor."""
        query_vector = _vectorize(query)
        scored = sorted(
            (
                (_cosine(query_vector, _vectorize(incident.text())), incident)
                for incident, _, _ in self._incidents.values()
            ),
            key=lambda pair: pair[0],
            reverse=True,
        )
        return [(similarity, incident) for similarity, incident in scored[:k] if similarity >= SIMILARITY_FLOOR]
