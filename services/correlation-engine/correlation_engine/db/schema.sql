-- Culprit — Postgres schema, implemented subset of docs/05-database.md.
-- Idempotent (IF NOT EXISTS / ON CONFLICT) so applying it is always safe.
--
-- Multi-tenancy: org_id columns exist from day one (the roadmap's
-- "schema-correct from the start" promise); a default organization is
-- seeded and RLS policies arrive with multi-tenant signup (Phase 2), not
-- before there are two tenants to isolate.
--
-- Deviations from docs/05, named:
--   * external_id columns on deploy_events/alerts — the natural idempotency
--     key from docs/06-api-design.md (webhook retries dedupe on it).
--   * k8s_events — an evidence table docs/05 folded into timeline/S3 blobs;
--     a plain table is the correct size at this scale.
--   * resolved_incidents — the incident-memory store (memory.py), with
--     embedding columns for PgVectorIncidentMemory (embeddings.py). The
--     columns are untyped `vector` so the dimension follows the configured
--     embedder; one embedder per store — re-embed everything on a switch.

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS organizations (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name          text NOT NULL,
    plan          text NOT NULL DEFAULT 'trial',
    created_at    timestamptz NOT NULL DEFAULT now()
);

INSERT INTO organizations (id, name, plan)
VALUES ('00000000-0000-0000-0000-000000000001', 'default', 'trial')
ON CONFLICT (id) DO NOTHING;

CREATE TABLE IF NOT EXISTS services (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id        uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    name          text NOT NULL,
    namespace     text,
    created_at    timestamptz NOT NULL DEFAULT now(),
    UNIQUE (org_id, name)
);

CREATE TABLE IF NOT EXISTS service_edges (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    from_service_id uuid NOT NULL REFERENCES services(id) ON DELETE CASCADE,
    to_service_id   uuid NOT NULL REFERENCES services(id) ON DELETE CASCADE,
    edge_type       text NOT NULL,  -- depends_on|owned_by|deployed_via|shares_namespace|monitored_by (ADR 0002)
    source          text NOT NULL DEFAULT 'manual',
    discovered_at   timestamptz NOT NULL DEFAULT now(),
    UNIQUE (org_id, from_service_id, to_service_id, edge_type)
);
CREATE INDEX IF NOT EXISTS idx_service_edges_from ON service_edges (org_id, from_service_id);
CREATE INDEX IF NOT EXISTS idx_service_edges_to   ON service_edges (org_id, to_service_id);

CREATE TABLE IF NOT EXISTS deploy_events (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id        uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    service_id    uuid NOT NULL REFERENCES services(id) ON DELETE CASCADE,
    external_id   text NOT NULL,
    source        text NOT NULL,
    git_sha       text,
    diff_summary  jsonb NOT NULL DEFAULT '{}',
    deployed_by   text NOT NULL DEFAULT 'unknown',
    occurred_at   timestamptz NOT NULL,
    created_at    timestamptz NOT NULL DEFAULT now(),
    UNIQUE (org_id, external_id)
);
CREATE INDEX IF NOT EXISTS idx_deploy_events_service_time ON deploy_events (service_id, occurred_at DESC);

CREATE TABLE IF NOT EXISTS alerts (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id        uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    service_id    uuid REFERENCES services(id),
    external_id   text NOT NULL,
    source        text NOT NULL DEFAULT 'import',
    title         text NOT NULL,
    severity      text NOT NULL,
    fired_at      timestamptz NOT NULL,
    resolved_at   timestamptz,
    UNIQUE (org_id, external_id)
);
CREATE INDEX IF NOT EXISTS idx_alerts_org_fired ON alerts (org_id, fired_at DESC);

CREATE TABLE IF NOT EXISTS k8s_events (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    namespace       text NOT NULL,
    involved_object text NOT NULL,
    reason          text NOT NULL,
    message         text NOT NULL DEFAULT '',
    occurred_at     timestamptz NOT NULL,
    UNIQUE (org_id, involved_object, reason, occurred_at)
);

CREATE TABLE IF NOT EXISTS resolved_incidents (
    org_id              uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    incident_id         text NOT NULL,
    title               text NOT NULL,
    culprit_service     text NOT NULL,
    root_cause_summary  text NOT NULL,
    resolution          text NOT NULL,
    resolved_at         timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (org_id, incident_id)
);

-- Embedding columns (untyped `vector` so the dimension follows the
-- configured embedder; exact scan for now — an ivfflat ANN index requires
-- a fixed dimension and becomes worthwhile past ~100k rows, both of which
-- arrive together with a committed production embedder).
ALTER TABLE resolved_incidents ADD COLUMN IF NOT EXISTS title_embedding vector;
ALTER TABLE resolved_incidents ADD COLUMN IF NOT EXISTS cause_embedding vector;
ALTER TABLE resolved_incidents ADD COLUMN IF NOT EXISTS text_embedding  vector;
