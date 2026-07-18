"""Confidence Scoring — v1.0 frozen formula (SPEC_VERSION.md "v1.0 Confidence Formula").

composite = w_rule * rule_score + w_rag * rag_score + (bounded LLM adjustment)

Until RAG (build step 6) and the LLM reasoning layer (build step 7) exist,
rag_score and llm_calibration are always 0 — meaning the ceiling on
confidence in the harness today is w_rule * rule_score (0.5 max). That's
intentional: it's the mechanical proof that this system cannot claim high
confidence without the evidence RAG/LLM are supposed to add.
"""
from __future__ import annotations

from dataclasses import dataclass

W_RULE = 0.5
W_RAG = 0.3
W_LLM = 0.2
LLM_ADJUSTMENT_BOUND = 0.15  # SPEC_VERSION.md: LLM may adjust the composite by at most +/-0.15


@dataclass(frozen=True)
class ConfidenceBreakdown:
    rule_score: float
    rag_score: float
    llm_calibration: float
    baseline: float
    llm_adjustment: float
    composite: float

    def as_dict(self) -> dict:
        return {
            "rule_score": self.rule_score,
            "rag_score": self.rag_score,
            "llm_calibration": self.llm_calibration,
            "baseline": self.baseline,
            "llm_adjustment": self.llm_adjustment,
            "composite": self.composite,
        }


def compute_confidence(rule_score: float, rag_score: float = 0.0, llm_calibration: float = 0.0) -> ConfidenceBreakdown:
    baseline = W_RULE * rule_score + W_RAG * rag_score
    raw_adjustment = W_LLM * llm_calibration
    llm_adjustment = max(-LLM_ADJUSTMENT_BOUND, min(LLM_ADJUSTMENT_BOUND, raw_adjustment))
    composite = max(0.0, min(1.0, baseline + llm_adjustment))
    return ConfidenceBreakdown(
        rule_score=rule_score,
        rag_score=rag_score,
        llm_calibration=llm_calibration,
        baseline=baseline,
        llm_adjustment=llm_adjustment,
        composite=composite,
    )
