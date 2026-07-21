# Phase 0 — problem-statement posts (DRAFTS — not posted)

Per [docs/02-product-decision.md](../02-product-decision.md): post the
**problem**, not the product. The goal is to see whether people describe
this exact pain unprompted — replies mentioning a tool we didn't name are
data; pitching would poison the sample. **These are drafts for you to
review, adapt, and post yourself** — nothing here has been published.

Etiquette: r/devops and r/sre allow discussion posts; avoid any link to
the repo in the post itself (that turns it into promotion). Engage every
substantive reply; DM the best ones toward an interview slot.

---

## r/sre / r/devops (discussion post)

**Title:** How do you actually figure out *which* change broke prod?

**Body:**

When an alert fires, "did a recent change cause this?" seems to be the
first question everyone asks and the last one any tool answers. Last
incident I debugged, the cause was a config change on a service one hop
upstream of the one alerting — took 40 minutes and five tabs (Grafana,
ArgoCD history, git log, Slack #deploys, kubectl) to connect them.

Genuinely curious what the state of the art is on real teams:

1. What's your actual mechanic for correlating an alert with recent
   deploys / config changes / flag flips / Terraform applies?
2. How long does "identify the causal change" typically take vs. fixing it?
3. Has anyone rolled back the *wrong* thing because time pressure said
   "newest deploy did it"?
4. Deploy markers on dashboards, incident-bot timelines, AIOps alert
   grouping — does any of it actually answer "which change," or just
   decorate the graph?

Not selling anything — trying to figure out if this is a real gap or if
I'm just bad at looking at five tools at once.

---

## r/kubernetes (variant, more topology-flavored)

**Title:** Incident postmortems keep having the same line: "the change was
in a different service than the alert"

**Body:**

Pattern I keep hitting: alert fires on service A; the cause is a change
to service B that A depends on — or a NetworkPolicy, a flag ramp, an IAM
change, something with no deploy marker anywhere near A's dashboard. The
k8s event stream knows, ArgoCD knows, GitHub knows, but nothing joins
them. How do your on-call folks connect an alert to a change across the
dependency graph today? Service catalogs? Mesh telemetry? Vibes?

---

## CNCF Slack #observability / #sre (short form)

> Question for on-call folks: when an alert fires, what actually answers
> "which recent change caused this" for you — across deploys, config,
> flags, and Terraform, not just the alerting service's own pushes? Deploy
> markers and alert grouping never seem to answer *which change*. Curious
> what real setups look like; happy to trade notes from ~N interviews I'm
> doing on this. (Replace N as interviews accumulate.)

---

## Scoring replies (add rows to 03-candidate-tracker.md)

- **Strong signal:** describes the five-tabs dance unprompted; names
  time lost; has a wrong-rollback story; asks "does anything do this?"
- **Weak signal:** "we don't have this problem" from mono-repo/mono-service
  teams (out of ICP — note and move on).
- **Counter-signal worth taking seriously:** "tool X already solves this,
  we use it daily" — go read tool X again with fresh eyes.
