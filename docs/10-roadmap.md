# Part 11: Roadmap

## Phase 0 — Validation (before any platform code)
Problem-statement interviews + CLI proof-of-concept, per
[02-product-decision.md](02-product-decision.md). Gate: 3-5 real engineers
confirm the CLI's RCA output is *actually useful*, not just interesting.

## Phase 1 — MVP (single deployable, 2 data sources)

The scope is the six-step core loop — Detect → Correlate → Reason →
Recommend → Human Approval → Learn — executed exceptionally well, not
broadened. Every item below serves depth on that loop, nothing else.

- Data sources: GitHub deploys + Kubernetes events + Prometheus alerts only
  (Terraform and Helm-diff ingestion deferred to Phase 2).
- Architecture collapsed per the `# ponytail` notes in
  [03-architecture.md](03-architecture.md) and
  [04-folder-structure.md](04-folder-structure.md): one Go/Python deployable
  with internal package boundaries mirroring the target service split, not
  9 separately-deployed services.
- Infra: single shared non-prod-grade EKS cluster, SQS+SNS bus, RDS single-AZ,
  no OpenSearch, no Redpanda (see [09-infrastructure.md](09-infrastructure.md)).
- UI: Incident List + Incident Detail only. No settings/billing UI —
  integrations configured via a setup script/CLI for early design-partner
  customers.
- Auth: single-org, email/password or GitHub OAuth — no SSO/OIDC yet.
- Remediation: propose-only, no execute. Human copies the suggested
  `helm rollback` command themselves. (Removes the highest-blast-radius,
  highest-trust-bar feature from the critical path to first users.)

### Incident Simulation Harness (built alongside the loop, not after)

A `kind`/`k3d`-based local cluster + a `scripts/simulate/` set of scenarios
that deliberately reproduce real, documented failure patterns end-to-end —
deploy the bad change, let Prometheus/Alertmanager fire for real, let
Culprit run its actual pipeline against it. Not mocked at any layer.

- `pool_exhaustion` — Helm values change shrinks a DB connection pool,
  triggers a real "pool exhausted" alert.
- `bad_config_rollout` — a config map change introduces a crash loop.
- `resource_starvation` — a resource-limits change causes OOMKills.
- `terraform_iam_break` — a Terraform change removes a permission a
  service needs, surfaces as downstream errors (Phase 2, once Terraform
  ingestion exists).

This does three jobs, deliberately, instead of three separate efforts:
1. **It's the automated test suite for the core loop** — each scenario is a
   CI-run integration test asserting the pipeline's top RCA candidate
   matches the known-injected cause (this is also the seed of the golden
   eval set in [07-ai-architecture.md](07-ai-architecture.md), before any
   real customer incident exists to curate from).
2. **It's the demo** — a recorded run of these scenarios is what a
   recruiter or interviewer sees, and it's honest: every "AI found the
   cause" claim in the demo is a real pipeline run against a real cluster,
   not a scripted UI mockup.
3. **It's the trust-building tool for design partners** — showing a
   prospective early user the harness passing on known scenarios is a
   concrete claim ("here's what it catches and how"), stronger than a pitch.

- **Exit criteria**: all simulation scenarios pass in CI with the top RCA
  candidate matching the injected cause; core loop deployed via Helm to a
  real (even if small) EKS cluster through the actual CI/CD pipeline (see
  [09-infrastructure.md](09-infrastructure.md)), not run ad hoc; documented
  (architecture doc set — this one — kept current, not written once and
  abandoned); and only then, 3-5 design-partner orgs using it on real
  incidents with RCA precision@1 measured against the golden set.

## Phase 2 — Beta
- Add Terraform + Helm/ArgoCD as evidence sources.
- Split into real services where load or team growth justifies it — starting
  with `ai-reasoning` (different scaling profile, isolate blast radius of
  model-provider issues).
- Multi-org support, RLS enforced (was already schema-correct from day one,
  per [05-database.md](05-database.md) — no migration needed, just turn on
  multi-tenant signup).
- Remediation execution goes live, allow-listed + human-approved, starting
  with `helm_rollback` only (the lowest-risk, most reversible action) before
  `pr_revert` or `scale_deployment`.
- SSO/OIDC, RBAC roles, audit-log UI.
- Move to Redpanda if event replay/fan-out needs from the growing feature
  set justify leaving SQS+SNS; move to OpenSearch if incident volume search
  actually degrades on Postgres full-text — both are measured triggers, not
  calendar-scheduled migrations.

## Phase 3 — Enterprise
- Canary/progressive-delivery AI analysis (the runner-up problem from
  [01-problem-landscape.md](01-problem-landscape.md)) as a feature built on
  the now-mature deploy-metadata pipeline.
- Terraform PR blast-radius review (#13 from the landscape doc) as a second
  feature on the same pipeline.
- SOC2 Type II process (audit log, backup/DR posture from
  [03-architecture.md](03-architecture.md) already built for this).
- Self-hosted/VPC-deployed option for enterprise customers who won't send
  infra data to a third-party SaaS — this is a real, common objection in
  this market and the architecture (outbound-only Collector, org-scoped
  everything) was chosen with this in mind from Phase 1.
- Dedicated cluster per environment, cross-region DR, read replicas —
  upgraded from Phase 1/2's shared/simpler setup as real customer SLAs
  demand it.

## Phase 4 — AI Agents (expanded scope, only after core loop is proven)
- Broaden the allow-listed remediation action set based on what customers
  actually request (not speculative).
- Multi-step remediation (e.g., rollback + scale + notify as one approved
  plan) — still human-approved, still bounded, still auditable; the
  single-bounded-agent design from
  [07-ai-architecture.md](07-ai-architecture.md) extends naturally here
  without needing a multi-agent rewrite.
- Runbook generation: agent drafts a runbook from a resolved incident's
  evidence + resolution, human edits/approves — folds in the "tribal
  knowledge" problem (#12 from the landscape doc) as a natural extension.

## Phase 5 — Commercial SaaS
- Self-serve signup + Stripe billing (usage-based: incidents analyzed/month,
  tiered by remediation-execution access).
- Public status page, SOC2 report available to prospects, security
  questionnaire response kit (the standard enterprise-sales unlocks).
- Marketing site + docs site separate from the app (`culprit.dev` vs
  `app.culprit.dev`), not built until there's a product worth marketing.

## What never gets built (reaffirmed)
The non-goals list in [00-INDEX.md](00-INDEX.md) stays a non-goals list
through every phase above unless a specific, named paying customer need
appears — "platforms like this usually have X" is never sufficient
justification on its own.

Continue to [11-resume-interviews.md](11-resume-interviews.md).
