# CI

`ci.yml` (build step 10, SPEC_VERSION.md):

- **pipeline-eval** — the regression suite doubles as the golden-set
  evaluation: every harness scenario is ground-truthed, and the suite gates
  precision@1 = 100% plus rule hits, confidence floors, evidence citations,
  decoy ordering, and the LLM guardrail contract. Also fails if
  `apps/web/lib/incidents.json` drifts from what the current pipeline
  actually produces.
- **web-build** — production build of the Next.js app (all incident pages
  prerendered).

Not here yet, deliberately: container build/push and deploy jobs (build
step 9 — EKS/ArgoCD; needs Docker + cluster access), and per-service path
filtering (arrives with the Phase 2 service split).
