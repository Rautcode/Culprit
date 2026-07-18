// Package eventschema implements the event contract v1alpha1 — source of
// truth: libs/eventschema/v1alpha1.md. Keep this file and
// libs/py/eventschema/__init__.py in sync with that table.
package eventschema

const EventVersion = "v1alpha1"

var EventTypes = []string{
	"IncidentCreated",
	"DeploymentDetected",
	"EvidenceCollected",
	"GraphUpdated",
	"CorrelationCompleted",
	"RecommendationGenerated",
	"HumanApproved",
	"IncidentClosed",
	"LearningCompleted",
}

// Envelope wraps every event on the bus. Payload is type-specific — see
// libs/eventschema/v1alpha1.md for the field set per EventType.
type Envelope struct {
	EventID    string                 `json:"event_id"`
	EventType  string                 `json:"event_type"`
	Version    string                 `json:"version"`
	OrgID      string                 `json:"org_id"`
	OccurredAt string                 `json:"occurred_at"` // RFC3339
	Payload    map[string]interface{} `json:"payload"`
}

func isKnownEventType(t string) bool {
	for _, known := range EventTypes {
		if known == t {
			return true
		}
	}
	return false
}
