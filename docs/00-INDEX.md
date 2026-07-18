# Culprit — AI SRE Copilot for Root Cause Analysis

> "The AI SRE that finds what broke prod, before your engineers do."

This is a strategy + architecture doc set for a focused, resume-and-startup-worthy
AI DevOps product. Per explicit scoping decision: **we are not building 100
features.** We build one outstanding core capability — deployment-aware causal
root cause analysis with guardrailed auto-remediation — and a small number of
supporting modules that exist only because the core capability needs them.

**Architecture principle (revised after review): the LLM is not the source
of truth.** A deterministic Rule Engine and a Knowledge Graph do the actual
correlation and produce cited evidence with a deterministic confidence
component; a Vector DB (RAG) surfaces historical precedent; the LLM's job is
reasoning, explanation, and recommendation *on top of* that evidence — never
asserting a conclusion it can't ground in something the rule engine or graph
actually returned. See [07-ai-architecture.md](07-ai-architecture.md) for
the full pipeline and confidence-scoring model.

**Spec is frozen as of v1.0 — see [../SPEC_VERSION.md](../SPEC_VERSION.md).**
Any change to architecture, rule engine, knowledge graph, confidence
formula, evaluation metrics, or success criteria goes through that file,
not a silent edit to the docs below.

## Reading order

| Part | File | Content |
|---|---|---|
| 1-2 | [01-problem-landscape.md](01-problem-landscape.md) | Real DevOps pain points surveyed + ranked |
| 3 | [02-product-decision.md](02-product-decision.md) | The chosen problem, fully validated, competitive analysis |
| 4 | [03-architecture.md](03-architecture.md) | SaaS system architecture |
| 5 | [04-folder-structure.md](04-folder-structure.md) | Repo layout |
| 6 | [05-database.md](05-database.md) | Schema, ER, indexes |
| 7 | [06-api-design.md](06-api-design.md) | REST/WebSocket/streaming API |
| 8 | [07-ai-architecture.md](07-ai-architecture.md) | Agent, RAG, guardrails, evals |
| 9 | [08-ui-design.md](08-ui-design.md) | Screens, IA, design system |
| 10 | [09-infrastructure.md](09-infrastructure.md) | AWS/Terraform/K8s production infra |
| 11 | [10-roadmap.md](10-roadmap.md) | MVP → Beta → Enterprise → Commercial |
| 12 | [11-resume-interviews.md](11-resume-interviews.md) | Resume framing + interview prep |

## Non-goals (explicitly deferred, not forgotten)

These are real, valid DevOps problems. They are not in scope for v1 because
they don't serve the core capability. See [10-roadmap.md](10-roadmap.md) for
when/if they get pulled in.

- General-purpose observability (metrics/log storage) — we *consume* Prometheus/Loki, we don't replace them.
- Full FinOps/cost-management suite — Kubecost/CAST AI already own this well.
- General CI pipeline orchestration — we consume GitHub Actions/ArgoCD events, we don't replace them.
- Generic chat-ops bot / ChatGPT-wrapper for "ask your infra questions."
- Full incident.io-style paging/on-call scheduling — we integrate with PagerDuty, we don't rebuild it.

`# ponytail: scope held to one core loop (detect → correlate via rules+graph → retrieve via RAG → explain via LLM → propose fix → learn). Expand only when the core loop is proven with real users.`

## Standing rule: depth over breadth

The six-step core loop — **Detect → Correlate → Reason → Recommend → Human
Approval → Learn** — executed exceptionally well (tested, documented,
deployed via real CI/CD to real Kubernetes, demonstrated against realistic
simulated incidents — see the Incident Simulation Harness in
[10-roadmap.md](10-roadmap.md)) beats a broad platform with shallow
features. This is the standing bar for Phase 1: no new feature gets added
until the six steps are executed at this level of polish.
