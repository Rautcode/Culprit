"""Event contract v1alpha1 — source of truth: libs/eventschema/v1alpha1.md
Keep this file and libs/go/eventschema/eventschema.go in sync with that table.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

EVENT_VERSION = "v1alpha1"

EVENT_TYPES: tuple[str, ...] = (
    "IncidentCreated",
    "DeploymentDetected",
    "EvidenceCollected",
    "GraphUpdated",
    "CorrelationCompleted",
    "RecommendationGenerated",
    "HumanApproved",
    "IncidentClosed",
    "LearningCompleted",
)


@dataclass(frozen=True)
class Envelope:
    event_type: str
    org_id: str
    payload: dict
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    version: str = EVENT_VERSION
    occurred_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        if self.event_type not in EVENT_TYPES:
            raise ValueError(f"unknown event_type '{self.event_type}', see libs/eventschema/v1alpha1.md")
