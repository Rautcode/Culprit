# Event Contract v1alpha1

Source of truth for inter-service events. `libs/go/eventschema` and
`libs/py/eventschema` must match this table exactly — if they diverge, this
file is correct and the code is the bug. Version lives in the event
envelope (`version: "v1alpha1"`), not the type name: a field can be added
within v1alpha1 (additive, optional), but removing/renaming a field or
changing its meaning requires v1alpha2 and an ADR (see `docs/adr/`,
process defined in `SPEC_VERSION.md`).

## Envelope (every event)

| Field | Type | Notes |
|---|---|---|
| `event_id` | string (uuid) | |
| `event_type` | string | one of the types below |
| `version` | string | `"v1alpha1"` |
| `org_id` | string (uuid) | tenant scope, see docs/05-database.md RLS |
| `occurred_at` | string (RFC3339) | |
| `payload` | object | type-specific, see below |

## Event types

| Event | Producer | Consumers | Payload (key fields) |
|---|---|---|---|
| `IncidentCreated` | Timeline Service | Correlation Engine, Notification | `incident_id`, `primary_alert_id`, `service` |
| `DeploymentDetected` | Ingestion API | Timeline Service, Correlation Engine | `deploy_event_id`, `service`, `source`, `git_sha` |
| `EvidenceCollected` | Correlation Engine | AI Reasoning | `incident_id`, `evidence_bundle_ref` |
| `GraphUpdated` | Correlation Engine | Correlation Engine (self), Web UI (live) | `service_id`, `edges_added`, `edges_removed` |
| `CorrelationCompleted` | Correlation Engine | AI Reasoning | `incident_id`, `ranked_candidates` (rule_score + evidence — **no LLM output**) |
| `RecommendationGenerated` | AI Reasoning | Remediation Service, Web UI | `incident_id`, `rca_candidates`, `proposed_action` |
| `HumanApproved` | Remediation Service | Remediation Service (self, triggers execution), Audit Log | `incident_id`, `action_id`, `approved_by` |
| `IncidentClosed` | Timeline Service | AI Reasoning (learn step), Notification | `incident_id`, `resolution` |
| `LearningCompleted` | AI Reasoning | — (terminal) | `incident_id`, `embedding_id` |

## Rules

- Consumers must ignore unknown fields (forward compatibility).
- Producers must not remove or repurpose a field within v1alpha1 — that's a
  v1alpha2 change, recorded as an ADR.
- `CorrelationCompleted` is the seam between the deterministic layers (Rule
  Engine + Knowledge Graph) and the LLM layer — see `SPEC_VERSION.md`
  "v1.0 Architecture." Its payload never contains LLM output;
  `RecommendationGenerated` is the first event allowed to carry any.
- The Incident Simulation Harness (`services/correlation-engine/correlation_engine/harness/`)
  does not go through this event bus at all — it calls
  `pipeline.run_scenario()` directly, in-process, deterministically. Events
  are how *services* talk to each other once there are multiple processes;
  the harness's job is to prove the logic before that wiring exists.
