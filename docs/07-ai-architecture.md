# Part 8: AI Architecture

This is the differentiated core of the product, so it gets the most rigor —
and the most restraint. The failure mode for an "AI DevOps" product isn't too
little AI, it's an LLM call where a five-line SQL query would do, producing a
system that's slow, expensive, unauditable, and no more accurate than
deterministic code — and worse, one that sounds authoritative regardless of
whether it's actually right. **The LLM is not the source of truth in this
system.** A Rule Engine and a Knowledge Graph do the actual correlation and
produce cited, deterministically-scored evidence; a vector-DB RAG store
surfaces historical precedent; the LLM's job is bounded to reasoning,
explanation, summarization, and recommendation *on top of* that evidence —
it is never allowed to assert a conclusion it can't trace back to something
the deterministic layer actually returned. This mirrors how mature
enterprise AIOps/observability systems are actually built (rules +
topology/graph models + ML/AI as a reasoning layer, not the whole system),
and it's the difference between a demo and something an SRE team will
actually trust with a rollback button.

## Agent architecture

**Not** a single free-roaming agent with unlimited tool access, and **not**
an LLM asked to "figure out the root cause" from raw evidence. A **bounded
pipeline where the deterministic layers do the correlation and the LLM does
exactly one agentic step: reasoning over what they found.**

```
1. Trigger              alert fires / webhook received
2. Evidence Gather      (deterministic, no LLM)
                         - query deploy_events for the affected service ± 2h window
                         - query k8s events for the affected namespace
                         - pull Terraform/Helm plan summaries touching related resources
                         - pull relevant log/metric excerpts around fired_at
3. Knowledge Graph      (deterministic, no LLM — Postgres recursive CTE over
   Query                 service_edges, see 05-database.md)
                         - blast-radius traversal: what's upstream/downstream
                           of the alerting service
                         - ownership resolution: which team/on-call owns each
                           candidate service in the graph
4. Rule Engine          (deterministic, no LLM — see "Rule Engine" below)
                         - a fixed set of named, independently-tested rules,
                           each scores candidate deploy_events against the
                           alert and cites its own evidence
                         - if zero deploys/changes in window AND no graph
                           hits → short-circuit, return "no recent change
                           detected," skip the LLM entirely
                         - output: a ranked candidate list, each with a
                           deterministic rule_score + cited evidence — this
                           is a real, useful answer on its own, even with
                           zero LLM involvement
5. RAG Retrieval        (deterministic retrieval, no generation yet)
                         - embed current alert+evidence, retrieve top-k
                           similar past incidents from incident_embeddings
                           (pgvector), each with a similarity score
6. Agent Reasoning       (LLM, THE agentic step — tool-use loop)
                         - input: the Rule Engine's ranked candidates +
                           Knowledge Graph context + RAG results — never
                           raw, unfiltered evidence
                         - may call additional tools to fill gaps:
                           get_diff(deploy_id), get_recent_logs(service_id, window)
                         - produces: prose explanation, a bounded confidence
                           calibration, and a rank/selection among the
                           Rule Engine's candidates — it reorders and
                           explains, it does not invent new candidates
                           out of nothing
                         - every evidence citation in its output is
                           validated against real evidence objects returned
                           in steps 2-5 before being written to rca_candidates
                           (see "Guardrails")
7. Remediation           (LLM proposes, deterministic executor enforces guardrails)
   Proposal              - agent may propose ONE action from an allow-listed set
                           (helm_rollback, pr_revert, scale_deployment)
                         - proposal always includes a dry-run diff; never auto-executes
8. Human Approval        (no LLM — a human clicks Approve/Reject)
9. Learn                  embed the resolved incident's summary + evidence into
                          incident_embeddings for future RAG retrieval; log
                          rule performance (did this rule's top candidate
                          match the human-confirmed cause?) for rule-weight
                          tuning, see "Rule Engine" below
```

Steps 2, 3, 4, 5, 8, 9 are plain, unit-testable code with zero model calls.
Only steps 6-7 touch an LLM. This bounds cost and latency, and — critically
for an infra product — means the system produces a real, evidence-backed
answer even if the LLM call fails, times out, or is disabled entirely.

## Rule Engine

