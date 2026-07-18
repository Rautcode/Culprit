# Part 9: UI Design

The original brief asked for a Datadog-scale UI (cost dashboards, security
dashboards, K8s explorer, Terraform explorer, log explorer, tracing explorer,
admin, full org/settings suite...). Per the scoping decision, we build the
screens the core loop actually needs and explicitly defer the rest — a
platform-grade IA with three real screens beats a wireframed shell around
fifteen empty ones.

## Information architecture (v1 screens)

```
/                        → redirect to /incidents
/incidents               → Incident list (the home screen)
/incidents/[id]          → Incident detail (the core screen — see below)
/services                → Service catalog (read-only list, from Collector data)
/settings/integrations   → Connect GitHub / Kubernetes / Terraform / Prometheus / PagerDuty
/settings/team           → Members, roles (RBAC)
/settings/remediation    → Configure allow-listed remediation actions per environment
/settings/billing        → Plan, usage, invoices
```

Deferred (see [00-INDEX.md](00-INDEX.md) non-goals): standalone cost
dashboard, standalone security dashboard, general log/metrics/trace
explorers (we deep-link into the customer's existing Grafana/Datadog for
that — we're not replacing their observability stack), full audit-log UI
(v1: CSV export only, screen comes in Phase 2 once a customer asks).

## The core screen: Incident Detail

This is the product. Three-pane layout:

```
┌─────────────────────────────────────────────────────────────────┐
│ checkout-service: p99 latency > 2s          [Investigating] 🔴   │
│ opened 4 min ago · severity: high · owner: payments-team          │
├───────────────────────────┬─────────────────────────────────────┤
│ TIMELINE                  │ AI INVESTIGATION (live, streamed)    │
│                            │                                       │
│ 14:32 alert fired          │ ● Gathering evidence...              │
│ 14:31 deploy: checkout     │ ● Found 1 deploy in window (14:31)   │
│       #a3f21c "bump conn   │ ● Checking similar past incidents... │
│       pool size" — jmartin │ ● Found 2 similar (85%, 78% match)   │
│ 14:15 k8s event: HPA       │                                       │
│       scaled 3→7 pods      │ TOP CANDIDATE (92% confidence)       │
│ 13:50 deploy: checkout     │ Deploy #a3f21c reduced DB connection │
│       #d9e102 "..."        │ pool from 50→10. Error logs show     │
│                            │ "pool exhausted" starting 90s after  │
│ [scroll for more →]        │ deploy. Similar to incident #442     │
│                            │ (same root cause, resolved via       │
│                            │ rollback).                            │
│                            │                                       │
│                            │ [ Why 92%? ▾ ] [ View diff ▾ ]        │
│                            │   → rules: 61%, history: 78%,        │
│                            │     LLM adjustment: +9%               │
│                            │                                       │
│                            │ PROPOSED FIX                          │
│                            │ Helm rollback checkout-service to     │
│                            │ revision 47 (pre-#a3f21c)             │
│                            │ [ dry-run diff shown here ]           │
│                            │                                       │
│                            │  [ Approve & Execute ]  [ Reject ]    │
├───────────────────────────┴─────────────────────────────────────┤
│ 💬 Comments · 📎 Link to Slack thread · 📄 Generate postmortem     │
└─────────────────────────────────────────────────────────────────┘
```

Design intent:
- **The AI's reasoning trace streams live** (SSE, see
  [06-api-design.md](06-api-design.md)) — an SRE watching "Gathering
  evidence → Found 1 deploy → Checking history → 92% confidence" builds
  trust incrementally, versus a black-box verdict appearing all at once.
- **Evidence, diff, and the confidence breakdown are always one click away**,
  never hidden — "Why 92%?" expands into the actual rule/history/LLM
  components (see [07-ai-architecture.md](07-ai-architecture.md)
  "Confidence scoring"), not a bare percentage. The "Approve & Execute"
  button next to an unexaminable AI claim is exactly the kind of
  unverifiable-automation SRE teams correctly refuse to adopt.
- **Reject is a first-class action**, tracked and fed back into the eval
  loop (see [07-ai-architecture.md](07-ai-architecture.md)), not a dead end.

## Incident List

Standard filterable table (status, severity, service, time range) — this is
intentionally boring, unglamorous UI. It doesn't need innovation; it needs to
get out of the way and let the SRE get to the incident that matters.

## Design system

- **Dark theme by default** (SRE tooling convention — this audience runs
  terminals and Grafana all day; a light-only UI reads as non-native to the
  domain), light theme supported via `prefers-color-scheme` + a manual
  toggle, not dark-only.
- **Component library**: shadcn/ui + Tailwind — accessible primitives
  (Radix under the hood) out of the box, no need to hand-roll a design
  system from scratch for a v1 product with three real screens.
- **Accessibility**: keyboard navigation through the timeline/evidence
  panes, ARIA live region on the streaming AI investigation pane (screen
  readers should announce new reasoning steps, not just sighted users see
  them), WCAG AA contrast minimum — non-negotiable, not deferred (per the
  standing rule that accessibility basics are never a "later").
- **Responsive**: desktop-first (this is an on-call, at-a-desk-or-laptop
  workflow, not a mobile one) but the incident list and a read-only incident
  summary work on mobile for the "paged at 2am, checking from my phone"
  case — the *approve remediation* action itself requires desktop-width
  confirmation to avoid a fat-thumb production rollback.

`# ponytail: no dedicated design tool output, no Figma file needed for v1 —
shadcn/ui defaults + this IA are enough to start building real screens.
Invest in a bespoke visual identity once there are users to delight, not
before.`

Continue to [09-infrastructure.md](09-infrastructure.md).
