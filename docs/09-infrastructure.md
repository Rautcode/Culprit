# Part 10: Production Infrastructure (AWS)

100% Terraform, one module per AWS concern, one `environments/{dev,staging,prod}`
tree that composes them with per-env variables — never copy-pasted HCL
between environments.

## Network & compute

| Component | Choice | Notes |
|---|---|---|
| **VPC** | 3 AZs, public/private/data subnet tiers | Standard; data subnets (RDS/Redis) have no route to the internet gateway at all. |
| **EKS** | Managed node groups (on-demand, small) + Karpenter for burst | Runs all our own services (ingestion-api, correlation-engine, ai-reasoning, remediation, notification, auth, billing, web). |
| **ALB** | One ALB, path/host-routed via AWS Load Balancer Controller + k8s Ingress | Fronts both the API and the WebSocket/SSE endpoints (ALB supports both natively). |
| **Route53 + ACM** | Public hosted zone, ACM-issued TLS, auto-renewed | `api.culprit.dev`, `app.culprit.dev`. |
| **CloudFront** | In front of the Next.js static assets (S3 origin for build output) + ALB origin for SSR/API | Standard CDN split; not fronting the WebSocket path (CloudFront + WS adds complexity for no benefit at this scale — direct-to-ALB for WS). |

## Data

| Component | Choice | Notes |
|---|---|---|
| **RDS Postgres** | Multi-AZ, `db.r6g` family, pgvector extension enabled | Single primary DB per environment; per-org logical isolation via RLS (see [05-database.md](05-database.md)), not per-org physical databases. |
| **ElastiCache Redis** | Single replication group, Multi-AZ in prod | Session cache, rate limiting, correlation-engine memoization. |
| **S3** | `culprit-evidence-{env}` (evidence blobs, versioned, lifecycle→Glacier at 90d), `culprit-web-{env}` (static assets) | Bucket policies deny public access by default; CloudFront OAC for the web bucket. |
| **Secrets Manager** | Customer integration secrets (GitHub PAT, kubeconfig, cloud creds) + our own service credentials | Rotation enabled for our own DB credentials; customer secrets rotated on their schedule via re-auth flow. |
| **IAM** | Per-service IRSA (IAM Roles for Service Accounts) in EKS | No service shares a role; least-privilege per service (e.g. remediation-service is the *only* service with any write-capable customer-cloud permissions, and only to what that customer explicitly allow-listed). |

## Observability (self-hosted, our own stack watching our own platform)

| Component | Choice | Notes |
|---|---|---|
| **Metrics** | Prometheus (in-cluster) + Grafana | Standard `kube-prometheus-stack` Helm chart to start — not reinventing scrape config tooling. |
| **Logs** | Loki | Cheaper than CloudWatch Logs at our log volume; Grafana as the single pane of glass for metrics+logs. |
| **Traces** | Tempo | OpenTelemetry SDK in every service (Go and Python), correlated with logs via trace ID (see [06-api-design.md](06-api-design.md) error format). |
| **Alerting** | Alertmanager → our own PagerDuty | We are, unavoidably and appropriately, our own first customer for "what broke and why" — dogfooding is both good engineering practice and a strong interview story. |

## Delivery

| Component | Choice | Notes |
|---|---|---|
| **CI** | GitHub Actions, path-filtered per service (see [04-folder-structure.md](04-folder-structure.md)) | Lint → unit test → build container → push to ECR → (on merge to main) update the GitOps repo's image tag. |
| **CD** | ArgoCD, app-of-apps pattern | ArgoCD watches the `infra/k8s/argocd` manifests; CI never runs `kubectl apply` directly — every deploy is a git commit, giving us the exact deploy-metadata trail our own product needs to reason about (eating our own dog food again). |
| **Progressive delivery** | Argo Rollouts, canary strategy for `ai-reasoning` and `correlation-engine` specifically | Those two services are where a bad deploy has the highest blast radius (wrong RCA output); other services roll out standard rolling-update. |
| **Guardrail policies** | Kyverno | Enforces "no privileged pods," "no `:latest` tags," "resource requests/limits required" — cluster-level guardrails, same philosophy as the product's own remediation guardrails. |

## Scaling

- Stateless services (ingestion-api, timeline, remediation, notification,
  auth, billing) scale horizontally via HPA on CPU + request-latency custom
  metric.
- `correlation-engine` and `ai-reasoning` scale on queue depth (SQS
  `ApproximateNumberOfMessages`) rather than CPU — their work is bursty and
  IO/latency-bound (waiting on model API calls), not CPU-bound.
- RDS: read replica added only once read load on the primary actually
  justifies it (dashboard/search queries are the read-heavy path) — not
  provisioned speculatively.

## Cost optimization (infra-specific; product-level cost controls are in
[03-architecture.md](03-architecture.md))

- Karpenter with a mixed spot/on-demand provisioner for stateless EKS
  workloads; RDS/Redis always on-demand (data tier, no spot).
- S3 Intelligent-Tiering on the evidence bucket instead of hand-tuned
  lifecycle rules for MVP — revisit with explicit lifecycle policies once
  access patterns are actually known.
- Single shared EKS cluster across our own services for MVP/staging
  (namespace-isolated) — a dedicated cluster per environment only from prod
  onward, not per-service clusters (that's over-provisioning for a system
  this size).

`# ponytail: MVP explicitly skips the full Redpanda/Kafka bus (SQS+SNS
covers Phase 1 throughput), skips OpenSearch (Postgres full-text is enough
under 100k incidents), and runs one shared non-prod EKS cluster instead of
one per environment. Each has a named trigger for when to upgrade — see
10-roadmap.md.`

Continue to [10-roadmap.md](10-roadmap.md).
