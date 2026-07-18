# Culprit — Specification Freeze

**Version: v1.0** · **Frozen: 2026-07-18** · **Status: build step 1 in progress (Incident Simulation Harness)**

This file is the single source of truth for "what v1.0 means." It doesn't
restate the design docs — it pins the specific decisions in them that are
now frozen, and defines the process for changing any of them. If a doc in
`docs/` and this file ever disagree, **this file wins** until it's amended.

## Why this file exists

Fourteen planning docs is enough surface area that scope can silently drift
during implementation — a rule gets "temporarily" hardcoded differently than
spec'd, a confidence weight gets tweaked in code without anyone deciding to
tweak it. This file exists so that doesn't happen invisibly. Every change to
a frozen item below is a deliberate, dated, versioned decision — not a
silent edit.

---

## v1.0 Architecture

The core loop is fixed at six steps: **Detect → Correlate → Reason →
Recommend → Human Approval → Learn.** No step is optional in v1.0; no
seventh step gets added without a version bump.

- Full pipeline (9 sub-steps mapping onto the six): [docs/07-ai-architecture.md](docs/07-ai-architecture.md) § Agent architecture
- Service topology: [docs/03-architecture.md](docs/03-architecture.md)
- **Non-negotiable principle**: the LLM is not the source of truth. Correlation is deterministic (Rule Engine + Knowledge Graph); the LLM reasons, explains, and recommends on top of evidence it did not generate. This principle is the thing to defend hardest against future shortcuts under deadline pressure.

## v1.0 Rule Engine

Five named rules, each a pure, independently unit-tested function returning
`(score: 0-1, evidence: dict)`: `time_proximity`, `ownership_distance`,
`diff_keyword_match`, `historical_pattern_match`, `blast_radius_weight`.
Weights are per-org, stored in `correlation_rule_configs`, default weight
`1.000` each until tuned by real data.

- Definition: [docs/07-ai-architecture.md](docs/07-ai-architecture.md) § Rule Engine
- Schema: [docs/05-database.md](docs/05-database.md) `correlation_rule_configs`
- **Frozen for v1.0**: exactly these 5 rules. A 6th rule, or a rules DSL/framework replacing plain functions, is a v1.1+ decision, not a mid-implementation addition.

## v1.0 Knowledge Graph

Modeled as edges in Postgres (`service_edges`: `depends_on | owned_by |
deployed_via | shares_namespace`), populated from Kubernetes
`ownerReferences`, service-mesh topology (where present), Helm chart
parent/subchild relationships, and an explicit `owner_team` field. Queried
via recursive CTE, not a dedicated graph database.

- Definition: [docs/07-ai-architecture.md](docs/07-ai-architecture.md) § Knowledge Graph
- Schema + traversal query: [docs/05-database.md](docs/05-database.md)
- **Frozen for v1.0**: Postgres, not Neo4j/Memgraph. The upgrade trigger (edge/traversal scale ceiling) is named in the database doc — hitting that trigger is what justifies revisiting this, not "graph databases are better for graphs" in the abstract.

## v1.0 Confidence Formula

```
confidence = w_rule * rule_score + w_rag * rag_similarity + w_llm * llm_calibration
```

Default weights: `w_rule = 0.5, w_rag = 0.3, w_llm = 0.2`. `llm_calibration`
is bounded to adjust the composite by **at most ±0.15** from the
rule+RAG-only baseline. Every stored `rca_candidates` row carries the full
breakdown (`confidence_breakdown` jsonb), not just the composite.

