"""LLM Explanation Layer — build step 7 (SPEC_VERSION.md).

The LLM's role, per the frozen architecture: explain, calibrate, recommend —
never invent. Input is the deterministic pipeline's finished output (ranked
candidates with cited evidence); output is a prose explanation, a bounded
confidence calibration, and citations that MUST map to evidence objects the
deterministic layer actually produced.

Guardrails, in the order they apply:
1. No candidates -> no model call at all (cost guardrail; the deterministic
   answer "no recent change detected" needs no explanation).
2. Malformed model output -> graceful fallback to a deterministic summary;
   the pipeline's answer is never lost because a model call failed.
3. A top_candidate_id naming a non-existent candidate -> overridden to the
   deterministic top; calibration zeroed (the model tried to invent).
4. Every citation validated against real evidence refs; invalid ones are
   stripped and calibration is zeroed — the mechanical enforcement of
   "the LLM explains, it doesn't invent" (docs/07, "Evidence grounding").
5. Calibration clamped to [-1, 1] before entering compute_confidence, which
   itself caps the LLM's effect on the composite at +/-0.15 (frozen formula).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

from correlation_engine.pipeline import RCAResult
from correlation_engine.ranking.confidence import ConfidenceBreakdown, compute_confidence

SYSTEM_PROMPT = """You are the explanation layer of an incident root-cause-analysis pipeline.
A deterministic rule engine and knowledge graph have already ranked candidate deploys
with cited evidence. Your job is to EXPLAIN that output to an on-call engineer:
why the top candidate is likely the cause, what the evidence shows, and how confident
to be. You must not invent evidence, candidates, or facts not present in the input.

Respond with ONLY a JSON object, no other text:
{
  "explanation": "<2-5 sentences for an on-call engineer>",
  "top_candidate_id": "<the deploy id you judge most likely, from the given candidates>",
  "calibration": <float in [-1, 1]; your confidence adjustment relative to the deterministic score>,
  "citations": ["<evidence refs from the provided valid_refs list that support your explanation>"]
}"""


@dataclass(frozen=True)
class Explanation:
    narrative: str
    top_candidate_id: str
    calibration: float          # post-guardrail value that entered the formula
    citations: tuple[str, ...]  # validated only
    stripped_citations: tuple[str, ...] = ()
    grounded: bool = True       # False when output was malformed or citations were stripped
    confidence: ConfidenceBreakdown | None = None  # recalibrated composite for the top candidate


def valid_refs(result: RCAResult) -> set[str]:
    """Everything the model is allowed to cite: rule names that fired,
    candidate deploy ids, timeline refs, and retrieved incident ids."""
    refs: set[str] = set()
    for candidate in result.candidates:
        refs.add(candidate.deploy_id)
        for key, value in candidate.evidence.items():
            refs.add(key)
            if key == "historical_pattern_match":
                refs.add(value["incident_id"])
            if key == "similar_past_incidents":
                refs.update(match["incident_id"] for match in value)
    refs.update(event["ref"] for event in result.timeline)
    return refs


def build_prompt(result: RCAResult) -> str:
    payload = {
        "candidates": [
            {
                "deploy_id": c.deploy_id,
                "rule_hits": c.rule_hits,
                "evidence": c.evidence,
                "confidence": c.confidence.as_dict(),
            }
            for c in result.candidates
        ],
        "timeline": result.timeline,
        "valid_refs": sorted(valid_refs(result)),
    }
    return json.dumps(payload, default=str)


def _fallback(result: RCAResult, reason: str) -> Explanation:
    top = result.top_candidate
    return Explanation(
        narrative=(
            f"Deterministic analysis ranks {top.deploy_id} first "
            f"(confidence {top.confidence.composite:.2f}; rules fired: {', '.join(top.rule_hits)}). "
            f"LLM explanation unavailable: {reason}."
        ),
        top_candidate_id=top.deploy_id,
        calibration=0.0,
        citations=(),
        grounded=False,
        confidence=top.confidence,
    )


def explain(result: RCAResult, model) -> Explanation | None:
    if not result.candidates:
        return None  # nothing to explain; no model call

    # Broad catch is deliberate: the contract is that ANY model failure —
    # network, timeout, rate limit, auth, refusal — degrades to the
    # deterministic verdict rather than crashing the caller (the "the
    # deterministic answer stands alone" principle, docs/07).
    try:
        raw = model.complete(SYSTEM_PROMPT, build_prompt(result))
    except Exception as exc:  # noqa: BLE001 — see comment above
        return _fallback(result, f"model call failed ({type(exc).__name__})")
    try:
        parsed = json.loads(raw)
        narrative = str(parsed["explanation"])
        claimed_top = str(parsed["top_candidate_id"])
        calibration = float(parsed.get("calibration", 0.0))
        claimed_citations = [str(c) for c in parsed.get("citations", [])]
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        return _fallback(result, f"unparseable model output ({type(exc).__name__})")

    grounded = True

    # Guardrail: the model reorders/explains among REAL candidates only.
    candidate_ids = {c.deploy_id for c in result.candidates}
    if claimed_top not in candidate_ids:
        claimed_top = result.top_candidate.deploy_id
        calibration = 0.0
        grounded = False

    # Guardrail: evidence grounding — strip citations that don't map to a
    # real evidence object; any stripping zeroes the model's calibration.
    refs = valid_refs(result)
    citations = tuple(c for c in claimed_citations if c in refs)
    stripped = tuple(c for c in claimed_citations if c not in refs)
    if stripped:
        calibration = 0.0
        grounded = False

    calibration = max(-1.0, min(1.0, calibration))

    top = next(c for c in result.candidates if c.deploy_id == claimed_top)
    confidence = compute_confidence(
        rule_score=top.confidence.rule_score,
        rag_score=top.confidence.rag_score,
        llm_calibration=calibration,
    )
    return Explanation(
        narrative=narrative,
        top_candidate_id=claimed_top,
        calibration=calibration,
        citations=citations,
        stripped_citations=stripped,
        grounded=grounded,
        confidence=confidence,
    )
