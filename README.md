# Culprit

> The AI SRE that finds what broke prod, before your engineers do.

[![CI](https://github.com/Rautcode/Culprit/actions/workflows/ci.yml/badge.svg)](https://github.com/Rautcode/Culprit/actions/workflows/ci.yml)
![Python 3.13](https://img.shields.io/badge/python-3.13-3776AB?logo=python&logoColor=white)
![tests 69 passing](https://img.shields.io/badge/tests-69%20passing-brightgreen)
![precision@1 100%](https://img.shields.io/badge/golden--set%20precision%401-100%25-brightgreen)
![License MIT](https://img.shields.io/badge/license-MIT-blue)

**What:** when a production alert fires, Culprit answers "which recent
change caused this?" — correlating deploys, config, Terraform, and
Kubernetes events against the alert, then explaining its verdict with cited
evidence and proposing a guardrailed fix.

**Why:** during an incident, "what changed?" is the most expensive question
and the one no tool answers — deploy history, config, IaC, metrics, and pod
state live in five disconnected systems that an on-call engineer
cross-references by hand while the outage runs. That phase, not the fix, is
the longest segment of a typical incident timeline.

**How it's different:** the correlation is **deterministic** (a Rule Engine
+ Knowledge Graph produce cited evidence and a defensible score); an LLM
only *explains* on top, bounded so it provably cannot invent a conclusion.
The system gives a correct, evidence-backed answer even with the LLM
switched off entirely. → [the case study](CASE-STUDY.md) for the full story.

## Architecture

The built core loop — every step before the LLM is pure, deterministic,
tested code:

```mermaid
flowchart LR
    A[Alert] --> B[Gather evidence<br/>deploys·config·IaC·k8s]
    B --> C[Knowledge Graph<br/>dependency+blast radius]
    C --> D[Rule Engine<br/>5 weighted rules]
    D --> E[RAG memory<br/>past incidents]
    E --> F[Confidence<br/>rules·history·LLM ±15%]
    F --> G[LLM explanation<br/>grounded, bounded]
    G --> H[Verdict<br/>+ evidence + fix]
```

The designed multi-service topology (Phase 2+ — see
[docs/03-architecture.md](docs/03-architecture.md)) collapses into one
process for v1; these are the boundaries it splits along, not nine separate
deployables today:

```mermaid
flowchart TD
    COL[Collector agent<br/>outbound-only] --> ING[Ingestion API]
    ING --> BUS[(Event bus)]
    BUS --> CORR[Correlation Engine<br/>rules + graph]
    BUS --> TL[Timeline Service]
    CORR --> AIR[AI Reasoning<br/>RAG + LLM]
    AIR --> REM[Remediation<br/>guardrailed, human-approved]
    REM --> NOT[Notification]
```

## Start here

- **[SPEC_VERSION.md](SPEC_VERSION.md)** — the frozen v1.0 spec and build sequence. Read this first.
- **[docs/00-INDEX.md](docs/00-INDEX.md)** — full design doc set (problem validation → architecture → AI pipeline → infra → roadmap).
- **[SETUP.md](SETUP.md)** — go-live checklist: what runs today, and the credential-gated tiers to activate the rest.
- **[CASE-STUDY.md](CASE-STUDY.md)** — the portfolio writeup: the problem, the three decisions that make it senior work, and what's proven vs. designed.

## Status

The core loop is built, tested, and CI-verified end to end. Every step of
the [v1.0 Build Sequence](SPEC_VERSION.md) has a working, verified
implementation; what remains of step 9 is gated purely on cloud
credentials, not code. CI runs on every push (see `.github/workflows/ci.yml`).

| # | Build-sequence step | State |
|---|---|---|
| 1 | Incident Simulation Harness | ✅ 18 scenarios, ground-truthed |
| 2 | Evidence Collection | ✅ source adapters + idempotent store |
| 3 | Knowledge Graph | ✅ `depends_on` / sibling / `monitored_by` coupling |
| 4 | Rule Engine | ✅ 5 frozen rules, per-rule evidence |
| 5 | Confidence Scoring | ✅ composite formula, ±0.15 LLM bound |
| 6 | RAG Retrieval | ✅ incident memory, two-sided precedent |
| 7 | LLM Explanation Layer | ✅ bounded reasoning behind the grounding guardrail |
| 8 | Web UI | ✅ Incident List + Detail on real pipeline output |
| 9 | Kubernetes Deployment | 🟡 container + Helm chart kind-verified in CI; EKS/ECR/OIDC Terraform written + CI-validated, `apply` pending AWS credentials |
| 10 | CI + automated evaluation | ✅ regression suite = golden-set eval, precision@1 gate, per-layer + per-rule metrics report |

**55 tests green** locally, plus a 14-test Postgres/pgvector suite that runs
against a real database in CI — 69 in total. The regression suite doubles as the golden-set
evaluation: every scenario is a ground-truthed incident, and CI gates
precision@1 = 100% (top candidate == injected cause) plus the full
expectation set — confidence floors, rule hits, evidence citations, decoy
ordering, timeline chronology, and the LLM guardrail contract. A rule or
weight change that flips any ranking fails before merge.

**What's proven vs. designed:** the deterministic pipeline, RAG memory
(lexical and pgvector backends, CI-tested against real Postgres), the LLM
explanation layer, the `culprit` CLI (demo / diagnose / learn / eval, with
persistent incident memory), and the web UI all run and are tested. The
golden-set evaluation (`culprit eval`) publishes per-layer and per-rule
precision into every CI run's summary — including an honest authored-bias
flag when a single rule matches the composite on simulated data. Still
credential-gated, not claimed: `culprit diagnose --explain` wires the
LLM layer into the CLI behind the grounding guardrail (CI-tested with a
scripted model), but the production client (AnthropicModel) and semantic
embedder (VoyageEmbedder) are pinned by deterministic stand-ins, not
exercised against live APIs; the
EKS/Terraform/ArgoCD cloud deployment is kind-verified but not applied to
a real cluster. No design-partner usage or real-incident precision numbers
exist yet — those are Phase 1 exit criteria, see
[SPEC_VERSION.md](SPEC_VERSION.md).

Design decisions that changed a frozen spec item go through an ADR — see
[docs/adr/](docs/adr/) and the amendment log in `SPEC_VERSION.md`.

## Run it

The 5-minute demo — a simulated incident through the real pipeline, verdict
with cited evidence (Phase 0 validation artifact, see
[docs/validation/](docs/validation/)):

```
cd services/correlation-engine
python -m correlation_engine.cli demo list
python -m correlation_engine.cli demo deadlock
```

Real output (a deadlock whose culprit is in a *different* service, coupled
only through a shared database — the case naive time-ordering gets wrong):

```text
ALERT [high] orders-service: database deadlock errors spiking

=== ROOT CAUSE CANDIDATES ===
>> #1  deploy-dead10  (billing-service, by grace)
     add invoice reconciliation job that batch-updates orders table in a transaction
     confidence 19%  (rules 39% · history 0% · llm +0%)
       - time_proximity: {"gap_seconds": 240.0}
       - ownership_distance: {"hops": 2, "shared_dependency": "orders-db"}
       - diff_keyword_match: {"matched_keywords": ["transaction"]}
       - blast_radius_weight: {"dependent_count": 1}

   #2  deploy-0rd3r5  (orders-service, by felix)   ← same-service decoy, ranked below
     improve order search pagination
     confidence 16%  (rules 32% · history 0% · llm +0%)

GROUND TRUTH: deploy-dead10 — pipeline verdict is correct.
```

Every line of evidence is a named rule with its inputs; the confidence
decomposes into `rules · history · LLM`. With a seeded memory store
(`culprit learn`), the `history` term lights up and a recurrence cites the
past incident and the fix that resolved it.

`culprit diagnose` runs the same pipeline on your own exported evidence
(`kubectl get events -o json` + a deploys JSON) — no agent, no credentials,
offline. `--explain` adds an LLM narrative on top (needs ANTHROPIC_API_KEY
+ the ai-reasoning package; the verdict itself is unchanged). See
`python -m correlation_engine.cli diagnose --help`.

Golden-set evaluation — per-layer and per-rule precision (the same report
CI publishes into every run's summary):

```
python -m correlation_engine.cli eval
```

With a Postgres DSN, `eval` also compares the lexical vs pgvector memory
backends on the golden set — the data behind the "adopt embeddings only if
they win" gate. It runs isolated and rolls back, so recorded incidents are
never touched:

```
culprit eval --memory-dsn postgresql://culprit:culprit@localhost:5432/culprit
```

Pipeline tests + golden-set evaluation:

```
python -m pytest services/correlation-engine/tests services/ai-reasoning/tests -v
```

Web UI (renders real pipeline output; regenerate after pipeline changes
with `python scripts/export_incidents.py`):

```
cd apps/web && npm install && npm run dev   # http://localhost:3000/incidents
```

Deploy to a local cluster (needs Docker + kind + helm):

```
docker build -t culprit-web:dev apps/web
kind create cluster --name culprit
kind load docker-image culprit-web:dev --name culprit
helm install culprit infra/helm/culprit-platform
kubectl port-forward svc/culprit-web 8080:80   # http://localhost:8080/incidents
```

Local backing services (postgres+pgvector, redis, redpanda, minio) for the
Phase 2 service split:

```
docker-compose up -d
```

## Tech stack

Honest about what's load-bearing vs. scaffolded — the same discipline as
the Status table above.

| Layer | Built with | State |
|---|---|---|
| Correlation engine, RAG, evaluation | **Python 3.13** (stdlib-only core; `psycopg` optional) | the real IP, fully tested |
| AI reasoning / LLM layer | Python + Anthropic SDK (`claude-opus-4-8`) | wired, guardrailed; live calls key-gated |
| Incident memory | **PostgreSQL + pgvector** | both lexical & vector backends, CI-tested on real PG |
| Web UI | **Next.js 16 / TypeScript / Tailwind** | Incident List + Detail, prerendered |
| Packaging & deploy | **Docker · Helm · Kubernetes** (kind-verified in CI) | container + chart deploy proven on a live cluster |
| Cloud infra | **Terraform · AWS EKS/ECR** (OIDC keyless CI) | written + `terraform validate`-clean; `apply` pending creds |
| CI/CD | **GitHub Actions** | golden-set eval gate, real-PG tests, kind deploy, TF validate |
| Backend services | **Go** module (ingestion, timeline, remediation, …) | scaffold — boundaries defined, bodies are Phase 2 |

Deliberately *not* yet present (designed in [docs/](docs/), not claimed as
built): OpenTelemetry tracing, Prometheus/Grafana self-observability, a REST
API server (the CLI is the current interface), and the multi-tenant SaaS
shell. The repo says so everywhere rather than implying completeness.

## Repo layout

See [docs/04-folder-structure.md](docs/04-folder-structure.md) for the full
layout and the reasoning behind it.

## License

[MIT](LICENSE) © 2026 Manav Raut.
