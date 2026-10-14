-- A registered tenant: one team/customer sending inference traffic through the
-- shared gateway. rate_per_sec + burst define its token bucket. baseline_* is
-- the tenant's OWN learned-normal latency/error, so health compares a tenant
-- to itself, not to a fleet average.
CREATE TABLE IF NOT EXISTS tenants (
    id                TEXT PRIMARY KEY,      -- 'search-team', 'genai-assist'
    rate_per_sec      REAL NOT NULL,         -- token-bucket refill rate
    burst             INTEGER NOT NULL,      -- token-bucket capacity
    baseline_p99_ms   REAL NOT NULL,         -- this tenant's normal p99 latency
    baseline_err_pct  REAL NOT NULL,         -- this tenant's normal error rate
    created_at        TEXT NOT NULL DEFAULT (datetime('now'))
);

-- A shared inference worker. Many tenants' requests land on the same worker.
-- version + healthy are exactly what a GitOps manifest apply changes.
CREATE TABLE IF NOT EXISTS workers (
    id        TEXT PRIMARY KEY,   -- 'w-1', 'w-2', 'w-3'
    version   TEXT NOT NULL,      -- the deployed manifest version, e.g. 'v1'
    healthy   INTEGER NOT NULL DEFAULT 1   -- 1 serving normally | 0 faulty
);

-- APPEND-ONLY per-tenant per-worker telemetry. One row per served or rejected
-- request. We never update a sample; health and burn are computed over a
-- WINDOW of these, per tenant.
CREATE TABLE IF NOT EXISTS samples (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id    TEXT NOT NULL REFERENCES tenants (id) ON DELETE CASCADE,
    worker_id    TEXT,                     -- NULL if quota-rejected before routing
    ts           TEXT NOT NULL,            -- ISO8601 sample time
    latency_ms   REAL NOT NULL,
    errored      INTEGER NOT NULL,         -- 1 the request failed | 0 it served fine
    quota_reject INTEGER NOT NULL DEFAULT 0  -- 1 the token bucket rejected it
);

-- APPEND-ONLY incident log. Every detected regression is an immutable row:
-- which tenant, what kind of error, which workers/tenants are in the blast
-- radius, and the burn evidence it was opened against.
CREATE TABLE IF NOT EXISTS incidents (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id     TEXT NOT NULL REFERENCES tenants (id) ON DELETE CASCADE,
    error_type    TEXT NOT NULL,          -- 'latency_regression' | 'error_spike'
    blast_workers TEXT NOT NULL,          -- JSON list of implicated worker ids
    blast_tenants TEXT NOT NULL,          -- JSON list of tenants sharing those workers
    evidence_json TEXT NOT NULL DEFAULT '{}',  -- the burn verdict that opened it
    opened_at     TEXT NOT NULL DEFAULT (datetime('now'))
);

-- APPEND-ONLY GitOps redeploy log. Every redeploy is a NEW immutable event:
-- which worker, from which version to which, why (linked incident), and the
-- manifest it was applied from. This is the audit trail a real Argo CD sync
-- would leave in its own application history.
CREATE TABLE IF NOT EXISTS redeploy_events (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    worker_id      TEXT NOT NULL REFERENCES workers (id) ON DELETE CASCADE,
    incident_id    INTEGER REFERENCES incidents (id),
    from_version   TEXT NOT NULL,
    to_version     TEXT NOT NULL,
    manifest_yaml  TEXT NOT NULL,
    created_at     TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Health/burn read a tenant's most recent samples; this index backs it.
CREATE INDEX IF NOT EXISTS ix_samples_tenant_ts ON samples (tenant_id, ts DESC);
-- Incident and redeploy history look up by tenant/worker.
CREATE INDEX IF NOT EXISTS ix_incidents_tenant ON incidents (tenant_id, opened_at DESC);
CREATE INDEX IF NOT EXISTS ix_redeploy_worker ON redeploy_events (worker_id, created_at DESC);
