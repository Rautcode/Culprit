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

    @classmethod
    def from_edges(cls, edges: tuple[ServiceEdge, ...]) -> "KnowledgeGraph":
        graph = cls()
        for edge in edges:
            if edge.edge_type == "depends_on":
                graph._downstream[edge.from_service].append(edge.to_service)
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

    def downstream_count(self, service: str, max_hops: int = MAX_HOPS) -> int:
        """Blast radius: number of distinct services reachable within
        max_hops of `depends_on` edges."""
        seen: set[str] = set()
        frontier = {service}
        for _ in range(max_hops):
            next_frontier: set[str] = set()
            for svc in frontier:
                for nxt in self._downstream.get(svc, ()):
                    if nxt not in seen:
                        seen.add(nxt)
                        next_frontier.add(nxt)
            frontier = next_frontier
        return len(seen)