A fixed set of named, independently unit-tested rules — plain Python
functions, not a rule DSL or a third-party rules-engine framework (Drools,
etc. would be solving a problem this system doesn't have: the rule set is
small, written and reviewed by us, not authored by end users). Each rule
takes the alert + candidate deploy_event + Knowledge Graph context and
returns `(score: 0-1, evidence: dict)`.

| Rule | Signal | Example evidence it cites |
|---|---|---|
| `time_proximity` | How close the deploy was to alert `fired_at` | "Deploy at 14:31, alert fired 14:32 (90s gap)" |
| `ownership_distance` | Knowledge-Graph hop distance between the deployed service and the alerting service | "checkout-service deployed; alert on checkout-service (0 hops)" |
| `diff_keyword_match` | Keyword/heuristic match between the deploy's diff summary and the alert's signal (e.g. a DB-pool-related alert vs. a diff touching connection-pool config) | "Diff modifies `connectionPoolSize: 50→10`; alert is `pool exhausted`" |
| `historical_pattern_match` | Whether this exact (service, change-type, alert-type) combination matched a past confirmed incident | "3 prior incidents on this service had the same signature" |
| `blast_radius_weight` | Whether the deploy touches a service with many downstream dependents (per Knowledge Graph), making it a more likely systemic cause | "12 downstream services depend on this one" |

Per-org rule weights live in `correlation_rule_configs` (see
[05-database.md](05-database.md)) so an org without a service mesh can
down-weight `ownership_distance`, for example, without a code deploy. The
Rule Engine's output score for a candidate is the weighted sum of fired
rules, normalized to 0-1 — this is the `rule_score` component of the final
confidence (see "Confidence Scoring" below).

Because every rule is a small, pure, independently testable function, the
golden-set eval (see "Evaluation" below) can measure *each rule's*
precision contribution over time — if `diff_keyword_match` turns out to be
noisy, that's visible and fixable without touching the LLM prompt at all.

## Knowledge Graph

Models services, their dependencies, and ownership as a graph — built
incrementally by the Collector agent from real signals already present in
the cluster (Kubernetes `ownerReferences` and service-mesh topology where
available, Helm chart parent/subchart relationships, and an explicit
`owner_team` field on the `services` table for anything not inferable) —
not hand-maintained by customers, which is exactly why service-catalog
products like Backstage struggle with staleness (see
[01-problem-landscape.md](01-problem-landscape.md), problem #9).

Stored as edges in Postgres (`service_edges`), queried with recursive CTEs
for blast-radius and dependency-distance traversal — see
[05-database.md](05-database.md) for the schema and an example query. This
is a deliberate choice over a dedicated graph database (Neo4j/Memgraph) at
this scale; the ponytail note in that doc names the concrete trigger for
revisiting it.

The Knowledge Graph feeds both the Rule Engine (`ownership_distance`,
`blast_radius_weight`) and the UI's blast-radius view directly — it's
shared infrastructure, not something built once for the AI pipeline and
forgotten.

## RAG (incident memory)

- **What's embedded**: a structured summary per resolved incident (title,
  root cause, affected service, resolution action) — not raw logs, which are
  noisy and blow up embedding volume for no retrieval benefit.
- **Retrieval**: on every new incident, embed the current alert + evidence
  summary, retrieve top-k similar past incidents (cosine similarity via
  pgvector, scoped by `org_id` — never cross-tenant, enforced at the query
  level in addition to RLS) and inject them into the agent's context as
  "here's what resolved similar incidents before."
- **Why this matters for the business, not just the tech**: RAG is what
  makes the product's value compound with usage — a customer's 50th incident
  gets diagnosed faster than their 5th because the system has seen their
  specific failure patterns. This is the retention moat, not the raw LLM
  call.

## Memory

Two distinct kinds, kept explicitly separate rather than blurred into one
"memory" concept:

1. **Episodic (per-incident)**: the tool-call trace and reasoning for the
   *current* investigation — lives only in the AI Reasoning Service's request
   context, persisted to `timeline_events`/`rca_candidates` for audit, not
   fed back as a long-running conversation.
2. **Semantic (cross-incident)**: the `incident_embeddings` RAG store —
   long-lived, compounds over time, scoped per org.

No third "chat memory" layer — the product isn't a general chatbot, so there's
no open-ended conversation history to manage.

## Tools (exposed to the agent)

