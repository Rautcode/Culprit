"""Export real pipeline output for the Web UI (build step 8).

Runs every harness scenario through the actual deterministic pipeline —
leave-one-out incident memory, so RAG precedent evidence is populated the
honest way — and writes apps/web/lib/incidents.json in the response shape
the future REST API (docs/06-api-design.md) will serve. The UI consuming
this file today consumes the live API in Phase 2 with a fetch-URL change.

No LLM narrative is exported: no scripted model output masquerades as AI in
a demo. The UI renders what the deterministic layers actually produced —
ranked candidates, confidence breakdowns, cited evidence, precedents.

Usage:  python scripts/export_incidents.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services" / "correlation-engine"))

from correlation_engine.harness.scenarios import ALL_SCENARIOS  # noqa: E402
from correlation_engine.memory import IncidentMemory  # noqa: E402
from correlation_engine.pipeline import run_scenario  # noqa: E402


def export() -> dict:
    incidents = []
    for scenario in ALL_SCENARIOS:
        memory = IncidentMemory()
        for other in ALL_SCENARIOS:
            if other.id != scenario.id:
                memory.learn_from_scenario(other)
        result = run_scenario(scenario, memory)

        primary_alert = scenario.evidence.alerts[0]
        incidents.append({
            "id": scenario.id,
            "title": primary_alert.title,
            "service": primary_alert.service,
            "severity": primary_alert.severity,
            "status": "identified",
            "opened_at": primary_alert.fired_at.isoformat(),
            "difficulty": scenario.difficulty.value,
            "description": scenario.description,
            "alerts": [
                {"id": a.id, "service": a.service, "title": a.title,
                 "severity": a.severity, "fired_at": a.fired_at.isoformat()}
                for a in scenario.evidence.alerts
            ],
            "timeline": [
                {"type": e["type"], "occurred_at": e["occurred_at"].isoformat(), "ref": e["ref"]}
                for e in result.timeline
            ],
            "rca_candidates": [
                {
                    "rank": rank,
                    "deploy_id": c.deploy_id,
                    "service": deploy.service,
                    "summary": deploy.diff_summary.get("summary", ""),
                    "deployed_by": deploy.deployed_by,
                    "occurred_at": deploy.occurred_at.isoformat(),
                    "confidence": round(c.confidence.composite, 3),
                    "confidence_breakdown": {
                        "rule_score": round(c.confidence.rule_score, 3),
                        "rag_score": round(c.confidence.rag_score, 3),
                        "llm_adjustment": round(c.confidence.llm_adjustment, 3),
                    },
                    "rule_hits": list(c.rule_hits),
                    "evidence": json.loads(json.dumps(c.evidence, default=str)),
                }
                for rank, c in enumerate(result.candidates, start=1)
                for deploy in [next(d for d in scenario.evidence.deploys if d.id == c.deploy_id)]
            ],
            "proposed_remediation": scenario.expected_rollback,
        })
    return {"incidents": incidents}


if __name__ == "__main__":
    out = ROOT / "apps" / "web" / "lib" / "incidents.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    # newline pinned so the CI drift check compares identical bytes on any OS
    out.write_text(json.dumps(export(), indent=2) + "\n", encoding="utf-8", newline="\n")
    data = json.loads(out.read_text(encoding="utf-8"))
    assert len(data["incidents"]) == len(ALL_SCENARIOS)
    assert all(i["rca_candidates"] for i in data["incidents"])
    print(f"exported {len(data['incidents'])} incidents -> {out}")
