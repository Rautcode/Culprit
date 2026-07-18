# Scenario catalog

Every scenario is a `Scenario` (see [`../schema.py`](../schema.py)) with all
10 fields populated — a scenario without an explicit expectation isn't a
test, it's a fixture. Register a new scenario's `build()` in
[`__init__.py`](__init__.py)'s `_BUILDERS` tuple; it's then automatically
covered by `tests/test_scenarios.py`'s all-scenarios regression loop.

## Implemented

| ID | Category | Difficulty | File |
|---|---|---|---|
| `pool_exhaustion` | Database | easy | [`pool_exhaustion.py`](pool_exhaustion.py) |

## Backlog — first 10, in build priority order

Chosen because all are reproducible from Phase 1's actual data sources
(GitHub deploys + Kubernetes events + Prometheus alerts, see
[docs/10-roadmap.md](../../../../../docs/10-roadmap.md) Phase 1) — no
scenario here needs Terraform, service-mesh, or feature-flag ingestion,
which are Phase 2+. Scenarios needing those (IAM policy, Terraform drift,
DNS, service mesh routing, NetworkPolicy, feature flags, missing
metrics/broken scraping) are deferred to a Phase 2 catalog, not dropped.

| # | ID | Category | Description |
|---|---|---|---|
| 1 | `pool_exhaustion` | Database | done, see above |
| 2 | `crash_loop_backoff` | Kubernetes | Bad command/entrypoint change causes CrashLoopBackOff |
| 3 | `oom_killed` | Kubernetes | Resource limit reduced below actual usage, pod OOMKilled |
| 4 | `image_pull_backoff` | Kubernetes | Deploy references a nonexistent/unpushed image tag |
| 5 | `bad_configmap` | Kubernetes | ConfigMap change breaks service startup config |
| 6 | `bad_secret` | Kubernetes | Secret rotation/change breaks an auth-dependent service |
| 7 | `bad_rollout` | Deployment | A rollout introduces a regression across all replicas at once (no canary) |
| 8 | `deadlock` | Database | Schema/query change introduces a lock contention pattern |
| 9 | `slow_query` | Database | Missing index / query-shape change degrades p99 latency |
| 10 | `alert_storm` | Observability | One root cause fans out into many correlated alerts across dependent services (tests the Knowledge Graph's blast-radius grouping, not just single-alert ranking) |

Each gets a `build()` function following `pool_exhaustion.py`'s pattern:
one clear culprit, at least one decoy, evidence limited to what a Phase 1
Collector agent could actually observe.
