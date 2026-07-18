# Part 7: API Design

REST for CRUD/resource operations, WebSocket for live incident updates,
Server-Sent Events for streaming the AI reasoning trace (cheaper and simpler
than WebSocket for one-directional token streaming). OpenAPI 3.1 spec is the
source of truth; SDKs and the frontend's typed client are generated from it,
not hand-written twice.

## Auth

- OIDC/SSO (Google Workspace, Okta, Azure AD) via the Auth Service for human
  users — issues a short-lived JWT (15 min) + refresh token.
- API keys (org-scoped, prefixed `culprit_sk_...`, hashed at rest) for the
  Collector agent and any CI/CD integration calling the API directly.
- Every request resolves to `(org_id, user_id | service_account_id, role)`
  before touching a handler — this tuple is what sets the Postgres RLS
  session variable (see [05-database.md](05-database.md)).

## REST endpoints (representative, not exhaustive)

```
POST   /v1/orgs/{org_id}/integrations              # connect GitHub/K8s/Terraform/Prometheus
GET    /v1/orgs/{org_id}/integrations
DELETE /v1/orgs/{org_id}/integrations/{id}

GET    /v1/orgs/{org_id}/services
GET    /v1/orgs/{org_id}/services/{id}

GET    /v1/orgs/{org_id}/incidents?status=investigating&severity=high&page=2&limit=25
GET    /v1/orgs/{org_id}/incidents/{id}
GET    /v1/orgs/{org_id}/incidents/{id}/timeline
GET    /v1/orgs/{org_id}/incidents/{id}/rca-candidates
POST   /v1/orgs/{org_id}/incidents/{id}/comments

GET    /v1/orgs/{org_id}/incidents/{id}/remediation-actions
POST   /v1/orgs/{org_id}/incidents/{id}/remediation-actions/{action_id}/approve
POST   /v1/orgs/{org_id}/incidents/{id}/remediation-actions/{action_id}/reject

GET    /v1/orgs/{org_id}/search?q=oomkill+checkout-service   # full-text over incidents/timeline

GET    /v1/orgs/{org_id}/audit-log?page=1&limit=50
```

Pagination: cursor-based (`?cursor=<opaque>&limit=25`) on high-volume
collections (`timeline`, `audit-log`) where offset pagination would skip/dupe
rows under concurrent writes; simple page-number pagination is fine for
low-volume, mostly-static collections (`services`, `integrations`).

Filtering: explicit query params per documented filterable field (not a
generic `?filter[x]=y` query DSL — YAGNI until a real multi-field filter UI
needs it).

## WebSocket

```
WSS /v1/orgs/{org_id}/incidents/{id}/live
```
Pushes `timeline_event.created`, `rca_candidate.created`,
`remediation_action.status_changed` as they happen, so the incident view
updates in real time while the AI is actively investigating. Auth via the
same JWT, passed as a subprotocol header at connect time (not in the URL
query string — avoids the token landing in server access logs).

## Streaming (SSE)

```
GET /v1/orgs/{org_id}/incidents/{id}/reasoning-stream
```
Streams the AI Reasoning Service's tool-use trace and token-by-token
explanation as it investigates — this is the "watch the AI work" experience
in the UI (see [08-ui-design.md](08-ui-design.md)), and it matters for trust:
an SRE is far more likely to approve a proposed rollback if they watched the
reasoning unfold rather than received an opaque verdict.

## Webhooks (inbound, from customer's tools)

```
POST /v1/webhooks/github/{integration_id}       # HMAC-signed, verified before processing
POST /v1/webhooks/argocd/{integration_id}
POST /v1/webhooks/pagerduty/{integration_id}
POST /v1/webhooks/alertmanager/{integration_id}
```
All inbound webhooks are signature-verified and idempotency-keyed (dedupe on
`(source, external_id)`) before hitting the event bus — webhook providers
retry on timeout, so consumers must be idempotent by construction, not by
convention.

## Error format (consistent across every endpoint)

```json
{
  "error": {
    "code": "integration_not_found",
    "message": "No integration with id abc123 in this organization.",
    "request_id": "req_9f8a..."
  }
}
```
`request_id` ties directly to the trace ID in our own OpenTelemetry pipeline
— a support engineer can paste it into Grafana/Tempo and see the exact
request.

## OpenAPI

Spec lives at `docs/openapi.yaml`, generated/validated in CI
(`.github/workflows/api-contract.yml`) against actual handler
request/response types (Go: via `oapi-codegen` in reverse — handlers
implement a generated interface, so the spec and the code cannot drift).
Frontend's API client is generated from the same spec (`openapi-typescript`).

`# ponytail: no GraphQL layer. REST + a couple of WebSocket/SSE endpoints
covers every real client need here; GraphQL's flexible-querying value only
shows up with many heterogeneous clients hitting the same data differently,
which this product doesn't have.`

Continue to [07-ai-architecture.md](07-ai-architecture.md).
