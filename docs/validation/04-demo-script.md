# Phase 0 — demo script (5 minutes, terminal first)

The demo is the CLI, not the web UI — SREs trust terminals, and the CLI
shows its work. The web UI is the encore, not the opener. Everything shown
is a real pipeline run; nothing is mocked — say so out loud, it's the
whole differentiator.

## Setup (before the call)

```
cd services/correlation-engine
python -m correlation_engine.cli demo list   # confirm it runs
```

Pick 2 scenarios matching their stack from the interview:
- Datadog/Prometheus shop, config-heavy: `bad_configmap` (cross-service culprit)
- Heavy flag usage: `feature_flag_failure` (culprit has no commit at all)
- Platform team: `broken_scraping` (monitoring-topology culprit + precedent)
- Default pair: `deadlock` + `broken_scraping`

## Beat 1 — the verdict (90 s)

```
python -m correlation_engine.cli demo deadlock
```

Talk track: "Alert on orders-service, database deadlocks. Two changes in
the window. The top candidate is a deploy on a *different* service with no
dependency between them in either direction — they only share a database.
Look at the evidence lines: every claim is a named rule with its inputs;
the confidence number decomposes into rules / history / LLM. Nothing here
is a language model guessing — the LLM layer can only re-rank within ±15
points and must cite this evidence."

## Beat 2 — memory compounds (60 s)

```
python -m correlation_engine.cli demo broken_scraping
```

Point at the `precedent:` line: "It's citing a *different* past incident
with the same failure shape, and the resolution that fixed it. The system
gets faster the more incidents it has seen — that's the retention story."

## Beat 3 — their data (90 s)

Show `culprit diagnose --help`. Talk track: "This is the ask. After your
next incident: `kubectl get events -o json` to a file, a JSON list of
recent changes, one command. Nothing installed in your cluster, no
credentials leave your laptop, works offline. If the verdict is right,
tell me; if it's wrong, *definitely* tell me — wrong verdicts are what I'm
buying with the free tier."

## Encore, if asked — the UI

`cd apps/web && npm run dev` → `/incidents` → open the incident they just
saw in the terminal → expand "Why N%?". Same data, same breakdown.

## Do not

- Do not claim live cluster collection, EKS deployment, or auto-remediation
  exist — propose-only, file-based, and the README's proven-vs-designed
  section is the source of truth.
- Do not demo a scenario you haven't run that morning.
- Do not argue with "tool X does this" — write it down (tracker), ask what
  X gets wrong, move on.
