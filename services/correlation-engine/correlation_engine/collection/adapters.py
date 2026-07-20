"""Source adapters — raw webhook/watch payloads -> schema events.

Build step 2 (Evidence Collection, SPEC_VERSION.md). Phase 1 sources only:
GitHub deployments, Alertmanager alerts, Kubernetes events
(docs/10-roadmap.md). Each adapter is a pure function from one raw payload
to schema events; transport (HTTP server, collector agent) is deliberately
absent — that's the Go ingestion-api's job in Phase 2, per the
collapsed-monolith note in docs/03-architecture.md. Keeping normalization
pure means the harness and tests drive the exact code production will use.

Timestamps: adapters emit timezone-aware UTC datetimes (webhook payloads
are ISO8601). Hand-authored harness scenarios use naive datetimes; the two
never mix inside one bundle.
"""
from __future__ import annotations

from datetime import datetime

from ..harness.schema import AlertEvent, DeployEvent, K8sEvent


def _ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def parse_github_deployment(payload: dict) -> DeployEvent:
    """GitHub `deployment` webhook -> DeployEvent.

    The webhook doesn't carry a diff; the deployment description is the
    v1 diff summary. Enriching from the compare API is a later step.
    """
    deployment = payload["deployment"]
    return DeployEvent(
        id=f"gh-{deployment['id']}",
        # ponytail: repo name == service name until a real mapping exists
        # (services table, docs/05-database.md).
        service=payload["repository"]["name"],
        source="github",
        git_sha=deployment.get("sha"),
        diff_summary={"summary": deployment.get("description") or ""},
        deployed_by=deployment.get("creator", {}).get("login", "unknown"),
        occurred_at=_ts(deployment["created_at"]),
    )


def parse_alertmanager(payload: dict) -> tuple[AlertEvent, ...]:
    """Alertmanager webhook (may carry several grouped alerts) -> AlertEvents.

    Only `firing` alerts become events; resolutions are a later concern
    (incident close-out, not evidence gathering).
    """
    events: list[AlertEvent] = []
    for alert in payload.get("alerts", ()):
        if alert.get("status") != "firing":
            continue
        labels = alert.get("labels", {})
        events.append(
            AlertEvent(
                id=f"am-{alert['fingerprint']}",
                service=labels.get("service", "unknown"),
                title=alert.get("annotations", {}).get("summary") or labels.get("alertname", "unknown alert"),
                severity=labels.get("severity", "unknown"),
                fired_at=_ts(alert["startsAt"]),
            )
        )
    return tuple(events)


def parse_k8s_event(obj: dict) -> K8sEvent:
    """Kubernetes core/v1 Event object (as watched by the Collector) -> K8sEvent."""
    involved = obj.get("involvedObject", {})
    return K8sEvent(
        namespace=involved.get("namespace") or obj.get("metadata", {}).get("namespace", "unknown"),
        involved_object=involved.get("name", "unknown"),
        reason=obj.get("reason", ""),
        message=obj.get("message", ""),
        occurred_at=_ts(obj.get("lastTimestamp") or obj["firstTimestamp"]),
    )
