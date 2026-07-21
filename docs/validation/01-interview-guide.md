# Phase 0 — SRE interview guide (15 minutes)

Goal per [docs/02-product-decision.md](../02-product-decision.md): find out
whether "which change caused this incident?" is a pain people describe
**unprompted**, how they solve it today, and whether the CLI's output is
useful on their incidents. This is a listening script, not a pitch — the
product isn't mentioned until section 4, and only if section 2 surfaced
the pain without prompting.

## 0. Setup (1 min)

- Who they are: role, team size, on-call rotation? Stack: k8s? GitOps
  (ArgoCD/Flux)? Observability (Prometheus/Datadog/other)?
- Permission to take notes. No recording unless offered.

## 1. Last real incident (5 min) — the core of the interview

> "Walk me through the last production incident you personally debugged.
> From the page to the fix — what did you actually do, minute by minute?"

Listen for (do NOT prompt these):
- [ ] Did they cross-reference deploys/changes against the alert timeline?
- [ ] How many tools did they touch to answer "what changed"? Name them.
- [ ] How long from page to *cause identified* (not to fix)?
- [ ] Was the cause a change (deploy/config/flag/infra)? Whose?
- [ ] Any wrong turns — time spent suspecting the wrong thing?

## 2. The general case (4 min)

> "When something breaks, how do you figure out whether a recent change
> caused it — and which one?"

- What's the actual mechanic? (Slack #deploys scrollback? ArgoCD history?
  `git log` + squinting? Datadog deploy markers? Tribal knowledge?)
- > "What's the most annoying part of that?"
- > "Ever rolled back the wrong thing?" (Their story here is gold.)
- Cross-service: > "What if the bad change was in a service upstream of
  the one alerting — or in Terraform, or a feature flag?"

## 3. Magic wand + money (2 min)

- > "If a tool could answer 'what changed and is that the cause' — what
  would it need to show you before you'd trust it enough to act on it?"
  (Listen for: evidence, confidence, blast radius — matches our design or not?)
- > "Does your team pay for anything adjacent today?" (Datadog, incident.io,
  Komodor, PagerDuty AIOps…) "What does it not do?"

## 4. The artifact (3 min — only if pain surfaced unprompted)

Show `culprit demo` on a scenario matching their stack (see
[04-demo-script.md](04-demo-script.md)). Then:

- > "Is this the answer you'd want at 2am? What's missing?"
- > "Would you run `culprit diagnose` on files exported from your own
  cluster after your next incident? What would stop you?"
- If strong: ask to be a design partner (3-5 slots — real incidents,
  monthly feedback, free forever tier).

## Log it

Record in [03-candidate-tracker.md](03-candidate-tracker.md) same day:
pain unprompted? time-to-cause? tools count? demo reaction verbatim?
pilot yes/no. Verbatim quotes beat summaries — they end up in the pitch.