Note: the Rule Engine's ranked candidates, the Knowledge Graph's blast-radius
context, and the top-k RAG results are already computed deterministically
*before* the agent starts (steps 3-5 above) and handed to it as input — the
agent doesn't re-derive correlation via tool calls, it reasons over
correlation that already happened. The tools below are for filling
*specific gaps* the reasoning step identifies (e.g. "I need the actual diff
content for candidate #1, not just its rule score").

| Tool | Backed by | Returns |
|---|---|---|
| `get_diff(deploy_id)` | Timeline Service | git diff / Helm values diff / Terraform plan diff |
| `get_service_dependencies(service_id)` | Knowledge Graph (`service_edges`, recursive CTE) | upstream/downstream services, hop distance |
| `get_recent_logs(service_id, window)` | Loki/CloudWatch adapter | log excerpt, pre-filtered for error-level lines |
| `get_similar_past_incidents(query)` | pgvector RAG store | top-k past incidents with resolutions (re-query with a refined query if the initial retrieval wasn't specific enough) |
| `propose_remediation(action_type, target, diff)` | Remediation Service (dry-run mode only) | validated dry-run diff, never executes |

Every tool call and its result is logged verbatim against the incident —
this log **is** the "show your work" trace streamed to the UI (see
[06-api-design.md](06-api-design.md) SSE endpoint).

## Planning & reasoning

A single ReAct-style loop (reason → act → observe, repeat, bounded to a max
of ~8 tool calls) rather than a multi-agent planner/orchestrator setup.
Multi-agent orchestration solves coordination problems between specialized
agents with different goals — this system has one goal (explain the
incident) and one agent. Adding a "planner agent" + "critic agent" here would
be complexity with no corresponding capability gain.

`# ponytail: single bounded agent, not a multi-agent framework. Revisit only
if a genuinely separate concern emerges (e.g. a distinct "remediation safety
reviewer" agent with different guardrail authority than the investigator).`

## Prompt engineering

- System prompt encodes the domain model explicitly (what a "deploy event,"
  "blast radius," and "confidence" mean in this product) rather than relying
  on the model's generic world knowledge of DevOps — this is what separates
  a usable product from a ChatGPT wrapper.
- Every reasoning output is **structured** (tool-call JSON / a fixed
  `RCACandidate` schema for the final answer) via the provider's native
  structured-output/tool-use mode, not regex-parsed free text.
- Few-shot examples in the system prompt are real, anonymized past
  investigations (once the product has enough usage data) — the eval suite
  below is what curates which examples earn a place in the prompt.

## Model selection

- Reasoning step: a frontier model with strong tool-use and long-context
  reliability (Claude Sonnet-class) — this step's output drives a proposed
  production remediation, so accuracy matters more than cost here.
- Cheap/high-volume steps (embedding generation, log excerpt summarization
  for pre-filtering): a small/cheap model or a dedicated embeddings endpoint
  — never the frontier model for work that doesn't need frontier reasoning.
- Model calls go through a thin internal abstraction (not a heavyweight
  framework) so swapping providers/models is a config change, not a rewrite —
  this is the one piece of "framework-shaped" code that earns its keep,
  because model churn in this space is fast and real.

## Context window management

- Evidence is pre-summarized/pre-filtered (step 3 above) specifically to
  keep what reaches the model small and relevant — the deterministic
  pre-filter is a context-budget mechanism as much as a cost mechanism.
- Long log excerpts are truncated to error/warn-level lines + surrounding
  context lines, not dumped wholesale.
- RAG-retrieved past incidents are capped at top-3, summarized form only.

## Token optimization

- Prompt-cache the system prompt + domain schema (stable across every
  request) using the provider's prompt-caching feature — this is pure
  savings with zero behavior change.
- Deterministic pre-filter (step 3) means a large fraction of alerts never
  reach the model at all — the single biggest token-cost lever in the
  system, and it's not an AI technique, it's just good engineering.
- Structured outputs avoid the token waste of the model re-explaining
  itself in prose when a schema will do.

## Confidence scoring

Every `rca_candidates` row carries a composite confidence *and* a stored
breakdown (`confidence_breakdown` jsonb, see
[05-database.md](05-database.md)) — never a single bare number the LLM
asserted:

```
confidence = w_rule * rule_score + w_rag * rag_similarity + w_llm * llm_calibration
```

- `rule_score` — the Rule Engine's weighted-sum output (deterministic,
  computed before the LLM runs).
- `rag_similarity` — cosine similarity of the best-matching historical
  incident, if any (0 if no relevant precedent found).
- `llm_calibration` — the LLM's own confidence in its explanation, **bounded
  to adjust the composite by at most ±0.15** from what `rule_score`+`rag`
  alone would produce. The LLM can nudge confidence up or down based on
  nuance the rules missed, but it cannot single-handedly turn a
  weak-evidence candidate into a "99% confident" verdict — that ceiling is
  the concrete mechanism that keeps the system from "sounding authoritative
  without support."
- Default weights `w_rule=0.5, w_rag=0.3, w_llm=0.2`, stored per-org
  alongside `correlation_rule_configs` so they're tunable as real usage data
  comes in — not hardcoded constants.

The UI's "why 92%" drill-down (see [08-ui-design.md](08-ui-design.md))
renders this breakdown directly — an SRE can see it's 92% because three
rules fired strongly and a near-identical past incident exists, not because
a model said so.

## Guardrails

- **Evidence grounding.** Before an `rca_candidates` row is written, every
  citation in the LLM's `evidence` output is validated against the actual
  evidence objects returned by the Rule Engine, Knowledge Graph, and tool
  calls in that request — a citation that doesn't match a real evidence
  object is stripped and the candidate's `llm_calibration` component is
  zeroed out for that response. This is the single most important guardrail
  in the system: it's the mechanical enforcement of "the LLM explains, it
  doesn't invent."
- **Allow-listed actions only.** The agent can propose from
  `{helm_rollback, pr_revert, scale_deployment}` — never arbitrary shell/API
  calls. Expanding this set is a deliberate product decision per customer
  (configured in `integrations.config`), not something the model decides.
- **Dry-run before propose.** `propose_remediation` always computes and
  returns a diff/plan; the Remediation Service will not execute anything the
  agent "decides" to run directly — execution requires the human-approval
  step (step 6), full stop.
- **Confidence threshold.** RCA candidates below a configurable confidence
  score are surfaced as "low confidence, needs human review" rather than
  hidden or auto-acted on — false confidence is worse than visible
  uncertainty in an incident-response tool.
- **Blast-radius cap.** Remediation Service refuses to execute any action
  whose target matches more than N resources (configurable) without
  additional explicit confirmation — prevents a bad rollback proposal from
  becoming a bad mass rollback.

## Evaluation

- **Golden set**: a curated set of real (anonymized, consented) past
  incidents with known root causes, used as regression tests — every prompt
  or model change runs against this set before deploy, scored on
  precision@1 (did the top RCA candidate match the actual cause) and
  precision@3. Because correlation is layered (Rule Engine → RAG → LLM),
  the golden set scores **each layer separately**: rule_score-only
  precision@1 is the baseline the deterministic layer must hit on its own;
  the full composite score's precision@1 must beat that baseline, or the
  LLM/RAG layers are adding noise, not signal, and get investigated before
  shipping.
- **Rule weight tuning**: the "Learn" pipeline step logs, per resolved
  incident, whether each fired rule's candidate matched the human-confirmed
  cause. This produces a simple, auditable per-rule precision number over
  time per org — weights in `correlation_rule_configs` get adjusted from
  this signal (manually at first; a lightweight automatic tuner is a
  reasonable Phase 2+ addition once there's enough resolved-incident volume
  per org to make it statistically meaningful, not before).
- **Shadow mode for new customers**: for the first N incidents after a
  customer onboards, the agent runs and produces candidates, but they're
  shown as "AI suggestion, not yet validated" until the customer confirms
  accuracy a few times — earns trust before the UI treats it as authoritative.
- **Human feedback loop**: every RCA candidate has a thumbs up/down in the
  UI; disagreements get added to the golden set (with review) rather than
  silently discarded — the eval set grows from real usage, not just from
  what we thought to test upfront.

## AI observability

The AI Reasoning Service emits OpenTelemetry spans for every tool call and
model call (latency, token count, cost, model version) into the same
Prometheus/Tempo stack as the rest of the platform (see
[09-infrastructure.md](09-infrastructure.md)) — AI observability is not a
separate bolted-on dashboard, it's the same observability system used to run
the company, which is also a strong interview talking point (see
[11-resume-interviews.md](11-resume-interviews.md)).

Continue to [08-ui-design.md](08-ui-design.md).
