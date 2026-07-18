# Part 4: SaaS Architecture

## Guiding constraint

The core loop is: **ingest evidence → correlate → reason (AI) → propose fix →
human approves → learn (store in incident memory).** Every service below
exists because that loop needs it. Nothing is added because "a platform like
this usually has X."

## System diagram (textual)

```
┌─────────────────────────────────────────────────────────────────────┐
│ Customer's environment                                              │
│  Kubernetes cluster(s) ── GitHub/GitLab ── Terraform Cloud/state    │
│  Prometheus/Grafana ── Loki/CloudWatch Logs ── ArgoCD/Flux          │
└───────────────┬───────────────────────────────────────────────────┬─┘
                 │ (lightweight in-cluster Collector agent,          │
                 │  outbound-only, no inbound firewall holes)        │
                 ▼                                                   │
        ┌─────────────────┐        webhooks (GitHub, ArgoCD, PagerDuty)
        │  Ingestion API   │◄──────────────────────────────────────┘
        │  (Go, stateless) │
        └────────┬─────────┘
                 │ publish
                 ▼
        ┌─────────────────┐
        │  Event Bus       │  (Redpanda/Kafka-compatible; SQS+SNS is the
        │                  │   AWS-native fallback for MVP — see 09-infra)
        └───┬─────┬────────┘
            │     │
            ▼     ▼
  ┌──────────────┐ ┌─────────────────────────────┐
  │ Timeline      │ │ Correlation Engine (Python)  │  (the core IP — all
  │ Service       │ │  - evidence gathering        │   deterministic, no LLM)
  │ (writes to    │ │  - Rule Engine: named,        │
  │  Postgres)    │ │    testable, weighted rules   │
  └──────────────┘ │  - Knowledge Graph queries:    │
                    │    ownership/dependency/       │
                    │    blast-radius traversal      │
                    │    (Postgres recursive CTE      │
                    │    over service_edges)          │
                    │  - produces ranked candidates   │
                    │    + cited evidence + a          │
                    │    deterministic confidence      │
                    │    component, BEFORE any LLM     │
                    └──────────┬───────────────────────┘
                               ▼
                    ┌─────────────────────┐
                    │ AI Reasoning Service │  (agent orchestration,
                    │  - RAG (pgvector) over│  see 07-ai-architecture.md)
                    │    past incidents      │  Consumes the Rule Engine's
                    │  - LLM: explains,      │  ranked candidates; explains,
                    │    summarizes,         │  recommends, and calibrates
                    │    recommends only —   │  confidence — never invents
                    │    never the sole       │  evidence the deterministic
                    │    source of a verdict  │  layer didn't already cite.
                    └──────────┬───────────┘
                               ▼
                    ┌─────────────────────┐
                    │ Remediation Service  │  (guardrailed action executor:
                    │  - dry-run diff      │   Helm rollback, PR revert,
                    │  - human approval    │   HPA scale — never auto-applies
                    │  - execute + audit   │   without explicit approval)
                    └──────────┬───────────┘
                               ▼
                    ┌─────────────────────┐
                    │ Notification Service │ (Slack, PagerDuty, email)
                    └─────────────────────┘

  ┌──────────────────────────────────────────────────────────┐
  │ API Gateway (REST + WebSocket) ── Web App (Next.js)       │
  │ Auth Service (OIDC/SSO, RBAC) ── Org/Billing Service       │
  └──────────────────────────────────────────────────────────┘
```

## Services (and why each is its own service, not a module)

| Service | Language | Why separate |
|---|---|---|
| **Ingestion API** | Go | Needs to be stateless, horizontally scaled, and handle bursty webhook traffic independently of the rest of the system. |
| **Collector agent** | Go, single static binary | Runs *inside* the customer's cluster (Helm chart), talks outbound-only to Ingestion API — no customer firewall holes, satisfies enterprise security review from day one. |
| **Timeline Service** | Go | Owns the append-only event timeline (Postgres). Simple CRUD-adjacent service, kept separate so the write-heavy timeline never blocks the compute-heavy correlation engine. |
| **Correlation Engine** | Python | The actual differentiated IP, and deliberately LLM-free. Owns two sub-components: a **Rule Engine** (named, unit-tested, individually-weighted correlation rules — time proximity, diff-keyword match, historical-pattern match, ownership distance) and **Knowledge Graph queries** (dependency/ownership/blast-radius traversal over the `service_edges` table, see [05-database.md](05-database.md)). Produces ranked candidates with cited evidence and a deterministic confidence score *before* anything reaches the LLM — this is what makes the system auditable and cheap, and it's fully testable without mocking a model. |
| **AI Reasoning Service** | Python | Wraps the agent loop, RAG (pgvector) retrieval of similar past incidents, and the LLM call itself. Its job is explanation, summarization, and recommendation on top of the Correlation Engine's output — it may refine confidence within a bounded range but must ground every claim in evidence the Rule Engine or Knowledge Graph actually returned (enforced by a citation-validation guardrail, see [07-ai-architecture.md](07-ai-architecture.md)). Isolated so model/provider swaps never touch correlation logic. |
| **Remediation Service** | Go | Executes approved actions against customer infra (Helm/kubectl/GitHub API). Isolated on purpose — this is the highest-blast-radius service, gets the tightest RBAC and its own audit log. |
| **Notification Service** | Go | Thin fan-out to Slack/PagerDuty/email. Separated so a notification-provider outage never blocks the core loop. |
| **Auth Service** | Go, using an OSS IdP library (ory/Kratos or a hosted OIDC provider like WorkOS) | Multi-tenant SSO is a solved problem — buy/integrate, don't build a custom auth stack. |
| **Org/Billing Service** | Go | Stripe integration, seat/usage metering. Isolated because billing correctness bugs must never be able to affect the core product path. |
| **Web App** | Next.js/TypeScript | See [08-ui-design.md](08-ui-design.md). |

