# ADR 0001: Event Contract v1alpha1

## Context

Go services (ingestion-api, timeline, remediation, notification, auth,
billing, collector) and Python services (correlation-engine, ai-reasoning)
need to agree on event shapes before either side writes real integration
code, or the two languages' event handling silently drifts apart the first
time someone adds a field on one side only.

## Decision

Define a single source-of-truth event contract at
`libs/eventschema/v1alpha1.md`, covering the envelope shape and the 9 event
types that trace the core loop end to end: `IncidentCreated`,
`DeploymentDetected`, `EvidenceCollected`, `GraphUpdated`,
`CorrelationCompleted`, `RecommendationGenerated`, `HumanApproved`,
`IncidentClosed`, `LearningCompleted`. `libs/py/eventschema` and
`libs/go/eventschema` implement it; the markdown file is authoritative if
they disagree.

`CorrelationCompleted` is explicitly documented as the seam between the
deterministic pipeline (Rule Engine + Knowledge Graph) and the LLM
reasoning layer — its payload may never contain LLM output. This encodes
the "LLM is not the source of truth" principle (`SPEC_VERSION.md` "v1.0
Architecture") directly into the event contract, not just prose.

Versioning: the contract version lives in the envelope's `version` field
(`v1alpha1`), not in type names. Additive, optional fields are allowed
within a version; removing or repurposing a field requires a new version
and a new ADR.

## Consequences

- Both languages can be implemented against a stable contract without
  waiting on each other.
- A future breaking change to any event forces a deliberate `v1alpha2` ADR
  instead of a silent field-meaning drift.
- The Incident Simulation Harness deliberately does **not** go through this
  event bus — it calls the pipeline in-process. This ADR's contract governs
  inter-service communication once there are multiple deployed services
  (Phase 2+ per `docs/10-roadmap.md`), not the harness's unit-test-style
  scenario runs.

## Alternatives considered

- **Protobuf/Avro schema + codegen**: rejected for v1 — real value once
  there are many producers/consumers and cross-language codegen pain, but
  overkill for 2 event producers and a markdown table that both languages
  can read directly. Revisit if schema drift actually happens in practice.
- **No shared contract, each service defines its own event shapes**:
  rejected — this is exactly the failure mode (structurally separate
  systems disagreeing about meaning) the product itself is built to
  detect and fix in *customers'* infrastructure; building it into our own
  would be an obvious inconsistency.
