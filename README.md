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

Pre-code. Scaffolding only — see `SPEC_VERSION.md` "v1.0 Build Sequence" for
what gets built, in what order, starting with the Incident Simulation
Harness.

## Local dev

```
docker-compose up -d     # postgres (pgvector), redis, redpanda, minio
```

## Repo layout

See [docs/04-folder-structure.md](docs/04-folder-structure.md) for the full
layout and the reasoning behind it.
