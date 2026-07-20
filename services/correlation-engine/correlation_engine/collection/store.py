"""EvidenceStore — idempotent evidence accumulation + correlation-window assembly.

Build step 2 (Evidence Collection, SPEC_VERSION.md). Webhook providers
retry on timeout, so ingestion must be idempotent by construction
(docs/06-api-design.md): every add_* dedupes on the event's natural key
and reports whether the event was new.

Phase 1 evidence types only (deploys, alerts, k8s events) plus topology
edges — no storage for types no adapter produces yet. Postgres replaces
the in-memory dicts in Phase 2 (docs/05-database.md); the bundle()
contract is what persists.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Iterable

from ..harness.schema import AlertEvent, DeployEvent, EvidenceBundle, K8sEvent, ServiceEdge
from ..ranking.rules import TIME_WINDOW_SECONDS


class EvidenceStore:
    def __init__(self) -> None:
        self._deploys: dict[str, DeployEvent] = {}
        self._alerts: dict[str, AlertEvent] = {}
        self._k8s_events: dict[tuple, K8sEvent] = {}
        self._edges: dict[tuple, ServiceEdge] = {}

    @staticmethod
    def _put(table: dict, key, value) -> bool:
        if key in table:
            return False
        table[key] = value
        return True

    def add_deploy(self, event: DeployEvent) -> bool:
        return self._put(self._deploys, event.id, event)

    def add_alert(self, event: AlertEvent) -> bool:
        return self._put(self._alerts, event.id, event)

    def add_k8s_event(self, event: K8sEvent) -> bool:
        # k8s Events carry a uid, but it isn't preserved through our schema;
        # (object, reason, timestamp) is the natural identity of an occurrence.
        return self._put(self._k8s_events, (event.involved_object, event.reason, event.occurred_at), event)

    def add_edge(self, edge: ServiceEdge) -> bool:
        # Topology arrives from the Collector agent's discovery in production;
        # tests/harness seed it directly.
        return self._put(self._edges, (edge.from_service, edge.to_service, edge.edge_type), edge)

    def bundle(self, start: datetime, end: datetime) -> EvidenceBundle:
        """Everything inside [start, end], chronologically sorted. Topology
        edges are state, not events — always included."""
        return EvidenceBundle(
            deploys=tuple(sorted((d for d in self._deploys.values() if start <= d.occurred_at <= end), key=lambda d: d.occurred_at)),
            alerts=tuple(sorted((a for a in self._alerts.values() if start <= a.fired_at <= end), key=lambda a: a.fired_at)),
            k8s_events=tuple(sorted((e for e in self._k8s_events.values() if start <= e.occurred_at <= end), key=lambda e: e.occurred_at)),
            service_edges=tuple(self._edges.values()),
        )

    def bundle_for_alerts(self, alerts: Iterable[AlertEvent] | None = None) -> EvidenceBundle:
        """The correlation window: ±TIME_WINDOW around the alerts' firing
        span — the 'Evidence Gather' step of docs/07-ai-architecture.md.
        Defaults to every stored alert (one storm = one incident, per the
        alert_storm scenario)."""
        selected = tuple(alerts) if alerts is not None else tuple(self._alerts.values())
        if not selected:
            return EvidenceBundle(service_edges=tuple(self._edges.values()))
        window = timedelta(seconds=TIME_WINDOW_SECONDS)
        return self.bundle(
            start=min(a.fired_at for a in selected) - window,
            end=max(a.fired_at for a in selected) + window,
        )
