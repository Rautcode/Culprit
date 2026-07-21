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
| 9 | Kubernetes Deployment | 🟡 container + Helm chart kind-verified in CI; EKS/ArgoCD pending AWS access |
| 10 | CI + automated evaluation | ✅ regression suite = golden-set eval, precision@1 gate |

**35 tests green.** The regression suite doubles as the golden-set
evaluation: every scenario is a ground-truthed incident, and CI gates
precision@1 = 100% (top candidate == injected cause) plus the full
expectation set — confidence floors, rule hits, evidence citations, decoy
ordering, timeline chronology, and the LLM guardrail contract. A rule or
weight change that flips any ranking fails before merge.

**What's proven vs. designed:** the deterministic pipeline, RAG memory,
LLM explanation layer, and web UI all run and are tested. The LLM layer's
production client (`AnthropicModel`) is contract-pinned by a scripted stub
in CI but not exercised against a live API here. The EKS/Terraform/ArgoCD
cloud deployment is designed and the same chart is kind-verified, but not
yet applied to a real cluster. No design-partner usage or real-incident
precision numbers exist yet — those are Phase 1 exit criteria, see
[SPEC_VERSION.md](SPEC_VERSION.md).

Design decisions that changed a frozen spec item go through an ADR — see
[docs/adr/](docs/adr/) and the amendment log in `SPEC_VERSION.md`.

## Run it

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
