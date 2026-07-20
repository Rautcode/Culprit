"""Knowledge Graph — v1.0 frozen (SPEC_VERSION.md "v1.0 Knowledge Graph").

In-memory adjacency here (harness/tests, no DB dependency); production is
the same traversal logic against Postgres `service_edges` via recursive CTE
(see docs/05-database.md). Keeping the algorithm identical in both places —
BFS to a hop limit — means a bug found here is a bug fixed there too.
"""
from __future__ import annotations

from collections import defaultdict

from .harness.schema import ServiceEdge

MAX_HOPS = 3


class KnowledgeGraph:
    def __init__(self) -> None:
        self._downstream: dict[str, list[str]] = defaultdict(list)
        self._upstream: dict[str, list[str]] = defaultdict(list)  # reverse: who depends on me

    @classmethod
    def from_edges(cls, edges: tuple[ServiceEdge, ...]) -> "KnowledgeGraph":
        graph = cls()
        for edge in edges:
            if edge.edge_type == "depends_on":
                graph._downstream[edge.from_service].append(edge.to_service)
                graph._upstream[edge.to_service].append(edge.from_service)
        return graph

    def hop_distance(self, from_service: str, to_service: str, max_hops: int = MAX_HOPS) -> int | None:
        """Shortest number of `depends_on` hops from from_service to
        to_service, or None if unreachable within max_hops."""
        if from_service == to_service:
            return 0
        frontier = {from_service}
        seen = {from_service}
        for hop in range(1, max_hops + 1):
            next_frontier: set[str] = set()
            for svc in frontier:
                for nxt in self._downstream.get(svc, ()):
                    if nxt == to_service:
                        return hop
                    if nxt not in seen:
                        seen.add(nxt)
                        next_frontier.add(nxt)
            frontier = next_frontier
        return None

    def _downstream_distances(self, source: str, max_hops: int = MAX_HOPS) -> dict[str, int]:
        """BFS distance map of everything reachable downstream of source
        (source itself excluded)."""
        distances: dict[str, int] = {}
        frontier = {source}
        for hop in range(1, max_hops + 1):
            next_frontier: set[str] = set()
            for svc in frontier:
                for nxt in self._downstream.get(svc, ()):
                    if nxt != source and nxt not in distances:
                        distances[nxt] = hop
                        next_frontier.add(nxt)
            frontier = next_frontier
        return distances

    def coupling(self, alert_service: str, deploy_service: str, max_hops: int = MAX_HOPS) -> tuple[int, str | None] | None:
        """Causal coupling distance from the alerting service to the
        deployed service, with the shared dependency that mediates it (or
        None for a direct path). Two causal shapes count:

        1. Direct: the alerter's depends_on chain reaches the deployed
           service (deploy broke a dependency -> dependents alert).
        2. Sibling: both services depend on a common resource (a shared
           database, a shared cache) — a deploy on one co-dependent can
           break the other THROUGH that resource (deadlocks being the
           canonical case). Distance = hops(alert->shared) +
           hops(deploy->shared), so direct sharing costs 2 — deliberately
           weaker than a direct 1-hop dependency. The shared node must be
           distinct from both endpoints, so "you are my dependency" never
           re-enters through the sibling path (preserving the direction
           fix: dependents of the alerter still score zero).
        """
        if alert_service == deploy_service:
            return 0, None
        best: tuple[int, str | None] | None = None
        direct = self.hop_distance(alert_service, deploy_service, max_hops)
        if direct is not None:
            best = (direct, None)
        alert_dist = self._downstream_distances(alert_service, max_hops)
        deploy_dist = self._downstream_distances(deploy_service, max_hops)
        for shared in alert_dist.keys() & deploy_dist.keys():
            if shared in (alert_service, deploy_service):
                continue
            total = alert_dist[shared] + deploy_dist[shared]
            if total <= max_hops and (best is None or total < best[0]):
                best = (total, shared)
        return best

    def dependent_count(self, service: str, max_hops: int = MAX_HOPS) -> int:
        """Blast radius: number of distinct services that (transitively)
        depend on `service` within max_hops — i.e. how many things break if
        this service breaks. Traverses the REVERSE of depends_on edges: a
        leaf-of-the-dependency-tree service like auth (depends on nothing,
        depended on by everything) has the largest blast radius, not zero."""
        seen: set[str] = set()
        frontier = {service}
        for _ in range(max_hops):
            next_frontier: set[str] = set()
            for svc in frontier:
                for nxt in self._upstream.get(svc, ()):
                    if nxt not in seen:
                        seen.add(nxt)
                        next_frontier.add(nxt)
            frontier = next_frontier
        return len(seen)
