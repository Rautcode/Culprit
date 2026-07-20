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
| `crash_loop_backoff` | Kubernetes | medium | [`crash_loop_backoff.py`](crash_loop_backoff.py) |
| `oom_killed` | Kubernetes | hard | [`oom_killed.py`](oom_killed.py) |
| `image_pull_backoff` | Kubernetes | medium | [`image_pull_backoff.py`](image_pull_backoff.py) |
| `bad_configmap` | Kubernetes | hard | [`bad_configmap.py`](bad_configmap.py) — first cross-service culprit (alert fires downstream of the cause) |
| `bad_secret` | Kubernetes | hard | [`bad_secret.py`](bad_secret.py) — two-hop culprit on a shared dependency; graph distance favors the decoy |
| `bad_rollout` | Deployment | hard | [`bad_rollout.py`](bad_rollout.py) — dormant app regression among three same-service deploys; no k8s events; title-token matching |
| `deadlock` | Database | hard | [`deadlock.py`](deadlock.py) — sibling culprit through a shared database; no depends_on path in either direction |
| `slow_query` | Database | hard | [`slow_query.py`](slow_query.py) — index-drop migration; sibling decoy fires all four rules and must still lose |
| `alert_storm` | Observability | hard | [`alert_storm.py`](alert_storm.py) — one root cause, four alerts across the tree; multi-alert aggregation |
| `terraform_iam_break` | Infrastructure | medium | [`terraform_iam_break.py`](terraform_iam_break.py) — first Terraform-sourced culprit; delayed cross-layer failure |
| `terraform_drift` | Infrastructure | hard | [`terraform_drift.py`](terraform_drift.py) — out-of-band console change; culprit has no git commit at all |
| `dns_failure` | Network | medium | [`dns_failure.py`](dns_failure.py) — shared-infra node (cluster-dns) with the catalog's largest blast radius |
| `feature_flag_failure` | Deployment | medium | [`feature_flag_failure.py`](feature_flag_failure.py) — flag ramp as a first-class change: no commit, no files, no rollout |
| `missing_metrics` | Observability | medium | [`missing_metrics.py`](missing_metrics.py) — absent-signal alert; service healthy, only observability broke |

## Backlog — first 10, in build priority order

Chosen because all are reproducible from Phase 1's actual data sources
(GitHub deploys + Kubernetes events + Prometheus alerts, see
[docs/10-roadmap.md](../../../../../docs/10-roadmap.md) Phase 1) — no
scenario here needs Terraform, service-mesh, or feature-flag ingestion,
which are Phase 2+.

## Phase 2 catalog

Five of the deferred Phase 2 scenarios are implemented (see the table
above): `terraform_iam_break`, `terraform_drift`, `dns_failure`,
`feature_flag_failure`, `missing_metrics` — each chosen because it
exercises an axis the engine had never seen (Terraform evidence, culprits
with no git artifact, shared-infra blast radius, non-deploy change events,
absent-signal alerts).

Still deferred, with reasons — not dropped:

| ID | Why deferred |
|---|---|
| `mesh_routing` | Its ranking mechanics (partial failure + same-service config change) duplicate bad_rollout + feature_flag coverage; add when mesh topology becomes a real evidence source. |
| `network_policy_block` | Coupling shape is identical to bad_configmap/terraform_drift (downstream alert, 1 hop); adds a symptom flavor, not an engine path. |
| `broken_scraping` | Needs monitoring-topology edges ("monitored_by") the Knowledge Graph doesn't model — a deliberate graph extension, not a scenario-writing task. |

| # | ID | Category | Description |
|---|---|---|---|
| 1 | `pool_exhaustion` | Database | done, see above |
| 2 | `crash_loop_backoff` | Kubernetes | done, see above |
| 3 | `oom_killed` | Kubernetes | done, see above |
| 4 | `image_pull_backoff` | Kubernetes | done, see above |
| 5 | `bad_configmap` | Kubernetes | done, see above |
| 6 | `bad_secret` | Kubernetes | done, see above |
| 7 | `bad_rollout` | Deployment | done, see above |
| 8 | `deadlock` | Database | done, see above |
| 9 | `slow_query` | Database | done, see above |
| 10 | `alert_storm` | Observability | done, see above — **first 10 complete** |

Each gets a `build()` function following `pool_exhaustion.py`'s pattern:
one clear culprit, at least one decoy, evidence limited to what a Phase 1
Collector agent could actually observe.
