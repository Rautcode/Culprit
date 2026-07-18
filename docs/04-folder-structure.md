# Part 5: Repository Structure

Monorepo. A solo/small team cannot afford the coordination overhead of
polyrepo for a system this interconnected — one PR that touches the event
schema should touch producer and consumer in the same diff.

```
culprit/
├── apps/
│   ├── web/                      # Next.js frontend (see 08-ui-design.md)
│   │   ├── app/                  # App Router: /incidents, /dashboard, /settings
│   │   ├── components/
│   │   ├── lib/
│   │   └── package.json
│   └── collector/                # Go binary shipped as Helm chart to customer clusters
│       ├── cmd/collector/
│       ├── internal/{k8swatch,gitwatch,shipper}/
│       └── go.mod
│
├── services/
│   ├── ingestion-api/             # Go — webhook + collector intake
│   ├── timeline/                  # Go — event timeline CRUD
│   ├── correlation-engine/        # Python — evidence gathering + ranking (core IP)
│   │   ├── correlation_engine/{sources,ranking,filters}/
│   │   └── pyproject.toml
│   ├── ai-reasoning/               # Python — agent orchestration, RAG (see 07)
│   │   ├── ai_reasoning/{agent,rag,prompts,evals}/
│   │   └── pyproject.toml
│   ├── remediation/                 # Go — guardrailed action executor
│   ├── notification/                # Go — Slack/PagerDuty/email fan-out
│   ├── auth/                        # Go — OIDC/SSO, RBAC
│   └── billing/                     # Go — Stripe, usage metering
│
├── libs/                          # Shared code, imported by services above
│   ├── go/{eventschema,authmw,telemetry}/
│   └── py/{eventschema,telemetry}/
│
├── infra/
│   ├── terraform/
│   │   ├── modules/{vpc,eks,rds,redis,s3,cloudfront,iam,acm,route53}/
│   │   └── environments/{dev,staging,prod}/
│   ├── helm/
│   │   ├── culprit-platform/       # our own services' chart
│   │   └── culprit-collector/      # chart shipped TO customers
│   └── k8s/
│       ├── argocd/                 # GitOps app-of-apps definitions
│       └── policies/               # OPA/Kyverno guardrail policies
│
├── .github/workflows/              # CI: lint/test/build per service, path-filtered
│
├── docs/                           # this doc set + ADRs + OpenAPI spec
│   └── adr/
│
├── scripts/                        # dev bootstrap, local docker-compose up
├── docker-compose.yml              # local dev: postgres, redis, redpanda, minio
└── README.md
```

## Rules this structure encodes

- **Path-filtered CI**: a PR touching only `apps/web` doesn't rebuild/redeploy
  Go services. GitHub Actions `paths:` filters per workflow.
- **Event schema lives in `libs/`, not duplicated** per service — the #1 cause
  of "the correlation engine and the timeline service disagree about what a
  field means" bugs in event-driven systems.
- **No `shared/` junk-drawer package.** Each lib in `libs/` has one clear
  reason to exist (schema, auth middleware, telemetry setup) — if a fourth
  reason shows up, it gets its own lib, not appended to an existing one.
- **`correlation-engine/` and `ai-reasoning/` are separate services** even
  though both are Python, because they scale differently (correlation is
  CPU/IO-bound and cheap to run per-alert; AI reasoning is the expensive,
  rate-limited path) and because keeping deterministic logic out of the
  LLM-calling service makes the deterministic part unit-testable without
  mocking an LLM.

`# ponytail: Phase 1 collapses services/{timeline,correlation-engine,
remediation} into one process with internal package boundaries mirroring
this structure — same folder layout, fewer deployables. Split into real
services in Phase 2 once there's load/team justification. See 10-roadmap.md.`

Continue to [05-database.md](05-database.md).
