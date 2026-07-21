# Sample incident — diagnose a real one from your own cluster

A worked, runnable example of `culprit diagnose` on evidence files shaped
exactly like what you'd export from a real cluster. The incident here is a
**cross-service** one — the alert fires on `checkout-service`, but the
culprit is a config change on `payments-service`, which checkout depends on.
Naive "blame the newest deploy on the alerting service" gets this wrong;
Culprit gets it right via the dependency graph.

## Run it

From `services/correlation-engine`:

```
python -m correlation_engine.cli diagnose \
  --alert-title "checkout-service: payment request timeouts spiking" \
  --alert-service checkout-service --severity critical \
  --fired-at 2026-07-22T14:35:00Z \
  --deploys-file ../../examples/sample-incident/deploys.json \
  --events-file ../../examples/sample-incident/events.json \
  --edges-file ../../examples/sample-incident/edges.json
```

Expected: the `payments-service` timeout change (`e4f5a6b`) ranks #1 with a
1-hop `ownership_distance` and a `timeout` keyword match; the same-service
CSS deploy (`a1b2c3d`) ranks below it.

## The three files

### `deploys.json` — recent changes (required)

A JSON list of the changes that happened near the alert. Only `service` and
`occurred_at` are required; everything else improves the verdict.

| Field | Required | Notes |
|---|---|---|
| `service` | ✅ | the service the change was deployed to |
| `occurred_at` | ✅ | ISO-8601 timestamp (UTC recommended) |
| `sha` | — | commit SHA; also used as the candidate id |
| `id` | — | explicit id (falls back to `sha`, then `deploy-N`) |
| `source` | — | `github` / `argocd` / `terraform` / `helm` / … (label only) |
| `summary` | — | one line describing the change — **this is what keyword matching reads**, so include the real change ("reduce pool size 50→10"), not just "deploy" |
| `files_changed` | — | list of paths |
| `deployed_by` | — | who shipped it |

**Where to get it:** from your deploy tooling. A few sources:
- `git log --since="3 hours ago" --pretty=format:'%H %s %an'` per service.
- ArgoCD application history, or `argocd app history <app>`.
- Your CI/CD's deployment records / GitHub Deployments API.

### `events.json` — Kubernetes events (optional but valuable)

**Literally the output of `kubectl get events -o json`.** No reshaping
needed — Culprit reads the `.items[]` array (or a bare list of Event
objects). Each event needs an `involvedObject.name`, a `reason`, a
`message`, and a `lastTimestamp` or `firstTimestamp`.

**Where to get it:**
```
kubectl get events -A -o json > events.json
# or scope to the affected namespace / time window:
kubectl get events -n prod -o json > events.json
```

### `edges.json` — service dependencies (optional, unlocks cross-service)

A JSON list of `{from, to, type}` edges. `type` defaults to `depends_on`.
This is what lets Culprit connect an alert on one service to a change on
another. Without it, only same-service and time correlation apply.

| `type` | Meaning |
|---|---|
| `depends_on` | `from` calls / depends on `to` at runtime (the common one) |
| `monitored_by` | `from` is scraped by monitoring service `to` (for observability-class alerts) |
| `shares_namespace`, `owned_by`, `deployed_via` | other topology signals |

**Where to get it:** your service catalog, a service mesh's topology, or
hand-write the handful of edges around the alerting service — even 3–4 edges
covering the immediate dependencies materially improves cross-service
verdicts.

## Add memory for precedent

Run `culprit learn --memory-dsn <postgres-dsn>` on your confirmed past
incidents first, then add `--memory-dsn <same-dsn>` to the diagnose command
above — the verdict will then cite similar past incidents and the fix that
resolved them. See [SETUP.md](../../SETUP.md) Tier 1.

## Add an AI explanation

With `ANTHROPIC_API_KEY` set and the `ai-reasoning` package installed, add
`--explain` for a narrated verdict — bounded by the grounding guardrail so
it can't overclaim.
