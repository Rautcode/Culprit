"""Postgres backends for the two interfaces designed with a DB upgrade path.

PostgresEvidenceStore mirrors collection.store.EvidenceStore's contract
(idempotent add_*, windowed bundle assembly); PostgresIncidentMemory
extends memory.IncidentMemory with durability — incidents survive process
restarts and are shared across processes, which is the actual point of
persistence. Scoring stays the existing lexical code, deliberately: the
pgvector column and ANN retrieval land together with a real embedding
model (memory.py's named trigger), not before.

Transactions: these classes don't manage them — pass an autocommit
connection or commit yourself. Single-tenant for now: every row carries
org_id (schema-correct from day one) against the seeded default org;
multi-org plumbing arrives with Phase 2 signup.

ponytail: PostgresIncidentMemory mirrors rows into the in-process index at
construction and on learn() — stale reads across concurrent writer
processes are the ceiling; the upgrade path is scoring pushed into SQL/
pgvector when that matters.

Requires the optional dependency: pip install "correlation-engine[pg]".
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable

from ..harness.schema import AlertEvent, DeployEvent, EvidenceBundle, K8sEvent, ServiceEdge
from ..memory import IncidentMemory, ResolvedIncident
from ..ranking.rules import TIME_WINDOW_SECONDS

DEFAULT_ORG = "00000000-0000-0000-0000-000000000001"
_SCHEMA = Path(__file__).with_name("schema.sql")


def apply_schema(conn) -> None:
    conn.execute(_SCHEMA.read_text(encoding="utf-8"))


class PostgresEvidenceStore:
    def __init__(self, conn, org_id: str = DEFAULT_ORG) -> None:
        self._conn = conn
        self._org = org_id
        self._service_ids: dict[str, str] = {}

    def _service_id(self, name: str) -> str:
        if name not in self._service_ids:
            row = self._conn.execute(
                """INSERT INTO services (org_id, name) VALUES (%s, %s)
                   ON CONFLICT (org_id, name) DO UPDATE SET name = EXCLUDED.name
                   RETURNING id""",
                (self._org, name),
            ).fetchone()
            self._service_ids[name] = str(row[0])
        return self._service_ids[name]

    def add_deploy(self, event: DeployEvent) -> bool:
        cur = self._conn.execute(
            """INSERT INTO deploy_events
                   (org_id, service_id, external_id, source, git_sha, diff_summary, deployed_by, occurred_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT (org_id, external_id) DO NOTHING""",
            (self._org, self._service_id(event.service), event.id, event.source,
             event.git_sha, json.dumps(event.diff_summary), event.deployed_by, event.occurred_at),
        )
        return cur.rowcount == 1

    def add_alert(self, event: AlertEvent) -> bool:
        cur = self._conn.execute(
            """INSERT INTO alerts (org_id, service_id, external_id, title, severity, fired_at)
               VALUES (%s, %s, %s, %s, %s, %s)
               ON CONFLICT (org_id, external_id) DO NOTHING""",
            (self._org, self._service_id(event.service), event.id, event.title,
             event.severity, event.fired_at),
        )
        return cur.rowcount == 1

    def add_k8s_event(self, event: K8sEvent) -> bool:
        cur = self._conn.execute(
            """INSERT INTO k8s_events (org_id, namespace, involved_object, reason, message, occurred_at)
               VALUES (%s, %s, %s, %s, %s, %s)
               ON CONFLICT (org_id, involved_object, reason, occurred_at) DO NOTHING""",
            (self._org, event.namespace, event.involved_object, event.reason,
             event.message, event.occurred_at),
        )
        return cur.rowcount == 1

    def add_edge(self, edge: ServiceEdge) -> bool:
        cur = self._conn.execute(
            """INSERT INTO service_edges (org_id, from_service_id, to_service_id, edge_type)
               VALUES (%s, %s, %s, %s)
               ON CONFLICT (org_id, from_service_id, to_service_id, edge_type) DO NOTHING""",
            (self._org, self._service_id(edge.from_service),
             self._service_id(edge.to_service), edge.edge_type),
        )
        return cur.rowcount == 1

    def bundle(self, start: datetime, end: datetime) -> EvidenceBundle:
        deploys = tuple(
            DeployEvent(id=r[0], service=r[1], source=r[2], git_sha=r[3],
                        diff_summary=r[4], deployed_by=r[5], occurred_at=r[6])
            for r in self._conn.execute(
                """SELECT d.external_id, s.name, d.source, d.git_sha, d.diff_summary, d.deployed_by, d.occurred_at
                   FROM deploy_events d JOIN services s ON s.id = d.service_id
                   WHERE d.org_id = %s AND d.occurred_at BETWEEN %s AND %s
                   ORDER BY d.occurred_at""",
                (self._org, start, end),
            )
        )
        alerts = tuple(
            AlertEvent(id=r[0], service=r[1], title=r[2], severity=r[3], fired_at=r[4])
            for r in self._conn.execute(
                """SELECT a.external_id, s.name, a.title, a.severity, a.fired_at
                   FROM alerts a JOIN services s ON s.id = a.service_id
                   WHERE a.org_id = %s AND a.fired_at BETWEEN %s AND %s
                   ORDER BY a.fired_at""",
                (self._org, start, end),
            )
        )
        k8s_events = tuple(
            K8sEvent(namespace=r[0], involved_object=r[1], reason=r[2], message=r[3], occurred_at=r[4])
            for r in self._conn.execute(
                """SELECT namespace, involved_object, reason, message, occurred_at
                   FROM k8s_events
                   WHERE org_id = %s AND occurred_at BETWEEN %s AND %s
                   ORDER BY occurred_at""",
                (self._org, start, end),
            )
        )
        edges = tuple(
            ServiceEdge(from_service=r[0], to_service=r[1], edge_type=r[2])
            for r in self._conn.execute(
                """SELECT f.name, t.name, e.edge_type
                   FROM service_edges e
                   JOIN services f ON f.id = e.from_service_id
                   JOIN services t ON t.id = e.to_service_id
                   WHERE e.org_id = %s""",
                (self._org,),
            )
        )
        return EvidenceBundle(deploys=deploys, alerts=alerts, k8s_events=k8s_events, service_edges=edges)

    def bundle_for_alerts(self, alerts: Iterable[AlertEvent] | None = None) -> EvidenceBundle:
        if alerts is None:
            rows = self._conn.execute(
                "SELECT min(fired_at), max(fired_at) FROM alerts WHERE org_id = %s", (self._org,)
            ).fetchone()
            first, last = rows
        else:
            selected = tuple(alerts)
            first = min(a.fired_at for a in selected) if selected else None
            last = max(a.fired_at for a in selected) if selected else None
        if first is None:
            return self.bundle(datetime.min, datetime.min)  # empty window, edges still returned
        window = timedelta(seconds=TIME_WINDOW_SECONDS)
        return self.bundle(first - window, last + window)


class PostgresIncidentMemory(IncidentMemory):
    """Durable incident memory: rows in resolved_incidents, scoring in
    the inherited lexical index (mirrored at construction and on learn)."""

    def __init__(self, conn, org_id: str = DEFAULT_ORG) -> None:
        super().__init__()
        self._conn = conn
        self._org = org_id
        for row in conn.execute(
            """SELECT incident_id, title, culprit_service, root_cause_summary, resolution
               FROM resolved_incidents WHERE org_id = %s""",
            (org_id,),
        ):
            super().learn(ResolvedIncident(*row))

    def learn(self, incident: ResolvedIncident) -> None:
        self._conn.execute(
            """INSERT INTO resolved_incidents
                   (org_id, incident_id, title, culprit_service, root_cause_summary, resolution)
               VALUES (%s, %s, %s, %s, %s, %s)
               ON CONFLICT (org_id, incident_id) DO UPDATE SET
                   title = EXCLUDED.title,
                   culprit_service = EXCLUDED.culprit_service,
                   root_cause_summary = EXCLUDED.root_cause_summary,
                   resolution = EXCLUDED.resolution""",
            (self._org, incident.incident_id, incident.title, incident.culprit_service,
             incident.root_cause_summary, incident.resolution),
        )
        super().learn(incident)
