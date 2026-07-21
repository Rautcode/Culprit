# Culprit

> The AI SRE that finds what broke prod, before your engineers do.

Deployment-aware, causal root-cause analysis for Kubernetes/GitOps stacks.
A deterministic Rule Engine + Knowledge Graph correlate alerts against
recent deploys; a Vector DB (RAG) surfaces historical precedent; an LLM
reasons and explains on top of that evidence — never inventing a
conclusion it can't cite.

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

**50 tests green** (plus a Postgres/pgvector suite that runs against a real
database in CI). The regression suite doubles as the golden-set
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

## Repo layout

See [docs/04-folder-structure.md](docs/04-folder-structure.md) for the full
layout and the reasoning behind it.
