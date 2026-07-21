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

Optional (Beat 2.5 only) — if you'll show the LLM narration, prep it the
morning of and confirm the guardrail line actually appears:

```
pip install -e . -e ../ai-reasoning     # both packages, so --explain can import the LLM layer
export ANTHROPIC_API_KEY=...
cat > /tmp/demo-deploys.json <<'JSON'
[{"service":"checkout-service","occurred_at":"2026-07-22T09:00:00Z","summary":"bump logging library","sha":"aaa111"},
 {"service":"checkout-service","occurred_at":"2026-07-22T09:31:00Z","summary":"reduce db.connectionPoolSize 50 -> 10","sha":"bbb222"}]
JSON
python -m correlation_engine.cli diagnose --explain \
  --alert-title "DB connection pool exhausted" --alert-service checkout-service \
  --fired-at 2026-07-22T09:32:30Z --deploys-file /tmp/demo-deploys.json
```

If the key isn't working that morning, **skip Beat 2.5** and lean on the
Beat 1 talk track — never run it live unrehearsed.

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

## Beat 2.5 — the AI, on a leash (60 s, optional; needs the key from Setup)

Run the prepared `diagnose --explain` command. Point at the **AI
EXPLANATION** block, then at the two lines under it:

Talk track: "Every AIOps tool now bolts an LLM on and calls it a day. The
question you actually have at 2am is 'can I trust it enough to act.' So
watch what this one is *not* allowed to do. The narration is on top of the
same deterministic evidence you already saw — and its confidence adjustment
is capped: see `LLM adjustment ±N%, bounded to ±15%`. It can nuance the
number, it can't manufacture certainty. And every fact it cites is checked
against the real evidence objects — anything it invents shows up on the
`guardrail stripped ungrounded citations` line and gets thrown out. The
deterministic verdict is what's authoritative; the model explains it, it
doesn't get to overrule it."

Why this beat lands: it inverts the usual AI-tool pitch. You're selling the
*constraints*, which is exactly what a skeptical SRE is listening for.

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
- Do not demo a scenario you haven't run that morning — including Beat 2.5:
  if `--explain` didn't produce the guardrail line in Setup, skip it.
- Do not oversell Beat 2.5 — it's optional. The deterministic verdict is
  the product; the LLM narration is a trust aid, not the pitch. Never imply
  the model decides the answer.
- Do not argue with "tool X does this" — write it down (tracker), ask what
  X gets wrong, move on.
