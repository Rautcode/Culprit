# Part 12: Resume & Interview Framing

## Why this impresses recruiters (specifically, not generically)

A generic "AI DevOps dashboard" reads as a tutorial project the instant a
senior engineer sees it — dashboards are the most-cloned portfolio artifact
there is. Culprit reads differently because:

1. **It has one hard, well-scoped technical problem**, not fifteen shallow
   features — a reviewer can ask "how does the correlation engine decide what
   evidence is relevant before calling the LLM" and get a real, specific
   answer (the deterministic pre-filter in
   [07-ai-architecture.md](07-ai-architecture.md)), which is exactly the kind
   of judgment a Staff/Senior interview is probing for.
2. **The guardrail design is the interesting part, not the LLM call.**
   Anyone can call an API and print the response. Designing "propose, never
   auto-execute; allow-list actions; blast-radius caps; confidence
   thresholds" demonstrates the actual scarce skill: building AI systems
   that are safe to put in front of production infrastructure.
3. **It touches the full stack a Platform/SRE/DevOps role actually needs**:
   Kubernetes internals, GitOps, Terraform, distributed event-driven
   architecture, multi-tenant data modeling, and applied (not toy) LLM
   engineering — in one coherent system with a real causal thread connecting
   the pieces, not a checklist of unrelated demos.

## Resume bullet framing

Lead with the outcome and the hard part, not the tech-stack list:

> Built Culprit, an AI-driven root-cause-analysis platform that correlates
> Kubernetes/GitOps deployment events with production alerts to identify the
> likely cause of an incident and propose a guardrailed, human-approved
> remediation — reducing time-to-cause-identification in [design-partner /
> personal-load-test] scenarios from N minutes to N seconds. Designed the
> multi-tenant event-driven architecture (Go/Python microservices, Postgres
> with row-level security, SQS-based event bus), the bounded AI agent
> pipeline with deterministic pre-filtering and execution guardrails, and the
> full AWS/Terraform/EKS/ArgoCD production infrastructure.

Fill in a real N once Phase 1 validation produces one — never state a metric
that isn't actually measured; an interviewer who asks "how did you measure
that" and gets a shrug does more damage than a modest, real number would.

## Interview questions this project prepares you for

**System design**
- "Design a multi-tenant SaaS with strict data isolation." → RLS + `org_id`
  scoping decision, and *why* that beats DB-per-tenant at this stage.
- "Design an event-driven system that must not lose or duplicate events." →
  idempotency-keyed webhook ingestion, at-least-once + dedupe pattern.
- "How would you scale this to 10x load?" → the specific, named triggers in
  [10-roadmap.md](10-roadmap.md) (queue depth → Redpanda, search latency →
  OpenSearch), not a vague "add more servers."

**AI/ML engineering**
- "Why not just let the LLM figure out the root cause from the raw data?" →
  the core architectural argument in
  [07-ai-architecture.md](07-ai-architecture.md): a Rule Engine + Knowledge
  Graph do the actual correlation deterministically and produce cited
  evidence with a defensible score; the LLM reasons and explains on top of
  that, bounded to ±0.15 confidence adjustment, with every citation
  validated against real evidence before it's stored. This answers the
  "how do you keep it from hallucinating a root cause" question directly,
  and it's the single strongest differentiator to walk an interviewer
  through — it shows you understand where LLM non-determinism is and isn't
  acceptable in a production system.
- "How do you keep an LLM agent from doing something dangerous in
  production?" → the full guardrail stack in
  [07-ai-architecture.md](07-ai-architecture.md): evidence grounding,
  allow-lists, dry-run, confidence thresholds, blast-radius caps, human
  approval.
- "How do you control cost/latency in an LLM-backed system?" → the
  deterministic layers (Rule Engine, Knowledge Graph, RAG retrieval) run
  before any model call and often make the call unnecessary entirely (zero
  recent changes → short-circuit), plus prompt caching and model tiering by
  task.
- "How do you evaluate a system like this?" → golden set scored per-layer
  (rule-only precision@1 as a baseline the full pipeline must beat) +
  precision@k + shadow mode + human-feedback-driven eval-set growth +
  per-rule precision tracking feeding weight tuning.

**Kubernetes/infra**
- "Walk me through what happens when a pod OOMKills." → directly answerable
  from having built the k8s-events evidence source.
- "How do you avoid vendor lock-in / minimize blast radius of a bad
  deploy?" → Argo Rollouts canary strategy specifically applied to the two
  highest-risk services, not uniformly (shows judgment, not cargo-culting).

**Product/business judgment** (increasingly asked at Staff level)
- "How would you validate this before building it?" → the Phase 0 validation
  plan in [02-product-decision.md](02-product-decision.md) — cold interviews
  and a CLI proof-of-concept *before* a platform.
- "Why this problem and not [alerting/cost/security]?" → the ranking table
  in [01-problem-landscape.md](01-problem-landscape.md) and the explicit
  "why current solutions fail" analysis — shows you can reason about market
  gaps, not just write code.

## How to talk about it without overselling

Be precise about what's real vs. designed-but-unbuilt at any point in time.
"I designed the multi-agent... " when only the single-agent pipeline is
built is the kind of gap an experienced interviewer finds in the second
follow-up question. State current status plainly: "Phase 1 MVP is built and
running against N design-partner clusters; Phases 2+ are the designed,
not-yet-built roadmap" is a *stronger* answer than vague overclaiming — it
shows exactly the scoping discipline this whole doc set is built around.
