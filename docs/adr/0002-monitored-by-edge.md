# ADR 0002: `monitored_by` edge type for monitoring topology

**Status:** Accepted · **Date:** 2026-07-20 · **Amends:** SPEC_VERSION.md § v1.0 Knowledge Graph (user-directed)

## Context

The `broken_scraping` scenario — a Prometheus scrape-config change causing
absent-metrics alerts on multiple services — was deferred from the Phase 2
scenario batch because the Knowledge Graph could not represent its causal
path. Services do not `depends_on` their monitoring stack: when Prometheus
breaks, the services keep serving traffic; only observability dies. With
`depends_on | owned_by | deployed_via | shares_namespace` as the frozen
edge set, a monitoring-stack change was causally invisible to every rule.

## Decision

Add a fifth edge type, `monitored_by` (`from` = the monitored service,
`to` = the monitor), with deliberately narrow semantics:

1. **Separate causal channel, not a dependency.** `monitored_by` edges are
   never ingested into the `depends_on` adjacency — they cannot create
   runtime coupling, sibling coupling, or blast radius.
2. **Observability-gated.** The monitoring path couples a deploy on the
   monitor to an alert on a monitored service **only when the alert is
   observability-shaped** (title carries markers like metrics / scrape /
   absent / telemetry / monitoring). A Prometheus deploy can never be
   ranked as a plausible cause for a checkout 500 spike.
3. **Scored as one hop** in `ownership_distance` (same as a direct
   dependency), with `monitoring_path: true` in the evidence; runtime
   coupling takes precedence when both exist. Time-proximity gating and
   the storm-correlation counter honor the same channel.
4. **Blast radius unchanged** — `blast_radius_weight` still counts runtime
   dependents only. Counting monitored services (a monitor's
   "observability blast radius") is a possible future refinement; it is
   *not* blended in silently because it would inflate monitoring-stack
   changes for non-observability incidents.

Population source in production: Prometheus target/scrape-config discovery
by the Collector agent (each scraped service gets a `monitored_by` edge to
the scraping stack).

## Consequences

- `broken_scraping` is expressible and guards the channel as a permanent
  regression; all 15 prior scenarios are bit-identical (no old scenario
  carries the edge type — verified before the scenario was added).
- The alert-classification gate introduces the system's first notion of
  alert *class* (observability vs service symptom). It is a marker list in
  `rules.py` for v1; if more classes emerge (security alerts? cost
  alerts?), classification deserves its own module — that is the trigger,
  not speculation.

## Alternatives considered

- **Model monitoring as `depends_on`** — rejected: false runtime blast
  radius and false coupling for every non-observability incident.
- **A separate monitoring-topology store** — rejected: `service_edges`
  with a type discriminator already models heterogeneous edges; a second
  table/graph is infrastructure without a need.
- **Ungated monitoring coupling** — rejected: in a real cluster everything
  is monitored, so every monitoring-stack deploy would become a plausible
  cause for every alert in the window — precisely the noise an RCA tool
  exists to remove.