`# ponytail: 9 services is already a lot for a solo build — Phase 1 MVP
collapses Timeline+Correlation+Remediation into one Go/Python monolith
behind clean internal interfaces; split into real services only when a team
exists to own each one. See 10-roadmap.md.`

## Data & infra choices

| Concern | Choice | Why |
|---|---|---|
| **Primary DB** | PostgreSQL (RDS) | Relational data (orgs, incidents, timeline events) with strong consistency needs; pgvector extension doubles as the vector store for MVP — no separate vector DB until scale demands it. |
| **Vector store** | pgvector (MVP) → Qdrant/Pinecone (scale) | Avoid a second database for RAG until embedding volume actually requires a dedicated ANN index. |
| **Cache** | Redis (ElastiCache) | Session cache, rate limiting, correlation-engine memoization (same evidence window queried repeatedly during one incident). |
| **Queue/Event Bus** | Amazon SQS+SNS (MVP) → Redpanda (scale) | SQS is "boring and it works" for MVP throughput; Kafka-compatible bus only once fan-out/replay needs justify the ops cost. |
| **Object storage** | S3 | Raw evidence blobs (log excerpts, Terraform plan output) too large/unstructured for Postgres rows. |
| **Search** | Postgres full-text (MVP) → OpenSearch (scale) | Don't stand up OpenSearch for a search feature that ILIKE + `tsvector` handles fine under 100k incidents. |
| **Multi-tenancy** | Single database, `org_id` on every row + Postgres RLS (row-level security) | Cheapest correct isolation model for a B2B SaaS at this stage; schema-per-tenant or DB-per-tenant only if a specific enterprise customer contractually requires physical isolation. |
| **API Gateway** | AWS ALB + a thin Go gateway for auth/rate-limit | Not Kong/Envoy on day one — that's infra to run for a problem ALB + middleware already solves. |
| **Secrets** | AWS Secrets Manager | Customer-provided tokens (GitHub PAT, kubeconfig, cloud creds) are the most sensitive data in the system — never in env vars, never in the DB unencrypted. |
| **Observability of Culprit itself** | OpenTelemetry → Prometheus + Grafana + Loki + Tempo (self-hosted, see 09-infra) | Eating our own dog food is also a resume/interview talking point. |

## Security model (non-negotiable, not deferred)

- Collector agent is **outbound-only** and requests the minimum k8s RBAC
  (read-only on core/apps/batch resources; no secrets access; no write
  access anywhere).
- Remediation actions require an explicit customer-configured allow-list
  (e.g. "allow Helm rollback on namespace `staging`") — nothing is executable
  by default, ever.
- All customer credentials (GitHub tokens, cloud IAM roles) are stored via
  Secrets Manager references, never returned in any API response, and
  scoped to least-privilege on setup.
- Full audit log (who/what/when) for every remediation action, immutable
  (append-only table + S3 archival), exportable for SOC2 evidence.

## Backups & DR

- RDS automated snapshots (daily, 7-day retention MVP → 35-day + cross-region
  for Enterprise tier).
- S3 versioning + lifecycle to Glacier for evidence blobs older than 90 days.
- Infra is 100% Terraform — DR runbook is "restore RDS snapshot to new
  region, `terraform apply` against that region's backend." No bespoke DR
  tooling until a paying customer's contract requires an RTO/RPO number.

## Cost optimization

- Correlation Engine does deterministic filtering *before* any LLM call —
  most alerts never need a model call at all (e.g., no deploys in the
  correlation window → skip straight to "no recent change detected").
  This is both a cost control and a latency win.
- Prompt-cache the incident-memory RAG context (stable across a single
  investigation) — see [07-ai-architecture.md](07-ai-architecture.md) token
  optimization section.
- Spot/Karpenter for the Kubernetes worker nodes running stateless services;
  on-demand only for RDS/Redis.

Continue to [04-folder-structure.md](04-folder-structure.md).