- Definition: [docs/07-ai-architecture.md](docs/07-ai-architecture.md) § Confidence scoring
- Schema: [docs/05-database.md](docs/05-database.md) `rca_candidates`
- **Frozen for v1.0**: the formula shape and the ±0.15 LLM bound. Per-org *weight values* are meant to be tuned by real data (that's what the config table is for) — tuning weights is normal operation, not a spec change. Changing the *formula shape* (e.g. adding a fourth term, removing the LLM bound) is a version bump.

## v1.0 Event Contract

Inter-service events (`IncidentCreated`, `DeploymentDetected`,
`EvidenceCollected`, `GraphUpdated`, `CorrelationCompleted`,
`RecommendationGenerated`, `HumanApproved`, `IncidentClosed`,
`LearningCompleted`), versioned in the envelope (`version: "v1alpha1"`, not
in type names). `CorrelationCompleted` is the seam between the
deterministic pipeline and the LLM layer — its payload never carries LLM
output.

- Source of truth: [libs/eventschema/v1alpha1.md](libs/eventschema/v1alpha1.md)
- Implementations: `libs/py/eventschema`, `libs/go/eventschema`
- ADR: [docs/adr/0001-event-contract-v1alpha1.md](docs/adr/0001-event-contract-v1alpha1.md)
- **Frozen for v1.0**: this event set and the envelope shape. Adding a field
  to an existing event is fine within v1alpha1; removing/renaming a field,
  or adding a new event type, is a v1alpha2 decision — new ADR required.
- **Not used by the Incident Simulation Harness**, which calls the pipeline
  in-process — this contract governs service-to-service communication once
  there are multiple deployed processes (Phase 2+).

## v1.0 Evaluation Metrics

- **precision@1 / precision@3** against a golden set of real, anonymized past incidents.
- **Per-layer precision**: rule-only score's precision@1 is the deterministic baseline; the full composite must beat it, or the LLM/RAG layers are logged as adding noise, not signal.
- **Per-rule precision**: each of the 5 rules tracked individually over resolved incidents, feeding weight-tuning.
- **Evidence-grounding rate**: % of LLM-cited evidence that validates against real evidence objects (target: 100% — anything less means the grounding guardrail failed, not a metric to optimize incrementally).

Definition: [docs/07-ai-architecture.md](docs/07-ai-architecture.md) § Evaluation

## v1.0 Success Criteria (Phase 1 exit — see [docs/10-roadmap.md](docs/10-roadmap.md))

1. All Incident Simulation Harness scenarios (`pool_exhaustion`,
   `bad_config_rollout`, `resource_starvation`) pass in CI — top RCA
   candidate matches the deliberately injected cause.
2. Core loop deployed via Helm through the real CI/CD pipeline to a real
   EKS cluster — not run ad hoc.
3. This doc set stays current as the implementation proceeds — a doc that
   silently drifts from the code is a failed success criterion, not a
   documentation nicety.
4. 3-5 design-partner orgs using it against real incidents.
5. RCA precision@1 measured (not assumed) against the golden eval set, with
   the number recorded here once it exists — **TBD, no number until it's
   real data.**

---

## v1.0 Build Sequence

Order matters: each step is validated against the Incident Simulation
Harness before the next one is built on top of it, so no component is ever
built on an unvalidated foundation, and there is no UI built in front of
unproven logic.

1. **Incident Simulation Harness** — the foundation everything else is tested against.
2. **Evidence Collection** — deploy_events/alerts ingestion from real (simulated) clusters.
3. **Knowledge Graph** — `service_edges` population + traversal.
4. **Rule Engine** — the 5 rules, scored against simulation scenarios.
5. **Confidence Scoring** — the composite formula wired to real rule output.
6. **RAG Retrieval** — pgvector similarity search over (initially, simulated) past incidents.
7. **LLM Explanation Layer** — reasoning/explanation bounded by the grounding guardrail.
8. **Web UI** — Incident List + Incident Detail, once there's real pipeline output to render.
9. **Kubernetes Deployment** — Helm chart, real EKS, ArgoCD.
10. **CI/CD + automated evaluation** — golden-set scoring wired into the pipeline from here on, not bolted on at the end.

## Amendment log

Any change to a frozen item above gets an entry here **and** an ADR in
`docs/adr/` explaining the why (per the folder structure in
[docs/04-folder-structure.md](docs/04-folder-structure.md)). No silent
edits to this file.

| Version | Date | Change | ADR |
|---|---|---|---|
| v1.0 | 2026-07-18 | Initial freeze — architecture, rule engine, knowledge graph, confidence formula, evaluation metrics, success criteria, build sequence, per prior planning session. | — |
| v1.0 | 2026-07-18 | Added Event Contract (v1alpha1): 9 event types + envelope, implemented in `libs/py/eventschema` and `libs/go/eventschema`. Additive — fills a gap in v1.0, doesn't override a prior decision. | [0001](docs/adr/0001-event-contract-v1alpha1.md) |
| v1.0 | 2026-07-18 | Incident Simulation Harness v1 built: Scenario/EvidenceBundle schema (10 required fields), in-memory Knowledge Graph, all 5 Rule Engine rules implemented, confidence scoring wired, `pool_exhaustion` scenario passing end-to-end in `services/correlation-engine/tests/test_scenarios.py`. First proof the deterministic pipeline (steps 1-5 of "v1.0 Build Sequence") works, per the walking-skeleton approach. 9 more scenarios cataloged as backlog in `services/correlation-engine/correlation_engine/harness/scenarios/README.md`. | — |

---

**Status: build step 1 (Incident Simulation Harness) underway.** One
scenario (`pool_exhaustion`) passes end-to-end through the real
deterministic pipeline — see `services/correlation-engine/tests/`. Next:
finish the remaining 9 backlog scenarios in
`services/correlation-engine/correlation_engine/harness/scenarios/README.md`
before moving to build step 2 (Evidence Collection). Do not start
`services/ai-reasoning` until steps 2-5 (Evidence Collection, Knowledge
Graph, Rule Engine, Confidence Scoring) all pass against the full scenario
set.
