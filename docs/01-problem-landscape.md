# Part 1-2: Problem Landscape & Ranking

Per scoping decision, this is not a 100-item catalog padded with filler. It's
~16 real, distinct, well-documented DevOps pain points — enough breadth to
credibly rank and pick one — sourced from patterns repeatedly described in:
Google/Meta/Uber/Netflix/Cloudflare engineering blogs and postmortems, the
Google SRE books, the annual DORA/State of DevOps reports, the CNCF annual
survey, and recurring threads in r/devops, r/kubernetes, r/sre, and HN
"Show HN" launches (which double as informal market validation — if five
different startups are chasing a niche, the pain is real).

Each entry: **Problem | Root cause | Business impact | Frequency/Severity |
Who's affected | Why current tools don't fully solve it | AI angle**.

---

### 1. No causal link between "a deploy/config change happened" and "prod broke"
Engineers manually eyeball deploy timelines against alert timestamps during an
incident. Root cause: deployment metadata (git SHA, Helm values diff,
Terraform plan) lives in a different system than metrics/logs/traces, and
nobody has time mid-incident to cross-reference five tools. Business impact:
MTTR inflation — the "detect → identify cause" phase is consistently the
longest segment of an incident timeline in published postmortems (Google SRE
workbook, GitLab's public incident reviews). Frequency: every incident, i.e.
weekly-to-daily at any company running microservices. Severity: high — this
is the segment that turns a 5-minute blip into a 45-minute outage. Affects:
anyone on Kubernetes/GitOps with more than ~10 services. Current tools
(Datadog, Grafana, New Relic) show deployment *markers* on a graph but do not
reason about *which* change is the likely cause across git + IaC + k8s events.
AI angle: exactly the multi-source correlation + reasoning task LLM agents are
good at. **→ This is the one we build (see [02-product-decision.md](02-product-decision.md)).**

### 2. Alert fatigue / noisy paging
Root cause: static thresholds, no correlation across flapping alerts for the
same underlying event. Impact: on-call burnout, alert blindness (real
incidents missed inside noise). Frequency: daily at scale. Affects: any org
with PagerDuty/Opsgenie. Current solutions: BigPanda, incident.io, Rootly
already do AI alert-grouping — **crowded, well-funded space.** AI angle: real
but saturated.

### 3. Kubernetes OOMKill / CrashLoopBackOff root-cause explanation
Root cause: resource limits set by guesswork, no easy diff of "what changed
before this pod started crashing." Impact: developer time lost to `kubectl
describe` archaeology. Frequency: very high, daily in any active cluster.
Current solutions: Komodor, Botkube partially cover this — **crowded.**

### 4. IaC drift (Terraform state vs. real cloud state silently diverges)
Root cause: manual console changes, partial applies, out-of-band automation.
Impact: security exposure + "works on my terraform, not in prod" incidents.
Current solutions: driftctl (discontinued), env0, Spacelift — **covered
reasonably well already.**

### 5. Flaky CI tests
Root cause: test isolation issues, timing/race conditions, shared state.
Impact: Google has publicly cited roughly 1 in 7 test failures at their scale
being flaky rather than real; engineering time lost to re-runs and lost trust
in CI is a widely cited cost across large orgs. Current solutions: Trunk.io,
BuildPulse — **decent coverage already, crowded.**

### 6. Kubernetes cost attribution / rightsizing
Root cause: shared clusters, no per-team cost visibility, over-provisioned
requests. Current solutions: Kubecost, CAST AI, Vantage — **crowded, capital-heavy incumbents.**

### 7. Secrets sprawl across CI/CD, k8s, and cloud IAM
Root cause: no single source of truth, secrets copy-pasted into pipeline env
vars. Current solutions: HashiCorp Vault, Doppler, Infisical — **solved at
the infra layer already; differentiation is thin.**

### 8. Postmortem writing is manual and inconsistent
Root cause: no automatic timeline capture, engineers reconstruct events from
memory/Slack days later. Current solutions: incident.io Copilot, Rootly AI —
**actively being built by well-funded incident-management vendors.**

### 9. "Which service owns this alert / who do I page" (ownership drift)
Root cause: no live-maintained service catalog. Current solutions: Backstage,
Port — **strong open-source incumbent (Backstage), hard to unseat.**

### 10. Canary/progressive-delivery analysis is manual
Root cause: engineers eyeball canary metrics vs. baseline instead of
statistical comparison. Netflix (Kayenta) and Google built internal tools for
this. Current solutions: Argo Rollouts + Flagger already do the mechanics;
the AI-judgment layer is thin. Real gap, but narrower than #1.

### 11. Multi-cloud IAM permission sprawl / least-privilege drift
Root cause: permissions granted broadly "to unblock" and never revoked.
Current solutions: AWS IAM Access Analyzer, Wiz, Ermetic — **crowded, well-funded CNAPP space.**

### 12. Runbook knowledge lives in tribal memory / stale wikis
Root cause: runbooks written once, never updated, not linked to live alerts.
Overlaps heavily with #1's remediation-suggestion angle — folded in as a
supporting feature rather than a separate product.

### 13. Terraform PR review is manual and risk-blind
Root cause: reviewers can't easily see blast radius of a `terraform plan`
(e.g. "this touches the prod VPC used by 40 services"). Current solutions:
Spacelift, env0 show the plan but not blast-radius-aware risk scoring. Real
gap, adjacent to #1's "what changed" data model — good Phase-2 feature, not a
standalone product.

### 14. Dependency/CVE noise in container scanning
Root cause: scanners report thousands of CVEs with no exploitability context.
Current solutions: Snyk, Trivy + AI triage (already emerging, e.g. Endor
Labs) — **crowded, becoming table stakes.**

### 15. Kubernetes upgrade risk (deprecated API usage, breaking changes)
Root cause: no easy way to know if a cluster upgrade will break workloads.
Current solutions: `kubent`, Pluto — **niche, low revenue ceiling, one-shot
tool not a platform.**

### 16. Log volume cost explosion (Datadog/Splunk bills exploding)
Root cause: verbose logging with no sampling/routing intelligence. Current
solutions: Cribl, Observo — **funded incumbents already solving this well.**

---

## Ranking (1-10 each, Total = sum)

| # | Problem | Market Demand | Tech Difficulty (10=hard,good) | Revenue Potential | Resume Value | Innovation | Competition (10=low competition) | Solo Feasibility | **Total** |
|---|---|---|---|---|---|---|---|---|---|
| 1 | Deployment-aware causal RCA | 9 | 8 | 8 | 10 | 8 | 6 | 6 | **55** |
| 2 | Alert fatigue / grouping | 8 | 5 | 7 | 6 | 3 | 2 | 6 | 37 |
| 3 | K8s crash root-cause | 7 | 6 | 6 | 7 | 5 | 4 | 7 | 42 |
| 4 | IaC drift | 6 | 5 | 5 | 6 | 3 | 3 | 6 | 34 |
| 5 | Flaky tests | 6 | 6 | 5 | 5 | 3 | 3 | 6 | 34 |
| 6 | K8s cost/rightsizing | 8 | 6 | 7 | 6 | 3 | 2 | 5 | 37 |
| 7 | Secrets sprawl | 5 | 4 | 4 | 4 | 2 | 2 | 6 | 27 |
| 8 | Postmortem automation | 7 | 5 | 6 | 6 | 4 | 3 | 7 | 38 |
| 9 | Service ownership catalog | 6 | 4 | 5 | 5 | 2 | 2 | 5 | 29 |
| 10 | Canary analysis AI | 6 | 7 | 6 | 8 | 6 | 5 | 5 | 43 |
| 13 | Terraform PR blast-radius | 6 | 6 | 5 | 6 | 5 | 6 | 6 | 40 |

*(Only entries with a real total >30 shown in ranked form; 7, 9, 11, 14-16
were scored low enough on competition/revenue/innovation to exclude from
the table entirely — they're documented above for completeness, not because
they're contenders.)*

**#1 wins clearly** — highest resume value, highest market demand, and while
competition exists (BigPanda, Causely) it's enterprise-priced, closed, and
focused on *alert* correlation, not *code-level causal attribution*. That gap
is the wedge. #10 (canary analysis) is a strong second and becomes a **Phase 3
feature** of #1 rather than a separate product — it needs the exact same
deployment-metadata pipeline.

Continue to [02-product-decision.md](02-product-decision.md) for the full
validation of the chosen problem.
