# Part 3: The Product Decision

## The pick

**Culprit** — an AI SRE copilot that, the moment an alert fires, automatically
answers "what changed, and is that the cause?" by correlating git deploys,
Helm/Kustomize diffs, Terraform plans, Kubernetes events, and
metrics/logs/traces — then proposes a guardrailed fix (rollback a Helm
release, revert a PR, scale a deployment) that a human approves, and files the
whole thing into a searchable incident memory so the next occurrence is
answered in seconds via RAG instead of minutes of investigation.

## Full validation (13 fields)

| Field | Answer |
|---|---|
| **Problem** | During an incident, "what changed recently that could have caused this" is answered by manually grepping five disconnected systems (git log, Helm history, Terraform plan output, `kubectl get events`, and a dashboard) under time pressure. |
| **Root Cause** | Deployment/change metadata and observability data live in structurally separate systems with no shared timeline or causal model. Every vendor treats "what changed" as a UI annotation, not as first-class, queryable, reasoned-over data. |
| **Business Impact** | MTTR is directly tied to revenue during outages; industry-cited downtime-cost figures (Gartner's commonly referenced ~$5,600/min average, far higher for e-commerce/fintech) make even a 10-minute reduction in cause-identification time worth real money at any company running production traffic. This is directional, not a number we can independently verify — treat it as "material, not proven" until we have our own case-study data. |
| **Engineering Impact** | On-call engineers lose focus time to interruptions; "detective work" during an incident is the least satisfying, most error-prone part of SRE work and a top cause of on-call burnout cited in SRE surveys. |
| **Frequency** | Every incident, at any org running microservices on Kubernetes — realistically weekly at a 20-engineer startup, daily at a 200+ engineer org. |
| **Severity** | High. This is the phase that turns "brief blip, nobody notices" into "45-minute customer-facing outage, exec follow-up." |
| **Companies Affected** | Any company running Kubernetes + GitOps (ArgoCD/Flux) + a standard observability stack (Prometheus/Grafana/Datadog). That's the median modern cloud-native company, not a niche. |
| **Current Solutions** | Datadog/Grafana deployment markers (visual only, no reasoning). BigPanda/Causely/Moogsoft (enterprise AIOps, alert-correlation-first, six-figure contracts, closed platforms). incident.io/Rootly Copilot (postmortem *summarization* from Slack, not causal analysis from infra data). Komodor (K8s-native RCA, closer competitor, but doesn't reach into Terraform/cloud IaC or propose remediation). |
| **Why Current Solutions Fail** | They either (a) show correlation visually and leave reasoning to the human, (b) correlate alerts to each other but not to code/infra changes, or (c) are priced/scoped for enterprise AIOps buyers, leaving the mid-market Kubernetes-native company underserved. None combine git + Helm/Kustomize + Terraform + k8s events + metrics into one causal timeline with an LLM doing the reasoning and a proposed, human-approved fix. |
| **AI Opportunity** | This is a genuine agentic-AI-shaped problem, not an LLM-wrapper — and the strongest version of it isn't "LLM does everything." The architecture layers a deterministic Rule Engine + Knowledge Graph (does the actual correlation, produces cited evidence and a defensible confidence score) with a Vector DB/RAG memory (surfaces precedent) and puts the LLM only at the reasoning/explanation/recommendation layer on top. That's closer to how mature enterprise AIOps systems are actually built than a single model call, and it's the difference between a system an SRE team will trust with a rollback button and one they won't. Full design in [07-ai-architecture.md](07-ai-architecture.md). |
| **Startup Opportunity** | Credible wedge into a market with recent comparable exits/rounds (Causely, BigPanda, Zebrium→CrowdStrike) proving the category is fundable; the differentiation ("code-level causal attribution for Kubernetes-native teams," mid-market pricing, self-hostable) is defensible against enterprise-only incumbents. |
| **Resume Value** | Extremely high — demonstrates Kubernetes internals, GitOps, distributed systems debugging, agentic AI with real tool use (not a chatbot demo), observability pipeline design, and a quantifiable business metric (MTTR) to talk about in interviews. |
| **Difficulty** | Appropriately hard for a flagship project: real complexity in the correlation engine and guardrails, but the MVP is scopeable to 2 data sources (GitHub deploys + Kubernetes events + Prometheus) before expanding to Terraform/Helm. |

## Validation plan (before writing a line of infra code)

1. Post the problem statement (not the product) in r/devops, r/kubernetes,
   r/sre, and the CNCF Slack `#observability` channel: *"How do you currently
   figure out which deploy caused an incident?"* — gauge whether people
   describe this exact pain unprompted.
2. Talk to 8-10 SRE/platform engineers (warm network + cold LinkedIn outreach)
   with a 15-minute structured interview: how they currently do this, what
   they've tried, what they'd pay for it to be faster.
3. Ship a CLI-only proof of concept (`culprit diagnose <alert-id>` reading
   local kubeconfig + GitHub token) to 3-5 of those engineers before building
   any UI or multi-tenant SaaS — this validates the correlation engine's
   accuracy before investing in the platform shell.
4. Only after the CLI proves useful to real users does the SaaS platform
   (Parts 4-11) get built.

`# ponytail: validation gate before platform build — a correlation engine
that isn't accurate makes a beautiful SaaS around it worthless.`

## Why not the runner-up (canary/progressive-delivery AI analysis)?

It's a real, high-resume-value problem, but it requires the exact same
deployment-metadata ingestion pipeline as Culprit's core loop — building it
as a *feature* of Culprit once the core loop works is strictly better than
building it as a second product. It's the natural Phase 3 expansion (see
[10-roadmap.md](10-roadmap.md)).

Continue to [03-architecture.md](03-architecture.md).
